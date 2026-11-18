"""Per-frame agreement of the DirectML and CUDA runs (probe_dml.py outputs)."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
out = {}
for model in ("tiny", "large"):
    r = {rt: json.load(open(os.path.join(HERE, "result_%s_%s.json" % (rt, model)))) for rt in ("cuda", "directml")}
    if any("exception" in x for x in r.values()):
        out[model] = {rt: x.get("exception", "")[-300:] for rt, x in r.items()}; continue
    m = {rt: np.load(os.path.join(HERE, "result_%s_%s_masks.npz" % (rt, model))) for rt in r}
    agree = [float((m["cuda"][k] & m["directml"][k]).sum() / max(1, (m["cuda"][k] | m["directml"][k]).sum()))
             for k in m["cuda"].files]
    row = {"frames": len(agree), "iou_dml_vs_cuda_mean": round(float(np.mean(agree)), 5),
           "iou_dml_vs_cuda_min": round(float(np.min(agree)), 5)}
    for rt, x in r.items():
        i = list(x["iou_vs_gt"].values())
        row[rt] = {"ort": x["ort_version"], "device": x["device"], "fallback": x["device_fallback"],
                   "iou_vs_gt_mean": round(float(np.mean(i)), 4), "iou_vs_gt_min": round(float(np.min(i)), 4),
                   "ms_per_frame_warm": x["ms_per_frame_warm"], "seconds_first_run": x["seconds_total"]}
    out[model] = row
json.dump(out, open(os.path.join(HERE, "comparison.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
