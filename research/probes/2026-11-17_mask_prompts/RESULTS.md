# T-100 — Rough masks as prompts: Roto shapes / polygons, mattes from other nodes, mask files (REQ-060), 2026-11-17

**Design.** Every rough mask becomes the prompt measured best on real footage (T-082): its tight box + a click on
the most interior pixel of each piece (largest first, up to 3; pieces under 2 % ignored) -
`st_roto.prompts.from_mask` / `set_from_mask`. Not fed as a MASK prompt on purpose: SAM 2 takes a mask input as the
final answer on its frame, so a rough polygon would stay rough; with box + clicks the AI draws the exact object.

**Node** (prompts section, hidden when AI is off): *prompt from* = **Roto shape** (a shape or polygon drawn in this
node: by name; a shape drawn only for this - not yet an ST-ROTO object - is removed from the Roto afterwards, so it
does not become an object itself) / **mask node** (alpha of any node in the script, by name, rendered on the current
frame) / **mask file** (PNG/TIFF/JPEG alpha or grey, EXR A/alpha; `####` / `%04d` = frame); *source*; **Use as
prompt** replaces the named object's prompts on the current frame. Then Track as usual. Masks of another size are
fitted like a default Reformat.

**Evidence** (`tests/nuke` `test_prompt_from_mask`, CUDA, `results_test_prompt_from_mask.json`; synthetic shot,
4 frames, one Track pass for all three):

| source | rough mask vs truth (IoU) | tracked keys vs truth: min / mean |
|---|---|---|
| crude polygon (6 px simplification, dilated 4 px) drawn in the node's Roto | 0.950 | 0.992 / 0.994 |
| rough SQUARE around the distractor disc in another Roto node | 0.610 | 0.985 / 0.987 |
| shrunken mask PNG (eroded 6 px) on disk | 0.894 | 0.991 / 0.994 |

The prompt-only polygon was removed from the Roto (status says so). Unit: `tests/unit/test_mask_prompts.py`.

**Not covered:** scribbles / brush strokes (open splines; Nuke's Roto has no brush in the ST_Roto node), text
prompts (no permissively licensed grounding model approved: Grounding DINO is not cleared for production, see
MODEL_REGISTER), real footage for these sources.
