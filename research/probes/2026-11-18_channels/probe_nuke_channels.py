"""T-110 probe (Nuke 17.1 NC, headless): extra channels of the synthetic CG shot.
  1. which channels / layers and which metadata a Read exposes;
  2. Nuke's own Cryptomatte node (Foundry's implementation) on our file: matte 'target' vs truth -> validates the
     encoding written by st_roto.channels (an independent decoder);
  3. does the ST_Roto group preserve every input channel (pass-through) - render all channels from the node;
  4. rendering selected layers through a Write (EXR) for ST-ROTO's own reading.
Run: Nuke17.1.exe --nc -t probe_nuke_channels.py -> result_nuke_channels.json
"""
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
from st_roto import exr  # noqa: E402

CG = HERE + "/out/cg"
OUT = HERE + "/out/probe"
os.makedirs(OUT, exist_ok=True)
R = {}


def attempt(name, fn):
    try:
        R[name] = fn()
    except Exception:                                         # noqa: BLE001
        R[name] = "ERROR: %s" % traceback.format_exc().strip().splitlines()[-1]
    print(name, "->", str(R[name])[:600])


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


nuke.root()["format"].setValue(nuke.addFormat("960 540 1 cg540"))
rd = nuke.nodes.Read(file=CG + "/cg.####.exr", first=0, last=23)
attempt("read_layers", lambda: sorted(set(c.split(".")[0] for c in rd.channels())))
attempt("read_channels", lambda: rd.channels())
attempt("crypto_metadata", lambda: {k: v for k, v in rd.metadata().items() if "crypto" in k})
w = nuke.nodes.Write(name="w")
w["file_type"].setValue("exr")
w["datatype"].setValue("32 bit float")


def render(node, frame, channels, path):
    w.setInput(0, node)
    w["channels"].setValue(channels)
    w["file"].setValue(path)
    nuke.execute(w, frame, frame)
    return exr.read_channels(path)


def crypto_node():
    cm = nuke.nodes.Cryptomatte()
    cm.setInput(0, rd)
    knobs = sorted(k for k in cm.knobs() if not k.startswith("_"))
    out = {"knobs": [k for k in knobs if k in ("cryptoLayer", "matteList", "matteOutput", "matteOnly",
                                                  "cryptoLayerChoice", "expression", "unpremultiply")]}
    try:
        out["layer_choice"] = cm["cryptoLayerChoice"].values()
    except Exception as e:                                    # noqa: BLE001
        out["layer_choice"] = str(e)
    cm["matteList"].setValue("target")
    res = {}
    for f in (0, 10, 20):
        ch = render(cm, f, "rgba", OUT + "/crypto_nuke.exr")
        a = ch.get("A")
        gt = cv2.imread(CG + "/gt_%04d.png" % f, 0) > 127
        res[f] = {"iou_vs_truth": round(iou(a > 0.5, gt), 5), "alpha_sum_over_truth": round(float(a.sum() / gt.sum()), 4)}
    out["frames"] = res
    return out


attempt("nuke_cryptomatte_node", crypto_node)


def pass_through():
    import st_roto_nuke.node as stnode
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "p.stroto"))
    out = {"group_layers": sorted(set(c.split(".")[0] for c in g.channels()))}
    src = exr.read_channels(CG + "/cg.0010.exr")
    got = render(g, 10, "all", OUT + "/through.exr")
    out["written_channels"] = sorted(got)
    diffs = {}
    for k, v in got.items():
        cand = [k, k.replace(".red", ".R").replace(".green", ".G").replace(".blue", ".B").replace(".alpha", ".A")]
        for c in cand:
            if c in src:
                diffs[k] = float(np.abs(v.astype(np.float64) - src[c].astype(np.float64)).max()); break
        else:
            diffs[k] = "not in source"
    out["max_abs_diff_vs_source"] = diffs
    return out


attempt("st_roto_pass_through", pass_through)
attempt("render_layer_depth", lambda: sorted(render(rd, 10, "depth", OUT + "/depth.exr")))
attempt("render_layer_forward", lambda: sorted(render(rd, 10, "forward", OUT + "/fwd.exr")))
json.dump(R, open(HERE + "/result_nuke_channels.json", "w"), indent=1, default=str)
print("done")
