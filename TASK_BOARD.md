# Task Board

Updated 2026-11-16 (second session).

## Done

| ID | Task | Evidence |
|---|---|---|
| T-072 | Learned matting ViTMatte-S (D-032): optional download with licence check, ONNX export exact vs PyTorch, registry-verified, node 'edges' choice with caveat; vs guided filter: hair 0.69 vs 0.95, shape-off 0.23 vs 0.89, motion blur 0.68 vs 0.52 (SAD) | `research/probes/2026-11-16_matting/RESULTS_vitmatte.md` |
| T-078 | Temporal-consistency review rule: shape area jumping > 35 % against both nearest present frames → CHECK (uncalibrated threshold). Synthetic reverse: newly flags frame 23 (confident, true IoU 0.42) and 24 (CPU truth IoU 0.986: possibly a false alarm; GPU run untested); good forward track: no new flags | `src/st_roto/quality.py` `area_jumps`, `tests/unit/test_quality.py` |
| T-076 | Per-point feather (schema v7 `key_feather`): imported from / synced to Roto (undoable, AI refused, locks respected, kept by delete/undo snapshots), RotoPaint copy pixel-identical, JSON, sync conflict key | `tests/unit/test_point_feather.py`, `tests/nuke` `test_point_feather_roundtrip` |
| T-068a | Calibration tooling + provisional run on synthetic data: current thresholds catch 6/7 bad frames with 14 flags; predicted IoU uninformative (corr 0.015); a confidently wrong frame needs a temporal rule. Defaults kept | `research/probes/2026-11-16_calibration/RESULTS.md` |
| T-020 | Collaboration architecture (Proposed) + working replication prototype: op ids + origin site (schema v6), file transport, per-(shape, frame) auto-merge, same-key edits kept as branch candidates (D-023), resolve with tombstones, idempotent, protection still applies | `docs/COLLABORATION_ARCHITECTURE.md`, `src/st_roto/sync.py`, `tests/unit/test_sync.py` |
| T-035 | Implications of D-022..D-025 for the design (one protocol / two transports, branches per key, leases + presence, roles + revocation) | `docs/COLLABORATION_ARCHITECTURE.md` §2 |
| T-036 | Benchmark datasets and licences: SA-V CC BY 4.0 (only permissive real-video GT found, masks only); MOSE NC; DAVIS data terms not stated; no permissive video-matting GT. Recommendation for D-020 approval | `docs/RESEARCH_2026-11-16_BENCHMARK_DATASETS.md` |
| T-034 | Competitor survey: Foundry SmartRoto (Jul 2026, spline AI, US$499 add-on), Nuke 17 CopyCat/BigCat, Silhouette 2026, Mocha Pro 2026.5, Roto Brush, Magic Mask, OpenMatte | `docs/RESEARCH_2026-11-16_COMPETITORS.md` |
| T-033 | Nuke API audit (measured in NC): no viewer pick events in Python (NDK only), XY/BBox handles + PyCustom_Knob work, Deep nodes and stereo views available | `research/probes/2026-11-16_api_audit/RESULTS.md` |
| T-032 | Python/Qt/compiler/CUDA per Nuke line 13 to 17.1 (3.7/PySide2 5.12 … 3.11/PySide6 6.5; VS2017/2019/2022; CUDA 10.1 → 12.8) | `COMPATIBILITY_MATRIX.md` |
| T-030b/T-031b | Licence texts (PyTorch, DirectML, OpenVINO, CUDA EULA key clauses); weights terms (Cutie, SEA-RAFT, RTMPose, Grounding DINO conflict resolved: not production); categories: no permissive hair/motion-blur models, VOID (video inpainting) to verify | `docs/RESEARCH_2026-11-16_LICENCES_AND_CATEGORIES.md` |
| T-011a | Route A proven in NC: TorchScript (torch 2.7.1) → CatFileCreator → `.catnc` → Inference; CPU bit-identical to PyTorch, GPU 1.2e-7; 720p 0.017 s/frame GPU. Per-frame stateless: fits matting/refinement, not SAM video tracking | `research/probes/2026-11-16_route_a/RESULTS.md` |
| T-046 | Pixel path researched and measured: Nuke Python has no buffer API (only per-pixel sample: 141 s/frame at 720p); current float TIFF is exact and fastest exact (0.022 s 720p, 0.041 s 1080p); kept (D-030); true in-memory needs the NDK (T-011b) | `research/probes/2026-11-16_pixels/RESULTS.md` |
| T-012 | One requirement ID per master-prompt bullet: 740 items generated verbatim with their lead-in and group row (`tools/docs/split_requirements.py`); 16 group rows updated with this session's evidence | `docs/REQUIREMENTS_DETAILED.md`, `REQUIREMENTS_REGISTER.md` |
| T-073 | Shape feather (schema v5: feather x/y/falloff) synced both ways with Roto (undoable), in JSON, and approximated in EXR mattes (50 % contour within 1 px, area 0.2 %, measured); 'Copy shapes to RotoPaint' (render identical to Roto) | `research/probes/2026-11-16_feather/RESULTS.md` |
| T-075 | Packages carry the Nuke script; menu 'ST-ROTO > Unpack project package...' with plate relink dialog; source fingerprints (schema v4: SHA-256 of the shot's first/last frame) accept moved footage, refuse different footage; relink is undoable (`update_shot`); NC scripts are encrypted, so relinking happens in the opened script (sidecar) | `src/st_roto_nuke/packages.py`, `tests/nuke` `test_package_script_relink` |
| T-048 | Resumable tracking: checkpoints every 10 frames and on Cancel (incremental, atomic meta), 'Resume track' continues with identical results (CPU proof incl. simulated crash); +1.2 % time, ~2.4 MB per object-frame while interrupted | `research/probes/2026-11-16_resume/RESULTS.md` |
| T-049 | Split objects: extra pieces become part shapes (centroid-matched, collapsed zero-area keys where absent, explicit `part_of`), adaptive point counts ('points' = auto, 0.3 px mean fit), Re-track carries parts, rename carries parts. Synthetic split frame IoU ~0.6 → 0.985-0.992; 48-frame mean 0.985 → 0.993 | `src/st_roto/pieces.py`, `research/probes/2026-11-16_pieces/` |
| T-038 | Nuke 17.1v3 bundles libtorch 2.7.1 (CUDA 12.8, cuDNN 9.7.1, sm_120, MSVC 2022) | `research/probes/2026-11-16_nuke_libtorch/RESULTS.md` |
| T-045 | Configurable AI input colour: built-in transforms derived from primaries + Bradford (Rec.709, ACEScg, ACES2065-1, Rec.2020, P3-D65, display-encoded), OCIO transforms; node 'AI input colour' (auto follows the script: Nuke default or OCIO working space). Built-ins = OCIO ACES config within 2e-5; ACES mode tracking IoU 0.994-0.995 | `src/st_roto/colour.py`, `tests/unit/test_colour.py`, `tests/nuke` |
| T-056 | Model registry: export manifests (`models/manifests/<name>.exports.json`, SHA-256 of every loaded file, source revision); every session/constant load verified (licence in production set, owner approval, pinned revision, size + SHA-256); verified stamps per (path,size,mtime); dev escape hatch `ST_ROTO_MODEL_VERIFY=0` | `src/st_roto_ai/registry.py`, `tests/unit/test_registry.py` |
| T-057 | CI on Node-24 actions (checkout v7, setup-python v7) | `.github/workflows/ci.yml` |
| T-074 | Nuke's own Roto motion blur exposed on ST_Roto (mode, samples, shutter, offset: linked knobs); 60 px/frame shape renders a ~50 px trail along the motion only | `tests/nuke` `test_motion_blur_links` |
| T-071 | Persistence: verified rotating backups of the OPEN project (SQLite online backup), auto-backup thread (only after changes, final on exit), session marker detects crashed / concurrent sessions, integrity check + restore newest valid backup (damaged file kept), portable zip packages (checksums, zip-slip refusal, source relink, optional plates). Unit 75, Nuke 11/11 | `src/st_roto/persistence.py`, `tests/unit/test_persistence.py` |
| T-069/T-070 | Matte pass + EXR export: 'Render mattes (EXR)' writes one EXR per frame (`<object>.A` layers + combined `A`), hard or soft edges; ST-ROTO JSON (round trip) and SVG export, JSON import. Nuke reads the layers exactly (0.0 diff); hard matte vs Roto render IoU 0.998; export → delete → import restores the shape (1.5e-5 px). Unit 68, Nuke 10/10 | `docs/RESEARCH_2026-11-16_INTERCHANGE.md`, `tests/nuke/` |
| T-067 | Several objects per tracking pass: `Sam2MultiVideo` (encoder once per frame, per-object state as upstream), `track_objects`/`retrack_objects`, per-object prompts, Track skips already-tracked objects, Re-track all, one undo step per pass. Identical to single-object runs (CPU tests; 0.0 px on GPU); 1.36x (tiny) / 1.56x (large) faster for 2 objects. Reverse-pass point-order seam bug fixed. Unit 61, Nuke 8/8, GUI passes | `research/probes/2026-11-16_multi_object/RESULTS.md` |
| T-065 | Bounded tracker state: SpillDict (24 frames in RAM, rest on disk), bit-identical results | `src/st_roto_ai/spill.py`, `tests/unit/test_spill.py` |
| T-031c | Matting licence research: no permissive model with clean training data; model-free soft edges measured (SAD 0.59x of hard shape) | `docs/RESEARCH_2026-11-16_MATTING.md`, `research/probes/2026-11-16_matting/` |
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
| T-068 | Calibrate review thresholds on REAL footage: tool ready (`tools/benchmark/calibrate_review.py --dir`); needs owner approval of a dataset licence (D-020, recommendation SA-V subset). Also evaluate a temporal-consistency rule (confidently wrong split frame found) | owner approval of a dataset licence (D-020 / OQ-23) |
| T-077 | Silhouette / Mocha direct shape formats — need those applications (or published specs) to validate; both already export Nuke Roto, which ST-ROTO ingests | Silhouette / Mocha applications or published specs to validate against |
| T-011b | In-process inference prototypes, routes B and D (NDK C++) | D-019: Build Tools only with a plug-in-capable licence (D-009/D-011) |

## Ready (desk research, can proceed now)

| ID | Task |
|---|---|
