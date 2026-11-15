"""Architecture guard (D-026, master prompt section 3): the core must not depend on Nuke, Qt or any AI runtime,
so traditional roto keeps working with AI disabled and the core stays testable outside Nuke."""
import ast
import os

CORE = os.path.join(os.path.dirname(__file__), "..", "..", "src", "st_roto")
FORBIDDEN = ("nuke", "PySide2", "PySide6", "PyQt5", "PyQt6", "onnxruntime", "torch", "transformers", "tensorrt")


def test_core_has_no_host_or_ai_imports():
    bad = []
    for dp, _, fns in os.walk(CORE):
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
                bad += ["%s: %s" % (fn, n) for n in names if n.split(".")[0] in FORBIDDEN]
    assert not bad, bad
