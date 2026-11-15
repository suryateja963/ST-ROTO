import json, time, os, nuke
out = {}
SP = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
# 1. native Roto shape creation (node 1)
try:
    import nuke.rotopaint as rp
    r = nuke.nodes.Roto()
    c = r["curves"]
    s = rp.Shape(c)
    for x, y in ((100, 100), (300, 100), (200, 300)):
        s.append(rp.ShapeControlPoint(x, y))
    s.name = "STROTO_probe"
    c.rootLayer.append(s)
    nuke.saveToScript  # noqa
    out["rotopaint_shape"] = "ok points=%d name=%s" % (len(s), s.name)
except Exception as e:
    out["rotopaint_shape"] = "ERR " + repr(e)
# 2. Inference with Foundry's built-in matting .cat on GPU (nodes 2-4)
try:
    ck = nuke.nodes.CheckerBoard2(format="square_1K")
    inf = nuke.nodes.Inference(modelFile="C:/Program Files/Nuke17.1v3/plugins/air/FnHumanMattingSmall.cat")
    inf.setInput(0, ck)
    out["inference_knobs"] = sorted(k for k in inf.knobs().keys() if k in ("useGPUIfAvailable", "optimizeForSpeed", "halfPrecision", "modelFile"))
    w = nuke.nodes.Write(file=SP + "/probe_inf.exr", file_type="exr")
    w.setInput(0, inf)
    t = time.time(); nuke.execute(w, 1, 1); t1 = time.time() - t
    t = time.time(); nuke.execute(w, 2, 2); t2 = time.time() - t
    out["inference_exec_s"] = [round(t1, 2), round(t2, 2)]
    out["inference_output_exists"] = os.path.exists(SP + "/probe_inf.exr")
except Exception as e:
    out["inference"] = "ERR " + repr(e)
out["node_count"] = len(nuke.allNodes())
print("PROBE_RESULT " + json.dumps(out, indent=1))
