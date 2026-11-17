"""T-113 probe: can Nuke 17.1's bundled USD write Alembic? (pxr present? 'abc' file format plugin (usdAbc)?)
Writes an animated cubic-Bezier BasisCurves prim to .abc through USD, reads it back with USD, and (headless) with
Nuke's ReadGeo / GeoImport to see whether Nuke reads it.
Run: Nuke17.1.exe --nc -t probe_usd_abc.py -> result_usd_abc.json"""
import json
import os
import sys
import traceback

import nuke

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
R = {}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception:                                         # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", str(R[name])[:400])


attempt("pxr_import", lambda: __import__("pxr").__file__)


def formats():
    from pxr import Sdf
    return {ext: (Sdf.FileFormat.FindByExtension(ext) is not None) for ext in ("usd", "usda", "usdc", "abc")}


attempt("file_formats", formats)
attempt("usd_version", lambda: __import__("pxr.Usd", fromlist=["Usd"]).GetVersion())


def write_abc():
    from pxr import Usd, UsdGeom, Gf, Vt, Sdf
    path = OUT + "/curves.abc"
    if os.path.exists(path):
        os.remove(path)
    stage = Usd.Stage.CreateInMemory()
    stage.SetStartTimeCode(1); stage.SetEndTimeCode(3)
    stage.SetTimeCodesPerSecond(24); stage.SetFramesPerSecond(24)
    UsdGeom.Xform.Define(stage, "/stroto")
    c = UsdGeom.BasisCurves.Define(stage, "/stroto/hero")
    c.CreateTypeAttr(UsdGeom.Tokens.cubic)
    c.CreateBasisAttr(UsdGeom.Tokens.bezier)
    c.CreateWrapAttr(UsdGeom.Tokens.periodic)
    # one closed curve of 4 anchors: periodic bezier needs 3 * anchors points
    for t in (1, 2, 3):
        pts = []
        for i, (x, y) in enumerate(((0, 0), (10, 0), (10, 10), (0, 10))):
            pts += [Gf.Vec3f(x + t, y, 0), Gf.Vec3f(x + t + 2, y, 0), Gf.Vec3f(x + t + 3, y + 1, 0)]
        c.GetPointsAttr().Set(Vt.Vec3fArray(pts), t)
    c.CreateCurveVertexCountsAttr(Vt.IntArray([12]))
    stage.GetRootLayer().Export(path)
    st2 = Usd.Stage.Open(path)
    out = {"size": os.path.getsize(path), "magic": open(path, "rb").read(16).hex(),
           "prims": [(str(p.GetPath()), str(p.GetTypeName())) for p in st2.Traverse()],
           "start_end_tps": [st2.GetStartTimeCode(), st2.GetEndTimeCode(), st2.GetTimeCodesPerSecond()]}
    for p in st2.Traverse():
        if p.GetTypeName() == "BasisCurves":
            cc = UsdGeom.BasisCurves(p)
            pa = cc.GetPointsAttr()
            ts = list(pa.GetTimeSamples())
            out["curve"] = {"path": str(p.GetPath()), "basis": str(cc.GetBasisAttr().Get()),
                            "type": str(cc.GetTypeAttr().Get()), "wrap": str(cc.GetWrapAttr().Get()),
                            "samples": ts, "counts": list(cc.GetCurveVertexCountsAttr().Get() or []),
                            "counts_at_1": list(cc.GetCurveVertexCountsAttr().Get(1) or []),
                            "counts_samples": list(cc.GetCurveVertexCountsAttr().GetTimeSamples()),
                            "first_point_each_sample": [list(pa.Get(t)[0]) if pa.Get(t) else None for t in ts],
                            "n_points": [len(pa.Get(t)) if pa.Get(t) else None for t in ts],
                            "attrs": [a.GetName() for a in p.GetAttributes()][:30]}
    return out


attempt("write_abc", write_abc)


def nuke_reads():
    out = {}
    for cls in ("ReadGeo2", "ReadGeo", "GeoImport"):
        try:
            n = getattr(nuke.nodes, cls)()
            ks = n.knobs()
            fk = "file" if "file" in ks else None
            out[cls] = {"created": True, "file_knob": fk}
            if fk:
                n[fk].setValue(OUT + "/curves.abc")
                out[cls]["error"] = n.hasError() if hasattr(n, "hasError") else None
                for k in ("scene_view", "object_type", "frame_rate"):
                    if k in ks:
                        try:
                            out[cls][k] = str(n[k].value())[:200]
                        except Exception as e:             # noqa: BLE001
                            out[cls][k] = str(e)
        except Exception as e:                            # noqa: BLE001
            out[cls] = "ERROR %s" % e
    return out


attempt("nuke_read_nodes", nuke_reads)


def readgeo_details():
    n = nuke.nodes.ReadGeo2(file=OUT + "/curves.abc")
    out = {"knobs": sorted(k for k in n.knobs() if not k.startswith("_"))[:120]}
    for k in n.knobs():
        if any(s in k.lower() for s in ("scene", "item", "object", "abc", "frame")):
            try:
                out["k_" + k] = str(n[k].value())[:300]
            except Exception as e:                            # noqa: BLE001
                out["k_" + k] = "ERR %s" % e
    try:
        out["scene_view_items"] = n["scene_view"].getAllItems() if "scene_view" in n.knobs() else None
        out["scene_view_selected"] = n["scene_view"].getSelectedItems() if "scene_view" in n.knobs() else None
    except Exception as e:                                    # noqa: BLE001
        out["scene_view_err"] = str(e)
    return out


attempt("readgeo2_details", readgeo_details)
json.dump(R, open(HERE + "/result_usd_abc.json", "w"), indent=1, default=str)
