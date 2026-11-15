"""Model registry: nothing is loaded unless registered, approved, production-licensed and unmodified (T-056)."""
import json
import os

import pytest

from st_roto_ai import registry as reg


def _model(root, name="m1", licence="apache-2.0", approval="D-015", rev="abc"):
    os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
    os.makedirs(os.path.join(root, "onnx", name, "video"), exist_ok=True)
    with open(os.path.join(root, "manifests", name + ".json"), "w") as fh:
        json.dump({"name": name, "repo": "x/" + name, "revision": rev, "licence": licence, "approval": approval,
                   "files": {}}, fh)
    p = os.path.join(root, "onnx", name, "video", "enc.onnx")
    with open(p, "wb") as fh:
        fh.write(b"weights" * 1000)
    reg.build_exports_manifest(name, root, tool="test")
    return p


@pytest.fixture(autouse=True)
def _clear():
    reg._MEM.clear()
    os.environ.pop("ST_ROTO_MODEL_VERIFY", None)
    yield
    reg._MEM.clear()


def test_registered_file_verifies_then_uses_cache(tmp_path):
    p = _model(str(tmp_path))
    r1 = reg.verify_file(p, str(tmp_path))
    assert r1["model"] == "m1" and r1["file"] == "video/enc.onnx" and not r1["cached"]
    assert reg.verify_file(p, str(tmp_path))["cached"]
    reg._MEM.clear()                                                  # new process: on-disk stamp is used
    assert reg.verify_file(p, str(tmp_path))["cached"]


def test_modified_file_is_refused_even_with_same_size(tmp_path):
    p = _model(str(tmp_path))
    reg.verify_file(p, str(tmp_path))
    with open(p, "r+b") as fh:
        fh.seek(10); fh.write(b"X")
    os.utime(p, (1, 1))                                               # different mtime -> stamp no longer valid
    with pytest.raises(reg.ModelIntegrityError, match="SHA-256"):
        reg.verify_file(p, str(tmp_path))
    with open(p, "ab") as fh:
        fh.write(b"more")
    with pytest.raises(reg.ModelIntegrityError, match="size"):
        reg.verify_file(p, str(tmp_path))


def test_unregistered_unlicensed_unapproved_are_refused(tmp_path):
    root = str(tmp_path)
    p = _model(root)
    extra = os.path.join(root, "onnx", "m1", "video", "new.onnx")
    open(extra, "wb").write(b"x")
    with pytest.raises(reg.ModelIntegrityError, match="not listed"):
        reg.verify_file(extra, root)
    p2 = _model(root, "nc", licence="cc-by-nc-4.0")
    with pytest.raises(reg.ModelIntegrityError, match="licence"):
        reg.verify_file(p2, root)
    p3 = _model(root, "noap", approval="")
    with pytest.raises(reg.ModelIntegrityError, match="approval"):
        reg.verify_file(p3, root)
    outside = tmp_path / "elsewhere.onnx"; outside.write_bytes(b"x")
    with pytest.raises(reg.ModelIntegrityError, match="not inside"):
        reg.verify_file(str(outside), root)
    rows = {m["name"]: m for m in reg.models(root)}
    assert rows["m1"]["usable"] and not rows["nc"]["usable"] and not rows["noap"]["usable"]
    assert rows["m1"]["exports_present"]


def test_exports_from_other_revision_are_refused(tmp_path):
    root = str(tmp_path)
    p = _model(root)
    src = os.path.join(root, "manifests", "m1.json")
    d = json.load(open(src)); d["revision"] = "zzz"; json.dump(d, open(src, "w"))
    with pytest.raises(reg.ModelIntegrityError, match="revision"):
        reg.verify_file(p, root)


def test_escape_hatch_is_explicit(tmp_path):
    os.environ["ST_ROTO_MODEL_VERIFY"] = "0"
    assert reg.verify_file(str(tmp_path / "anything.onnx"))["skipped"] and "OFF" in reg.status()


def test_real_models_are_registered():
    """The development models on this machine must verify (skips where they are not exported)."""
    root = reg.default_models_root()
    rows = [m for m in reg.models(root) if m["exports_present"]]
    if not rows:
        pytest.skip("no exported models here")
    for m in rows:
        assert m["usable"], m
        p = os.path.join(root, "onnx", m["name"], "video", "config.json")
        assert reg.verify_file(p)["model"] == m["name"]
