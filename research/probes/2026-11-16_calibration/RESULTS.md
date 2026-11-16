# Review-flag calibration (T-068) — PROVISIONAL, synthetic data only — 2026-11-16

Tool: `tools/benchmark/calibrate_review.py` (+ `st_roto.calibration`), ready for approved real footage (`--dir`, layout frames/ + masks/). Real footage needs the owner's approval of each dataset's licence (D-020; recommendation SA-V subset, `docs/RESEARCH_2026-11-16_BENCHMARK_DATASETS.md`).

**Run.** Synthetic shot (D-020 data): target and distractor disc, each forward from frame 0 and time-reversed from frame 47; SAM 2.1 tiny on CPU; prompt = most interior truth pixel; 192 frames, of which **7 are bad** (IoU < 0.9 or visible-but-reported-absent). Raw: `calibration.json`.

| Thresholds (score margin / predicted IoU min) | flags | bad caught | precision | recall | F1 |
|---|---|---|---|---|---|
| **current 1.0 / 0.7** | 14 | 6 / 7 | 0.43 | 0.86 | 0.57 |
| best on this data 0.25 / 0.0 | 8 | 6 / 7 | 0.75 | 0.86 | 0.80 |

**Findings.**
1. The LOST rule (object absent between visible frames) catches the occlusion losses (reverse 16–20, 22).
2. **Predicted IoU is uninformative here** (correlation with true IoU 0.015; 0.50 on the earlier forward-only shot): the iou_min rule adds flags without catching bad frames.
3. **A confidently wrong frame exists**: reverse frame 23 (the split frame), object score 8.0, predicted IoU 0.98, true IoU 0.42 — the mask holds only one of the two pieces. No score threshold can flag it; a temporal-consistency rule (sudden area / shape change vs neighbours) is the candidate, to be evaluated on real data.

**Decision.** Defaults stay (1.0 / 0.7) — 7 bad frames from one synthetic shot are not evidence enough to change them; the tool reruns in minutes once real data is approved.
