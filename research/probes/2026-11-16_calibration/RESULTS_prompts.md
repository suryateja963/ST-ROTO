# T-082 — Which prompt should an artist use? (SA-V subset, 2026-11-17)

**Setup.** Same 51 sequences (30 SA-V validation videos, D-031), same tracker (SAM 2.1 tiny, CUDA inside Nuke 17.1,
`calibrate_review.py`), prompt on the first frame where the object is visible, every annotated frame scored against
the SA-V truth (3,974 visible frames). Only the prompt differs:

| prompt | how it was simulated from the truth mask |
|---|---|
| 1 click | the most interior pixel |
| 3 clicks | up to 3 spread interior points (each the most interior point outside 1.5× the previous radius) |
| box only | the mask's tight bounding box (SAM corner labels 2/3) |
| box + click | that box + the most interior pixel |

## Results

| | 1 click | 3 clicks | box only | box + click |
|---|---|---|---|---|
| wrong object on the prompt frame (IoU < 0.5) | 19 / 51 | 13 / 51 | **2 / 51** | **2 / 51** |
| prompt-frame IoU, mean / median | 0.621 / 0.805 | 0.680 / 0.843 | 0.844 / 0.895 | 0.844 / 0.891 |
| **mean IoU, visible frames** | 0.536 | 0.576 | 0.673 | **0.679** |
| frames with IoU ≥ 0.9 | 25 % | 30 % | **34 %** | 32 % |
| frames with IoU < 0.5 | 43 % | 36 % | 24 % | **21 %** |
| mean IoU, sequences that started on the right object | 0.696 | 0.697 | 0.671 | 0.678 |
| per sequence vs box + click: better / worse by > 0.05 | 1 / 22 | 1 / 17 | 0 / 2 | — |

Files: `sav/`, `sav_points3/`, `sav_box_only/`, `sav_box/` (`calibration.json` each), `compare_prompts.py` →
`compare_prompts.json`.

## Conclusions

1. **A box is the biggest single improvement**: wrong-object starts 19 → 2, mean IoU +0.14 over one click.
   On real footage most failures of click prompts are SAM choosing a different object or part, not losing it later.
2. **Box + click vs box only:** nearly the same (+0.006 mean IoU, fewer badly-off frames, 2 sequences clearly
   better, none clearly worse). Adding the click costs nothing and helps slightly.
3. **More clicks help a little** (3 clicks: 13 instead of 19 wrong starts) but far less than a box.
4. **When a click does pick the right object, it is as good as a box** (0.696 vs 0.678 on sequences that started
   correctly): clicks are fine for whole, distinct objects; use a box for parts and for objects among similar ones.

**Caveats.** Prompts were simulated from the truth (tight boxes, ideal interior clicks); an artist's box is looser,
and an artist sees a wrong preview and corrects it before tracking (Preview button), which the benchmark cannot.
Tiny model only (T-080: the large model adds ~+0.045 mean IoU). SA-V annotations are 6-fps samples.

The calibration side effect of these runs (review thresholds) is unchanged: the box + click run (T-068) remains the
calibration reference.
