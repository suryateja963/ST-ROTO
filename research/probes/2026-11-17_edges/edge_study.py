"""T-095 measurement study: where is mask edge accuracy lost, and which model-free / cheap change sharpens it?

Isolates edge quality from tracking: on single SA-V frames SAM 2.1 (tiny, image predictor, CPU) gets the RIGHT object
(ground-truth tight box + its most interior pixel, the recommended prompt, T-082). Variants of turning SAM's output
into a mask, all scored against the SA-V truth:
  A  bilinear   - today's path: 256x256 logits bilinearly upscaled, threshold 0
  B  guided     - A's mask refined against the plate with the guided filter (st_roto.matte.refine_alpha), > 0.5
  C  zoom       - second pass on a crop around A's mask (25 % margin, at least 64 px): the object fills more of the
                  model's 1024x1024 input; crop logits pasted back
  C2 zoom wide  - like C with generous context: margin = 100 % of the mask's size, at least 128 px
  O  oracle     - the TRUTH pushed through SAM's 256x256 logit grid (area-downsampled, bilinear back, > 0.5): how
                  much the low-resolution mask FORMAT alone can lose, independent of the model
Metrics: IoU; boundary F (precision/recall of boundary pixels within 2 px, DAVIS-style); mean boundary distance (px).
Only frames where A already found the object (IoU >= 0.5) count for the edge comparison (wrong-object starts are a
prompting problem, T-082). Writes edge_study.json.
--composite: EXACT-edge truth. SA-V truth masks were made with SAM's help (SAM 2 data engine), so their edges are
SAM-like; here each real object is cut out of its frame with its mask and pasted onto a frame of ANOTHER video
(resized), so the truth is exactly the paste mask (hard edges by construction). Writes edge_study_composite.json.
  .venv\\Scripts\\python.exe -I research/probes/2026-11-17_edges/edge_study.py [max_frames_per_object]
"""
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
SAV = os.path.join(ROOT, "data", "benchmarks", "sa-v")
MODEL = os.path.join(ROOT, "models", "onnx", "sam2.1-hiera-tiny")
TOL = 2
KEYS = ("A", "B", "C", "C2", "O")


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def boundary(m):
    m = m.astype(np.uint8)
    return (m - cv2.erode(m, np.ones((3, 3), np.uint8))) > 0


def boundary_scores(pred, gt):
    bp, bg = boundary(pred), boundary(gt)
    if not bp.any() or not bg.any():
        return 0.0, None
    dg = cv2.distanceTransform((~bg).astype(np.uint8), cv2.DIST_L2, 3)     # distance to the true boundary
    dp = cv2.distanceTransform((~bp).astype(np.uint8), cv2.DIST_L2, 3)
    prec = float((dg[bp] <= TOL).mean())
    rec = float((dp[bg] <= TOL).mean())
    f = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return f, float(dg[bp].mean())


def interior_point(gt):
    d = cv2.distanceTransform(gt.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(d)), d.shape)
    return float(x) + 0.5, float(y) + 0.5


def bbox(m):
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def main(per_obj=6, composite=False):
    from st_roto_ai.sam2 import Sam2Image, upscale_logits
    from st_roto.matte import refine_alpha
    sam = Sam2Image(os.path.join(MODEL), device="cpu")
    rows, t_enc, t_zoom, t_guided = [], [], [], []
    seqs = sorted(d for d in os.listdir(SAV) if d.startswith("sav_"))
    videos = sorted(set(q.rsplit("_", 1)[0] for q in seqs))
    for seq in seqs:
        masks = sorted(glob.glob(os.path.join(SAV, seq, "masks", "*.png")))
        vis = [p for p in masks if (cv2.imread(p, cv2.IMREAD_GRAYSCALE) > 127).sum() >= 64]
        pick = vis[:: max(1, len(vis) // per_obj)][:per_obj]
        for mp in pick:
            name = os.path.splitext(os.path.basename(mp))[0]
            gt = cv2.imread(mp, cv2.IMREAD_GRAYSCALE) > 127
            img = cv2.imread(os.path.join(SAV, seq, "frames", name + ".jpg"))[:, :, ::-1].astype(np.float32) / 255.0
            h, w = gt.shape
            if composite:                                     # paste onto a frame of another video
                other = videos[(videos.index(seq.rsplit("_", 1)[0]) + len(videos) // 2) % len(videos)]
                bgp = sorted(glob.glob(os.path.join(SAV, other + "_000", "frames", "*.jpg")))[0]
                bg = cv2.resize(cv2.imread(bgp)[:, :, ::-1], (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                img = np.where(gt[..., None], img, bg)
            x0, y0, x1, y1 = bbox(gt)
            cx, cy = interior_point(gt)
            pts, lab = [(x0, y0), (x1, y1), (cx, cy)], [2, 3, 1]
            t0 = time.time(); enc = sam.encode(img); out = sam.predict(enc, pts, lab); t_enc.append(time.time() - t0)
            a = out["logits"] > 0
            r = {"seq": seq, "frame": name, "size": [w, h], "object_px": int(gt.sum()),
                 "box_frac": round((x1 - x0) * (y1 - y0) / float(w * h), 4)}
            r["A"] = (iou(a, gt),) + boundary_scores(a, gt)
            t0 = time.time(); b = refine_alpha(img, a) > 0.5; t_guided.append(time.time() - t0)
            r["B"] = (iou(b, gt),) + boundary_scores(b, gt)
            for key, frac, least in (("C", 0.25, 32), ("C2", 1.0, 128)):
                if not a.any():
                    r[key] = r["A"]; continue
                ax0, ay0, ax1, ay1 = bbox(a)
                mx, my = max(least, int(frac * (ax1 - ax0))), max(least, int(frac * (ay1 - ay0)))
                X0, Y0, X1, Y1 = max(0, ax0 - mx), max(0, ay0 - my), min(w, ax1 + mx), min(h, ay1 + my)
                t0 = time.time()
                enc2 = sam.encode(img[Y0:Y1, X0:X1])
                o2 = sam.predict(enc2, [(px - X0, py - Y0) for px, py in pts], lab)
                full = out["logits"].copy()
                full[Y0:Y1, X0:X1] = o2["logits"]
                if key == "C":
                    t_zoom.append(time.time() - t0)
                c = full > 0
                r["crop_" + key] = [int(X1 - X0), int(Y1 - Y0)]
                r[key] = (iou(c, gt),) + boundary_scores(c, gt)
            g256 = cv2.resize(gt.astype(np.float32), (256, 256), interpolation=cv2.INTER_AREA)
            o = cv2.resize(g256, (w, h), interpolation=cv2.INTER_LINEAR) > 0.5
            r["O"] = (iou(o, gt),) + boundary_scores(o, gt)
            rows.append(r)
            print(seq, name, " ".join("%s %.3f/%.3f" % (k, r[k][0], r[k][1]) for k in KEYS), flush=True)
    good = [r for r in rows if r["A"][0] >= 0.5]
    summ = {"frames": len(rows), "frames_object_found": len(good), "tolerance_px": TOL,
            "seconds": {"encode+predict": round(float(np.mean(t_enc)), 3), "guided": round(float(np.mean(t_guided)), 3),
                        "zoom_extra": round(float(np.mean(t_zoom)), 3) if t_zoom else None}}
    for k in KEYS:
        summ[k] = {"mean_iou": round(float(np.mean([r[k][0] for r in good])), 4),
                   "mean_boundary_f": round(float(np.mean([r[k][1] for r in good])), 4),
                   "mean_boundary_dist_px": round(float(np.mean([r[k][2] for r in good if r[k][2] is not None])), 3),
                   "better_iou_than_A_by_0.01": sum(1 for r in good if r[k][0] > r["A"][0] + 0.01),
                   "worse_iou_than_A_by_0.01": sum(1 for r in good if r[k][0] < r["A"][0] - 0.01)}
    small = [r for r in good if r["box_frac"] < 0.02]
    summ["small_objects (box < 2 % of frame)"] = {
        "n": len(small), **{k: round(float(np.mean([r[k][0] for r in small])), 4) if small else None for k in KEYS}}
    out_name = "edge_study_composite.json" if composite else "edge_study.json"
    json.dump({"summary": summ, "rows": rows}, open(os.path.join(HERE, out_name), "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else 6, composite="--composite" in sys.argv)
