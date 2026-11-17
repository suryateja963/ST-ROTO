"""T-096: run tools/edge_truth/open_kit.py in INTERACTIVE Nuke exactly as the owner will (as __main__), then check
the nodes, the AI-off state and the frame range, and exit. Uses the kit's real project path but saves nothing.
Run: Nuke17.1.exe --nc research/probes/2026-11-17_edge_truth/gui_open_kit.py -> result_gui_open_kit.json"""
import json, os, runpy, traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
import nuke                                           # noqa: E402
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore
R = {"gui": bool(nuke.GUI)}
try:
    runpy.run_path(ROOT + "/tools/edge_truth/open_kit.py", run_name="__main__")
    R["ran"] = True
except Exception:
    R["error"] = traceback.format_exc()


def check():
    try:
        g = nuke.toNode("draw_truth")
        R["node"] = g is not None
        R["ai_off"] = bool(g["stroto_ai_off"].value()) if g else None
        R["track_hidden"] = (not g["stroto_track"].visible()) if g else None
        R["range"] = [int(nuke.root()["first_frame"].value()), int(nuke.root()["last_frame"].value())]
        R["format"] = [nuke.root().format().width(), nuke.root().format().height()]
        R["passed"] = bool(R.get("ran") and R["node"] and R["ai_off"] and R["track_hidden"] and R["range"] == [1, 20]
                           and R["format"] == [1920, 1920])
    except Exception:
        R["error"] = traceback.format_exc()
    json.dump(R, open(HERE + "/result_gui_open_kit.json", "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(4000, check)
