"""Where do the GUI stalls during ST_Roto tracking come from (R-40)? GUI run, instrumented.
Run: Nuke17.1.exe --nc probe_gui_stalls.py  -> result.json next to this file.
Wraps (monkeypatch, probe only): Sam2Video.__init__/encode/track/add_points (worker thread), pixels.render_frame
(main thread). Records a 16 ms UI timer. Each UI gap > 100 ms is attributed to the events overlapping it.
"""
import json, os, sys, tempfile, threading, time, traceback

ROOT = "D:/ST-ROTO"
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                 # noqa: E402
try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"
EV, ticks, R = [], [], {}


def wrap(cls_or_mod, name, label):
    orig = getattr(cls_or_mod, name)

    def w(*a, **k):
        t0 = time.perf_counter()
        try:
            return orig(*a, **k)
        finally:
            EV.append((label, threading.current_thread().name, t0, time.perf_counter()))
    setattr(cls_or_mod, name, w)


def finish():
    try:
        import numpy as np
        t = np.array(ticks)
        gaps = []
        for i in range(1, len(t)):
            g = t[i] - t[i - 1]
            if g > 0.1:
                s, e = t[i - 1], t[i]
                over = sorted({(lbl, th) for lbl, th, a, b in EV if a < e and b > s})
                gaps.append({"start_s": round(s - T0[0], 3), "gap_ms": round(g * 1000, 1), "overlapping": over})
        R["stalls"] = gaps
        R["events_summary"] = {}
        for lbl, th, a, b in EV:
            d = R["events_summary"].setdefault(lbl, {"thread": th, "n": 0, "max_ms": 0.0, "total_ms": 0.0})
            d["n"] += 1; d["max_ms"] = round(max(d["max_ms"], (b - a) * 1000), 1); d["total_ms"] = round(d["total_ms"] + (b - a) * 1000, 1)
        R["ui_gap_mean_ms"] = round(float(np.diff(t).mean() * 1000), 2) if len(t) > 2 else None
        # per-run breakdown (runs are sequential; attribute events by start time)
        starts = [T0[0] + r["start_s"] for r in R.get("runs", [])] + [float("inf")]
        per = []
        for i in range(len(starts) - 1):
            evs = [(lbl, b - a) for lbl, th, a, b in EV if starts[i] <= a < starts[i + 1]]
            d = {}
            for lbl, dur in evs:
                x = d.setdefault(lbl, {"n": 0, "total_ms": 0.0, "max_ms": 0.0})
                x["n"] += 1; x["total_ms"] = round(x["total_ms"] + dur * 1000, 1); x["max_ms"] = round(max(x["max_ms"], dur * 1000), 1)
            per.append(d)
        R["per_run"] = per
    except Exception:
        R["finish_error"] = traceback.format_exc()
    json.dump(R, open(HERE + "/result_%s.json" % VARIANT, "w"), indent=1, default=str)
    os._exit(0)


VARIANT = os.environ.get("STROTO_PROBE_VARIANT", "baseline")
T0 = [0.0]


def main():
    try:
        import st_roto_ai.sam2 as sam2
        import st_roto_nuke.pixels as px
        import st_roto_nuke.node as stnode
        for n in ("__init__", "encode", "track", "add_points"):
            wrap(sam2.Sam2Video, n, "Sam2Video." + n)
        wrap(px, "render_frame", "render_frame")
        stnode.pixels.render_frame = px.render_frame          # node.py imported the module; patch attribute use
        meta = json.load(open(VIDEO + "/meta.json"))
        nuke.root()["format"].setValue("HD_720")
        rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=meta["frames"] - 1)
        g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "p.stroto"))
        g["stroto_click"].setValue([meta["click_xy"][0], meta["h"] - meta["click_xy"][1]])
        timer = QtCore.QTimer(); timer.setInterval(16); timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
        timer.start(); main.timer = timer
        if os.environ.get("STROTO_PROBE_PRELOAD") == "1":            # press "Load model" before the timer starts
            t = time.perf_counter(); R["preload"] = stnode.on_load_model(g)
            R["preload_wall_s"] = round(time.perf_counter() - t, 2)
        T0[0] = time.perf_counter()
        runs = int(os.environ.get("STROTO_PROBE_RUNS", "1"))
        R["runs"] = []
        state = {"job": stnode.on_track(g, background=True), "n": 1, "t": time.perf_counter()}

        def poll():
            job = state["job"]
            if job.status in ("running", "pending") or (job.status == "done" and job.applied is None):
                QtCore.QTimer.singleShot(100, poll); return
            R["runs"].append({"status": job.status, "applied": job.applied,
                              "error_tail": (job.error or "").strip().splitlines()[-3:],
                              "start_s": round(state["t"] - T0[0], 2), "seconds": round(time.perf_counter() - state["t"], 1)})
            if state["n"] < runs:                      # press Track again in the same Nuke session
                state["n"] += 1; state["t"] = time.perf_counter()
                state["job"] = stnode.on_track(g, background=True)
                QtCore.QTimer.singleShot(100, poll); return
            QtCore.QTimer.singleShot(300, finish)
        QtCore.QTimer.singleShot(100, poll)
    except Exception:
        R["main_error"] = traceback.format_exc(); finish()


QtCore.QTimer.singleShot(3000, main)
QtCore.QTimer.singleShot(180000, finish)
