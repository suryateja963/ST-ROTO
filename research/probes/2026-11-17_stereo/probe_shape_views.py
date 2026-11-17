"""T-109 probe 2: restricting a Roto shape to one view (attributes nv / view1..n), and per-view pixel renders.
Run: Nuke17.1.exe --nc -t probe_shape_views.py -> result_shape_views.json"""
import json
import os
import sys
import traceback

sys.path.append("D:/ST-ROTO/.tools/nuke-py311")
import nuke
import nuke.rotopaint as rp
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out/probe"
os.makedirs(OUT, exist_ok=True)
R = {}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception:                                         # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", str(R[name])[:300])


root = nuke.root()
root["views"].fromScript("left #ff0000\nright #00ff00")
read = nuke.nodes.Read(file=HERE + "/out/stereo/%V/frame_####.png", first=0, last=47)
w = nuke.nodes.Write(name="px")
w["file_type"].setValue("tiff")
w["datatype"].setValue("32 bit float")


def render(node, view, frame, path, channels="rgb"):
    w.setInput(0, node)
    w["channels"].setValue(channels)
    w["file"].setValue(path)
    nuke.execute(w, frame, frame, 1, views=[view])
    return cv2.imread(path, cv2.IMREAD_UNCHANGED)


def per_view():
    out = {}
    for v in ("left", "right"):
        img = render(read, v, 10, OUT + "/px_%s.tif" % v)
        for ref_v in ("left", "right"):
            ref = cv2.imread(HERE + "/out/stereo/%s/frame_0010.png" % ref_v).astype(np.float32) / 255.0
            out["%s_vs_%s_png" % (v, ref_v)] = float(np.abs(img - ref).max())
    return out


attempt("per_view_render", per_view)
attempt("same_path_written_twice_ok", lambda: [render(read, v, 11, OUT + "/px_same.tif").shape for v in ("left", "right")])
attempt("set_doc", lambda: rp.AnimAttributes.set.__doc__)
attempt("getValue_doc", lambda: rp.AnimAttributes.getValue.__doc__)

roto = nuke.nodes.Roto(name="rt")
roto.setInput(0, read)
curves = roto["curves"]


def make_shape(name, x0):
    s = rp.Shape(curves)
    s.name = name
    for (x, y) in ((x0, 200), (x0 + 200, 200), (x0 + 200, 400), (x0, 400)):
        s.append(rp.ShapeControlPoint(x, y))
    curves.rootLayer.append(s)
    return s


sa, sb, sc = make_shape("A", 100), make_shape("B", 700), make_shape("C", 400)


def alpha(view):
    img = render(roto, view, 10, OUT + "/alpha.tif", "rgba")
    a = img[:, :, 3]
    return {"A(100-300)": float(a[:, 100:300].sum()), "C(400-600)": float(a[:, 400:600].sum()),
            "B(700-900)": float(a[:, 700:900].sum())}


def restrict_a():
    a = sa.getAttributes()
    a.set("nv", 1)
    a.set("view1", 1)
    curves.changed()
    return [l.strip() for l in curves.toScript().splitlines() if " nv " in l]


def restrict_b():
    b = sb.getAttributes()
    b.set(0, "nv", 1)            # try the (time, name, value) form
    b.set(0, "view1", 2)
    curves.changed()
    return [l.strip() for l in curves.toScript().splitlines() if " nv " in l]


attempt("restrict_A_set_name_value", restrict_a)
attempt("restrict_B_set_time_name_value", restrict_b)
attempt("alpha_left", lambda: alpha("left"))
attempt("alpha_right", lambda: alpha("right"))
attempt("serialise_A", lambda: sa.serialise()[:400] if hasattr(sa, "serialise") else None)
json.dump(R, open(HERE + "/result_shape_views.json", "w"), indent=1, default=str)
print("done")
