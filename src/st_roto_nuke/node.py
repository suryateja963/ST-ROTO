"""The ST_Roto node (single-node core under the Non-commercial 10-node cap, D-012) — v0.

Structure: Group "ST_Roto" with  Input -> Roto(STROTO_shapes, alpha) -> Output, plus a disabled Write
(STROTO_pixels) that pulls pixels into numpy. 5 nodes per shot including the group.

Artist workflow (knob tab ST-ROTO):
  1. set "object name", drag the "point" handle in the viewer onto the object, press "+ Include" (or "- Exclude")
     - repeat as needed; change "object name" and add points to prompt further objects (T-067);
     or drag the "box" rectangle around the object and press "Set box" (most reliable for object parts, T-079),
     then refine with include/exclude points;
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

from st_roto import jobs, prompts, views
from . import colour, pixels, session
from .roto_export import export_preview, import_edits, sync_shot
from .track import apply_results, models_root, track_object, track_objects

AUTO_MODEL = "auto (by free GPU memory)"
MODELS = ["sam2.1-hiera-tiny", "sam2.1-hiera-large", AUTO_MODEL]
SAME_MODEL = "same as model"
RANGE_MODES = ["whole shot", "from-to"]
RETRACK_MODELS = [SAME_MODEL, "sam2.1-hiera-large", AUTO_MODEL]
MATTE_SIZES = ["full resolution", "fit 1920x1080"]


def default_matte_size():
    """D-041 (owner, 2026-11-17): Nuke Non-commercial -> 'fit 1920x1080' (its own output limit); other editions ->
    'full resolution'."""
    try:
        return MATTE_SIZES[1] if nuke.env.get("nc") else MATTE_SIZES[0]
    except Exception:                                         # noqa: BLE001
        return MATTE_SIZES[0]
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
    bx = nuke.BBox_Knob("stroto_box", "box")
    bx.setTooltip("Drag this rectangle's corners in the viewer around the object, then press Set box. A box is the "
                  "most reliable prompt for parts of something bigger (a sleeve, a bag, one of several people); add "
                  "include/exclude points to refine it.")
    group.addKnob(bx)
    if source is not None:                                    # start as a visible rectangle in the middle of the plate
        w, h = float(source.width()), float(source.height())
        bx.setValue([w * 0.35, h * 0.35, w * 0.65, h * 0.65])
    _button(group, "stroto_set_box", "Set box", "n.on_set_box(nuke.thisNode())")
    cb = _button(group, "stroto_clear_box", "Clear box", "n.on_clear_box(nuke.thisNode())", new_line=False)
    cb.setTooltip("Removes the box of the object named above (its points stay).")
    pts = nuke.String_Knob("stroto_points", "points (json)"); group.addKnob(pts)
    group.addKnob(nuke.Text_Knob("stroto_points_info", "", "no points"))
    group.addKnob(nuke.Int_Knob("stroto_click_frame", "click frame (if no points)"))
    group.addKnob(nuke.Text_Knob("stroto_div2", "AI"))
    off = nuke.Boolean_Knob("stroto_ai_off", "disable AI (traditional roto only)")
    off.setTooltip("Master prompt section 3: switches every AI feature of this node off and hides its AI controls. "
                   "Draw and edit shapes in the node's Roto as usual, then 'Save Roto edits to project'; mattes "
                   "(guided filter / hard), export, RotoPaint copy, backups and packages keep working. A studio can "
                   "switch AI off for a whole Nuke session with the environment variable ST_ROTO_AI=off.")
    group.addKnob(off)
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
    rf = _button(group, "stroto_retrack_flagged", "Re-track flagged",
                 "n.on_retrack(nuke.thisNode(), every_object=True, flagged_only=True)", new_line=False)
    rf.setTooltip("Re-tracks only the objects whose review flags say the AI LOST them (REVIEW lost ...), with the "
                  "'re-track model' - e.g. track everything quickly with the tiny model, then fix the hard objects "
                  "with the large one.")
    rm_ = nuke.Enumeration_Knob("stroto_retrack_model", "re-track model", RETRACK_MODELS)
    rm_.setTooltip("Model for Re-track, Re-track all, Re-track flagged and Re-prompt here. 'same as model' uses the "
                   "model above. sam2.1-hiera-large was more accurate on real footage (mean IoU +0.045, mostly fewer "
                   "lost frames; T-080) and ~1.4x slower; it needs ~7.1 GB of free GPU memory (T-092).")
    rm_.clearFlag(nuke.STARTLINE)
    group.addKnob(rm_)
    # propagation controls (T-097, REQ-091)
    rr = nuke.Enumeration_Knob("stroto_range_mode", "re-track range", RANGE_MODES)
    rr.setTooltip("whole shot: Re-track works on every frame. from-to: only frames 'from'..'to' are re-tracked; the "
                  "keys just outside the range guide it and stay unchanged, so the range joins smoothly.")
    group.addKnob(rr)
    for name, label in (("stroto_range_from", "from"), ("stroto_range_to", "to")):
        k = nuke.Int_Knob(name, label); k.clearFlag(nuke.STARTLINE); group.addKnob(k)
    lk = _button(group, "stroto_lock_range", "Lock range", "n.on_lock_range(nuke.thisNode(), True)", new_line=False)
    lk.setTooltip("Locks the keys of the object named above on frames 'from'..'to': the AI never changes them and "
                  "every re-track uses them as guides. Undoable.")
    _button(group, "stroto_unlock_range", "Unlock range", "n.on_lock_range(nuke.thisNode(), False)", new_line=False)
    ex_ = nuke.String_Knob("stroto_exclude", "exclude frames")
    ex_.setTooltip("Frames the AI must not process or change in Track and Re-track, e.g. '12-14, 30' (flash frames, "
                   "cuts, frames you will roto by hand). Existing keys there stay as they are.")
    group.addKnob(ex_)
    rp = _button(group, "stroto_reprompt", "Re-prompt here", "n.on_reprompt_here(nuke.thisNode())")
    rp.setTooltip("For a frame the review flags (or your eye) say is wrong: drag the box around the object on THIS "
                  "frame, press Re-prompt here. The object named above is re-tracked in both directions with this "
                  "box as an extra guide; the fix is kept for later re-tracks. Your own keys are never changed.")
    wp = nuke.Boolean_Knob("stroto_reprompt_point", "with point"); wp.clearFlag(nuke.STARTLINE)
    wp.setTooltip("Also use the 'point' handle as an include click inside the box.")
    group.addKnob(wp)
    imp = _button(group, "stroto_import", "Save Roto edits to project", "n.on_import_edits(nuke.thisNode())",
                  new_line=False)
    imp.setTooltip("Records shapes you edited or drew in this node's Roto into the ST-ROTO project (undoable).")
    group.addKnob(nuke.Text_Knob("stroto_div3", "mattes"))
    meth = nuke.Enumeration_Knob("stroto_edges", "edges", ["guided filter", "ViTMatte-S (optional AI)", "hard"])
    meth.setTooltip("guided filter: model-free soft edges. ViTMatte-S: learned matting, better on hair and slightly "
                    "inaccurate shapes, weaker on motion blur (measured); optional download. NOTE: its weights are "
                    "Apache-2.0 but were trained on Composition-1k (Adobe Deep Image Matting data, terms on request "
                    "from Adobe) - check that this suits your use. hard: mattes identical to the shapes.")
    group.addKnob(meth)
    soft = nuke.Boolean_Knob("stroto_soft", "soft edges"); soft.setValue(True); group.addKnob(soft)
    soft.setVisible(False)                                   # kept for scripts made before the 'edges' choice
    soft.setTooltip("Refine a narrow band around each shape's edge against the plate (guided filter, no AI model). "
                    "Off: hard mattes identical to the shapes.")
    msz = nuke.Enumeration_Knob("stroto_matte_size", "matte size", MATTE_SIZES)
    msz.setValue(default_matte_size())
    msz.setTooltip("full resolution: EXR mattes at the plate's size. fit 1920x1080: mattes computed at full "
                   "resolution, then area-averaged down to fit 1920x1080 with the plate's proportions (Nuke "
                   "Non-commercial's own output limit). Plates that already fit are never scaled. Default: fit 1920x1080 in "
                   "Nuke Non-commercial, full resolution in other editions.")
    msz.clearFlag(nuke.STARTLINE)
    group.addKnob(msz)
    band = nuke.Int_Knob("stroto_band", "edge band"); band.setValue(3); band.clearFlag(nuke.STARTLINE); group.addKnob(band)
    band.setTooltip("Half-width in pixels of the zone that may become soft.")
    rad = nuke.Int_Knob("stroto_radius", "radius"); rad.setValue(8); rad.clearFlag(nuke.STARTLINE); group.addKnob(rad)
    rad.setTooltip("Guided-filter window radius in pixels.")
    rl = nuke.Enumeration_Knob("stroto_role", "object role", ["add", "holdout", "garbage"])
    rl.setTooltip("Role of the object named above in the combined matte (rgba.alpha and Nuke's render): add, holdout "
                  "(cut out, e.g. a pole in front of the actor) or garbage (the matte is kept only inside it). Its "
                  "own EXR layer stays unchanged. Press Set role.")
    group.addKnob(rl)
    sr_ = _button(group, "stroto_set_role", "Set role", "n.on_set_role(nuke.thisNode())", new_line=False)
    sr_.setTooltip("Applies 'object role' to the object named above (undoable).")
    md = nuke.File_Knob("stroto_matte_dir", "matte folder"); group.addKnob(md)
    md.setTooltip("Where the EXR mattes go. Empty: <project>_mattes/<shot>/ next to the project file.")
    rm = _button(group, "stroto_render_mattes", "Render mattes (EXR)", "n.on_render_mattes(nuke.thisNode())")
    rm.setTooltip("Writes one EXR per frame: a layer per object (<object>.A) and the combined matte in alpha.")
    ex = _button(group, "stroto_export_shapes", "Export shapes (JSON + SVG)", "n.on_export_shapes(nuke.thisNode())")
    ex.setTooltip("Writes <project>_export/<shot>/<shot>.json (every object, key and provenance; re-importable) and "
                  "one SVG per keyed frame.")
    cr = _button(group, "stroto_copy_rotopaint", "Copy shapes to RotoPaint", "n.on_copy_to_rotopaint(nuke.thisNode())")
    cr.setTooltip("Creates a RotoPaint node next to this one with native copies of every shape (keys and feather).")
    im = _button(group, "stroto_import_shapes", "Import shapes (JSON)", "n.on_import_shapes(nuke.thisNode())",
                 new_line=False)
    im.setTooltip("Adds the objects of an ST-ROTO JSON file to this shot (one undo step; marked as imported).")
    bk = _button(group, "stroto_backup", "Back up now", "n.on_backup(nuke.thisNode())")
    bk.setTooltip("Snapshot of the project file into <project>_backups/ (automatic backups also run every 5 minutes "
                  "after changes).")
    pk = _button(group, "stroto_package", "Package project", "n.on_package(nuke.thisNode())", new_line=False)
    pk.setTooltip("Portable zip: project, mattes, exports and a checksummed manifest (no model weights).")
    sr = _button(group, "stroto_sysreport", "System report",
                 "import st_roto_nuke.capabilities as c; c.show_report(nuke.thisNode())", new_line=False)
    sr.setTooltip("What this machine and Nuke edition can do: GPU, memory, AI runtime, models, edition limits "
                  "(render size, node budget, plug-ins), and why a feature is limited or unavailable.")
    group.addKnob(nuke.Text_Knob("stroto_status", "status", "idle"))
    with group:
        inp = nuke.nodes.Input(name="Input1")
        roto = nuke.nodes.Roto(name="STROTO_shapes", output="alpha")
        roto.setInput(0, inp)
        clamp = _make_clamp(roto)                             # T-098: holdout / garbage subtract; keep alpha 0-1
        out = nuke.nodes.Output(name="Output1")
        out.setInput(0, clamp)
        w = nuke.nodes.Write(name="STROTO_pixels")
        w.setInput(0, inp)
        pixels.configure_write(w, pixels.temp_pixel_path(group.name()))
        w["disable"].setValue(True)
    _add_motionblur_links(group)
    group["knobChanged"].setValue(KNOB_CHANGED)
    group["onCreate"].setValue(ON_CREATE)
    _INNER[group.fullName()] = {"write": w, "roto": roto, "src": source}
    apply_ai_visibility(group)
    return group


# ------------------------------------------------------------------------------------------------ AI off (REQ-010)
# Callbacks stored in the script: they must not fail where ST-ROTO is not installed, and must not touch
# nuke.thisNode() for unrelated knobs (Non-commercial: 10 Python node objects per session).
KNOB_CHANGED = ("k = nuke.thisKnob()\n"
                "if k is not None and k.name() == 'stroto_ai_off':\n"
                "    try:\n"
                "        import st_roto_nuke.node as n; n.apply_ai_visibility(nuke.thisNode())\n"
                "    except Exception:\n"
                "        pass\n")
ON_CREATE = ("try:\n"
             "    import st_roto_nuke.node as n; n.apply_ai_visibility(nuke.thisNode())\n"
             "except Exception:\n"
             "    pass\n")
AI_KNOBS = ("stroto_click", "stroto_add_inc", "stroto_add_exc", "stroto_clear", "stroto_clear_all", "stroto_box",
            "stroto_set_box", "stroto_clear_box", "stroto_points", "stroto_points_info", "stroto_click_frame",
            "stroto_model", "stroto_device", "stroto_anchors", "stroto_load", "stroto_preview", "stroto_track",
            "stroto_resume", "stroto_retrack", "stroto_retrack_all", "stroto_reprompt", "stroto_reprompt_point",
            "stroto_retrack_flagged", "stroto_retrack_model", "stroto_range_mode", "stroto_range_from",
            "stroto_range_to", "stroto_lock_range", "stroto_unlock_range", "stroto_exclude")
AI_ENV = "ST_ROTO_AI"


def ai_disabled_reason(group):
    """Why AI is off for this node (session-wide environment variable or the node's checkbox), or None."""
    v = os.environ.get(AI_ENV, "").strip().lower()
    if v in ("0", "off", "false", "no", "disabled"):
        return "AI is switched off for this Nuke session (%s=%s)" % (AI_ENV, os.environ.get(AI_ENV))
    if "stroto_ai_off" in group.knobs() and group["stroto_ai_off"].value():
        return "AI is disabled on this node ('disable AI' is ticked)"
    return None


def ai_runtime_problem():
    """None if the AI runtime can load, else an artist-readable reason. Imports st_roto_ai.runtime (which switches
    ONNX Runtime telemetry off at import), never onnxruntime directly."""
    try:
        from st_roto_ai import runtime  # noqa: F401
    except Exception as e:                                    # noqa: BLE001 - any failure means: no AI here
        return "the AI runtime (ONNX Runtime) is not installed or cannot load (%s: %s)" % (type(e).__name__, e)
    return None


def _refuse_ai(group):
    """True (and a status message) if an AI action must not run: AI switched off, or no AI runtime."""
    why = ai_disabled_reason(group) or ai_runtime_problem()
    if why:
        _status(group, "error: %s. ST-ROTO still works as a traditional roto tool: draw and edit shapes in this "
                       "node's Roto, then 'Save Roto edits to project'." % why)
        return True
    return False


def apply_ai_visibility(group):
    off = ai_disabled_reason(group) is not None
    for name in AI_KNOBS:
        if name in group.knobs():
            group[name].setVisible(not off)
    return off


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
            "model": group["stroto_model"].value(), "device": group["stroto_device"].value(), "model_note": "",
            "colour": _colour(group), "anchors": _anchors(group),
            "project": group["stroto_project"].value(), "object": current,
            "pixel_path": pixels.temp_pixel_path(group.name()), "group": group}


def plan_model(choice, device):
    """Memory-aware (model, device, note) for an AI action (T-092, REQ-021): measured GPU memory needs vs free
    memory now (local nvidia-smi); models already loaded by this Nuke need nothing new."""
    from st_roto import capabilities as cap
    present = {m: os.path.exists(os.path.join(models_root(), m, "video")) for m in MODELS if m != AUTO_MODEL}
    loaded = _loaded_models()
    gi = cap.gpu_info() if device != "cpu" else {"gpus": []}
    free = gi["gpus"][0]["free_mib"] if gi["gpus"] else None
    model, dev, note = cap.plan_model(choice, device, free, present, loaded, auto_choice=AUTO_MODEL)
    if dev != device and dev == "cpu" and loaded - {model}:
        # memory held by OTHER cached models may be what is missing: release it and look again
        _release_gpu_sessions()
        gi = cap.gpu_info()
        free = gi["gpus"][0]["free_mib"] if gi["gpus"] else None
        model, dev, note = cap.plan_model(choice, device, free, present, _loaded_models(), auto_choice=AUTO_MODEL)
    return model, dev, note


def _loaded_models():
    import sys
    rt = sys.modules.get("st_roto_ai.runtime")              # not loaded yet: nothing can be cached
    if rt is None:
        return set()
    return {os.path.basename(os.path.dirname(d)) for d in rt.loaded_model_dirs()}


def _release_gpu_sessions():
    import gc
    import sys
    rt = sys.modules.get("st_roto_ai.runtime")
    if rt is not None:
        rt.clear_cache()
    gc.collect()


def _is_oom(err):
    import sys
    rt = sys.modules.get("st_roto_ai.runtime")
    return bool(rt is not None and rt.is_out_of_memory(err))


def _excluded(group):
    """Frames the artist excluded from AI processing (knob 'exclude frames', T-097). Raises ValueError."""
    from st_roto import frames as _frames
    return _frames.parse(group["stroto_exclude"].value()) if "stroto_exclude" in group.knobs() else []


def _range(group, first, last):
    """(lo, hi) of a range-limited re-track, or (first, last) for the whole shot. Raises ValueError."""
    if "stroto_range_mode" not in group.knobs() or group["stroto_range_mode"].value() != "from-to":
        return first, last
    lo, hi = int(group["stroto_range_from"].value()), int(group["stroto_range_to"].value())
    if lo > hi:
        lo, hi = hi, lo
    lo, hi = max(lo, first), min(hi, last)
    if lo > hi:
        raise ValueError("the re-track range is outside the shot (%d-%d)" % (first, last))
    return lo, hi


def on_lock_range(group, lock: bool = True):
    """Lock (or unlock) the named object's keys on frames 'from'..'to' (T-097, REQ-11-14): stored in the main shape's
    generator ("locked_frames", one undoable op); locked keys guide every re-track and the AI never changes them."""
    from st_roto import views as _views
    try:
        store, bus = _open_project(group, group["stroto_project"].value())
        src = _inner(group, "src", None)
        shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (src.name(),)).fetchone()
        name = _object_name(group)
        obj = [o for o in (store.objects(shot["id"]) if shot else []) if o["name"] == name]
        if not obj:
            raise ValueError("no object named %r" % name)
        main = _views.main_shape(store, obj[0]["id"])
        lo, hi = int(group["stroto_range_from"].value()), int(group["stroto_range_to"].value())
        lo, hi = min(lo, hi), max(lo, hi)
        gen = json.loads(main["generator"]) if main["generator"] else {}
        cur = set(gen.get("locked_frames", []))
        new = (cur | set(range(lo, hi + 1))) if lock else (cur - set(range(lo, hi + 1)))
        if new:
            gen["locked_frames"] = sorted(new)
        else:
            gen.pop("locked_frames", None)
        bus.execute({"op": "update_shape", "id": main["id"], "fields": {"generator": json.dumps(gen, sort_keys=True)}})
        _status(group, "%s frames %d-%d of %s; locked now: %s" % ("locked" if lock else "unlocked", lo, hi, name,
                                                                 _ranges(sorted(new)) or "none"))
        return sorted(new)
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e)
        return None


def _make_clamp(roto):
    c = nuke.nodes.Clamp(name="STROTO_clamp")
    c["channels"].setValue("alpha")
    c["minimum"].setValue(0.0)
    c["maximum"].setValue(1.0)
    c.setInput(0, roto)
    return c


def _ensure_clamp(group):
    """Nodes made before T-098 have no Clamp after their Roto: add it when a role is first used (costs 2 node
    objects of the Non-commercial budget, once)."""
    cache = _INNER.setdefault(group.fullName(), {})
    if cache.get("clamp") is not None:
        return cache["clamp"]
    with group:
        c = nuke.toNode("STROTO_clamp")
        if c is None:
            roto = _inner(group, "roto", "STROTO_shapes")
            out = nuke.toNode("Output1")
            if out is None:
                raise NodeBudgetError("Nuke returned no node for %s.Output1 (Non-commercial 10-node limit); save the "
                                      "script, reopen it and try again." % group.name())
            c = _make_clamp(roto)
            out.setInput(0, c)
    cache["clamp"] = c
    return c


def on_set_role(group, role=None):
    """Set the role of the object named above (T-098): add / holdout / garbage, one undoable op; the Roto node and
    the EXR combined matte follow it."""
    from st_roto import model as _m
    try:
        role = role or group["stroto_role"].value()
        if role not in _m.ROLES:
            raise ValueError("role must be one of %s" % ", ".join(_m.ROLES))
        store, bus = _open_project(group, group["stroto_project"].value())
        src = _inner(group, "src", None)
        shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (src.name(),)).fetchone()
        name = _object_name(group)
        obj = [o for o in (store.objects(shot["id"]) if shot else []) if o["name"] == name]
        if not obj:
            raise ValueError("no object named %r" % name)
        if role != "add":
            _ensure_clamp(group)
        bus.execute({"op": "update_object", "id": obj[0]["id"], "fields": {"role": role}})
        resync(group, import_first=False)
        _status(group, "%s is now %s%s" % (name, role, {"holdout": " (cut out of the combined matte)",
                                                         "garbage": " (combined matte kept only inside it)"}.get(role, "")))
        return role
    except (ValueError, NodeBudgetError, KeyError) as e:
        _status(group, "error: %s" % e)
        return None


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
    """get_rgb(frame) for jobs. Frames of another size (proxy mode, mixed-resolution sequences) are brought to the
    shot format and listed in ctx["refitted"] {frame: (w, h)}; unreadable frames raise pixels.FrameUnavailable
    (in background mode Nuke's main-thread call returns the exception object, so it is re-raised here). If the Nuke
    edition refuses to render the plate's size (Non-commercial: 1920 x 1080), frames are rendered reduced into the
    allowed box and scaled back to the shot size; ctx["capped"] records it (T-089)."""
    ctx.setdefault("refitted", {})

    def get_rgb(frame):
        if frame in ctx.get("excluded", ()):
            raise pixels.FrameExcluded(frame)
        if background:
            img = nuke.executeInMainThreadWithResult(_render_or_error, (ctx, frame))
            if isinstance(img, Exception):
                raise img
        else:
            img = _render_capped(ctx, frame)
        if img.shape[:2] != (ctx["height"], ctx["width"]):
            ctx["refitted"][frame] = (img.shape[1], img.shape[0])
            img = pixels.fit_to_format(img, ctx["width"], ctx["height"])
        return img
    return get_rgb


def _render_or_error(ctx, frame):
    """Main-thread side of get_rgb: exceptions in executeInMainThread callbacks are swallowed, so return them."""
    try:
        return _render_capped(ctx, frame)
    except Exception as e:                                    # noqa: BLE001 - handed back to the worker thread
        return e


def _render_capped(ctx, frame):
    """Main thread. Plain render; on the edition's resolution limit switch this job to a reduced render through the
    node's STROTO_pixel_fit Reformat (enabled only around each render, so saved scripts keep it off)."""
    if not ctx.get("capped"):
        try:
            return pixels.render_frame(ctx["write"], frame, ctx["pixel_path"])
        except pixels.ResolutionCapped as e:
            ctx["capped"] = _setup_fit(ctx, e)
    cap = ctx["capped"]
    fit = cap["node"]
    fit["disable"].setValue(False)
    try:
        img = pixels.render_frame(ctx["write"], frame, ctx["pixel_path"])
    finally:
        fit["disable"].setValue(True)
    if img.shape[:2] == (cap["box"][1], cap["box"][0]):
        import cv2
        img = cv2.resize(img, (ctx["width"], ctx["height"]), interpolation=cv2.INTER_LINEAR)
    return img


def _setup_fit(ctx, err):
    """Reformat (to box, distort) between the node's Input and its pixel Write, sized to the largest box inside the
    edition's limit with the plate's proportions. Created once per node (costs Non-commercial node budget)."""
    limit = err.limit or (1920, 1080)
    w, h = ctx["width"], ctx["height"]
    s = min(limit[0] / float(w), limit[1] / float(h), 1.0)
    box = (max(1, int(w * s)), max(1, int(h * s)))
    group = ctx.get("group")
    if group is None:
        raise ValueError("%s (this node cannot reduce frames for the AI; recreate it)" % err)
    cache = _INNER.setdefault(group.fullName(), {})
    fit = cache.get("fit")
    if fit is None:
        with group:
            fit = nuke.toNode("STROTO_pixel_fit")
            if fit is None:
                fit = nuke.nodes.Reformat(name="STROTO_pixel_fit")
                fit["disable"].setValue(True)
                fit.setInput(0, ctx["write"].input(0))
                ctx["write"].setInput(0, fit)
        if fit is None:
            raise NodeBudgetError("Nuke returned no node for the frame-reduction Reformat (Non-commercial 10-node "
                                  "limit); save the script, reopen it and try again.")
        cache["fit"] = fit
    fit["type"].setValue("to box")
    fit["box_fixed"].setValue(True)
    fit["box_width"].setValue(box[0])
    fit["box_height"].setValue(box[1])
    fit["resize"].setValue("distort")
    return {"node": fit, "box": box, "limit": limit}


def _sequence_note(ctx, missing):
    """Status text for T-086 conditions: skipped unreadable frames and frames brought to the shot format."""
    note = ""
    cap = ctx.get("capped")
    if cap:
        note += ("; this Nuke edition renders at most %dx%d, so the AI saw frames reduced to %dx%d (from %dx%d); "
                 "shapes are full resolution, accuracy slightly lower" % (cap["limit"] + cap["box"]
                                                                          + (ctx["width"], ctx["height"])))
    excl = sorted(set(missing or ()) & set(ctx.get("excluded", ())))
    missing = sorted(set(missing or ()) - set(excl))
    if excl:
        note += "; excluded by you (not processed, keys unchanged): %s" % _ranges(excl)
    if missing:
        note += "; %d unreadable frame(s) skipped (no key): %s" % (len(missing), _ranges(sorted(missing)))
    ref = ctx.get("refitted") or {}
    if ref:
        sizes = sorted(set(ref.values()))
        note += ("; %d frame(s) at another resolution (%s) were fitted to %dx%d like a default Reformat%s: frames %s"
                 % (len(ref), ", ".join("%dx%d" % s for s in sizes), ctx["width"], ctx["height"],
                    " (proxy mode is on: full accuracy needs proxy off)" if _proxy_on() else "",
                    _ranges(sorted(ref))))
    return note


def _proxy_on():
    try:
        return bool(nuke.root()["proxy"].value())
    except Exception:                                         # noqa: BLE001
        return False


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


def on_set_box(group):
    """Store the viewer rectangle as the current object's box on the current frame (replaces its old box)."""
    if "stroto_box" not in group.knobs():
        _status(group, "error: this node was made before box prompts; create a new ST_Roto node"); return
    x, y, r, t = [float(v) for v in group["stroto_box"].value()]
    h = _height(group)
    try:                                                      # Nuke y-up -> canonical y-down
        text = prompts.set_box(group["stroto_points"].value(), int(nuke.frame()), x, h - t, r, h - y,
                               obj=_object_name(group))
    except ValueError as e:
        _status(group, "error: %s" % e); return
    group["stroto_points"].setValue(text)
    group["stroto_points_info"].setValue(prompts.summary(text, _object_name(group)))


def on_clear_box(group):
    name = _object_name(group)
    text = prompts.clear_box(group["stroto_points"].value(), name, name)
    if not prompts.load(text):
        text = ""
    group["stroto_points"].setValue(text)
    group["stroto_points_info"].setValue(prompts.summary(text, name))


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
    if _refuse_ai(group):
        return None
    from st_roto_ai.sam2 import preload_video
    model, device, note = plan_model(group["stroto_model"].value(), group["stroto_device"].value())
    group["stroto_status"].setValue("loading %s (Nuke may pause briefly)..." % model)
    try:
        r = preload_video(os.path.join(models_root(), model, "video"), device)
    except Exception as e:
        group["stroto_status"].setValue("failed to load model: %s" % e)
        return None
    msg = "model %s loaded on %s in %.1f s" % (model, r["device"], r["seconds"])
    if r["fallback"]:
        msg += " (FALLBACK: %s)" % r["reason"]
    if note:
        msg += "; " + note
    group["stroto_status"].setValue(msg)
    return r


def on_cancel(group):
    job = _JOBS.get(group.fullName())
    if job:
        job.cancel()


def on_preview(group, background: bool = True):
    """Segment the current object on its prompt frame and show it as a temporary shape (not saved, not undoable)."""
    if _refuse_ai(group):
        return None
    try:
        ctx = _context(group)
        o = ctx["current"]
        if o is None:
            raise ValueError("no points for object %r (points exist for: %s)"
                             % (ctx["object"], ", ".join(g["name"] for g in ctx["objects"])))
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)

    ctx["model"], ctx["device"], ctx["model_note"] = plan_model(ctx["model"], ctx["device"])

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
    if _refuse_ai(group):
        return None
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
    try:
        ctx["excluded"] = set(_excluded(group))
    except ValueError as e:
        _status(group, "error: exclude frames: %s" % e); return None
    get_rgb = _renderer(ctx, background)
    ctx["model"], ctx["device"], ctx["model_note"] = plan_model(ctx["model"], ctx["device"])

    def work(job):
        def run(device, again):
            return track_objects(get_rgb, frames, ctx["objects"], model=ctx["model"], device=device, job=job,
                                 colour_transform=ctx["colour"], anchors=ctx["anchors"],
                                 parts=ctx.get("parts", True), checkpoint_dir=ck, resume=again)
        try:
            return run(ctx["device"], resume)
        except Exception as e:                              # noqa: BLE001
            if ctx["device"] == "cpu" or not _is_oom(e):
                raise
            # T-092: the GPU ran out of memory mid-run: free it and continue on the CPU from the last checkpoint
            _release_gpu_sessions()
            m = read_checkpoint(ck)
            res = run("cpu", m is not None)
            res["oom_fallback"] = ("the GPU ran out of memory; continued on the CPU from frame %s"
                                   % (m["next_frame"] if m else frames[0]))
            return res

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
        msg = "done%s: %s; device %s%s%s" % (" (resumed)" if resume else "", " | ".join(parts), result["device"],
                                              skipped_note, _sequence_note(ctx, result.get("missing_frames")))
        for extra in (ctx.get("model_note"), result.get("oom_fallback")):
            if extra:
                msg += "; " + extra
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


def on_reprompt_here(group, background: bool = True):
    """T-081: the box (+ optionally the point handle) on the CURRENT frame becomes a fix prompt of the current object,
    which is then re-tracked in both directions (one undo step; the fix is stored with the shape)."""
    if _refuse_ai(group):
        return None
    if "stroto_box" not in group.knobs():
        _status(group, "error: this node was made before box prompts; create a new ST_Roto node"); return None
    x, y, r, t = [float(v) for v in group["stroto_box"].value()]
    h = _height(group)
    x0, y0, x1, y1 = x, h - t, r, h - y
    if abs(x1 - x0) < prompts.MIN_BOX or abs(y1 - y0) < prompts.MIN_BOX:
        _status(group, "error: the box is too small: drag its corners around the object"); return None
    pts, labels = [(min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))], [prompts.BOX_TL, prompts.BOX_BR]
    if "stroto_reprompt_point" in group.knobs() and group["stroto_reprompt_point"].value():
        cx, cy = group["stroto_click"].value()
        pts.append((float(cx), h - float(cy))); labels.append(prompts.INCLUDE)
    return on_retrack(group, background, fix={"frame": int(nuke.frame()), "points": pts, "labels": labels})


def on_retrack(group, background: bool = True, every_object: bool = False, fix=None, flagged_only: bool = False):
    """Re-track the object named in 'object name' (or every unlocked object of the shot, in one pass) using its
    artist keys and prompts as guides (forward + reverse). All results are ONE undo step. fix: a new fix prompt for
    the current object (on_reprompt_here). flagged_only: only objects with REVIEW lost flags (T-093). The model is
    the node's 're-track model' (or 'model' when that says 'same as model')."""
    if _refuse_ai(group):
        return None
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
        first, last = int(src.firstFrame()), int(src.lastFrame())
        frames = list(range(first, last + 1))
        lo, hi = _range(group, first, last)
        width = int(src.width())
        anchors = {}
        if (lo, hi) != (first, last):                       # T-097: range-limited re-track
            from st_roto import views as _views
            frames = list(range(lo, hi + 1))
            for o in store.objects(shot["id"]):
                main = _views.main_shape(store, o["id"])
                if main is None:
                    continue
                ks = {k["frame"]: k["points"] for k in store.keys(main["id"])}
                a = {f: ks[f] for f in (lo - 1, hi + 1) if first <= f <= last and ks.get(f)}
                if a:
                    anchors[main["id"]] = a
            extra = sorted(set(f for a in anchors.values() for f in a))
            frames = sorted(set(frames) | set(extra))
        plan_fn = lambda st, sid, fr: retrack_plan(st, sid, fr, anchors=anchors.get(sid))   # noqa: E731
        targets, skipped = _retrack_targets(store, shot["id"], _object_name(group), frames, every_object, plan_fn)
        if flagged_only:
            from st_roto import quality, views
            keep = []
            for t in targets:
                if any(lvl == quality.LOST for _, lvl, _ in views.review_for_object(store, t[1])):
                    keep.append(t)
                else:
                    skipped.append((t[0], "no REVIEW lost flags"))
            targets = keep
            if not targets:
                raise ValueError("no object has REVIEW lost flags: nothing to re-track")
        fixes = None
        if fix is not None:
            if not frames[0] <= fix["frame"] <= frames[-1]:
                raise ValueError("frame %d is outside the source range" % fix["frame"])
            sid = targets[0][2]
            if fix["frame"] in retrack_plan(store, sid, frames)["artist"]:
                raise ValueError("frame %d has your own key for %r: it already guides the re-track (edit that key "
                                 "instead)" % (fix["frame"], targets[0][0]))
            fixes = {sid: fix}
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name()), "width": width, "height": height,
               "group": group, "excluded": set(_excluded(group)), "range": (lo, hi) if anchors or (lo, hi) != (first, last)
               else None}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)
    sids = [sid for _, _, sid in targets]
    choice = group["stroto_retrack_model"].value() if "stroto_retrack_model" in group.knobs() else SAME_MODEL
    if choice == SAME_MODEL:
        choice = group["stroto_model"].value()
    model, device, model_note = plan_model(choice, group["stroto_device"].value())
    try:
        ctransform = _colour(group)
    except ValueError as e:
        _status(group, "error: %s" % e); return None

    def work(job):
        ro = store_ro(project)          # worker thread: its own connection (SQLite objects are thread-bound)
        try:
            try:
                return retrack_objects(get_rgb, ro, sids, frames, width, height, model=model, device=device,
                                       job=job, colour_transform=ctransform, fixes=fixes, anchors=anchors)
            except Exception as e:                          # noqa: BLE001
                if device == "cpu" or not _is_oom(e):
                    raise
                _release_gpu_sessions()                     # T-092: GPU out of memory -> whole re-track on the CPU
                res = retrack_objects(get_rgb, ro, sids, frames, width, height, model=model, device="cpu",
                                      job=job, colour_transform=ctransform, fixes=fixes, anchors=anchors)
                res["oom_fallback"] = "the GPU ran out of memory; re-tracked on the CPU"
                return res
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
        msg = "re-tracked %s; model %s, device %s" % (" | ".join(parts), model, job.result["device"])
        if ctx.get("range"):
            msg += "; frames %d-%d only (keys outside unchanged)" % ctx["range"]
        msg += _sequence_note(ctx, job.result.get("missing_frames"))
        for extra in (model_note, job.result.get("oom_fallback")):
            if extra:
                msg += "; " + extra
        if fix is not None:
            msg = "re-prompted frame %d: %s" % (fix["frame"], msg)
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
        method = {"guided filter": "guided", "ViTMatte-S (optional AI)": "vitmatte", "hard": "hard"}.get(
            group["stroto_edges"].value() if "stroto_edges" in group.knobs() else "", "guided" if soft else "hard")
        if not soft:
            method = "hard"                                  # old scripts / tests that switch soft edges off
        if method == "vitmatte" and (ai_disabled_reason(group) or ai_runtime_problem()):
            raise ValueError("ViTMatte-S edges need AI: %s; choose 'guided filter' or 'hard'"
                             % (ai_disabled_reason(group) or ai_runtime_problem()))
        dev = group["stroto_device"].value()
        band, radius = max(1, int(group["stroto_band"].value())), max(1, int(group["stroto_radius"].value()))
        size_choice = (group["stroto_matte_size"].value() if "stroto_matte_size" in group.knobs()
                       else default_matte_size())             # nodes made before T-090 follow the edition default
        out_size = (1920, 1080) if size_choice == "fit 1920x1080" else None
        ctransform = _colour(group)
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name()),
               "width": int(src.width()), "height": int(src.height()), "group": group}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    get_rgb = _renderer(ctx, background)

    def work(job):
        ro = store_ro(project)          # worker thread: its own connection
        try:
            return render_mattes(get_rgb, ro, shot["id"], frames, out_dir, soft=soft, method=method,
                                 models_root=models_root(), device=dev, band=band, radius=radius, out_size=out_size,
                                 job=job, colour_transform=ctransform)
        finally:
            ro.close()

    def apply(job):
        r = job.result
        msg = "mattes: %d frames %dx%d -> %s (layers: %s; %s edges, %.1f s)" % (
            len(r["files"]), r["size"][0], r["size"][1], r["pattern"], ", ".join(sorted(r["layers"].values())),
            {"guided": "guided-filter", "vitmatte": "ViTMatte-S", "hard": "hard"}[method], r["seconds"])
        if tuple(r["size"]) != (int(src.width()), int(src.height())):
            msg += " (fitted from %dx%d)" % (int(src.width()), int(src.height()))
        if method == "vitmatte":
            from st_roto_ai.vitmatte import CAVEAT
            msg += ". " + CAVEAT
        if r["frames_interpolated"]:
            msg += "; frames between keys (linear, may differ from Roto): %s" % "; ".join(
                "%s %s" % (k, _ranges(v)) for k, v in sorted(r["frames_interpolated"].items()))
        if r.get("plate_missing"):
            msg += "; plate unreadable, hard edges written: %s" % _ranges(r["plate_missing"])
        msg += _sequence_note(ctx, None)
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
    curves = _inner(group, "roto", "STROTO_shapes")["curves"]
    if shot is None:
        # traditional roto (REQ-010): shapes drawn before any AI run create the shot, otherwise they would never be
        # recorded (found in T-088)
        if not (import_first and any(True for _ in curves.rootLayer)):
            return empty
        ctx = {"src": src, "width": int(src.width()), "height": int(src.height()),
               "first": int(src.firstFrame()), "last": int(src.lastFrame())}
        shot = {"id": _ensure_shot(store, bus, ctx)}
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
    if _refuse_ai(group):
        return None
    return on_track(group, background, resume=True)


def checkpoint_dir(project: str, shot_name: str) -> str:
    """Where an interrupted Track keeps its state (inside the project's cache folder, never packaged)."""
    from st_roto import exr
    return os.path.join(os.path.splitext(os.path.abspath(project))[0] + "_cache", "track_resume",
                        exr.layer_name(shot_name))


def on_copy_to_rotopaint(group):
    """Copy every shape of this shot (keys and feather) into a NEW RotoPaint node next to ST_Roto, fed by the same
    plate (T-073): independent native shapes, editable and renderable without ST-ROTO."""
    from .roto_export import build_shape, feather_of
    try:
        project = group["stroto_project"].value()
        if not project:
            raise ValueError("set a project file")
        store, _ = _open_project(group, project)
        src = _inner(group, "src", None)
        shot = store.conn.execute("SELECT id FROM shots WHERE name = ?", (src.name(),)).fetchone()
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % src.name())
        resync(group)                                              # include the latest Roto edits
        with nuke.root():                                          # next to ST_Roto, not inside it
            rpn = nuke.nodes.RotoPaint(name=group.name() + "_paint")
        rpn.setInput(0, src)
        rpn.setXYpos(group.xpos() + 120, group.ypos())
        curves, height = rpn["curves"], int(src.height())
        n = 0
        for s in views.shot_shapes(store, shot["id"]):
            keys = {k["frame"]: k["points"] for k in store.keys(s["id"])}
            if not keys:
                continue
            curves.rootLayer.append(build_shape(curves, s["name"], keys, height, feather_of(store.row("shapes", s["id"])),
                                                store.feathers(s["id"])))
            n += 1
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    _status(group, "copied %d shape(s) into %s (independent native RotoPaint shapes)" % (n, rpn.name()))
    return rpn