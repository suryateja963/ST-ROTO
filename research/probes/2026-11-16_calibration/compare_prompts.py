"""T-082: compare prompt types on the SA-V subset (same 51 sequences, tiny model, CUDA): one click, three clicks,
box only, box + click. Reads <folder>/calibration.json of each run; writes compare_prompts.json next to this file.
Run: .venv/Scripts/python.exe research/probes/2026-11-16_calibration/compare_prompts.py"""
import json, os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = [("1 click", "sav"), ("3 clicks", "sav_points3"), ("box only", "sav_box_only"), ("box + click", "sav_box")]


def summarise(recs):
    seqs = sorted({r["seq"] for r in recs})
    first, per_seq, wrong = {}, {}, 0
    for s in seqs:
        rs = sorted([r for r in recs if r["seq"] == s], key=lambda r: r["frame"])
        first[s] = rs[0]["iou_true"]
        vis = [r["iou_true"] for r in rs if r["truth_visible"]]
        per_seq[s] = float(np.mean(vis)) if vis else None
    wrong = sum(v < 0.5 for v in first.values())
    vis = [r["iou_true"] for r in recs if r["truth_visible"]]
    good_seqs = [s for s in seqs if first[s] >= 0.5]
    return {"sequences": len(seqs), "frames": len(recs), "visible_frames": len(vis),
            "wrong_object_first_frame": int(wrong),
            "first_frame_iou_mean": round(float(np.mean(list(first.values()))), 4),
            "first_frame_iou_median": round(float(np.median(list(first.values()))), 4),
            "mean_iou_visible": round(float(np.mean(vis)), 4),
            "frames_iou_ge_0.9": round(float(np.mean([v >= 0.9 for v in vis])), 4),
            "frames_iou_lt_0.5": round(float(np.mean([v < 0.5 for v in vis])), 4),
            "mean_iou_visible_correct_start": round(float(np.mean(
                [r["iou_true"] for r in recs if r["truth_visible"] and r["seq"] in good_seqs])), 4),
            "seq_mean": per_seq}


def main():
    out, cols = {}, []
    for label, folder in RUNS:
        p = os.path.join(HERE, folder, "calibration.json")
        if not os.path.exists(p):
            print("%-12s missing (%s)" % (label, folder)); continue
        d = json.load(open(p))
        s = summarise(d["records"])
        s.update({"folder": folder, "prompt": d.get("prompt", "point"), "devices": d.get("devices")})
        out[label] = s
        cols.append(label)
    keys = ["sequences", "visible_frames", "wrong_object_first_frame", "first_frame_iou_mean", "first_frame_iou_median",
            "mean_iou_visible", "frames_iou_ge_0.9", "frames_iou_lt_0.5", "mean_iou_visible_correct_start"]
    print("%-32s" % "" + "".join("%14s" % c for c in cols))
    for k in keys:
        print("%-32s" % k + "".join("%14s" % out[c][k] for c in cols))
    if len(cols) > 1:                                    # per-sequence wins vs box + click
        ref = out.get("box + click")
        if ref:
            for c in cols:
                if c == "box + click":
                    continue
                d = [out[c]["seq_mean"][s] - ref["seq_mean"][s] for s in ref["seq_mean"]
                     if out[c]["seq_mean"].get(s) is not None and ref["seq_mean"][s] is not None]
                out[c]["vs_box_click"] = {"better_by_0.05": int(sum(x > 0.05 for x in d)),
                                          "worse_by_0.05": int(sum(x < -0.05 for x in d)),
                                          "mean_diff": round(float(np.mean(d)), 4)}
                print("%-12s vs box + click (per sequence): %s" % (c, out[c]["vs_box_click"]))
    for c in out:
        out[c].pop("seq_mean", None)
    json.dump(out, open(os.path.join(HERE, "compare_prompts.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
