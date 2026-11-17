"""REQ-140 (master prompt section 16): fully local operation, no telemetry, no automatic transmission.

Static guard over the product code (`src/`, `nuke_plugin/`): no network module may be imported, except `socket`
in `st_roto/persistence.py`, which may only call `socket.gethostname()` (local: the session marker records which
machine holds the project). ONNX Runtime's Windows telemetry must be switched off where ORT is imported.
The behavioural evidence (no socket/DNS/HTTP use during a full workflow inside Nuke, OS connection table) is
`tests/nuke/run_nuke_tests.py::test_offline_no_network` and `tools/offline/watch_network.py` (T-085).
"""
import ast
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
PRODUCT = [os.path.join(ROOT, "src"), os.path.join(ROOT, "nuke_plugin")]
NETWORK = ("socket", "ssl", "http", "urllib", "urllib2", "urllib3", "requests", "httpx", "aiohttp", "ftplib",
           "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "socketserver", "asyncio", "webbrowser",
           "huggingface_hub", "websocket", "websockets", "grpc", "paramiko", "zmq")
SOCKET_ALLOWED = {("persistence.py", "gethostname")}


def _python_files():
    for top in PRODUCT:
        for dp, _, fns in os.walk(top):
            for fn in fns:
                if fn.endswith(".py"):
                    yield os.path.join(dp, fn)


def _tree(path):
    return ast.parse(open(path, encoding="utf-8").read(), path)


def test_product_code_imports_no_network_module():
    bad = []
    for path in _python_files():
        fn = os.path.basename(path)
        for node in ast.walk(_tree(path)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "__import__":
                names = [a.value for a in node.args[:1] if isinstance(a, ast.Constant)]
            for n in names:
                top = n.split(".")[0]
                if top == "socket" and fn == "persistence.py":
                    continue                                    # attribute use checked below
                if top in NETWORK:
                    bad.append("%s: %s" % (os.path.relpath(path, ROOT), n))
    assert not bad, bad


def test_socket_only_used_for_hostname():
    used = set()
    for path in _python_files():
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Attribute) and getattr(node.value, "id", None) == "socket":
                used.add((os.path.basename(path), node.attr))
    assert used <= SOCKET_ALLOWED, used - SOCKET_ALLOWED


def test_onnxruntime_telemetry_disabled_where_imported():
    """Every product module importing onnxruntime must call disable_telemetry_events at module level."""
    importers, disabled = [], []
    for path in _python_files():
        tree = _tree(path)
        imports_ort = any(isinstance(n, ast.Import) and any(a.name.split(".")[0] == "onnxruntime" for a in n.names)
                          or isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "onnxruntime"
                          for n in ast.walk(tree))
        if not imports_ort:
            continue
        importers.append(path)
        top_calls = [n for stmt in tree.body for n in ast.walk(stmt)
                     if not isinstance(stmt, (ast.FunctionDef, ast.ClassDef))
                     and isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "disable_telemetry_events"]
        if top_calls:
            disabled.append(path)
    assert importers, "expected st_roto_ai.runtime to import onnxruntime"
    assert sorted(importers) == sorted(disabled)
