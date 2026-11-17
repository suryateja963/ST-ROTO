"""T-110 probe: a Roto node over a plate that HAS alpha (CG plate, A = 1). Default: shapes are composited over the
input alpha (output alpha 1 everywhere). With the Roto's 'replace' knob: alpha = the shapes only? Other layers
untouched? Run: Nuke17.1.exe --nc -t probe_roto_replace.py -> result_roto_replace.json"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke  # noqa: E402
import nuke.rotopaint as rp  # noqa: E402
import numpy as np  # noqa: E402
from st_roto import exr  # noqa: E402

CG = HERE + "/out/cg"
OUT = HERE + "/out/probe"
R = {}
rd = nuke.nodes.Read(file=CG + "/cg.####.exr", first=0, last=23)
ro = nuke.nodes.Roto()
ro.setInput(0, rd)
R["defaults"] = {k: ro[k].value() for k in ("output", "premultiply")}
ro["output"].setValue("alpha")
ro["premultiply"].setValue("none")
s = rp.Shape(ro["curves"])
for (x, y) in ((100, 100), (300, 100), (300, 300), (100, 300)):
    s.append(rp.ShapeControlPoint(x, y))
ro["curves"].rootLayer.append(s)
w = nuke.nodes.Write()
w.setInput(0, ro)
w["file_type"].setValue("exr"); w["datatype"].setValue("32 bit float"); w["channels"].setValue("all")
src = exr.read_channels(CG + "/cg.0010.exr")
for mode in (False, True):
    ro["replace"].setValue(mode)
    p = OUT + "/replace_%d.exr" % mode
    w["file"].setValue(p)
    nuke.execute(w, 10, 10)
    c = exr.read_channels(p)
    a = c["A"]
    inside = a[540 - 300:540 - 100, 100:300]                     # Nuke y-up: rows 240-440 from the top
    diffs = {k: float(np.abs(c[k].astype(np.float64) - src[k].astype(np.float64)).max()) for k in src if k != "A"}
    others = max(diffs.values())
    R["replace_%s" % mode] = {"alpha_mean_inside": float(inside.mean()), "alpha_mean_outside": float(a[:, 400:].mean()),
                              "max_diff_other_channels": others}
json.dump(R, open(HERE + "/result_roto_replace.json", "w"), indent=1)
print(R)
