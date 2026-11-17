"""Traditional-roto assists from render passes (T-121; follow-up of T-110). Not AI: both work with AI disabled.

* Shapes from Cryptomatte: the named Cryptomatte objects' coverage (> 0.5) on every frame of the shot becomes a new
  ST-ROTO object with native animated shapes (main + part shapes, st_roto.pieces - the tracker's own shape builder).
  Measured on the synthetic CG shot: IoU 0.9975 (auto point count) / 0.9994 (24 points) vs truth.
* Propagate along vectors: the named object's key on the CURRENT frame is carried forward or backward along the
  plate's motion vectors (st_roto.channels.warp_points_robust: the object's dominant affine motion, robust to an
  occluder in front), frame by frame, until the shot ends or a frame with the artist's own key or a locked frame
  (that key is the next guide). AI / earlier propagated keys on the way are replaced.
Both write as ACTOR_IMPORT (provenance 'imported_native': data-derived, neither AI nor hand-drawn) with the source in
the shape / key generator, as ONE undoable batch.
"""
from __future__ import annotations

import json

import numpy as np

from st_roto import model as m


def _n():
    from . import node as n
    return n


def on_shapes_from_crypto(group, background: bool = True, names=None):
    """Object 'object name' <- Cryptomatte coverage of `names` (default: the 'source' knob, comma separated) in the
    node's Cryptomatte layer, every frame."""
    n = _n()
    from st_roto import channels as chn, pieces
    from . import pixels
    try:
        store, bus, src, project, shot = n._shot_for(group)
        obj = n._object_name(group)
        if shot is not None and any(o["name"] == obj for o in store.objects(shot["id"])):
            raise ValueError("an object named %r already exists: rename 'object name' or delete it first" % obj)
        names = names or [x.strip() for x in group["stroto_prompt_source"].value().split(",") if x.strip()]
        if not names:
            raise ValueError("set 'source' to the Cryptomatte name(s), comma separated")
        layer, manifest = n._crypto_layer(group)
        unknown = [x for x in names if manifest and x not in manifest]
        if unknown:
            raise ValueError("not in the %s manifest: %s" % (layer, ", ".join(unknown)))
        frames = list(range(int(src.firstFrame()), int(src.lastFrame()) + 1))
        ctx = {"src": src, "width": int(src.width()), "height": int(src.height()), "first": frames[0],
               "last": frames[-1], "write": n._inner(group, "write", "STROTO_pixels"),
               "channel_path": pixels.temp_pixel_path(group.name() + "_ch")[:-4] + ".exr"}
        view = n.prompt_view(group)
        anchors = n._anchors(group)
    except (ValueError, n.NodeBudgetError) as e:
        n._status(group, "error: Cryptomatte shapes: %s" % e)
        return None

    def fetch(f):
        r = nuke_call(n._render_ch, (ctx, f, view), background)
        if isinstance(r, pixels.FrameUnavailable):
            return None
        if isinstance(r, Exception):
            raise r
        return r

    def work(job):
        seq = pieces.Sequencer(count=anchors, parts=True)
        last, empty = None, []
        for i, f in enumerate(frames):
            job.check()
            job.report(i / float(len(frames)), "frame %d" % f)
            ch = fetch(f)
            if ch is None:
                empty.append(f); continue
            cov = chn.crypto_mask(ch, layer, names)
            present = bool((cov > 0.5).any())
            if seq.add(f, (cov - 0.5) * 8.0, ref=last, present=present):
                last = f
            else:
                empty.append(f)
        return {"seq": seq.result(frames), "count": seq.count, "empty": empty}

    def apply(job):
        res = job.result
        if not res["seq"]["main"]:
            raise ValueError("%s covers no pixel on any frame" % ", ".join(names))
        store2, bus2 = n._open_project(group, project)
        shot_id = n._ensure_shot(store2, bus2, ctx)
        from .track import result_ops
        gen = json.dumps({"source": "cryptomatte", "layer": layer, "names": names}, sort_keys=True)
        result = {"keys": res["seq"]["main"], "parts": res["seq"]["parts"], "anchors": res["count"],
                  "generator": gen, "reports": {}}
        if view:
            result.update(view=view, pair=obj)
        oid, sid, ops = result_ops(shot_id, obj, result)
        bus2.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_IMPORT)
        n._set_crypto_map(group, obj, layer, names)
        n._sync(group, store2, shot_id, n._inner(group, "roto", "STROTO_shapes")["curves"], ctx["height"])
        msg = ("shapes from Cryptomatte %s %s -> object %s: %d keys (%s points)%s; one undo step; provenance "
               "'imported' (not AI)" % (layer, ", ".join(names), obj, len(res["seq"]["main"]), res["count"],
                                        (", %d part shape(s)" % len(res["seq"]["parts"])) if res["seq"]["parts"] else ""))
        if res["empty"]:
            msg += "; no coverage on frames %s" % n._ranges(res["empty"])
        job.applied = msg
        group["stroto_status"].setValue(msg)

    return n._run(group, "cryptomatte shapes", work, apply, background)


def nuke_call(fn, args, background):
    import nuke
    return nuke.executeInMainThreadWithResult(fn, args) if background else fn(*args)


def on_propagate(group, direction: str = None, background: bool = True):
    """Carry the named object's key(s) on the CURRENT frame along the motion vectors ('forward' uses the forward
    layer, 'backward' the backward layer; 'both' does both)."""
    n = _n()
    from st_roto import channels as chn
    from st_roto.pieces import is_collapsed
    from st_roto.stereo import mask_from_keys
    from . import pixels
    import nuke
    try:
        store, bus, src, project, shot = n._shot_for(group)
        if shot is None:
            raise ValueError("draw the object first (and press 'Save Roto edits to project')")
        roto = n._inner(group, "roto", "STROTO_shapes")
        n.import_edits(store, bus, shot["id"], roto["curves"], int(src.height()), int(nuke.frame()))
        name = n._object_name(group)
        objs = [o for o in store.objects(shot["id"]) if o["name"] == name]
        if not objs:
            raise ValueError("no object named %r" % name)
        o = objs[0]
        if o["locked"]:
            raise ValueError("%r is locked" % name)
        f0 = int(nuke.frame())
        shapes = [s for s in store.shapes(o["id"]) if not s["locked"]]
        start = {s["id"]: store.key(s["id"], f0) for s in shapes}
        start = {sid: k for sid, k in start.items() if k and k["points"] and not is_collapsed(k["points"])}
        if not start:
            raise ValueError("%r has no key on frame %d: go to a frame where you drew it" % (name, f0))
        direction = direction or group["stroto_prop_dir"].value()
        fwd = group["stroto_ch_motion"].value().strip()
        bwd = group["stroto_ch_motion_back"].value().strip()
        if direction in ("forward", "both") and not fwd:
            raise ValueError("set 'motion vectors' (the forward layer, e.g. forward)")
        if direction in ("backward", "both") and not bwd:
            raise ValueError("set 'backward' (the backward vector layer, e.g. backward)")
        conv = group["stroto_ch_motion_conv"].value()
        first, last = int(src.firstFrame()), int(src.lastFrame())
        height, width = int(src.height()), int(src.width())
        locked = set()
        for s in shapes:
            g = json.loads(s["generator"] or "{}") if s.get("generator") else {}
            locked |= set(int(x) for x in g.get("locked_frames", []))
        guard = {}                                    # frame -> True if a hand key / lock stops propagation there
        for s in shapes:
            for k in store.keys(s["id"]):
                if k["origin"] in (m.ARTIST_CREATED, m.ARTIST_MODIFIED_AI) and k["frame"] != f0:
                    guard[k["frame"]] = True
        for f in locked:
            guard[f] = True
        ctx = {"write": n._inner(group, "write", "STROTO_pixels"),
               "channel_path": pixels.temp_pixel_path(group.name() + "_ch")[:-4] + ".exr"}
        view = o.get("view") or n.prompt_view(group)
    except (ValueError, n.NodeBudgetError) as e:
        n._status(group, "error: propagate: %s" % e)
        return None

    def fetch(f):
        r = nuke_call(n._render_ch, (ctx, f, view), background)
        if isinstance(r, pixels.FrameUnavailable):
            return None
        if isinstance(r, Exception):
            raise r
        return r

    def measure(layer, step, frames_):
        """Vector convention of `layer` from a few frame pairs (frame f vs f + step)."""
        errs = []
        for f in frames_[:: max(1, len(frames_) // 4)][:4]:
            a, b = fetch(f), fetch(f + step)
            if a is None or b is None:
                continue
            try:
                errs.append(chn.vector_errors(np.stack([a["R"], a["G"], a["B"]], -1),
                                              np.stack([b["R"], b["G"], b["B"]], -1),
                                              chn.resolve(a, layer + ".u"), chn.resolve(a, layer + ".v")))
            except ValueError:
                continue
        if not errs:
            raise ValueError("could not measure the %s vectors' convention: choose it in 'vector convention'" % layer)
        return chn.choose_convention(errs)

    def work(job):
        out, info = {}, {}
        runs = []
        if direction in ("forward", "both"):
            runs.append(("forward", fwd, 1, list(range(f0, last))))
        if direction in ("backward", "both"):
            runs.append(("backward", bwd, -1, list(range(f0, first, -1))))
        for label, layer, step, frs in runs:
            c = conv
            if conv == n.AUTO_CONVENTION:
                c = measure(layer, step, frs)["convention"]
            info[label] = {"convention": c, "frames": 0, "stopped_at": None}
            cur = {sid: k["points"] for sid, k in start.items()}
            f = f0
            while 0 <= (f + step - first) <= (last - first):
                job.check()
                nxt = f + step
                if guard.get(nxt):
                    info[label]["stopped_at"] = nxt
                    break
                ch = fetch(f)
                if ch is None:
                    info[label]["stopped_at"] = f
                    break
                u, v = chn.resolve(ch, layer + ".u"), chn.resolve(ch, layer + ".v")
                mask = mask_from_keys(list(cur.values()), height, width)
                cur = {sid: chn.warp_points_robust(p, u, v, c, mask) for sid, p in cur.items()}
                for sid, p in cur.items():
                    out.setdefault(sid, {})[nxt] = p
                info[label]["frames"] += 1
                f = nxt
                job.report(min(0.99, info[label]["frames"] / float(max(1, len(frs)))), "%s frame %d" % (label, f))
        return {"keys": out, "info": info}

    def apply(job):
        res = job.result
        gen = json.dumps({"source": "motion vectors", "from_frame": f0,
                          "conventions": {k: v["convention"] for k, v in res["info"].items()}}, sort_keys=True)
        ops = [{"op": "set_key", "shape_id": sid, "frame": f, "points": p, "generator": gen}
               for sid, per in res["keys"].items() for f, p in sorted(per.items())]
        if not ops:
            raise ValueError("nothing propagated (the next frame already has your own key or is locked)")
        bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_IMPORT)
        n._sync(group, store, shot["id"], roto["curves"], height)
        parts = []
        for label, i in res["info"].items():
            parts.append("%s %d frame(s) (vectors %s)%s" % (label, i["frames"], i["convention"],
                                                            (", stopped before frame %d (your key / locked)"
                                                             % i["stopped_at"]) if i["stopped_at"] is not None else ""))
        msg = "propagated %s from frame %d: %s; one undo step; provenance 'imported' (not AI)%s" % (
            name, f0, "; ".join(parts), n._review_text(store, o["id"]))
        job.applied = msg
        group["stroto_status"].setValue(msg)

    return n._run(group, "propagate", work, apply, background)
