"""Nuke -> numpy pixel transfer (ADR-0003). v0 renders one frame at a time through a Write node to an uncompressed
float TIFF and reads it back (measured ~26-90 ms/frame at 720p-1080p). An in-memory path is task T-046.
Must run on Nuke's MAIN thread (nuke.execute); worker threads call it via nuke.executeInMainThreadWithResult.

Difficult sequences (T-086, master prompt section 11, measured in research/probes/2026-11-17_sequences):
* a frame Nuke cannot read (missing file, gap in a discontinuous sequence) raises `FrameUnavailable`; callers
  skip it and report it instead of failing the whole run;
* proxy mode: the Write node needs a proxy file name, otherwise Nuke refuses to execute it; the frame then comes
  at proxy resolution and is brought to the shot format by `fit_to_format`;
* a frame whose resolution differs from the shot (mixed-resolution sequences) is brought to the shot format the
  way Nuke's default Reformat node does (scale to the format width, centred), so shapes stay in shot coordinates.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np

_MISSING = ("no such file", "read error", "cannot open", "can't open", "missing frame", "file not found")


class FrameUnavailable(Exception):
    """Nuke could not produce this frame (e.g. the file is missing). `frame` and Nuke's message are kept."""

    def __init__(self, frame, message):
        Exception.__init__(self, "frame %s unavailable: %s" % (frame, message))
        self.frame, self.message = frame, message


def configure_write(write_node, path: str):
    write_node["file"].setValue(path.replace("\\", "/"))
    write_node["proxy"].setValue(path.replace("\\", "/"))     # proxy mode refuses to render without one (T-086)
    write_node["file_type"].setValue("tiff")
    write_node["datatype"].setValue("32 bit float")
    write_node["compression"].setValue("none")
    write_node["channels"].setValue("rgb")


def render_frame(write_node, frame: int, path: str):
    """Render `frame` through `write_node` (temporarily enabled) and return HxWx3 float32 linear RGB at the size
    Nuke produced (see `fit_to_format`). Raises FrameUnavailable when Nuke cannot read the frame."""
    import nuke
    import cv2                                    # from the bundled site folder (pip OpenCV has TIFF, not EXR)
    if write_node["proxy"].value() != write_node["file"].value():          # nodes created before T-086
        write_node["proxy"].setValue(write_node["file"].value())
    write_node["disable"].setValue(False)
    try:
        nuke.execute(write_node, frame, frame)
    except RuntimeError as e:
        text = str(e)
        if any(m in text.lower() for m in _MISSING):
            raise FrameUnavailable(frame, text.strip().splitlines()[-1][:300])
        raise
    finally:
        write_node["disable"].setValue(True)
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError("rendered frame %d could not be read from %s" % (frame, path))
    return img[:, :, ::-1].copy()                 # BGR -> RGB


def fit_to_format(img, width: int, height: int):
    """Bring an image of another size to width x height like Nuke's default Reformat (resize type 'width',
    centred, black outside / cropped). Returns the image unchanged if it already has that size."""
    h, w = img.shape[:2]
    if (w, h) == (width, height):
        return img
    import cv2
    nh = int(round(h * width / float(w)))
    interp = cv2.INTER_AREA if width < w else cv2.INTER_LINEAR
    scaled = cv2.resize(img, (width, nh), interpolation=interp)
    if scaled.ndim == 2:
        scaled = scaled[:, :, None]
    out = np.zeros((height, width, scaled.shape[2]), img.dtype)
    if nh >= height:
        top = (nh - height) // 2
        out[:] = scaled[top:top + height]
    else:
        top = (height - nh) // 2
        out[top:top + nh] = scaled
    return out.reshape((height, width) + img.shape[2:])


def temp_pixel_path(tag: str) -> str:
    d = os.path.join(tempfile.gettempdir(), "st_roto")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "px_%s.tif" % "".join(c if c.isalnum() else "_" for c in tag))
