"""T-067 timing probe: two objects in ONE pass vs two single-object passes, on the GPU inside Nuke's Python.

Run:  Nuke17.1.exe --nc -t research/probes/2026-11-16_multi_object/probe_multi_speed.py [model]
Frames come from the synthetic shot PNGs (no Nuke render), so this measures the tracker, not pixel transfer
(pixel transfer is a second saving of the one-pass design: each frame is rendered once instead of once per object).
Writes result_<model>.json next to this file.
"""
import json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402

from st_roto_ai.sam2 import preload_video        # noqa: E402
from st_roto_nuke.track import models_root, track_object, track_objects   # noqa: E402

FR = ROOT + "/research/probes/2026-11-15_video/frames"
MODEL = [a for a in sys.argv[1:] if a.startswith("sam2")][:1] or ["sam2.1-hiera-tiny"]
MODEL = MODEL[0]
meta = json.load(open(FR + "/meta.json"))
N = meta["frames"]
_cache = {}


def get_rgb(f):
    if f not in _cache:
        x = cv2.cvtColor(cv2.imread(FR + "/frame_%04d.png" % f), cv2.COLOR_BGR2RGB) / 255.0
        _cache[f] = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)
    return _cache[f]


def disc(f):
    s = f / 47.0
    return 1050 - 600 * s, 560 - 120 * np.sin(np.pi * s)


for f in range(N):
    get_rgb(f)                                                  # decode outside the timings
objs = [{"name": "target", "frame": 0, "points": [tuple(meta["click_xy"])], "labels": [1]},
        {"name": "disc", "frame": 0, "points": [disc(0)], "labels": [1]}]
load = preload_video(os.path.join(models_root(), MODEL, "video"), "auto")
frames = list(range(N))
track_object(get_rgb, frames[:3], 0, objs[0]["points"], model=MODEL)         # warm-up (CUDA kernels, arena)
out = {"model": MODEL, "frames": N, "load": load, "trials": []}
for trial in range(2):
    t0 = time.time()
    singles = [track_object(get_rgb, frames, 0, o["points"], model=MODEL) for o in objs]
    t_single = time.time() - t0
    t0 = time.time()
    multi = track_objects(get_rgb, frames, objs, model=MODEL)
    t_multi = time.time() - t0
    same = []
    for s, m in zip(singles, multi["objects"]):
        d = max(abs(a - b) for f in s["keys"] for p, q in zip(s["keys"][f], m["keys"].get(f, [])) for a, b in zip(p, q)) \
            if sorted(s["keys"]) == sorted(m["keys"]) else None
        same.append(d)
    out["trials"].append({"two_single_passes_s": round(t_single, 2), "one_multi_pass_s": round(t_multi, 2),
                          "speedup": round(t_single / t_multi, 2), "device": multi["device"],
                          "max_point_diff_px_single_vs_multi": same})
    print(out["trials"][-1], flush=True)
import cProfile, pstats, io
pr = cProfile.Profile(); pr.enable(); track_objects(get_rgb, frames, objs, model=MODEL); pr.disable()
st = io.StringIO(); pstats.Stats(pr, stream=st).sort_stats("tottime").print_stats(12)
prof = st.getvalue(); print(prof)
out["profile_multi_pass_top_tottime"] = prof.splitlines()[:40]
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_%s.json" % MODEL), "w"), indent=1)
