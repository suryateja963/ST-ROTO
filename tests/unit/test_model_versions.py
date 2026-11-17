"""Model versions side by side, activation, rollback (T-114, REQ-130)."""
import json
import os

import pytest

from st_roto_ai import registry as reg


def _staged(root, payload, rev="abc", name="m1"):
    """A source models root holding one version of `name` whose encoder bytes are `payload`."""
    os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
    os.makedirs(os.path.join(root, "onnx", name, "video"), exist_ok=True)
    with open(os.path.join(root, "manifests", name + ".json"), "w") as fh:
        json.dump({"name": name, "repo": "x/" + name, "revision": rev, "licence": "apache-2.0", "approval": "D-015",
                   "files": {}}, fh)
    with open(os.path.join(root, "onnx", name, "video", "enc.onnx"), "wb") as fh:
        fh.write(payload)
    return reg.build_exports_manifest(name, root, tool="test")


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    reg._MEM.clear()
    monkeypatch.delenv("ST_ROTO_MODEL_VERIFY", raising=False)
    yield
    reg._MEM.clear()


def _enc(root, name="m1"):
    return open(os.path.join(root, "onnx", name, "video", "enc.onnx"), "rb").read()


def test_import_archives_previous_and_rollback(tmp_path):
    dst = str(tmp_path / "user")
    os.makedirs(dst)
    m1 = _staged(str(tmp_path / "s1"), b"v1" * 500)
    m2 = _staged(str(tmp_path / "s2"), b"v2" * 600)
    id1, id2 = reg.version_id(m1), reg.version_id(m2)
    assert id1 != id2 and len(id1) == 12
    r1 = reg.import_model(str(tmp_path / "s1"), "m1", dst)
    assert r1["version"] == id1 and r1["archived"] is None
    assert reg.import_model(str(tmp_path / "s1"), "m1", dst).get("unchanged")        # same version: no-op
    r2 = reg.import_model(str(tmp_path / "s2"), "m1", dst, note="new export")
    assert r2["archived"] == id1 and _enc(dst) == b"v2" * 600
    vs = reg.list_versions("m1", dst)
    assert [(v["id"], v["active"]) for v in vs] == [(id2, True), (id1, False)]
    assert vs[1]["files"] == 1 and vs[1]["bytes"] == 1000 and vs[1]["archived_utc"]
    # side by side: the archived version loads (and verifies) by 'name@id' without activation
    os.environ["ST_ROTO_MODELS_USER"] = dst
    try:
        d = reg.model_dir("m1@" + id1)
        assert open(os.path.join(d, "video", "enc.onnx"), "rb").read() == b"v1" * 500
        assert reg.verify_file(os.path.join(d, "video", "enc.onnx"))["model"] == "m1"
    finally:
        os.environ.pop("ST_ROTO_MODELS_USER")
    # rollback -> v1 active, v2 archived; rollback again -> v2
    rb = reg.rollback("m1", dst)
    assert rb["active"] == id1 and rb["previous"] == id2 and _enc(dst) == b"v1" * 500
    assert [(v["id"], v["active"]) for v in reg.list_versions("m1", dst)] == [(id1, True), (id2, False)]
    assert reg.rollback("m1", dst)["active"] == id2
    acts = [h["action"] for h in reg.history("m1", dst)]
    assert acts == ["import", "import", "activate", "activate"]


def test_tampered_version_is_not_activated_and_nothing_changes(tmp_path):
    dst = str(tmp_path / "root")
    os.makedirs(dst)
    _staged(str(tmp_path / "s1"), b"v1" * 500)
    _staged(str(tmp_path / "s2"), b"v2" * 600)
    reg.import_model(str(tmp_path / "s1"), "m1", dst)
    reg.import_model(str(tmp_path / "s2"), "m1", dst)
    id1 = reg.list_versions("m1", dst)[1]["id"]
    bad = os.path.join(reg.version_root(dst, "m1", id1), "onnx", "m1", "video", "enc.onnx")
    with open(bad, "r+b") as fh:
        fh.write(b"XX")
    with pytest.raises(reg.ModelIntegrityError, match="not activated"):
        reg.activate_version("m1", dst, id1)
    assert _enc(dst) == b"v2" * 600 and reg.list_versions("m1", dst)[0]["active"]
    with pytest.raises(reg.ModelIntegrityError):
        reg.activate_version("m1", dst, "nope")
    reg.remove_version("m1", dst, id1)
    assert len(reg.list_versions("m1", dst)) == 1
    with pytest.raises(reg.ModelIntegrityError, match="nothing to roll back"):
        reg.rollback("m1", dst)


def test_models_listing_ignores_the_versions_folder(tmp_path):
    dst = str(tmp_path / "root")
    os.makedirs(dst)
    _staged(str(tmp_path / "s1"), b"v1" * 500)
    _staged(str(tmp_path / "s2"), b"v2" * 600)
    reg.import_model(str(tmp_path / "s1"), "m1", dst)
    reg.import_model(str(tmp_path / "s2"), "m1", dst)
    rows = reg.models(dst)
    assert [r["name"] for r in rows] == ["m1"] and rows[0]["exports_present"]
