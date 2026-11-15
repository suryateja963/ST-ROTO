"""Mask sequence -> animated shapes with constant topology, for objects that split into several pieces (T-049).

A tracked object's mask can break into pieces (an occluder cuts it in two, a person's arm separates from the body).
Roto shapes need a constant point count over time, so each piece becomes its own animated shape:
  * the MAIN shape follows the piece nearest to its previous position (the largest piece at the start);
  * extra pieces become PART shapes, matched across frames by centroid distance; a part is created the first time
    an unmatched piece appears;
  * on frames where a part does not exist it gets a COLLAPSED key (every point at one position: zero area, renders
    nothing in Roto and in mattes) - Roto would otherwise hold or interpolate the neighbouring keys;
  * point counts are ADAPTIVE: the smallest count whose spline fits the piece's contour within tolerance at its
    first appearance (then constant, as Roto requires).
Holes inside a piece (e.g. a ring) are not represented yet (they would need a subtracting shape); they are counted
in `holes` so the caller can report them.
"""
from __future__ import annotations

import numpy as np

from .geometry import _signed_area, fit_fixed_count, max_deviation, trace_contours

COUNTS = (8, 12, 16, 20, 24, 32, 40, 48, 64)


def outer_loops(field, level=0.0, min_area=50.0, min_fraction=0.02):
    """-> (outer loops sorted by area desc, number of holes). Pieces smaller than `min_area` px^2 or than
    `min_fraction` of the largest piece are ignored (speckle)."""
    loops = trace_contours(field, level)
    if not loops:
        return [], 0
    areas = [_signed_area(l) for l in loops]
    sign = np.sign(areas[int(np.argmax(np.abs(areas)))])
    outer = [(abs(a), l) for a, l in zip(areas, loops) if np.sign(a) == sign]
    holes = sum(1 for a in areas if np.sign(a) != sign and abs(a) >= min_area)
    big = max(a for a, _ in outer)
    keep = sorted([(a, l) for a, l in outer if a >= min_area and a >= min_fraction * big], key=lambda t: -t[0])
    return [l for _, l in keep], holes


def choose_count(loop, mean_tol=0.3, max_tol=1.5, counts=COUNTS):
    """Smallest anchor count whose fixed-count spline fits `loop` within tolerances (pixels); the largest count
    if none does. Measured on the synthetic shot's truth masks: 16 (frame 0), 24 (frame 20), 12 (frame 30)."""
    for k in counts:
        mx, mn = max_deviation(fit_fixed_count(loop, k), loop)
        if mn <= mean_tol and mx <= max_tol:
            return k
    return counts[-1]


def to_points(anchors):
    return [[float(a.p[0]), float(a.p[1]), float(a.h_in[0]), float(a.h_in[1]), float(a.h_out[0]), float(a.h_out[1])]
            for a in anchors]


def centroid(points):
    p = np.asarray(points, np.float64)[:, :2]
    return p.mean(0)


def collapsed(count, at):
    x, y = float(at[0]), float(at[1])
    return [[x, y, x, y, x, y] for _ in range(count)]


def is_collapsed(points) -> bool:
    p = np.asarray(points, np.float64)
    return bool(np.ptp(p[:, 0]) == 0 and np.ptp(p[:, 1]) == 0)


class Sequencer(object):
    """Feed one mask per frame in VISIT order (`add`), then `result(frames)`.

    count: fixed main-shape point count, or "auto". `ref`: the frame whose shapes give point order and positions
    for this one (the previous frame in visit order; a reverse pass starts again from its conditioning frame).
    Frames the AI did not decide (artist keys) are registered with `add_known` so they can serve as references."""

    def __init__(self, count="auto", parts=True, min_area=50.0, min_fraction=0.02, match_px=None):
        self.count = count
        self.parts_enabled = parts
        self.min_area, self.min_fraction = min_area, min_fraction
        self.match_px = match_px
        self.main = {}              # frame -> points ([] = no object)
        self.parts = []             # [{"count", "keys": {frame: points}}]
        self.holes = {}             # frame -> number of holes ignored

    # -- references ---------------------------------------------------------------------------
    def add_known(self, frame, points):
        self.main[frame] = points
        if self.count == "auto" and points:
            self.count = len(points)

    def _ref_main(self, ref):
        pts = self.main.get(ref) if ref is not None else None
        return pts or None

    # -- one frame ------------------------------------------------------------------------------
    def add(self, frame, field, ref=None, present=True):
        """field: mask logits (or binary - 0.5) of the whole object; present=False: AI says no object here."""
        loops, holes = outer_loops(field, min_area=self.min_area, min_fraction=self.min_fraction) if present else ([], 0)
        if holes:
            self.holes[frame] = holes
        if not loops:
            self.main[frame] = []
            return self.main[frame]
        prev = self._ref_main(ref)
        if prev:
            c = centroid(prev)
            i = int(np.argmin([np.linalg.norm(l.mean(0) - c) for l in loops]))
        else:
            i = 0
        main_loop = loops.pop(i)
        if self.count == "auto":
            self.count = choose_count(main_loop)
        hint = np.array(prev[0][:2]) if prev else None
        self.main[frame] = to_points(fit_fixed_count(main_loop, int(self.count), start_hint=hint))
        if self.parts_enabled:
            self._assign_parts(frame, loops, ref)
        return self.main[frame]

    def _assign_parts(self, frame, loops, ref):
        free = list(range(len(self.parts)))
        for loop in loops:                                   # largest first
            c = loop.mean(0)
            size = np.sqrt(abs(_signed_area(loop)))
            best, best_d = None, None
            for j in free:
                last = self._part_ref(j, ref)
                if last is None:
                    continue
                d = np.linalg.norm(centroid(last) - c)
                lim = self.match_px or max(40.0, 1.5 * size)
                if d <= lim and (best_d is None or d < best_d):
                    best, best_d = j, d
            if best is None:
                self.parts.append({"count": choose_count(loop), "keys": {}})
                best = len(self.parts) - 1
            else:
                free.remove(best)
            part = self.parts[best]
            last = self._part_ref(best, ref)
            hint = np.array(last[0][:2]) if last is not None else None
            part["keys"][frame] = to_points(fit_fixed_count(loop, part["count"], start_hint=hint))

    def _part_ref(self, j, ref):
        """Most recent real (non-collapsed) key of part j at or before the reference frame in visit terms: the
        reference frame itself if present, otherwise the part's last key."""
        keys = self.parts[j]["keys"]
        if ref is not None and ref in keys:
            return keys[ref]
        return keys[max(keys)] if keys else None

    # -- output -------------------------------------------------------------------------------
    def result(self, frames):
        """-> {"main": {frame: points}, "parts": [{frame: points}], "holes": {...}}. Parts get collapsed keys on
        every frame of `frames` (that the AI decided) where they do not exist, at their nearest real position."""
        decided = [f for f in frames if f in self.main]
        parts = []
        for p in self.parts:
            real = sorted(p["keys"])
            out = {}
            for f in decided:
                if f in p["keys"]:
                    out[f] = p["keys"][f]
                else:
                    near = min(real, key=lambda r: abs(r - f))
                    out[f] = collapsed(p["count"], centroid(p["keys"][near]))
            parts.append(out)
        return {"main": {f: self.main[f] for f in decided if self.main[f]}, "parts": parts, "holes": dict(self.holes)}
