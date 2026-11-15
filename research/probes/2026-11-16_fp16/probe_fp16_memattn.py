"""fp32 vs fp16 memory attention for SAM 2.1 tiny tracking, inside Nuke on CUDA (T-062, R-34/R-41).
Run: Nuke17.1.exe --nc -t probe_fp16_memattn.py <memattn file>     (one variant per process, clean GPU state)
Two full 48-frame runs in the same process. Measures per-frame IoU vs PyTorch reference and ground truth,
time per tracking step, and peak whole-GPU memory (nvidia-smi sampled every 100 ms).
Pixels are read straight from the synthetic PNGs (sRGB) to isolate the model; Nuke is only the host process.
"""
import json, os, subprocess, sys, threading, time

ROOT = "D:/ST-ROTO"
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                       # noqa: E402,F401  (host process)
import numpy as np                # noqa: E402
import cv2                        # noqa: E402
from st_roto_ai.sam2 import Sam2Video   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
FR = ROOT + "/research/probes/2026-11-15_video/frames"
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "memattn.onnx"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "sam2.1-hiera-tiny"
peak = {"v": 0, "stop": False}


def sampler():
    while not peak["stop"]:
        try:
            o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, creationflags=0x08000000).stdout
            peak["v"] = max(peak["v"], int(o.strip()))
        except Exception:
            pass
        time.sleep(0.1)


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


meta = json.load(open(FR + "/meta.json")); n, W, H = meta["frames"], meta["w"], meta["h"]
ref = np.load(ROOT + "/research/probes/2026-11-15_video/ref_logits_%s.npz" % MODEL)
frames = [cv2.cvtColor(cv2.imread(FR + "/frame_%04d.png" % i), cv2.COLOR_BGR2RGB).astype(np.float32) / 255 for i in range(n)]
gts = [cv2.imread(FR + "/gt_%04d.png" % i, cv2.IMREAD_GRAYSCALE) > 127 for i in range(n)]
threading.Thread(target=sampler, daemon=True).start()
R = {"variant": VARIANT, "model": MODEL, "runs": []}
for run in range(2):
    trk = Sam2Video(ROOT + "/models/onnx/%s/video" % MODEL, device="cuda", num_total_frames=n, memattn_file=VARIANT)
    R["device"] = trk.report.active
    ious_ref, ious_gt, steps, lows = [], [], [], {}
    for i in range(n):
        enc = trk.encode(frames[i])
        t = time.perf_counter()
        out = trk.add_points(0, enc, [tuple(meta["click_xy"])], [1]) if i == 0 else trk.track(i, enc)
        if i > 1:
            steps.append(time.perf_counter() - t)
        lows["f%04d" % i] = out["low_res"].astype(np.float32)
        m = out["logits"] > 0
        mr = cv2.resize(ref["f%04d" % i].astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR) > 0
        ious_ref.append(iou(m, mr)); ious_gt.append(iou(m, gts[i]))
    R["runs"].append({"iou_vs_torch_min": round(min(ious_ref), 5), "iou_vs_torch_mean": round(float(np.mean(ious_ref)), 5),
                      "iou_vs_gt_mean": round(float(np.mean(ious_gt)), 4), "iou_vs_gt_min": round(min(ious_gt), 4),
                      "track_step_ms": round(1000 * float(np.mean(steps)), 1), "peak_gpu_MiB_so_far": peak["v"]})
    if run == 0:
        np.savez_compressed(HERE + "/lowres_%s_%s.npz" % (MODEL, os.path.splitext(VARIANT)[0]), **lows)
peak["stop"] = True
json.dump(R, open(HERE + "/result_%s_%s.json" % (MODEL, os.path.splitext(VARIANT)[0]), "w"), indent=1)
print("DONE")
