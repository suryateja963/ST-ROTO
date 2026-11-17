"""Acceptance run (T-104, REQ-280, master prompt section 30): every automatable verification in one command, with a
dated report. Each step maps to the acceptance criteria it supports (docs/ACCEPTANCE.md lists all 20 with their
status). Run with the project venv:
  .venv\\Scripts\\python.exe -I tools/acceptance/run_acceptance.py [--skip installer,gui,...]
Writes docs/acceptance/run_<UTC date>.json and .md. Nothing outside D:\\ST-ROTO is changed: the installer step uses
temporary folders under tmp/ and redirects only HOME for Nuke; the owner's real .nuke is checked afterwards.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
NUKE = r"C:\Program Files\Nuke17.1v3\Nuke17.1.exe"
NUKE_PY = r"C:\Program Files\Nuke17.1v3\python.exe"
GUI_PROBES = [  # (script, result json) - interactive Nuke, each exits by itself
    ("tests/nuke/gui_track_slice.py", "tests/nuke/out/gui_track_slice.json"),
    ("research/probes/2026-11-17_ai_off/gui_ai_toggle.py", "research/probes/2026-11-17_ai_off/result_gui_ai_toggle.json"),
    ("research/probes/2026-11-17_collab_ui/gui_panel_collab.py",
     "research/probes/2026-11-17_collab_ui/result_gui_panel_collab.json"),
    ("research/probes/2026-11-17_timeline/gui_timeline.py", "research/probes/2026-11-17_timeline/result_gui_timeline.json"),
    ("research/probes/2026-11-17_model_manager/gui_model_panel.py",
     "research/probes/2026-11-17_model_manager/result_gui_model_panel.json"),
    ("research/probes/2026-11-18_overlay/gui_review_overlay.py",
     "research/probes/2026-11-18_overlay/result_gui_review_overlay.json"),
    ("research/probes/2026-11-18_model_versions/gui_model_versions.py",
     "research/probes/2026-11-18_model_versions/result_gui_model_versions.json"),
]


def run(cmd, timeout=3600, env=None):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or ""), round(time.time() - t0, 1)


def step_unit():
    rc, out, sec = run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    tail = [l for l in out.splitlines() if "passed" in l or "failed" in l][-1:] or out.splitlines()[-1:]
    return {"ok": rc == 0, "seconds": sec, "detail": tail[0] if tail else ""}


def step_nuke_headless():
    rc, out, sec = run([PY, "-I", os.path.join("tools", "run_nuke_tests.py")], timeout=7200)
    lines = [l for l in out.splitlines() if l.strip().endswith(("PASS", "FAIL"))]
    fails = [l.split()[0] for l in lines if l.strip().endswith("FAIL")]
    return {"ok": rc == 0 and lines and not fails, "seconds": sec,
            "detail": "%d/%d pass%s" % (len(lines) - len(fails), len(lines), ("; failed: " + ", ".join(fails)) if fails else "")}


def step_gui():
    res, ok, t0 = [], True, time.time()
    for script, result in GUI_PROBES:
        rp = os.path.join(ROOT, result)
        if os.path.exists(rp):
            os.remove(rp)
        try:
            subprocess.run([NUKE, "--nc", os.path.join(ROOT, script)], cwd=ROOT, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            pass
        passed = bool(os.path.exists(rp) and json.load(open(rp)).get("passed"))
        ok &= passed
        res.append("%s %s" % (os.path.basename(script), "PASS" if passed else "FAIL"))
    return {"ok": ok, "seconds": round(time.time() - t0, 1), "detail": "; ".join(res)}


def step_installer():
    """Build a package (tiny model), install with Nuke's python into tmp/, run Nuke from the installed copy (HOME
    only), uninstall; then confirm the owner's real .nuke / LOCALAPPDATA have no ST-ROTO."""
    t0 = time.time()
    tmp = os.path.join(ROOT, "tmp", "acceptance_install")
    shutil.rmtree(tmp, ignore_errors=True)
    base, home = os.path.join(tmp, "base"), os.path.join(tmp, "home")
    os.makedirs(os.path.join(home, ".nuke"))
    setup = os.path.join(ROOT, "tools", "installer", "st_roto_setup.py")
    pkg = os.path.join(tmp, "ST-ROTO-acceptance.zip")
    steps = []
    rc, out, _ = run([PY, "-I", setup, "package", "--out", pkg, "--models", "tiny"], timeout=1800)
    steps.append(("package", rc == 0))
    rc, out, _ = run([NUKE_PY, setup, "install", "--source", pkg, "--base", base, "--home", home], timeout=1800)
    steps.append(("install", rc == 0))
    env = dict(os.environ, HOME=home)
    res = os.path.join(tmp, "check.json")
    run([NUKE, "--nc", "-t", os.path.join(ROOT, "research", "probes", "2026-11-17_installer", "check_installed.py"),
         "out=" + res, "frames=" + os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")],
        timeout=900, env=env)
    chk = json.load(open(res)) if os.path.exists(res) else {}
    steps.append(("nuke_runs_installed_copy", bool(chk.get("passed") and "acceptance_install" in
                                                   chk.get("st_roto_nuke_from", "") and not chk.get("repo_on_path"))))
    rc, out, _ = run([NUKE_PY, setup, "uninstall", "--base", base, "--home", home])
    steps.append(("uninstall", rc == 0 and not os.path.exists(base)))
    real_init = os.path.join(os.environ.get("USERPROFILE", ""), ".nuke", "init.py")
    untouched = not (os.path.exists(real_init) and "ST-ROTO" in open(real_init, encoding="utf-8", errors="ignore").read()) \
        and not os.path.exists(os.path.join(os.environ.get("LOCALAPPDATA", ""), "ST-ROTO"))
    steps.append(("owner_setup_untouched", untouched))
    shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": all(v for _, v in steps), "seconds": round(time.time() - t0, 1),
            "detail": "; ".join("%s %s" % (k, "ok" if v else "FAIL") for k, v in steps)}


def step_offline():
    """Network use of the whole workflow: the Nuke test's audit hook (0 Python network events) under the OS
    connection watcher."""
    out_json = os.path.join(ROOT, "tmp", "acceptance_watch.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    rc, out, sec = run([PY, "-I", os.path.join("tools", "offline", "watch_network.py"), "--out", out_json, "--",
                        NUKE, "--nc", "-t", os.path.join(ROOT, "tests", "nuke", "run_nuke_tests.py"),
                        "test_offline_no_network"], timeout=1800)
    w = json.load(open(out_json)) if os.path.exists(out_json) else {}
    r = json.load(open(os.path.join(ROOT, "tests", "nuke", "out", "results_test_offline_no_network.json")))
    t = r.get("test_offline_no_network", {})
    ext = len(w.get("external_remote_endpoints", []))
    return {"ok": bool(t.get("passed")) and t.get("network_event_count") == 0, "seconds": sec,
            "detail": "Python network events %s; external connections seen %d (Nuke's own; firewall rule D-040 %s)"
                      % (t.get("network_event_count"), ext, "blocks them" if ext == 0 else "not active?")}


def step_defects():
    """Criterion 20: no OPEN defect that blocks a release (DEFECTS.md)."""
    rows = [l for l in open(os.path.join(ROOT, "DEFECTS.md"), encoding="utf-8") if l.startswith("| DEF-")]
    cells = [[c.strip() for c in l.strip().strip("|").split("|")] for l in rows]
    blocking = [c[0] for c in cells if c[5].lower() == "yes" and c[6].lower() == "open"]
    open_all = [c[0] for c in cells if c[6].lower() == "open"]
    return {"ok": not blocking, "seconds": 0, "detail": "%d defects, %d open (%s), %d open release blockers%s" % (
        len(cells), len(open_all), ", ".join(open_all) or "-", len(blocking), (": " + ", ".join(blocking)) if blocking else "")}


STEPS = [  # name, function, acceptance criteria (docs/ACCEPTANCE.md numbers)
    ("defects", step_defects, [20]),
    ("unit", step_unit, [3, 6, 9, 10, 11, 13, 15, 17]),
    ("nuke_headless", step_nuke_headless, [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]),
    ("gui", step_gui, [2, 3, 4, 9, 13, 17]),
    ("installer", step_installer, [1, 2]),
    ("offline", step_offline, [12]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="", help="comma-separated step names to skip")
    a = ap.parse_args()
    skip = set(s for s in a.skip.split(",") if s)
    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {"utc": stamp, "commit": head, "steps": {}}
    for name, fn, crit in STEPS:
        if name in skip:
            report["steps"][name] = {"ok": None, "detail": "skipped", "criteria": crit}
            continue
        print("running", name, flush=True)
        try:
            r = fn()
        except Exception as e:                                # noqa: BLE001 - a crashed step is a failed step
            r = {"ok": False, "detail": "%s: %s" % (type(e).__name__, e), "seconds": None}
        r["criteria"] = crit
        report["steps"][name] = r
        print("  ->", "PASS" if r["ok"] else "FAIL", r["detail"][:200], flush=True)
    d = os.path.join(ROOT, "docs", "acceptance")
    os.makedirs(d, exist_ok=True)
    json.dump(report, open(os.path.join(d, "run_%s.json" % stamp), "w"), indent=1)
    lines = ["# Acceptance run %s (commit %s)" % (stamp, head), "",
             "| step | result | time (s) | supports criteria | detail |", "|---|---|---|---|---|"]
    for name, r in report["steps"].items():
        res = "skipped" if r["ok"] is None else ("PASS" if r["ok"] else "FAIL")
        lines.append("| %s | %s | %s | %s | %s |" % (name, res, r.get("seconds", ""), ", ".join(map(str, r["criteria"])),
                                                    r["detail"].replace("|", "/")))
    lines += ["", "Criteria and their full status: docs/ACCEPTANCE.md. A passing run does not make a criterion met "
                  "where ACCEPTANCE.md lists gaps."]
    open(os.path.join(d, "run_%s.md" % stamp), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("report:", os.path.join(d, "run_%s.md" % stamp))
    return 0 if all(r["ok"] is not False for r in report["steps"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
