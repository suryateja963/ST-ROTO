"""T-115: edge decontamination and spill correction measured on synthetic composites with exact truth.

Foreground F: textured warm colours; alpha: a soft-edged blob plus thin hair-like strands (fractional alpha);
backgrounds B: a green screen (textured) and a natural textured background. I = a F + (1 - a) B (+ spill for the
despill case). Metrics over the soft edge (0.05 < a < 0.95), alpha-weighted:
  * fg_error: |F_est - F| (colour of the foreground),
  * fringe: recomposite over a new grey background N, |a F_est + (1-a) N - (a F + (1-a) N)| (what an artist sees).
Straight plate colour (F_est = I, what ST-ROTO wrote before T-115) vs decontaminated.
Writes result_edge_colour.json.
"""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import matte  # noqa: E402

H, W = 360, 480
rng = np.random.default_rng(5)


def smooth_noise(scale, amp):
    n = rng.normal(0, 1, (H, W, 3)).astype(np.float32)
    return cv2.GaussianBlur(n, (0, 0), scale) * amp


def scene():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    a = ((xx - 240) ** 2 / 120 ** 2 + (yy - 190) ** 2 / 95 ** 2 < 1).astype(np.float32)
    a = cv2.GaussianBlur(a, (0, 0), 3.0)
    hair = np.zeros((H, W), np.float32)
    for i in range(40):                                    # strands leaving the top of the blob
        x0 = 150 + 4.5 * i + rng.normal(0, 2)
        pts = np.array([[x0 + 15 * np.sin(t / 10.0 + i), 110 - t] for t in range(0, 70, 2)], np.int32)
        cv2.polylines(hair, [pts], False, 1.0, 1, cv2.LINE_AA)
    hair = cv2.GaussianBlur(hair, (0, 0), 0.7) * 0.8
    a = np.clip(np.maximum(a, hair), 0, 1)
    F = np.stack([0.75 + 0*xx, 0.42 + 0*xx, 0.22 + 0*xx], -1) + smooth_noise(6, 0.6)
    F = np.clip(F, 0.02, 1.2)
    screen = np.stack([0.08 + 0*xx, 0.65 + 0*xx, 0.12 + 0*xx], -1) + smooth_noise(20, 0.4)
    natural = np.clip(np.stack([0.2 + 0*xx, 0.3 + 0*xx, 0.45 + 0*xx], -1) + smooth_noise(4, 1.2), 0.0, 1.5)
    return a, F, {"green screen": np.clip(screen, 0, 1.5), "natural": natural}


def metrics(a, F_true, F_est):
    band = (a > 0.05) & (a < 0.95)
    w = a[band][:, None]
    fg = float((np.abs(F_est[band] - F_true[band]) * w).sum() / (w.sum() * 3))
    N = np.full(3, 0.5, np.float32)
    comp_t = a[..., None] * F_true + (1 - a[..., None]) * N
    comp_e = a[..., None] * F_est + (1 - a[..., None]) * N
    fringe = float(np.abs(comp_e - comp_t)[band].mean())
    return {"fg_error": round(fg, 4), "fringe": round(fringe, 4)}


a, F, bgs = scene()
R = {"band_pixels": int(((a > 0.05) & (a < 0.95)).sum())}
for name, B in bgs.items():
    I = a[..., None] * F + (1 - a[..., None]) * B
    R[name] = {"straight (before)": metrics(a, F, I), "decontaminated": metrics(a, F, matte.decontaminate(I, a))}
    # robustness to an imperfect alpha (a shape/matte that is slightly too big: dilated 2 px)
    a_big = cv2.dilate(a, np.ones((5, 5), np.uint8))
    R[name]["decontaminated, alpha 2px too big"] = metrics(a, F, matte.decontaminate(I, a_big))
    R[name]["straight, alpha 2px too big"] = metrics(a, F, I)
# spill: green light bounced onto the foreground near its edge (fades inwards), on the green screen
B = bgs["green screen"]
dist = cv2.distanceTransform((a > 0.5).astype(np.uint8), cv2.DIST_L2, 3)
spill = np.exp(-dist / 12.0)[..., None] * np.array([0.0, 0.25, 0.0], np.float32)
F_sp = F + spill
I = a[..., None] * F_sp + (1 - a[..., None]) * B
inside = a > 0.95
R["spill colour detected"] = matte.spill_colour_of(I, a)
Fd = matte.decontaminate(I, a)
for label, est in (("no correction", Fd), ("despill average", matte.despill(Fd, "green", "average")),
                   ("despill max", matte.despill(Fd, "green", "max"))):
    m = metrics(a, F, est)
    m["fg_error_inside"] = round(float(np.abs(est[inside] - F[inside]).mean()), 4)
    m["green_excess_inside"] = round(float((est[inside][:, 1] - F[inside][:, 1]).mean()), 4)
    R.setdefault("spill", {})[label] = m
json.dump(R, open(os.path.join(HERE, "result_edge_colour.json"), "w"), indent=1)
print(json.dumps(R, indent=1))
