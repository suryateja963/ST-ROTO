"""T-073: what does Nuke's Roto shape feather (attributes fx/fy, falloff ff) render? A 16-point circle of radius
200 at (640, 360), rendered with fx=fy in {0, 10, 25} and ff in {1, 2}; alpha sampled along a horizontal line
through the centre, as a function of signed distance to the shape edge (negative = inside).
Run: Nuke17.1.exe --nc -t research/probes/2026-11-16_feather/probe_feather_profile.py"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np                         # noqa: E402
import cv2                                 # noqa: E402
import nuke                                # noqa: E402
import nuke.rotopaint as rp                # noqa: E402
from st_roto.geometry import mask_to_points   # noqa: E402
from st_roto_nuke.roto_export import build_shape   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out").replace("\\", "/")
os.makedirs(OUT, exist_ok=True)
W, H = 1280, 720
nuke.root()["format"].setValue("HD_720")
yy, xx = np.mgrid[0:H, 0:W] + 0.5
pts = mask_to_points(200.0 - np.hypot(xx - 640, yy - 360), count=16)
roto = nuke.nodes.Roto(output="alpha")
c = roto["curves"]
sh = build_shape(c, "disc", {1: pts}, H)
c.rootLayer.append(sh)
w = nuke.nodes.Write(file=OUT + "/f.####.tif", file_type="tiff", channels="alpha")
w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, roto)
res = {}
for fx in (0.0, 10.0, 25.0):
    for ff in (1.0, 2.0):
        a = sh.getAttributes()
        a.set(1, "fx", fx); a.set(1, "fy", fx); a.set(1, "ff", ff)
        c.changed()
        nuke.execute(w, 1, 1)
        img = cv2.imread(OUT + "/f.0001.tif", cv2.IMREAD_UNCHANGED)
        al = img if img.ndim == 2 else img[:, :, -1]
        row = al[360, 640:]                         # from the centre to the right
        d = (np.arange(len(row)) + 0.5) - 200.0      # signed distance to the edge (x = 640 + 200)
        sel = (d > -40) & (d < 40)
        res["fx%g_ff%g" % (fx, ff)] = {"d": [round(float(v), 1) for v in d[sel][::2]],
                                       "alpha": [round(float(v), 4) for v in row[sel][::2]],
                                       "area": round(float(al.sum()), 1)}
        print("fx", fx, "ff", ff, "area", res["fx%g_ff%g" % (fx, ff)]["area"],
              "alpha at d=-10,0,+5,+10,+20:",
              [round(float(row[int(200 + k)]), 3) for k in (-10, 0, 5, 10, 20)], flush=True)
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json"), "w"), indent=1)
