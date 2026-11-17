# T-097 — Propagation controls: range re-track, exclude frames, lock range (REQ-091), 2026-11-17

**Feature** (ST_Roto node, AI section; hidden when AI is off):

- **re-track range** = *whole shot* / *from-to* (+ *from*, *to*): Re-track, Re-track all, Re-track flagged and
  Re-prompt here work only on frames from..to. The object's existing keys just outside the range (from-1, to+1) are
  used as guides and stay unchanged, so the re-tracked interval joins its neighbours (REQ-11-13, REQ-11-16).
- **exclude frames** (e.g. `12-14, 30`, `st_roto.frames.parse`): the AI neither processes nor changes these frames in
  Track and Re-track; existing keys stay; skipped with true time positions like unreadable frames (T-086) and
  reported as "excluded by you" (REQ-11-15). A prompt or guide frame that is excluded is refused with a message.
- **Lock range / Unlock range**: the named object's keys on from..to are locked (main shape's generator
  `locked_frames`, one undoable op): every re-track uses them as guides and never changes them; listed as
  `guide_frames` in the re-track record, apart from artist keys (REQ-11-14).

Enforcement is in the re-track path (locked/anchor frames are conditioning frames, which never appear in a result);
the command bus itself does not block AI writes to locked frames (no other AI path writes existing shapes).

**Evidence** (`tests/nuke` `test_propagation_controls`, CUDA, `results_test_propagation_controls.json`; synthetic
shot, 30 frames): Track (tiny) -> lock 5-7, exclude 12-13 -> Re-track with the LARGE model: exactly frames 5, 6, 7,
12, 13 unchanged, every other key re-tracked; guide frames [5, 6, 7]; status "excluded by you (not processed, keys
unchanged): 12-13". Range re-track 15-19 (tiny): exactly frames 15-19 changed, IoU 0.993-0.996 vs truth (edges of the
range included); status "frames 15-19 only (keys outside unchanged)". One undo restores the previous keys; Unlock
range clears the lock. Unit: `tests/unit/test_frames.py`.

**Not done** (REQ-091 remainder): reviewing alternative propagation candidates (REQ-11-18). "Replace tracking
references" is covered by Re-prompt here (T-081) and artist keys.
