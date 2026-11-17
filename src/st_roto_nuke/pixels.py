"""Nuke -> numpy pixel transfer (ADR-0003). v0 renders one frame at a time through a Write node to an uncompressed
float TIFF and reads it back (measured ~26-90 ms/frame at 720p-1080p). An in-memory path is task T-046.
Must run on Nuke's MAIN thread (nuke.execute); worker threads call it via nuke.executeInMainThreadWithResult.

Difficult sequences (T-086, master prompt section 11, measured in research/probes/2026-11-17_sequences):
* a frame Nuke cannot read (missing file, gap in a discontinuous sequence) raises `FrameUnavailable`; callers
  skip it and report it instead of failing the whole run;
* proxy mode: the Write node needs a proxy file name, otherwise Nuke refuses to execute it; the frame then comes
  at proxy resolution and is brought to the shot format by `fit_to_format`;
* an edition render limit (Non-commercial: 1920 x 1080) raises `ResolutionCapped`; the node then renders the
  frame reduced into that box and scales it back, so tracking still works on larger plates (T-089);
* a frame whose resolution differs from the shot (mixed-resolution sequences) is brought to the shot format the
  way Nuke's default Reformat node does (scale to the format width, centred), so shapes stay in shot coordinates.
"""
from __future__ import annotations

import os
import re
import tempfile

import numpy as np

_MISSING = ("no such file", "read error", "cannot open", "can't open", "missing frame", "file not found")


class ResolutionCapped(Exception):
    """The Nuke edition refuses to render this size (Non-commercial: 1920 x 1080, measured, T-089). `limit` is
    (width, height) parsed from Nuke's message, or None if it could not be parsed."""

    def __init__(self, message):
        Exception.__init__(self, message)
        m = re.search(r"\((\d+)\s*x\s*(\d+)\)", message)
        self.limit = (int(m.group(1)), int(m.group(2))) if m else None


class FrameUnavailable(Exception):
    """Nuke could not produce this frame (e.g. the file is missing). `frame` and Nuke's message are kept."""

    def __init__(self, frame, message):
        Exception.__init__(self, "frame %s unavailable: %s" % (frame, message))
        self.frame, self.message = frame, message


class FrameExcluded(FrameUnavailable):
    """The artist excluded this frame from AI processing (T-097): skipped exactly like an unreadable frame (no key,
    existing keys untouched, true time positions), reported as excluded."""

    def __init__(self, frame):
        FrameUnavailable.__init__(self, frame, "excluded by the artist")


def configure_write(write_node, path: str):
    write_node["file"].setValue(path.replace("\\", "/"))
    write_node["proxy"].setValue(path.replace("\\", "/"))     # proxy mode refuses to render without one (T-086)
    write_node["file_type"].setValue("tiff")
    write_node["datatype"].setValue("32 bit float")
    write_node["compression"].setValue("none")
    write_node["channels"].setValue("rgb")


def render_frame(write_node, frame: int, path: str, view: str = None):
    """Render `frame` through `write_node` (temporarily enabled) and return HxWx3 float32 linear RGB at the size
    Nuke produced (see `fit_to_format`). Raises FrameUnavailable when Nuke cannot read the frame.
    view: the script view to render (T-109). In a script with several views Nuke refuses to execute a Write whose
    file has no %V for all views ("cannot be executed for multiple views", measured), so callers always name one."""
    import nuke
    import cv2                                    # from the bundled site folder (pip OpenCV has TIFF, not EXR)
    if write_node["proxy"].value() != write_node["file"].value():          # nodes created before T-086
        write_node["proxy"].setValue(write_node["file"].value())
    write_node["disable"].setValue(False)
    try:
        if view:
            nuke.execute(write_node, frame, frame, 1, views=[view])
        else:
            nuke.execute(write_node, frame, frame)
    except RuntimeError as e:
        text = str(e)
        if "maximum resolution allowed" in text.lower():
            raise ResolutionCapped(text.strip())
        if any(m in text.lower() for m in _MISSING):
            raise FrameUnavailable(frame, text.strip().splitlines()[-1][:300])
        raise
    finally:
        write_node["disable"].setValue(True)
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError("rendered frame %d could not be read from %s" % (frame, path))
    return img[:, :, ::-1].copy()                 # BGR -> RGB


def render_channels(write_node, frame: int, path: str, view: str = None, channels: str = "all") -> dict:
    """Every channel (or one layer) of `frame` as {EXR channel name: HxW float array} (T-110): the pixel Write is
    switched to a 32-bit float EXR for this render and restored afterwards (rgba comes back as R/G/B/A, other
    layers keep Nuke's names, e.g. depth.Z, forward.u, CryptoObject00.R). Main thread. Raises FrameUnavailable."""
    import nuke
    from st_roto import exr
    knobs = ("file", "proxy", "file_type", "datatype", "channels", "compression")
    saved = {k: write_node[k].value() for k in knobs if k in write_node.knobs()}
    try:
        write_node["file"].setValue(path.replace("\\", "/"))
        write_node["proxy"].setValue(path.replace("\\", "/"))
        write_node["file_type"].setValue("exr")
        write_node["datatype"].setValue("32 bit float")
        write_node["channels"].setValue(channels)
        if "compression" in write_node.knobs():
            write_node["compression"].setValue("none")
        write_node["disable"].setValue(False)
        try:
            if view:
                nuke.execute(write_node, frame, frame, 1, views=[view])
            else:
                nuke.execute(write_node, frame, frame)
        except RuntimeError as e:
            text = str(e)
            if any(m in text.lower() for m in _MISSING):
                raise FrameUnavailable(frame, text.strip().splitlines()[-1][:300])
            raise
        return exr.read_channels(path)
    finally:
        write_node["disable"].setValue(True)
        if "file_type" in saved:                      # file_type first so its knobs exist again
            write_node["file_type"].setValue(saved["file_type"])
        for k, v in saved.items():
            if k != "file_type":
                try:
                    write_node[k].setValue(v)
                except Exception:                     # noqa: BLE001 - e.g. a knob of the other file type
                    pass


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
