"""st_roto.matte: model-free soft edges, checked against composites with KNOWN alpha."""
import numpy as np

from st_roto.matte import box_sum, edge_band, guided_filter, refine_alpha

H, W = 160, 200
yy, xx = np.mgrid[0:H, 0:W] + 0.5
D = np.hypot(xx - 100, yy - 80) - 45                       # signed distance to a disc


def composite(A, seed=0):
    rng = np.random.default_rng(seed)
    F = np.clip([0.75, 0.25, 0.2] + 0.05 * rng.normal(0, 1, (H, W, 3)), 0, 1)
    B = np.clip([0.2, 0.45, 0.3] + 0.05 * rng.normal(0, 1, (H, W, 3)), 0, 1)
    return A[..., None] * F + (1 - A[..., None]) * B


def sad(a, b):
    return float(np.abs(a - b).sum())


def test_box_sum_matches_brute_force():
    x = np.random.default_rng(1).normal(size=(9, 11))
    s = box_sum(x, 2)
    for y in range(9):
        for c in range(11):
            assert np.isclose(s[y, c], x[max(0, y - 2):y + 3, max(0, c - 2):c + 3].sum())


def test_guided_filter_keeps_constant_and_follows_guide_edges():
    g = np.zeros((20, 20, 3)); g[:, 10:] = 1.0
    assert np.allclose(guided_filter(g, np.full((20, 20), 0.3)), 0.3)
    q = guided_filter(g, (g[..., 0] > 0.5).astype(float), r=3, eps=1e-6)   # edge in both: preserved
    assert np.abs(q - (g[..., 0] > 0.5)).max() < 0.01


def test_soft_edge_improves_and_stays_hard_away_from_edge():
    A = np.clip(0.5 - D / 3.0, 0, 1)                         # 3 px soft edge
    mask = A > 0.5
    a = refine_alpha(composite(A), mask)
    assert sad(a, A) < 0.6 * sad(mask.astype(float), A)
    far = ~edge_band(mask, 3)
    assert np.array_equal(a[far], mask[far].astype(np.float32))      # only the band may change
    assert a.dtype == np.float32 and a.min() >= 0 and a.max() <= 1


def test_motion_blur_edge_improves():
    k = np.ones(11) / 11
    A = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, (D < 0).astype(float))
    mask = A > 0.5
    assert sad(refine_alpha(composite(A, 2), mask), A) < 0.6 * sad(mask.astype(float), A)


def test_empty_and_full_masks_unchanged():
    img = composite(np.zeros((H, W)))
    assert not refine_alpha(img, np.zeros((H, W), bool)).any()
    assert refine_alpha(img, np.ones((H, W), bool)).all()
