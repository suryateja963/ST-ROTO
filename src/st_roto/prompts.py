"""AI prompt points (include / exclude clicks), stored as JSON on the host node. Pure Python.

A prompt is {"frame": int, "x": float, "y": float, "label": 1 | 0, "object": str} in canonical image coordinates
(y down, st_roto.model). Several objects can be prompted on one node (T-067); each object's points must be on ONE
frame (the frame its tracking starts from). Points without "object" (files written before T-067) belong to the
`default` object the caller passes (the node's current object name).
"""
from __future__ import annotations

import json

INCLUDE, EXCLUDE = 1, 0
_REQUIRED = {"frame", "x", "y", "label"}


def load(text: str) -> list:
    if not text or not text.strip():
        return []
    pts = json.loads(text)
    for p in pts:
        keys = set(p)
        if not (_REQUIRED <= keys <= _REQUIRED | {"object"}) or p["label"] not in (INCLUDE, EXCLUDE):
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
        s = "frame %d: %d include, %d exclude" % (g["frame"], inc, len(g["labels"]) - inc)
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
    """Like `groups`, but every object needs at least one include point (artist-readable error otherwise)."""
    gs = groups(text, default)
    if not gs:
        raise ValueError("add at least one include point")
    for g in gs:
        if INCLUDE not in g["labels"]:
            raise ValueError("add at least one include point%s" % ("" if g["name"] in (None, default)
                                                                    else " for %r" % g["name"]))
    return gs
