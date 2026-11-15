import sys, json, nuke
out = {"python": sys.version, "nuke": nuke.NUKE_VERSION_STRING}
for k in ("nc", "indie", "nukex", "studio", "hiero", "gui", "ple", "64bit", "ExecutablePath"):
    try:
        out["env." + k] = nuke.env.get(k)
    except Exception as e:
        out["env." + k] = "ERR " + repr(e)
# node retrieval cap probe
try:
    for i in range(15):
        nuke.nodes.NoOp(name="probe%d" % i)
    out["allNodes_after_15"] = len(nuke.allNodes())
except Exception as e:
    out["allNodes_err"] = repr(e)
for cls in ("Inference", "Roto", "RotoPaint", "CatFileCreator", "SmartVector", "Kronos"):
    try:
        n = nuke.createNode(cls, inpanel=False)
        out["create." + cls] = "ok"
        nuke.delete(n)
    except Exception as e:
        out["create." + cls] = "ERR " + repr(e)
try:
    import nuke.rotopaint as rp
    r = nuke.nodes.Roto()
    c = r["curves"]
    s = rp.Shape(c)
    for x, y in ((100, 100), (300, 100), (200, 300)):
        s.append(rp.ShapeControlPoint(x, y))
    c.rootLayer.append(s)
    out["rotopaint_shape"] = "ok, points=%d" % len(s)
except Exception as e:
    out["rotopaint_shape"] = "ERR " + repr(e)
for mod in ("numpy", "torch", "onnxruntime", "PySide6"):
    try:
        m = __import__(mod)
        out["import." + mod] = getattr(m, "__version__", "ok")
    except Exception as e:
        out["import." + mod] = "ERR " + repr(e)
print("PROBE_RESULT " + json.dumps(out, indent=1))
