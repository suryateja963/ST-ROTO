"""Model storage locations, verify, remove, import (T-101, REQ-130). A small fake model in temporary folders; no
ONNX Runtime needed (the registry is plain Python)."""
import hashlib
import json
import os

import pytest

from st_roto_ai import registry as reg


def make_root(root, name="toy-model", licence="apache-2.0", approval="D-999", data=b"weights-v1", tamper=False):
    os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
    os.makedirs(os.path.join(root, "onnx", name, "video"), exist_ok=True)
    p = os.path.join(root, "onnx", name, "video", "net.onnx")
    with open(p, "wb") as fh:
        fh.write(data)
    sha = hashlib.sha256(data).hexdigest()
    src = {"name": name, "repo": "example/toy", "revision": "abc123", "licence": licence, "approval": approval,
           "files": {}}
    exp = {"name": name, "source_revision": "abc123", "tool": "test",
           "files": {"video/net.onnx": {"bytes": len(data), "sha256": sha}}}
    json.dump(src, open(os.path.join(root, "manifests", name + ".json"), "w"))
    json.dump(exp, open(os.path.join(root, "manifests", name + ".exports.json"), "w"))
    if tamper:
        with open(p, "wb") as fh:
            fh.write(b"weights-v2")                                  # same size, different content
    return p


def test_lookup_order_user_studio_plugin(tmp_path, monkeypatch):
    user, studio = str(tmp_path / "user"), str(tmp_path / "studio")
    make_root(studio)
    monkeypatch.setenv("ST_ROTO_MODELS_STUDIO", studio)
    monkeypatch.setenv("ST_ROTO_MODELS_USER", user)                  # not created: ignored
    assert [lbl for lbl, _ in reg.roots()] == ["studio", "plugin"]
    assert reg.find_model("toy-model") == os.path.abspath(studio)
    make_root(user)
    assert [lbl for lbl, _ in reg.roots()] == ["user", "studio", "plugin"]
    assert reg.find_model("toy-model") == os.path.abspath(user)       # user location wins
    rows = [r for r in reg.models() if r["name"] == "toy-model"]
    assert {(r["location"], r["active"]) for r in rows} == {("user", True), ("studio", False)}
    assert reg.find_model("not-installed") == os.path.abspath(reg.default_models_root())


def test_verify_file_infers_its_location(tmp_path, monkeypatch):
    monkeypatch.delenv("ST_ROTO_MODEL_VERIFY", raising=False)
    p = make_root(str(tmp_path / "studio"))
    assert reg.verify_file(p)["model"] == "toy-model"                 # no models_root given: found from the path


def test_verify_model_and_tampering(tmp_path):
    good = str(tmp_path / "good"); make_root(good)
    res = reg.verify_model("toy-model", good)
    assert all(r["ok"] for r in res) and len(res) == 2
    bad = str(tmp_path / "bad"); make_root(bad, tamper=True)
    res = reg.verify_model("toy-model", bad)
    assert not res[1]["ok"] and "MISMATCH" in res[1]["detail"]
    nolic = str(tmp_path / "nolic"); make_root(nolic, licence="cc-by-nc-4.0")
    assert not reg.verify_model("toy-model", nolic)[0]["ok"]


def test_import_refuses_unapproved_or_tampered_and_copies_good(tmp_path):
    dst = str(tmp_path / "user"); os.makedirs(dst)
    unapproved = str(tmp_path / "a"); make_root(unapproved, approval="")
    with pytest.raises(reg.ModelIntegrityError, match="not imported"):
        reg.import_model(unapproved, "toy-model", dst)
    tampered = str(tmp_path / "b"); make_root(tampered, tamper=True)
    with pytest.raises(reg.ModelIntegrityError, match="MISMATCH"):
        reg.import_model(tampered, "toy-model", dst)
    assert not os.path.exists(os.path.join(dst, "onnx", "toy-model"))   # nothing copied
    good = str(tmp_path / "c"); make_root(good)
    out = reg.import_model(good, "toy-model", dst)
    assert out["files"] == 1 and all(r["ok"] for r in reg.verify_model("toy-model", dst))


def test_remove_keeps_manifests(tmp_path):
    root = str(tmp_path / "r"); make_root(root)
    gone = reg.remove_model("toy-model", root)
    assert len(gone) == 1 and not os.path.exists(os.path.join(root, "onnx", "toy-model"))
    assert os.path.exists(os.path.join(root, "manifests", "toy-model.json"))
    row = [r for r in reg.models(root) if r["name"] == "toy-model"][0]
    assert row["exports_registered"] and not row["exports_present"]
