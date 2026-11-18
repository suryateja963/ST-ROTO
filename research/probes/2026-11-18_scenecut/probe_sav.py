"""T-123: scene-cut detection on real footage (SA-V subset, CC BY 4.0, D-031; frames are 6-fps samples, so motion
between frames is ~4x larger than in a 24-fps plate - a hard test for false alarms).
(a) false cuts INSIDE each real video (every video is one continuous shot);
(b) real cuts: every video joined to the next one -> exactly one cut must be found, at the junction;
(c) one-frame flash: a white frame / a frame of another video inserted -> no cut.
  .venv\\Scripts\\python.exe -I probe_sav.py   -> result_sav.json"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from st_roto import scenecut  # noqa: E402

SAV = os.path.join(ROOT, "data", "benchmarks", "sa-v", "raw", "frames")
vids = {}
for d in sorted(glob.glob(os.path.join(SAV, "*"))):
    fs = sorted(glob.glob(os.path.join(d, "*.jpg")))
    if len(fs) >= 8:
        vids[os.path.basename(d)] = [scenecut.thumbnail(np.asarray(Image.open(f).convert("RGB"))) for f in fs]
R = {"videos": len(vids), "frames": sum(len(v) for v in vids.values())}

false = {}
for name, th in vids.items():                                            # (a)
    cuts, rep = scenecut.detect(th)
    if cuts:
        false[name] = [(c, [r for r in rep if r["frame"] == c][0]) for c in cuts]
R["a_false_cuts"] = {"videos_with_false_cuts": len(false), "false_cuts": sum(len(v) for v in false.values()),
                     "pairs_checked": sum(len(v) - 1 for v in vids.values()), "detail": false}

names = list(vids)
found, missed, extra = 0, [], []                                         # (b)
for a, b in zip(names, names[1:] + names[:1]):
    seq = vids[a][-12:] + vids[b][:12]
    cuts, rep = scenecut.detect(seq)
    if 12 in cuts:
        found += 1
    else:
        missed.append((a, b, [r for r in rep if r["frame"] == 12][0]))
    extra += [(a, b, c) for c in cuts if c != 12]
R["b_real_cuts"] = {"junctions": len(names), "found": found, "missed": missed, "extra_cuts": extra}

flash_cuts, glitch_cuts = 0, 0                                           # (c)
for i, a in enumerate(names):
    seq = list(vids[a][:16])
    if len(seq) < 16:
        continue
    white = np.ones_like(seq[0])
    cuts, _ = scenecut.detect(seq[:8] + [white] + seq[8:])
    flash_cuts += len(cuts)
    other = vids[names[(i + 1) % len(names)]][0]
    cuts, _ = scenecut.detect(seq[:8] + [other] + seq[8:])
    glitch_cuts += len(cuts)
R["c_flashes"] = {"white_flash_cuts": flash_cuts, "one_frame_of_another_video_cuts": glitch_cuts,
                  "sequences": len(names)}
json.dump(R, open(os.path.join(HERE, "result_sav.json"), "w"), indent=1)
print(json.dumps({k: (v if k != "a_false_cuts" else {kk: vv for kk, vv in v.items() if kk != "detail"})
                  for k, v in R.items()}, indent=1)[:3000])
