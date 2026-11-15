"""Headless Nuke probe: SAM 2.1 video tracking (ONNX, CUDA) inside Nuke -> one ANIMATED native Roto shape.

Run: Nuke17.1.exe --nc -t probe_track_in_nuke.py <model-name>
Nodes (4, within the Non-commercial 10-node cap): Read(sequence), Write(pixel dump), Roto(animated shape), Write(render).
Measures: pixel transfer, per-frame encoder/track time, GPU memory, IoU (tracker mask vs ground truth, vs PyTorch
reference, rendered animated Roto vs mask and vs ground truth).
"""
import json, os, subprocess, sys, threading, time
import nuke
import nuke.rotopaint as rp

ROOT = "D:/ST-ROTO"
sys.path.append(ROOT + "/.tools/nuke-py311")
sys.path.append(ROOT + "/prototypes/tracking")
sys.path.append(ROOT + "/prototypes/geometry")
import numpy as np                                     # noqa: E402
import cv2                                             # noqa: E402
from sam2_video_onnx import Sam2VideoTracker           # noqa: E402
from bezier_fit import fit_fixed_count                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
FR, OUT = HERE + "/frames", HERE + "/out"
os.makedirs(OUT, exist_ok=True)
MODEL = sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny"
K = 16                                                  # anchors in the animated shape
MEAN = np.array([0.485, 0.456, 0.406], np.float32); STD = np.array([0.229, 0.224, 0.225], np.float32)
meta = json.load(open(FR + "/meta.json")); N, W, H = meta["frames"], meta["w"], meta["h"]
R = {"model": MODEL, "frames": N, "size": f"{W}x{H}", "anchors": K}


class Peak(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.peak = 0; self.stop = False
    def run(self):
        while not self.stop:
            try:
                o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, creationflags=0x08000000).stdout
                self.peak = max(self.peak, int(o.strip()))
            except Exception:
                pass
            time.sleep(0.2)


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


peak = Peak(); peak.start()
nuke.root()["format"].setValue("HD_720")
# ---- 1. pixels out of Nuke (whole range in one render)
rd = nuke.nodes.Read(file=FR + "/frame_####.png", first=0, last=N - 1)
dump = nuke.nodes.Write(file=OUT + "/src.####.tif", file_type="tiff", channels="rgb")
dump["datatype"].setValue("32 bit float"); dump["compression"].setValue("none")
dump.setInput(0, rd)
t = time.time(); nuke.execute(dump, 0, N - 1); R["nuke_dump_s_per_frame"] = round((time.time() - t) / N, 3)

# ---- 2. track on CUDA
prov = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
t = time.time()
trk = Sam2VideoTracker(f"{ROOT}/models/onnx/{MODEL}/video", providers=prov, num_total_frames=N)
R["session_load_s"] = round(time.time() - t, 2); R["providers"] = trk.providers
ref = np.load(HERE + f"/ref_logits_{MODEL}.npz")
cx, cy = meta["click_xy"]; pts = np.array([[cx * 1024 / W, cy * 1024 / H]], np.float32)
t_read, t_enc, t_trk, rows, masks = [], [], [], [], []
for f in range(N):
    t = time.time()
    lin = np.clip(cv2.imread(OUT + "/src.%04d.tif" % f, cv2.IMREAD_UNCHANGED)[:, :, ::-1], 0, 1)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055).astype(np.float32)
    x = ((cv2.resize(srgb, (1024, 1024), interpolation=cv2.INTER_LINEAR) - MEAN) / STD).transpose(2, 0, 1)[None]
    t_read.append(time.time() - t)
    t = time.time(); enc = trk.encode(np.ascontiguousarray(x, np.float32)); t_enc.append(time.time() - t)
    t = time.time()
    out = trk.add_points(0, enc, pts, np.array([1], np.int32)) if f == 0 else trk.track(f, enc)
    t_trk.append(time.time() - t)
    m = cv2.resize(out["low_res"][0, 0], (W, H), interpolation=cv2.INTER_LINEAR) > 0
    mr = cv2.resize(ref["f%04d" % f].astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR) > 0
    gt = cv2.imread(FR + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
    masks.append(m)
    rows.append({"frame": f, "iou_vs_gt": round(iou(m, gt), 4), "iou_vs_torch_ref": round(iou(m, mr), 4)})
R["timing_ms_per_frame"] = {"read+preprocess": round(1000 * float(np.mean(t_read)), 1),
                            "encoder_warm": round(1000 * float(np.mean(t_enc[1:])), 1),
                            "track_step_warm": round(1000 * float(np.mean(t_trk[2:])), 1),
                            "first_encoder": round(1000 * t_enc[0], 1), "first_track": round(1000 * t_trk[1], 1)}

# ---- 3. animated Roto shape, K anchors keyed on every frame
roto = nuke.nodes.Roto(output="alpha"); roto.setInput(0, rd)
curves = roto["curves"]; shape = rp.Shape(curves)
# NOTE (measured, probe_anim_keys.py): keys added to a ShapeControlPoint AFTER shape.append() are silently lost
# (the shape stores a copy). So: fit every frame first, key each point completely, then append.
cps = [rp.ShapeControlPoint(0.0, 0.0) for _ in range(K)]
prev, fit_ms, skipped = None, [], []
for f, m in enumerate(masks):
    cnts = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    if not cnts:
        skipped.append(f); continue
    c = max(cnts, key=cv2.contourArea)[:, 0, :].astype(np.float64)   # largest piece only (see limitations)
    t = time.time(); a = fit_fixed_count(c, K, start_hint=None if prev is None else prev[0].p); fit_ms.append(time.time() - t)
    prev = a
    for cp, an in zip(cps, a):
        px, py = an.p[0] + 0.5, H - an.p[1] - 0.5
        cp.center.addPositionKey(f, rp.CVec2(px, py))
        # Nuke tangent = 2 x Bezier handle offset; leftTangent -> previous point (research/probes/2026-11-15_bezier)
        cp.leftTangent.addPositionKey(f, rp.CVec2(2 * (an.h_in[0] - an.p[0]), -2 * (an.h_in[1] - an.p[1])))
        cp.rightTangent.addPositionKey(f, rp.CVec2(2 * (an.h_out[0] - an.p[0]), -2 * (an.h_out[1] - an.p[1])))
for cp in cps:
    shape.append(cp)
R["keys_on_point0"] = len(list(shape[0].center.getControlPointKeyTimes()))
shape.name = "STROTO_track_" + MODEL.replace(".", "_").replace("-", "_")
curves.rootLayer.append(shape)
R["bezier_fit_ms_mean"] = round(1000 * float(np.mean(fit_ms)), 1)
R["frames_without_contour"] = skipped

# ---- 4. render the animated shape and compare
rw = nuke.nodes.Write(file=OUT + "/roto.####.tif", file_type="tiff", channels="alpha")
rw["datatype"].setValue("32 bit float"); rw["compression"].setValue("none"); rw.setInput(0, roto)
nuke.execute(rw, 0, N - 1)
for f in range(N):
    img = cv2.imread(OUT + "/roto.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
    rm = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
    gt = cv2.imread(FR + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
    rows[f]["roto_iou_vs_mask"] = round(iou(rm, masks[f]), 4)
    rows[f]["roto_iou_vs_gt"] = round(iou(rm, gt), 4)
nuke.scriptSaveAs(OUT + f"/track_{MODEL}.nk", overwrite=1)

peak.stop = True; peak.join()
R["gpu_mem_peak_MiB_system"] = peak.peak
for k in ("iou_vs_gt", "iou_vs_torch_ref", "roto_iou_vs_mask", "roto_iou_vs_gt"):
    v = [r[k] for r in rows]
    R[k + "_mean"] = round(float(np.mean(v)), 4); R[k + "_min"] = float(min(v))
R["nodes_used"] = len(nuke.allNodes())
R["per_frame"] = rows
with open(HERE + f"/nuke_track_{MODEL}.json", "w") as fh:
    json.dump(R, fh, indent=1)
print("PROBE_DONE", MODEL)
