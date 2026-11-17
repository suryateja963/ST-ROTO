"""Delivery packages (T-108, REQ-180)."""
import json
import os
import zipfile

import numpy as np
import pytest

from st_roto import delivery
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.geometry import mask_to_points
from st_roto.store import ProjectStore


def disc(cx, w=64, h=48):
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    return 10 - np.hypot(xx - cx, yy - 24)


def project(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s, author="alice")
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot10", "width": 64, "height": 48,
                                              "first_frame": 0, "last_frame": 3}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}}, actor=m.ACTOR_AI)
    gen = json.dumps({"model": "sam2.1-hiera-tiny", "prompts": {"frame": 0}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "hero", "point_count": 12,
                                               "generator": gen}}, actor=m.ACTOR_AI)
    for f in range(4):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": f, "points": mask_to_points(disc(20 + f), count=12)},
                    actor=m.ACTOR_ARTIST if f == 2 else m.ACTOR_AI)
        bus.execute({"op": "set_report", "shape_id": "P", "frame": f, "object_score": 5.0 if f != 3 else -2.0,
                     "iou_pred": 0.9})
    return s


def test_build_contains_every_section_and_verifies(tmp_path):
    s = project(tmp_path)
    out = tmp_path / "mattes"; out.mkdir(); (out / "shot10_mattes.0000.exr").write_bytes(b"exr-bytes")
    md = tmp_path / "manifests"; md.mkdir()
    (md / "sam2.1-hiera-tiny.json").write_text(json.dumps({"repo": "facebook/sam2.1-hiera-tiny", "revision": "abc",
                                                           "licence": "apache-2.0", "approval": "D-015"}))
    r = delivery.build(s, "S", str(tmp_path / "d.zip"), outputs={"mattes": str(out)},
                       settings={"edges": "guided filter"}, dependencies={"st_roto": "0.1.0"}, manifests_dir=str(md))
    names = set(zipfile.ZipFile(r["zip"]).namelist())
    for n in ("project_settings.json", "models.json", "processing_report.json", "processing_report.md",
              "provenance.json", "quality_report.json", "quality_report.md", "dependencies.json", "MANIFEST.json",
              "outputs/mattes/shot10_mattes.0000.exr"):
        assert n in names, n
    z = zipfile.ZipFile(r["zip"])
    models = json.loads(z.read("models.json"))
    assert models["sam2.1-hiera-tiny"]["licence"] == "apache-2.0" and models["sam2.1-hiera-tiny"]["used_by_objects"] == ["hero"]
    prov = json.loads(z.read("provenance.json"))[0]["shapes"][0]["key_origins"]
    assert prov == {"ai_generated": 3, "artist_modified_ai": 1}             # artist key on an AI shape
    q = json.loads(z.read("quality_report.json"))[0]
    assert q["keys"] == 4 and q["artist_keys"] == 1 and q["frames_object_absent"] == 1
    proc = json.loads(z.read("processing_report.json"))
    assert proc["by_author"] == {"alice": proc["operations"]} and proc["by_kind"]["set_key"] == 4
    assert delivery.verify(r["zip"]) == []
    s.close()


def test_verify_detects_tampering_and_empty_shot_refused(tmp_path):
    s = project(tmp_path)
    r = delivery.build(s, "S", str(tmp_path / "d.zip"))
    bad = str(tmp_path / "bad.zip")
    with zipfile.ZipFile(r["zip"]) as zin, zipfile.ZipFile(bad, "w") as zout:
        for n in zin.namelist():
            zout.writestr(n, b"{}" if n == "quality_report.json" else zin.read(n))
    assert delivery.verify(bad) == [("quality_report.json", "changed")]
    bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "E", "name": "empty", "width": 8, "height": 8}})
    with pytest.raises(ValueError, match="nothing to deliver"):
        delivery.build(s, "E", str(tmp_path / "e.zip"))
    s.close()
