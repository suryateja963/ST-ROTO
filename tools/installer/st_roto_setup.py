"""ST-ROTO setup: offline package, install, upgrade, rollback, repair, uninstall, status (T-103, REQ-210, master
prompt section 23). Pure Python 3.7+ standard library: runs with Nuke's own python.exe, no admin rights.

Layout of an install (same as the repository, so nuke_plugin/init.py finds everything relative to itself):
  <base>/<version>/{src, nuke_plugin, .tools/nuke-py311, models/{manifests, onnx}, docs, LICENSE, NOTICE}
  <base>/<version>/INSTALL_MANIFEST.json   size + SHA-256 of every installed file (repair, verification)
  <base>/install_state.json                installed versions, the active one, the previous one (rollback)
default <base> = %LOCALAPPDATA%\\ST-ROTO (user-writable: no administrator rights).
Nuke registration: a block between '# >>> ST-ROTO >>>' and '# <<< ST-ROTO <<<' in <home>/.nuke/init.py adding the
active version's nuke_plugin folder; nothing else in that file is touched. <home> = %USERPROFILE% (--home for tests).

  python st_roto_setup.py package  --out ST-ROTO-<v>.zip [--models none|tiny|all]   (from a repository checkout)
  python st_roto_setup.py package-model --model <name> [--out ST-ROTO-model-<name>.zip]  (one model, own download)
  python st_roto_setup.py install  [--source <package dir or zip>] [--base DIR] [--home DIR]
                                   (also installs every ST-ROTO-model-*.zip next to the package zip)
  python st_roto_setup.py install-model --source ST-ROTO-model-<name>.zip    (into the active version)
  python st_roto_setup.py upgrade  --source <newer package>          (= install a new version and switch to it)
  python st_roto_setup.py rollback                                   (switch back to the previous version)
  python st_roto_setup.py repair   [--source <package>]              (re-copy files whose checksum is wrong)
  python st_roto_setup.py uninstall [--keep-files]
  python st_roto_setup.py status
Never downloads anything: everything comes from the package (master prompt section 16).
"""
from __future__ import print_function

import argparse
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

APP = "ST-ROTO"
BEGIN, END = "# >>> ST-ROTO >>>", "# <<< ST-ROTO <<<"
PAYLOAD = ("src", "nuke_plugin", os.path.join(".tools", "nuke-py311"), os.path.join("models", "manifests"),
           "LICENSE", "NOTICE", "VERSION", os.path.join("docs", "USER_GUIDE_v0.md"))
MODEL_SETS = {"none": (), "tiny": ("sam2.1-hiera-tiny",),
              "all": ("sam2.1-hiera-tiny", "sam2.1-hiera-large", "vitmatte-small-composition-1k")}
SKIP_DIRS = {"__pycache__", ".git"}
MANIFEST = "INSTALL_MANIFEST.json"
MODEL_MANIFEST = "MODEL_PACKAGE_MANIFEST.json"
MODEL_PREFIX = "ST-ROTO-model-"


# ------------------------------------------------------------------------------------------------ helpers
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def default_base():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP)


def default_home():
    return os.environ.get("USERPROFILE") or os.path.expanduser("~")


def _walk(root, rel):
    p = os.path.join(root, rel)
    if os.path.isfile(p):
        yield rel
        return
    for dp, dns, fns in os.walk(p):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith((".pyc", ".pyo")):
                continue
            yield os.path.relpath(os.path.join(dp, fn), root)


def payload_files(root, models="tiny"):
    files = []
    for rel in PAYLOAD:
        if os.path.exists(os.path.join(root, rel)):
            files += list(_walk(root, rel))
    for name in MODEL_SETS[models]:
        d = os.path.join("models", "onnx", name)
        if os.path.isdir(os.path.join(root, d)):
            files += list(_walk(root, d))
    return sorted(set(f.replace("\\", "/") for f in files))


def version_of(root):
    v = os.path.join(root, "VERSION")
    if os.path.exists(v):
        return io.open(v, encoding="utf-8").read().strip()
    try:
        sha = subprocess.check_output(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                                      stderr=subprocess.DEVNULL).decode().strip()
        return "0.1.0-dev+" + sha
    except (OSError, subprocess.CalledProcessError):
        return "0.1.0-dev"


# ------------------------------------------------------------------------------------------------ package
def build_package(repo, out_zip, models="tiny"):
    """Offline package: payload/<files>, PACKAGE_MANIFEST.json (version, files with size + SHA-256), this script."""
    files = payload_files(repo, models)
    entries = {f: {"bytes": os.path.getsize(os.path.join(repo, f)), "sha256": sha256(os.path.join(repo, f))}
               for f in files}
    version = version_of(repo)
    man = {"app": APP, "version": version, "models": models, "built_utc": _now(), "files": entries}
    tmp = out_zip + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.writestr("PACKAGE_MANIFEST.json", json.dumps(man, indent=1, sort_keys=True))
        z.write(os.path.abspath(__file__), "st_roto_setup.py")
        z.writestr("VERSION", version)
        for f in files:
            z.write(os.path.join(repo, f), "payload/" + f)
    os.replace(tmp, out_zip)
    return {"zip": out_zip, "version": version, "files": len(files)}


def build_model_package(repo, name, out_zip):
    """One model as its own download (release 0.1.0: GitHub refuses files over 2 GiB, the large model is 2.05 GB):
    MODEL_PACKAGE_MANIFEST.json + payload/models/onnx/<name>/... Stored, not deflated (ONNX weights barely compress
    and the large model only fits GitHub's limit uncompressed)."""
    d = os.path.join("models", "onnx", name)
    if not os.path.isdir(os.path.join(repo, d)):
        raise ValueError("model %s is not exported in %s" % (name, repo))
    files = sorted(f.replace("\\", "/") for f in _walk(repo, d))
    entries = {f: {"bytes": os.path.getsize(os.path.join(repo, f)), "sha256": sha256(os.path.join(repo, f))}
               for f in files}
    man = {"app": APP, "kind": "model", "model": name, "built_utc": _now(), "files": entries}
    tmp = out_zip + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        z.writestr(MODEL_MANIFEST, json.dumps(man, indent=1, sort_keys=True))
        for f in files:
            z.write(os.path.join(repo, f), "payload/" + f)
    os.replace(tmp, out_zip)
    return {"zip": out_zip, "model": name, "files": len(files), "bytes": os.path.getsize(out_zip)}


def _safe_names(z):
    for n in z.namelist():                                   # refuse paths escaping the folder (zip slip)
        if os.path.isabs(n) or ".." in n.replace("\\", "/").split("/"):
            raise ValueError("unsafe path in package: %s" % n)


def _write_install_manifest(d, files):
    p = os.path.join(d, MANIFEST)
    man = json.load(io.open(p, encoding="utf-8"))
    man["files"] = files
    tmp = p + ".part"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(man, indent=1))
    os.replace(tmp, p)


def _expected_model_files(d, name):
    """Checksums the installed ST-ROTO version expects for model <name> (models/manifests/<name>.exports.json)."""
    p = os.path.join(d, "models", "manifests", "%s.exports.json" % name)
    if not os.path.exists(p):
        raise ValueError("this ST-ROTO version does not know the model %s (no %s)" % (name, os.path.basename(p)))
    return json.load(io.open(p, encoding="utf-8"))["files"]


def _check_model_files(d, name, entries):
    """entries: {models/onnx/<name>/<rel>: {bytes, sha256}} already verified against the files. Every file the
    version's export manifest lists must be there with the same checksum."""
    pre = "models/onnx/%s/" % name
    for rel, e in sorted(_expected_model_files(d, name).items()):
        m = entries.get(pre + rel)
        if not m or m["sha256"] != e["sha256"]:
            raise ValueError("model %s does not match this ST-ROTO version: %s %s" % (
                name, rel, "missing" if not m else "has another checksum"))


def install_model(source, base=None, version=None):
    """Install a model package (ST-ROTO-model-<name>.zip) into an installed ST-ROTO version (default: the active
    one). Checked twice before anything is replaced: against the package's own manifest and against the
    version's model export manifest. The model folder appears complete or not at all."""
    base = base or default_base()
    version = version or load_state(base)["active"]
    if not version or not os.path.isdir(os.path.join(base, version)):
        raise ValueError("install ST-ROTO itself first (no installed version in %s)" % base)
    d = os.path.join(base, version)
    with zipfile.ZipFile(source) as z:
        _safe_names(z)
        if MODEL_MANIFEST not in z.namelist():
            raise ValueError("%s is not an ST-ROTO model package" % source)
        man = json.loads(z.read(MODEL_MANIFEST).decode("utf-8"))
        name = man["model"]
        pre = "models/onnx/%s/" % name
        if any(not rel.startswith(pre) for rel in man["files"]):
            raise ValueError("model package %s holds files outside %s" % (source, pre))
        _check_model_files(d, name, man["files"])
        work = tempfile.mkdtemp(prefix="st_roto_model_", dir=base)   # same drive: the final rename is atomic
        try:
            bad = []
            for rel, e in sorted(man["files"].items()):
                t = os.path.join(work, rel)
                os.makedirs(os.path.dirname(t), exist_ok=True)
                with z.open("payload/" + rel) as fi, open(t, "wb") as fo:
                    shutil.copyfileobj(fi, fo, 1 << 22)
                if os.path.getsize(t) != e["bytes"] or sha256(t) != e["sha256"]:
                    bad.append(rel)
            if bad:
                raise ValueError("model package damaged, nothing installed: %d file(s) wrong, e.g. %s"
                                 % (len(bad), bad[0]))
            target = os.path.join(d, "models", "onnx", name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.isdir(target):
                shutil.rmtree(target)
            _rename_retry(os.path.join(work, "models", "onnx", name), target)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    files = json.load(io.open(os.path.join(d, MANIFEST), encoding="utf-8"))["files"]
    files = {k: v for k, v in files.items() if not k.startswith(pre)}
    files.update(man["files"])
    _write_install_manifest(d, files)
    return {"model": name, "version": version, "files": len(man["files"])}


def model_packages_near(path):
    """ST-ROTO-model-*.zip files in the folder of <path> (a file or a folder)."""
    d = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    return [os.path.join(d, f) for f in sorted(os.listdir(d))
            if f.startswith(MODEL_PREFIX) and f.lower().endswith(".zip")]


def _carry_models(base, old, new):
    """After an upgrade: copy models the new package does not contain from the previous version, if they are
    exactly what the new version expects (re-hashed), so a 2 GB model need not be downloaded again."""
    od, nd = os.path.join(base, old), os.path.join(base, new)
    src_root = os.path.join(od, "models", "onnx")
    if not os.path.isdir(src_root):
        return []
    carried = []
    files = json.load(io.open(os.path.join(nd, MANIFEST), encoding="utf-8"))["files"]
    for name in sorted(os.listdir(src_root)):
        if os.path.isdir(os.path.join(nd, "models", "onnx", name)):
            continue
        pre = "models/onnx/%s/" % name
        entries = {}
        for rel in _walk(od, os.path.join("models", "onnx", name)):
            rel = rel.replace("\\", "/")
            p = os.path.join(od, rel)
            entries[rel] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}
        try:
            _check_model_files(nd, name, entries)
        except ValueError:
            continue                                         # not what the new version expects: leave it behind
        stage = os.path.join(nd, "models", "onnx", name + ".copying")
        shutil.rmtree(stage, ignore_errors=True)
        shutil.copytree(os.path.join(src_root, name), stage)
        _rename_retry(stage, os.path.join(nd, "models", "onnx", name))
        files = {k: v for k, v in files.items() if not k.startswith(pre)}
        files.update(entries)
        carried.append(name)
    if carried:
        _write_install_manifest(nd, files)
    return carried


def open_source(source):
    """A package (zip or extracted folder) or a repository checkout -> (payload root, manifest, cleanup dir)."""
    if source.lower().endswith(".zip"):
        d = tempfile.mkdtemp(prefix="st_roto_pkg_")
        with zipfile.ZipFile(source) as z:
            _safe_names(z)
            z.extractall(d)
        source, cleanup = d, d
    else:
        cleanup = None
    pm = os.path.join(source, "PACKAGE_MANIFEST.json")
    if os.path.exists(pm):
        man = json.load(io.open(pm, encoding="utf-8"))
        return os.path.join(source, "payload"), man, cleanup
    files = payload_files(source)                            # repository checkout (development install)
    man = {"app": APP, "version": version_of(source), "files": {
        f: {"bytes": os.path.getsize(os.path.join(source, f)), "sha256": sha256(os.path.join(source, f))}
        for f in files}}
    return source, man, cleanup


def _rename_retry(src, dst, tries=40, wait=0.25):
    """Rename a freshly written folder. On Windows a virus scanner or the search indexer briefly holds new files open
    and the rename fails with 'Access is denied' (measured: 1,628 files just copied, T-103); retry for ~10 s."""
    import time
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise PermissionError("could not move %s to %s: files are still in use (virus scanner?). Run the "
                                      "same command again." % (src, dst))
            time.sleep(wait)


# ------------------------------------------------------------------------------------------------ state + Nuke
def _now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _state_path(base):
    return os.path.join(base, "install_state.json")


def load_state(base):
    try:
        return json.load(io.open(_state_path(base), encoding="utf-8"))
    except (OSError, ValueError):
        return {"versions": [], "active": None, "previous": None}


def save_state(base, st):
    os.makedirs(base, exist_ok=True)
    tmp = _state_path(base) + ".part"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(st, indent=1))
    os.replace(tmp, _state_path(base))


def _init_py(home):
    return os.path.join(home, ".nuke", "init.py")


def register(home, plugin_dir):
    """Write (or replace) ST-ROTO's block in <home>/.nuke/init.py; every other line stays as it was."""
    p = _init_py(home)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    text = io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    text = _strip_block(text)
    block = "%s\n# Added by ST-ROTO setup (st_roto_setup.py). Remove with 'st_roto_setup.py uninstall'.\n" \
            "import nuke\nnuke.pluginAddPath(%r)\n%s\n" % (BEGIN, plugin_dir.replace("\\", "/"), END)
    if text and not text.endswith("\n"):
        text += "\n"
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(text + block)


def _strip_block(text):
    """The text without ST-ROTO's block (everything between and including the markers)."""
    if BEGIN not in text:
        return text
    a = text.index(BEGIN)
    b = text.index(END, a) + len(END)
    return text[:a] + text[b:].lstrip("\n")


def unregister(home):
    p = _init_py(home)
    if not os.path.exists(p):
        return False
    text = io.open(p, encoding="utf-8").read()
    if BEGIN not in text:
        return False
    new = _strip_block(text)
    if not new.strip():                                      # only our block was there: the file was ours
        os.remove(p)
    else:
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(new)
    return True


def registered_plugin(home):
    p = _init_py(home)
    if not os.path.exists(p):
        return None
    text = io.open(p, encoding="utf-8").read()
    if BEGIN not in text:
        return None
    seg = text[text.index(BEGIN):text.index(END)]
    for line in seg.splitlines():
        if line.startswith("nuke.pluginAddPath("):
            return line[len("nuke.pluginAddPath("):].strip().rstrip(")").strip("'\"")
    return None


# ------------------------------------------------------------------------------------------------ commands
def install(source, base=None, home=None, activate=True):
    base, home = base or default_base(), home or default_home()
    root, man, cleanup = open_source(source)
    try:
        version = man["version"]
        dst = os.path.join(base, version)
        bad = []
        for rel, e in sorted(man["files"].items()):
            src = os.path.join(root, rel)
            if not os.path.exists(src) or os.path.getsize(src) != e["bytes"] or sha256(src) != e["sha256"]:
                bad.append(rel)
        if bad:
            raise ValueError("package damaged, nothing installed: %d file(s) wrong, e.g. %s" % (len(bad), bad[0]))
        tmp = dst + ".installing"
        shutil.rmtree(tmp, ignore_errors=True)
        for rel in man["files"]:
            t = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copy2(os.path.join(root, rel), t)
        with io.open(os.path.join(tmp, MANIFEST), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"version": version, "installed_utc": _now(), "files": man["files"]}, indent=1))
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        _rename_retry(tmp, dst)                              # the version appears complete or not at all
    finally:
        if cleanup:
            shutil.rmtree(cleanup, ignore_errors=True)
    st = load_state(base)
    carried = []
    if st["active"] and st["active"] != version and os.path.isdir(os.path.join(base, st["active"])):
        carried = _carry_models(base, st["active"], version)
    if version not in st["versions"]:
        st["versions"].append(version)
    if activate:
        if st["active"] and st["active"] != version:
            st["previous"] = st["active"]
        st["active"] = version
        register(home, os.path.join(dst, "nuke_plugin"))
    save_state(base, st)
    return {"version": version, "path": dst, "files": len(man["files"]), "active": st["active"],
            "models_carried_over": carried}


def rollback(base=None, home=None):
    base, home = base or default_base(), home or default_home()
    st = load_state(base)
    prev = st.get("previous")
    if not prev or not os.path.isdir(os.path.join(base, prev)):
        raise ValueError("no previous version to roll back to")
    st["previous"], st["active"] = st["active"], prev
    register(home, os.path.join(base, prev, "nuke_plugin"))
    save_state(base, st)
    return {"active": prev}


def verify(base=None, version=None):
    base = base or default_base()
    version = version or load_state(base)["active"]
    if not version:
        raise ValueError("ST-ROTO is not installed in %s" % base)
    d = os.path.join(base, version)
    man = json.load(io.open(os.path.join(d, MANIFEST), encoding="utf-8"))
    bad = []
    for rel, e in sorted(man["files"].items()):
        p = os.path.join(d, rel)
        if not os.path.exists(p):
            bad.append((rel, "missing"))
        elif os.path.getsize(p) != e["bytes"] or sha256(p) != e["sha256"]:
            bad.append((rel, "changed"))
    return {"version": version, "files": len(man["files"]), "bad": bad}


def repair(source=None, base=None, home=None):
    """Re-copy the active version's missing or changed files from the package (and re-register it in Nuke)."""
    base, home = base or default_base(), home or default_home()
    v = verify(base)
    fixed = []
    if v["bad"]:
        if not source:
            raise ValueError("%d file(s) need repair; give --source <the package>" % len(v["bad"]))
        root, man, cleanup = open_source(source)
        try:
            if man["version"] != v["version"]:
                raise ValueError("package is version %s, the installed one is %s" % (man["version"], v["version"]))
            models = set()
            for rel, _why in v["bad"]:
                if rel not in man["files"] and rel.startswith("models/onnx/"):
                    models.add(rel.split("/")[2])            # a separately installed model: needs its package
                    continue
                t = os.path.join(base, v["version"], rel)
                os.makedirs(os.path.dirname(t), exist_ok=True)
                shutil.copy2(os.path.join(root, rel), t)
                fixed.append(rel)
        finally:
            if cleanup:
                shutil.rmtree(cleanup, ignore_errors=True)
        near = {}
        for p in model_packages_near(source):
            try:
                with zipfile.ZipFile(p) as z:
                    near[json.loads(z.read(MODEL_MANIFEST).decode("utf-8"))["model"]] = p
            except (KeyError, ValueError, zipfile.BadZipFile):
                pass
        for name in sorted(models):
            if name in near:
                install_model(near[name], base, v["version"])
                fixed.append("models/onnx/%s/ (model package)" % name)
    register(home, os.path.join(base, v["version"], "nuke_plugin"))
    after = verify(base)
    return {"version": v["version"], "fixed": fixed, "still_bad": after["bad"]}


def uninstall(base=None, home=None, keep_files=False):
    base, home = base or default_base(), home or default_home()
    removed = unregister(home)
    if not keep_files and os.path.isdir(base):
        st = load_state(base)
        for v in st["versions"]:
            shutil.rmtree(os.path.join(base, v), ignore_errors=True)
        if os.path.exists(_state_path(base)):
            os.remove(_state_path(base))
        try:
            os.rmdir(base)                                   # only if nothing else is in it
        except OSError:
            pass
    return {"unregistered": removed, "files_removed": not keep_files}


def status(base=None, home=None):
    base, home = base or default_base(), home or default_home()
    st = load_state(base)
    md = os.path.join(base, st["active"], "models", "onnx") if st["active"] else ""
    models = sorted(f for f in os.listdir(md) if os.path.isdir(os.path.join(md, f))) if os.path.isdir(md) else []
    return {"base": base, "versions": st["versions"], "active": st["active"], "previous": st.get("previous"),
            "models": models, "registered_in_nuke": registered_plugin(home)}


def install_with_models(pkg, models, base=None, home=None):
    """The main package (if given) then every model package (into the version just installed / the active one)."""
    r = {"installed": install(pkg, base, home) if pkg else None, "models": []}
    for m in models:
        print("installing %s ..." % os.path.basename(m))
        r["models"].append(install_model(m, base))
    return r


def _here():
    """Folder of this script, or of ST-ROTO-Setup.exe when frozen by PyInstaller."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def interactive():
    """Double-clicked ST-ROTO-Setup.exe (no arguments): a small text menu using the package zip next to it."""
    here = _here()
    zips = sorted(f for f in os.listdir(here) if f.startswith("ST-ROTO-") and f.endswith(".zip")
                  and not f.startswith(MODEL_PREFIX))
    pkg = os.path.join(here, zips[-1]) if zips else None
    models = model_packages_near(here)
    print("ST-ROTO setup (offline, no administrator rights)\n")
    print(json.dumps(status(), indent=1))
    what = os.path.basename(pkg) if pkg else "(no ST-ROTO-<version>.zip next to me)"
    if models:
        what += " + " + ", ".join(os.path.basename(m) for m in models)
    print("\n  1  install / upgrade from %s" % what)
    print("  2  repair\n  3  roll back to the previous version\n  4  uninstall\n  5  quit")
    choice = input("\nchoice: ").strip()
    try:
        if choice == "1" and (pkg or models):
            r = install_with_models(pkg, models)
        elif choice == "2":
            r = repair(pkg)
        elif choice == "3":
            r = rollback()
        elif choice == "4" and input("remove ST-ROTO and its Nuke registration? (yes/no) ").strip() == "yes":
            r = uninstall()
        else:
            r = "nothing done"
        print(json.dumps(r, indent=1) if not isinstance(r, str) else r)
        print("\nRestart Nuke to see the change." if choice in ("1", "3", "4") else "")
    except Exception as e:                                   # noqa: BLE001 - show it, do not crash the window
        print("ERROR: %s" % e)
    input("\npress Enter to close")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return interactive()
    ap = argparse.ArgumentParser(prog="st_roto_setup", description="ST-ROTO offline setup (no downloads).")
    ap.add_argument("command", choices=["package", "package-model", "install", "upgrade", "install-model", "rollback",
                                        "repair", "uninstall", "status"])
    ap.add_argument("--source", help="package zip / folder, or a repository checkout")
    ap.add_argument("--out", help="package: output zip")
    ap.add_argument("--models", choices=sorted(MODEL_SETS), default="tiny")
    ap.add_argument("--model", help="package-model: the model name, e.g. sam2.1-hiera-large")
    ap.add_argument("--no-model-packages", action="store_true",
                    help="install: do not install the ST-ROTO-model-*.zip files lying next to the package")
    ap.add_argument("--base", help="install folder (default %%LOCALAPPDATA%%\\ST-ROTO)")
    ap.add_argument("--home", help="user folder holding .nuke (default %%USERPROFILE%%)")
    ap.add_argument("--keep-files", action="store_true")
    a = ap.parse_args(argv)
    here = _here()
    if a.command == "package":
        repo = a.source or os.path.abspath(os.path.join(here, "..", ".."))
        out = a.out or os.path.join(repo, "dist", "ST-ROTO-%s.zip" % version_of(repo))
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        r = build_package(repo, out, a.models)
    elif a.command == "package-model":
        repo = a.source or os.path.abspath(os.path.join(here, "..", ".."))
        if not a.model:
            ap.error("--model is required")
        out = a.out or os.path.join(repo, "dist", "%s%s.zip" % (MODEL_PREFIX, a.model))
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        r = build_model_package(repo, a.model, out)
    elif a.command == "install-model":
        if not a.source:
            ap.error("--source <ST-ROTO-model-*.zip> is required")
        r = install_model(a.source, a.base)
    elif a.command in ("install", "upgrade"):
        src = a.source or (here if os.path.exists(os.path.join(here, "PACKAGE_MANIFEST.json")) else None)
        if not src:
            ap.error("--source is required (a package zip/folder or a repository checkout)")
        models = [] if a.no_model_packages or not src.lower().endswith(".zip") else model_packages_near(src)
        r = install_with_models(src, models, a.base, a.home)
    elif a.command == "rollback":
        r = rollback(a.base, a.home)
    elif a.command == "repair":
        r = repair(a.source, a.base, a.home)
    elif a.command == "uninstall":
        r = uninstall(a.base, a.home, a.keep_files)
    else:
        r = status(a.base, a.home)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
