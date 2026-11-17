# T-095 — Sharper mask edges: measurement study (no product change), 2026-11-17

**Question.** T-080 found that the remaining shape error sits in the AI's mask, not in the spline. Is the loss caused
by SAM's low-resolution (256x256) mask output, and can a model-free or cheap change recover it?

**Method** (`edge_study.py`; SAM 2.1 tiny image predictor, CPU; the RIGHT object is given: ground-truth tight box +
its most interior pixel, the recommended prompt (T-082); frames where the object was not found (IoU < 0.5) are
excluded as a prompting problem). Variants of turning SAM's output into a mask:

| | variant |
|---|---|
| A | today: 256x256 logits, bilinear upscale, threshold 0 |
| B | A refined against the plate with the guided filter (`st_roto.matte.refine_alpha`, as used for soft mattes) |
| C | zoom: second pass on a crop around A's mask (25 % margin, >= 32 px), logits pasted back |
| C2 | zoom with wide context (100 % margin, >= 128 px) |
| O | oracle: the TRUTH pushed through the 256x256 grid and back - the most the mask format itself can lose |

Metrics: IoU; boundary F (boundary pixels within 2 px, DAVIS-style); mean distance of the predicted boundary to the
true one. Two truth sets, 306 frames each (51 objects x 6 frames, 30 videos):

1. **SA-V truth** (`edge_study.json`): real footage; but SA-V masks were annotated with SAM's help (SAM 2 data
   engine), so their edges are SAM-like.
2. **Exact-edge composites** (`edge_study_composite.json`, `--composite`): each real object cut out with its mask and
   pasted onto a frame of another video, so the truth is exactly the paste mask; edges are crisp and high-contrast by
   construction (easier than real edges).

## Results (frames with the object found: 295 / 299)

| variant | SA-V: IoU | SA-V: boundary F | SA-V: edge dist. | composite: IoU | composite: boundary F | composite: edge dist. |
|---|---|---|---|---|---|---|
| A today | **0.844** | **0.775** | 2.16 px | 0.926 | 0.948 | 0.80 px |
| B guided | 0.823 (better on 40 / worse on 139 frames) | 0.758 | 1.95 px | 0.974 (245 / 6) | 0.963 | 0.30 px |
| C zoom | 0.806 (60 / 188) | 0.726 | 2.84 px | **0.980** (234 / 20) | 0.976 | 0.56 px |
| C2 zoom wide | 0.833 (84 / 126) | 0.768 | 2.34 px | 0.974 (209 / 14) | **0.982** | 0.40 px |
| O 256 grid (limit) | 0.973 | 0.993 | 0.16 px | 0.974 | 0.992 | 0.16 px |

Small objects (box < 2 % of the frame) are 229 of 295 frames; same pattern (SA-V: A 0.834, C2 0.825; composite:
A 0.916, C 0.981). Cost on CPU: encode+predict 1.32 s/frame, guided 0.23 s, a zoom pass +1.21 s (GPU ~10x faster).

## Findings

1. **The 256x256 mask format costs at most ~0.027 IoU** (oracle 0.973-0.974), mostly on small objects.
2. **On crisp, exactly known edges the loss is real and recoverable**: today's path 0.926 vs the 0.974 limit; guided
   refinement or a zoom pass recover all of it (0.974-0.980, better on 70-80 % of frames). A zoom pass even beats
   the format limit, because the object gets more model pixels.
3. **On real footage judged by SA-V's truth, the same changes make IoU slightly worse** (-0.011 to -0.038). The
   gap to the limit there (0.844 vs 0.973) is mostly the model's region error (where it thinks the object is), not
   edge resolution; the large model addresses that (T-080: +0.045 mean IoU; T-093 'Re-track flagged').
4. Why they disagree is **not settled by these data**: either the SAM-assisted SA-V truth favours SAM-like edges,
   or real edges (soft, motion-blurred, low-contrast) mislead the refinement while pasted edges are artificially
   easy. Both are plausible; no test set here has precise edges on real footage.

## Recommendation (no product change made)

- Keep today's path as the default.
- Owner decision (OQ-29): (a) add an optional "edge refine: zoom (wide)" for crisp objects, labelled experimental,
  and/or (b) build a small precise-edge truth on real footage (an artist draws exact edges on ~20 frames of the
  owner's own or approved footage) to decide properly; (c) leave it. Recommendation: (b) first, then decide (a).
- Already available meanwhile: soft mattes use the guided filter (B) on the matte, not the shape.
