"""Prompts -> SAM 2.1 video tracking -> stored, keyed ST-ROTO shapes (T-055, several objects per pass: T-067).

The tracking functions contain no Nuke calls: frames come from an injected `get_rgb(frame)` (headless tests pass a
direct renderer, the GUI passes a main-thread-marshalled one). The apply functions write through the command bus as
actor "ai", so the protection rules (REQ-042) apply; a whole tracking pass is ONE undoable batch.
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


def _ram_budget(n_objects, total=24, horizon=16):
    """Per-object in-RAM frame budget of the tracker state (T-065); results do not depend on it, speed does.
    Each tracking step reads the previous 15 frames (object pointers; memory uses 6), so a budget below 16 reloads
    spilled frames from disk on every step: measured 5,208 reloads in one 48-frame two-object pass with 12
    (research/probes/2026-11-16_multi_object). Hence never below `horizon` (~2 MB per frame per object)."""
    return max(horizon, total // max(1, n_objects))


# ------------------------------------------------------------------------------------------------ track
def track_objects(get_rgb, frames, objects, model="sam2.1-hiera-tiny", device="auto", job=None, anchors=ANCHORS,
                  colour_transform=colour.TRANSFORM_ID):
    """Track several objects forward in ONE pass (T-067): each frame is rendered and encoded once, every object
    keeps its own tracker memory (st_roto_ai.sam2.Sam2MultiVideo).

    frames: ordered list of shot frame numbers. objects: [{"name", "frame", "points": [(x, y), ...], "labels"}];
    each object is tracked from its own prompt frame to the end of `frames`, with exactly the positions and sequence
    length a single-object run over that range uses, so per-object results equal tracking each object alone.
    Returns {"objects": [per-object result, input order], "device", "device_fallback", "device_reason"}; a
    per-object result has "name", "keys", "absent_frames", "reports", "generator".
    """
    from st_roto_ai.sam2 import Sam2MultiVideo     # AI layer is optional: imported only when tracking is requested
    frames = list(frames)
    if not objects:
        raise ValueError("no objects to track")
    index = {f: i for i, f in enumerate(frames)}
    for o in objects:
        if o["frame"] not in index:
            raise ValueError("prompt frame %d of %r is outside the frame range" % (o["frame"], o["name"]))
    multi = Sam2MultiVideo(os.path.join(models_root(), model, "video"), device=device)
    runs = []
    for i, o in enumerate(objects):
        pts = [tuple(p) for p in o["points"]]
        labels = [1] * len(pts) if o.get("labels") is None else list(o["labels"])
        start = index[o["frame"]]
        runs.append({"name": o["name"], "start": start, "pts": pts, "labels": labels,
                     "trk": multi.add_object(i, num_total_frames=len(frames) - start,
                                             max_frames_in_ram=_ram_budget(len(objects))),
                     "keys": {}, "absent": [], "reports": {}, "prev": None})
    first = min(r["start"] for r in runs)
    n = len(frames) - first
    try:
        for idx in range(first, len(frames)):
            frame = frames[idx]
            if job:
                job.check(); job.report((idx - first) / float(n), "frame %d (%d/%d)" % (frame, idx - first + 1, n))
            enc = multi.encode(colour.to_model_input(get_rgb(frame), colour_transform))
            for r in runs:
                p = idx - r["start"]
                if p < 0:
                    continue
                trk = r["trk"]
                out = trk.add_points(p, enc, r["pts"], r["labels"]) if p == 0 else trk.track(p, enc)
                r["reports"][frame] = (out["object_score"], out["iou_pred"])
                pts = mask_to_points(out["logits"], count=anchors, start_hint=r["prev"]) if out["object_score"] > 0 else []
                if pts:
                    r["keys"][frame] = pts
                    r["prev"] = np.array(pts[0][:2])
                else:
                    r["absent"].append(frame)
    finally:
        multi.close()                                   # remove spilled per-frame state (T-065)
    if job:
        job.report(1.0, "tracked %d frames, %d object(s)" % (n, len(runs)))
    results = []
    for r in runs:
        gen = json.dumps({"model": model, "colour": colour.transform_id(colour_transform), "anchors": anchors,
                          "prompts": {"frame": frames[r["start"]], "points": [list(p) for p in r["pts"]],
                                      "labels": r["labels"]}}, sort_keys=True)
        results.append({"name": r["name"], "keys": r["keys"], "absent_frames": r["absent"], "reports": r["reports"],
                        "generator": gen})
    rep = multi.report
    return {"objects": results, "device": rep.active, "device_fallback": rep.fallback, "device_reason": rep.reason}


def track_object(get_rgb, frames, click_frame, click_xy, model="sam2.1-hiera-tiny", device="auto",
                 job=None, anchors=ANCHORS, labels=None, colour_transform=colour.TRANSFORM_ID):
    """Track one object from prompt points on one frame. Returns dict with per-frame points and run metadata.

    frames: ordered list of shot frame numbers (any integers); click_frame must be the first of them (forward only).
    click_xy: one (x, y) or a list of (x, y) in canonical image coordinates (y down); labels: 1 include / 0 exclude
    (default: all include).
    """
    pts = [tuple(click_xy)] if isinstance(click_xy[0], (int, float)) else [tuple(p) for p in click_xy]
    frames = list(frames)
    if not frames or frames[0] != click_frame:
        raise ValueError("Track runs forward only: the prompt frame must be the first frame of the range")
    res = track_objects(get_rgb, frames, [{"name": "", "frame": click_frame, "points": pts, "labels": labels}],
                        model=model, device=device, job=job, anchors=anchors, colour_transform=colour_transform)
    one = res["objects"][0]
    return {"keys": one["keys"], "absent_frames": one["absent_frames"], "reports": one["reports"],
            "device": res["device"], "device_fallback": res["device_fallback"],
            "device_reason": res["device_reason"], "generator": one["generator"]}


# ------------------------------------------------------------------------------------------------ re-track
def retrack_plan(store, shape_id, frames):
    """What a re-track of one shape starts from. Raises ValueError (artist-readable) if there is nothing."""
    shape = store.row("shapes", shape_id)
    if shape is None:
        raise KeyError("no shape %s" % shape_id)
    pos = set(frames)
    artist = {k["frame"]: k["points"] for k in store.keys(shape_id)
              if k["origin"] in (m.ARTIST_CREATED, m.ARTIST_MODIFIED_AI, m.IMPORTED_NATIVE)}
    gen = json.loads(shape["generator"]) if shape["generator"] else {}
    prompt = gen.get("prompts")
    cond = sorted(set([f for f in artist if f in pos] + ([prompt["frame"]] if prompt and prompt["frame"] in pos else [])))
    if not cond:
        raise ValueError("nothing to track %s from: no artist keys or prompt in this frame range" % shape["name"])
    return {"shape_id": shape_id, "anchors": int(shape["point_count"]), "artist": artist, "prompt": prompt,
            "cond": cond, "first": cond[0], "gen": gen}


def retrack_objects(get_rgb, store, shape_ids, frames, width, height, model="sam2.1-hiera-tiny", device="auto",
                    job=None, colour_transform=colour.TRANSFORM_ID):
    """Re-track several shapes in ONE pass (T-067). Each shape uses every ARTIST key as a mask prompt (plus its
    original click prompts, if any) and is tracked forward from its first conditioning frame and in reverse to the
    first frame of `frames` (master prompt section 11: propagate corrections forward and backward). Each frame is
    rendered/encoded once per sweep for all shapes; per-shape results equal re-tracking each shape alone.

    Returns {"shapes": {shape_id: {"keys": {frame: points | None}, "reports", "generator"}}, "device", ...};
    artist keys are not included (they are never overwritten)."""
    from st_roto_ai.sam2 import Sam2MultiVideo
    from st_roto.geometry import Anchor, rasterize_spline
    frames = sorted(frames)
    pos = {f: i for i, f in enumerate(frames)}
    plans = [retrack_plan(store, sid, frames) for sid in shape_ids]
    if not plans:
        raise ValueError("no objects to re-track")
    multi = Sam2MultiVideo(os.path.join(models_root(), model, "video"), device=device)
    for i, p in enumerate(plans):
        p.update(trk=multi.add_object(i, num_total_frames=len(frames), max_frames_in_ram=_ram_budget(len(plans))),
                 results={}, reports={}, prev=None, anchor_at_first=None)
    cache = {}

    def enc(f):
        if f not in cache:
            cache.clear()                                   # keep at most one encoding in memory
            cache[f] = multi.encode(colour.to_model_input(get_rgb(f), colour_transform))
        return cache[f]

    def step(p, f, reverse):
        trk = p["trk"]
        out = trk._result(trk.cond[pos[f]]) if pos[f] in trk.cond else trk.track(pos[f], enc(f), reverse=reverse)
        if f in p["artist"]:
            p["prev"] = np.array(p["artist"][f][0][:2])
        else:
            p["reports"][f] = (out["object_score"], out["iou_pred"])
            pts = mask_to_points(out["logits"], count=p["anchors"], start_hint=p["prev"]) if out["object_score"] > 0 else []
            p["results"][f] = pts or None
            if pts:
                p["prev"] = np.array(pts[0][:2])
        if f == p["first"]:
            p["anchor_at_first"] = p["prev"]

    try:
        for f in sorted(set(c for p in plans for c in p["cond"])):     # conditioning frames first, in time order
            for p in plans:
                if f not in p["cond"]:
                    continue
                if f in p["artist"]:
                    a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:]), corner=False)
                         for q in p["artist"][f]]
                    p["trk"].add_mask(pos[f], enc(f), rasterize_spline(a, height, width))
                else:
                    pr = p["prompt"]
                    p["trk"].add_points(pos[f], enc(f), [tuple(q) for q in pr["points"]], pr["labels"])
        fwd = [f for f in frames if f >= min(p["first"] for p in plans)]
        rev = [f for f in reversed(frames) if f < max(p["first"] for p in plans)]
        total, done = float(len(fwd) + len(rev)), 0
        for reverse, todo in ((False, fwd), (True, rev)):
            for f in todo:
                if job:
                    job.check(); job.report(done / total, "frame %d (%d/%d)" % (f, done + 1, int(total)))
                done += 1
                for p in plans:
                    if (f < p["first"]) != reverse:
                        continue
                    if reverse and pos[f] == pos[p["first"]] - 1:
                        # the reverse pass continues the point correspondence from the first conditioning frame,
                        # not from the last frame of the forward pass
                        p["prev"] = p["anchor_at_first"]
                    step(p, f, reverse)
    finally:
        multi.close()                                       # remove spilled per-frame state (T-065)
    shapes = {}
    for p in plans:
        gen_out = dict(p["gen"], retrack={"model": model, "colour": colour.transform_id(colour_transform),
                                          "conditioning_frames": p["cond"], "artist_frames": sorted(p["artist"])})
        shapes[p["shape_id"]] = {"keys": p["results"], "reports": p["reports"],
                                 "generator": json.dumps(gen_out, sort_keys=True)}
    rep = multi.report
    return {"shapes": shapes, "device": rep.active, "device_fallback": rep.fallback, "device_reason": rep.reason}


def retrack_object(get_rgb, store, shape_id, frames, width, height, model="sam2.1-hiera-tiny", device="auto",
                   job=None, colour_transform=colour.TRANSFORM_ID):
    """Re-track one stored shape (see retrack_objects). Returns "keys" {frame: points | None}, "reports",
    "generator" and the device fields."""
    res = retrack_objects(get_rgb, store, [shape_id], frames, width, height, model=model, device=device, job=job,
                          colour_transform=colour_transform)
    one = res["shapes"][shape_id]
    return dict(one, device=res["device"], device_fallback=res["device_fallback"], device_reason=res["device_reason"])


# ------------------------------------------------------------------------------------------------ apply
def _report_ops(shape_id, reports, skip=()):
    return [{"op": "set_report", "shape_id": shape_id, "frame": f, "object_score": s, "iou_pred": q}
            for f, (s, q) in sorted(reports.items()) if f not in skip]


def retrack_ops(store, shape_id, result):
    """-> (number of AI key changes, ops). AI keys replaced/added/removed and AI diagnostics updated; artist keys
    untouched (also enforced by the bus) and their frames carry no AI report (the artist decided them)."""
    existing = {k["frame"]: k for k in store.keys(shape_id)}
    artist = {f for f, k in existing.items() if k["origin"] != m.AI_GENERATED}
    ops = []
    for f, pts in sorted(result["keys"].items()):
        old = existing.get(f)
        if f in artist:
            continue
        if pts:
            ops.append({"op": "set_key", "shape_id": shape_id, "frame": f, "points": pts, "generator": result["generator"]})
        elif old is not None:
            ops.append({"op": "delete_key", "shape_id": shape_id, "frame": f})
    n_keys = len(ops)
    ops += _report_ops(shape_id, result.get("reports", {}), skip=artist)
    ops += [{"op": "set_report", "shape_id": shape_id, "frame": f, "object_score": None, "iou_pred": None}
            for f in sorted(artist) if store.conn.execute("SELECT 1 FROM key_reports WHERE shape_id=? AND frame=?",
                                                           (shape_id, f)).fetchone()]
    return n_keys, ops


def apply_retrack(bus, store, shape_id, result):
    """One undoable batch for one re-tracked shape. Returns the number of AI key changes."""
    n_keys, ops = retrack_ops(store, shape_id, result)
    if ops:
        bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_AI)
    return n_keys


def apply_retracks(bus, store, shapes):
    """Several re-tracked shapes ({shape_id: result}) as ONE undoable batch. Returns {shape_id: AI key changes}."""
    counts, ops = {}, []
    for sid, result in shapes.items():
        counts[sid], o = retrack_ops(store, sid, result)
        ops += o
    if ops:
        bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_AI)
    return counts


def result_ops(shot_id, object_name, result, anchors=ANCHORS):
    """-> (object_id, shape_id, ops) creating an AI object + shape with its keys and per-frame diagnostics."""
    oid, sid = m.new_id(), m.new_id()
    ops = [{"op": "create_object", "row": {"id": oid, "shot_id": shot_id, "name": object_name}},
           {"op": "create_shape", "row": {"id": sid, "object_id": oid, "name": object_name, "point_count": anchors,
                                          "generator": result["generator"]}}]
    ops += [{"op": "set_key", "shape_id": sid, "frame": f, "points": result["keys"][f], "generator": result["generator"]}
            for f in sorted(result["keys"])]
    ops += _report_ops(sid, result.get("reports", {}))
    return oid, sid, ops


def apply_result(bus, shot_id, object_name, result, anchors=ANCHORS):
    """Create an AI object + shape with its keys and per-frame diagnostics as ONE undoable step.
    Returns (object_id, shape_id)."""
    oid, sid, ops = result_ops(shot_id, object_name, result, anchors)
    bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_AI)
    return oid, sid


def apply_results(bus, shot_id, results, anchors=ANCHORS):
    """Several tracked objects (track_objects()["objects"]) as ONE undoable step. Returns [(object_id, shape_id)]."""
    ids, ops = [], []
    for r in results:
        oid, sid, o = result_ops(shot_id, r["name"], r, anchors)
        ids.append((oid, sid)); ops += o
    bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_AI)
    return ids
