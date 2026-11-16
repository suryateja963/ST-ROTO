"""First-frame IoU on the SA-V subset: one interior click vs truth bounding box + click (SAM box corner labels 2/3).
Separates "wrong object prompted" from tracking failures before calibrating (T-068).
Run: Nuke17.1.exe --nc -t research/probes/2026-11-16_calibration/probe_prompt_first_frame.py
"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "benchmark"))
import calibrate_review as cr   # noqa: E402

seqs = cr.folder_sequences(os.path.join(ROOT, "data", "benchmarks", "sa-v"))
out = {}
for kind in ("point", "box"):
    recs = cr.run([(n, o[:1], fr, gt) for n, o, fr, gt in seqs], "auto", kind)
    out[kind] = {r["seq"]: r["iou_true"] for r in recs}
low = {k: sum(1 for v in out[k].values() if v < 0.5) for k in out}
mean = {k: round(sum(out[k].values()) / len(out[k]), 3) for k in out}
res = {"devices": sorted(cr.DEVICES), "sequences": len(seqs), "first_frame_iou": out, "below_0.5": low, "mean": mean}
json.dump(res, open(os.path.join(os.path.dirname(__file__), "sav", "prompt_first_frame.json"), "w"), indent=1)
print("RESULT below 0.5:", low, "mean:", mean, "devices:", res["devices"])
