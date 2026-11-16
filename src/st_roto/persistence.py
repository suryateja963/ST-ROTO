"""Backups, crash recovery and portable project packages (T-071, master prompt section 18). Pure Python (stdlib).

What is already safe without this module: every edit is ONE SQLite transaction in WAL mode, logged with its inverse
(ADR-0006), so a crash loses at most the edit in flight, never a half-applied one. This module adds:

* `backup()`        consistent snapshot of an OPEN project (SQLite online backup API), verified, rotated;
* `AutoBackup`      background thread: snapshot every `interval` seconds, only when the operation log changed;
* `SessionMarker`   `<project>.session.json` while a process has the project open; a marker left by a process that
                    no longer runs = the previous session ended uncleanly (crash, power loss: R-38);
* `check()` / `recover()`  integrity check; a damaged file is MOVED aside (never deleted) and the newest backup
                    that passes the check is restored;
* `pack()` / `unpack()`  portable package (zip): consistent database snapshot, manifest with checksums, optional
                    mattes / exports / source frames; unpack verifies checksums, refuses unsafe paths and relinks
                    shot source paths.
Model weights are never packaged (they are referenced by id; D-008).
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import threading
import zipfile

BACKUP_EXT = ".stroto"
PACKAGE_FORMAT = "st_roto.package"
PACKAGE_VERSION = 1
ENCRYPTED_SCRIPT = "Nuke NC mode encrypted"
RELINK_SIDECAR = ".st_roto_relink.json"


def _stamp():
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")


def default_backup_dir(project_path: str) -> str:
    return os.path.splitext(os.path.abspath(project_path))[0] + "_backups"


# ------------------------------------------------------------------------------------------------ integrity
def check(path: str) -> dict:
    """{"ok", "detail", "schema", "operations"} without modifying the file (read-only connection)."""
    if not os.path.exists(path):
        return {"ok": False, "detail": "missing", "schema": None, "operations": None}
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
        try:
            res = conn.execute("PRAGMA integrity_check").fetchall()
            ok = len(res) == 1 and res[0][0] == "ok"
            schema = conn.execute("PRAGMA user_version").fetchone()[0]
            fmt = conn.execute("SELECT value FROM meta WHERE key = 'format'").fetchone()
            ops = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM operations").fetchone()[0]
            if not fmt or fmt[0] != "st-roto-project":
                return {"ok": False, "detail": "not an ST-ROTO project", "schema": schema, "operations": ops}
            return {"ok": ok, "detail": "ok" if ok else "; ".join(r[0] for r in res[:5]), "schema": schema,
                    "operations": ops}
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        return {"ok": False, "detail": "%s: %s" % (type(e).__name__, e), "schema": None, "operations": None}


def last_operation(path: str) -> int:
    conn = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    try:
        return int(conn.execute("SELECT COALESCE(MAX(seq), 0) FROM operations").fetchone()[0])
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------------ backups
def _snapshot(src_path: str, dst_path: str):
    """Consistent copy of a (possibly open, WAL) project via SQLite's online backup API."""
    tmp = dst_path + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)
    src = sqlite3.connect("file:%s?mode=ro" % src_path.replace("\\", "/"), uri=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")     # a single self-contained file
    finally:
        dst.close(); src.close()
    os.replace(tmp, dst_path)


def backup(project_path: str, backup_dir: str = None, keep: int = 20, reason: str = "auto") -> str:
    """Snapshot the project into `backup_dir` (default `<project>_backups/`), verify it, keep the newest `keep`
    backups of the same `reason` (others are never rotated away). Returns the backup path."""
    d = backup_dir or default_backup_dir(project_path)
    os.makedirs(d, exist_ok=True)
    base = os.path.splitext(os.path.basename(project_path))[0]
    path = os.path.join(d, "%s.%s.%s%s" % (base, _stamp(), reason, BACKUP_EXT))
    _snapshot(project_path, path)
    c = check(path)
    if not c["ok"]:
        os.replace(path, path + ".bad")
        raise RuntimeError("backup failed verification: %s" % c["detail"])
    for old in list_backups(project_path, d, reason)[keep:]:
        os.remove(old)
    return path


def list_backups(project_path: str, backup_dir: str = None, reason: str = None) -> list:
    """Backups of this project, newest first."""
    d = backup_dir or default_backup_dir(project_path)
    base = os.path.splitext(os.path.basename(project_path))[0]
    pat = "%s.*.%s%s" % (base, reason or "*", BACKUP_EXT)
    return sorted(glob.glob(os.path.join(glob.escape(d), pat)), reverse=True)


class AutoBackup(object):
    """Snapshot every `interval` seconds while the operation log keeps changing. Uses its own read-only
    connections, so it never blocks or touches the host's connection (SQLite WAL allows concurrent readers)."""

    def __init__(self, project_path: str, interval: float = 300.0, keep: int = 20, backup_dir: str = None):
        self.path, self.interval, self.keep, self.dir = project_path, float(interval), keep, backup_dir
        self._stop = threading.Event()
        self._last = None
        self.backups, self.errors = [], []
        self._thread = threading.Thread(target=self._run, name="st_roto_autobackup", daemon=True)

    def start(self):
        try:
            self._last = last_operation(self.path)          # nothing new yet: no backup at start
        except sqlite3.Error:
            self._last = None
        self._thread.start()
        return self

    def tick(self) -> str:
        """One check (also callable directly, e.g. on script save). Returns a backup path or None."""
        try:
            seq = last_operation(self.path)
            if seq == self._last:
                return None
            p = backup(self.path, self.dir, self.keep, "auto")
            self._last = seq
            self.backups.append(p)
            return p
        except Exception as e:                              # never let a backup failure hurt the artist's session
            self.errors.append("%s: %s" % (type(e).__name__, e))
            return None

    def _run(self):
        while not self._stop.wait(self.interval):
            self.tick()

    def stop(self, final: bool = True):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        if final:
            self.tick()


# ------------------------------------------------------------------------------------------------ sessions
def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))         # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259               # STILL_ACTIVE
    try:
        os.kill(pid, 0)                                     # POSIX only (on Windows os.kill would terminate)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class SessionMarker(object):
    """`<project>.session.json` while this process has the project open.

    `previous` after `acquire()`: None (clean), or the marker found: with "state" = "crashed" (its process is gone
    on this machine), "open_elsewhere" (another live process here) or "other_host" (cannot tell)."""

    def __init__(self, project_path: str):
        self.path = os.path.abspath(project_path) + ".session.json"
        self.previous = None

    def acquire(self, info: dict = None) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as fh:
                    prev = json.load(fh)
            except (OSError, ValueError):
                prev = {"pid": -1, "host": socket.gethostname()}
            if prev.get("host") != socket.gethostname():
                prev["state"] = "other_host"
            elif prev.get("pid") != os.getpid() and _pid_alive(int(prev.get("pid", -1))):
                prev["state"] = "open_elsewhere"
            elif prev.get("pid") == os.getpid():
                prev = None                                  # our own marker (re-open in the same process)
            else:
                prev["state"] = "crashed"
            self.previous = prev
        mine = dict(info or {}, pid=os.getpid(), host=socket.gethostname(),
                    started_utc=datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z")
        tmp = self.path + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(mine, fh)
        os.replace(tmp, self.path)
        return self.previous

    def release(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                if json.load(fh).get("pid") != os.getpid():
                    return                                   # someone else's marker: leave it
            os.remove(self.path)
        except (OSError, ValueError):
            pass


def recover(project_path: str, backup_dir: str = None) -> dict:
    """If the project fails the integrity check: move it (and its -wal/-shm) aside as `.damaged.<stamp>` and
    restore the newest backup that passes. Returns {"action": "none"|"restored"|"failed", ...}."""
    c = check(project_path)
    if c["ok"]:
        return {"action": "none", "check": c}
    stamp = _stamp()
    moved = []
    for suffix in ("", "-wal", "-shm"):
        p = project_path + suffix
        if os.path.exists(p):
            dst = "%s.damaged.%s%s" % (project_path, stamp, suffix)
            os.replace(p, dst)
            moved.append(dst)
    for b in list_backups(project_path, backup_dir):
        bc = check(b)
        if bc["ok"]:
            shutil.copy2(b, project_path)
            return {"action": "restored", "from": b, "operations": bc["operations"], "damaged": moved, "check": c}
    return {"action": "failed", "damaged": moved, "check": c, "detail": "no valid backup found"}


# ------------------------------------------------------------------------------------------------ packages
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _frame_glob(pattern: str) -> str:
    """Nuke-style sequence path (####, %04d) -> glob pattern."""
    import re
    g = re.sub(r"#+", "*", pattern)
    return re.sub(r"%0?\d*d", "*", g)


def pack(project_path: str, zip_path: str, include_dirs=("_mattes", "_export"), include_sources: bool = False,
         tool_version: str = "", scripts=()) -> dict:
    """Portable package of an (open or closed) project. `scripts`: Nuke scripts to include (scripts/<name>); on
    unpack their paths to the project, its folders and the plates are rewritten. Returns the manifest."""
    base = os.path.splitext(os.path.abspath(project_path))[0]
    name = os.path.basename(base)
    tmpdb = zip_path + ".db.part"
    _snapshot(project_path, tmpdb)
    files = {}
    try:
        conn = sqlite3.connect(tmpdb)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(shots)")]
        want = [c for c in ("id", "name", "source_path", "source_fingerprint", "width", "height", "first_frame",
                            "last_frame") if c in cols]
        shots = [dict(zip(want, r)) for r in conn.execute("SELECT %s FROM shots" % ", ".join(want))]
        schema = conn.execute("PRAGMA user_version").fetchone()[0]
        if include_sources:
            for s in shots:
                if not s["source_path"]:
                    continue
                d = os.path.dirname(s["source_path"])
                for f in sequence_files(s["source_path"]):
                    files["sources/%s/%s" % (s["id"], os.path.basename(f))] = f
                rel = "sources/%s/%s" % (s["id"], os.path.basename(s["source_path"]))
                conn.execute("UPDATE shots SET source_path = ? WHERE id = ?", ("@package/" + rel, s["id"]))
                s["packaged_source"] = rel
                s["original_dir"] = d
            conn.commit()
        conn.close()
        files["project" + BACKUP_EXT] = tmpdb
        for suffix in include_dirs:
            root = base + suffix
            for dp, _, fns in os.walk(root):
                for fn in fns:
                    full = os.path.join(dp, fn)
                    files["%s/%s" % (suffix.strip("_"), os.path.relpath(full, root).replace("\\", "/"))] = full
        script_names = []
        for sp in scripts or ():
            arc = "scripts/" + os.path.basename(sp)
            files[arc] = sp
            script_names.append(arc)
        manifest = {"format": PACKAGE_FORMAT, "version": PACKAGE_VERSION, "project_name": name,
                    "original_project": os.path.abspath(project_path).replace("\\", "/"),
                    "created_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    "schema": schema, "tool_version": tool_version, "shots": shots, "scripts": script_names,
                    "files": {arc: {"sha256": _sha256(src), "bytes": os.path.getsize(src)} for arc, src in files.items()},
                    "not_included": ["model weights (referenced by model id; install separately)"]}
        tmpzip = zip_path + ".part"
        with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=1, sort_keys=True))
            for arc, src in files.items():
                z.write(src, arc)
        os.replace(tmpzip, zip_path)
    finally:
        if os.path.exists(tmpdb):
            os.remove(tmpdb)
    return manifest


def unpack(zip_path: str, dest_dir: str, relink: dict = None) -> dict:
    """Extract a package into `dest_dir` (must be empty or new), verify every checksum, refuse paths escaping
    `dest_dir`, then relink: shot source paths (packaged sources -> their extracted location; others via `relink`
    {old prefix: new prefix}) and, in packaged Nuke scripts, the project path, its folders and the plate paths.
    Relinked sources are checked against the recorded fingerprints.
    Returns {"project", "manifest", "missing_sources", "fingerprints": {shot id: state}, "scripts"}."""
    dest = os.path.abspath(dest_dir)
    if os.path.exists(dest) and os.listdir(dest):
        raise ValueError("destination is not empty: %s" % dest)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != PACKAGE_FORMAT:
            raise ValueError("not an ST-ROTO package")
        if int(manifest.get("version", 0)) > PACKAGE_VERSION:
            raise ValueError("package version %s is newer than this ST-ROTO" % manifest.get("version"))
        for arc in manifest["files"]:
            target = os.path.abspath(os.path.join(dest, arc))
            if os.path.commonpath([dest, target]) != dest:
                raise ValueError("unsafe path in package: %r" % arc)
        for arc, meta in manifest["files"].items():
            target = os.path.join(dest, arc)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(arc) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            if _sha256(target) != meta["sha256"]:
                raise ValueError("checksum mismatch for %s" % arc)
    project = os.path.join(dest, manifest["project_name"] + BACKUP_EXT)
    os.replace(os.path.join(dest, "project" + BACKUP_EXT), project)
    for suffix in ("mattes", "export"):                     # restore the <project>_<dir> layout
        d = os.path.join(dest, suffix)
        if os.path.isdir(d):
            os.replace(d, os.path.join(dest, manifest["project_name"] + "_" + suffix))
    text_map = dict(relink or {})
    if manifest.get("original_project"):
        text_map[os.path.splitext(manifest["original_project"])[0]] = os.path.splitext(project)[0].replace("\\", "/")
    missing, prints = [], {}
    conn = sqlite3.connect(project)
    try:
        has_fp = "source_fingerprint" in [r[1] for r in conn.execute("PRAGMA table_info(shots)")]
        rows = conn.execute("SELECT id, source_path, %s FROM shots" % ("source_fingerprint" if has_fp else "NULL")).fetchall()
        orig = {s["id"]: s for s in manifest.get("shots", [])}
        for sid, sp, fp in rows:
            if not sp:
                continue
            new = sp
            if sp.startswith("@package/"):
                new = os.path.join(dest, sp[len("@package/"):]).replace("\\", "/")
                od = orig.get(sid, {}).get("original_dir")
                if od:
                    text_map[od] = os.path.dirname(new)
            else:
                new = relink_path(sp, relink or {})
            if new != sp:
                conn.execute("UPDATE shots SET source_path = ? WHERE id = ?", (new, sid))
            cmp_ = compare_fingerprint(fp, new)
            prints[sid] = cmp_["state"]
            if cmp_["state"] == "missing":
                missing.append({"shot_id": sid, "source_path": new})
        conn.commit()
    finally:
        conn.close()
    scripts, encrypted = [], []
    for arc in manifest.get("scripts", []):
        p = os.path.join(dest, arc)
        if is_encrypted_script(p):
            # Non-commercial scripts are encrypted: the paths are applied after opening the script in Nuke
            # (st_roto_nuke.packages.apply_relink_to_open_script reads this sidecar)
            with open(p + RELINK_SIDECAR, "w", encoding="utf-8") as fh:
                json.dump(text_map, fh, indent=1, sort_keys=True)
            encrypted.append(p)
        else:
            with open(p, encoding="utf-8", errors="surrogateescape") as fh:
                text = fh.read()
            with open(p, "w", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write(relink_text(text, text_map))
        scripts.append(p)
    c = check(project)
    if not c["ok"]:
        raise ValueError("unpacked project fails the integrity check: %s" % c["detail"])
    return {"project": project, "manifest": manifest, "missing_sources": missing, "fingerprints": prints,
            "scripts": scripts, "encrypted_scripts": encrypted, "path_map": text_map}
def sequence_files(pattern: str) -> list:
    """Existing files of a Nuke-style sequence path (####, %04d) or a single file, sorted."""
    if not pattern:
        return []
    return sorted(glob.glob(_frame_glob(pattern)))


def fingerprint_sequence(pattern: str, first: int = None, last: int = None) -> str:
    """JSON fingerprint of a source sequence: SHA-256 + size of its first and last frame and how many frames of the
    range exist (T-075). With a frame range the shot's own first/last frames are used (a folder often holds more
    frames than the shot); without one, the first/last matching files. Returns None when nothing exists."""
    if first is not None and last is not None and re.search(r"#+|%0?\d*d", pattern or ""):
        ends = [frame_file(pattern, first), frame_file(pattern, last)]
        if not all(os.path.exists(e) for e in ends):
            return None
        count = sum(1 for f in range(first, last + 1) if os.path.exists(frame_file(pattern, f)))
    else:
        files = sequence_files(pattern)
        if not files:
            return None
        ends, count = [files[0], files[-1]], len(files)
    return json.dumps({"files": count, "first_frame": first, "last_frame": last,
                       "first": {"name": os.path.basename(ends[0]), "bytes": os.path.getsize(ends[0]), "sha256": _sha256(ends[0])},
                       "last": {"name": os.path.basename(ends[1]), "bytes": os.path.getsize(ends[1]), "sha256": _sha256(ends[1])}},
                      sort_keys=True)


def compare_fingerprint(recorded: str, pattern: str) -> dict:
    """{"state": "match" | "different" | "missing" | "unknown", "detail"} for a source path against a recorded
    fingerprint ('unknown': nothing was recorded, e.g. projects from before schema v4). The recorded frame range
    is used for the comparison."""
    rec = json.loads(recorded) if recorded else {}
    now = fingerprint_sequence(pattern, rec.get("first_frame"), rec.get("last_frame"))
    if now is None:
        return {"state": "missing", "detail": "no files at %s" % pattern}
    if not recorded:
        return {"state": "unknown", "detail": "no fingerprint recorded"}
    b = json.loads(now)
    if rec["first"]["sha256"] == b["first"]["sha256"] and rec["last"]["sha256"] == b["last"]["sha256"]:
        note = "" if rec["files"] == b["files"] else " (frame count %d -> %d)" % (rec["files"], b["files"])
        return {"state": "match", "detail": "same first and last frame" + note}
    return {"state": "different", "detail": "first/last frame content differs from the recorded footage"}


def relink_text(text: str, mapping: dict) -> str:
    """Replace path prefixes in a plain-text file (a commercial-edition .nk script), longest first, case-insensitive
    for Windows paths, / and \\ spellings."""
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        for o in {old.replace("\\", "/").rstrip("/"), old.replace("/", "\\").rstrip("\\")}:
            n = new.replace("\\", "/").rstrip("/") if "/" in o else new.replace("/", "\\").rstrip("\\")
            flags = re.IGNORECASE if re.match(r"^[A-Za-z]:[/\\]", o) else 0
            text = re.sub(re.escape(o), lambda _m, n=n: n, text, flags=flags)
    return text



def relink_shot(bus, shot_id: str, new_path: str) -> dict:
    """Point a shot at a new source path (one undoable step) after checking it against the recorded fingerprint.
    Returns the comparison; refuses 'different' footage unless the caller relinks via update_shot directly."""
    shot = bus.store.row("shots", shot_id)
    if shot is None:
        raise KeyError("no shot %s" % shot_id)
    c = compare_fingerprint(shot.get("source_fingerprint"), new_path)
    if c["state"] == "different":
        raise ValueError("refused: %s is not the recorded footage (%s)" % (new_path, c["detail"]))
    if c["state"] == "missing":
        raise ValueError("refused: %s" % c["detail"])
    fields = {"source_path": new_path}
    if c["state"] == "unknown":
        fields["source_fingerprint"] = fingerprint_sequence(new_path)
    bus.execute({"op": "update_shot", "id": shot_id, "fields": fields})
    return c


def frame_file(pattern: str, frame: int) -> str:
    """Path of one frame of a Nuke-style sequence path: '#' runs or %0Nd, negative frames as sign + (N-1) digits
    (Nuke: 'name.-002.tif' for #### and frame -2, measured)."""
    m = re.search(r"(#+)|%0?(\d*)d", pattern)
    if not m:
        return pattern
    n = len(m.group(1)) if m.group(1) else int(m.group(2) or 1)
    num = ("-" + str(-frame).zfill(max(1, n - 1))) if frame < 0 else str(frame).zfill(n)
    return pattern[:m.start()] + num + pattern[m.end():]


def relink_path(path: str, mapping: dict) -> str:
    """Apply the longest matching prefix of `mapping` to one path. Windows paths compare case-insensitively and
    with / or \\ (Nuke stores 'd:/...' even when the folder was given as 'D:\\...', measured)."""
    if not path:
        return path
    p = path.replace("\\", "/")
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        o = old.replace("\\", "/").rstrip("/")
        windows = re.match(r"^[A-Za-z]:/", o) is not None
        head = p[:len(o)]
        if (head.lower() == o.lower() if windows else head == o) and (len(p) == len(o) or p[len(o)] in "/."):
            return new.replace("\\", "/").rstrip("/") + p[len(o):]
    return path


def is_encrypted_script(path: str) -> bool:
    """Nuke Non-commercial saves scripts encrypted (measured: '.nknc' starting 'Nuke NC mode encrypted text'):
    paths in them cannot be rewritten as text; relink after opening the script in Nuke instead."""
    with open(path, "rb") as fh:
        return fh.read(len(ENCRYPTED_SCRIPT)).decode("latin-1") == ENCRYPTED_SCRIPT