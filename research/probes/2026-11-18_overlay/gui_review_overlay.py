"""T-111 GUI test of the PRODUCT path (interactive Nuke 17.1 NC): an object lost on frame 4 and checked on frame 7;
'Show shapes in viewer' (st_roto_nuke.node.on_show_shapes) -> the viewer (screen capture) shows a MAGENTA outline
on frame 4, YELLOW on frame 7, neither on frame 2; the node's 'this frame' readout follows the viewer's frame
(Viewer knobChanged callback).
Run: Nuke17.1.exe --nc research/probes/2026-11-18_overlay/gui_review_overlay.py -> result_gui_review_overlay.json"""
import json, os, sys, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                           # noqa: E402
import numpy as np                                    # noqa: E402
try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
R = {"gui": bool(nuke.GUI)}
VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
MAGENTA, YELLOW = (255, 0, 255), (255, 217, 0)
S = {}


def viewer_widget():
    ws = [w for w in QtWidgets.QApplication.allWidgets()
          if w.metaObject().className() == "Viewer_Window" and w.isVisible()]
    return max(ws, key=lambda w: w.width() * w.height()) if ws else None


def grab(name):
    w = viewer_widget()
    QtCore.QCoreApplication.processEvents()
    tl = w.mapToGlobal(QtCore.QPoint(0, 0))
    scr = w.screen() if hasattr(w, "screen") else QtGui.QGuiApplication.primaryScreen()
    img = scr.grabWindow(0, tl.x() - scr.geometry().x(), tl.y() - scr.geometry().y(), w.width(), w.height()).toImage()
    img = img.convertToFormat(QtGui.QImage.Format_RGB888)
    img.save(OUT + "/review_" + name + ".png")
    a = np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes()).reshape(img.height(), img.bytesPerLine())
    a = a[:, :img.width() * 3].reshape(img.height(), img.width(), 3).astype(int)
    return a


def count(a, rgb, tol=45):
    return int(np.all(np.abs(a - np.array(rgb)) < tol, axis=-1).sum())


def later(fn, ms=900):
    def run():
        try:
            fn()
        except Exception:
            R["error"] = traceback.format_exc()
            finish()
    QtCore.QTimer.singleShot(ms, run)


def main():
    import st_roto_nuke.node as n
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import sync_shot
    from st_roto import model as m
    from st_roto.geometry import mask_to_points
    OID, SID = "0a0b0c0d" + "0" * 24, "1a2b3c4d" + "0" * 24
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=9)
    proj = os.path.join(tempfile.mkdtemp(), "rv.stroto")
    g = n.create(rd, proj)
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": rd.name(), "width": 1280, "height": 720,
                                              "first_frame": 0, "last_frame": 9}})
    bus.execute({"op": "create_object", "row": {"id": OID, "shot_id": "S", "name": "hero"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": SID, "object_id": OID, "name": "hero", "point_count": 12}},
                actor=m.ACTOR_AI)
    yy, xx = np.mgrid[0:720, 0:1280] + 0.5
    for f in range(10):
        bus.execute({"op": "set_key", "shape_id": SID, "frame": f,
                     "points": mask_to_points(170 - np.hypot(xx - 640, yy - 360), count=12)}, actor=m.ACTOR_AI)
        bus.execute({"op": "set_report", "shape_id": SID, "frame": f, "object_score": 5.0, "iou_pred": 0.95})
    bus.execute({"op": "set_channel_report", "object_id": OID, "frame": 4, "data": {"crypto_iou": 0.2}})
    bus.execute({"op": "set_channel_report", "object_id": OID, "frame": 7, "data": {"crypto_iou": 0.3}})
    # frame 4 also LOST: absent between present frames (object score negative there, key removed)
    bus.execute({"op": "delete_key", "shape_id": SID, "frame": 4}, actor=m.ACTOR_AI)
    bus.execute({"op": "set_report", "shape_id": SID, "frame": 4, "object_score": -5.0, "iou_pred": 0.1})
    roto = n._inner(g, "roto", "STROTO_shapes")
    sync_shot(store, "S", roto["curves"], 720)
    S["g"] = g
    nuke.connectViewer(0, g)
    n.on_show_shapes(g)
    R["status_after_show"] = g["stroto_status"].value()
    nuke.frame(2)
    later(step_f2, 1800)


def step_f2():
    a = grab("f2")
    R["f2"] = {"magenta": count(a, MAGENTA), "yellow": count(a, YELLOW), "this_frame": S["g"]["stroto_this_frame"].value()}
    nuke.frame(4)
    later(step_f4)


def step_f4():
    a = grab("f4")
    R["f4"] = {"magenta": count(a, MAGENTA), "yellow": count(a, YELLOW), "this_frame": S["g"]["stroto_this_frame"].value()}
    nuke.frame(7)
    later(step_f7)


def step_f7():
    a = grab("f7")
    R["f7"] = {"magenta": count(a, MAGENTA), "yellow": count(a, YELLOW), "this_frame": S["g"]["stroto_this_frame"].value()}
    # yellow baseline: the NC start-up dialog's warning icon is on screen too -> compare with frame 2
    R["passed"] = (R["f4"]["magenta"] > 50 and R["f7"]["yellow"] - R["f2"]["yellow"] > 80 and R["f2"]["magenta"] < 10
                   and abs(R["f4"]["yellow"] - R["f2"]["yellow"]) < 40 and R["f7"]["magenta"] < 10
                   and "LOST" in R["f4"]["this_frame"] and "CHECK" in R["f7"]["this_frame"]
                   and "no flags" in R["f2"]["this_frame"])
    finish()


def finish():
    json.dump(R, open(HERE + "/result_gui_review_overlay.json", "w"), indent=1, default=str)
    os._exit(0)


def start():
    try:
        main()
    except Exception:
        R["error"] = traceback.format_exc()
        finish()


QtCore.QTimer.singleShot(3000, start)
QtCore.QTimer.singleShot(120000, lambda: os._exit(1))
