"""Camera geometry for multi-view correspondence (T-120, REQ-115 'multi-camera correspondence when camera
information is available'). Pure Python + numpy.

Conventions: a camera is (K, R, C): K the 3x3 intrinsics in ST-ROTO's canonical image space (pixels, x right,
y DOWN, origin top-left corner), R the 3x3 world-to-camera rotation, C the camera centre in world coordinates.
Nuke cameras look down their local -Z with +Y up; `from_nuke` converts its parameters (focal, apertures, window
translate/scale, world matrix) into that form, so x_image = project(P, X) matches Nuke's own render (verified in
research/probes/2026-11-18_multicam).
"""
from __future__ import annotations

import numpy as np


def intrinsics(width, height, focal, haperture, vaperture=None, win_translate=(0.0, 0.0), win_scale=(1.0, 1.0)):
    """K for a Nuke camera (measured against Nuke 17's own render, research/probes/2026-11-18_multicam): the
    horizontal aperture spans the image width and pixels are square (fy = fx; vaperture does not change the
    projection); win_translate moves the camera WINDOW in units of half the image width, so the image content moves
    the opposite way: +x shifts content left, +y (Nuke's y up) shifts it down. Measured: 14 projected points within
    0.33 px of Nuke's render for 3 non-rectified cameras incl. roll, toe-in and window translate."""
    fx = float(focal) / float(haperture) * float(width) / float(win_scale[0])
    fy = fx * float(win_scale[0]) / float(win_scale[1])
    cx = width / 2.0 - float(win_translate[0]) * width / 2.0 / float(win_scale[0])
    cy = height / 2.0 + float(win_translate[1]) * width / 2.0 / float(win_scale[1])
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])


def from_world_matrix(world4x4):
    """(R world->camera in canonical axes, C) from a camera's 4x4 world matrix (camera->world, Nuke axes: -Z view,
    +Y up). Canonical camera axes: x right, y down, z forward = Nuke (x, -y, -z)."""
    M = np.asarray(world4x4, np.float64).reshape(4, 4)
    Rcw = M[:3, :3]                                  # columns: camera x, y, z axes in world (Nuke axes)
    C = M[:3, 3].copy()
    flip = np.diag([1.0, -1.0, -1.0])                # Nuke camera axes -> canonical (y down, z forward)
    R = flip @ Rcw.T                                  # world -> canonical camera
    return R, C


def projection(K, R, C):
    """3x4 projection matrix P = K [R | -R C]."""
    return K @ np.hstack([R, -R @ np.asarray(C, np.float64).reshape(3, 1)])


def project(P, X):
    """World points (N, 3) -> image points (N, 2) (canonical) and depth (N,) (positive in front)."""
    Xh = np.hstack([np.asarray(X, np.float64).reshape(-1, 3), np.ones((len(np.asarray(X).reshape(-1, 3)), 1))])
    x = Xh @ np.asarray(P).T
    return x[:, :2] / x[:, 2:3], x[:, 2]


def _skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], np.float64)


def fundamental(P1, P2, C1):
    """F with x2^T F x1 = 0 for the same world point seen in images 1 and 2: F = [e2]x P2 P1^+, e2 = P2 C1."""
    e2 = np.asarray(P2) @ np.append(np.asarray(C1, np.float64), 1.0)
    F = _skew(e2) @ np.asarray(P2) @ np.linalg.pinv(np.asarray(P1))
    n = np.linalg.norm(F)
    return F / n if n > 0 else F


def epipolar_line(F, x1):
    """Line (a, b, c), a x + b y + c = 0, normalised so (a, b) is a unit vector, in image 2 for point x1 of image 1."""
    l = np.asarray(F) @ np.array([x1[0], x1[1], 1.0])
    return l / max(np.hypot(l[0], l[1]), 1e-12)


def triangulate(P1, P2, x1, x2):
    """World point (3,) seen at x1 in image 1 and x2 in image 2 (linear DLT)."""
    A = np.array([x1[0] * P1[2] - P1[0], x1[1] * P1[2] - P1[1], x2[0] * P2[2] - P2[0], x2[1] * P2[2] - P2[1]],
                 np.float64)
    _, _, vt = np.linalg.svd(A)
    X = vt[-1]
    return X[:3] / X[3]


def image_scale(K1, R1, C1, K2, R2, C2, X):
    """How much larger an object at world point X appears in camera 2 than in camera 1 (focal / depth ratio)."""
    z1 = float((np.asarray(R1) @ (np.asarray(X) - np.asarray(C1)))[2])
    z2 = float((np.asarray(R2) @ (np.asarray(X) - np.asarray(C2)))[2])
    if z1 <= 0 or z2 <= 0:
        return 1.0
    return (float(K2[0, 0]) / z2) / (float(K1[0, 0]) / z1)


def scale_along(cam1, cam2, x1):
    """shift -> how much larger camera 2 sees an object whose centre is at x1 in image 1 and at x1 + shift in
    image 2 (depth by triangulation). cam = (K, R, C). Used to compare candidates at their own scale (T-120)."""
    K1, R1, C1 = cam1
    K2, R2, C2 = cam2
    P1, P2 = projection(K1, R1, C1), projection(K2, R2, C2)

    def f(shift):
        X = triangulate(P1, P2, x1, (x1[0] + shift[0], x1[1] + shift[1]))
        return image_scale(K1, R1, C1, K2, R2, C2, X)
    return f


def line_distance(l, x):
    """Signed distance (px) of image point x from a normalised line."""
    return float(l[0] * x[0] + l[1] * x[1] + l[2])
