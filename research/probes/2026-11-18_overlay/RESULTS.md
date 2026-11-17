# Review overlay in the viewer + settings presets (T-111, REQ-120 / REQ-121) — 2026-11-18

Nuke 17.1v3 Non-commercial, interactive GUI (screen captures of the viewer) and headless.

## What Python can show in the NC viewer (measured)

| Route | Result |
|---|---|
| Custom viewer drawing (OpenGL overlays, handles) | NDK only (T-033); NC cannot load plug-ins (D-011) |
| Viewer text: `ViewerWindow.showStatusMessage()` | takes NO arguments; `getStatusMessage()` returns None; no setter exists → no text from Python |
| Frame-change callback | `nuke.addKnobChanged(fn, nodeClass="Viewer")` fires with knob `frame` once the event loop runs (not synchronously inside `nuke.frame(n)`); `addUpdateUI` also fires |
| Roto shape overlay colour | attributes `ro, go, bo, ao` (rp.AnimAttributes.k*OverlayAttribute); animatable per frame, linear between keys; survive save + reopen (`probe_overlay_attrs.py`) |
| … drawn in the viewer? | yes, while the Roto's controls are open: a shape keyed magenta drew 162 magenta pixels, keyed green 178 green pixels (screen capture; `widget.grab()` does not capture OpenGL, the viewer area comes out black) |
| `ao = 0` | Nuke's default outline colour (RED in this setup) → ST-ROTO uses magenta for LOST, not red |

## Built

* **Review colours on the shapes** (`roto_export.apply_review_colours`, knob *review colours on shapes*, default on):
  per frame, MAGENTA = lost, YELLOW = check, Nuke's default elsewhere; keys only at the first and last frame of each
  run of equal colour, so interpolation is constant on whole frames (`views.colour_runs`, unit-tested by
  interpolating like Nuke). Re-applied after every sync (Track, Re-track, Save Roto edits), after the channel check
  and when the checkbox changes; off removes every overlay key.
* **Show shapes in viewer** (button): refreshes the colours and opens the inner Roto's controls.
* **this frame** (readout on the node): the flags of the frame the viewer shows, with reasons, updated by the Viewer
  frame callback (`views.review_levels`: worst level per frame, every reason).
* **Presets** (`st_roto.presets`): built-in (Quick look, Final quality, Traditional roto (AI off), CG plate with
  passes, Stereo), studio (`ST_ROTO_PRESET_DIR`, read-only), user (`%USERPROFILE%/.st_roto/presets` or
  `ST_ROTO_USER_PRESET_DIR`, created only when the artist saves one); user > studio > built-in by name. Only node
  SETTINGS (27 knobs incl. linked inner-Roto knobs: replace alpha, motion blur), never shot data; wrong types and
  unknown keys are rejected; choices not offered by an older node are skipped and reported.

## Tests

* Unit: `tests/unit/test_presets.py` (priority, validation, broken / newer files, delete only own, colour runs constant
  on whole frames, worst level per frame).
* Headless Nuke `test_review_overlay_and_presets`: colours keyed exactly (frame 4 lost = 1,0,1,1; frame 7 check =
  1,0.85,0,1; other frames ao = 0), off again; readout "frame 7: hero CHECK: …", "frame 2: no flags"; built-in preset
  applied; own preset saved, re-applied (band 7, inner Roto replace off), deleted; built-in cannot be deleted.
* GUI `gui_review_overlay.py` (product path: Show shapes in viewer, artist changes frames): magenta outline pixels
  frame 2 / 4 / 7 = 0 / 165 / 0; yellow above the screen's baseline (the NC start-up dialog's warning icon) only on
  frame 7 (+185 px); the readout followed the viewer to 2, 4 (LOST + reasons) and 7 (CHECK). Added to the acceptance
  run's GUI list.

## Limits (honest)

* Colours show only while the shapes' Roto controls are open (that is when Nuke draws Roto outlines); there is no
  always-on HUD and no confidence heat map in the image (would need the NDK or extra nodes).
* Shortcuts, toolbars, layouts, themes, workspaces (rest of REQ-121) are not part of this task.
