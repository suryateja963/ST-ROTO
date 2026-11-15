"""Antialiased bilinear resize matching torch.nn.functional.interpolate(mode="bilinear", align_corners=False,
antialias=True), in numpy (no torch at runtime, ADR-0002). Port of PyTorch's separable "aa" weight computation
(aten/src/ATen/native/UpSample.h, _compute_indices_min_size_weights_aa) with a triangle filter."""
from __future__ import annotations

import numpy as np


def _weights(in_size: int, out_size: int) -> np.ndarray:
    scale = in_size / float(out_size)
    support = scale if scale >= 1.0 else 1.0                # interp_size/2 * scale for bilinear (interp_size = 2)
    invscale = 1.0 / scale if scale >= 1.0 else 1.0
    w = np.zeros((out_size, in_size), np.float64)
    for i in range(out_size):
        center = scale * (i + 0.5)
        xmin = max(int(center - support + 0.5), 0)
        xmax = min(int(center + support + 0.5), in_size)
        js = np.arange(xmin, xmax)
        x = (js - center + 0.5) * invscale
        f = np.clip(1.0 - np.abs(x), 0.0, None)
        s = f.sum()
        if s > 0:
            w[i, xmin:xmax] = f / s
    return w


_WCACHE = {}


def _cached(in_size, out_size, dtype):
    key = (in_size, out_size, np.dtype(dtype).str)
    w = _WCACHE.get(key)
    if w is None:
        w = _WCACHE[key] = _weights(in_size, out_size).astype(dtype)
    return w


def resize_aa(img: np.ndarray, out_h: int, out_w: int, dtype=np.float64) -> np.ndarray:
    """Resize (H, W) or (H, W, C) with antialiased bilinear filtering; returns float32.
    dtype=float64 for exact mask preparation, float32 for fast image preprocessing (BLAS)."""
    a = np.asarray(img, dtype)
    wy, wx = _cached(a.shape[0], out_h, dtype), _cached(a.shape[1], out_w, dtype)
    if a.ndim == 2:
        return (wy @ a @ wx.T).astype(np.float32)
    return np.stack([wy @ a[..., c] @ wx.T for c in range(a.shape[2])], -1).astype(np.float32)


def mask_to_model_input(mask: np.ndarray, size: int = 1024) -> np.ndarray:
    """Binary mask (H, W) -> [1,1,size,size] float {0,1}, exactly as Sam2VideoProcessor prepares mask prompts."""
    m = np.asarray(mask, np.float32)
    if m.shape != (size, size):
        m = (resize_aa(m, size, size) >= 0.5).astype(np.float32)
    return m[None, None]
