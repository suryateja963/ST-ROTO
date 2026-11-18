"""Run every headless Nuke integration test in its own Nuke process and summarise.

Usage:  .venv\\Scripts\\python.exe tools/run_nuke_tests.py ["C:/Program Files/Nuke17.1v3/Nuke17.1.exe"]
Each test runs in a separate process because Nuke Non-commercial limits Python to 10 Node objects per session.
"""
import ast, json, os, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNNER = os.path.join(ROOT, "tests", "nuke", "run_nuke_tests.py")
OUT = os.path.join(ROOT, "tests", "nuke", "out")


def test_names():
    tree = ast.parse(open(RUNNER, encoding="utf-8").read())
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\Nuke17.1v3\Nuke17.1.exe"
    os.makedirs(OUT, exist_ok=True)
    summary, failed = {}, 0
    for name in test_names():
        log = open(os.path.join(OUT, "log_%s.txt" % name), "w")
        env = dict(os.environ)                     # one ONNX Runtime build per process (T-116): DirectML tests
        if "directml" in name:                     # get the DirectML build, every other test the default choice
            env["ST_ROTO_RUNTIME"] = "directml"
        else:
            env.pop("ST_ROTO_RUNTIME", None)
        rc = subprocess.call([exe, "--nc", "-t", RUNNER, name], stdout=log, stderr=subprocess.STDOUT, timeout=1800,
                             env=env)
        log.close()
        path = os.path.join(OUT, "results_%s.json" % name)
        res = json.load(open(path)).get(name, {}) if os.path.exists(path) else {"passed": False, "error": "no result"}
        summary[name] = {"passed": bool(res.get("passed")), "exit_code": rc}
        failed += 0 if res.get("passed") else 1
        print("%-40s %s" % (name, "PASS" if res.get("passed") else "FAIL"))
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print("failed:", failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
