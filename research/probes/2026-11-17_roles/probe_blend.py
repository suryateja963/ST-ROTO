"""T-098: how Nuke 17.1's Roto combines shapes (blend modes, order), to make holdout / garbage objects render in
Nuke exactly like ST-ROTO's EXR combine. Headless: Nuke17.1.exe --nc -t probe_blend.py -> result_blend.json"""
import json, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                           # noqa: E402
import nuke.rotopaint as rp                           # noqa: E402
import numpy as np                                    # noqa: E402
import cv2                                            # noqa: E402

R = {}
W, H = 200, 100


def rect(curves, name, x0, y0, x1, y1):
    s = rp.Shape(curves)
    s.name = name
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        p = rp.ShapeControlPoint(x, y)
        s.append(p)
    return s


def render(node, tag):
    w = nuke.nodes.Write(inputs=[node], file=HERE + "/out_%s.tif" % tag, file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none")
    nuke.execute(w, 1, 1)
    img = cv2.imread(HERE + "/out_%s.tif" % tag, cv2.IMREAD_UNCHANGED)
    a = img if img.ndim == 2 else img[:, :, -1]
    return a[::-1]                                     # -> y-up rows to match Nuke coordinates


try:
    nuke.addFormat("%d %d 1 probe_fmt" % (W, H)); nuke.root()["format"].setValue("probe_fmt")
    c = nuke.nodes.Constant(); c["format"].setValue("probe_fmt")
    roto = nuke.nodes.Roto(inputs=[c], output="alpha")
    curves = roto["curves"]
    a = rect(curves, "A", 10, 10, 110, 90)             # big
    b = rect(curves, "B", 60, 30, 160, 70)             # overlaps A on x 60-110
    curves.rootLayer.append(b); curves.rootLayer.append(a)        # B FIRST = on top (measured order, 1st run)
    attrs = b.getAttributes()
    BM, INV = attrs.kBlendingModeAttribute, attrs.kInvertedAttribute
    R["attribute_names"] = {"blending": BM, "inverted": INV}
    base = render(roto, "base")
    R["base"] = {"in_A_only": float(base[50, 30]), "overlap": float(base[50, 80]), "in_B_only": float(base[50, 140])}
    for mode in range(0, 20):
        try:
            attrs.set(BM, float(mode))
            curves.changed()
        except Exception as e:
            R["bm_error"] = str(e); break
        r = render(roto, "bm%d" % mode)
        R["bm_%d" % mode] = {"A_only": round(float(r[50, 30]), 3), "overlap": round(float(r[50, 80]), 3),
                             "B_only": round(float(r[50, 140]), 3), "outside": round(float(r[5, 190]), 3)}
    for mode in (0, 2, 3, 4, 10, 15, 16):
        attrs.set(BM, float(mode)); attrs.set(INV, 1.0); curves.changed()
        r = render(roto, "inv%d" % mode)
        R["inv_bm_%d" % mode] = {"A_only": round(float(r[50, 30]), 3), "overlap": round(float(r[50, 80]), 3),
                                 "B_only": round(float(r[50, 140]), 3), "outside": round(float(r[5, 190]), 3)}
    attrs.set(BM, 0.0)
    attrs.set(INV, 1.0)
    curves.changed()
    r = render(roto, "inv")
    R["inverted_B"] = {"A_only": float(r[50, 30]), "overlap": float(r[50, 80]), "B_only": float(r[50, 140]),
                       "outside_both": float(r[5, 190])}
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_blend.json", "w"), indent=1)
