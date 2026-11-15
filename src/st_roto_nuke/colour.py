"""Model-input colour transform (ADR-0010) — v0.

v0 implements ONE explicit, documented transform: scene-linear Rec.709/sRGB primaries -> sRGB-encoded (IEC 61966-2-1
piecewise curve), clipped to [0,1]. It is correct when Nuke's working space is linear sRGB/Rec.709 (Nuke's default
nuke-default config); it is NOT correct for ACES or other working spaces. The OCIO-based, configurable version is
task T-045. The transform id is written into every AI-generated key's provenance so results stay reproducible.
"""
from __future__ import annotations

import numpy as np

TRANSFORM_ID = "linear_srgb_to_srgb_encoded_v0"


def to_model_input(linear_rgb: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(linear_rgb, np.float32), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)
