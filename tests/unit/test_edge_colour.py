"""Edge decontamination and spill correction (T-115, REQ-101)."""
import numpy as np
import pytest

from st_roto import matte

H, W = 80, 100


def composite(bg):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    a = np.clip(25 - np.hypot(xx - 50, yy - 40), 0, 6) / 6.0            # 6 px soft ramp
    F = np.zeros((H, W, 3), np.float32); F[..., 0], F[..., 1], F[..., 2] = 0.8, 0.4, 0.2
    B = np.zeros((H, W, 3), np.float32); B[...] = bg
    I = a[..., None] * F + (1 - a[..., None]) * B
    return a.astype(np.float32), F, I.astype(np.float32)


def test_decontaminate_recovers_edge_colour():
    a, F, I = composite((0.1, 0.7, 0.1))
    band = (a > 0.05) & (a < 0.95)
    before = np.abs(I[band] - F[band]).mean()
    after = np.abs(matte.decontaminate(I, a)[band] - F[band]).mean()
    assert before > 0.1 and after < 0.01
    out = matte.decontaminate(I, a)
    assert np.array_equal(out[a >= 0.98], I[a >= 0.98])                 # solid foreground untouched


def test_despill_and_spill_detection():
    a, F, I = composite((0.1, 0.7, 0.1))
    assert matte.spill_colour_of(I, a) == "green"
    assert matte.spill_colour_of(composite((0.1, 0.1, 0.7))[2], a) == "blue"
    assert matte.spill_colour_of(composite((0.4, 0.4, 0.4))[2], a) is None
    c = np.array([[[0.3, 0.8, 0.2]]], np.float32)
    assert np.allclose(matte.despill(c, "green"), [[[0.3, 0.25, 0.2]]])          # G limited to (R+B)/2
    assert np.allclose(matte.despill(c, "green", "max"), [[[0.3, 0.3, 0.2]]])
    assert np.allclose(matte.despill(c, "green", amount=0.5), [[[0.3, 0.525, 0.2]]])
    assert np.allclose(matte.despill(np.array([[[0.5, 0.2, 0.4]]], np.float32), "green"), [[[0.5, 0.2, 0.4]]])
    with pytest.raises(ValueError):
        matte.despill(c, "red")


def test_foreground_rgb_modes():
    a, F, I = composite((0.1, 0.7, 0.1))
    assert np.allclose(matte.foreground_rgb(I, a, "straight"), I)
    assert np.allclose(matte.foreground_rgb(I, a, "premultiplied"), I * a[..., None])
    d = matte.foreground_rgb(I, a, "straight, decontaminated")
    assert np.allclose(matte.foreground_rgb(I, a, "premultiplied, decontaminated"), d * a[..., None])
    s = matte.foreground_rgb(I, a, "straight, decontaminated", spill="auto")
    assert (s[..., 1] <= d[..., 1] + 1e-6).all()
    assert matte.rgb_mode_parts("premultiplied, decontaminated") == ("premultiplied", True)
    with pytest.raises(ValueError):
        matte.foreground_rgb(I, a, "unpremultiplied")
