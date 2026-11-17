"""Synthetic CG shot with render passes and exact truth (T-110; synthetic per D-020).

The 2026-11-15 scene (textured background pan, red rotating/scaling ellipse TARGET, similar-coloured DISTRACTOR
disc, grey OCCLUDER bar) at 960x540, 24 frames, rendered 3x3 supersampled like a CG renderer:
  rgba             anti-aliased plate (A = 1)
  depth.Z          distance of the front surface at the pixel centre: background 100, distractor 40,
                   target 20 -> 12 (approaching), occluder 6
  forward.u/.v     pixels to the NEXT frame, backward.u/.v to the PREVIOUS frame, written in the convention
                   u right, v UP (Nuke's y-up); ST-ROTO must DETECT this, not assume it
  N.red/green/blue normals (constant per object), P.red/green/blue position (pinhole camera, f = 800 px)
  CryptoObject00/01 Cryptomatte v1.2 (4 ranks), names: background, distractor, target, occluder; manifest in the
                   header (cryptomatte/<key>/...)
Truth: gt_####.png = visible target (pixel-centre test, occluder removed).
Output (git-ignored): out/cg/cg.####.exr, out/cg/gt_####.png, out/cg/meta.json
"""
import json
import math
import os
import sys

import cv2
import numpy as np
import OpenEXR

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "src"))
from st_roto import channels as ch  # noqa: E402

OUT = os.path.join(HERE, "out", "cg")
W, H, N, SS, SEED = 960, 540, 24, 3, 11
NAMES = ["background", "distractor", "target", "occluder"]
FOCAL = 800.0


def params(f):
    s = f / (N - 1.0)
    return {"pan": 225.0 * s,
            "dis": (787.5 - 450 * s, 420 - 90 * math.sin(math.pi * s), 64.0),
            "tgt": (225 + 487.5 * s, 247.5 + 105 * math.sin(2 * math.pi * s),
                    127.5 * (1 + 0.25 * math.sin(2 * math.pi * s)), 78.75 * (1 + 0.15 * math.cos(2 * math.pi * s)),
                    math.radians(15 + 90 * s)),
            "occ": (-150 + 1275 * min(max((f - 7) / 10.0, 0), 1)) if 7 <= f <= 17 else None,
            "ztgt": 20.0 - 8.0 * s}


def layers_at(xx, yy, f):
    """Per sample: object index (0 bg, 1 dis, 2 tgt, 3 occ) of the front surface, and ellipse local coords."""
    p = params(f)
    obj = np.zeros(xx.shape, np.int8)
    dx, dy, r = p["dis"]
    obj[(xx - dx) ** 2 + (yy - dy) ** 2 <= r * r] = 1
    cx, cy, ax, ay, ang = p["tgt"]
    lx = (xx - cx) * math.cos(ang) + (yy - cy) * math.sin(ang)
    ly = -(xx - cx) * math.sin(ang) + (yy - cy) * math.cos(ang)
    obj[(lx / ax) ** 2 + (ly / ay) ** 2 <= 1] = 2
    if p["occ"] is not None:
        obj[(xx >= p["occ"]) & (xx < p["occ"] + 68)] = 3
    return obj, lx / ax, ly / ay


def surface_pos(obj, xx, yy, f, g):
    """Where each sample's surface point is on frame g (canonical pixels) - exact forward/backward motion."""
    p, q = params(f), params(g)
    nx, ny = xx.copy(), yy.copy()
    m = obj == 0
    nx[m] = xx[m] - (q["pan"] - p["pan"])
    for i, key in ((1, "dis"),):
        m = obj == i
        nx[m] = xx[m] + (q[key][0] - p[key][0]); ny[m] = yy[m] + (q[key][1] - p[key][1])
    m = obj == 2
    cx, cy, ax, ay, ang = p["tgt"]
    lx = ((xx[m] - cx) * math.cos(ang) + (yy[m] - cy) * math.sin(ang)) / ax
    ly = (-(xx[m] - cx) * math.sin(ang) + (yy[m] - cy) * math.cos(ang)) / ay
    cx2, cy2, ax2, ay2, ang2 = q["tgt"]
    nx[m] = cx2 + lx * ax2 * math.cos(ang2) - ly * ay2 * math.sin(ang2)
    ny[m] = cy2 + lx * ax2 * math.sin(ang2) + ly * ay2 * math.cos(ang2)
    m = obj == 3
    if q["occ"] is not None and p["occ"] is not None:
        nx[m] = xx[m] + (q["occ"] - p["occ"])
    return nx, ny


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(SEED)
    big = np.zeros((H, W + 300, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W + 300].astype(np.float32)
    big[..., 0] = 0.27 + 0.14 * np.sin(xx / 40.0) * np.cos(yy / 53.0)
    big[..., 1] = 0.35 + 0.12 * np.sin((xx + 2 * yy) / 73.0)
    big[..., 2] = 0.24 + 0.10 * np.cos(xx / 28.0)
    big += rng.normal(0, 0.03, big.shape).astype(np.float32)
    tex = rng.normal(0, 0.05, (64, 64, 3)).astype(np.float32)
    # supersample grid
    sy, sx = np.mgrid[0:H * SS, 0:W * SS].astype(np.float64)
    sx, sy = (sx + 0.5) / SS, (sy + 0.5) / SS
    cy_, cx_ = np.mgrid[0:H, 0:W].astype(np.float64) + 0.5
    attrs = ch.manifest_attributes("CryptoObject", NAMES)
    meta = {"w": W, "h": H, "frames": N, "names": NAMES, "vector_convention": "u right, v up (Nuke)",
            "depth": {"background": 100, "distractor": 40, "target": "20 - 8 s", "occluder": 6}, "targets": {}}
    for f in range(N):
        p = params(f)
        obj, lx, ly = layers_at(sx, sy, f)
        # colour per sample
        col = np.empty(obj.shape + (3,), np.float32)
        bx = np.clip((sx + p["pan"]).astype(int), 0, W + 299); by = np.clip(sy.astype(int), 0, H - 1)
        col[:] = big[by, bx]
        col[obj == 1] = (0.84, 0.31, 0.16)
        t = obj == 2
        tx = ((lx[t] + 1) * 32).astype(int) % 64; ty = ((ly[t] + 1) * 32).astype(int) % 64
        col[t] = np.array((0.80, 0.18, 0.18), np.float32) + tex[ty, tx]
        col[obj == 3] = (0.5, 0.5, 0.5)
        rgb = col.reshape(H, SS, W, SS, 3).mean((1, 3))
        cov = {n: (obj == i).reshape(H, SS, W, SS).mean((1, 3)).astype(np.float32) for i, n in enumerate(NAMES)}
        ranks = ch.encode_ranks(cov, depth=4)
        # pixel-centre passes
        pobj, _, _ = layers_at(cx_, cy_, f)
        z = np.choose(pobj, [100.0, 40.0, p["ztgt"], 6.0]).astype(np.float32)
        nrm = np.zeros((H, W, 3), np.float32)
        nrm[..., 2] = 1.0
        nrm[pobj == 1] = (0.0, 0.6, 0.8); nrm[pobj == 2] = (0.6, 0.0, 0.8); nrm[pobj == 3] = (-0.8, 0.0, 0.6)
        pos = np.stack([(cx_ - W / 2) * z / FOCAL, -(cy_ - H / 2) * z / FOCAL, -z], -1).astype(np.float32)
        chans = {"R": rgb[..., 0], "G": rgb[..., 1], "B": rgb[..., 2], "A": np.ones((H, W), np.float32),
                 "depth.Z": z}
        for lay, g in (("forward", f + 1), ("backward", f - 1)):
            if 0 <= g < N:
                nx, ny = surface_pos(pobj, cx_, cy_, f, g)
                du, dv = nx - cx_, ny - cy_
            else:
                du = dv = np.zeros((H, W))
            chans[lay + ".u"] = du.astype(np.float32)
            chans[lay + ".v"] = (-dv).astype(np.float32)              # y-up
        for i, c in enumerate("XYZ"):
            chans["N." + c] = nrm[..., i]; chans["P." + c] = pos[..., i]
        for k, a in ranks.items():
            for i, c in enumerate("RGBA"):
                chans["CryptoObject%s.%s" % (k, c)] = np.ascontiguousarray(a[..., i])
        header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
        header.update(attrs)
        OpenEXR.File(header, {k: np.ascontiguousarray(v, np.float32) for k, v in chans.items()}).write(
            os.path.join(OUT, "cg.%04d.exr" % f))
        gt = pobj == 2
        cv2.imwrite(os.path.join(OUT, "gt_%04d.png" % f), gt.astype(np.uint8) * 255)
        meta["targets"][f] = {"center": [p["tgt"][0], p["tgt"][1]], "visible_px": int(gt.sum())}
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print("wrote %d frames to %s" % (N, OUT))


if __name__ == "__main__":
    main()
