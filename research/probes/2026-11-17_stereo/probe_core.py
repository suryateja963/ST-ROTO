"""T-109: st_roto.stereo measured on the synthetic stereo shot (exact ground truth), outside Nuke.

1. disparity: estimate_disparity on the ground-truth left mask, every frame, vs the true target disparity;
2. prompt transfer: left GT box + centre click -> right prompt; box IoU vs the right GT box;
3. consistency on CORRECT shapes (splines fitted to the GT masks of both views): false flags;
4. consistency with injected errors in the right view: detected?
Run with the project venv; writes result_core.json.
"""
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import stereo  # noqa: E402
from st_roto.geometry import mask_to_points  # noqa: E402

D = os.path.join(HERE, "out", "stereo")
meta = json.load(open(os.path.join(D, "meta.json")))
N, W, H = meta["frames"], meta["w"], meta["h"]


def img(view, f):
    return cv2.imread(os.path.join(D, view, "frame_%04d.png" % f))[:, :, ::-1].astype(np.float32) / 255.0


def gt(view, f):
    return cv2.imread(os.path.join(D, view, "gt_%04d.png" % f), 0) > 127


def box(m):
    ys, xs = np.nonzero(m)
    return (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1))


def box_iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u


R = {"disparity": {}, "transfer": {}}
errs, times = [], []
for f in range(N):
    s = f / (N - 1.0)
    true_dx = -(30 + 20 * s)
    t = time.time()
    r = stereo.estimate_disparity(img("left", f), img("right", f), gt("left", f))
    times.append(time.time() - t)
    # the centroid shift of the GT masks is the truth for the visible part (occluder cuts differ per view)
    R["disparity"][f] = dict(r, true_dx=round(true_dx, 3))
    errs.append(abs(r["dx"] - true_dx))
    if f in (0, 20, 47):
        lb = box(gt("left", f))
        c = ((lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2)
        p = stereo.transfer_prompt({"name": "t", "frame": f, "points": [c], "labels": [1]}, r["dx"], r["dy"], lb, W, H)
        rb = (p["points"][0][0], p["points"][0][1], p["points"][1][0], p["points"][1][1])
        R["transfer"][f] = {"box_iou_vs_right_gt": round(box_iou(rb, box(gt("right", f))), 4),
                            "click_inside_right_gt": bool(gt("right", f)[int(p["points"][2][1]), int(p["points"][2][0])])}
R["disparity_abs_error"] = {"mean": float(np.mean(errs)), "max": float(np.max(errs)),
                            "max_frame": int(np.argmax(errs))}
R["disparity_seconds_mean"] = float(np.mean(times))

# consistency on correct shapes
geo = {}
for v in ("left", "right"):
    geo[v] = {}
    for f in range(N):
        pts = mask_to_points(gt(v, f).astype(np.float32) - 0.5, count=24)
        geo[v][f] = stereo.key_geometry(pts) if pts else None
clean = stereo.consistency(geo["left"], geo["right"], "left", "right")
R["clean"] = {"flags": clean["flags"], "offset": clean["offset"], "disparity": clean["disparity"]}
_ot, _ob = clean["offset"]
_fr = clean["frames"]
_dx = [_fr[f]["dx"] for f in sorted(_fr)]
R["clean_residuals"] = {
    "max_top_px": max(abs(p["dy_top"] - _ot) for p in _fr.values()),
    "max_bottom_px": max(abs(p["dy_bottom"] - _ob) for p in _fr.values()),
    "object_height_px": [min(g["y1"] - g["y0"] for g in geo["left"].values()),
                         max(g["y1"] - g["y0"] for g in geo["left"].values())],
    "max_area_ratio": max(p["area_ratio"] for p in _fr.values()),
    "max_dx_step_px": max(abs(_dx[i + 1] - _dx[i]) for i in range(len(_dx) - 1))}
print("clean residuals:", R["clean_residuals"])


def injected(kind, f):
    g = dict(geo["right"])
    m = gt("right", f)
    if kind == "vertical_12px":
        m = np.roll(m, 12, axis=0)
    elif kind == "scaled_1.5":
        c = box(m); cx, cy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
        M = cv2.getRotationMatrix2D((cx, cy), 0, 1.5)
        m = cv2.warpAffine(m.astype(np.uint8), M, (W, H), flags=cv2.INTER_NEAREST) > 0
    elif kind == "wrong_object":                       # the distractor disc in the right view
        dx = int(1050 - 600 * f / (N - 1.0)) - 20; dy = int(560 - 120 * np.sin(np.pi * f / (N - 1.0)))
        m = np.zeros((H, W), np.uint8); cv2.circle(m, (dx, dy), 85, 1, -1); m = m > 0
    elif kind == "horizontal_25px":
        m = np.roll(m, -25, axis=1)
    elif kind == "missing":
        g[f] = None
        return g
    g[f] = stereo.key_geometry(mask_to_points(m.astype(np.float32) - 0.5, count=24))
    return g


R["injected"] = {}
for kind in ("vertical_12px", "scaled_1.5", "wrong_object", "horizontal_25px", "missing"):
    hits = []
    for f in (5, 12, 25, 40):
        rep = stereo.consistency(geo["left"], injected(kind, f), "left", "right")
        fl = [x for x in rep["flags"] if x not in clean["flags"]]
        hits.append({"frame": f, "caught": any(x[0] == f for x in fl), "new_flags": fl})
    R["injected"][kind] = {"caught": sum(h["caught"] for h in hits), "of": len(hits), "detail": hits}
json.dump(R, open(os.path.join(HERE, "result_core.json"), "w"), indent=1)
print(json.dumps({k: R[k] for k in ("disparity_abs_error", "disparity_seconds_mean", "transfer")}, indent=1))
print("clean flags:", clean["flags"])
for k, v in R["injected"].items():
    print(k, v["caught"], "/", v["of"], [h["new_flags"] for h in v["detail"] if not h["caught"]][:2])
