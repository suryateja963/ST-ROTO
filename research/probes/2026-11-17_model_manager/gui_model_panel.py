"""T-101: the ST-ROTO Models panel in INTERACTIVE Nuke: rows, select tiny, Verify; writes result_gui_model_panel.json.
Run: Nuke17.1.exe --nc research/probes/2026-11-17_model_manager/gui_model_panel.py"""
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
R = {"gui": bool(nuke.GUI)}


def main():
    try:
        from st_roto_nuke.model_panel import ModelPanel, COLUMNS
        p = ModelPanel(); p.show()
        R["rows"] = [[p.table.item(i, j).text() for j in range(4)] for i in range(p.table.rowCount())]
        idx = [i for i in range(p.table.rowCount()) if p.table.item(i, 0).text() == "sam2.1-hiera-tiny"][0]
        p.table.selectRow(idx)
        res = p.verify()
        R["verify_info"] = p.info.text()
        R["passed"] = bool(res and res["ok"] and "all files verified" in R["verify_info"] and len(R["rows"]) >= 3
                           and COLUMNS[0] == "model")
    except Exception:
        R["error"] = traceback.format_exc()
    json.dump(R, open(HERE + "/result_gui_model_panel.json", "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(90000, lambda: os._exit(1))
