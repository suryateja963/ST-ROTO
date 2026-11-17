# T-088 — Traditional roto with AI disabled (REQ-010, master prompt §3), 2026-11-17

§3: artists must be able to "disable AI entirely" and "complete an entire shot using traditional roto tools";
"AI must never become a requirement for basic operation".

## What was missing

- No way to switch AI off; the AI controls were always shown.
- Without ONNX Runtime, Track / Preview / Load model failed with a raw `ImportError` from the job.
- **Bug found:** "Save Roto edits to project" did nothing when no Track had run yet (no shot existed), so a purely
  hand-drawn shot was never recorded in the project. Earlier tests created the shot by hand and hid this.

## Changes

- Node checkbox **disable AI (traditional roto only)** and the session-wide environment variable `ST_ROTO_AI=off`:
  the 22 AI controls (prompts, box, model, device, points, Load model, Preview, Track, Resume, Re-track, Re-prompt)
  are hidden; any AI action refuses with a message that points to the traditional workflow; ViTMatte edges are
  refused (guided filter and hard edges are model-free and stay).
- AI actions first check that the AI runtime loads (`st_roto_ai.runtime`, which also switches ORT telemetry off)
  and otherwise say "the AI runtime (ONNX Runtime) is not installed or cannot load".
- `resync` / "Save Roto edits to project" creates the shot when shapes exist and no shot does.
- The node stores `knobChanged` / `onCreate` callbacks that re-apply the visibility; both are wrapped so a script
  still opens where ST-ROTO is not installed, and `knobChanged` reads `nuke.thisNode()` only for the AI checkbox
  (Non-commercial 10-node Python budget).

## Evidence

| test | result |
|---|---|
| `tests/nuke` `test_traditional_roto_without_ai` (headless; ONNX Runtime made unimportable) | Track refused: "AI runtime ... not installed"; after ticking disable AI: all 22 AI controls hidden, Preview refused; a hand-drawn 3-frame shape saved with no prior Track (object `hero`, keys 0-2, origin `artist_created`); guided-filter matte IoU 1.000 and hard matte 0.997 vs the drawn truth; ViTMatte refused; JSON/SVG export, RotoPaint copy, backup, package OK; no AI module (onnxruntime, torch, st_roto_ai.runtime/sam2/vitmatte) loaded |
| `gui_ai_toggle.py` (interactive Nuke, `result_gui_ai_toggle.json`) | ticking the checkbox hides 22/22 AI controls through the stored knobChanged callback; unticking shows 22/22 again |
| full headless Nuke suite + GUI track test | see `nuke_suite.txt` |

## Not covered

- Visibility after re-opening a saved script (onCreate) was not tested: Nuke Non-commercial saves encrypted
  scripts and re-opening in the same session costs node objects from the 10-node budget.
- Traditional tools beyond Nuke's own Roto (ST-ROTO adds no drawing tools of its own; §3 is met through Nuke's
  Roto + ST-ROTO's project, mattes, export and packaging).
- An install without ST-ROTO's AI packages at all (simulated here by blocking the import, not by a real install).
