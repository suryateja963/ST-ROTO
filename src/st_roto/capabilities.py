"""Hardware detection and capability report (REQ-020 / REQ-022, master prompt section 4: "report when a feature is
unavailable due to hardware, driver, edition or API"). T-091.

Pure Python, no Nuke / Qt / AI imports (layering rule). Two parts:
* probes of the machine that need no host: `gpu_info()` (local `nvidia-smi`, no network), `ram_info()`;
* `evaluate(facts)`: turns a facts dict (gathered by the host adapter, st_roto_nuke.capabilities) into a list of
  features, each "available", "limited" or "unavailable" with the reason and what would change it.

Edition limits marked "measured" were measured in this project (research/probes); others are from Foundry's
documentation and marked as such (docs/PHASE1_DISCOVERY_REPORT.md).
"""
import os
import subprocess
import sys

AVAILABLE, LIMITED, UNAVAILABLE = "available", "limited", "unavailable"

# Nuke edition limits. Values not measured here are None (unknown) or labelled "docs".
EDITION_LIMITS = {
    "nc": {"label": "Nuke Non-commercial", "render_max": (1920, 1080), "render_source": "measured (T-089)",
           "python_nodes": 10, "python_nodes_source": "measured", "cpp_plugins": False, "plugins_source": "docs"},
    "indie": {"label": "Nuke Indie", "render_max": None, "render_source": "not measured",
              "python_nodes": 10, "python_nodes_source": "docs", "cpp_plugins": False, "plugins_source": "docs"},
    "commercial": {"label": "Nuke / NukeX / Nuke Studio", "render_max": None, "render_source": "no limit",
                   "python_nodes": None, "python_nodes_source": "no limit", "cpp_plugins": True,
                   "plugins_source": "docs"},
}

# Peak GPU memory of a Track (MiB above the idle baseline, CUDA context included), measured by T-092 on an RTX 5060
# Laptop 8 GB in Nuke 17.1 (research/probes/2026-11-17_vram): the same for 1 and 2 objects; SAM 2.1 works at
# 1024x1024 internally, so the plate size matters little (720p measured).
MODEL_VRAM_MIB = {"sam2.1-hiera-tiny": 3730, "sam2.1-hiera-large": 6793}
VRAM_MARGIN = 1.05
# The same peaks with the DirectML build (T-116, measured on the same GPU: research/probes/2026-11-18_directml). Free
# memory of non-NVIDIA GPUs cannot be read here, so these are reported, not used for 'auto'.
DML_VRAM_MIB = {"sam2.1-hiera-tiny": 2556, "sam2.1-hiera-large": 4299}


def vram_need(model, needs=None):
    """MiB of free GPU memory required before running `model` on the GPU (measured peak + 5 %), or None.
    needs: the peak table (default MODEL_VRAM_MIB = CUDA; DML_VRAM_MIB for the DirectML build)."""
    v = (MODEL_VRAM_MIB if needs is None else needs).get(model)
    return None if v is None else int(v * VRAM_MARGIN)


def plan_model(choice, device, free_mib, present, loaded=(), auto_choice="auto", needs=None):
    """Memory-aware model/device choice (T-092, REQ-021). Pure.
    choice: a model name or `auto_choice`; device: "auto" | "cuda" | "cpu"; free_mib: free GPU memory or None
    (no NVIDIA GPU / unknown); present: {model: installed}; loaded: models whose sessions are already on the GPU
    (they need no new memory); needs: peak table (vram_need). Returns (model, device, note). Never silently swaps a model the artist chose:
    if it does not fit, it runs on the CPU and the note says so (and suggests the smaller model)."""
    order = ("sam2.1-hiera-large", "sam2.1-hiera-tiny")

    def fits(m):
        need = vram_need(m, needs)
        return m in loaded or need is None or (free_mib is not None and free_mib >= need)
    if choice == auto_choice:
        if device == "cpu" or free_mib is None:
            m = "sam2.1-hiera-tiny" if present.get("sam2.1-hiera-tiny") else "sam2.1-hiera-large"
            return m, device, "auto model: %s (no GPU memory to choose by)" % m
        for m in order:
            if present.get(m) and fits(m):
                return m, device, "auto model: %s (%d MiB GPU memory free, needs ~%s)" % (
                    m, free_mib, "0 more: already loaded" if m in loaded else vram_need(m, needs))
        m = "sam2.1-hiera-tiny" if present.get("sam2.1-hiera-tiny") else "sam2.1-hiera-large"
        return m, "cpu", ("auto model: not enough free GPU memory (%d MiB free, %s needs ~%d): running on the CPU, "
                          "much slower; close GPU-heavy programs to use the GPU" % (free_mib, m, vram_need(m, needs)))
    if device == "cpu" or free_mib is None or fits(choice):
        return choice, device, ""
    note = ("%s needs ~%d MiB of free GPU memory, %d MiB free: running on the CPU, much slower"
            % (choice, vram_need(choice, needs), free_mib))
    small = "sam2.1-hiera-tiny"
    if choice != small and present.get(small) and fits(small):
        note += "; '%s' fits on the GPU" % small
    return choice, "cpu", note

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW: no console flash in the GUI


def gpu_info(timeout=10):
    """NVIDIA GPUs via the local `nvidia-smi` (ships with the driver; no network). Returns
    {"gpus": [{"index", "name", "total_mib", "used_mib", "free_mib", "driver"}], "error": str or None}.
    Other vendors are not detected here (no AMD/Intel query tool assumed); their absence is reported, not hidden."""
    cmd = ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,driver_version",
           "--format=csv,noheader,nounits"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        return {"gpus": [], "error": "nvidia-smi not available (%s): no NVIDIA driver, or another GPU vendor"
                % type(e).__name__}
    if out.returncode != 0:
        return {"gpus": [], "error": "nvidia-smi failed: %s" % (out.stderr or out.stdout).strip()[:200]}
    return {"gpus": parse_nvidia_smi(out.stdout), "error": None}


def display_adapters():
    """Names of the display adapters Windows knows (any vendor: AMD, Intel, NVIDIA...), via user32
    EnumDisplayDevicesW (no process, no network). [] elsewhere or if unknown. Memory is not available this way."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                        ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                        ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]
        names, i = [], 0
        while i < 32:
            d = DISPLAY_DEVICEW()
            d.cb = ctypes.sizeof(d)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
                break
            if d.DeviceString and d.DeviceString not in names:
                names.append(d.DeviceString)
            i += 1
        return names
    except Exception:                                         # noqa: BLE001 - a report fact, never an error
        return []


def parse_nvidia_smi(text):
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            gpus.append({"index": int(parts[0]), "name": parts[1], "total_mib": int(float(parts[2])),
                         "used_mib": int(float(parts[3])), "free_mib": int(float(parts[4])), "driver": parts[5]})
        except ValueError:
            continue
    return gpus


def ram_info():
    """{"total_mib", "available_mib"} of system RAM, or {} if unknown."""
    if sys.platform == "win32":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return {"total_mib": st.ullTotalPhys // 2 ** 20, "available_mib": st.ullAvailPhys // 2 ** 20}
        return {}
    try:
        info = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) // 1024
        return {"total_mib": info.get("MemTotal"), "available_mib": info.get("MemAvailable")}
    except (OSError, ValueError):
        return {}


def _feature(name, status, reason, fix=""):
    return {"feature": name, "status": status, "reason": reason, "fix": fix}


def evaluate(f):
    """facts -> [feature dicts]. Expected keys (missing ones count as unknown / absent):
    edition ("nc" | "indie" | "commercial"), nuke_version, ai_disabled (reason or None), ai_runtime_problem (reason
    or None), providers ([...] e.g. ["cuda", "cpu"]), gpus (gpu_info()["gpus"]), gpu_error, models ({name: bool}),
    ocio (bool), signing_keys (int)."""
    lim = EDITION_LIMITS.get(f.get("edition"), EDITION_LIMITS["commercial"])
    out = [_feature("Traditional roto (draw/edit shapes, save, mattes, export, packages)", AVAILABLE,
                    "needs no AI and no GPU (REQ-010, T-088)")]
    models = f.get("models") or {}
    gpus = f.get("gpus") or []
    cuda = "cuda" in (f.get("providers") or [])
    have_tracker = models.get("sam2.1-hiera-tiny") or models.get("sam2.1-hiera-large")
    # AI tracking
    if f.get("ai_disabled"):
        out.append(_feature("AI tracking (SAM 2.1)", UNAVAILABLE, f["ai_disabled"], "untick 'disable AI' / unset ST_ROTO_AI"))
    elif f.get("ai_runtime_problem"):
        out.append(_feature("AI tracking (SAM 2.1)", UNAVAILABLE, f["ai_runtime_problem"],
                            "install ST-ROTO's AI packages (onnxruntime-gpu 1.26.0)"))
    elif not have_tracker:
        out.append(_feature("AI tracking (SAM 2.1)", UNAVAILABLE, "no exported SAM 2.1 model found",
                            "tools/models/download_models.py + export_sam2_video_onnx.py (owner-approved models)"))
    else:
        out.append(_feature("AI tracking (SAM 2.1)", AVAILABLE, "models: %s" % ", ".join(sorted(k for k, v in models.items()
                                                                                      if v and k.startswith("sam2")))))
    # GPU acceleration
    ai_ok = not f.get("ai_disabled") and not f.get("ai_runtime_problem") and have_tracker
    if not ai_ok:
        pass
    elif cuda and gpus:
        g = gpus[0]
        out.append(_feature("GPU acceleration (CUDA)", AVAILABLE, "%s, %d MiB (%d MiB free), driver %s"
                            % (g["name"], g["total_mib"], g["free_mib"], g["driver"])))
    elif cuda:
        out.append(_feature("GPU acceleration (CUDA)", LIMITED, "CUDA build installed but no NVIDIA GPU reported (%s)"
                            % (f.get("gpu_error") or "nvidia-smi listed none"),
                            "check the NVIDIA driver, or start Nuke with ST_ROTO_RUNTIME=directml"))
    elif "directml" in (f.get("providers") or []):
        out.append(_feature("GPU acceleration (DirectML)", AVAILABLE,
                            "%s; display adapters: %s. Free GPU memory cannot be read for DirectML, so model 'auto' "
                            "uses the tiny model; choose the large one yourself if your GPU has enough memory (measured "
                            "DirectML peaks: tiny %d MiB, large %d MiB)"
                            % (f.get("ort_build_reason") or "DirectML build", ", ".join(f.get("adapters") or [])
                               or "unknown", DML_VRAM_MIB["sam2.1-hiera-tiny"], DML_VRAM_MIB["sam2.1-hiera-large"])))
    else:
        out.append(_feature("GPU acceleration", UNAVAILABLE, "this ONNX Runtime build has no GPU provider for this "
                            "machine (%s; display adapters: %s); AI runs on the CPU, much slower"
                            % (f.get("ort_build_reason") or "build unknown", ", ".join(f.get("adapters") or [])
                               or "unknown"),
                            "NVIDIA GPU + CUDA 12 driver, or a DirectX 12 GPU with ST_ROTO_RUNTIME=directml"))
    # model fit in VRAM
    if ai_ok and cuda and gpus:
        for name, need in sorted(MODEL_VRAM_MIB.items()):
            if not models.get(name):
                continue
            if need is None:
                out.append(_feature("%s on this GPU" % name, AVAILABLE, "memory need not measured yet"))
            elif gpus[0]["total_mib"] < need:
                out.append(_feature("%s on this GPU" % name, UNAVAILABLE, "needs ~%d MiB, GPU has %d MiB"
                                    % (need, gpus[0]["total_mib"]), "use the tiny model or the CPU"))
            elif gpus[0]["free_mib"] < need:
                out.append(_feature("%s on this GPU" % name, LIMITED, "needs ~%d MiB, %d MiB free now (other "
                                    "programs use the GPU)" % (need, gpus[0]["free_mib"]), "close GPU-heavy programs"))
            else:
                out.append(_feature("%s on this GPU" % name, AVAILABLE, "needs ~%d MiB, %d MiB free"
                                    % (need, gpus[0]["free_mib"])))
    # learned matting
    if models.get("vitmatte-small-composition-1k") and ai_ok:
        out.append(_feature("ViTMatte-S edges (optional)", AVAILABLE, "installed (D-032; training-data caveat applies)"))
    else:
        why = "AI unavailable" if not ai_ok else "optional model not installed (D-032)"
        out.append(_feature("ViTMatte-S edges (optional)", UNAVAILABLE, why,
                            "tools/models/download_models.py vitmatte-small-composition-1k" if ai_ok else ""))
    # edition limits
    rm = lim["render_max"]
    if rm:
        out.append(_feature("Tracking plates above %dx%d" % rm, LIMITED, "%s renders at most %dx%d (%s): the AI sees "
                            "frames reduced to fit; shapes stay full resolution" % ((lim["label"],) + rm
                                                                                    + (lim["render_source"],)),
                            "commercial Nuke"))
        out.append(_feature("Rendering ST_Roto output above %dx%d" % rm, UNAVAILABLE, "%s render limit" % lim["label"],
                            "commercial Nuke"))
        out.append(_feature("EXR mattes", AVAILABLE, "default size 'fit %dx%d' in this edition (D-041); full "
                            "resolution selectable" % rm))
    else:
        out.append(_feature("Full-resolution rendering and mattes", AVAILABLE if f.get("edition") == "commercial"
                            else LIMITED, "render limit: %s" % lim["render_source"]))
    if lim["python_nodes"]:
        out.append(_feature("Python node access", LIMITED, "%s: %d nodes per session (%s); ST-ROTO works as one node"
                            % (lim["label"], lim["python_nodes"], lim["python_nodes_source"]),
                            "save and reopen the script if Nuke reports the limit"))
    out.append(_feature("C++ plug-ins (in-process inference, Deep)", AVAILABLE if lim["cpp_plugins"] else UNAVAILABLE,
                        "%s %s C++ plug-ins (%s)" % (lim["label"], "loads" if lim["cpp_plugins"] else "does not load",
                                                     lim["plugins_source"]),
                        "" if lim["cpp_plugins"] else "plug-in-capable licence (D-011)"))
    out.append(_feature("OCIO colour management", AVAILABLE if f.get("ocio") else LIMITED,
                        "script uses OCIO" if f.get("ocio") else "script uses Nuke's default colour management; AI "
                        "input colour 'auto' follows it"))
    keys = f.get("signing_keys") or 0
    out.append(_feature("Collaboration (leases, signed changes)", LIMITED,
                        "core prototype only; %d signing key(s) on this machine" % keys, "Nuke UI: T-093 (planned)"))
    return out


def report_text(facts, features):
    """Plain-text report for the artist / a support request."""
    lines = ["ST-ROTO system report", "",
             "Nuke: %s (%s)" % (facts.get("nuke_version", "?"),
                                EDITION_LIMITS.get(facts.get("edition"), {}).get("label", facts.get("edition", "?")))]
    for g in facts.get("gpus") or []:
        lines.append("GPU %d: %s, %d MiB total, %d MiB free, driver %s" % (g["index"], g["name"], g["total_mib"],
                                                                         g["free_mib"], g["driver"]))
    if not facts.get("gpus"):
        lines.append("GPU: none detected (%s)" % (facts.get("gpu_error") or "no NVIDIA GPU"))
    ram = facts.get("ram") or {}
    if ram:
        lines.append("RAM: %d MiB total, %d MiB available" % (ram["total_mib"], ram["available_mib"]))
    lines.append("AI runtime: %s" % (facts.get("ai_runtime_problem") or "ONNX Runtime %s, providers %s"
                                     % (facts.get("ort_version", "?"), ", ".join(facts.get("providers") or []))))
    lines.append("")
    mark = {AVAILABLE: "[ok]     ", LIMITED: "[limited]", UNAVAILABLE: "[no]     "}
    for x in features:
        lines.append("%s %s - %s%s" % (mark[x["status"]], x["feature"], x["reason"],
                                       ("  -> " + x["fix"]) if x["fix"] and x["status"] != AVAILABLE else ""))
    return "\n".join(lines)


def signing_key_count(folder=None):
    """Number of private signing keys in the D-038 key folder (no key content is read)."""
    if folder is None:
        from .signing import key_dir
        folder = key_dir()
    try:
        return len([n for n in os.listdir(folder) if n.endswith(".strotokey")])
    except OSError:
        return 0
