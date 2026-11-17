"""T-109 probe: Nuke 17.1 NC stereo mechanics, measured headless.
  1. set up left/right views in the root;
  2. Read with %V renders each view through a Write (nuke.execute(..., views=[v])) -> correct per-view pixels?
  3. Roto shape attributes: which attribute restricts a shape to one view; per-view render of the Roto alpha.
Run: Nuke17.1.exe --nc -t probe_nuke_views.py   -> result_views.json
"""
import json
import os
import traceback

import sys
sys.path.append('D:/ST-ROTO/.tools/nuke-py311')
import nuke
import nuke.rotopaint as rp

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out/probe"
os.makedirs(OUT, exist_ok=True)
R = {}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception as e:                                    # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", R[name])


root = nuke.root()
attempt("views_before", lambda: nuke.views())
attempt("root_views_knob", lambda: root["views"].toScript())


def setup_views():
    # the "Set up views for stereo" equivalent: rename main -> left, add right
    root["views"].fromScript("left #ff0000\nright #00ff00")
    root["hero_view"].setValue("left") if "hero_view" in root.knobs() else None
    return nuke.views()


attempt("views_after", setup_views)
attempt("root_knobs_with_view", lambda: [k for k in root.knobs() if "view" in k.lower()])

read = nuke.nodes.Read(file=HERE + "/out/stereo/%V/frame_####.png", first=0, last=47)
attempt("read_size", lambda: (read.width(), read.height()))
w = nuke.nodes.Write(name="px")
w.setInput(0, read)
w["file_type"].setValue("tiff")
w["datatype"].setValue("32 bit float")
w["channels"].setValue("rgb")


def render_view(view, frame, path):
    import cv2
    w["file"].setValue(path)
    nuke.execute(w, frame, frame, 1, views=[view])
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    return img


def compare_views():
    import cv2
    import numpy as np
    out = {}
    for v in ("left", "right"):
        img = render_view(v, 10, OUT + "/px_%s.tif" % v)
        ref = cv2.imread(HERE + "/out/stereo/%s/frame_0010.png" % v).astype(np.float32) / 255.0
        out[v] = {"shape": list(img.shape), "max_abs_diff_vs_png": float(np.abs(img - ref).max())}
    # also: execute with no views argument -> which view is written to a path without %V?
    img = cv2.imread((lambda p: (w["file"].setValue(p), nuke.execute(w, 10, 10), p)[2])(OUT + "/px_default.tif"),
                     cv2.IMREAD_UNCHANGED)
    for v in ("left", "right"):
        ref = cv2.imread(HERE + "/out/stereo/%s/frame_0010.png" % v).astype(np.float32) / 255.0
        out["no_views_arg_vs_" + v] = float(np.abs(img - ref).max())
    return out


attempt("per_view_render", compare_views)

# ---- Roto shapes and views
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


sa = make_shape("A", 100)
sb = make_shape("B", 700)
attempt("roto_node_knobs_with_view", lambda: [k for k in roto.knobs() if "view" in k.lower()])
attempt("shape_attribute_names", lambda: sorted(sa.getAttributes().keys()) if hasattr(sa.getAttributes(), "keys")
        else str(dir(sa.getAttributes())))
attempt("shape_dir", lambda: sorted(m for m in dir(sa) if not m.startswith("_")))
attempt("attr_dir", lambda: sorted(m for m in dir(sa.getAttributes()) if not m.startswith("_")))


def attr_values():
    a = sa.getAttributes()
    out = {}
    for n in list(a.keys()) if hasattr(a, "keys") else []:
        try:
            out[n] = a.getValue(0, n)
        except Exception as e:                                # noqa: BLE001
            out[n] = "ERR %s" % e
    return out


attempt("shape_attribute_values", attr_values)

# Roto shape 'view' knob in the GUI is per-shape: try likely attribute names
CANDIDATES = ["view", "views", "vw", "viewsKnob", "shapeViews"]


def try_view_attr():
    a = sa.getAttributes()
    res = {}
    for c in CANDIDATES:
        try:
            res[c] = a.getValue(0, c)
        except Exception as e:                                # noqa: BLE001
            res[c] = "ERR %s" % str(e)[:80]
    return res


attempt("view_attr_candidates", try_view_attr)


def curves_script_snippet():
    s = curves.toScript()
    i = s.find('"A"')
    return s[:1500]


attempt("curves_toScript_head", curves_script_snippet)


_AW = {}


def alpha_sum(view, frame=10):
    import cv2
    ww = _AW.get("w")
    if ww is None:
        ww = _AW["w"] = nuke.nodes.Write(name="pa")
    ww.setInput(0, roto)
    ww["file_type"].setValue("tiff")
    ww["datatype"].setValue("32 bit float")
    ww["channels"].setValue("rgba")
    p = OUT + "/alpha_%s.tif" % view
    ww["file"].setValue(p)
    nuke.execute(ww, frame, frame, 1, views=[view])
    img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    a = img[:, :, 3]
    return {"left_half": float(a[:, :640].sum()), "right_half": float(a[:, 640:].sum())}


attempt("view_consts", lambda: (rp.AnimAttributes.kNumberOfViewsAttribute, rp.AnimAttributes.kViewAttribute))
attempt("alpha_both_views_before", lambda: {v: alpha_sum(v) for v in ("left", "right")})


def restrict():
    a, b = sa.getAttributes(), sb.getAttributes()
    a.set("nv", 1); a.set("view1", 1)
    b.set("nv", 1); b.set("view1", 2)
    return {"A": [a.getValue(0, "nv"), a.getValue(0, "view1"), a.getValue(0, "view2")],
            "B": [b.getValue(0, "nv"), b.getValue(0, "view1"), b.getValue(0, "view2")]}


attempt("restrict", restrict)
attempt("restricted_script", lambda: [l for l in curves.toScript().splitlines() if " nv " in l])
attempt("alpha_after_restrict", lambda: {v: alpha_sum(v) for v in ("left", "right")})
attempt("_unused", lambda: {v: alpha_sum(v) for v in ("left", "right")})
json.dump(R, open(HERE + "/result_views.json", "w"), indent=1, default=str)
print("done")
