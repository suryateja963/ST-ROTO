"""Record SHA-256 and size of every exported model file (models/onnx/<name>/**) in
models/manifests/<name>.exports.json, which IS committed. Run after export_sam2_onnx.py / export_sam2_video_onnx.py /
convert_fp16.py. The runtime refuses files that do not match (st_roto_ai.registry, T-056).

Usage:  .venv\\Scripts\\python.exe tools/models/register_exports.py sam2.1-hiera-tiny sam2.1-hiera-large
"""
import os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from st_roto_ai.registry import build_exports_manifest   # noqa: E402

TOOLS = "tools/models/export_sam2_onnx.py + export_sam2_video_onnx.py + convert_fp16.py"

if __name__ == "__main__":
    for name in sys.argv[1:]:
        t0 = time.time()
        m = build_exports_manifest(name, tool=TOOLS)
        print("%s: %d files, %.0f MB, %.1f s" % (name, len(m["files"]),
                                                 sum(f["bytes"] for f in m["files"].values()) / 1e6, time.time() - t0))
