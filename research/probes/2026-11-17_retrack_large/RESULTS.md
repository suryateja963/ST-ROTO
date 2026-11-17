# T-093 — Large model where it helps: 're-track model' and 'Re-track flagged', 2026-11-17

**Feature.** Node choice **re-track model** (*same as model* / *sam2.1-hiera-large* / *auto*) used by Re-track,
Re-track all, Re-prompt here and the new button **Re-track flagged**, which re-tracks only objects whose review flags
say the AI LOST them (`REVIEW lost ...`), in one pass. Workflow: track everything with the fast tiny model, then fix
the hard objects with the large one. Memory planning (T-092) applies to the re-track model.

**Evidence** (`tests/nuke` `test_retrack_flagged_large`, CUDA, `results_test_retrack_flagged_large.json`): synthetic
shot, hand-drawn key on frame 47, re-tracked backwards through the occluder, plus a second object (disc) tracked
cleanly from frame 0.

| | tiny (Re-track) | large (Re-track flagged) |
|---|---|---|
| frames lost (no key) | 6: 16-20, 22 | **0** |
| IoU on frames 16-20, 22 | - (no shape) | 0.9935-0.9959 |
| IoU on frames 10-15, 21, 24-26 | 0.984-0.995 | 0.987-0.997 |
| frame 23 (known split frame: the cut-off piece is a part shape, T-049) | 0.42 | 0.42 |
| disc (no lost flags) | - | skipped, keys unchanged |

On real footage the large model gained +0.045 mean IoU over 51 SA-V sequences, mostly through fewer lost frames
(T-080, `research/probes/2026-11-16_shape_fit/RESULTS.md`); this test shows the mechanism end to end in the node on
one synthetic case. Not measured: Re-track flagged on SA-V (the per-object gain there is from full large runs).
