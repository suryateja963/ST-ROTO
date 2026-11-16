"""T-033: what the Nuke 17.1 Python API offers for viewer interaction, custom knobs, Deep and stereo - measured in
Non-commercial, headless (GUI-only objects reported as such). Run: Nuke17.1.exe --nc -t probe_api.py"""
import json, os
import nuke

R = {"gui": nuke.GUI, "nc": bool(nuke.env.get("nc"))}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception as e:
        R[name] = "ERR %s: %s" % (type(e).__name__, str(e)[:160])


# viewer
attempt("viewer_functions", lambda: sorted(n for n in dir(nuke) if "iewer" in n))
attempt("activeViewer", lambda: str(nuke.activeViewer()))
attempt("ViewerWindow_methods", lambda: sorted(m for m in dir(nuke.ViewerWindow) if not m.startswith("_")) if hasattr(nuke, "ViewerWindow") else "absent")
v = nuke.nodes.Viewer()
attempt("viewer_node_knobs_roi", lambda: [k for k in v.knobs() if k in ("roi", "gain", "gamma", "channels", "input_process", "viewerProcess", "zoom_lock")])
# custom knobs
attempt("PyCustom_Knob", lambda: hasattr(nuke, "PyCustom_Knob"))
attempt("PythonCustomKnob_in_NC", lambda: (lambda n: (n.addKnob(nuke.PyCustom_Knob("x", "x", "object()")), "added")[1])(nuke.nodes.NoOp()))
attempt("XY_Knob_viewer_handle", lambda: hasattr(nuke, "XY_Knob"))
attempt("Box3_or_BBox_Knob", lambda: [k for k in ("BBox_Knob", "Box3_Knob", "UV_Knob", "XYZ_Knob") if hasattr(nuke, k)])
attempt("knobChanged_callbacks", lambda: [f for f in ("addKnobChanged", "addOnUserCreate", "addUpdateUI") if hasattr(nuke, f)])
# deep
attempt("deep_nodes_create", lambda: [c for c in ("DeepRead", "DeepMerge", "DeepToImage", "DeepFromImage", "DeepHoldout2", "DeepRecolor")
                                      if (lambda c: (getattr(nuke.nodes, c)() is not None))(c)])
attempt("deepSample_method", lambda: hasattr(nuke.Node, "deepSample") and hasattr(nuke.Node, "deepSampleCount"))
# stereo
attempt("views", lambda: nuke.views())
attempt("addView", lambda: (nuke.root().addView("right"), nuke.views())[1])
attempt("oneView_views_knobs", lambda: [k for k in nuke.nodes.OneView().knobs() if k == "view"])
attempt("JoinViews", lambda: nuke.nodes.JoinViews().Class())
# blinkscript / gpu ops availability (for edge ops)
attempt("BlinkScript", lambda: nuke.nodes.BlinkScript().Class())
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json")
json.dump(R, open(out, "w"), indent=1)
print("API_AUDIT", json.dumps(R)[:3000])
