"""SAM 2.1 video tracking with ONNX Runtime + numpy bookkeeping (PROTOTYPE, single object, forward only).

Re-implements the inference-time memory logic of transformers' Sam2VideoModel (v5.23) around the ONNX graphs
written by tools/models/export_sam2_video_onnx.py, so it can run inside Nuke without PyTorch:
  * conditioning frame (user clicks): no-memory embedding, multimask when 0<=points<=1, mask binarised for memory;
  * tracked frames: memories from all conditioning frames (temporal slot -1, as upstream) + the previous
    num_maskmem-1 tracked frames, object pointers with sine temporal encoding projected to mem_dim,
    memory attention -> decoder (no prompt) -> sigmoid mask for memory;
  * occlusion embedding added to memories when the object score is <= 0;
  * stored memories rounded to bfloat16 exactly like upstream (round-to-nearest-even).
Not implemented yet: reverse tracking, multiple objects, corrections on tracked frames, mask prompts.
"""
from __future__ import annotations

import json, os
import numpy as np
import onnxruntime as ort


def bf16_round(x: np.ndarray) -> np.ndarray:
    """float32 -> bfloat16 -> float32 with round-to-nearest-even (matches torch .to(torch.bfloat16))."""
    u = np.ascontiguousarray(x, np.float32).view(np.uint32)
    r = ((u + np.uint32(0x7FFF) + ((u >> np.uint32(16)) & np.uint32(1))) & np.uint32(0xFFFF0000)).astype(np.uint32)
    return r.view(np.float32)


def sine_pe_1d(pos: np.ndarray, dim: int, temperature: float = 10000.0) -> np.ndarray:
    pe_dim = dim // 2
    dim_t = np.arange(pe_dim, dtype=np.float32)
    dim_t = temperature ** (2 * (dim_t // 2) / pe_dim)
    pe = pos[:, None].astype(np.float32) / dim_t
    return np.concatenate([np.sin(pe), np.cos(pe)], -1).astype(np.float32)


class Sam2VideoTracker:
    def __init__(self, model_dir: str, providers=None, num_total_frames: int | None = None):
        providers = providers or ["CPUExecutionProvider"]
        so = ort.SessionOptions(); so.log_severity_level = 3
        mk = lambda n: ort.InferenceSession(os.path.join(model_dir, n), so, providers=providers)  # noqa: E731
        self.venc, self.mattn, self.menc = mk("vencoder.onnx"), mk("memattn.onnx"), mk("memenc.onnx")
        self.dec_mm, self.dec_single = mk("decoder_mm.onnx"), mk("decoder_single.onnx")
        self.providers = self.venc.get_providers()
        c = np.load(os.path.join(model_dir, "constants.npz"))
        self.no_mem = c["no_memory_embedding"]                       # [1,1,256]
        self.tpos = c["memory_temporal_positional_encoding"]          # [7,1,1,64]
        self.w, self.b = c["tpos_proj_w"], c["tpos_proj_b"]            # [64,256], [64]
        self.occ = c["occlusion_spatial_embedding"]                   # [1,64]
        self.cfg = json.load(open(os.path.join(model_dir, "config.json")))
        self.num_total_frames = num_total_frames
        self.cond: dict[int, dict] = {}
        self.noncond: dict[int, dict] = {}

    # ---------------------------------------------------------------- neural pieces
    def encode(self, pixel_values: np.ndarray):
        s0, s1, feat, pos = self.venc.run(None, {"pixel_values": pixel_values.astype(np.float32)})
        return {"s0": s0, "s1": s1, "feat": feat, "pos": pos}

    def _decode(self, enc, pix_feat, points, labels):
        n = points.shape[2]
        mm = self.cfg["multimask_output_in_sam"] and self.cfg["multimask_min_pt_num"] <= n <= self.cfg["multimask_max_pt_num"]
        dec = self.dec_mm if mm else self.dec_single
        low, high, ptr, score, iou = dec.run(None, {"s0": enc["s0"], "s1": enc["s1"], "pix_feat": pix_feat,
                                                    "points": points.astype(np.float32), "labels": labels.astype(np.int32)})
        return {"low_res": low, "high_res": high, "obj_ptr": ptr, "obj_score": score, "iou": iou}

    def _encode_memory(self, enc, out, from_points: bool):
        h = out["high_res"]
        m = (h > 0).astype(np.float32) if from_points else 1.0 / (1.0 + np.exp(-h))
        m = m * self.cfg["sigmoid_scale_for_mem_enc"] + self.cfg["sigmoid_bias_for_mem_enc"]
        mem, mem_pos = self.menc.run(None, {"feat": enc["feat"], "mask_for_mem": m.astype(np.float32)})
        appearing = (out["obj_score"] > 0).astype(np.float32)        # [1,1]
        mem = mem + (1.0 - appearing[..., None, None]) * self.occ[..., None, None]
        out["maskmem"] = bf16_round(mem.reshape(1, 64, -1).transpose(2, 0, 1))      # [4096,1,64]
        out["maskmem_pos"] = mem_pos.reshape(1, 64, -1).transpose(2, 0, 1).astype(np.float32)

    # ---------------------------------------------------------------- user prompt on a frame
    def add_points(self, frame_idx: int, enc, points_1024: np.ndarray, labels: np.ndarray):
        """points_1024: [N,2] in 1024x1024 model space; labels: [N] (1 pos, 0 neg)."""
        pix = (enc["feat"] + self.no_mem).transpose(1, 2, 0).reshape(1, 256, 64, 64)
        out = self._decode(enc, pix, points_1024[None, None], labels[None, None])
        self._encode_memory(enc, out, from_points=True)
        self.cond[frame_idx] = out
        return out

    # ---------------------------------------------------------------- tracking step
    def track(self, frame_idx: int, enc):
        mems, mpos = [], []
        for t, out in self.cond.items():                          # conditioning frames, temporal slot "0"
            mems.append(out["maskmem"]); mpos.append(out["maskmem_pos"] + self.tpos[0 - 1])
        nm = self.cfg["num_maskmem"]
        for r in range(nm - 1, 0, -1):                            # previous tracked frames, oldest first
            out = self.noncond.get(frame_idx - r)
            if out is not None:
                mems.append(out["maskmem"]); mpos.append(out["maskmem_pos"] + self.tpos[r - 1])
        # object pointers
        n_total = self.num_total_frames
        max_ptr = self.cfg["max_object_pointers_in_encoder"] if n_total is None else min(n_total, self.cfg["max_object_pointers_in_encoder"])
        offs, ptrs = [], []
        for t, out in self.cond.items():
            if t <= frame_idx:
                offs.append(frame_idx - t); ptrs.append(out["obj_ptr"])
        for d in range(1, max_ptr):
            ref = frame_idx - d
            if ref < 0 or (n_total is not None and ref >= n_total):
                break
            out = self.noncond.get(ref)
            if out is not None:
                offs.append(d); ptrs.append(out["obj_ptr"])
        ptr = np.stack(ptrs, 0)                                   # [k,1,256]
        pe = sine_pe_1d(np.asarray(offs, np.float32) / float(max_ptr - 1), 256)
        ppos = (pe @ self.w.T + self.b)[:, None, :]               # [k,1,64]
        ptr = ptr.reshape(-1, 1, 4, 64).transpose(0, 2, 1, 3).reshape(-1, 1, 64)
        ppos = np.repeat(ppos, 4, axis=0)
        pix = self.mattn.run(None, {"feat": enc["feat"], "pos": enc["pos"],
                                    "mem": np.concatenate(mems, 0), "mem_pos": np.concatenate(mpos, 0).astype(np.float32),
                                    "ptr": ptr.astype(np.float32), "ptr_pos": ppos.astype(np.float32)})[0]
        out = self._decode(enc, pix, np.zeros((1, 1, 1, 2), np.float32), -np.ones((1, 1, 1), np.int32))
        self._encode_memory(enc, out, from_points=False)
        # keep only what future frames can reference (bounded memory, master prompt section 11)
        out = {k: out[k] for k in ("low_res", "obj_ptr", "obj_score", "maskmem", "maskmem_pos")}
        self.noncond[frame_idx] = out
        for old in [k for k in self.noncond if k < frame_idx - max(nm, max_ptr)]:
            del self.noncond[old]
        return out
