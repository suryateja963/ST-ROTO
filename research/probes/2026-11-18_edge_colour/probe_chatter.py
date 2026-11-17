"""T-115: does 'Reduce chatter' help where chatter exists? Controlled measurement with exact truth.

A slowly moving, rotating ellipse (24 frames). Per frame the 'AI mask' = truth with a small random boundary wobble
(the edge displaced by smooth noise of sigma `noise` px, new noise every frame - what per-frame mask predictions
do on a steady edge). Keys are fitted exactly like ST-ROTO's tracker (geometry.mask_to_points, fixed count, start
hint = previous frame's first point). Measured against the truth before / after st_roto.chatter.smooth_keys:
mean IoU, temporal error (st_roto.metrics, the benchmark methodology's flicker measure) and jitter.
Writes result_chatter.json."""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import chatter, metrics  # noqa: E402
from st_roto.geometry import mask_to_points  # noqa: E402
from st_roto.stereo import mask_from_keys  # noqa: E402

H, W, N, K = 360, 480, 24, 24


def truth_field(f):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    cx, cy, ang = 200 + 2.5 * f, 180 + 0.8 * f, np.radians(10 + 1.5 * f)
    u = ((xx - cx) * np.cos(ang) + (yy - cy) * np.sin(ang)) / 110.0
    v = (-(xx - cx) * np.sin(ang) + (yy - cy) * np.cos(ang)) / 70.0
    return (1 - np.sqrt(u * u + v * v)) * 70.0                       # ~ signed distance in px near the edge


def run(noise, seed=3):
    rng = np.random.default_rng(seed)
    keys, truth = {}, {}
    hint = None
    for f in range(N):
        fld = truth_field(f)
        truth[f] = fld > 0
        wob = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 12)
        wob *= noise / max(float(wob.std()), 1e-6)
        pts = mask_to_points(fld + wob, count=K, start_hint=hint)
        hint = np.array(pts[0][:2])
        keys[f] = pts
    out = {}
    for label, ks in (("before", keys), ("radius 2", None), ("radius 3", None)):
        if ks is None:
            r = int(label.split()[1])
            ks = dict(keys); ks.update(chatter.smooth_keys(keys, radius=r))
        masks = [mask_from_keys([ks[f]], H, W) for f in range(N)]
        ious = [float((m & truth[f]).sum() / (m | truth[f]).sum()) for f, m in enumerate(masks)]
        out[label] = {"mean_iou": round(float(np.mean(ious)), 5), "min_iou": round(min(ious), 5),
                      "temporal_error": round(metrics.temporal_error([m.astype(np.float32) for m in masks],
                                                                     [truth[f].astype(np.float32) for f in range(N)]), 6),
                      "jitter_px": round(chatter.jitter(ks), 4)}
    return out


R = {"clean (no wobble)": run(0.0)}
for nz in (0.5, 1.0, 2.0):
    R["wobble sigma %.1f px" % nz] = run(nz)
json.dump(R, open(os.path.join(HERE, "result_chatter.json"), "w"), indent=1)
for k, v in R.items():
    print(k)
    for lab, m in v.items():
        print("   %-9s %s" % (lab, m))
