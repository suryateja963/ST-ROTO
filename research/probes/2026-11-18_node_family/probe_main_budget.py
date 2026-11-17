"""T-112 probe: Node-object budget of the MAIN ST_Roto workflow in a fresh NC session, step by step, by counting
Node objects obtained (monkeypatched nuke.nodes.* / nuke.toNode / Node.input / nuke.selectedNode count calls that
return a node). Run: Nuke17.1.exe --nc -t probe_main_budget.py [mode] -> result_main_budget_<mode>.json
mode: count (default; count only) | track (Track the box prompt, see what each step costs)."""
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

VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"
R = {"steps": []}
LOG = []


def remaining_probe():
    return None


def wrap(obj, name):
    orig = getattr(obj, name)

    def f(*a, **k):
        r = orig(*a, **k)
        if r is not None and hasattr(r, "Class"):
            import traceback as tb
            st = [l for l in tb.format_stack(limit=6)[:-1] if "st_roto" in l or "probe_main" in l]
            LOG.append((name, getattr(r, "name", lambda: "?")(), st[-1].strip().splitlines()[0] if st else ""))
        return r
    setattr(obj, name, f)


for nm in ("toNode", "selectedNode", "createNode", "nodePaste"):
    wrap(nuke, nm)


class _Nodes(object):
    def __getattr__(self, cls):
        orig = getattr(nuke._real_nodes, cls)

        def f(*a, **k):
            r = orig(*a, **k)
            if r is not None:
                LOG.append(("nodes." + cls, r.name(), ""))
            return r
        return f


nuke._real_nodes = nuke.nodes
nuke.nodes = _Nodes()


def step(label):
    R["steps"].append({"step": label, "objects_so_far": len(LOG), "new": LOG[R.get("_last", 0):]})
    R["_last"] = len(LOG)


try:
    import st_roto_nuke.node as stnode
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh = meta["w"], meta["h"]
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=7)
    step("Read")
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "b.stroto"))
    step("ST_Roto create")
    gt0 = cv2.imread(VIDEO + "/gt_0000.png", cv2.IMREAD_GRAYSCALE) > 127
    ys, xs = np.nonzero(gt0)
    g["stroto_object"].setValue("target")
    nuke.frame(0)
    g["stroto_box"].setValue([xs.min() - 4.0, vh - ys.max() - 5.0, xs.max() + 5.0, vh - ys.min() + 4.0])
    stnode.on_set_box(g)
    step("Set box")
    if (sys.argv[1:] or ["count"])[0] == "track":
        j = stnode.on_track(g, background=False)
        R["track"] = g["stroto_status"].value()[:200]
        step("Track")
        stnode.on_render_mattes(g, background=False)
        step("Render mattes")
        import st_roto_nuke.family as fam
        m = fam.create_matte(g, g["stroto_project"].value(), "Read1")
        step("ST_RotoMatte create")
        fam.on_matte_render(m, background=False)
        R["matte_status"] = m["stroto_status"].value()[:300]
        step("ST_RotoMatte render")
        o = fam.create_output(m, g["stroto_project"].value(), "Read1")
        step("ST_RotoOutput create")
        r = fam.on_output(o, "export")
        R["output_status"] = o["stroto_status"].value()[:300]
        step("ST_RotoOutput export")
        R["budget_left_after_all"] = sum(1 for _ in range(12) if nuke._real_nodes.NoOp() is not None)
except Exception:
    R["error"] = traceback.format_exc()
R.pop("_last", None)
R["total"] = len(LOG)
_txt = json.dumps(R, indent=1, default=str)
_home = os.path.expanduser("~")                 # privacy: never publish the local user folder (CLAUDE.md rule 5)
for _h in (_home, _home.replace("\\", "/"), _home.replace("\\", "\\\\")):
    _txt = _txt.replace(_h, "<HOME>")
open(HERE + "/result_main_budget_%s.json" % ((sys.argv[1:] or ["count"])[0]), "w").write(_txt)
print(json.dumps({s["step"]: s["objects_so_far"] for s in R["steps"]}), R.get("error", "")[-600:])
