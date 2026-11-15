"""ONNX + numpy tracker (st_roto_ai.sam2.Sam2Video) on the two reference scenarios, inside Nuke on CUDA.
Run: Nuke17.1.exe --nc -t probe_scenarios_onnx.py <model>
  correction: click frame 0 + ground-truth MASK on frame 24, forward 0..47 (cond frames reuse their outputs)
  reverse:    click frame 47, reverse 46..0
Compares each frame with the PyTorch reference (reference_scenarios.py) and the ground truth.
"""
import json, os, sys, time

ROOT = "D:/ST-ROTO"
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                      # noqa: E402,F401  (host process)
import numpy as np               # noqa: E402
import cv2                       # noqa: E402
from st_roto_ai.sam2 import Sam2Video   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
FR = ROOT + "/research/probes/2026-11-15_video/frames"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny"
meta = json.load(open(FR + "/meta.json")); N, W, H = meta["frames"], meta["w"], meta["h"]
rgb = [cv2.cvtColor(cv2.imread(FR + "/frame_%04d.png" % i), cv2.COLOR_BGR2RGB).astype(np.float32) / 255 for i in range(N)]
gts = [cv2.imread(FR + "/gt_%04d.png" % i, cv2.IMREAD_GRAYSCALE) > 127 for i in range(N)]


def iou(a, b):
    u = (a | b).sum()
    return 1.0 if u == 0 else float((a & b).sum() / u)        # both empty = full agreement


def run(scenario):
    ref = np.load(HERE + "/ref_%s_%s.npz" % (scenario, MODEL))
    trk = Sam2Video(ROOT + "/models/onnx/%s/video" % MODEL, device="cuda", num_total_frames=N,
                    memattn_file=os.environ.get("STROTO_MEMATTN"))
    outs, t0 = {}, time.time()
    if scenario == "correction":
        outs[0] = trk.add_points(0, trk.encode(rgb[0]), [tuple(meta["click_xy"])], [1])
        outs[24] = trk.add_mask(24, trk.encode(rgb[24]), gts[24])
        order, reverse = range(0, N), False
    else:
        outs[47] = trk.add_points(47, trk.encode(rgb[47]), [tuple(meta["objects"]["47"]["target_center"])], [1])
        order, reverse = range(N - 1, -1, -1), True
    for f in order:
        if f in trk.cond:
            continue
        outs[f] = trk.track(f, trk.encode(rgb[f]), reverse=reverse)
    secs = time.time() - t0
    rows = []
    for f in sorted(outs):
        m = outs[f]["logits"] > 0
        mr = cv2.resize(ref["f%04d" % f].astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR) > 0
        rows.append({"frame": f, "iou_vs_torch": round(iou(m, mr), 5), "iou_vs_gt": round(iou(m, gts[f]), 4),
                     "px_onnx": int(m.sum()), "px_torch": int(mr.sum()), "px_gt": int(gts[f].sum())})
    v = [r["iou_vs_torch"] for r in rows]; g = [r["iou_vs_gt"] for r in rows]
    return {"frames": len(rows), "seconds": round(secs, 1), "device": trk.report.active,
            "iou_vs_torch_min": min(v), "iou_vs_torch_mean": round(float(np.mean(v)), 5),
            "iou_vs_gt_mean": round(float(np.mean(g)), 4), "iou_vs_gt_min": min(g),
            "worst_vs_torch": sorted(rows, key=lambda r: r["iou_vs_torch"])[:3],
            "frames_object_lost_torch": [r["frame"] for r in rows if r["px_torch"] == 0],
            "frames_object_lost_onnx": [r["frame"] for r in rows if r["px_onnx"] == 0]}


R = {"model": MODEL, "correction": run("correction"), "reverse": run("reverse")}
R["memattn"] = os.environ.get("STROTO_MEMATTN") or "default (fp16 if present)"
json.dump(R, open(HERE + "/onnx_scenarios_%s%s.json" % (MODEL, "_" + os.environ["STROTO_MEMATTN"].split(".")[0] if os.environ.get("STROTO_MEMATTN") else ""), "w"), indent=1)
print("DONE")
