"""OQ-28 (owner, 2026-11-17: "do it both full resolution and 1920x1080, test them"): EXR mattes at full plate
resolution vs fitted into 1920x1080, from the PRODUCT node in Nuke 17.1 NC.

  Nuke17.1.exe --nc -t research/probes/2026-11-17_matte_size/probe_matte_size.py <case>
cases: hd (1280x720 control), uhd4k (3840x2160), uhd8k (7680x4320); plates from research/probes/2026-11-17_formats/out.
Track once, then mattes for {full resolution, fit 1920x1080} x {guided filter, hard}: EXR size, time, IoU of the
matte (>0.5) vs the truth at that size, soft pixels, fit-vs-downscaled-full difference, and Nuke reading each EXR
back (channels, values at sample pixels). Writes result_<case>.json next to this script.
"""
import json
import os
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                       # noqa: E402
import numpy as np                                                # noqa: E402
import cv2                                                        # noqa: E402

PLATES = ROOT + "/research/probes/2026-11-17_formats/out"
CASE_DIR = {"hd": "png16", "uhd4k": "uhd4k", "uhd8k": "uhd8k"}


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def main(case):
    import st_roto_nuke.node as stnode
    from st_roto import exr
    d = PLATES + "/" + CASE_DIR[case]
    meta = json.load(open(d + "/case.json"))
    W, H, n = meta["width"], meta["height"], meta["frames"]
    res = {"case": case, "plate": [W, H]}
    rd = nuke.nodes.Read(file="%s/frame_####.%s" % (d, meta["ext"]), first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "ms.stroto")
    g = stnode.create(rd, proj)
    cx, cy = meta["click_xy"]
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([cx, H - cy]); stnode.on_add_point(g, 1)
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return res
    checker = None
    full_alpha = {}
    for size in ("full resolution", "fit 1920x1080"):
        for edges in ("guided filter", "hard"):
            key = "%s | %s" % (size, edges)
            g["stroto_matte_size"].setValue(size)
            g["stroto_edges"].setValue(edges)
            g["stroto_matte_dir"].setValue(os.path.join(tempfile.mkdtemp(), "m").replace("\\", "/"))
            t0 = time.time()
            jm = stnode.on_render_mattes(g, background=False)
            r = {"seconds": round(time.time() - t0, 2), "status": g["stroto_status"].value()[:260]}
            res[key] = r
            if jm is None or jm.status != "done":
                r["error"] = getattr(jm, "error", None); continue
            files = jm.result["files"]
            r["mb_per_frame"] = round(os.path.getsize(files[2]) / 1e6, 2)
            ch = exr.read_channels(files[2])
            a = ch["A"]
            r["exr_size"] = [a.shape[1], a.shape[0]]
            gt_full = cv2.imread("%s/gt_%04d.png" % (d, 2), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
            gt = gt_full if a.shape == gt_full.shape else cv2.resize(gt_full, (a.shape[1], a.shape[0]),
                                                                     interpolation=cv2.INTER_AREA)
            r["iou_vs_truth"] = round(iou(a > 0.5, gt > 0.5), 4)
            r["soft_pixels"] = int(((a > 0.02) & (a < 0.98)).sum())
            if size == "full resolution":
                full_alpha[edges] = a
            elif edges in full_alpha and a.shape != full_alpha[edges].shape:
                down = cv2.resize(full_alpha[edges], (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
                r["max_diff_vs_downscaled_full"] = float(np.abs(down - a).max())
            # Nuke reads it back (reading is not limited by the Non-commercial render cap)
            try:
                if checker is None:
                    checker = nuke.nodes.Read(file=files[2].replace("\\", "/"), first=2, last=2)
                else:
                    checker["file"].setValue(files[2].replace("\\", "/"))
                    checker["reload"].execute()
                nuke.frame(2)
                r["nuke_format"] = [checker.format().width(), checker.format().height()]
                r["nuke_channels"] = sorted(c for c in checker.channels() if "alpha" in c)
                ys, xs = np.nonzero((a > 0.02) & (a < 0.98)) if r["soft_pixels"] else np.nonzero(a > 0.5)
                pick = list(zip(xs[::max(1, len(xs) // 10)], ys[::max(1, len(ys) // 10)]))[:10]
                h = a.shape[0]
                r["nuke_max_abs_diff"] = float(max(abs(checker.sample("rgba.alpha", x + 0.5, h - y - 0.5) - a[y, x])
                                                   for x, y in pick))
            except Exception as e:
                r["nuke_read_error"] = str(e)[:200]
    return res


if __name__ == "__main__":
    case = sys.argv[1]
    try:
        out = main(case)
    except Exception:
        out = {"case": case, "exception": traceback.format_exc()}
    json.dump(out, open("%s/result_%s.json" % (HERE, case), "w"), indent=1, default=str)
    print("done", case)
