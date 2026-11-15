"""Model-input colour transforms (ADR-0010, T-045). Pure numpy; OpenColorIO is used only for `ocio` transforms.

SAM 2.1 (and most vision models) were trained on sRGB-encoded 8-bit photos, so frames are converted from the
host's working space to sRGB-encoded Rec.709 in [0, 1] before inference. Built-in transforms are DERIVED here from
the published primaries / white points (RGB->XYZ from chromaticities, Bradford chromatic adaptation), not typed-in
matrices, and are tested against published reference matrices and against OpenColorIO's ACES configs.

Every transform has a stable id that is written into the provenance of AI results (reproducibility).
"""
from __future__ import annotations

import numpy as np

# chromaticities (x, y) of R, G, B and white
PRIMARIES = {
    "rec709": ((0.640, 0.330), (0.300, 0.600), (0.150, 0.060), (0.3127, 0.3290)),    # = sRGB, D65 (ITU-R BT.709)
    "ap1": ((0.713, 0.293), (0.165, 0.830), (0.128, 0.044), (0.32168, 0.33767)),       # ACEScg (S-2014-004), ACES white
    "ap0": ((0.7347, 0.2653), (0.0, 1.0), (0.0001, -0.0770), (0.32168, 0.33767)),      # ACES2065-1 (SMPTE ST 2065-1)
    "rec2020": ((0.708, 0.292), (0.170, 0.797), (0.131, 0.046), (0.3127, 0.3290)),     # ITU-R BT.2020, D65
    "p3d65": ((0.680, 0.320), (0.265, 0.690), (0.150, 0.060), (0.3127, 0.3290)),       # Display P3 / P3-D65
}
BRADFORD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])


def _xyz(xy):
    x, y = xy
    return np.array([x / y, 1.0, (1 - x - y) / y])


def rgb_to_xyz(name: str) -> np.ndarray:
    r, g, b, w = PRIMARIES[name]
    m = np.stack([_xyz(r), _xyz(g), _xyz(b)], 1)
    s = np.linalg.solve(m, _xyz(w))
    return m * s


def bradford(src_white, dst_white) -> np.ndarray:
    s, d = BRADFORD @ _xyz(src_white), BRADFORD @ _xyz(dst_white)
    return np.linalg.inv(BRADFORD) @ np.diag(d / s) @ BRADFORD


def conversion_matrix(src: str, dst: str = "rec709") -> np.ndarray:
    """Linear RGB in `src` primaries -> linear RGB in `dst` primaries (Bradford adaptation between whites)."""
    cat = bradford(PRIMARIES[src][3], PRIMARIES[dst][3])
    return np.linalg.inv(rgb_to_xyz(dst)) @ cat @ rgb_to_xyz(src)


def srgb_encode(x: np.ndarray) -> np.ndarray:
    """IEC 61966-2-1 piecewise sRGB curve on [0, 1]."""
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


# id -> (label, primaries or None, needs encoding). Ids are stable: they go into provenance.
TRANSFORMS = {
    "linear_srgb_to_srgb_encoded_v0": ("scene-linear Rec.709 / sRGB (Nuke default)", "rec709", True),
    "acescg_to_srgb_encoded_v1": ("ACEScg (AP1 linear)", "ap1", True),
    "aces2065_to_srgb_encoded_v1": ("ACES2065-1 (AP0 linear)", "ap0", True),
    "linear_rec2020_to_srgb_encoded_v1": ("linear Rec.2020", "rec2020", True),
    "linear_p3d65_to_srgb_encoded_v1": ("linear P3-D65", "p3d65", True),
    "display_encoded_passthrough_v1": ("already display-encoded (sRGB / Rec.709 video)", None, False),
}
DEFAULT = "linear_srgb_to_srgb_encoded_v0"


def to_model_input(rgb: np.ndarray, transform: str = DEFAULT) -> np.ndarray:
    """H x W x 3 float in the source space -> sRGB-encoded Rec.709 float32 in [0, 1]. `transform`: a built-in id
    or an `OcioTransform`."""
    if isinstance(transform, OcioTransform):
        return transform(rgb)
    if transform not in TRANSFORMS:
        raise ValueError("unknown colour transform %r" % (transform,))
    _, prim, encode = TRANSFORMS[transform]
    x = np.asarray(rgb, np.float32)[..., :3]
    if prim and prim != "rec709":
        x = x @ conversion_matrix(prim, "rec709").T.astype(np.float32)
    if encode:
        return srgb_encode(x).astype(np.float32)
    return np.clip(x, 0.0, 1.0).astype(np.float32)


def transform_id(transform) -> str:
    return transform.id if isinstance(transform, OcioTransform) else transform


SRGB_TARGETS = ("sRGB Encoded Rec.709 (sRGB)", "sRGB - Texture", "Utility - sRGB - Texture", "sRGB")


class OcioTransform(object):
    """OpenColorIO conversion `src` -> sRGB-encoded Rec.709 with a given config (file path or ocio:// URI).
    The id records config, its cache id and both colour spaces."""

    def __init__(self, config: str, src: str, dst: str = None):
        import PyOpenColorIO as OCIO
        self.config_path = config
        cfg = OCIO.Config.CreateFromFile(config)
        names = set(cfg.getColorSpaceNames())
        roles = dict(cfg.getRoles()) if hasattr(cfg, "getRoles") else {}
        if src not in names and src not in roles:
            raise ValueError("colour space %r is not in OCIO config %s" % (src, config))
        dst = dst or next((n for n in SRGB_TARGETS if n in names), None)
        if dst is None:
            raise ValueError("OCIO config %s has no sRGB-encoded colour space (%s)" % (config, ", ".join(SRGB_TARGETS)))
        self.src, self.dst = src, dst
        self._cpu = cfg.getProcessor(src, dst).getDefaultCPUProcessor()
        self.id = "ocio_v1:%s|%s|%s|%s" % (config, cfg.getCacheID(), src, dst)

    def __call__(self, rgb):
        # applyRGB works IN PLACE: always on a private copy (np.ascontiguousarray would return the caller's own
        # array when it is already contiguous float32 and the caller's frame would be overwritten - found in testing)
        x = np.array(np.asarray(rgb, np.float32)[..., :3], dtype=np.float32, order="C", copy=True)
        self._cpu.applyRGB(x)
        return np.clip(x, 0.0, 1.0).astype(np.float32)
