"""T-121 core measurements on the synthetic CG shot (research/probes/2026-11-18_channels, exact truth), outside Nuke.

1. Shapes straight from Cryptomatte: per frame, the coverage of 'target' (> 0.5) -> pieces.Sequencer (the tracker's
   own shape builder: main + part shapes, fixed point count) -> IoU of the shapes vs truth.
2. Propagation of ONE key along the motion vectors: the truth shape of frame 0 (and of frame 23 backwards) is
   moved frame by frame with st_roto.channels.warp_points (forward vectors, measured convention) -> IoU vs truth per
   frame: how far a hand-drawn key can be carried before it drifts.
Writes result_core.json."""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import channels as ch, exr, pieces  # noqa: E402
from st_roto.geometry import mask_to_points  # noqa: E402
from st_roto.stereo import mask_from_keys  # noqa: E402

D = os.path.join(HERE, "..", "2026-11-18_channels", "out", "cg")
meta = json.load(open(os.path.join(D, "meta.json")))
N, W, H = meta["frames"], meta["w"], meta["h"]
CH = {f: exr.read_channels(os.path.join(D, "cg.%04d.exr" % f)) for f in range(N)}
CONV = meta["vector_convention"]


def gt(f):
    return cv2.imread(os.path.join(D, "gt_%04d.png" % f), 0) > 127


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


R = {}
# 1. Cryptomatte -> shapes
for count in ("auto", 24):
    seq = pieces.Sequencer(count=count, parts=True)
    last = None
    for f in range(N):
        cov = ch.crypto_mask(CH[f], "CryptoObject", "target")
        present = bool((cov > 0.5).any())
        if seq.add(f, (cov - 0.5) * 8.0, ref=last, present=present):
            last = f
    res = seq.result(list(range(N)))
    ious = []
    for f in range(N):
        keys = [res["main"].get(f)] + [p.get(f) for p in res["parts"]]
        ious.append(iou(mask_from_keys([k for k in keys if k], H, W), gt(f)))
    R["crypto_shapes_count_%s" % count] = {"mean_iou": round(float(np.mean(ious)), 4), "min_iou": round(min(ious), 4),
                                           "parts": len(res["parts"]), "points": seq.count}


# 2. propagation along vectors
def propagate(start, direction, robust=True):
    k0 = mask_to_points(gt(start).astype(np.float32) - 0.5, count=24)
    keys, cur = {start: k0}, [k0]
    f = start
    while 0 <= f + direction < N:
        lay = "forward" if direction > 0 else "backward"
        u, v = CH[f][lay + ".u"], CH[f][lay + ".v"]
        m = mask_from_keys(cur, H, W)
        cur = [(ch.warp_points_robust(k, u, v, CONV, m) if robust else ch.warp_points(k, u, v, CONV, mask=m))
               for k in cur]
        f += direction
        keys[f] = cur[0]
    return {f: round(iou(mask_from_keys([k], H, W), gt(f)), 4) for f, k in sorted(keys.items())}


R["propagate_forward_from_0 (plain)"] = propagate(0, 1, robust=False)
R["propagate_forward_from_0 (robust)"] = propagate(0, 1)
R["propagate_backward_from_23 (plain)"] = propagate(N - 1, -1, robust=False)
R["propagate_backward_from_23 (robust)"] = propagate(N - 1, -1)
json.dump(R, open(os.path.join(HERE, "result_core.json"), "w"), indent=1)
for k, v in R.items():
    print(k, v if not isinstance(v, dict) or len(v) < 6 else {f: v[f] for f in list(v)[::3]})
