"""Images for the local PDF report (owner's footage: output ONLY to a local folder, never committed).
  .venv\\Scripts\\python.exe -I pdf_images.py work=<dir> out=<folder>
Per shot: first / worst / last frame, tiny-only and large-only outlines side by side, cropped to the subjects;
hair crops from the real EXR mattes (115, 116); despill crops; frame strips from the preview sheets."""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(ROOT, ".tools", "nuke-py311"))
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
sys.argv = [sys.argv[0], "work=" + args["work"]]
import cv2  # noqa: E402
import measure as M  # noqa: E402
import render_overlays as RO  # noqa: E402
from st_roto import exr  # noqa: E402

WORK, OUT = args["work"], args["out"]
os.makedirs(OUT, exist_ok=True)
COL = {"tiny": (0, 0, 255), "large": (255, 80, 0)}


def plate_bgr(shot, f, w=1920):
    a = cv2.imread("%s/%s/%s_%05d.tif" % (M.SRC, shot, shot, f), cv2.IMREAD_UNCHANGED)
    h = int(round(a.shape[0] * w / float(a.shape[1])))
    return (cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA) / 257.0).astype(np.uint8), w / float(a.shape[1])


def label(img, text, col=(255, 255, 255)):
    cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(img, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.75, col, 2, cv2.LINE_AA)
    return img


def shot_pairs(shot, summary):
    res = json.load(open(os.path.join(HERE, "result_%s.json" % shot)))
    sp = {m: RO.splines(WORK, shot, m) for m in ("tiny", "large")}
    n = res["frames"]
    worst = min(range(n), key=lambda f: min(res["tracking"][m]["per_frame"][f]["iou_core"] for m in res["tracking"]))
    frames = sorted({0, worst, n - 1})
    for f in frames:
        base, sc = plate_bgr(shot, f)
        polys = {m: [np.round(p * sc).astype(np.int32) for _n, p in sp[m].get(f, [])] for m in sp}
        allp = np.concatenate([p for v in polys.values() for p in v]) if any(polys.values()) else None
        if allp is not None:
            x0, y0 = np.maximum(allp.min(0) - 60, 0)
            x1, y1 = np.minimum(allp.max(0) + 60, [base.shape[1] - 1, base.shape[0] - 1])
        else:
            x0, y0, x1, y1 = 0, 0, base.shape[1] - 1, base.shape[0] - 1
        tiles = []
        for m in ("tiny", "large"):
            img = base.copy()
            cv2.polylines(img, [p.reshape(-1, 1, 2) for p in polys[m]], True, COL[m], 3, cv2.LINE_AA)
            crop = img[y0:y1, x0:x1].copy()
            s = 900.0 / max(crop.shape[:2])
            crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)), interpolation=cv2.INTER_AREA)
            r = res["tracking"][m]["per_frame"][f]
            tiles.append(label(crop, "%s  f%d  core IoU %.3f" % (m.upper(), f, r["iou_core"]), (180, 180, 255) if m == "tiny" else (255, 200, 120)))
        h = max(t.shape[0] for t in tiles)
        tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
        cv2.imwrite(os.path.join(OUT, "%s_pair_f%05d.jpg" % (shot, f)), np.concatenate(tiles, 1), [cv2.IMWRITE_JPEG_QUALITY, 88])
    summary[shot] = {"pair_frames": frames, "worst": worst}


def hair(shot, frame=13):
    d = os.path.join(WORK, shot + "_large")
    ch = {}
    for t in ("hard", "guided", "vitmatte"):
        fs = sorted(glob.glob(os.path.join(d, "mattes_" + t, "*.exr")))
        if fs:
            ch[t] = exr.read_channels(fs[frame])
    if len(ch) < 3:
        return
    a = ch["guided"]["A"]
    h, w = a.shape
    pl, _ = plate_bgr(shot, frame, w)
    ka, _ = M.key_alpha(pl[..., ::-1].astype(np.float32) / 255.0)
    band = (ch["hard"]["A"] > 0.5).astype(np.uint8)
    edge = band - cv2.erode(band, np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero(edge)
    sel = xs > np.percentile(xs, 80)
    cy, cx = int(np.median(ys[sel])), int(np.median(xs[sel]))
    y0, x0 = max(0, cy - 170), max(0, cx - 170)
    crops = [("plate", pl[y0:y0 + 340, x0:x0 + 340].copy())]
    for name, img in (("keyed reference", ka), ("hard", ch["hard"]["A"]), ("guided filter", ch["guided"]["A"]),
                      ("ViTMatte-S", ch["vitmatte"]["A"])):
        g = (np.clip(img[y0:y0 + 340, x0:x0 + 340], 0, 1) * 255).astype(np.uint8)
        crops.append((name, cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)))
    tiles = [label(cv2.resize(c, (420, 420), interpolation=cv2.INTER_CUBIC), n) for n, c in crops]
    cv2.imwrite(os.path.join(OUT, "%s_hair_f%05d.jpg" % (shot, frame)), np.concatenate(
        [cv2.copyMakeBorder(t, 0, 0, 0, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles], 1),
        [cv2.IMWRITE_JPEG_QUALITY, 90])


def despill(shot, frame=None):
    d = os.path.join(WORK, shot + "_large")
    fa = sorted(glob.glob(os.path.join(d, "mattes_guided", "*.exr")))
    fb = sorted(glob.glob(os.path.join(d, "mattes_decon_spill", "*.exr")))
    if not fa or not fb:
        return
    i = len(fa) // 2 if frame is None else frame
    tiles = []
    ca, cb = exr.read_channels(fa[i]), exr.read_channels(fb[i])
    a = ca["A"]
    band = ((a > 0.05) & (a < 0.95)).astype(np.uint8)
    ys, xs = np.nonzero(band)
    cy, cx = int(np.median(ys)), int(np.median(xs[xs > np.percentile(xs, 70)]))
    y0, x0 = max(0, cy - 150), max(0, cx - 150)
    for name, c in (("plain (premultiplied)", ca), ("decontaminated + despill", cb)):
        rgb = np.stack([c["B"], c["G"], c["R"]], -1).astype(np.float32)
        grey = np.full_like(rgb, 0.18)
        comp = rgb + grey * (1 - c["A"][..., None])                    # premultiplied over mid grey
        comp = np.clip(comp, 0, 1) ** (1 / 2.2)
        crop = (comp[y0:y0 + 300, x0:x0 + 300] * 255).astype(np.uint8)
        tiles.append(label(cv2.resize(crop, (480, 480), interpolation=cv2.INTER_CUBIC), name))
    cv2.imwrite(os.path.join(OUT, "%s_despill.jpg" % shot), np.concatenate(
        [cv2.copyMakeBorder(t, 0, 0, 0, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles], 1),
        [cv2.IMWRITE_JPEG_QUALITY, 90])


def main():
    summary = {}
    for shot in sorted(k for k in M.PROMPTS if not k.startswith("_")):
        shot_pairs(shot, summary)
        print(shot, summary[shot], flush=True)
    for s in ("SHOT-115", "SHOT-116"):
        hair(s)
    for s in ("SHOT-113", "SHOT-115", "SHOT-118"):
        despill(s)
    json.dump(summary, open(os.path.join(OUT, "index.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
