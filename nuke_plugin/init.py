# ST-ROTO plugin entry. Loaded by Nuke when this folder is on the plugin path (the setup adds it to .nuke/init.py).
# Adds the ST-ROTO source and the bundled Python packages to sys.path. Two ONNX Runtime builds are shipped
# (T-116): onnxruntime-gpu 1.26.0 (CUDA, NVIDIA) in .tools/nuke-py311 and onnxruntime-directml 1.24.4 (AMD / Intel /
# any DirectX 12 GPU) in .tools/nuke-py311-dml; st_roto.runtime_choice picks one per Nuke session
# (environment variable ST_ROTO_RUNTIME = auto | cuda | directml).
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from st_roto import runtime_choice as _rc
    _build, _why = _rc.choose(os.environ.get(_rc.ENV, ""), _rc.nvidia_driver_present(),
                              os.path.isdir(os.path.join(_ROOT, _rc.DML_DIR)))
    _sites = _rc.site_dirs(_ROOT, _build)
    os.environ[_rc.ACTIVE_ENV], os.environ[_rc.REASON_ENV] = _build, _why
except Exception as _e:                                     # noqa: BLE001 - never stop Nuke from starting
    _sites = [os.path.join(_ROOT, ".tools", "nuke-py311")]
    os.environ["ST_ROTO_RUNTIME_ACTIVE"], os.environ["ST_ROTO_RUNTIME_REASON"] = "cuda", "runtime choice failed: %s" % _e
for _site in _sites:                                        # cp311 packages for Nuke 16/17 (Python 3.11)
    if os.path.isdir(_site) and _site not in sys.path:
        sys.path.append(_site)                              # appended: Nuke's own packages keep priority
