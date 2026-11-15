"""Export SAM 2.1 *video* (transformers Sam2VideoModel) to ONNX components + numpy constants, and verify each.

Graphs written to models/onnx/<name>/video/:
  vencoder.onnx   pixel_values[1,3,1024,1024] -> s0[1,32,256,256], s1[1,64,128,128], feat[4096,1,256], pos[4096,1,256]
  memattn.onnx    feat, pos, mem[S,1,64], mem_pos[S,1,64], ptr[P,1,64], ptr_pos[P,1,64] -> pix_feat[1,256,64,64]
                  (S = n_memory_frames*4096, P = n_pointer_tokens; both dynamic)
  decoder_mm.onnx / decoder_single.onnx  (multimask True / False)
                  s0, s1, pix_feat, points[1,1,N,2], labels[1,1,N] ->
                  low_res[1,1,256,256], high_res[1,1,1024,1024], obj_ptr[1,256], obj_score[1,1], iou[1,1,K]
  memenc.onnx     feat[4096,1,256], mask_for_mem[1,1,1024,1024] -> maskmem[1,64,64,64], maskmem_pos[1,64,64,64]
  constants.npz   no_memory_embedding, memory_temporal_positional_encoding, tpos_proj_w/b,
                  occlusion_spatial_embedding, config scalars
Every graph is checked against PyTorch on real inputs from the synthetic test shot (CPU ORT).
Usage: .venv\\Scripts\\python.exe tools/models/export_sam2_video_onnx.py sam2.1-hiera-tiny
"""
import json, os, sys
import numpy as np
import torch
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home")
os.environ["HF_HUB_OFFLINE"] = "1"
from transformers import Sam2VideoModel, Sam2VideoProcessor    # noqa: E402
import onnxruntime as ort                                      # noqa: E402

FR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


class VEncoder(torch.nn.Module):
    def __init__(self, m):
        super().__init__(); self.m = m

    def forward(self, px):
        o = self.m.get_image_features(px, return_dict=True)
        f, p = o.fpn_hidden_states, o.fpn_position_encoding
        s0 = f[0].permute(1, 2, 0).reshape(1, -1, 256, 256)
        s1 = f[1].permute(1, 2, 0).reshape(1, -1, 128, 128)
        return s0, s1, f[2], p[2]


class MemAttn(torch.nn.Module):
    def __init__(self, m):
        super().__init__(); self.m = m

    def forward(self, feat, pos, mem, mem_pos, ptr, ptr_pos):
        memory = torch.cat([mem, ptr], 0)
        memory_pos = torch.cat([mem_pos, ptr_pos], 0)
        out = self.m.memory_attention(current_vision_features=feat, current_vision_position_embeddings=pos,
                                      memory=memory, memory_posision_embeddings=memory_pos,
                                      num_object_pointer_tokens=ptr.shape[0])
        return out.squeeze(1).transpose(1, 2).reshape(1, 256, 64, 64)


class Decoder(torch.nn.Module):
    def __init__(self, m, multimask):
        super().__init__(); self.m = m; self.mm = multimask

    def forward(self, s0, s1, pix_feat, points, labels):
        o = self.m._single_frame_forward(input_points=points, input_labels=labels,
                                         image_embeddings=[s0, s1, pix_feat], multimask_output=self.mm)
        return o.pred_masks, o.high_res_masks, o.object_pointer, o.object_score_logits, o.iou_scores


class MemEnc(torch.nn.Module):
    def __init__(self, m):
        super().__init__(); self.m = m

    def forward(self, feat, mask_for_mem):
        pix = feat.permute(1, 2, 0).reshape(1, 256, 64, 64)
        return self.m.memory_encoder(pix, mask_for_mem)


def maxdiff(a, b):
    return float(np.abs(np.asarray(a, np.float32) - np.asarray(b, np.float32)).max())


def main(name):
    torch.set_grad_enabled(False)
    src = os.path.join(ROOT, "models", "weights", name)
    dst = os.path.join(ROOT, "models", "onnx", name, "video")
    os.makedirs(dst, exist_ok=True)
    model, info = Sam2VideoModel.from_pretrained(src, attn_implementation="eager", output_loading_info=True)
    model.eval()
    assert not info.get("missing_keys"), info["missing_keys"]
    proc = Sam2VideoProcessor.from_pretrained(src)
    cfg = model.config
    rep = {"model": name, "torch": torch.__version__, "ort": ort.__version__, "checks": {}}

    frames = [cv2.cvtColor(cv2.imread(os.path.join(FR, "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB) for i in (0, 1)]
    px = proc.video_processor(videos=frames, return_tensors="pt").pixel_values_videos[0]   # [2,3,1024,1024]

    def sess(p):
        return ort.InferenceSession(p, providers=["CPUExecutionProvider"])

    # ---- vencoder
    venc = VEncoder(model).eval()
    t_out = venc(px[:1])
    p = os.path.join(dst, "vencoder.onnx")
    torch.onnx.export(venc, (px[:1],), p, input_names=["pixel_values"], output_names=["s0", "s1", "feat", "pos"],
                      opset_version=17, dynamo=False)
    o = sess(p).run(None, {"pixel_values": px[:1].numpy()})
    rep["checks"]["vencoder_maxdiff"] = max(maxdiff(a, b) for a, b in zip(o, t_out))
    s0, s1, feat, pos = t_out

    # ---- memattn: build realistic memories with the real memory encoder
    menc = MemEnc(model).eval()
    mask = (torch.rand(1, 1, 1024, 1024) > 0.5).float() * cfg.sigmoid_scale_for_mem_enc + cfg.sigmoid_bias_for_mem_enc
    mm_feat, mm_pos = menc(feat, mask)
    p = os.path.join(dst, "memenc.onnx")
    torch.onnx.export(menc, (feat, mask), p, input_names=["feat", "mask_for_mem"], output_names=["maskmem", "maskmem_pos"],
                      opset_version=17, dynamo=False)
    o = sess(p).run(None, {"feat": feat.numpy(), "mask_for_mem": mask.numpy()})
    rep["checks"]["memenc_maxdiff"] = max(maxdiff(o[0], mm_feat), maxdiff(o[1], mm_pos))

    mem1 = mm_feat.flatten(2).permute(2, 0, 1)                    # [4096,1,64]
    mpos1 = mm_pos.flatten(2).permute(2, 0, 1)
    ma = MemAttn(model).eval()

    def mk(nm, npt):
        mem = torch.cat([mem1 * (1 + 0.1 * k) for k in range(nm)], 0)
        mpos = torch.cat([mpos1 + model.memory_temporal_positional_encoding[k] for k in range(nm)], 0)
        ptr = torch.randn(npt * 4, 1, 64)
        ppos = torch.randn(npt * 4, 1, 64)
        return feat, pos, mem, mpos, ptr, ppos

    ex = mk(2, 2)
    p = os.path.join(dst, "memattn.onnx")
    torch.onnx.export(ma, ex, p, input_names=["feat", "pos", "mem", "mem_pos", "ptr", "ptr_pos"], output_names=["pix_feat"],
                      dynamic_axes={"mem": {0: "S"}, "mem_pos": {0: "S"}, "ptr": {0: "P"}, "ptr_pos": {0: "P"}},
                      opset_version=17, dynamo=False)
    s_ma = sess(p)
    rep["checks"]["memattn_maxdiff_by_(memories,pointers)"] = {}
    for nm, npt in ((1, 1), (2, 2), (4, 5), (7, 16)):          # cover the real range: 1..7 memories, 1..16 pointers
        args = mk(nm, npt)
        ref = ma(*args)
        o = s_ma.run(None, dict(zip(["feat", "pos", "mem", "mem_pos", "ptr", "ptr_pos"], [a.numpy() for a in args])))
        rep["checks"]["memattn_maxdiff_by_(memories,pointers)"][f"{nm},{npt}"] = maxdiff(o[0], ref)

    # ---- decoders
    pix_cond = (feat + model.no_memory_embedding).permute(1, 2, 0).reshape(1, 256, 64, 64)
    pts = torch.tensor([[[[500.0, 400.0]]]]); lbl = torch.ones(1, 1, 1, dtype=torch.int32)
    pad_pts = torch.zeros(1, 1, 1, 2); pad_lbl = -torch.ones(1, 1, 1, dtype=torch.int32)
    for tag, mm in (("decoder_mm", True), ("decoder_single", False)):
        dec = Decoder(model, mm).eval()
        p = os.path.join(dst, tag + ".onnx")
        torch.onnx.export(dec, (s0, s1, pix_cond, pts, lbl), p,
                          input_names=["s0", "s1", "pix_feat", "points", "labels"],
                          output_names=["low_res", "high_res", "obj_ptr", "obj_score", "iou"],
                          dynamic_axes={"points": {2: "N"}, "labels": {2: "N"}}, opset_version=17, dynamo=False)
        sd = sess(p)
        for case, (pp, ll) in {"click": (pts, lbl), "no_prompt_pad": (pad_pts, pad_lbl)}.items():
            ref = dec(s0, s1, pix_cond, pp, ll)
            o = sd.run(None, {"s0": s0.numpy(), "s1": s1.numpy(), "pix_feat": pix_cond.numpy(),
                              "points": pp.numpy(), "labels": ll.numpy()})
            rep["checks"][f"{tag}_{case}_maxdiff"] = max(maxdiff(a, b) for a, b in zip(o, ref))

    # ---- constants for the numpy side
    np.savez(os.path.join(dst, "constants.npz"),
             no_memory_embedding=model.no_memory_embedding.numpy(),
             memory_temporal_positional_encoding=model.memory_temporal_positional_encoding.numpy(),
             tpos_proj_w=model.temporal_positional_encoding_projection_layer.weight.numpy(),
             tpos_proj_b=model.temporal_positional_encoding_projection_layer.bias.numpy(),
             occlusion_spatial_embedding=model.occlusion_spatial_embedding_parameter.numpy())
    consts = {k: getattr(cfg, k) for k in ("num_maskmem", "max_cond_frame_num", "max_object_pointers_in_encoder",
                                           "sigmoid_scale_for_mem_enc", "sigmoid_bias_for_mem_enc",
                                           "multimask_output_in_sam", "multimask_output_for_tracking",
                                           "multimask_min_pt_num", "multimask_max_pt_num")}
    consts["mem_dim"] = model.mem_dim
    with open(os.path.join(dst, "config.json"), "w") as fh:
        json.dump(consts, fh, indent=1)
    rep["config"] = consts
    rep["onnx_mb"] = {f: round(os.path.getsize(os.path.join(dst, f)) / 1e6, 1) for f in sorted(os.listdir(dst)) if f.endswith(".onnx")}
    # fp16 memory attention (default at runtime, D-029). Must be re-validated against the reference per model.
    import subprocess
    subprocess.check_call([sys.executable, "-I", os.path.join(ROOT, "tools", "models", "convert_fp16.py"),
                           os.path.join(dst, "memattn.onnx")])
    out = os.path.join(ROOT, "research", "probes", "2026-11-15_video", f"export_video_{name}.json")
    with open(out, "w") as fh:
        json.dump(rep, fh, indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny")
