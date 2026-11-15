"""GUI integration test of the ST_Roto Track button on the REAL background path (worker thread + main-thread
marshalling), with UI responsiveness measured while tracking.
Run (GUI): Nuke17.1.exe --nc tests/nuke/gui_track_slice.py   -> tests/nuke/out/gui_track_slice.json, then exits.
"""
import json, os, sys, tempfile, time, traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                           # noqa: E402
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

OUT = ROOT + "/tests/nuke/out"
VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"
R = {"nuke": nuke.NUKE_VERSION_STRING, "gui": bool(nuke.GUI)}
ticks = []


def finish():
    try:                                  # record state even when we got here by timeout
        job = getattr(main, "job", None)
        if job is not None:
            R.setdefault("job_status", job.status)
            R.setdefault("job_progress", round(job.progress, 3))
            R.setdefault("job_message", job.message)
            R.setdefault("error", job.error)
            R.setdefault("applied", job.applied)
            R.setdefault("apply_error", getattr(job, "apply_error", None))
            R.setdefault("status_knob", main.g["stroto_status"].value())
    except Exception:
        R["finish_state_error"] = traceback.format_exc()
    try:
        import numpy as np
        g = np.diff(ticks) * 1000 if len(ticks) > 2 else np.array([0.0])
        R["ui_gap_ms_during_track"] = {"mean": round(float(g.mean()), 1), "max": round(float(g.max()), 1),
                                       "over_100ms": int((g > 100).sum()), "ticks": len(ticks)}
    except Exception:
        R["finish_error"] = traceback.format_exc()
    os.makedirs(OUT, exist_ok=True)
    json.dump(R, open(OUT + "/gui_track_slice.json", "w"), indent=1, default=str)
    os._exit(0)


def main():
    try:
        import st_roto_nuke.node as stnode
        meta = json.load(open(VIDEO + "/meta.json"))
        nuke.root()["format"].setValue("HD_720")
        rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=meta["frames"] - 1)
        proj = os.path.join(tempfile.mkdtemp(), "gui.stroto")
        g = stnode.create(rd, proj)
        g["stroto_click"].setValue([meta["click_xy"][0], meta["h"] - meta["click_xy"][1]])
        timer = QtCore.QTimer(); timer.setInterval(16); timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
        timer.start(); main.timer = timer
        t0 = time.time()
        job = stnode.on_track(g, background=True)
        main.job, main.g, main.t0 = job, g, t0

        def poll():
            if job.status in ("running", "pending") or (job.status == "done" and job.applied is None):
                QtCore.QTimer.singleShot(200, poll); return
            R["job_status"] = job.status
            R["error"] = job.error
            R["status_knob"] = g["stroto_status"].value()
            R["seconds"] = round(time.time() - t0, 1)
            if True:
                roto = stnode._INNER[g.fullName()]["roto"]          # cached reference: no extra node access
                layer = roto["curves"].rootLayer
                R["shapes_in_roto"] = len(layer)
                if len(layer):
                    R["keys_on_point0"] = len(list(layer[0][0].center.getControlPointKeyTimes()))
            R["passed"] = (job.status == "done" and R.get("keys_on_point0") == meta["frames"])
            QtCore.QTimer.singleShot(500, finish)
        QtCore.QTimer.singleShot(200, poll)
    except Exception:
        R["main_error"] = traceback.format_exc()
        finish()


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(180000, finish)
