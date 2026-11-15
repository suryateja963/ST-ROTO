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
import shutil
import socket
import sqlite3
import threading
import zipfile

BACKUP_EXT = ".stroto"
PACKAGE_FORMAT = "st_roto.package"
PACKAGE_VERSION = 1


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
         tool_version: str = "") -> dict:
    """Portable package of an (open or closed) project. Returns the manifest."""
    base = os.path.splitext(os.path.abspath(project_path))[0]
    name = os.path.basename(base)
    tmpdb = zip_path + ".db.part"
    _snapshot(project_path, tmpdb)
    files = {}
    try:
        conn = sqlite3.connect(tmpdb)
        shots = [dict(zip(("id", "name", "source_path", "width", "height", "first_frame", "last_frame"), r))
                 for r in conn.execute("SELECT id, name, source_path, width, height, first_frame, last_frame FROM shots")]
        schema = conn.execute("PRAGMA user_version").fetchone()[0]
        if include_sources:
            for s in shots:
                if not s["source_path"]:
                    continue
                d = os.path.dirname(s["source_path"])
                for f in sorted(glob.glob(_frame_glob(s["source_path"]))):
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
        manifest = {"format": PACKAGE_FORMAT, "version": PACKAGE_VERSION, "project_name": name,
                    "created_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                    "schema": schema, "tool_version": tool_version, "shots": shots,
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
    `dest_dir`, then relink shot source paths: packaged sources -> their extracted location; others via `relink`
    {old prefix: new prefix}. Returns {"project", "manifest", "missing_sources"}."""
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
    missing = []
    conn = sqlite3.connect(project)
    try:
        for sid, sp in conn.execute("SELECT id, source_path FROM shots").fetchall():
            if not sp:
                continue
            new = sp
            if sp.startswith("@package/"):
                new = os.path.join(dest, sp[len("@package/"):]).replace("\\", "/")
            else:
                for old, rep in sorted((relink or {}).items(), key=lambda kv: -len(kv[0])):
                    if sp.replace("\\", "/").startswith(old.replace("\\", "/")):
                        new = rep.replace("\\", "/") + sp.replace("\\", "/")[len(old.replace("\\", "/")):]
                        break
            if new != sp:
                conn.execute("UPDATE shots SET source_path = ? WHERE id = ?", (new, sid))
            if not glob.glob(_frame_glob(new)):
                missing.append({"shot_id": sid, "source_path": new})
        conn.commit()
    finally:
        conn.close()
    c = check(project)
    if not c["ok"]:
        raise ValueError("unpacked project fails the integrity check: %s" % c["detail"])
    return {"project": project, "manifest": manifest, "missing_sources": missing}
