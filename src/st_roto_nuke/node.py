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

PROMPT_SOURCES = ["Roto shape", "mask node", "mask file", "Cryptomatte"]
AUTO_CONVENTION = "auto (measure)"
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
    _add_preset_knobs(group)
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
    pf = nuke.Enumeration_Knob("stroto_prompt_from", "prompt from", PROMPT_SOURCES)
    pf.setTooltip("Make the named object's prompt from a rough mask on the CURRENT frame (T-100): a Roto shape or "
                  "polygon drawn in this node, the alpha of another node (by name), or a mask image file (#### = "
                  "frame). The mask becomes its box + a click in each piece (the best prompt on real footage), so "
                  "the AI draws the exact shape. Then Track.")
    group.addKnob(pf)
    ps = nuke.String_Knob("stroto_prompt_source", "source"); ps.clearFlag(nuke.STARTLINE)
    ps.setTooltip("Roto shape: its name. Mask node: the node's name. Mask file: a path, #### or %04d for the frame.")
    group.addKnob(ps)
    up = _button(group, "stroto_prompt_use", "Use as prompt", "n.on_prompt_from_mask(nuke.thisNode())",
                 new_line=False)
    up.setTooltip("Replaces the named object's prompts with the box + clicks of that mask on the current frame. A Roto "
                  "shape drawn only for this (not yet an ST-ROTO object) is removed from the Roto afterwards.")
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
    rc = _button(group, "stroto_chatter", "Reduce chatter", "n.on_reduce_chatter(nuke.thisNode())")
    rc.setTooltip("Smooths the jitter of the named object's AI keys from frame to frame (each point's path is "
                  "fitted with a local quadratic over +-'frames' frames: real motion stays, frame-to-frame noise "
                  "goes). Your own keys and locked frames are never changed but steer the result. One undo step.")
    rca = _button(group, "stroto_chatter_all", "Reduce chatter (all)", "n.on_reduce_chatter(nuke.thisNode(), True)",
                  new_line=False)
    rca.setTooltip("Reduce chatter for every unlocked object of the shot (one undo step).")
    crk = nuke.Int_Knob("stroto_chatter_radius", "frames")
    crk.setValue(2)
    crk.setTooltip("Half-window of the smoothing in frames (2 = fit over 5 frames). Larger = smoother, but fast "
                   "changes of direction are rounded.")
    crk.clearFlag(nuke.STARTLINE)
    group.addKnob(crk)
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
    # stereo / multi-view (T-109, REQ-115)
    sv = nuke.Boolean_Knob("stroto_stereo", "track every view (stereo)")
    sv.setTooltip("For scripts with several views (stereo): Track tracks each prompted object in EVERY view, "
                  "independently. Prompts are given in the 'prompt view'; ST-ROTO finds the object in the other "
                  "views (disparity search on the prompt frame) and prompts them with a box + your clicks moved "
                  "there. Each view gets its own object (<name>_<view>), shown only in that view; a stereo check "
                  "flags frames where the views disagree (vertical offset, size, disparity jump, object in one view "
                  "only).")
    group.addKnob(sv)
    pv = nuke.String_Knob("stroto_prompt_view", "prompt view")
    pv.setTooltip("The view your prompts (point, box) are placed in. Empty = the script's hero view (or its first "
                  "view). Without 'track every view', Track works in this view only and its objects are shown only "
                  "in this view.")
    pv.clearFlag(nuke.STARTLINE)
    group.addKnob(pv)
    _add_channel_knobs(group)
    _add_review_view_knobs(group)
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
    from st_roto.matte import RGB_MODES
    rgbk = nuke.Enumeration_Knob("stroto_rgb_mode", "RGB in mattes", ["none"] + list(RGB_MODES))
    rgbk.setTooltip("none: EXRs hold mattes only. premultiplied: the plate's scene-linear RGB x combined alpha in "
                    "R, G, B (ready to merge 'over'). straight: unmultiplied. '..., decontaminated' (T-115): the colour "
                    "of soft-edge pixels (hair, motion blur) is recovered without the old background (measured: "
                    "fringe on a new background 42x lower on a green screen, 3x on a natural background); otherwise "
                    "edges keep the plate colour, old background included. The convention is written into each EXR "
                    "header.")
    group.addKnob(rgbk)
    spk = nuke.Enumeration_Knob("stroto_spill", "spill", ["none", "auto", "green", "blue"])
    spk.setTooltip("Spill correction of the foreground colour in the mattes' RGB: the screen colour's channel is "
                   "limited by the average of the other two. auto = judged from the background. Genuinely green "
                   "(blue) foreground colours are reduced too. Mattes only; alpha is never changed.")
    spk.clearFlag(nuke.STARTLINE)
    group.addKnob(spk)
    ofk = nuke.Int_Knob("stroto_offset", "edge offset"); ofk.clearFlag(nuke.STARTLINE)
    ofk.setTooltip("Grow (+) or shrink (-) every matte by this many pixels (dilate / erode). Mattes only: shapes "
                   "do not change.")
    group.addKnob(ofk)
    blk = nuke.Double_Knob("stroto_edge_blur", "edge blur"); blk.clearFlag(nuke.STARTLINE)
    blk.setTooltip("Feather the matte edges with a Gaussian of this size in pixels (mattes only).")
    group.addKnob(blk)
    cek = nuke.Int_Knob("stroto_core_edge", "core/edge width")
    cek.setTooltip("> 0: also write layers core_matte (the combined matte shrunk by this width) and edge_matte "
                   "(the band between), for edge work in comp.")
    group.addKnob(cek)
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
    ab = _button(group, "stroto_export_abc", "Export Alembic", "n.on_export_alembic(nuke.thisNode())",
                 new_line=False)
    ab.setTooltip("Writes <project>_export/<shot>/<shot>.abc for 3D packages: per shape an animated closed Bezier "
                  "curve (the exact spline) and an outline mesh (for readers without curves, e.g. Nuke's 3D), in pixel "
                  "units, y up, origin bottom-left, z = 0, one sample per keyed frame at the script's fps.")
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
    dl = _button(group, "stroto_delivery", "Delivery package", "n.on_delivery(nuke.thisNode())", new_line=False)
    dl.setTooltip("Zip for handing over this shot: the latest mattes and shape export, project settings, models used "
                  "(licence, revision, approval), processing, provenance and quality reports, dependencies, and a "
                  "checksummed manifest. Render mattes / Export shapes first.")
    sr = _button(group, "stroto_sysreport", "System report",
                 "import st_roto_nuke.capabilities as c; c.show_report(nuke.thisNode())", new_line=False)
    sr.setTooltip("What this machine and Nuke edition can do: GPU, memory, AI runtime, models, edition limits "
                  "(render size, node budget, plug-ins), and why a feature is limited or unavailable.")
    group.addKnob(nuke.Text_Knob("stroto_status", "status", "idle"))
    # Inner graph PASTED (T-112, measured: a paste costs 1 of the Non-commercial 10 Python node objects whatever its
    # size, and returns its last node - the pixel Write); then one look-up for the Roto: 3 objects for the whole node
    # instead of 6. Same nodes as before: Input1 -> STROTO_shapes (alpha, replace, T-110) -> STROTO_clamp (T-098)
    # -> Output1, and the disabled STROTO_pixels Write on the input.
    from .family import _paste_inner
    w = _paste_inner(group, MAIN_INNER)
    with group:
        roto = nuke.toNode("STROTO_shapes")
    if w is None or roto is None or w.name() != "STROTO_pixels":
        raise NodeBudgetError("Nuke returned no node while building %s (Non-commercial 10-node limit); save the "
                              "script, reopen it and try again." % group.name())
    pixels.configure_write(w, pixels.temp_pixel_path(group.name()))
    w["disable"].setValue(True)
    _add_motionblur_links(group)
    rk = nuke.Link_Knob("stroto_replace_alpha", "replace input alpha")
    rk.setLink("STROTO_shapes.replace")
    rk.setTooltip("On (default): the node's alpha is exactly the shapes. Off: the shapes are added over the input's "
                  "alpha (Nuke's Roto default) - on plates that already have alpha (CG renders, many EXRs) that "
                  "alpha is then 1 almost everywhere. Every other channel passes through unchanged either way "
                  "(measured, T-110). Nodes made before T-110 keep 'off'.")
    group.addKnob(rk)
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
                "        pass\n"
                "if k is not None and k.name() == 'stroto_review_colours':\n"
                "    try:\n"
                "        import st_roto_nuke.node as n; n.on_review_colours_toggled(nuke.thisNode())\n"
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
            "stroto_range_to", "stroto_lock_range", "stroto_unlock_range", "stroto_exclude",
            "stroto_prompt_from", "stroto_prompt_source", "stroto_prompt_use", "stroto_stereo", "stroto_prompt_view")
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


def _add_channel_knobs(group):
    """Extra channels as hints (T-110, REQ-113). Not AI controls: the checks also work with AI disabled."""
    from st_roto.channels import CONVENTIONS
    group.addKnob(nuke.Text_Knob("stroto_div_ch", "extra channels"))
    lc = _button(group, "stroto_ch_list", "List channels", "n.on_list_channels(nuke.thisNode())")
    lc.setTooltip("Shows the layers of the node's input (depth, motion vectors, Cryptomatte, normals, position, ...) "
                  "and its Cryptomatte layers with their object names. Every input channel passes through the node "
                  "unchanged; only alpha is replaced by the shapes.")
    group.addKnob(nuke.Text_Knob("stroto_ch_layers", "", "(press List channels)"))
    st = nuke.String_Knob("stroto_ch_stats", "medians of")
    st.setTooltip("Channels whose median inside each shape is recorded per frame, e.g. 'depth.Z' or 'depth.Z, "
                  "P.green, N.blue'. A spike (a frame differing from both neighbours, same direction, by more than "
                  "a quarter of the shot's usual range) flags the frame: the shape probably grabbed something nearer "
                  "or further away.")
    group.addKnob(st)
    mv = nuke.String_Knob("stroto_ch_motion", "motion vectors")
    mv.setTooltip("Forward motion-vector layer (pixels to the next frame), e.g. 'forward' (channels .u/.v). Each "
                  "shape moved by the vectors must match the next frame's shape (IoU >= 0.85), else CHECK.")
    group.addKnob(mv)
    mb = nuke.String_Knob("stroto_ch_motion_back", "backward")
    mb.setTooltip("Backward vector layer, e.g. 'backward'. Strongly recommended: with it, places where something "
                  "else covers or reveals the object are left out of the motion check (without it, occlusions "
                  "raise CHECK flags: measured).")
    mb.clearFlag(nuke.STARTLINE)
    group.addKnob(mb)
    cv = nuke.Enumeration_Knob("stroto_ch_motion_conv", "vector convention", [AUTO_CONVENTION] + list(CONVENTIONS))
    cv.setTooltip("Renderers differ in the sign of motion vectors. 'auto' measures it on the plate (the vectors "
                  "must move frame f onto frame f+1) and reports it; an axis that cannot be measured (nothing moves "
                  "that way) uses Nuke's convention.")
    cv.clearFlag(nuke.STARTLINE)
    group.addKnob(cv)
    cl = nuke.String_Knob("stroto_ch_crypto", "Cryptomatte layer")
    cl.setTooltip("e.g. CryptoObject, CryptoAsset, CryptoMaterial. Empty = the input's only Cryptomatte layer.")
    group.addKnob(cl)
    cm = nuke.String_Knob("stroto_ch_crypto_map", "Cryptomatte objects")
    cm.setTooltip("Which Cryptomatte names each ST-ROTO object should match, as JSON {\"object\": [\"name\", ...]}. "
                  "Filled automatically when you prompt an object from Cryptomatte; editable. The check flags frames "
                  "where the shape and the matte differ (IoU < 0.9).")
    cm.clearFlag(nuke.STARTLINE)
    group.addKnob(cm)
    ck = _button(group, "stroto_ch_check", "Check with channels", "n.on_check_channels(nuke.thisNode())")
    ck.setTooltip("Renders the chosen channels for the whole shot and checks every object's shapes against them. "
                  "Results are stored with the project (undoable) and appear as 'check' review flags in the status, "
                  "the Objects pane and the timeline.")


PRESET_NONE = "(choose a preset)"


def _add_preset_knobs(group):
    """Settings presets (T-111, REQ-121): built-in, studio (ST_ROTO_PRESET_DIR) and your own."""
    from st_roto import presets as _p
    pk = nuke.Enumeration_Knob("stroto_preset", "preset", [PRESET_NONE] + [e["name"] for e in _p.list_presets()])
    pk.setTooltip("Named sets of this node's SETTINGS (model, edges, matte options, channels to check, stereo, ...). "
                  "Never prompts, objects, frame ranges or paths. Built-in presets, your studio's (folder in "
                  "ST_ROTO_PRESET_DIR) and your own (Save settings as).")
    group.addKnob(pk)
    a = _button(group, "stroto_preset_apply", "Apply", "n.on_apply_preset(nuke.thisNode())", new_line=False)
    a.setTooltip("Sets this node's settings from the chosen preset; settings the preset does not name stay as they are.")
    _button(group, "stroto_preset_refresh", "Refresh", "n.on_refresh_presets(nuke.thisNode())", new_line=False)
    nm = nuke.String_Knob("stroto_preset_name", "new preset")
    nm.setTooltip("Name for 'Save settings as' (letters, digits, space, _ . ( ) + -).")
    group.addKnob(nm)
    sv = _button(group, "stroto_preset_save", "Save settings as", "n.on_save_preset(nuke.thisNode())",
                 new_line=False)
    sv.setTooltip("Saves this node's current settings as your preset (in %USERPROFILE%/.st_roto/presets, or "
                  "ST_ROTO_USER_PRESET_DIR). A preset of yours with the same name is replaced.")
    _button(group, "stroto_preset_delete", "Delete", "n.on_delete_preset(nuke.thisNode())", new_line=False)


_LINKED = {"stroto_replace_alpha": "replace"}                  # preset key -> inner Roto knob (Link_Knob targets)
_LINKED.update({name: target for name, _label, target in (
    ("stroto_mb_mode", "", "motionblur_mode"), ("stroto_mb_samples", "", "global_motionblur"),
    ("stroto_mb_shutter", "", "global_motionblur_shutter"),
    ("stroto_mb_offset", "", "global_motionblur_shutter_offset_type"))})


def _setting_knob(group, key):
    """The knob holding a preset setting: the node's own, or the inner Roto's for linked knobs (None if absent)."""
    if key in _LINKED:
        if key not in group.knobs():
            return None
        roto = _inner(group, "roto", "STROTO_shapes")
        return roto[_LINKED[key]] if _LINKED[key] in roto.knobs() else None
    return group[key] if key in group.knobs() else None


def current_settings(group) -> dict:
    """This node's preset settings (st_roto.presets.SETTINGS) with their current values."""
    from st_roto import presets as _p
    out = {}
    for key, kind in _p.SETTINGS.items():
        k = _setting_knob(group, key)
        if k is None:
            continue
        v = k.value()
        if kind == "bool":
            v = bool(v)
        elif kind == "int":
            v = int(v)
        elif kind == "float":
            v = float(v)
        else:
            v = str(v)
        out[key] = v
    return out


def on_refresh_presets(group):
    from st_roto import presets as _p
    names = [e["name"] for e in _p.list_presets()]
    cur = group["stroto_preset"].value()
    group["stroto_preset"].setValues([PRESET_NONE] + names)
    group["stroto_preset"].setValue(cur if cur in names else PRESET_NONE)
    return names


def on_apply_preset(group, name: str = None):
    """Apply a preset to this node. Returns {"applied": [keys], "skipped": [(key, why)]} or None on error."""
    from st_roto import presets as _p
    name = name or group["stroto_preset"].value()
    if not name or name == PRESET_NONE:
        _status(group, "error: choose a preset"); return None
    try:
        pr = _p.load(name)
    except (KeyError, ValueError) as e:
        _status(group, "error: preset: %s" % e); return None
    applied, skipped = [], [(p, "invalid") for p in pr["problems"]]
    for key, v in pr["settings"].items():
        k = _setting_knob(group, key)
        if k is None:
            skipped.append((key, "this node has no such setting (made with an older ST-ROTO)")); continue
        if _p.SETTINGS[key] == "choice" and hasattr(k, "values") and v not in k.values():
            skipped.append((key, "%r is not offered here" % v)); continue
        k.setValue(v)
        applied.append(key)
    if "stroto_ai_off" in applied:
        apply_ai_visibility(group)
    msg = "preset %r (%s) applied: %d setting(s)" % (name, pr["origin"], len(applied))
    if skipped:
        msg += "; skipped %s" % "; ".join("%s (%s)" % s for s in skipped)
    _status(group, msg)
    return {"applied": applied, "skipped": skipped, "origin": pr["origin"]}


def on_save_preset(group, name: str = None, description: str = ""):
    from st_roto import presets as _p
    name = (name or group["stroto_preset_name"].value()).strip()
    try:
        path = _p.save(name, current_settings(group), description)
    except (ValueError, OSError) as e:
        _status(group, "error: preset: %s" % e); return None
    on_refresh_presets(group)
    group["stroto_preset"].setValue(name)
    _status(group, "saved preset %r (%d settings) to %s" % (name, len(current_settings(group)), path))
    return path


def on_delete_preset(group, name: str = None):
    from st_roto import presets as _p
    name = name or group["stroto_preset"].value()
    try:
        path = _p.delete(name)
    except (KeyError, ValueError) as e:
        _status(group, "error: preset: %s" % e); return None
    on_refresh_presets(group)
    _status(group, "deleted preset %r (%s)" % (name, path))
    return path


def _add_review_view_knobs(group):
    """Review state in the viewer (T-111, REQ-120). Nuke Non-commercial cannot draw custom viewer graphics from Python
    (NDK only, T-033) and its viewer has no Python text API (measured): the shapes' own outlines are coloured per
    frame instead, and a readout names the flags of the current frame."""
    group.addKnob(nuke.Text_Knob("stroto_div_rv", "review in viewer"))
    rc = nuke.Boolean_Knob("stroto_review_colours", "review colours on shapes")
    rc.setValue(True)
    rc.setTooltip("Outlines of the node's shapes in the viewer: MAGENTA on frames flagged 'lost', YELLOW on 'check' "
                  "frames, Nuke's usual colour elsewhere. Visible while the shapes' Roto controls are open (Show "
                  "shapes in viewer). Updated after every Track, Re-track, Save Roto edits and channel check.")
    group.addKnob(rc)
    ss = _button(group, "stroto_show_shapes", "Show shapes in viewer", "n.on_show_shapes(nuke.thisNode())",
                 new_line=False)
    ss.setTooltip("Opens the controls of the node's Roto so its shapes (and their review colours) are drawn in the "
                  "viewer and can be edited.")
    tf = nuke.Text_Knob("stroto_this_frame", "this frame", "-")
    tf.setTooltip("The review flags of the frame the viewer shows (updated when the frame changes).")
    group.addKnob(tf)


_REVIEW = {}            # group full name -> {"group": Node, "levels": {object name: {frame: (level, reason)}}}
_VIEWER_CB = []


def _sync(group, store, shot_id, curves, height):
    """sync_shot, then the review colours (T-111) and the 'this frame' readout cache."""
    rep = sync_shot(store, shot_id, curves, height)
    _refresh_review(group, store, shot_id, curves)
    return rep


def _refresh_review(group, store, shot_id, curves):
    from .roto_export import apply_review_colours
    on = bool(group["stroto_review_colours"].value()) if "stroto_review_colours" in group.knobs() else True
    try:
        res = apply_review_colours(store, shot_id, curves, enabled=on)
    except Exception:                                         # noqa: BLE001 - never break a sync over colours
        res = {"levels": {}, "error": traceback.format_exc().strip().splitlines()[-1]}
    levels = res.get("levels") or {}
    if not on:
        from st_roto import views as _v
        levels = _v.review_levels(store, shot_id)
    names = {o["id"]: o["name"] for o in store.objects(shot_id)}
    _REVIEW[group.fullName()] = {"group": group, "levels": {names.get(k, k): v for k, v in levels.items()}}
    _ensure_viewer_callback()
    _show_this_frame(group.fullName(), int(nuke.frame()))
    return res


def _show_this_frame(full_name, frame):
    entry = _REVIEW.get(full_name)
    if not entry:
        return
    g = entry["group"]
    if "stroto_this_frame" not in g.knobs():
        return
    parts = []
    for name, per in sorted(entry["levels"].items()):
        if frame in per:
            lv, why = per[frame]
            parts.append("%s %s: %s" % (name, lv.upper(), why))
    g["stroto_this_frame"].setValue(("frame %d: " % frame + " | ".join(parts)) if parts else "frame %d: no flags" % frame)


def _on_viewer_frame():
    """Viewer knobChanged callback (measured T-111: fires with knob 'frame' when the frame changes)."""
    try:
        k = nuke.thisKnob()
        if k is None or k.name() != "frame":
            return
        f = int(nuke.frame())
        for name in list(_REVIEW):
            _show_this_frame(name, f)
    except Exception:                                         # noqa: BLE001 - callbacks must never raise
        pass


def _ensure_viewer_callback():
    if not _VIEWER_CB:
        try:
            nuke.addKnobChanged(_on_viewer_frame, nodeClass="Viewer")
            _VIEWER_CB.append(True)
        except Exception:                                     # noqa: BLE001
            pass


def on_review_colours_toggled(group):
    """knobChanged: colours on / off on the existing shapes right away (no other change)."""
    try:
        store, bus, src, project, shot = _shot_for(group)
    except (ValueError, NodeBudgetError):
        return None
    if shot is None:
        return None
    return _refresh_review(group, store, shot["id"], _inner(group, "roto", "STROTO_shapes")["curves"])


def on_show_shapes(group):
    """T-111: open the inner Roto's controls so the shapes and their review colours are drawn in the viewer."""
    roto = _inner(group, "roto", "STROTO_shapes")
    try:
        store, bus, src, project, shot = _shot_for(group)
        if shot is not None:
            _refresh_review(group, store, shot["id"], roto["curves"])
    except (ValueError, NodeBudgetError):
        pass
    roto.showControlPanel()
    _status(group, "shapes shown in the viewer (magenta = lost, yellow = check); edit them there, then 'Save Roto "
                   "edits to project'")


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
            "colour": _colour(group), "anchors": _anchors(group), "view": prompt_view(group),
            "project": group["stroto_project"].value(), "object": current,
            "pixel_path": pixels.temp_pixel_path(group.name()), "group": group}


def plan_model(choice, device):
    """Memory-aware (model, device, note) for an AI action (T-092, REQ-021): measured GPU memory needs vs free
    memory now (local nvidia-smi); models already loaded by this Nuke need nothing new."""
    from st_roto import capabilities as cap
    from .track import model_dir
    present = {m: os.path.exists(os.path.join(model_dir(m), "video")) for m in MODELS if m != AUTO_MODEL}
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


MAIN_INNER = """set cut_paste_input [stack 0]
version 17.1 v3
Input {
 inputs 0
 name Input1
}
set N_IN [stack 0]
Roto {
 output alpha
 replace true
 name STROTO_shapes
}
Clamp {
 channels alpha
 minimum 0
 maximum 1
 name STROTO_clamp
}
Output {
 name Output1
}
push $N_IN
Write {
 disable true
 name STROTO_pixels
}
"""


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


def _vitmatte_root():
    """The onnx folder of the location holding ViTMatte-S (T-101; vitmatte.model_path joins the model name)."""
    from .track import model_dir
    return os.path.dirname(model_dir("vitmatte-small-composition-1k"))


def _latest_dir(d):
    """`d` or its newest version folder (`d_v002`, ... - T-099), whichever exists last."""
    import glob
    vs = sorted(glob.glob(glob.escape(d) + "_v[0-9][0-9][0-9]"))
    return vs[-1] if vs else (d if os.path.isdir(d) else None)


def on_delivery(group, zip_path: str = None):
    """Delivery package of this node's shot (T-108, REQ-180): st_roto.delivery with the outputs, settings and
    dependencies gathered here."""
    import platform
    import sys as _sys
    from st_roto import delivery
    from .mattes import default_output_dir
    from .track import models_root
    try:
        store, bus, _src, project, row = _shot_for(group)
        name = _shot_name(group)
        if row is None:
            raise ValueError("nothing tracked or imported yet for %s" % name)
        resync(group)                                           # capture the latest Roto edits first
        from st_roto import exr as _exr
        exr_layer = _exr.layer_name(name)
        mdir = group["stroto_matte_dir"].value().strip() or default_output_dir(project, name)
        outputs = {"mattes": _latest_dir(mdir),
                   "shapes": _latest_dir(os.path.join(os.path.splitext(os.path.abspath(project))[0] + "_export",
                                                      exr_layer))}
        settings = {k: str(group[k].value()) for k in group.knobs() if k.startswith("stroto_")
                    and k not in ("stroto_status", "stroto_points_info")}
        deps = {"st_roto": _st_roto_version(), "nuke": nuke.NUKE_VERSION_STRING,
                "nuke_edition": "nc" if nuke.env.get("nc") else ("indie" if nuke.env.get("indie") else "commercial"),
                "python": platform.python_version(), "os": platform.platform()}
        for mod in ("numpy", "cv2", "OpenEXR", "onnxruntime"):
            m_ = _sys.modules.get(mod)
            if m_ is not None:
                deps[mod] = getattr(m_, "__version__", "?")
        zip_path = zip_path or os.path.join(os.path.dirname(os.path.abspath(project)),
                                            "%s_%s_delivery.zip" % (os.path.splitext(os.path.basename(project))[0],
                                                                     exr_layer))
        r = delivery.build(store, row["id"], zip_path, outputs={k: v for k, v in outputs.items() if v},
                           settings=settings, dependencies=deps,
                           manifests_dir=os.path.join(os.path.dirname(models_root()), "manifests"))
        missing = [k for k, v in outputs.items() if not v]
        _status(group, "delivery package: %s (%d files)%s" % (r["zip"], r["files"],
                                                             ("; not included (make them first): " + ", ".join(missing))
                                                             if missing else ""))
        return r
    except (ValueError, NodeBudgetError, KeyError, OSError) as e:
        _status(group, "error: delivery package: %s" % e)
        return None


def _st_roto_version():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    v = os.path.join(root, "VERSION")
    if os.path.exists(v):
        return open(v).read().strip()
    try:
        import subprocess
        return "0.1.0-dev+" + subprocess.check_output(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                                                     stderr=subprocess.DEVNULL).decode().strip()
    except Exception:                                          # noqa: BLE001
        return "0.1.0-dev"


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


def script_views():
    """The script's views in order (T-109); ['main'] when Nuke cannot say."""
    try:
        return list(nuke.views()) or ["main"]
    except Exception:                                         # noqa: BLE001
        return ["main"]


def prompt_view(group):
    """The view prompts are placed in and single-view work renders (T-109): the node's 'prompt view', else the
    script's hero view, else its first view. None in a single-view script. Raises ValueError for an unknown view."""
    vs = script_views()
    if len(vs) < 2:
        return None
    v = group["stroto_prompt_view"].value().strip() if "stroto_prompt_view" in group.knobs() else ""
    if v:
        if v not in vs:
            raise ValueError("prompt view %r is not a view of this script (%s)" % (v, ", ".join(vs)))
        return v
    try:
        hero = nuke.root()["hero_view"].value()
    except Exception:                                         # noqa: BLE001
        hero = ""
    return hero if hero in vs else vs[0]


def stereo_on(group):
    """True when the node tracks every view (its checkbox, and the script has several views)."""
    return bool("stroto_stereo" in group.knobs() and group["stroto_stereo"].value() and len(script_views()) > 1)


def _renderer(ctx, background, view=None):
    """get_rgb(frame) for jobs. Frames of another size (proxy mode, mixed-resolution sequences) are brought to the
    shot format and listed in ctx["refitted"] {frame: (w, h)}; unreadable frames raise pixels.FrameUnavailable
    (in background mode Nuke's main-thread call returns the exception object, so it is re-raised here). If the Nuke
    edition refuses to render the plate's size (Non-commercial: 1920 x 1080), frames are rendered reduced into the
    allowed box and scaled back to the shot size; ctx["capped"] records it (T-089)."""
    ctx.setdefault("refitted", {})
    view = view or ctx.get("view")                  # T-109: the view to render (None: single-view script)

    def get_rgb(frame):
        if frame in ctx.get("excluded", ()):
            raise pixels.FrameExcluded(frame)
        if background:
            img = nuke.executeInMainThreadWithResult(_render_or_error, (ctx, frame, view))
            if isinstance(img, Exception):
                raise img
        else:
            img = _render_capped(ctx, frame, view)
        if img.shape[:2] != (ctx["height"], ctx["width"]):
            ctx["refitted"][frame] = (img.shape[1], img.shape[0])
            img = pixels.fit_to_format(img, ctx["width"], ctx["height"])
        return img
    return get_rgb


def _render_or_error(ctx, frame, view=None):
    """Main-thread side of get_rgb: exceptions in executeInMainThread callbacks are swallowed, so return them."""
    try:
        return _render_capped(ctx, frame, view)
    except Exception as e:                                    # noqa: BLE001 - handed back to the worker thread
        return e


def _render_capped(ctx, frame, view=None):
    """Main thread. Plain render; on the edition's resolution limit switch this job to a reduced render through the
    node's STROTO_pixel_fit Reformat (enabled only around each render, so saved scripts keep it off)."""
    if not ctx.get("capped"):
        try:
            return pixels.render_frame(ctx["write"], frame, ctx["pixel_path"], view)
        except pixels.ResolutionCapped as e:
            ctx["capped"] = _setup_fit(ctx, e)
    cap = ctx["capped"]
    fit = cap["node"]
    fit["disable"].setValue(False)
    try:
        img = pixels.render_frame(ctx["write"], frame, ctx["pixel_path"], view)
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


def on_prompt_from_mask(group):
    """T-100 (REQ-060): rough Roto shape / another node's alpha / a mask file on the current frame -> the named
    object's prompt (box + interior clicks, st_roto.prompts.from_mask)."""
    frame, name = int(nuke.frame()), _object_name(group)
    h, w = _height(group), int(group.width())
    kind = group["stroto_prompt_from"].value()
    source = group["stroto_prompt_source"].value().strip()
    note = ""
    try:
        if not source:
            raise ValueError("set 'source' (shape name, node name or file path)")
        if kind == "Roto shape":
            mask, removed = _mask_from_roto_shape(group, source, frame, h, w)
            if removed:
                note = "; the shape %r was only a prompt and was removed from the Roto" % removed
        elif kind == "mask node":
            mask = _mask_from_node(source, frame, h, w, prompt_view(group))
        elif kind == "Cryptomatte":
            mask, layer, names = _mask_from_crypto(group, source, frame)
            _set_crypto_map(group, name, layer, names)
            note = "; the channel check will compare %s with Cryptomatte %s %s" % (name, layer, ", ".join(names))
        else:
            mask = _mask_from_file(source, frame, h, w)
        text = prompts.set_from_mask(group["stroto_points"].value(), frame, mask, obj=name)
    except (ValueError, IOError, OSError) as e:
        _status(group, "error: prompt from %s: %s" % (kind, e)); return None
    group["stroto_points"].setValue(text)
    group["stroto_points_info"].setValue(prompts.summary(text, name))
    p = prompts.from_mask(mask)
    _status(group, "prompt for %s on frame %d from %s %r: box + %d click(s)%s - now Track"
            % (name, frame, kind, source, len(p["points"]), note))
    return p


def _crypto_layer(group, src=None):
    """The Cryptomatte layer to use: the node's 'Cryptomatte layer', else the input's only one (from its metadata).
    Returns (layer, manifest {name: id}). Raises ValueError with what the input offers."""
    from st_roto import channels as chn
    src = src or _inner(group, "src", None)
    try:
        found = chn.find_layers(src.metadata())
    except Exception:                                         # noqa: BLE001
        found = {}
    want = group["stroto_ch_crypto"].value().strip() if "stroto_ch_crypto" in group.knobs() else ""
    if want:
        return want, found.get(want, {})
    if len(found) == 1:
        return next(iter(found.items()))
    if not found:
        raise ValueError("the input has no Cryptomatte metadata; set 'Cryptomatte layer' (e.g. CryptoObject)")
    raise ValueError("the input has several Cryptomatte layers (%s): set 'Cryptomatte layer'" % ", ".join(sorted(found)))


def _render_ch(ctx, frame, view):
    """Main thread: every channel of `frame` (pixels.render_channels); exceptions are returned (callback rule)."""
    try:
        return pixels.render_channels(ctx["write"], frame, ctx["channel_path"], view)
    except Exception as e:                                    # noqa: BLE001
        return e


def _mask_from_crypto(group, source, frame):
    """Coverage > 0.5 of the Cryptomatte names in `source` (comma separated) on `frame` (prompt view)."""
    from st_roto import channels as chn
    names = [n.strip() for n in source.split(",") if n.strip()]
    layer, manifest = _crypto_layer(group)
    unknown = [n for n in names if manifest and n not in manifest]
    if unknown:
        raise ValueError("not in the %s manifest: %s (it has: %s)" % (layer, ", ".join(unknown),
                                                                      ", ".join(sorted(manifest)[:30])))
    ctx = {"write": _inner(group, "write", "STROTO_pixels"),
           "channel_path": pixels.temp_pixel_path(group.name() + "_ch")[:-4] + ".exr"}
    ch = _render_ch(ctx, frame, prompt_view(group))
    if isinstance(ch, Exception):
        raise ValueError("could not render the channels of frame %d: %s" % (frame, str(ch).splitlines()[0]))
    mask = chn.crypto_mask(ch, layer, names) > 0.5
    if not mask.any():
        raise ValueError("%s %s covers no pixel on frame %d" % (layer, ", ".join(names), frame))
    return mask, layer, names


def _crypto_map(group):
    """{object name: {"layer", "names"}} from the node's 'Cryptomatte objects' knob (JSON). Raises ValueError."""
    if "stroto_ch_crypto_map" not in group.knobs():
        return {}
    text = group["stroto_ch_crypto_map"].value().strip()
    if not text:
        return {}
    try:
        raw = json.loads(text)
    except ValueError as e:
        raise ValueError("'Cryptomatte objects' is not valid JSON: %s" % e)
    out = {}
    for obj, v in raw.items():
        if isinstance(v, dict):
            out[obj] = {"layer": v.get("layer"), "names": list(v.get("names") or [])}
        else:
            out[obj] = {"layer": None, "names": [v] if isinstance(v, str) else list(v)}
    return out


def _set_crypto_map(group, obj, layer, names):
    if "stroto_ch_crypto_map" not in group.knobs():
        return
    try:
        cur = _crypto_map(group)
    except ValueError:
        cur = {}
    cur[obj] = {"layer": layer, "names": list(names)}
    group["stroto_ch_crypto_map"].setValue(json.dumps(cur, sort_keys=True))


def on_list_channels(group):
    """T-110: the input's layers and Cryptomatte layers (names) in the node; returns {"layers", "cryptomatte"}."""
    from st_roto import channels as chn
    src = _inner(group, "src", None)
    layers = chn.layers_of(src.channels())
    try:
        crypto = chn.find_layers(src.metadata())
    except Exception:                                         # noqa: BLE001
        crypto = {}
    text = "layers: %s" % ", ".join(layers)
    if crypto:
        text += " | Cryptomatte: %s" % "; ".join("%s (%s)" % (k, ", ".join(sorted(v)[:12]) + (" ..." if len(v) > 12 else ""))
                                                 for k, v in sorted(crypto.items()))
    group["stroto_ch_layers"].setValue(text)
    _status(group, text)
    return {"layers": layers, "cryptomatte": {k: sorted(v) for k, v in crypto.items()}}


def on_check_channels(group, background: bool = True):
    """T-110 (REQ-113): render the chosen channels for the whole shot and check every object's shapes (channel
    medians, motion vectors, Cryptomatte); store the reports (one undo step) -> CHECK review flags."""
    from st_roto import channels as chn, quality
    try:
        store, bus, src, project, shot = _shot_for(group)
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % src.name())
        write, roto = _inner(group, "write", "STROTO_pixels"), _inner(group, "roto", "STROTO_shapes")
        height, width = int(src.height()), int(src.width())
        import_edits(store, bus, shot["id"], roto["curves"], height, int(nuke.frame()))   # latest artist edits
        frames = list(range(int(src.firstFrame()), int(src.lastFrame()) + 1))
        stats = [s.strip() for s in group["stroto_ch_stats"].value().split(",") if s.strip()]
        ml = group["stroto_ch_motion"].value().strip()
        bl = group["stroto_ch_motion_back"].value().strip()
        conv_choice = group["stroto_ch_motion_conv"].value()
        motion = None
        if ml:
            motion = {"u": ml + ".u", "v": ml + ".v"}
            if bl:
                motion.update(bu=bl + ".u", bv=bl + ".v")
        cmap = _crypto_map(group)
        objs = [o for o in store.objects(shot["id"]) if views.main_shape(store, o["id"]) is not None]
        if not objs:
            raise ValueError("no object with shapes")
        crypto = {}
        if cmap:
            default_layer = None
            for o in objs:
                spec = cmap.get(o["name"]) or cmap.get(o.get("pair") or "")
                if spec and spec["names"]:
                    if not spec.get("layer"):
                        default_layer = default_layer or _crypto_layer(group, src)[0]
                    crypto[o["id"]] = {"layer": spec.get("layer") or default_layer, "names": spec["names"]}
        if not (stats or motion or crypto):
            raise ValueError("choose what to check: 'medians of' (e.g. depth.Z), 'motion vectors' (e.g. forward) "
                             "or 'Cryptomatte objects'")
        vs_ = script_views()
        pv = prompt_view(group)
        by_view = {}
        for o in objs:
            v = o.get("view") if o.get("view") in vs_ and len(vs_) > 1 else pv
            by_view.setdefault(v, []).append(o)
        ctx = {"write": write, "channel_path": pixels.temp_pixel_path(group.name() + "_ch")[:-4] + ".exr"}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: channels: %s" % e); return None
    names = {o["id"]: o["name"] for o in objs}

    def fetch(f, view):
        r = nuke.executeInMainThreadWithResult(_render_ch, (ctx, f, view)) if background else _render_ch(ctx, f, view)
        if isinstance(r, pixels.FrameUnavailable):
            return None
        if isinstance(r, Exception):
            raise r
        return r

    def work(job):
        import numpy as np
        ro = store_ro(project)
        try:
            keyed = {}
            for o in objs:
                per = {}
                for s in ro.shapes(o["id"]):
                    for k in ro.keys(s["id"]):
                        per.setdefault(k["frame"], []).append(k["points"])
                keyed[o["id"]] = per
            res, conv_info = {}, {}
            for v, group_objs in by_view.items():
                conv = conv_choice
                if motion and conv_choice == AUTO_CONVENTION:
                    pairs = [f for f in frames[::max(1, len(frames) // 6)] if f + 1 in frames][:6]
                    errs = []
                    for f in pairs:
                        job.check()
                        a, b = fetch(f, v), fetch(f + 1, v)
                        if a is None or b is None:
                            continue
                        try:
                            rgb_a = np.stack([a["R"], a["G"], a["B"]], -1)
                            rgb_b = np.stack([b["R"], b["G"], b["B"]], -1)
                            errs.append(chn.vector_errors(rgb_a, rgb_b, chn.resolve(a, motion["u"]),
                                                          chn.resolve(a, motion["v"])))
                        except ValueError:
                            continue                         # nothing moves on this frame
                    if not errs:
                        raise ValueError("could not measure the vector convention (no frame where the vectors move "
                                         "anything): choose it in 'vector convention'")
                    conv_info[v] = chn.choose_convention(errs)
                    conv = conv_info[v]["convention"]
                m = dict(motion, convention=conv) if motion else None

                def progress(i, n, v=v):
                    job.check()
                    job.report(i / float(max(1, n)), "frame %d%s" % (frames[i], (" (%s)" % v) if v else ""))
                out = chn.check_objects(
                    frames, {o["id"]: (lambda f, oid=o["id"]: keyed[oid].get(f, [])) for o in group_objs},
                    lambda f, v=v: fetch(f, v), height, width, stats=stats, motion=m,
                    crypto={o["id"]: crypto[o["id"]] for o in group_objs if o["id"] in crypto}, progress=progress)
                res.update(out)
            return {"reports": res, "conventions": conv_info}
        finally:
            ro.close()

    def apply(job):
        ops = []
        for oid, rep in job.result["reports"].items():
            old = store.channel_reports(oid)
            ops += [{"op": "set_channel_report", "object_id": oid, "frame": f, "data": None} for f in old if f not in rep]
            ops += [{"op": "set_channel_report", "object_id": oid, "frame": f, "data": r} for f, r in sorted(rep.items())]
        if ops:
            bus.execute({"op": "batch", "ops": ops})
        _refresh_review(group, store, shot["id"], roto["curves"])         # T-111: new flags show on the shapes
        parts = []
        for oid, rep in job.result["reports"].items():
            flags = [x for x in views.review_for_object(store, oid) if x[2].startswith("channels:")]
            parts.append("%s: %d frames%s" % (names[oid], len(rep),
                                              ("; CHECK " + quality.ranges([f for f, _, _ in flags])) if flags else ", no flags"))
        what = ([", ".join(stats)] if stats else []) + (["motion %s%s" % (ml, "/" + bl if bl else "")] if motion else []) \
            + (["Cryptomatte"] if crypto else [])
        msg = "channels checked (%s): %s" % ("; ".join(what), " | ".join(parts))
        for v, c in job.result["conventions"].items():
            msg += "; vectors%s: %s (measured%s)" % ((" " + v) if v else "", c["convention"],
                                                    (", %s axis not measurable: Nuke's sign used" % "/".join(c["undetermined"]))
                                                    if c["undetermined"] else "")
        if motion and not bl:
            msg += "; no backward layer: occlusions may raise motion flags"
        job.applied = msg
        group["stroto_status"].setValue(msg)

    return _run(group, "channels", work, apply, background)


def _mask_from_roto_shape(group, source, frame, h, w):
    """Canonical bool mask of the Roto shape named `source` (exact name, or ST-ROTO label without its tag) at
    `frame` (held / interpolated like the mattes). Returns (mask, removed name or None)."""
    import numpy as np
    from st_roto.geometry import Anchor, rasterize_spline
    from st_roto import matte as _matte
    from .roto_export import TAG_RE, read_keys, _remove
    curves = _inner(group, "roto", "STROTO_shapes")["curves"]
    hit = None
    for it in curves.rootLayer:
        nm = getattr(it, "name", "") or ""
        if nm == source or TAG_RE.sub("", nm) == source:
            hit = it
            break
    if hit is None:
        raise ValueError("no Roto shape named %r in this node" % source)
    keys = read_keys(hit, h)
    pts, _how = _matte.key_points_at([{"frame": f, "points": p} for f, p in sorted(keys.items())], frame)
    if not pts:
        raise ValueError("shape %r has no points" % source)
    a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:6]), corner=False) for q in pts]
    mask = rasterize_spline(a, h, w)
    removed = None
    if not TAG_RE.search(hit.name or ""):                    # drawn only as a prompt: not an ST-ROTO object
        removed = hit.name
        _remove(curves.rootLayer, hit)
        curves.changed()
    return mask, removed


def _mask_from_node(source, frame, h, w, view=None):
    """Alpha (> 0.5) of the node named `source` at `frame`, rendered through a temporary Write, fitted to the shot
    size like a default Reformat if it differs."""
    import cv2
    src = nuke.toNode(source)
    if src is None:
        raise ValueError("no node named %r (or the Non-commercial 10-node limit was reached)" % source)
    if "rgba.alpha" not in src.channels():
        raise ValueError("node %r has no alpha channel" % source)
    path = pixels.temp_pixel_path("mask_" + source)
    with nuke.root():
        wr = nuke.nodes.Write(inputs=[src])
    try:
        wr["file"].setValue(path.replace("\\", "/")); wr["proxy"].setValue(path.replace("\\", "/"))
        wr["file_type"].setValue("tiff"); wr["datatype"].setValue("32 bit float")
        wr["compression"].setValue("none"); wr["channels"].setValue("alpha")
        try:
            if view:                                     # several views: name one (T-109)
                nuke.execute(wr, frame, frame, 1, views=[view])
            else:
                nuke.execute(wr, frame, frame)
        except RuntimeError as e:
            raise ValueError("could not render %r on frame %d: %s" % (source, frame, str(e).splitlines()[0]))
    finally:
        nuke.delete(wr)
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError("rendered alpha of %r could not be read" % source)
    a = img if img.ndim == 2 else img[:, :, -1]
    if a.shape != (h, w):
        a = pixels.fit_to_format(a.astype("float32"), w, h)
    return a > 0.5


def _mask_from_file(source, frame, h, w):
    """A mask image (PNG/TIFF/JPEG: alpha if present, else grey; EXR: A / alpha / first channel) > half its range."""
    import re
    import numpy as np
    import cv2
    path = re.sub(r"#+", lambda m: "%0*d" % (len(m.group(0)), frame), source)
    if "%" in path:
        path = path % frame
    if not os.path.exists(path):
        raise IOError("mask file not found: %s" % path)
    if path.lower().endswith(".exr"):
        from st_roto import exr
        ch = exr.read_channels(path)
        a = next((ch[k] for k in ("A", "alpha", "rgba.alpha", "R", "Y") if k in ch), next(iter(ch.values())))
        a = np.asarray(a, np.float32)
        lim = 0.5
    else:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise IOError("cannot read %s" % path)
        a = img[:, :, 3] if img.ndim == 3 and img.shape[2] == 4 else (img if img.ndim == 2 else img[:, :, 0])
        a = a.astype(np.float32)
        lim = 0.5 * (65535.0 if img.dtype == np.uint16 else 255.0 if img.dtype == np.uint8 else 1.0)
    if a.shape != (h, w):
        a = pixels.fit_to_format(a, w, h)
    return a > lim


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
        from .track import model_dir
        r = preload_video(os.path.join(model_dir(model), "video"), device)
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
    rows = store.objects(shot["id"]) if shot else []
    # an object counts as tracked under its own name and under its stereo pair key (T-109: target -> target_left)
    existing = {o["name"] for o in rows} | {o["pair"] for o in rows if o.get("pair")}
    skipped_note = ""
    # T-109: stereo = every view tracked independently (one object per view); not checkpointed (no Resume yet)
    stereo = stereo_on(group) and not resume
    all_views = script_views()
    if stereo:
        from st_roto.stereo import view_object_name

        def names_of(o):
            return [view_object_name(o["name"], v) for v in all_views]
    else:
        def names_of(o):
            return [o["name"]]
    if not resume:
        already = [o["name"] for o in ctx["objects"] if any(n in existing for n in names_of(o))]
        ctx["objects"] = [o for o in ctx["objects"] if o["name"] not in already]
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
            if stereo:
                return _track_stereo(job, ctx, frames, get_rgb, background, device, all_views)
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
            if stereo:                                      # not checkpointed: the whole stereo run on the CPU
                res = run("cpu", False)
                res["oom_fallback"] = "the GPU ran out of memory; the stereo run was redone on the CPU"
                return res
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
        if not stereo and ctx.get("view"):
            # T-109: several views but one tracked: the shapes are right for that view only, so they show only there
            for r in result["objects"]:
                r.setdefault("view", ctx["view"]); r.setdefault("pair", r["name"])
        ids = apply_results(bus, shot_id, result["objects"])
        rep = _sync(group, store, shot_id, ctx["roto"]["curves"], ctx["height"])
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
        if result.get("transfers"):
            msg += "; stereo (prompt view %s): %s" % (ctx["view"], ", ".join(
                "%s in %s %s" % (n, v, ("found at disparity %+.1f px" % t["dx"]) if isinstance(t, dict) else t)
                for (n, v), t in sorted(result["transfers"].items())))
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


def _track_stereo(job, ctx, frames, get_rgb, background, device, all_views):
    """T-109: track every prompted object in the prompt view, then find each object in every other view on its
    prompt frame (st_roto.stereo.estimate_disparity on the prompt-view result) and track it there independently,
    prompted with a box + the artist's clicks moved by that disparity. Results are named <name>_<view> and carry
    view + pair. Returns track_objects()-like {"objects", "device", ..., "transfers": {(name, view): info}}."""
    from st_roto import stereo as st
    hero = ctx["view"]
    w, h = ctx["width"], ctx["height"]
    kw = dict(model=ctx["model"], device=device, job=job, colour_transform=ctx["colour"], anchors=ctx["anchors"],
              parts=ctx.get("parts", True))
    res = track_objects(get_rgb, frames, ctx["objects"], **kw)
    out = [dict(r, name=st.view_object_name(o["name"], hero), view=hero, pair=o["name"])
           for o, r in zip(ctx["objects"], res["objects"])]
    missing = set(res.get("missing_frames") or ())
    transfers = {}
    for v in [x for x in all_views if x != hero]:
        if job is not None:
            job.check()                                     # cancelled -> jobs.Cancelled
        get_v = _renderer(ctx, background, v)
        derived = []
        for o, r in zip(ctx["objects"], res["objects"]):
            f = o["frame"]
            keys = [r["keys"].get(f)] + [p.get(f) for p in r.get("parts", [])]
            mask = st.mask_from_keys([k for k in keys if k], h, w)
            box = st.mask_box(mask)
            if box is None:
                transfers[(o["name"], v)] = "not tracked: the AI found nothing in %s on frame %d" % (hero, f); continue
            try:
                d = st.estimate_disparity(get_rgb(f), get_v(f), mask)
            except (ValueError, pixels.FrameUnavailable) as e:
                transfers[(o["name"], v)] = "not tracked: %s" % e; continue
            p = st.transfer_prompt(o, d["dx"], d["dy"], box, w, h)
            if p is None:
                transfers[(o["name"], v)] = "not tracked: outside the %s view" % v; continue
            transfers[(o["name"], v)] = d
            derived.append(p)
        if not derived:
            continue
        rv = track_objects(get_v, frames, derived, **kw)
        out += [dict(r, name=st.view_object_name(p["name"], v), view=v, pair=p["name"])
                for p, r in zip(derived, rv["objects"])]
        missing |= set(rv.get("missing_frames") or ())
        if rv.get("device_fallback"):
            res["device_fallback"], res["device_reason"] = True, rv.get("device_reason")
    res["objects"], res["transfers"], res["missing_frames"] = out, transfers, sorted(missing)
    return res


def on_reduce_chatter(group, every_object: bool = False, radius: int = None):
    """T-115 (REQ-101 chatter reduction): smooth the AI keys of the named object (or every unlocked object) with
    st_roto.chatter; artist keys, locked frames and collapsed part keys are kept and anchor the fit. One undoable
    batch, written as AI (the command bus refuses locked content). Returns {object: (jitter before, after, keys)}."""
    from st_roto import chatter, model as m
    from st_roto.pieces import is_collapsed
    try:
        store, bus, src, project, shot = _shot_for(group)
        if shot is None:
            raise ValueError("nothing tracked yet for %s" % _shot_name(group))
        roto = _inner(group, "roto", "STROTO_shapes")
        import_edits(store, bus, shot["id"], roto["curves"], int(src.height()), int(nuke.frame()))
        r = int(radius if radius is not None else (group["stroto_chatter_radius"].value()
                                                   if "stroto_chatter_radius" in group.knobs() else 2))
        if r < 1:
            raise ValueError("'frames' must be at least 1")
        objs = store.objects(shot["id"])
        if not every_object:
            objs = [o for o in objs if o["name"] == _object_name(group)]
            if not objs:
                raise ValueError("no object named %r (set 'object name')" % _object_name(group))
        objs = [o for o in objs if not o["locked"]]
        if not objs:
            raise ValueError("the object is locked")
        ops, report = [], {}
        for o in objs:
            before_all, after_all, changed = [], [], 0
            for s in store.shapes(o["id"]):
                if s["locked"]:
                    continue
                rows = store.keys(s["id"])
                keys = {k["frame"]: k["points"] for k in rows}
                gens = {k["frame"]: k["generator"] for k in rows}
                fixed = {k["frame"] for k in rows if k["origin"] != m.AI_GENERATED}
                gen = json.loads(s["generator"] or "{}") if s.get("generator") else {}
                fixed |= set(int(f) for f in gen.get("locked_frames", []))
                skip = {f for f, p in keys.items() if not p or is_collapsed(p)}
                sm = chatter.smooth_keys(keys, fixed=fixed, radius=r, skip=skip)
                before_all.append(chatter.jitter({f: p for f, p in keys.items() if f not in skip}))
                merged = dict(keys); merged.update(sm)
                after_all.append(chatter.jitter({f: p for f, p in merged.items() if f not in skip}))
                for f, pts in sorted(sm.items()):
                    ops.append({"op": "set_key", "shape_id": s["id"], "frame": f, "points": pts,
                                "generator": gens.get(f)})
                    changed += 1
            report[o["name"]] = (round(max(before_all or [0.0]), 3), round(max(after_all or [0.0]), 3), changed)
        if not ops:
            raise ValueError("nothing to smooth (no AI keys in runs of 4 or more frames)")
        bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_AI)
        _sync(group, store, shot["id"], roto["curves"], int(src.height()))
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    _status(group, "chatter reduced (+-%d frames, one undo step): %s" % (r, " | ".join(
        "%s: jitter %.3f -> %.3f px, %d keys" % (n, b, a, c) for n, (b, a, c) in report.items())))
    return report


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
            locked = json.loads(store.row("shapes", sid)["generator"] or "{}").get("locked_frames", [])
            if fix["frame"] in locked:                      # DEF-008: say why, with the right remedy
                raise ValueError("frame %d of %r is locked: press Unlock range for it first" % (fix["frame"], targets[0][0]))
            if fix["frame"] in retrack_plan(store, sid, frames)["artist"]:
                raise ValueError("frame %d has your own key for %r: it already guides the re-track (edit that key "
                                 "instead)" % (fix["frame"], targets[0][0]))
            fixes = {sid: fix}
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name()), "width": width, "height": height,
               "group": group, "excluded": set(_excluded(group)), "range": (lo, hi) if anchors or (lo, hi) != (first, last)
               else None}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    try:
        ctx["view"] = prompt_view(group)
    except ValueError as e:
        _status(group, "error: %s" % e); return None
    # T-109: every object is re-tracked on ITS view's pixels (objects without a view: the prompt view)
    vs_ = script_views()
    by_view = {}
    for _, oid, sid in targets:
        v = store.row("objects", oid).get("view") if len(vs_) > 1 else None
        by_view.setdefault(v if v in vs_ else ctx["view"], []).append(sid)
    renderers = {v: _renderer(ctx, background, v) for v in by_view}
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

        def run(dev):
            res = None
            for v, sids in by_view.items():                  # one pass per view (T-109)
                r = retrack_objects(renderers[v], ro, sids, frames, width, height, model=model, device=dev,
                                    job=job, colour_transform=ctransform, fixes=fixes, anchors=anchors)
                if res is None:
                    res = r
                else:
                    res["shapes"].update(r["shapes"])
                    res["missing_frames"] = sorted(set(res["missing_frames"]) | set(r["missing_frames"]))
            return res
        try:
            try:
                return run(device)
            except Exception as e:                          # noqa: BLE001
                if device == "cpu" or not _is_oom(e):
                    raise
                _release_gpu_sessions()                     # T-092: GPU out of memory -> whole re-track on the CPU
                res = run("cpu")
                res["oom_fallback"] = "the GPU ran out of memory; re-tracked on the CPU"
                return res
        finally:
            ro.close()

    def apply(job):
        counts = apply_retracks(bus, store, job.result["shapes"])
        rep = _sync(group, store, shot["id"], curves, height)
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
        knobs = group.knobs()
        extras = {"rgb_mode": group["stroto_rgb_mode"].value() if "stroto_rgb_mode" in knobs else None,
                  "spill": group["stroto_spill"].value() if "stroto_spill" in knobs else None,
                  "offset_px": int(group["stroto_offset"].value()) if "stroto_offset" in knobs else 0,
                  "blur_px": float(group["stroto_edge_blur"].value()) if "stroto_edge_blur" in knobs else 0.0,
                  "core_edge_px": int(group["stroto_core_edge"].value()) if "stroto_core_edge" in knobs else 0}
        ctransform = _colour(group)
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name()),
               "width": int(src.width()), "height": int(src.height()), "group": group}
    except (ValueError, NodeBudgetError) as e:
        _status(group, "error: %s" % e); return None
    # T-109: several views -> one matte sequence per view (<matte dir>/<view>/), each with that view's objects and
    # the objects shown in every view, refined on that view's plate
    vs_ = script_views()
    passes = {None: None}
    if len(vs_) > 1:
        try:
            ctx["view"] = prompt_view(group)
        except ValueError as e:
            _status(group, "error: %s" % e); return None
        objs = store.objects(shot["id"])
        every = [o["id"] for o in objs if o.get("view") not in vs_]
        passes = {}
        for v in vs_:
            ids = [o["id"] for o in objs if o.get("view") == v] + every
            if ids and (every or any(o.get("view") == v for o in objs)):
                passes[v] = ids
        if not passes:
            _status(group, "error: no objects to render"); return None
    renderers = {v: _renderer(ctx, background, v) for v in passes}

    def work(job):
        ro = store_ro(project)          # worker thread: its own connection
        try:
            out = {}
            for v, ids in passes.items():
                out[v] = render_mattes(renderers[v], ro, shot["id"], frames,
                                       out_dir if v is None else os.path.join(out_dir, v), soft=soft, method=method,
                                       models_root=_vitmatte_root() if method == "vitmatte" else None, device=dev,
                                       band=band, radius=radius, out_size=out_size, objects=ids, **extras,
                                       job=job, colour_transform=ctransform)
            if None in out:                                  # single view: the result as before
                return out[None]
            first = out[ctx["view"]] if ctx.get("view") in out else next(iter(out.values()))
            return dict(first, views=out)                   # several views: prompt view's result + every view's
        finally:
            ro.close()

    def apply(job):
        per = job.result.get("views") or {None: job.result}
        msgs = [("" if v is None else "%s view: " % v) + _describe(r) for v, r in per.items()]
        job.applied = "; ".join(msgs) if len(msgs) == 1 else " || ".join(msgs)
        group["stroto_status"].setValue(job.applied)

    def _describe(r):
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
        if r.get("moved_from"):
            msg += ("; the previous mattes are open in Nuke (a Read node), so this render went to a NEW folder: %s"
                    % os.path.dirname(r["pattern"]))
        st_ = r["settings"]
        bits = []
        if st_.get("alpha_convention") not in (None, "alpha only"):
            bits.append("RGB %s%s%s" % (st_["alpha_convention"],
                                        ", edges decontaminated" if st_.get("edge_colour") == "decontaminated" else "",
                                        (", despill %s" % st_["spill"]) if st_.get("spill") else ""))
        if st_.get("offset_px"):
            bits.append("offset %+d px" % st_["offset_px"])
        if st_.get("blur_px"):
            bits.append("edge blur %g px" % st_["blur_px"])
        if st_.get("core_edge_px"):
            bits.append("core/edge layers (%d px)" % st_["core_edge_px"])
        if bits:
            msg += "; " + ", ".join(bits)
        msg += _sequence_note(ctx, None)
        return msg

    return _run(group, "mattes", work, apply, background)


def is_family_node(group):
    """True for ST_RotoMatte / ST_RotoOutput (T-112): they name their shot in a knob and have no Roto of their own."""
    return "stroto_kind" in group.knobs()


def _shot_name(group):
    """The shot a node works on: the family nodes' 'shot' knob, else the ST_Roto node's source name."""
    if is_family_node(group):
        name = group["stroto_shot"].value().strip()
        if not name:
            raise ValueError("set 'shot' (the name of the node feeding the ST_Roto node, e.g. Read1)")
        return name
    return _inner(group, "src", None).name()


def _shot_for(group):
    """(store, bus, src, project, shot row or None) for a node; src is None for family nodes. Raises ValueError."""
    src = None if is_family_node(group) else _inner(group, "src", None)
    project = group["stroto_project"].value()
    if not project:
        raise ValueError("set a project file")
    if is_family_node(group) and not os.path.exists(project):
        raise ValueError("project file not found: %s" % project)
    store, bus = _open_project(group, project)
    shot = store.conn.execute("SELECT * FROM shots WHERE name = ?", (_shot_name(group),)).fetchone()
    return store, bus, src, project, shot


def on_export_shapes(group, out_dir: str = None):
    """Shot -> JSON (full fidelity) + one SVG per keyed frame. Returns {"json", "svg"} paths."""
    from st_roto import exr, interchange
    try:
        store, bus, src, project, shot = _shot_for(group)
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % _shot_name(group))
        resync(group)                                           # capture the latest Roto edits first
        base = exr.layer_name(_shot_name(group))
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


def on_export_alembic(group, path: str = None):
    """T-113: shot -> Alembic (.abc) next to the JSON export. Returns st_roto_nuke.alembic.write_shot's dict."""
    from st_roto import exr
    from . import alembic
    try:
        why = alembic.available()
        if why:
            raise ValueError("Alembic export is not available: %s" % why)
        store, bus, src, project, shot = _shot_for(group)
        if shot is None:
            raise ValueError("nothing tracked or imported yet for %s" % _shot_name(group))
        resync(group)                                           # capture the latest Roto edits first
        base = exr.layer_name(_shot_name(group))
        path = path or os.path.join(os.path.splitext(os.path.abspath(project))[0] + "_export", base, base + ".abc")
        try:
            fps = float(nuke.root()["fps"].value())
        except Exception:                                      # noqa: BLE001
            fps = 24.0
        r = alembic.write_shot(store, shot["id"], path, fps=fps)
    except (ValueError, NodeBudgetError, OSError, RuntimeError) as e:
        _status(group, "error: %s" % e); return None
    shapes = len(r["prims"]) // 2
    _status(group, "exported %s: %d shape(s) as curves + outline meshes, frames %d-%d at %g fps (pixel units, y up)"
            % (r["path"], shapes, r["frames"][0], r["frames"][1], fps))
    return r


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
    (sync_shot). Returns the sync report with the import report under "import". Family nodes (no Roto): None."""
    if is_family_node(group):
        return None
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
    rep = _sync(group, store, shot["id"], curves, _height(group))
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