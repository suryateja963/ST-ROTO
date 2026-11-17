"""T-111 GUI probe (INTERACTIVE Nuke 17.1 NC): what can show review state IN the viewer from Python?
  1. which callback fires when the frame changes (knobChanged on Viewer nodes / updateUI / nuke.frame());
  2. ViewerWindow.showStatusMessage: visible in the viewer? (viewer widget grabbed before / after; pixel difference);
  3. Roto shape overlay colour (ro/go/bo/ao, keyed per frame): does the outline in the viewer take the colour? Inner
     Roto panel open; viewer grabbed with magenta keyed vs green keyed; count magenta / green pixels.
Run: Nuke17.1.exe --nc research/probes/2026-11-18_overlay/gui_overlay.py -> result_gui_overlay.json (+ PNGs), exits."""
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
CALLS = {"viewer_knob": [], "update_ui": 0}


def on_viewer_knob():
    k = nuke.thisKnob()
    CALLS["viewer_knob"].append(k.name() if k else None)


def on_update_ui():
    CALLS["update_ui"] += 1


def gl_widgets():
    out = []
    for w in QtWidgets.QApplication.allWidgets():
        cn = type(w).__name__ + " " + w.metaObject().className()
        if ("GL" in cn or "Viewer" in cn) and w.isVisible() and w.width() > 300 and w.height() > 200:
            out.append(w)
    return out


def grab(w, name):
    QtCore.QCoreApplication.processEvents()
    tl = w.mapToGlobal(QtCore.QPoint(0, 0))            # OpenGL content is not in widget.grab(): capture the screen
    scr = w.screen() if hasattr(w, "screen") else QtGui.QGuiApplication.primaryScreen()
    img = scr.grabWindow(0, tl.x() - scr.geometry().x(), tl.y() - scr.geometry().y(), w.width(), w.height()).toImage()
    img = img.convertToFormat(QtGui.QImage.Format_RGB888)
    img.save(OUT + "/" + name + ".png")
    ptr = img.constBits()
    a = np.frombuffer(ptr, np.uint8, img.sizeInBytes()).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 3]
    return a.reshape(img.height(), img.width(), 3).astype(int)


def count(a, rgb):
    r, g, b = rgb
    return int(((np.abs(a[..., 0] - r) < 50) & (np.abs(a[..., 1] - g) < 50) & (np.abs(a[..., 2] - b) < 50)).sum())


def step(fn, delay=600):
    QtCore.QTimer.singleShot(delay, fn)


def main():
    try:
        import nuke.rotopaint as rp
        import st_roto_nuke.node as n
        from st_roto_nuke import session
        from st_roto_nuke.roto_export import sync_shot
        from st_roto.geometry import mask_to_points
        rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=9)
        proj = os.path.join(tempfile.mkdtemp(), "ov.stroto")
        g = n.create(rd, proj)
        store, bus = session.project(proj)
        bus.execute({"op": "create_shot", "row": {"id": "S", "name": rd.name(), "width": 1280, "height": 720,
                                                  "first_frame": 0, "last_frame": 9}})
        bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
        bus.execute({"op": "create_shape", "row": {"id": "Os", "object_id": "O", "name": "hero", "point_count": 12}})
        yy, xx = np.mgrid[0:720, 0:1280] + 0.5
        for f in range(10):
            bus.execute({"op": "set_key", "shape_id": "Os", "frame": f,
                         "points": mask_to_points(150 - np.hypot(xx - 640, yy - 360), count=12)})
        roto = n._inner(g, "roto", "STROTO_shapes")
        sync_shot(store, "S", roto["curves"], 720)
        R["shapes"] = [s.name for s in roto["curves"].rootLayer]
        nuke.addKnobChanged(on_viewer_knob, nodeClass="Viewer")
        nuke.addUpdateUI(on_update_ui)
        v = nuke.activeViewer()
        R["active_viewer_before"] = str(v)
        nuke.connectViewer(0, g)
        roto.showControlPanel()
        nuke.frame(2)
        state = {"g": g, "roto": roto}
        step(lambda: phase2(state), 1500)
    except Exception:
        R["error"] = traceback.format_exc()
        finish()


def phase2(state):
    try:
        v = nuke.activeViewer()
        R["active_viewer"] = str(v)
        R["viewer_window_methods"] = [m for m in dir(v) if "tatus" in m or "rame" in m] if v else None
        ws = gl_widgets()
        R["gl_widgets"] = [(type(w).__name__, w.metaObject().className(), w.width(), w.height()) for w in ws]
        state["w"] = max(ws, key=lambda w: w.width() * w.height()) if ws else None
        CALLS["viewer_knob"].clear(); CALLS["update_ui"] = 0
        nuke.frame(5)
        QtCore.QCoreApplication.processEvents()
        R["after_nuke_frame_5"] = {"viewer_knobs": list(CALLS["viewer_knob"]), "update_ui": CALLS["update_ui"]}
        if state["w"] is not None:
            state["before_msg"] = grab(state["w"], "before_msg")
        R["get_status_message"] = str(v.getStatusMessage()) if v is not None else None
        step(lambda: phase3(state))
    except Exception:
        R["error"] = traceback.format_exc()
        finish()


def phase3(state):
    try:
        R["callbacks_600ms_after_frame_5"] = {"viewer_knobs": list(CALLS["viewer_knob"]), "update_ui": CALLS["update_ui"]}
        # overlay colours: key the shape magenta on frame 5
        s = list(state["roto"]["curves"].rootLayer)[0]
        a = s.getAttributes()
        for nm, val in (("ro", 1.0), ("go", 0.0), ("bo", 1.0), ("ao", 1.0)):
            a.set(5, nm, val)
        state["roto"]["curves"].changed()
        step(lambda: phase4(state))
    except Exception:
        R["error"] = traceback.format_exc()
        finish()


def phase4(state):
    try:
        w = state["w"]
        if w is not None:
            img = grab(w, "overlay_magenta")
            R["magenta_pixels"] = count(img, (255, 0, 255))
            R["green_pixels_when_magenta"] = count(img, (0, 255, 0))
        s = list(state["roto"]["curves"].rootLayer)[0]
        a = s.getAttributes()
        for nm, val in (("ro", 0.0), ("go", 1.0), ("bo", 0.0), ("ao", 1.0)):
            a.set(5, nm, val)
        state["roto"]["curves"].changed()
        step(lambda: phase5(state))
    except Exception:
        R["error"] = traceback.format_exc()
        finish()


def phase5(state):
    try:
        w = state["w"]
        if w is not None:
            img = grab(w, "overlay_green")
            R["magenta_pixels_when_green"] = count(img, (255, 0, 255))
            R["green_pixels"] = count(img, (0, 255, 0))
        # overlay alpha 0 with a magenta colour keyed: default outline colour expected (no magenta)
        s_ = list(state["roto"]["curves"].rootLayer)[0]
        a = s_.getAttributes()
        for nm, val in (("ro", 1.0), ("go", 0.0), ("bo", 1.0), ("ao", 0.0)):
            a.set(5, nm, val)
        state["roto"]["curves"].changed()
        step(lambda: phase6(state))
    except Exception:
        R["error"] = traceback.format_exc()
        finish()


def phase6(state):
    try:
        w = state["w"]
        if w is not None:
            img = grab(w, "overlay_ao0")
            R["magenta_pixels_ao0"] = count(img, (255, 0, 255))
    except Exception:
        R["error"] = traceback.format_exc()
    finish()


def finish():
    R["calls_total"] = {"viewer_knob": CALLS["viewer_knob"][:20], "update_ui": CALLS["update_ui"]}
    json.dump(R, open(HERE + "/result_gui_overlay.json", "w"), indent=1, default=str)
    os._exit(0)


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(90000, lambda: os._exit(1))
