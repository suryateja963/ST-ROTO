"""T-038: identify the libtorch bundled with Nuke 17.1v3 from strings embedded in its DLLs (no version resource).
Run: .venv/Scripts/python.exe research/probes/2026-11-16_nuke_libtorch/find_versions.py [Nuke folder]"""
import collections, json, os, re, sys

NUKE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\Nuke17.1v3"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json")
PATTERNS = {
    "version_like": re.compile(rb"(?<![0-9.])(2\.[0-9]{1,2}\.[0-9]{1,2}(?:a0|\+[a-z0-9.]+)?)(?![0-9])"),
    "torch_context": re.compile(rb"[ -~]{0,60}(?:PyTorch|libtorch|TORCH_VERSION|torch version|BUILD_TYPE|CUDA Runtime)[ -~]{0,80}"),
    "build_settings": re.compile(rb"Build settings:[ -~\r\n]{0,1500}"),
    "cuda_arch": re.compile(rb"sm_[0-9]{2,3}a?"),
    "git_hash": re.compile(rb"[0-9a-f]{40}"),
}


def scan(path, limit=None):
    data = open(path, "rb").read()
    res = {}
    for name, pat in PATTERNS.items():
        hits = collections.Counter(m.group(0) if name != "version_like" else m.group(1) for m in pat.finditer(data))
        res[name] = [(h.decode("latin-1"), n) for h, n in hits.most_common(limit or 15)]
    return res


out = {}
for fn in ("torch_cpu.dll", "c10.dll", "torch_cuda.dll", "torchvision.dll"):
    p = os.path.join(NUKE, fn)
    if os.path.exists(p):
        out[fn] = scan(p)
        out[fn]["bytes"] = os.path.getsize(p)
json.dump(out, open(OUT, "w"), indent=1)
for fn, r in out.items():
    print("==", fn, r["bytes"])
    for k in ("build_settings", "torch_context", "version_like", "cuda_arch"):
        for h, n in r[k][:8]:
            print("  %-15s %4d  %s" % (k, n, h[:300].replace("\r", " ").replace("\n", " | ")))
