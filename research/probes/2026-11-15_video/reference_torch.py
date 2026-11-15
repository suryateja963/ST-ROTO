"""PyTorch reference: SAM 2.1 video propagation (transformers Sam2VideoModel) on the synthetic shot. CPU only.

Purpose: (1) quality baseline per frame vs exact ground truth; (2) saved per-frame low-res mask logits used later
to validate an ONNX + numpy re-implementation that can run inside Nuke.
Usage: .venv\\Scripts\\python.exe research/probes/2026-11-15_video/reference_torch.py sam2.1-hiera-tiny
"""
import json, os, sys, time
import numpy as np
import cv2
import torch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home")
os.environ["HF_HUB_OFFLINE"] = "1"
from transformers import Sam2VideoModel, Sam2VideoProcessor   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, "frames")


def main(name):
    torch.set_grad_enabled(False)
    meta = json.load(open(os.path.join(FR, "meta.json")))
    n = meta["frames"]
    frames = [cv2.cvtColor(cv2.imread(os.path.join(FR, "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB) for i in range(n)]
    gts = [cv2.imread(os.path.join(FR, "gt_%04d.png" % i), cv2.IMREAD_GRAYSCALE) > 127 for i in range(n)]
    src = os.path.join(ROOT, "models", "weights", name)
    model = Sam2VideoModel.from_pretrained(src).eval()
    proc = Sam2VideoProcessor.from_pretrained(src)
    t0 = time.time()
    sess = proc.init_video_session(video=frames, inference_device="cpu", dtype=torch.float32)
    t_init = time.time() - t0
    proc.add_inputs_to_inference_session(sess, frame_idx=0, obj_ids=1,
                                         input_points=[[[meta["click_xy"]]]], input_labels=[[[1]]])
    model(inference_session=sess, frame_idx=0)            # segment the clicked frame first (required)
    res = {"model": name, "frames": n, "init_session_s": round(t_init, 2), "per_frame": []}
    logits_store = {}
    t0 = time.time()
    for out in model.propagate_in_video_iterator(sess):
        fi = int(out.frame_idx)
        low = out.pred_masks                               # [obj, 1, 256, 256] logits
        logits_store["f%04d" % fi] = low[0, 0].float().numpy().astype(np.float16)
        m = proc.post_process_masks([low], original_sizes=[[meta["h"], meta["w"]]], binarize=True)[0][0, 0].numpy()
        g = gts[fi]
        iou = float((m & g).sum() / max(1, (m | g).sum()))
        res["per_frame"].append({"frame": fi, "iou": round(iou, 4), "pred_px": int(m.sum()), "gt_px": int(g.sum())})
        if fi in (0, 12, 24, 36, 47):
            cv2.imwrite(os.path.join(HERE, f"ref_{name}_f{fi:02d}.png"), m.astype(np.uint8) * 255)
    total = time.time() - t0
    ious = [p["iou"] for p in res["per_frame"]]
    occ = [p["iou"] for p in res["per_frame"] if meta["objects"][str(p["frame"])]["occluder_on"]]
    res.update({"propagate_s": round(total, 1), "s_per_frame_cpu": round(total / n, 2),
                "iou_mean": round(float(np.mean(ious)), 4), "iou_min": round(float(np.min(ious)), 4),
                "iou_mean_occluded_frames": round(float(np.mean(occ)), 4) if occ else None,
                "torch": torch.__version__})
    np.savez_compressed(os.path.join(HERE, f"ref_logits_{name}.npz"), **logits_store)
    with open(os.path.join(HERE, f"reference_{name}.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "per_frame"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny")
