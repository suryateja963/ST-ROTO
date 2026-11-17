"""T-120: correspondence on the synthetic NON-rectified multi-camera shot (exact truth), outside Nuke.
For every frame and pair A->B, A->C: the target's truth mask in A is searched in the other view
  (1) by the T-109 horizontal disparity search (assumes a rectified rig, +-4 px vertical),
  (2) by the T-120 epipolar search with the known cameras.
Score: the transferred box (A's truth box moved by the found shift) vs the other view's truth box (IoU), and the
error of the moved centroid vs the other view's truth centroid. Also: epipolar distance of the truth centroids
(how well 'centroid on the epipolar line' holds for correct shapes) vs a wrong object's.
Writes result_correspondence.json."""
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import cameras as cm, stereo  # noqa: E402

D = os.path.join(HERE, "out", "mc")
meta = json.load(open(os.path.join(D, "meta.json")))
W, H, N = meta["w"], meta["h"], meta["frames"]
CAMS = meta["cameras"]


def P_of(v):
    c = CAMS[v]
    K = cm.intrinsics(W, H, c["focal"], c["haperture"], win_translate=c["win_translate"])
    R, C = cm.from_world_matrix(np.array(c["world_matrix"]).reshape(4, 4))
    return cm.projection(K, R, C), C


def img(v, f):
    """Linear light, as the product gets it from Nuke (sRGB PNG decoded)."""
    a = cv2.cvtColor(cv2.imread(os.path.join(D, v, "frame_%04d.png" % f)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def cam_of(v):
    c = CAMS[v]
    K = cm.intrinsics(W, H, c["focal"], c["haperture"], win_translate=c["win_translate"])
    R_, C_ = cm.from_world_matrix(np.array(c["world_matrix"]).reshape(4, 4))
    return K, R_, C_


def gt(v, f):
    return cv2.imread(os.path.join(D, v, "gt_%04d.png" % f), 0) > 127


def box_iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u else 0.0


PA, CA = P_of("A")
R = {}
for v in ("B", "C"):
    Pv, _ = P_of(v)
    F = cm.fundamental(PA, Pv, CA)
    rows = []
    for f in range(N):
        ma, mb = gt("A", f), gt(v, f)
        if mb.sum() < 2000:
            continue
        ba, bb = stereo.mask_box(ma), stereo.mask_box(mb)
        ca = np.array(np.nonzero(ma)[::-1]).mean(1) + 0.5
        cb = np.array(np.nonzero(mb)[::-1]).mean(1) + 0.5
        r = {"frame": f, "true_shift": (cb - ca).round(1).tolist()}
        sf = f / (N - 1.0)                                 # exact 3D centre of the target (make_multicam.py)
        X3 = [-0.9 + 1.6 * sf, 0.25 * np.sin(2 * np.pi * sf), -5.0]
        pa3, pv3 = cm.project(PA, [X3])[0][0], cm.project(Pv, [X3])[0][0]
        r["visible_fraction_in_view"] = round(float(mb.sum()) / float(ma.sum()), 3)
        for label, fn in (("horizontal", lambda: stereo.estimate_disparity(img("A", f), img(v, f), ma)),
                          ("epipolar", lambda: stereo.estimate_shift_epipolar(
                              img("A", f), img(v, f), ma, F, scale_of=cm.scale_along(cam_of("A"), cam_of(v), ca)))):
            t = time.time()
            try:
                s = fn()
                sc = 1.0
                if label == "epipolar":                      # T-120: box scaled by the triangulated depth
                    cA, RA_, KA = cm.from_world_matrix(np.array(CAMS["A"]["world_matrix"]).reshape(4, 4))[1],                         cm.from_world_matrix(np.array(CAMS["A"]["world_matrix"]).reshape(4, 4))[0],                         cm.intrinsics(W, H, CAMS["A"]["focal"], CAMS["A"]["haperture"], win_translate=CAMS["A"]["win_translate"])
                    Rv_, cV = cm.from_world_matrix(np.array(CAMS[v]["world_matrix"]).reshape(4, 4))
                    Kv = cm.intrinsics(W, H, CAMS[v]["focal"], CAMS[v]["haperture"], win_translate=CAMS[v]["win_translate"])
                    X = cm.triangulate(PA, Pv, ca, ca + [s["dx"], s["dy"]])
                    sc = cm.image_scale(KA, RA_, cA, Kv, Rv_, cV, X)
                    r.setdefault("scale", round(sc, 4))
                cx_, cy_ = ca
                bs = (cx_ + (ba[0] - cx_) * sc, cy_ + (ba[1] - cy_) * sc, cx_ + (ba[2] - cx_) * sc, cy_ + (ba[3] - cy_) * sc)
                moved = (bs[0] + s["dx"], bs[1] + s["dy"], bs[2] + s["dx"], bs[3] + s["dy"])
                r[label] = {"box_iou": round(box_iou(moved, bb), 3),
                            "centre_3d_error_px": round(float(np.hypot(*(pa3 + [s["dx"], s["dy"]] - pv3))), 2),
                            "centroid_error_px": round(float(np.hypot(*(ca + [s["dx"], s["dy"]] - cb))), 2),
                            "seconds": round(time.time() - t, 2)}
            except ValueError as e:
                r[label] = {"error": str(e)}
        l = cm.epipolar_line(F, ca)
        r["truth_centroid_epipolar_px"] = round(abs(cm.line_distance(l, cb)), 2)
        rows.append(r)
    ok = lambda lab, thr: sum(1 for r in rows if r[lab].get("box_iou", 0) >= thr)   # noqa: E731
    R[v] = {"frames": len(rows), "rows": rows,
            "horizontal_box_iou>=0.8": ok("horizontal", 0.8), "epipolar_box_iou>=0.8": ok("epipolar", 0.8),
            "horizontal_mean_centroid_error": round(float(np.mean([r["horizontal"].get("centroid_error_px", 999)
                                                                   for r in rows])), 2),
            "epipolar_mean_centroid_error": round(float(np.mean([r["epipolar"].get("centroid_error_px", 999)
                                                                 for r in rows])), 2),
            "truth_centroid_epipolar_px_max": max(r["truth_centroid_epipolar_px"] for r in rows),
            "epipolar_centre_3d_error_median": round(float(np.median([r["epipolar"].get("centre_3d_error_px", 999)
                                                                       for r in rows])), 2),
            "epipolar_centre_3d_error<=5px": sum(1 for r in rows if r["epipolar"].get("centre_3d_error_px", 999) <= 5)}
json.dump(R, open(os.path.join(HERE, "result_correspondence.json"), "w"), indent=1)
for v, x in R.items():
    print(v, {k: val for k, val in x.items() if k != "rows"})
