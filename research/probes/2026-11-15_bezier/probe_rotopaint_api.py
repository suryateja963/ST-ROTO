"""Inspect nuke.rotopaint ShapeControlPoint API: how centre and tangents are stored and keyed.
Run: Nuke17.1.exe --nc -t probe_rotopaint_api.py"""
import json, os
import nuke
import nuke.rotopaint as rp

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
R = {}
cp = rp.ShapeControlPoint(100.0, 200.0)
R["ShapeControlPoint_attrs"] = [a for a in dir(cp) if not a.startswith("_")]
R["ShapeControlPoint_doc"] = (rp.ShapeControlPoint.__doc__ or "")[:1500]
R["ShapeControlPoint_init_doc"] = (rp.ShapeControlPoint.__init__.__doc__ or "")[:1500]
for name in ("center", "leftTangent", "rightTangent", "featherCenter", "featherLeftTangent", "featherRightTangent"):
    if hasattr(cp, name):
        a = getattr(cp, name)
        R[name] = {"type": type(a).__name__, "attrs": [x for x in dir(a) if not x.startswith("_")]}
        try:
            v = a.getPosition(nuke.frame())
            R[name]["pos"] = [v.x, v.y]
        except Exception as e:
            R[name]["pos_err"] = repr(e)
shape = rp.Shape(nuke.nodes.Roto()["curves"])
R["Shape_attrs"] = [a for a in dir(shape) if not a.startswith("_")]
R["CVec2_doc"] = (getattr(rp, "CVec2", None).__doc__ or "")[:600] if hasattr(rp, "CVec2") else "no rp.CVec2"
import _curvelib
R["curvelib_attrs"] = [a for a in dir(_curvelib) if not a.startswith("_")][:80]
with open(HERE + "/api.json", "w") as f:
    json.dump(R, f, indent=1)
print("DONE")
