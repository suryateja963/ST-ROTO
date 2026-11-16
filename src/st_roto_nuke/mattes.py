"""Matte pass (T-069/T-070): every object of a shot -> (refined) alpha -> one multi-layer EXR per frame.

No Nuke calls: plate frames come from an injected `get_rgb(frame)` (scene-linear, like tracking). Each object's
hard mask is the exact rasterisation of its stored splines (st_roto.matte.object_mask); with `soft=True` the edge
band is refined with the guided filter against the plate (st_roto.matte.refine_alpha, model-free). The plate is
read only when soft edges are requested.
"""
from __future__ import annotations

import json
import os
import time

from st_roto import exr, matte
from . import colour

PASS_ID = "st_roto_matte_v1"


def default_output_dir(project_path: str, shot_name: str) -> str:
    base = os.path.splitext(os.path.abspath(project_path))[0]
    return os.path.join(base + "_mattes", exr.layer_name(shot_name))


METHODS = ("guided", "vitmatte", "hard")


def _vitmatte_crop(vm, guide, mask, inner=6, outer=20, margin=8):
    """ViTMatte-S on the bounding box of the unknown zone only (cost scales with the outline, not the frame)."""
    from st_roto_ai.vitmatte import trimap_from_mask
    import numpy as np
    alpha = mask.astype("float32")
    tri_full = trimap_from_mask(mask, inner, outer)
    ys, xs = np.nonzero(tri_full == 0.5)
    if not len(xs):
        return alpha
    y0, y1 = max(0, ys.min() - margin), min(mask.shape[0], ys.max() + margin + 1)
    x0, x1 = max(0, xs.min() - margin), min(mask.shape[1], xs.max() + margin + 1)
    a = vm.alpha(guide[y0:y1, x0:x1], tri_full[y0:y1, x0:x1])
    alpha[y0:y1, x0:x1] = a
    return alpha


def render_mattes(get_rgb, store, shot_id, frames, out_dir, soft=True, band=3, radius=8, eps=1e-4,
                  objects=None, compression="zip", job=None, colour_transform=colour.TRANSFORM_ID, method=None,
                  models_root=None, device="auto"):
    """Write `<out_dir>/<shot>_mattes.####.exr` for `frames`. objects: object ids (default: every object of the
    shot). Returns {"pattern", "files", "layers": {object name: layer}, "frames_interpolated": {name: [frames]},
    "frames_held": {...}, "seconds"}."""
    t0 = time.time()
    method = method or ("guided" if soft else "hard")
    if method not in METHODS:
        raise ValueError("unknown edge method %r" % method)
    soft = method != "hard"
    vm = None
    if method == "vitmatte":                       # D-032: optional model, verified by the registry before loading
        from st_roto_ai.vitmatte import ViTMatte, model_path
        import os as _os
        if not _os.path.exists(model_path(models_root)):
            raise ValueError("ViTMatte-S is not installed (optional download, D-032): run "
                             "tools/models/download_models.py vitmatte-small-composition-1k and "
                             "tools/models/export_vitmatte_onnx.py")
        vm = ViTMatte(models_root, device)
    shot = store.row("shots", shot_id)
    if shot is None:
        raise KeyError("no shot %s" % shot_id)
    w, h = int(shot["width"]), int(shot["height"])
    objs = [o for o in store.objects(shot_id) if objects is None or o["id"] in objects]
    objs = [o for o in objs if store.shapes(o["id"])]
    if not objs:
        raise ValueError("no objects with shapes to render")
    base = exr.layer_name(shot["name"]) + "_mattes"
    settings = {"pass": PASS_ID, "soft": bool(soft), "method": method, "band": band, "radius": radius, "eps": eps,
                "model": "vitmatte-small-composition-1k (D-032)" if vm else None,
                "guide_colour": colour.transform_id(colour_transform) if soft else None}
    files, layers, interp, held = [], {}, {}, {}
    frames = list(frames)
    for i, f in enumerate(frames):
        if job:
            job.check(); job.report(i / float(len(frames)), "matte frame %d (%d/%d)" % (f, i + 1, len(frames)))
        guide = colour.to_model_input(get_rgb(f), colour_transform) if soft else None
        alphas = {}
        for o in objs:
            fa, how, feathered = matte.object_alpha(store, o["id"], f, h, w)
            m = fa >= 1.0
            for shape_name, kind in how.items():
                if kind == "interpolated":
                    interp.setdefault(o["name"], []).append(f)
                elif kind == "held":
                    held.setdefault(o["name"], []).append(f)
            if feathered:
                alphas[o["name"]] = fa            # the artist's feather (T-073) decides the edge, as in Roto
            elif method == "vitmatte":
                alphas[o["name"]] = _vitmatte_crop(vm, guide, m)
            else:
                alphas[o["name"]] = matte.refine_alpha(guide, m, band=band, radius=radius, eps=eps) if soft else fa
        path = exr.frame_path(out_dir, base, f)
        layers = exr.write_mattes(path, alphas, compression=compression,
                                  attributes={"st_roto": json.dumps(settings, sort_keys=True)})
        files.append(path)
    if job:
        job.report(1.0, "wrote %d matte frames" % len(files))
    return {"pattern": exr.sequence_pattern(out_dir, base), "files": files, "layers": layers,
            "frames_interpolated": interp, "frames_held": held, "seconds": round(time.time() - t0, 2),
            "settings": settings}
