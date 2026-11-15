"""Export ST-ROTO shape tracks to native Nuke Roto shapes (REQ-041: editable without ST-ROTO installed)."""
from __future__ import annotations

from .convention import key_to_nuke


def export_shape(store, shape_id: str, curves_knob, height: float, layer=None):
    """Create a native, fully keyed Roto shape from a stored ST-ROTO shape track.

    curves_knob: the `curves` knob of a Roto/RotoPaint node. height: format height in pixels.
    Keys are added BEFORE the point is appended to the shape: keys added afterwards are silently lost
    in Nuke 17.1 (measured, risk R-33). Returns the created nuke.rotopaint.Shape.
    """
    import nuke.rotopaint as rp            # lazy: keeps this module importable outside Nuke

    shape_row = store.row("shapes", shape_id)
    if shape_row is None:
        raise KeyError("no shape %s" % shape_id)
    keys = store.keys(shape_id)
    if not keys:
        raise ValueError("shape %s has no keys to export" % shape_id)
    n = int(shape_row["point_count"])
    converted = [(k["frame"], key_to_nuke(k["points"], height)) for k in keys]
    first = converted[0][1]
    cps = []
    for i in range(n):
        (cx, cy), _, _ = first[i]
        cp = rp.ShapeControlPoint(cx, cy)
        for frame, pts in converted:
            (cx, cy), lt, rt = pts[i]
            cp.center.addPositionKey(frame, rp.CVec2(cx, cy))
            cp.leftTangent.addPositionKey(frame, rp.CVec2(*lt))
            cp.rightTangent.addPositionKey(frame, rp.CVec2(*rt))
        cps.append(cp)
    shape = rp.Shape(curves_knob)
    for cp in cps:                          # append only after every key is set
        shape.append(cp)
    shape.name = _safe_name(shape_row["name"])
    (layer if layer is not None else curves_knob.rootLayer).append(shape)
    return shape


def _safe_name(name: str) -> str:
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    return out if out and not out[0].isdigit() else "s_" + out
