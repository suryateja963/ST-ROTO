"""T-109 probe 3: does a shape's view restriction (nv/view1) survive save + reopen? Also: what getValue reports for
unrestricted shapes, and whether animated keys keep working on a restricted shape.
Run twice:  Nuke17.1.exe --nc -t probe_view_persist.py save   then   ... probe_view_persist.py load
-> result_view_persist_<mode>.json"""
import json
import os
import sys
import traceback

sys.path.append("D:/ST-ROTO/.tools/nuke-py311")
import nuke
import nuke.rotopaint as rp
import cv2

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out/probe"
os.makedirs(OUT, exist_ok=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else "save"
SCRIPT = OUT + "/persist.nk"
R = {"mode": MODE}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception:                                         # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", str(R[name])[:300])


if MODE == "save":
    nuke.root()["views"].fromScript("left #ff0000\nright #00ff00")
    read = nuke.nodes.Read(file=HERE + "/out/stereo/%V/frame_####.png", first=0, last=47)
    roto = nuke.nodes.Roto(name="rt")
    roto.setInput(0, read)
    curves = roto["curves"]
    for name, x0, view in (("A", 100, 1), ("B", 700, 2), ("C", 400, None)):
        s = rp.Shape(curves)
        s.name = name
        for (x, y) in ((x0, 200), (x0 + 200, 200), (x0 + 200, 400), (x0, 400)):
            p = rp.ShapeControlPoint(x, y)
            p.center.addPositionKey(10, (x, y))
            p.center.addPositionKey(20, (x + 50, y))
            s.append(p)
        curves.rootLayer.append(s)
        if view:
            a = s.getAttributes()
            a.set("nv", 1)
            a.set("view1", view)
    w = nuke.nodes.Write(name="px")
    w.setInput(0, roto)
    attempt("saved", lambda: (nuke.scriptSaveAs(SCRIPT, overwrite=1), os.listdir(OUT))[1])
else:
    path = SCRIPT if os.path.exists(SCRIPT) else SCRIPT + "nc"
    if not os.path.exists(path):
        cands = [f for f in os.listdir(OUT) if f.startswith("persist")]
        path = OUT + "/" + cands[0]
    nuke.scriptOpen(path)
    R["opened"] = path
    roto = nuke.toNode("rt")
    w = nuke.toNode("px")
    curves = roto["curves"]
    attempt("attrs", lambda: {s.name: [s.getAttributes().getValue(0, "nv"), s.getAttributes().getValue(0, "view1"),
                                       s.getAttributes().getValue(0, "view2")] for s in curves.rootLayer})
    w["file_type"].setValue("tiff")
    w["datatype"].setValue("32 bit float")
    w["channels"].setValue("rgba")

    def alpha(view, frame):
        p = OUT + "/persist_alpha.tif"
        w["file"].setValue(p)
        nuke.execute(w, frame, frame, 1, views=[view])
        a = cv2.imread(p, cv2.IMREAD_UNCHANGED)[:, :, 3]
        return {"A": float(a[:, 100:350].sum()), "C": float(a[:, 400:650].sum()), "B": float(a[:, 700:950].sum())}

    attempt("alpha", lambda: {"%s@%d" % (v, f): alpha(v, f) for v in ("left", "right") for f in (10, 20)})
json.dump(R, open(HERE + "/result_view_persist_%s.json" % MODE, "w"), indent=1, default=str)
print("done")
