"""T-102: the Objects pane timeline in INTERACTIVE Nuke. An object with AI keys 0-9, an artist key on 4, locked 6-7,
and an absent frame 8 between present frames (REVIEW lost); the timeline is grabbed as an image and the colours at
those frames are checked; a click on frame 7 must move Nuke to frame 7 and select the row.
Run: Nuke17.1.exe --nc research/probes/2026-11-17_timeline/gui_timeline.py -> result_gui_timeline.json"""
import json, os, sys, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                           # noqa: E402
import numpy as np                                    # noqa: E402
try:
    from PySide6 import QtCore, QtGui
except ImportError:
    from PySide2 import QtCore, QtGui
R = {"gui": bool(nuke.GUI)}
VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"


def colour_at(img, x, y):
    s = img.devicePixelRatio()                       # grab() renders at the screen's scaling (HiDPI)
    c = QtGui.QColor(img.pixel(int(x * s), int(y * s)))
    return (c.red(), c.green(), c.blue())


def main():
    try:
        import st_roto_nuke.node as n
        from st_roto_nuke import session
        from st_roto_nuke.panel import ObjectPanel, TIMELINE_COLOURS
        from st_roto import model as m
        from st_roto.geometry import mask_to_points
        rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=9)
        proj = os.path.join(tempfile.mkdtemp(), "tl.stroto")
        g = n.create(rd, proj)
        store, bus = session.project(proj)
        bus.execute({"op": "create_shot", "row": {"id": "S", "name": rd.name(), "width": 1280, "height": 720,
                                                  "first_frame": 0, "last_frame": 9}})
        bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
        bus.execute({"op": "create_shape", "row": {"id": "Os", "object_id": "O", "name": "hero", "point_count": 12,
                                                   "generator": json.dumps({"locked_frames": [6, 7]})}})
        yy, xx = np.mgrid[0:720, 0:1280] + 0.5
        for f in range(10):
            if f == 8:
                continue
            pts = mask_to_points(60 - np.hypot(xx - 300 - 10 * f, yy - 300), count=12)
            bus.execute({"op": "set_key", "shape_id": "Os", "frame": f, "points": pts},
                        actor=m.ACTOR_ARTIST if f == 4 else m.ACTOR_AI)
            bus.execute({"op": "set_report", "shape_id": "Os", "frame": f, "object_score": 5.0, "iou_pred": 0.95})
        bus.execute({"op": "set_report", "shape_id": "Os", "frame": 8, "object_score": -4.0, "iou_pred": 0.1})
        p = ObjectPanel(); p.resize(700, 400); p.show()
        p.set_group(g)
        tl = p.timeline
        R["timeline_rows"] = [r["name"] for r in tl.rows]
        QtCore.QCoreApplication.processEvents()
        img = tl.grab().toImage()
        R["device_pixel_ratio"] = img.devicePixelRatio()
        R["image_size"] = [img.width(), img.height()]
        R["widget_size"] = [tl.width(), tl.height()]
        y_key = tl.ROW_H // 2
        R["colour_ai_f0"] = colour_at(img, tl.x_of(0), y_key)
        R["colour_artist_f4"] = colour_at(img, tl.x_of(4), y_key)
        R["colour_locked_f6_edge"] = colour_at(img, tl.x_of(6) + 1.5, 3)
        R["colour_flag_f8"] = colour_at(img, tl.x_of(8), tl.ROW_H - 4)
        nuke.frame(0)
        x7 = tl.x_of(7)
        ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(x7, y_key), QtCore.QPointF(x7, y_key),
                               QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        tl.mousePressEvent(ev)
        R["frame_after_click"] = int(nuke.frame())
        R["selected_row"] = p.table.currentRow()
        C = TIMELINE_COLOURS
        R["passed"] = (R["timeline_rows"] == ["hero"] and R["colour_ai_f0"] == C["ai"]
                       and R["colour_artist_f4"] == C["artist"] and R["colour_locked_f6_edge"] == C["locked"]
                       and R["colour_flag_f8"] in (C["lost"], C["check"]) and R["frame_after_click"] == 7
                       and R["selected_row"] == 0)
    except Exception:
        R["error"] = traceback.format_exc()
    json.dump(R, open(HERE + "/result_gui_timeline.json", "w"), indent=1)
    os._exit(0)


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(90000, lambda: os._exit(1))
