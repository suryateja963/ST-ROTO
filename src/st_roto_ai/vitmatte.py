"""ViTMatte-S (hustvl/vitmatte-small-composition-1k) on ONNX Runtime: trimap-guided alpha matting (D-032, OPTIONAL).

Licence: weights Apache-2.0; TRAINED ON Composition-1k (Adobe Deep Image Matting data, terms on request from
Adobe, reported non-commercial) - the training-data caveat is shown to the user wherever this model is offered
(docs/RESEARCH_2026-11-16_MATTING.md, R-11). Off by default; download is a separate, explicit step.

Preprocessing reproduces VitMatteImageProcessor exactly (verified by tools/models/export_vitmatte_onnx.py):
RGB in [0,1] -> (x - 0.5) / 0.5, trimap in [0,1] (0 background, 0.5 unknown, 1 foreground), 4 channels,
zero-padded right/bottom to multiples of 32.
"""
from __future__ import annotations

import os

import numpy as np

from .runtime import open_session

NAME = "vitmatte-small-composition-1k"
CAVEAT = ("ViTMatte-S weights are Apache-2.0 but were trained on Composition-1k (Adobe Deep Image Matting data, "
          "terms on request from Adobe). Check that this suits your use before delivering work made with it.")


def model_path(models_root: str) -> str:
    return os.path.join(models_root, NAME, "vitmatte.onnx")


def preprocess(rgb01: np.ndarray, trimap01: np.ndarray, divisor: int = 32) -> np.ndarray:
    """rgb01 (H, W, 3) float in [0,1] (display-encoded, like the photos it was trained on), trimap01 (H, W)."""
    h, w = trimap01.shape
    x = np.concatenate([(np.asarray(rgb01, np.float32)[..., :3] - 0.5) / 0.5,
                        np.asarray(trimap01, np.float32)[..., None]], -1).transpose(2, 0, 1)
    ph, pw = (-h) % divisor, (-w) % divisor
    if ph or pw:
        x = np.pad(x, ((0, 0), (0, ph), (0, pw)))
    return np.ascontiguousarray(x[None], np.float32)


def trimap_from_mask(mask: np.ndarray, inner: int = 6, outer: int = 20) -> np.ndarray:
    """Hard shape mask -> trimap: foreground = mask eroded by `inner` px, background = outside the mask dilated
    by `outer` px (hair and blur extend outward), unknown (0.5) between. Square windows via box sums."""
    from st_roto.matte import box_mean
    m = np.asarray(mask, np.float64) > 0.5
    fg = box_mean(m.astype(np.float64), inner) >= 1.0 - 1e-9 if inner > 0 else m
    near = box_mean(m.astype(np.float64), outer) > 1e-9
    return np.where(fg, 1.0, np.where(near, 0.5, 0.0)).astype(np.float32)


class ViTMatte(object):
    def __init__(self, models_root: str, device: str = "auto"):
        self.session, self.report = open_session(model_path(models_root), device)

    def alpha(self, rgb01: np.ndarray, trimap01: np.ndarray) -> np.ndarray:
        """-> (H, W) float32 alpha in [0,1]; known fg/bg of the trimap are kept exactly."""
        h, w = trimap01.shape
        out = self.session.run(None, {"pixel_values": preprocess(rgb01, trimap01)})[0][0, 0, :h, :w]
        a = np.clip(out, 0.0, 1.0).astype(np.float32)
        a[trimap01 >= 1.0] = 1.0
        a[trimap01 <= 0.0] = 0.0
        return a
