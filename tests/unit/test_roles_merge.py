"""Object roles (add / holdout / garbage) and merging objects (T-098, REQ-082 / REQ-100)."""
import json

import numpy as np
import pytest

from st_roto import interchange, views
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.geometry import mask_to_points
from st_roto.store import ProjectStore

W, H = 120, 80


def disc(cx, cy, r):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    return r - np.hypot(xx - cx, yy - cy)


def project(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot", "width": W, "height": H}})
    for oid, cx, cy, r in (("A", 50, 40, 25), ("B", 70, 40, 12), ("G", 40, 40, 30)):
        bus.execute({"op": "create_object", "row": {"id": oid, "shot_id": "S", "name": "obj" + oid}})
        bus.execute({"op": "create_shape", "row": {"id": oid + "s", "object_id": oid, "name": oid, "point_count": 16}})
        bus.execute({"op": "set_key", "shape_id": oid + "s", "frame": 0,
                     "points": mask_to_points(disc(cx, cy, r), count=16)}, actor=m.ACTOR_ARTIST)
    return s, bus


def test_role_is_validated_stored_and_undoable(tmp_path):
    s, bus = project(tmp_path)
    assert s.row("objects", "B")["role"] == "add"                       # default for every object
    bus.execute({"op": "update_object", "id": "B", "fields": {"role": "holdout"}})
    assert s.row("objects", "B")["role"] == "holdout"
    bus.undo()
    assert s.row("objects", "B")["role"] == "add"
    with pytest.raises(ValueError, match="role must be one of"):
        bus.execute({"op": "update_object", "id": "B", "fields": {"role": "punch"}})
    with pytest.raises(ValueError, match="role must be one of"):
        bus.execute({"op": "create_object", "row": {"id": "X", "shot_id": "S", "name": "x", "role": "bad"}})


def test_combine_roles_matches_nuke_arithmetic():
    a = np.array([[1.0, 1.0, 0.0, 0.5]], np.float32)
    b = np.array([[0.0, 1.0, 1.0, 0.5]], np.float32)
    g = np.array([[1.0, 0.0, 1.0, 1.0]], np.float32)
    assert views.combine_roles({"a": a, "b": b}, {}).tolist() == [[1.0, 1.0, 1.0, 0.75]]        # over, not max
    hold = views.combine_roles({"a": a, "b": b}, {"b": "holdout"})
    assert hold.tolist() == [[1.0, 0.0, 0.0, 0.0]]                       # cut out, clamped (no negatives)
    garb = views.combine_roles({"a": a, "g": g}, {"g": "garbage"})
    assert garb.tolist() == [[1.0, 0.0, 0.0, 0.5]]                       # kept only inside the garbage matte


def test_mattes_use_roles(tmp_path):
    pytest.importorskip("OpenEXR")
    from st_roto import exr
    from st_roto_nuke.mattes import render_mattes
    s, bus = project(tmp_path)
    bus.execute({"op": "update_object", "id": "B", "fields": {"role": "holdout"}})
    bus.execute({"op": "update_object", "id": "G", "fields": {"role": "garbage"}})
    plate = lambda f: np.full((H, W, 3), 0.2, np.float32)                # noqa: E731
    rep = render_mattes(plate, s, "S", [0], str(tmp_path / "m"), soft=False)
    ch = exr.read_channels(rep["files"][0])
    a, b, g = ch["objA.A"], ch["objB.A"], ch["objG.A"]                   # per-object layers stay raw
    assert b.sum() > 0 and g.sum() > 0
    expect = np.clip(a - b - (1 - g), 0, 1)
    assert np.abs(ch["A"] - expect).max() < 1e-6
    assert ch["A"][40, 70] == 0.0 and ch["A"][40, 35] == 1.0             # holdout cut; inside A and G kept
    assert rep["settings"]["roles"] == {"objA": "add", "objB": "holdout", "objG": "garbage"}


def test_merge_moves_shapes_and_undoes(tmp_path):
    s, bus = project(tmp_path)
    keys_b = s.keys("Bs")
    bus.execute({"op": "batch", "ops": views.merge_ops(s, "B", "A")})
    assert s.row("objects", "B") is None
    assert sorted(x["id"] for x in s.shapes("A")) == ["As", "Bs"] and s.keys("Bs") == keys_b
    assert views.main_shape(s, "A")["id"] == "As"                        # target keeps its main shape
    bus.undo()
    assert s.row("objects", "B")["name"] == "objB" and [x["id"] for x in s.shapes("B")] == ["Bs"]
    with pytest.raises(ValueError):
        views.merge_ops(s, "A", "A")


def test_interchange_keeps_roles(tmp_path):
    s, bus = project(tmp_path)
    bus.execute({"op": "update_object", "id": "B", "fields": {"role": "holdout"}})
    data = interchange.export_shot(s, "S")
    assert {o["name"]: o["role"] for o in data["objects"]}["objB"] == "holdout"
    t = ProjectStore(str(tmp_path / "t.stroto")); bt = CommandBus(t)
    bt.execute({"op": "create_shot", "row": {"id": "T", "name": "shot", "width": W, "height": H}})
    interchange.import_shot(bt, json.loads(json.dumps(data)), "T")
    assert {o["name"]: o["role"] for o in t.objects("T")}["objB"] == "holdout"


def test_combined_matte_is_over_not_max_on_soft_overlaps(tmp_path):
    """DEF-001: two soft edges overlapping at 0.5 each -> 0.75 (as Nuke's Roto renders), not 0.5 (max)."""
    pytest.importorskip("OpenEXR")
    from st_roto import exr
    from st_roto_nuke.mattes import render_mattes
    s, bus = project(tmp_path)
    plate = lambda f: np.full((H, W, 3), 0.2, np.float32)                # noqa: E731
    rep = render_mattes(plate, s, "S", [0], str(tmp_path / "m"), soft=False, objects=["A", "B"], blur_px=3.0)
    ch = exr.read_channels(rep["files"][0])
    a, b = ch["objA.A"], ch["objB.A"]
    assert np.abs(ch["A"] - (a + b - a * b)).max() < 1e-5
    both = (a > 0.2) & (a < 0.8) & (b > 0.2) & (b < 0.8)
    assert both.any() and (ch["A"][both] > np.maximum(a, b)[both] + 0.01).all()
