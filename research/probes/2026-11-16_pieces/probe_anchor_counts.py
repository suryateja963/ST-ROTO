"""T-049: point-count choice vs accuracy on the synthetic shot (48 frames, GPU in Nuke's Python).
Compares fixed 12 / 16 / 24 / 32 points and 'auto' (tolerances 0.3 px mean / 1.5 px max, and a stricter 0.2 / 1.0),
union of main + part shapes vs truth. Run: Nuke17.1.exe --nc -t research/probes/2026-11-16_pieces/probe_anchor_counts.py
"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402
from st_roto import pieces                        # noqa: E402
from st_roto.geometry import Anchor, rasterize_spline   # noqa: E402
from st_roto_nuke.track import track_objects      # noqa: E402

FR = ROOT + "/research/probes/2026-11-15_video/frames"
meta = json.load(open(FR + "/meta.json"))
N, W, H = meta["frames"], meta["w"], meta["h"]
cache = {}


def get_rgb(f):
    if f not in cache:
        x = cv2.cvtColor(cv2.imread(FR + "/frame_%04d.png" % f), cv2.COLOR_BGR2RGB) / 255.0
        cache[f] = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)
    return cache[f]


def raster(points):
    return rasterize_spline([Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False)
                             for p in points], H, W)


gts = [cv2.imread(FR + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127 for f in range(N)]
out = {}
variants = [("fixed12", 12, None), ("fixed16", 16, None), ("fixed24", 24, None), ("fixed32", 32, None),
            ("auto_0.3", "auto", (0.3, 1.5)), ("auto_0.2", "auto", (0.2, 1.0))]
orig = pieces.choose_count
for name, anchors, tol in variants:
    if tol:
        pieces.choose_count = lambda loop, mean_tol=tol[0], max_tol=tol[1], counts=pieces.COUNTS: orig(loop, mean_tol, max_tol, counts)
    res = track_objects(get_rgb, list(range(N)), [{"name": "t", "frame": 0, "points": [tuple(meta["click_xy"])], "labels": [1]}],
                        anchors=anchors)["objects"][0]
    pieces.choose_count = orig
    ious = []
    for f in range(N):
        m = np.zeros((H, W), bool)
        if f in res["keys"]:
            m |= raster(res["keys"][f])
        for part in res["parts"]:
            if f in part and not pieces.is_collapsed(part[f]):
                m |= raster(part[f])
        ious.append(float((m & gts[f]).sum() / max(1, (m | gts[f]).sum())))
    out[name] = {"points": res["anchors"], "parts": len(res["parts"]), "mean_iou": round(float(np.mean(ious)), 4),
                 "min_iou": round(float(np.min(ious)), 4), "worst_frame": int(np.argmin(ious)),
                 "iou_f23": round(ious[23], 4)}
    print(name, out[name], flush=True)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_anchor_counts.json"), "w"), indent=1)
