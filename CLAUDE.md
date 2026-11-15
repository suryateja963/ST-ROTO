# ST-ROTO — working instructions for Claude Code (read first every session)

ST-ROTO = free, open-source (Apache-2.0) AI-assisted **and** traditional rotoscoping inside Foundry Nuke.
Owner's full specification: `docs/MASTER_PROMPT.md` (authoritative). Public repo: https://github.com/suryateja963/ST-ROTO

## Where things stand (update this section at the end of every session)

- **Last session ended 2026-11-16** at commit `53765f8`. Phase 1 done, Phase 2 architecture **approved** (D-026), Phase 3/4 in progress.
- Working in Nuke 17.1 NC (product code, tested): ST_Roto node → include/exclude prompts (XY handle) → Preview → Load model → Track (SAM 2.1 video, ONNX Runtime CUDA in-process) → animated native Roto shape; artist edits in Roto are imported (never overwritten); Re-track uses artist keys as mask prompts, forward + reverse; per-frame confidence with review flags (LOST / CHECK); object panel (rename/lock/delete/undo/redo).
- Tests: `pytest` 49/49 · headless Nuke 7/7 (`tools/run_nuke_tests.py`) · GUI test passes · CI green (Win/Linux, py3.9/3.11, real py3.7 run).
- **Next tasks (in order):** T-065 bounded/disk-backed tracker state for long shots (now ~2 MB RAM per tracked frame, R-42) → T-067 several objects per tracking pass → then see `TASK_BOARD.md` "Ready".
- **Open owner questions:** OQ-16/17 (supervisor lock override: confirm "only if holder offline/idle", and the idle threshold). Everything else answered — see `DECISION_REGISTER.md` (D-001..D-029).

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
- Project venv: `D:\ST-ROTO\.venv` (Python 3.11.18, CPU torch 2.15, transformers 5.23, onnx, onnxconverter-common, pytest). Packages imported **inside Nuke**: `D:\ST-ROTO\.tools\nuke-py311` = **onnxruntime-gpu 1.26.0** (last CUDA-12 build; 1.27+ need CUDA 13 and silently fall back to CPU), numpy 2.4.6, opencv-python-headless 5.0 (no EXR → use float TIFF).
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

- `src/st_roto/` core, pure Python **3.7-compatible**, must not import nuke/Qt/onnxruntime (enforced by `tests/unit/test_layering.py`): model, store (SQLite, schema v3), commands (op log, undo, batch, REQ-042 protection), geometry (Bézier fitting, sub-pixel contours), jobs, prompts, views, quality.
- `src/st_roto_ai/` AI layer (no nuke/Qt): runtime (session cache, honest device report, arena shrink), sam2 (image + video tracker port, mask prompts, reverse), resize (exact torch AA resize).
- `src/st_roto_nuke/` Nuke adapter: node (ST_Roto group), track, roto_export (sync/import), session, panel, pixels, colour, convention.
- `nuke_plugin/` init/menu · `tests/unit`, `tests/nuke` · `research/probes/*/RESULTS.md` = evidence for every measured claim.

## Measured pitfalls (do not re-learn these)

- Nuke NC: max 10 Python-accessible Node objects per session (cache node refs; one Nuke test per process); renders capped at 1920×1080; headless `-t` has no GPU for Nuke's own nodes unless `--gpu`.
- Roto API: tangent = **2 ×** Bézier handle offset, `leftTangent` → previous point; keys added after `Shape.append()` are silently lost (key first, then append); `Layer.remove()` takes an index; negative frames are written as `name.-002.tif`.
- Exceptions in `nuke.executeInMainThread` callbacks are swallowed → always catch and write to the status knob.
- ORT session creation holds the GIL (UI pause) → cached sessions + "Load model" button. ORT CUDA pool grows across runs → arena shrinkage after memory attention; fp16 memory attention is default (D-029).
- cv2.findContours sits 0.5 px inside the mask edge → use `st_roto.geometry.trace_contours`. cv2.fillPoly paints outlines (biased reference).
- PowerShell: put multi-line Python in files (here-strings/escaping broke several commands); `$LASTEXITCODE` is unreliable after pipelines.
