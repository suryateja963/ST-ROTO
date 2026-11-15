"""Multi-piece objects and adaptive point counts (T-049)."""
import os

import numpy as np
import pytest

from st_roto import pieces
from st_roto.geometry import Anchor, rasterize_spline

H, W = 120, 200
YY, XX = np.mgrid[0:H, 0:W] + 0.5


def disc(cx, cy, r):
    return r - np.hypot(XX - cx, YY - cy)


def raster(points):
    a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in points]
    return rasterize_spline(a, H, W)


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def test_choose_count_grows_with_shape_complexity():
    circle = pieces.outer_loops(disc(100, 60, 40))[0][0]
    star_field = 30 + 12 * np.cos(5 * np.arctan2(YY - 60, XX - 100)) - np.hypot(XX - 100, YY - 60)
    star = pieces.outer_loops(star_field)[0][0]
    kc, ks = pieces.choose_count(circle), pieces.choose_count(star)
    assert kc <= 12 < ks


def test_split_object_gets_a_part_shape_with_collapsed_keys():
    """One blob splits into two on frames 2-3 and merges again: main follows the left piece, a part appears for the
    right one; the part is collapsed (renders nothing) where it does not exist; union of shapes ~ truth."""
    frames = list(range(6))
    truth = {}
    seq = pieces.Sequencer(count="auto")
    for f in frames:
        if f in (2, 3):
            field = np.maximum(disc(70, 60, 25), disc(130 + 5 * f, 60, 22))
        else:
            field = disc(100, 60, 40)
        truth[f] = field > 0
        seq.add(f, field, ref=f - 1 if f else None)
    out = seq.result(frames)
    assert sorted(out["main"]) == frames and len(out["parts"]) == 1
    part = out["parts"][0]
    assert sorted(part) == frames
    assert [pieces.is_collapsed(part[f]) for f in frames] == [True, True, False, False, True, True]
    for f in frames:
        u = raster(out["main"][f]) | raster(part[f])
        assert iou(u, truth[f]) > 0.98, f
        assert not raster(part[f]).any() or f in (2, 3)            # collapsed keys render nothing
    counts = {len(out["main"][f]) for f in frames}
    assert len(counts) == 1                                          # constant topology


def test_main_follows_its_piece_not_the_largest():
    seq = pieces.Sequencer(count=12)
    seq.add(0, disc(60, 60, 30), ref=None)
    seq.add(1, np.maximum(disc(62, 60, 20), disc(150, 60, 35)), ref=0)    # the other piece is now larger
    out = seq.result([0, 1])
    assert np.linalg.norm(pieces.centroid(out["main"][1]) - [62, 60]) < 3
    assert np.linalg.norm(pieces.centroid(out["parts"][0][1]) - [150, 60]) < 3


def test_speckle_and_holes():
    field = np.maximum(disc(100, 60, 40), disc(20, 20, 2))          # 2 px speckle ignored
    ring = np.minimum(disc(100, 60, 40), -disc(100, 60, 15))        # a ring: hole reported, not represented
    loops, holes = pieces.outer_loops(field)
    assert len(loops) == 1 and holes == 0
    seq = pieces.Sequencer(count=16)
    seq.add(0, ring)
    assert seq.result([0])["holes"] == {0: 1}


FRAMES = os.path.join(os.path.dirname(__file__), "..", "..", "research", "probes", "2026-11-15_video", "frames")


@pytest.mark.skipif(not os.path.exists(os.path.join(FRAMES, "gt_0023.png")), reason="synthetic frames not generated")
def test_synthetic_split_frame_is_complete():
    """The synthetic shot's object is cut in two by the occluder on frame 23 (truth: pieces of 14,652 and 10,766
    px^2); before T-049 only the larger piece was kept (IoU ~0.58 on that frame)."""
    cv2 = pytest.importorskip("cv2")
    seq = pieces.Sequencer(count=16)
    gts = {}
    for f in range(20, 27):
        gts[f] = cv2.imread(os.path.join(FRAMES, "gt_%04d.png" % f), cv2.IMREAD_GRAYSCALE) > 127
        seq.add(f, gts[f].astype(float) - 0.5, ref=f - 1 if f > 20 else None)
    out = seq.result(list(range(20, 27)))
    h, w = gts[23].shape
    def r(points):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in points]
        return rasterize_spline(a, h, w)
    union = r(out["main"][23]) | np.logical_or.reduce([r(p[23]) for p in out["parts"]])
    main_only = r(out["main"][23])
    assert iou(union, gts[23]) > 0.98 and iou(main_only, gts[23]) < 0.7
