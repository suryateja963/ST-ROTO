"""D-032: ViTMatte-S vs the model-free guided filter on the SAME known-alpha composites as probe_refine.py
(soft edge, 2 px offset edge, motion blur, missed hair strands). Both start from the same hard shape; ViTMatte
gets the trimap from st_roto_ai.vitmatte.trimap_from_mask. Metric: SAD (thousands) and MSE vs true alpha.
Run: .venv/Scripts/python.exe research/probes/2026-11-16_matting/probe_vitmatte_vs_guided.py"""
import json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import numpy as np   # noqa: E402
from st_roto.matte import refine_alpha                     # noqa: E402
from st_roto_ai.vitmatte import ViTMatte, trimap_from_mask  # noqa: E402

H, W = 360, 480
rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:H, 0:W] + 0.5


def tex(base, amp, scale):
    n = np.kron(rng.normal(0, 1, (H // scale + 2, W // scale + 2, 3)), np.ones((scale, scale, 1)))[:H, :W]
    return np.clip(np.asarray(base) + amp * n, 0, 1)


F, B = tex([0.75, 0.25, 0.2], 0.06, 6), tex([0.2, 0.45, 0.3], 0.08, 9)
d = np.hypot(xx - 240, yy - 180) - 100
soft = lambda dist, wdt: np.clip(0.5 - dist / wdt, 0, 1)   # noqa: E731


def scenes():
    A = soft(d, 3.0); yield "soft_edge", A, A > 0.5
    yield "offset_edge", A, soft(d - 2.0, 1e-6) > 0.5
    k = np.ones(15) / 15
    Am = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, (d < 0).astype(float)); yield "motion_blur", Am, Am > 0.5
    Ah = soft(d, 2.0)
    for i in range(40):
        ang, ln = rng.uniform(0, 2 * np.pi), rng.uniform(10, 30)
        for t in np.linspace(0, ln, int(ln * 3)):
            x, y = int(240 + (100 + t) * np.cos(ang + 0.01 * t)), int(180 + (100 + t) * np.sin(ang + 0.01 * t))
            if 0 <= x < W and 0 <= y < H:
                Ah[y, x] = max(Ah[y, x], 0.6)
    yield "hair", Ah, soft(d, 2.0) > 0.5


vm = ViTMatte(os.path.join(ROOT, "models", "onnx"), device="cpu")
out = {}
for name, A, shape in scenes():
    I = A[..., None] * F + (1 - A[..., None]) * B
    enc = np.where(I <= 0.0031308, I * 12.92, 1.055 * I ** (1 / 2.4) - 0.055).astype(np.float32)
    t0 = time.time(); g = refine_alpha(enc, shape); tg = time.time() - t0
    tri = trimap_from_mask(shape, inner=6, outer=20)
    t0 = time.time(); v = vm.alpha(enc, tri); tv = time.time() - t0
    sad = lambda a: round(float(np.abs(a - A).sum()) / 1000, 3)   # noqa: E731
    out[name] = {"hard_shape": sad(shape.astype(float)), "guided_filter": sad(g), "vitmatte_s": sad(v),
                 "seconds": {"guided": round(tg, 3), "vitmatte_cpu": round(tv, 3)}}
    print(name, out[name], flush=True)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_vitmatte.json"), "w"), indent=1)
