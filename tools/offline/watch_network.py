"""T-085 / REQ-140: OS-level view of the network use of a process tree (native code included: Nuke, ONNX Runtime,
CUDA). Launches a command, polls the Windows TCP/UDP tables (psutil.net_connections) every --interval seconds
for the launched process and all its children, and writes every endpoint seen (local, remote, status, first and
last time seen, process) to a JSON file.

Usage:
  .venv\\Scripts\\python.exe -I tools/offline/watch_network.py --out <file.json> -- <command ...>

Limitations (stated in the result file): polling can miss a connection that opens and closes between two polls
(default 0.05 s); loopback endpoints are listed separately (local only, not transmission); ETW telemetry is
handed to the Windows service, not sent by the process itself, so it would not appear here (ST-ROTO disables
ONNX Runtime's events instead, see st_roto_ai.runtime).
"""
import argparse
import json
import subprocess
import sys
import time

import psutil

LOOPBACK = ("127.", "::1", "0.0.0.0", "::")


def tree(pid):
    try:
        p = psutil.Process(pid)
        return {pid} | {c.pid for c in p.children(recursive=True)}
    except psutil.Error:
        return set()


def addr(a, local=False):
    """Local non-loopback addresses are redacted (the machine's LAN address is not needed and is not published)."""
    if not a:
        return ""
    if local and not a.ip.startswith(LOOPBACK):
        return "<local>:%d" % a.port
    return "%s:%d" % (a.ip, a.port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=0.05)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen, names, polls = {}, {}, 0
    while True:
        alive = proc.poll() is None
        pids = tree(proc.pid)
        for pid in pids:
            if pid not in names:
                try:
                    names[pid] = psutil.Process(pid).name()
                except psutil.Error:
                    names[pid] = "?"
        try:
            conns = psutil.net_connections(kind="inet")
        except psutil.Error:
            conns = []
        now = round(time.time() - t0, 2)
        for c in conns:
            if c.pid not in pids:
                continue
            key = (c.pid, "tcp" if c.type == 1 else "udp", addr(c.laddr, local=True), addr(c.raddr), c.status)
            if key not in seen:
                seen[key] = {"first_s": now}
            seen[key]["last_s"] = now
        polls += 1
        if not alive:
            break
        time.sleep(a.interval)
    rows = []
    for (pid, kind, laddr, raddr, status), t in sorted(seen.items(), key=lambda kv: kv[1]["first_s"]):
        rows.append({"pid": pid, "process": names.get(pid, "?"), "proto": kind, "local": laddr, "remote": raddr,
                     "status": status, "first_s": t["first_s"], "last_s": t["last_s"],
                     "loopback_or_unbound": (not raddr) or raddr.startswith(LOOPBACK)})
    external = [r for r in rows if not r["loopback_or_unbound"]]
    result = {"command": cmd, "exit_code": proc.returncode, "seconds": round(time.time() - t0, 1), "polls": polls,
              "interval_s": a.interval, "processes": names, "endpoints": rows,
              "external_remote_endpoints": external,
              "limitations": "polling may miss connections shorter than the interval; ETW telemetry is not "
                             "visible as a connection of the process"}
    json.dump(result, open(a.out, "w"), indent=1)
    print("exit=%s seconds=%s polls=%d endpoints=%d external=%d" % (
        proc.returncode, result["seconds"], polls, len(rows), len(external)))
    for r in rows:
        print("  %-14s %s %-22s -> %-22s %s" % (r["process"], r["proto"], r["local"], r["remote"], r["status"]))


if __name__ == "__main__":
    main()
