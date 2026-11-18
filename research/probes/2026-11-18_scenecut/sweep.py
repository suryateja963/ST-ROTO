"""Threshold study on cached SA-V thumbnails (cache_thumbs.py): false cuts inside videos, real cuts at junctions,
flashes, for several RATIO / HIST_MIN values. The three badminton jumps in sav_050687 (frames 10, 23, 59) and the jump in
sav_006251 (frame 104) are real camera cuts / jump cuts inside the SA-V video (checked by eye, contact sheet), so
they are counted apart ("edits_in_video"), not as false cuts."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from st_roto import scenecut as sc
V = dict(np.load(os.path.join(ROOT, "tmp", "thumbs_sav.npz")))
EDITS = {("sav_050687", 10), ("sav_050687", 23), ("sav_050687", 59), ("sav_006251", 104)}
names = sorted(V)


def run():
    false, edits = [], []
    for n in names:
        cuts, _ = sc.detect(list(V[n]))
        for c in cuts:
            (edits if (n, c) in EDITS else false).append((n, c))
    found, extra = 0, 0
    for a, b in zip(names, names[1:] + names[:1]):
        cuts, _ = sc.detect(list(V[a][-12:]) + list(V[b][:12]))
        found += 12 in cuts
        extra += sum(1 for c in cuts if c != 12 and not ((a, len(V[a]) - 12 + c) in EDITS or (b, c - 12) in EDITS))
    fl = gl = 0
    for i, a in enumerate(names):
        s = list(V[a][:16])
        fl += len(sc.detect(s[:8] + [np.ones_like(s[0])] + s[8:])[0])
        gl += len(sc.detect(s[:8] + [V[names[(i + 1) % len(names)]][0]] + s[8:])[0])
    return {"false_in_video": len(false), "false_list": false, "edits_found": len(edits), "junctions_found": found,
            "junctions": len(names), "extra_at_junction_tests": extra, "white_flash_cuts": fl, "glitch_cuts": gl}


out = {}
for ratio in (3.0, 4.0, 5.0, 6.0):
    for hmin in (0.25, 0.3, 0.35):
        sc.RATIO, sc.HIST_MIN = ratio, hmin
        r = run(); out["ratio %.1f hist_min %.2f" % (ratio, hmin)] = r
        print("ratio %.1f hmin %.2f" % (ratio, hmin), {k: v for k, v in r.items() if k != "false_list"})
json.dump(out, open(os.path.join(HERE, "result_sweep.json"), "w"), indent=1)
