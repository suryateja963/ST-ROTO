"""T-048: cost of checkpointing (every 10 frames) on a 48-frame, 2-object Track, GPU in Nuke's Python.
Run: Nuke17.1.exe --nc -t research/probes/2026-11-16_resume/probe_checkpoint_cost.py"""
import json, os, shutil, sys, tempfile, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402
from st_roto_nuke.track import track_objects   # noqa: E402

FR = ROOT + "/research/probes/2026-11-15_video/frames"
meta = json.load(open(FR + "/meta.json"))
N = meta["frames"]
cache = {}


def get_rgb(f):
    if f not in cache:
        x = cv2.cvtColor(cv2.imread(FR + "/frame_%04d.png" % f), cv2.COLOR_BGR2RGB) / 255.0
        cache[f] = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)
    return cache[f]


for f in range(N):
    get_rgb(f)
objs = [{"name": "t", "frame": 0, "points": [tuple(meta["click_xy"])], "labels": [1]},
        {"name": "d", "frame": 0, "points": [(1050.0, 560.0)], "labels": [1]}]
track_objects(get_rgb, list(range(3)), objs[:1])                              # warm-up
out = {"trials": []}
for t in range(2):
    t0 = time.time(); track_objects(get_rgb, list(range(N)), objs); plain = time.time() - t0
    ck = tempfile.mkdtemp()
    sizes = []
    real_write = __import__("st_roto_nuke.track", fromlist=["_write_checkpoint"])._write_checkpoint
    t0 = time.time(); track_objects(get_rgb, list(range(N)), objs, checkpoint_dir=os.path.join(ck, "c"), checkpoint_every=10)
    with_ck = time.time() - t0
    shutil.rmtree(ck, ignore_errors=True)
    out["trials"].append({"plain_s": round(plain, 2), "checkpoint_every_10_s": round(with_ck, 2),
                          "overhead_pct": round(100 * (with_ck - plain) / plain, 1)})
    print(out["trials"][-1], flush=True)
# size of a checkpoint at the end of a run (cancelled at the last frame)
from st_roto.jobs import Cancelled   # noqa: E402


class StopAt(object):
    def __init__(self, n): self.n, self.c = n, 0
    def check(self):
        self.c += 1
        if self.c > self.n:
            raise Cancelled("probe")
    def report(self, *a): pass


ck = os.path.join(tempfile.mkdtemp(), "c")
try:
    track_objects(get_rgb, list(range(N)), objs, job=StopAt(N - 1), checkpoint_dir=ck)
except Cancelled:
    pass
total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(ck) for f in fs)
out["checkpoint_after_%d_frames_2_objects_MB" % (N - 1)] = round(total / 1e6, 1)
print(out, flush=True)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json"), "w"), indent=1)
