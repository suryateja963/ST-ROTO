"""OQ-29: drawn shapes -> truth masks. Reads data/edge_truth/edge_truth.stroto (no Nuke needed) and writes
data/edge_truth/truth.####.png at each frame's REAL size: per frame, the union of every shape with a key ON that frame
(shapes whose name starts with 'hole' are subtracted), rasterised exactly from the stored splines on the kit canvas
and cropped to the frame (top-left placement, make_kit.py). Prints which frames have no drawing yet.
  .venv\\Scripts\\python.exe -I tools/edge_truth/export_truth.py [kit folder] [project]
"""
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
KIT = os.path.join(ROOT, "data", "edge_truth")


def export(kit=KIT, project=None, out_dir=None):
    from st_roto.geometry import Anchor, rasterize_spline
    from st_roto.store import ProjectStore
    man = json.load(open(os.path.join(kit, "manifest.json")))
    cw, ch = man["canvas"]
    frames = {e["frame"]: e for e in man["frames"]}
    project = project or os.path.join(kit, "edge_truth.stroto")
    out_dir = out_dir or kit
    masks = {}
    if os.path.exists(project):
        store = ProjectStore(project)
        for o in store.conn.execute("SELECT id FROM objects"):
            for s in store.shapes(o["id"]):
                hole = s["name"].lower().startswith("hole")
                for k in store.keys(s["id"]):
                    f = k["frame"]
                    if f not in frames or not k["points"]:
                        continue
                    a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False)
                         for p in k["points"]]
                    m = masks.setdefault(f, {"add": np.zeros((ch, cw), bool), "hole": np.zeros((ch, cw), bool)})
                    m["hole" if hole else "add"] |= rasterize_spline(a, ch, cw)
        store.close()
    done = []
    for f, e in sorted(frames.items()):
        if f not in masks:
            continue
        truth = (masks[f]["add"] & ~masks[f]["hole"])[:e["height"], :e["width"]]
        if truth.any():
            cv2.imwrite(os.path.join(out_dir, "truth.%04d.png" % f), truth.astype(np.uint8) * 255)
            done.append(f)
    missing = [f for f in sorted(frames) if f not in done]
    print("drawn %d / %d%s" % (len(done), len(frames), ("   missing: %s" % missing) if missing else ""))
    return {"drawn": done, "missing": missing}


if __name__ == "__main__":
    a = sys.argv[1:]
    export(a[0] if a else KIT, a[1] if len(a) > 1 else None)
