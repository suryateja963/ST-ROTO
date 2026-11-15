"""Nuke -> numpy pixel transfer (ADR-0003). v0 renders one frame at a time through a Write node to an uncompressed
float TIFF and reads it back (measured ~26-90 ms/frame at 720p-1080p). An in-memory path is task T-046.
Must run on Nuke's MAIN thread (nuke.execute); worker threads call it via nuke.executeInMainThreadWithResult.
"""
from __future__ import annotations

import os
import tempfile


def configure_write(write_node, path: str):
    write_node["file"].setValue(path.replace("\\", "/"))
    write_node["file_type"].setValue("tiff")
    write_node["datatype"].setValue("32 bit float")
    write_node["compression"].setValue("none")
    write_node["channels"].setValue("rgb")


def render_frame(write_node, frame: int, path: str):
    """Render `frame` through `write_node` (temporarily enabled) and return HxWx3 float32 linear RGB."""
    import nuke
    import cv2                                    # from the bundled site folder (pip OpenCV has TIFF, not EXR)
    write_node["disable"].setValue(False)
    try:
        nuke.execute(write_node, frame, frame)
    finally:
        write_node["disable"].setValue(True)
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError("rendered frame %d could not be read from %s" % (frame, path))
    return img[:, :, ::-1].copy()                 # BGR -> RGB


def temp_pixel_path(tag: str) -> str:
    d = os.path.join(tempfile.gettempdir(), "st_roto")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "px_%s.tif" % "".join(c if c.isalnum() else "_" for c in tag))
