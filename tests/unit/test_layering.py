"""Architecture guard (D-026, master prompt section 3): the core must not depend on Nuke, Qt or any AI runtime,
so traditional roto keeps working with AI disabled and the core stays testable outside Nuke."""
import ast
import os

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
CORE = os.path.join(SRC, "st_roto")
FORBIDDEN = ("nuke", "PySide2", "PySide6", "PyQt5", "PyQt6", "onnxruntime", "torch", "transformers", "tensorrt")


def test_core_has_no_host_or_ai_imports():
    assert not _violations(CORE, FORBIDDEN)


def test_ai_layer_has_no_host_imports():
    """AI layer may use onnxruntime, never Nuke or Qt (ADR-0001/0003: host specifics live in st_roto_nuke)."""
    assert not _violations(os.path.join(SRC, "st_roto_ai"), ("nuke", "PySide2", "PySide6", "PyQt5", "PyQt6", "torch"))


def _violations(root, forbidden):
    bad = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dp, fn)
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module]
                bad += ["%s: %s" % (fn, n) for n in names if n.split(".")[0] in forbidden]
    return bad
