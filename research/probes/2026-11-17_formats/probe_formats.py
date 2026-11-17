"""T-089 / REQ-110, REQ-111: PRODUCT Track (ST_Roto node, tiny, CUDA) on one format / resolution case, scored.

  Nuke17.1.exe --nc -t research/probes/2026-11-17_formats/probe_formats.py <case>
cases: make_formats.py cases + dpx10 (written by Nuke from the PNG source first).
Writes out/result_<case>.json: status, pixel sizes the tracker received, IoU of each key vs the truth at the
plate's size, and IoU of the node's own Roto render (frame 2) vs the truth (output coordinate mapping).
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


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def main(case):
    import time
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto import views
    from st_roto.geometry import Anchor, rasterize_spline
    res = {"case": case, "nuke": nuke.NUKE_VERSION_STRING}
    if case == "dpx10":
        os.makedirs(OUT + "/dpx10", exist_ok=True)
        src_png = nuke.nodes.Read(file=OUT + "/png16/frame_####.png", first=0, last=5)
        wd = nuke.nodes.Write(inputs=[src_png], file=OUT + "/dpx10/frame_####.dpx", file_type="dpx")
        wd["datatype"].setValue("10 bit")
        nuke.execute(wd, 0, 5)
        import shutil
        for f in range(6):
            shutil.copyfile(OUT + "/png16/gt_%04d.png" % f, OUT + "/dpx10/gt_%04d.png" % f)
        meta = dict(json.load(open(OUT + "/png16/case.json")), ext="dpx", kind="dpx10 (Nuke)")
        json.dump(meta, open(OUT + "/dpx10/case.json", "w"))
    meta = json.load(open("%s/%s/case.json" % (OUT, case)))
    W, H, n = meta["width"], meta["height"], meta["frames"]
    rd = nuke.nodes.Read(file="%s/%s/frame_####.%s" % (OUT, case, meta["ext"]), first=0, last=n - 1)
    if case == "anamorphic":
        nuke.addFormat("1280 720 0 0 1280 720 2.0 st_anamorphic_test")
        rd["format"].setValue("st_anamorphic_test")
    res["read_format"] = {"w": rd.format().width(), "h": rd.format().height(),
                          "pixel_aspect": rd.format().pixelAspect()}
    try:
        res["read_bitdepth"] = rd.metadata().get("input/bitsperchannel") or rd.metadata().get("dpx/bit_depth")
    except Exception:
        res["read_bitdepth"] = None
    proj = os.path.join(tempfile.mkdtemp(), "fmt.stroto")
    g = stnode.create(rd, proj)
    cx, cy = meta["click_xy"]
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([cx, H - cy]); stnode.on_add_point(g, 1)
    t0 = time.time()
    job = stnode.on_track(g, background=False)
    res["track_seconds"] = round(time.time() - t0, 1)
    res["status"] = g["stroto_status"].value()
    res["job_status"] = job.status if job else None
    res["job_error"] = (job.error or "")[-600:] if job else None
    store, _ = session.project(proj)
    scores = {}
    try:
        shot = store.conn.execute("SELECT * FROM shots").fetchone()
        res["shot_size"] = [shot["width"], shot["height"]] if shot else None
        oid = store.objects(shot["id"])[0]["id"]
        sid = views.main_shape(store, oid)["id"]
        for k in store.keys(sid):
            a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False)
                 for p in k["points"]]
            gt = cv2.imread("%s/%s/gt_%04d.png" % (OUT, case, k["frame"]), cv2.IMREAD_GRAYSCALE) > 127
            scores[k["frame"]] = round(iou(rasterize_spline(a, H, W), gt), 4)
    except Exception:
        res["score_error"] = traceback.format_exc()[-800:]
    res["key_iou"] = scores
    # output mapping: render the node's own Roto (alpha) on frame 2 through Nuke and compare with the truth
    try:
        w = nuke.nodes.Write(inputs=[g], file=OUT + "/roto_%s.####.tif" % case, file_type="tiff", channels="alpha")
        w["datatype"].setValue("32 bit float"); w["compression"].setValue("none")
        nuke.execute(w, 2, 2)
        img = cv2.imread(OUT + "/roto_%s.0002.tif" % case, cv2.IMREAD_UNCHANGED)
        a = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        gt = cv2.imread("%s/%s/gt_0002.png" % (OUT, case), cv2.IMREAD_GRAYSCALE) > 127
        res["roto_render_size"] = [a.shape[1], a.shape[0]]
        res["roto_render_iou_f2"] = round(iou(a, gt), 4) if a.shape == gt.shape else None
    except Exception as e:
        res["roto_render_error"] = str(e)[:300]
    return res


if __name__ == "__main__":
    case = sys.argv[1]
    try:
        r = main(case)
    except Exception:
        r = {"case": case, "exception": traceback.format_exc()}
    json.dump(r, open("%s/result_%s.json" % (OUT, case), "w"), indent=1, default=str)
    print("done", case)
