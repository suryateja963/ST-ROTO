"""Sub-pixel contour tracing and exact rasterisation (st_roto.geometry)."""
import numpy as np

from st_roto.geometry import trace_contours, rasterize_closed, fit_closed_contour, fit_fixed_count, rasterize_spline


def disk_field(h, w, cx, cy, r):
    yy, xx = np.mgrid[0:h, 0:w]
    return r - np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)          # signed distance, canonical coords


def exact_disk(h, w, cx, cy, r):
    return disk_field(h, w, cx, cy, r) > 0


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def test_soft_field_contour_is_subpixel_accurate():
    loops = trace_contours(disk_field(300, 400, 201.3, 148.7, 97.25))
    assert len(loops) == 1
    rr = np.hypot(loops[0][:, 0] - 201.3, loops[0][:, 1] - 148.7)
    assert abs(rr.mean() - 97.25) < 0.01 and np.abs(rr - 97.25).max() < 0.05


def test_binary_mask_contour_sits_on_pixel_edges():
    m = exact_disk(300, 400, 200.0, 150.0, 90.0)
    loops = trace_contours(m.astype(float) - 0.5)
    rr = np.hypot(loops[0][:, 0] - 200.0, loops[0][:, 1] - 150.0)
    assert abs(rr.mean() - 90.0) < 0.35            # staircase averages close to the true edge, not 0.5 px inside


def test_rasterize_closed_matches_exact_disk():
    t = np.linspace(0, 2 * np.pi, 4000, endpoint=False)
    poly = np.stack([200 + 90 * np.cos(t), 150 + 90 * np.sin(t)], 1)
    assert iou(rasterize_closed(poly, 300, 400), exact_disk(300, 400, 200, 150, 90)) > 0.9995


def test_fit_from_binary_mask_reproduces_mask():
    m = exact_disk(300, 400, 200.0, 150.0, 90.0)
    loop = trace_contours(m.astype(float) - 0.5)[0]
    for anchors in (fit_closed_contour(loop, tol=0.5), fit_fixed_count(loop, 16)):
        assert iou(rasterize_spline(anchors, 300, 400), m) > 0.997


def test_holes_and_multiple_components():
    m = exact_disk(300, 500, 120, 150, 80) & ~exact_disk(300, 500, 120, 150, 30)
    m |= exact_disk(300, 500, 380, 150, 60)
    loops = trace_contours(m.astype(float) - 0.5)
    assert len(loops) == 3                         # outer A, hole in A, outer B


def test_border_touching_object_closes():
    m = np.zeros((50, 60), bool); m[:, :20] = True
    loops = trace_contours(m.astype(float) - 0.5)
    assert len(loops) == 1 and iou(rasterize_closed(loops[0], 50, 60), m) > 0.999
