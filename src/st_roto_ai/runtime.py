"""ONNX Runtime session creation with honest device reporting (ADR-0001, master prompt section 4).

ONNX Runtime silently falls back to CPU when a GPU provider cannot load (measured: onnxruntime-gpu built for
CUDA 13 inside Nuke 17.1's CUDA 12 process). `open_session` compares requested vs active providers and returns
a `DeviceReport` the UI must show to the artist.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import onnxruntime as ort


@dataclass
class DeviceReport:
    requested: str                      # "cuda", "directml", "cpu"
    active: str                         # what actually runs
    fallback: bool                      # True if active != requested
    reason: str = ""
    providers: list = field(default_factory=list)
    ort_version: str = ort.__version__


_PROVIDER = {"cuda": "CUDAExecutionProvider", "directml": "DmlExecutionProvider", "cpu": "CPUExecutionProvider"}


def available_devices() -> list:
    """Devices this ONNX Runtime build was compiled for (not a guarantee that they load)."""
    av = set(ort.get_available_providers())
    return [d for d, p in _PROVIDER.items() if p in av]


def open_session(path: str, device: str = "auto", log_severity: int = 3):
    """Create an InferenceSession on `device` ("auto" = cuda, then directml, then cpu) and report what loaded."""
    order = [device] if device != "auto" else [d for d in ("cuda", "directml") if d in available_devices()] + ["cpu"]
    so = ort.SessionOptions()
    so.log_severity_level = log_severity
    requested = order[0]
    providers = [_PROVIDER[d] for d in order]
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
