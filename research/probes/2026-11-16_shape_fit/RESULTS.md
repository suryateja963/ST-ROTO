# T-080 — Where does shape accuracy go on real footage? (2026-11-17)

**Question.** On the SA-V subset (D-031) correctly tracked frames reach only about 0.85–0.93 IoU. Is the spline
(point count) losing accuracy, and would another default count be clearly better?

**Method.** `probe_point_counts.py`, run inside Nuke 17.1 (`--nc -t`, CUDA, device recorded in the result files).
51 sequences (30 videos), box prompt on the first visible frame, every 2nd frame scored against the SA-V truth
(2,005 frames). One tracking pass per sequence; the **same logits** feed every shape builder, so only the shape
step differs:

- `raw`: the AI's pixel mask (logits > 0), the ceiling set by the model;
- `outline`: its traced outer contours filled as polygons, the ceiling for any spline without holes;
- `auto`, `16`–`64`: `pieces.Sequencer` (main and part shapes) with that point count; `auto` is today's default
  (count chosen on the prompt frame, then constant).

Rasterisation: vectorised even-odd fill, checked equal to `geometry.rasterize_closed` on 200 random polygons
(`--selftest`). Analysis: `analyse_point_counts.py` → `analysis_point_counts.json`.

## Results (mean IoU)

"found" = frames where the AI mask overlaps the truth at IoU ≥ 0.5 (the fit question). "all" includes the frames
where the tracker lost the object or followed something else.

| model | frames found | | raw | outline | **auto** | 16 | 24 | 32 | 48 | 64 |
|---|---|---|---|---|---|---|---|---|---|---|
| tiny  | 1582 / 2005 | found | 0.8460 | 0.8461 | **0.8453** | 0.8402 | 0.8444 | 0.8454 | 0.8460 | 0.8461 |
|       |             | all   | 0.6829 | 0.6830 | **0.6824** | 0.6783 | 0.6816 | 0.6824 | 0.6828 | 0.6829 |
| large | 1692 / 2005 | found | 0.8576 | 0.8576 | **0.8549** | 0.8514 | 0.8557 | 0.8568 | 0.8574 | 0.8575 |
|       |             | all   | 0.7364 | 0.7363 | **0.7341** | 0.7311 | 0.7347 | 0.7356 | 0.7361 | 0.7362 |

Per frame (found frames), auto vs the raw mask: tiny −0.0007 on average (over 0.01 below on 101 of 1,582 frames),
large −0.0027 (over 0.01 below on 191 of 1,692). Where auto chose 8–16 points, 64 points gains 0.004–0.008 on
average; for auto counts ≥ 20 the difference is ≤ 0.001.

Large vs tiny, per sequence (mean raw IoU): large better by > 0.05 in 13 of 51 sequences, tiny in 3; mean
+0.045, median +0.009. Most of the gain comes from finding the object more often (1,692 vs 1,582 found frames);
on found frames the gain is +0.012. Run time (tracking + scoring, same work) 4,118 s vs 3,010 s: large is
about 1.4× slower here.

## Conclusions

1. **The spline is not the limit.** The traced outline equals the AI mask (within 0.0001), and today's auto
   spline is within 0.003 of it. The remaining ~0.15 IoU gap on found frames is in the **model's mask** itself
   (SAM 2 predicts at 256×256 and upsamples), not in the conversion to Roto shapes.
2. **Default point count: unchanged (auto).** A fixed 48 or 64 points would gain at most 0.0026 mean IoU
   (large) at the cost of 2–8× more points for the artist to edit; that is not "clearly better". Fewer points
   (16) is clearly worse. The small loss is concentrated in shapes where auto chose 8–16 points; a higher auto
   floor could recover ~0.005 there, too small to justify changing artist-facing defaults now.
3. **The larger model is the available quality gain** on real footage: +0.045 mean IoU overall, mostly
   fewer lost / wrong-object frames. It is already selectable in the node (*model*); the default stays tiny
   (speed, memory) pending the owner's choice; the user guide now states the trade-off.
4. Closer shapes beyond this need a better mask, not a better spline: mask refinement at full resolution
   (e.g. the existing guided-filter / ViTMatte edge step applied to the shape, or a high-resolution refinement
   model) — a candidate for a later task, needs measurement first.

## Files

- `probe_point_counts.py`, `analyse_point_counts.py` (this folder)
- `result_point_counts_sam2.1-hiera-tiny.json`, `result_point_counts_sam2.1-hiera-large.json` (per-frame rows),
  `analysis_point_counts.json`
- Logs: `data/benchmarks/shape_fit_tiny.log`, `shape_fit_large.log` (local, git-ignored)
