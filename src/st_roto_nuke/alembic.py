"""Alembic export of a shot's shapes (T-113, REQ-180 'Alembic where suitable').

Written through the USD library bundled with Nuke (pxr 0.25.8 in Nuke 17.1, measured: its Alembic file-format plugin
usdAbc writes genuine Ogawa .abc files). No extra dependency; available wherever Nuke ships USD (Nuke 14+; older
Nuke: the export reports that it is unavailable).

Layout (st_roto.geomexport has the coordinates: pixel units, y up, origin bottom-left, z = 0):
    /st_roto/<object>/<shape>_curve   BasisCurves, cubic bezier, periodic (the exact spline, 3 points per anchor)
    /st_roto/<object>/<shape>_mesh    Mesh, one polygon of the outline (for readers without curves, e.g. Nuke)
One time sample per keyed frame (time code = frame number, the script's fps); frames where a part shape is
collapsed (piece absent, T-049) are invisible. Alembic stores every prim as an Xform with a shape child
(usdAbc maps /a/b_curve to /a/b_curve/b_curveShape when read back - measured).
"""
from __future__ import annotations

import os

from st_roto import geomexport as ge
from st_roto.pieces import is_collapsed


def available() -> str:
    """'' if Alembic can be written here, else the reason."""
    try:
        from pxr import Sdf
    except Exception as e:                                    # noqa: BLE001
        return "this Nuke has no USD library (pxr): %s" % e
    if Sdf.FileFormat.FindByExtension("abc") is None:
        return "this Nuke's USD has no Alembic plug-in (usdAbc)"
    return ""


def write_shot(store, shot_id: str, path: str, fps: float = 24.0, per_segment: int = 16) -> dict:
    """Write every object / shape of the shot. Returns {"path", "prims": {prim path: (object, shape)}, "frames"}."""
    why = available()
    if why:
        raise RuntimeError(why)
    from pxr import Usd, UsdGeom, Vt, Gf
    shot = store.row("shots", shot_id)
    if shot is None:
        raise ValueError("no shot %s" % shot_id)
    h = float(shot["height"])
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    stage.SetTimeCodesPerSecond(float(fps))
    stage.SetFramesPerSecond(float(fps))
    UsdGeom.Xform.Define(stage, "/st_roto")
    prims, used, all_frames = {}, set(), set()
    for o in store.objects(shot_id):
        base = ge.prim_name(o["name"])
        name, i = base, 2
        while name in used:
            name, i = "%s_%d" % (base, i), i + 1
        used.add(name)
        opath = "/st_roto/" + name
        UsdGeom.Xform.Define(stage, opath)
        snames = set()
        for s in store.shapes(o["id"]):
            keys = store.keys(s["id"])
            if not keys:
                continue
            sbase = ge.prim_name(s["name"])
            sname, j = sbase, 2
            while sname in snames:
                sname, j = "%s_%d" % (sbase, j), j + 1
            snames.add(sname)
            n = int(s["point_count"])
            cur = UsdGeom.BasisCurves.Define(stage, "%s/%s_curve" % (opath, sname))
            cur.CreateTypeAttr(UsdGeom.Tokens.cubic)
            cur.CreateBasisAttr(UsdGeom.Tokens.bezier)
            cur.CreateWrapAttr(UsdGeom.Tokens.periodic)
            cur.CreateCurveVertexCountsAttr(Vt.IntArray([3 * n]))
            mesh = UsdGeom.Mesh.Define(stage, "%s/%s_mesh" % (opath, sname))
            m = n * per_segment
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray([m]))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(list(range(m))))
            for k in keys:
                f = float(k["frame"])
                all_frames.add(k["frame"])
                pts = k["points"]
                hidden = (not pts) or is_collapsed(pts)
                for g in (cur, mesh):
                    g.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible if hidden else UsdGeom.Tokens.inherited, f)
                if hidden:
                    continue
                cp = ge.curve_points(pts, h)
                cur.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in cp]), f)
                mp = ge.mesh_polygon(pts, h, per_segment)
                mesh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in mp]), f)
                ext = Vt.Vec3fArray([Gf.Vec3f(*map(float, cp.min(0))), Gf.Vec3f(*map(float, cp.max(0)))])
                cur.GetExtentAttr().Set(ext, f)
                mesh.GetExtentAttr().Set(ext, f)
            prims["%s/%s_curve" % (opath, sname)] = (o["name"], s["name"])
            prims["%s/%s_mesh" % (opath, sname)] = (o["name"], s["name"])
    if not prims:
        raise ValueError("the shot has no keyed shapes to export")
    stage.SetStartTimeCode(float(min(all_frames)))
    stage.SetEndTimeCode(float(max(all_frames)))
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".part.abc"
    if os.path.exists(tmp):
        os.remove(tmp)
    stage.GetRootLayer().Export(tmp)
    os.replace(tmp, path)
    return {"path": path, "prims": prims, "frames": [min(all_frames), max(all_frames)]}


def read_back(path: str) -> dict:
    """{prim path: {frame: points [(x, y, z)]}} of every curve / mesh in an .abc (for verification)."""
    from pxr import Usd, UsdGeom
    st = Usd.Stage.Open(path)
    out = {}
    for p in st.Traverse():
        t = p.GetTypeName()
        if t not in ("BasisCurves", "Mesh"):
            continue
        pa = UsdGeom.PointBased(p).GetPointsAttr()
        out[str(p.GetPath())] = {int(round(ts)): [tuple(v) for v in pa.Get(ts)] for ts in pa.GetTimeSamples()
                                 if pa.Get(ts) is not None}
    return out
