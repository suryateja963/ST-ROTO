"""T-092: one product Track in headless Nuke (for VRAM measurement by measure_vram.py).
  Nuke17.1.exe --nc -t track_once.py model=<model> objects=<n> frames=<n>
Writes result_<model>_<n>obj.json (status, seconds)."""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                       # noqa: E402

VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"
_a = dict(x.split("=", 1) for x in sys.argv[1:] if "=" in x)   # bare numbers would be frame ranges for Nuke
model, n_obj, n = _a["model"], int(_a["objects"]), int(_a["frames"])
import st_roto_nuke.node as stnode                                # noqa: E402
meta = json.load(open(VIDEO + "/meta.json"))
vh = meta["h"]
nuke.root()["format"].setValue("HD_720")
rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "v.stroto"))
g["stroto_model"].setValue(model)
pts = [("target", meta["click_xy"]), ("disc", (1050.0, 560.0))][:n_obj]
for name, (x, y) in pts:
    g["stroto_object"].setValue(name); nuke.frame(0)
    g["stroto_click"].setValue([x, vh - y]); stnode.on_add_point(g, 1)
t0 = time.time()
job = stnode.on_track(g, background=False)
out = {"model": model, "objects": n_obj, "frames": n, "seconds": round(time.time() - t0, 1),
       "status": g["stroto_status"].value(), "job": job.status if job else None}
json.dump(out, open(HERE + "/result_%s_%dobj.json" % (model, n_obj), "w"), indent=1)
