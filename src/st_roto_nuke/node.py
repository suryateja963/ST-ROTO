"""The ST_Roto node (single-node core under the Non-commercial 10-node cap, D-012) — v0.

Structure: Group "ST_Roto" with  Input -> Roto(STROTO_shapes, alpha) -> Output, plus a disabled Write
(STROTO_pixels) that pulls pixels into numpy. 5 nodes per shot including the group.

Artist workflow (knob tab ST-ROTO):
  1. set "object name", drag the "point" handle in the viewer onto the object, press "+ Include" (or "- Exclude")
     - repeat as needed; change "object name" and add points to prompt further objects (T-067);
  2. "Preview" shows the AI shape of the current object on its prompt frame (temporary, not saved);
  3. "Load model" (optional, once per Nuke session) takes the one-time GPU set-up pause now;
  4. "Track" tracks every prompted object forward from its prompt frame, in one pass on a worker thread (each frame
     is rendered and encoded once); the result is stored in the project (AI provenance, ONE undo step) and
     synchronised into the Roto node without touching shapes edited there.
Python viewer clicks are not used: Non-commercial cannot load C++ overlays and Nuke offers no supported Python
mapping from viewer clicks to image coordinates; the XY knob handle is Nuke's native in-viewer point.
"""
from __future__ import annotations

import json
import os
import threading
import traceback

import nuke
import nuke.rotopaint  # noqa: F401

from st_roto import jobs, prompts
from . import colour, pixels, session
from .roto_export import export_preview, import_edits, sync_shot
from .track import apply_results, models_root, track_object, track_objects

MODELS = ["sam2.1-hiera-tiny", "sam2.1-hiera-large"]
DEVICES = ["auto", "cpu"]
POINT_COUNTS = ["auto", "8", "12", "16", "24", "32", "48"]
_JOBS = {}            # group full name -> last Job
_INNER = {}           # group full name -> cached Node references (10-node budget: never re-fetch, R-39)


class NodeBudgetError(RuntimeError):
    """Nuke Non-commercial / Indie returned None because the 10-Python-Node-object limit was reached (ADR-0003)."""


# ------------------------------------------------------------------------------------------------ creation
def create(source=None, project_path: str = ""):
    group = nuke.nodes.Group(name="ST_Roto1")
    if source is not None:
        group.setInput(0, source)
    group.addKnob(nuke.Tab_Knob("stroto_tab", "ST-ROTO"))
    k = nuke.File_Knob("stroto_project", "project file"); group.addKnob(k); k.setValue(project_path)
    group.addKnob(nuke.String_Knob("stroto_object", "object name", "object1"))
    group.addKnob(nuke.Text_Knob("stroto_div1", "prompts"))
    xy = nuke.XY_Knob("stroto_click", "point")
    xy.setTooltip("Drag this handle in the viewer onto the object, then press + Include or - Exclude.")
    group.addKnob(xy)
    _button(group, "stroto_add_inc", "+ Include", "n.on_add_point(nuke.thisNode(), 1)")
    _button(group, "stroto_add_exc", "- Exclude", "n.on_add_point(nuke.thisNode(), 0)", new_line=False)
    cp = _button(group, "stroto_clear", "Clear points", "n.on_clear_points(nuke.thisNode())", new_line=False)
    cp.setTooltip("Removes the points of the object named above.")
    _button(group, "stroto_clear_all", "Clear all", "n.on_clear_points(nuke.thisNode(), every_object=True)",
            new_line=False)
    pts = nuke.String_Knob("stroto_points", "points (json)"); group.addKnob(pts)
    group.addKnob(nuke.Text_Knob("stroto_points_info", "", "no points"))
    group.addKnob(nuke.Int_Knob("stroto_click_frame", "click frame (if no points)"))
    group.addKnob(nuke.Text_Knob("stroto_div2", "AI"))
    group.addKnob(nuke.Enumeration_Knob("stroto_model", "model", MODELS))
    group.addKnob(nuke.Enumeration_Knob("stroto_device", "device", DEVICES))
    pc = nuke.Enumeration_Knob("stroto_anchors", "points", POINT_COUNTS)
    pc.setTooltip("Points per shape. auto: the fewest points that follow the object's outline within ~0.3 px on "
                  "its prompt frame. Pieces the object splits into become extra part shapes.")
    pc.clearFlag(nuke.STARTLINE)
    group.addKnob(pc)
    ck = nuke.Enumeration_Knob("stroto_colour", "AI input colour", colour.CHOICES)
    ck.setTooltip("Colour space of the plate as the AI sees it. auto: follow the script (Nuke default = linear sRGB; OCIO = the working space through the script's OCIO config). Recorded with every AI result.")
    group.addKnob(ck)
    lm = _button(group, "stroto_load", "Load model", "n.on_load_model(nuke.thisNode())")
    lm.setTooltip("Loads the AI model onto the GPU now. Nuke may pause for a few seconds once; Track is smooth afterwards.")
    _button(group, "stroto_preview", "Preview", "n.on_preview(nuke.thisNode())", new_line=False)
    _button(group, "stroto_track", "Track", "n.on_track(nuke.thisNode())", new_line=False)
    _button(group, "stroto_cancel", "Cancel", "n.on_cancel(nuke.thisNode())", new_line=False)
    rs = _button(group, "stroto_resume", "Resume track", "n.on_resume_track(nuke.thisNode())", new_line=False)
    rs.setTooltip("Continues a Track that was cancelled, failed or interrupted by a crash, from its last checkpoint "
                  "(same result as an uninterrupted run).")
    rt = _button(group, "stroto_retrack", "Re-track object", "n.on_retrack(nuke.thisNode())")
    rt.setTooltip("Re-tracks the object named above in both directions, using every frame you corrected or drew as a "
                  "guide. Your keys are never changed; only AI keys are replaced.")
    ra = _button(group, "stroto_retrack_all", "Re-track all", "n.on_retrack(nuke.thisNode(), every_object=True)",
                 new_line=False)
    ra.setTooltip("Re-tracks every unlocked object of this shot in one pass (each frame is analysed once).")
    imp = _button(group, "stroto_import", "Save Roto edits to project", "n.on_import_edits(nuke.thisNode())",
                  new_line=False)
    imp.setTooltip("Records shapes you edited or drew in this node's Roto into the ST-ROTO project (undoable).")
    group.addKnob(nuke.Text_Knob("stroto_div3", "mattes"))
    soft = nuke.Boolean_Knob("stroto_soft", "soft edges"); soft.setValue(True); group.addKnob(soft)
    soft.setTooltip("Refine a narrow band around each shape's edge against the plate (guided filter, no AI model). "
                    "Off: hard mattes identical to the shapes.")
    band = nuke.Int_Knob("stroto_band", "edge band"); band.setValue(3); band.clearFlag(nuke.STARTLINE); group.addKnob(band)
    band.setTooltip("Half-width in pixels of the zone that may become soft.")
    rad = nuke.Int_Knob("stroto_radius", "radius"); rad.setValue(8); rad.clearFlag(nuke.STARTLINE); group.addKnob(rad)
    rad.setTooltip("Guided-filter window radius in pixels.")
    md = nuke.File_Knob("stroto_matte_dir", "matte folder"); group.addKnob(md)
    md.setTooltip("Where the EXR mattes go. Empty: <project>_mattes/<shot>/ next to the project file.")
    rm = _button(group, "stroto_render_mattes", "Render mattes (EXR)", "n.on_render_mattes(nuke.thisNode())")
    rm.setTooltip("Writes one EXR per frame: a layer per object (<object>.A) and the combined matte in alpha.")
    ex = _button(group, "stroto_export_shapes", "Export shapes (JSON + SVG)", "n.on_export_shapes(nuke.thisNode())")
    ex.setTooltip("Writes <project>_export/<shot>/<shot>.json (every object, key and provenance; re-importable) and "
                  "one SVG per keyed frame.")
    im = _button(group, "stroto_import_shapes", "Import shapes (JSON)", "n.on_import_shapes(nuke.thisNode())",
                 new_line=False)
    im.setTooltip("Adds the objects of an ST-ROTO JSON file to this shot (one undo step; marked as imported).")
    bk = _button(group, "stroto_backup", "Back up now", "n.on_backup(nuke.thisNode())")
    bk.setTooltip("Snapshot of the project file into <project>_backups/ (automatic backups also run every 5 minutes "
                  "after changes).")
    pk = _button(group, "stroto_package", "Package project", "n.on_package(nuke.thisNode())", new_line=False)
    pk.setTooltip("Portable zip: project, mattes, exports and a checksummed manifest (no model weights).")
    group.addKnob(nuke.Text_Knob("stroto_status", "status", "idle"))
    with group:
        inp = nuke.nodes.Input(name="Input1")
        roto = nuke.nodes.Roto(name="STROTO_shapes", output="alpha")
        roto.setInput(0, inp)
        out = nuke.nodes.Output(name="Output1")
        out.setInput(0, roto)
        w = nuke.nodes.Write(name="STROTO_pixels")
        w.setInput(0, inp)
        pixels.configure_write(w, pixels.temp_pixel_path(group.name()))
        w["disable"].setValue(True)
    _add_motionblur_links(group)
    _INNER[group.fullName()] = {"write": w, "roto": roto, "src": source}
    return group


MOTIONBLUR_LINKS = (("stroto_mb_mode", "motion blur", "motionblur_mode"),
                    ("stroto_mb_samples", "samples", "global_motionblur"),
                    ("stroto_mb_shutter", "shutter", "global_motionblur_shutter"),
                    ("stroto_mb_offset", "shutter offset", "global_motionblur_shutter_offset_type"))


def _add_motionblur_links(group):
    """Nuke's own Roto motion blur on the ST_Roto node (T-074): the shapes are real animated splines, so Nuke blurs
    them along their tracked motion. Linked knobs of the inner Roto (knob names measured on Nuke 17.1)."""
    group.addKnob(nuke.Text_Knob("stroto_div_mb", "motion blur"))
    for name, label, target in MOTIONBLUR_LINKS:
        k = nuke.Link_Knob(name, label)
        k.setLink("STROTO_shapes." + target)
        if name != "stroto_mb_mode":
            k.clearFlag(nuke.STARTLINE)
        group.addKnob(k)


def create_from_selection():
    """Menu entry: create an ST_Roto node below the selected node; project file defaults to <script>.stroto."""
    try:
        src = nuke.selectedNode()
    except ValueError:
        src = None
    script = nuke.root().name()
    project = "" if script in ("", "Root") else os.path.splitext(script)[0] + ".stroto"
    g = create(src, project)
    if not project:
        g["stroto_status"].setValue("set a project file (save the script first for an automatic one)")
    return g


def _button(group, name, label, code, new_line=True):
    b = nuke.PyScript_Knob(name, label, "import st_roto_nuke.node as n; " + code)
    if not new_line:
        b.clearFlag(nuke.STARTLINE)
    group.addKnob(b)
    return b


# ------------------------------------------------------------------------------------------------ helpers
def _inner(group, key, name):
    cached = _INNER.get(group.fullName(), {}).get(key)
    if cached is not None:
        return cached
    if key == "src":
        n = group.input(0)
        if n is None:
            raise ValueError("connect a source to the ST_Roto input")
    else:
        with group:
            n = nuke.toNode(name)
    if n is None:
        raise NodeBudgetError("Nuke returned no node for %s.%s. In Non-commercial/Indie mode Python can access only "
                              "10 nodes per session; save the script, reopen it and try again." % (group.name(), name))
    _INNER.setdefault(group.fullName(), {})[key] = n
    return n


_REPORTED = set()


def _open_project(group, path):
    """session.project + show, once per project and Nuke session, anything found when opening it (crash,
    recovery, another Nuke using it) in the node status."""
    store, bus = session.project(path)
    key = os.path.normcase(os.path.abspath(path))
    if key not in _REPORTED:
        _REPORTED.add(key)
        note = session.report_text(path)
        if note:
            _status(group, "project: " + note)
            nuke.tprint("ST-ROTO: %s: %s" % (path, note))
    return store, bus


def _status(group, text):
    def _set():
        group["stroto_status"].setValue(text)
    if threading.current_thread() is threading.main_thread():
        _set()
    else:
        nuke.executeInMainThread(_set)


def _height(group):
    return int(group.height())


def _context(group, need_prompts: bool = True):
    """Everything a job needs, gathered on the main thread. Raises ValueError with an artist-readable message.
    need_prompts=False (resuming): prompts come from the checkpoint, the node may have none."""
    src = _inner(group, "src", None)
    write, roto = _inner(group, "write", "STROTO_pixels"), _inner(group, "roto", "STROTO_shapes")
    text = group["stroto_points"].value()
    current = _object_name(group)
    if not need_prompts:
        objects = []
    elif prompts.load(text):
        objects = prompts.objects_for_tracker(text, current)
    else:                                                     # backwards-compatible single click
        cx, cy = group["stroto_click"].value()
        objects = [{"name": current, "frame": int(group["stroto_click_frame"].value()),
                    "points": [(float(cx), _height(group) - float(cy))], "labels": [1]}]
    first, last = int(src.firstFrame()), int(src.lastFrame())
    for o in objects:
        if not first <= o["frame"] <= last:
            raise ValueError("prompt frame %d of %r is outside the source range %d-%d" % (o["frame"], o["name"], first, last))
    mine = [o for o in objects if o["name"] == current] or (objects if len(objects) == 1 else [])
    return {"src": src, "write": write, "roto": roto, "objects": objects, "current": mine[0] if mine else None,
            "first": first, "last": last, "width": int(src.width()), "height": int(src.height()),
            "model": group["stroto_model"].value(), "device": group["stroto_device"].value(),
            "colour": _colour(group), "anchors": _anchors(group),
            "project": group["stroto_project"].value(), "object": current,
            "pixel_path": pixels.temp_pixel_path(group.name())}


def _anchors(group):
    v = group["stroto_anchors"].value() if "stroto_anchors" in group.knobs() else "16"     # old nodes: v0 count
    return "auto" if v == "auto" else int(v)


def _colour(group):
    """The node's AI input colour transform (main thread). Old nodes without the knob use auto."""
    choice = group["stroto_colour"].value() if "stroto_colour" in group.knobs() else colour.AUTO
    try:
        return colour.resolve(choice)
    except Exception as e:
        raise ValueError("AI input colour: %s" % e)


def _object_name(group):
    return group["stroto_object"].value().strip() or "object"


def _renderer(ctx, background):
    def get_rgb(frame):
        if background:
            return nuke.executeInMainThreadWithResult(pixels.render_frame, (ctx["write"], frame, ctx["pixel_path"]))
        return pixels.render_frame(ctx["write"], frame, ctx["pixel_path"])
    return get_rgb


def _run(group, name, work, apply, background, stop_hint=None):
    """Start a job; `apply(job)` runs on the main thread; every failure ends up in the status knob.
    stop_hint(): text appended when the job is cancelled or fails (e.g. how to resume it)."""
    prev = _JOBS.get(group.fullName())
    if prev is not None and prev.status == jobs.RUNNING:
        _status(group, "busy: %s is still running" % prev.name)
        return prev

    def safe_apply(job):
        try:
            apply(job)
        except Exception:
            job.apply_error = traceback.format_exc()
            job.applied = "failed applying result: " + job.apply_error.strip().splitlines()[-1]
            group["stroto_status"].setValue(job.applied)

    def finished(job):
        if job.status == jobs.DONE:
            nuke.executeInMainThread(safe_apply, (job,)) if background else safe_apply(job)
        elif job.status == jobs.FAILED:
            job.applied = "failed: " + job.error.strip().splitlines()[-1] + (stop_hint() if stop_hint else "")
            _status(group, job.applied)
        else:
            job.applied = "cancelled" + (stop_hint() if stop_hint else "")
            _status(group, job.applied)

    job = jobs.Job(work, name=name, on_finish=finished,
                   on_progress=lambda j: _status(group, "%s %d%%: %s" % (name, 100 * j.progress, j.message)))
    job.applied, job.apply_error = None, None
    _JOBS[group.fullName()] = job
    return job.start(background=background)


# ------------------------------------------------------------------------------------------------ buttons
def on_add_point(group, label: int):
    cx, cy = group["stroto_click"].value()
    try:
        text = prompts.add(group["stroto_points"].value(), int(nuke.frame()), float(cx), _height(group) - float(cy),
                           label, obj=_object_name(group))
    except ValueError as e:
        _status(group, "error: %s" % e); return
    group["stroto_points"].setValue(text)
    group["stroto_points_info"].setValue(prompts.summary(text, _object_name(group)))


def on_clear_points(group, every_object: bool = False):
    """Clear the current object's points (or every object's)."""
    name = _object_name(group)
    text = "" if every_object else prompts.clear(group["stroto_points"].value(), name, name)
    if not prompts.load(text):
        text = ""
    group["stroto_points"].setValue(text)
    group["stroto_points_info"].setValue(prompts.summary(text, name))


def on_load_model(group):
    """Create the GPU sessions now, synchronously and visibly (the GIL-bound pause, R-40)."""
    from st_roto_ai.sam2 import preload_video
    model, device = group["stroto_model"].value(), group["stroto_device"].value()
    group["stroto_status"].setValue("loading %s (Nuke may pause briefly)..." % model)
    try:
        r = preload_video(os.path.join(models_root(), model, "video"), device)
    except Exception as e:
        group["stroto_status"].setValue("failed to load model: %s" % e)
        return None
    msg = "model %s loaded on %s in %.1f s" % (model, r["device"], r["seconds"])
    if r["fallback"]:
        msg += " (FALLBACK: %s)" % r["reason"]
    group["stroto_status"].setValue(msg)
    return r


def on_cancel(group):
    job = _JOBS.get(group.fullName())
    if job:
        job.cancel()


def on_preview(group, background: bool = True):
    """Segment the current object on its prompt frame and show it as a temporary shape (not saved, not undoable)."""
    try:
        ctx = _context(group)
        o = ctx["current"]
        if o is None:
            raise ValueError("no points for object %r (points exist for: %s)"
                             % (ctx["object"], ", ".join(g["name"] for g in ctx["objects"])))
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)

    def work(job):
        return track_object(get_rgb, [o["frame"]], o["frame"], o["points"], model=ctx["model"],
                            device=ctx["device"], job=job, labels=o["labels"], colour_transform=ctx["colour"])

    def apply(job):
        export_preview(ctx["roto"]["curves"], job.result["keys"], ctx["height"])
        job.applied = "preview of %s on frame %d (%s)" % (o["name"], o["frame"],
                                                          "object found" if job.result["keys"] else "NO object found")
        group["stroto_status"].setValue(job.applied)

    return _run(group, "preview", work, apply, background)


def on_track(group, background: bool = True, resume: bool = False):
    """Track every prompted object forward from its prompt frame in one pass; store (AI provenance, one undo step)
    and sync into the Roto node. The run is checkpointed (T-048): after Cancel, a failure or a crash,
    `resume=True` ('Resume track') continues it from the checkpoint with identical results."""
    from .track import discard_checkpoint, read_checkpoint
    try:
        ctx = _context(group, need_prompts=not resume)
        if not ctx["project"]:
            raise ValueError("set a project file")
        ck = checkpoint_dir(ctx["project"], ctx["src"].name())
        saved = read_checkpoint(ck) if resume else None
        if resume:
            if saved is None:
                raise ValueError("nothing to resume for %s" % ctx["src"].name())
            d = saved["definition"]
            if d["colour"] != colour.transform_id(ctx["colour"]):
                raise ValueError("'AI input colour' changed since the interrupted run (it used %s); set it back to "
                                 "resume" % d["colour"])
            ctx.update(objects=[dict(o, points=[tuple(p) for p in o["points"]]) for o in d["objects"]],
                       model=d["model"], anchors=d["anchors"], parts=d["parts"])
            frames = list(d["frames"])
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    store, _ = _open_project(group, ctx["project"])
    shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (ctx["src"].name(),)).fetchone()
    existing = {o["name"] for o in store.objects(shot["id"])} if shot else set()
    skipped_note = ""
    if not resume:
        already = [o["name"] for o in ctx["objects"] if o["name"] in existing]
        ctx["objects"] = [o for o in ctx["objects"] if o["name"] not in existing]
        if not ctx["objects"]:
            _status(group, "error: already tracked: %s - use Re-track, or delete the object first (or rename it and "
                           "prompt again)" % ", ".join(already))
            return None
        skipped_note = ("; skipped %s (already tracked: use Re-track)" % ", ".join(already)) if already else ""
        start = min(o["frame"] for o in ctx["objects"])
        frames = list(range(start, ctx["last"] + 1))
        discard_checkpoint(ck)                              # a new run replaces any interrupted one
    start = frames[0]
    get_rgb = _renderer(ctx, background)

    def work(job):
        return track_objects(get_rgb, frames, ctx["objects"], model=ctx["model"], device=ctx["device"], job=job,
                             colour_transform=ctx["colour"], anchors=ctx["anchors"], parts=ctx.get("parts", True),
                             checkpoint_dir=ck, resume=resume)

    def apply(job):
        result = job.result
        store, bus = _open_project(group, ctx["project"])
        shot_id = _ensure_shot(store, bus, ctx)
        export_preview(ctx["roto"]["curves"], {}, ctx["height"])          # remove the temporary preview
        import_edits(store, bus, shot_id, ctx["roto"]["curves"], ctx["height"], start)   # capture artist work first
        ids = apply_results(bus, shot_id, result["objects"])
        rep = sync_shot(store, shot_id, ctx["roto"]["curves"], ctx["height"])
        parts = []
        for r, (oid, _) in zip(result["objects"], ids):
            extra = (", %d extra piece(s)" % len(r["parts"])) if r.get("parts") else ""
            if r.get("holes"):
                extra += ", holes not represented on frames %s" % _ranges(sorted(r["holes"]))
            parts.append("%s%d keys (%d points)%s, %d frames without object" % (
                "" if len(ids) == 1 else r["name"] + ": ", len(r["keys"]), r.get("anchors") or 16, extra,
                len(r["absent_frames"])) + _review_text(store, oid))
        msg = "done%s: %s; device %s%s" % (" (resumed)" if resume else "", " | ".join(parts), result["device"],
                                            skipped_note)
        if result["device_fallback"]:
            msg += " (FALLBACK: %s)" % result["device_reason"]
        if rep["conflicts"]:
            msg += "; NOT updated (edited in Roto): %s" % ", ".join(rep["conflicts"])
        job.sync_report = rep
        job.applied = msg
        group["stroto_status"].setValue(msg)

    def hint():
        m = read_checkpoint(ck)
        return (" - 'Resume track' continues from frame %s" % m["next_frame"]) if m else ""

    return _run(group, "track", work, apply, background, stop_hint=hint)


def on_retrack(group, background: bool = True, every_object: bool = False):
    """Re-track the object named in 'object name' (or every unlocked object of the shot, in one pass) using its
    artist keys and prompts as guides (forward + reverse). All results are ONE undo step."""
    from .track import apply_retracks, retrack_objects, retrack_plan
    try:
        src = _inner(group, "src", None)
        write, roto = _inner(group, "write", "STROTO_pixels"), _inner(group, "roto", "STROTO_shapes")
        project = group["stroto_project"].value()
        if not project:
            raise ValueError("set a project file")
        store, bus = _open_project(group, project)
        curves, height = roto["curves"], int(src.height())
        shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (src.name(),)).fetchone()
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % src.name())
        import_edits(store, bus, shot["id"], curves, height, int(nuke.frame()))       # capture latest artist edits
        frames = list(range(int(src.firstFrame()), int(src.lastFrame()) + 1))
        width = int(src.width())
        targets, skipped = _retrack_targets(store, shot["id"], _object_name(group), frames, every_object, retrack_plan)
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name())}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)
    sids = [sid for _, _, sid in targets]
    model, device = group["stroto_model"].value(), group["stroto_device"].value()     # read knobs on main thread
    try:
        ctransform = _colour(group)
    except ValueError as e:
        _status(group, "error: %s" % e); return None

    def work(job):
        ro = store_ro(project)          # worker thread: its own connection (SQLite objects are thread-bound)
        try:
            return retrack_objects(get_rgb, ro, sids, frames, width, height, model=model, device=device, job=job,
                                   colour_transform=ctransform)
        finally:
            ro.close()

    def apply(job):
        counts = apply_retracks(bus, store, job.result["shapes"])
        rep = sync_shot(store, shot["id"], curves, height)
        parts = []
        for name, oid, sid in targets:
            kept = len(json.loads(job.result["shapes"][sid]["generator"])["retrack"]["artist_frames"])
            parts.append("%s: %d AI keys changed, %d artist keys kept" % (name, counts[sid], kept)
                         + _review_text(store, oid))
        msg = "re-tracked %s; device %s" % (" | ".join(parts), job.result["device"])
        if skipped:
            msg += "; skipped %s" % ", ".join("%s (%s)" % s for s in skipped)
        if rep["conflicts"]:
            msg += "; NOT updated (edited in Roto): %s" % ", ".join(rep["conflicts"])
        job.applied = msg
        job.sync_report = rep
        group["stroto_status"].setValue(msg)

    return _run(group, "re-track", work, apply, background)


def on_render_mattes(group, background: bool = True):
    """Every object of the shot -> (soft) mattes -> multi-layer EXR sequence (T-069/T-070)."""
    from .mattes import default_output_dir, render_mattes
    try:
        src = _inner(group, "src", None)
        write, roto = _inner(group, "write", "STROTO_pixels"), _inner(group, "roto", "STROTO_shapes")
        project = group["stroto_project"].value()
        if not project:
            raise ValueError("set a project file")
        store, bus = _open_project(group, project)
        shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (src.name(),)).fetchone()
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % src.name())
        import_edits(store, bus, shot["id"], roto["curves"], int(src.height()), int(nuke.frame()))  # latest edits
        frames = list(range(int(src.firstFrame()), int(src.lastFrame()) + 1))
        out_dir = group["stroto_matte_dir"].value().strip() or default_output_dir(project, src.name())
        soft = bool(group["stroto_soft"].value())
        band, radius = max(1, int(group["stroto_band"].value())), max(1, int(group["stroto_radius"].value()))
        ctransform = _colour(group)
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name())}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)

    def work(job):
        ro = store_ro(project)          # worker thread: its own connection
        try:
            return render_mattes(get_rgb, ro, shot["id"], frames, out_dir, soft=soft, band=band, radius=radius,
                                 job=job, colour_transform=ctransform)
        finally:
            ro.close()

    def apply(job):
        r = job.result
        msg = "mattes: %d frames -> %s (layers: %s; %s edges, %.1f s)" % (
            len(r["files"]), r["pattern"], ", ".join(sorted(r["layers"].values())), "soft" if soft else "hard",
            r["seconds"])
        if r["frames_interpolated"]:
            msg += "; frames between keys (linear, may differ from Roto): %s" % "; ".join(
                "%s %s" % (k, _ranges(v)) for k, v in sorted(r["frames_interpolated"].items()))
        job.applied = msg
        group["stroto_status"].setValue(msg)

    return _run(group, "mattes", work, apply, background)


def _shot_for(group):
    """(store, bus, src, shot row) for a node whose shot exists; raises ValueError otherwise."""
    src = _inner(group, "src", None)
    project = group["stroto_project"].value()
    if not project:
        raise ValueError("set a project file")
    store, bus = _open_project(group, project)
    shot = store.conn.execute("SELECT * FROM shots WHERE name = ?", (src.name(),)).fetchone()
    return store, bus, src, project, shot


def on_export_shapes(group, out_dir: str = None):
    """Shot -> JSON (full fidelity) + one SVG per keyed frame. Returns {"json", "svg"} paths."""
    from st_roto import exr, interchange
    try:
        store, bus, src, project, shot = _shot_for(group)
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % src.name())
        resync(group)                                           # capture the latest Roto edits first
        base = exr.layer_name(src.name())
        out_dir = out_dir or os.path.join(os.path.splitext(os.path.abspath(project))[0] + "_export", base)
        os.makedirs(os.path.join(out_dir, "svg"), exist_ok=True)
        jpath = os.path.join(out_dir, base + ".json")
        interchange.write_json(jpath, store, shot["id"])
        frames = sorted({r[0] for r in store.conn.execute(
            "SELECT k.frame FROM shape_keys k JOIN shapes s ON s.id = k.shape_id JOIN objects o ON o.id = s.object_id "
            "WHERE o.shot_id = ?", (shot["id"],))})
        svgs = []
        for f in frames:
            path = exr.frame_path(os.path.join(out_dir, "svg"), base, f, "svg")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(interchange.svg_frame(store, shot["id"], f))
            svgs.append(path)
    except (ValueError, NodeBudgetError, OSError) as e:
        _status(group, "error: %s" % e); return None
    _status(group, "exported %s and %d SVG frames" % (jpath, len(svgs)))
    return {"json": jpath, "svg": svgs}


def on_import_shapes(group, path: str = None):
    """ST-ROTO JSON -> new objects in this shot (one undo step), then sync into the Roto node."""
    from st_roto import interchange
    try:
        if path is None:
            path = nuke.getFilename("Import ST-ROTO shapes", "*.json")
            if not path:
                return None
        store, bus, src, project, shot = _shot_for(group)
        if shot is None:
            ctx = {"src": src, "width": int(src.width()), "height": int(src.height()),
                   "first": int(src.firstFrame()), "last": int(src.lastFrame())}
            _ensure_shot(store, bus, ctx)
            shot = store.conn.execute("SELECT * FROM shots WHERE name = ?", (src.name(),)).fetchone()
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        ids = interchange.import_shot(bus, data, shot["id"])
        rep = resync(group, import_first=False)
    except (ValueError, NodeBudgetError, OSError) as e:
        _status(group, "error: %s" % e); return None
    _status(group, "imported %d objects from %s" % (len(data["objects"]), os.path.basename(path)))
    return {"ids": ids, "sync": rep}


def on_backup(group):
    try:
        project = group["stroto_project"].value()
        if not project:
            raise ValueError("set a project file")
        _open_project(group, project)
        path = session.backup_now(project)
    except Exception as e:
        _status(group, "error: backup failed: %s" % e); return None
    _status(group, "backup: %s" % path)
    return path


def on_package(group, zip_path: str = None, include_sources: bool = False, include_script: bool = True):
    """Portable package of the project (T-071) including the saved Nuke script (T-075). Sources are not included
    by default (size); unpacking relinks them."""
    from st_roto import persistence
    import datetime
    try:
        project = group["stroto_project"].value()
        if not project:
            raise ValueError("set a project file")
        _open_project(group, project)
        zip_path = zip_path or "%s_package_%s.zip" % (os.path.splitext(os.path.abspath(project))[0],
                                                      datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        script = nuke.root().name()
        scripts = [script] if include_script and script not in ("", "Root") and os.path.exists(script) else []
        man = persistence.pack(project, zip_path, include_sources=include_sources, tool_version="v0", scripts=scripts)
    except Exception as e:
        _status(group, "error: packaging failed: %s" % e); return None
    note = ""
    if include_script and not scripts:
        note = "; script NOT included (save it first)"
    elif scripts and nuke.root().modified():
        note = "; the script as last SAVED is included (unsaved changes are not)"
    _status(group, "package: %s (%d files)%s" % (zip_path, len(man["files"]), note))
    return zip_path


def _ranges(frames):
    from st_roto import quality
    return quality.ranges(frames)


def _retrack_targets(store, shot_id, current, frames, every_object, plan):
    """-> ([(object name, object id, shape id)], [(name, reason)]). One object: errors are raised; every object:
    locked objects and objects with nothing to track from are skipped and reported."""
    objs = store.objects(shot_id)
    if not every_object:
        objs = [o for o in objs if o["name"] == current]
        if not objs:
            raise ValueError("no object named %r (set 'object name')" % current)
    targets, skipped = [], []
    from st_roto import views
    for o in objs:
        main = views.main_shape(store, o["id"])
        shapes = [main] if main else []
        if not shapes:
            if not every_object:
                raise ValueError("object %r has no shape" % o["name"])
            skipped.append((o["name"], "no shape")); continue
        if every_object and (o["locked"] or shapes[0]["locked"]):
            skipped.append((o["name"], "locked")); continue
        try:
            plan(store, shapes[0]["id"], frames)
        except ValueError:
            if not every_object:
                raise
            skipped.append((o["name"], "no artist keys or prompt")); continue
        targets.append((o["name"], o["id"], shapes[0]["id"]))
    if not targets:
        raise ValueError("nothing to re-track" + (": skipped %s" % ", ".join("%s (%s)" % s for s in skipped)
                                                  if skipped else ""))
    return targets, skipped


def _review_text(store, object_id):
    """'; REVIEW lost 16-20, 22; check 15, 21' (heuristic flags, st_roto.quality) or ''."""
    from st_roto import quality, views
    flags = views.review_for_object(store, object_id)
    return "; REVIEW %s" % quality.summary(flags) if flags else ""


def store_ro(path):
    """Separate store connection for worker threads, used for reading only (SQLite connections are thread-bound)."""
    from st_roto.store import ProjectStore
    return ProjectStore(path)


def resync(group, import_first: bool = True):
    """Capture artist edits made in the Roto node (import_edits), then make the Roto node reflect the project
    (sync_shot). Returns the sync report with the import report under "import"."""
    store, bus = _open_project(group, group["stroto_project"].value())
    src = _inner(group, "src", None)
    shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (src.name(),)).fetchone()
    empty = {"written": [], "updated": [], "removed": [], "unchanged": [], "conflicts": [], "import": None}
    if shot is None:
        return empty
    curves = _inner(group, "roto", "STROTO_shapes")["curves"]
    imp = import_edits(store, bus, shot["id"], curves, _height(group), int(nuke.frame())) if import_first else None
    rep = sync_shot(store, shot["id"], curves, _height(group))
    rep["import"] = imp
    notes = []
    if imp and (imp["imported"] or imp["new_objects"]):
        notes.append("imported Roto edits: %s" % ", ".join(imp["imported"] + imp["new_objects"]))
    if imp and imp["skipped"]:
        notes.append("not imported: %s" % "; ".join("%s (%s)" % s for s in imp["skipped"]))
    if rep["conflicts"]:
        notes.append("NOT updated (edited in Roto): %s" % ", ".join(rep["conflicts"]))
    if notes:
        _status(group, " | ".join(notes))
    return rep


def on_import_edits(group):
    try:
        return resync(group)
    except Exception as e:
        _status(group, "error: %s" % e)
        return None


def shot_id_for(group):
    store, _ = _open_project(group, group["stroto_project"].value())
    r = store.conn.execute("SELECT id FROM shots WHERE name = ?", (_inner(group, "src", None).name(),)).fetchone()
    return r["id"] if r else None


def _ensure_shot(store, bus, ctx):
    """One shot per source node name in v0. Records the Read path and a fingerprint of its frames (T-075)."""
    name = ctx["src"].name()
    r = store.conn.execute("SELECT id FROM shots WHERE name = ?", (name,)).fetchone()
    if r:
        return r["id"]
    from st_roto import model as m, persistence
    sid = m.new_id()
    src_file = ctx["src"]["file"].value() if "file" in ctx["src"].knobs() else None
    try:
        fp = persistence.fingerprint_sequence(src_file, ctx["first"], ctx["last"]) if src_file else None
    except OSError:
        fp = None
    bus.execute({"op": "create_shot", "row": {"id": sid, "name": name, "width": ctx["width"], "height": ctx["height"],
                                              "first_frame": ctx["first"], "last_frame": ctx["last"],
                                              "source_path": src_file or None, "source_fingerprint": fp}})
    return sid



def on_resume_track(group, background: bool = True):
    return on_track(group, background, resume=True)


def checkpoint_dir(project: str, shot_name: str) -> str:
    """Where an interrupted Track keeps its state (inside the project's cache folder, never packaged)."""
    from st_roto import exr
    return os.path.join(os.path.splitext(os.path.abspath(project))[0] + "_cache", "track_resume",
                        exr.layer_name(shot_name))