"""T-089 / REQ-110, REQ-111: build format and resolution variants of the synthetic shot (6 frames each).

out/<case>/frame_####.<ext> (plate) + gt_####.png (truth at the plate's size) + case.json. Formats written here:
PNG 16-bit, TIFF 16-bit, EXR half and float (scene-linear, via OpenEXR). DPX is written by Nuke in the probe (no
DPX writer outside Nuke). Run: .venv\\Scripts\\python.exe -I research/probes/2026-11-17_formats/make_formats.py
"""
import json
import os
import shutil

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "2026-11-15_video", "frames")
OUT = os.path.join(HERE, "out")
N = 6

# case: (width, height, file extension, writer)
CASES = {
    "png16": (1280, 720, "png", "png16"),
    "tiff16": (1280, 720, "tif", "tiff16"),
    "exr_half": (1280, 720, "exr", "half"),
    "exr_float": (1280, 720, "exr", "float"),
    "dci2k": (2048, 1080, "png", "png8"),
    "uhd4k": (3840, 2160, "png", "png8"),
    "dci4k": (4096, 2160, "png", "png8"),
    "uhd8k": (7680, 4320, "png", "png8"),
    "vertical": (1080, 1920, "png", "png8"),
    "scope": (1920, 804, "png", "png8"),
    "anamorphic": (1280, 720, "png", "png8"),          # same pixels; the probe gives the Read a 2:1 pixel aspect
}


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def write(path, rgb8, kind):
    """rgb8: HxWx3 uint8 RGB (display-encoded sRGB, as the synthetic PNGs)."""
    if kind == "png8":
        cv2.imwrite(path, rgb8[:, :, ::-1])
    elif kind in ("png16", "tiff16"):
        cv2.imwrite(path, (rgb8[:, :, ::-1].astype(np.uint16) * 257))
    else:
        import OpenEXR
        lin = srgb_to_linear(rgb8.astype(np.float64) / 255.0)
        dt = np.float16 if kind == "half" else np.float32
        ch = {c: np.ascontiguousarray(lin[:, :, i], dt) for i, c in enumerate("RGB")}
        OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}, ch).write(path)


def main():
    meta = json.load(open(os.path.join(SRC, "meta.json")))
    for case, (w, h, ext, kind) in CASES.items():
        d = os.path.join(OUT, case)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        for f in range(N):
            img = cv2.imread(os.path.join(SRC, "frame_%04d.png" % f))[:, :, ::-1]
            gt = cv2.imread(os.path.join(SRC, "gt_%04d.png" % f), cv2.IMREAD_GRAYSCALE)
            if (w, h) != (img.shape[1], img.shape[0]):
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
                gt = cv2.resize(gt, (w, h), interpolation=cv2.INTER_NEAREST)
            write(os.path.join(d, "frame_%04d.%s" % (f, ext)), img, kind)
            cv2.imwrite(os.path.join(d, "gt_%04d.png" % f), gt)
        sx, sy = w / 1280.0, h / 720.0
        cx, cy = meta["click_xy"]
        json.dump({"width": w, "height": h, "ext": ext, "kind": kind, "frames": N, "click_xy": [cx * sx, cy * sy]},
                  open(os.path.join(d, "case.json"), "w"), indent=1)
        print(case, w, h, ext, kind)


if __name__ == "__main__":
    main()
