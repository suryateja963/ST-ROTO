"""T-099: does a Nuke Read node keep an EXR open so that it cannot be replaced (Windows), and which Nuke call releases
it? Headless: Nuke17.1.exe --nc -t probe_file_lock.py -> result_file_lock.json"""
import json, os, sys, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                       # noqa: E402
import numpy as np                                                # noqa: E402
from st_roto import exr                                           # noqa: E402

R = {}


def try_replace(path, tag):
    try:
        exr.write_mattes(path, {"x": np.full((8, 8), 0.5, np.float32)})
        R[tag] = "replaced"
    except Exception as e:
        R[tag] = "%s: %s" % (type(e).__name__, str(e)[:120])


try:
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.0001.exr").replace("\\", "/")
    exr.write_mattes(p, {"x": np.ones((8, 8), np.float32)})
    rr = nuke.nodes.Read(file=p, first=1, last=1)
    nuke.frame(1)
    R["sample"] = rr.sample("rgba.alpha", 2.5, 2.5)
    try_replace(p, "while_read_open")
    for name in ("clearRAMCache", "clearDiskCache"):
        getattr(nuke, name)()
        try_replace(p, "after_" + name)
    try:
        rr["reload"].execute()
    except Exception as e:
        R["reload_error"] = str(e)
    try_replace(p, "after_reload")
    rr["file"].setValue("")
    try_replace(p, "after_clearing_file_knob")
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(HERE + "/result_file_lock.json", "w"), indent=1)
