"""Fit closed cubic Bezier splines to mask contours (PROTOTYPE, not production code).

Algorithm: P. J. Schneider, "An Algorithm for Automatically Fitting Digitized Curves", Graphics Gems (1990):
least-squares cubic fit with chord-length parameterisation, Newton-Raphson reparameterisation, and
recursive splitting at the point of maximum error. Additions for roto use:
  * circular Gaussian smoothing of the pixel contour (removes raster staircase),
  * corner detection by turning angle (corners become cusp points; elsewhere tangents are shared, G1 smooth),
  * closed-loop handling.

Pure numpy so it can run both in the project venv and inside Nuke's Python 3.11.
Coordinates are whatever the caller passes (no flipping here).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class Anchor:
    """One spline vertex: position, absolute in/out handle positions, and whether it is a corner (cusp)."""
    p: np.ndarray
    h_in: np.ndarray
    h_out: np.ndarray
    corner: bool


# ----------------------------------------------------------------------------- helpers
def _bez(ctrl: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = t[:, None]
    mt = 1.0 - t
    return mt**3 * ctrl[0] + 3 * mt**2 * t * ctrl[1] + 3 * mt * t**2 * ctrl[2] + t**3 * ctrl[3]


def _bez_d1(ctrl, t):
    t = t[:, None]
    mt = 1.0 - t
    return 3 * mt**2 * (ctrl[1] - ctrl[0]) + 6 * mt * t * (ctrl[2] - ctrl[1]) + 3 * t**2 * (ctrl[3] - ctrl[2])


def _bez_d2(ctrl, t):
    t = t[:, None]
    return 6 * (1 - t) * (ctrl[2] - 2 * ctrl[1] + ctrl[0]) + 6 * t * (ctrl[3] - 2 * ctrl[2] + ctrl[1])


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def smooth_closed(pts: np.ndarray, sigma: float) -> np.ndarray:
    """Circular Gaussian smoothing of a closed polyline (N,2)."""
    if sigma <= 0:
        return pts.astype(np.float64)
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    ext = np.concatenate([pts[-r:], pts, pts[:r]]).astype(np.float64)
    return np.stack([np.convolve(ext[:, i], k, mode="valid") for i in range(2)], 1)


def detect_corners(pts: np.ndarray, window: int, angle_deg: float) -> list[int]:
    """Indices where the turning angle between the incoming and outgoing chords (length `window`)
    exceeds `angle_deg`; non-maximum suppression within the window."""
    n = len(pts)
    if n < 2 * window + 1:
        return []
    a = pts - np.roll(pts, window, 0)
    b = np.roll(pts, -window, 0) - pts
    cosang = np.sum(a * b, 1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12)
    ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    cand = np.where(ang > angle_deg)[0]
    corners = []
    for i in cand:
        lo, hi = i - window, i + window
        idx = np.arange(lo, hi + 1) % n
        if ang[i] >= ang[idx].max():
            if all(min(abs(i - c), n - abs(i - c)) > window for c in corners):
                corners.append(int(i))
    return sorted(corners)


def _tangent_at(pts, i, side, span=3):
    """Unit tangent at index i estimated from up to `span` neighbours on one side (+1 forward, -1 backward)."""
    n = len(pts)
    j = min(n - 1, i + span) if side > 0 else max(0, i - span)
    return _unit(pts[j] - pts[i])


# ----------------------------------------------------------------------------- Schneider core
def _chord_params(pts):
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    return d / d[-1] if d[-1] > 0 else np.linspace(0, 1, len(pts))


def _generate(pts, u, t1, t2):
    p0, p3 = pts[0], pts[-1]
    a1 = np.outer(3 * (1 - u) ** 2 * u, t1)
    a2 = np.outer(3 * (1 - u) * u**2, t2)
    c = np.array([[np.sum(a1 * a1), np.sum(a1 * a2)], [np.sum(a1 * a2), np.sum(a2 * a2)]])
    base = _bez(np.array([p0, p0, p3, p3]), u)
    tmp = pts - base
    x = np.array([np.sum(a1 * tmp), np.sum(a2 * tmp)])
    det = c[0, 0] * c[1, 1] - c[0, 1] * c[1, 0]
    seg = np.linalg.norm(p3 - p0)
    if abs(det) > 1e-12:
        al = (x[0] * c[1, 1] - c[0, 1] * x[1]) / det
        ar = (c[0, 0] * x[1] - c[1, 0] * x[0]) / det
    else:
        al = ar = seg / 3.0
    eps = 1e-6 * seg
    if al < eps or ar < eps:                          # Wu/Barsky heuristic fallback
        al = ar = seg / 3.0
    return np.array([p0, p0 + t1 * al, p3 + t2 * ar, p3])


def _reparam(ctrl, pts, u):
    q = _bez(ctrl, u) - pts
    d1, d2 = _bez_d1(ctrl, u), _bez_d2(ctrl, u)
    num = np.sum(q * d1, 1)
    den = np.sum(d1 * d1, 1) + np.sum(q * d2, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        un = np.where(np.abs(den) > 1e-12, u - num / den, u)
    return np.clip(un, 0, 1)


def _max_err(ctrl, pts, u):
    d = np.sum((_bez(ctrl, u) - pts) ** 2, 1)
    i = int(np.argmax(d))
    return float(np.sqrt(d[i])), i


def _fit(pts, t1, t2, tol, out, depth=0):
    if len(pts) == 2:
        dist = np.linalg.norm(pts[1] - pts[0]) / 3.0
        out.append(np.array([pts[0], pts[0] + t1 * dist, pts[1] + t2 * dist, pts[1]]))
        return
    u = _chord_params(pts)
    ctrl = _generate(pts, u, t1, t2)
    err, split = _max_err(ctrl, pts, u)
    if err < tol:
        out.append(ctrl)
        return
    if err < tol * 4:
        for _ in range(8):
            u = _reparam(ctrl, pts, u)
            ctrl = _generate(pts, u, t1, t2)
            err, split = _max_err(ctrl, pts, u)
            if err < tol:
                out.append(ctrl)
                return
    if depth > 40 or len(pts) < 4:
        out.append(ctrl)
        return
    split = min(max(split, 1), len(pts) - 2)
    tc = _unit(pts[split - 1] - pts[split + 1])       # centre tangent, keeps the joint G1 smooth
    _fit(pts[: split + 1], t1, tc, tol, out, depth + 1)
    _fit(pts[split:], -tc, t2, tol, out, depth + 1)


# ----------------------------------------------------------------------------- public API
def fit_closed_contour(contour: np.ndarray, tol: float = 1.0, smooth_sigma: float = 1.5,
                       corner_angle_deg: float = 45.0, corner_window: int = 6) -> list[Anchor]:
    """Fit a closed cubic Bezier spline to a closed contour (N,2) in pixels.

    tol: max allowed distance (px) from the smoothed contour to the curve.
    corner_angle_deg: measured turning-angle threshold. Raster stepping + smoothing attenuate real corners
      (a true 69.7 deg corner measures 55-60 deg at window 6), hence 45 by default; a smooth curve of
      radius r turns only ~2*window/r rad over the window (circle r=200: ~3.4 deg).
    Returns anchors in contour order; handles are absolute positions.
    """
    pts = np.asarray(contour, np.float64).reshape(-1, 2)
    if len(pts) > 2 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < 4:
        raise ValueError("contour too short")
    s = smooth_closed(pts, smooth_sigma)
    corners = detect_corners(s, corner_window, corner_angle_deg)
    n = len(s)
    if len(corners) >= 1:
        breaks, is_corner = corners, True
    else:
        breaks, is_corner = [0, n // 2], False      # smooth loop: two seed splits with shared tangents
    segs_all = []
    for k, b0 in enumerate(breaks):
        b1 = breaks[(k + 1) % len(breaks)]
        idx = np.arange(b0, b1 + (n if b1 <= b0 else 0) + 1) % n
        chunk = s[idx]
        if is_corner:
            t1, t2 = _tangent_at(chunk, 0, +1), _tangent_at(chunk, len(chunk) - 1, -1)
        else:
            t1 = _unit(s[(b0 + 1) % n] - s[(b0 - 1) % n])
            t2 = -_unit(s[(b1 + 1) % n] - s[(b1 - 1) % n])
        out = []
        _fit(chunk, t1, t2, tol, out)
        segs_all.append((out, is_corner))
    # flatten to anchors: anchor i = start of segment i
    segs = [(c, (j == 0 and corner)) for out, corner in segs_all for j, c in enumerate(out)]
    anchors = []
    for i, (c, corner) in enumerate(segs):
        prev = segs[i - 1][0]
        anchors.append(Anchor(p=c[0].copy(), h_in=prev[2].copy(), h_out=c[1].copy(), corner=bool(corner)))
    return anchors


def fit_fixed_count(contour: np.ndarray, k: int, start_hint: np.ndarray | None = None,
                    smooth_sigma: float = 1.5) -> list[Anchor]:
    """Fit a closed spline with exactly `k` anchors (needed for animated Roto shapes: constant topology).

    Anchors are placed at equal arc-length spacing, starting at the contour point closest to `start_hint`
    (e.g. anchor 0 of the previous frame) so that anchor i corresponds across frames. Handles are least-squares
    fitted per segment (Schneider's generator) with G1 tangents estimated from the smoothed contour.
    """
    pts = np.asarray(contour, np.float64).reshape(-1, 2)
    s = smooth_closed(pts, smooth_sigma)
    n = len(s)
    if start_hint is not None:
        s = np.roll(s, -int(np.argmin(((s - start_hint) ** 2).sum(1))), axis=0)
    seg = np.linalg.norm(np.diff(np.vstack([s, s[:1]]), axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    targets = np.arange(k) * total / k
    idx = np.searchsorted(cum, targets).clip(0, n - 1)
    # +-6 contour points: +-2 was measured too noisy (ellipse, k=16: IoU 0.9955 vs 0.9980 with +-6)
    tangents = [_unit(s[(i + 6) % n] - s[(i - 6) % n]) for i in idx]
    anchors_p = [s[i] for i in idx]
    handles = []
    for j in range(k):
        i0, i1 = idx[j], idx[(j + 1) % k]
        chunk = s[np.arange(i0, i1 + (n if i1 <= i0 else 0) + 1) % n]
        if len(chunk) < 3:
            d = np.linalg.norm(chunk[-1] - chunk[0]) / 3.0
            handles.append((chunk[0] + tangents[j] * d, chunk[-1] - tangents[(j + 1) % k] * d))
            continue
        c = _generate(chunk, _chord_params(chunk), tangents[j], -tangents[(j + 1) % k])
        handles.append((c[1], c[2]))
    return [Anchor(p=anchors_p[j].copy(), h_in=handles[j - 1][1].copy(), h_out=handles[j][0].copy(), corner=False)
            for j in range(k)]


def sample_spline(anchors: list[Anchor], per_segment: int = 64) -> np.ndarray:
    """Dense closed polyline of the spline (for rasterising / error measurement)."""
    t = np.linspace(0, 1, per_segment, endpoint=False)
    out = []
    for i, a in enumerate(anchors):
        b = anchors[(i + 1) % len(anchors)]
        out.append(_bez(np.array([a.p, a.h_out, b.h_in, b.p]), t))
    return np.concatenate(out)


def max_deviation(anchors: list[Anchor], contour: np.ndarray) -> tuple[float, float]:
    """(max, mean) distance from each contour point to the nearest densely sampled spline point."""
    curve = sample_spline(anchors, 200)
    c = np.asarray(contour, np.float64).reshape(-1, 2)
    d = np.sqrt(((c[:, None, :] - curve[None, :, :]) ** 2).sum(-1)).min(1)
    return float(d.max()), float(d.mean())
