"""Why does a good forward track get review flags on frames 25-30? Print per-frame score / predicted IoU / IoU vs GT.
Run: Nuke17.1.exe --nc -t probe_forward_reports.py"""
import json, os, sys
ROOT = "D:/ST-ROTO"
sys.path[:0] = [ROOT + "/src"]; sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                   # noqa: E402,F401
import numpy as np, cv2                       # noqa: E402
from st_roto_ai.sam2 import Sam2Video         # noqa: E402
from st_roto import quality                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
FR = ROOT + "/research/probes/2026-11-15_video/frames"
meta = json.load(open(FR + "/meta.json")); N, W, H = meta["frames"], meta["w"], meta["h"]
trk = Sam2Video(ROOT + "/models/onnx/sam2.1-hiera-tiny/video", device="cuda", num_total_frames=N)
rows = []
for f in range(N):
    rgb = cv2.cvtColor(cv2.imread(FR + "/frame_%04d.png" % f), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    e = trk.encode(rgb)
    o = trk.add_points(0, e, [tuple(meta["click_xy"])], [1]) if f == 0 else trk.track(f, e)
    gt = cv2.imread(FR + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
    m = o["logits"] > 0
    rows.append({"frame": f, "object_score": round(o["object_score"], 3), "iou_pred": round(o["iou_pred"] or 0, 3),
                 "iou_vs_gt": round(float((m & gt).sum() / max(1, (m | gt).sum())), 4),
                 "occluded": meta["objects"][str(f)]["occluder_on"]})
flags = dict(quality.review_frames(rows, [r["frame"] for r in rows]))
for r in rows:
    r["flag"] = flags.get(r["frame"], "")
json.dump(rows, open(HERE + "/forward_reports.json", "w"), indent=1)
print("DONE")
