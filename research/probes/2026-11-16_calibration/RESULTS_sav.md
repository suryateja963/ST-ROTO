# T-068 — review-flag calibration on real footage (SA-V subset, D-031)

**Data:** SA-V validation split (Meta, CC BY 4.0), the first 30 videos in archive order: 51 object sequences,
5,527 frames (annotated 6-fps frames = every 4th 24-fps frame; up to 1080×1920). Fetched with
`tools/benchmark/fetch_sav_subset.py` (streams the 15 GB tar, stops after the subset, 74 min at ~5 MB/s; 2 GB kept,
git-ignored, SHA-256 per file in `data/benchmarks/sa-v/MANIFEST.json`).

**Runs** (`tools/benchmark/calibrate_review.py`, inside `Nuke17.1.exe --nc -t`, device **cuda**, SAM 2.1 tiny, 16
anchors + part shapes; records in `sav/` and `sav_box/calibration.json`; analysis `analyse_sav.py`):

## 1. One click is often the wrong object (prompt, not tracking)

`probe_prompt_first_frame.py`: IoU on the prompted frame itself.

| prompt | first frames < 0.5 IoU | mean first-frame IoU |
|---|---|---|
| one click at the mask's most interior point | **19 / 51** | 0.621 |
| truth bounding box + that click (SAM box corners, labels 2/3) | **2 / 51** | 0.844 |

SA-V objects are often parts (a sleeve, a bag, one of several people); a single click picks the whole/another
object. The box result also shows the exported decoder handles box-corner labels correctly. The calibration below
uses the box run and excludes the 2 sequences whose prompted frame is already wrong (49 sequences, 5,220 frames).
**Product implication (not changed, owner decision):** offer a box prompt in the node, and tell artists to add
clicks when the first frame is wrong.

Even correct first frames reach only ~0.85–0.93 IoU: a 16-anchor spline cannot follow SA-V's detailed mask outlines.
Therefore "bad frame" is evaluated at three levels: IoU < 0.5 (serious), < 0.7, < 0.9.

## 2. The LOST rule flagged real exits — fixed

With the old rule (every absent frame between present frames = LOST), **1,054 of 1,858 flags (57 %) were on frames
where the object really was gone** (left the shot / occluded). `probe_lost_rule.py`, absent runs between present
frames:

| absent run (6-fps samples) | runs | frames | object actually visible |
|---|---|---|---|
| 1 | 28 | 28 | 46 % |
| 2 | 25 | 50 | 60 % |
| 3–4 | 18 | 60 | 48 % |
| 5–8 | 13 | 90 | 23 % |
| ≥ 9 | 35 | 1018 | 12 % |

New rule (`quality.LOST_MAX_GAP = 16` shot frames ≈ 0.7 s = 4 samples): short runs stay LOST; longer runs flag only
their first and last frame (CHECK: "object disappears here … / reappears"). Current thresholds (margin 1.0,
iou_min 0.7):

| bad = IoU < | rule | flags | precision | recall | F1 |
|---|---|---|---|---|---|
| 0.5 | old | 1858 | 0.311 | 0.562 | 0.400 |
| 0.5 | **new** | **933** | **0.535** | 0.486 | **0.509** |
| 0.7 | old | 1858 | 0.366 | 0.464 | 0.409 |
| 0.7 | **new** | 933 | 0.645 | 0.410 | 0.502 |
| 0.9 | old | 1858 | 0.422 | 0.294 | 0.347 |
| 0.9 | **new** | 933 | 0.757 | 0.265 | 0.392 |

Half the flags, every flag more likely real; the recall cost (0.56 → 0.49 for serious errors) is in long runs
where the AI also misses a returning object — their exit/return edges are still flagged. Robustness (the gap was
chosen on this data): split by video into halves A (15) / B (14): F1 0.412 → 0.533 and 0.385 → 0.480; gap 2, 4
and 8 give nearly the same result (A 0.536/0.533/0.536, B 0.478/0.480/0.458).

## 3. Score thresholds: kept (1.0, 0.7)

With the new LOST rule, the best grid point for serious errors is (1.5, 0.7): F1 0.529 vs 0.509 — within noise for
49 sequences, so the defaults stay. Higher F1 at the 0.9 level needs iou_min 0.9, which flags 2,361 of 5,220 frames
(45 %) — useless as a review list. Predicted IoU correlates 0.53 with true IoU (synthetic: 0.015–0.50).

## 4. T-078 area-jump rule: kept at 0.35 (CHECK)

| threshold | flags | precision (IoU<0.5) | precision (IoU<0.9) | real catches it adds (IoU<0.9) |
|---|---|---|---|---|
| 0.20 | 412 | 0.29 | 0.81 | 187 of 261 |
| 0.35 | 165 | 0.28 | 0.79 | 64 of 95 |
| 0.50 | 72 | 0.28 | 0.83 | 31 of 42 |

It catches **moderate** shape errors well (~80 % of its flags are real at the 0.9 level, base rate 51 %) but not
serious failures (≈ base rate 20 %). 0.35 keeps it to ~3 % of frames; 0.20 would add 2.5× the flags for the same
precision — a possible "thorough review" setting later, not a default change.

## What is still unknown

- 30 videos / 49 sequences from one dataset; SA-V is not VFX plates (no greenscreen, motion blur, 4K, EXR).
- Results at 6-fps sampling; the tracker in the product sees every frame (easier tracking, gap rule in shot frames).
- Point-prompt run kept for comparison (`sav/`): same conclusions on the 32 correctly prompted sequences (area rule
  precision 0.73–0.85 at the 0.9 level).
