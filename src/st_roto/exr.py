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
                 attributes: dict = None, rgb=None, extra: dict = None):
    """layers: {object name: H x W float alpha}. Writes `<layer>.A` per object and, if `combined`, `A` = max over
    objects (or the given combined alpha). Unique layer names are enforced (a clash gets a numeric suffix).
    rgb: optional H x W x 3 foreground colour -> R, G, B (T-099; its alpha convention goes in `attributes`).
    extra: {layer: H x W alpha} additional matte layers (e.g. core_matte, edge_matte), never clashing with objects.
    Returns {object name: layer}."""
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
    for name, a in (extra or {}).items():
        ln, i = layer_name(name), 2
        while ln in used:
            ln, i = "%s_%d" % (layer_name(name), i), i + 1
        used.add(ln)
        channels[ln + ".A"] = np.ascontiguousarray(np.clip(a, 0, 1), dtype)
    if rgb is not None:
        rgb = np.asarray(rgb)
        if rgb.shape[:2] != shape:
            raise ValueError("RGB size %r differs from the mattes %r" % (rgb.shape[:2], shape))
        for i, c in enumerate("RGB"):
            channels[c] = np.ascontiguousarray(rgb[..., i], dtype)
    if combined is not None and not isinstance(combined, bool):        # an explicit combined alpha (T-098 roles)
        channels["A"] = np.ascontiguousarray(np.clip(combined, 0, 1), dtype)
    elif combined:
        channels["A"] = np.ascontiguousarray(np.max(np.stack([channels[n + ".A"] for n in names.values()]), 0), dtype)
    header = {"compression": comp, "type": OpenEXR.scanlineimage}
    for k, v in (attributes or {}).items():
        header[k] = str(v)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".part"
    OpenEXR.File(header, channels).write(tmp)
    try:
        os.replace(tmp, path)             # never leave a half-written frame behind (crash safety)
    except PermissionError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise PermissionError("%s is open in another program (e.g. a Nuke Read node showing the mattes) and cannot be "
                              "replaced; render into another folder or close it" % path)
    return names


def is_locked(path: str) -> bool:
    """True if `path` exists and cannot be replaced right now (Windows: another program holds it open without
    delete sharing - a Nuke Read node does, measured in T-099; clearing Nuke's caches or reloading does not
    release it). Tested by renaming the file away and back."""
    if not os.path.exists(path):
        return False
    probe = path + ".lockcheck"
    try:
        os.rename(path, probe)
    except OSError:
        return True
    os.rename(probe, path)
    return False


def next_version_dir(directory: str) -> str:
    """'<dir>' -> '<dir>_v002' (or the next free _vNNN), for rendering when the current files are in use."""
    base = directory.rstrip("/\\")
    i = 2
    while os.path.exists("%s_v%03d" % (base, i)):
        i += 1
    return "%s_v%03d" % (base, i)


def read_channels(path: str) -> dict:
    """{channel name: H x W array} (tests and tools). OpenEXR's Python API groups R, G, B(, A) into one 'RGB'/'RGBA'
    entry (H x W x n); those are split back into single channels."""
    import OpenEXR
    out = {}
    with OpenEXR.File(path) as f:
        for k, v in f.channels().items():
            px = np.array(v.pixels)
            if k in ("RGB", "RGBA") and px.ndim == 3:
                for i, c in enumerate(k):
                    out[c] = px[..., i]
            else:
                out[k] = px
    return out
