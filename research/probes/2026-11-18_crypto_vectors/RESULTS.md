# Shapes from Cryptomatte, propagation along motion vectors (T-121, follow-up of T-110) — 2026-11-18

Synthetic CG shot of T-110 (`research/probes/2026-11-18_channels`: 24 frames, exact truth, vectors written
'u right, v up'). Both are traditional-roto assists: no AI, they work with AI disabled.

## Core (`probe_core.py` → `result_core.json`)

| | Result vs truth |
|---|---|
| Shapes from Cryptomatte 'target' (coverage > 0.5 → pieces.Sequencer, main + part shapes) | auto points (8): mean IoU **0.9975**, min 0.9904; 24 points: mean **0.9994**, min 0.998 |
| Propagation of a frame-0 key forward, plain per-point vectors (`warp_points`) | 0.9986 → 0.976 at frame 9, then **0.03** at frame 12 and never recovers (points inside the shape took the fast occluder's vectors) |
| ... with robust affine motion, first version (least-squares start) | **0.0** after frame 12 - worse: the start was poisoned by the occluder (fitted scale 0.16) |
| ... robust, median-vector start (`warp_points_robust`) | 0.976 at 9, **0.963 at 15, 0.949 at 21** (frames 11-12 lower only because the truth is the occluder-split VISIBLE part, the propagated shape is the whole object) |
| Backward from frame 23, plain / robust | plain 0.35 at frame 0; robust **0.945** at frame 0 |

`fit_affine_motion`: dominant affine motion inside the shape, robust start = median vector, then trimmed least
squares; each point keeps its own vector only if it agrees with the affine within 2 px.

## In Nuke (`tests/nuke` `test_crypto_shapes_and_propagation`, AI disabled)

* **Shapes from Cryptomatte** (`object name` = target_crypto, `source` = target): 24 keys, 8 points, 1 part shape,
  one undo step, provenance `imported_native` on object, shapes and keys; mean IoU 0.9975, min 0.9904.
* **Propagate along vectors**: hand keys (artist) on frames 0 and 20; forward from 0 filled frames 1-19 and
  **stopped before frame 20** (its key untouched); vector convention measured automatically ('u right, v up');
  IoU 0.996 (1) → 0.976 (9) → 0.955 (19); one undo step (back to the 2 hand keys). Backward from 20: 19 frames,
  mean IoU 0.939, stopped before frame 0.

## Limits

* Propagation drifts slowly (about 0.002 IoU per frame here) - hand keys every 10-20 frames keep it on track
  (propagation stops at them). Vectors must belong to the plate (renderer passes); vectors from optical flow on live
  action were not tested (Nuke's VectorGenerator gave unusable output headless, T-110).
* Synthetic CG only.
