# Development Log

## 2026-11-15 — Phase 1, research half

**Objective.** Begin Phase 1 (Discovery and Audit) from the master prompt.

**Work completed.**
- Read the master prompt in full.
- Web research on Nuke edition restrictions, Nuke 17 platform facts, in-process inference options, and licences of 10 candidate models.
- Connected `D:\ST-ROTO` (owner granted access) and listed it: empty.
- Wrote the first issues of the registers listed below.

**Files created.** `README.md`, `REQUIREMENTS_REGISTER.md`, `OPEN_QUESTIONS.md`, `DECISION_REGISTER.md`, `RISK_REGISTER.md`, `COMPATIBILITY_MATRIX.md`, `MODEL_REGISTER.md`, `LICENCE_REGISTER.md`, `TASK_BOARD.md`, `DEVELOPMENT_LOG.md`, `docs/PHASE1_DISCOVERY_REPORT.md`, `docs/MASTER_PROMPT.md` (verbatim copy).

**Tests executed.** None. No code exists.

**Actual test results.** None.

**Problems discovered.**
- Nuke Non-commercial and Indie cannot load NDK plug-ins and cap Python at 10 nodes (R-01 to R-03).
- No commercially licensed video matting model or point tracker found yet (R-07, R-08).
- This session has no terminal on the development machine (R-18).

**Requirements satisfied.** None of the product requirements. Process requirements REQ-002, 003, 006, 007 are in operation.

**Requirements outstanding.** All product requirements.

**Architectural decisions.** None.

**Next actions.** Owner to answer OQ-01. Desk tasks T-012 and T-030 to T-036 can proceed. Machine audit T-010 must be run locally.

**Not done that Phase 1 requires.** Machine audit; GitHub inspection; full API audit; competitor research; most model categories; architecture proposal.

## 2026-11-15 — Phase 1, folder and machine audit (local Claude Code session)

**Objective.** Audit the complete folder, then master prompt section 31 steps 1-2 (T-010).

**Work completed.** Read all 13 existing files; confirmed `docs/MASTER_PROMPT.md` has all 32 sections. Inspected Git, toolchain, hardware and the Nuke install. Ran two headless probes inside Nuke 17.1v3 Non-commercial.

**Files created.** `docs/MACHINE_AUDIT_2026-11-15.md`; `research/probes/2026-11-15_machine_audit/` (2 probe scripts, logs, 1 test EXR).

**Files modified.** `README.md`, `TASK_BOARD.md`, `RISK_REGISTER.md`, `COMPATIBILITY_MATRIX.md`, `OPEN_QUESTIONS.md`, `DECISION_REGISTER.md`, `REQUIREMENTS_REGISTER.md`, `docs/PHASE1_DISCOVERY_REPORT.md`, this log.

**Tests executed and actual results.**
- Probe 1: edition flags (`nc=True`); 10-node cap reproduced. Its node-creation and Roto results are invalid because the probe itself exhausted the cap.
- Probe 2 (4 nodes): native Roto shape created via `nuke.rotopaint`: pass. Inference node + Foundry FnHumanMattingSmall on a 1K checkerboard written to EXR: pass, 4.56 s first frame. GPU use not demonstrated.

**Problems discovered.** No VS 2022 / CMake / CUDA toolkit (R-20). Python ABI mismatch 3.12 vs 3.11 (R-21). GPU use by Inference unproven (R-22). Not a Git repository; `gh` not installed.

**Requirements satisfied.** No product requirements.

**Architectural decisions.** None. D-006 recorded (owner).

**Next actions.** Owner: OQ-01 (licence), OQ-14 (C++ toolchain), OQ-15 (local Git). Ready without approval: T-011a, T-011c, T-037, T-038; desk tasks T-012, T-030 to T-036.

## 2026-11-15 — Environment, GPU and ONNX Runtime probes; licence and model research

**Objective.** Owner-requested: (1) project Python 3.11 environment; (2) prove whether the Inference node uses the GPU; (3) test ONNX Runtime inside Nuke next to Nuke's CUDA; (4) read licence texts and research missing model categories.

**Work completed.**
- Python 3.11.18 + venv inside `D:\ST-ROTO` (uv install/cache redirected to `.tools/`; a uv shim written to `C:\Users\<user>\.local\bin` was removed).
- Synthetic ONNX test model (random weights; nothing downloaded).
- Headless Nuke probes, 5 runs (`research/probes/2026-11-15_gpu_ort/`).
- Licence texts and model-category research (`docs/RESEARCH_2026-11-15_LICENCES_AND_MODELS.md`).

**Tests executed and actual results.**
- Inference node, 1080p, FnHumanMattingSmall: CPU 2.741 s/frame without `--gpu`; GPU 0.25–0.30 s/frame with `--gpu` (100 % util, about 1.8 GB VRAM).
- onnxruntime-gpu 1.32.0 in Nuke: CUDA EP failed (`cublasLt64_13.dll` missing), silent CPU fallback.
- onnxruntime-gpu 1.26.0 in Nuke: CUDA EP active; 0.195–0.219 s/run against 2.63–2.73 s on CPU; max |CUDA−CPU| 3.2e-5; used Nuke's own CUDA 12 / cuDNN 9 DLLs; coexisted with the Inference node in both orders.
- First probe run of the Inference test failed due to my script errors (Noise has no `format` knob; knob read-only). Both were fixed and re-run.

**Problems discovered.** Foundry EULA 2.1(g)(e) may prohibit developing ST-ROTO on Non-commercial (R-23). ORT must be pinned per Nuke CUDA major (R-24). ViTMatte training-data risk (R-25). No permissive general video matting or video inpainting model yet.

**Requirements advanced (not satisfied).** REQ-032 (in-process inference): routes A and C demonstrated feasible on this machine. REQ-050: model register second issue.

**Architectural decisions.** None.

**Next actions.** Owner: OQ-01 now includes the EULA question; approve SAM 2.1 tiny download for T-041. Ready: T-040, T-030b, T-031b.

## 2026-11-15 — Owner decisions recorded

Owner answered all open questions (D-009 to D-025). Key effects: development stays on Non-commercial (D-009/D-010, EULA risk accepted); C++/Deep remain mandatory but deferred (D-011); single-node core (D-012); Apache-2.0 (D-013); Nuke 13+ mandatory (D-017); model downloads approved (D-015); collaboration decisions made (D-022 to D-025). New open items: OQ-11, OQ-16, OQ-17.

## 2026-11-15 — Public repository

GitHub CLI 2.104.0 installed via winget (D-014); owner signed in as suryateja963. Public repository https://github.com/suryateja963/ST-ROTO created; initial commit 2a0adea pushed to `main`. Commits use the GitHub no-reply address (D-008). Personal-data check on staged files: clean.

## 2026-11-15 — SAM 2.1 tiny + large in Nuke (first real milestone)

**Objective.** Owner request: start with SAM 2.1 tiny, and run SAM 2.1 large in parallel.

**Work completed.** Installed CPU PyTorch 2.15, torchvision, transformers 5.23 and OpenCV in the project venv. Downloaded both models (pinned revisions; checksums in `models/manifests/`). Exported each to encoder/decoder ONNX with automatic verification. Ran both inside Nuke 17.1 NC on CUDA via ONNX Runtime 1.26.0, converted the mask to a native Roto shape and rendered it back.

**Tests executed and actual results.** See `research/probes/2026-11-15_sam2/RESULTS.md`. ONNX vs PyTorch mask IoU 1.0 (both). In Nuke: encoder 65 ms / 317 ms, click 6.7 ms, peak GPU 2.5 / 5.6 GB, rendered Roto vs SAM mask IoU 0.996 / 0.996, centroid offset < 0.07 px.

**Problems hit and fixed.** torchvision missing (installed); pip OpenCV has no OpenEXR (switched to float TIFF); Roto default format 2048×1556 refused by NC (set HD); the hardware logger had a column-merging bug (fixed and restarted; old file kept as `_buggy-columns`).

**Problems discovered.** NC 1920×1080 render cap (R-28); large-model GPU headroom (R-29); two unexplained power-offs earlier today (R-31).

**Requirements advanced (not satisfied).** REQ-032 in-process inference: demonstrated with a real model. REQ-041 native Roto export: polygon shape demonstrated. REQ-060 click selection: demonstrated headless, no UI yet.

**Next actions.** T-043 Bézier fitting, T-044 video propagation export, T-045 colour transform, T-047 architecture proposal.

## 2026-11-15 — Bézier shapes (T-043)

**Work.** `prototypes/geometry/bezier_fit.py` (Schneider fitting + corner detection) with 6 unit tests. Probes measured how Nuke stores Roto tangents.

**Results.** Tests: 6/6 passing after fixing an undefined-variable bug and recalibrating the corner threshold from 60° to 45° (measured attenuation). Nuke: `leftTangent` points to the previous point, and **Nuke tangent = 2 × Bézier handle offset** (circle IoU 0.9993). SAM mask → 20-point Bézier Roto shape rendered by Nuke: IoU 0.9957 vs mask, centroid offset 0.05 px. The 61-point polygon scored 0.9961.

**Problems.** First Nuke render was wrong (IoU 0.971) because of the undocumented 2× tangent scale. Found with a circle experiment and confirmed not to be a keying artefact.

**Next.** T-044 temporal propagation.

## 2026-11-15 — Temporal propagation (T-044)

**Work.** Synthetic 48-frame test shot with exact ground truth. PyTorch reference (transformers Sam2VideoModel). Exported 5 ONNX graphs (vencoder, memattn with dynamic memory/pointer counts, two decoders, memenc) plus constants. Ported the memory bookkeeping to numpy (`prototypes/tracking/sam2_video_onnx.py`), including bf16 rounding of stored memories. Fixed-count Bézier fitting with frame-to-frame correspondence (7/7 geometry tests). Ran everything inside Nuke 17.1 NC on CUDA and wrote one animated Roto shape.

**Results.** See `research/probes/2026-11-15_video/RESULTS.md`. Port vs PyTorch: per-frame IoU min 0.99997. In Nuke: tiny ≈ 0.24 s/frame, IoU vs GT 0.995 (min 0.986); large 0.45 s/frame, 0.987 (min 0.573 on frame 23, same in PyTorch), peak GPU 7.8 GB. Animated shape vs mask: 0.983 mean (tiny), 0.558 on the split-object frame.

**Problems found and fixed.** Propagation needs an explicit call on the clicked frame; fixed-count tangents were too noisy (±2 → ±6 points, measured); animated keys were silently lost after `Shape.append` (R-33, fixed by keying before append).

**Next.** T-047 architecture proposal.

**Correction (same day).** Commit f3257b8 accidentally included `models/onnx/<model>/video/constants.npz` and `config.json` (~70 KB each of parameters extracted from SAM 2.1 weights), against D-008. The weights are Apache-2.0, so redistribution is permitted, but they were not committed with the licence notice. Removed from the tree in the next commit and `models/onnx/` is now git-ignored. The files remain in the history of f3257b8; removing them from history would need a force-push (owner decision).

## 2026-11-15 — Architecture proposal (T-047)

`ARCHITECTURE.md` and ADR-0001..0010 (`docs/adr/`, generated by `tools/docs/write_adrs.py`). All **Proposed**; nothing approved. Grounded in today's measurements; assumptions flagged (GUI threading R-37, group-node cap counting, Nuke 13 runtime R-36). Owner questions OQ-18..OQ-21 raised.

## 2026-11-15 — GUI threading (T-051, R-37)

Owner approved the architecture (D-026..D-028). Interactive-GUI probe: SAM 2.1 tiny encoder ×40 on a worker thread with CUDA, while the GUI's 16 ms timer averaged 16.0 ms (max 17.7 ms, no gaps > 100 ms). Same work on the main thread gave 60 ms gaps. Main-thread marshalling created a Roto shape; cancellation took 39 ms. ADR-0009 confirmed for Nuke 17.1.

## 2026-11-15 — Phase 4 core v0 (T-052)

**Work.** First product code in `src/st_roto`: `model.py` (provenance, canonical coordinates, validation), `store.py` (per-project SQLite, WAL, foreign keys, versioned migrations, old-SQLite-safe SQL), `commands.py` (operation log with exact inverses, undo/redo, protection rules), `geometry.py` (promoted from the prototype). `pyproject.toml`, `requirements-dev.txt`, GitHub Actions CI (pytest on Windows/Linux × Python 3.9/3.11, Python 3.7 compatibility via vermin).

**Tests.** 22 unit tests passing locally (geometry 7, store/commands 14, layering 1). vermin: minimum required Python 3.7.

**Requirements.** REQ-042 implemented in the core; REQ-160 partly. "Implemented (core)" means unit-tested outside Nuke, not yet tested inside Nuke (§22 status scale).

**Process note.** A register-update script matched `| REQ-160 |` inside the REQ-070 row and aborted halfway; commit 922b956 carried the task-board and REQ-042 changes without this log entry or the REQ-160 update. Fixed in the next commit (line-anchored matching).

## 2026-11-15 — Nuke adapter v0 and sub-pixel contours (T-053)

**Work.** `src/st_roto_nuke/convention.py` (y flip, 2× tangents, inverse for import) and `roto_export.py` (keyed points built before `append`). Core geometry gained `trace_contours` (marching squares, sub-pixel, holes, border-safe) and exact pixel-centre rasterisers. Headless Nuke integration test `tests/nuke/run_nuke_tests.py`.

**Results.** Unit tests 31/31 passing. The first Nuke test run FAILED (IoU 0.9926, and negative-frame renders "missing"). Investigation: Nuke names negative frames `name.-002.tif`, and the test's reference rasteriser (cv2.fillPoly) paints outline pixels, making shapes ~0.5 px fat. A real bias was found too: shapes fitted to cv2 contours are ~0.5 px too small (R-38). After the fixes: render vs exact spline 0.9980–0.9984, vs analytic ellipse 0.9968–0.9978 on frames −2..5; test passes. The 0.998 threshold has little margin.

**CI.** First GitHub Actions runs green (Windows/Linux × Python 3.9/3.11, Python 3.7 compatibility). Node 20 deprecation warning on actions to address.

## 2026-11-15 — AI layer v0 (T-054) and real Python 3.7 CI

**Work.** `src/st_roto_ai/runtime.py` reports requested vs actually-loaded device (silent CPU fallback becomes visible). `src/st_roto_ai/sam2.py`: SAM 2.1 image and video adapters promoted from the prototypes. A fidelity slip (an improvised pointer-loop stop condition) was caught in review before testing and reverted to upstream behaviour; tracker frames are now documented as 0-based sequence positions. `st_roto.geometry.mask_to_points` (logits → sub-pixel contour → stored-key points). Layering test extended to the AI layer.

**Tests.** 34 unit tests passing locally, including SAM image click → shape (IoU > 0.995 vs mask) and the video tracker vs the PyTorch reference (first 6 frames, IoU > 0.995). AI tests skip in CI (no weights in the repository). CI: vermin check replaced by running the whole suite on Python 3.7 (it gave non-deterministic results locally); all CI jobs green, including Python 3.7.

## 2026-11-15 — First product-code vertical slice in Nuke (T-055)

**Work.** `st_roto.jobs` (cancellable background jobs), `st_roto_nuke.colour` (explicit v0 model-input transform, recorded in provenance), `st_roto_nuke.pixels` (main-thread frame render to numpy), `st_roto_nuke.track` (click → SAM 2.1 video → fixed-count sub-pixel Bézier keys; AI writes go through the command bus as actor "ai"), `st_roto_nuke.node` (ST_Roto group: Input → Roto → Output + disabled pixel Write; Track/Cancel/status). `tools/run_nuke_tests.py` runs each Nuke test in its own process (10-node budget is per session). GUI test `tests/nuke/gui_track_slice.py`.

**Tests.** Unit 38/38. Headless Nuke 2/2: ST_Roto slice stores 48 AI keys, rendered output vs ground truth mean IoU 0.985 (0.994 excluding the split-object frame 23; the prototype animated shape was 0.983). GUI: first run FAILED silently (no result after 10 min). Diagnosis: exceptions in main-thread callbacks are swallowed; after adding error capture, the cause was the 10-node budget (Roto lookup returned None). Fixed by caching node references and raising a clear NodeBudgetError. GUI test now passes: 48 frames in 22 s, shape with 48 keys; UI mean gap 19 ms but max stall 1.56 s (R-40).

## 2026-11-16 — GUI stalls and GPU memory (T-058)

**Method.** Instrumented GUI probe: 16 ms UI timer plus timestamps of every adapter call; stalls attributed to overlapping calls; GPU memory from the hardware logger and direct sampling.

**Findings.** (1) Stalls coincide only with ORT session creation on the worker thread (GIL held, 0.9–1.3 s). Fix: process-wide session cache; later Track presses create sessions in ~2 ms. (2) While verifying, a third Track press in the same session took 35.9 s instead of ~15 s: ORT's CUDA pool grew to 7.8 of 8.15 GB and the encoder slowed ~5×. Two option sets were tried and rejected (both made every run fail after 17 frames, one with a 470 MB allocation failure). Kept: ORT defaults plus arena shrinkage after each memory-attention run: three runs 22.5 / 16.3 / 16.4 s, memory 3.3–6.4 GB (sampled peak 7.65 GB), tracking step +35% slower.

**Tests.** Unit 38/38, headless Nuke 2/2, GUI slice passes (21.2 s; first-press stall 1.6 s remains, T-061).

## 2026-11-16 — Load model action (T-061) and fp16 memory attention (T-062)

**T-061.** "Load model" button on ST_Roto (`on_load_model`, `st_roto_ai.sam2.preload_video`): sessions created synchronously with a status message (≈2.9 s, once). GUI probe, 2 trials of Load + 2 Track runs each: zero UI stalls > 100 ms, mean timer gap 16.0–16.2 ms.

**T-062.** fp16 conversion of memory attention. First two attempts would not load in ORT (stale value_info; model's own fp32 casts); both fixed in `tools/models/convert_fp16.py`. A partially-fp32 variant was measured and rejected (slower, slightly less accurate). fp16 result, verified on raw logits: tiny 7 sign flips in 48×256×256 low-res pixels, large 0; peak GPU tiny 5.06 → 3.92 GB, large 7.77 → 7.00 GB; step 148 → 96 ms (tiny), 192 → 98 ms (large). Made the runtime default (D-029). New regression test (3 runs in one session) passes: 10.5 / 8.3 / 8.3 s, peak 3.9 GB. Unit 38/38, Nuke 3/3.

## 2026-11-16 — Prompts, preview, object panel, safe Roto sync (T-059)

**Decision on "viewer click".** Non-commercial cannot load C++ viewer overlays and Nuke has no supported Python mapping from viewer clicks to image coordinates; hooking the viewer's Qt widget would be fragile. Used Nuke's native XY knob handle (draggable in the viewer) plus Include/Exclude buttons. A true click-in-viewer tool is noted for the C++ path (commercial editions).

**Work.** `st_roto.prompts`, `st_roto.views`, schema v2 (`host_exports`: exact keys last written into each host shape), `st_roto_nuke.roto_export.sync_shot` (writes/updates/removes only shapes whose Roto copy is unchanged since ST-ROTO wrote it; otherwise reports a conflict), `st_roto_nuke.session` (one store + bus per project for the Nuke session → persistent undo), ST_Roto node rewritten (prompts, Preview, Track via session + sync), `st_roto_nuke.panel.ObjectPanel`, `nuke_plugin/` (init/menu), `docs/USER_GUIDE_v0.md`.

**Tests.** Unit 41/41 (incl. v1→v2 migration). Nuke 4/4. New test: include+exclude prompts → preview → track → second track → delete/undo (unedited shape removed and restored) → simulated artist edit in Roto + delete → shape kept, conflict reported, edit intact. GUI: Track 48 frames in 19.4 s, panel lists 1 object, lock → locked, undo → unlocked.

**Plugin smoke test (same day).** `tests/nuke/gui_plugin_smoke.py` with NUKE_PATH set for that one Nuke process only (user environment untouched): ST-ROTO menu entry present, Objects panel registered, menu command creates an ST_Roto node with the expected 'set a project file' status, panel widget constructs. Passes.

## 2026-11-16 — Artist edits captured into the project (T-063) and rename (T-064)

**Work.** `batch` command (several ops = one atomic, undoable step). `roto_export.import_edits`: changed/added/removed keys of ST-ROTO shapes edited in the Roto node become artist ops (edited AI keys → artist_modified_ai); untagged hand-drawn shapes become artist_created objects and are re-created with their tag; point-count changes, locked content and deleted objects are reported, not imported. `resync` now imports then syncs; Track imports pending edits before applying AI results; node button "Save Roto edits to project". Panel rename also renames the object's shapes (one batch).

**Tests.** Unit 42/42 (batch atomicity and single-step undo). Nuke 5/5: new `test_import_artist_edits` (edit frame 3 + delete frame 5 → imported, origins correct; undo → project and Roto shape reverted; hand-drawn shape → artist_created + tagged; removing a point → reported, kept). GUI: rename → Roto shape relabelled `hero_st…`. A type bug (Roto layers would have been treated as shapes) was caught in review before testing.

## 2026-11-16 — Corrections, reverse tracking, Re-track (T-060)

**Work.** `st_roto_ai.resize` (numpy port of PyTorch's antialiased bilinear weights; exact vs torch). Mask prompts: `maskptr.onnx` + numpy for the rest of upstream `_use_mask_as_output` (the AA op cannot be exported at opset 17); `Sam2Video.add_mask`, `track(reverse=True)`, any number of conditioning frames; pruning of tracked-frame memory removed (it would change results; RAM risk R-42). Preprocessing switched to the torch-equivalent AA resize. `st_roto_nuke.track.retrack_object/apply_retrack` and the ST_Roto "Re-track object" button.

**Validation.** PyTorch reference scenarios (correction: click f0 + mask f24; reverse: click f47). Correction: ONNX vs PyTorch min 0.993, mean 0.998. Reverse: PyTorch itself loses the object on 5 occluded frames; ONNX loses one more (f16). Root-caused with an exact-pixel CPU run (port matches PyTorch on all frames; f16 object score 0.025 at threshold) → preprocessing sensitivity, not a port bug; fp32 gives the same → D-029 unaffected. Own metric bug (empty-vs-empty IoU = 0) found and fixed.

**Tests.** Unit 47/47 (incl. resize vs torch). Nuke 6/6: new `test_retrack_with_corrections` — one hand-drawn shape on frame 6 → all 12 frames, AI IoU vs GT 0.994–0.996; corrected frame kept exactly. GUI test passes (21.0 s).

## 2026-11-16 — Confidence and review flags (T-066)

**Work.** Schema v3 `key_reports` (per-frame object score and predicted IoU of the latest AI run, also for frames where the AI found no object); `set_report` op (undoable, included in subtree/shape snapshots); `st_roto.quality.review_frames` (heuristic rules: |score| < 1.0, object lost between visible frames, predicted IoU < 0.7 on keyed frames); `views.review_for_object`; tracker returns predicted IoU; Track and Re-track write keys + reports in ONE undoable batch (Track was previously one undo step per key); node status "REVIEW frames …"; panel "review" column with per-frame reasons as tooltip.

**Tests.** Unit 49/49 (rules, undo/subtree of reports, genuine v1→v3 migration — my old migration test had to be fixed because it faked a v1 file incompletely). Nuke 7/7: new `test_review_flags_reverse` — hand-drawn last frame, reverse re-track across the occluder: flagged exactly 15–22 (lost 16–20, 22; uncertain 15, 21 at ~0.35–0.38); confident frames score ~1.2–10. GUI passes.

**Follow-up (same day): flag severity.** The GUI forward track flagged frames 25-30 although their masks were accurate (IoU 0.993-0.996 vs GT): after the occlusion the object score fell to 0.15-0.94 (a real near-miss; the reverse run lost the object in the same region). Predicted IoU correlated only 0.50 with real IoU on this shot. Flags now have two levels: LOST (object missing between visible frames: fix) and CHECK (uncertain / low predicted quality: glance). Reverse: 'REVIEW lost 16-20, 22; check 15, 21'; forward: 'REVIEW check 25-30'. Unit 49/49, reverse Nuke test and GUI pass. Evidence: research/probes/2026-11-16_corrections/forward_reports.json.
