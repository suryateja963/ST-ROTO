# ST-ROTO development plugin entry (pre-alpha). Loaded by Nuke when this folder is on the plugin path.
# Adds the ST-ROTO source and the bundled Python packages (onnxruntime-gpu 1.26.0, numpy, opencv) to sys.path.
# The installer (Phase 8) will replace this development layout.
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_SITE = os.path.join(_ROOT, ".tools", "nuke-py311")       # cp311 packages for Nuke 17.x only (pins: research/probes/2026-11-15_gpu_ort)
if os.path.isdir(_SITE) and _SITE not in sys.path:
    sys.path.append(_SITE)                                 # appended: Nuke's own packages keep priority
