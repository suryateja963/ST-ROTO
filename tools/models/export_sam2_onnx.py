"""Export SAM 2.1 (Hugging Face transformers format) to two ONNX graphs and verify them.

  encoder.onnx : pixel_values[1,3,1024,1024]            -> image_embed[1,256,64,64], feat_s0[1,32,256,256], feat_s1[1,64,128,128]
  decoder.onnx : image_embed, feat_s0, feat_s1,
                 point_coords[1,1,N,2] (1024-space px), point_labels[1,1,N] (int32: 1 pos, 0 neg, -10 pad)
                                                          -> masks[1,1,3,256,256] (logits), iou_scores[1,1,3], object_score_logits[1,1,1]

Verification (CPU, fp32):
  1. our numpy pre-processing == transformers Sam2Processor pre-processing
  2. ONNX outputs vs PyTorch outputs (max abs diff, mask IoU)
  3. mask IoU vs the exact ground truth of a synthetic test image (sanity check, not a benchmark)

Usage:  .venv\\Scripts\\python.exe tools/models/export_sam2_onnx.py sam2.1-hiera-tiny [sam2.1-hiera-large ...]
Writes models/onnx/<name>/{encoder,decoder}.onnx (git-ignored) and research/probes/2026-11-15_sam2/export_<name>.json.
"""
import json, os, sys, time
import numpy as np
import torch
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home")
os.environ["HF_HUB_OFFLINE"] = "1"                       # weights must already be local
from transformers import Sam2Model, Sam2Processor       # noqa: E402
import onnxruntime as ort                               # noqa: E402

PROBE = os.path.join(ROOT, "research", "probes", "2026-11-15_sam2")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


# ---------------------------------------------------------------- synthetic test image
def make_test_image(w=1920, h=1080, seed=7):
    """Textured background + 3 objects. Returns RGB uint8, GT mask of the target ellipse, a click inside it."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = np.stack([60 + 40 * np.sin(xx / 97.0), 80 + 30 * np.cos(yy / 61.0), 70 + 20 * np.sin((xx + yy) / 133.0)], -1)
    bg += rng.normal(0, 12, (h, w, 3))
    img = np.clip(bg, 0, 255).astype(np.uint8)
    cv2.rectangle(img, (1150, 250), (1650, 800), (40, 70, 200), -1)                 # blue box (distractor)
    star = np.array([[300, 700], [380, 880], [560, 900], [420, 1000], [470, 1070], [300, 980], [130, 1070], [180, 1000], [40, 900], [220, 880]], np.int32)
    cv2.fillPoly(img, [star], (40, 180, 60))                                         # green star (distractor)
    gt = np.zeros((h, w), np.uint8)
    cv2.ellipse(gt, (820, 480), (300, 190), 20, 0, 360, 1, -1)                       # target: red ellipse
    tex = np.clip(np.stack([200 + rng.normal(0, 18, (h, w)), 50 + rng.normal(0, 18, (h, w)), 45 + rng.normal(0, 18, (h, w))], -1), 0, 255)
    img[gt == 1] = tex[gt == 1].astype(np.uint8)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return img, gt, (820.0, 480.0)


# ---------------------------------------------------------------- pre/post processing (numpy, mirrors processor)
def preprocess(rgb):
    # INTER_AREA when shrinking approximates the processor's antialiased resize; INTER_LINEAR when enlarging.
    shrink = rgb.shape[0] > 1024 or rgb.shape[1] > 1024
    x = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LINEAR).astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return x.transpose(2, 0, 1)[None].astype(np.float32)


def scale_points(points_xy, w, h):
    p = np.asarray(points_xy, np.float32).copy()
    p[:, 0] *= 1024.0 / w
    p[:, 1] *= 1024.0 / h
    return p[None, None]                                  # [1,1,N,2]


def upscale_mask(logits_256, w, h):
    return cv2.resize(logits_256, (w, h), interpolation=cv2.INTER_LINEAR) > 0.0


def iou(a, b):
    a, b = a.astype(bool), b.astype(bool)
    return float((a & b).sum() / max(1, (a | b).sum()))


# ---------------------------------------------------------------- export wrappers
class Encoder(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, pixel_values):
        emb = self.m.get_image_embeddings(pixel_values)
        return emb[2], emb[0], emb[1]                     # image_embed, feat_s0, feat_s1


class Decoder(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, image_embed, feat_s0, feat_s1, point_coords, point_labels):
        out = self.m(image_embeddings=[feat_s0, feat_s1, image_embed], input_points=point_coords,
                     input_labels=point_labels, multimask_output=True)
        return out.pred_masks, out.iou_scores, out.object_score_logits


def export(name):
    t0 = time.time()
    src = os.path.join(ROOT, "models", "weights", name)
    dst = os.path.join(ROOT, "models", "onnx", name)
    os.makedirs(dst, exist_ok=True)
    os.makedirs(PROBE, exist_ok=True)
    rep = {"model": name, "torch": torch.__version__, "onnxruntime": ort.__version__}

    model, info = Sam2Model.from_pretrained(src, attn_implementation="eager", output_loading_info=True)
    model.eval()
    # The checkpoint is the sam2_video model; we use its image sub-model. Any *missing* key would mean
    # randomly initialised weights in the image path, so fail loudly.
    rep["missing_keys"] = sorted(info.get("missing_keys", []))
    rep["unexpected_keys_count"] = len(info.get("unexpected_keys", []))
    if rep["missing_keys"]:
        raise SystemExit(f"{name}: missing weights in image model: {rep['missing_keys'][:10]}")
    proc = Sam2Processor.from_pretrained(src)
    img, gt, click = make_test_image()
    h, w = gt.shape
    cv2.imwrite(os.path.join(PROBE, "test_image.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    cv2.imwrite(os.path.join(PROBE, "test_gt.png"), gt * 255)

    # 1. pre-processing parity with the official processor
    inputs = proc(images=img, input_points=[[[list(click)]]], input_labels=[[[1]]], return_tensors="pt")
    ours = preprocess(img)
    rep["preproc_max_abs_diff_vs_processor"] = float(np.abs(inputs["pixel_values"].numpy() - ours).max())
    rep["points_max_abs_diff_vs_processor"] = float(np.abs(inputs["input_points"].numpy() - scale_points([click], w, h)).max())

    pts = torch.from_numpy(scale_points([click], w, h))
    lbl = torch.ones((1, 1, 1), dtype=torch.int32)
    px = torch.from_numpy(ours)
    enc, dec = Encoder(model).eval(), Decoder(model).eval()
    with torch.no_grad():
        t_img, t_s0, t_s1 = enc(px)
        t_masks, t_iou, t_obj = dec(t_img, t_s0, t_s1, pts, lbl)

        enc_path, dec_path = os.path.join(dst, "encoder.onnx"), os.path.join(dst, "decoder.onnx")
        torch.onnx.export(enc, (px,), enc_path, input_names=["pixel_values"],
                          output_names=["image_embed", "feat_s0", "feat_s1"], opset_version=17, dynamo=False)
        torch.onnx.export(dec, (t_img, t_s0, t_s1, pts, lbl), dec_path,
                          input_names=["image_embed", "feat_s0", "feat_s1", "point_coords", "point_labels"],
                          output_names=["masks", "iou_scores", "object_score_logits"],
                          dynamic_axes={"point_coords": {2: "num_points"}, "point_labels": {2: "num_points"}},
                          opset_version=17, dynamo=False)
    rep["onnx_bytes"] = {"encoder": os.path.getsize(enc_path), "decoder": os.path.getsize(dec_path)}

    # 2. ONNX (CPU) vs PyTorch
    se = ort.InferenceSession(enc_path, providers=["CPUExecutionProvider"])
    sd = ort.InferenceSession(dec_path, providers=["CPUExecutionProvider"])
    o_img, o_s0, o_s1 = se.run(None, {"pixel_values": ours})
    o_masks, o_iou, o_obj = sd.run(None, {"image_embed": o_img, "feat_s0": o_s0, "feat_s1": o_s1,
                                          "point_coords": pts.numpy(), "point_labels": lbl.numpy()})
    rep["encoder_max_abs_diff"] = float(max(np.abs(o_img - t_img.numpy()).max(), np.abs(o_s0 - t_s0.numpy()).max(),
                                            np.abs(o_s1 - t_s1.numpy()).max()))
    rep["decoder_iou_scores_torch"] = t_iou.numpy().ravel().round(4).tolist()
    rep["decoder_iou_scores_onnx"] = o_iou.ravel().round(4).tolist()
    best = int(np.argmax(o_iou.ravel()))
    m_onnx = upscale_mask(o_masks[0, 0, best], w, h)
    m_torch = upscale_mask(t_masks.numpy()[0, 0, best], w, h)
    rep["best_mask_index"] = best
    rep["mask_iou_onnx_vs_torch"] = iou(m_onnx, m_torch)
    # effect of our pre-processing vs the official processor's, on the final mask
    p_img, p_s0, p_s1 = se.run(None, {"pixel_values": inputs["pixel_values"].numpy()})
    p_out = sd.run(None, {"image_embed": p_img, "feat_s0": p_s0, "feat_s1": p_s1,
                          "point_coords": pts.numpy(), "point_labels": lbl.numpy()})
    m_proc = upscale_mask(p_out[0][0, 0, int(np.argmax(p_out[1].ravel()))], w, h)
    rep["mask_iou_ours_vs_processor_preproc"] = iou(m_onnx, m_proc)
    rep["mask_iou_processor_preproc_vs_ground_truth"] = iou(m_proc, gt)
    # 3. sanity vs synthetic ground truth
    rep["mask_iou_vs_ground_truth"] = iou(m_onnx, gt)
    cv2.imwrite(os.path.join(PROBE, f"mask_{name}.png"), m_onnx.astype(np.uint8) * 255)

    # extra prompt with 2 points (1 pos + 1 neg) to prove the dynamic point axis works
    pts2 = scale_points([click, (1400.0, 520.0)], w, h)
    lbl2 = np.array([[[1, 0]]], np.int32)
    o2 = sd.run(None, {"image_embed": o_img, "feat_s0": o_s0, "feat_s1": o_s1, "point_coords": pts2, "point_labels": lbl2})
    rep["two_point_prompt_mask_iou_vs_gt"] = iou(upscale_mask(o2[0][0, 0, int(np.argmax(o2[1].ravel()))], w, h), gt)
    rep["seconds_total"] = round(time.time() - t0, 1)
    with open(os.path.join(PROBE, f"export_{name}.json"), "w") as f:
        json.dump(rep, f, indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    torch.set_grad_enabled(False)
    for n in sys.argv[1:]:
        export(n)
