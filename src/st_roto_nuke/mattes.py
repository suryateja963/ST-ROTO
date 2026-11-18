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

import numpy as np

from st_roto import exr, matte
from . import colour
from .pixels import FrameUnavailable

PASS_ID = "st_roto_matte_v1"


def default_output_dir(project_path: str, shot_name: str) -> str:
    base = os.path.splitext(os.path.abspath(project_path))[0]
    return os.path.join(base + "_mattes", exr.layer_name(shot_name))


METHODS = ("guided", "vitmatte", "hard")


def fit_size(w, h, box=None):
    """(width, height) of the shot scaled down to fit in `box` with its proportions (never up); the shot size when
    box is None or the shot already fits."""
    if not box:
        return (int(w), int(h))
    s = min(box[0] / float(w), box[1] / float(h), 1.0)
    return (max(1, int(w * s)), max(1, int(h * s)))


VITMATTE_TILE, VITMATTE_OVERLAP = 1024, 256          # overlap 256: closest to the keyed reference (tile study)


def _vitmatte_tiled(vm, rgb, tri, tile=VITMATTE_TILE, overlap=VITMATTE_OVERLAP):
    """ViTMatte-S in overlapping tiles (found on real 4K plates: one pass over a close-up's unknown zone asked the
    GPU for 10.5 GB - its global attention grows with the square of the area). Tiles without unknown pixels keep the
    trimap; overlaps are blended with linear ramps. A region that fits one tile runs in one pass, exactly as before."""
    import numpy as np
    h, w = tri.shape
    if h <= tile and w <= tile:
        return vm.alpha(rgb, tri)
    step = tile - overlap
    acc = np.zeros((h, w), np.float64)
    wsum = np.zeros((h, w), np.float64)

    def starts(n):
        s = list(range(0, max(1, n - tile) + 1, step))
        if s[-1] + tile < n:
            s.append(n - tile)
        return s
    for ty in starts(h):
        for tx in starts(w):
            sl = (slice(ty, min(h, ty + tile)), slice(tx, min(w, tx + tile)))
            t = tri[sl]
            a = vm.alpha(rgb[sl], t) if (t == 0.5).any() else t.astype(np.float32)
            th, tw = t.shape
            ry = np.minimum(1.0, (np.minimum(np.arange(th), th - 1 - np.arange(th)) + 1) / float(overlap))
            rx = np.minimum(1.0, (np.minimum(np.arange(tw), tw - 1 - np.arange(tw)) + 1) / float(overlap))
            if ty == 0:
                ry[:th // 2] = 1.0
            if ty + th >= h:
                ry[th // 2:] = 1.0
            if tx == 0:
                rx[:tw // 2] = 1.0
            if tx + tw >= w:
                rx[tw // 2:] = 1.0
            wt = ry[:, None] * rx[None, :]
            acc[sl] += a * wt
            wsum[sl] += wt
    out = (acc / np.maximum(wsum, 1e-9)).astype(np.float32)
    out[tri >= 1.0] = 1.0
    out[tri <= 0.0] = 0.0
    return out


def _vitmatte_crop(vm, guide, mask, inner=6, outer=20, margin=8):
    """ViTMatte-S on the bounding box of the unknown zone only (cost scales with the outline, not the frame), in
    tiles when that box is larger than one tile (_vitmatte_tiled)."""
    from st_roto_ai.vitmatte import trimap_from_mask
    import numpy as np
    alpha = mask.astype("float32")
    tri_full = trimap_from_mask(mask, inner, outer)
    ys, xs = np.nonzero(tri_full == 0.5)
    if not len(xs):
        return alpha
    y0, y1 = max(0, ys.min() - margin), min(mask.shape[0], ys.max() + margin + 1)
    x0, x1 = max(0, xs.min() - margin), min(mask.shape[1], xs.max() + margin + 1)
    a = _vitmatte_tiled(vm, guide[y0:y1, x0:x1], tri_full[y0:y1, x0:x1])
    alpha[y0:y1, x0:x1] = a
    return alpha


def render_mattes(get_rgb, store, shot_id, frames, out_dir, soft=True, band=3, radius=8, eps=1e-4,
                  objects=None, compression="zip", job=None, colour_transform=colour.TRANSFORM_ID, method=None,
                  models_root=None, device="auto", out_size=None, rgb_mode=None, offset_px=0, blur_px=0.0,
                  core_edge_px=0, spill=None):
    """Write `<out_dir>/<shot>_mattes.####.exr` for `frames`. objects: object ids (default: every object of the
    shot). out_size: (width, height) box the EXRs must fit in (OQ-28: e.g. 1920x1080); mattes are computed at the
    shot's full resolution and area-averaged down into the largest box with the shot's proportions; None = full
    resolution. Returns {"pattern", "files", "layers": {object name: layer}, "frames_interpolated": {name: [frames]},
    "frames_held": {...}, "plate_missing": [frames], "seconds"}. A frame whose plate cannot be read (T-086) gets a
    hard matte (the shapes need no plate) and is listed in "plate_missing".
    T-099 (REQ-100/101), applied to the mattes only (shapes never change), in this order: per object `offset_px`
    (grow > 0 / shrink < 0) and `blur_px` (edge feather, Gaussian sigma), then the combined matte (roles), then
    `core_edge_px` > 0 adds layers core_matte (combined eroded by that width) and edge_matte (the band). rgb_mode
    'premultiplied' / 'straight' writes the plate's scene-linear RGB (x combined alpha if premultiplied) into R, G, B;
    the convention is in the header ('st_roto' alpha_convention) - never implied."""
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
    size = fit_size(w, h, out_size)
    rgb_mode = None if rgb_mode in (None, "none") else rgb_mode
    if rgb_mode is not None:
        matte.rgb_mode_parts(rgb_mode)                        # raises for unknown modes
    if spill not in (None, "none", "auto", "green", "blue"):
        raise ValueError("unknown spill setting %r" % spill)
    spill = None if spill in (None, "none") else spill
    settings = {"pass": PASS_ID, "soft": bool(soft), "method": method, "band": band, "radius": radius, "eps": eps,
                "offset_px": int(offset_px), "blur_px": float(blur_px), "core_edge_px": int(core_edge_px),
                "alpha_convention": matte.rgb_mode_parts(rgb_mode)[0] if rgb_mode else "alpha only",
                "edge_colour": ("decontaminated" if matte.rgb_mode_parts(rgb_mode)[1] else "plate") if rgb_mode else None,
                "spill": spill if rgb_mode else None,
                "roles": {o["name"]: (o.get("role") or "add") for o in objs},
                "size": list(size), "shot_size": [w, h],
                "model": "vitmatte-small-composition-1k (D-032)" if vm else None,
                "guide_colour": colour.transform_id(colour_transform) if soft else None}
    files, layers, interp, held, no_plate = [], {}, {}, {}, []
    frames = list(frames)
    moved_from = None
    if any(exr.is_locked(exr.frame_path(out_dir, base, f)) for f in frames):
        # T-099: a Nuke Read node keeps the old mattes open (Windows cannot replace them): new version folder
        moved_from, out_dir = out_dir, exr.next_version_dir(out_dir)
        settings["written_to_new_version_because"] = "previous files in use: %s" % moved_from
    for i, f in enumerate(frames):
        if job:
            job.check(); job.report(i / float(len(frames)), "matte frame %d (%d/%d)" % (f, i + 1, len(frames)))
        guide, plate = None, None
        if soft or rgb_mode:
            try:
                plate = get_rgb(f)
                guide = colour.to_model_input(plate, colour_transform) if soft else None
            except FrameUnavailable:
                no_plate.append(f)
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
            elif guide is None:
                alphas[o["name"]] = fa            # hard matte, or no plate for this frame (T-086)
            elif method == "vitmatte":
                alphas[o["name"]] = _vitmatte_crop(vm, guide, m)
            else:
                alphas[o["name"]] = matte.refine_alpha(guide, m, band=band, radius=radius, eps=eps)
        if offset_px or blur_px:                            # T-099 refinement, per object, full resolution
            alphas = {k: matte.blur_edge(matte.offset_alpha(v, offset_px), blur_px) for k, v in alphas.items()}
        roles = {o["name"]: (o.get("role") or "add") for o in objs}
        from st_roto.views import combine_roles             # same arithmetic as Nuke's Roto render (DEF-001):
        combined = combine_roles(alphas, roles)             # objects composited 'over', not max
        extra = {}
        if core_edge_px:
            extra["core_matte"], extra["edge_matte"] = matte.core_edge(combined, core_edge_px)
        rgb = None
        if rgb_mode:
            rgb = (matte.foreground_rgb(plate, combined, rgb_mode, spill) if plate is not None
                   else np.zeros((h, w, 3), np.float32))     # no plate on this frame: black, listed in plate_missing
        if size != (w, h):
            import cv2
            rs = lambda v: cv2.resize(np.asarray(v, np.float32), size, interpolation=cv2.INTER_AREA)   # noqa: E731
            alphas = {k: rs(v) for k, v in alphas.items()}
            combined, extra = rs(combined), {k: rs(v) for k, v in extra.items()}
            rgb = rs(rgb) if rgb is not None else None
        path = exr.frame_path(out_dir, base, f)
        layers = exr.write_mattes(path, alphas, combined=combined, compression=compression,
                                  attributes={"st_roto": json.dumps(settings, sort_keys=True)}, rgb=rgb, extra=extra)
        files.append(path)
    if job:
        job.report(1.0, "wrote %d matte frames" % len(files))
    return {"pattern": exr.sequence_pattern(out_dir, base), "files": files, "layers": layers,
            "frames_interpolated": interp, "frames_held": held, "plate_missing": no_plate, "seconds": round(time.time() - t0, 2),
            "settings": settings, "size": size, "moved_from": moved_from}
