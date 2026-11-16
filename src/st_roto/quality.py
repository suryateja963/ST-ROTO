"""Which AI frames should an artist review? (master prompt §9: confidence estimates, failure detection). Pure Python.

The thresholds are HEURISTICS from the synthetic test shot (research/probes/2026-11-16_corrections: a frame whose
object score was 0.025 flipped between "present" and "absent" on tiny input differences; neighbours scored 0.96
and 1.09). They must be calibrated on real footage by the benchmark programme before being trusted.
"""
from __future__ import annotations

OBJECT_SCORE_MARGIN = 1.0      # |score| below this: the present/absent decision is fragile
IOU_PRED_MIN = 0.7             # the model's own quality estimate of its mask
AREA_JUMP = 0.35               # T-078: relative area change vs BOTH nearest present neighbours (uncalibrated)


LOST, CHECK = "lost", "check"
# Measured on the synthetic shot (research/probes/2026-11-16_corrections/forward_reports.json): after an occlusion the
# object score fell to 0.15-0.94 on frames whose masks were still IoU 0.993-0.996 vs ground truth, while in reverse the
# same region was really lost. Hence two levels: LOST = object missing between visible frames (fix it);
# CHECK = model uncertain or low predicted quality (glance at it). Predicted IoU correlated only 0.50 with real IoU there.


def area_jumps(areas: dict, threshold: float = None) -> dict:
    """{frame: relative change} for frames whose area differs by more than `threshold` from BOTH nearest frames
    that have an area (> 0). Catches confidently wrong frames the model's own scores miss (T-078: the synthetic
    split frame, score 8.0, predicted IoU 0.98, true IoU 0.42). Uncalibrated: CHECK level only."""
    t = AREA_JUMP if threshold is None else threshold
    fs = sorted(f for f, a in areas.items() if a and a > 0)
    out = {}
    for i, f in enumerate(fs):
        if i == 0 or i == len(fs) - 1:
            continue
        a, p, n = areas[f], areas[fs[i - 1]], areas[fs[i + 1]]
        dp, dn = abs(a - p) / max(a, p), abs(a - n) / max(a, n)
        if dp > t and dn > t:
            out[f] = round(min(dp, dn), 3)
    return out


def review_frames(reports: list, keyed_frames, areas: dict = None) -> list:
    """reports: [{"frame", "object_score", "iou_pred"}], keyed_frames: frames that currently have a key,
    areas: optional {frame: shape area} (AI frames). Returns [(frame, level, reason), ...] sorted by frame;
    level is LOST or CHECK."""
    jumps = area_jumps(areas) if areas else {}
    keyed = set(keyed_frames)
    present = sorted(r["frame"] for r in reports if (r["object_score"] or 0) > 0)
    out = []
    for r in sorted(reports, key=lambda r: r["frame"]):
        f, s, q = r["frame"], r["object_score"], r["iou_pred"]
        reasons, level = [], CHECK
        if s is not None and s <= 0 and present and present[0] < f < present[-1]:
            reasons.append("object lost between frames where it is visible"); level = LOST
        if s is not None and abs(s) < OBJECT_SCORE_MARGIN:
            reasons.append("uncertain whether the object is visible (score %.2f)" % s)
        if q is not None and f in keyed and q < IOU_PRED_MIN:
            reasons.append("low predicted mask quality (%.2f)" % q)
        if f in jumps:
            reasons.append("shape area jumps %.0f%% against both neighbouring frames" % (100 * jumps[f]))
        if reasons:
            out.append((f, level, "; ".join(reasons)))
    return out


def summary(flags: list) -> str:
    """'lost 16-20, 22; check 15, 21' or ''."""
    lost = [f for f, lvl, _ in flags if lvl == LOST]
    check = [f for f, lvl, _ in flags if lvl == CHECK]
    parts = (["lost " + ranges(lost)] if lost else []) + (["check " + ranges(check)] if check else [])
    return "; ".join(parts)


def ranges(frames) -> str:
    """[3,4,5,9] -> '3-5, 9' for compact status messages."""
    fs = sorted(set(frames))
    if not fs:
        return ""
    parts, start, prev = [], fs[0], fs[0]
    for f in fs[1:] + [None]:
        if f is not None and f == prev + 1:
            prev = f; continue
        parts.append(str(start) if start == prev else "%d-%d" % (start, prev))
        if f is not None:
            start = prev = f
    return ", ".join(parts)
