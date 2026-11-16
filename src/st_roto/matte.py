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

FEATHER_WIDTH = 0.92      # Nuke's ramp ends at ~0.92 x the feather value (research/probes/2026-11-16_feather)


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



def feathered_alpha(points, feather_x, feather_y, falloff, height, width, width_factor=FEATHER_WIDTH,
                    per_segment=16):
    """APPROXIMATION of Nuke Roto's shape feather for ST-ROTO's own EXR mattes (T-073): 1 inside the spline,
    outside (1 - d / (width_factor * feather))^falloff with d the distance to the spline (per axis in units of
    feather_x / feather_y when they differ), 0 beyond. Measured against Nuke's render (tests/nuke
    test_feather_and_rotopaint, research/probes/2026-11-16_feather): the 50 % contour matches within ~1 px in
    every direction and the area within 0.3 %, but the ramp's tails differ (mean |error| ~0.11 inside the feather
    band): Nuke's ramp depends on the control points. Nuke stays authoritative: for exact feathered mattes render
    the ST_Roto output in Nuke. (A 'feather curve from offset control points' model was tried and was not better.)"""
    from .geometry import Anchor, rasterize_spline, sample_spline
    a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:6]), corner=False) for p in points]
    inside = rasterize_spline(a, height, width)              # the same exact raster as the hard mattes
    alpha = inside.astype(np.float32)
    fx, fy = max(0.0, float(feather_x)), max(0.0, float(feather_y))
    if fx <= 0 and fy <= 0:
        return alpha
    fx, fy = (fx or fy) * width_factor, (fy or fx) * width_factor
    poly = sample_spline(a, per_segment)                      # coarser polyline: distances only
    x0 = int(max(0, np.floor(poly[:, 0].min() - fx - 1))); x1 = int(min(width, np.ceil(poly[:, 0].max() + fx + 1)))
    y0 = int(max(0, np.floor(poly[:, 1].min() - fy - 1))); y1 = int(min(height, np.ceil(poly[:, 1].max() + fy + 1)))
    if x1 <= x0 or y1 <= y0:
        return alpha
    ys, xs = np.mgrid[y0:y1, x0:x1]
    out = ~inside[y0:y1, x0:x1]
    q = np.stack([poly[:, 0] / fx, poly[:, 1] / fy], 1)
    d = _dist_to_polyline((xs[out] + 0.5) / fx, (ys[out] + 0.5) / fy, q)
    v = np.clip(1.0 - d, 0.0, 1.0) ** float(falloff if falloff and falloff > 0 else 1.0)
    sub = alpha[y0:y1, x0:x1]
    sub[out] = v.astype(np.float32)
    alpha[y0:y1, x0:x1] = sub
    return alpha


def object_alpha(store, object_id: str, frame: int, height: int, width: int):
    """Like object_mask but float alpha that includes each shape's feather (max over shapes). -> (alpha, how,
    feathered: bool)."""
    alpha = np.zeros((height, width), np.float32)
    how, feathered = {}, False
    for s in store.shapes(object_id):
        pts, h = key_points_at(store.keys(s["id"]), frame)
        how[s["name"]] = h
        if not pts:
            continue
        fx, fy, ff = float(s.get("feather_x") or 0), float(s.get("feather_y") or 0), float(s.get("feather_falloff") or 1)
        feathered |= fx > 0 or fy > 0
        alpha = np.maximum(alpha, feathered_alpha(pts, fx, fy, ff, height, width))
    return alpha, how, feathered


def _dist_to_polyline(px, py, poly):
    a0, a1 = poly, np.roll(poly, -1, axis=0)
    seg = a1 - a0
    seg_len2 = np.maximum((seg ** 2).sum(1), 1e-12)
    d = np.empty(len(px))
    for i in range(0, len(px), 8192):                       # chunked: pixels x segments
        cx, cy = px[i:i + 8192, None], py[i:i + 8192, None]
        t = np.clip(((cx - a0[:, 0]) * seg[:, 0] + (cy - a0[:, 1]) * seg[:, 1]) / seg_len2, 0, 1)
        dx = cx - (a0[:, 0] + t * seg[:, 0]); dy = cy - (a0[:, 1] + t * seg[:, 1])
        d[i:i + 8192] = np.sqrt((dx ** 2 + dy ** 2).min(1))
    return d

