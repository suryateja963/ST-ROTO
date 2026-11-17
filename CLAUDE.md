# ST-ROTO — working instructions for Claude Code (read first every session)

ST-ROTO = free, open-source (Apache-2.0) AI-assisted **and** traditional rotoscoping inside Foundry Nuke.
Owner's full specification: `docs/MASTER_PROMPT.md` (authoritative). Public repo: https://github.com/suryateja963/ST-ROTO

## Where things stand (update this section at the end of every session)

- **Last session: 2026-11-17/18** (T-080..T-109); everything committed and pushed. Phase 1 done, Phase 2 approved (D-026), Phase 3/4 in progress. No owner question is open.
- **Product (Nuke 17.1 NC, tested):** ST_Roto node: prompts (clicks, box, or rough masks from a Roto shape / another node's alpha / a mask file) for several objects -> Track (SAM 2.1 ONNX/CUDA in-process, checkpointed, Resume) -> native animated Roto shapes; Re-track / Re-track all / Re-track flagged (re-track model, e.g. large) / Re-prompt here; range re-track, exclude frames, Lock range (enforced in the command bus); model auto by free GPU memory with CPU fallback; difficult sequences (missing frames, gaps, proxy, mixed resolution, plates above HD in NC); AI-off mode (traditional roto); **stereo / multi-view (T-109): 'track every view' -> one object per view (objects.view/pair, schema v11), other views prompted by a disparity search, shapes limited to their view, per-view re-track and mattes, stereo consistency CHECK flags**; mattes EXR (guided / ViTMatte / hard, size full or fit 1920x1080 = NC default, holdout / garbage roles, RGB premult/straight, offset, blur, core/edge, version folders when files are in use); JSON/SVG export, RotoPaint copy, delivery packages, project packages, backups + crash recovery; Objects pane (roles, merge, leases/keys/roles, timeline), Models pane, System report; Windows installer + ST-ROTO-Setup.exe.
- **Tests:** unit 216 (CI, Python 3.7-3.11) · headless Nuke 36 (`tools/run_nuke_tests.py`) · 5 GUI probes · acceptance run `tools/acceptance/run_acceptance.py` (latest report in `docs/acceptance/`; not rerun after T-109, but unit/Nuke/GUI all pass).
- **Status of 1.0:** `docs/ACCEPTANCE.md`: 3 met (v0), 16 partly, 1 not met (verified compatibility: only 17.1 NC tested). `DEFECTS.md`: 1 open (DEF-009 unsigned exe, minor); DEF-010 (AI actions failed in any multi-view script) fixed in T-109. Benchmark methodology v1 published (`docs/BENCHMARK_METHODOLOGY.md`), no competitor run (no lawful access).
- **Task board:** Ready T-110..T-120 (extra channels, overlays/presets, node family, Alembic, model versions, decontamination, DirectML, other Nuke versions, real shot, stereo resume T-119, multi-camera from camera data T-120); blocked T-011b (NDK: licence) and T-077 (Silhouette/Mocha: apps) - owner said to ignore these two.
- **Decisions:** D-035..D-043 (leases/idle/signing, key folder, D-039 mixed resolution fit, D-040 firewall rule KEPT: Nuke has no network on this machine on purpose, D-041 NC matte default fit 1920x1080, D-042 keep git history, D-043 edge-drawing study dropped - do not ask again); D-044 stereo data model (proposed, delegated).
- **Machine state:** Windows Firewall rule blocks Nuke17.1.exe outbound (D-040). PyInstaller is in .venv. The owner has NOT installed ST-ROTO into their own Nuke yet (installer only tested in temporary folders).

## Non-negotiable rules (from the owner)

1. Everything stays in `D:\ST-ROTO` (D-001/D-006): code, models, venvs, caches, probes. Use the session scratchpad only for throw-away files.
2. Never claim untested work is done; label prototypes; report failures and own mistakes honestly in `DEVELOPMENT_LOG.md`.
3. Never silently reduce scope (§28). C++/NDK/Deep stay mandatory for 1.0 but are deferred until a plug-in-capable licence (D-011).
4. No model download without owner approval (§15). Approved so far: D-015 + SAM 2.1 large. Weights and exports are never committed (`models/weights/`, `models/onnx/` ignored; checksums in `models/manifests/`).
5. Privacy: never publish the owner's email or local user name/paths (redact temp paths in probe outputs). Commit ONLY via `tools/dev/commit_checked.ps1 -MessageFile <file>` (it aborts on any privacy match). Commits use `suryateja963` / `74024559+suryateja963@users.noreply.github.com` (repo-local git config). Before each commit run: `git grep --cached -i -n -e surya -e gmail | Select-String -NotMatch 'suryateja963'` → must print nothing.
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

- `src/st_roto/` core (store schema v10), pure Python **3.7-compatible**, must not import nuke/Qt/onnxruntime (enforced by `tests/unit/test_layering.py`): model, store (SQLite), commands (op log, undo, batch, REQ-042 protection), geometry (Bézier fitting, sub-pixel contours), jobs, prompts (per object), views, quality, matte (guided-filter soft edges), exr (OpenEXR writer, lazy import), interchange (JSON/SVG), persistence (backups, crash recovery, packages, fingerprints), pieces (split objects), colour (derived matrices + OCIO), calibration, sync (replication prototype), leases (object leases, presence, roles; checked by the command bus for ops made locally), signing (pure-Python Ed25519, signed ops, verify_log).
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
- CI installs only `requirements-dev.txt` (no onnxruntime/torch/models). Every test module must import AI packages lazily or `importorskip` them; run `tools/dev/pytest_without_ort.py` before pushing, and check `gh run list --limit 1` after pushing (CI was red for 8 commits, 2026-11-16..17, unnoticed).
- `tests/nuke/run_nuke_tests.py` has CRLF line endings: string-replace scripts with LF text silently miss; use the Edit tool.
- OCIO `applyRGB` is in place; never pass the caller's array (`st_roto.colour.OcioTransform` copies).
- Stereo: a Write without %V must be executed with `views=[v]` in a multi-view script (else it fails); Roto shape view = attributes `nv` + `view1..n` (1-based view indices).
- Nuke Non-commercial saves scripts ENCRYPTED (`.nknc`): never edit them as text; relink knobs after opening (`st_roto_nuke.packages.apply_relink_to_open_script`).
- A Nuke Read node keeps an EXR open: on Windows the file cannot be replaced (Access is denied) until Nuke lets go - clearRAMCache/clearDiskCache/reload/emptying the file knob do NOT release it (T-099); mattes use version folders then. OpenEXR's Python API groups R,G,B(,A) into one 'RGB'/'RGBA' channel (exr.read_channels splits).
- Windows' clock advances only every ~2 ms (200,000 utcnow() calls -> 194 distinct values): never build unique names from a timestamp alone (T-104 backup collision). Acceptance run: `.venv\Scripts\python.exe -I tools/acceptance/run_acceptance.py` (~20 min; reports in docs/acceptance/).
- Installer tests must use temporary `--base` / `--home`; to start Nuke against a test home, redirect only `HOME` (changing `USERPROFILE` makes Nuke NC exit with code 100). Build: `tools/installer/build_exe.py` (PyInstaller is in .venv). (T-103)
- Models resolve through `st_roto_ai.registry.find_model` (user `ST_ROTO_MODELS_USER` > studio `ST_ROTO_MODELS_STUDIO` > plugin); load paths come from `st_roto_nuke.track.model_dir(name)`, never `models_root()` (T-101).
- Roto shape blending (T-098, measured): attributes `bm` (blend) / `inv` (invert); `getValue` returns 0 for ANY name (useless for discovery: use `attrs.k...Attribute`); Python attribute edits after a render need `curves.changed()`; the FIRST layer item is on top; blend 12 = minus (can go negative -> STROTO_clamp).
- ST_Roto nodes store knobChanged/onCreate callbacks (AI-off visibility): keep them wrapped in try/except and touch `nuke.thisNode()` only after filtering on `nuke.thisKnob()` (10-node budget). knobChanged does not fire in headless `-t`: tests call `apply_ai_visibility` directly.
- SA-V truth masks are SAM-assisted: they cannot judge edge precision beyond SAM (T-095); use exact-edge composites (`edge_study.py --composite`) or precise human truth.
- Tests that touch signing keys must set `ST_ROTO_KEY_DIR` to a temp folder (never the owner's real `%USERPROFILE%\.st_roto\keys`); `USERNAME` sets the project author in `session.project` (T-094).
- Measured Track GPU memory peaks (RTX 5060 8 GB, 720p): tiny 3,730 MiB, large 6,793 MiB, independent of the object count; Windows shows no per-process GPU memory (nvidia-smi N/A) - measure the total-used increase. Fault injection for OOM: `runtime.set_cuda_memory_limit(200)` after releasing cached sessions (T-092).
- Nuke NC refuses to render anything wider/taller than 1920x1080 (`The bounding box exceeds the maximum resolution allowed in Non-commercial mode (1920 x 1080)`), even 2048x1080 or 1080x1920; ST-ROTO renders AI frames through a temporary Reformat then (T-089).
- Missing Read frames make `nuke.execute` raise `Read error: No such file or directory`; proxy mode makes any Write without a proxy file name fail ('You must specify a proxy file name'); a frame of another size renders at its own size (no error). `st_roto_nuke.pixels` handles all three (T-086).
- Nuke reports Read paths as `d:/…/name_%04d.ext` (lowercase drive, %04d) even if set as `D:/…/name_####.ext`: compare paths case-insensitively and accept both frame spellings.
- This Bash tool collapses `\` to `\` even inside quoted heredocs: put Python edit scripts in files with the Write tool (`tools/dev/replace_functions.py` replaces whole functions, CRLF-safe).
- Nuke NC CatFileCreator writes `.catnc` (not `.cat`); create via `nuke.execute(node, nuke.FrameRanges([1]))`. TorchScript must come from torch 2.7.x (`.tools/torch27-venv`), Nuke's libtorch.
- Nuke's standalone `python.exe` cannot load the CUDA DLLs: ONNX Runtime silently falls back to CPU (measured). For GPU runs of tools use `Nuke17.1.exe --nc -t tool.py`.
- SA-V calibration: one click is ambiguous for object parts - use `calibrate_review.py --prompt box`; frames are 6-fps samples, so shot-frame gaps divide by 4.
- SA-V (D-031): links come only after the owner submits Meta's form (first/last name, email, affiliation, country, intended use = a licence signature in their name; Claude must not submit it or bypass it) and expire; `tools/benchmark/fetch_sav_subset.py --links <file>` streams just the subset into `data/benchmarks/sa-v` (git-ignored).
