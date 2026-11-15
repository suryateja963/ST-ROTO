# Task Board

Updated 2026-11-15.

## Done

| ID | Task | Evidence |
|---|---|---|
| T-001 | Connect and inspect `D:\ST-ROTO` | Folder was empty; no Git repository |
| T-002 | Research Nuke edition restrictions | `docs/PHASE1_DISCOVERY_REPORT.md` §2 |
| T-003 | First licence check of 10 candidate models | `MODEL_REGISTER.md` |
| T-004 | Requirements register, first issue | `REQUIREMENTS_REGISTER.md` |
| T-005 | Risk register, open questions, decision register, compatibility matrix, first issues | Root files |
| T-039 | Project Python 3.11 venv inside `D:\ST-ROTO` (uv, pinned) | `.venv`, `.tools/uv-python` (git-ignored); requirements files in `research/probes/2026-11-15_gpu_ort/` |
| T-037 | Inference node GPU use proven with `--gpu` | `research/probes/2026-11-15_gpu_ort/RESULTS.md` |
| T-011c | ONNX Runtime CUDA in-process in Nuke 17.1 NC, coexisting with libtorch; version pin found | same |
| T-030 | Licence texts: SAM License, S-Lab 1.0, ORT, BiRefNet, Foundry EULA key clauses (partial) | `docs/RESEARCH_2026-11-15_LICENCES_AND_MODELS.md` |
| T-031 | Missing model categories, first pass (partial) | `docs/RESEARCH_2026-11-15_LICENCES_AND_MODELS.md` |
| T-021 | Public GitHub repository created and pushed | https://github.com/suryateja963/ST-ROTO (commit 2a0adea) |
| T-066 | Confidence: schema v3 key_reports (object score, predicted IoU) written in the same undoable batch as AI keys; review flags in status + panel; Track is now one undo step. Unit 49, Nuke 7/7, GUI passes | `src/st_roto/quality.py`, `tests/nuke/` |
| T-060 | Mask prompts (maskptr graph + exact numpy AA resize), reverse tracking, Re-track object with corrections both directions (artist keys kept); port exactness proven vs PyTorch incl. reverse; preprocessing now torch-equivalent AA | `research/probes/2026-11-16_corrections/RESULTS.md` |
| T-063 | Roto edits imported into the project (`import_edits`, `batch` command = one undo step); hand-drawn shapes become artist_created objects; topology changes reported; resync = import then sync. Unit 42, Nuke 5/5 | `src/st_roto_nuke/roto_export.py`, `tests/nuke/` |
| T-064 | Object rename renames its shapes (one undoable batch); Roto label follows (GUI test) | `src/st_roto_nuke/panel.py` |
| T-059 | Prompts (include/exclude via XY viewer handle), Preview, session project with persistent undo, schema v2 host-export records, safe Roto sync (artist-edited shapes never overwritten), object panel, `nuke_plugin/` + `docs/USER_GUIDE_v0.md`. Unit 41, Nuke 4/4, GUI with panel passes | `src/st_roto_nuke/`, `tests/nuke/` |
| T-061 | 'Load model' button: the one-time GIL pause (≈2.9 s) happens when the artist chooses; afterwards 2 Track runs with zero UI stalls (2 trials) | `research/probes/2026-11-16_gui_stalls/result_preload*.json` |
| T-062 | fp16 memory attention (tiny + large validated vs PyTorch), default per D-029; regression test of 3 runs in one session (10.5/8.3/8.3 s, peak 3.9 GB) | `research/probes/2026-11-16_fp16/RESULTS.md` |
| T-058 | GUI stalls diagnosed (GIL during ORT session creation) and fixed for repeat presses (session cache); GPU memory growth across runs found and fixed (arena shrinkage); 2 rejected option sets documented | `research/probes/2026-11-16_gui_stalls/RESULTS.md` |
| T-055 | Vertical slice in product code: ST_Roto node (Track/Cancel/status) → background SAM 2.1 tracking → project DB (AI provenance) → animated native Roto. Headless test: IoU vs GT 0.985 (0.994 excl. split frame); GUI test: 48 frames in 22 s, passes | `src/st_roto_nuke/node.py`, `tests/nuke/`, `tools/run_nuke_tests.py` |
| T-054 | AI layer v0: `st_roto_ai.runtime` (silent CPU-fallback detection), `st_roto_ai.sam2` (image + video adapters), `st_roto.geometry.mask_to_points`; AI tests pass locally (skip in CI: no weights); CI now runs the suite on real Python 3.7 | `src/st_roto_ai/`, `tests/unit/test_ai_sam2.py` |
| T-053 | Nuke adapter v0: `st_roto_nuke.convention` + `roto_export`; headless Nuke integration test passing (negative frames included); sub-pixel `trace_contours` + exact `rasterize_*` in core geometry; 31 unit tests | `src/st_roto_nuke/`, `tests/nuke/` |
| T-052 | Phase 4 core v0: `src/st_roto` (model, SQLite store with migrations, command bus with op log + undo/redo + REQ-042 protection, geometry); 22 unit tests; Python 3.7 compatibility check; CI workflow | `src/`, `tests/unit/`, `.github/workflows/ci.yml` |
| T-051 | GUI threading verified in interactive Nuke 17.1 (worker thread, marshalling, cancel) | `research/probes/2026-11-15_gui_threading/RESULTS.md` |
| T-047 | Architecture proposal: `ARCHITECTURE.md` + ADR-0001..0010 (all Proposed, awaiting owner) | `ARCHITECTURE.md`, `docs/adr/` |
| T-044 | SAM 2.1 video tracking: 5 ONNX graphs + numpy memory logic (IoU vs PyTorch ≥ 0.99997); in Nuke on CUDA ≈ 0.24 s/frame (tiny); animated 16-anchor native Roto shape | `research/probes/2026-11-15_video/RESULTS.md` |
| T-043 | Bézier fitting prototype (6 unit tests) + Nuke tangent semantics measured; SAM mask → 20-point Bézier Roto shape, IoU 0.9957 | `research/probes/2026-11-15_bezier/RESULTS.md` |
| T-041 | SAM 2.1 tiny + large: download (pinned, checksummed), ONNX export (exact vs PyTorch), CUDA in Nuke NC, mask → native Roto shape (IoU 0.996 vs mask) | `research/probes/2026-11-15_sam2/RESULTS.md` |
| T-040 | Nuke → numpy pixel transfer measured (HD: 0.09 s render + 0.02 s read via float TIFF) | `research/probes/2026-11-15_sam2/RESULTS.md` |
| T-042 | Hardware logger for crash diagnosis (`tools/monitoring/hw_logger.ps1`) | `logs/hardware/` (local, git-ignored) |
| T-010 | Machine audit: Python, compiler, CUDA, driver, Nuke build, Git; live headless probes in Nuke NC | `docs/MACHINE_AUDIT_2026-11-15.md`, `research/probes/2026-11-15_machine_audit/` |

## Blocked

| ID | Task | Blocked by |
|---|---|---|
| T-011b | In-process inference prototypes, routes B and D (NDK C++) | OQ-01; VS 2022 Build Tools + CMake not installed (OQ-14) |
| T-020 | Collaboration architecture | Unblocked by D-022..D-025 (OQ-16/17 minor) |

## Ready (desk research, can proceed now)

| ID | Task |
|---|---|
| T-068 | Calibrate review thresholds (OBJECT_SCORE_MARGIN, IOU_PRED_MIN) on real footage with ground truth (benchmark plan) |
| T-065 | Bounded / disk-backed tracker state for long shots (now ~2 MB RAM per tracked frame) — R-42 |
| T-067 | Several objects per ST_Roto node in one tracking pass (multi-object tracker) |
| T-056 | Model registry from `models/manifests` (licence, revision, checksum verification before load) |
| T-057 | Update GitHub Actions to Node-24-based action versions (deprecation warning) |
| T-045 | Documented, configurable model-input colour transform (replace hard-coded sRGB re-encode) |
| T-048 | Tracker: reverse propagation, multiple objects, corrections on tracked frames, resumable state |
| T-049 | Multi-shape objects (object split into several pieces) and adaptive anchor counts for animated shapes |
| T-046 | In-memory pixel path Nuke ↔ numpy (avoid disk round-trip) |
| T-012 | Split requirements register to one ID per bullet |
| T-030b | Remaining licence texts: Cutie weights, Adobe DIM dataset, SEA-RAFT/RTMPose weights, NVIDIA, PyTorch, DirectML, OpenVINO |
| T-031b | Remaining categories: hair-specific, motion-blur reconstruction, occlusion reasoning, permissive video matting/inpainting; resolve Grounding DINO conflict |
| T-032 | Tabulate Python, Qt, compiler and CUDA versions for Nuke 13 to 17.1 |
| T-033 | Audit Nuke Python and NDK APIs for viewer interaction, custom knobs, Deep, stereo |
| T-034 | Competitor survey (§21) |
| T-035 | Research implications of the five collaboration decisions |
| T-036 | Identify open benchmark datasets with ground-truth mattes and their licences |
| T-011a | Route A prototype: export a permissive model to TorchScript, convert to `.cat`, run in Inference node, measured |
| T-038 | Determine libtorch version bundled with Nuke 17.1v3 |
