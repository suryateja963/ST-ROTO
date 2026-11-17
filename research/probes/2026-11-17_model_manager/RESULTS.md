# T-101 — Model manager (REQ-052 / REQ-130, master prompt section 15), 2026-11-17

**Feature.** Dockable panel **ST-ROTO Models** (Windows › Custom; `st_roto_nuke.model_panel`, logic in
`st_roto_nuke.models_ui`, registry in `st_roto_ai.registry`):

| REQ-15 item | how |
|---|---|
| discovery, metadata, licence display | every model in every location: name, location, used copy, licence, owner approval, pinned revision, source repository, installed or not; licence tooltip if not in the production set |
| checksums | **Verify**: SHA-256 of every file again (ignores remembered results) |
| storage locations | lookup order **user** (`ST_ROTO_MODELS_USER`) -> **studio** (`ST_ROTO_MODELS_STUDIO`) -> **plugin** (built-in); a location exists only when its variable names an existing folder (ST-ROTO creates none); loading uses the first location that has the model; file verification infers its location from the file path |
| hardware / runtime compatibility | GPU memory need (T-092) vs this GPU per model; runtime and providers in the System report (T-091) |
| model testing, benchmarking | **Self-test**: tracks a generated moving disc (3 frames) from one click on this machine: IoU of every key and time per frame; ViTMatte: matting error on a disc |
| manual import | **Import...**: copies a model from another models folder into the user location, only if licence, owner approval, pinned revision and every checksum are right (nothing copied otherwise) |
| removal | **Remove...** (confirmation): deletes the copy's files; manifests stay as the record |
| installation, update approval | stays the owner-approved download tool (`tools/models/download_models.py`, rule 4): no download from the UI |

**Evidence.** `tests/nuke` `test_model_manager` (headless, CUDA; `results_test_model_manager.json`): rows - tiny
(D-015), large (owner request 2026-11-15), ViTMatte-S (D-032), all apache-2.0, used from the plugin location, GPU fit
tiny 3,916 / large 7,132 of 8,151 MiB; Verify tiny: 12 files OK in 1.7 s; Self-test tiny: CUDA, IoU 0.9966 / 0.9966 /
0.9935, 1.74 s per frame including model load (1.34 s from the imported copy); ViTMatte error 0.0002; import of tiny
into a temporary user location (12 files) -> that copy is used and passes its self-test; Remove -> the plugin copy is
used again. GUI (`gui_model_panel.py`, `result_gui_model_panel.json`): the panel lists the 3 models; Verify on tiny
-> "all files verified (12 files, 1.7 s)". Unit: `tests/unit/test_model_locations.py` (lookup order, inferred
location, tampered file and non-production licence detected, import refused without approval or with a wrong
checksum, removal keeps manifests).

**Not done (REQ-15 remainder):** several versions of one model side by side and rollback between them (one copy per
location today; a user-location copy overrides the plugin copy, which is a manual form of pinning), update approval
workflow (no updates without the owner, by rule).
