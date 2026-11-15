"""Does setting one tangent of a nuke.rotopaint ShapeControlPoint change the other? Which flags exist?
Run: Nuke17.1.exe --nc -t probe_tangent_link.py"""
import json, os
import nuke
import nuke.rotopaint as rp
import _curvelib as cl

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
R = {}
f = nuke.frame()
shape = rp.Shape(nuke.nodes.Roto()["curves"])


def rb(cp):
    l, r = cp.leftTangent.getPosition(f), cp.rightTangent.getPosition(f)
    return {"left": [l.x, l.y], "right": [r.x, r.y]}


cp = rp.ShapeControlPoint(100.0, 100.0)
shape.append(cp)
cp.leftTangent.addPositionKey(f, rp.CVec2(-10.0, 2.0)); R["after_set_left"] = rb(cp)
cp.rightTangent.addPositionKey(f, rp.CVec2(30.0, 9.0)); R["after_set_right"] = rb(cp)
R["flag_types"] = [n for n in dir(cl.FlagType) if not n.startswith("_")]
R["shape_flags"] = {}
for n in R["flag_types"]:
    try:
        R["shape_flags"][n] = bool(shape.getFlag(getattr(cl.FlagType, n)))
    except Exception as e:
        R["shape_flags"][n] = repr(e)[:80]
R["attrs_sample"] = {}
try:
    attrs = shape.getAttributes()
    for k in ("bm", "fo", "ff", "tt", "ltn", "ltm", "inv", "fx", "fy", "str"):
        try:
            R["attrs_sample"][k] = attrs.getValue(f, k)
        except Exception as e:
            R["attrs_sample"][k] = repr(e)[:60]
except Exception as e:
    R["attrs_err"] = repr(e)
R["serialise_head"] = shape.serialise()[:600] if hasattr(shape, "serialise") else None
with open(HERE + "/result_tangent_link.json", "w") as fh:
    json.dump(R, fh, indent=1, default=str)
print("DONE")
