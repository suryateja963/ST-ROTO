"""OpenEXR matte files (T-070): one layer per object plus a combined alpha, one file per frame.

Uses the official OpenEXR Python binding (`OpenEXR`, BSD-3-Clause, Academy Software Foundation), imported lazily so
the core stays importable without it. Channel naming follows the EXR layer convention `<layer>.<channel>`; the
combined matte is the plain `A` channel, which Nuke reads as rgba.alpha (verified in tests/nuke).
Frame numbering follows Nuke's sequence convention: 4-digit padding, negative frames as sign + 3 digits
(`name.-002.exr`, measured, CLAUDE.md pitfalls).
"""
from __future__ import annotations

import os
import re

import numpy as np

COMPRESSIONS = ("zip", "piz", "none", "dwaa")


def layer_name(name: str) -> str:
    """Object name -> EXR/Nuke-safe layer name (letters, digits, underscore; no leading digit)."""
    out = re.sub(r"[^A-Za-z0-9_]", "_", name or "object")
    return out if not out[0].isdigit() else "o_" + out


def frame_path(directory: str, base: str, frame: int, ext: str = "exr") -> str:
    f = int(frame)
    num = "%04d" % f if f >= 0 else "-%03d" % (-f)
    return os.path.join(directory, "%s.%s.%s" % (base, num, ext))


def sequence_pattern(directory: str, base: str, ext: str = "exr") -> str:
    """Pattern for a Nuke Read node (forward slashes)."""
    return os.path.join(directory, "%s.####.%s" % (base, ext)).replace("\\", "/")


def write_mattes(path: str, layers: dict, combined=True, compression: str = "zip", half: bool = False,
                 attributes: dict = None):
    """layers: {object name: H x W float alpha}. Writes `<layer>.A` per object and, if `combined`, `A` = max over
    objects. Unique layer names are enforced (a clash gets a numeric suffix). Returns {object name: layer}."""
    import OpenEXR
    if not layers:
        raise ValueError("no mattes to write")
    comp = {"zip": OpenEXR.ZIP_COMPRESSION, "piz": OpenEXR.PIZ_COMPRESSION, "none": OpenEXR.NO_COMPRESSION,
            "dwaa": OpenEXR.DWAA_COMPRESSION}[compression]
    dtype = np.float16 if half else np.float32
    channels, names, used = {}, {}, set()
    shape = None
    for name, a in layers.items():
        a = np.ascontiguousarray(np.clip(a, 0, 1), dtype)
        if shape is None:
            shape = a.shape
        elif a.shape != shape:
            raise ValueError("matte sizes differ: %r vs %r" % (a.shape, shape))
        ln, i = layer_name(name), 2
        while ln in used:
            ln, i = "%s_%d" % (layer_name(name), i), i + 1
        used.add(ln); names[name] = ln
        channels[ln + ".A"] = a
    if combined is not None and not isinstance(combined, bool):        # an explicit combined alpha (T-098 roles)
        channels["A"] = np.ascontiguousarray(np.clip(combined, 0, 1), dtype)
    elif combined:
        channels["A"] = np.ascontiguousarray(np.max(np.stack([channels[n + ".A"] for n in used]), 0), dtype)
    header = {"compression": comp, "type": OpenEXR.scanlineimage}
    for k, v in (attributes or {}).items():
        header[k] = str(v)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".part"
    OpenEXR.File(header, channels).write(tmp)
    os.replace(tmp, path)                 # never leave a half-written frame behind (crash safety)
    return names


def read_channels(path: str) -> dict:
    """{channel name: H x W array} (tests and tools)."""
    import OpenEXR
    with OpenEXR.File(path) as f:
        return {k: np.array(v.pixels) for k, v in f.channels().items()}
