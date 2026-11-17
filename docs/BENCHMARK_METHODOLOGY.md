# ST-ROTO benchmark methodology (REQ-190, master prompt section 21) — version 1, published 2026-11-17

Published **before any comparative test**, as section 21.1 requires. Its git commit records the date; any change to
the metrics, weights or procedure after a comparison has started gets a new version number here and is reported with
the results. Implementation: `src/st_roto/metrics.py` (unit-tested in `tests/unit/test_metrics.py`).

## 1. Rules

1. Only lawful access: each tool through its own licence or evaluation terms; footage and truth under licences that
   allow it (D-020 / D-031: SA-V subset, CC BY 4.0, attribution in `data/benchmarks/sa-v/MANIFEST.json`; synthetic
   shots generated in this repository; owner-approved footage).
2. Identical inputs for every tool: same source frames, resolution, frame range, first-frame prompt (box + one
   interior click, simulated from the truth, T-082) or the closest input the tool accepts (stated per tool).
3. Two results per tool and sequence: **automatic** (no correction) and **artist-corrected** (section 5). Artist
   correction TIME is never a metric.
4. Every category result is published, as well as the overall score; cases where another tool is better are
   reported in the same tables. No claim of superiority without the reproducible run behind it.
5. Nothing is tuned on the benchmark sequences: ST-ROTO's settings are fixed before the run (defaults of the
   release being tested, recorded).

## 2. Data

| set | what | truth | use |
|---|---|---|---|
| SA-V subset | 51 object sequences from 30 validation videos (6 fps annotation) | SA-V masks (SAM-assisted annotation: region truth; NOT edge-precision truth, T-095) | region, boundary, temporal, stability, identity |
| synthetic shots | `research/probes/2026-11-15_video` and generated variants | exact masks | all categories incl. edge precision |
| known-alpha composites | `research/probes/2026-11-16_matting` scenes | exact alpha | alpha / soft-edge categories |

Recorded per run: tool name and version, model and version, hardware (GPU, VRAM, CPU, RAM), host application and
edition, resolution, frame ranges, settings.

## 3. Metrics (per frame, then averaged per sequence; `metrics.sequence_scores`)

| metric | definition |
|---|---|
| IoU | \|P ∩ G\| / \|P ∪ G\|, masks = alpha >= 0.5; both empty = 1 |
| Dice | 2\|P ∩ G\| / (\|P\| + \|G\|) |
| Boundary F | F1 of boundary pixels matched within 0.2 % of the image diagonal (>= 1 px) |
| MAE / SAD / MSE | mean absolute / sum of absolute (in thousands) / mean squared alpha difference |
| Temporal error | mean \|(a_t − a_t−1) − (g_t − g_t−1)\|: change the truth does not have (flicker, drift) |
| Contour quality | HD95: 95th percentile symmetric boundary distance in px (inf when one side is empty) |
| Tracking stability | fraction of visible frames with IoU >= 0.5; number of losses (kept -> not kept) |
| Identity preservation | fraction of truth objects whose best-overlapping prediction is their own (no swaps) |

## 4. Category scores and weights (`metrics.category_scores`, `metrics.overall`)

| category | score (0..1, higher is better) | weight |
|---|---|---|
| region | mean IoU over visible frames | 0.25 |
| boundary | mean boundary F over visible frames | 0.20 |
| alpha | max(0, 1 − 10 × MAE) | 0.10 |
| temporal | max(0, 1 − 10 × temporal error) | 0.15 |
| contour | exp(−HD95 / 10 px), scaled by the share of visible frames with a contour | 0.10 |
| stability | kept fraction / (1 + losses) | 0.15 |
| identity | identity preservation (1 for single-object sequences) | 0.05 |
| **overall** | weighted mean of the categories | 1.00 |

Results are reported per category, per data set and per difficult-case category (master prompt section 9) where
the data allows; the overall score never replaces them.

## 5. Artist-corrected result

A fixed correction protocol, identical for every tool: on each sequence the operator may correct at most **3 frames**
chosen by the tool's own review aid or, without one, the frames with the lowest IoU; corrections use the tool's own
correction mechanism (for ST-ROTO: an edited key or Re-prompt here, then Re-track). The result after that protocol
is scored like the automatic one. The number of corrections used is reported; time is not.

## 6. Competitors: current access (2026-11-17)

| tool | lawful access now | status |
|---|---|---|
| Foundry SmartROTO | paid add-on, not available here | not run |
| Silhouette ML, Mocha Pro | not installed (T-077 blocked) | not run |
| Adobe Roto Brush / Object Matte | not installed | not run |
| DaVinci Resolve Magic Mask | Studio feature; not installed | not run |
| ONYX Ai Matte, Slapshot Autopilot | not installed | not run |
| open-source Nuke tools | to be listed per tool and licence | not run |

No comparative result exists yet; none is claimed. ST-ROTO's own results so far (SA-V region IoU, T-068 / T-080 /
T-082) were measured before this methodology and are not re-scored here.
