# Benchmark datasets with ground truth — licences (T-036, 2026-11-16)

Purpose: footage with ground-truth masks or mattes for calibrating review flags (T-068) and for the benchmarks of master prompt §21. Owner question OQ-13 asks which footage may lawfully be used and published; **nothing has been downloaded**.

Evidence: **V-text** = licence text read; **V-page** = official dataset page/README; **S** = secondary source; **–** = not established.

| Dataset | Ground truth | Licence as found | Commercial / publishable results? | Evidence |
|---|---|---|---|---|
| **SA-V** (Meta, SAM 2 training/eval) | masklets (binary masks), ~51k videos | **CC BY 4.0** (videos and annotations) | Licence permits commercial use with attribution; Meta's page adds "intended to be used for computer vision research for the purposes permitted under the CC BY 4.0 license" | V-page (Meta dataset page, HF README); S |
| DAVIS 2016/2017 | binary masks, 480p/full-res | Evaluation **code** BSD-3-Clause (LICENSE text read); the LICENSE says nothing about images/annotations; the download page states no licence, asks for citation | Not established for the data (internet-sourced videos) | V-text (code), V-page |
| MOSE / MOSEv2 | binary masks, complex scenes | **CC BY-NC-SA 4.0**, "non-commercial research purpose only" | No (NC); results could be published for research | V-page |
| YouTube-VOS | binary masks | – | – | not found |
| LVOS (long videos) | binary masks | – | – | not found |
| VideoMatte240K / PhotoMatte85 | alpha mattes (green-screen) | Repository **code** MIT; the datasets' own terms not stated in the README; download page unreadable | Not established | V-page (code only) |
| AM-2k, P3M-10k, Distinctions-646, AIM-500 (image matting) | alpha mattes | reported non-commercial research use (see matting research) | No | S (`docs/RESEARCH_2026-11-16_MATTING.md`) |
| Composition-1k (Adobe DIM) | alpha mattes | terms on request from Adobe | Not established | V-page |
| ST-ROTO synthetic shot (D-020) | exact masks | ours (Apache-2.0) | Yes | `research/probes/2026-11-15_video/make_synthetic_video.py` |

## Findings

1. **SA-V is the only large real-video set with ground truth found under a licence that permits commercial use and redistribution of results (CC BY 4.0, attribution).** It has binary masks, not alpha: good for tracking/review-flag calibration, not for matting quality.
2. No permissively licensed **video matting** ground truth was found; matting quality on real footage needs either owner-provided footage or synthetic composites (D-020 approach: our own foreground/background/alpha composites, as in `research/probes/2026-11-16_matting`).
3. DAVIS is the field's standard, but its data terms are not stated; MOSE is explicitly non-commercial.

## Recommendation (for OQ-13)

Approve a **small SA-V subset** (e.g. 20–50 videos from the validation split) for T-068 calibration, downloaded into `D:\ST-ROTO\data\benchmarks\` (git-ignored) with checksums and attribution in `NOTICE` for any published figures. Keep MOSE/DAVIS for internal, non-published comparison only if the owner accepts their terms. Until approved, calibration runs on synthetic shots only and is labelled provisional.

## Sources

- SA-V: https://ai.meta.com/datasets/segment-anything-video/ ; https://ai.meta.com/blog/segment-anything-2/
- DAVIS: https://github.com/davisvideochallenge/davis2017-evaluation/blob/master/LICENSE ; https://davischallenge.org/davis2017/code.html
- MOSE: https://henghuiding.github.io/MOSE ; https://github.com/henghuiding/MOSE-api
- VideoMatte240K: https://github.com/PeterL1n/BackgroundMattingV2 ; https://arxiv.org/abs/2012.07810
