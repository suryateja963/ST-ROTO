# T-096 — Precise-edge truth kit (OQ-29, owner: "continue with your recommendation"), 2026-11-17

**Purpose.** T-095 could not decide whether edge refinement helps on real footage, because SA-V's truth is
SAM-assisted. The decision needs a small truth with precise edges on real footage, drawn by an artist. Claude cannot
draw it; this task builds everything around the drawing and proves the pipeline end to end.

**Kit** (`tools/edge_truth/`; data in `data/edge_truth/`, git-ignored, SA-V subset D-031, CC BY 4.0):

- `make_kit.py`: picks 20 SA-V frames where T-095's methods disagreed most (one per object; 8 portrait 1080x1920,
  6 portrait 720x1280, 3 landscape 1920x1080, 3 landscape 1280x720), pads each (never scaled: pixels and edges
  exact) top-left onto one 1920x1920 canvas so ONE ST_Roto node holds the kit (Nuke NC: 10 Python nodes per
  session); writes `plate.####.png`, `reference.####.png` (object outlined and boxed in magenta, a pointer only),
  `manifest.json`, `INSTRUCTIONS.md`.
- `open_kit.py`: `Nuke17.1.exe --nc tools/edge_truth/open_kit.py` -> plate Read, reference Read, ST_Roto node
  'draw_truth' with AI switched off, project `data/edge_truth/edge_truth.stroto`, frames 1-20.
- `export_truth.py`: union of the shapes keyed on each frame (shapes named `hole...` subtracted), rasterised exactly
  from the stored splines, cropped to the frame's real size -> `truth.####.png`; lists frames not drawn yet.
- `research/probes/2026-11-17_edges/edge_study.py --truth data/edge_truth [--truth-dir D] [--tag T]`: T-095's
  variants scored against the drawn truth, plus how far SA-V's own mask is from it.

**Pipeline test with a SIMULATED artist** (`simulate_artist.py`, headless Nuke; NOT a truth): kit opened with a
throw-away project, one shape per object piece fitted to SA-V's mask and keyed only on its frame, plus a `hole`
shape; 'Save Roto edits to project'; export into a throw-away folder. Result (`result_simulate_artist.json`): AI off,
20 / 20 frames exported at their real sizes, IoU vs what was drawn 0.983-1.000 (mean 0.995; the rest is the 96-point
spline fit), hole subtracted. The comparison then ran on that truth (`edge_study_simulated.json`): it reproduces the
SA-V picture on these 20 hard frames (A 0.791, B 0.786, C 0.697, C2 0.764; SA-V vs truth 0.993, as built), which
only proves the evaluation step works.

Two bugs found and fixed while building: renaming the kit's ST_Roto node dropped ST-ROTO's inner-node cache (the
product copes but spends Non-commercial node budget, so `open_kit` carries the cache over); the first simulation drew
one outline per object, wrong for objects in two pieces (frames 9, 10, 12) - an artist draws each piece.

**Waiting for:** the owner (or an artist) drawing the 20 frames (INSTRUCTIONS.md; ~5-15 min per frame). Then Claude
runs `export_truth.py` and `edge_study.py --truth data/edge_truth` and reports which edge method wins on real
footage.
