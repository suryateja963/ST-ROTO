"""Unit tests for st_roto.geometry (Bezier fitting)."""
import numpy as np
import cv2
import pytest

from st_roto.geometry import fit_closed_contour, max_deviation, sample_spline, detect_corners, smooth_closed


def _contour(mask):
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cnts, key=cv2.contourArea)[:, 0, :].astype(np.float64)


def _raster(anchors, shape):
    m = np.zeros(shape, np.uint8)
    pts = np.round(sample_spline(anchors, 128) * 16).astype(np.int32)        # 4-bit sub-pixel precision
    cv2.fillPoly(m, [pts], 1, lineType=cv2.LINE_8, shift=4)
    return m.astype(bool)


def _iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def test_circle_is_smooth_and_compact():
    m = np.zeros((600, 600), np.uint8)
    cv2.circle(m, (300, 300), 200, 1, -1)
    c = _contour(m)
    a = fit_closed_contour(c, tol=1.0)
    assert not any(x.corner for x in a), "a circle has no corners"
    assert len(a) <= 8, f"circle should need few anchors, got {len(a)}"
    mx, mean = max_deviation(a, c)
    assert mx < 1.6 and mean < 0.7
    assert _iou(_raster(a, m.shape), m.astype(bool)) > 0.995


def test_square_gets_four_corners():
    m = np.zeros((500, 500), np.uint8)
    cv2.rectangle(m, (100, 120), (400, 380), 1, -1)
    c = _contour(m)
    a = fit_closed_contour(c, tol=1.0)
    assert sum(x.corner for x in a) == 4
    assert _iou(_raster(a, m.shape), m.astype(bool)) > 0.99


def test_star_corners_and_accuracy():
    m = np.zeros((700, 700), np.uint8)
    ang = np.radians(np.arange(10) * 36 - 90)
    rad = np.where(np.arange(10) % 2 == 0, 300, 120)
    star = np.stack([350 + rad * np.cos(ang), 350 + rad * np.sin(ang)], 1).astype(np.int32)
    cv2.fillPoly(m, [star], 1)
    c = _contour(m)
    a = fit_closed_contour(c, tol=1.0)
    assert sum(x.corner for x in a) >= 9            # 5 tips + 5 inner corners (one may merge)
    assert _iou(_raster(a, m.shape), m.astype(bool)) > 0.985


def test_tolerance_controls_point_count():
    m = np.zeros((600, 800), np.uint8)
    cv2.ellipse(m, (400, 300), (300, 150), 25, 0, 360, 1, -1)
    c = _contour(m)
    loose = fit_closed_contour(c, tol=3.0)
    tight = fit_closed_contour(c, tol=0.5)
    assert len(tight) >= len(loose)


def test_smoothing_preserves_closed_length():
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    pts = np.stack([100 * np.cos(t), 100 * np.sin(t)], 1)
    s = smooth_closed(pts, 2.0)
    assert s.shape == pts.shape
    assert np.abs(np.linalg.norm(s, axis=1) - 100).max() < 0.2


def test_fixed_count_topology_and_correspondence():
    from st_roto.geometry import fit_fixed_count
    prev = None
    for f in range(5):                                   # moving, rotating ellipse
        m = np.zeros((600, 800), np.uint8)
        cv2.ellipse(m, (300 + 30 * f, 300), (200, 110), 10 * f, 0, 360, 1, -1)
        c = _contour(m)
        a = fit_fixed_count(c, 16, start_hint=None if prev is None else prev[0].p)
        assert len(a) == 16
        assert _iou(_raster(a, m.shape), m.astype(bool)) > 0.995
        if prev is not None:                             # anchor 0 must move smoothly, not jump around the loop
            assert np.linalg.norm(a[0].p - prev[0].p) < 80
        prev = a


def test_too_short_contour_raises():
    with pytest.raises(ValueError):
        fit_closed_contour(np.array([[0, 0], [1, 0], [0, 1]]))
