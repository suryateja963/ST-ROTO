"""Model manager logic (T-101, REQ-052 / REQ-130, master prompt section 15). No Qt here: the "ST-ROTO Models" panel
(model_panel.py) only calls these, so everything is testable headless.

- rows(): every model in every storage location (user, studio, plugin; st_roto_ai.registry.roots) with licence,
  approval, pinned revision, source repository, installed / used copy, and its GPU memory need vs this GPU.
- verify(): full SHA-256 check of every file (ignores remembered results).
- self_test(): tracks a generated moving disc with the model (3 frames) and reports accuracy and time per frame -
  the model test and benchmark on this machine, no footage needed.
- remove() / import_from(): delete a copy (manifests stay as the record) / copy an approved model from another
  location (refused unless licence, approval, revision and every checksum are right).
Downloading new models stays a separate, owner-approved step (tools/models/download_models.py, CLAUDE.md rule 4).
"""
from __future__ import annotations

import os
import time

import numpy as np


def _registry():
    from st_roto_ai import registry           # plain Python: no ONNX Runtime import
    return registry


def rows() -> list:
    from st_roto import capabilities as cap
    reg = _registry()
    gi = cap.gpu_info()
    total = gi["gpus"][0]["total_mib"] if gi["gpus"] else None
    out = []
    for r in reg.models():
        need = cap.vram_need(r["name"])
        fit = ("-" if need is None else "no GPU" if total is None
               else "fits (%d of %d MiB)" % (need, total) if total >= need else "too big (%d > %d MiB)" % (need, total))
        out.append(dict(r, vram=fit))
    return out


def verify(name: str, root: str) -> dict:
    t0 = time.time()
    res = _registry().verify_model(name, root)
    return {"ok": all(x["ok"] for x in res), "files": res, "seconds": round(time.time() - t0, 1)}


def _disc_frames(n=3, w=320, h=240):
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    frames, masks = [], []
    for f in range(n):
        cx, cy = 110 + 25 * f, 120
        m = np.hypot(xx - cx, yy - cy) <= 45
        img = np.full((h, w, 3), 0.05, np.float32)
        img[..., 1] += 0.02 * np.sin(xx / 7.0)                    # mild texture
        img[m] = (0.8, 0.3, 0.1)
        frames.append(img); masks.append(m)
    return frames, masks, (110.0, 120.0)


def self_test(name: str, device: str = "auto") -> dict:
    """Track a generated orange disc moving over 3 frames from one click; IoU of every key vs the true disc and the
    time per frame. Only for SAM 2.1 video models (the tracker); ViTMatte gets a matting run on a soft disc."""
    from st_roto.geometry import Anchor, rasterize_spline
    if name.startswith("sam2"):
        from .track import track_objects
        frames, masks, click = _disc_frames()
        t0 = time.time()
        r = track_objects(lambda f: frames[f], [0, 1, 2], [{"name": "disc", "frame": 0, "points": [click],
                                                             "labels": [1]}], model=name, device=device)
        sec = time.time() - t0
        keys = r["objects"][0]["keys"]
        ious = []
        for f, pts in sorted(keys.items()):
            a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:6]), corner=False) for q in pts]
            m = rasterize_spline(a, 240, 320)
            ious.append(float((m & masks[f]).sum()) / max(1.0, float((m | masks[f]).sum())))
        ok = len(ious) == 3 and min(ious) > 0.95
        return {"ok": ok, "device": r["device"], "iou": [round(v, 4) for v in ious],
                "seconds_per_frame": round(sec / 3.0, 3), "note": "includes model load on the first run"}
    if name.startswith("vitmatte"):
        from st_roto_ai.vitmatte import ViTMatte, trimap_from_mask
        from .track import model_dir
        frames, masks, _ = _disc_frames(1)
        t0 = time.time()
        vm = ViTMatte(os.path.dirname(model_dir(name)), device)
        a = vm.alpha(frames[0], trimap_from_mask(masks[0], 6, 20))
        sec = time.time() - t0
        err = float(np.abs(a - masks[0].astype(np.float32)).mean())
        return {"ok": err < 0.05, "mean_abs_error": round(err, 4), "seconds": round(sec, 2)}
    return {"ok": False, "note": "no self-test for %s" % name}


def remove(name: str, root: str) -> list:
    return _registry().remove_model(name, root)


def import_from(src_root: str, name: str, dst_label: str = "user") -> dict:
    """Copy an approved model into a configured location ('user' or 'studio'; must be set up, see roots())."""
    reg = _registry()
    dst = dict(reg.roots()).get(dst_label)
    if dst is None:
        raise ValueError("no %s model location configured (set %s)" % (
            dst_label, dict(reg.LOCATION_ENV).get(dst_label, "?")))
    return reg.import_model(src_root, name, dst)
