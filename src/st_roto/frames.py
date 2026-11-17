"""Frame lists typed by artists ("12-14, 30, -2--1") and their compact text form (T-097). Pure Python 3.7."""
import re

_TOKEN = re.compile(r"^\s*(-?\d+)\s*(?:-\s*(-?\d+))?\s*$")
_SPACED_DASH = re.compile(r"(\d)\s*-\s*(?=-?\d)")


def parse(text):
    """'12-14, 30' -> [12, 13, 14, 30] (sorted, unique). Accepts commas or spaces, negative frames ('-3--1'),
    spaces around range dashes ('12 - 14') and reversed ranges. Raises ValueError naming the offending part."""
    out = set()
    norm = _SPACED_DASH.sub(lambda m: m.group(1) + "-", (text or "").strip())     # '12 - 14' -> '12-14'
    for part in re.split(r"[,\s]+", norm):
        if not part.strip():
            continue
        m = _TOKEN.match(part)
        if not m:
            raise ValueError("not a frame or range: %r (use e.g. 12-14, 30)" % part.strip())
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        if a > b:
            a, b = b, a
        if b - a > 1000000:
            raise ValueError("range too long: %r" % part.strip())
        out.update(range(a, b + 1))
    return sorted(out)


def ranges(frames):
    """[12, 13, 14, 30] -> '12-14, 30'."""
    fs = sorted(set(frames))
    if not fs:
        return ""
    parts, start, prev = [], fs[0], fs[0]
    for f in fs[1:] + [None]:
        if f is not None and f == prev + 1:
            prev = f
            continue
        parts.append(str(start) if start == prev else "%d-%d" % (start, prev))
        if f is not None:
            start = prev = f
    return ", ".join(parts)
