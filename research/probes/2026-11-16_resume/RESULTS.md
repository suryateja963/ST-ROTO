# Resumable tracking (T-048) — 2026-11-16

**Claim:** a Track that is cancelled, fails, or dies (crash / power loss) continues from its checkpoint with results IDENTICAL to an uninterrupted run.

**Mechanism.** `Sam2Video.save_state/load_state` (conditioning frames + every tracked frame's memory; the bounded RAM store exports/imports its entries, `SpillDict.export_to/import_from`), `pieces.sequencer_state` (shape building), per-object reports / absent frames. `track_objects(checkpoint_dir=…)` writes a checkpoint every 10 frames and on Cancel; tracked-frame files are immutable and written once (incremental), `meta.json` (run definition + next frame) is replaced atomically LAST, so an interrupted checkpoint leaves the previous one valid. A finished run deletes its checkpoint. Resume refuses a different run (prompts, frames, model, colour, point setting).

**Evidence.**
- Unit (CPU, 2 objects, 10 frames, `tests/unit/test_resume.py`): cancel before frame 5 → resume == uninterrupted (keys, parts, reports, absent frames, provenance); exception in the middle of frame 7 with checkpoints every 3 frames → resumes from frame 6 → identical; different prompts refused.
- Nuke (`test_cancel_and_resume_track`): Cancel during frame 5 → status "cancelled - 'Resume track' continues from frame 6"; changed 'AI input colour' refused; resume with the node's prompts cleared (definition comes from the checkpoint) → 12 keys, IoU 0.993–0.996, checkpoint removed.
- Cost (GPU, 48 frames, 2 objects, `probe_checkpoint_cost.py`): 20.42 → 20.69 s and 20.53 → 20.78 s (**+1.2–1.3 %**). Checkpoint size near the end: **231 MB** (≈ 2.4 MB per object-frame), removed when the run finishes.
