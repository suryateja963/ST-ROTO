import os, sys, json, traceback
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke
import numpy as np
from st_roto import exr
R = {}
try:
    nuke.root()["format"].setValue(nuke.addFormat("960 540 1 mc"))
    con = nuke.nodes.Constant(color=[1, 0, 0, 1]); con["format"].setValue("mc")
    cam = nuke.nodes.Camera3()
    cam["translate"].setValue([0.6, 0.05, 0.1]); cam["rotate"].setValue([1.5, -4.0, 2.5])
    card = nuke.nodes.GeoCard()
    R["card_knobs"] = sorted(k for k in card.knobs() if any(t in k for t in ("translate", "scale", "uniform", "size")))
    card["uniform_scale"].setValue(0.3); card["translate"].setValue([0.0, 0.0, -6.0])
    sr = nuke.nodes.ScanlineRender2(); sr.setInput(1, card); sr.setInput(2, cam)
    wr = nuke.nodes.Write(file=HERE + "/out/dbg.exr", file_type="exr", datatype="32 bit float", channels="rgba")
    wr.setInput(0, sr)
    k = cam["world_matrix"]
    R["k_type"] = type(k).__name__
    R["methods"] = [m for m in dir(k) if "alue" in m or "atrix" in m][:30]
    for meth in ("valueAt", "getValueAt"):
        try:
            R[meth] = [getattr(k, meth)(1, i) for i in range(16)]
        except Exception as e:
            R[meth] = "ERR %s" % e
    try:
        R["value_list"] = list(k.value())
    except Exception as e:
        R["value_list"] = "ERR %s" % e
    nuke.execute(wr, 1, 1)
    ch = exr.read_channels(HERE + "/out/dbg.exr")
    R["channels"] = sorted(ch)
    R["alpha_max"] = float(ch["A"].max()) if "A" in ch else None
    R["alpha_px"] = int((ch["A"] > 0.5).sum()) if "A" in ch else None
    R["red_max"] = float(ch["R"].max()) if "R" in ch else None
    R["sr_inputs"] = [sr.inputLabel(i) if hasattr(sr, "inputLabel") else None for i in range(3)]
except Exception:
    R["error"] = traceback.format_exc()
json.dump(R, open(HERE + "/debug_render.json", "w"), indent=1, default=str)
print(json.dumps(R, default=str)[:2000])
