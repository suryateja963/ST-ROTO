"""PyTorch reference for correction-driven and reverse tracking (transformers Sam2VideoModel, CPU).

Scenario A "correction": click on frame 0 + MASK prompt (the exact ground truth) on frame 24, propagate forward 0..47.
Scenario B "reverse": click on frame 47, propagate in reverse 47..0.
Saves per-frame low-res logits (ref_<scenario>_<model>.npz) and IoU vs ground truth (ref_<scenario>_<model>.json).
Usage: .venv\\Scripts\\python.exe research/probes/2026-11-16_corrections/reference_scenarios.py sam2.1-hiera-tiny
"""
import json, os, sys, time
import numpy as np
import cv2
import torch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home"); os.environ["HF_HUB_OFFLINE"] = "1"
from transformers import Sam2VideoModel, Sam2VideoProcessor   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


def run(name, scenario):
    torch.set_grad_enabled(False)
    meta = json.load(open(os.path.join(FR, "meta.json"))); n, H, W = meta["frames"], meta["h"], meta["w"]
    frames = [cv2.cvtColor(cv2.imread(os.path.join(FR, "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB) for i in range(n)]
    gts = [cv2.imread(os.path.join(FR, "gt_%04d.png" % i), cv2.IMREAD_GRAYSCALE) > 127 for i in range(n)]
    src = os.path.join(ROOT, "models", "weights", name)
    model = Sam2VideoModel.from_pretrained(src).eval(); proc = Sam2VideoProcessor.from_pretrained(src)
    sess = proc.init_video_session(video=frames, inference_device="cpu", dtype=torch.float32)
    if scenario == "correction":
        proc.add_inputs_to_inference_session(sess, frame_idx=0, obj_ids=1, input_points=[[[meta["click_xy"]]]], input_labels=[[[1]]])
        model(inference_session=sess, frame_idx=0)
        proc.add_inputs_to_inference_session(sess, frame_idx=24, obj_ids=1, input_masks=gts[24])
        model(inference_session=sess, frame_idx=24)
        it = model.propagate_in_video_iterator(sess, start_frame_idx=0)
    else:
        c = meta["objects"]["47"]["target_center"]
        proc.add_inputs_to_inference_session(sess, frame_idx=47, obj_ids=1, input_points=[[[c]]], input_labels=[[[1]]])
        model(inference_session=sess, frame_idx=47)
        it = model.propagate_in_video_iterator(sess, start_frame_idx=47, reverse=True)
    logits, rows, t0 = {}, [], time.time()
    for out in it:
        f = int(out.frame_idx)
        low = out.pred_masks
        logits["f%04d" % f] = low[0, 0].numpy().astype(np.float16)
        m = proc.post_process_masks([low], original_sizes=[[H, W]], binarize=True)[0][0, 0].numpy()
        rows.append({"frame": f, "iou_vs_gt": round(float((m & gts[f]).sum() / max(1, (m | gts[f]).sum())), 4)})
    np.savez_compressed(os.path.join(HERE, "ref_%s_%s.npz" % (scenario, name)), **logits)
    res = {"model": name, "scenario": scenario, "frames": len(rows), "seconds": round(time.time() - t0, 1),
           "iou_vs_gt_mean": round(float(np.mean([r["iou_vs_gt"] for r in rows])), 4),
           "iou_vs_gt_min": min(r["iou_vs_gt"] for r in rows), "per_frame": rows}
    json.dump(res, open(os.path.join(HERE, "ref_%s_%s.json" % (scenario, name)), "w"), indent=1)
    print(scenario, name, {k: v for k, v in res.items() if k != "per_frame"})


if __name__ == "__main__":
    for sc in ("correction", "reverse"):
        run(sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny", sc)
