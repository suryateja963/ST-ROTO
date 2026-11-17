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
    """Folder of a model's exported files in the location that is used (find_model)."""
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


def import_model(src_root: str, name: str, dst_root: str) -> dict:
    """Manual import (REQ-15): copy model `name` (its manifests and onnx/<name>/) from another models root into
    `dst_root` - ONLY if its source manifest records a production licence, an owner approval and a pinned revision,
    and every exported file matches its recorded size and SHA-256. Nothing is copied otherwise."""
    import shutil
    check = verify_model(name, src_root)
    bad = [c for c in check if not c["ok"]]
    if bad:
        raise ModelIntegrityError("not imported: %s" % "; ".join("%s: %s" % (c["file"], c["detail"]) for c in bad))
    os.makedirs(os.path.join(dst_root, "manifests"), exist_ok=True)
    for fn in (name + ".json", name + ".exports.json"):
        shutil.copy2(os.path.join(src_root, "manifests", fn), os.path.join(dst_root, "manifests", fn))
    dst = os.path.join(dst_root, "onnx", name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(src_root, "onnx", name), dst)
    return {"model": name, "to": dst, "files": len(check) - 1}


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
