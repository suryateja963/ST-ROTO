"""Extra image channels as hints (T-110, REQ-113, master prompt section 13.2). Pure Python + numpy.

Channels a plate can carry besides RGB, and what ST-ROTO does with each (artist-selected per node):
* Cryptomatte (ID mattes from CG renders): an object's exact coverage per frame -> prompt (box + clicks), and a
  per-frame comparison with the tracked shape (`crypto_mask`, spec: Psyop Cryptomatte v1.2: MurmurHash3_x86_32 of
  the name, `uint32_to_float32` conversion, rank channels <layer>00.. as (id, coverage) pairs).
* Motion vectors (forward/backward, pixels per frame): the shape on frame f moved by the vectors should match the
  shape on f+1 (`warp_points`, `motion_agreement`). Renderers differ in the sign of the vertical (and sometimes
  horizontal) component, so the convention is MEASURED per shot from the pixels (`detect_vector_convention`).
* Depth (Z), position (P), normals (N) or any other layer: a robust statistic inside the object (median) per frame;
  a jump against BOTH neighbouring frames suggests the shape grabbed something else (`channel_jumps`).
Every rule only adds CHECK flags; thresholds are provisional (synthetic CG shot, research/probes/2026-11-18_channels).
"""
from __future__ import annotations

import json
import struct

import numpy as np

STAT_JUMP = 0.25            # spike: deviation from BOTH neighbouring frames, same direction, > this x the shot's
#                             robust spread (p90 - p10) of the channel median (relative jumps fail for signed
#                             channels crossing zero, e.g. position: measured, T-110)
STAT_JUMP_REL = 0.05        # ... and at least this fraction of the value's magnitude (channels nearly constant)
STAT_JUMP_ABS = 1e-6
CONVENTION_MARGIN = 1.02    # an axis's sign is decided only if the flipped sign is >= 2 % worse
EPIPOLAR_TOL_PX = 10.0     # T-120: centroid off its epipolar line (truth centroids: <= 7.6 px, clipping)
MOTION_IOU_MIN = 0.85       # shape(f) moved by the vectors vs shape(f+1)
WARP_INSET = 3              # px inside the shape where outline points read their vector (see warp_points)
OCCLUSION_MARGIN = 4        # px around occluded / revealed object pixels also left out of the motion check: a
#                             spline outline along an occluder's edge is approximate (measured on AI shapes, T-110:
#                             motion IoU 0.88 on frames whose truth IoU was 0.99 without it)
CRYPTO_IOU_MIN = 0.90       # tracked shape vs the object's Cryptomatte coverage (> 0.5)


# ------------------------------------------------------------------------------------------------ Cryptomatte
def murmur3_32(data, seed: int = 0) -> int:
    """MurmurHash3_x86_32 (Austin Appleby), as used by Cryptomatte. data: bytes or str (UTF-8)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    c1, c2, m = 0xcc9e2d51, 0x1b873593, 0xffffffff
    h, n = seed & m, len(data)
    for i in range(n // 4):
        k = int.from_bytes(data[4 * i:4 * i + 4], "little")
        k = (k * c1) & m
        k = ((k << 15) | (k >> 17)) & m
        k = (k * c2) & m
        h ^= k
        h = ((h << 13) | (h >> 19)) & m
        h = (h * 5 + 0xe6546b64) & m
    tail, k = data[(n // 4) * 4:], 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * c1) & m
        k = ((k << 15) | (k >> 17)) & m
        k = (k * c2) & m
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85ebca6b) & m
    h ^= h >> 13
    h = (h * 0xc2b2ae35) & m
    h ^= h >> 16
    return h


def name_to_id(name: str) -> int:
    """Cryptomatte id (uint32 bit pattern of the float32 stored in the image): the hash with exponent 0 / 255
    avoided (flip of the lowest exponent bit), per the specification."""
    h = murmur3_32(name)
    e = (h >> 23) & 0xff
    if e in (0, 255):
        h ^= 1 << 23
    return h


def id_to_float(i: int) -> float:
    return struct.unpack("<f", struct.pack("<I", i))[0]


def layer_key(layer: str) -> str:
    """Metadata key of a Cryptomatte layer: the first 7 hex digits of the hash of its name."""
    return ("%08x" % murmur3_32(layer))[:7]


def find_layers(metadata: dict) -> dict:
    """{layer name: manifest {name: id (int)}} from image metadata (EXR header attributes or Nuke's
    node.metadata(): keys like '[exr/]cryptomatte/<key>/name', '.../manifest'). Layers without a manifest get {}."""
    groups = {}
    for k, v in (metadata or {}).items():
        parts = str(k).split("/")
        if "cryptomatte" not in parts:
            continue
        i = parts.index("cryptomatte")
        if len(parts) < i + 3:
            continue
        groups.setdefault(parts[i + 1], {})[parts[i + 2]] = v
    out = {}
    for g in groups.values():
        name = g.get("name")
        if not name:
            continue
        man = {}
        try:
            raw = g.get("manifest")
            if raw:
                man = {n: int(h, 16) for n, h in json.loads(raw).items()}
        except (ValueError, TypeError):
            man = {}
        out[str(name)] = man
    return out


def rank_pairs(channels: dict, layer: str) -> list:
    """[(id array, coverage array)] of a Cryptomatte layer from {channel name: HxW array}. Channel names may be
    EXR style (<layer>00.R/G/B/A) or Nuke style (<layer>00.red/green/blue/alpha)."""
    pairs, i = [], 0
    while True:
        base = "%s%02d" % (layer, i)
        names = None
        for sfx in (("R", "G", "B", "A"), ("red", "green", "blue", "alpha"), ("r", "g", "b", "a")):
            if all("%s.%s" % (base, s) in channels for s in sfx):
                names = ["%s.%s" % (base, s) for s in sfx]
                break
        if names is None:
            break
        c = [np.asarray(channels[n], np.float32) for n in names]
        pairs += [(c[0], c[1]), (c[2], c[3])]
        i += 1
    if not pairs:
        raise ValueError("no Cryptomatte channels %s00.R/G/B/A in the image" % layer)
    return pairs


def crypto_mask(channels: dict, layer: str, names) -> np.ndarray:
    """Coverage (HxW float, 0..1) of the objects `names` (one name or several) in a Cryptomatte layer."""
    if isinstance(names, str):
        names = [names]
    want = np.array([name_to_id(n) for n in names], np.uint32)
    cov = None
    for ids, c in rank_pairs(channels, layer):
        bits = np.ascontiguousarray(ids, np.float32).view(np.uint32)
        hit = np.isin(bits, want)
        cov = (c * hit) if cov is None else cov + c * hit
    return np.clip(cov, 0.0, 1.0)


def encode_ranks(coverages: dict, depth: int = 4) -> dict:
    """Test/tool helper: {name: HxW coverage} -> {'00': (H,W,4), '01': ...} rank channels (id, cov, id, cov),
    highest coverage first, as a renderer writes them."""
    names = list(coverages)
    cov = np.stack([np.asarray(coverages[n], np.float32) for n in names], -1)
    ids = np.array([id_to_float(name_to_id(n)) for n in names], np.float32)
    if len(names) < depth:                                     # fewer objects than ranks: empty ranks
        cov = np.concatenate([cov, np.zeros(cov.shape[:-1] + (depth - len(names),), np.float32)], -1)
        ids = np.concatenate([ids, np.zeros(depth - len(names), np.float32)])
    order = np.argsort(-cov, axis=-1, kind="stable")[..., :depth]
    c_sorted = np.take_along_axis(cov, order, -1)
    i_sorted = np.where(c_sorted > 0, ids[order], 0.0).astype(np.float32)
    out = {}
    for r in range(0, depth, 2):
        out["%02d" % (r // 2)] = np.stack([i_sorted[..., r], c_sorted[..., r], i_sorted[..., r + 1],
                                           c_sorted[..., r + 1]], -1)
    return out


def manifest_attributes(layer: str, names) -> dict:
    """EXR header attributes of a Cryptomatte layer (for test data and exports)."""
    key = layer_key(layer)
    man = {n: "%08x" % name_to_id(n) for n in names}
    return {"cryptomatte/%s/name" % key: layer, "cryptomatte/%s/hash" % key: "MurmurHash3_32",
            "cryptomatte/%s/conversion" % key: "uint32_to_float32", "cryptomatte/%s/manifest" % key: json.dumps(man)}


# ------------------------------------------------------------------------------------------------ motion vectors
CONVENTIONS = {"u right, v up (Nuke)": (1.0, -1.0), "u right, v down": (1.0, 1.0),
               "u left, v up": (-1.0, -1.0), "u left, v down": (-1.0, 1.0)}


def _bilinear(a, x, y):
    h, w = a.shape
    x = np.clip(np.asarray(x, np.float64) - 0.5, 0, w - 1)      # canonical: pixel centre at +0.5
    y = np.clip(np.asarray(y, np.float64) - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    return ((a[y0, x0] * (1 - fx) + a[y0, x1] * fx) * (1 - fy) + (a[y1, x0] * (1 - fx) + a[y1, x1] * fx) * fy)


def _nearest(a, x, y):
    """Nearest-pixel sample (canonical coordinates). Vector fields are discontinuous at object edges: bilinear
    sampling there mixes object and background motion and fakes occlusions along every silhouette (measured, T-110)."""
    h, w = a.shape
    c = np.clip(np.floor(np.asarray(x)).astype(int), 0, w - 1)
    r = np.clip(np.floor(np.asarray(y)).astype(int), 0, h - 1)
    return a[r, c]


def displacement(u, v, convention):
    """(dx, dy) arrays in canonical image coordinates (x right, y DOWN) from the vector channels."""
    su, sv = CONVENTIONS[convention] if isinstance(convention, str) else convention
    return su * np.asarray(u, np.float32), sv * np.asarray(v, np.float32)


def warp_points(points, u, v, convention, mask=None, inset: int = None):
    """Move a shape key (stored points: x, y + absolute handles) by the vectors sampled at each point. Points
    outside the object may sample the background's vectors; with `mask` (the object's pixels on that frame) each
    point samples the vector of the nearest pixel at least `inset` px INSIDE the mask (default WARP_INSET): a traced
    outline sits on or just over the object's edge, where the pixel can belong to a neighbouring object moving
    differently (measured, T-110: one outline point took the passing distractor's vector, motion IoU 0.88 on a
    frame whose shape was 0.99 correct). Vectors are sampled nearest-pixel (no mixing across edges)."""
    dx, dy = displacement(u, v, convention)
    pts = np.asarray(points, np.float64)
    xy = pts[:, 0:2]
    sx, sy = xy[:, 0], xy[:, 1]
    if mask is not None and np.asarray(mask).any():
        m = np.asarray(mask, bool)
        core = ~_grow(~m, WARP_INSET if inset is None else inset)
        if core.any():
            m = core
        ys, xs = np.nonzero(m)
        cx, cy = xs + 0.5, ys + 0.5
        # nearest inner pixel for each point (few points: brute force is fine)
        d2 = (sx[:, None] - cx[None, :]) ** 2 + (sy[:, None] - cy[None, :]) ** 2
        j = np.argmin(d2, axis=1)
        sx, sy = cx[j], cy[j]
    mx, my = _nearest(dx, sx, sy), _nearest(dy, sx, sy)
    out = pts.copy()
    for c in (0, 2, 4):                                          # point and both handles move together
        out[:, c] += mx
        out[:, c + 1] += my
    return out.tolist()


def fit_affine_motion(u, v, convention, mask, max_samples: int = 4000, iterations: int = 4):
    """The dominant motion inside `mask` as a 2x3 affine map A (x' = A [x, y, 1]), robust to pixels of something
    else in front (iteratively reweighted least squares, residuals beyond 3 x the median dropped). Returns
    (A, inlier fraction) or (None, 0) if too few pixels."""
    dx, dy = displacement(u, v, convention)
    ys, xs = np.nonzero(np.asarray(mask, bool))
    if len(xs) < 12:
        return None, 0.0
    if len(xs) > max_samples:
        sel = np.linspace(0, len(xs) - 1, max_samples).astype(int)
        ys, xs = ys[sel], xs[sel]
    X = np.c_[xs + 0.5, ys + 0.5, np.ones(len(xs))]
    T = np.c_[xs + 0.5 + dx[ys, xs], ys + 0.5 + dy[ys, xs]]
    # robust START: the median vector (the majority's motion). A least-squares start over all pixels was poisoned by
    # an occluder covering 30 % of the shape (fitted scale 0.16; measured) and trimming then kept the mixture.
    mx, my = float(np.median(dx[ys, xs])), float(np.median(dy[ys, xs]))
    A = np.array([[1.0, 0.0, mx], [0.0, 1.0, my]])
    r0 = np.hypot(*(X @ A.T - T).T)
    keep = r0 <= max(2.0, 3.0 * float(np.median(r0)))
    for _ in range(iterations):
        if keep.sum() < 12:
            break
        sol, *_ = np.linalg.lstsq(X[keep], T[keep], rcond=None)
        A = sol.T
        r = np.hypot(*(X @ A.T - T).T)
        med = float(np.median(r[keep]))
        keep = r <= max(0.5, 3.0 * med)
    return A, float(keep.mean())


def warp_points_robust(points, u, v, convention, mask, tol: float = 2.0):
    """warp_points that survives occlusion (T-121, measured): each point keeps its own (inset-sampled) vector only if
    it agrees within `tol` px with the object's dominant affine motion (fit_affine_motion); otherwise it moves with
    the affine motion. Without this a shape propagated across an occluder took the occluder's vectors and fell
    apart (IoU 0.98 -> 0.03 in one frame)."""
    local = np.asarray(warp_points(points, u, v, convention, mask=mask), np.float64)
    A, _ = fit_affine_motion(u, v, convention, mask)
    if A is None:
        return local.tolist()
    pts = np.asarray(points, np.float64)
    out = local.copy()
    for c in (0, 2, 4):
        xy = np.c_[pts[:, c], pts[:, c + 1], np.ones(len(pts))]
        aff = xy @ A.T
        bad = np.hypot(*(local[:, c:c + 2] - aff).T) > tol
        out[bad, c:c + 2] = aff[bad]
    return out.tolist()


def warp_image(img, u, v, convention):
    """Backward-warp check helper: predicted next frame = img sampled at (x - d(x)) (approximate: uses the vectors
    at the destination). Returns the prediction (HxW or HxWxC)."""
    dx, dy = displacement(u, v, convention)
    h, w = dx.shape
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    sx, sy = xx - dx, yy - dy
    a = np.asarray(img, np.float32)
    if a.ndim == 2:
        return _bilinear(a, sx, sy)
    return np.stack([_bilinear(a[..., c], sx, sy) for c in range(a.shape[2])], -1)


def vector_errors(img_a, img_b, u, v) -> dict:
    """{convention: mean absolute difference between frame B and frame A moved by the forward vectors} where the
    vectors move something (|d| > 0.5 px); raises ValueError if (almost) nothing moves."""
    a, b = np.asarray(img_a, np.float32), np.asarray(img_b, np.float32)
    if a.ndim == 3:
        a, b = a.mean(2), b.mean(2)
    moving = np.hypot(np.asarray(u, np.float32), np.asarray(v, np.float32)) > 0.5
    if moving.sum() < 50:
        raise ValueError("the vectors move (almost) nothing on this frame: cannot tell their convention")
    errs = {}
    for name in CONVENTIONS:
        pred = warp_image(a, u, v, name)
        errs[name] = float(np.abs(pred - b)[moving].mean())
    return errs


def choose_convention(per_frame_errors: list, default: str = "u right, v up (Nuke)") -> dict:
    """Decide the vector convention from several frames' `vector_errors` (summed). Each axis's sign is decided
    separately: the best candidate is compared with the same candidate with that axis flipped; below
    CONVENTION_MARGIN the axis is undetermined (e.g. nothing moved vertically) and the default's sign is used.
    Returns {"convention", "errors", "margin_u", "margin_v", "undetermined": [axes]}."""
    if not per_frame_errors:
        raise ValueError("no frame with motion to measure the vector convention on")
    tot = {n: sum(e[n] for e in per_frame_errors) for n in CONVENTIONS}
    name_of = {sg: n for n, sg in CONVENTIONS.items()}
    best = min(tot, key=tot.get)
    su, sv = CONVENTIONS[best]
    mu = tot[name_of[(-su, sv)]] / max(tot[best], 1e-12)
    mv = tot[name_of[(su, -sv)]] / max(tot[best], 1e-12)
    du, dv = CONVENTIONS[default]
    und = []
    if mu < CONVENTION_MARGIN:
        su = du
        und.append("u")
    if mv < CONVENTION_MARGIN:
        sv = dv
        und.append("v")
    return {"convention": name_of[(su, sv)], "errors": tot, "margin_u": round(mu, 4), "margin_v": round(mv, 4),
            "undetermined": und}


def detect_vector_convention(img_a, img_b, u, v) -> dict:
    """One frame pair: `choose_convention([vector_errors(...)])`."""
    return choose_convention([vector_errors(img_a, img_b, u, v)])


def mask_iou(a, b, region=None) -> float:
    """IoU of two masks, optionally only inside `region` (bool)."""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    if region is not None:
        a, b = a & region, b & region
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def occluded_object_pixels(prev_mask, cur_mask, fu, fv, bu, bv, convention, tol: float = 1.0):
    """Pixels of frame f to leave out of the motion check because ANOTHER surface hides or reveals the object there
    (bool mask on frame f). Object-centric on purpose: a plain forward-backward test also removes the object's own
    silhouette moving over the background, which hides exactly the errors the check is for (measured, T-110: a
    shape stuck on the previous frame then scored IoU 0.997).
      * hidden: an object pixel x of f-1 (prev_mask) moves by its forward vector (fu, fv of f-1) to y on f, and y's
        backward vector (bu, bv of f) does not lead back to x within `tol` px: something covers the object at y;
      * revealed: y inside the current shape whose backward vector leads to a point x of f-1 that does not come
        back (y was hidden on f-1) AND x lies OUTSIDE the previous shape: the object was hidden there by something
        else. (Background wrongly kept by a shape stuck on the previous frame leads back INSIDE the previous shape,
        so it still counts; a test on the vectors' similarity to the object's motion failed on a rotating, scaling
        object: measured, T-110.)"""
    fdx, fdy = displacement(fu, fv, convention)
    bdx, bdy = displacement(bu, bv, convention)
    h, w = fdx.shape
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    pm = np.asarray(prev_mask, bool)
    hidden = np.zeros((h, w), bool)
    if pm.any():
        x0, y0 = xx[pm], yy[pm]
        qx, qy = x0 + fdx[pm], y0 + fdy[pm]
        sx, sy = qx + _nearest(bdx, qx, qy), qy + _nearest(bdy, qx, qy)
        fail = (np.hypot(sx - x0, sy - y0) >= tol) & (qx >= 0) & (qx < w) & (qy >= 0) & (qy < h)
        hidden[np.clip(np.floor(qy[fail]).astype(int), 0, h - 1), np.clip(np.floor(qx[fail]).astype(int), 0, w - 1)] = True
        g = hidden.copy()                                      # splatted points leave gaps: close them by 1 px
        g[1:, :] |= hidden[:-1, :]; g[:-1, :] |= hidden[1:, :]; g[:, 1:] |= hidden[:, :-1]; g[:, :-1] |= hidden[:, 1:]
        hidden = g
    cm = np.asarray(cur_mask, bool)
    revealed = np.zeros((h, w), bool)
    if cm.any() and pm.any():
        px, py = xx + bdx, yy + bdy
        rx, ry = px + _nearest(fdx, px, py), py + _nearest(fdy, px, py)
        dis = cm & (np.hypot(rx - xx, ry - yy) >= tol)
        cols = np.clip(np.floor(px).astype(int), 0, w - 1)
        rows = np.clip(np.floor(py).astype(int), 0, h - 1)
        revealed = dis & ~pm[rows, cols]
    return _grow(hidden | revealed, OCCLUSION_MARGIN)


def _grow(mask, px: int):
    """Dilate a bool mask by `px` pixels (4-neighbour steps, no dependency on OpenCV / SciPy)."""
    out = np.asarray(mask, bool).copy()
    for _ in range(max(0, int(px))):
        g = out.copy()
        g[1:, :] |= out[:-1, :]; g[:-1, :] |= out[1:, :]; g[:, 1:] |= out[:, :-1]; g[:, :-1] |= out[:, 1:]
        out = g
    return out


# ------------------------------------------------------------------------------------------------ statistics
def masked_stat(channel, mask, erode: int = 2):
    """Median of a channel inside a mask (eroded by `erode` px so edge pixels of neighbours do not count); None if
    the mask is (nearly) empty."""
    m = np.asarray(mask, bool)
    if erode > 0 and m.any():
        e = m.copy()
        for _ in range(erode):
            e[1:, :] &= m[:-1, :]; e[:-1, :] &= m[1:, :]; e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
            m = e.copy()
    vals = np.asarray(channel, np.float64)[m]
    vals = vals[np.isfinite(vals)]
    return float(np.median(vals)) if vals.size >= 4 else None


def channel_jumps(values: dict, threshold: float = None) -> dict:
    """{frame: deviation / tolerance} for SPIKES of a per-frame statistic: the value differs from BOTH nearest
    frames that have one, in the same direction, by more than max(threshold x robust spread over the shot
    (p90 - p10), STAT_JUMP_REL x |value|). Smooth trends and zero crossings are never flagged."""
    t = STAT_JUMP if threshold is None else threshold
    fs = sorted(f for f, x in values.items() if x is not None)
    if len(fs) < 3:
        return {}
    vs = np.array([values[f] for f in fs], np.float64)
    spread = float(np.percentile(vs, 90) - np.percentile(vs, 10))
    out = {}
    for i in range(1, len(fs) - 1):
        a, p, n = vs[i], vs[i - 1], vs[i + 1]
        if (a - p) * (a - n) <= 0:                                  # not a spike (trend or flat)
            continue
        tol = max(t * spread, STAT_JUMP_REL * abs(a), STAT_JUMP_ABS)
        d = min(abs(a - p), abs(a - n))
        if d > tol:
            out[fs[i]] = round(d / tol, 2)
    return out


_NUKE_SUFFIX = {"red": "R", "green": "G", "blue": "B", "alpha": "A"}


def resolve(channels: dict, name: str):
    """The array of channel `name` as the artist writes it in Nuke ('depth.Z', 'rgba.alpha', 'N.red', 'forward.u')
    from an EXR channel dict (Nuke writes rgba as R/G/B/A and keeps other layers' suffixes). KeyError if absent."""
    if name in channels:
        return channels[name]
    layer, _, sfx = name.partition(".")
    cands = []
    if layer == "rgba" and sfx in _NUKE_SUFFIX:
        cands.append(_NUKE_SUFFIX[sfx])
    if sfx in _NUKE_SUFFIX:
        cands.append("%s.%s" % (layer, _NUKE_SUFFIX[sfx]))
    rev = {v: k for k, v in _NUKE_SUFFIX.items()}
    if sfx in rev:
        cands.append("%s.%s" % (layer, rev[sfx]))
    for c in cands:
        if c in channels:
            return channels[c]
    raise KeyError("channel %r not found (have: %s)" % (name, ", ".join(sorted(channels)[:20])))


def layers_of(channel_names) -> list:
    """Distinct layer names of a channel list ('depth.Z' -> 'depth'; R/G/B/A -> 'rgba')."""
    out = []
    for c in channel_names:
        layer = c.split(".")[0] if "." in c else "rgba"
        if layer not in out:
            out.append(layer)
    return out


def check_object(frames, get_keys, get_channels, height, width, stats=(), motion=None, crypto=None) -> dict:
    """Extra-channel report of one object: {frame: {"stats": {channel: median inside the shape}, "motion_iou",
    "crypto_iou"}} for the frames where the object has a shape.

    get_keys(f) -> [point lists] of the object's shapes on frame f ([] if none); get_channels(f) -> {channel: HxW}.
    stats: channel names whose median inside the shape is recorded (depth.Z, P.y, N.blue, ...).
    motion: {"u", "v" (forward vector channel names), "convention", optional "bu", "bv" (backward vectors)}:
      shape(f-1) moved by the forward vectors of f-1 vs shape(f); with backward vectors, pixels that fail the
      object-centric forward-backward check (the object hidden or revealed by something else) are left out.
    crypto: {"layer", "names"}: shape(f) vs the Cryptomatte coverage (> 0.5) of those names."""
    return check_objects(frames, {"_": get_keys}, get_channels, height, width, stats, motion,
                         {"_": crypto} if crypto else None)["_"]


def check_objects(frames, get_keys: dict, get_channels, height, width, stats=(), motion=None, crypto=None,
                  progress=None) -> dict:
    """`check_object` for several objects in ONE pass over the frames (each frame's channels fetched once):
    get_keys {object: fn(frame)}, crypto {object: {"layer", "names"}} (objects without an entry: no Cryptomatte
    check). progress(i, n) is called per frame. Returns {object: report}."""
    from .stereo import mask_from_keys
    out = {o: {} for o in get_keys}
    prev = {o: None for o in get_keys}
    prev_ch = None
    frames = list(frames)
    for i, f in enumerate(frames):
        if progress:
            progress(i, len(frames))
        masks = {}
        for o, gk in get_keys.items():
            keys = gk(f)
            m = mask_from_keys(keys, height, width) if keys else None
            masks[o] = (keys, m) if m is not None and m.any() else None
        if not any(masks.values()):
            prev = {o: None for o in get_keys}
            prev_ch = None
            continue
        ch = get_channels(f)
        if ch is None:                                          # frame unreadable: skipped, motion chain restarts
            prev = {o: None for o in get_keys}
            prev_ch = None
            continue
        for o, km in masks.items():
            if km is None:
                prev[o] = None
                continue
            keys, mask = km
            r = {}
            if stats:
                r["stats"] = {}
                for name in stats:
                    v = masked_stat(resolve(ch, name), mask)
                    if v is not None:
                        r["stats"][name] = round(v, 6)
            cs = (crypto or {}).get(o)
            if cs:
                cm = crypto_mask(ch, cs["layer"], cs["names"]) > 0.5
                r["crypto_iou"] = round(mask_iou(mask, cm), 4)
            p = prev[o]
            if motion and p is not None and p["frame"] == f - 1 and prev_ch is not None:
                pc = prev_ch
                fu, fv = resolve(pc, motion["u"]), resolve(pc, motion["v"])
                moved = [warp_points(k, fu, fv, motion["convention"], mask=p["mask"]) for k in p["keys"]]
                region = None
                if motion.get("bu") and motion.get("bv"):
                    region = ~occluded_object_pixels(p["mask"], mask, fu, fv, resolve(ch, motion["bu"]),
                                                     resolve(ch, motion["bv"]), motion["convention"])
                r["motion_iou"] = round(mask_iou(mask_from_keys(moved, height, width), mask, region), 4)
            out[o][f] = r
            prev[o] = {"frame": f, "keys": keys, "mask": mask}
        prev_ch = ch
    return out


def review_flags(report: dict) -> list:
    """CHECK flags from an object's channel report {frame: {"stats": {channel: value}, "motion_iou": x,
    "crypto_iou": x}} -> [(frame, reason)]."""
    out = {}
    stats = {}
    for f, r in report.items():
        for ch, val in (r.get("stats") or {}).items():
            stats.setdefault(ch, {})[f] = val
    for ch, vals in sorted(stats.items()):
        for f, j in channel_jumps(vals).items():
            out.setdefault(f, []).append("%s inside the shape jumps against both neighbouring frames (%.1fx the "
                                         "usual change)" % (ch, j))
    for f, r in report.items():
        mi = r.get("motion_iou")
        if mi is not None and mi < MOTION_IOU_MIN:
            out.setdefault(f, []).append("shape does not follow the motion vectors from the previous frame "
                                         "(IoU %.2f)" % mi)
        ci = r.get("crypto_iou")
        if ci is not None and ci < CRYPTO_IOU_MIN:
            out.setdefault(f, []).append("shape differs from the Cryptomatte matte (IoU %.2f)" % ci)
        ep = r.get("epipolar_px")                             # T-120: known cameras (stereo / multi-camera)
        if ep is not None and ep > float(r.get("epipolar_tol", EPIPOLAR_TOL_PX)):
            out.setdefault(f, []).append("shape is %.1f px off the epipolar line from the %s view (cameras)"
                                         % (ep, r.get("epipolar_from", "prompt")))
    return sorted((f, "; ".join(rs)) for f, rs in out.items())
