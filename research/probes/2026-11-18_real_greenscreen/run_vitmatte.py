"""Re-render only the ViTMatte-S mattes of a finished large-model run, with the tiling fix (the first run failed:
one pass over a 4K close-up's edge zone asked for a 10.5 GB GPU buffer).
  Nuke17.1.exe --nc -t run_vitmatte.py shot=SHOT-115 work=<dir of SHOT-115_large>"""
import glob
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path.insert(0, ROOT + "/src")
from st_roto import runtime_choice as _rc                    # noqa: E402
_b, _w = _rc.choose(os.environ.get(_rc.ENV, ""), _rc.nvidia_driver_present(), os.path.isdir(ROOT + "/" + _rc.DML_DIR))
os.environ[_rc.ACTIVE_ENV], os.environ[_rc.REASON_ENV] = _b, _w
sys.path += [p.replace("\\", "/") for p in _rc.site_dirs(ROOT, _b)]
import nuke                                                   # noqa: E402

SRC = "D:/reffeerce shots/GREEN MATTE"
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
shot, work = args["shot"], args["work"].replace("\\", "/")
R = {"shot": shot}
try:
    import st_roto_nuke.node as n
    files = sorted(glob.glob("%s/%s/%s_*.tif" % (SRC, shot, shot)))
    rd = nuke.nodes.Read(file="%s/%s/%s_#####.tif" % (SRC, shot, shot), first=0, last=len(files) - 1)
    g = n.create(rd, work + "/" + shot + ".stroto")
    g["stroto_edges"].setValue("ViTMatte-S (optional AI)")
    g["stroto_rgb_mode"].setValue("premultiplied")
    g["stroto_spill"].setValue("none")
    g["stroto_matte_dir"].setValue(work + "/mattes_vitmatte")
    t = time.time()
    job = n.on_render_mattes(g, background=False)
    R["seconds"] = round(time.time() - t, 1)
    R["status"] = g["stroto_status"].value()
    R["ok"] = bool(job is not None and job.status == "done")
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(work + "/run_vitmatte.json", "w"), indent=1)
