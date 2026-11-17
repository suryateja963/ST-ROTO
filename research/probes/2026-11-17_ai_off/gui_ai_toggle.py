"""T-088: in INTERACTIVE Nuke, ticking 'disable AI' on an ST_Roto node hides its AI controls through the node's
own knobChanged callback (stored in the script), and unticking shows them again.
Run (GUI): Nuke17.1.exe --nc research/probes/2026-11-17_ai_off/gui_ai_toggle.py -> result_gui_ai_toggle.json, exits.
"""
import json, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                           # noqa: E402
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

R = {"nuke": nuke.NUKE_VERSION_STRING, "gui": bool(nuke.GUI)}
VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"


def visible(g):
    import st_roto_nuke.node as n
    return sorted(k for k in n.AI_KNOBS if g[k].visible())


def step2():
    try:
        g = main.g
        R["after_tick_visible_ai_knobs"] = visible(g)
        g["stroto_ai_off"].setValue(False)
        QtCore.QTimer.singleShot(500, step3)
    except Exception:
        R["error"] = traceback.format_exc(); finish()


def step3():
    try:
        import st_roto_nuke.node as n
        R["after_untick_visible_count"] = len(visible(main.g))
        R["ai_knob_count"] = len(n.AI_KNOBS)
        R["passed"] = (R["before_visible_count"] == len(n.AI_KNOBS) and R["after_tick_visible_ai_knobs"] == []
                       and R["after_untick_visible_count"] == len(n.AI_KNOBS))
    except Exception:
        R["error"] = traceback.format_exc()
    finish()


def finish():
    json.dump(R, open(HERE + "/result_gui_ai_toggle.json", "w"), indent=1)
    os._exit(0)


def main():
    try:
        import tempfile
        import st_roto_nuke.node as n
        rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=2)
        g = n.create(rd, os.path.join(tempfile.mkdtemp(), "t.stroto"))
        main.g = g
        R["before_visible_count"] = len(visible(g))
        R["knobChanged_stored"] = g["knobChanged"].value() == n.KNOB_CHANGED
        g["stroto_ai_off"].setValue(True)             # in the GUI this fires the node's knobChanged callback
        QtCore.QTimer.singleShot(500, step2)
    except Exception:
        R["error"] = traceback.format_exc(); finish()


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(60000, finish)
