"""T-094: the object panel's collaboration controls in INTERACTIVE Nuke (throw-away key folder).
Run: Nuke17.1.exe --nc research/probes/2026-11-17_collab_ui/gui_panel_collab.py -> result_gui_panel_collab.json"""
import json, os, sys, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
os.environ["ST_ROTO_KEY_DIR"] = tempfile.mkdtemp()
os.environ["USERNAME"] = "alice"
import nuke                                           # noqa: E402
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

R = {"nuke": nuke.NUKE_VERSION_STRING, "gui": bool(nuke.GUI)}
VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"


def finish():
    json.dump(R, open(HERE + "/result_gui_panel_collab.json", "w"), indent=1)
    os._exit(0)


def main():
    try:
        import st_roto_nuke.node as n
        from st_roto_nuke import session
        from st_roto_nuke.panel import ObjectPanel, COLUMNS
        rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=2)
        proj = os.path.join(tempfile.mkdtemp(), "p.stroto")
        g = n.create(rd, proj)
        store, bus = session.project(proj)
        bus.execute({"op": "create_shot", "row": {"id": "S", "name": rd.name(), "width": 1280, "height": 720}})
        bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
        p = ObjectPanel()
        p.show()
        p.set_group(g)
        col = COLUMNS.index("held by")
        R["columns"] = COLUMNS
        p.set_role("alice", "admin")
        p.table.selectRow(0)
        R["take_ok"] = p.take()
        R["held_cell"] = p.table.item(0, col).text()
        R["after_take_info"] = p.info.text()
        R["setup_key_ok"] = p.setup_key()
        R["after_key_info"] = p.info.text()
        R["collab_line"] = p.collab_info.text()
        p.table.selectRow(0)
        R["release_ok"] = p.release()
        R["held_cell_after_release"] = p.table.item(0, col).text()
        p._heartbeat()
        from st_roto import leases
        R["presence"] = [x["user"] for x in leases.presence(store.conn)]
        R["passed"] = (R["take_ok"] and R["held_cell"] == "you" and R["setup_key_ok"]
                       and "key registered" in R["collab_line"] and "alice (admin)" in R["collab_line"]
                       and R["release_ok"] and R["held_cell_after_release"] == "" and "alice" in R["presence"])
    except Exception:
        R["error"] = traceback.format_exc()
    finish()


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(60000, finish)
