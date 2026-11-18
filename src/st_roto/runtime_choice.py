"""Which ONNX Runtime build ST-ROTO loads into Nuke (T-116, REQ-020). Pure Python, no Nuke / ONNX Runtime import.

ST-ROTO ships two builds of ONNX Runtime, in separate folders, because both are the Python package `onnxruntime`
and only one can be imported per process:
* `.tools/nuke-py311`      onnxruntime-gpu 1.26.0: CUDA 12, NVIDIA GPUs (fastest there; uses Nuke's CUDA DLLs);
* `.tools/nuke-py311-dml`  onnxruntime-directml 1.24.4: DirectML, any DirectX 12 GPU (AMD, Intel, NVIDIA).
The choice is made once, when Nuke starts (nuke_plugin/init.py), from the environment variable ST_ROTO_RUNTIME:
  auto (default)  CUDA build if the NVIDIA driver is installed (nvcuda.dll present), else DirectML;
  cuda | directml force one build (e.g. directml on an NVIDIA machine whose driver is too old for CUDA 12).
Measured on an RTX 5060 Laptop (research/probes/2026-11-18_directml): the same masks (per-frame IoU DirectML vs CUDA
>= 0.997), DirectML 7-20 % slower, so CUDA stays first where it works."""
import os
import sys

BUILDS = ("cuda", "directml")
ENV = "ST_ROTO_RUNTIME"
ACTIVE_ENV, REASON_ENV = "ST_ROTO_RUNTIME_ACTIVE", "ST_ROTO_RUNTIME_REASON"
DML_DIR = os.path.join(".tools", "nuke-py311-dml")


def nvidia_driver_present():
    """True if the NVIDIA display driver's CUDA library is installed (Windows: System32\\nvcuda.dll). No process is
    started and nothing is loaded."""
    if sys.platform != "win32":
        return os.path.exists("/proc/driver/nvidia/version")
    sysroot = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    return os.path.exists(os.path.join(sysroot, "System32", "nvcuda.dll"))


def choose(setting, nvidia, dml_available):
    """-> (build, reason). setting: the ST_ROTO_RUNTIME value ('' = auto); nvidia: nvidia_driver_present();
    dml_available: the DirectML folder is installed. Never fails: an unusable request falls back with the reason."""
    s = (setting or "auto").strip().lower()
    if s not in BUILDS + ("auto",):
        return (("directml", "ST_ROTO_RUNTIME=%r is not one of auto/cuda/directml; using auto: DirectML (no NVIDIA "
                 "driver)" % setting) if not nvidia and dml_available else
                ("cuda", "ST_ROTO_RUNTIME=%r is not one of auto/cuda/directml; using auto: CUDA" % setting))
    if s == "cuda":
        return "cuda", "ST_ROTO_RUNTIME=cuda"
    if s == "directml":
        if dml_available:
            return "directml", "ST_ROTO_RUNTIME=directml"
        return "cuda", "ST_ROTO_RUNTIME=directml but the DirectML runtime is not installed (%s): using CUDA" % DML_DIR
    if nvidia:
        return "cuda", "auto: NVIDIA driver found (CUDA build)"
    if dml_available:
        return "directml", "auto: no NVIDIA driver, DirectML build (AMD / Intel / other DirectX 12 GPUs)"
    return "cuda", "auto: no NVIDIA driver and no DirectML runtime installed: the AI runs on the CPU"


def site_dirs(root, build):
    """Folders to append to sys.path, in order: the chosen build's onnxruntime must come before the CUDA folder
    (which also holds numpy, OpenCV, OpenEXR used by both)."""
    base = os.path.join(root, ".tools", "nuke-py311")
    return ([os.path.join(root, DML_DIR)] if build == "directml" else []) + [base]


def active():
    """(build, reason) chosen at Nuke start-up, or (None, '') outside the plugin."""
    return os.environ.get(ACTIVE_ENV) or None, os.environ.get(REASON_ENV, "")
