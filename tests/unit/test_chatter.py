"""Chatter reduction (T-115): trajectory smoothing of AI keys only."""
import numpy as np

from st_roto import chatter


def _keys(n=20, noise=0.0, seed=0):
    rng = np.random.RandomState(seed)
    base = np.array([[0, 0, -1, 0, 1, 0], [10, 0, 9, 0, 11, 0], [10, 10, 11, 10, 9, 10]], np.float64)
    out, truth = {}, {}
    for f in range(n):
        move = np.array([2.0 * f + 0.05 * f * f, 1.0 * f] * 3)          # accelerating motion
        t = base + move
        truth[f] = t.tolist()
        out[f] = (t + rng.normal(0, noise, t.shape)).tolist()
    return out, truth


def test_noise_free_motion_is_preserved():
    keys, truth = _keys()
    sm = chatter.smooth_keys(keys)
    assert sm and all(np.allclose(sm[f], truth[f], atol=1e-6) for f in sm)     # quadratic motion passes unchanged


def test_jitter_is_reduced_and_error_drops():
    keys, truth = _keys(noise=0.6)
    sm = chatter.smooth_keys(keys)
    merged = dict(keys); merged.update(sm)
    err_before = np.mean([np.abs(np.array(keys[f]) - truth[f]).mean() for f in keys])
    err_after = np.mean([np.abs(np.array(merged[f]) - truth[f]).mean() for f in keys])
    assert chatter.jitter(merged) < 0.5 * chatter.jitter(keys)
    assert err_after < 0.75 * err_before


def test_fixed_skipped_and_gaps():
    keys, _ = _keys(noise=0.5)
    sm = chatter.smooth_keys(keys, fixed={5, 6}, skip={12})
    assert 5 not in sm and 6 not in sm and 12 not in sm
    gappy = {f: p for f, p in keys.items() if f not in (8,)}
    sm2 = chatter.smooth_keys(gappy)
    assert 6 in sm2 and 10 in sm2                               # each side of the gap smoothed separately
    assert 7 not in sm2 and 9 not in sm2                        # run ends next to the gap: exact, left as they are
    short = {f: keys[f] for f in (0, 1)}
    assert chatter.smooth_keys(short) == {}
    half = chatter.smooth_keys(keys, strength=0.5)
    full = chatter.smooth_keys(keys)
    f = 10
    assert np.allclose(np.array(half[f]), 0.5 * (np.array(keys[f]) + np.array(full[f])))
