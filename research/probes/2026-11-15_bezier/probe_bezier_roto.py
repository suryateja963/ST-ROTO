"""Headless Nuke probe: Bezier-fitted SAM mask -> native Roto shape with tangents.

Run: Nuke17.1.exe --nc -t probe_bezier_roto.py
Input: research/probes/2026-11-15_sam2/mask_sam2.1-hiera-tiny.png (SAM 2.1 tiny mask, 1920x1080) + test_gt.png.
Renders two Roto nodes that differ only in the tangent convention:
  A: leftTangent = h_in - p,  rightTangent = h_out - p
  B: leftTangent = h_out - p, rightTangent = h_in - p
The correct convention reproduces the mask (IoU ~1); the wrong one twists the curve.
Also reports point count / accuracy for several tolerances (rasterised in numpy) and the Nuke-rendered IoU.
Nodes used: 4 (2 Roto + 2 Write) under the Non-commercial 10-node cap.
"""
import json, os, sys, time
import nuke
import nuke.rotopaint as rp

ROOT = "D:/ST-ROTO"
sys.path.append(ROOT + "/.tools/nuke-py311")
sys.path.append(ROOT + "/prototypes/geometry")
import numpy as np            # noqa: E402
import cv2                    # noqa: E402
from bezier_fit import fit_closed_contour, sample_spline, max_deviation   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
SAM = ROOT + "/research/probes/2026-11-15_sam2"
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
R = {}


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


mask = cv2.imread(SAM + "/mask_sam2.1-hiera-tiny.png", cv2.IMREAD_GRAYSCALE) > 127
gt = cv2.imread(SAM + "/test_gt.png", cv2.IMREAD_GRAYSCALE) > 127
H, W = mask.shape
cnt = max(cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)
contour = cnt[:, 0, :].astype(np.float64)
R["contour_pixels"] = len(contour)


def raster(anchors):
    m = np.zeros((H, W), np.uint8)
    pts = np.round(sample_spline(anchors, 128) * 16).astype(np.int32)
    cv2.fillPoly(m, [pts], 1, lineType=cv2.LINE_8, shift=4)
    return m.astype(bool)


# tolerance sweep (numpy rasterisation, no Nuke)
R["sweep"] = {}
for tol in (0.5, 1.0, 2.0, 3.0):
    t = time.time(); a = fit_closed_contour(contour, tol=tol); dt = time.time() - t
    mx, mean = max_deviation(a, contour)
    r = raster(a)
    R["sweep"][str(tol)] = {"anchors": len(a), "corners": int(sum(x.corner for x in a)), "fit_ms": round(dt * 1000, 1),
                            "max_dev_px": round(mx, 3), "mean_dev_px": round(mean, 3),
                            "iou_vs_mask": round(iou(r, mask), 5), "iou_vs_gt": round(iou(r, gt), 5)}

# Nuke render for tol = 1.0, both tangent conventions
anchors = fit_closed_contour(contour, tol=1.0)
nuke.root()["format"].setValue("HD_1080")


def to_nuke(v):       # image (col,row) -> Nuke canvas (x right, y up, pixel centre at +0.5)
    return float(v[0]) + 0.5, float(H - v[1]) - 0.5


def build(convention):
    roto = nuke.nodes.Roto(output="alpha")
    curves = roto["curves"]
    shape = rp.Shape(curves)
    for a in anchors:
        px, py = to_nuke(a.p); ix, iy = to_nuke(a.h_in); ox, oy = to_nuke(a.h_out)
        cp = rp.ShapeControlPoint(px, py)
        # Nuke tangent = 2 x (Bezier handle - point); measured in probe_tangent_keys.py (circle IoU 0.9993)
        s = 2.0
        lt, rt = ((s * (ix - px), s * (iy - py)), (s * (ox - px), s * (oy - py))) if convention == "A" else ((s * (ox - px), s * (oy - py)), (s * (ix - px), s * (iy - py)))
        cp.leftTangent.addPositionKey(nuke.frame(), rp.CVec2(*lt) if hasattr(rp, "CVec2") else lt)
        cp.rightTangent.addPositionKey(nuke.frame(), rp.CVec2(*rt) if hasattr(rp, "CVec2") else rt)
        shape.append(cp)
    shape.name = "STROTO_bezier_" + convention
    curves.rootLayer.append(shape)
    w = nuke.nodes.Write(file=f"{OUT}/bezier_{convention}.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none")
    w.setInput(0, roto)
    nuke.execute(w, 1, 1)
    img = cv2.imread(f"{OUT}/bezier_{convention}.tif", cv2.IMREAD_UNCHANGED)
    img = img if img.ndim == 2 else img[:, :, -1]
    rm = img > 0.5
    cy1, cx1 = np.argwhere(rm).mean(0); cy2, cx2 = np.argwhere(mask).mean(0)
    # read back a tangent to confirm storage is relative
    k = shape[0]
    lt_back = k.leftTangent.getPosition(nuke.frame())
    return {"roto_size": "%dx%d" % (roto.width(), roto.height()), "anchors": len(anchors),
            "iou_vs_mask": round(iou(rm, mask), 5), "iou_vs_gt": round(iou(rm, gt), 5),
            "centroid_offset_px": [round(float(cx1 - cx2), 3), round(float(cy1 - cy2), 3)],
            "first_left_tangent_readback": [round(lt_back.x, 3), round(lt_back.y, 3)]}


R["nuke_A_left_is_incoming"] = build("A")
R["nuke_B_left_is_outgoing"] = build("B")
R["polygon_baseline_from_sam_probe"] = {"anchors": 61, "iou_vs_mask": 0.99608, "note": "approxPolyDP 1px, no tangents"}
nuke.scriptSaveAs(OUT + "/bezier_roto.nk", overwrite=1)
R["nodes_used"] = len(nuke.allNodes())
with open(HERE + "/result_bezier.json", "w") as f:
    json.dump(R, f, indent=1)
print("PROBE_DONE")
