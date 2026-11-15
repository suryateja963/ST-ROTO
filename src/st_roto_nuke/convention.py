"""Nuke Roto conventions, measured on Nuke 17.1v3 (research/probes/2026-11-15_bezier, 2026-11-15_video).

ST-ROTO canonical space (st_roto.model): x right, y DOWN, origin = top-left corner of the image.
Nuke Roto space: x right, y UP, origin = bottom-left corner of the format.
Nuke ShapeControlPoint tangents are RELATIVE to the point and equal to 2 x the cubic Bezier handle offset;
`leftTangent` points to the previous control point, `rightTangent` to the next one.
These facts are re-verified per Nuke version by tests/nuke (risk R-32).
"""
from __future__ import annotations

NUKE_TANGENT_SCALE = 2.0


def point_to_nuke(x: float, y: float, height: float):
    """Canonical (y down) -> Nuke (y up). Both spaces use the image corner as origin, so no 0.5 offset here."""
    return float(x), float(height) - float(y)


def tangents_to_nuke(px, py, hin_x, hin_y, hout_x, hout_y):
    """Absolute canonical handles -> (leftTangent, rightTangent) relative Nuke vectors (y flipped, scaled)."""
    s = NUKE_TANGENT_SCALE
    left = (s * (hin_x - px), -s * (hin_y - py))
    right = (s * (hout_x - px), -s * (hout_y - py))
    return left, right


def key_to_nuke(points, height):
    """One stored key (list of [x,y,hin_x,hin_y,hout_x,hout_y]) -> list of (centre, left, right) in Nuke terms."""
    out = []
    for x, y, hix, hiy, hox, hoy in points:
        c = point_to_nuke(x, y, height)
        lt, rt = tangents_to_nuke(x, y, hix, hiy, hox, hoy)
        out.append((c, lt, rt))
    return out


def nuke_to_key(centre, left, right, height):
    """Inverse of key_to_nuke for one point (used by the native Roto importer)."""
    s = NUKE_TANGENT_SCALE
    x, y = float(centre[0]), float(height) - float(centre[1])
    hin = (x + left[0] / s, y - left[1] / s)
    hout = (x + right[0] / s, y - right[1] / s)
    return [x, y, hin[0], hin[1], hout[0], hout[1]]
