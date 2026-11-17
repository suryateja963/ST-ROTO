"""OQ-29 pipeline test with a SIMULATED artist (not a truth!): proves kit -> Nuke drawing -> Save Roto edits ->
export_truth -> edge_study --truth end to end, without touching the owner's kit project or truth files.

  Nuke17.1.exe --nc -t research/probes/2026-11-17_edge_truth/simulate_artist.py
In headless Nuke: tools/edge_truth/open_kit.py with a THROW-AWAY project; per frame a Roto shape keyed only on that
frame, fitted to SA-V's mask placed on the canvas (stand-in for the artist's drawing), plus one 'hole' shape on frame
1; 'Save Roto edits to project'; export_truth into a throw-away folder; each exported truth is compared with the mask
that was drawn (size, IoU, the hole). Writes result_simulate_artist.json; the folder of the exported masks is in it
for `edge_study.py --truth data/edge_truth --truth-dir <folder> --tag simulated`.
"""
import json
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src", ROOT + "/tools/edge_truth"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                       # noqa: E402
import numpy as np                                                # noqa: E402
import cv2                                                        # noqa: E402

KIT = ROOT + "/data/edge_truth"
SAV = ROOT + "/data/benchmarks/sa-v"


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def main():
    import open_kit
    import export_truth
    import st_roto_nuke.node as stnode
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "simulated.stroto")
    out = os.path.join(tmp, "truth")
    os.makedirs(out)
    man = json.load(open(KIT + "/manifest.json"))
    cw, ch = man["canvas"]
    g, plate = open_kit.open_kit(KIT, project=proj)
    res = {"ai_off": bool(g["stroto_ai_off"].value()), "frames": len(man["frames"])}
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    drawn = {}
    for e in man["frames"]:
        m = cv2.imread("%s/%s/masks/%s.png" % (SAV, e["seq"], e["sav_frame"]), cv2.IMREAD_GRAYSCALE) > 127
        canvas = np.zeros((ch, cw), bool); canvas[:m.shape[0], :m.shape[1]] = m
        n, lab = cv2.connectedComponents(canvas.astype(np.uint8))   # like the artist: one shape per piece
        for i in range(1, n):
            piece = lab == i
            if piece.sum() < 10:
                continue
            pts = mask_to_points(piece.astype(float) - 0.5, count=96)
            curves.rootLayer.append(build_shape(curves, "truth_%02d_p%d" % (e["frame"], i), {e["frame"]: pts}, ch))
        drawn[e["frame"]] = m
    e1 = man["frames"][0]
    ys, xs = np.nonzero(drawn[1])
    cy, cx = int(np.median(ys)), int(np.median(xs))
    r = max(3, int(0.15 * min(xs.max() - xs.min(), ys.max() - ys.min())))
    yy, xx = np.mgrid[0:ch, 0:cw]
    hole = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) <= r
    curves.rootLayer.append(build_shape(curves, "hole_1", {1: mask_to_points(hole.astype(float) - 0.5, count=24)}, ch))
    nuke.frame(1)
    rep = stnode.on_import_edits(g)                           # = the 'Save Roto edits to project' button
    res["save_status"] = g["stroto_status"].value()[:300]
    ex = export_truth.export(KIT, project=proj, out_dir=out)
    res["export"] = ex
    res["truth_dir"] = out.replace("\\", "/")
    cmp = {}
    for f, m in drawn.items():
        p = os.path.join(out, "truth.%04d.png" % f)
        if not os.path.exists(p):
            cmp[f] = None; continue
        t = cv2.imread(p, cv2.IMREAD_GRAYSCALE) > 127
        expect = m & ~hole[:m.shape[0], :m.shape[1]] if f == 1 else m
        cmp[f] = {"size_ok": t.shape == m.shape, "iou_vs_drawn": round(iou(t, expect), 4)}
    res["compare"] = cmp
    res["hole_respected"] = bool(cmp.get(1)) and not (cv2.imread(os.path.join(out, "truth.0001.png"),
                                                                 cv2.IMREAD_GRAYSCALE)[cy, cx] > 127)
    vals = [c["iou_vs_drawn"] for c in cmp.values() if c]
    res["iou_min"], res["iou_mean"] = (min(vals), round(float(np.mean(vals)), 4)) if vals else (None, None)
    res["passed"] = (res["ai_off"] and len(ex["drawn"]) == res["frames"] and all(c and c["size_ok"] for c in cmp.values())
                     and res["hole_respected"] and res["iou_min"] > 0.95)
    return res


if __name__ == "__main__":
    try:
        r = main()
    except Exception:
        r = {"exception": traceback.format_exc()}
    json.dump(r, open(HERE + "/result_simulate_artist.json", "w"), indent=1, default=str)
    print("done", r.get("passed"))
