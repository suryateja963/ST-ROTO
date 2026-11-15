"""Model-input colour transform for Nuke (ADR-0010, T-045).

The transforms themselves live in `st_roto.colour` (derived matrices + optional OpenColorIO). This module picks
one for an ST_Roto node: an explicit choice on the node, or "auto", which follows the script's colour management:
  * root colorManagement = "Nuke" (nuke-default)  -> scene-linear Rec.709/sRGB -> sRGB encoded (the v0 transform);
  * root colorManagement = "OCIO"                 -> OpenColorIO processor from the script's working space
                                                     (root workingSpaceLUT) to sRGB-encoded Rec.709, using the
                                                     config file in root OCIOConfigPath.
The transform id goes into every AI result's provenance.
"""
from __future__ import annotations

import numpy as np

from st_roto import colour as _c

TRANSFORM_ID = _c.DEFAULT                   # kept for callers/tests written against v0
AUTO = "auto"
CHOICES = [AUTO] + list(_c.TRANSFORMS)
LABELS = dict([(AUTO, "auto (follow the script's colour management)")] +
              [(k, v[0]) for k, v in _c.TRANSFORMS.items()])


def to_model_input(rgb: np.ndarray, transform=_c.DEFAULT) -> np.ndarray:
    return _c.to_model_input(rgb, transform)


def transform_id(transform) -> str:
    return _c.transform_id(transform)


def resolve(choice: str, root=None):
    """Node choice -> a transform usable by to_model_input (built-in id or OcioTransform). Main thread only."""
    if choice != AUTO:
        if choice not in _c.TRANSFORMS:
            raise ValueError("unknown colour transform %r" % choice)
        return choice
    if root is None:
        import nuke
        root = nuke.root()
    if root["colorManagement"].value() != "OCIO":
        return _c.DEFAULT
    return _c.OcioTransform(root["OCIOConfigPath"].value(), root["workingSpaceLUT"].value())
