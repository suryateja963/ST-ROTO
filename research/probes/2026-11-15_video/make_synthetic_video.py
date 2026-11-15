"""Deterministic synthetic test shot with exact per-frame ground truth (owner decision D-020: synthetic footage).

48 frames, 1280x720 (inside the Non-commercial HD limit):
  * textured background with a slow camera pan;
  * TARGET: red textured ellipse moving on a curve while rotating and changing scale;
  * DISTRACTOR: an orange-red disc of similar colour drifting the other way;
  * OCCLUDER: a grey bar sweeping across the target around frames 18-30 (partial occlusion).
Ground truth = visible part of the target (occluder removed).
Output (git-ignored, regenerate any time): frames/frame_####.png, frames/gt_####.png, frames/meta.json
"""
import json, os
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "frames")
W, H, N, SEED = 1280, 720, 48, 11


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(SEED)
    big = np.zeros((H, W + 400, 3), np.float32)                    # background wider than frame for panning
    yy, xx = np.mgrid[0:H, 0:W + 400].astype(np.float32)
    big[..., 0] = 70 + 35 * np.sin(xx / 53.0) * np.cos(yy / 71.0)
    big[..., 1] = 90 + 30 * np.sin((xx + 2 * yy) / 97.0)
    big[..., 2] = 60 + 25 * np.cos(xx / 37.0)
    big += rng.normal(0, 10, big.shape)
    tex_t = rng.normal(0, 16, (H, W, 3))
    meta = {"w": W, "h": H, "frames": N, "seed": SEED, "click_frame": 0, "objects": {}}
    for f in range(N):
        s = f / (N - 1)
        pan = int(round(300 * s))
        img = np.clip(big[:, pan:pan + W], 0, 255).astype(np.float32)
        # distractor disc (similar hue)
        dx, dy = int(1050 - 600 * s), int(560 - 120 * np.sin(np.pi * s))
        cv2.circle(img, (dx, dy), 85, (215, 80, 40), -1)            # RGB
        # target ellipse
        cx = 300 + 650 * s
        cy = 330 + 140 * np.sin(2 * np.pi * s)
        ax = 170 * (1 + 0.25 * np.sin(2 * np.pi * s))
        ay = 105 * (1 + 0.15 * np.cos(2 * np.pi * s))
        ang = 15 + 90 * s
        tgt = np.zeros((H, W), np.uint8)
        cv2.ellipse(tgt, (int(round(cx)), int(round(cy))), (int(round(ax)), int(round(ay))), ang, 0, 360, 1, -1)
        col = np.stack([205 + tex_t[..., 0], 45 + tex_t[..., 1], 45 + tex_t[..., 2]], -1)
        img[tgt == 1] = col[tgt == 1]
        # occluder bar
        occ = np.zeros((H, W), np.uint8)
        bx = int(-200 + 1700 * np.clip((f - 14) / 20.0, 0, 1))
        if 14 <= f <= 34:
            cv2.rectangle(occ, (bx, 0), (bx + 90, H), 1, -1)
            img[occ == 1] = (128, 128, 128)
        gt = (tgt == 1) & (occ == 0)
        img = cv2.GaussianBlur(np.clip(img, 0, 255).astype(np.uint8), (3, 3), 0)
        cv2.imwrite(os.path.join(OUT, "frame_%04d.png" % f), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        cv2.imwrite(os.path.join(OUT, "gt_%04d.png" % f), gt.astype(np.uint8) * 255)
        if f == 0:
            meta["click_xy"] = [float(cx), float(cy)]
        meta["objects"][f] = {"target_center": [float(cx), float(cy)], "visible_px": int(gt.sum()),
                              "occluder_on": bool(occ.any() and (tgt & occ).any())}
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print("wrote", N, "frames to", OUT)


if __name__ == "__main__":
    main()
