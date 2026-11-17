"""Camera geometry and epipolar correspondence (T-120)."""
import numpy as np
import pytest

from st_roto import cameras as cm, stereo


def _rot(rx, ry, rz):
    rx, ry, rz = np.radians([rx, ry, rz])
    X = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Y = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Z = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    return Z @ X @ Y


def _cam(t, r, focal=35.0, W=320, H=240, wt=(0.0, 0.0)):
    M = np.eye(4)
    M[:3, :3] = _rot(*r)
    M[:3, 3] = t
    K = cm.intrinsics(W, H, focal, 24.576, win_translate=wt)
    R, C = cm.from_world_matrix(M)
    return K, R, C


def test_projection_basics():
    K, R, C = _cam([0, 0, 0], [0, 0, 0])
    P = cm.projection(K, R, C)
    x, z = cm.project(P, [[0, 0, -5.0], [1, 1, -5.0]])
    assert np.allclose(x[0], [160, 120]) and z[0] > 0                     # centre; Nuke looks down -Z
    assert x[1][0] > 160 and x[1][1] < 120                                  # +X right, +Y up -> smaller row
    Kw, _, _ = _cam([0, 0, 0], [0, 0, 0], wt=(0.1, 0.0))
    assert cm.project(cm.projection(Kw, R, C), [[0, 0, -5.0]])[0][0][0] < 160   # window right -> content left


def test_fundamental_triangulate_scale():
    A = _cam([0, 0, 0], [0, 0, 0])
    B = _cam([0.6, 0.05, 0.1], [1.5, -4.0, 2.5], focal=30.0)
    PA, PB = cm.projection(*A), cm.projection(*B)
    F = cm.fundamental(PA, PB, A[2])
    rng = np.random.RandomState(0)
    pts = np.c_[rng.uniform(-1, 1, 20), rng.uniform(-0.7, 0.7, 20), rng.uniform(-9, -3, 20)]
    xa, _ = cm.project(PA, pts)
    xb, _ = cm.project(PB, pts)
    for a_, b_, X in zip(xa, xb, pts):
        assert abs(cm.line_distance(cm.epipolar_line(F, a_), b_)) < 1e-6
        assert np.allclose(cm.triangulate(PA, PB, a_, b_), X, atol=1e-6)
    s = cm.scale_along(A, B, xa[0])(xb[0] - xa[0])
    za = (A[1] @ (pts[0] - A[2]))[2]; zb = (B[1] @ (pts[0] - B[2]))[2]
    assert abs(s - (B[0][0, 0] / zb) / (A[0][0, 0] / za)) < 1e-9


def test_epipolar_search_finds_a_shift_off_the_horizontal():
    rng = np.random.RandomState(2)
    H, W = 200, 300
    img_a = rng.rand(H, W).astype(np.float32)
    k = np.ones(5) / 5
    for ax in (0, 1):
        img_a = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), ax, img_a)
    dx, dy = -37, 21                                                        # diagonal: not a rectified pair
    img_b = np.roll(np.roll(img_a, dy, 0), dx, 1)
    mask = np.zeros((H, W), bool); mask[70:120, 140:200] = True
    c = np.array([170.0, 95.0])
    # F of a pure translation along (dx, dy) in the image plane: lines through the epipole at infinity
    d = np.array([dx, dy], float) / np.hypot(dx, dy)
    F = np.array([[0, 0, -d[1]], [0, 0, d[0]], [d[1], -d[0], 0]], float)
    assert abs(cm.line_distance(cm.epipolar_line(F, c), c + [dx, dy])) < 1e-6
    r = stereo.estimate_shift_epipolar(img_a, img_b, mask, F)
    assert abs(r["dx"] - dx) < 0.6 and abs(r["dy"] - dy) < 0.6
    h = stereo.estimate_disparity(img_a, img_b, mask, max_dx=60, max_dy=4)  # the rectified search cannot
    assert abs(h["dy"] - dy) > 10
    with pytest.raises(ValueError):
        stereo.estimate_shift_epipolar(img_a, img_b, np.zeros((H, W), bool), F)


def test_epipolar_distances_and_unrectified_consistency():
    ga = {f: {"area": 400.0, "cx": 100.0 + f, "cy": 50.0, "x0": 90.0, "y0": 40.0, "x1": 110.0, "y1": 60.0}
          for f in range(5)}
    gb = {f: dict(g, cx=g["cx"] - 20, cy=g["cy"] + 3 * f, y0=g["y0"] + 3 * f, y1=g["y1"] + 3 * f, area=700.0)
          for f, g in ga.items()}
    F = np.array([[0, 0, 0], [0, 0, -1], [0, 1, 0]], float)                 # horizontal epipolar lines
    dist = stereo.epipolar_distances(ga, gb, lambda f: F)
    assert dist[0] == 0 and abs(dist[4] - 12) < 1e-9
    rect = stereo.consistency(ga, gb)
    unrect = stereo.consistency(ga, gb, rectified=False)
    assert any("size" in r for _, r in rect["flags"])                       # 75 % larger: flagged when rectified
    assert not any("size" in r or "vertically" in r for _, r in unrect["flags"])
