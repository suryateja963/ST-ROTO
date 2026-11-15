"""Determine how Nuke Roto tangents map to cubic Bezier handles, using an exact 4-point circle.

A circle of radius r drawn with 4 cubic Beziers needs handles of length k*r, k = 0.5523 (standard kappa),
along the tangent direction. We render variants and compare with the ideal disk:
  convention A: leftTangent = handle toward PREVIOUS point, rightTangent = toward NEXT point
  convention B: swapped
  scale s: tangent vector = s * (handle - centre)
Order is counter-clockwise in Nuke coordinates; a clockwise order is also tested.
Run: Nuke17.1.exe --nc -t probe_tangent_semantics.py   (2 nodes: one Roto + one Write, reused)
"""
import json, math, os, sys
import nuke
import nuke.rotopaint as rp

ROOT = "D:/ST-ROTO"
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
nuke.root()["format"].setValue("HD_1080")
W, H, CX, CY, RAD, K = 1920, 1080, 960.0, 540.0, 400.0, 0.5522847498
f = nuke.frame()

# ideal disk in Nuke pixel space (row 0 = top in the file, y up in Nuke)
yy, xx = np.mgrid[0:H, 0:W]
ideal = ((xx + 0.5 - CX) ** 2 + ((H - yy - 0.5) - CY) ** 2) <= RAD ** 2

roto = nuke.nodes.Roto(output="alpha")
w = nuke.nodes.Write(file=OUT + "/sem.tif", file_type="tiff", channels="alpha")
w["datatype"].setValue("32 bit float"); w["compression"].setValue("none")
w.setInput(0, roto)


def render(convention, scale, ccw):
    curves = roto["curves"]
    for i in reversed(range(len(curves.rootLayer))):      # Layer.remove() takes an index
        curves.rootLayer.remove(i)
    angles = [0, 90, 180, 270] if ccw else [0, 270, 180, 90]
    sh = rp.Shape(curves)
    for a in angles:
        t = math.radians(a)
        px, py = CX + RAD * math.cos(t), CY + RAD * math.sin(t)
        d = (-math.sin(t), math.cos(t)) if ccw else (math.sin(t), -math.cos(t))   # direction of travel
        nxt = (d[0] * K * RAD * scale, d[1] * K * RAD * scale)
        prv = (-nxt[0], -nxt[1])
        left, right = (prv, nxt) if convention == "A" else (nxt, prv)
        cp = rp.ShapeControlPoint(px, py)
        cp.leftTangent.addPositionKey(f, rp.CVec2(*left))
        cp.rightTangent.addPositionKey(f, rp.CVec2(*right))
        sh.append(cp)
    curves.rootLayer.append(sh)
    nuke.execute(w, 1, 1)
    img = cv2.imread(OUT + "/sem.tif", cv2.IMREAD_UNCHANGED)
    img = img if img.ndim == 2 else img[:, :, -1]
    m = img > 0.5
    return {"iou_vs_ideal": round(float((m & ideal).sum() / max(1, (m | ideal).sum())), 5),
            "area_ratio": round(float(m.sum() / ideal.sum()), 4)}


R = {}
for conv in ("A", "B"):
    for ccw in (True, False):
        for s in (1 / 3, 1.0, 3.0):
            R[f"{conv}_{'ccw' if ccw else 'cw'}_scale{round(s, 3)}"] = render(conv, s, ccw)
R["nodes_used"] = len(nuke.allNodes())
with open(HERE + "/result_tangent_semantics.json", "w") as fh:
    json.dump(R, fh, indent=1)
print("DONE")
