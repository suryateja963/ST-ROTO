"""Benchmark metrics (T-107): known values on simple shapes."""
import numpy as np
import pytest

pytest.importorskip("cv2")
from st_roto import metrics as mt     # noqa: E402

H, W = 100, 100


def sq(x0, y0, x1, y1):
    a = np.zeros((H, W), np.float32); a[y0:y1, x0:x1] = 1.0
    return a


def test_region_metrics_exact():
    a, b = sq(0, 0, 50, 100), sq(25, 0, 75, 100)          # overlap 25 cols of 50
    assert mt.iou(a, b) == pytest.approx(1 / 3) and mt.dice(a, b) == pytest.approx(0.5)
    assert mt.iou(a, a) == 1.0 and mt.iou(sq(0, 0, 0, 0), sq(0, 0, 0, 0)) == 1.0
    assert mt.mae(a, b) == pytest.approx(0.5) and mt.sad(a, b) == pytest.approx(5.0) and mt.mse(a, b) == pytest.approx(0.5)


def test_boundary_and_contour():
    a = sq(20, 20, 80, 80)
    assert mt.boundary_f(a, a) == 1.0 and mt.hd95(a, a) == 0.0
    shifted = sq(23, 20, 83, 80)                            # 3 px shift, tolerance 1 px at 100x100
    assert mt.boundary_f(a, shifted) < 0.7 and 2.5 < mt.hd95(a, shifted) <= 3.5
    assert mt.boundary_f(a, sq(0, 0, 0, 0)) == 0.0 and mt.hd95(a, sq(0, 0, 0, 0)) == float("inf")


def test_temporal_stability_identity():
    g = [sq(10 + t, 10, 50 + t, 50) for t in range(4)]
    assert mt.temporal_error(g, g) == 0.0
    flick = [g[0], sq(0, 0, 0, 0), g[2], g[3]]             # dropped on frame 1
    assert mt.temporal_error(flick, g) > 0.05
    st = mt.stability([1.0, 0.0, 0.9, 0.95])
    assert st == {"kept_fraction": 0.75, "losses": 1}
    a, b = sq(0, 0, 40, 40), sq(60, 60, 100, 100)
    assert mt.identity_preservation({"x": a, "y": b}, {"x": a, "y": b}) == 1.0
    assert mt.identity_preservation({"x": b, "y": a}, {"x": a, "y": b}) == 0.0


def test_scores_and_overall_weights():
    g = [sq(10 + t, 10, 50 + t, 50) for t in range(3)]
    s = mt.sequence_scores(g, g)
    c = mt.category_scores(s)
    assert all(v == pytest.approx(1.0) for v in c.values())
    assert mt.overall(c) == pytest.approx(1.0) and sum(mt.WEIGHTS.values()) == pytest.approx(1.0)
    bad = mt.category_scores(mt.sequence_scores([sq(0, 0, 0, 0)] * 3, g))
    assert mt.overall(bad) < 0.3
