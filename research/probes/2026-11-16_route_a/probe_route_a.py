"""T-011a: TorchScript (torch 2.7.1) -> CatFileCreator -> .cat -> Inference node, in Nuke 17.1 Non-commercial.
Checks the output against PyTorch's (reference.npz) and times it. Run twice:
  Nuke17.1.exe --nc -t probe_route_a.py cpu          Nuke17.1.exe --nc --gpu -t probe_route_a.py gpu
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..")).replace("\\", "/")
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402
import nuke          # noqa: E402

mode = sys.argv[-1] if sys.argv[-1] in ("cpu", "gpu") else "cpu"
OUT = HERE + "/out"
os.makedirs(OUT, exist_ok=True)
ref = np.load(HERE + "/reference.npz")
img, want = ref["input"], ref["output"]
H, W = want.shape
cv2.imwrite(OUT + "/input.tif", cv2.cvtColor(np.ascontiguousarray(img.transpose(1, 2, 0)), cv2.COLOR_RGB2BGR))
res = {"mode": mode, "nuke": nuke.NUKE_VERSION_STRING}
nuke.root()["format"].setValue("HD_720")
cat = OUT + "/softkey.catnc"                  # Non-commercial writes and reads .catnc (measured)
if not os.path.exists(cat):
    c = nuke.nodes.CatFileCreator()
    c["torchScriptFile"].setValue(HERE + "/softkey.pt")
    c["catFile"].setValue(cat)
    c["channelsIn"].setValue("rgba.red,rgba.green,rgba.blue")
    c["channelsOut"].setValue("rgba.alpha")
    c["modelId"].setValue("st_roto_softkey_test")
    t0 = time.time()
    try:
        nuke.execute(c, nuke.FrameRanges([1]))                   # what the node's own 'create' button runs
    except Exception as e:
        res["create_error"] = "%s: %s" % (type(e).__name__, e)
    res["create_s"] = round(time.time() - t0, 2)
res["cat_exists"] = os.path.exists(cat)
if res["cat_exists"]:
    rd = nuke.nodes.Read(file=OUT + "/input.tif")
    rd["raw"].setValue(True)                                   # no colour conversion: same numbers as PyTorch
    inf = nuke.nodes.Inference(modelFile=cat)
    inf["halfPrecision"].setValue(False)
    inf.setInput(0, rd)
    w = nuke.nodes.Write(file=OUT + "/result_%s.####.tif" % mode, file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, inf)
    times = []
    for k in range(4):
        nuke.memory("free") if hasattr(nuke, "memory") else None
        t0 = time.time(); nuke.execute(w, 1, 1); times.append(time.time() - t0)
        rd["reload"].execute() if "reload" in rd.knobs() else None
    got = cv2.imread(OUT + "/result_%s.0001.tif" % mode, cv2.IMREAD_UNCHANGED)
    got = got if got.ndim == 2 else got[:, :, -1]
    d = np.abs(got.astype(np.float32) - want)
    res.update({"render_s": [round(t, 3) for t in times], "max_abs_diff_vs_pytorch": float(d.max()),
                "mean_abs_diff": float(d.mean()), "interior_max_abs_diff": float(d[3:-3, 3:-3].max())})
json.dump(res, open(HERE + "/result_%s.json" % mode, "w"), indent=1)
print("ROUTE_A", json.dumps(res))
