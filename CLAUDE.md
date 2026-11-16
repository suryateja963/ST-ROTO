# ST-ROTO — working instructions for Claude Code (read first every session)

ST-ROTO = free, open-source (Apache-2.0) AI-assisted **and** traditional rotoscoping inside Foundry Nuke.
Owner's full specification: `docs/MASTER_PROMPT.md` (authoritative). Public repo: https://github.com/suryateja963/ST-ROTO

## Where things stand (update this section at the end of every session)

- **Last session ended 2026-11-16** (all work below committed and pushed). Phase 1 done, Phase 2 architecture **approved** (D-026), Phase 3/4 in progress.
- Working in Nuke 17.1 NC (product code, tested): ST_Roto node → prompts for **several objects** (XY handle, per object name) → Preview → Load model → Track (all prompted objects in one pass, SAM 2.1 video, ONNX Runtime CUDA in-process) → animated native Roto shapes; artist edits imported (never overwritten); Re-track object / **Re-track all** (artist keys as mask prompts, forward + reverse); review flags (LOST / CHECK); **Render mattes (EXR)** (layer per object + combined alpha, model-free soft edges); **JSON/SVG export, JSON import**; Roto **motion blur** knobs; **auto-backups, crash detection + recovery, portable packages**; object panel.
- Tests: `pytest` 75/75 · headless Nuke 12/12 (`tools/run_nuke_tests.py`) · GUI test passes · CI green (Win/Linux, py3.9/3.11, real py3.7 run).
- Session 2026-11-16 finished the owner's list: T-067 multi-object, matting step 1 (research + soft edges), T-069/T-070 mattes + EXR + JSON/SVG, T-071 persistence, T-074 motion blur. Evidence in `DEVELOPMENT_LOG.md` and `research/probes/2026-11-16_*`.
- **Next tasks (proposal, owner to confirm order):** learned matting model for hair (blocked on OQ-22) → T-075 package unpack UI + relink dialog + source fingerprints → T-073 RotoPaint export + feather storage → T-068 review-threshold calibration on real footage (needs OQ-13 footage) → T-056 model registry with checksum verification → T-045 OCIO colour transform.
- **Open owner questions:** OQ-22 (learned matting model, recommendation ViTMatte-S optional), OQ-16/17 (supervisor lock override), OQ-13 (benchmark footage). See `OPEN_QUESTIONS.md`, `DECISION_REGISTER.md` (D-001..D-029).

## Non-negotiable rules (from the owner)

1. Everything stays in `D:\ST-ROTO` (D-001/D-006): code, models, venvs, caches, probes. Use the session scratchpad only for throw-away files.
2. Never claim untested work is done; label prototypes; report failures and own mistakes honestly in `DEVELOPMENT_LOG.md`.
3. Never silently reduce scope (§28). C++/NDK/Deep stay mandatory for 1.0 but are deferred until a plug-in-capable licence (D-011).
4. No model download without owner approval (§15). Approved so far: D-015 + SAM 2.1 large. Weights and exports are never committed (`models/weights/`, `models/onnx/` ignored; checksums in `models/manifests/`).
5. Privacy: never publish the owner's email. Commits use `suryateja963` / `74024559+suryateja963@users.noreply.github.com` (repo-local git config). Before each commit run: `git grep --cached -i -n -e surya -e gmail | Select-String -NotMatch 'suryateja963'` → must print nothing.
6. Ask before system-wide changes (installs outside the project, NUKE_PATH, ~/.nuke). The owner has NOT enabled the plugin in their Nuke yet (see `docs/USER_GUIDE_v0.md`).
7. Commit + push after every verified milestone; update registers (TASK_BOARD, DEVELOPMENT_LOG, RISK/REQUIREMENTS/DECISION registers as relevant). End commit messages with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
8. Validate AI ports against the upstream PyTorch reference before trusting them; measure, don't assume.

## Environment (measured)

- Windows 11, i7-13700HX, 16 GB RAM, RTX 5060 Laptop 8 GB (driver 621.24). Nuke **17.1v3 Non-commercial** at `C:\Program Files\Nuke17.1v3\Nuke17.1.exe` (Python 3.11.11, PySide6 6.5.3, CUDA 12.8, cuDNN 9.7.1).
- Project venv: `D:\ST-ROTO\.venv` (Python 3.11.18, CPU torch 2.15, transformers 5.23, onnx, onnxconverter-common, pytest). Packages imported **inside Nuke**: `D:\ST-ROTO\.tools\nuke-py311` = **onnxruntime-gpu 1.26.0** (last CUDA-12 build; 1.27+ need CUDA 13 and silently fall back to CPU), numpy 2.4.6, opencv-python-headless 5.0 (no EXR → use float TIFF), openexr 3.5.4 (EXR mattes).
- uv: `D:\softwares\uv\uv.exe`; always set `$env:UV_PYTHON_INSTALL_DIR="D:\ST-ROTO\.tools\uv-python"; $env:UV_CACHE_DIR="D:\ST-ROTO\.tools\uv-cache"`.
- GitHub CLI: `C:\Program Files\GitHub CLI\gh.exe` (logged in as suryateja963).
- Hardware logger (crash diagnosis, laptop had 2 sudden power-offs on 2026-11-15): `tools/monitoring/hw_logger.ps1` → `logs/hardware/` (restart it if not running).

## Commands

- Unit tests: `.venv\Scripts\python.exe -m pytest`
- Headless Nuke tests (each in its own process because of the 10-node cap): `.venv\Scripts\python.exe -I tools\run_nuke_tests.py`
- GUI test: `Start-Process "C:\Program Files\Nuke17.1v3\Nuke17.1.exe" -ArgumentList '--nc','"D:\ST-ROTO\tests\nuke\gui_track_slice.py"'` → `tests/nuke/out/gui_track_slice.json`
- Model pipeline: `tools/models/download_models.py`, `export_sam2_onnx.py` (image), `export_sam2_video_onnx.py` (video, also makes fp16 memattn), `convert_fp16.py`.
- Synthetic test shot: `research/probes/2026-11-15_video/make_synthetic_video.py` (frames are git-ignored; regenerate if missing).

## Code map

- `src/st_roto/` core, pure Python **3.7-compatible**, must not import nuke/Qt/onnxruntime (enforced by `tests/unit/test_layering.py`): model, store (SQLite, schema v3), commands (op log, undo, batch, REQ-042 protection), geometry (Bézier fitting, sub-pixel contours), jobs, prompts (per object), views, quality, matte (guided-filter soft edges), exr (OpenEXR writer, lazy import), interchange (JSON/SVG), persistence (backups, crash recovery, packages).
- `src/st_roto_ai/` AI layer (no nuke/Qt): runtime (session cache, honest device report, arena shrink), sam2 (image + video tracker port, mask prompts, reverse), resize (exact torch AA resize).
- `src/st_roto_nuke/` Nuke adapter: node (ST_Roto group), track (multi-object), mattes, roto_export (sync/import), session (marker, recovery, auto-backup), panel, pixels, colour, convention.
- `nuke_plugin/` init/menu · `tests/unit`, `tests/nuke` · `research/probes/*/RESULTS.md` = evidence for every measured claim.

## Measured pitfalls (do not re-learn these)

- Nuke NC: max 10 Python-accessible Node objects per session (cache node refs; one Nuke test per process); renders capped at 1920×1080; headless `-t` has no GPU for Nuke's own nodes unless `--gpu`.
- Roto API: tangent = **2 ×** Bézier handle offset, `leftTangent` → previous point; keys added after `Shape.append()` are silently lost (key first, then append); `Layer.remove()` takes an index; negative frames are written as `name.-002.tif`.
- Exceptions in `nuke.executeInMainThread` callbacks are swallowed → always catch and write to the status knob.
- ORT session creation holds the GIL (UI pause) → cached sessions + "Load model" button. ORT CUDA pool grows across runs → arena shrinkage after memory attention; fp16 memory attention is default (D-029).
- cv2.findContours sits 0.5 px inside the mask edge → use `st_roto.geometry.trace_contours`. cv2.fillPoly paints outlines (biased reference).
- PowerShell: put multi-line Python in files (here-strings/escaping broke several commands); `$LASTEXITCODE` is unreliable after pipelines.
- Tracker spill budget per object must be ≥ 16 frames (each step reads the previous 15): below that every step reloads from disk (5,208 reloads measured).
- On Windows never use `os.kill(pid, 0)` to test a process: it terminates it. Use `st_roto.persistence._pid_alive` (OpenProcess).
- The command bus refuses key writes into LOCKED objects for every actor (import too): apply locks after keys.
- Objects created in the same second sort by id (`store.objects`): tests must look objects up by name.
- Nuke reads EXR channel `<layer>.A` as `<layer>.alpha` and plain `A` as `rgba.alpha` (measured).
- The Bash tool breaks on heredocs with nested quotes in some commands: write multi-line edit scripts to the scratchpad with the Write tool, then run them.
- `tests/nuke/run_nuke_tests.py` has CRLF line endings: string-replace scripts with LF text silently miss; use the Edit tool.
- OCIO `applyRGB` is in place; never pass the caller's array (`st_roto.colour.OcioTransform` copies).
- Nuke Non-commercial saves scripts ENCRYPTED (`.nknc`): never edit them as text; relink knobs after opening (`st_roto_nuke.packages.apply_relink_to_open_script`).
- Nuke reports Read paths as `d:/…/name_%04d.ext` (lowercase drive, %04d) even if set as `D:/…/name_####.ext`: compare paths case-insensitively and accept both frame spellings.
- This Bash tool collapses `\` to `\` even inside quoted heredocs: put Python edit scripts in files with the Write tool (`tools/dev/replace_functions.py` replaces whole functions, CRLF-safe).
- Nuke NC CatFileCreator writes `.catnc` (not `.cat`); create via `nuke.execute(node, nuke.FrameRanges([1]))`. TorchScript must come from torch 2.7.x (`.tools/torch27-venv`), Nuke's libtorch.
