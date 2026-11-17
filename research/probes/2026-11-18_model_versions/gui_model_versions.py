"""T-114 GUI: the ST-ROTO Models panel's versions table in INTERACTIVE Nuke, with a small fake approved model in a
temporary user location (real models are not moved): 2 versions listed, 'Use this version' switches, 'Roll back'
returns, 'Remove version' deletes the archived one. Writes result_gui_model_versions.json.
Run: Nuke17.1.exe --nc research/probes/2026-11-18_model_versions/gui_model_versions.py"""
import json, os, shutil, sys, tempfile, traceback
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


def staged(root, payload, name="fake-model"):
    from st_roto_ai import registry as reg
    os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
    os.makedirs(os.path.join(root, "onnx", name, "video"), exist_ok=True)
    json.dump({"name": name, "repo": "test/" + name, "revision": "r1", "licence": "apache-2.0", "approval": "test",
               "files": {}}, open(os.path.join(root, "manifests", name + ".json"), "w"))
    open(os.path.join(root, "onnx", name, "video", "enc.onnx"), "wb").write(payload)
    return reg.build_exports_manifest(name, root, tool="gui test")


def main():
    tmp = tempfile.mkdtemp(prefix="stroto_gui_versions_")
    try:
        from st_roto_nuke import models_ui
        user = os.path.join(tmp, "user"); os.makedirs(user)
        os.environ["ST_ROTO_MODELS_USER"] = user
        staged(os.path.join(tmp, "s1"), b"a" * 2000)
        staged(os.path.join(tmp, "s2"), b"b" * 3000)
        models_ui.import_from(os.path.join(tmp, "s1"), "fake-model")
        models_ui.import_from(os.path.join(tmp, "s2"), "fake-model")
        from st_roto_nuke.model_panel import ModelPanel, COLUMNS
        p = ModelPanel(); p.resize(900, 600); p.show()
        QtCore.QCoreApplication.processEvents()
        vcol = COLUMNS.index("versions")
        idx = [i for i in range(p.table.rowCount()) if p.table.item(i, 0).text() == "fake-model"][0]
        R["versions_column"] = p.table.item(idx, vcol).text()
        p.table.selectRow(idx)
        QtCore.QCoreApplication.processEvents()
        R["version_rows"] = [[p.vtable.item(i, j).text() for j in (0, 1)] for i in range(p.vtable.rowCount())]
        used_before = R["version_rows"][0][0]
        p.vtable.selectRow(1)
        a = p.activate()
        R["activate_info"] = p.info.text()
        R["after_activate"] = [[p.vtable.item(i, j).text() for j in (0, 1)] for i in range(p.vtable.rowCount())]
        r = p.rollback()
        R["rollback_info"] = p.info.text()
        R["after_rollback"] = [[p.vtable.item(i, j).text() for j in (0, 1)] for i in range(p.vtable.rowCount())]
        p.vtable.selectRow(1)
        gone = p.remove_version(confirm=True)
        R["after_remove"] = [[p.vtable.item(i, j).text() for j in (0, 1)] for i in range(p.vtable.rowCount())]
        R["passed"] = (R["versions_column"] == "2" and len(R["version_rows"]) == 2
                       and R["version_rows"][0][1] == "USED" and a is not None and "now using" in R["activate_info"]
                       and R["after_activate"][0][0] != used_before and r is not None
                       and R["after_rollback"][0][0] == used_before and gone is not None
                       and len(R["after_remove"]) == 1)
    except Exception:
        R["error"] = traceback.format_exc()
    finally:
        os.environ.pop("ST_ROTO_MODELS_USER", None)
        shutil.rmtree(tmp, ignore_errors=True)
    json.dump(R, open(HERE + "/result_gui_model_versions.json", "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(90000, lambda: os._exit(1))
