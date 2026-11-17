"""Deterministic synthetic STEREO test shot with exact per-view ground truth (T-109, REQ-115; synthetic per D-020).

The 2026-11-15 synthetic scene (textured pan, red rotating ellipse = TARGET, similar-coloured DISTRACTOR disc,
grey OCCLUDER bar) rendered for two rectified cameras: the right view sees every layer shifted LEFT by its
disparity (x_right = x_left - d). Layers sit at different depths:
    background d = 8 px (far), distractor d = 20 px, target d = 30 -> 50 px (moves towards camera), occluder d = 45 px.
Vertical disparity is 0 (rectified rig). Ground truth = visible part of the target in each view.

Output (git-ignored, regenerate any time):  out/stereo/<view>/frame_####.png, out/stereo/<view>/gt_####.png,
out/stereo/meta.json   (<view> = left / right; Nuke Read path out/stereo/%V/frame_####.png)
"""
import json
import os

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "stereo")
W, H, N, SEED = 1280, 720, 48, 11
D_BG, D_DIS, D_OCC = 8, 20, 45


def d_target(s):
    return 30.0 + 20.0 * s


def render(f, view, big, tex_t):
    s = f / (N - 1)
    sh = 0 if view == "left" else 1                                  # right view: subtract the disparity
    pan = int(round(300 * s)) + sh * D_BG
    img = np.clip(big[:, pan:pan + W], 0, 255).astype(np.float32)
    dx, dy = int(1050 - 600 * s) - sh * D_DIS, int(560 - 120 * np.sin(np.pi * s))
    cv2.circle(img, (dx, dy), 85, (215, 80, 40), -1)
    cx = 300 + 650 * s - sh * d_target(s)
    cy = 330 + 140 * np.sin(2 * np.pi * s)
    ax = 170 * (1 + 0.25 * np.sin(2 * np.pi * s))
    ay = 105 * (1 + 0.15 * np.cos(2 * np.pi * s))
    ang = 15 + 90 * s
    tgt = np.zeros((H, W), np.uint8)
    cv2.ellipse(tgt, (int(round(cx)), int(round(cy))), (int(round(ax)), int(round(ay))), ang, 0, 360, 1, -1)
    # the texture travels with the object (shifted by its disparity), as a real surface would
    tex = np.roll(tex_t, -int(round(sh * d_target(s))), axis=1)
    col = np.stack([205 + tex[..., 0], 45 + tex[..., 1], 45 + tex[..., 2]], -1)
    img[tgt == 1] = col[tgt == 1]
    occ = np.zeros((H, W), np.uint8)
    bx = int(-200 + 1700 * np.clip((f - 14) / 20.0, 0, 1)) - sh * D_OCC
    if 14 <= f <= 34:
        cv2.rectangle(occ, (bx, 0), (bx + 90, H), 1, -1)
        img[occ == 1] = (128, 128, 128)
    gt = (tgt == 1) & (occ == 0)
    img = cv2.GaussianBlur(np.clip(img, 0, 255).astype(np.uint8), (3, 3), 0)
    return img, gt, (float(cx), float(cy))


def main():
    rng = np.random.default_rng(SEED)
    big = np.zeros((H, W + 400, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W + 400].astype(np.float32)
    big[..., 0] = 70 + 35 * np.sin(xx / 53.0) * np.cos(yy / 71.0)
    big[..., 1] = 90 + 30 * np.sin((xx + 2 * yy) / 97.0)
    big[..., 2] = 60 + 25 * np.cos(xx / 37.0)
    big += rng.normal(0, 10, big.shape)
    tex_t = rng.normal(0, 16, (H, W, 3))
    meta = {"w": W, "h": H, "frames": N, "seed": SEED, "views": ["left", "right"],
            "disparity": {"background": D_BG, "distractor": D_DIS, "occluder": D_OCC, "target": "30 + 20 * f/47"},
            "click_frame": 0, "targets": {}}
    for view in ("left", "right"):
        d = os.path.join(OUT, view)
        os.makedirs(d, exist_ok=True)
        meta["targets"][view] = {}
        for f in range(N):
            img, gt, c = render(f, view, big, tex_t)
            cv2.imwrite(os.path.join(d, "frame_%04d.png" % f), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            cv2.imwrite(os.path.join(d, "gt_%04d.png" % f), gt.astype(np.uint8) * 255)
            meta["targets"][view][f] = {"center": list(c), "visible_px": int(gt.sum())}
    meta["click_xy"] = meta["targets"]["left"][0]["center"]
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print("wrote %d frames x 2 views to %s" % (N, OUT))


if __name__ == "__main__":
    main()
