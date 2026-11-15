"""Measure st_roto.matte.refine_alpha on composites with KNOWN alpha (owner decision D-020: synthetic data).

Scenes (each: foreground F over background B with alpha A; the 'shape' is a hard mask a roto artist / SAM would give):
  soft_edge   : textured disc with a 3 px soft (defocus-like) edge; shape = A > 0.5            (ideal case)
  offset_edge : same, but the shape is 2 px too large                                         (spline slightly off)
  motion_blur : disc blurred horizontally by 15 px (box);  shape = A > 0.5
  hair        : disc + 40 one-pixel strands of alpha 0.6 sticking out 10-30 px; shape = disc only (strands missed)
Metric: SAD (sum |alpha - A|, in thousands, as in matting papers) and MSE over the frame, binary shape vs refined,
for several band / radius / eps settings. Writes results.json next to this file.
Run: .venv/Scripts/python.exe research/probes/2026-11-16_matting/probe_refine.py
"""
import json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import numpy as np   # noqa: E402
from st_roto.matte import refine_alpha   # noqa: E402

H, W = 360, 480
rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:H, 0:W] + 0.5


def smooth_texture(base, amp, scale):
    n = rng.normal(0, 1, (H // scale + 2, W // scale + 2, 3))
    n = np.kron(n, np.ones((scale, scale, 1)))[:H, :W]
    return np.clip(np.asarray(base) + amp * n, 0, 1)


F = smooth_texture([0.75, 0.25, 0.2], 0.06, 6)
B = smooth_texture([0.2, 0.45, 0.3], 0.08, 9)
d = np.hypot(xx - 240, yy - 180) - 100                # signed distance to a disc of radius 100


def soft(dist, width):
    return np.clip(0.5 - dist / width, 0, 1)


def hboxblur(a, n):
    k = np.ones(n) / n
    return np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, a)


def scenes():
    A = soft(d, 3.0)
    yield "soft_edge", A, A > 0.5
    yield "offset_edge", A, soft(d - 2.0, 1e-6) > 0.5
    Am = hboxblur((d < 0).astype(float), 15)
    yield "motion_blur", Am, Am > 0.5
    Ah = soft(d, 2.0)
    for i in range(40):
        ang = rng.uniform(0, 2 * np.pi); length = rng.uniform(10, 30)
        for t in np.linspace(0, length, int(length * 3)):
            x = int(240 + (100 + t) * np.cos(ang + 0.01 * t)); y = int(180 + (100 + t) * np.sin(ang + 0.01 * t))
            if 0 <= x < W and 0 <= y < H:
                Ah[y, x] = max(Ah[y, x], 0.6)
    yield "hair", Ah, soft(d, 2.0) > 0.5


SETTINGS = [dict(band=b, radius=r, eps=e) for b in (3, 6, 10) for r in (2, 4, 8) for e in (1e-4, 1e-3, 1e-2)]
out = {"scenes": {}}
for name, A, shape in scenes():
    I = A[..., None] * F + (1 - A[..., None]) * B
    enc = np.where(I <= 0.0031308, I * 12.92, 1.055 * I ** (1 / 2.4) - 0.055)       # display encoding for the guide
    base = {"sad_k": round(float(np.abs(shape - A).sum()) / 1000, 3), "mse": float(((shape - A) ** 2).mean())}
    rows = []
    for s in SETTINGS:
        t0 = time.time()
        a = refine_alpha(enc, shape, **s)
        rows.append(dict(s, sad_k=round(float(np.abs(a - A).sum()) / 1000, 3), mse=float(((a - A) ** 2).mean()),
                         seconds=round(time.time() - t0, 3)))
    out["scenes"][name] = {"binary_shape": base, "refined": sorted(rows, key=lambda r: r["sad_k"])}
# one default for all scenes: the setting with the best mean SAD ratio
ratios = {}
for s in SETTINGS:
    key = (s["band"], s["radius"], s["eps"])
    ratios[key] = np.mean([next(r["sad_k"] for r in v["refined"] if (r["band"], r["radius"], r["eps"]) == key)
                           / v["binary_shape"]["sad_k"] for v in out["scenes"].values()])
best = min(ratios, key=ratios.get)
out["best_default"] = {"band": best[0], "radius": best[1], "eps": best[2], "mean_sad_ratio_vs_binary": round(ratios[best], 3)}
out["per_scene_at_default"] = {n: {"binary_sad_k": v["binary_shape"]["sad_k"],
                                   "refined_sad_k": next(r["sad_k"] for r in v["refined"]
                                                         if (r["band"], r["radius"], r["eps"]) == best)}
                               for n, v in out["scenes"].items()}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json"), "w"), indent=1)
print(json.dumps({"best_default": out["best_default"], "per_scene_at_default": out["per_scene_at_default"]}, indent=1))
