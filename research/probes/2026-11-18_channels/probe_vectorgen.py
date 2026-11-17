"""T-110 probe: Nuke's motion-vector convention, measured with its own VectorGenerator on the synthetic shot whose
motion is known (2026-11-15: background pans LEFT by 300/47 = 6.38 px/frame; the target ellipse moves RIGHT by
650/47 = 13.83 px/frame and vertically by 140*sin(2*pi*s), i.e. DOWN in image rows around frame 0-11).
Run: Nuke17.1.exe --nc -t probe_vectorgen.py -> result_vectorgen.json
"""
import json
import os
import sys
import traceback

sys.path.append("D:/ST-ROTO/.tools/nuke-py311")
import nuke
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path.insert(0, ROOT + "/src")
from st_roto import exr  # noqa: E402

VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"
OUT = HERE + "/out/probe"
os.makedirs(OUT, exist_ok=True)
R = {}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception:                                         # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", str(R[name])[:400])


nuke.root()["format"].setValue("HD_720")
rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=47)
vg = nuke.nodes.VectorGenerator()
vg.setInput(0, rd)
attempt("vg_knobs", lambda: sorted(k for k in vg.knobs() if not k.startswith("_"))[:60])
attempt("vg_channels", lambda: sorted(set(c.split(".")[0] for c in vg.channels())))
w = nuke.nodes.Write()
w.setInput(0, vg)
w["file_type"].setValue("exr")
w["channels"].setValue("all")
attempt("write_channels_knob_values", lambda: w["channels"].values()[:30])
p = OUT + "/vg.exr"
w["file"].setValue(p)


def run():
    nuke.execute(w, 6, 6)
    ch = exr.read_channels(p)
    out = {"channels": sorted(ch)}
    meta = json.load(open(VIDEO + "/meta.json"))
    gt = None
    import cv2
    gt = cv2.imread(VIDEO + "/gt_0006.png", 0) > 127
    for k in ch:
        if k.startswith(("forward", "backward", "motion")):
            a = ch[k]
            bg = np.ones_like(gt)
            bg[:, :] = True
            bg[gt] = False
            bg[620:, :] = False                                    # avoid the distractor region roughly
            out[k] = {"target_median": float(np.median(a[gt])), "background_median": float(np.median(a[bg]))}
    s = 6 / 47.0
    import math
    out["truth_canonical_px_per_frame"] = {
        "target_dx": 650 / 47.0, "target_dy_rows_down": 140 * (math.sin(2 * math.pi * 7 / 47) - math.sin(2 * math.pi * 6 / 47)),
        "background_dx": -300 / 47.0, "background_dy": 0.0}
    return out


attempt("frame6", run)
json.dump(R, open(HERE + "/result_vectorgen.json", "w"), indent=1, default=str)
print("done")
