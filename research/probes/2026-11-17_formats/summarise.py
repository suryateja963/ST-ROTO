"""One-screen summary of out/result_<case>.json (T-089)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = sys.argv[1:] or ["png16", "tiff16", "exr_half", "exr_float", "dpx10", "dci2k", "scope", "vertical",
                         "anamorphic", "uhd4k", "dci4k", "uhd8k"]
for c in CASES:
    p = os.path.join(HERE, "out", "result_%s.json" % c)
    if not os.path.exists(p):
        print("%-10s NO RESULT" % c); continue
    r = json.load(open(p))
    if "exception" in r:
        print("%-10s EXCEPTION %s" % (c, r["exception"][-300:])); continue
    ious = list(r.get("key_iou", {}).values())
    print("%-10s fmt=%s bits=%s job=%s %.0fs keys=%d iou=%s..%s roto_f2=%s %s" % (
        c, "%(w)dx%(h)d pa%(pixel_aspect)s" % r["read_format"], r.get("read_bitdepth"), r.get("job_status"),
        r.get("track_seconds", 0), len(ious), min(ious) if ious else None, max(ious) if ious else None,
        r.get("roto_render_iou_f2"), r.get("roto_render_size") or r.get("roto_render_error", "")[:80]))
    st = r.get("status", "")
    if r.get("job_status") != "done" or "fitted" in st:
        print("           status:", st[:300])
        if r.get("job_error"):
            print("           error:", r["job_error"][-300:])
