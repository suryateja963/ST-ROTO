"""Every frame of every shot as a JPG with the ST-ROTO Roto splines drawn on the plate (owner's footage: output ONLY
to a local folder outside the repository, never committed).
  .venv\\Scripts\\python.exe -I render_overlays.py work=<dir with SHOT-xxx_tiny / _large> out=<folder> [shots=...]
red = tiny model, blue = large model (each object, main + part shapes, the exact stored spline), thin yellow = keyed
reference outline (measure.py key). 1920 px wide."""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(ROOT, ".tools", "nuke-py311"))
import cv2  # noqa: E402
from st_roto.geometry import Anchor, sample_spline  # noqa: E402
from st_roto import pieces  # noqa: E402
from st_roto.store import ProjectStore  # noqa: E402

args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
sys.argv = [sys.argv[0], "work=" + args["work"]]
import measure as M  # noqa: E402

OW = 1920
COL = {"tiny": (0, 0, 255), "large": (255, 80, 0)}          # BGR


def splines(work, shot, model):
    d = os.path.join(work, "%s_%s" % (shot, model))
    p = os.path.join(d, shot + ".stroto")
    if not (os.path.exists(p) and os.path.exists(os.path.join(d, "run.json"))):
        return None
    st = ProjectStore(p)
    out = {}
    sid = st.conn.execute("SELECT id FROM shots").fetchone()["id"]
    for o in st.objects(sid):
        for s in st.shapes(o["id"]):
            for k in st.keys(s["id"]):
                if k["points"] and not pieces.is_collapsed(k["points"]):
                    a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:]), corner=False)
                         for q in k["points"]]
                    out.setdefault(k["frame"], []).append((o["name"], sample_spline(a, 48)))
    st.conn.close()
    return out


def main():
    work, out = args["work"], args["out"]
    shots = args["shots"].split(",") if args.get("shots") else sorted(k for k in M.PROMPTS if not k.startswith("_"))
    for shot in shots:
        n = len(glob.glob("%s/%s/%s_*.tif" % (M.SRC, shot, shot)))
        sp = {m: splines(work, shot, m) for m in ("tiny", "large")}
        sp = {m: v for m, v in sp.items() if v}
        od = os.path.join(out, shot)
        os.makedirs(od, exist_ok=True)
        for f in range(n):
            a16 = cv2.imread("%s/%s/%s_%05d.tif" % (M.SRC, shot, shot, f), cv2.IMREAD_UNCHANGED)
            H, W = a16.shape[:2]
            sc = OW / float(W)
            oh = int(round(H * sc))
            img = (cv2.resize(a16, (OW, oh), interpolation=cv2.INTER_AREA) / 257.0).astype(np.uint8)
            ka, _ = M.key_alpha(img[..., ::-1].astype(np.float32) / 255.0)
            cs, _ = cv2.findContours((ka >= 0.5).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            cs = [c for c in cs if cv2.contourArea(c) > 400]
            cv2.drawContours(img, cs, -1, (0, 230, 255), 1, cv2.LINE_AA)
            for m, per in sp.items():
                for name, poly in per.get(f, []):
                    pts = np.round(poly * sc).astype(np.int32).reshape(-1, 1, 2)
                    cv2.polylines(img, [pts], True, COL[m], 2, cv2.LINE_AA)
            txt = "%s  frame %d   " % (shot, f) + "   ".join(
                "%s = %s" % (m, "red" if m == "tiny" else "blue") for m in sp) + "   yellow = keyed reference"
            cv2.rectangle(img, (0, 0), (OW, 30), (0, 0, 0), -1)
            cv2.putText(img, txt, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imwrite(os.path.join(od, "%s_overlay_%05d.jpg" % (shot, f)), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(shot, n, "frames", "models:", ",".join(sp), flush=True)


if __name__ == "__main__":
    main()
