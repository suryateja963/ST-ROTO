"""T-111 probe (headless): Roto shape overlay-colour attributes - names, defaults, per-frame animation, save/reopen.
Run: Nuke17.1.exe --nc -t probe_overlay_attrs.py save ; then ... load  -> result_overlay_attrs_<mode>.json"""
import json
import os
import sys
import traceback

import nuke
import nuke.rotopaint as rp

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else "save"
R = {"mode": MODE}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception:                                         # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", str(R[name])[:500])


A = rp.AnimAttributes
NAMES = {k: getattr(A, k) for k in dir(A) if k.startswith("k") and "Overlay" in k}
R["overlay_attribute_names"] = NAMES
if MODE == "save":
    ro = nuke.nodes.Roto(name="rt")
    s = rp.Shape(ro["curves"])
    s.name = "A"
    for (x, y) in ((100, 100), (300, 100), (300, 300), (100, 300)):
        s.append(rp.ShapeControlPoint(x, y))
    ro["curves"].rootLayer.append(s)
    a = s.getAttributes()
    attempt("defaults", lambda: {n: a.getValue(0, n) for n in NAMES.values()})

    def animate():
        ro_, go_, bo_ = NAMES["kRedOverlayAttribute"], NAMES["kGreenOverlayAttribute"], NAMES["kBlueOverlayAttribute"]
        for f, (r, g, b) in ((1, (0, 1, 0)), (5, (1, 1, 0)), (9, (1, 0, 0))):
            a.set(f, ro_, r); a.set(f, go_, g); a.set(f, bo_, b)
        ro["curves"].changed()
        return {f: [round(a.getValue(f, n), 3) for n in (ro_, go_, bo_)] for f in (1, 3, 5, 7, 9, 12)}

    attempt("animated_values", animate)
    attempt("keys_on_red", lambda: a.getNumberOfKeys(NAMES["kRedOverlayAttribute"]))

    def stepped():
        # constant per frame: also key the frame before each change (no interpolation between states)
        ro_ = NAMES["kRedOverlayAttribute"]
        crv = a.getCurve(ro_)
        return {"curve_type": str(type(crv)), "curve_dir": [m for m in dir(crv) if not m.startswith("_")][:40]}

    attempt("curve_api", stepped)
    attempt("save", lambda: (nuke.scriptSaveAs(OUT + "/overlay.nk", overwrite=1), sorted(os.listdir(OUT)))[1])
else:
    path = [OUT + "/" + f for f in os.listdir(OUT) if f.startswith("overlay.nk")][0]
    nuke.scriptOpen(path)
    s = list(nuke.toNode("rt")["curves"].rootLayer)[0]
    a = s.getAttributes()
    attempt("reloaded_values", lambda: {f: [round(a.getValue(f, n), 3) for n in
                                            (NAMES["kRedOverlayAttribute"], NAMES["kGreenOverlayAttribute"],
                                             NAMES["kBlueOverlayAttribute"])] for f in (1, 5, 9)})
json.dump(R, open(HERE + "/result_overlay_attrs_%s.json" % MODE, "w"), indent=1, default=str)
