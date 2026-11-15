"""Headless Nuke probe: (A) does the Inference node use the GPU, (B) can ONNX Runtime
CUDA run inside the Nuke process next to Nuke's own CUDA/cuDNN/libtorch.

Run:  Nuke17.1.exe --nc -t probe_gpu_ort.py <order>
  order = "inf_first" (Inference node then ORT) or "ort_first" (ORT then Inference node)
Stays under the Non-commercial 10-node Python cap (uses 4 nodes).
Requires onnxruntime-gpu 1.26.0 (last CUDA 12 build) in D:/ST-ROTO/.tools/nuke-py311.
"""
import json, os, subprocess, sys, threading, time
import nuke
import psutil

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
ORDER = sys.argv[1] if len(sys.argv) > 1 else "inf_first"
SITE = "D:/ST-ROTO/.tools/nuke-py311"
MODEL = HERE + "/test_conv.onnx"
CAT = "C:/Program Files/Nuke17.1v3/plugins/air/FnHumanMattingSmall.cat"
R = {"order": ORDER, "pid": os.getpid()}


class GpuSampler(threading.Thread):
    """Samples whole-GPU memory and utilisation every 0.25 s via nvidia-smi."""
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop = [], False
    def run(self):
        while not self.stop:
            try:
                o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                                    "--format=csv,noheader,nounits"], capture_output=True,
                                   text=True, timeout=5, creationflags=0x08000000).stdout.strip()
                m, u = [int(x) for x in o.split(",")]
                self.samples.append((m, u))
            except Exception:
                pass
            time.sleep(0.25)


def sampled(fn):
    s = GpuSampler(); s.start(); time.sleep(0.6)
    base = s.samples[-1] if s.samples else (None, None)
    t = time.time(); res = fn(); dt = time.time() - t
    time.sleep(0.6); s.stop = True; s.join()
    peak_m = max(x[0] for x in s.samples); peak_u = max(x[1] for x in s.samples)
    return res, {"seconds": round(dt, 3), "gpu_mem_base_MiB": base[0], "gpu_mem_peak_MiB": peak_m,
                 "gpu_util_peak_pct": peak_u, "n_samples": len(s.samples)}


def loaded_dlls(keys=("cudart", "cudnn64", "cudnn_cnn", "cublas", "torch_cuda", "onnxruntime", "nvrtc")):
    found = set()
    for mm in psutil.Process().memory_maps():
        p = mm.path.lower()
        if p.endswith(".dll") and any(k in os.path.basename(p) for k in keys):
            found.add(mm.path)
    return sorted(found)


# ---------------- A. Inference node ----------------
def test_inference():
    out = {}
    src = nuke.nodes.CheckerBoard2(format="HD_1080")
    noise = nuke.nodes.Noise()          # animated so every frame is a new input (defeats cache)
    noise.setInput(0, src)
    noise["zoffset"].setExpression("frame*0.37")
    inf = nuke.nodes.Inference(modelFile=CAT)
    inf.setInput(0, noise)
    w = nuke.nodes.Write(file=HERE + "/out/inf_####.exr", file_type="exr")
    w.setInput(0, inf)
    os.makedirs(HERE + "/out", exist_ok=True)
    # In terminal mode the GPU is controlled by Nuke's --gpu flag; the knob is read-only
    # from Python there, so we only record it. Compare runs launched with and without --gpu.
    out["knob_useGPUIfAvailable"] = inf["useGPUIfAvailable"].value()
    out["knob_enabled"] = inf["useGPUIfAvailable"].enabled()
    out["nuke_argv"] = sys.argv
    for label, (a, b) in (("run", (1, 6)),):
        nuke.clearRAMCache()
        _, st1 = sampled(lambda: nuke.execute(w, a, a))          # first frame (may include load)
        _, st = sampled(lambda: nuke.execute(w, a + 1, b))       # 5 further frames
        st["sec_per_frame"] = round(st["seconds"] / (b - a), 3)
        out[label] = {"first_frame": st1, "next_5_frames": st}
    out["dlls_after_inference"] = loaded_dlls()
    return out


# ---------------- B. ONNX Runtime in-process ----------------
def test_ort():
    out = {}
    sys.path.append(SITE)            # appended: Nuke's own packages keep priority
    import numpy as np
    import onnxruntime as ort
    out["ort_version"] = ort.__version__
    out["ort_file"] = ort.__file__
    out["numpy"] = np.__version__
    out["available_providers"] = ort.get_available_providers()
    x = np.random.default_rng(1).random((1, 3, 1080, 1920), dtype=np.float32)
    res = {}
    for name, provs in (("cuda", [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]),
                        ("cpu", ["CPUExecutionProvider"])):
        try:
            so = ort.SessionOptions(); so.log_severity_level = 2
            t = time.time(); sess = ort.InferenceSession(MODEL, so, providers=provs)
            load = time.time() - t
            sess.run(None, {"input": x})  # warm-up
            def run5():
                return [sess.run(None, {"input": x})[0] for _ in range(5)]
            ys, st = sampled(run5)
            st["sec_per_run"] = round(st["seconds"] / 5, 4)
            res[name] = {"active_providers": sess.get_providers(), "session_load_s": round(load, 3),
                         "runs": st, "out_mean": float(ys[-1].mean())}
            res[name]["_y"] = ys[-1]
        except Exception as e:
            res[name] = {"error": repr(e)}
    if "_y" in res.get("cuda", {}) and "_y" in res.get("cpu", {}):
        out["max_abs_diff_cuda_vs_cpu"] = float(abs(res["cuda"]["_y"] - res["cpu"]["_y"]).max())
    for v in res.values():
        v.pop("_y", None)
    out["sessions"] = res
    out["dlls_after_ort"] = loaded_dlls()
    return out


steps = [("A_inference", test_inference), ("B_ort", test_ort)]
if ORDER == "ort_first":
    steps.reverse()
elif ORDER.startswith("inf_only"):
    steps = steps[:1]
for name, fn in steps:
    try:
        R[name] = fn()
    except Exception as e:
        import traceback
        R[name] = {"error": repr(e), "trace": traceback.format_exc()}
R["nodes_used"] = len(nuke.allNodes())
with open(HERE + "/result_%s.json" % ORDER, "w") as f:
    json.dump(R, f, indent=1)
print("PROBE_DONE " + ORDER)
