"""Summarise result_point_counts_<model>.json files (T-080): mean IoU per shape builder, the gap between the AI mask
and the spline, how often a fixed count beats today's auto count by a visible margin, and tiny vs large per sequence.
Run: .venv/Scripts/python.exe research/probes/2026-11-16_shape_fit/analyse_point_counts.py
Writes analysis_point_counts.json next to this file."""
import glob, json, os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ["raw", "outline", "auto", "16", "24", "32", "48", "64"]


def summarise(res):
    rows = res["rows"]
    found = [r for r in rows if r["raw"] >= 0.5]
    out = {"model": res["model"], "devices": res["devices"], "frames": len(rows), "frames_found": len(found),
           "seconds": res["seconds"]}
    for name, sel in (("all", rows), ("found", found)):
        out[name] = {k: round(float(np.mean([r[k] for r in sel])), 4) for k in KEYS}
    # per-frame: how far is the auto spline below the AI mask, and does any fixed count beat auto clearly?
    gap = np.array([r["raw"] - r["auto"] for r in found])
    out["auto_below_raw"] = {"mean": round(float(gap.mean()), 4), "p95": round(float(np.percentile(gap, 95)), 4),
                             "frames_over_0.01": int((gap > 0.01).sum()), "frames_over_0.02": int((gap > 0.02).sum())}
    out["beats_auto_by_0.01"] = {k: int(sum(r[k] - r["auto"] > 0.01 for r in found)) for k in KEYS[3:]}
    out["worse_than_auto_by_0.01"] = {k: int(sum(r["auto"] - r[k] > 0.01 for r in found)) for k in KEYS[3:]}
    # per auto count: is auto under-choosing for some shapes?
    by = {}
    for seq, c in res["auto_counts"].items():
        sel = [r for r in found if r["seq"] == seq]
        if sel:
            by.setdefault(c["auto"], []).extend(sel)
    out["by_auto_count"] = {str(c): {"frames": len(s), "auto": round(float(np.mean([r["auto"] for r in s])), 4),
                                     "64": round(float(np.mean([r["64"] for r in s])), 4),
                                     "raw": round(float(np.mean([r["raw"] for r in s])), 4)}
                            for c, s in sorted(by.items())}
    out["seq_mean_raw"] = {s: round(float(np.mean([r["raw"] for r in rows if r["seq"] == s])), 4)
                           for s in res["auto_counts"]}
    return out


def main():
    res = {}
    for p in sorted(glob.glob(os.path.join(HERE, "result_point_counts_*.json"))):
        s = summarise(json.load(open(p)))
        res[s["model"]] = s
        print("== %s (%s): %d frames, %d found, %d s" % (s["model"], ", ".join(s["devices"]), s["frames"],
                                                         s["frames_found"], s["seconds"]))
        for name in ("all", "found"):
            print("  %-5s " % name + "  ".join("%s %.4f" % (k, s[name][k]) for k in KEYS))
        print("  auto below raw:", s["auto_below_raw"])
        print("  beats auto by >0.01 (frames):", s["beats_auto_by_0.01"])
        print("  worse than auto by >0.01:", s["worse_than_auto_by_0.01"])
        print("  by auto count:", s["by_auto_count"])
    if len(res) == 2:
        a, b = sorted(res)                                    # sam2.1-hiera-large, sam2.1-hiera-tiny
        la, ti = res[a]["seq_mean_raw"], res[b]["seq_mean_raw"]
        common = sorted(set(la) & set(ti))
        d = np.array([la[s] - ti[s] for s in common])
        cmp_ = {"sequences": len(common), "large_better_by_0.05": int((d > 0.05).sum()),
                "tiny_better_by_0.05": int((d < -0.05).sum()), "mean_diff_large_minus_tiny": round(float(d.mean()), 4),
                "median_diff": round(float(np.median(d)), 4)}
        res["large_vs_tiny"] = cmp_
        print("large vs tiny (per-sequence mean raw IoU):", cmp_)
    json.dump(res, open(os.path.join(HERE, "analysis_point_counts.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
