"""ViTMatte-S tiled vs one pass (fix for the 10.5 GB allocation on 4K close-ups). Inside Nuke (GPU):
  Nuke17.1.exe --nc -t check_vitmatte_tiles.py work=<dir> out=<json>
(a) SHOT-115 frame 13 at HALF resolution, where one pass still fits: one pass vs tiles of 512 (overlap 128) - the
    tiles must not change the alpha; (b) the same frame at FULL 4K, which failed in one pass: tiles of 1024."""
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.append(os.path.join(ROOT, ".tools", "nuke-py311"))
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
R = {}
try:
    import numpy as np
    import cv2
    from st_roto.geometry import Anchor, rasterize_spline
    from st_roto.store import ProjectStore
    from st_roto_ai.vitmatte import ViTMatte, trimap_from_mask
    from st_roto_ai.registry import model_dir
    from st_roto_nuke import mattes as mt
    vm = ViTMatte(os.path.dirname(model_dir("vitmatte-small-composition-1k")), args.get("device", "auto"))
    R["device"] = vm.report.active
    st = ProjectStore(os.path.join(args["work"], "SHOT-115_tiny", "SHOT-115.stroto"))
    sid = st.conn.execute("SELECT id FROM shots").fetchone()["id"]
    obj = st.objects(sid)[0]
    key = [k for k in st.keys(st.shapes(obj["id"])[0]["id"]) if k["frame"] == 13][0]
    a16 = cv2.imread("D:/reffeerce shots/GREEN MATTE/SHOT-115/SHOT-115_00013.tif", cv2.IMREAD_UNCHANGED)

    def setup(scale):
        h, w = int(a16.shape[0] * scale), int(a16.shape[1] * scale)
        rgb = cv2.resize(a16, (w, h), interpolation=cv2.INTER_AREA)[..., ::-1].astype(np.float32) / 65535.0
        an = [Anchor(p=np.array(q[:2]) * scale, h_in=np.array(q[2:4]) * scale, h_out=np.array(q[4:]) * scale,
                     corner=False) for q in key["points"]]
        mask = rasterize_spline(an, h, w)
        tri = trimap_from_mask(mask, 6, 20)
        ys, xs = np.nonzero(tri == 0.5)
        y0, y1, x0, x1 = max(0, ys.min() - 8), min(h, ys.max() + 9), max(0, xs.min() - 8), min(w, xs.max() + 9)
        return rgb[y0:y1, x0:x1], tri[y0:y1, x0:x1]
    rgb, tri = setup(0.5)
    R["half_crop"] = list(tri.shape)
    t = time.time(); one = vm.alpha(rgb, tri); R["half_one_pass_s"] = round(time.time() - t, 2)
    t = time.time(); til = mt._vitmatte_tiled(vm, rgb, tri, tile=512, overlap=128); R["half_tiled512_s"] = round(time.time() - t, 2)
    band = tri == 0.5
    d = np.abs(one - til)[band]
    R["half_tiles_vs_one_pass"] = {"mean_abs_diff_in_unknown": round(float(d.mean()), 5),
                                   "p99_abs_diff": round(float(np.percentile(d, 99)), 4),
                                   "max_abs_diff": round(float(d.max()), 4), "unknown_px": int(band.sum())}
    rgb, tri = setup(1.0)
    R["full_crop"] = list(tri.shape)
    t = time.time(); full = mt._vitmatte_tiled(vm, rgb, tri); R["full_tiled1024_s"] = round(time.time() - t, 2)
    R["full_ok"] = bool(np.isfinite(full).all())
    R["passed"] = R["full_ok"] and R["half_tiles_vs_one_pass"]["mean_abs_diff_in_unknown"] < 0.02
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(args["out"], "w"), indent=1)
