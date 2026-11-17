"""Capability report rules (T-091, REQ-020/022): every limited or unavailable feature carries its reason."""
from st_roto import capabilities as cap

SMI = ("0, NVIDIA GeForce RTX 5060 Laptop GPU, 8151, 1200, 6800, 621.24\n"
       "1, Some Other GPU, 4096, 0, 4096, 621.24\n")
GPU = cap.parse_nvidia_smi(SMI)
ALL_MODELS = {"sam2.1-hiera-tiny": True, "sam2.1-hiera-large": True, "vitmatte-small-composition-1k": True}


def by_name(features):
    return {x["feature"].split(" (")[0].split(" on ")[0]: x for x in features}


def test_parse_nvidia_smi():
    assert GPU[0] == {"index": 0, "name": "NVIDIA GeForce RTX 5060 Laptop GPU", "total_mib": 8151, "used_mib": 1200,
                      "free_mib": 6800, "driver": "621.24"}
    assert len(GPU) == 2 and cap.parse_nvidia_smi("garbage\n\n") == []


def test_full_featured_nc_machine():
    f = {"edition": "nc", "providers": ["cuda", "cpu"], "gpus": GPU, "models": ALL_MODELS, "ocio": False}
    feats = cap.evaluate(f)
    assert all(x["status"] in (cap.AVAILABLE, cap.LIMITED, cap.UNAVAILABLE) and x["reason"] for x in feats)
    st = {x["feature"]: x["status"] for x in feats}
    assert st["AI tracking (SAM 2.1)"] == cap.AVAILABLE
    assert st["GPU acceleration (CUDA)"] == cap.AVAILABLE
    assert st["Tracking plates above 1920x1080"] == cap.LIMITED
    assert st["Rendering ST_Roto output above 1920x1080"] == cap.UNAVAILABLE
    assert st["Python node access"] == cap.LIMITED
    assert st["C++ plug-ins (in-process inference, Deep)"] == cap.UNAVAILABLE
    nodes = [x for x in feats if x["feature"] == "Python node access"][0]
    assert "10 nodes per session" in nodes["reason"] and "measured" in nodes["reason"]


def test_ai_disabled_and_missing_runtime_explain_themselves():
    off = cap.evaluate({"edition": "commercial", "ai_disabled": "AI is disabled on this node", "models": ALL_MODELS})
    ai = [x for x in off if x["feature"].startswith("AI tracking")][0]
    assert ai["status"] == cap.UNAVAILABLE and "disabled" in ai["reason"] and ai["fix"]
    assert [x for x in off if x["feature"].startswith("Traditional")][0]["status"] == cap.AVAILABLE
    no_rt = cap.evaluate({"edition": "commercial", "ai_runtime_problem": "ONNX Runtime not installed",
                          "models": ALL_MODELS})
    ai = [x for x in no_rt if x["feature"].startswith("AI tracking")][0]
    assert ai["status"] == cap.UNAVAILABLE and "not installed" in ai["reason"]
    assert not [x for x in no_rt if x["feature"].startswith("GPU")]          # no GPU line when there is no AI


def test_cpu_only_machine_and_missing_models():
    feats = cap.evaluate({"edition": "commercial", "providers": ["cpu"], "gpus": [], "models": ALL_MODELS})
    gpu = [x for x in feats if x["feature"].startswith("GPU")][0]
    assert gpu["status"] == cap.UNAVAILABLE and "CPU" in gpu["reason"] and "DirectML" in gpu["reason"]
    none = cap.evaluate({"edition": "commercial", "providers": ["cuda"], "gpus": GPU, "models": {}})
    ai = [x for x in none if x["feature"].startswith("AI tracking")][0]
    assert ai["status"] == cap.UNAVAILABLE and "no exported SAM 2.1 model" in ai["reason"]


def test_vram_rule_uses_measured_need(monkeypatch):
    monkeypatch.setitem(cap.MODEL_VRAM_MIB, "sam2.1-hiera-large", 7000)
    monkeypatch.setitem(cap.MODEL_VRAM_MIB, "sam2.1-hiera-tiny", 3000)
    feats = cap.evaluate({"edition": "nc", "providers": ["cuda", "cpu"], "gpus": GPU, "models": ALL_MODELS})
    large = [x for x in feats if x["feature"] == "sam2.1-hiera-large on this GPU"][0]
    tiny = [x for x in feats if x["feature"] == "sam2.1-hiera-tiny on this GPU"][0]
    assert large["status"] == cap.LIMITED and "6800 MiB free" in large["reason"]        # fits the card, not right now
    assert tiny["status"] == cap.AVAILABLE


def test_report_text_and_probes_do_not_raise():
    f = {"edition": "nc", "nuke_version": "17.1v3", "providers": ["cuda", "cpu"], "gpus": GPU, "models": ALL_MODELS,
         "ram": {"total_mib": 16000, "available_mib": 6000}, "ort_version": "1.26.0"}
    text = cap.report_text(f, cap.evaluate(f))
    assert "Nuke Non-commercial" in text and "RTX 5060" in text and "[limited]" in text and "[no]" in text
    gi = cap.gpu_info()                                        # real machine: works or says why, never raises
    assert set(gi) == {"gpus", "error"} and (gi["gpus"] or gi["error"])
    ram = cap.ram_info()
    assert ram == {} or ram["total_mib"] > 0
