"""T-068 analysis of the SA-V calibration runs (tools/benchmark/calibrate_review.py output).
Evaluates the review rules at several definitions of a BAD frame (IoU < 0.5 / 0.7 / 0.9) because a 16-anchor spline
cannot follow SA-V's detailed masks (correct first frames reach only ~0.85-0.93). Sequences whose prompted frame is
already wrong (first-frame IoU < 0.5: wrong object prompted) are excluded - that is a prompt problem, not tracking.
SA-V frames are 6-fps samples (every 4th 24-fps frame): the LOST gap is compared OLD (every absent frame between
present ones) vs NEW (quality.LOST_MAX_GAP = 16 shot frames = 4 samples).
Run: .venv/Scripts/python.exe research/probes/2026-11-16_calibration/analyse_sav.py <calibration.json> [out.json]
"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from st_roto.calibration import evaluate, evaluate_area_jumps   # noqa: E402


def main(path, out=None):
    d = json.load(open(path))
    recs = d["records"]
    first = {}
    for r in sorted(recs, key=lambda r: r["frame"]):
        first.setdefault(r["seq"], r["iou_true"])
    keep = [r for r in recs if first[r["seq"]] >= 0.5]
    vis = [r["iou_true"] for r in keep if r["truth_visible"]]
    res = {"source": path, "prompt": d.get("prompt", "point"), "devices": d.get("devices"),
           "sequences": len(first), "sequences_kept": sum(1 for v in first.values() if v >= 0.5),
           "frames_kept": len(keep), "mean_iou_visible": round(sum(vis) / len(vis), 3)}
    print("prompt %s: kept %d/%d sequences, %d frames, mean IoU %.3f" % (res["prompt"], res["sequences_kept"],
          res["sequences"], len(keep), res["mean_iou_visible"]))
    for rule, gap in (("old", 10 ** 6), ("new", 4)):
      res["by_bad_iou_" + rule] = {}
      print("\n===== LOST rule", rule)
      for bad_iou in (0.5, 0.7, 0.9):
        ev = evaluate(keep, bad_iou=bad_iou, lost_max_gap=gap)
        cur = [g for g in ev["grid"] if g["margin"] == 1.0 and g["iou_min"] == 0.7][0]
        area = evaluate_area_jumps(keep, bad_iou=bad_iou, lost_max_gap=gap)
        res["by_bad_iou_" + rule][str(bad_iou)] = {"bad": ev["bad"], "current": cur, "best": ev["best"],
                                           "corr": ev["iou_pred_vs_true_corr"], "grid": ev["grid"], "area": area}
        print("\nBAD = IoU < %.1f: %d bad frames; corr(iou_pred, iou) %s" % (bad_iou, ev["bad"], ev["iou_pred_vs_true_corr"]))
        print("  current (1.0, 0.7):", {k: cur[k] for k in ("flagged", "tp", "precision", "recall", "f1")})
        print("  best:", ev["best"])
        for a in area:
            print("  area %.2f: flags %d precision %.3f | adds %d flags, %d real; recall %.3f -> %.3f"
                  % (a["threshold"], a["flagged"], a["precision"], a["added_flags"], a["added_tp"],
                     a["recall_scores"], a["recall_combined"]))
    if out:
        json.dump(res, open(out, "w"), indent=1)
    return res


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
