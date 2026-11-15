"""Why does a keyframed (animated) Roto shape render empty? Test variants on a square that moves per frame.
Run: Nuke17.1.exe --nc -t probe_anim_keys.py   (2 nodes, reused)"""
import json, os, sys
import nuke
import nuke.rotopaint as rp
sys.path.append("D:/ST-ROTO/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out"
nuke.root()["format"].setValue("HD_720")
roto = nuke.nodes.Roto(output="alpha")
w = nuke.nodes.Write(file=OUT + "/anim.####.tif", file_type="tiff", channels="alpha")
w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, roto)
R = {}


def square(f):
    x0 = 200 + 40 * f
    return [(x0, 200), (x0 + 300, 200), (x0 + 300, 500), (x0, 500)]


def run(variant):
    curves = roto["curves"]
    for i in reversed(range(len(curves.rootLayer))):
        curves.rootLayer.remove(i)
    shape = rp.Shape(curves)
    if variant == "ctor_first_frame_then_keys":
        cps = [rp.ShapeControlPoint(x, y) for x, y in square(0)]
    else:
        cps = [rp.ShapeControlPoint(0.0, 0.0) for _ in range(4)]
    if variant == "append_layer_before_keys":
        for cp in cps:
            shape.append(cp)
        curves.rootLayer.append(shape)
    else:
        for cp in cps:
            shape.append(cp)
    for f in range(0, 4):
        for cp, (x, y) in zip(cps, square(f)):
            cp.center.addPositionKey(f, rp.CVec2(float(x), float(y)))
    if variant != "append_layer_before_keys":
        curves.rootLayer.append(shape)
    if variant == "keys_via_shape_index":
        pass
    nuke.execute(w, 0, 3)
    res = {}
    for f in range(0, 4):
        img = cv2.imread(OUT + "/anim.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        a = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        ys, xs = np.nonzero(a)
        res[f] = {"area": int(a.sum()), "xmin": int(xs.min()) if len(xs) else None}
    k0 = shape[0].center
    res["key_times_point0"] = list(k0.getControlPointKeyTimes())
    res["pos_point0_f2"] = [k0.getPosition(2).x, k0.getPosition(2).y]
    return res


for v in ("ctor_zero_then_keys", "ctor_first_frame_then_keys", "append_layer_before_keys"):
    try:
        R[v] = run(v)
    except Exception as e:
        R[v] = {"error": repr(e)}
with open(HERE + "/result_anim_keys.json", "w") as fh:
    json.dump(R, fh, indent=1, default=str)
print("DONE")
