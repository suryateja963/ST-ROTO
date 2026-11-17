"""T-103: run INSIDE Nuke started with a temporary HOME/USERPROFILE whose .nuke/init.py was written by
st_roto_setup.py. Checks that ST-ROTO was loaded from the INSTALLED copy (not the repository), creates an ST_Roto node
and tracks 3 frames with the installed tiny model. Writes the result path given as out=<file>.
  Nuke17.1.exe --nc -t check_installed.py out=<json> frames=<synthetic frames dir>"""
import json
import os
import sys
import tempfile
import traceback

args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
R = {}
try:
    import nuke
    import st_roto_nuke.node as n
    from st_roto_nuke.track import model_dir
    R["st_roto_nuke_from"] = os.path.dirname(os.path.abspath(n.__file__))
    R["model_dir"] = model_dir("sam2.1-hiera-tiny")
    R["repo_on_path"] = any(os.path.abspath(p).lower().startswith("d:\\st-roto\\src") for p in sys.path)
    vid = args["frames"]
    meta = json.load(open(os.path.join(vid, "meta.json")))
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=vid.replace("\\", "/") + "/frame_####.png", first=0, last=2)
    g = n.create(rd, os.path.join(tempfile.mkdtemp(), "inst.stroto"))
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([meta["click_xy"][0], meta["h"] - meta["click_xy"][1]]); n.on_add_point(g, 1)
    job = n.on_track(g, background=False)
    R["track_status"] = g["stroto_status"].value()
    R["passed"] = bool(job is not None and job.status == "done" and "device cuda" in R["track_status"])
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(args["out"], "w"), indent=1)
