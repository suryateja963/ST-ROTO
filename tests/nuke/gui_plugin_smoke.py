"""GUI smoke test of nuke_plugin (init.py + menu.py) loaded via NUKE_PATH for this process only.
Run: set NUKE_PATH=D:\\ST-ROTO\\nuke_plugin (process env) and start  Nuke17.1.exe --nc tests/nuke/gui_plugin_smoke.py
"""
import json, os, traceback
import nuke
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
R = {}


def run():
    try:
        item = nuke.menu("Nodes").findItem("ST-ROTO/ST_Roto")
        R["menu_item"] = item is not None
        import nukescripts
        R["panel_registered"] = any("st_roto.objects" in str(k) for k in getattr(nukescripts.panels, "__panels", {}).keys()) \
            if hasattr(nukescripts.panels, "__panels") else None
        if item is not None:
            item.invoke()                                           # same as clicking the menu entry
            g = [n for n in nuke.allNodes("Group") if "stroto_project" in n.knobs()]
            R["created_st_roto"] = len(g)
            R["status"] = g[0]["stroto_status"].value() if g else None
        import st_roto_nuke.panel as p
        w = p.ObjectPanel()
        R["panel_widget_ok"] = w is not None
    except Exception:
        R["error"] = traceback.format_exc()
    R["passed"] = bool(R.get("menu_item") and R.get("created_st_roto") == 1 and R.get("panel_widget_ok"))
    os.makedirs(OUT, exist_ok=True)
    json.dump(R, open(os.path.join(OUT, "gui_plugin_smoke.json"), "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(3000, run)
QtCore.QTimer.singleShot(60000, lambda: os._exit(1))
