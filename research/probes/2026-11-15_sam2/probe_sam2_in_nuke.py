"""Headless Nuke probe: SAM 2.1 (ONNX, CUDA) inside the Nuke process -> mask -> native Roto shape.

Run:  Nuke17.1.exe --nc -t probe_sam2_in_nuke.py <model-name>     e.g. sam2.1-hiera-tiny
Prereqs: models/onnx/<model>/{encoder,decoder}.onnx (tools/models/export_sam2_onnx.py),
         .tools/nuke-py311 with onnxruntime-gpu 1.26.0, numpy, opencv-python-headless.
Uses 4 nodes (Non-commercial 10-node cap): Read, Write(dump), Roto, Write(roto).

Steps and what is measured:
  1. Nuke renders the source frame to a float TIFF (pip OpenCV 5 has no OpenEXR); Python reads it (pixel transfer cost).
  2. Encoder + decoder on CUDA via ONNX Runtime (timings, GPU memory).
  3. Mask -> contour -> polygon -> nuke.rotopaint Shape (native, editable without ST-ROTO).
  4. Nuke renders the Roto shape; IoU of rendered shape vs SAM mask vs ground truth (coordinate mapping check).
"""
import json, os, subprocess, sys, threading, time
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import nuke
import nuke.rotopaint as rp

ROOT = "D:/ST-ROTO"
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np            # noqa: E402
import cv2                    # noqa: E402
import onnxruntime as ort     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
MODEL = sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny"
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
R = {"model": MODEL, "nuke": nuke.NUKE_VERSION_STRING, "nc": bool(nuke.env.get("nc")), "ort": ort.__version__}
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
CLICK = (820.0, 480.0)  # image coords (x right, y down), inside the target ellipse of test_image.png


def gpu_mem():
    o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, creationflags=0x08000000).stdout
    return int(o.strip())


class Peak(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.peak = 0; self.stop = False
    def run(self):
        while not self.stop:
            try: self.peak = max(self.peak, gpu_mem())
            except Exception: pass
            time.sleep(0.2)


def iou(a, b):
    a, b = a.astype(bool), b.astype(bool)
    return float((a & b).sum() / max(1, (a | b).sum()))


R["gpu_mem_before_MiB"] = gpu_mem()
peak = Peak(); peak.start()

# ---- 1. pixels out of Nuke
rd = nuke.nodes.Read(file=HERE + "/test_image.png")
W, H = rd.width(), rd.height()
dump = nuke.nodes.Write(file=OUT + "/src_dump.tif", file_type="tiff", channels="rgb")
dump["datatype"].setValue("32 bit float")
dump["compression"].setValue("none")  # tiff: uncompressed
dump.setInput(0, rd)
t = time.time(); nuke.execute(dump, 1, 1); t_render = time.time() - t
t = time.time(); src = cv2.imread(OUT + "/src_dump.tif", cv2.IMREAD_UNCHANGED); t_read = time.time() - t
rgb = np.clip(src[:, :, ::-1], 0, 1)            # BGR->RGB; Nuke linearises sRGB PNG on read
R["pixel_transfer"] = {"w": W, "h": H, "nuke_render_tiff_s": round(t_render, 3), "cv2_read_s": round(t_read, 3)}
# Model expects sRGB-encoded 0..1 like the PNG; convert Nuke's linear float back (Nuke default sRGB OCIO/legacy).
srgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
ref = cv2.cvtColor(cv2.imread(HERE + "/test_image.png"), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
R["pixel_transfer"]["max_abs_diff_vs_png_after_srgb_encode"] = float(np.abs(srgb - ref).max())

# ---- 2. SAM on CUDA
prov = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
mdir = f"{ROOT}/models/onnx/{MODEL}"
t = time.time()
enc = ort.InferenceSession(mdir + "/encoder.onnx", providers=prov)
dec = ort.InferenceSession(mdir + "/decoder.onnx", providers=prov)
R["session_load_s"] = round(time.time() - t, 2)
R["providers"] = {"encoder": enc.get_providers(), "decoder": dec.get_providers()}
x = cv2.resize(srgb.astype(np.float32), (1024, 1024), interpolation=cv2.INTER_AREA)
x = ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
enc_times = []
for i in range(4):
    t = time.time(); img_e, s0, s1 = enc.run(None, {"pixel_values": x}); enc_times.append(time.time() - t)
pts = np.array([[[[CLICK[0] * 1024 / W, CLICK[1] * 1024 / H]]]], np.float32)
lbl = np.ones((1, 1, 1), np.int32)
dec_times = []
for i in range(11):
    t = time.time(); masks, scores, obj = dec.run(None, {"image_embed": img_e, "feat_s0": s0, "feat_s1": s1,
                                                         "point_coords": pts, "point_labels": lbl}); dec_times.append(time.time() - t)
R["encoder_s"] = {"first": round(enc_times[0], 3), "warm_mean": round(float(np.mean(enc_times[1:])), 3)}
R["decoder_ms"] = {"first": round(dec_times[0] * 1000, 1), "warm_mean": round(float(np.mean(dec_times[1:])) * 1000, 1)}
best = int(np.argmax(scores.ravel()))
R["iou_scores"] = scores.ravel().round(4).tolist()
mask = cv2.resize(masks[0, 0, best], (W, H), interpolation=cv2.INTER_LINEAR) > 0
gt = cv2.imread(HERE + "/test_gt.png", cv2.IMREAD_GRAYSCALE) > 127
R["sam_mask_iou_vs_gt"] = iou(mask, gt)

# ---- 3. mask -> native Roto shape
cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
cnt = max(cnts, key=cv2.contourArea)
poly = cv2.approxPolyDP(cnt, 1.0, True)[:, 0, :].astype(np.float64)
nuke.root()["format"].setValue("HD_1080")      # NC caps output at 1920x1080; default root is 2K
roto = nuke.nodes.Roto(output="alpha")
roto.setInput(0, rd)                           # inherit the source format
R["roto_format"] = "%dx%d" % (roto.width(), roto.height())
curves = roto["curves"]
shape = rp.Shape(curves)
for (col, row) in poly:
    # image (col,row) pixel centre -> Nuke canvas (origin bottom-left, pixel centre at +0.5)
    shape.append(rp.ShapeControlPoint(float(col) + 0.5, float(H - row) - 0.5))
shape.name = "STROTO_sam_" + MODEL.replace(".", "_").replace("-", "_")
curves.rootLayer.append(shape)
R["roto"] = {"control_points": len(poly), "contour_pixels": int(len(cnt)), "shape_name": shape.name}

# ---- 4. render the Roto shape and compare
rw = nuke.nodes.Write(file=OUT + f"/roto_{MODEL}.tif", file_type="tiff", channels="alpha")
rw["datatype"].setValue("32 bit float"); rw["compression"].setValue("none")
rw.setInput(0, roto)
nuke.execute(rw, 1, 1)
ra = cv2.imread(OUT + f"/roto_{MODEL}.tif", cv2.IMREAD_UNCHANGED)
ra = ra if ra.ndim == 2 else ra[:, :, -1]
roto_mask = ra > 0.5
R["roto_iou_vs_sam_mask"] = iou(roto_mask, mask)
R["roto_iou_vs_gt"] = iou(roto_mask, gt)
# centroid offset catches a flipped/shifted coordinate mapping
cy1, cx1 = np.argwhere(roto_mask).mean(0); cy2, cx2 = np.argwhere(mask).mean(0)
R["roto_centroid_offset_px"] = [round(float(cx1 - cx2), 3), round(float(cy1 - cy2), 3)]
nuke.scriptSaveAs(OUT + f"/roto_{MODEL}.nk", overwrite=1)   # NC saves .nknc; shape stays native and editable

peak.stop = True; peak.join()
R["gpu_mem_peak_MiB"] = peak.peak
R["nodes_used"] = len(nuke.allNodes())
with open(HERE + f"/result_{MODEL}.json", "w") as f:
    json.dump(R, f, indent=1)
print("PROBE_DONE", MODEL)
