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
from st_roto import pieces, views
from st_roto.geometry import mask_to_points  # noqa: F401  (kept for callers)
from . import colour
from .pixels import FrameUnavailable

ANCHORS = 16


def models_root() -> str:
    """The PLUGIN location's onnx folder (dev layout: <repo>/models/onnx). Use model_dir(name) to load a model."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "models", "onnx")


def model_dir(name: str) -> str:
    """Folder of model `name` in the storage location that is used (user, studio, plugin; T-101)."""
    from st_roto_ai.registry import model_dir as _md          # no ONNX Runtime import (registry is plain Python)
    return _md(name)


def _ram_budget(n_objects, total=24, horizon=16):
    """Per-object in-RAM frame budget of the tracker state (T-065); results do not depend on it, speed does.
    Each tracking step reads the previous 15 frames (object pointers; memory uses 6), so a budget below 16 reloads
    spilled frames from disk on every step: measured 5,208 reloads in one 48-frame two-object pass with 12
    (research/probes/2026-11-16_multi_object). Hence never below `horizon` (~2 MB per frame per object)."""
    return max(horizon, total // max(1, n_objects))


# ------------------------------------------------------------------------------------------------ track
def track_objects(get_rgb, frames, objects, model="sam2.1-hiera-tiny", device="auto", job=None, anchors=ANCHORS,
                  colour_transform=colour.TRANSFORM_ID, parts=True, checkpoint_dir=None, checkpoint_every=10,
                  resume=False):
    """Track several objects forward in ONE pass (T-067): each frame is rendered and encoded once, every object
    keeps its own tracker memory (st_roto_ai.sam2.Sam2MultiVideo).

    frames: ordered list of shot frame numbers. objects: [{"name", "frame", "points": [(x, y), ...], "labels"}];
    each object is tracked from its own prompt frame to the end of `frames`, with exactly the positions and sequence
    length a single-object run over that range uses, so per-object results equal tracking each object alone.
    anchors: point count of the main shape, or "auto" (chosen on the prompt frame, st_roto.pieces.choose_count).
    parts: pieces the object splits into become part shapes (T-049).
    checkpoint_dir: if given, the complete state is saved there every `checkpoint_every` frames and when the job is
    cancelled (T-048); `resume=True` continues from it (frames/objects/model/settings must match: use
    `read_checkpoint`). A finished run removes its checkpoint. Resumed results equal an uninterrupted run.
    Returns {"objects": [per-object result, input order], "device", "device_fallback", "device_reason"}; a
    per-object result has "name", "keys" (main shape), "parts" ([{frame: points}], collapsed where absent),
    "anchors", "absent_frames", "holes", "reports", "generator".
    """
    from st_roto_ai.sam2 import Sam2MultiVideo     # AI layer is optional: imported only when tracking is requested
    from st_roto import jobs
    frames = list(frames)
    if not objects:
        raise ValueError("no objects to track")
    index = {f: i for i, f in enumerate(frames)}
    for o in objects:
        if o["frame"] not in index:
            raise ValueError("prompt frame %d of %r is outside the frame range" % (o["frame"], o["name"]))
    definition = {"frames": frames, "model": model, "colour": colour.transform_id(colour_transform),
                  "anchors": anchors, "parts": bool(parts),
                  "objects": [{"name": o["name"], "frame": o["frame"], "points": [list(p) for p in o["points"]],
                               "labels": None if o.get("labels") is None else list(o["labels"])} for o in objects]}
    saved = None
    if resume:
        saved = read_checkpoint(checkpoint_dir)
        if saved is None:
            raise ValueError("no checkpoint to resume in %s" % checkpoint_dir)
        if saved["definition"] != json.loads(json.dumps(definition)):
            raise ValueError("the checkpoint belongs to a different tracking run (prompts, frames or settings differ)")
    multi = Sam2MultiVideo(os.path.join(model_dir(model), "video"), device=device)
    runs = []
    for i, o in enumerate(objects):
        pts = [tuple(p) for p in o["points"]]
        labels = [1] * len(pts) if o.get("labels") is None else list(o["labels"])
        start = index[o["frame"]]
        runs.append({"name": o["name"], "start": start, "pts": pts, "labels": labels,
                     "trk": multi.add_object(i, num_total_frames=len(frames) - start,
                                             max_frames_in_ram=_ram_budget(len(objects))),
                     "seq": pieces.Sequencer(count=anchors, parts=parts), "absent": [], "reports": {}, "last": None})
    first = min(r["start"] for r in runs)
    begin = first
    missing = []
    if saved:
        begin = saved["next_idx"]
        missing = list(saved.get("missing") or [])
        for r, st in zip(runs, saved["runs"]):
            r["trk"].load_state(os.path.join(checkpoint_dir, "obj%d" % runs.index(r)), st["trk"])
            r["seq"] = pieces.sequencer_from_state(st["seq"])
            r["absent"] = list(st["absent"])
            r["reports"] = {int(f): (s, q) for f, s, q in st["reports"]}
            r["last"] = st["last"]
    n = len(frames) - first

    def save(next_idx):
        _write_checkpoint(checkpoint_dir, definition, next_idx, runs, missing)

    idx = begin
    try:
        for idx in range(begin, len(frames)):
            frame = frames[idx]
            if job:
                job.check(); job.report((idx - first) / float(n), "frame %d (%d/%d)" % (frame, idx - first + 1, n))
            try:
                rgb = get_rgb(frame)
            except FrameUnavailable as e:
                starts = [r["name"] for r in runs if r["start"] == idx]
                if starts:
                    raise ValueError("the prompt frame %d of %s cannot be read (%s): prompt on a frame that exists"
                                     % (frame, ", ".join(starts), e.message))
                missing.append(frame)                       # T-086: no key; memory keeps true time positions
                continue
            enc = multi.encode(colour.to_model_input(rgb, colour_transform))
            for r in runs:
                p = idx - r["start"]
                if p < 0:
                    continue
                trk = r["trk"]
                out = trk.add_points(p, enc, r["pts"], r["labels"]) if p == 0 else trk.track(p, enc)
                r["reports"][frame] = (out["object_score"], out["iou_pred"])
                main = r["seq"].add(frame, out["logits"], ref=r["last"], present=out["object_score"] > 0)
                if main:
                    r["last"] = frame
                else:
                    r["absent"].append(frame)
            if checkpoint_dir and (idx + 1 - first) % checkpoint_every == 0 and idx + 1 < len(frames):
                save(idx + 1)
    except jobs.Cancelled:
        if checkpoint_dir:
            save(idx)                                       # frames before idx are complete for every object
        raise
    finally:
        multi.close()                                   # remove spilled per-frame state (T-065)
    if checkpoint_dir:
        discard_checkpoint(checkpoint_dir)
    if job:
        job.report(1.0, "tracked %d frames, %d object(s)" % (n, len(runs)))
    results = []
    for r in runs:
        seq = r["seq"].result(frames[r["start"]:])
        count = r["seq"].count if r["seq"].count != "auto" else ANCHORS
        gen = json.dumps({"model": model, "colour": colour.transform_id(colour_transform), "anchors": count,
                          "anchors_mode": "auto" if anchors == "auto" else "fixed",
                          "prompts": {"frame": frames[r["start"]], "points": [list(p) for p in r["pts"]],
                                      "labels": r["labels"]}}, sort_keys=True)
        results.append({"name": r["name"], "keys": seq["main"], "parts": seq["parts"], "anchors": count,
                        "absent_frames": r["absent"], "holes": seq["holes"], "reports": r["reports"],
                        "generator": gen})
    rep = multi.report
    return {"objects": results, "device": rep.active, "device_fallback": rep.fallback, "device_reason": rep.reason,
            "missing_frames": sorted(missing)}


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
    return dict(one, device=res["device"], device_fallback=res["device_fallback"], device_reason=res["device_reason"])


# ------------------------------------------------------------------------------------------------ re-track
def retrack_plan(store, shape_id, frames, fix=None, anchors=None):
    """What a re-track of one object (given by its MAIN shape) starts from. Raises ValueError (artist-readable) if
    there is nothing. The guide mask on an artist frame is the main shape's artist key united with the object's
    part shapes at that frame (non-collapsed).
    Fix prompts (T-081, "Re-prompt here"): {"frame", "points", "labels"} clicks/box on a frame the AI got wrong;
    kept in the shape generator ("fixes", one per frame, a new one replaces the old) and used as conditioning frames
    by every later re-track. Priority on one frame: artist key > fix prompt > original prompt.
    Guide frames (T-097): keys on frames the artist LOCKED (shape generator "locked_frames") and `anchors`
    ({frame: points}, e.g. the keys just outside a range-limited re-track) condition the tracker exactly like artist
    keys and are never in the result, so the AI cannot change them; they are listed apart ("guide_frames") so
    provenance and reports still distinguish them from artist keys."""
    shape = store.row("shapes", shape_id)
    if shape is None:
        raise KeyError("no shape %s" % shape_id)
    pos = set(frames)
    keys = {k["frame"]: k for k in store.keys(shape_id)}
    artist = {f: k["points"] for f, k in keys.items()
              if k["origin"] in (m.ARTIST_CREATED, m.ARTIST_MODIFIED_AI, m.IMPORTED_NATIVE)}
    gen = json.loads(shape["generator"]) if shape["generator"] else {}
    guides = {}
    for f in gen.get("locked_frames", []):
        if f in keys and f not in artist and keys[f]["points"] and not pieces.is_collapsed(keys[f]["points"]):
            guides[int(f)] = keys[f]["points"]
    for f, pts in (anchors or {}).items():
        if f not in artist and pts:
            guides.setdefault(int(f), pts)
    merged = dict(guides)
    merged.update(artist)                                     # artist keys win on a shared frame
    artist = merged
    prompt = gen.get("prompts")
    fixes = {int(x["frame"]): x for x in gen.get("fixes", [])}
    if fix is not None:
        fixes[int(fix["frame"])] = {"frame": int(fix["frame"]), "points": [list(q) for q in fix["points"]],
                                    "labels": [int(v) for v in fix["labels"]]}
    cond = sorted(set([f for f in artist if f in pos] + [f for f in fixes if f in pos]
                      + ([prompt["frame"]] if prompt and prompt["frame"] in pos else [])))
    if not cond:
        raise ValueError("nothing to track %s from: no artist keys or prompt in this frame range" % shape["name"])
    part_keys = {}
    for s in views.part_shapes(store, shape_id):
        for k in store.keys(s["id"]):
            if k["frame"] in artist and not pieces.is_collapsed(k["points"]):
                part_keys.setdefault(k["frame"], []).append(k["points"])
    return {"shape_id": shape_id, "object_id": shape["object_id"], "anchors": int(shape["point_count"]),
            "artist": artist, "guide_frames": sorted(f for f in guides if f in artist and f not in
                                                     {k for k, v in keys.items() if v["origin"] != m.AI_GENERATED}),
            "part_keys": part_keys, "prompt": prompt, "fixes": fixes, "cond": cond, "first": cond[0],
            "gen": gen}


def retrack_objects(get_rgb, store, shape_ids, frames, width, height, model="sam2.1-hiera-tiny", device="auto",
                    job=None, colour_transform=colour.TRANSFORM_ID, parts=True, fixes=None, anchors=None):
    """Re-track several objects (given by their MAIN shape ids) in ONE pass (T-067). Each uses every ARTIST key of
    its main shape (united with its parts on that frame) as a mask prompt, plus its original click prompts, and is
    tracked forward from its first conditioning frame and in reverse to the first frame of `frames` (master prompt
    section 11). Each frame is rendered/encoded once per sweep for all objects; per-object results equal
    re-tracking each object alone. fixes: {main shape id: new fix prompt} (see retrack_plan). anchors: {main shape
    id: {frame: points}} guide keys that are not changed (range-limited re-track, T-097).

    Returns {"shapes": {main shape id: {"keys": {frame: points | None}, "parts": [{frame: points}], "reports",
    "generator"}}, "device", ...}; artist keys are not included (they are never overwritten)."""
    from st_roto_ai.sam2 import Sam2MultiVideo
    from st_roto.geometry import Anchor, rasterize_spline
    frames = sorted(frames)
    pos = {f: i for i, f in enumerate(frames)}
    plans = [retrack_plan(store, sid, frames, (fixes or {}).get(sid), (anchors or {}).get(sid)) for sid in shape_ids]
    if not plans:
        raise ValueError("no objects to re-track")
    multi = Sam2MultiVideo(os.path.join(model_dir(model), "video"), device=device)
    for i, p in enumerate(plans):
        seq = pieces.Sequencer(count=p["anchors"], parts=parts)
        for f, pts in p["artist"].items():
            seq.add_known(f, pts)
        p.update(trk=multi.add_object(i, num_total_frames=len(frames), max_frames_in_ram=_ram_budget(len(plans))),
                 seq=seq, reports={}, decided=set(), last=None)
    cache = {}

    def enc(f):
        if f not in cache:
            cache.clear()                                   # keep at most one encoding in memory
            cache[f] = multi.encode(colour.to_model_input(get_rgb(f), colour_transform))
        return cache[f]

    def raster(points):
        a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:]), corner=False) for q in points]
        return rasterize_spline(a, height, width)

    def step(p, f, reverse):
        trk = p["trk"]
        out = trk._result(trk.cond[pos[f]]) if pos[f] in trk.cond else trk.track(pos[f], enc(f), reverse=reverse)
        if f not in p["artist"]:
            p["reports"][f] = (out["object_score"], out["iou_pred"])
            p["decided"].add(f)
            if not p["seq"].add(f, out["logits"], ref=p["last"], present=out["object_score"] > 0):
                return                                      # no object: keep the chain at the last real frame
        p["last"] = f

    missing = set()
    try:
        for f in sorted(set(c for p in plans for c in p["cond"])):     # conditioning frames first, in time order
            try:
                enc(f)
            except FrameUnavailable as e:
                raise ValueError("frame %d guides the re-track (prompt, fix or your key) but cannot be read (%s)"
                                 % (f, e.message))
            for p in plans:
                if f not in p["cond"]:
                    continue
                if f in p["artist"]:
                    mask = raster(p["artist"][f])
                    for q in p["part_keys"].get(f, []):
                        mask |= raster(q)
                    p["trk"].add_mask(pos[f], enc(f), mask)
                elif f in p["fixes"]:
                    fx = p["fixes"][f]
                    p["trk"].add_points(pos[f], enc(f), [tuple(q) for q in fx["points"]], fx["labels"])
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
                try:
                    for p in plans:
                        if (f < p["first"]) != reverse:
                            continue
                        if reverse and pos[f] == pos[p["first"]] - 1:
                            # the reverse pass continues the point correspondence from the first conditioning
                            # frame, not from the last frame of the forward pass
                            p["last"] = p["first"]
                        step(p, f, reverse)         # enc(f) runs before any tracker state changes
                except FrameUnavailable:
                    missing.add(f)                  # T-086: skipped, no key; memory keeps true time positions
    finally:
        multi.close()                                       # remove spilled per-frame state (T-065)
    shapes = {}
    for p in plans:
        res = p["seq"].result(sorted(p["decided"]))
        keys = {f: res["main"].get(f) for f in sorted(p["decided"])}
        gen_out = dict(p["gen"], retrack={"model": model, "colour": colour.transform_id(colour_transform),
                                          "conditioning_frames": p["cond"],
                                          "artist_frames": sorted(set(p["artist"]) - set(p["guide_frames"])),
                                          "guide_frames": p["guide_frames"],
                                          "fix_frames": sorted(f for f in p["fixes"] if f not in p["artist"])})
        if p["fixes"]:
            gen_out["fixes"] = [p["fixes"][f] for f in sorted(p["fixes"])]
        shapes[p["shape_id"]] = {"keys": keys, "parts": res["parts"], "holes": res["holes"], "reports": p["reports"],
                                 "generator": json.dumps(gen_out, sort_keys=True)}
    rep = multi.report
    return {"shapes": shapes, "device": rep.active, "device_fallback": rep.fallback, "device_reason": rep.reason,
            "missing_frames": sorted(missing)}


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
    """-> (number of AI key changes, ops). Main shape: AI keys replaced/added/removed and AI diagnostics updated;
    parts: each result part goes to the existing part shape of the object nearest to it (same point count), or to a
    new part shape; existing parts without a match get collapsed AI keys on the decided frames. Artist keys are
    never touched (also enforced by the bus) and their frames carry no AI report."""
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
    main = store.row("shapes", shape_id)
    old_gen = json.loads(main["generator"]) if main["generator"] else {}
    new_fixes = json.loads(result["generator"]).get("fixes") if result.get("generator") else None
    if new_fixes != old_gen.get("fixes"):                   # T-081: the shape keeps its fix prompts (undoable)
        g = dict(old_gen)
        g.pop("fixes", None)
        if new_fixes:
            g["fixes"] = new_fixes
        ops.append({"op": "update_shape", "id": shape_id, "fields": {"generator": json.dumps(g, sort_keys=True)}})
    old_parts = views.part_shapes(store, shape_id)          # only AI part shapes; other hand-drawn shapes untouched
    part_gen = _part_generator(result["generator"], shape_id)
    part_keys = {s["id"]: {k["frame"]: k for k in store.keys(s["id"])} for s in old_parts}
    free = [s for s in old_parts if not s["locked"]]
    for i, part in enumerate(result.get("parts", [])):
        real = {f: q for f, q in part.items() if not pieces.is_collapsed(q)}
        count = len(next(iter(part.values())))
        c = np.mean([pieces.centroid(q) for q in real.values()], 0) if real else None
        best, best_d = None, None
        for s in free:
            if int(s["point_count"]) != count or c is None:
                continue
            rk = [pieces.centroid(k["points"]) for k in part_keys[s["id"]].values() if not pieces.is_collapsed(k["points"])]
            if not rk:
                continue
            d = float(np.min(np.linalg.norm(np.asarray(rk) - c, axis=1)))
            if best_d is None or d < best_d:
                best, best_d = s, d
        if best is not None:
            free.remove(best)
            sid = best["id"]
        else:
            sid = m.new_id()
            ops.append({"op": "create_shape", "row": {"id": sid, "object_id": main["object_id"],
                                                      "name": "%s_part%d" % (main["name"], len(old_parts) + i + 2),
                                                      "point_count": count, "generator": part_gen}})
            part_keys[sid] = {}
        skip = {f for f, k in part_keys[sid].items() if k["origin"] != m.AI_GENERATED}
        ops += _part_key_ops(sid, part, part_gen, skip)
    for s in free:                                          # parts the AI no longer sees: collapse their AI keys
        ks = part_keys[s["id"]]
        at = next((pieces.centroid(k["points"]) for k in ks.values()), np.zeros(2))
        for f in sorted(result["keys"]):
            k = ks.get(f)
            if k is not None and k["origin"] != m.AI_GENERATED:
                continue
            if k is None or not pieces.is_collapsed(k["points"]):
                ops.append({"op": "set_key", "shape_id": s["id"], "frame": f,
                            "points": pieces.collapsed(int(s["point_count"]), at),
                            "generator": _collapsed_generator(part_gen)})
    n_keys = sum(1 for x in ops if x["op"] in ("set_key", "delete_key"))
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
    """-> (object_id, shape_id, ops) creating an AI object + main shape (+ part shapes) with keys and per-frame
    diagnostics (diagnostics belong to the main shape)."""
    oid, sid = m.new_id(), m.new_id()
    count = result.get("anchors") or anchors
    row = {"id": oid, "shot_id": shot_id, "name": object_name}
    for f in ("view", "pair"):                               # T-109: the view tracked and the stereo pair key
        if result.get(f):
            row[f] = result[f]
    ops = [{"op": "create_object", "row": row},
           {"op": "create_shape", "row": {"id": sid, "object_id": oid, "name": object_name, "point_count": count,
                                          "generator": result["generator"]}}]
    ops += [{"op": "set_key", "shape_id": sid, "frame": f, "points": result["keys"][f], "generator": result["generator"]}
            for f in sorted(result["keys"])]
    for i, part in enumerate(result.get("parts", [])):
        pid = m.new_id()
        pgen = _part_generator(result["generator"], sid, i + 2)
        ops.append({"op": "create_shape", "row": {"id": pid, "object_id": oid, "name": "%s_part%d" % (object_name, i + 2),
                                                  "point_count": len(next(iter(part.values()))), "generator": pgen}})
        ops += _part_key_ops(pid, part, pgen)
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



def _part_generator(generator, main_id, n=None):
    try:
        g = json.loads(generator) if generator else {}
    except ValueError:
        g = {}
    g["part_of"] = main_id                                   # marks an AI part shape (st_roto.views.part_of)
    if n is not None:
        g["part"] = n
    return json.dumps(g, sort_keys=True)


def _collapsed_generator(generator):
    try:
        g = json.loads(generator) if generator else {}
    except ValueError:
        g = {}
    g["collapsed"] = True                                   # part absent on this frame: zero-area key (T-049)
    return json.dumps(g, sort_keys=True)


def _part_key_ops(shape_id, keys, generator, skip=()):
    ops = []
    for f, pts in sorted(keys.items()):
        if f in skip:
            continue
        gen = _collapsed_generator(generator) if pieces.is_collapsed(pts) else generator
        ops.append({"op": "set_key", "shape_id": shape_id, "frame": f, "points": pts, "generator": gen})
    return ops


def _write_checkpoint(directory, definition, next_idx, runs, missing=()):
    """Incremental, crash-safe: per-object tensors first (immutable files, written once), meta.json LAST via an
    atomic replace, so a checkpoint interrupted half-way leaves the previous one valid."""
    import datetime
    os.makedirs(directory, exist_ok=True)
    states = []
    for i, r in enumerate(runs):
        states.append({"trk": r["trk"].save_state(os.path.join(directory, "obj%d" % i)),
                       "seq": pieces.sequencer_state(r["seq"]), "absent": r["absent"], "last": r["last"],
                       "reports": [[f, s, q] for f, (s, q) in sorted(r["reports"].items())]})
    meta = {"format": "st_roto.track_checkpoint", "version": 1, "definition": definition, "next_idx": next_idx,
            "next_frame": definition["frames"][next_idx] if next_idx < len(definition["frames"]) else None,
            "saved_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "runs": states,
            "missing": sorted(missing)}
    tmp = os.path.join(directory, "meta.json.part")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    os.replace(tmp, os.path.join(directory, "meta.json"))


def read_checkpoint(directory):
    """The checkpoint's meta (with "definition": frames, objects, model, colour id, anchors, parts) or None."""
    p = os.path.join(directory or "", "meta.json")
    if not directory or not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        meta = json.load(fh)
    return meta if meta.get("format") == "st_roto.track_checkpoint" else None


def discard_checkpoint(directory):
    import shutil
    if directory and os.path.isdir(directory):
        shutil.rmtree(directory, ignore_errors=True)