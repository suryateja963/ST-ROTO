"""Is the observed 0.5x tangent scale real, or an artefact of animation keys (interpolating towards an implicit key)?
Circle (convention A, textbook kappa handles). Variants:
  key_cur      : tangent keyed only at nuke.frame()
  key_range    : tangent keyed at frames 0..10 (constant)
  key_cur_x2   : keyed only at nuke.frame(), values doubled
  center_keyed : centre ALSO explicitly keyed at frames 0..10, tangents keyed 0..10
Rendered at frames 1 and 5. Run: Nuke17.1.exe --nc -t probe_tangent_keys.py"""
import json, math, os, sys
import nuke
import nuke.rotopaint as rp

ROOT = "D:/ST-ROTO"
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out"
nuke.root()["format"].setValue("HD_1080")
W, H, CX, CY, RAD, K = 1920, 1080, 960.0, 540.0, 400.0, 0.5522847498
yy, xx = np.mgrid[0:H, 0:W]
ideal = ((xx + 0.5 - CX) ** 2 + ((H - yy - 0.5) - CY) ** 2) <= RAD ** 2
roto = nuke.nodes.Roto(output="alpha")
w = nuke.nodes.Write(file=OUT + "/keys.####.tif", file_type="tiff", channels="alpha")
w["datatype"].setValue("32 bit float"); w["compression"].setValue("none")
w.setInput(0, roto)
R = {"nuke_frame": nuke.frame(), "root_first": nuke.root().firstFrame(), "root_last": nuke.root().lastFrame()}


def build(variant):
    curves = roto["curves"]
    for i in reversed(range(len(curves.rootLayer))):
        curves.rootLayer.remove(i)
    sh = rp.Shape(curves)
    frames = [nuke.frame()] if variant in ("key_cur", "key_cur_x2") else list(range(0, 11))
    mul = 2.0 if variant == "key_cur_x2" else 1.0
    for a in (0, 90, 180, 270):
        t = math.radians(a)
        px, py = CX + RAD * math.cos(t), CY + RAD * math.sin(t)
        d = (-math.sin(t), math.cos(t))
        nxt = (d[0] * K * RAD * mul, d[1] * K * RAD * mul)
        cp = rp.ShapeControlPoint(px, py)
        for fr in frames:
            if variant == "center_keyed":
                cp.center.addPositionKey(fr, rp.CVec2(px, py))
            cp.leftTangent.addPositionKey(fr, rp.CVec2(-nxt[0], -nxt[1]))
            cp.rightTangent.addPositionKey(fr, rp.CVec2(*nxt))
        sh.append(cp)
    curves.rootLayer.append(sh)
    res = {}
    for fr in (1, 5):
        nuke.execute(w, fr, fr)
        img = cv2.imread(OUT + "/keys.%04d.tif" % fr, cv2.IMREAD_UNCHANGED)
        img = img if img.ndim == 2 else img[:, :, -1]
        m = img > 0.5
        res["frame%d" % fr] = {"iou": round(float((m & ideal).sum() / (m | ideal).sum()), 5),
                               "area_ratio": round(float(m.sum() / ideal.sum()), 4)}
    lt = sh[0].leftTangent
    res["left_key_times"] = list(lt.getControlPointKeyTimes()) if hasattr(lt, "getControlPointKeyTimes") else None
    return res


for v in ("key_cur", "key_range", "key_cur_x2", "center_keyed"):
    R[v] = build(v)
with open(HERE + "/result_tangent_keys.json", "w") as fh:
    json.dump(R, fh, indent=1, default=str)
print("DONE")
