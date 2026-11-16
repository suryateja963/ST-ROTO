"""Why do 57 % of review flags on SA-V fall on frames where the object is REALLY absent? The LOST rule flags every
absent frame between present frames. Can gap length (absent run) or score strength separate true dropouts
(object visible, AI says absent) from true absences (object left/occluded)?
Run: .venv/Scripts/python.exe research/probes/2026-11-16_calibration/probe_lost_rule.py <calibration.json>
"""
import json, sys
from collections import Counter

d = json.load(open(sys.argv[1]))
first = {}
for r in sorted(d["records"], key=lambda r: r["frame"]):
    first.setdefault(r["seq"], r["iou_true"])
seqs = {}
for r in d["records"]:
    if first[r["seq"]] >= 0.5:
        seqs.setdefault(r["seq"], []).append(r)

rows = []          # (run length, min |score| in run, frames truly visible in run, frames in run)
for s, rs in seqs.items():
    rs.sort(key=lambda r: r["frame"])
    present = [i for i, r in enumerate(rs) if r["object_score"] > 0]
    if not present:
        continue
    i = present[0]
    while i <= present[-1]:
        if rs[i]["object_score"] > 0:
            i += 1; continue
        j = i
        while j <= present[-1] and rs[j]["object_score"] <= 0:
            j += 1
        run = rs[i:j]
        rows.append((len(run), min(abs(r["object_score"]) for r in run), sum(r["truth_visible"] for r in run), len(run)))
        i = j

print("absent runs between present frames:", len(rows))
for lo, hi in ((1, 1), (2, 2), (3, 4), (5, 8), (9, 1000)):
    sel = [r for r in rows if lo <= r[0] <= hi]
    fr = sum(r[3] for r in sel); vis = sum(r[2] for r in sel)
    print("run %d-%d frames (6 fps): %3d runs, %4d frames, truly visible %4d (%.0f %%)"
          % (lo, hi, len(sel), fr, vis, 100.0 * vis / max(1, fr)))
for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 10), (10, 1e9)):
    sel = [r for r in rows if lo <= r[1] < hi]
    fr = sum(r[3] for r in sel); vis = sum(r[2] for r in sel)
    print("min |score| in run %g-%g: %3d runs, %4d frames, truly visible %4d (%.0f %%)"
          % (lo, hi, len(sel), fr, vis, 100.0 * vis / max(1, fr)))
