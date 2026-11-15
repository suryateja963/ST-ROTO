"""Interactive-GUI probe (R-37 / ADR-0009): ORT CUDA work on a worker thread inside the Nuke GUI.

Run (GUI, not -t):  Nuke17.1.exe --nc probe_gui_threading.py
Measures:
  * main-thread responsiveness: a 16 ms QTimer records the real gap between ticks, baseline vs during the job;
  * worker-thread ORT CUDA encoder timings (SAM 2.1 tiny), vs the same run on the main thread for comparison;
  * marshalling a result to the main thread (nuke.executeInMainThreadWithResult) to create a Roto shape;
  * cooperative cancellation latency.
Writes result.json next to this file, then exits Nuke without saving (os._exit).
"""
import json, os, sys, threading, time, traceback

import nuke
import nuke.rotopaint as rp

ROOT = "D:/ST-ROTO"
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np                      # noqa: E402
import onnxruntime as ort               # noqa: E402

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:                     # older Nuke
    from PySide2 import QtCore, QtWidgets

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
R = {"nuke": nuke.NUKE_VERSION_STRING, "gui": bool(nuke.GUI), "nc": bool(nuke.env.get("nc")), "phases": {}}
MODEL = ROOT + "/models/onnx/sam2.1-hiera-tiny/video/vencoder.onnx"
ticks = []
phase = {"name": "startup"}


def on_tick():
    ticks.append((phase["name"], time.perf_counter()))


def gap_stats(name):
    t = [x[1] for x in ticks if x[0] == name]
    if len(t) < 3:
        return None
    g = np.diff(t) * 1000
    return {"ticks": len(t), "gap_ms_mean": round(float(g.mean()), 1), "gap_ms_p99": round(float(np.percentile(g, 99)), 1),
            "gap_ms_max": round(float(g.max()), 1), "gaps_over_100ms": int((g > 100).sum())}


def finish():
    try:
        for name in ("baseline", "worker_job", "main_thread_job", "after"):
            R["phases"][name] = gap_stats(name)
    except Exception:
        R["finish_error"] = traceback.format_exc()
    with open(HERE + "/result.json", "w") as fh:
        json.dump(R, fh, indent=1)
    os._exit(0)                          # leave Nuke without save prompts


def main():
    try:
        timer = QtCore.QTimer()
        timer.setInterval(16)
        timer.timeout.connect(on_tick)
        timer.start()
        R["_timer"] = None
        main.timer = timer

        so = ort.SessionOptions(); so.log_severity_level = 3
        sess = ort.InferenceSession(MODEL, so, providers=[("CUDAExecutionProvider", {}), "CPUExecutionProvider"])
        R["providers"] = sess.get_providers()
        x = np.random.default_rng(0).standard_normal((1, 3, 1024, 1024)).astype(np.float32)
        sess.run(None, {"pixel_values": x})                      # warm-up (first call is slow)

        state = {"times": [], "cancel": False, "cancel_at": None, "stopped_at": None, "error": None}

        def worker():
            try:
                for i in range(40):
                    if state["cancel"]:
                        state["stopped_at"] = time.perf_counter(); return
                    t = time.perf_counter(); sess.run(None, {"pixel_values": x}); state["times"].append(time.perf_counter() - t)
                # hand a result to the main thread: create a native Roto shape there
                def make_shape():
                    roto = nuke.nodes.Roto()
                    sh = rp.Shape(roto["curves"])
                    for px, py in ((100.0, 100.0), (400.0, 100.0), (250.0, 350.0)):
                        sh.append(rp.ShapeControlPoint(px, py))
                    roto["curves"].rootLayer.append(sh)
                    return threading.current_thread() is threading.main_thread(), len(sh)
                R["marshal_result_(on_main_thread,points)"] = nuke.executeInMainThreadWithResult(make_shape)
            except Exception:
                state["error"] = traceback.format_exc()

        def stage_baseline():
            phase["name"] = "baseline"
            QtCore.QTimer.singleShot(2000, stage_worker)

        def stage_worker():
            phase["name"] = "worker_job"
            th = threading.Thread(target=worker, daemon=True)
            main.th = th; th.start()
            QtCore.QTimer.singleShot(200, wait_worker)

        def wait_worker():
            if main.th.is_alive():
                QtCore.QTimer.singleShot(100, wait_worker); return
            R["worker"] = {"runs": len(state["times"]), "ms_mean": round(1000 * float(np.mean(state["times"])), 1),
                           "error": state["error"]}
            stage_main_thread()

        def stage_main_thread():
            # same work ON the main thread, to show what blocking would look like
            phase["name"] = "main_thread_job"
            t0 = time.perf_counter()
            for _ in range(10):
                sess.run(None, {"pixel_values": x})
                QtWidgets.QApplication.processEvents()
            R["main_thread_10_runs_s"] = round(time.perf_counter() - t0, 2)
            stage_cancel()

        def stage_cancel():
            phase["name"] = "after"
            state.update({"cancel": False, "times": [], "stopped_at": None})
            th = threading.Thread(target=worker, daemon=True); th.start()
            def do_cancel():
                state["cancel"] = True; state["cancel_at"] = time.perf_counter()
                th.join(10)
                R["cancel"] = {"latency_ms": round(1000 * (state["stopped_at"] - state["cancel_at"]), 1) if state["stopped_at"] else None,
                               "runs_before_cancel": len(state["times"])}
                QtCore.QTimer.singleShot(1500, finish)
            QtCore.QTimer.singleShot(1000, do_cancel)

        QtCore.QTimer.singleShot(500, stage_baseline)
    except Exception:
        R["main_error"] = traceback.format_exc()
        finish()


# Start once the GUI event loop is running.
QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(240000, finish)     # hard stop after 4 minutes whatever happens
