"""Several objects per tracking pass (T-067).

Prompt rules are pure Python and always run. The AI tests need the locally exported SAM 2.1 tiny video model and
the synthetic shot (research/probes/2026-11-15_video/make_synthetic_video.py), so they skip in CI. They run on CPU
(deterministic) and require a two-object pass to give EXACTLY the keys and diagnostics of tracking each object
alone: upstream tracks objects independently (Sam2VideoModel.forward loops over objects), so anything else would be
a bug in the shared-encoding pass.
"""
import json
import os

import numpy as np
import pytest

from st_roto import prompts

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VID_DIR = os.path.join(ROOT, "models", "onnx", "sam2.1-hiera-tiny", "video")
FRAMES_DIR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


# ------------------------------------------------------------------------------------------------ prompts
def test_prompts_per_object():
    t = prompts.add("", 0, 10.0, 20.0, prompts.INCLUDE, obj="car")
    t = prompts.add(t, 0, 30.0, 20.0, prompts.EXCLUDE, obj="car")
    t = prompts.add(t, 7, 50.0, 60.0, prompts.INCLUDE, obj="dog")          # other object, other frame: allowed
    with pytest.raises(ValueError):
        prompts.add(t, 3, 1, 1, prompts.INCLUDE, obj="car")                  # one frame per object
    gs = prompts.objects_for_tracker(t, "car")
    assert [(g["name"], g["frame"], g["labels"]) for g in gs] == [("car", 0, [1, 0]), ("dog", 7, [1])]
    assert prompts.summary(t, "car") == "car frame 0: 1 include, 1 exclude; dog frame 7: 1 include, 0 exclude"
    t2 = prompts.clear(t, "car", "car")
    assert [g["name"] for g in prompts.groups(t2)] == ["dog"]
    with pytest.raises(ValueError, match="'car'"):                           # every object needs an include point
        prompts.objects_for_tracker(prompts.add(t2, 1, 1, 1, prompts.EXCLUDE, obj="car"))
    with pytest.raises(ValueError):
        prompts.for_tracker(t)                                               # single-object API refuses 2 objects


def test_untagged_points_belong_to_current_object():
    """Points saved before T-067 carry no object name: they belong to the node's current object."""
    old = '[{"frame":4,"x":1.0,"y":2.0,"label":1}]'
    assert prompts.groups(old, "hero")[0]["name"] == "hero"
    t = prompts.add(old, 4, 5, 6, prompts.EXCLUDE, obj="hero")              # same object -> same frame rule
    assert len(prompts.groups(t, "hero")) == 1
    with pytest.raises(ValueError):
        prompts.add(old, 5, 5, 6, prompts.INCLUDE, obj="hero")
    assert prompts.clear(t, "hero", "hero") == "[]"


# ------------------------------------------------------------------------------------------------ AI
ort = pytest.importorskip("onnxruntime")
cv2 = pytest.importorskip("cv2")
needs = pytest.mark.skipif(not (os.path.exists(os.path.join(VID_DIR, "vencoder.onnx"))
                                and os.path.exists(os.path.join(FRAMES_DIR, "meta.json"))),
                           reason="exported video model / synthetic frames not present")
N = 8


def disc_centre(f, n=48):
    """The synthetic shot's orange distractor disc (make_synthetic_video.py)."""
    s = f / (n - 1.0)
    return 1050 - 600 * s, 560 - 120 * np.sin(np.pi * s)


def get_rgb(f):
    """Shot frames as scene-linear float (the tracker re-encodes to sRGB, st_roto_nuke.colour)."""
    x = cv2.cvtColor(cv2.imread(os.path.join(FRAMES_DIR, "frame_%04d.png" % f)), cv2.COLOR_BGR2RGB) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


@needs
def test_track_objects_equals_single_object_runs():
    from st_roto_nuke.track import track_object, track_objects
    meta = json.load(open(os.path.join(FRAMES_DIR, "meta.json")))
    frames = list(range(N))
    objs = [{"name": "target", "frame": 0, "points": [tuple(meta["click_xy"])], "labels": [1]},
            {"name": "disc", "frame": 2, "points": [disc_centre(2)], "labels": [1]}]   # starts later
    multi = track_objects(get_rgb, frames, objs, device="cpu")
    assert multi["device"] == "cpu" and [o["name"] for o in multi["objects"]] == ["target", "disc"]
    for o, got in zip(objs, multi["objects"]):
        alone = track_object(get_rgb, frames[o["frame"]:], o["frame"], o["points"], device="cpu", labels=o["labels"])
        assert sorted(got["keys"]) == sorted(alone["keys"]) == frames[o["frame"]:], o["name"]
        assert got["keys"] == alone["keys"], o["name"]                       # identical points, every frame
        assert got["reports"] == alone["reports"] and got["generator"] == alone["generator"], o["name"]
    t, d = multi["objects"][0]["keys"][4], multi["objects"][1]["keys"][4]   # really two different objects
    assert np.linalg.norm(np.mean(np.array(t)[:, :2], 0) - np.array(disc_centre(4))) > 200
    assert np.linalg.norm(np.mean(np.array(d)[:, :2], 0) - np.array(disc_centre(4))) < 10


@needs
def test_retrack_objects_equals_single_object_runs(tmp_path):
    """Two shapes, each drawn on a different middle frame -> forward + reverse in one pass == each alone."""
    from st_roto import model as m
    from st_roto.commands import CommandBus
    from st_roto.geometry import mask_to_points
    from st_roto.store import ProjectStore
    from st_roto_nuke.track import retrack_object, retrack_objects
    meta = json.load(open(os.path.join(FRAMES_DIR, "meta.json")))
    W, H = meta["w"], meta["h"]
    store = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(store)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh", "width": W, "height": H}})
    gt3 = cv2.imread(os.path.join(FRAMES_DIR, "gt_0003.png"), cv2.IMREAD_GRAYSCALE) > 127
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    cx, cy = disc_centre(5)
    disc5 = 85.0 - np.hypot(xx - cx, yy - cy)                                 # signed distance, > 0 inside
    for oid, frame, field in (("A", 3, gt3.astype(float) - 0.5), ("B", 5, disc5)):
        bus.execute({"op": "create_object", "row": {"id": oid, "shot_id": "S", "name": oid}})
        bus.execute({"op": "create_shape", "row": {"id": oid + "s", "object_id": oid, "name": oid, "point_count": 16}})
        bus.execute({"op": "set_key", "shape_id": oid + "s", "frame": frame, "points": mask_to_points(field, count=16)},
                    actor=m.ACTOR_ARTIST)
    frames = list(range(N))
    multi = retrack_objects(get_rgb, store, ["As", "Bs"], frames, W, H, device="cpu")
    for sid, drawn in (("As", 3), ("Bs", 5)):
        alone = retrack_object(get_rgb, store, sid, frames, W, H, device="cpu")
        got = multi["shapes"][sid]
        assert sorted(got["keys"]) == [f for f in frames if f != drawn], sid    # artist frame never returned
        assert all(got["keys"][f] for f in got["keys"]), sid                    # object found on every frame
        assert got["keys"] == alone["keys"] and got["reports"] == alone["reports"], sid
    store.close()


@needs
def test_reverse_pass_continues_point_order_from_conditioning_frame(tmp_path):
    """Regression (found in review, T-067): the reverse pass used the LAST forward frame's point 0 as its start
    hint instead of the conditioning frame's, which can rotate the point order across the seam. Point 0 of the
    frame before the conditioning frame must now be the point nearest to the conditioning frame's point 0."""
    from st_roto import model as m
    from st_roto.commands import CommandBus
    from st_roto.geometry import mask_to_points
    from st_roto.store import ProjectStore
    from st_roto_nuke.track import retrack_object
    meta = json.load(open(os.path.join(FRAMES_DIR, "meta.json")))
    W, H = meta["w"], meta["h"]
    store = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(store)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh", "width": W, "height": H}})
    bus.execute({"op": "create_object", "row": {"id": "A", "shot_id": "S", "name": "A"}})
    bus.execute({"op": "create_shape", "row": {"id": "As", "object_id": "A", "name": "A", "point_count": 16}})
    gt = cv2.imread(os.path.join(FRAMES_DIR, "gt_0004.png"), cv2.IMREAD_GRAYSCALE) > 127
    drawn = mask_to_points(gt.astype(float) - 0.5, count=16)
    bus.execute({"op": "set_key", "shape_id": "As", "frame": 4, "points": drawn}, actor=m.ACTOR_ARTIST)
    res = retrack_object(get_rgb, store, "As", list(range(N)), W, H, device="cpu")
    p3 = np.array(res["keys"][3])[:, :2]
    d = np.linalg.norm(p3 - np.array(drawn[0][:2]), axis=1)
    assert int(np.argmin(d)) == 0
    store.close()
