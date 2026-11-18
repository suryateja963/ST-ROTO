"""Scene-cut detection (T-123, master prompt section 11: temporal strategies; acceptance criterion 7).

A tracker must not carry an object across a hard cut: after the cut the pixels belong to another shot, and SAM 2.1
keeps "finding" something there. Pure Python + numpy (no Nuke / OpenCV / AI): the host passes frames in.

Method (classic shot-boundary detection, made robust for VFX plates):
* every frame -> a small thumbnail (area average to about 64 x 36, display-encoded so dark plates are not flat);
* score of each pair of consecutive frames = colour-histogram distance (1 - intersection of 8x8x8 joint RGB
  histograms; insensitive to motion inside the frame) and the mean thumbnail difference;
* a CUT between f-1 and f when the histogram distance is high in absolute terms (>= HIST_MIN) AND much higher than
  around it (>= RATIO x the median of the neighbouring scores: fast camera moves raise every score, a cut only one);
* flashes, one- or two-frame glitches and strobes are NOT cuts: if the frame before the jump matches a frame
  shortly after it (within FLASH_SPAN), the content came back.
Dissolves / fades are gradual and are not detected (documented limit); the artist can type cut frames by hand.
Thresholds were set on synthetic sequences and checked on real footage (research/probes/2026-11-18_scenecut)."""
import numpy as np

THUMB = (36, 64)              # rows, columns
BINS = 8                      # per channel -> 512-bin joint histogram
HIST_MIN = 0.25               # absolute floor of the histogram distance for a cut
DIFF_MIN = 0.08               # absolute floor of the mean thumbnail difference (0..1)
RATIO = 5.0                   # a cut must stand out from its neighbourhood by this factor
WINDOW = 4                    # neighbours on each side for the local median
FLASH_SPAN = 3                # frames after the jump checked for "the old content came back"


def thumbnail(rgb):
    """H x W x 3 (linear or display float, or uint8) -> THUMB float32 in [0, 1], display-encoded."""
    a = np.asarray(rgb)
    if a.dtype == np.uint8:
        x = a[..., :3].astype(np.float32) / 255.0
    else:
        x = np.clip(np.asarray(a[..., :3], np.float32), 0.0, 1.0) ** (1.0 / 2.2)   # linear -> roughly display
    h, w = x.shape[:2]
    th, tw = min(THUMB[0], h), min(THUMB[1], w)
    ys = (np.arange(th + 1) * h) // th
    xs = (np.arange(tw + 1) * w) // tw
    c = np.cumsum(np.cumsum(np.pad(x, ((1, 0), (1, 0), (0, 0))), 0), 1)            # summed-area table
    s = c[ys[1:]][:, xs[1:]] - c[ys[:-1]][:, xs[1:]] - c[ys[1:]][:, xs[:-1]] + c[ys[:-1]][:, xs[:-1]]
    area = ((ys[1:] - ys[:-1])[:, None] * (xs[1:] - xs[:-1])[None, :])[..., None]
    return (s / area).astype(np.float32)


def histogram(t):
    q = np.minimum((t * BINS).astype(np.int32), BINS - 1)
    idx = (q[..., 0] * BINS + q[..., 1]) * BINS + q[..., 2]
    h = np.bincount(idx.ravel(), minlength=BINS ** 3).astype(np.float32)
    return h / max(1.0, h.sum())


def distance(ta, tb, ha=None, hb=None):
    """(histogram distance, mean abs thumbnail difference) of two thumbnails."""
    ha = histogram(ta) if ha is None else ha
    hb = histogram(tb) if hb is None else hb
    return float(1.0 - np.minimum(ha, hb).sum()), float(np.abs(ta - tb).mean())


def scores(thumbs):
    """Per consecutive pair: [(hist, diff)] with len(thumbs) - 1 entries (entry i = frames i -> i + 1)."""
    hs = [histogram(t) for t in thumbs]
    return [distance(thumbs[i], thumbs[i + 1], hs[i], hs[i + 1]) for i in range(len(thumbs) - 1)]


def detect(thumbs, frames=None):
    """thumbs: thumbnails in shot order; frames: their frame numbers (default 0..n-1; gaps allowed). Returns the
    frames that START a new shot, and a per-pair report [{frame, hist, diff, local, cut, why}]."""
    n = len(thumbs)
    frames = list(range(n)) if frames is None else list(frames)
    if n < 2:
        return [], []
    hs = [histogram(t) for t in thumbs]
    sc = [distance(thumbs[i], thumbs[i + 1], hs[i], hs[i + 1]) for i in range(n - 1)]
    hist = np.array([s[0] for s in sc])
    cuts, report = [], []
    for i in range(n - 1):
        nb = [hist[j] for j in range(max(0, i - WINDOW), min(n - 1, i + WINDOW + 1)) if j != i]
        local = float(np.median(nb)) if nb else 0.0
        h, d = sc[i]
        cut = h >= HIST_MIN and d >= DIFF_MIN and h >= RATIO * max(local, 0.02)
        why = ""
        if cut:
            # flash / glitch: the content before the jump comes back shortly after it (jump INTO the flash), or the
            # frame after the jump matches one shortly before it (jump OUT of the flash)
            pairs = [(i, k) for k in range(i + 2, min(n, i + 2 + FLASH_SPAN))] + \
                    [(j, i + 1) for j in range(max(0, i - FLASH_SPAN + 1), i)]
            for a, b in pairs:
                back_h, back_d = distance(thumbs[a], thumbs[b], hs[a], hs[b])
                if back_h < 0.5 * h and back_d < 0.75 * d:   # motion raises d: looser
                    cut, why = False, "flash: frame %s matches frame %s" % (frames[b], frames[a])
                    break
        report.append({"frame": frames[i + 1], "hist": round(h, 4), "diff": round(d, 4), "local": round(local, 4),
                       "cut": bool(cut), "why": why})
        if cut:
            cuts.append(frames[i + 1])
    return cuts, report


def segment(frame, cuts, first, last):
    """(lo, hi) of the shot segment holding `frame` within first..last, given the cut frames (each starts a new
    segment)."""
    lo, hi = first, last
    for c in sorted(cuts):
        if c <= frame:
            lo = max(lo, c)
        elif c - 1 < hi:
            hi = c - 1
            break
    return lo, hi


def parse(text):
    """'12, 48' -> [12, 48] (the knob holding the cuts; the artist may edit it)."""
    out = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(float(part)))
        except ValueError:
            raise ValueError("scene cuts: %r is not a frame number" % part)
    return sorted(set(out))


def format_cuts(cuts):
    return ", ".join(str(int(c)) for c in sorted(set(cuts)))
