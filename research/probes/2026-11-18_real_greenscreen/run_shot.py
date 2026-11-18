"""Real green-screen shots (owner's footage, read in place; NOT redistributed): ST-ROTO's product path in Nuke.
One process per (shot, model) because of the Non-commercial 10-node budget.
  Nuke17.1.exe --nc -t run_shot.py shot=SHOT-112 model=sam2.1-hiera-tiny work=<dir> [mattes=1]
Track (box + clicks per object, prompts.json), Re-track objects prompted after frame 0 back to the start; with
mattes=1 also EXR mattes: guided (premultiplied RGB), hard / ViTMatte (hair shots), decontaminated + despill (spill
shots), holdout role (two-person shots). Writes <work>/run.json (status texts, timings); the project file and the
mattes stay in <work> for measure.py."""
import glob
import json
import os
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path.insert(0, ROOT + "/src")
from st_roto import runtime_choice as _rc                    # noqa: E402 - same runtime choice as the plugin
_b, _w = _rc.choose(os.environ.get(_rc.ENV, ""), _rc.nvidia_driver_present(), os.path.isdir(ROOT + "/" + _rc.DML_DIR))
os.environ[_rc.ACTIVE_ENV], os.environ[_rc.REASON_ENV] = _b, _w
sys.path += [p.replace("\\", "/") for p in _rc.site_dirs(ROOT, _b)]
import nuke                                                   # noqa: E402

SRC = "D:/reffeerce shots/GREEN MATTE"
HAIR = {"SHOT-115", "SHOT-116"}
SPILL = {"SHOT-115", "SHOT-116", "SHOT-118", "SHOT-113"}
HOLDOUT = {"SHOT-114": "man", "SHOT-117": "man"}
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
shot, model, work = args["shot"], args["model"], args["work"].replace("\\", "/")
R = {"shot": shot, "model": model, "steps": []}


def step(name, t0, status):
    R["steps"].append({"step": name, "seconds": round(time.time() - t0, 1), "status": status})


try:
    import st_roto_nuke.node as n
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    prompts = json.load(open(HERE + "/prompts.json"))[shot]
    files = sorted(glob.glob("%s/%s/%s_*.tif" % (SRC, shot, shot)))
    first, last = 0, len(files) - 1
    rd = nuke.nodes.Read(file="%s/%s/%s_#####.tif" % (SRC, shot, shot), first=first, last=last)
    W, H = int(rd.width()), int(rd.height())
    R["plate"] = {"w": W, "h": H, "frames": len(files), "read_colorspace": rd["colorspace"].value()}
    g = n.create(rd, work + "/" + shot + ".stroto")
    g["stroto_model"].setValue(model)
    for name, o in prompts["objects"].items():
        g["stroto_object"].setValue(name)
        nuke.frame(o["frame"])
        b = o["box"]
        g["stroto_box"].setValue([b[0] * W, H - b[3] * H, b[2] * W, H - b[1] * H])     # Nuke y up
        n.on_set_box(g)
        for c in o["clicks"]:
            g["stroto_click"].setValue([c[0] * W, H - c[1] * H])
            n.on_add_point(g, 1)
    R["prompts"] = g["stroto_points_info"].value()
    t0 = time.time()
    job = n.on_track(g, background=False)
    step("track", t0, g["stroto_status"].value())
    R["scene_cuts_knob"] = g["stroto_cuts"].value()
    for name, o in prompts["objects"].items():                    # objects prompted later: also back to frame 0
        if o["frame"] > first:
            g["stroto_object"].setValue(name)
            nuke.frame(o["frame"])
            t0 = time.time()
            n.on_retrack(g, background=False)
            step("retrack " + name, t0, g["stroto_status"].value())
    if args.get("mattes") == "1":
        def render(tag, edges="guided filter", rgb="premultiplied", spill="none"):
            g["stroto_edges"].setValue(edges)
            g["stroto_rgb_mode"].setValue(rgb)
            g["stroto_spill"].setValue(spill)
            g["stroto_matte_dir"].setValue(work + "/mattes_" + tag)
            t = time.time()
            n.on_render_mattes(g, background=False)
            step("mattes " + tag, t, g["stroto_status"].value())
        render("guided")
        if shot in HAIR:
            render("hard", edges="hard")
            render("vitmatte", edges="ViTMatte-S (optional AI)")
        if shot in SPILL:
            render("decon_spill", rgb="premultiplied, decontaminated", spill="auto")
        if shot in HOLDOUT:
            g["stroto_object"].setValue(HOLDOUT[shot])
            n.on_set_role(g, "holdout")
            step("role", time.time(), g["stroto_status"].value())
            render("holdout")
    R["ok"] = True
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(work + "/run.json", "w"), indent=1)
