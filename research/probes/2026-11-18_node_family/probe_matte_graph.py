"""T-112 probe: the ST_RotoMatte inner graph (product code st_roto_nuke.family.create_matte) on the CG plate
(RGB + alpha 1 + depth/vectors/N/P/Cryptomatte). Mattes = EXRs written from the truth (layers target, distractor,
combined A). Checks: before 'ready' the node passes its input through exactly; after: alpha = combined matte,
<object>.alpha layers present, plate RGB and every other plate layer unchanged; Node-object budget used.
Run: Nuke17.1.exe --nc -t probe_matte_graph.py -> result_matte_graph.json"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
from st_roto import exr  # noqa: E402

CG = ROOT + "/research/probes/2026-11-18_channels/out/cg"
OUT = HERE + "/out"
R = {}
try:
    md = OUT + "/mattes"
    os.makedirs(md, exist_ok=True)
    for f in range(24):
        t = (cv2.imread(CG + "/gt_%04d.png" % f, 0) > 127).astype(np.float32)
        d = np.zeros_like(t); cv2.circle(d, (int(787.5 - 450 * f / 23.0), int(420 - 90 * np.sin(np.pi * f / 23.0))), 64, 1, -1)
        exr.write_mattes(exr.frame_path(md, "m", f), {"target": t, "distractor": d})
    import st_roto_nuke.family as fam
    rd = nuke.nodes.Read(file=CG + "/cg.####.exr", first=0, last=23)                         # 1 object
    g = fam.create_matte(rd, "", "Read1")                                                      # expected 2
    w = nuke.nodes.Write()                                                                     # 1
    w.setInput(0, g)
    w["file_type"].setValue("exr"); w["datatype"].setValue("32 bit float"); w["channels"].setValue("all")
    src = exr.read_channels(CG + "/cg.0010.exr")

    def render(name):
        p = OUT + "/%s.exr" % name
        w["file"].setValue(p)
        nuke.execute(w, 10, 10)
        return exr.read_channels(p)

    before = render("before")
    R["before_max_diff_all"] = max(float(np.abs(before[k].astype(np.float64) - src[k].astype(np.float64)).max())
                                   for k in src)
    g["stroto_pattern"].setValue(md + "/m.####.exr")
    g["stroto_first"].setValue(0); g["stroto_last"].setValue(23); g["stroto_ready"].setValue(1)
    after = render("after")
    m = exr.read_channels(exr.frame_path(md, "m", 10))
    R["after_channels"] = sorted(after)
    R["alpha_vs_combined"] = float(np.abs(after["A"] - m["A"]).max())
    R["layers"] = {k: float(np.abs(after[k] - m[k]).max()) for k in after if k.endswith(".A") and k in m and "Crypto" not in k}
    R["plate_rgb_and_layers_diff"] = max(float(np.abs(after[k].astype(np.float64) - src[k].astype(np.float64)).max())
                                         for k in src if k != "A")
    R["budget_remaining"] = sum(1 for _ in range(20) if nuke.nodes.NoOp() is not None)
except Exception:
    R["error"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_matte_graph.json", "w"), indent=1)
print(R)
