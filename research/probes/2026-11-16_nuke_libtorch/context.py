"""Print the bytes around every '2.7.1' in Nuke's libtorch DLLs (T-038)."""
import re, sys

NUKE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\Nuke17.1v3"
for fn in ("torch_cpu.dll", "torch_cuda.dll"):
    d = open(NUKE + "\\" + fn, "rb").read()
    for m in re.finditer(rb"(?<![0-9.])2\.7\.1(?![0-9])", d):
        s = d[max(0, m.start() - 160):m.end() + 100]
        print(fn, m.start(), re.sub(rb"[^ -~]+", b" | ", s).decode())
    for pat in (rb"CUDA Runtime [0-9.]+", rb"CuDNN [0-9.]+", rb"MSVC [0-9]+", rb"C\+\+ Version: [0-9]+"):
        hits = set(x.group(0) for x in re.finditer(pat, d))
        if hits:
            print(fn, pat.decode(), sorted(h.decode() for h in hits)[:5])
