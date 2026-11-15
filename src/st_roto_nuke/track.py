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


def retrack_object(get_rgb, store, shape_id, frames, width, height, model="sam2.1-hiera-tiny", device="auto",
                   job=None):
    """Re-track a stored shape using every ARTIST key as a mask prompt (plus the original click prompts, if any),
    forward from the first conditioning frame and in reverse to the first frame of `frames` (master prompt §11:
    propagate corrections forward and backward). Returns {frame: points | None} for frames AI may write
    (artist keys are not included: they are never overwritten)."""
    from st_roto_ai.sam2 import Sam2Video
    from st_roto.geometry import Anchor, rasterize_spline
    shape = store.row("shapes", shape_id)
    if shape is None:
        raise KeyError("no shape %s" % shape_id)
    anchors = int(shape["point_count"])
    frames = sorted(frames)
    pos = {f: i for i, f in enumerate(frames)}
    artist = {k["frame"]: k["points"] for k in store.keys(shape_id) if k["origin"] in (m.ARTIST_CREATED, m.ARTIST_MODIFIED_AI, m.IMPORTED_NATIVE)}
    gen = json.loads(shape["generator"]) if shape["generator"] else {}
    prompt = gen.get("prompts")
    cond = sorted(set([f for f in artist if f in pos] + ([prompt["frame"]] if prompt and prompt["frame"] in pos else [])))
    if not cond:
        raise ValueError("nothing to track from: the object has no artist keys or prompt in this frame range")
    tracker = Sam2Video(os.path.join(models_root(), model, "video"), device=device, num_total_frames=len(frames))
    results, cache = {}, {}

    def enc(f):
        if f not in cache:
            cache.clear()                                   # keep at most one encoding in memory
            cache[f] = tracker.encode(colour.to_model_input(get_rgb(f)))
        return cache[f]

    for f in cond:                                           # conditioning frames first, in time order
        if f in artist:
            a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in artist[f]]
            tracker.add_mask(pos[f], enc(f), rasterize_spline(a, height, width))
        else:
            tracker.add_points(pos[f], enc(f), [tuple(p) for p in prompt["points"]], prompt["labels"])
    first = cond[0]
    todo = [f for f in frames if f >= first] + [f for f in reversed(frames) if f < first]
    prev_anchor = None
    for i, f in enumerate(todo):
        if job:
            job.check(); job.report(i / float(len(todo)), "frame %d (%d/%d)" % (f, i + 1, len(todo)))
        if f == first:
            prev_anchor = None                               # reverse pass restarts its correspondence chain
        if pos[f] in tracker.cond:
            out = tracker._result(tracker.cond[pos[f]])
        else:
            out = tracker.track(pos[f], enc(f), reverse=f < first)
        if f in artist:
            prev_anchor = np.array(artist[f][0][:2]); continue
        pts = mask_to_points(out["logits"], count=anchors, start_hint=prev_anchor) if out["object_score"] > 0 else []
        results[f] = pts or None
        if pts:
            prev_anchor = np.array(pts[0][:2])
    gen_out = dict(gen, retrack={"model": model, "colour": colour.TRANSFORM_ID, "conditioning_frames": cond,
                                 "artist_frames": sorted(artist)})
    return {"keys": results, "device": tracker.report.active, "device_fallback": tracker.report.fallback,
            "device_reason": tracker.report.reason, "generator": json.dumps(gen_out, sort_keys=True)}


def apply_retrack(bus, store, shape_id, result):
    """One undoable batch: AI keys replaced/added/removed; artist keys untouched (also enforced by the bus)."""
    existing = {k["frame"]: k for k in store.keys(shape_id)}
    ops = []
    for f, pts in sorted(result["keys"].items()):
        old = existing.get(f)
        if old is not None and old["origin"] != m.AI_GENERATED:
            continue
        if pts:
            ops.append({"op": "set_key", "shape_id": shape_id, "frame": f, "points": pts, "generator": result["generator"]})
        elif old is not None:
            ops.append({"op": "delete_key", "shape_id": shape_id, "frame": f})
    if ops:
        bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_AI)
    return len(ops)


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
