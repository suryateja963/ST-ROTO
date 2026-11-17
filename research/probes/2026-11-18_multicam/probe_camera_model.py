"""T-120 probe: does st_roto.cameras project like Nuke? Nuke 17 3D (Camera3 + GeoCard + ScanlineRender2; the classic system rendered nothing headless), headless NC.
Three non-rectified cameras (toe-in, roll, vertical offset, window translate, different focal lengths); small cards
at known world points; the centroid of each rendered card vs st_roto.cameras.project(projection(intrinsics(...),
from_world_matrix(world_matrix knob))). Also writes cameras.json (Nuke parameters + world matrices) for the
synthetic multi-camera scene generator.
Run: Nuke17.1.exe --nc -t probe_camera_model.py -> result_camera_model.json"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke  # noqa: E402
import numpy as np  # noqa: E402
from st_roto import cameras as cm, exr  # noqa: E402

OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
W, H = 960, 540
CAMS = {
    "A": {"translate": [0.0, 0.0, 0.0], "rotate": [0.0, 0.0, 0.0], "focal": 35.0, "haperture": 24.576,
          "win_translate": [0.0, 0.0]},
    "B": {"translate": [0.6, 0.05, 0.1], "rotate": [1.5, -4.0, 2.5], "focal": 35.0, "haperture": 24.576,
          "win_translate": [0.0, 0.0]},
    "C": {"translate": [-0.3, 0.45, -0.2], "rotate": [-3.0, 2.0, -1.5], "focal": 30.0, "haperture": 24.576,
          "win_translate": [0.05, -0.03]},
}
POINTS = [[0.0, 0.0, -6.0], [0.8, 0.4, -5.0], [-1.0, -0.5, -8.0], [0.3, -0.7, -4.0], [-0.6, 0.6, -10.0]]
R = {"cams": {}, "points": POINTS}
try:
    nuke.root()["format"].setValue(nuke.addFormat("%d %d 1 mc" % (W, H)))
    con = nuke.nodes.Constant(color=[1, 0, 0, 1])
    con["format"].setValue("mc")
    cam = nuke.nodes.Camera3()
    card = nuke.nodes.GeoCard()
    card["uniform_scale"].setValue(0.05)
    sr = nuke.nodes.ScanlineRender2()
    sr.setInput(1, card); sr.setInput(2, cam)
    wr = nuke.nodes.Write(file=OUT + "/card.exr", file_type="exr", datatype="32 bit float", channels="rgba")
    wr.setInput(0, sr)
    R["camera_knobs"] = sorted(k for k in cam.knobs() if any(t in k for t in ("matrix", "aperture", "win", "rot")))
    errs = []
    for name, c in CAMS.items():
        cam["translate"].setValue(c["translate"]); cam["rotate"].setValue(c["rotate"])
        cam["focal"].setValue(c["focal"]); cam["haperture"].setValue(c["haperture"])
        cam["win_translate"].setValue(c["win_translate"])
        wm = [cam["world_matrix"].valueAt(1, i) for i in range(16)]
        info = dict(c, world_matrix=wm, vaperture=cam["vaperture"].value(), rot_order=cam["rot_order"].value())
        Rm, C = cm.from_world_matrix(np.array(wm).reshape(4, 4))
        K = cm.intrinsics(W, H, c["focal"], c["haperture"], win_translate=c["win_translate"])
        P = cm.projection(K, Rm, C)
        pts = []
        for X in POINTS:
            card["translate"].setValue(X)
            nuke.execute(wr, 1, 1)
            a = exr.read_channels(OUT + "/card.exr")["A"]
            ys, xs = np.nonzero(a > 0.5)
            if len(xs) == 0:
                pts.append({"X": X, "rendered": None}); continue
            got = [float(xs.mean() + 0.5), float(ys.mean() + 0.5)]
            pred, depth = cm.project(P, [X])
            e = float(np.hypot(*(np.array(got) - pred[0])))
            errs.append(e)
            pts.append({"X": X, "rendered": got, "predicted": pred[0].tolist(), "error_px": round(e, 3),
                        "pixels": int(len(xs))})
        info["points"] = pts
        R["cams"][name] = info
    R["max_error_px"] = max(errs) if errs else None
    R["mean_error_px"] = float(np.mean(errs)) if errs else None
    json.dump({n: {k: v for k, v in c.items() if k != "points"} for n, c in R["cams"].items()},
              open(HERE + "/cameras.json", "w"), indent=1)
except Exception:
    R["error"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_camera_model.json", "w"), indent=1)
print(json.dumps({k: R.get(k) for k in ("camera_knobs", "max_error_px", "mean_error_px")}), R.get("error", "")[-600:])
