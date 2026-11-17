"""The ST-ROTO node family beyond the main ST_Roto node (T-112, REQ-040, master prompt section 6).

Research and naming: docs/RESEARCH_2026-11-18_NODE_FAMILY.md. Measured budget rules (Nuke 17.1 Non-commercial,
research/probes/2026-11-18_node_family): every Node object Python obtains costs 1 of 10 per session (also repeated
look-ups of the same node; deleting the reference frees nothing), but a pasted node graph costs 1 whatever its
size and `nuke.thisNode()` in button callbacks costs nothing. So each family node is a Group made by Python
(1 object) whose inner graph is PASTED (1 object) and driven by knob expressions - Python never looks inner nodes
up, except the pixel Write of ST_RotoMatte when it renders (1 object, cached for the session).

* ST_RotoMatte (Matte + Refine + Holdout modules): renders ST-ROTO's refined mattes (guided / ViTMatte / hard, edge
  offset / blur, core/edge) for chosen objects or roles of a shot and brings them into the node graph: output =
  the input with alpha = the combined matte, plus one layer per object (and core/edge); plate RGB and every other
  input channel unchanged. Before the first render it passes its input through.
* ST_RotoOutput (Output module): shape export (JSON + SVG), delivery package, project package and backup for a
  shot; passes its input through.
Both name their shot explicitly (project file + shot = the ST_Roto node's source name), so they work anywhere in the
script and validate it.
"""
from __future__ import annotations

import os
import tempfile

import nuke

KIND_KNOB = "stroto_kind"
MATTE, OUTPUT = "matte", "output"

# Inner graph of ST_RotoMatte (.nk paste syntax). Stack rule (measured): a node with 'inputs 2' takes input 0 from
# the top of the stack, input 1 from below it.
MATTE_INNER = """set cut_paste_input [stack 0]
version 17.1 v3
Input {
 inputs 0
 name Input1
}
set N_IN [stack 0]
Read {
 inputs 0
 file "\\[value parent.stroto_pattern]"
 first {{parent.stroto_first}}
 last {{parent.stroto_last}}
 origfirst {{parent.stroto_first}}
 origlast {{parent.stroto_last}}
 on_error black
 name STROTO_mattes
}
push $N_IN
Copy {
 inputs 2
 channels all
 name STROTO_take_mattes
}
set N_C1 [stack 0]
push $N_IN
push $N_C1
Copy {
 inputs 2
 from0 rgba.red
 to0 rgba.red
 from1 rgba.green
 to1 rgba.green
 from2 rgba.blue
 to2 rgba.blue
 name STROTO_keep_plate_rgb
}
set N_C2 [stack 0]
push $N_C2
push $N_IN
Switch {
 inputs 2
 which {{parent.stroto_ready}}
 name STROTO_before_render
}
Output {
 name Output1
}
push $N_IN
Write {
 file_type tiff
 datatype "32 bit float"
 compression none
 channels rgb
 disable true
 name STROTO_pixels
}
"""

OUTPUT_INNER = """set cut_paste_input [stack 0]
version 17.1 v3
Input {
 inputs 0
 name Input1
}
Output {
 name Output1
}
"""


def _paste_inner(group, text):
    """Paste `text` as the group's inner graph; costs 1 Node object (measured), whatever its size. Returns the LAST
    pasted node (what nuke.nodePaste returns, measured)."""
    fd, path = tempfile.mkstemp(suffix=".nk", prefix="stroto_family_")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    try:
        with group:
            return nuke.nodePaste(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _btn(group, name, label, code, new_line=True, tip=None):
    b = nuke.PyScript_Knob(name, label, "import st_roto_nuke.family as f; " + code)
    if not new_line:
        b.clearFlag(nuke.STARTLINE)
    if tip:
        b.setTooltip(tip)
    group.addKnob(b)
    return b


def _common_knobs(group, kind, title, project, shot):
    group.addKnob(nuke.Tab_Knob("stroto_tab", title))
    k = nuke.String_Knob(KIND_KNOB, "kind", kind)
    k.setVisible(False)
    group.addKnob(k)
    p = nuke.File_Knob("stroto_project", "project file")
    p.setValue(project or "")
    p.setTooltip("The ST-ROTO project (.stroto) of the ST_Roto node that tracked the shot.")
    group.addKnob(p)
    s = nuke.String_Knob("stroto_shot", "shot", shot or "")
    s.setTooltip("The shot inside the project: the name of the node feeding the ST_Roto node (e.g. Read1). "
                 "Press 'Check' to list the shots and objects the project has.")
    group.addKnob(s)
    _btn(group, "stroto_check", "Check", "f.on_check(nuke.thisNode())", new_line=False,
         tip="Validates project, shot and objects and lists what the project contains.")


def create_matte(source=None, project: str = "", shot: str = ""):
    """ST_RotoMatte node (Group + pasted inner graph: 2 Node objects)."""
    from .node import MATTE_SIZES, default_matte_size
    g = nuke.nodes.Group(name="ST_RotoMatte1")
    _common_knobs(g, MATTE, "ST-ROTO Matte", project, shot)
    o = nuke.String_Knob("stroto_objects", "objects")
    o.setTooltip("Object names, comma separated; empty = every object of the shot (after the role filter).")
    g.addKnob(o)
    r = nuke.Enumeration_Knob("stroto_role_filter", "roles", ["all roles", "add", "holdout", "garbage"])
    r.setTooltip("Only objects with this role (holdout: a holdout matte of everything marked holdout, etc.). The "
                 "combined alpha follows the roles of the included objects (holdouts cut, garbage limits).")
    r.clearFlag(nuke.STARTLINE)
    g.addKnob(r)
    g.addKnob(nuke.Text_Knob("stroto_div_refine", "refine"))
    e = nuke.Enumeration_Knob("stroto_edges", "edges", ["guided filter", "ViTMatte-S (optional AI)", "hard"])
    e.setTooltip("guided filter: model-free soft edges from the plate; ViTMatte-S: learned matting (optional "
                 "download, training-data caveat); hard: the shapes exactly.")
    g.addKnob(e)
    for name, label, val in (("stroto_band", "edge band", 3), ("stroto_radius", "radius", 8)):
        k = nuke.Int_Knob(name, label); k.setValue(val); k.clearFlag(nuke.STARTLINE); g.addKnob(k)
    ms = nuke.Enumeration_Knob("stroto_matte_size", "matte size", MATTE_SIZES)
    ms.setValue(default_matte_size())
    g.addKnob(ms)
    off = nuke.Int_Knob("stroto_offset", "edge offset"); g.addKnob(off)
    bl = nuke.Double_Knob("stroto_edge_blur", "edge blur"); bl.clearFlag(nuke.STARTLINE); g.addKnob(bl)
    ce = nuke.Int_Knob("stroto_core_edge", "core/edge px"); ce.clearFlag(nuke.STARTLINE); g.addKnob(ce)
    dv = nuke.Enumeration_Knob("stroto_device", "device", ["auto", "cpu"]); g.addKnob(dv)
    md = nuke.File_Knob("stroto_matte_dir", "matte folder")
    md.setTooltip("Where the EXR mattes are written; empty = next to the project (<project>_mattes/<shot>_matte_node).")
    g.addKnob(md)
    _btn(g, "stroto_render", "Render mattes", "f.on_matte_render(nuke.thisNode())",
         tip="Renders the mattes for the whole shot and shows them in this node's output.")
    _btn(g, "stroto_cancel", "Cancel", "f.on_cancel(nuke.thisNode())", new_line=False)
    for name, label in (("stroto_pattern", "mattes"), ):
        k = nuke.String_Knob(name, label); k.setEnabled(False); g.addKnob(k)
    for name in ("stroto_first", "stroto_last", "stroto_ready"):
        k = nuke.Int_Knob(name, name); k.setVisible(False); g.addKnob(k)
    g.addKnob(nuke.Text_Knob("stroto_status", "status", "not rendered yet (passes its input through)"))
    w = _paste_inner(g, MATTE_INNER)                         # the last pasted node: the pixel Write (no look-up)
    if w is not None and w.name() == "STROTO_pixels":
        from . import node as n, pixels
        pixels.configure_write(w, pixels.temp_pixel_path(g.name()))
        w["disable"].setValue(True)
        n._INNER.setdefault(g.fullName(), {})["write"] = w
    if source is not None:
        g.setInput(0, source)
    return g


def create_output(source=None, project: str = "", shot: str = ""):
    """ST_RotoOutput node (Group + pasted pass-through: 2 Node objects)."""
    g = nuke.nodes.Group(name="ST_RotoOutput1")
    _common_knobs(g, OUTPUT, "ST-ROTO Output", project, shot)
    g.addKnob(nuke.Text_Knob("stroto_div_out", "deliver"))
    _btn(g, "stroto_export", "Export shapes (JSON + SVG)", "f.on_output(nuke.thisNode(), 'export')")
    _btn(g, "stroto_export_abc", "Export Alembic", "f.on_output(nuke.thisNode(), 'alembic')", new_line=False,
         tip="Animated closed Bezier curves + outline meshes per shape (.abc), pixel units, y up, z = 0.")
    _btn(g, "stroto_delivery", "Delivery package", "f.on_output(nuke.thisNode(), 'delivery')", new_line=False,
         tip="Zip with the latest mattes and shape export, settings, models used, reports and a checksummed manifest.")
    _btn(g, "stroto_package", "Package project", "f.on_output(nuke.thisNode(), 'package')")
    _btn(g, "stroto_backup", "Back up now", "f.on_output(nuke.thisNode(), 'backup')", new_line=False)
    md = nuke.File_Knob("stroto_matte_dir", "matte folder")
    md.setTooltip("Mattes to include in a delivery package; empty = the project's default matte folder.")
    g.addKnob(md)
    g.addKnob(nuke.Text_Knob("stroto_status", "status", "idle"))
    _paste_inner(g, OUTPUT_INNER)
    if source is not None:
        g.setInput(0, source)
    return g


# ------------------------------------------------------------------------------------------------ handlers
def _node():
    from . import node as n
    return n


def _status(group, text):
    _node()._status(group, text)


def _objects(group, store, shot_id):
    """Objects of the shot selected by the Matte node's 'objects' and 'roles' knobs. Raises ValueError."""
    from st_roto import views
    objs = [o for o in store.objects(shot_id) if views.main_shape(store, o["id"]) is not None]
    names = [x.strip() for x in group["stroto_objects"].value().split(",") if x.strip()] \
        if "stroto_objects" in group.knobs() else []
    if names:
        have = {o["name"] for o in objs}
        unknown = [x for x in names if x not in have]
        if unknown:
            raise ValueError("no object named %s in this shot (it has: %s)" % (", ".join(unknown),
                                                                             ", ".join(sorted(have)) or "none"))
        objs = [o for o in objs if o["name"] in names]
    role = group["stroto_role_filter"].value() if "stroto_role_filter" in group.knobs() else "all roles"
    if role != "all roles":
        objs = [o for o in objs if (o.get("role") or "add") == role]
    if not objs:
        raise ValueError("no object to render (objects %r, roles %r)" % (", ".join(names) or "all", role))
    return objs


def on_check(group):
    """Validate project / shot / objects; the status lists what the project offers. Returns a dict or None."""
    n = _node()
    try:
        store, bus, _src, project, shot = n._shot_for(group)
        shots = [r["name"] for r in store.conn.execute("SELECT name FROM shots ORDER BY name")]
        if shot is None:
            raise ValueError("no shot %r in this project (it has: %s)" % (group["stroto_shot"].value(),
                                                                        ", ".join(shots) or "none"))
        objs = store.objects(shot["id"])
        desc = ", ".join("%s%s%s" % (o["name"], "" if (o.get("role") or "add") == "add" else " [%s]" % o["role"],
                                     " (%s)" % o["view"] if o.get("view") else "") for o in objs)
        is_matte = group[KIND_KNOB].value() == MATTE
        chosen = _objects(group, store, shot["id"]) if is_matte else objs
    except (ValueError, n.NodeBudgetError) as e:
        _status(group, "error: %s" % e)
        return None
    _status(group, "ok: shot %s, %d object(s): %s%s" % (shot["name"], len(objs), desc or "none",
                                                       ("; this node uses: %s" % ", ".join(o["name"] for o in chosen))
                                                       if is_matte else ""))
    return {"shots": shots, "objects": [o["name"] for o in objs], "chosen": [o["name"] for o in chosen]}


def on_cancel(group):
    _node().on_cancel(group)


def _view_pattern(pattern, view):
    """'<dir>/<view>/<name>.####.exr' -> '<dir>/%V/<name>.####.exr' (Nuke Read per view)."""
    p = pattern.replace("\\", "/")
    head, tail = os.path.split(p)
    if os.path.basename(head) == view:
        return os.path.dirname(head) + "/%V/" + tail
    return p


def on_matte_render(group, background: bool = True):
    """Render the chosen objects' mattes for the whole shot (st_roto_nuke.mattes.render_mattes) and show them in this
    node's output (inner Read via the 'mattes' pattern knob). Several views: one sequence per view (%V)."""
    n = _node()
    from st_roto_nuke import colour, pixels
    from .mattes import default_output_dir, render_mattes
    try:
        store, bus, _src, project, shot = n._shot_for(group)
        if shot is None:
            raise ValueError("no shot %r in this project (press Check)" % group["stroto_shot"].value())
        objs = _objects(group, store, shot["id"])
        if shot["first_frame"] is None or shot["last_frame"] is None:
            raise ValueError("the shot has no frame range recorded")
        frames = list(range(int(shot["first_frame"]), int(shot["last_frame"]) + 1))
        width, height = int(shot["width"]), int(shot["height"])
        method = {"guided filter": "guided", "ViTMatte-S (optional AI)": "vitmatte", "hard": "hard"}[
            group["stroto_edges"].value()]
        if method == "vitmatte" and (n.ai_disabled_reason(group) or n.ai_runtime_problem()):
            raise ValueError("ViTMatte-S edges need AI: %s" % (n.ai_disabled_reason(group) or n.ai_runtime_problem()))
        out_dir = group["stroto_matte_dir"].value().strip() or \
            default_output_dir(project, shot["name"] + "_" + group.name())
        out_size = (1920, 1080) if group["stroto_matte_size"].value() == "fit 1920x1080" else None
        extras = {"offset_px": int(group["stroto_offset"].value()), "blur_px": float(group["stroto_edge_blur"].value()),
                  "core_edge_px": int(group["stroto_core_edge"].value())}
        band, radius = max(1, int(group["stroto_band"].value())), max(1, int(group["stroto_radius"].value()))
        dev = group["stroto_device"].value()
        ctransform = colour.resolve(colour.AUTO)
        write = n._inner(group, "write", "STROTO_pixels")
        ctx = {"write": write, "pixel_path": pixels.temp_pixel_path(group.name()), "width": width, "height": height,
               "group": group}
        vs = n.script_views()
        passes = {None: [o["id"] for o in objs]}
        if len(vs) > 1:
            ctx["view"] = n.prompt_view(group)
            every = [o["id"] for o in objs if o.get("view") not in vs]
            passes = {v: [o["id"] for o in objs if o.get("view") == v] + every for v in vs}
            passes = {v: ids for v, ids in passes.items() if ids}
    except (ValueError, KeyError, n.NodeBudgetError) as e:
        _status(group, "error: %s" % e)
        return None
    renderers = {v: n._renderer(ctx, background, v) for v in passes}
    names = [o["name"] for o in objs]

    def work(job):
        ro = n.store_ro(project)
        try:
            out = {}
            for v, ids in passes.items():
                out[v] = render_mattes(renderers[v], ro, shot["id"], frames,
                                       out_dir if v is None else os.path.join(out_dir, v), method=method,
                                       models_root=n._vitmatte_root() if method == "vitmatte" else None, device=dev,
                                       band=band, radius=radius, out_size=out_size, objects=ids, job=job,
                                       colour_transform=ctransform, **extras)
            return out
        finally:
            ro.close()

    def apply(job):
        res = job.result
        if None in res:
            pattern = res[None]["pattern"].replace("\\", "/")
        else:
            v0 = next(iter(res))
            pattern = _view_pattern(res[v0]["pattern"], v0)
        group["stroto_pattern"].setValue(pattern)
        group["stroto_first"].setValue(frames[0])
        group["stroto_last"].setValue(frames[-1])
        group["stroto_ready"].setValue(1)
        r0 = next(iter(res.values()))
        msg = "mattes of %s: %d frames %dx%d (%s edges) -> %s; alpha = combined, layers: %s" % (
            ", ".join(names), len(r0["files"]), r0["size"][0], r0["size"][1], method, pattern,
            ", ".join(sorted(r0["layers"].values())))
        if len(res) > 1:
            msg += "; one sequence per view (%s)" % ", ".join(str(v) for v in res)
        if r0.get("moved_from"):
            msg += "; previous mattes were in use: rendered into a new folder"
        job.applied = msg
        group["stroto_status"].setValue(msg)

    return n._run(group, "mattes", work, apply, background)


def on_output(group, what: str):
    """ST_RotoOutput actions, delegated to the main node's implementations (they accept family nodes)."""
    n = _node()
    try:
        _s, _b, _src, _p, shot = n._shot_for(group)            # validates project + shot early
        if shot is None:
            raise ValueError("no shot %r in this project (press Check)" % group["stroto_shot"].value())
    except (ValueError, n.NodeBudgetError) as e:
        _status(group, "error: %s" % e)
        return None
    if what == "export":
        return n.on_export_shapes(group)
    if what == "alembic":
        return n.on_export_alembic(group)
    if what == "delivery":
        return n.on_delivery(group)
    if what == "package":
        return n.on_package(group)
    if what == "backup":
        return n.on_backup(group)
    raise ValueError(what)


def create_from_selection(kind: str):
    """Menu: a Matte / Output node below the selected node. From an ST_Roto node: its project and shot."""
    try:
        sel = nuke.selectedNode()
    except ValueError:
        sel = None
    project, shot = "", ""
    if sel is not None and "stroto_project" in sel.knobs():
        project = sel["stroto_project"].value()
        if KIND_KNOB in sel.knobs():
            shot = sel["stroto_shot"].value()
        else:
            src = sel.input(0)
            shot = src.name() if src is not None else ""
    else:
        script = nuke.root().name()
        project = "" if script in ("", "Root") else os.path.splitext(script)[0] + ".stroto"
        shot = sel.name() if sel is not None else ""
    return (create_matte if kind == MATTE else create_output)(sel, project, shot)
