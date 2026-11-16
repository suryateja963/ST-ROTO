"""T-068 calibration tool: track sequences that have ground truth, record per-frame AI diagnostics vs the truth,
and evaluate the review-flag thresholds (st_roto.calibration). Writes <out>/calibration.json.

Sequence sources:
  * built-in: the synthetic shot (research/probes/2026-11-15_video) - target and distractor disc, each tracked
    forward from frame 0 and time-reversed from frame 47 (4 sequences, 192 frames). PROVISIONAL (D-020 data).
  * --dir D: every sub-folder with frames/*.png|jpg and masks/*.png (same names; >127 = object) - for approved real
    footage (OQ-13). The prompt is the truth mask's most interior pixel on the first frame.
Run: .venv/Scripts/python.exe tools/benchmark/calibrate_review.py [--dir D] [--device cpu|auto] [--out folder]
GPU: run INSIDE Nuke (Nuke's standalone python.exe cannot load the CUDA DLLs and silently falls back to CPU, measured):
     Nuke17.1.exe --nc -t tools/benchmark/calibrate_review.py --dir D
"""
import argparse, glob, json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
if "nuke" in os.path.basename(os.path.dirname(sys.executable)).lower():   # Nuke (-t): packages it needs
    sys.path.append(os.path.join(ROOT, ".tools", "nuke-py311"))
import numpy as np   # noqa: E402
import cv2           # noqa: E402

from st_roto.calibration import evaluate     # noqa: E402
from st_roto.geometry import Anchor, rasterize_spline   # noqa: E402

SYN = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def interior_point(mask):
    d = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(d)), d.shape)
    return float(x) + 0.5, float(y) + 0.5


def synthetic_sequences():
    if not os.path.exists(os.path.join(SYN, "meta.json")):
        return []
    meta = json.load(open(os.path.join(SYN, "meta.json")))
    n, w, h = meta["frames"], meta["w"], meta["h"]
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    frames = {f: os.path.join(SYN, "frame_%04d.png" % f) for f in range(n)}
    target = {f: cv2.imread(os.path.join(SYN, "gt_%04d.png" % f), cv2.IMREAD_GRAYSCALE) > 127 for f in range(n)}

    def disc(f):                                             # make_synthetic_video.py: distractor under target/occluder
        s = f / (n - 1.0)
        cx, cy = 1050 - 600 * s, 560 - 120 * np.sin(np.pi * s)
        bx = int(-200 + 1700 * np.clip((f - 14) / 20.0, 0, 1))
        occ = np.zeros((h, w), bool)
        if 14 <= f <= 34:
            occ[:, max(0, bx):max(0, bx + 91)] = True
        return (np.hypot(xx - cx, yy - cy) <= 85) & ~target[f] & ~occ
    discs = {f: disc(f) for f in range(n)}
    out = []
    for name, gt in (("syn_target", target), ("syn_disc", discs)):
        out.append((name + "_fwd", list(range(n)), frames, gt))
        out.append((name + "_rev", list(range(n - 1, -1, -1)), frames, gt))
    return out


def folder_sequences(d):
    out = []
    for seq in sorted(glob.glob(os.path.join(d, "*"))):
        fr = sorted(glob.glob(os.path.join(seq, "frames", "*.png")) + glob.glob(os.path.join(seq, "frames", "*.jpg")))
        if not fr:
            continue
        frames, gt = {}, {}
        for i, p in enumerate(fr):
            m = os.path.join(seq, "masks", os.path.splitext(os.path.basename(p))[0] + ".png")
            if os.path.exists(m):
                frames[i] = p
                gt[i] = cv2.imread(m, cv2.IMREAD_GRAYSCALE) > 127
        order = sorted(frames)
        first_visible = next((f for f in order if gt[f].sum() > 50), None)
        if first_visible is None:
            continue                                        # object never visible: nothing to prompt
        order = [f for f in order if f >= first_visible]   # prompt on the first frame the object is visible
        out.append((os.path.basename(seq), order, frames, gt))
    return out


DEVICES = set()


def run(seqs, device):
    from st_roto_nuke.track import track_objects
    records = []
    for name, order, frames, gt in seqs:
        t0 = time.time()
        first = order[0]
        get_rgb = lambda f: srgb_to_linear(cv2.cvtColor(cv2.imread(frames[f]), cv2.COLOR_BGR2RGB) / 255.0)  # noqa: E731
        full = track_objects(get_rgb, order, [{"name": name, "frame": first, "points": [interior_point(gt[first])],
                                               "labels": [1]}], device=device, anchors=16, parts=True)
        res = full["objects"][0]
        DEVICES.add(full["device"] + (" (FALLBACK: %s)" % full["device_reason"] if full["device_fallback"] else ""))
        h, w = gt[first].shape
        for f in order:
            s, q = res["reports"][f]
            m = np.zeros((h, w), bool)
            for pts in [res["keys"].get(f)] + [p.get(f) for p in res["parts"]]:
                if pts and len({tuple(p[:2]) for p in pts}) > 1:
                    m |= rasterize_spline([Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]),
                                                  corner=False) for p in pts], h, w)
            vis = bool(gt[f].sum() > 50)
            iou = float((m & gt[f]).sum() / max(1, (m | gt[f]).sum())) if vis else (1.0 if not m.any() else 0.0)
            records.append({"seq": name, "frame": f, "object_score": s, "iou_pred": q, "iou_true": round(iou, 4),
                            "truth_visible": vis})
        print("%-16s %3d frames  %.0f s  mean IoU %.3f" % (name, len(order), time.time() - t0,
              np.mean([r["iou_true"] for r in records if r["seq"] == name and r["truth_visible"]])), flush=True)
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir"); ap.add_argument("--device", default="auto")
    ap.add_argument("--out", default=os.path.join(ROOT, "research", "probes", "2026-11-16_calibration"))
    a = ap.parse_args()
    seqs = folder_sequences(a.dir) if a.dir else synthetic_sequences()
    if not seqs:
        sys.exit("no sequences")
    records = run(seqs, a.device)
    ev = evaluate(records)
    os.makedirs(a.out, exist_ok=True)
    print("device(s): %s" % ", ".join(sorted(DEVICES)))
    json.dump({"source": a.dir or "synthetic (PROVISIONAL)", "devices": sorted(DEVICES), "evaluation": ev, "records": records},
              open(os.path.join(a.out, "calibration.json"), "w"), indent=1)
    cur = [g for g in ev["grid"] if g["margin"] == 1.0 and g["iou_min"] == 0.7][0]
    print("frames %d, bad %d; current (1.0, 0.7): %s; best: %s; corr(iou_pred, iou) %s"
          % (ev["frames"], ev["bad"], cur, ev["best"], ev["iou_pred_vs_true_corr"]))


if __name__ == "__main__":
    main()
