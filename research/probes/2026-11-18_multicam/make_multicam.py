"""Synthetic multi-camera shot with exact truth (T-120; synthetic per D-020), rendered by ray casting through the
three NON-RECTIFIED Nuke cameras measured in probe_camera_model.py (cameras.json: toe-in, roll, vertical offset,
window translate, different focal length). World (Nuke axes, y up), all planes facing the cameras (z = const):
  background  z = -15, large textured plane
  distractor  z = -8,  orange disc moving right-to-left
  target      z = -5,  red textured ellipse moving and rotating (TRUTH)
Views A, B, C, 16 frames, 960x540. Output (git-ignored): out/mc/<view>/frame_####.png, gt_####.png, meta.json
"""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import cameras as cm  # noqa: E402

W, H, N = 960, 540, 16
OUT = os.path.join(HERE, "out", "mc")
cams = json.load(open(os.path.join(HERE, "cameras.json")))
rng = np.random.default_rng(7)
TEX = cv2.GaussianBlur(rng.normal(0, 1, (512, 512, 3)).astype(np.float32), (0, 0), 3)


def tex(u, v, base, amp, scale):
    iu = (np.floor(u * scale) % 512).astype(int)
    iv = (np.floor(v * scale) % 512).astype(int)
    return np.clip(np.array(base, np.float32) + amp * TEX[iv, iu], 0, 1)


def render(view, f):
    c = cams[view]
    K = cm.intrinsics(W, H, c["focal"], c["haperture"], win_translate=c["win_translate"])
    R, C = cm.from_world_matrix(np.array(c["world_matrix"]).reshape(4, 4))
    vv, uu = np.mgrid[0:H, 0:W] + 0.5
    rays_cam = np.linalg.inv(K) @ np.stack([uu.ravel(), vv.ravel(), np.ones(uu.size)])
    d = (R.T @ rays_cam).T                                   # world directions (canonical -> world)
    s = f / (N - 1.0)
    img = np.zeros((H * W, 3), np.float32)
    hit_obj = np.zeros(H * W, np.int8)
    depth = np.full(H * W, np.inf)
    # planes, far to near
    for oid, z in ((0, -15.0), (1, -8.0), (2, -5.0)):
        t = (z - C[2]) / d[:, 2]
        X = C[None, :] + t[:, None] * d
        ok = t > 0
        if oid == 0:
            inside = ok
            col = tex(X[:, 0] * 40 + 200, X[:, 1] * 40 + 200, (0.25, 0.35, 0.3), 0.5, 1)
        elif oid == 1:
            cx, cy = 1.6 - 3.2 * s, -0.6
            inside = ok & ((X[:, 0] - cx) ** 2 + (X[:, 1] - cy) ** 2 < 0.45 ** 2)
            col = np.tile(np.array([[0.85, 0.35, 0.15]], np.float32), (len(X), 1))
        else:
            cx, cy, ang = -0.9 + 1.6 * s, 0.25 * np.sin(2 * np.pi * s), np.radians(10 + 60 * s)
            lx = (X[:, 0] - cx) * np.cos(ang) + (X[:, 1] - cy) * np.sin(ang)
            ly = -(X[:, 0] - cx) * np.sin(ang) + (X[:, 1] - cy) * np.cos(ang)
            inside = ok & ((lx / 0.7) ** 2 + (ly / 0.42) ** 2 < 1)
            col = tex(lx * 120 + 256, ly * 120 + 256, (0.8, 0.2, 0.2), 0.35, 1)
        nearer = inside & (t < depth)
        img[nearer] = col[nearer]
        hit_obj[nearer] = oid
        depth[nearer] = t[nearer]
    return img.reshape(H, W, 3), (hit_obj == 2).reshape(H, W)


def main():
    meta = {"w": W, "h": H, "frames": N, "views": sorted(cams), "cameras": cams, "targets": {}}
    for v in sorted(cams):
        d = os.path.join(OUT, v)
        os.makedirs(d, exist_ok=True)
        meta["targets"][v] = {}
        for f in range(N):
            img, gt = render(v, f)
            srgb = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(np.clip(img, 0, None), 1 / 2.4) - 0.055)
            cv2.imwrite(os.path.join(d, "frame_%04d.png" % f),
                        cv2.cvtColor((np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
            cv2.imwrite(os.path.join(d, "gt_%04d.png" % f), gt.astype(np.uint8) * 255)
            ys, xs = np.nonzero(gt)
            meta["targets"][v][f] = {"visible_px": int(gt.sum()),
                                     "centroid": [float(xs.mean() + 0.5), float(ys.mean() + 0.5)] if len(xs) else None}
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
    print("wrote", N, "frames x", len(cams), "views to", OUT)


if __name__ == "__main__":
    main()
