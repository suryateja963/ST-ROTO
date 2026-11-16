"""AI prompt points (include / exclude clicks), stored as JSON on the host node. Pure Python.

A prompt is {"frame": int, "x": float, "y": float, "label": 1 | 0, "object": str} in canonical image coordinates
(y down, st_roto.model). Several objects can be prompted on one node (T-067); each object's points must be on ONE
frame (the frame its tracking starts from). Points without "object" (files written before T-067) belong to the
`default` object the caller passes (the node's current object name).

Box prompts (OQ-25, T-079): an object may have ONE box, stored as two points with SAM's corner labels
BOX_TL (2, top-left) and BOX_BR (3, bottom-right) on the object's prompt frame. On real footage (SA-V, T-068) a
single click picked the wrong object in 19 of 51 first frames, a box + click in 2 of 51. The tracker receives the
box corners first, then the clicks (SAM 2 reference order).
"""
from __future__ import annotations

import json

INCLUDE, EXCLUDE = 1, 0
BOX_TL, BOX_BR = 2, 3
LABELS = (INCLUDE, EXCLUDE, BOX_TL, BOX_BR)
MIN_BOX = 2.0          # pixels: a smaller box is a mistake (handles on top of each other)
_REQUIRED = {"frame", "x", "y", "label"}


def load(text: str) -> list:
    if not text or not text.strip():
        return []
    pts = json.loads(text)
    for p in pts:
        keys = set(p)
        if not (_REQUIRED <= keys <= _REQUIRED | {"object"}) or p["label"] not in LABELS:
            raise ValueError("invalid prompt point %r" % (p,))
    return pts


def dump(points: list) -> str:
    return json.dumps(points, separators=(",", ":"))


def _owner(p, default):
    return p.get("object") or default


def add(text: str, frame: int, x: float, y: float, label: int, obj: str = None) -> str:
    """Add a point for object `obj` (None: an untagged point, the pre-T-067 format)."""
    pts = load(text)
    mine = [p for p in pts if _owner(p, obj) == obj]
    if mine and any(p["frame"] != int(frame) for p in mine):
        raise ValueError("all prompt points of %s must be on one frame (existing: frame %d); clear its points first"
                         % ("this object" if obj is None else repr(obj), mine[0]["frame"]))
    p = {"frame": int(frame), "x": float(x), "y": float(y), "label": int(label)}
    if obj is not None:
        p["object"] = obj
    pts.append(p)
    return dump(pts)


def set_box(text: str, frame: int, x0: float, y0: float, x1: float, y1: float, obj: str = None) -> str:
    """Set (replace) the box of object `obj` on `frame`; corners in canonical coordinates, any order."""
    if abs(x1 - x0) < MIN_BOX or abs(y1 - y0) < MIN_BOX:
        raise ValueError("the box is too small (%.0f x %.0f px): drag its corners around the object"
                         % (abs(x1 - x0), abs(y1 - y0)))
    pts = [p for p in load(text) if not (_owner(p, obj) == obj and p["label"] in (BOX_TL, BOX_BR))]
    mine = [p for p in pts if _owner(p, obj) == obj]
    if mine and any(p["frame"] != int(frame) for p in mine):
        raise ValueError("all prompts of %s must be on one frame (existing: frame %d); clear its points first"
                         % ("this object" if obj is None else repr(obj), mine[0]["frame"]))
    for lbl, x, y in ((BOX_TL, min(x0, x1), min(y0, y1)), (BOX_BR, max(x0, x1), max(y0, y1))):
        p = {"frame": int(frame), "x": float(x), "y": float(y), "label": lbl}
        if obj is not None:
            p["object"] = obj
        pts.append(p)
    return dump(pts)


def clear_box(text: str, obj: str, default: str = None) -> str:
    """Remove the box of one object, keep its clicks."""
    return dump([p for p in load(text) if not (_owner(p, default) == obj and p["label"] in (BOX_TL, BOX_BR))])


def clear(text: str, obj: str, default: str = None) -> str:
    """Remove the points of one object (untagged points count as `default`)."""
    return dump([p for p in load(text) if _owner(p, default) != obj])


def groups(text: str, default: str = None) -> list:
    """-> [{"name", "frame", "points": [(x, y)], "labels"}] per object, in order of first appearance."""
    out = {}
    for p in load(text):
        g = out.setdefault(_owner(p, default), {"name": _owner(p, default), "frame": p["frame"], "points": [],
                                                "labels": []})
        if p["frame"] != g["frame"]:
            raise ValueError("prompt points of %r are on several frames (%d, %d)" % (g["name"], g["frame"], p["frame"]))
        g["points"].append((p["x"], p["y"])); g["labels"].append(p["label"])
    return list(out.values())


def summary(text: str, default: str = None) -> str:
    gs = groups(text, default)
    if not gs:
        return "no points"
    parts = []
    for g in gs:
        inc = sum(1 for v in g["labels"] if v == INCLUDE)
        exc = sum(1 for v in g["labels"] if v == EXCLUDE)
        s = "frame %d: %s%d include, %d exclude" % (g["frame"], "box + " if BOX_TL in g["labels"] else "", inc, exc)
        parts.append(s if len(gs) == 1 and g["name"] in (None, default) else "%s %s" % (g["name"], s))
    return "; ".join(parts)


def for_tracker(text: str, default: str = None):
    """-> (frame, [(x, y), ...], [label, ...]) of a node with ONE prompted object; raises if there is no include
    point. Several objects: use `objects_for_tracker`."""
    gs = objects_for_tracker(text, default)
    if len(gs) != 1:
        raise ValueError("points for %d objects; use objects_for_tracker" % len(gs))
    return gs[0]["frame"], gs[0]["points"], gs[0]["labels"]


def objects_for_tracker(text: str, default: str = None) -> list:
    """Like `groups`, but every object needs an include point or a box (artist-readable error otherwise); box
    corners come first (SAM 2 reference order: box, then clicks)."""
    gs = groups(text, default)
    if not gs:
        raise ValueError("add an include point or a box")
    for g in gs:
        if INCLUDE not in g["labels"] and BOX_TL not in g["labels"]:
            raise ValueError("add an include point or a box%s" % ("" if g["name"] in (None, default)
                                                                  else " for %r" % g["name"]))
        order = sorted(range(len(g["labels"])), key=lambda i: g["labels"][i] not in (BOX_TL, BOX_BR))
        g["points"] = [g["points"][i] for i in order]
        g["labels"] = [g["labels"][i] for i in order]
    return gs
