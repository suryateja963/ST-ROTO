"""Print a one-screen summary of out/result_<case>.json (T-086)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = sys.argv[1:] or ["start1001", "missing", "discontinuous", "duplicate", "mixed_res", "proxy", "retime"]
for c in CASES:
    p = os.path.join(HERE, "out", "result_%s.json" % c)
    if not os.path.exists(p):
        print(c, "NO RESULT"); continue
    r = json.load(open(p))
    print("=" * 20, c)
    if "exception" in r:
        print(r["exception"][-600:]); continue
    print(" range", r.get("source_range"), "size", r.get("source_size"), "on_error", r.get("read_on_error"))
    print(" job", r.get("job_status"), "|", (r.get("job_error") or "")[-300:])
    print(" status", r.get("status", "")[:300])
    for k in ("retrack_job", "retrack_status", "mattes_job", "mattes_status", "matte_files"):
        if k in r:
            print(" %s %s" % (k, str(r[k])[:400]))
    shown = r.get("shown", {})
    print(" shown", {k: (v.get("source_frame"), v.get("size"), v.get("error", "")[:60]) for k, v in shown.items()})
    keys = r.get("keys", {})
    print(" keys", {k: {kk: vv for kk, vv in v.items() if kk != "area"} for k, v in keys.items()})
    if r.get("score_error"):
        print(" score_error", r["score_error"][-400:])
