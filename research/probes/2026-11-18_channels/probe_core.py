"""T-110: st_roto.channels measured on the synthetic CG shot (exact truth), outside Nuke.

1. vector convention detection (frames f -> f+1 RGB + forward vectors), every frame;
2. reports on CORRECT shapes (24-point splines fitted to the truth masks): false CHECK flags per rule;
3. injected errors (shape on one frame replaced): wrong object (distractor), shifted 30 px, previous frame's shape
   held (stuck), scaled x1.3 -> which rule catches them.
Writes result_core.json.
"""
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import channels as ch, exr  # noqa: E402
from st_roto.geometry import mask_to_points  # noqa: E402

D = os.path.join(HERE, "out", "cg")
meta = json.load(open(os.path.join(D, "meta.json")))
N, W, H = meta["frames"], meta["w"], meta["h"]
CH = {f: exr.read_channels(os.path.join(D, "cg.%04d.exr" % f)) for f in range(N)}


def rgb(f):
    c = CH[f]
    return np.stack([c["R"], c["G"], c["B"]], -1)


def gt(f):
    return cv2.imread(os.path.join(D, "gt_%04d.png" % f), 0) > 127


R = {"convention_single_frame": {}}
t = time.time()
errs = []
for f in range(N - 1):
    e = ch.vector_errors(rgb(f), rgb(f + 1), CH[f]["forward.u"], CH[f]["forward.v"])
    errs.append(e)
    d = ch.choose_convention([e])
    R["convention_single_frame"][f] = {k: d[k] for k in ("convention", "margin_u", "margin_v", "undetermined")}
R["convention_seconds_per_frame"] = (time.time() - t) / (N - 1)
agg = ch.choose_convention(errs)
R["convention_all_frames"] = {k: agg[k] for k in ("convention", "margin_u", "margin_v", "undetermined")}
R["convention_correct"] = agg["convention"] == meta["vector_convention"] and not agg["undetermined"]
sf = R["convention_single_frame"].values()
R["single_frame_decided_both"] = sum(1 for v in sf if not v["undetermined"])
R["single_frame_wrong_when_decided"] = sum(1 for v in sf if not v["undetermined"] and v["convention"] != meta["vector_convention"])

def pieces(m, min_px=150):
    n, lab = cv2.connectedComponents(m.astype(np.uint8))
    return [mask_to_points((lab == i).astype(np.float32) - 0.5, count=24) for i in range(1, n)
            if (lab == i).sum() >= min_px]


KEYS = {f: pieces(gt(f)) for f in range(N)}
SPEC = dict(stats=("depth.Z", "N.Z", "P.Y"), motion={"u": "forward.u", "v": "forward.v",
                                                     "convention": meta["vector_convention"],
                                                     "bu": "backward.u", "bv": "backward.v"},
            crypto={"layer": "CryptoObject", "names": ["target"]})


def run(keys):
    return ch.check_object(range(N), lambda f: keys.get(f, []), lambda f: CH[f], H, W, **SPEC)


t = time.time()
clean = run(KEYS)
R["check_seconds_per_frame"] = (time.time() - t) / N
R["clean"] = {"flags": ch.review_flags(clean),
              "min_motion_iou": min(r["motion_iou"] for r in clean.values() if "motion_iou" in r),
              "min_crypto_iou": min(r["crypto_iou"] for r in clean.values()),
              "depth": [clean[f]["stats"]["depth.Z"] for f in range(N)]}


def bad_keys(kind, f):
    k = dict(KEYS)
    m = gt(f)
    if kind == "wrong_object":
        p = (787.5 - 450 * f / (N - 1.0), 420 - 90 * np.sin(np.pi * f / (N - 1.0)))
        m = np.zeros((H, W), np.uint8); cv2.circle(m, (int(p[0]), int(p[1])), 64, 1, -1); m = m > 0
    elif kind == "shifted_30px":
        m = np.roll(m, 30, axis=1)
    elif kind == "stuck_previous_frame":
        k[f] = KEYS[f - 1]
        return k
    elif kind == "scaled_1.3":
        ys, xs = np.nonzero(m); cx, cy = xs.mean(), ys.mean()
        M = cv2.getRotationMatrix2D((float(cx), float(cy)), 0, 1.3)
        m = cv2.warpAffine(m.astype(np.uint8), M, (W, H), flags=cv2.INTER_NEAREST) > 0
    k[f] = pieces(m)
    return k


R["injected"] = {}
clean_flags = set(R["clean"]["flags"])
for kind in ("wrong_object", "shifted_30px", "stuck_previous_frame", "scaled_1.3"):
    rows = []
    for f in (5, 12, 18):
        rep = run(bad_keys(kind, f))
        fl = [x for x in ch.review_flags(rep) if x not in clean_flags]
        rules = {"depth": any("depth.Z" in r for g, r in fl if g == f),
                 "motion": any("motion" in r for g, r in fl if g in (f, f + 1)),
                 "crypto": any("Cryptomatte" in r for g, r in fl if g == f)}
        rows.append({"frame": f, "caught": any(rules.values()), "by_rule": rules,
                     "values": {k: rep[f].get(k) for k in ("motion_iou", "crypto_iou")},
                     "depth": rep[f]["stats"].get("depth.Z")})
    R["injected"][kind] = {"caught": sum(r["caught"] for r in rows), "of": len(rows), "rows": rows}
json.dump(R, open(os.path.join(HERE, "result_core.json"), "w"), indent=1)
print("convention all frames:", R["convention_all_frames"], "correct", R["convention_correct"],
      "| single frames decided both axes:", R["single_frame_decided_both"], "wrong:", R["single_frame_wrong_when_decided"],
      "%.2f s/frame" % R["convention_seconds_per_frame"])
print("clean flags:", R["clean"]["flags"])
print("clean min motion IoU", R["clean"]["min_motion_iou"], "min crypto IoU", R["clean"]["min_crypto_iou"],
      "check %.2f s/frame" % R["check_seconds_per_frame"])
for k, v in R["injected"].items():
    print(k, v["caught"], "/", v["of"], [(r["frame"], {a: b for a, b in r["by_rule"].items() if b}, r["values"]) for r in v["rows"]])

# variant: forward vectors only (no backward layer -> no occlusion handling)
fwd_only = dict(SPEC, motion={"u": "forward.u", "v": "forward.v", "convention": meta["vector_convention"]})
rep = ch.check_object(range(N), lambda f: KEYS.get(f, []), lambda f: CH[f], H, W, **fwd_only)
R["clean_forward_only"] = {"flags": ch.review_flags(rep),
                           "min_motion_iou": min(r["motion_iou"] for r in rep.values() if "motion_iou" in r)}
json.dump(R, open(os.path.join(HERE, "result_core.json"), "w"), indent=1)
print("forward vectors only, clean flags:", R["clean_forward_only"]["flags"])
