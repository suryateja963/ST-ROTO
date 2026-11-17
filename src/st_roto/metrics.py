"""Benchmark metrics (T-107, REQ-190, master prompt section 21.1). One implementation used for every benchmark, so
results are reproducible and comparable. Definitions and weights: docs/BENCHMARK_METHODOLOGY.md. numpy + OpenCV
(OpenCV imported lazily, only for boundary distances). Alphas are float arrays in [0, 1]; masks = alpha >= 0.5.
"""
import numpy as np

WEIGHTS = {"region": 0.25, "boundary": 0.20, "alpha": 0.10, "temporal": 0.15, "contour": 0.10, "stability": 0.15,
           "identity": 0.05}
CONTOUR_SCALE_PX = 10.0      # contour score = exp(-HD95 / 10 px)


def _m(a):
    return np.asarray(a, np.float32) >= 0.5


def iou(pred, gt):
    p, g = _m(pred), _m(gt)
    u = (p | g).sum()
    return 1.0 if u == 0 else float((p & g).sum()) / float(u)


def dice(pred, gt):
    p, g = _m(pred), _m(gt)
    s = p.sum() + g.sum()
    return 1.0 if s == 0 else 2.0 * float((p & g).sum()) / float(s)


def mae(pred, gt):
    return float(np.abs(np.asarray(pred, np.float64) - np.asarray(gt, np.float64)).mean())


def sad(pred, gt):
    """Sum of absolute differences in thousands (matting convention)."""
    return float(np.abs(np.asarray(pred, np.float64) - np.asarray(gt, np.float64)).sum()) / 1000.0


def mse(pred, gt):
    return float(((np.asarray(pred, np.float64) - np.asarray(gt, np.float64)) ** 2).mean())


def _boundary(m):
    import cv2
    m = m.astype(np.uint8)
    return (m - cv2.erode(m, np.ones((3, 3), np.uint8))) > 0


def _dist_to(b):
    import cv2
    return cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 3)


def boundary_tolerance(shape):
    """Boundary match tolerance: 0.2 % of the image diagonal (a relative tolerance as in the DAVIS benchmark), at
    least 1 px - about 4.4 px at 1920x1080."""
    h, w = shape[:2]
    return max(1.0, 0.002 * float(np.hypot(h, w)))


def boundary_f(pred, gt, tol=None):
    p, g = _m(pred), _m(gt)
    bp, bg = _boundary(p), _boundary(g)
    if not bp.any() and not bg.any():
        return 1.0
    if not bp.any() or not bg.any():
        return 0.0
    tol = boundary_tolerance(p.shape) if tol is None else tol
    prec = float((_dist_to(bg)[bp] <= tol).mean())
    rec = float((_dist_to(bp)[bg] <= tol).mean())
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def hd95(pred, gt):
    """95th percentile symmetric boundary distance in pixels (contour quality). inf if one side is empty."""
    p, g = _m(pred), _m(gt)
    bp, bg = _boundary(p), _boundary(g)
    if not bp.any() and not bg.any():
        return 0.0
    if not bp.any() or not bg.any():
        return float("inf")
    d = np.concatenate([_dist_to(bg)[bp], _dist_to(bp)[bg]])
    return float(np.percentile(d, 95))


def temporal_error(preds, gts):
    """Mean |(a_t - a_t-1) - (g_t - g_t-1)| over consecutive frames: flicker/drift the truth does not have."""
    errs = []
    for t in range(1, len(preds)):
        dp = np.asarray(preds[t], np.float64) - np.asarray(preds[t - 1], np.float64)
        dg = np.asarray(gts[t], np.float64) - np.asarray(gts[t - 1], np.float64)
        errs.append(float(np.abs(dp - dg).mean()))
    return float(np.mean(errs)) if errs else 0.0


def stability(ious, visible=None, kept=0.5):
    """Tracking stability over the frames where the object is visible: fraction kept (IoU >= 0.5) and the number of
    losses (kept -> not kept transitions)."""
    v = [x for i, x in enumerate(ious) if visible is None or visible[i]]
    if not v:
        return {"kept_fraction": 1.0, "losses": 0}
    k = [x >= kept for x in v]
    return {"kept_fraction": float(np.mean(k)), "losses": int(sum(1 for a, b in zip(k, k[1:]) if a and not b))}


def identity_preservation(pred_by_obj, gt_by_obj):
    """Several objects on one frame: fraction of truth objects whose best-overlapping prediction is their own
    (no swaps). pred_by_obj / gt_by_obj: {object id: alpha} with the same ids."""
    ids = [k for k in gt_by_obj if _m(gt_by_obj[k]).any()]
    if not ids:
        return 1.0
    ok = 0
    for k in ids:
        best = max(pred_by_obj, key=lambda j: iou(pred_by_obj[j], gt_by_obj[k]))
        ok += best == k
    return ok / float(len(ids))


def sequence_scores(preds, gts, visible=None):
    """All per-sequence metrics for ONE object: preds / gts lists of alphas (same frames)."""
    vis = visible if visible is not None else [bool(_m(g).any()) for g in gts]
    ious = [iou(p, g) for p, g in zip(preds, gts)]
    on = [i for i, v in enumerate(vis) if v]
    pick = lambda xs: [xs[i] for i in on] or [0.0]                         # noqa: E731
    hds = [hd95(preds[i], gts[i]) for i in on]
    finite = [h for h in hds if np.isfinite(h)]
    st = stability(ious, vis)
    return {"iou": float(np.mean(pick(ious))), "dice": float(np.mean(pick([dice(p, g) for p, g in zip(preds, gts)]))),
            "boundary_f": float(np.mean(pick([boundary_f(p, g) for p, g in zip(preds, gts)]))),
            "mae": float(np.mean([mae(p, g) for p, g in zip(preds, gts)])),
            "sad": float(np.mean([sad(p, g) for p, g in zip(preds, gts)])),
            "mse": float(np.mean([mse(p, g) for p, g in zip(preds, gts)])),
            "temporal_error": temporal_error(preds, gts),
            "hd95_px": float(np.mean(finite)) if finite else float("inf"),
            "hd95_missing_frames": len(hds) - len(finite),
            "kept_fraction": st["kept_fraction"], "losses": st["losses"], "frames": len(preds), "visible": len(on)}


def category_scores(s, identity=1.0):
    """Normalised 0..1 (higher is better) per category, from sequence_scores (methodology section 4)."""
    contour = float(np.exp(-s["hd95_px"] / CONTOUR_SCALE_PX)) if np.isfinite(s["hd95_px"]) else 0.0
    if s["hd95_missing_frames"] and s["visible"]:
        contour *= 1.0 - s["hd95_missing_frames"] / float(s["visible"])
    return {"region": s["iou"], "boundary": s["boundary_f"], "alpha": max(0.0, 1.0 - 10.0 * s["mae"]),
            "temporal": max(0.0, 1.0 - 10.0 * s["temporal_error"]), "contour": contour,
            "stability": s["kept_fraction"] / (1.0 + s["losses"]), "identity": float(identity)}


def overall(categories, weights=WEIGHTS):
    return float(sum(weights[k] * categories[k] for k in weights) / sum(weights.values()))
