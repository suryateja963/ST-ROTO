"""T-086 / REQ-092: run the PRODUCT Track (ST_Roto node, tiny model, CUDA) on one edge-case sequence and score it.

  Nuke17.1.exe --nc -t research/probes/2026-11-17_sequences/probe_sequences.py <case>
cases: start1001 missing discontinuous duplicate mixed_res proxy retime
Writes out/result_<case>.json: job status/error, status text, frames keyed, rendered plate sizes, IoU of each key
against the truth of the image Nuke actually showed on that frame.
"""
import json
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                       # noqa: E402
import numpy as np                                                # noqa: E402
import cv2                                                        # noqa: E402

OUT = HERE + "/out"
SYN = ROOT + "/research/probes/2026-11-15_video/frames"
W, H = 1280, 720


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def main(case):
    import st_roto_nuke.node as stnode
    from st_roto_nuke import pixels, session
    from st_roto import views
    from st_roto.geometry import Anchor, rasterize_spline
    res = {"case": case, "nuke": nuke.NUKE_VERSION_STRING}
    seq = {"proxy": "plain", "retime": "plain"}.get(case, case)
    frames = {int(k): v for k, v in json.load(open("%s/%s/case.json" % (OUT, seq)))["frames"].items()}
    first, last = min(frames), max(frames)
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file="%s/%s/frame_####.png" % (OUT, seq), first=first, last=last)
    res["read_on_error"] = rd["on_error"].value()
    src = rd
    if case == "retime":
        src = nuke.nodes.Retime(inputs=[rd])
        src["input.first_lock"].setValue(True); src["input.last_lock"].setValue(True)
        src["speed"].setValue(0.5)
        src["filter"].setValue("none")
    if case == "proxy":
        nuke.root()["proxy_type"].setValue("scale")
        nuke.root()["proxy_scale"].setValue(0.5)
        nuke.root()["proxy"].setValue(True)
    res["source_range"] = [int(src.firstFrame()), int(src.lastFrame())]
    res["source_size"] = [int(src.width()), int(src.height())]
    proj = os.path.join(tempfile.mkdtemp(), "seq.stroto")
    g = stnode.create(src, proj)
    pf = int(src.firstFrame())
    cx, cy = json.load(open(SYN + "/meta.json"))["click_xy"]
    g["stroto_object"].setValue("target"); nuke.frame(pf)
    g["stroto_click"].setValue([cx, H - cy]); stnode.on_add_point(g, 1)
    job = stnode.on_track(g, background=False)
    res["status"] = g["stroto_status"].value()
    res["job_status"] = job.status if job else None
    res["job_error"] = (job.error if job else None)
    if job is not None and job.status == "done" and case != "retime":
        jr = stnode.on_retrack(g, background=False)            # Re-track over the same sequence
        res["retrack_status"] = g["stroto_status"].value()
        res["retrack_job"] = jr.status if jr else None
        g["stroto_soft"].setValue(True)
        jm = stnode.on_render_mattes(g, background=False)
        res["mattes_status"] = g["stroto_status"].value()
        res["mattes_job"] = jm.status if jm else None
        res["matte_files"] = len(jm.result["files"]) if jm is not None and jm.status == "done" else None
    # what Nuke shows on each frame of the source (full resolution, proxy off) -> which truth to score against
    nuke.root()["proxy"].setValue(False)
    wr = nuke.nodes.Write(inputs=[src]); path = OUT + "/px_%s.tif" % case
    pixels.configure_write(wr, path); wr["disable"].setValue(True)
    synth = {i: cv2.imread(SYN + "/frame_%04d.png" % i)[:, :, ::-1].astype(np.float32) / 255.0 for i in range(48)}
    shown = {}
    for f in range(res["source_range"][0], res["source_range"][1] + 1):
        try:
            img = pixels.render_frame(wr, f, path)
        except Exception as e:
            shown[f] = {"error": str(e).splitlines()[0][:160]}
            continue
        entry = {"size": [img.shape[1], img.shape[0]]}
        if img.shape[:2] == (H, W):                                # identify the synthetic source frame
            lin = np.clip(img, 0, 1) ** (1 / 2.2)                 # Read linearises sRGB PNGs; compare roughly
            d = {i: float(np.abs(lin[::8, ::8] - s[::8, ::8]).mean()) for i, s in synth.items()}
            best = min(d, key=d.get)
            entry["source_frame"] = best; entry["match_err"] = round(d[best], 4)
        shown[f] = entry
    res["shown"] = shown
    store, _ = session.project(proj)
    scores = {}
    try:
        oid = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]["id"]
        sid = views.main_shape(store, oid)["id"]
        for k in store.keys(sid):
            f = k["frame"]
            a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False)
                 for p in k["points"]]
            m = rasterize_spline(a, H, W)
            s = shown.get(f, {})
            sf = s.get("source_frame")
            if sf is None and f in frames:
                sf = frames[f]["source"]
            if sf is None:
                scores[f] = {"area": int(m.sum()), "iou": None}
                continue
            gt = cv2.imread(SYN + "/gt_%04d.png" % sf, cv2.IMREAD_GRAYSCALE) > 127
            scores[f] = {"area": int(m.sum()), "iou_vs_full_res_truth": round(iou(m, gt), 4)}
            if frames.get(f, {}).get("scale", 1.0) != 1.0:          # mixed res: image sits at Nuke's origin
                sc = frames[f]["scale"]
                small = cv2.resize(gt.astype(np.uint8), (int(W * sc), int(H * sc)), interpolation=cv2.INTER_NEAREST)
                placed = np.zeros((H, W), bool); placed[H - small.shape[0]:, :small.shape[1]] = small > 0
                scores[f]["iou_vs_truth_at_bottom_left"] = round(iou(m, placed), 4)
    except Exception:
        res["score_error"] = traceback.format_exc()
    res["keys"] = scores
    res["frames_keyed"] = sorted(scores)
    return res


if __name__ == "__main__":
    case = sys.argv[1]
    try:
        r = main(case)
    except Exception:
        r = {"case": case, "exception": traceback.format_exc()}
    json.dump(r, open("%s/result_%s.json" % (OUT, case), "w"), indent=1, default=str)
    print("done", case)
