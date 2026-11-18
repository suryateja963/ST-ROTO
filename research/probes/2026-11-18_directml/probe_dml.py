"""T-116: SAM 2.1 tracking through ST-ROTO's own tracker (st_roto_nuke.track.track_object) with the CUDA build
(onnxruntime-gpu 1.26.0) or the DirectML build (onnxruntime-directml 1.24.4) of ONNX Runtime, inside Nuke's Python.
One ONNX Runtime per process: run once per runtime and compare the JSON outputs (compare.py).
  Nuke17.1.exe --nc -t probe_dml.py runtime=cuda|directml model=sam2.1-hiera-tiny out=<json> [frames=48]
DirectML runs on any DirectX 12 GPU (AMD, Intel, NVIDIA): on this NVIDIA laptop it measures DirectML correctness and
speed; AMD / Intel hardware itself is not available here."""
import json
import os
import sys
import time

ROOT = "D:/ST-ROTO"
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
RUNTIME = args.get("runtime", "cuda")
if RUNTIME == "directml":
    sys.path.insert(0, ROOT + "/.tools/nuke-py311-dml")        # its onnxruntime shadows the CUDA build
sys.path.insert(0, ROOT + "/src")
sys.path.append(ROOT + "/.tools/nuke-py311")                    # numpy, cv2 (and the CUDA onnxruntime otherwise)
R = {"runtime": RUNTIME}
try:
    import numpy as np
    import cv2
    import onnxruntime as ort
    R["ort_version"], R["ort_file"] = ort.__version__, os.path.relpath(ort.__file__, ROOT)
    R["available_providers"] = ort.get_available_providers()
    from st_roto.geometry import Anchor, rasterize_spline
    from st_roto_nuke.track import track_object, model_dir

    VID = ROOT + "/research/probes/2026-11-15_video/frames"
    meta = json.load(open(VID + "/meta.json"))
    n = int(args.get("frames", meta["frames"]))
    model = args.get("model", "sam2.1-hiera-tiny")

    def get_rgb(f):                                             # sRGB PNG -> linear float (what Nuke's Read gives)
        s = cv2.imread(VID + "/frame_%04d.png" % f, cv2.IMREAD_COLOR)[:, :, ::-1].astype(np.float32) / 255.0
        return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4).astype(np.float32)

    device = "directml" if RUNTIME == "directml" else "cuda"
    # GPU memory: total used on the GPU sampled every 0.2 s (Windows shows no per-process value; T-092 method:
    # peak minus the idle baseline before any session exists). nvidia-smi sees DirectML's use of this NVIDIA GPU.
    import subprocess
    import threading

    def used():
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, creationflags=0x08000000).stdout
        return int(o.strip().splitlines()[0])
    base = used()
    peak = {"v": base, "stop": False}

    def poll():
        while not peak["stop"]:
            try:
                peak["v"] = max(peak["v"], used())
            except Exception:                                   # noqa: BLE001
                pass
            time.sleep(0.2)
    threading.Thread(target=poll, daemon=True).start()
    t0 = time.time()
    res = track_object(get_rgb, list(range(n)), 0, tuple(meta["click_xy"]), model=model, device=device)
    R["seconds_total"] = round(time.time() - t0, 2)
    R["device"], R["device_fallback"], R["device_reason"] = res["device"], res["device_fallback"], res["device_reason"]
    masks, ious = {}, {}
    for f, pts in sorted(res["keys"].items()):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in pts]
        m = rasterize_spline(a, meta["h"], meta["w"])
        gt = cv2.imread(VID + "/gt_%04d.png" % int(f), cv2.IMREAD_GRAYSCALE) > 127
        ious[int(f)] = round(float((m & gt).sum() / max(1, (m | gt).sum())), 4)
        masks[int(f)] = m
    R["iou_vs_gt"] = ious
    np.savez_compressed(args["out"].replace(".json", "_masks.npz"), **{"f%04d" % f: m for f, m in masks.items()})
    # second run in the same process = warm sessions: the per-frame speed an artist sees after 'Load model'
    t0 = time.time()
    track_object(get_rgb, list(range(n)), 0, tuple(meta["click_xy"]), model=model, device=device)
    R["seconds_warm"] = round(time.time() - t0, 2)
    peak["stop"] = True
    R["gpu_mem_baseline_mib"], R["gpu_mem_peak_increase_mib"] = base, peak["v"] - base
    R["ms_per_frame_warm"] = round(1000 * R["seconds_warm"] / n, 1)
except Exception:
    import traceback
    R["exception"] = traceback.format_exc()
json.dump(R, open(args["out"], "w"), indent=1)
