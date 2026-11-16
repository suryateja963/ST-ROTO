"""ViTMatte-S (D-032, optional): preprocessing, trimap, and the measured advantage on hair. Skips without the
exported model (it is an optional download, never in the repository)."""
import os

import numpy as np
import pytest

from st_roto_ai.vitmatte import preprocess, trimap_from_mask

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS = os.path.join(ROOT, "models", "onnx")


def test_preprocess_layout_and_padding():
    rgb = np.full((50, 70, 3), 0.25, np.float32)
    tri = np.full((50, 70), 0.5, np.float32)
    x = preprocess(rgb, tri)
    assert x.shape == (1, 4, 64, 96)
    assert np.allclose(x[0, :3, :50, :70], -0.5) and np.allclose(x[0, 3, :50, :70], 0.5)
    assert not x[0, :, 50:, :].any() and not x[0, :, :, 70:].any()          # zero padding right/bottom


def test_trimap_from_mask():
    m = np.zeros((60, 60), bool); m[20:40, 20:40] = True
    t = trimap_from_mask(m, inner=3, outer=5)
    assert t[30, 30] == 1.0 and t[21, 21] == 0.5 and t[17, 30] == 0.5 and t[10, 10] == 0.0
    assert set(np.unique(t)) == {0.0, 0.5, 1.0}


pytest.importorskip("onnxruntime")
needs = pytest.mark.skipif(not os.path.exists(os.path.join(MODELS, "vitmatte-small-composition-1k", "vitmatte.onnx")),
                           reason="ViTMatte-S not installed (optional, D-032)")


@needs
def test_vitmatte_recovers_hair_better_than_guided_filter():
    """Measured in research/probes/2026-11-16_matting/result_vitmatte.json: hair SAD 0.69k vs guided 0.95k."""
    from st_roto.matte import refine_alpha
    from st_roto_ai.vitmatte import ViTMatte
    H, W = 240, 320
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    d = np.hypot(xx - 160, yy - 120) - 70
    A = np.clip(0.5 - d / 2.0, 0, 1)
    for i in range(30):
        ang, ln = rng.uniform(0, 2 * np.pi), rng.uniform(10, 25)
        for t in np.linspace(0, ln, int(ln * 3)):
            x, y = int(160 + (70 + t) * np.cos(ang)), int(120 + (70 + t) * np.sin(ang))
            if 0 <= x < W and 0 <= y < H:
                A[y, x] = max(A[y, x], 0.6)
    F = np.clip([0.75, 0.25, 0.2] + 0.05 * rng.normal(0, 1, (H, W, 3)), 0, 1)
    B = np.clip([0.2, 0.45, 0.3] + 0.08 * rng.normal(0, 1, (H, W, 3)), 0, 1)
    img = (A[..., None] * F + (1 - A[..., None]) * B).astype(np.float32)
    shape = np.clip(0.5 - d / 2.0, 0, 1) > 0.5                            # strands missed by the shape
    v = ViTMatte(MODELS, device="cpu").alpha(img, trimap_from_mask(shape, 6, 20))
    g = refine_alpha(img, shape)
    sad = lambda a: np.abs(a - A).sum()                                    # noqa: E731
    assert sad(v) < 0.85 * sad(g) and v.min() >= 0 and v.max() <= 1
