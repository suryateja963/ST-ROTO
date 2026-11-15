"""SAM 2.1 adapters (image click-to-mask and video tracking) on ONNX Runtime + numpy (ADR-0002).

Graphs are produced by tools/models/export_sam2_onnx.py (image) and tools/models/export_sam2_video_onnx.py (video).
The video tracker re-implements the inference-time memory logic of transformers' Sam2VideoModel (v5.23); it was
verified frame by frame against PyTorch (mask IoU >= 0.99997, research/probes/2026-11-15_video). Supported now:
one object, forward tracking from one clicked frame. Not yet: reverse, multi-object, corrections, mask prompts.

Input images: float32 RGB in [0,1], in the model's expected encoding (sRGB-encoded for SAM). Converting from the
host's working colour space is the host adapter's job (ADR-0010) and must be recorded in provenance.
"""
from __future__ import annotations

import json
import os

import numpy as np

from .runtime import open_session

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
SIZE = 1024
LICENCE = "Apache-2.0"          # facebook/sam2.1-hiera-* (MODEL_REGISTER M-01)


def preprocess(rgb: np.ndarray) -> np.ndarray:
    """HxWx3 float RGB [0,1] -> 1x3x1024x1024 normalised.

    Antialiased bilinear resize (torch-equivalent, st_roto_ai.resize) like the official Sam2VideoProcessor. Plain
    cv2 bilinear differed by up to 0.11 (normalised) and flipped a borderline object score (0.025) in the reverse
    scenario (research/probes/2026-11-16_corrections). Remaining difference (<= 0.017) is the processor's 8-bit
    fixed-point rounding; float input is kept unquantised on purpose (artists' footage is often float)."""
    from .resize import resize_aa
    x = resize_aa(np.asarray(rgb, np.float32), SIZE, SIZE, dtype=np.float32)
    x = (x - MEAN) / STD
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None], np.float32)


def _resize_bilinear(img, h, w):
    H, W = img.shape[:2]
    ys = (np.arange(h) + 0.5) * H / h - 0.5
    xs = (np.arange(w) + 0.5) * W / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H - 1); y1 = np.clip(y0 + 1, 0, H - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, W - 1); x1 = np.clip(x0 + 1, 0, W - 1)
    wy = np.clip(ys - y0, 0, 1)[:, None, None]; wx = np.clip(xs - x0, 0, 1)[None, :, None]
    top = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
    bot = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return top * (1 - wy) + bot * wy


def to_model_points(points_xy, width, height) -> np.ndarray:
    """Canonical image coordinates [(x,y), ...] -> [1,1,N,2] in the 1024x1024 model space."""
    p = np.asarray(points_xy, np.float32).reshape(-1, 2).copy()
    p[:, 0] *= SIZE / float(width)
    p[:, 1] *= SIZE / float(height)
    return p[None, None]


def upscale_logits(low_res: np.ndarray, width: int, height: int) -> np.ndarray:
    """256x256 mask logits -> HxW logits (bilinear). Threshold at 0 for a mask; trace at 0 for sub-pixel contours."""
    lr = np.asarray(low_res, np.float32).reshape(low_res.shape[-2], low_res.shape[-1])
    try:
        import cv2
        return cv2.resize(lr, (width, height), interpolation=cv2.INTER_LINEAR)
    except ImportError:                                    # pragma: no cover
        return _resize_bilinear(lr[..., None], height, width)[..., 0]


# ------------------------------------------------------------------------------------------------ image
class Sam2Image:
    """Click/box-to-mask on single frames. `encode` once per frame, then `predict` per prompt (~7 ms on GPU)."""

    def __init__(self, model_dir: str, device: str = "auto"):
        self.encoder, self.report = open_session(os.path.join(model_dir, "encoder.onnx"), device)
        self.decoder, _ = open_session(os.path.join(model_dir, "decoder.onnx"), device)

    def encode(self, rgb: np.ndarray) -> dict:
        h, w = rgb.shape[:2]
        e, s0, s1 = self.encoder.run(None, {"pixel_values": preprocess(rgb)})
        return {"image_embed": e, "feat_s0": s0, "feat_s1": s1, "width": w, "height": h}

    def predict(self, enc: dict, points_xy, labels) -> dict:
        """points in canonical image coordinates; labels 1 = include, 0 = exclude. Returns best mask logits."""
        pts = to_model_points(points_xy, enc["width"], enc["height"])
        lbl = np.asarray(labels, np.int32).reshape(1, 1, -1)
        masks, iou, obj = self.decoder.run(None, {"image_embed": enc["image_embed"], "feat_s0": enc["feat_s0"],
                                                  "feat_s1": enc["feat_s1"], "point_coords": pts, "point_labels": lbl})
        best = int(np.argmax(iou.ravel()))
        return {"low_res": masks[0, 0, best], "iou_score": float(iou.ravel()[best]),
                "logits": upscale_logits(masks[0, 0, best], enc["width"], enc["height"])}


VIDEO_GRAPHS = ("vencoder.onnx", "memenc.onnx", "decoder_mm.onnx", "decoder_single.onnx", "maskptr.onnx")


def preload_video(model_dir: str, device: str = "auto") -> dict:
    """Create (and cache) every session the video tracker needs. Session creation holds Python's GIL for ~1-3 s
    (measured), so hosts call this at a moment the artist chooses; later tracking reuses the cached sessions."""
    import time
    t0 = time.time()
    report = None
    mattn = "memattn_fp16.onnx" if os.path.exists(os.path.join(model_dir, "memattn_fp16.onnx")) else "memattn.onnx"
    for g in VIDEO_GRAPHS + (mattn,):
        _, rep = open_session(os.path.join(model_dir, g), device)
        report = report or rep
    return {"seconds": round(time.time() - t0, 2), "device": report.active, "fallback": report.fallback,
            "reason": report.reason}


# ------------------------------------------------------------------------------------------------ video
def bf16_round(x: np.ndarray) -> np.ndarray:
    """float32 -> bfloat16 -> float32, round-to-nearest-even (matches torch .to(torch.bfloat16))."""
    u = np.ascontiguousarray(x, np.float32).view(np.uint32)
    r = ((u + np.uint32(0x7FFF) + ((u >> np.uint32(16)) & np.uint32(1))) & np.uint32(0xFFFF0000)).astype(np.uint32)
    return r.view(np.float32)


def sine_pe_1d(pos: np.ndarray, dim: int, temperature: float = 10000.0) -> np.ndarray:
    pe_dim = dim // 2
    dim_t = np.arange(pe_dim, dtype=np.float32)
    dim_t = temperature ** (2 * (dim_t // 2) / pe_dim)
    pe = pos[:, None].astype(np.float32) / dim_t
    return np.concatenate([np.sin(pe), np.cos(pe)], -1).astype(np.float32)


class Sam2Video:
    """Single-object forward tracker. Usage: enc = encode(rgb); add_points(i0, enc, pts, labels); track(i, enc)...

    `frame` arguments are 0-based POSITIONS in the processed sequence (as upstream), not shot frame numbers:
    shots may start at any number, including negatives (master prompt section 11). Callers map frame <-> position.
    """

    def __init__(self, model_dir: str, device: str = "auto", num_total_frames: int | None = None,
                 memattn_file: str | None = None):
        d = model_dir
        if memattn_file is None:
            # fp16 memory attention is the default when present (decision D-029): measured on the synthetic shot,
            # same masks as fp32 (7 of 48x256x256 low-res pixels flip), 22% less peak GPU memory, 35% faster steps.
            memattn_file = "memattn_fp16.onnx" if os.path.exists(os.path.join(d, "memattn_fp16.onnx")) else "memattn.onnx"
        self.memattn_file = memattn_file
        self.venc, self.report = open_session(os.path.join(d, "vencoder.onnx"), device)
        self.mattn, _ = open_session(os.path.join(d, memattn_file), device)
        self.menc, _ = open_session(os.path.join(d, "memenc.onnx"), device)
        self.dec_mm, _ = open_session(os.path.join(d, "decoder_mm.onnx"), device)
        self.dec_single, _ = open_session(os.path.join(d, "decoder_single.onnx"), device)
        mp = os.path.join(d, "maskptr.onnx")
        self.maskptr = open_session(mp, device)[0] if os.path.exists(mp) else None
        c = np.load(os.path.join(d, "constants.npz"))
        self.no_mem = c["no_memory_embedding"]
        self.tpos = c["memory_temporal_positional_encoding"]
        self.w, self.b = c["tpos_proj_w"], c["tpos_proj_b"]
        self.occ = c["occlusion_spatial_embedding"]
        self.no_obj_ptr = c["no_object_pointer"] if "no_object_pointer" in c.files else None
        with open(os.path.join(d, "config.json")) as fh:
            self.cfg = json.load(fh)
        self.num_total_frames = num_total_frames
        from .runtime import shrink_run_options
        self._shrink = shrink_run_options() if self.report.active == "cuda" else None
        self.cond = {}
        self.noncond = {}
        self.size = None

    def encode(self, rgb: np.ndarray) -> dict:
        self.size = (rgb.shape[1], rgb.shape[0])
        s0, s1, feat, pos = self.venc.run(None, {"pixel_values": preprocess(rgb)})
        return {"s0": s0, "s1": s1, "feat": feat, "pos": pos}

    def _decode(self, enc, pix, points, labels):
        n = points.shape[2]
        mm = self.cfg["multimask_output_in_sam"] and self.cfg["multimask_min_pt_num"] <= n <= self.cfg["multimask_max_pt_num"]
        low, high, ptr, score, iou = (self.dec_mm if mm else self.dec_single).run(None, {
            "s0": enc["s0"], "s1": enc["s1"], "pix_feat": pix,
            "points": points.astype(np.float32), "labels": labels.astype(np.int32)})
        return {"low_res": low, "high_res": high, "obj_ptr": ptr, "obj_score": score, "iou": iou}

    def _encode_memory(self, enc, out, from_points):
        h = out["high_res"]
        mk = (h > 0).astype(np.float32) if from_points else 1.0 / (1.0 + np.exp(-h))
        mk = mk * self.cfg["sigmoid_scale_for_mem_enc"] + self.cfg["sigmoid_bias_for_mem_enc"]
        mem, mem_pos = self.menc.run(None, {"feat": enc["feat"], "mask_for_mem": mk.astype(np.float32)})
        appearing = (out["obj_score"] > 0).astype(np.float32)
        mem = mem + (1.0 - appearing[..., None, None]) * self.occ[..., None, None]
        out["maskmem"] = bf16_round(mem.reshape(1, 64, -1).transpose(2, 0, 1))
        out["maskmem_pos"] = mem_pos.reshape(1, 64, -1).transpose(2, 0, 1).astype(np.float32)

    def _result(self, out):
        w, h = self.size
        iou = out.get("iou")
        return {"low_res": out["low_res"][0, 0], "logits": upscale_logits(out["low_res"][0, 0], w, h),
                "object_score": float(np.asarray(out["obj_score"]).ravel()[0]),
                # model's own quality estimate of the chosen mask (None for mask prompts: no prediction made)
                "iou_pred": None if iou is None else float(np.max(iou))}

    def add_points(self, frame: int, enc: dict, points_xy, labels) -> dict:
        w, h = self.size
        pix = (enc["feat"] + self.no_mem).transpose(1, 2, 0).reshape(1, 256, 64, 64)
        out = self._decode(enc, pix, to_model_points(points_xy, w, h), np.asarray(labels, np.int32).reshape(1, 1, -1))
        self._encode_memory(enc, out, from_points=True)
        self.cond[frame] = out
        return self._result(out)

    def add_mask(self, frame: int, enc: dict, mask) -> dict:
        """Mask prompt (e.g. an artist correction) on a frame: becomes a conditioning frame, exactly as upstream
        `add_inputs_to_inference_session(input_masks=...)` + `_use_mask_as_output`."""
        from .resize import mask_to_model_input, resize_aa
        if self.maskptr is None:
            raise RuntimeError("this model export has no maskptr.onnx; re-run tools/models/export_sam2_video_onnx.py")
        m = mask_to_model_input(mask)                                          # [1,1,1024,1024] {0,1}
        feed = {"s0": enc["s0"], "s1": enc["s1"], "feat": enc["feat"], "mask": m}
        names = [i.name for i in self.maskptr.get_inputs()]            # exporter prunes unused inputs (s0/s1)
        ptr = self.maskptr.run(None, {k: feed[k] for k in names})[0]
        # remaining arithmetic of upstream _use_mask_as_output (verified against PyTorch at export time)
        appearing = float(m.any())
        high = m * 20.0 - 10.0
        low = resize_aa(high[0, 0], 256, 256)[None, None]
        ptr = appearing * ptr + (1.0 - appearing) * self.no_obj_ptr
        score = np.array([[20.0 * appearing - 10.0]], np.float32)
        out = {"low_res": low, "high_res": high.astype(np.float32), "obj_ptr": ptr.astype(np.float32), "obj_score": score}
        self._encode_memory(enc, out, from_points=True)
        self.cond[frame] = out
        return self._result(out)

    def track(self, frame: int, enc: dict, reverse: bool = False) -> dict:
        """Track a non-conditioning frame. reverse=True mirrors upstream `track_in_reverse_time`."""
        sign = -1 if reverse else 1
        mems, mpos = [], []
        for out in self.cond.values():                    # all conditioning frames (max_cond_frame_num = -1)
            mems.append(out["maskmem"]); mpos.append(out["maskmem_pos"] + self.tpos[-1])   # upstream: slot index -1
        nm = self.cfg["num_maskmem"]
        for r in range(nm - 1, 0, -1):
            out = self.noncond.get(frame - sign * r)       # upstream also checks *unselected* cond frames: none here
            if out is not None:
                mems.append(out["maskmem"]); mpos.append(out["maskmem_pos"] + self.tpos[r - 1])
        n_total = self.num_total_frames
        max_ptr = self.cfg["max_object_pointers_in_encoder"]
        if n_total is not None:
            max_ptr = min(n_total, max_ptr)
        offs, ptrs = [], []
        for t, out in self.cond.items():
            if (t >= frame) if reverse else (t <= frame):
                offs.append((frame - t) * sign); ptrs.append(out["obj_ptr"])
        for dt in range(1, max_ptr):
            ref = frame + dt if reverse else frame - dt
            if ref < 0 or (n_total is not None and ref >= n_total):     # exactly as upstream
                break
            out = self.noncond.get(ref)
            if out is not None:
                offs.append(dt); ptrs.append(out["obj_ptr"])
        ptr = np.stack(ptrs, 0)
        pe = sine_pe_1d(np.asarray(offs, np.float32) / float(max_ptr - 1), 256)
        ppos = np.repeat((pe @ self.w.T + self.b)[:, None, :], 4, axis=0)
        ptr = ptr.reshape(-1, 1, 4, 64).transpose(0, 2, 1, 3).reshape(-1, 1, 64)
        # Memory attention allocates ~0.5 GB attention buffers whose size changes as memories accumulate; shrink the
        # CUDA pool after each call so repeated tracking does not fill an 8 GB card (research/probes/2026-11-16_gui_stalls).
        pix = self.mattn.run(None, {"feat": enc["feat"], "pos": enc["pos"], "mem": np.concatenate(mems, 0),
                                    "mem_pos": np.concatenate(mpos, 0).astype(np.float32),
                                    "ptr": ptr.astype(np.float32), "ptr_pos": ppos.astype(np.float32)},
                             run_options=self._shrink)[0]
        out = self._decode(enc, pix, np.zeros((1, 1, 1, 2), np.float32), -np.ones((1, 1, 1), np.int32))
        self._encode_memory(enc, out, from_points=False)
        keep = {k: out[k] for k in ("low_res", "obj_ptr", "obj_score", "maskmem", "maskmem_pos", "iou")}
        # Every tracked frame is kept (~2 MB/frame), as upstream: a reverse pass reads frames from an earlier forward
        # pass, so pruning would change results. Bounded/disk-backed state for long shots is task T-065 (R-42).
        self.noncond[frame] = keep
        return self._result(keep)
