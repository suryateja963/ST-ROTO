"""AI prompt points (include / exclude clicks), stored as JSON on the host node. Pure Python.

A prompt is {"frame": int, "x": float, "y": float, "label": 1 | 0} in canonical image coordinates
(y down, st_roto.model). v0 trackers accept prompts on ONE frame only.
"""
from __future__ import annotations

import json

INCLUDE, EXCLUDE = 1, 0


def load(text: str) -> list:
    if not text or not text.strip():
        return []
    pts = json.loads(text)
    for p in pts:
        if set(p) != {"frame", "x", "y", "label"} or p["label"] not in (INCLUDE, EXCLUDE):
            raise ValueError("invalid prompt point %r" % (p,))
    return pts


def dump(points: list) -> str:
    return json.dumps(points, separators=(",", ":"))


def add(text: str, frame: int, x: float, y: float, label: int) -> str:
    pts = load(text)
    if pts and any(p["frame"] != int(frame) for p in pts):
        raise ValueError("all prompt points must be on one frame in this version (existing: frame %d); "
                         "clear the points first" % pts[0]["frame"])
    pts.append({"frame": int(frame), "x": float(x), "y": float(y), "label": int(label)})
    return dump(pts)


def summary(text: str) -> str:
    pts = load(text)
    if not pts:
        return "no points"
    inc = sum(1 for p in pts if p["label"] == INCLUDE)
    return "frame %d: %d include, %d exclude" % (pts[0]["frame"], inc, len(pts) - inc)


def for_tracker(text: str):
    """-> (frame, [(x, y), ...], [label, ...]); raises if there is no include point."""
    pts = load(text)
    if not any(p["label"] == INCLUDE for p in pts):
        raise ValueError("add at least one include point")
    return pts[0]["frame"], [(p["x"], p["y"]) for p in pts], [p["label"] for p in pts]
