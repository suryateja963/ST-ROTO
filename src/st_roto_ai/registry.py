"""Model registry: licence, revision, approval and checksum verification BEFORE any model file is loaded (T-056,
master prompt sections 15 and 24, rule: no unapproved model in the production set).

Layout (dev): `models/manifests/<name>.json`         source weights: repo, pinned revision, licence, approval,
                                                     SHA-256 of every downloaded file (tools/models/download_models.py)
              `models/manifests/<name>.exports.json` derived ONNX/npz/json files the runtime loads: SHA-256 and
                                                     size of each, the tool that made them and the source revision
                                                     (tools/models/register_exports.py)
              `models/onnx/<name>/...`               the exported files (git-ignored)

`verify_file(path)` raises ModelIntegrityError unless the file is listed in its model's export manifest with the
same size and SHA-256, AND the model's source manifest records an allowed licence and an owner approval. Hashing a
2 GB model takes seconds, so a successful verification is remembered per (path, size, mtime) in memory and in
`models/.verified.json`; any change of the file invalidates it. Development escape hatch: environment variable
ST_ROTO_MODEL_VERIFY=0 (reported by `status()`; never set in a release).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading

ALLOWED_LICENCES = ("apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause")   # production set (MODEL_REGISTER classes)
_LOCK = threading.Lock()
_MEM = {}


class ModelIntegrityError(RuntimeError):
    pass


def default_models_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "models")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def enabled() -> bool:
    return os.environ.get("ST_ROTO_MODEL_VERIFY", "1") != "0"


# ------------------------------------------------------------------------------------------------ locations (T-101)
LOCATION_ENV = (("user", "ST_ROTO_MODELS_USER"), ("studio", "ST_ROTO_MODELS_STUDIO"))


def roots() -> list:
    """Model storage locations in lookup order (REQ-15: user-selected, shared studio, plugin directory): [(label,
    root)]. A location is used only when its environment variable names an existing folder; ST-ROTO never creates
    one by itself. Each root has the same layout: manifests/, onnx/<name>/, weights/<name>/."""
    out = []
    for label, env in LOCATION_ENV:
        d = os.environ.get(env, "").strip()
        if d and os.path.isdir(d):
            out.append((label, os.path.abspath(d)))
    out.append(("plugin", os.path.abspath(default_models_root())))
    return out


def find_model(name: str) -> str:
    """The root whose copy of `name` is used: the first location (user, studio, plugin) that has both its manifests
    and its exported files; the plugin root if none does (callers then report it as missing)."""
    for _label, root in roots():
        if (os.path.exists(os.path.join(root, "manifests", name + ".exports.json"))
                and os.path.isdir(os.path.join(root, "onnx", name))):
            return root
    return os.path.abspath(default_models_root())


def model_dir(name: str) -> str:
    """Folder of a model's exported files in the location that is used (find_model). 'name@<version id>' names an
    archived version (T-114) of the location that is used: versions run side by side without being activated."""
    if "@" in name:
        base, vid = name.split("@", 1)
        return os.path.join(version_root(find_model(base), base, vid), "onnx", base)
    return os.path.join(find_model(name), "onnx", name)


def _infer_root(path: str):
    """The models root a file belongs to: the nearest parent with manifests/ next to the onnx/ the file is in."""
    p = os.path.abspath(path)
    while True:
        parent = os.path.dirname(p)
        if parent == p:
            return None
        if os.path.basename(p) == "onnx" and os.path.isdir(os.path.join(parent, "manifests")):
            return parent
        p = parent


def locate(path: str, models_root: str = None):
    """-> (models_root, model name, path relative to models/onnx/<name>) for a file under models/onnx/<name>/."""
    p = os.path.abspath(path)
    root = os.path.abspath(models_root or _infer_root(path) or default_models_root())
    onnx = os.path.join(root, "onnx")
    rel = os.path.relpath(p, onnx)
    if rel.startswith("..") or os.path.isabs(rel):
        raise ModelIntegrityError("%s is not inside the model folder %s" % (path, onnx))
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 2:
        raise ModelIntegrityError("%s is not inside a model's folder" % path)
    return root, parts[0], "/".join(parts[1:])


def load_manifests(name: str, models_root: str = None):
    root = models_root or default_models_root()
    out = []
    for fn in (name + ".json", name + ".exports.json"):
        p = os.path.join(root, "manifests", fn)
        if not os.path.exists(p):
            raise ModelIntegrityError("model %r is not registered: %s is missing" % (name, p))
        with open(p, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def check_source(src: dict) -> None:
    lic = (src.get("licence") or "").lower()
    if lic not in ALLOWED_LICENCES:
        raise ModelIntegrityError("model %r has licence %r, not in the production set %s"
                                  % (src.get("name"), lic, ", ".join(ALLOWED_LICENCES)))
    if not src.get("approval"):
        raise ModelIntegrityError("model %r has no recorded owner approval" % src.get("name"))
    if not src.get("revision"):
        raise ModelIntegrityError("model %r has no pinned revision" % src.get("name"))


def _stamp_path(root):
    return os.path.join(root, ".verified.json")


def _load_stamps(root):
    try:
        with open(_stamp_path(root), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_stamps(root, stamps):
    tmp = _stamp_path(root) + ".part"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(stamps, fh, indent=0, sort_keys=True)
        os.replace(tmp, _stamp_path(root))
    except OSError:
        pass                                               # read-only installs: verification still happens


def verify_file(path: str, models_root: str = None) -> dict:
    """Raise ModelIntegrityError unless `path` is a registered, approved, unmodified model file.
    Returns {"model", "file", "sha256", "cached"}."""
    if not enabled():
        return {"model": None, "file": path, "sha256": None, "cached": False, "skipped": True}
    root, name, rel = locate(path, models_root)
    src, exp = load_manifests(name, root)
    check_source(src)
    entry = exp.get("files", {}).get(rel)
    if entry is None:
        raise ModelIntegrityError("%s is not listed in %s.exports.json" % (rel, name))
    if exp.get("source_revision") != src.get("revision"):
        raise ModelIntegrityError("exports of %r were made from revision %s, but the registered weights are %s"
                                  % (name, exp.get("source_revision"), src.get("revision")))
    st = os.stat(path)
    if st.st_size != entry["bytes"]:
        raise ModelIntegrityError("%s/%s: size %d, expected %d (file changed or incomplete)"
                                  % (name, rel, st.st_size, entry["bytes"]))
    key = "%s|%d|%d|%s" % (os.path.abspath(path), st.st_size, int(st.st_mtime), entry["sha256"])
    with _LOCK:
        if _MEM.get(key):
            return {"model": name, "file": rel, "sha256": entry["sha256"], "cached": True}
        stamps = _load_stamps(root)
    if stamps.get(key):
        with _LOCK:
            _MEM[key] = True
        return {"model": name, "file": rel, "sha256": entry["sha256"], "cached": True}
    digest = sha256_file(path)
    if digest != entry["sha256"]:
        raise ModelIntegrityError("%s/%s: SHA-256 mismatch (file modified or corrupted)" % (name, rel))
    with _LOCK:
        _MEM[key] = True
        stamps = _load_stamps(root)
        stamps = {k: v for k, v in stamps.items() if not k.startswith(os.path.abspath(path) + "|")}
        stamps[key] = True
        _save_stamps(root, stamps)
    return {"model": name, "file": rel, "sha256": digest, "cached": False}


def models(models_root: str = None) -> list:
    """Every registered model: name, licence, revision, approval, whether weights / exports are present and
    whether it may be used (production licence + approval). Hashes are not computed here. Without `models_root`:
    every storage location (roots()), each row with "location", "root" and "active" (this copy is the one used)."""
    if models_root is None:
        out = []
        for label, root in roots():
            for r in models(root):
                r.update(location=label, root=root, active=(find_model(r["name"]) == root and r["exports_present"]))
                out.append(r)
        return out
    root = models_root
    md = os.path.join(root, "manifests")
    out = []
    for fn in sorted(os.listdir(md)) if os.path.isdir(md) else []:
        if not fn.endswith(".json") or fn.endswith(".exports.json"):
            continue
        with open(os.path.join(md, fn), encoding="utf-8") as fh:
            src = json.load(fh)
        name = src.get("name") or fn[:-5]
        exp_path = os.path.join(md, name + ".exports.json")
        exp = json.load(open(exp_path, encoding="utf-8")) if os.path.exists(exp_path) else None
        try:
            check_source(src); usable, reason = True, ""
        except ModelIntegrityError as e:
            usable, reason = False, str(e)
        present = bool(exp) and all(os.path.exists(os.path.join(root, "onnx", name, r)) for r in exp["files"])
        out.append({"name": name, "repo": src.get("repo"), "revision": src.get("revision"),
                    "licence": src.get("licence"), "approval": src.get("approval"), "usable": usable,
                    "reason": reason, "weights_present": os.path.isdir(os.path.join(root, "weights", name)),
                    "exports_registered": exp is not None, "exports_present": present})
    return out


def verify_model(name: str, root: str) -> list:
    """Full check of every exported file of `name` in `root`, ignoring remembered results (manager 'Verify'):
    [{"file", "ok", "detail"}]. Licence / approval / revision are checked once, as the first row."""
    out = []
    try:
        src, exp = load_manifests(name, root)
        check_source(src)
        out.append({"file": "(licence, approval, revision)", "ok": True,
                    "detail": "%s, %s, %s" % (src.get("licence"), src.get("approval"), src.get("revision"))})
    except ModelIntegrityError as e:
        return [{"file": "(manifests)", "ok": False, "detail": str(e)}]
    for rel, entry in sorted(exp.get("files", {}).items()):
        p = os.path.join(root, "onnx", name, rel)
        if not os.path.exists(p):
            out.append({"file": rel, "ok": False, "detail": "missing"}); continue
        size = os.path.getsize(p)
        if size != entry["bytes"]:
            out.append({"file": rel, "ok": False, "detail": "size %d, expected %d" % (size, entry["bytes"])}); continue
        d = sha256_file(p)
        out.append({"file": rel, "ok": d == entry["sha256"], "detail": "SHA-256 %s" % ("ok" if d == entry["sha256"]
                                                                                     else "MISMATCH")})
    return out


def remove_model(name: str, root: str) -> list:
    """Delete a model's exported files and source weights from `root` (manager 'Remove'); the manifests stay as the
    record of what was installed. Returns the deleted folders."""
    import shutil
    gone = []
    for sub in ("onnx", "weights"):
        d = os.path.join(root, sub, name)
        if os.path.isdir(d):
            shutil.rmtree(d)
            gone.append(d)
    with _LOCK:
        _MEM.clear()
    return gone


def import_model(src_root: str, name: str, dst_root: str, note: str = "", user: str = "") -> dict:
    """Manual import (REQ-15): copy model `name` (its manifests and onnx/<name>/) from another models root into
    `dst_root` - ONLY if its source manifest records a production licence, an owner approval and a pinned revision,
    and every exported file matches its recorded size and SHA-256. Nothing is copied otherwise.
    T-114: a version already installed there is ARCHIVED (versions/<name>/<id>/), never deleted, so the import can be
    rolled back; importing the version that is already active changes nothing."""
    import shutil
    check = verify_model(name, src_root)
    bad = [c for c in check if not c["ok"]]
    if bad:
        raise ModelIntegrityError("not imported: %s" % "; ".join("%s: %s" % (c["file"], c["detail"]) for c in bad))
    new_vid = version_id(load_manifests(name, src_root)[1])
    old = active_version(name, dst_root)
    if old is not None and old["id"] == new_vid:
        return {"model": name, "to": os.path.join(dst_root, "onnx", name), "files": len(check) - 1,
                "version": new_vid, "archived": None, "unchanged": True}
    archived = _archive_active(name, dst_root) if old is not None else None
    os.makedirs(os.path.join(dst_root, "manifests"), exist_ok=True)
    for fn in (name + ".json", name + ".exports.json"):
        shutil.copy2(os.path.join(src_root, "manifests", fn), os.path.join(dst_root, "manifests", fn))
    dst = os.path.join(dst_root, "onnx", name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(src_root, "onnx", name), dst)
    _history(dst_root, name, "import", archived, new_vid, note, user)
    with _LOCK:
        _MEM.clear()
    return {"model": name, "to": dst, "files": len(check) - 1, "version": new_vid, "archived": archived}


# ------------------------------------------------------------------------------------------------ versions (T-114)
# Several versions of a model side by side, one ACTIVE (the normal layout: manifests/<name>*.json + onnx/<name>/),
# the others archived as complete mini models roots: <root>/versions/<name>/<id>/{manifests/, onnx/<name>/}, so the
# same verification applies to them and 'name@id' can load one without activating it. A version id is a hash of its
# exports manifest (every file's SHA-256 + the source revision). Activation MOVES folders (models are GBs), records
# who/when in versions/<name>/history.json and is undone by 'rollback'. Source weights (weights/<name>/) are not
# versioned: the runtime never loads them.

def version_id(exports_manifest: dict) -> str:
    h = hashlib.sha256()
    h.update(str(exports_manifest.get("source_revision")).encode())
    for rel, e in sorted(exports_manifest.get("files", {}).items()):
        h.update(("%s:%s:%s;" % (rel, e.get("sha256"), e.get("bytes"))).encode())
    return h.hexdigest()[:12]


def version_root(root: str, name: str, vid: str) -> str:
    return os.path.join(root, "versions", name, vid)


def _describe(name, mroot, vid, active):
    src, exp = load_manifests(name, mroot)
    meta = {}
    mp = os.path.join(mroot, "version.json")
    if os.path.exists(mp):
        try:
            meta = json.load(open(mp, encoding="utf-8"))
        except ValueError:
            meta = {}
    files = exp.get("files", {})
    return {"id": vid, "active": active, "root": mroot, "revision": src.get("revision"), "licence": src.get("licence"),
            "approval": src.get("approval"), "tool": exp.get("tool", ""), "files": len(files),
            "bytes": sum(int(e.get("bytes", 0)) for e in files.values()), "archived_utc": meta.get("archived_utc"),
            "note": meta.get("note", "")}


def active_version(name: str, root: str):
    """The active version's description, or None if `root` has no installed copy of `name`."""
    if not (os.path.exists(os.path.join(root, "manifests", name + ".exports.json"))
            and os.path.isdir(os.path.join(root, "onnx", name))):
        return None
    return _describe(name, root, version_id(load_manifests(name, root)[1]), True)


def list_versions(name: str, root: str) -> list:
    """Active version first, then archived ones (newest archive first)."""
    out = []
    a = active_version(name, root)
    if a:
        out.append(a)
    vd = os.path.join(root, "versions", name)
    arch = []
    for vid in sorted(os.listdir(vd)) if os.path.isdir(vd) else []:
        p = os.path.join(vd, vid)
        if os.path.isdir(p) and os.path.isdir(os.path.join(p, "manifests")):
            try:
                arch.append(_describe(name, p, vid, False))
            except ModelIntegrityError:
                continue
    arch.sort(key=lambda d: d.get("archived_utc") or "", reverse=True)
    return out + arch


def history(name: str, root: str) -> list:
    p = os.path.join(root, "versions", name, "history.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _history(root, name, action, frm, to, note="", user=""):
    import datetime
    d = os.path.join(root, "versions", name)
    os.makedirs(d, exist_ok=True)
    h = history(name, root)
    h.append({"utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "action": action, "from": frm,
              "to": to, "note": note, "user": user or os.environ.get("USERNAME") or os.environ.get("USER") or ""})
    tmp = os.path.join(d, "history.json.part")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(h, fh, indent=1)
    os.replace(tmp, os.path.join(d, "history.json"))


def _archive_active(name, root, note=""):
    """MOVE the active version into versions/<name>/<id>/ (manifests copied, onnx folder moved). Returns its id.
    If that id is already archived, the active copy is identical: the active onnx folder is removed instead."""
    import datetime
    import shutil
    vid = version_id(load_manifests(name, root)[1])
    dst = version_root(root, name, vid)
    if os.path.isdir(dst):
        shutil.rmtree(os.path.join(root, "onnx", name))
    else:
        os.makedirs(os.path.join(dst, "manifests"))
        os.makedirs(os.path.join(dst, "onnx"))
        for fn in (name + ".json", name + ".exports.json"):
            shutil.copy2(os.path.join(root, "manifests", fn), os.path.join(dst, "manifests", fn))
        os.rename(os.path.join(root, "onnx", name), os.path.join(dst, "onnx", name))
        with open(os.path.join(dst, "version.json"), "w", encoding="utf-8") as fh:
            json.dump({"id": vid, "archived_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "note": note}, fh, indent=1)
    return vid


def verify_version(name: str, root: str, vid: str) -> list:
    """verify_model on an archived version (full SHA-256 of every file)."""
    return verify_model(name, version_root(root, name, vid))


def activate_version(name: str, root: str, vid: str, note: str = "", user: str = "") -> dict:
    """Make archived version `vid` the active one: verified first (licence, approval, revision, every file's
    SHA-256 - nothing changes if anything fails), then the active version is archived and `vid` moved into place.
    Callers must release loaded sessions of `name` first (Windows cannot move files a session still holds)."""
    import shutil
    src = version_root(root, name, vid)
    if not os.path.isdir(src):
        raise ModelIntegrityError("%s has no archived version %s" % (name, vid))
    bad = [c for c in verify_version(name, root, vid) if not c["ok"]]
    if bad:
        raise ModelIntegrityError("version %s not activated: %s" % (vid, "; ".join("%s: %s" % (c["file"], c["detail"])
                                                                                 for c in bad)))
    cur = active_version(name, root)
    if cur is not None and cur["id"] == vid:
        return {"model": name, "active": vid, "previous": vid, "unchanged": True}
    prev = _archive_active(name, root, note="replaced by %s" % vid) if cur is not None else None
    try:
        os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
        os.makedirs(os.path.join(root, "onnx"), exist_ok=True)
        for fn in (name + ".json", name + ".exports.json"):
            shutil.copy2(os.path.join(src, "manifests", fn), os.path.join(root, "manifests", fn))
        os.rename(os.path.join(src, "onnx", name), os.path.join(root, "onnx", name))
    except OSError:
        if prev is not None and not os.path.isdir(os.path.join(root, "onnx", name)):   # put the old one back
            _restore_from_archive(name, root, prev)
        raise
    shutil.rmtree(src)
    _history(root, name, "activate", prev, vid, note, user)
    with _LOCK:
        _MEM.clear()
    return {"model": name, "active": vid, "previous": prev}


def _restore_from_archive(name, root, vid):
    import shutil
    src = version_root(root, name, vid)
    for fn in (name + ".json", name + ".exports.json"):
        shutil.copy2(os.path.join(src, "manifests", fn), os.path.join(root, "manifests", fn))
    os.rename(os.path.join(src, "onnx", name), os.path.join(root, "onnx", name))
    shutil.rmtree(src)


def rollback(name: str, root: str, user: str = "") -> dict:
    """Re-activate the version that was active before the last import / activation (history.json)."""
    cur = active_version(name, root)
    for h in reversed(history(name, root)):
        if h.get("from") and (cur is None or h["from"] != cur["id"]) and \
                os.path.isdir(version_root(root, name, h["from"])):
            r = activate_version(name, root, h["from"], note="rollback", user=user)
            return r
    raise ModelIntegrityError("nothing to roll back to for %s (no earlier version archived)" % name)


def remove_version(name: str, root: str, vid: str) -> str:
    """Delete an ARCHIVED version (the active one cannot be removed here)."""
    import shutil
    p = version_root(root, name, vid)
    if not os.path.isdir(p):
        raise ModelIntegrityError("%s has no archived version %s" % (name, vid))
    shutil.rmtree(p)
    _history(root, name, "remove", vid, None)
    return p


def status() -> str:
    return "model verification ON" if enabled() else "model verification OFF (ST_ROTO_MODEL_VERIFY=0)"


def build_exports_manifest(name: str, models_root: str = None, tool: str = "") -> dict:
    """Hash every file under models/onnx/<name>/ into models/manifests/<name>.exports.json (run after exporting)."""
    root = models_root or default_models_root()
    src, = [json.load(open(os.path.join(root, "manifests", name + ".json"), encoding="utf-8"))]
    base = os.path.join(root, "onnx", name)
    files = {}
    for dp, _, fns in os.walk(base):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            files[os.path.relpath(p, base).replace("\\", "/")] = {"bytes": os.path.getsize(p), "sha256": sha256_file(p)}
    man = {"name": name, "source_revision": src["revision"], "tool": tool, "files": files}
    with open(os.path.join(root, "manifests", name + ".exports.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
    return man
