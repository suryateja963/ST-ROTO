"""Difficult sequences (T-086, REQ-092, master prompt section 11).

fit_to_format always runs. The tracking tests need the exported SAM 2.1 tiny video model and the synthetic shot
(skip in CI); they run on CPU (deterministic). In Nuke the same cases are measured end to end in
research/probes/2026-11-17_sequences and tests/nuke `test_difficult_sequences`.
"""
import json
import os

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from st_roto_nuke.pixels import FrameUnavailable, fit_to_format     # noqa: E402  (no Nuke import at module level)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VID_DIR = os.path.join(ROOT, "models", "onnx", "sam2.1-hiera-tiny", "video")
FRAMES_DIR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


# ------------------------------------------------------------------------------------------ fit_to_format
def test_fit_same_size_is_untouched():
    img = np.random.RandomState(0).rand(36, 64, 3).astype(np.float32)
    assert fit_to_format(img, 64, 36) is img


def test_fit_half_resolution_scales_to_full_frame():
    img = np.zeros((18, 32, 3), np.float32); img[4:9, 8:16] = 1.0
    out = fit_to_format(img, 64, 36)
    assert out.shape == (36, 64, 3) and out.dtype == np.float32
    ys, xs = np.nonzero(out[:, :, 0] > 0.5)                 # the block doubles in place: rows 8-17, cols 16-31
    assert (ys.min(), ys.max(), xs.min(), xs.max()) == (8, 17, 16, 31)


def test_fit_other_aspect_is_centred_like_reformat_width():
    wide = np.ones((27, 64, 3), np.float32)                  # same width, shorter: black bars top and bottom
    out = fit_to_format(wide, 64, 36)
    rows = np.nonzero(out[:, 0, 0] > 0.5)[0]
    assert (rows.min(), rows.max()) == (4, 30)               # (36 - 27) // 2 = 4 rows above
    tall = np.zeros((48, 64, 3), np.float32); tall[6:42] = 1.0
    out = fit_to_format(tall, 64, 36)                        # cropped around the centre
    assert out.shape == (36, 64, 3) and out.min() == 1.0


def test_fit_single_channel():
    assert fit_to_format(np.ones((18, 32), np.float32), 64, 36).shape == (36, 64)


# ------------------------------------------------------------------------------------------ tracking with gaps
needs_ai = pytest.mark.skipif(not (os.path.exists(os.path.join(VID_DIR, "vencoder.onnx"))
                                   and os.path.exists(os.path.join(FRAMES_DIR, "meta.json"))),
                              reason="exported video model / synthetic frames not present")
N, GAP = 8, (3, 4)


def get_rgb(f):
    x = cv2.cvtColor(cv2.imread(os.path.join(FRAMES_DIR, "frame_%04d.png" % f)), cv2.COLOR_BGR2RGB) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def with_gap(f):
    if f in GAP:
        raise FrameUnavailable(f, "Read error: No such file or directory")
    return get_rgb(f)


def target():
    meta = json.load(open(os.path.join(FRAMES_DIR, "meta.json")))
    return [{"name": "target", "frame": 0, "points": [tuple(meta["click_xy"])], "labels": [1]}]


def iou_vs_truth(points, f):
    from st_roto.geometry import Anchor, rasterize_spline
    a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:]), corner=False) for q in points]
    m = rasterize_spline(a, 720, 1280)
    gt = cv2.imread(os.path.join(FRAMES_DIR, "gt_%04d.png" % f), cv2.IMREAD_GRAYSCALE) > 127
    return (m & gt).sum() / float((m | gt).sum())


@pytest.fixture(scope="module")
def gap_run():
    pytest.importorskip("onnxruntime")
    from st_roto_nuke.track import track_objects
    return track_objects(with_gap, list(range(N)), target(), device="cpu")


@needs_ai
def test_unreadable_frames_are_skipped_and_reported(gap_run):
    pytest.importorskip("onnxruntime")
    from st_roto_nuke.track import track_objects
    o = gap_run["objects"][0]
    assert gap_run["missing_frames"] == list(GAP)
    assert sorted(o["keys"]) == [f for f in range(N) if f not in GAP]
    assert o["absent_frames"] == []                          # unreadable is not "object absent"
    full = track_objects(get_rgb, list(range(N)), target(), device="cpu")["objects"][0]   # same run, no gap
    assert all(o["keys"][f] == full["keys"][f] for f in range(GAP[0]))     # before the gap: unchanged
    assert min(iou_vs_truth(o["keys"][f], f) for f in o["keys"]) > 0.98     # after the gap: still on target


@needs_ai
def test_unreadable_prompt_frame_is_a_clear_error():
    pytest.importorskip("onnxruntime")
    from st_roto_nuke.track import track_objects
    objs = [dict(target()[0], frame=3)]
    with pytest.raises(ValueError, match="prompt frame 3"):
        track_objects(with_gap, list(range(N)), objs, device="cpu")


@needs_ai
def test_resume_across_a_gap_is_identical(tmp_path, gap_run):
    pytest.importorskip("onnxruntime")
    from st_roto.jobs import Cancelled
    from st_roto_nuke.track import read_checkpoint, track_objects

    class CancelAt(object):
        def __init__(self, n):
            self.n, self.calls = n, 0

        def check(self):
            self.calls += 1
            if self.calls > self.n:
                raise Cancelled("test")

        def report(self, *a):
            pass
    ck = str(tmp_path / "ck")
    with pytest.raises(Cancelled):
        track_objects(with_gap, list(range(N)), target(), device="cpu", job=CancelAt(6), checkpoint_dir=ck,
                      checkpoint_every=100)
    meta = read_checkpoint(ck)
    assert meta["next_frame"] == 6 and meta["missing"] == list(GAP)
    d = meta["definition"]
    resumed = track_objects(with_gap, d["frames"], d["objects"], device="cpu", checkpoint_dir=ck, resume=True)
    a, b = resumed["objects"][0], gap_run["objects"][0]
    assert a["keys"] == b["keys"] and a["reports"] == b["reports"]
    assert resumed["missing_frames"] == list(GAP)
