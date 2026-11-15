"""Headless Nuke integration tests. Run:  Nuke17.1.exe --nc -t tests/nuke/run_nuke_tests.py
Writes tests/nuke/out/results.json and exits non-zero on failure. Stays under the Non-commercial 10-node cap.

test_export_animated_shape: an analytic ellipse moving/rotating over frames -2..5 is traced (sub-pixel marching
squares), fitted with a fixed-count spline, stored through the command bus, exported with st_roto_nuke.roto_export,
rendered by Nuke, and compared per frame with (a) an exact pixel-centre rasterisation of the same stored spline and
(b) the analytic ellipse. (a) checks the export conventions; (b) checks the whole mask -> shape -> Nuke chain.
"""
import json, os, sys, tempfile, traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                               # noqa: E402
import numpy as np                                        # noqa: E402
import cv2                                                # noqa: E402

from st_roto.commands import CommandBus                   # noqa: E402
from st_roto.store import ProjectStore                    # noqa: E402
from st_roto.geometry import Anchor, fit_fixed_count, rasterize_spline, trace_contours   # noqa: E402
from st_roto_nuke.roto_export import export_shape         # noqa: E402

OUT = ROOT + "/tests/nuke/out"
os.makedirs(OUT, exist_ok=True)
W, H, K = 1280, 720, 16
FRAMES = list(range(-2, 6))                               # includes negative frames (master prompt section 11)


def ellipse_field(f):
    """Signed (approximately) distance-like field of a rotated ellipse, evaluated at pixel centres."""
    cx, cy, ax, ay, ang = 400 + 60 * f, 360 - 10 * f, 260.0, 140.0, np.radians(12 * f)
    yy, xx = np.mgrid[0:H, 0:W]
    x, y = xx + 0.5 - cx, yy + 0.5 - cy
    u = x * np.cos(ang) + y * np.sin(ang)
    v = -x * np.sin(ang) + y * np.cos(ang)
    return 1.0 - np.sqrt((u / ax) ** 2 + (v / ay) ** 2)


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def frame_file(f):
    return OUT + ("/export.%04d.tif" % f if f >= 0 else "/export.-%03d.tif" % (-f))   # Nuke: sign + 3 digits


def test_export_animated_shape(res):
    tmp = tempfile.mkdtemp()
    store = ProjectStore(os.path.join(tmp, "t.stroto"))
    bus = CommandBus(store)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh", "width": W, "height": H}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "ellipse"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "ellipse main", "point_count": K}})
    prev, stored, truth = None, {}, {}
    for f in FRAMES:
        field = ellipse_field(f)
        truth[f] = field > 0
        loop = max(trace_contours(truth[f].astype(float) - 0.5), key=len)      # from the binary mask, like AI output
        a = fit_fixed_count(loop, K, start_hint=None if prev is None else prev[0].p)
        prev = a
        stored[f] = [[float(x.p[0]), float(x.p[1]), float(x.h_in[0]), float(x.h_in[1]),
                      float(x.h_out[0]), float(x.h_out[1])] for x in a]
        bus.execute({"op": "set_key", "shape_id": "P", "frame": f, "points": stored[f]})
    nuke.root()["format"].setValue("HD_720")
    roto = nuke.nodes.Roto(output="alpha")
    shape = export_shape(store, "P", roto["curves"], H)
    w = nuke.nodes.Write(file=OUT + "/export.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, roto)
    nuke.execute(w, FRAMES[0], FRAMES[-1])
    per = {}
    for f in FRAMES:
        img = cv2.imread(frame_file(f), cv2.IMREAD_UNCHANGED)
        if img is None:
            per[f] = {"error": "render missing: " + frame_file(f)}; continue
        r = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        anchors = [Anchor(p=np.array(p[0:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:6]), corner=False) for p in stored[f]]
        per[f] = {"iou_vs_exact_raster_of_stored_spline": round(iou(r, rasterize_spline(anchors, H, W)), 5),
                  "iou_vs_analytic_ellipse": round(iou(r, truth[f]), 5)}
    res["per_frame"] = per
    res["keys_on_point0"] = len(list(shape[0].center.getControlPointKeyTimes()))
    res["thresholds"] = {"vs_exact_raster": 0.998, "vs_analytic": 0.995}
    ok = res["keys_on_point0"] == len(FRAMES) and all(
        "error" not in v and v["iou_vs_exact_raster_of_stored_spline"] > 0.998 and v["iou_vs_analytic_ellipse"] > 0.995
        for v in per.values())
    store.close()
    return ok


VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"


def test_st_roto_node_track_slice(res):
    """Vertical slice through PRODUCT code: ST_Roto node -> Track (synchronous in -t) -> project DB -> native Roto."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated (research/probes/2026-11-15_video/make_synthetic_video.py)"
        return True
    import st_roto_nuke.node as stnode
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], meta["frames"]
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "slice.stroto")
    g = stnode.create(rd, proj)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]])     # canonical -> Nuke y-up
    g["stroto_click_frame"].setValue(0)
    job = stnode.on_track(g, background=False)
    res["status_knob"] = g["stroto_status"].value()
    res["job_status"] = job.status if job else None
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"
        return False
    store = ProjectStore(proj)
    objs = store.conn.execute("SELECT * FROM objects").fetchall()
    shapes = store.conn.execute("SELECT * FROM shapes").fetchall()
    res["db"] = {"objects": len(objs), "shapes": len(shapes),
                 "keys": store.conn.execute("SELECT COUNT(*) FROM shape_keys").fetchone()[0],
                 "origins": sorted(set(r["origin"] for r in store.conn.execute("SELECT origin FROM shape_keys"))),
                 "ops": len(store.operations())}
    store.close()
    w = nuke.nodes.Write(file=OUT + "/slice.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)
    nuke.execute(w, 0, n - 1)
    ious = []
    for f in range(n):
        img = cv2.imread(OUT + "/slice.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        a = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
        ious.append(iou(a, gt))
    res["iou_vs_gt"] = {"mean": round(float(np.mean(ious)), 4), "min": round(float(np.min(ious)), 4),
                        "worst_frame": int(np.argmin(ious)),
                        "mean_excluding_split_frame_23": round(float(np.mean([v for i, v in enumerate(ious) if i != 23])), 4)}
    res["nodes_accessed"] = len(nuke.allNodes())
    return (res["db"]["objects"] == 1 and res["db"]["keys"] == n and res["db"]["origins"] == ["ai_generated"]
            and res["iou_vs_gt"]["mean"] > 0.98)


def test_repeated_tracking_stable(res):
    """Regression for R-41: three full 48-frame tracking runs in one Nuke session must not slow down or exhaust
    GPU memory (before the fix: run 3 was 2.4x slower at 7.8 of 8.15 GB)."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import subprocess, threading, time
    from st_roto_ai.sam2 import Sam2Video
    meta = json.load(open(VIDEO + "/meta.json"))
    frames = [cv2.cvtColor(cv2.imread(VIDEO + "/frame_%04d.png" % i), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
              for i in range(meta["frames"])]
    peak = {"v": 0, "stop": False}

    def sample():
        while not peak["stop"]:
            o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, creationflags=0x08000000).stdout
            peak["v"] = max(peak["v"], int(o.strip() or 0)); time.sleep(0.1)
    threading.Thread(target=sample, daemon=True).start()
    secs = []
    for run in range(3):
        trk = Sam2Video(ROOT + "/models/onnx/sam2.1-hiera-tiny/video", device="cuda", num_total_frames=len(frames))
        t0 = time.time()
        for i, rgb in enumerate(frames):
            enc = trk.encode(rgb)
            trk.add_points(0, enc, [tuple(meta["click_xy"])], [1]) if i == 0 else trk.track(i, enc)
        secs.append(round(time.time() - t0, 2))
    peak["stop"] = True
    res.update({"seconds_per_run": secs, "peak_gpu_MiB": peak["v"], "memattn": trk.memattn_file,
                "limits": {"run3_vs_run2_max_ratio": 1.3, "peak_gpu_MiB_max": 6500}})
    return secs[2] <= 1.3 * secs[1] and peak["v"] <= 6500


TESTS = (test_export_animated_shape, test_st_roto_node_track_slice, test_repeated_tracking_stable)


def main():
    # One test per Nuke process (tools/run_nuke_tests.py): the Non-commercial 10-node Python budget is per session.
    wanted = sys.argv[1:] or [t.__name__ for t in TESTS]
    results, failed = {"nuke": nuke.NUKE_VERSION_STRING, "nc": bool(nuke.env.get("nc"))}, 0
    for t in [t for t in TESTS if t.__name__ in wanted]:
        r = {}
        try:
            ok = t(r)
        except Exception:
            ok = False; r["exception"] = traceback.format_exc()
        r["passed"] = bool(ok); failed += 0 if ok else 1
        results[t.__name__] = r
    results["failed"] = failed
    with open(OUT + "/results_%s.json" % ("_".join(wanted) if len(wanted) == 1 else "all"), "w") as fh:
        json.dump(results, fh, indent=1)
    print("NUKE_TESTS_FAILED=%d" % failed)
    sys.exit(1 if failed else 0)


main()
