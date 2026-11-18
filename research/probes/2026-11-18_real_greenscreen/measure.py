"""Measure the real green-screen runs (run_shot.py) against a KEYED REFERENCE made from the plates.
  .venv\\Scripts\\python.exe -I measure.py work=<dir with SHOT-xxx_tiny / _large> overlays=<folder for images>
Numbers -> result_<shot>.json + summary.json here (committed); overlay images ONLY into `overlays` (never committed).

Keyed reference (no human truth exists for this footage): plates are display-referred 16-bit (colour space unknown;
treated as sRGB/Rec.709), measured at half resolution (2048 x 1080). Green ratio r = (G - max(R, B)) / G; the
screen's r is the median r of clearly green pixels of that frame; alpha = 1 - clip((r - 0.3 s) / (0.4 s), 0, 1).
reference = alpha >= 0.5; 'certain' pixels have alpha <= 0.05 or >= 0.95 (the rest - hair, motion blur, spill, soft
edges - is the uncertain band, excluded from the core IoU). The key sees EVERY non-green thing, so SHOT-118 is
measured inside a region of interest around the couple only."""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.append(os.path.join(ROOT, ".tools", "nuke-py311"))
import cv2  # noqa: E402
from st_roto.geometry import Anchor, rasterize_spline  # noqa: E402
from st_roto import pieces, views  # noqa: E402
from st_roto.store import ProjectStore  # noqa: E402
from st_roto import exr  # noqa: E402

SRC = "D:/reffeerce shots/GREEN MATTE"
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
WORK, OVER = args["work"], args.get("overlays")
HW, HH = 2048, 1080                       # measurement size (half of 4096 x 2160)
PROMPTS = json.load(open(os.path.join(HERE, "prompts.json")))


def plate(shot, f, size=(HW, HH)):
    a = cv2.imread("%s/%s/%s_%05d.tif" % (SRC, shot, shot, f), cv2.IMREAD_UNCHANGED)
    a = cv2.resize(a, size, interpolation=cv2.INTER_AREA).astype(np.float32) / 65535.0
    return a[..., ::-1]                                       # RGB


def key_alpha(rgb):
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    ratio = (g_ - np.maximum(r_, b_)) / np.maximum(g_, 0.02)
    s = float(np.median(ratio[ratio > 0.2])) if (ratio > 0.2).any() else 0.4
    return 1.0 - np.clip((ratio - 0.3 * s) / (0.4 * s), 0.0, 1.0), s


def raster(points, scale=0.5):
    a = [Anchor(p=np.array(q[:2]) * scale, h_in=np.array(q[2:4]) * scale, h_out=np.array(q[4:]) * scale, corner=False)
         for q in points]
    return rasterize_spline(a, HH, HW)


def fill_holes(m):
    """m plus every background region not connected to the image border (e.g. green seen between raised arms)."""
    inv = (~m).astype(np.uint8)
    lab_n, lab = cv2.connectedComponents(inv, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    holes = (inv > 0) & ~np.isin(lab, list(border))
    return m | holes


def bfscore(p, g, tol=3.0):
    def edge(m):
        m8 = m.astype(np.uint8)
        return (m8 - cv2.erode(m8, np.ones((3, 3), np.uint8))).astype(bool)
    bp, bg = edge(p), edge(g)
    # where the subject leaves the frame the AI shape ends a pixel or two inside the image while the key touches the
    # border: those are frame edges, not object boundaries - ignore a 4 px strip along the border (both sides)
    inner = np.zeros_like(bp)
    inner[4:-4, 4:-4] = True
    bp, bg = bp & inner, bg & inner
    if not bp.any() or not bg.any():
        return 0.0
    dg = cv2.distanceTransform((~bg).astype(np.uint8), cv2.DIST_L2, 3)
    dp = cv2.distanceTransform((~bp).astype(np.uint8), cv2.DIST_L2, 3)
    prec, rec = float((dg[bp] <= tol).mean()), float((dp[bg] <= tol).mean())
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def object_masks(store, frames):
    """{object name: {frame: bool mask (half res)}} - union of main + part shapes, collapsed keys = absent."""
    shot_id = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    out, flags = {}, {}
    for o in store.objects(shot_id):
        per = {}
        for s in store.shapes(o["id"]):
            for k in store.keys(s["id"]):
                if not k["points"] or pieces.is_collapsed(k["points"]):
                    continue
                m = raster(k["points"])
                per[k["frame"]] = per[k["frame"]] | m if k["frame"] in per else m
        out[o["name"]] = per
        fl = views.review_for_object(store, o["id"])
        flags[o["name"]] = {"lost": sorted({f for f, lvl, _ in fl if lvl == "lost"}),
                            "check": sorted({f for f, lvl, _ in fl if lvl != "lost"})}
    return out, flags


def roi_mask(shot):
    m = np.ones((HH, HW), bool)
    roi = PROMPTS[shot].get("roi")
    if roi:
        m[:] = False
        m[int(roi[1] * HH):int(roi[3] * HH), int(roi[0] * HW):int(roi[2] * HW)] = True
    return m


def measure_tracking(shot, nframes):
    roi = roi_mask(shot)
    eval_objs = [n for n in PROMPTS[shot]["objects"] if n != "crew"]
    res, preds = {}, {}
    keys = {}
    for mdl in ("tiny", "large"):
        p = os.path.join(WORK, "%s_%s" % (shot, mdl), shot + ".stroto")
        if not os.path.exists(p) or not os.path.exists(os.path.join(os.path.dirname(p), "run.json")):
            continue                                          # missing, or the run has not finished yet
        st = ProjectStore(p)
        keys[mdl] = object_masks(st, range(nframes))
        st.conn.close()
    rows = {m: [] for m in keys}
    ref_cache = []
    for f in range(nframes):
        rgb = plate(shot, f)
        a, s = key_alpha(rgb)
        ref = (a >= 0.5) & roi
        certain = ((a <= 0.05) | (a >= 0.95)) & roi
        filled = fill_holes(ref)                              # Roto shapes have no holes (status says so)
        ref_cache.append((f, a, s))
        for mdl, (masks, _fl) in keys.items():
            pu = np.zeros((HH, HW), bool)
            for n in eval_objs:
                if f in masks.get(n, {}):
                    pu |= masks[n][f]
            pu &= roi
            inter, union = (pu & ref).sum(), (pu | ref).sum()
            ci, cu = (pu & ref & certain).sum(), ((pu | ref) & certain).sum()
            hi_, hu_ = (pu & filled & certain).sum(), ((pu | filled) & certain).sum()
            row = {"frame": f, "iou": round(float(inter / max(1, union)), 4),
                   "iou_core_holes_filled": round(float(hi_ / max(1, hu_)), 4),
                   "iou_core": round(float(ci / max(1, cu)), 4), "bf3": round(bfscore(pu, ref), 4),
                   "screen_ratio": round(s, 3), "uncertain_px_pct": round(100.0 * float((~certain & roi).sum()) / roi.sum(), 2)}
            per = {}
            for n, mk in masks.items():
                if f in mk:
                    m = mk[f]
                    per[n] = {"area_px": int(m.sum()),
                              "on_certain_background_pct": round(100.0 * float((m & (a <= 0.05)).sum()) / max(1, m.sum()), 2)}
                else:
                    per[n] = None
            if len(eval_objs) == 2 and all(f in masks.get(n, {}) for n in eval_objs):
                m1, m2 = masks[eval_objs[0]][f], masks[eval_objs[1]][f]
                per["overlap_between_objects_px"] = int((m1 & m2).sum())
            row["objects"] = per
            rows[mdl].append(row)
            preds.setdefault(mdl, {})[f] = pu
    for mdl, rs in rows.items():
        iou = np.array([r["iou"] for r in rs])
        core = np.array([r["iou_core"] for r in rs])
        bf = np.array([r["bf3"] for r in rs])
        fl = keys[mdl][1]
        bad = [r["frame"] for r in rs if r["iou_core"] < 0.9]
        flagged = sorted({f for v in fl.values() for f in v["lost"] + v["check"]})
        leak = {n: round(float(np.mean([r["objects"][n]["on_certain_background_pct"] for r in rs
                                         if r["objects"].get(n)])), 3)
                for n in keys[mdl][0] if any(r["objects"].get(n) for r in rs)}
        hf = np.array([r["iou_core_holes_filled"] for r in rs])
        res[mdl] = {"frames": len(rs), "iou_mean": round(float(iou.mean()), 4), "iou_min": round(float(iou.min()), 4),
                    "iou_core_holes_filled_mean": round(float(hf.mean()), 4),
                    "iou_core_holes_filled_min": round(float(hf.min()), 4),
                    "iou_core_mean": round(float(core.mean()), 4), "iou_core_min": round(float(core.min()), 4),
                    "bf3_mean": round(float(bf.mean()), 4), "bf3_min": round(float(bf.min()), 4),
                    "temporal_iou_jitter": round(float(np.mean(np.abs(np.diff(core)))), 4) if len(core) > 1 else 0.0,
                    "frames_core_below_0.9": bad, "review_flags": fl,
                    "flags_on_bad_frames": sorted(set(flagged) & set(bad)),
                    "object_leak_onto_certain_background_pct": leak,
                    "frames_without_object": {n: [f for f in range(nframes) if f not in keys[mdl][0][n]]
                                              for n in keys[mdl][0]},
                    "per_frame": rs}
    return res, preds, ref_cache


def measure_mattes(shot):
    out = {}
    d = os.path.join(WORK, shot + "_large")
    if not os.path.exists(os.path.join(d, "run.json")):
        return out
    tags = [os.path.basename(p)[len("mattes_"):] for p in sorted(glob.glob(os.path.join(d, "mattes_*")))]
    if not tags:
        return out
    data = {}
    for t in tags:
        fs = sorted(glob.glob(os.path.join(d, "mattes_" + t, "**", "*.exr"), recursive=True))
        data[t] = fs
    nfr = min(len(v) for v in data.values())
    roi_full = PROMPTS[shot].get("roi")
    stats = {t: {"sad_band": [], "mse_band": [], "sad_all": []} for t in tags}
    spill = {"plain": [], "decon_spill": [], "core_change": []}
    hold = []
    for i in range(nfr):
        chans = {t: exr.read_channels(data[t][i]) for t in tags}
        a0 = chans[tags[0]]["A"]
        h, w = a0.shape
        f = int(os.path.basename(data[tags[0]][i]).split(".")[-2])
        ka, _s = key_alpha(plate(shot, f, (w, h)))
        roi = np.ones((h, w), bool)
        if roi_full:
            roi[:] = False
            roi[int(roi_full[1] * h):int(roi_full[3] * h), int(roi_full[0] * w):int(roi_full[2] * w)] = True
        band = cv2.dilate(((ka > 0.05) & (ka < 0.95)).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & roi
        for t in tags:
            if t == "holdout":
                continue
            am = np.clip(chans[t]["A"].astype(np.float64), 0, 1)
            stats[t]["sad_band"].append(float(np.abs(am - ka)[band].sum()) / 1000.0)
            stats[t]["mse_band"].append(float(((am - ka) ** 2)[band].mean()) if band.any() else 0.0)
            stats[t]["sad_all"].append(float(np.abs(am - ka)[roi].sum()) / 1000.0)
        if "decon_spill" in chans and "guided" in chans:
            def unpremult(c):
                a = np.clip(c["A"].astype(np.float64), 1e-4, 1)
                return np.stack([c["R"], c["G"], c["B"]], -1).astype(np.float64) / a[..., None], c["A"]
            for tag, key in (("guided", "plain"), ("decon_spill", "decon_spill")):
                rgb, a = unpremult(chans[tag])
                eb = (a > 0.1) & (a < 0.9) & roi
                g_exc = np.maximum(0.0, rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2]))
                spill[key].append(float(g_exc[eb].mean()) if eb.any() else 0.0)
            rp, ap = unpremult(chans["guided"])
            rd, _ = unpremult(chans["decon_spill"])
            core = (ap > 0.98) & roi
            spill["core_change"].append(float(np.abs(rp - rd)[core].mean()) if core.any() else 0.0)
        if "holdout" in chans:
            c = chans["holdout"]
            layers = {k.split(".")[0]: v for k, v in c.items() if k.endswith(".A")}
            hn = "man"
            others = [k for k in layers if k != hn]
            if hn in layers and others:
                expect = np.clip(sum(layers[k] for k in others), 0, 1) * (1 - layers[hn])
                hold.append({"max_abs_err": float(np.abs(c["A"] - expect).max()),
                             "mean_abs_err": float(np.abs(c["A"] - expect).mean()),
                             "removed_px": int(((np.clip(sum(layers[k] for k in others), 0, 1) - c["A"]) > 0.5).sum())})
    for t in tags:
        if t != "holdout" and stats[t]["sad_band"]:
            out[t] = {k: round(float(np.mean(v)), 4) for k, v in stats[t].items()}
    out["frames"] = nfr
    if spill["plain"]:
        out["despill"] = {"edge_green_excess_plain": round(float(np.mean(spill["plain"])), 5),
                          "edge_green_excess_decon_spill": round(float(np.mean(spill["decon_spill"])), 5),
                          "core_rgb_change_mean": round(float(np.mean(spill["core_change"])), 5)}
    if hold:
        out["holdout"] = {"frames": len(hold), "max_abs_err": round(max(h["max_abs_err"] for h in hold), 5),
                          "mean_abs_err": round(float(np.mean([h["mean_abs_err"] for h in hold])), 6),
                          "frames_where_holdout_removed_pixels": sum(1 for h in hold if h["removed_px"] > 0)}
    return out


def overlays(shot, preds, ref_cache, track):
    if not OVER:
        return
    os.makedirs(OVER, exist_ok=True)
    pick = sorted({0, len(ref_cache) // 2, len(ref_cache) - 1}
                  | {min(track[m]["per_frame"], key=lambda r: r["iou_core"])["frame"] for m in track})
    tiles = []
    for f in pick:
        rgb = plate(shot, f, (HW, HH))
        img = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)[..., ::-1].copy()
        a = ref_cache[f][1]
        for m, col in (("ref", (0, 255, 255)), ("tiny", (0, 0, 255)), ("large", (255, 0, 0))):
            mk = (a >= 0.5) if m == "ref" else preds.get(m, {}).get(f)
            if mk is None:
                continue
            cs, _ = cv2.findContours(mk.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(img, cs, -1, col, 2)
        t = cv2.resize(img, (960, 506), interpolation=cv2.INTER_AREA)
        txt = "%s f%d  " % (shot, f) + "  ".join("%s IoUcore %.3f" % (m, track[m]["per_frame"][f]["iou_core"]) for m in track)
        cv2.putText(t, txt, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        tiles.append(t)
    legend = np.zeros((30, 960, 3), np.uint8)
    cv2.putText(legend, "yellow = keyed reference   red = tiny   blue = large", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 1)
    cv2.imwrite(os.path.join(OVER, "%s_overlay.jpg" % shot), np.concatenate([legend] + tiles, 0),
                [cv2.IMWRITE_JPEG_QUALITY, 88])


def main():
    shots = sorted(k for k in PROMPTS if not k.startswith("_"))
    if args.get("shots"):
        shots = args["shots"].split(",")
    summary = {}
    for shot in shots:
        n = len(glob.glob("%s/%s/%s_*.tif" % (SRC, shot, shot)))
        track, preds, refc = measure_tracking(shot, n)
        mattes = measure_mattes(shot)
        runs = {}
        for m in ("tiny", "large"):
            rp = os.path.join(WORK, "%s_%s" % (shot, m), "run.json")
            if os.path.exists(rp):
                r = json.load(open(rp))
                runs[m] = {"ok": r.get("ok", False), "exception": (r.get("exception") or "")[-400:],
                           "steps": [{"step": s["step"], "seconds": s["seconds"], "status": s["status"]}
                                     for s in r["steps"]], "scene_cuts_knob": r.get("scene_cuts_knob")}
        res = {"shot": shot, "frames": n, "runs": runs, "tracking": track, "mattes": mattes}
        json.dump(res, open(os.path.join(HERE, "result_%s.json" % shot), "w"), indent=1)
        overlays(shot, preds, refc, track)
        summary[shot] = {"frames": n, "tracking": {m: {k: v for k, v in t.items() if k != "per_frame"}
                                                   for m, t in track.items()}, "mattes": mattes,
                         "seconds": {m: sum(s["seconds"] for s in r["steps"]) for m, r in runs.items()}}
        print(shot, {m: (t["iou_core_mean"], t["iou_core_min"], t["bf3_mean"]) for m, t in track.items()},
              json.dumps(mattes)[:300])
    json.dump(summary, open(os.path.join(HERE, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
