"""Model-free soft edges for a hard shape (matting step 1, docs/RESEARCH_2026-11-16_MATTING.md). Pure numpy.

`refine_alpha(rgb, mask)`: the shape's hard mask decides what is surely inside / outside; only a band of
`band` pixels around its edge becomes soft, computed with the colour guided filter (He, Sun, Tang, "Guided Image
Filtering", ECCV 2010 / TPAMI 2013) using the plate as guide. Edges follow colour boundaries the shape missed by a
pixel or two, and partially covered pixels get partial alpha. This is an algorithm, no learned weights: it needs no
licence decision (OQ-22). It does NOT recover individual hair strands far outside the shape; that needs a learned
matting model plugged into the same mask -> band -> alpha pipeline.

Works on a crop around the edge, so cost scales with the object's outline, not the frame size.
"""
from __future__ import annotations

import numpy as np


def box_sum(x: np.ndarray, r: int) -> np.ndarray:
    """Sum over a (2r+1)x(2r+1) window (clipped at the borders), via an integral image. x: (H, W[, C])."""
    h, w = x.shape[:2]
    c = np.cumsum(np.cumsum(np.asarray(x, np.float64), 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)) + ((0, 0),) * (x.ndim - 2))
    y0 = np.clip(np.arange(h) - r, 0, h); y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w); x1 = np.clip(np.arange(w) + r + 1, 0, w)
    return c[y1][:, x1] - c[y0][:, x1] - c[y1][:, x0] + c[y0][:, x0]


def box_mean(x: np.ndarray, r: int) -> np.ndarray:
    n = box_sum(np.ones(x.shape[:2]), r)
    return box_sum(x, r) / n.reshape(n.shape + (1,) * (x.ndim - 2))


def guided_filter(guide: np.ndarray, src: np.ndarray, r: int = 4, eps: float = 1e-3) -> np.ndarray:
    """Colour guided filter. guide (H, W, 3) float, src (H, W) float -> (H, W) float64."""
    I = np.asarray(guide, np.float64)
    p = np.asarray(src, np.float64)
    mI = box_mean(I, r)
    mp = box_mean(p, r)
    cov = box_mean(I * p[..., None], r) - mI * mp[..., None]                       # (H, W, 3)
    var = box_mean(I[..., :, None] * I[..., None, :], r) - mI[..., :, None] * mI[..., None, :]
    var = var + eps * np.eye(3)
    a = np.linalg.solve(var, cov[..., None])[..., 0]                                 # (H, W, 3)
    b = mp - (a * mI).sum(-1)
    return (box_mean(a, r) * I).sum(-1) + box_mean(b, r)


def edge_band(mask: np.ndarray, band: int) -> np.ndarray:
    """Pixels within `band` (square window) of the mask edge: the window holds both inside and outside pixels."""
    m = box_mean(np.asarray(mask, np.float64), band)
    return (m > 1e-9) & (m < 1 - 1e-9)


def key_points_at(keys: list, frame: int):
    """Shape points at `frame` from its stored keys (sorted by frame): the key itself, a LINEAR blend of the two
    neighbouring keys, or the first/last key held outside the keyed range. -> (points, how) with how in
    {"key", "interpolated", "held"}, or (None, None) without keys. Linear blending differs from Nuke's own curve
    interpolation between sparse keys; AI-tracked shapes are keyed on every frame, so it only matters for sparse,
    hand-animated shapes (reported to the user)."""
    if not keys:
        return None, None
    frames = [k["frame"] for k in keys]
    if frame <= frames[0] or frame >= frames[-1]:
        k = keys[0] if frame <= frames[0] else keys[-1]
        return k["points"], ("key" if k["frame"] == frame else "held")
    for a, b in zip(keys, keys[1:]):
        if a["frame"] == frame:
            return a["points"], "key"
        if a["frame"] < frame < b["frame"] and len(a["points"]) == len(b["points"]):
            t = (frame - a["frame"]) / float(b["frame"] - a["frame"])
            pa, pb = np.asarray(a["points"], np.float64), np.asarray(b["points"], np.float64)
            return ((1 - t) * pa + t * pb).tolist(), "interpolated"
        if a["frame"] < frame < b["frame"]:
            return a["points"], "held"                     # point count changed between keys: hold
    return keys[-1]["points"], "key"


def object_mask(store, object_id: str, frame: int, height: int, width: int):
    """Hard mask (bool H x W) of all shapes of an object at `frame` (union), exact pixel-centre rasterisation of
    the stored splines. -> (mask, {shape name: how}) — see key_points_at."""
    from .geometry import Anchor, rasterize_spline
    mask = np.zeros((height, width), bool)
    how = {}
    for s in store.shapes(object_id):
        pts, h = key_points_at(store.keys(s["id"]), frame)
        how[s["name"]] = h
        if pts:
            a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:6]), corner=False) for p in pts]
            mask |= rasterize_spline(a, height, width)
    return mask, how


def refine_alpha(rgb: np.ndarray, mask: np.ndarray, band: int = 3, radius: int = 8, eps: float = 1e-4,
                 margin: int = 4) -> np.ndarray:
    """Hard mask + plate -> soft alpha (H, W) float32 in [0, 1]. Outside the edge band alpha equals the mask.

    rgb: (H, W, 3) float plate in a perceptual-ish encoding (display-referred works best; the guided filter is
    sensitive to colour differences, which are compressed in scene-linear darks). mask: (H, W) bool or {0,1}.
    band: half-width in pixels of the zone that may become soft; radius/eps: guided-filter window and smoothness.
    Defaults = best mean result on known-alpha composites (research/probes/2026-11-16_matting: SAD 0.59x the hard
    shape's on average; soft edge 0.44x, motion blur 0.35x, 2 px offset edge 0.70x, missed hair 0.86x). The best
    setting differs per scene, so hosts expose band/radius to the artist.
    """
    mask = np.asarray(mask) > 0.5
    alpha = mask.astype(np.float32)
    zone = edge_band(mask, band)
    if not zone.any():
        return alpha
    ys, xs = np.nonzero(zone)
    pad = band + 2 * radius + margin
    y0, y1 = max(0, ys.min() - pad), min(mask.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(mask.shape[1], xs.max() + pad + 1)
    crop = np.asarray(rgb, np.float64)[y0:y1, x0:x1, :3]
    q = guided_filter(crop, mask[y0:y1, x0:x1].astype(np.float64), radius, eps)
    z = zone[y0:y1, x0:x1]
    alpha[y0:y1, x0:x1][z] = np.clip(q[z], 0.0, 1.0)
    return alpha
