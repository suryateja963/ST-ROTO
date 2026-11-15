"""Port-correctness check for the two scenarios: ONNX + numpy tracker fed with the OFFICIAL processor's pixel values
(so only the port can differ), CPU, compared with the PyTorch reference logits frame by frame.
Usage: .venv\\Scripts\\python.exe research/probes/2026-11-16_corrections/validate_scenarios_cpu.py sam2.1-hiera-tiny [scenario]
"""
import json, os, sys, time
import numpy as np
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home"); os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, os.path.join(ROOT, "src"))
from transformers import Sam2VideoProcessor          # noqa: E402
from st_roto_ai.sam2 import Sam2Video                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


class FixedPixels(Sam2Video):
    """Sam2Video whose encode() takes the processor's pixel_values directly."""
    def encode_px(self, px, size):
        self.size = size
        s0, s1, feat, pos = self.venc.run(None, {"pixel_values": px})
        return {"s0": s0, "s1": s1, "feat": feat, "pos": pos}


def main(name, scenario):
    meta = json.load(open(os.path.join(FR, "meta.json"))); N, W, H = meta["frames"], meta["w"], meta["h"]
    frames = [cv2.cvtColor(cv2.imread(os.path.join(FR, "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB) for i in range(N)]
    gts = [cv2.imread(os.path.join(FR, "gt_%04d.png" % i), cv2.IMREAD_GRAYSCALE) > 127 for i in range(N)]
    px = Sam2VideoProcessor.from_pretrained(os.path.join(ROOT, "models", "weights", name)).video_processor(
        videos=frames, return_tensors="pt").pixel_values_videos[0].numpy()
    ref = np.load(os.path.join(HERE, "ref_%s_%s.npz" % (scenario, name)))
    trk = FixedPixels(os.path.join(ROOT, "models", "onnx", name, "video"), device="cpu", num_total_frames=N,
                      memattn_file="memattn.onnx")
    enc = lambda i: trk.encode_px(px[i:i + 1], (W, H))                           # noqa: E731
    outs, t0 = {}, time.time()
    if scenario == "correction":
        outs[0] = trk.add_points(0, enc(0), [tuple(meta["click_xy"])], [1])
        outs[24] = trk.add_mask(24, enc(24), gts[24])
        order, rev = range(N), False
    else:
        outs[47] = trk.add_points(47, enc(47), [tuple(meta["objects"]["47"]["target_center"])], [1])
        order, rev = range(N - 1, -1, -1), True
    for f in order:
        if f not in trk.cond:
            outs[f] = trk.track(f, enc(f), reverse=rev)
    rows = []
    for f in sorted(outs):
        r = ref["f%04d" % f].astype(np.float32)
        lo = outs[f]["low_res"]
        m, mr = lo > 0, r > 0
        u = (m | mr).sum()
        rows.append({"frame": f, "logit_maxdiff": round(float(np.abs(lo - r).max()), 4),
                     "lowres_iou": 1.0 if u == 0 else round(float((m & mr).sum() / u), 5),
                     "obj_score": round(outs[f]["object_score"], 3)})
    res = {"model": name, "scenario": scenario, "seconds": round(time.time() - t0, 1),
           "lowres_iou_min": min(r["lowres_iou"] for r in rows),
           "logit_maxdiff_max": max(r["logit_maxdiff"] for r in rows),
           "frames_lowres_iou_below_0.999": [(r["frame"], r["lowres_iou"], r["obj_score"]) for r in rows if r["lowres_iou"] < 0.999],
           "obj_scores_frames_14_to_18": [(r["frame"], r["obj_score"]) for r in rows if 14 <= r["frame"] <= 18]}
    json.dump(res, open(os.path.join(HERE, "cpu_exact_%s_%s.json" % (scenario, name)), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sam2.1-hiera-tiny", sys.argv[2] if len(sys.argv) > 2 else "reverse")
