"""OQ-29: open the precise-edge drawing kit in Nuke (GUI).
  "C:\\Program Files\\Nuke17.1v3\\Nuke17.1.exe" --nc D:\\ST-ROTO\\tools\\edge_truth\\open_kit.py
Creates a plate Read and a reference Read (object outlined in magenta) of data/edge_truth/ (one 1920x1920 canvas
sequence, frames 1..n) and one ST_Roto node with AI switched off whose project is data/edge_truth/edge_truth.stroto
(3 nodes: within Nuke Non-commercial's 10-node Python budget). Draw in the ST_Roto node's Roto, then press 'Save Roto
edits to project' (INSTRUCTIONS.md). Nothing is saved to a .nk script automatically.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")).replace("\\", "/")
if ROOT + "/src" not in sys.path:
    sys.path[:0] = [ROOT + "/src"]
    sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                                       # noqa: E402

KIT = ROOT + "/data/edge_truth"
PROJECT = KIT + "/edge_truth.stroto"


def open_kit(kit=KIT, project=None):
    import st_roto_nuke.node as stnode
    man = json.load(open(kit + "/manifest.json"))
    n, (cw, ch) = len(man["frames"]), man["canvas"]
    nuke.addFormat("%d %d 1 st_edge_truth_canvas" % (cw, ch))
    nuke.root()["format"].setValue("st_edge_truth_canvas")
    plate = nuke.nodes.Read(file=kit + "/plate.####.png", first=1, last=n, name="plate")
    ref = nuke.nodes.Read(file=kit + "/reference.####.png", first=1, last=n, name="reference")
    node = stnode.create(plate, project or (kit + "/edge_truth.stroto"))
    old = node.fullName()
    node.setName("draw_truth")
    stnode._INNER[node.fullName()] = stnode._INNER.pop(old)   # keep the inner-node cache (NC node budget)
    node["stroto_ai_off"].setValue(True)
    stnode.apply_ai_visibility(node)
    node["stroto_object"].setValue("truth")
    plate.setXYpos(0, 0); ref.setXYpos(150, 0); node.setXYpos(0, 150)
    nuke.root()["first_frame"].setValue(1)
    nuke.root()["last_frame"].setValue(n)
    return node, plate


if __name__ == "__main__":
    open_kit()
