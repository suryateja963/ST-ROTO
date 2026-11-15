"""Resumable tracking (T-048): cancelled or crashed runs continue from a checkpoint with IDENTICAL results.
Needs the exported SAM 2.1 tiny video model and the synthetic shot (skips in CI). CPU: deterministic."""
import json
import os

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VID_DIR = os.path.join(ROOT, "models", "onnx", "sam2.1-hiera-tiny", "video")
FRAMES_DIR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")
pytest.importorskip("onnxruntime")
cv2 = pytest.importorskip("cv2")
pytestmark = pytest.mark.skipif(not (os.path.exists(os.path.join(VID_DIR, "vencoder.onnx"))
                                     and os.path.exists(os.path.join(FRAMES_DIR, "meta.json"))),
                                reason="exported video model / synthetic frames not present")
N = 10


def get_rgb(f):
    x = cv2.cvtColor(cv2.imread(os.path.join(FRAMES_DIR, "frame_%04d.png" % f)), cv2.COLOR_BGR2RGB) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def objects():
    meta = json.load(open(os.path.join(FRAMES_DIR, "meta.json")))
    s = 2 / 47.0
    return [{"name": "target", "frame": 0, "points": [tuple(meta["click_xy"])], "labels": [1]},
            {"name": "disc", "frame": 2, "points": [(1050 - 600 * s, 560 - 120 * np.sin(np.pi * s))], "labels": [1]}]


class CancelAt(object):
    """Job stand-in: cancels when asked to check the n-th time (i.e. before processing that frame)."""
    def __init__(self, n):
        self.n, self.calls = n, 0

    def check(self):
        from st_roto.jobs import Cancelled
        self.calls += 1
        if self.calls > self.n:
            raise Cancelled("test")

    def report(self, *a):
        pass


def same(a, b):
    for x, y in zip(a["objects"], b["objects"]):
        assert x["keys"] == y["keys"] and x["parts"] == y["parts"] and x["reports"] == y["reports"]
        assert x["absent_frames"] == y["absent_frames"] and x["generator"] == y["generator"]


@pytest.fixture(scope="module")
def reference():
    from st_roto_nuke.track import track_objects
    return track_objects(get_rgb, list(range(N)), objects(), device="cpu", anchors="auto")


def test_cancel_then_resume_is_identical(tmp_path, reference):
    from st_roto.jobs import Cancelled
    from st_roto_nuke.track import read_checkpoint, track_objects
    ck = str(tmp_path / "ck")
    with pytest.raises(Cancelled):
        track_objects(get_rgb, list(range(N)), objects(), device="cpu", anchors="auto", job=CancelAt(5),
                      checkpoint_dir=ck, checkpoint_every=100)
    meta = read_checkpoint(ck)
    assert meta["next_idx"] == 5 and meta["next_frame"] == 5
    d = meta["definition"]
    resumed = track_objects(get_rgb, d["frames"], d["objects"], device="cpu", anchors=d["anchors"],
                            checkpoint_dir=ck, resume=True)
    same(resumed, reference)
    assert not os.path.exists(ck)                                          # finished runs remove their checkpoint


def test_crash_then_resume_from_periodic_checkpoint_is_identical(tmp_path, reference):
    from st_roto_nuke.track import read_checkpoint, track_objects
    ck = str(tmp_path / "ck")

    def crashing(f):
        if f == 7:
            raise RuntimeError("power loss")                               # dies in the middle of frame 7
        return get_rgb(f)
    with pytest.raises(RuntimeError):
        track_objects(crashing, list(range(N)), objects(), device="cpu", anchors="auto", checkpoint_dir=ck,
                      checkpoint_every=3)
    meta = read_checkpoint(ck)
    assert meta["next_idx"] == 6                                           # last periodic checkpoint (frames 0-5)
    d = meta["definition"]
    resumed = track_objects(get_rgb, d["frames"], d["objects"], device="cpu", anchors=d["anchors"],
                            checkpoint_dir=ck, resume=True)
    same(resumed, reference)


def test_resume_refuses_a_different_run(tmp_path):
    from st_roto.jobs import Cancelled
    from st_roto_nuke.track import track_objects
    ck = str(tmp_path / "ck")
    with pytest.raises(Cancelled):
        track_objects(get_rgb, list(range(4)), objects()[:1], device="cpu", job=CancelAt(2), checkpoint_dir=ck)
    other = [dict(objects()[0], points=[(10.0, 10.0)])]
    with pytest.raises(ValueError, match="different tracking run"):
        track_objects(get_rgb, list(range(4)), other, device="cpu", checkpoint_dir=ck, resume=True)
