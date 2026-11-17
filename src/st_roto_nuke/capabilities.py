"""Nuke side of the capability report (T-091, REQ-020/022): gathers the facts st_roto.capabilities.evaluate needs.
Never raises: every probe that fails is reported as a fact ("unknown"), because this report is what an artist sends
when something does not work. Imports no AI module unless the AI is enabled (it then loads st_roto_ai.runtime, which
switches ONNX Runtime telemetry off)."""
from __future__ import annotations

import os

import nuke

from st_roto import capabilities as cap


def edition() -> str:
    env = getattr(nuke, "env", {}) or {}
    if env.get("nc"):
        return "nc"
    if env.get("indie"):
        return "indie"
    return "commercial"


def facts(group=None) -> dict:
    from .track import models_root
    from . import node as stnode
    f = {"nuke_version": getattr(nuke, "NUKE_VERSION_STRING", "?"), "edition": edition()}
    gi = cap.gpu_info()
    f["gpus"], f["gpu_error"] = gi["gpus"], gi["error"]
    f["ram"] = cap.ram_info()
    f["ai_disabled"] = stnode.ai_disabled_reason(group) if group is not None else _env_ai_off()
    f["ai_runtime_problem"] = None
    if not f["ai_disabled"]:
        f["ai_runtime_problem"] = stnode.ai_runtime_problem()
        if not f["ai_runtime_problem"]:
            from st_roto_ai import runtime
            f["providers"] = runtime.available_devices()
            f["ort_version"] = runtime.ort.__version__
    root = models_root()
    f["models"] = {"sam2.1-hiera-tiny": os.path.exists(os.path.join(root, "sam2.1-hiera-tiny", "video")),
                   "sam2.1-hiera-large": os.path.exists(os.path.join(root, "sam2.1-hiera-large", "video")),
                   "vitmatte-small-composition-1k": _vitmatte_present(root)}
    try:
        f["ocio"] = nuke.root()["colorManagement"].value() == "OCIO"
    except Exception:                                         # noqa: BLE001
        f["ocio"] = False
    f["signing_keys"] = cap.signing_key_count()
    return f


def _env_ai_off():
    v = os.environ.get("ST_ROTO_AI", "").strip().lower()
    return ("AI is switched off for this Nuke session (ST_ROTO_AI=%s)" % os.environ.get("ST_ROTO_AI")
            if v in ("0", "off", "false", "no", "disabled") else None)


def _vitmatte_present(root):
    d = os.path.join(root, "vitmatte-small-composition-1k")
    return os.path.isdir(d) and any(n.endswith(".onnx") for n in os.listdir(d))


def report(group=None):
    """-> (facts, features, text)."""
    f = facts(group)
    feats = cap.evaluate(f)
    return f, feats, cap.report_text(f, feats)


def show_report(group=None):
    """Button / menu entry: the report in a dialog (GUI) or printed (headless); the summary goes to the node's
    status line."""
    try:
        f, feats, text = report(group)
    except Exception as e:                                    # noqa: BLE001 - the report must never crash Nuke
        text = "ST-ROTO system report failed: %s" % e
        feats = []
    if group is not None and "stroto_status" in group.knobs():
        n_lim = sum(1 for x in feats if x["status"] != cap.AVAILABLE)
        group["stroto_status"].setValue("system report: %d of %d features fully available, %d limited/unavailable "
                                        "(details in the dialog)" % (len(feats) - n_lim, len(feats), n_lim))
    if getattr(nuke, "GUI", False):
        nuke.message(text)
    else:
        print(text)
    return text
