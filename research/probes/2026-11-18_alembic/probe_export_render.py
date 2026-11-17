"""T-113 probe: export a shot to Alembic (st_roto_nuke.alembic), read it back through USD (exactness), and render the
MESH with Nuke's OWN Alembic reader (ReadGeo2 / Alembic_In.dll - a different implementation than USD's writer) +
ScanlineRender through an orthographic camera (1 world unit = 1 pixel) -> alpha vs ST-ROTO's exact raster of the
spline. Run: Nuke17.1.exe --nc -t probe_export_render.py -> result_export_render.json"""
import json
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402

OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
R = {}
W, H = 640, 360
try:
    from st_roto import geomexport as ge, model as m
    from st_roto.commands import CommandBus
    from st_roto.geometry import mask_to_points
    from st_roto.stereo import mask_from_keys
    from st_roto.store import ProjectStore
    import st_roto_nuke.alembic as abc
    s = ProjectStore(os.path.join(tempfile.mkdtemp(), "a.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "Read1", "width": W, "height": H,
                                              "first_frame": 1, "last_frame": 5}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero arm"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "Os", "object_id": "O", "name": "hero arm", "point_count": 12}},
                actor=m.ACTOR_AI)
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    keys = {}
    for f in range(1, 6):
        u = (xx - 200 - 30 * f) / 110.0; v = (yy - 150 - 10 * f) / 60.0
        keys[f] = mask_to_points(1 - np.sqrt(u * u + v * v), count=12)
        bus.execute({"op": "set_key", "shape_id": "Os", "frame": f, "points": keys[f]}, actor=m.ACTOR_AI)
    path = OUT + "/shot.abc"
    res = abc.write_shot(s, "S", path, fps=24.0)
    R["prims"] = res["prims"]
    R["magic"] = open(path, "rb").read(5).decode("ascii", "replace")
    back = abc.read_back(path)
    R["read_back_paths"] = sorted(back)
    err_c = err_m = 0.0
    for pth, per in back.items():
        for f, pts in per.items():
            if f not in keys:
                R.setdefault("extra_sample_times", {})[pth] = f
                R.setdefault("extra_sample_equals_first", {})[pth] = pts == per[min(keys)]
                continue
            exp = ge.curve_points(keys[f], H) if "curve" in pth else ge.mesh_polygon(keys[f], H)
            e = float(np.abs(np.array(pts) - exp).max())
            if "curve" in pth:
                err_c = max(err_c, e)
            else:
                err_m = max(err_m, e)
    R["read_back_max_error_curve"] = err_c
    R["read_back_max_error_mesh"] = err_m
    R["read_back_frames"] = {p: sorted(v) for p, v in back.items()}

    nuke.root()["format"].setValue(nuke.addFormat("%d %d 1 abc_probe" % (W, H)))
    rg = nuke.nodes.GeoImport(file=path)
    R["geoimport_knobs"] = sorted(k for k in rg.knobs() if not k.startswith("_"))[:80]
    camcls = "Camera3" if hasattr(nuke.nodes, "Camera3") else "Camera2"
    cam = getattr(nuke.nodes, camcls)()
    R["camera_class"] = camcls
    R["camera_knobs"] = sorted(k for k in cam.knobs() if any(t in k for t in ("proj", "focal", "aperture", "translate", "win")))
    cam["projection_mode"].setValue("orthographic")
    cam["focal"].setValue(1.0)
    cam["haperture"].setValue(float(W))
    cam["vaperture"].setValue(float(H))
    cam["translate"].setValue([W / 2.0, H / 2.0, 100.0])
    rcls = "ScanlineRender2" if hasattr(nuke.nodes, "ScanlineRender2") else "ScanlineRender"
    sr = getattr(nuke.nodes, rcls)()
    R["render_class"] = rcls
    R["render_inputs"] = [sr.inputLabel(i) if hasattr(sr, "inputLabel") else i for i in range(sr.maxInputs())]
    sr.setInput(1, rg); sr.setInput(2, cam)
    wr = nuke.nodes.Write(file=OUT + "/render.####.exr", file_type="exr", datatype="32 bit float", channels="rgba")
    wr.setInput(0, sr)
    out = {}
    for f in (1, 3, 5):
        nuke.execute(wr, f, f)
        from st_roto import exr as _exr
        a = _exr.read_channels(OUT + "/render.%04d.exr" % f)["A"] > 0.5
        ref = mask_from_keys([keys[f]], H, W)
        out[f] = {"iou": round(float((a & ref).sum() / max(1, (a | ref).sum())), 4), "alpha_px": int(a.sum()),
                  "ref_px": int(ref.sum())}
    R["nuke_render_vs_spline"] = out
except Exception:
    R["error"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_export_render.json", "w"), indent=1, default=str)
print(json.dumps({k: R.get(k) for k in ("magic", "extra_sample_times", "extra_sample_equals_first", "read_back_max_error_curve", "read_back_max_error_mesh",
                                         "scene_items", "nuke_render_vs_spline")}), R.get("error", "")[-800:])
