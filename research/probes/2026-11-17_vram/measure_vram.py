"""T-092: peak GPU memory of a product Track per model / object count (Nuke 17.1 NC, RTX 5060 Laptop 8 GB).

  .venv\\Scripts\\python.exe -I research/probes/2026-11-17_vram/measure_vram.py
Polls nvidia-smi every 0.2 s while Nuke runs track_once.py: total memory.used (minus the idle baseline before
Nuke starts) and, where Windows reports it, the Nuke process's own used_memory. Writes vram.json.
"""
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NUKE = r"C:\Program Files\Nuke17.1v3\Nuke17.1.exe"
NOWIN = 0x08000000


def smi(args):
    return subprocess.run(["nvidia-smi"] + args, capture_output=True, text=True, creationflags=NOWIN).stdout


def used_total():
    return int(smi(["--query-gpu=memory.used", "--format=csv,noheader,nounits"]).split()[0])


def per_process():
    out = {}
    for line in smi(["--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"]).splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) == 2:
            try:
                out[int(p[0])] = int(p[1])
            except ValueError:
                out[int(p[0])] = None                     # "[N/A]" on WDDM
    return out


def run(model, n_obj, frames=24):
    time.sleep(3)
    base = min(used_total() for _ in range(5))
    proc = subprocess.Popen([NUKE, "--nc", "-t", os.path.join(HERE, "track_once.py"), "model=" + model, "objects=%d" % n_obj, "frames=%d" % frames],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    peak_total, peak_proc, samples = 0, None, 0
    while proc.poll() is None:
        peak_total = max(peak_total, used_total() - base)
        pp = per_process().get(proc.pid)
        if pp is not None:
            peak_proc = max(peak_proc or 0, pp)
        samples += 1
        time.sleep(0.2)
    res = json.load(open(os.path.join(HERE, "result_%s_%dobj.json" % (model, n_obj))))
    res.update(baseline_mib=base, peak_increase_mib=peak_total, peak_process_mib=peak_proc, samples=samples)
    print(res)
    return res


if __name__ == "__main__":
    out = [run(m, k) for m in ("sam2.1-hiera-tiny", "sam2.1-hiera-large") for k in (1, 2)]
    json.dump(out, open(os.path.join(HERE, "vram.json"), "w"), indent=1)
