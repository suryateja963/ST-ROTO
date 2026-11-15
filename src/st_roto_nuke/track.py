"""Click -> SAM 2.1 video tracking -> stored, keyed ST-ROTO shape (vertical slice, T-055).

`track_object` contains no Nuke calls: frames come from an injected `get_rgb(frame)` (headless tests pass a direct
renderer, the GUI passes a main-thread-marshalled one). `apply_result` writes through the command bus as actor "ai",
so the protection rules (REQ-042) apply, and returns the shape id for export.
"""
from __future__ import annotations

import json
import os

import numpy as np

from st_roto import model as m
from st_roto.geometry import mask_to_points
from . import colour

ANCHORS = 16


def models_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "models", "onnx")      # dev layout: <repo>/models/onnx


def track_object(get_rgb, frames, click_frame, click_xy, model="sam2.1-hiera-tiny", device="auto",
                 job=None, anchors=ANCHORS, labels=None):
    """Track one object from prompt points on one frame. Returns dict with per-frame points and run metadata.

    frames: ordered list of shot frame numbers (any integers); click_frame must be the first of them (forward only, v0).
    click_xy: one (x, y) or a list of (x, y) in canonical image coordinates (y down); labels: 1 include / 0 exclude
    (default: all include).
    """
    pts = [tuple(click_xy)] if isinstance(click_xy[0], (int, float)) else [tuple(p) for p in click_xy]
    labels = [1] * len(pts) if labels is None else list(labels)
    from st_roto_ai.sam2 import Sam2Video          # AI layer is optional: imported only when tracking is requested
    frames = list(frames)
    if not frames or frames[0] != click_frame:
        raise ValueError("v0 tracks forward only: the clicked frame must be the first frame of the range")
    tracker = Sam2Video(os.path.join(models_root(), model, "video"), device=device, num_total_frames=len(frames))
    keys, prev_anchor0, absent = {}, None, []
    for pos, frame in enumerate(frames):
        if job:
            job.check(); job.report(pos / float(len(frames)), "frame %d (%d/%d)" % (frame, pos + 1, len(frames)))
        rgb = colour.to_model_input(get_rgb(frame))
        enc = tracker.encode(rgb)
        out = tracker.add_points(pos, enc, pts, labels) if pos == 0 else tracker.track(pos, enc)
        pts = mask_to_points(out["logits"], count=anchors, start_hint=prev_anchor0) if out["object_score"] > 0 else []
        if pts:
            keys[frame] = pts
            prev_anchor0 = np.array(pts[0][:2])
        else:
            absent.append(frame)
    if job:
        job.report(1.0, "tracked %d frames" % len(frames))
    return {"keys": keys, "absent_frames": absent, "device": tracker.report.active,
            "device_fallback": tracker.report.fallback, "device_reason": tracker.report.reason,
            "generator": json.dumps({"model": model, "colour": colour.TRANSFORM_ID, "anchors": anchors,
                                     "prompts": {"frame": click_frame, "points": [list(p) for p in pts],
                                                 "labels": labels}}, sort_keys=True)}


def apply_result(bus, shot_id, object_name, result, anchors=ANCHORS):
    """Create an AI object + shape and one key per tracked frame. Returns (object_id, shape_id)."""
    oid, sid = m.new_id(), m.new_id()
    bus.execute({"op": "create_object", "row": {"id": oid, "shot_id": shot_id, "name": object_name}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": sid, "object_id": oid, "name": object_name, "point_count": anchors,
                                               "generator": result["generator"]}}, actor=m.ACTOR_AI)
    for frame in sorted(result["keys"]):
        bus.execute({"op": "set_key", "shape_id": sid, "frame": frame, "points": result["keys"][frame],
                     "generator": result["generator"]}, actor=m.ACTOR_AI)
    return oid, sid
