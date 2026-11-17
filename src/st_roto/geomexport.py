"""Shape geometry for 3D interchange (T-113: Alembic, REQ-180 "where suitable"). Pure Python + numpy.

ST-ROTO shapes are 2D cubic Bezier splines in canonical image space (x right, y DOWN, absolute handles,
st_roto.model). For 3D packages they are written in PIXEL units on the z = 0 plane with y UP and the origin at the
bottom-left image corner (Nuke's 2D convention, so x/y equal the Roto values in Nuke):
    X = x,  Y = height - y,  Z = 0
Two representations per shape and frame:
  * curve: a closed (periodic) cubic Bezier curve, control points p0, out0, in1, p1, out1, in2, ..., in0 (3 per
    anchor) - the exact spline;
  * mesh: one polygon of the outline sampled `per_segment` times per Bezier segment - for readers without curve
    support (Nuke's classic 3D reads Alembic meshes but not curves).
"""
from __future__ import annotations

import numpy as np


def to_3d(xy, height):
    """(N, 2) canonical -> (N, 3) pixel units, y up, z = 0."""
    a = np.asarray(xy, np.float64).reshape(-1, 2)
    return np.stack([a[:, 0], float(height) - a[:, 1], np.zeros(len(a))], -1)


def curve_points(points, height):
    """Periodic cubic Bezier control points (3 per anchor) of one key, in 3D (see module doc)."""
    seq = []
    for p in points:
        seq += [p[0:2], p[4:6]]                               # anchor, its outgoing handle
        seq.append(None)                                      # placeholder: incoming handle of the NEXT anchor
    n = len(points)
    for i in range(n):
        seq[3 * i + 2] = points[(i + 1) % n][2:4]
    return to_3d(np.array(seq, np.float64), height)


def mesh_polygon(points, height, per_segment: int = 16):
    """Outline polygon (M, 3) of one key, counter-clockwise in the y-up plane (front face towards +z)."""
    from .geometry import Anchor, sample_spline
    poly = sample_spline([Anchor(p=np.array(p[:2], float), h_in=np.array(p[2:4], float),
                                 h_out=np.array(p[4:6], float), corner=False) for p in points], per_segment)
    v = to_3d(poly, height)
    area2 = float(np.dot(v[:, 0], np.roll(v[:, 1], -1)) - np.dot(v[:, 1], np.roll(v[:, 0], -1)))
    return v if area2 >= 0 else v[::-1].copy()


def prim_name(name: str) -> str:
    """A valid USD/Alembic prim name from an object/shape name."""
    import re
    s = re.sub(r"[^A-Za-z0-9_]", "_", name or "shape")
    return s if s and not s[0].isdigit() else "_" + s
