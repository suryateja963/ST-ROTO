"""T-116: choice of the ONNX Runtime build (CUDA / DirectML) and how the capability report and the memory-aware
model choice treat DirectML."""
import os

from st_roto import capabilities as cap
from st_roto import runtime_choice as rc


def test_auto_prefers_cuda_with_an_nvidia_driver():
    assert rc.choose("", nvidia=True, dml_available=True)[0] == "cuda"
    assert rc.choose("auto", nvidia=True, dml_available=False)[0] == "cuda"


def test_auto_uses_directml_without_nvidia():
    b, why = rc.choose("", nvidia=False, dml_available=True)
    assert b == "directml" and "AMD / Intel" in why
    b, why = rc.choose("", nvidia=False, dml_available=False)          # nothing usable: CPU, and it says so
    assert b == "cuda" and "CPU" in why


def test_forced_choices_and_bad_values():
    assert rc.choose("DirectML", nvidia=True, dml_available=True) == ("directml", "ST_ROTO_RUNTIME=directml")
    assert rc.choose("cuda", nvidia=False, dml_available=True)[0] == "cuda"
    b, why = rc.choose("directml", nvidia=True, dml_available=False)
    assert b == "cuda" and "not installed" in why
    b, why = rc.choose("rocm", nvidia=False, dml_available=True)
    assert b == "directml" and "not one of" in why


def test_site_dirs_put_the_directml_build_first():
    root = os.path.join("R")
    assert rc.site_dirs(root, "cuda") == [os.path.join(root, ".tools", "nuke-py311")]
    assert rc.site_dirs(root, "directml") == [os.path.join(root, ".tools", "nuke-py311-dml"),
                                              os.path.join(root, ".tools", "nuke-py311")]


def _facts(**kw):
    f = {"edition": "nc", "models": {"sam2.1-hiera-tiny": True, "sam2.1-hiera-large": True}, "gpus": [],
         "gpu_error": "nvidia-smi not available", "providers": ["directml", "cpu"],
         "ort_build_reason": "auto: no NVIDIA driver", "adapters": ["AMD Radeon RX 7600"]}
    f.update(kw)
    return f


def test_report_shows_directml_and_its_memory_needs():
    gpu = [x for x in cap.evaluate(_facts()) if x["feature"].startswith("GPU acceleration")][0]
    assert gpu["feature"] == "GPU acceleration (DirectML)" and gpu["status"] == cap.AVAILABLE
    assert "AMD Radeon RX 7600" in gpu["reason"] and "2556" in gpu["reason"] and "4299" in gpu["reason"]
    none = [x for x in cap.evaluate(_facts(providers=["cpu"])) if x["feature"].startswith("GPU acceleration")][0]
    assert none["status"] == cap.UNAVAILABLE and "ST_ROTO_RUNTIME=directml" in none["fix"]


def test_plan_model_uses_the_directml_needs_when_given():
    present = {"sam2.1-hiera-tiny": True, "sam2.1-hiera-large": True}
    # 5,000 MiB free: large does not fit the CUDA need (~7,132) but fits the DirectML one (~4,514)
    assert cap.plan_model("auto", "auto", 5000, present)[0] == "sam2.1-hiera-tiny"
    assert cap.plan_model("auto", "auto", 5000, present, needs=cap.DML_VRAM_MIB)[0] == "sam2.1-hiera-large"
    m, d, note = cap.plan_model("auto", "auto", None, present, needs=cap.DML_VRAM_MIB)   # AMD/Intel: unknown free
    assert m == "sam2.1-hiera-tiny" and d == "auto"


def test_display_adapters_never_raises():
    assert isinstance(cap.display_adapters(), list)
