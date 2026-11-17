"""Stereo and multi-view support (T-109, REQ-115, master prompt section 13.4). Pure Python + numpy.

Model: every view gets its OWN object (tracked independently, never derived frame by frame from another view).
Objects of one subject in different views share `objects.pair` (the correspondence key) and carry `objects.view`
(the Nuke view name; NULL = every view, i.e. a monoscopic object). Names follow `view_object_name`.

* `estimate_disparity` finds where an object seen in one view lies in another view (masked block matching along
  the epipolar line with a small vertical tolerance, coarse-to-fine, sub-pixel). It is used ONCE per object, on its
  prompt frame, to carry the artist's prompt to the other views (`transfer_prompt`): the other view is then tracked
  by the AI on its own pixels.
* `consistency` compares corresponding objects frame by frame (vertical alignment, size, disparity continuity,
  presence) and returns CHECK flags. The thresholds are PROVISIONAL (synthetic stereo shot, research/probes/
  2026-11-17_stereo); no permissively licensed real stereo ground truth has been found yet.
"""
from __future__ import annotations

import math

import numpy as np

MAX_DISPARITY_FRACTION = 0.1    # default horizontal search: +-10 % of the image width
MAX_VERTICAL = 4                # default vertical search (pixels): rectified rigs are within a few pixels
VERTICAL_TOL_PX, VERTICAL_TOL_FRAC = 3.0, 0.02     # top AND bottom edge off the shot's usual offset by more
# (synthetic shot, correct shapes: residuals up to 5.0 px top / 2.5 px bottom on 251-335 px tall objects, from
# view-dependent occlusion; 0.04 missed a 12 px vertical error on 2 of 4 frames, 0.02 catches it)
AREA_RATIO_MAX = 1.35           # one view's object more than 35 % larger than the other's
DISPARITY_JUMP_PX, DISPARITY_JUMP_FRAC = 4.0, 0.25  # disparity jump against BOTH neighbouring frames


def view_object_name(base: str, view: str) -> str:
    return "%s_%s" % (base, view)


# ------------------------------------------------------------------------------------------------ geometry
def _polygon(points, per_segment=16):
    from .geometry import Anchor, sample_spline
    return sample_spline([Anchor(p=np.array(p[:2], float), h_in=np.array(p[2:4], float),
                                 h_out=np.array(p[4:6], float), corner=False) for p in points], per_segment)


def key_geometry(points) -> dict:
    """{"area", "cx", "cy", "x0", "y0", "x1", "y1"} of one closed spline key (area-weighted centroid)."""
    poly = _polygon(points)
    x, y = poly[:, 0], poly[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    a2 = float(cross.sum())
    area = abs(a2) / 2.0
    if area < 1e-9:
        return {"area": 0.0, "cx": float(x.mean()), "cy": float(y.mean()),
                "x0": float(x.min()), "y0": float(y.min()), "x1": float(x.max()), "y1": float(y.max())}
    cx = float(((x + xn) * cross).sum() / (3.0 * a2))
    cy = float(((y + yn) * cross).sum() / (3.0 * a2))
    return {"area": area, "cx": cx, "cy": cy,
            "x0": float(x.min()), "y0": float(y.min()), "x1": float(x.max()), "y1": float(y.max())}


def merge_geometry(parts: list) -> dict:
    """Union of several shapes' geometry on one frame (area-weighted centroid, union box). Zero-area parts (collapsed
    part keys, T-049) are ignored; None if nothing has area."""
    parts = [p for p in parts if p["area"] > 0]
    if not parts:
        return None
    a = sum(p["area"] for p in parts)
    return {"area": a, "cx": sum(p["cx"] * p["area"] for p in parts) / a,
            "cy": sum(p["cy"] * p["area"] for p in parts) / a,
            "x0": min(p["x0"] for p in parts), "y0": min(p["y0"] for p in parts),
            "x1": max(p["x1"] for p in parts), "y1": max(p["y1"] for p in parts)}


def object_geometry(store, object_id: str) -> dict:
    """{frame: geometry or None} of an object (all its shapes). None = keyed but without area (object absent)."""
    per = {}
    for s in store.shapes(object_id):
        for k in store.keys(s["id"]):
            per.setdefault(k["frame"], []).append(key_geometry(k["points"]))
    return {f: merge_geometry(g) for f, g in per.items()}


def counterparts(store, object_id: str) -> list:
    """Rows of the objects corresponding to `object_id` in other views (same shot and pair, other view)."""
    o = store.row("objects", object_id)
    if o is None or not o.get("pair") or not o.get("view"):
        return []
    return [dict(r) for r in store.conn.execute(
        "SELECT * FROM objects WHERE shot_id = ? AND pair = ? AND view IS NOT NULL AND view != ? AND id != ? "
        "ORDER BY view", (o["shot_id"], o["pair"], o["view"], object_id))]


def mask_from_keys(keys: list, height: int, width: int):
    """Union mask (HxW bool) of several shape keys (point lists) on one frame; collapsed part keys add nothing."""
    from .geometry import Anchor, rasterize_spline
    from .pieces import is_collapsed
    out = np.zeros((height, width), bool)
    for pts in keys:
        if not pts or is_collapsed(pts):
            continue
        out |= rasterize_spline([Anchor(p=np.array(p[:2], float), h_in=np.array(p[2:4], float),
                                        h_out=np.array(p[4:6], float), corner=False) for p in pts], height, width)
    return out


def mask_box(mask):
    """(x0, y0, x1, y1) pixel-edge box of a mask, or None if empty."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    return (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1))


# ------------------------------------------------------------------------------------------------ correspondence
def _gray(img):
    a = np.asarray(img, np.float32)
    return a.mean(axis=2) if a.ndim == 3 else a


def _block(a, s):
    if s == 1:
        return a
    h, w = (a.shape[0] // s) * s, (a.shape[1] // s) * s
    return a[:h, :w].reshape(h // s, s, w // s, s).mean(axis=(1, 3))


def _ssd_map(a, b, mask, x0, y0, dxs, dys):
    """Zero-mean masked SSD per (dy, dx) of the patch a[y0:y0+h, x0:x0+w] (mask) against b shifted. inf where less
    than half of the masked pixels fall inside b."""
    h, w = mask.shape
    pa = a[y0:y0 + h, x0:x0 + w]
    m = mask.astype(bool)
    n = m.sum()
    va = pa[m] - pa[m].mean()
    out = np.full((len(dys), len(dxs)), np.inf)
    H, W = b.shape
    for i, dy in enumerate(dys):
        for j, dx in enumerate(dxs):
            ys, xs = y0 + dy, x0 + dx
            cy0, cx0 = max(0, -ys), max(0, -xs)
            cy1, cx1 = min(h, H - ys), min(w, W - xs)
            if cy1 <= cy0 or cx1 <= cx0:
                continue
            mm = np.zeros_like(m)
            mm[cy0:cy1, cx0:cx1] = m[cy0:cy1, cx0:cx1]
            k = mm.sum()
            if k < 0.5 * n:
                continue
            pb = b[ys + cy0:ys + cy1, xs + cx0:xs + cx1]
            sel = mm[cy0:cy1, cx0:cx1]
            vb = pb[sel]
            vb = vb - vb.mean()
            vaa = pa[cy0:cy1, cx0:cx1][sel]
            vaa = vaa - vaa.mean()
            out[i, j] = float(((vaa - vb) ** 2).mean())
    return out


def _subpixel(e, i):
    """Parabola vertex offset around index i of a 1-D error curve (0 if not a proper minimum)."""
    if i <= 0 or i >= len(e) - 1 or not all(np.isfinite(e[i - 1:i + 2])):
        return 0.0
    d = e[i - 1] - 2 * e[i] + e[i + 1]
    return float(0.5 * (e[i - 1] - e[i + 1]) / d) if d > 0 else 0.0


def estimate_disparity(img_a, img_b, mask, max_dx: int = None, max_dy: int = MAX_VERTICAL, margin: int = 2) -> dict:
    """Where the masked region of view A appears in view B: b(x + dx, y + dy) ~ a(x, y).

    img_a, img_b: HxW(x3) float images of the same frame in two views; mask: HxW bool (the object in A).
    max_dx: horizontal search radius in pixels (default 10 % of the width); max_dy: vertical radius.
    Returns {"dx", "dy" (sub-pixel), "error" (zero-mean masked mean squared difference at the best shift),
    "ambiguity" (best error / best error at least 3 px away horizontally: near 1 = repetitive texture, unreliable)}
    or raises ValueError if the mask is empty."""
    a, b = _gray(img_a), _gray(img_b)
    mask = np.asarray(mask, bool)
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        raise ValueError("empty mask: nothing to match")
    H, W = mask.shape
    if max_dx is None:
        max_dx = max(8, int(round(MAX_DISPARITY_FRACTION * W)))
    y0, y1 = max(0, ys.min() - margin), min(H, ys.max() + 1 + margin)
    x0, x1 = max(0, xs.min() - margin), min(W, xs.max() + 1 + margin)
    # coarse level: block-average so that the horizontal search has at most ~64 steps each way
    s = max(1, int(math.ceil(max_dx / 64.0)))
    if s > 1 and min(y1 - y0, x1 - x0) // s < 4:
        s = 1
    ac, bc = _block(a, s), _block(b, s)
    mc = _block(mask[:(H // s) * s, :(W // s) * s].astype(np.float32), s) > 0.5
    cy0, cy1, cx0, cx1 = y0 // s, max(y0 // s + 1, y1 // s), x0 // s, max(x0 // s + 1, x1 // s)
    sub = mc[cy0:cy1, cx0:cx1]
    if not sub.any():
        sub, s = mask[y0:y1, x0:x1], 1
        ac, bc, cy0, cx0 = a, b, y0, x0
    rdx, rdy = int(math.ceil(max_dx / float(s))), int(math.ceil(max_dy / float(s)))
    dxs, dys = list(range(-rdx, rdx + 1)), list(range(-rdy, rdy + 1))
    e = _ssd_map(ac, bc, sub, cx0, cy0, dxs, dys)
    if not np.isfinite(e).any():
        raise ValueError("the object cannot be compared with the other view (search outside the image)")
    i, j = np.unravel_index(int(np.argmin(e)), e.shape)
    cdx, cdy = dxs[j] * s, dys[i] * s
    # fine level: full resolution around the coarse result
    r = s + 1
    fdxs = [d for d in range(cdx - r, cdx + r + 1) if abs(d) <= max_dx + s]
    fdys = [d for d in range(cdy - r, cdy + r + 1) if abs(d) <= max_dy + s]
    ef = _ssd_map(a, b, mask[y0:y1, x0:x1], x0, y0, fdxs, fdys)
    fi, fj = np.unravel_index(int(np.argmin(ef)), ef.shape)
    best = float(ef[fi, fj])
    dx = fdxs[fj] + _subpixel(ef[fi, :], fj)
    dy = fdys[fi] + _subpixel(ef[:, fj], fi)
    # ambiguity from the coarse map's best row, away from the winner
    row = e[i].copy()
    far = [k for k in range(len(dxs)) if abs(dxs[k] - dxs[j]) * s >= 3]
    second = float(np.min(row[far])) if far and np.isfinite(row[far]).any() else float("inf")
    amb = (float(e[i, j]) / second) if second > 0 and np.isfinite(second) else 0.0
    return {"dx": float(dx), "dy": float(dy), "error": best, "ambiguity": round(amb, 4)}


def transfer_prompt(obj: dict, dx: float, dy: float, box, width: int, height: int, name: str = None):
    """Prompt for another view: the object's clicks moved by (dx, dy), preceded by a box (x0, y0, x1, y1) = the
    object's extent in the source view moved by (dx, dy) (box + click: the most reliable prompt, T-082). Points
    that leave the image are dropped; None if the box falls (mostly) outside the image."""
    from .prompts import BOX_BR, BOX_TL
    bx0, by0, bx1, by1 = box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy
    cx0, cy0, cx1, cy1 = max(0.0, bx0), max(0.0, by0), min(float(width), bx1), min(float(height), by1)
    if cx1 - cx0 < 2 or cy1 - cy0 < 2 or (cx1 - cx0) * (cy1 - cy0) < 0.25 * (bx1 - bx0) * (by1 - by0):
        return None
    pts, labels = [(cx0, cy0), (cx1, cy1)], [BOX_TL, BOX_BR]
    for (x, y), lab in zip(obj["points"], obj["labels"]):
        if lab in (BOX_TL, BOX_BR):
            continue
        x2, y2 = x + dx, y + dy
        if 0 <= x2 < width and 0 <= y2 < height:
            pts.append((x2, y2)); labels.append(lab)
    out = dict(obj, points=pts, labels=labels)
    if name is not None:
        out["name"] = name
    return out


# ------------------------------------------------------------------------------------------------ consistency
def _median(v):
    v = sorted(v)
    n = len(v)
    return 0.0 if n == 0 else (v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2]))


def consistency(geo_a: dict, geo_b: dict, name_a: str = "A", name_b: str = "B") -> dict:
    """Compare one object's geometry in two views ({frame: geometry or None}, from `object_geometry`).

    Returns {"frames": {frame: {"dx", "dy_top", "dy_bottom", "area_ratio"}}, "offset": (median dy_top, median
    dy_bottom), "disparity": median dx, "flags": [(frame, reason)]}. Flags (CHECK level, provisional thresholds):
      * present in one view only (keyed frames of either object);
      * vertical misalignment: top AND bottom edges deviate from the shot's usual vertical offset by more than
        max(VERTICAL_TOL_PX, VERTICAL_TOL_FRAC x object height) (one edge alone can be a view-dependent occlusion);
      * size: area ratio above AREA_RATIO_MAX;
      * disparity jump: horizontal disparity differs from BOTH neighbouring frames by more than
        max(DISPARITY_JUMP_PX, DISPARITY_JUMP_FRAC x |median disparity|)."""
    frames = sorted(set(geo_a) | set(geo_b))
    per, flags = {}, []
    for f in frames:
        a, b = geo_a.get(f), geo_b.get(f)
        if f in geo_a and f in geo_b and (a is None) != (b is None):
            flags.append((f, "object in the %s view only" % (name_a if a is not None else name_b)))
        if a is None or b is None:
            continue
        per[f] = {"dx": b["cx"] - a["cx"], "dy_top": b["y0"] - a["y0"], "dy_bottom": b["y1"] - a["y1"],
                  "area_ratio": max(a["area"], b["area"]) / max(1e-9, min(a["area"], b["area"])),
                  "height": 0.5 * ((a["y1"] - a["y0"]) + (b["y1"] - b["y0"]))}
    off_t = _median([p["dy_top"] for p in per.values()])
    off_b = _median([p["dy_bottom"] for p in per.values()])
    disp = _median([p["dx"] for p in per.values()])
    jump_tol = max(DISPARITY_JUMP_PX, DISPARITY_JUMP_FRAC * abs(disp))
    fs = sorted(per)
    for i, f in enumerate(fs):
        p = per[f]
        reasons = []
        tol = max(VERTICAL_TOL_PX, VERTICAL_TOL_FRAC * p["height"])
        et, eb = p["dy_top"] - off_t, p["dy_bottom"] - off_b
        if abs(et) > tol and abs(eb) > tol:
            reasons.append("views disagree vertically (top %+.1f px, bottom %+.1f px against the shot's usual offset)"
                           % (et, eb))
        if p["area_ratio"] > AREA_RATIO_MAX:
            reasons.append("size differs %.0f%% between the views" % (100 * (p["area_ratio"] - 1)))
        if 0 < i < len(fs) - 1:
            dp, dn = abs(p["dx"] - per[fs[i - 1]]["dx"]), abs(p["dx"] - per[fs[i + 1]]["dx"])
            if dp > jump_tol and dn > jump_tol:
                reasons.append("disparity jumps %.1f px against both neighbouring frames" % min(dp, dn))
        if reasons:
            flags.append((f, "; ".join(reasons)))
    for p in per.values():
        p.pop("height", None)
    return {"frames": per, "offset": (off_t, off_b), "disparity": disp, "flags": sorted(flags)}


def review_for_object(store, object_id: str) -> list:
    """Stereo CHECK flags of an object against each corresponding object: [(frame, "check", "stereo: ...")]."""
    from .quality import CHECK
    me = store.row("objects", object_id)
    out = []
    others = counterparts(store, object_id)
    if not others:
        return out
    mine = object_geometry(store, object_id)
    for o in others:
        rep = consistency(mine, object_geometry(store, o["id"]), me["view"], o["view"])
        out += [(f, CHECK, "stereo vs %s: %s" % (o["view"], r)) for f, r in rep["flags"]]
    return sorted(out)
