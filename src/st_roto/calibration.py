"""Calibration of the review-flag thresholds (T-068) from tracked frames with ground truth. Pure Python + numpy.

A frame is BAD when its mask is wrong (IoU vs truth < `bad_iou`) or the object is visible in the truth but the AI
reports it absent (or vice versa). The review rules (st_roto.quality) flag a frame when |object score| < margin or
(on keyed frames) predicted IoU < iou_min, or when the object is lost between visible frames. For a grid of
(margin, iou_min) this computes how many bad frames are flagged (recall) and how many flags are real
(precision). Results on synthetic shots are PROVISIONAL; real footage needs OQ-13.
"""
from __future__ import annotations

import numpy as np


def label_bad(rec: dict, bad_iou: float = 0.9) -> bool:
    if rec["truth_visible"] != (rec["object_score"] > 0):
        return True
    return rec["truth_visible"] and rec["iou_true"] < bad_iou


def flags_for(records: list, margin: float, iou_min: float, lost_max_gap: int = None) -> list:
    """Same rules as st_roto.quality.review_frames, per sequence (records carry 'seq'). -> [bool] aligned."""
    from .quality import review_frames
    out = [False] * len(records)
    by_seq = {}
    for i, r in enumerate(records):
        by_seq.setdefault(r["seq"], []).append(i)
    import st_roto.quality as q
    old = (q.OBJECT_SCORE_MARGIN, q.IOU_PRED_MIN)
    q.OBJECT_SCORE_MARGIN, q.IOU_PRED_MIN = margin, iou_min
    try:
        for idx in by_seq.values():
            reps = [{"frame": records[i]["frame"], "object_score": records[i]["object_score"],
                     "iou_pred": records[i]["iou_pred"]} for i in idx]
            keyed = [records[i]["frame"] for i in idx if records[i]["object_score"] > 0]
            flagged = {f for f, _, _ in review_frames(reps, keyed, lost_max_gap=lost_max_gap)}
            for i in idx:
                out[i] = records[i]["frame"] in flagged
    finally:
        q.OBJECT_SCORE_MARGIN, q.IOU_PRED_MIN = old
    return out


def evaluate(records: list, margins=(0.25, 0.5, 1.0, 1.5, 2.0, 3.0), iou_mins=(0.0, 0.5, 0.6, 0.7, 0.8, 0.9),
             bad_iou: float = 0.9, lost_max_gap: int = None) -> dict:
    """-> {"frames", "bad", "grid": [{margin, iou_min, flagged, tp, precision, recall, f1}], "best",
    "iou_pred_vs_true_corr"}."""
    bad = [label_bad(r, bad_iou) for r in records]
    grid = []
    for m in margins:
        for q in iou_mins:
            fl = flags_for(records, m, q, lost_max_gap)
            tp = sum(1 for a, b in zip(fl, bad) if a and b)
            nf, nb = sum(fl), sum(bad)
            p = tp / nf if nf else 1.0
            rc = tp / nb if nb else 1.0
            f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
            grid.append({"margin": m, "iou_min": q, "flagged": nf, "tp": tp, "precision": round(p, 3),
                         "recall": round(rc, 3), "f1": round(f1, 3)})
    vis = [r for r in records if r["truth_visible"] and r["object_score"] > 0 and r["iou_pred"] is not None]
    corr = float(np.corrcoef([r["iou_pred"] for r in vis], [r["iou_true"] for r in vis])[0, 1]) if len(vis) > 2 else None
    best = max(grid, key=lambda g: (g["f1"], g["recall"], -g["flagged"]))
    return {"frames": len(records), "bad": sum(bad), "grid": grid, "best": best,
            "iou_pred_vs_true_corr": None if corr is None or np.isnan(corr) else round(corr, 3)}


def area_jump_flags(records: list, threshold: float) -> list:
    """T-078 rule (st_roto.quality.area_jumps) per sequence on records carrying 'area_pred'. -> [bool] aligned."""
    from .quality import area_jumps
    out = [False] * len(records)
    by_seq = {}
    for i, r in enumerate(records):
        by_seq.setdefault(r["seq"], []).append(i)
    for idx in by_seq.values():
        j = area_jumps({records[i]["frame"]: records[i].get("area_pred", 0) for i in idx}, threshold)
        for i in idx:
            out[i] = records[i]["frame"] in j
    return out


def evaluate_area_jumps(records: list, thresholds=(0.2, 0.25, 0.35, 0.5, 0.65), margin: float = 1.0,
                        iou_min: float = 0.7, bad_iou: float = 0.9, lost_max_gap: int = None) -> list:
    """For each threshold: the area rule alone, and what it ADDS to the score rules at (margin, iou_min).
    -> [{threshold, flagged, tp, precision, added_flags, added_tp, recall_scores, recall_combined}]"""
    bad = [label_bad(r, bad_iou) for r in records]
    nb = max(1, sum(bad))
    base = flags_for(records, margin, iou_min, lost_max_gap)
    rows = []
    for t in thresholds:
        a = area_jump_flags(records, t)
        tp = sum(1 for x, b in zip(a, bad) if x and b)
        add = [x and not y for x, y in zip(a, base)]
        comb = [x or y for x, y in zip(a, base)]
        rows.append({"threshold": t, "flagged": sum(a), "tp": tp, "precision": round(tp / sum(a), 3) if sum(a) else 1.0,
                     "added_flags": sum(add), "added_tp": sum(1 for x, b in zip(add, bad) if x and b),
                     "recall_scores": round(sum(1 for x, b in zip(base, bad) if x and b) / nb, 3),
                     "recall_combined": round(sum(1 for x, b in zip(comb, bad) if x and b) / nb, 3)})
    return rows
