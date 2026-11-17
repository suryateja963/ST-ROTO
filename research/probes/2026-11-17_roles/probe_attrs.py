"""T-098: which Roto shape attribute names exist (getValue works) and which change the render. Headless."""
import json, os, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
import nuke, nuke.rotopaint as rp
R = {}
try:
    c = nuke.nodes.Constant()
    roto = nuke.nodes.Roto(inputs=[c], output="alpha")
    curves = roto["curves"]
    s = rp.Shape(curves)
    for x, y in ((10, 10), (100, 10), (100, 90), (10, 90)):
        s.append(rp.ShapeControlPoint(x, y))
    curves.rootLayer.append(s)
    a = s.getAttributes()
    R["dir"] = [d for d in dir(a) if not d.startswith("_")]
    found = {}
    for name in ("bm", "inv", "opc", "fx", "fy", "ff", "ro", "go", "bo", "ao", "str", "ltt", "ltn", "ltm", "mbo",
                 "mbs", "src", "vis", "invert", "blendMode", "blending_mode", "nv", "view", "fbe", "cr", "cg", "cb", "ca"):
        try:
            found[name] = a.getValue(1, name)
        except Exception as e:
            pass
    R["getValue_ok"] = found
    try:
        R["keys_via_iter"] = [str(k) for k in a]
    except Exception as e:
        R["iter_error"] = str(e)
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_attrs.json", "w"), indent=1, default=str)
