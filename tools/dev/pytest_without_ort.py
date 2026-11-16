"""Run the unit suite as CI sees it: ONNX Runtime (and other optional AI packages) NOT importable.
CI installs only requirements-dev.txt; a test module that imports onnxruntime at collection time breaks every job
(happened 2026-11-16..17, eight red commits). Run: .venv/Scripts/python.exe tools/dev/pytest_without_ort.py"""
import sys

for name in ("onnxruntime", "torch", "transformers"):
    sys.modules[name] = None                      # import raises ImportError, like a machine without the package

import pytest  # noqa: E402

sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "-rfs"] + sys.argv[1:]))
