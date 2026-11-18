"""T-125: docs/API_REFERENCE.md is generated from the source and must stay in step with it."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.mark.skipif(sys.version_info < (3, 9), reason="the generator uses ast.unparse (Python 3.9+)")
def test_api_reference_is_up_to_date():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "docs", "build_api_reference.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_manual_and_guides_exist_and_link_each_other():
    docs = {n: open(os.path.join(ROOT, "docs", n), encoding="utf-8").read()
            for n in ("MANUAL.md", "DEVELOPER_GUIDE.md", "INSTALL.md", "API_REFERENCE.md")}
    assert "docs/INSTALL.md" in docs["MANUAL.md"] and "docs/API_REFERENCE.md" in docs["DEVELOPER_GUIDE.md"]
