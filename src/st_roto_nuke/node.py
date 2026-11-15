"""The ST_Roto node (single-node core under the Non-commercial 10-node cap, D-012) — v0.

Structure: Group "ST_Roto" with  Input -> Roto(STROTO_shapes, alpha) -> Output, plus a disabled Write
(STROTO_pixels) that pulls pixels into numpy. 5 nodes per shot including the group.

Artist workflow (knob tab ST-ROTO):
  1. drag the "point" handle in the viewer onto the object, press "+ Include" (or "- Exclude") - repeat as needed;
  2. "Preview" shows the AI shape for the current frame (temporary, not saved);
  3. "Load model" (optional, once per Nuke session) takes the one-time GPU set-up pause now;
  4. "Track" tracks forward from the prompt frame on a worker thread; the result is stored in the project
     (AI provenance, undoable) and synchronised into the Roto node without touching shapes edited there.
Python viewer clicks are not used: Non-commercial cannot load C++ overlays and Nuke offers no supported Python
mapping from viewer clicks to image coordinates; the XY knob handle is Nuke's native in-viewer point.
"""
from __future__ import annotations

import os
import threading
import traceback

import nuke
import nuke.rotopaint  # noqa: F401

from st_roto import jobs, prompts
from . import pixels, session
from .roto_export import export_preview, import_edits, sync_shot
from .track import apply_result, models_root, track_object

MODELS = ["sam2.1-hiera-tiny", "sam2.1-hiera-large"]
DEVICES = ["auto", "cpu"]
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
    _button(group, "stroto_clear", "Clear points", "n.on_clear_points(nuke.thisNode())", new_line=False)
    pts = nuke.String_Knob("stroto_points", "points (json)"); group.addKnob(pts)
    group.addKnob(nuke.Text_Knob("stroto_points_info", "", "no points"))
    group.addKnob(nuke.Int_Knob("stroto_click_frame", "click frame (if no points)"))
    group.addKnob(nuke.Text_Knob("stroto_div2", "AI"))
    group.addKnob(nuke.Enumeration_Knob("stroto_model", "model", MODELS))
    group.addKnob(nuke.Enumeration_Knob("stroto_device", "device", DEVICES))
    lm = _button(group, "stroto_load", "Load model", "n.on_load_model(nuke.thisNode())")
    lm.setTooltip("Loads the AI model onto the GPU now. Nuke may pause for a few seconds once; Track is smooth afterwards.")
    _button(group, "stroto_preview", "Preview", "n.on_preview(nuke.thisNode())", new_line=False)
    _button(group, "stroto_track", "Track", "n.on_track(nuke.thisNode())", new_line=False)
    _button(group, "stroto_cancel", "Cancel", "n.on_cancel(nuke.thisNode())", new_line=False)
    imp = _button(group, "stroto_import", "Save Roto edits to project", "n.on_import_edits(nuke.thisNode())")
    imp.setTooltip("Records shapes you edited or drew in this node's Roto into the ST-ROTO project (undoable).")
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
    _INNER[group.fullName()] = {"write": w, "roto": roto, "src": source}
    return group


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


def _status(group, text):
    def _set():
        group["stroto_status"].setValue(text)
    if threading.current_thread() is threading.main_thread():
        _set()
    else:
        nuke.executeInMainThread(_set)


def _height(group):
    return int(group.height())


def _context(group):
    """Everything a job needs, gathered on the main thread. Raises ValueError with an artist-readable message."""
    src = _inner(group, "src", None)
    write, roto = _inner(group, "write", "STROTO_pixels"), _inner(group, "roto", "STROTO_shapes")
    text = group["stroto_points"].value()
    if prompts.load(text):
        frame, xy, labels = prompts.for_tracker(text)
    else:                                                     # backwards-compatible single click
        cx, cy = group["stroto_click"].value()
        frame, xy, labels = int(group["stroto_click_frame"].value()), [(float(cx), _height(group) - float(cy))], [1]
    first, last = int(src.firstFrame()), int(src.lastFrame())
    if not first <= frame <= last:
        raise ValueError("prompt frame %d is outside the source range %d-%d" % (frame, first, last))
    return {"src": src, "write": write, "roto": roto, "frame": frame, "xy": xy, "labels": labels,
            "first": first, "last": last, "width": int(src.width()), "height": int(src.height()),
            "model": group["stroto_model"].value(), "device": group["stroto_device"].value(),
            "project": group["stroto_project"].value(), "object": group["stroto_object"].value() or "object",
            "pixel_path": pixels.temp_pixel_path(group.name())}


def _renderer(ctx, background):
    def get_rgb(frame):
        if background:
            return nuke.executeInMainThreadWithResult(pixels.render_frame, (ctx["write"], frame, ctx["pixel_path"]))
        return pixels.render_frame(ctx["write"], frame, ctx["pixel_path"])
    return get_rgb


def _run(group, name, work, apply, background):
    """Start a job; `apply(job)` runs on the main thread; every failure ends up in the status knob."""
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
            job.applied = "failed: " + job.error.strip().splitlines()[-1]
            _status(group, job.applied)
        else:
            job.applied = "cancelled"
            _status(group, "cancelled")

    job = jobs.Job(work, name=name, on_finish=finished,
                   on_progress=lambda j: _status(group, "%s %d%%: %s" % (name, 100 * j.progress, j.message)))
    job.applied, job.apply_error = None, None
    _JOBS[group.fullName()] = job
    return job.start(background=background)


# ------------------------------------------------------------------------------------------------ buttons
def on_add_point(group, label: int):
    cx, cy = group["stroto_click"].value()
    try:
        text = prompts.add(group["stroto_points"].value(), int(nuke.frame()), float(cx), _height(group) - float(cy), label)
    except ValueError as e:
        _status(group, "error: %s" % e); return
    group["stroto_points"].setValue(text)
    group["stroto_points_info"].setValue(prompts.summary(text))


def on_clear_points(group):
    group["stroto_points"].setValue("")
    group["stroto_points_info"].setValue("no points")


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
    """Segment only the prompt frame and show it as a temporary shape (not saved, not undoable)."""
    try:
        ctx = _context(group)
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)

    def work(job):
        return track_object(get_rgb, [ctx["frame"]], ctx["frame"], ctx["xy"], model=ctx["model"],
                            device=ctx["device"], job=job, labels=ctx["labels"])

    def apply(job):
        export_preview(ctx["roto"]["curves"], job.result["keys"], ctx["height"])
        job.applied = "preview on frame %d (%s)" % (ctx["frame"], "object found" if job.result["keys"] else "NO object found")
        group["stroto_status"].setValue(job.applied)

    return _run(group, "preview", work, apply, background)


def on_track(group, background: bool = True):
    """Track forward from the prompt frame; store (AI provenance) and sync into the Roto node."""
    try:
        ctx = _context(group)
        if not ctx["project"]:
            raise ValueError("set a project file")
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)
    frames = list(range(ctx["frame"], ctx["last"] + 1))

    def work(job):
        return track_object(get_rgb, frames, ctx["frame"], ctx["xy"], model=ctx["model"], device=ctx["device"],
                            job=job, labels=ctx["labels"])

    def apply(job):
        result = job.result
        store, bus = session.project(ctx["project"])
        shot_id = _ensure_shot(store, bus, ctx)
        export_preview(ctx["roto"]["curves"], {}, ctx["height"])          # remove the temporary preview
        import_edits(store, bus, shot_id, ctx["roto"]["curves"], ctx["height"], ctx["frame"])   # capture artist work first
        apply_result(bus, shot_id, ctx["object"], result)
        rep = sync_shot(store, shot_id, ctx["roto"]["curves"], ctx["height"])
        msg = "done: %d keys, %d frames without object, device %s" % (
            len(result["keys"]), len(result["absent_frames"]), result["device"])
        if result["device_fallback"]:
            msg += " (FALLBACK: %s)" % result["device_reason"]
        if rep["conflicts"]:
            msg += "; NOT updated (edited in Roto): %s" % ", ".join(rep["conflicts"])
        job.sync_report = rep
        job.applied = msg
        group["stroto_status"].setValue(msg)

    return _run(group, "track", work, apply, background)


def resync(group, import_first: bool = True):
    """Capture artist edits made in the Roto node (import_edits), then make the Roto node reflect the project
    (sync_shot). Returns the sync report with the import report under "import"."""
    store, bus = session.project(group["stroto_project"].value())
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
    store, _ = session.project(group["stroto_project"].value())
    r = store.conn.execute("SELECT id FROM shots WHERE name = ?", (_inner(group, "src", None).name(),)).fetchone()
    return r["id"] if r else None


def _ensure_shot(store, bus, ctx):
    """One shot per source node name in v0."""
    name = ctx["src"].name()
    r = store.conn.execute("SELECT id FROM shots WHERE name = ?", (name,)).fetchone()
    if r:
        return r["id"]
    from st_roto import model as m
    sid = m.new_id()
    bus.execute({"op": "create_shot", "row": {"id": sid, "name": name, "width": ctx["width"], "height": ctx["height"],
                                              "first_frame": ctx["first"], "last_frame": ctx["last"]}})
    return sid
