"""EXR matte export (T-070) and the matte pass (T-069). Needs the `OpenEXR` Python package (skips without it)."""
import json
import os

import numpy as np
import pytest

from st_roto import exr, matte
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.geometry import Anchor, mask_to_points, rasterize_spline
from st_roto.store import ProjectStore

OpenEXR = pytest.importorskip("OpenEXR")
H, W = 90, 120


def test_frame_paths_follow_nuke_convention(tmp_path):
    assert exr.frame_path("d", "sh", 7).endswith("sh.0007.exr")
    assert exr.frame_path("d", "sh", -2).endswith("sh.-002.exr")          # Nuke: sign + 3 digits (measured)
    assert exr.sequence_pattern("d", "sh").endswith("d/sh.####.exr")
    assert exr.layer_name("my car #2") == "my_car__2" and exr.layer_name("2nd") == "o_2nd"


def test_write_read_layers_exact(tmp_path):
    rng = np.random.default_rng(0)
    a, b = rng.random((H, W)).astype(np.float32), rng.random((H, W)).astype(np.float32)
    p = str(tmp_path / "x" / "m.0001.exr")
    names = exr.write_mattes(p, {"hero": a, "car 1": b, "car_1": b * 0.5}, attributes={"st_roto": "{}"})
    assert names == {"hero": "hero", "car 1": "car_1", "car_1": "car_1_2"}          # clash -> suffix
    ch = exr.read_channels(p)
    assert set(ch) == {"A", "hero.A", "car_1.A", "car_1_2.A"}
    assert np.array_equal(ch["hero.A"], a) and np.array_equal(ch["car_1_2.A"], b * 0.5)
    assert np.array_equal(ch["A"], np.maximum(a, b))
    assert not os.path.exists(p + ".part")
    with pytest.raises(ValueError):
        exr.write_mattes(p, {"a": a, "b": np.zeros((2, 2))})


def test_key_points_at_interpolates_and_holds():
    keys = [{"frame": 2, "points": [[0.0] * 6]}, {"frame": 6, "points": [[4.0] * 6]}]
    assert matte.key_points_at(keys, 2) == ([[0.0] * 6], "key")
    pts, how = matte.key_points_at(keys, 3)
    assert how == "interpolated" and np.allclose(pts, [[1.0] * 6])
    assert matte.key_points_at(keys, 0)[1] == "held" and matte.key_points_at(keys, 9)[1] == "held"
    assert matte.key_points_at([], 1) == (None, None)


def _disc(cx, cy, r):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    return r - np.hypot(xx - cx, yy - cy)


def test_render_mattes_hard_and_soft(tmp_path):
    from st_roto_nuke.mattes import render_mattes
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot 10", "width": W, "height": H}})
    for oid, cx in (("A", 35), ("B", 85)):
        bus.execute({"op": "create_object", "row": {"id": oid, "shot_id": "S", "name": "obj" + oid}})
        bus.execute({"op": "create_shape", "row": {"id": oid + "s", "object_id": oid, "name": oid, "point_count": 12}})
        for f in (0, 2):
            bus.execute({"op": "set_key", "shape_id": oid + "s", "frame": f,
                         "points": mask_to_points(_disc(cx + 2 * f, 45, 20), count=12)}, actor=m.ACTOR_ARTIST)
    out = str(tmp_path / "mattes")
    plate = lambda f: np.full((H, W, 3), 0.2, np.float32)                          # noqa: E731
    rep = render_mattes(plate, s, "S", [0, 1, 2], out, soft=False)
    assert rep["layers"] == {"objA": "objA", "objB": "objB"} and len(rep["files"]) == 3
    assert rep["frames_interpolated"] == {"objA": [1], "objB": [1]}
    ch = exr.read_channels(exr.frame_path(out, "shot_10_mattes", 2))
    key = s.key("As", 2)["points"]
    exact = rasterize_spline([Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False)
                              for p in key], H, W)
    assert np.array_equal(ch["objA.A"] > 0.5, exact)                                 # hard matte = stored spline
    assert np.array_equal(ch["A"], np.maximum(ch["objA.A"], ch["objB.A"]))
    meta = json.loads(OpenEXR.File(rep["files"][0]).header()["st_roto"])
    assert meta["soft"] is False and meta["pass"] == "st_roto_matte_v1"
    # soft edges: a plate whose real edge is 1 px outside the shape -> alpha follows the plate in the band
    def plate2(f):
        img = np.full((H, W, 3), 0.05, np.float32)
        img[_disc(35 + 2 * f, 45, 21) > 0] = 0.6
        return img
    rep2 = render_mattes(plate2, s, "S", [0], out, soft=True, objects=["A"])
    a = exr.read_channels(rep2["files"][0])["objA.A"]
    assert set(exr.read_channels(rep2["files"][0])) == {"A", "objA.A"}
    ring = (_disc(35, 45, 21) > 0) & (_disc(35, 45, 20) <= 0)
    assert a[ring].mean() > 0.5                                                      # pulled out to the plate edge
    s.close()
