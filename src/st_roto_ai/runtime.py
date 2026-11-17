"""ONNX Runtime session creation with honest device reporting (ADR-0001, master prompt section 4).

ONNX Runtime silently falls back to CPU when a GPU provider cannot load (measured: onnxruntime-gpu built for
CUDA 13 inside Nuke 17.1's CUDA 12 process). `open_session` compares requested vs active providers and returns
a `DeviceReport` the UI must show to the artist.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import onnxruntime as ort

# REQ-140 (master prompt section 16: no telemetry). Official ONNX Runtime builds for Windows contain Microsoft's
# TraceLogging provider "Microsoft.ML.ONNXRuntime" (found in the bundled onnxruntime.dll, T-085) and emit usage
# events through ETW by default; Windows may forward them depending on the user's diagnostic-data settings.
# Switch them off before any session exists. Builds without telemetry lack the function: nothing to disable.
TELEMETRY_DISABLED = False
if hasattr(ort, "disable_telemetry_events"):
    ort.disable_telemetry_events()
    TELEMETRY_DISABLED = True


@dataclass
class DeviceReport:
    requested: str                      # "cuda", "directml", "cpu"
    active: str                         # what actually runs
    fallback: bool                      # True if active != requested
    reason: str = ""
    providers: list = field(default_factory=list)
    ort_version: str = ort.__version__


_PROVIDER = {"cuda": "CUDAExecutionProvider", "directml": "DmlExecutionProvider", "cpu": "CPUExecutionProvider"}

# CUDA EP options. Measured on an 8 GB laptop GPU inside Nuke (research/probes/2026-11-16_gui_stalls): with ORT
# defaults, GPU memory grew 5.3 -> 7.4 -> 7.8 GB over three Track runs in one Nuke session and the encoder became
# ~5x slower (pool rounding to powers of two + cuDNN exhaustive search workspaces for every new input shape).
#   Tried and REJECTED (probe results in that folder):
#   * "cudnn_conv_algo_search": "HEURISTIC" -> tracking ~15x slower, runs failed after 17 frames;
#   * "arena_extend_strategy": "kSameAsRequested" -> pool fragmentation: memory attention's ~470 MB attention
#     buffer could not be allocated, every run failed after 17 frames.
#   Kept: ORT defaults + arena shrinkage after runs (SHRINK_RUN_OPTIONS below).
CUDA_OPTIONS = {}


def shrink_run_options():
    """RunOptions that return unused CUDA pool memory to the driver at the end of a run (ORT run config
    'memory.enable_memory_arena_shrinkage'). Use for the large, variable-shape calls (memory attention)."""
    ro = ort.RunOptions()
    ro.add_run_config_entry("memory.enable_memory_arena_shrinkage", "gpu:0;cpu:0")
    return ro


def set_cuda_memory_limit(megabytes: int | None):
    """Per-session cap on ORT's CUDA memory pool (None = no cap). Used by hardware-aware routing (ADR-0007)."""
    if megabytes:
        CUDA_OPTIONS["gpu_mem_limit"] = str(int(megabytes) * 1024 * 1024)
    else:
        CUDA_OPTIONS.pop("gpu_mem_limit", None)


def available_devices() -> list:
    """Devices this ONNX Runtime build was compiled for (not a guarantee that they load)."""
    av = set(ort.get_available_providers())
    return [d for d, p in _PROVIDER.items() if p in av]


import os
import threading

_CACHE = {}
_CACHE_LOCK = threading.Lock()


def open_session(path: str, device: str = "auto", log_severity: int = 3, cache: bool = True):
    """Like `create_session`, but reuses a process-wide session for the same (file, device).

    Why: creating ONNX Runtime sessions holds Python's GIL; in Nuke's GUI this froze the UI for 0.9-1.3 s on every
    Track press (research/probes/2026-11-16_gui_stalls). Cached sessions make that a once-per-Nuke-session cost.
    ORT InferenceSession.run is safe to call from several threads.
    Every file is verified against the model registry first (st_roto_ai.registry, T-056).
    """
    key = (os.path.abspath(path), device, os.path.getmtime(path))
    if cache:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit is not None:
            return hit
    from .registry import verify_file          # licence/approval/checksum gate before any model file is loaded
    verify_file(path)
    res = create_session(path, device, log_severity)
    if cache:
        with _CACHE_LOCK:
            _CACHE[key] = res
    return res


def loaded_model_dirs():
    """Folders of model files whose sessions are cached (already holding GPU / CPU memory)."""
    with _CACHE_LOCK:
        return {os.path.dirname(k[0]) for k in _CACHE}


def is_out_of_memory(err) -> bool:
    """True if an exception from ONNX Runtime means the GPU ran out of memory (T-092)."""
    t = str(err).lower()
    return any(s in t for s in ("failed to allocate memory", "out of memory", "bfcarena", "cudaerrormemoryallocation",
                                "cuda failure 2"))


def clear_cache():
    """Release cached sessions (frees GPU memory; ADR-0009 GPU arbiter will call this under memory pressure)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def create_session(path: str, device: str = "auto", log_severity: int = 3):
    """Create an InferenceSession on `device` ("auto" = cuda, then directml, then cpu) and report what loaded."""
    order = [device] if device != "auto" else [d for d in ("cuda", "directml") if d in available_devices()] + ["cpu"]
    so = ort.SessionOptions()
    so.log_severity_level = log_severity
    requested = order[0]
    providers = [(_PROVIDER[d], dict(CUDA_OPTIONS)) if d == "cuda" else _PROVIDER[d] for d in order]
    if "CPUExecutionProvider" not in providers:
        providers.append("CPUExecutionProvider")
    sess = ort.InferenceSession(path, so, providers=providers)
    active_providers = sess.get_providers()
    active = next((d for d, p in _PROVIDER.items() if p == active_providers[0]), active_providers[0])
    report = DeviceReport(requested=requested, active=active, fallback=(active != requested),
                          providers=list(active_providers))
    if report.fallback:
        report.reason = ("%s was requested but could not be loaded by onnxruntime %s; running on %s. "
                         "Typical cause: the onnxruntime-gpu build does not match the CUDA version available "
                         "in this process." % (requested, ort.__version__, active))
    return sess, report
