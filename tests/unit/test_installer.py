"""ST-ROTO setup (T-103, REQ-210): package, install, upgrade, rollback, repair, uninstall on a small fake checkout in
temporary folders (base and home are always temporary: the real %USERPROFILE%\\.nuke is never touched)."""
import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "installer"))
import st_roto_setup as setup        # noqa: E402


def fake_repo(root, version, extra=b""):
    for rel, data in (("src/st_roto/__init__.py", b"# core\n" + extra), ("nuke_plugin/init.py", b"# plugin\n"),
                      ("nuke_plugin/menu.py", b"# menu\n"), ("models/manifests/m.json", b"{}"),
                      ("models/onnx/sam2.1-hiera-tiny/video/x.onnx", b"onnx" * 10), ("LICENSE", b"Apache-2.0"),
                      ("src/st_roto/__pycache__/junk.pyc", b"junk")):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
    open(os.path.join(root, "VERSION"), "w").write(version)
    return root


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"; (home / ".nuke").mkdir(parents=True)
    (home / ".nuke" / "init.py").write_text("import nuke\nnuke.pluginAddPath('C:/other/tool')\n")   # artist's own
    return {"base": str(tmp_path / "base"), "home": str(home), "tmp": tmp_path}


def test_package_contents_and_models_choice(env):
    repo = fake_repo(str(env["tmp"] / "repo"), "1.0.0")
    r = setup.build_package(repo, str(env["tmp"] / "p.zip"), models="tiny")
    names = zipfile.ZipFile(r["zip"]).namelist()
    assert "PACKAGE_MANIFEST.json" in names and "st_roto_setup.py" in names
    assert "payload/models/onnx/sam2.1-hiera-tiny/video/x.onnx" in names
    assert not any("__pycache__" in n for n in names)
    r0 = setup.build_package(repo, str(env["tmp"] / "p0.zip"), models="none")
    assert not any("models/onnx" in n for n in zipfile.ZipFile(r0["zip"]).namelist())


def test_install_registers_without_touching_other_lines(env):
    repo = fake_repo(str(env["tmp"] / "repo"), "1.0.0")
    pkg = setup.build_package(repo, str(env["tmp"] / "p.zip"))["zip"]
    r = setup.install(pkg, env["base"], env["home"])
    assert r["version"] == "1.0.0" and os.path.exists(os.path.join(r["path"], "nuke_plugin", "init.py"))
    text = io.open(os.path.join(env["home"], ".nuke", "init.py")).read()
    assert "C:/other/tool" in text and setup.BEGIN in text and text.count(setup.BEGIN) == 1
    assert setup.registered_plugin(env["home"]).endswith("1.0.0/nuke_plugin")
    assert setup.verify(env["base"])["bad"] == []


def test_upgrade_rollback_repair_uninstall(env):
    pkg1 = setup.build_package(fake_repo(str(env["tmp"] / "r1"), "1.0.0"), str(env["tmp"] / "1.zip"))["zip"]
    pkg2 = setup.build_package(fake_repo(str(env["tmp"] / "r2"), "1.1.0", b"# new\n"), str(env["tmp"] / "2.zip"))["zip"]
    setup.install(pkg1, env["base"], env["home"])
    setup.install(pkg2, env["base"], env["home"])                       # upgrade
    st = setup.status(env["base"], env["home"])
    assert st["active"] == "1.1.0" and st["previous"] == "1.0.0" and st["registered_in_nuke"].endswith("1.1.0/nuke_plugin")
    setup.rollback(env["base"], env["home"])
    assert setup.status(env["base"], env["home"])["active"] == "1.0.0"
    setup.rollback(env["base"], env["home"])                            # and forward again
    # damage a file -> verify finds it -> repair from the package fixes it
    victim = os.path.join(env["base"], "1.1.0", "src", "st_roto", "__init__.py")
    open(victim, "wb").write(b"broken")
    assert setup.verify(env["base"])["bad"] == [("src/st_roto/__init__.py", "changed")]
    with pytest.raises(ValueError, match="--source"):
        setup.repair(None, env["base"], env["home"])
    fix = setup.repair(pkg2, env["base"], env["home"])
    assert fix["fixed"] == ["src/st_roto/__init__.py"] and fix["still_bad"] == []
    open(victim, "wb").write(b"x")                                      # damaged again ...
    with pytest.raises(ValueError, match="version"):
        setup.repair(pkg1, env["base"], env["home"])                    # ... and the wrong package is refused
    setup.repair(pkg2, env["base"], env["home"])
    u = setup.uninstall(env["base"], env["home"])
    assert u["unregistered"] and not os.path.exists(env["base"])
    text = io.open(os.path.join(env["home"], ".nuke", "init.py")).read()
    assert text == "import nuke\nnuke.pluginAddPath('C:/other/tool')\n"   # the artist's file exactly as before


def test_damaged_package_installs_nothing(env):
    repo = fake_repo(str(env["tmp"] / "repo"), "1.0.0")
    pkg = setup.build_package(repo, str(env["tmp"] / "p.zip"))["zip"]
    bad = str(env["tmp"] / "bad.zip")
    with zipfile.ZipFile(pkg) as zin, zipfile.ZipFile(bad, "w") as zout:
        for n in zin.namelist():
            data = zin.read(n)
            zout.writestr(n, b"tampered" if n.endswith("menu.py") else data)
    with pytest.raises(ValueError, match="damaged"):
        setup.install(bad, env["base"], env["home"])
    assert not os.path.exists(os.path.join(env["base"], "1.0.0"))
    assert setup.registered_plugin(env["home"]) is None


def test_uninstall_removes_init_py_it_created(tmp_path):
    home = str(tmp_path / "h")
    pkg = setup.build_package(fake_repo(str(tmp_path / "r"), "2.0"), str(tmp_path / "p.zip"))["zip"]
    setup.install(pkg, str(tmp_path / "b"), home)
    assert os.path.exists(os.path.join(home, ".nuke", "init.py"))
    setup.uninstall(str(tmp_path / "b"), home)
    assert not os.path.exists(os.path.join(home, ".nuke", "init.py"))


# ------------------------------------------------------------------ model packages (release 0.1.0, D-046)
def big_model(repo, name="sam2.1-hiera-large", data=b"large" * 20):
    """A separately shipped model in the fake checkout + the export manifest the version expects for it."""
    rel = "video/vencoder.onnx"
    p = os.path.join(repo, "models", "onnx", name, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data)
    exp = {"files": {rel: {"bytes": len(data), "sha256": setup.sha256(p)}}}
    open(os.path.join(repo, "models", "manifests", name + ".exports.json"), "w").write(json.dumps(exp))
    return name


def test_model_package_installs_next_to_the_main_package(env):
    repo = fake_repo(str(env["tmp"] / "repo"), "0.1.0")
    name = big_model(repo)
    rel = env["tmp"] / "release"; rel.mkdir()
    pkg = setup.build_package(repo, str(rel / "ST-ROTO-0.1.0.zip"))["zip"]
    m = setup.build_model_package(repo, name, str(rel / ("ST-ROTO-model-%s.zip" % name)))
    zn = zipfile.ZipFile(m["zip"]).namelist()
    assert setup.MODEL_MANIFEST in zn and "payload/models/onnx/%s/video/vencoder.onnx" % name in zn
    assert not any("sam2.1-hiera-large" in n for n in zipfile.ZipFile(pkg).namelist() if "onnx/" in n)
    assert setup.model_packages_near(pkg) == [m["zip"]]
    r = setup.install_with_models(pkg, setup.model_packages_near(pkg), env["base"], env["home"])
    assert r["models"][0]["model"] == name
    st = setup.status(env["base"], env["home"])
    assert st["models"] == [name, "sam2.1-hiera-tiny"]
    assert setup.verify(env["base"])["bad"] == []                      # the model is covered by verify / repair
    # damaged model file -> repair re-installs it from the model package next to the main package
    victim = os.path.join(env["base"], "0.1.0", "models", "onnx", name, "video", "vencoder.onnx")
    open(victim, "wb").write(b"broken")
    assert setup.verify(env["base"])["bad"] == [("models/onnx/%s/video/vencoder.onnx" % name, "changed")]
    fix = setup.repair(pkg, env["base"], env["home"])
    assert fix["still_bad"] == [] and any(name in f for f in fix["fixed"])


def test_model_package_checked_against_the_version(env):
    repo = fake_repo(str(env["tmp"] / "repo"), "0.1.0")
    pkg = setup.build_package(repo, str(env["tmp"] / "p.zip"))["zip"]
    other = fake_repo(str(env["tmp"] / "other"), "0.1.0")
    name = big_model(other, data=b"another export")              # same name, different files than 0.1.0 expects
    m = setup.build_model_package(other, name, str(env["tmp"] / "m.zip"))["zip"]
    with pytest.raises(ValueError, match="install ST-ROTO itself first"):
        setup.install_model(m, env["base"])
    setup.install(pkg, env["base"], env["home"])
    with pytest.raises(ValueError, match="does not know the model"):       # 0.1.0 has no manifest for it
        setup.install_model(m, env["base"])
    big_model(repo, data=b"the real export")                              # now it does, with other checksums
    pkg = setup.build_package(repo, str(env["tmp"] / "p2.zip"))["zip"]
    setup.install(pkg, env["base"], env["home"])
    with pytest.raises(ValueError, match="does not match"):
        setup.install_model(m, env["base"])
    assert not os.path.exists(os.path.join(env["base"], "0.1.0", "models", "onnx", name))


def test_damaged_model_package_installs_nothing(env):
    repo = fake_repo(str(env["tmp"] / "repo"), "0.1.0")
    name = big_model(repo)
    pkg = setup.build_package(repo, str(env["tmp"] / "p.zip"))["zip"]
    m = setup.build_model_package(repo, name, str(env["tmp"] / "m.zip"))["zip"]
    bad = str(env["tmp"] / "bad.zip")
    with zipfile.ZipFile(m) as zin, zipfile.ZipFile(bad, "w") as zout:
        for n in zin.namelist():
            zout.writestr(n, b"tampered!" if n.endswith(".onnx") else zin.read(n))
    setup.install(pkg, env["base"], env["home"])
    with pytest.raises(ValueError, match="damaged"):
        setup.install_model(bad, env["base"])
    assert not os.path.exists(os.path.join(env["base"], "0.1.0", "models", "onnx", name))
    assert [d for d in os.listdir(env["base"]) if d.startswith("st_roto_model_")] == []   # work folder removed


def test_upgrade_carries_separately_installed_models(env):
    r1 = fake_repo(str(env["tmp"] / "r1"), "0.1.0")
    name = big_model(r1)
    pkg1 = setup.build_package(r1, str(env["tmp"] / "1.zip"))["zip"]
    m = setup.build_model_package(r1, name, str(env["tmp"] / "m.zip"))["zip"]
    setup.install(pkg1, env["base"], env["home"])
    setup.install_model(m, env["base"])
    r2 = fake_repo(str(env["tmp"] / "r2"), "0.2.0", b"# new\n")
    big_model(r2)                                                # 0.2.0 expects the same export
    r = setup.install(setup.build_package(r2, str(env["tmp"] / "2.zip"))["zip"], env["base"], env["home"])
    assert r["models_carried_over"] == [name]
    assert setup.verify(env["base"])["bad"] == []
    r3 = fake_repo(str(env["tmp"] / "r3"), "0.3.0", b"# newer\n")
    big_model(r3, data=b"re-exported")                           # 0.3.0 expects a new export: not carried
    r = setup.install(setup.build_package(r3, str(env["tmp"] / "3.zip"))["zip"], env["base"], env["home"])
    assert r["models_carried_over"] == []
    assert name not in setup.status(env["base"], env["home"])["models"]
