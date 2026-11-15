"""Validate the ONNX + numpy SAM 2.1 video tracker against the PyTorch reference, frame by frame (CPU).
Same pixel values as the reference (official video processor), so differences come only from the port.
Usage: .venv\\Scripts\\python.exe research/probes/2026-11-15_video/validate_onnx_tracker.py sam2.1-hiera-tiny
"""
import json, os, sys, time
import numpy as np
import cv2
import torch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home"); os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.append(os.path.join(ROOT, "prototypes", "tracking"))
from transformers import Sam2VideoProcessor          # noqa: E402
from sam2_video_onnx import Sam2VideoTracker          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)); FR = os.path.join(HERE, "frames")


def up(low, h, w):
    return cv2.resize(low[0, 0].astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR) > 0


def main(name):
    meta = json.load(open(os.path.join(FR, "meta.json"))); n, H, W = meta["frames"], meta["h"], meta["w"]
    frames = [cv2.cvtColor(cv2.imread(os.path.join(FR, "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB) for i in range(n)]
    gts = [cv2.imread(os.path.join(FR, "gt_%04d.png" % i), cv2.IMREAD_GRAYSCALE) > 127 for i in range(n)]
    proc = Sam2VideoProcessor.from_pretrained(os.path.join(ROOT, "models", "weights", name))
    px = proc.video_processor(videos=frames, return_tensors="pt").pixel_values_videos[0].numpy()
    ref = np.load(os.path.join(HERE, f"ref_logits_{name}.npz"))
    trk = Sam2VideoTracker(os.path.join(ROOT, "models", "onnx", name, "video"), num_total_frames=n)
    cx, cy = meta["click_xy"]
    pts = np.array([[cx * 1024 / W, cy * 1024 / H]], np.float32)
    rows, t0 = [], time.time()
    for f in range(n):
        enc = trk.encode(px[f:f + 1])
        out = trk.add_points(0, enc, pts, np.array([1], np.int32)) if f == 0 else trk.track(f, enc)
        low = out["low_res"]
        r = ref["f%04d" % f].astype(np.float32)[None, None]
        m, mr = up(low, H, W), up(r, H, W)
        rows.append({"frame": f, "logit_maxdiff": round(float(np.abs(low - r).max()), 4),
                     "iou_vs_torch": round(float((m & mr).sum() / max(1, (m | mr).sum())), 5),
                     "iou_vs_gt": round(float((m & gts[f]).sum() / max(1, (m | gts[f]).sum())), 4)})
    res = {"model": name, "providers": trk.providers, "s_per_frame_cpu": round((time.time() - t0) / n, 2),
           "iou_vs_torch_min": min(r["iou_vs_torch"] for r in rows),
           "iou_vs_torch_mean": round(float(np.mean([r["iou_vs_torch"] for r in rows])), 5),
           "logit_maxdiff_max": max(r["logit_maxdiff"] for r in rows),
           "iou_vs_gt_mean": round(float(np.mean([r["iou_vs_gt"] for r in rows])), 4),
           "iou_vs_gt_min": min(r["iou_vs_gt"] for r in rows), "per_frame": rows}
    with open(os.path.join(HERE, f"validate_onnx_{name}.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "per_frame"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny")
