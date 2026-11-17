"""3D interchange geometry (T-113): curve control points, outline polygons, prim names."""
import numpy as np

from st_roto import geomexport as ge
from st_roto.geometry import mask_to_points


def test_curve_points_order_and_coordinates():
    pts = [[10, 20, 9, 20, 11, 20], [30, 20, 29, 20, 31, 20], [20, 40, 21, 40, 19, 40]]
    c = ge.curve_points(pts, height=100)
    assert c.shape == (9, 3)
    # p0, out0, in1, p1, out1, in2, p2, out2, in0 ; y flipped (100 - y), z = 0
    exp = [(10, 80), (11, 80), (29, 80), (30, 80), (31, 80), (21, 60), (20, 60), (19, 60), (9, 80)]
    assert np.allclose(c[:, :2], exp) and np.all(c[:, 2] == 0)


def test_mesh_polygon_is_ccw_and_matches_area():
    yy, xx = np.mgrid[0:100, 0:120] + 0.5
    pts = mask_to_points(30 - np.hypot(xx - 60, yy - 50), count=16)
    v = ge.mesh_polygon(pts, 100, per_segment=16)
    a2 = float(np.dot(v[:, 0], np.roll(v[:, 1], -1)) - np.dot(v[:, 1], np.roll(v[:, 0], -1)))
    assert a2 > 0                                                           # counter-clockwise (front = +z)
    assert abs(a2 / 2 - np.pi * 900) / (np.pi * 900) < 0.01
    assert abs(v[:, 1].mean() - 50) < 0.5                                   # y up: 100 - 50


def test_prim_names():
    assert ge.prim_name("hero arm.L") == "hero_arm_L"
    assert ge.prim_name("1st") == "_1st"
    assert ge.prim_name("") == "shape"
