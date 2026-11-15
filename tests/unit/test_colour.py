"""Model-input colour transforms (T-045): derived matrices vs published values and vs OpenColorIO's ACES config."""
import numpy as np
import pytest

from st_roto import colour as c

# Published linear AP1 -> linear Rec.709 and AP0 -> Rec.709 with Bradford adaptation (ACES documentation /
# colour-science); ours are DERIVED from primaries, so agreement checks the derivation.
AP1_TO_709 = [[1.70505, -0.62179, -0.08326], [-0.13026, 1.14080, -0.01055], [-0.02400, -0.12897, 1.15297]]
AP0_TO_709 = [[2.52169, -1.13413, -0.38756], [-0.27648, 1.37272, -0.09624], [-0.01538, -0.15298, 1.16835]]


def test_derived_matrices_match_published():
    assert np.allclose(c.conversion_matrix("ap1"), AP1_TO_709, atol=1e-5)
    assert np.allclose(c.conversion_matrix("ap0"), AP0_TO_709, atol=1e-5)
    assert np.allclose(c.conversion_matrix("rec709"), np.eye(3), atol=1e-12)
    for p in c.PRIMARIES:                                        # white maps to white (rows sum to 1)
        assert np.allclose(c.conversion_matrix(p).sum(1), 1.0, atol=1e-6), p


def test_srgb_curve_and_v0_compatibility():
    x = np.array([0.0, 0.0031308, 0.18, 1.0, 2.0, -1.0])
    y = c.srgb_encode(x)
    assert np.isclose(y[1], 0.0031308 * 12.92) and np.isclose(y[3], 1.0) and np.isclose(y[4], 1.0) and y[5] == 0.0
    assert np.isclose(y[2], 0.46135612950044164)                 # 18 % grey
    img = np.random.default_rng(0).random((8, 8, 3)).astype(np.float32)
    old = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(img, 1 / 2.4) - 0.055)
    assert np.allclose(c.to_model_input(img), old, atol=1e-7)   # default = the v0 transform, unchanged results
    assert np.array_equal(c.to_model_input(img, "display_encoded_passthrough_v1"), img)
    with pytest.raises(ValueError):
        c.to_model_input(img, "nope")


OCIO = pytest.importorskip("PyOpenColorIO")
CFG = "ocio://cg-config-v2.2.0_aces-v1.3_ocio-v2.4"
PAIRS = [("ACEScg", "acescg_to_srgb_encoded_v1"), ("ACES2065-1", "aces2065_to_srgb_encoded_v1"),
         ("Linear Rec.709 (sRGB)", "linear_srgb_to_srgb_encoded_v0"), ("Linear Rec.2020", "linear_rec2020_to_srgb_encoded_v1"),
         ("Linear P3-D65", "linear_p3d65_to_srgb_encoded_v1")]


@pytest.mark.parametrize("space,tid", PAIRS)
def test_builtins_match_ocio_aces_config(space, tid):
    x = np.random.default_rng(1).random((32, 32, 3)).astype(np.float32) * 1.2
    t = c.OcioTransform(CFG, space)
    assert t.dst == "sRGB Encoded Rec.709 (sRGB)" and t.id.startswith("ocio_v1:" + CFG)
    assert np.abs(t(x) - c.to_model_input(x, tid)).max() < 2e-5


def test_ocio_rejects_unknown_space():
    with pytest.raises(ValueError):
        c.OcioTransform(CFG, "no such space")


def test_ocio_never_modifies_the_callers_frame():
    """Regression: applyRGB works in place; the transform used to overwrite contiguous float32 input."""
    x = np.full((4, 4, 3), 0.5, np.float32)
    c.OcioTransform(CFG, "ACEScg")(x)
    assert (x == 0.5).all()
