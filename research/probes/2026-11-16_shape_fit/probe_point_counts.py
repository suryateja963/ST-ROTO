"""Where does shape accuracy go on real footage? (T-080, SA-V subset, box prompts.)

One tracking pass per sequence; the SAME logits feed several shape builders, all scored against the SA-V truth:
  raw      - the AI's pixel mask (logits > 0): the ceiling set by the model
  outline  - the traced outer contours filled as polygons (no holes): the ceiling for ANY spline without holes
  auto, 16, 24, 32, 48, 64 - pieces.Sequencer (main + part shapes) with that point count (auto = chosen on the
             prompt frame by pieces.choose_count, then constant - today's default)
Rasterisation is exact (geometry.rasterize_closed) inside the bounding box of all candidates + truth.
Run: Nuke17.1.exe --nc -t research/probes/2026-11-16_shape_fit/probe_point_counts.py [--limit=N] [--every=K] [--model=sam2.1-hiera-large]
(use --opt=value: Nuke -t takes bare numbers as frame ranges)
Writes result_point_counts_<model>.json next to this file.
"""
import argparse, json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools", "benchmark"))
import calibrate_review as cr                                  # noqa: E402  (adds .tools/nuke-py311 under Nuke: first)
import numpy as np   # noqa: E402
import cv2           # noqa: E402
from st_roto import pieces                                     # noqa: E402
from st_roto.geometry import Anchor, sample_spline, rasterize_closed   # noqa: E402

VARIANTS = ["auto", 16, 24, 32, 48, 64]


def polys_of_keys(points_list):
    out = []
    for pts in points_list:
        if pts and not pieces.is_collapsed(pts):
            out.append(sample_spline([Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]),
                                             corner=False) for p in pts], 32))
    return out


def fast_closed(poly, height, width):
    """Same rule as geometry.rasterize_closed (pixel centre inside, even-odd), vectorised: every edge crossing of a
    row at x flips all centres c + 0.5 > x, i.e. columns >= floor(x - 0.5) + 1 (checked equal in --selftest)."""
    p = np.asarray(poly, np.float64)
    q = np.roll(p, -1, axis=0)
    ys = np.arange(height) + 0.5
    y0, y1 = p[:, 1][None, :], q[:, 1][None, :]
    cross = ((y0 <= ys[:, None]) & (y1 > ys[:, None])) | ((y1 <= ys[:, None]) & (y0 > ys[:, None]))
    r, e = np.nonzero(cross)
    t = (ys[r] - p[e, 1]) / (q[e, 1] - p[e, 1])
    xs = p[e, 0] + t * (q[e, 0] - p[e, 0])
    k = np.clip(np.floor(xs - 0.5).astype(np.int64) + 1, 0, width)
    acc = np.zeros((height, width + 1), np.int32)
    np.add.at(acc, (r, k), 1)
    return (np.cumsum(acc, axis=1)[:, :width] % 2).astype(bool)


def raster(polys, box):
    x0, y0, x1, y1 = box
    m = np.zeros((y1 - y0, x1 - x0), bool)
    for p in polys:
        m |= fast_closed(p - [x0, y0], y1 - y0, x1 - x0)
    return m


def selftest():
    rng = np.random.default_rng(0)
    for i in range(200):
        n = rng.integers(3, 60)
        ang = np.sort(rng.uniform(0, 2 * np.pi, n))
        rad = rng.uniform(5, 40, n)
        poly = np.c_[50 + rad * np.cos(ang), 45 + rad * np.sin(ang)] + rng.uniform(-0.5, 0.5, (n, 2))
        if i % 3 == 0:
            poly = np.round(poly)                         # vertices exactly on pixel centres / edges
        a, b = rasterize_closed(poly, 90, 100), fast_closed(poly, 90, 100)
        assert (a == b).all(), i
    print("selftest: fast_closed == rasterize_closed on 200 random polygons")


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--model", default="sam2.1-hiera-tiny")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    from st_roto_ai.sam2 import Sam2MultiVideo
    from st_roto_nuke import colour
    from st_roto_nuke.track import models_root
    seqs = cr.folder_sequences(os.path.join(ROOT, "data", "benchmarks", "sa-v"))
    if a.limit:
        seqs = seqs[:a.limit]
    rows, counts, t_all = [], {}, time.time()
    for name, order, frames, gt in seqs:
        t0 = time.time()
        pts, lbl = cr.prompt_for(gt[order[0]], "box")
        multi = Sam2MultiVideo(os.path.join(models_root(), a.model, "video"), device="auto")
        trk = multi.add_object(0, num_total_frames=len(order), max_frames_in_ram=24)
        seqrs = {v: pieces.Sequencer(count=v, parts=True) for v in VARIANTS}
        last = {v: None for v in VARIANTS}
        try:
            for i, f in enumerate(order):
                rgb = cr.srgb_to_linear(cv2.cvtColor(cv2.imread(frames[f]), cv2.COLOR_BGR2RGB) / 255.0)
                enc = multi.encode(colour.to_model_input(rgb, colour.TRANSFORM_ID))
                out = trk.add_points(0, enc, pts, lbl) if i == 0 else trk.track(i, enc)
                present = out["object_score"] > 0
                for v in VARIANTS:
                    if seqrs[v].add(f, out["logits"], ref=last[v], present=present):
                        last[v] = f
                if i % a.every or not gt[f].sum() > 50:
                    continue                                   # score visible truth frames only
                h, w = gt[f].shape
                raw = out["logits"] > 0 if present else np.zeros((h, w), bool)
                loops = pieces.outer_loops(out["logits"])[0] if present else []
                cand = {v: polys_of_keys([seqrs[v].main.get(f)] + [p["keys"].get(f) for p in seqrs[v].parts])
                        for v in VARIANTS}
                allp = [p for ps in cand.values() for p in ps] + list(loops)
                ys, xs = np.nonzero(gt[f] | raw)
                bx = [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]
                for p in allp:
                    bx = [min(bx[0], p[:, 0].min()), min(bx[1], p[:, 1].min()), max(bx[2], p[:, 0].max()),
                          max(bx[3], p[:, 1].max())]
                x0, y0 = max(0, int(np.floor(bx[0])) - 1), max(0, int(np.floor(bx[1])) - 1)
                x1, y1 = min(w, int(np.ceil(bx[2])) + 1), min(h, int(np.ceil(bx[3])) + 1)
                box = (x0, y0, x1, y1)
                g = gt[f][y0:y1, x0:x1]
                r = {"seq": name, "frame": f, "raw": iou(raw[y0:y1, x0:x1], g), "outline": iou(raster(loops, box), g),
                     "holes": int(pieces.outer_loops(out["logits"])[1]) if present else 0,
                     "gt_area": int(gt[f].sum())}
                for v in VARIANTS:
                    r[str(v)] = iou(raster(cand[v], box), g)
                rows.append(r)
        finally:
            rep = multi.report
            cr.DEVICES.add(rep.active + (" (FALLBACK: %s)" % rep.reason if rep.fallback else ""))
            multi.close()
        counts[name] = {str(v): seqrs[v].count for v in VARIANTS}
        sel = [r for r in rows if r["seq"] == name]
        print("%-16s %3d frames %4.0f s  raw %.3f outline %.3f auto(%s) %.3f 32 %.3f 64 %.3f" % (
            name, len(order), time.time() - t0, np.mean([r["raw"] for r in sel]), np.mean([r["outline"] for r in sel]),
            counts[name]["auto"], np.mean([r["auto"] for r in sel]), np.mean([r["32"] for r in sel]),
            np.mean([r["64"] for r in sel])), flush=True)
    keys = ["raw", "outline"] + [str(v) for v in VARIANTS]
    good = [r for r in rows if r["raw"] >= 0.5]               # frames where the AI found the object (fit question)
    summary = {k: {"mean_all": round(float(np.mean([r[k] for r in rows])), 4),
                   "mean_found": round(float(np.mean([r[k] for r in good])), 4)} for k in keys}
    res = {"model": a.model, "devices": sorted(cr.DEVICES), "sequences": len(seqs), "frames": len(rows),
           "frames_found": len(good), "every": a.every, "auto_counts": counts, "summary": summary, "rows": rows,
           "seconds": round(time.time() - t_all)}
    json.dump(res, open(os.path.join(os.path.dirname(__file__), "result_point_counts_%s.json" % a.model), "w"), indent=1)
    print("SUMMARY (mean IoU; 'found' = frames with raw IoU >= 0.5):")
    for k in keys:
        print("  %-8s all %.4f  found %.4f" % (k, summary[k]["mean_all"], summary[k]["mean_found"]))


if __name__ == "__main__":
    main()
