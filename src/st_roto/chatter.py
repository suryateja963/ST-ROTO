"""Chatter reduction for tracked shapes (T-115, REQ-101 'chatter reduction'). Pure Python + numpy.

AI shapes are fitted per frame, so their control points jitter by fractions of a pixel from frame to frame and the
edge 'chatters' in playback. Each point's trajectory (all six numbers: position and both handles) is replaced, on
AI frames only, by a local quadratic least-squares fit over the frames within `radius` (Savitzky-Golay style):
constant velocity and acceleration pass unchanged, frame-to-frame noise is averaged out. Artist keys and locked
frames are never changed but take part in the fits (they anchor the result). Fits never span a gap in the keys or a
collapsed part key (piece absent, T-049): those split the trajectory.
"""
from __future__ import annotations

import numpy as np

DEFAULT_RADIUS = 2


def _runs(frames):
    """Split sorted frames into runs of consecutive frames."""
    out, cur = [], []
    for f in frames:
        if cur and f != cur[-1] + 1:
            out.append(cur)
            cur = []
        cur.append(f)
    if cur:
        out.append(cur)
    return out


def _fit_value(t, y, t0):
    """Value at t0 of the least-squares quadratic (linear if fewer than 4 samples) through (t, y)."""
    t = np.asarray(t, np.float64) - t0
    deg = 2 if len(t) >= 4 else (1 if len(t) >= 2 else 0)
    A = np.vander(t, deg + 1)
    coef, *_ = np.linalg.lstsq(A, np.asarray(y, np.float64), rcond=None)
    return coef[-1]                                            # polynomial value at t = t0 (offset 0)


def smooth_keys(keys: dict, fixed=(), radius: int = DEFAULT_RADIUS, strength: float = 1.0, skip=()) -> dict:
    """keys {frame: points (N x 6)} of one shape -> {frame: smoothed points} for the frames that are NOT in `fixed`
    (artist / locked) and not in `skip` (e.g. collapsed). strength 0..1 blends original -> fitted."""
    fixed, skip = set(fixed), set(skip)
    usable = sorted(f for f, p in keys.items() if p and f not in skip)
    out = {}
    for run in _runs(usable):
        if len(run) < 3:
            continue
        arr = np.array([keys[f] for f in run], np.float64)        # T x N x 6
        if arr.ndim != 3 or len(set(len(keys[f]) for f in run)) != 1:
            continue
        for i, f in enumerate(run):
            if f in fixed:
                continue
            lo, hi = max(0, i - radius), min(len(run), i + radius + 1)
            t = np.arange(lo, hi)
            if len(t) < 4:                 # a quadratic through <= 3 samples is exact: nothing to average (and a
                continue                   # lower-order fit would bend real acceleration at the ends of a run)
            seg = arr[lo:hi].reshape(len(t), -1)
            fitted = np.array([_fit_value(t, seg[:, j], i) for j in range(seg.shape[1])])
            new = arr[i].reshape(-1) + float(strength) * (fitted - arr[i].reshape(-1))
            out[f] = new.reshape(arr.shape[1], arr.shape[2]).tolist()
    return out


def jitter(keys: dict) -> float:
    """Mean |second difference| of the control points over consecutive keyed frames (px): 0 for constant velocity,
    grows with frame-to-frame noise. A simple chatter measure for reports."""
    fs = sorted(f for f, p in keys.items() if p)
    vals = []
    for run in _runs(fs):
        if len(run) < 3:
            continue
        arr = np.array([keys[f] for f in run], np.float64)[:, :, :2]
        vals.append(np.abs(arr[2:] - 2 * arr[1:-1] + arr[:-2]).mean())
    return float(np.mean(vals)) if vals else 0.0
