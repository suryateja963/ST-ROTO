"""Stereo / multi-view core (T-109, REQ-115): correspondence (disparity, prompt transfer), consistency flags,
per-view objects in the store (schema v11)."""
import numpy as np
import pytest

from st_roto import stereo, views
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.geometry import mask_to_points
from st_roto.prompts import BOX_BR, BOX_TL
from st_roto.store import ProjectStore

W, H = 160, 100


def disc(cx, cy, r):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    return r - np.hypot(xx - cx, yy - cy)


def textured_pair(dx, dy, seed=3):
    """Left: smooth random texture with a textured disc; right: the disc moved by (dx, dy), background by 2 px."""
    rng = np.random.RandomState(seed)
    bg = rng.rand(H + 20, W + 40, 3).astype(np.float32)
    k = np.ones(3) / 3.0
    for ax in (0, 1):
        bg = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), ax, bg)
    obj = rng.rand(H + 20, W + 40, 3).astype(np.float32) * 0.5 + 0.5
    left = bg[10:10 + H, 20:20 + W].copy()
    right = bg[10:10 + H, 22:22 + W].copy()
    mask_l = disc(60, 50, 18) > 0
    mask_r = disc(60 + dx, 50 + dy, 18) > 0
    left[mask_l] = obj[10:10 + H, 20:20 + W][mask_l]
    yy, xx = np.nonzero(mask_r)
    right[yy, xx] = obj[10 + yy - dy, 20 + xx - dx]
    return left, right, mask_l


def test_disparity_found_on_epipolar_line():
    left, right, mask = textured_pair(-17, 1)
    r = stereo.estimate_disparity(left, right, mask, max_dx=40, max_dy=3)
    assert abs(r["dx"] + 17) < 0.5 and abs(r["dy"] - 1) < 0.5
    assert r["ambiguity"] < 0.5                   # textured object: clear winner
    with pytest.raises(ValueError):
        stereo.estimate_disparity(left, right, np.zeros((H, W), bool))


def test_disparity_coarse_to_fine_with_large_search():
    left, right, mask = textured_pair(-33, 0)
    r = stereo.estimate_disparity(left, right, mask, max_dx=150)   # coarse level is block-averaged (s = 3)
    assert abs(r["dx"] + 33) < 0.5 and abs(r["dy"]) < 0.5


def test_transfer_prompt_moves_box_and_clicks():
    obj = {"name": "car", "frame": 4, "points": [(10, 10), (30, 30), (50, 40), (5, 5)],
           "labels": [BOX_TL, BOX_BR, 1, 0]}
    p = stereo.transfer_prompt(obj, -8, 1, (20, 20, 60, 50), W, H, name="car_right")
    assert p["name"] == "car_right" and p["frame"] == 4
    assert p["labels"] == [BOX_TL, BOX_BR, 1]           # the exclude click moved outside the image: dropped
    assert p["points"][:3] == [(12, 21), (52, 51), (42, 41)]
    assert stereo.transfer_prompt(obj, -70, 0, (20, 20, 60, 50), W, H) is None   # box (mostly) outside


def _geo(cx, cy, r=20.0):
    return {"area": np.pi * r * r, "cx": cx, "cy": cy, "x0": cx - r, "y0": cy - r, "x1": cx + r, "y1": cy + r}


def test_consistency_flags():
    a = {f: _geo(100 + f, 50) for f in range(10)}
    b = {f: _geo(100 + f - 30, 50.5) for f in range(10)}
    clean = stereo.consistency(a, b, "left", "right")
    assert clean["flags"] == [] and abs(clean["disparity"] + 30) < 1e-9
    bad = dict(b)
    bad[2] = _geo(72 - 30, 58)                          # vertical: both edges 7.5 px off
    bad[4] = _geo(104 - 30, 50.5, r=26)                  # size (+69 %), edges also off
    bad[6] = _geo(106 - 45, 50.5)                        # disparity jump 15 px
    bad[8] = None                                        # object only in the left view
    rep = stereo.consistency(a, bad, "left", "right")
    flagged = {f: r for f, r in rep["flags"]}
    assert set(flagged) == {2, 4, 6, 8}
    assert "vertically" in flagged[2] and "size" in flagged[4]
    assert "disparity jumps" in flagged[6] and "left view only" in flagged[8]
    one_edge = dict(b)
    one_edge[3] = dict(_geo(103 - 30, 50.5), y0=50.5 - 20 + 9)    # top edge only: a view-dependent occlusion
    assert stereo.consistency(a, one_edge)["flags"] == []


def test_key_geometry_matches_disc():
    g = stereo.key_geometry(mask_to_points(disc(70, 40, 20), count=24))
    assert abs(g["cx"] - 70) < 0.2 and abs(g["cy"] - 40) < 0.2
    assert abs(g["area"] - np.pi * 400) / (np.pi * 400) < 0.02


def project(tmp_path, right_cy=50):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot", "width": W, "height": H}})
    for view, dx, cy in (("left", 0, 50), ("right", -12, right_cy)):
        oid = "car_" + view
        bus.execute({"op": "create_object", "row": {"id": oid, "shot_id": "S", "name": oid, "view": view,
                                                    "pair": "car"}}, actor=m.ACTOR_AI)
        bus.execute({"op": "create_shape", "row": {"id": oid + "s", "object_id": oid, "name": oid,
                                                   "point_count": 16}}, actor=m.ACTOR_AI)
        for f in range(6):
            c = cy if not (view == "right" and f == 3) else cy + 10       # frame 3: right view 10 px low
            bus.execute({"op": "set_key", "shape_id": oid + "s", "frame": f,
                         "points": mask_to_points(disc(60 + f + dx, c, 18), count=16)}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_object", "row": {"id": "mono", "shot_id": "S", "name": "mono"}})
    return s, bus


def test_store_views_pairs_and_review(tmp_path):
    s, bus = project(tmp_path)
    assert s.schema_version() >= 11
    assert s.row("objects", "car_left")["view"] == "left" and s.row("objects", "mono")["view"] is None
    assert [o["id"] for o in stereo.counterparts(s, "car_left")] == ["car_right"]
    assert stereo.counterparts(s, "mono") == []
    flags = views.review_for_object(s, "car_right")
    st = [x for x in flags if "stereo" in x[2]]
    assert [x[0] for x in st] == [3] and st[0][1] == "check" and "stereo vs left" in st[0][2]
    assert [x[0] for x in views.review_for_object(s, "car_left") if "stereo" in x[2]] == [3]
    # an artist can assign an object to a view (e.g. a hand-drawn shape), undoably
    bus.execute({"op": "update_object", "id": "mono", "fields": {"view": "right", "pair": "car"}})
    assert s.row("objects", "mono")["view"] == "right"
    bus.undo()
    assert s.row("objects", "mono")["view"] is None


def test_json_round_trip_keeps_views(tmp_path):
    from st_roto import interchange
    s, bus = project(tmp_path)
    data = interchange.export_shot(s, "S")
    assert {o["name"]: o["view"] for o in data["objects"]} == {"car_left": "left", "car_right": "right", "mono": None}
    bus.execute({"op": "create_shot", "row": {"id": "T", "name": "copy", "width": W, "height": H}})
    interchange.import_shot(bus, data, "T")
    got = {o["name"]: (o["view"], o["pair"]) for o in s.objects("T")}
    assert got == {"car_left": ("left", "car"), "car_right": ("right", "car"), "mono": (None, None)}


def test_mask_from_keys_and_box():
    pts = mask_to_points(disc(50, 40, 10), count=16)
    m_ = stereo.mask_from_keys([pts, [[5, 5, 5, 5, 5, 5]] * 4], H, W)      # second: a collapsed part key
    assert abs(int(m_.sum()) - np.pi * 100) < 15
    x0, y0, x1, y1 = stereo.mask_box(m_)
    assert (x0, y0, x1, y1) == (40.0, 30.0, 60.0, 50.0)
    assert stereo.mask_box(np.zeros((H, W), bool)) is None
