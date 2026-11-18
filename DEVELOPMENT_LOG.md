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

## 2026-11-16 — Bounded tracker memory (T-065)

`st_roto_ai/spill.py` SpillDict: per-frame tracker state with at most N frames in RAM (default 24), least-recently-used frames written to disk and reloaded on demand, so results equal upstream's keep-everything behaviour. Test: tracker with a 2-frame RAM budget gives bit-identical masks to an unlimited one, with real disk reloads. Pipelines remove the temporary state when done. Unit 51/51, Nuke 7/7. R-42 mitigated (disk use ~2 MB per tracked frame during a run).

## 2026-11-16 — Several objects per tracking pass (T-067)

**Design from upstream.** transformers' `Sam2VideoModel.forward` tracks objects independently (per-object loop, batch size 1, shared image features). `st_roto_ai.sam2.Sam2MultiVideo` does the same: the image encoder runs once per frame, each object keeps its own `Sam2Video` state. `st_roto_nuke.track.track_objects` / `retrack_objects` (single-object functions are now thin wrappers); `apply_results` / `apply_retracks` write a whole pass as ONE undo step. Prompts carry an object name (old untagged points belong to the node's current object); ST_Roto: points per object, Clear all, Track tracks every prompted object, **Re-track all** (locked objects and objects with nothing to track from are skipped and reported).

**Behaviour change.** Track now skips objects that already exist in the project (before: pressing Track twice created a duplicate object; with several objects per node this would duplicate every earlier object). The old Nuke test relied on renaming + re-tracking the same points and was updated to the new workflow.

**Own bugs found.** (1) In `retrack_object` the reverse pass was meant to restart the point-order chain from the conditioning frame, but the reset ran at the start of the forward pass, so frame `first-1` took its start point from the LAST forward frame (possible point-order rotation at the seam). Fixed; regression test. (2) My first per-object RAM budget (24 // objects = 12) was below the tracker's 15-frame read window: 5,208 disk reloads per pass, found by profiling; budget ≥ 16 now. (3) The first timing probe did not pass the model, so "large" ran tiny; caught because both timings matched.

**Tests.** Unit 61/61: two-object track and re-track identical to single-object runs (CPU), seam regression, per-object prompt rules. Nuke 8/8: new `test_multi_object_track` (IoU target 0.994–0.996, disc 0.983–0.995; one undo removes both; Re-track all fills the disc's frames before its prompt). GUI test passes (22.9 s). GPU probe: identical results (0.0 px), 2 objects 1.36× (tiny) / 1.56× (large) faster than two passes. Evidence: `research/probes/2026-11-16_multi_object/RESULTS.md`.

## 2026-11-16 — Matting: licence research and model-free soft edges (step 1)

**Research** (`docs/RESEARCH_2026-11-16_MATTING.md`): no matting model is clean on both licence and training data. ViTMatte (Apache weights) trained on Adobe DIM / Composition-1k (terms by request, reported non-commercial); BiRefNet matting weights MIT but trained on P3M-10k, AM-2k, Distinctions-646 etc.; ZIM is CC BY-NC 4.0 (licence text read); MatAnyone, VideoMaMa non-commercial. Owner question OQ-22 (recommendation: ViTMatte-S as optional download, off by default, caveat shown). No model downloaded.

**Work.** `st_roto.matte`: colour guided filter (He et al.) restricted to a band around the shape edge; hard inside/outside. Measured on composites with known alpha (`research/probes/2026-11-16_matting`): edge error (SAD) 0.59× the hard shape's on average with the chosen defaults (soft edge 0.44×, motion blur 0.35×, 2 px offset 0.70×, missed hair strands 0.86× — hair needs a learned model). Unit tests pin the improvement (≥ 40 % on soft and motion-blurred edges) and that pixels outside the band never change.

## 2026-11-16 — Matte pass, EXR export, JSON/SVG interchange (T-069, T-070)

**Work.** `st_roto.matte.object_mask` (exact raster of an object's shapes at any frame; between sparse keys a LINEAR blend, reported because Nuke's own curve interpolation may differ), `st_roto.exr` (official OpenEXR Python binding 3.5.4, BSD-3, installed only inside the project: `.tools/nuke-py311`, `.venv`; atomic write via `.part` + rename; Nuke frame naming incl. negative frames), `st_roto_nuke.mattes.render_mattes` and the ST_Roto controls *soft edges / edge band / radius / matte folder / Render mattes (EXR)*. `st_roto.interchange`: ST-ROTO JSON v1 (full fidelity: ids, hierarchy, colours, locks, provenance of every key, explicit coordinate statement; import = new ids, imported origin, one undo step) and SVG per frame; node buttons *Export shapes (JSON + SVG)* / *Import shapes (JSON)*. Silhouette, Mocha, Alembic researched: no public format specs / no Windows binding; both Boris FX apps export Nuke Roto shapes, which ST-ROTO already ingests (`docs/RESEARCH_2026-11-16_INTERCHANGE.md`).

**Own mistakes caught by tests.** Import first created locked objects before writing their keys (the bus refuses key writes into locked objects for every actor): locks now applied last. A unit test assumed object order by creation; objects created in the same second sort by id.

**Tests.** Unit 68/68 (EXR round trip exact, layer-name clashes, hard matte == stored spline, soft edge follows the plate; JSON round trip incl. hierarchy/locks/origins; SVG path numbers exact). Nuke 10/10: `test_render_mattes_exr` (Nuke reads `target.alpha`, `disc.alpha`, `rgba.alpha`; sampled values identical to what was written at 42 points incl. soft-edge pixels; hard matte vs Roto's own render IoU 0.998 on 4 frames), `test_export_import_shapes` (hand-drawn shape → export → delete → import → Roto shape back within 1.5e-5 px).

## 2026-11-16 — Backups, crash recovery, portable projects (T-071)

**Starting point.** Every edit was already one SQLite transaction (WAL) logged with its inverse, so a crash could lose at most the edit in flight. Missing were backups, detection of an unclean session, recovery from a damaged file and portability.

**Work.** `st_roto.persistence`: `backup` (SQLite online backup API → consistent snapshot of an open WAL project, verified with `integrity_check`, rotated per reason), `AutoBackup` (own read-only connections; snapshot only when the operation log changed; final backup on stop), `SessionMarker` (`<project>.session.json`; a marker whose process is gone = crashed; a live one = open in another Nuke; Windows process check via OpenProcess, because `os.kill` would terminate on Windows), `check`/`recover` (damaged file and its -wal/-shm moved aside, never deleted; newest valid backup restored), `pack`/`unpack` (zip with manifest and SHA-256 per file, optional plates; refuses non-empty destinations, path escapes and checksum mismatches; relinks plate paths). `st_roto_nuke.session` runs all of it when a project is opened (auto-backup every 300 s, `ST_ROTO_BACKUP_SECONDS`), the node shows what was found; shots now record their Read path; buttons *Back up now* / *Package project*.

**Tests.** Unit 75/75 incl. a real crashed subprocess, a live competing process, a zeroed database header restored from backup, tampered and path-escaping packages. Nuke 11/11: new `test_crash_recovery_and_package` (process holding the project dies + file damaged → opening from the node reports both, restores the backup, keeps the damaged file; Package project → unpack → same content; marker removed on close).

## 2026-11-16 — Roto motion blur on ST_Roto (T-074)

Knob names measured on Nuke 17.1 (`motionblur_mode`, `global_motionblur`, `global_motionblur_shutter`, `global_motionblur_shutter_offset_type`); linked onto the ST_Roto node. Nuke test: a shape moving 60 px/frame renders with a ~50 px trail along x (y extent unchanged) when set to global, 10 samples, shutter 1. My first pass threshold (20× more soft pixels) was a guess and failed against the measurement (12×; the 'off' render already has 1,401 anti-aliased edge pixels); replaced by the physical check (trail length along the motion). GUI test passes (21.7 s). Unit 75/75, Nuke 12/12.

## 2026-11-16 — CI on Node 24 (T-057), model registry with verification (T-056)

**T-057.** actions/checkout v7 and actions/setup-python v7 (both declare `using: node24`, checked in their action.yml).

**T-056.** The weights manifests existed, but the ONNX exports the runtime loads had no checksums and nothing was checked before loading. `tools/models/register_exports.py` writes `models/manifests/<name>.exports.json` (SHA-256 + size of every exported file, source revision); `st_roto_ai.registry.verify_file` runs before every ORT session and before the tracker's constants/config are read: refuses files outside a model folder, unlisted files, size or SHA-256 mismatches, exports from another revision, non-production licences and models without owner approval. Hashing runs at ~1.2 GB/s (large: 2 GB in 1.7 s); verified files are stamped per (path, size, mtime) in `models/.verified.json` (git-ignored). Tests: unit (tampering with same size, appended data, unlisted file, NC licence, missing approval, revision mismatch, escape hatch, real models verify); Nuke track test passes with verification on (8 files stamped).

## 2026-11-16 — Configurable AI input colour (T-045)

**Measured first.** Nuke 17.1 ships PyOpenColorIO 2.4.2 and Foundry's ACES configs; root knobs `colorManagement`, `OCIOConfigPath` (actual config file) and `workingSpaceLUT` give everything needed.

**Work.** `st_roto.colour`: matrices DERIVED from published primaries/white points with Bradford adaptation (Rec.709/sRGB, ACEScg AP1, ACES2065-1 AP0, Rec.2020, P3-D65) + sRGB curve; display-encoded passthrough; `OcioTransform` for any config/space. `st_roto_nuke.colour.resolve`: node knob *AI input colour*; *auto* = v0 transform under Nuke colour management, OCIO working space → sRGB-encoded Rec.709 under OCIO. The transform id (OCIO: config path, cache id, both spaces) goes into provenance of tracks, re-tracks and matte settings.

**Validation.** Derived AP1→Rec.709 and AP0→Rec.709 equal the published Bradford matrices (1e-5); all five built-ins equal OCIO's ACES cg config 2.2.0 to < 2e-5. Default transform output unchanged (old results reproducible). Nuke: script in OCIO/ACES cg mode, PNG plates read into ACEScg, auto → OCIO transform recorded, tracking IoU vs truth 0.994–0.995 (same as default mode).

**Own bug caught by a test.** `OcioTransform` converted in place and `np.ascontiguousarray` does not copy an already-contiguous float32 array: it overwrote the caller's frame. My first ad-hoc comparison passed only because it passed a copy. Fixed (explicit copy) + regression test. Also: a test compared 0.9999999999999999 == 1.0 exactly (test bug).

## 2026-11-16 — Split objects and adaptive point counts (T-049); libtorch in Nuke (T-038)

**T-049 measured first.** On the synthetic split frame the truth is two pieces (14,652 and 10,766 px²); the tracker kept only the largest (frame IoU ~0.6). `st_roto.pieces.Sequencer`: main shape follows the piece nearest its previous position; other pieces become part shapes matched by centroid; frames without the piece get a collapsed zero-area key (verified: renders nothing in Nuke and in mattes); point count 'auto' = fewest points with mean fit error ≤ 0.3 px and max ≤ 1.5 px on the first frame. Part shapes carry `part_of` in their generator (`views.main_shape` / `part_shapes`), because shapes created in one batch share a timestamp and sort by random id — my first version picked "shapes[0]" as the main shape, which could have been a part. Re-track: guide mask = main artist key ∪ parts; result parts matched to existing part shapes by centroid; unmatched old parts get collapsed AI keys; hand-drawn extra shapes are never touched. Rename carries `_partN` (found by the GUI test: the part kept the old name).

**Accuracy (GPU, 48 frames, union vs truth).** fixed 12/16/24/32 points: mean 0.9941/0.9944/0.9947/0.9949; auto (0.3 px) picks 12. Split frame 23: 0.990–0.993 for all variants. Node slice test: mean 0.985 → 0.993, worst frame ≥ 0.98. Two Nuke tests assumed 16 points / one shape per object and were updated to the intended behaviour; the slice test threshold was tightened (mean > 0.99, worst > 0.97).

**T-038.** libtorch 2.7.1 (string beside `TORCH_VERSION` / `PT_VERSION`), CUDA 12.8, cuDNN 9.7.1, sm_120, MSVC 2022.

**Tests.** Unit 96/96; Nuke 15/15 (new `test_split_object_parts`: Roto render vs truth ≥ 0.981 on frames 18–28, split frame 0.985); GUI passes (rename → `hero`, `hero_part2`).

## 2026-11-16 — Resumable tracking (T-048)

Checkpointed Track with 'Resume track' (details and numbers: `research/probes/2026-11-16_resume/RESULTS.md`). Identical results after cancel and after a simulated crash (CPU proof); +1.2 % tracking time; ~2.4 MB per object-frame on disk while interrupted (R-44). Unit 99/99, Nuke 15/15.

## 2026-11-16 — Package unpack in Nuke, relink, source fingerprints (T-075)

**Work.** Schema v4 (`shots.source_fingerprint`); undoable `update_shot` op (AI refused); `persistence.fingerprint_sequence` (SHA-256 + size of the shot's own first and last frame, frame count), `compare_fingerprint` (match / different / missing / unknown), `relink_shot` (refuses different footage), `relink_path` / `relink_text`; packages include the saved Nuke script and the original project path; `st_roto_nuke.packages` (unpack + ask for missing plates until the fingerprint matches; menu *ST-ROTO › Unpack project package…*; `apply_relink_to_open_script`).

**Found by the Nuke test (three real problems, all fixed).** (1) My first fingerprint hashed the first/last file of the whole folder (48 frames) although the shot uses 0–2 → "different" for identical footage; now the shot's frame range. (2) Nuke stores the Read path as `d:/…/frame_%04d.png` when given `D:/…/frame_####.png`: prefix matching is now case-insensitive for Windows paths and frame patterns accept both spellings. (3) **Nuke Non-commercial saves scripts encrypted** (`.nknc`, "Nuke NC mode encrypted text"), so text relinking of scripts cannot work there; unpack writes a sidecar map and the paths are applied in the opened script (only ST_Roto groups and their Read inputs are touched: 10-node limit). Plain-text scripts (commercial editions) are rewritten directly (unit-tested). Also: a unit test hard-coded schema 3; a heredoc turned `\` into `\` in a test (raw string now).

**Tests.** Unit 104/104 (fingerprints: moved vs different footage, frame ranges; undo of relink; package with plain-text script; unpack asks again after wrong footage). Nuke 16/16: new `test_package_script_relink` (saved NC script + Track → package → unpack with plates moved → script opened, relinked from the sidecar: Read on the moved plates, ST_Roto on the unpacked project, fingerprint match, shapes present).

## 2026-11-16 — Feather and RotoPaint (T-073)

Schema v5 (shape feather x/y/falloff, as Roto's fx/fy/ff); feather written to Roto on export/sync, artist feather edits imported (undoable; undo syncs back); JSON carries it; EXR mattes approximate it; 'Copy shapes to RotoPaint'. Measured Nuke's feather first (`research/probes/2026-11-16_feather/RESULTS.md`): falloff is an exponent; 50 % contour at half the feather; tails depend on the control points. My approximation matches area (0.998) and the 50 % contour (≤ 1 px) but not the tails (mean band error 0.11): documented, Nuke authoritative. A second model (offset control points) was tried, was not better, and was removed. Also caught: my first feathered raster used 16 samples per segment while hard mattes use 64 (inconsistent; fixed). Unit 105/105, Nuke 17/17.

## 2026-11-16 (second session) — Board completion: research, calibration tooling, replication prototype, per-point feather

**Research (no code).** T-032 Nuke 13–17.1 versions (`COMPATIBILITY_MATRIX.md`), T-033 API audit measured in NC (no viewer pick events in Python; XY/BBox handles and PyCustom_Knob work; Deep nodes and stereo views available), T-034 competitors (Foundry **SmartRoto**, announced Jul 2026, is a direct spline-AI competitor), T-036 benchmark datasets (SA-V CC BY 4.0 is the only permissive real-video GT found; MOSE NC; DAVIS data terms not stated), T-030b/T-031b licences (PyTorch BSD-3, DirectML MIT, OpenVINO Apache-2.0, CUDA EULA §1.2.5; Cutie/SEA-RAFT/Grounding DINO weights: no licence stated → Grounding DINO conflict resolved: not production).

**T-068 calibration tooling.** `st_roto.calibration` + `tools/benchmark/calibrate_review.py`. Provisional run (synthetic, 192 frames, 7 bad): current thresholds catch 6/7 with 14 flags; predicted IoU uninformative (corr 0.015); the split frame in reverse is *confidently* wrong (score 8, predicted IoU 0.98, true 0.42) → a temporal-consistency rule is needed (T-078). Defaults kept. Real data needs the owner's approval of a dataset licence (D-020).

**T-020 replication prototype.** Schema v6 (op uuid + origin site, sync marks, branch candidates). `st_roto.sync`: export/import of operations; per-(shape, frame) auto-merge; same-key edits wait as branch candidates; resolve keeps tombstones. Own bugs found by the tests: the first version would have reported the whole shared history as conflicts (fork point added), left pre-v6 operations without ids (migration assigns them), and re-created a resolved conflict on the next sync (resolution now replays the original operation id). Unit tests incl. protection on replicated ops.

**T-076 per-point feather.** Measured the API first (featherCenter keys per frame, read back exact, affects the render). Schema v7 `key_feather`; `set_key_feather` op (undoable; AI refused; locks respected; kept by delete/undo snapshots); Roto import/sync, RotoPaint copy (pixel-identical), JSON. Nuke test `test_point_feather_roundtrip`.

## 2026-11-16 (second session) — Temporal review rule (T-078)

`quality.area_jumps`: a frame whose object area (main + parts, from the stored splines) differs by more than 35 % from both nearest present frames is flagged CHECK. Motivated by the calibration finding (reverse split frame: score 8.0, predicted IoU 0.98, true IoU 0.42 — no score rule can catch it). Nuke: reverse test now flags 23 (true error) and 24 (CPU-run truth 0.986 → possibly a false alarm; GPU-run truth not recorded); the good forward track gets no new flags. Threshold uncalibrated until real data (OQ-23). Unit + Nuke review tests pass.

## 2026-11-16 — Owner approvals D-031 (SA-V subset) and D-032 (ViTMatte-S); ViTMatte integrated

ViTMatte-S downloaded through the licence-checked catalogue, exported to ONNX (exact vs PyTorch at 5 sizes), registered, integrated as an optional *edges* choice with the training-data caveat in tooltip and status. Measured vs the guided filter: better on hair and slightly-off shapes, worse on motion blur (`research/probes/2026-11-16_matting/RESULTS_vitmatte.md`). A registry unit test assumed every model has video graphs; fixed. SA-V: the val split is one 16 GB tar behind a consent click on Meta's site that issues expiring links — the owner must click it; a streaming subset tool is prepared.

## 2026-11-16 - Full headless Nuke suite after ViTMatte; SA-V download not automated

All 19 headless Nuke tests pass (incl. test_vitmatte_mattes). The owner asked Claude to download SA-V itself. Inspection of the downloads page script showed the "Download all links" step sits behind a form (first/last name, email, affiliation, country, intended use) that signs the SA-V licence in the submitter's name. Claude did not submit personal data or bypass the form (it is gated by a browser-storage flag); nothing was sent to Meta. T-068 still waits for the owner to submit the form and save the links file in data/benchmarks/.

## 2026-11-16 - T-068 real-footage calibration (SA-V subset)

Owner submitted Meta's form; Claude streamed the 30-video subset (74 min; the val tar holds all frames before all masks, so most of 15 GB was read; 2 GB kept). Own mistakes: the links-file parser assumed the file name is in the URL (it is a separate column) - first run failed immediately, fixed + test; a calibration run was started without per-frame area (needed for T-078) and restarted a minute in. Findings (CUDA, `RESULTS_sav.md`): single-click prompts picked the wrong object in 19/51 first frames (box: 2/51) -> calibration on the box run; 57 % of review flags were LOST flags on frames where the object really left -> new LOST_MAX_GAP rule (D-033): flags halved, precision 0.31 -> 0.54, recall 0.56 -> 0.49, robust on held-out halves; score and area thresholds kept. Box prompt in the UI proposed (OQ-25). Unit tests 123 pass.

## 2026-11-16 - T-079 box prompt (D-034)

Owner approved OQ-25. The node gets Nuke's native BBox knob (the Crop rectangle; works in Non-commercial, no C++ overlay) with Set box / Clear box; prompts store one box per object as SAM corner points (labels 2/3), passed before clicks (SAM 2 reference order). Measured: the knob value is [x, y, r, t] in Nuke y-up coordinates; a box-only prompt previews and tracks the synthetic target at IoU 0.993-0.996 on CUDA. Old nodes without the knob get a clear message.

## 2026-11-17 - T-081 Re-prompt here, T-080 shape-fit study, owner answers D-035..D-037

T-081: a box (and optional click) on the current frame becomes an extra conditioning prompt for a both-way re-track; stored in the main shape's generator ("fixes"), kept by later re-tracks, one undo step. Own mistake found by the test: the first version saved the fix only on key generators, so a later plain re-track dropped it; the command bus now accepts shape "generator" updates. Also fixed: the status counted all ops as "AI keys changed" (13 for 12 frames). Nuke test: wrong-object track fixed to IoU 0.988-0.995 from the re-prompt frame on. The full Nuke suite ran 20/21 while a probe shared the GPU; the failing GPU-memory test (peak 7,752 MiB) passed rerun alone (4,021 MiB) - concurrency, not a regression.

T-080: on SA-V (51 sequences, tiny and large, CUDA) the traced outline equals the AI mask and the auto spline is within 0.003 IoU; fixed 48/64 points gain <= 0.0026 -> default point count unchanged. The large model is +0.045 mean IoU (mostly fewer lost frames), ~1.4x slower; documented in the user guide. The first probe version rasterised with a per-row Python loop (~170 s per sequence); replaced by a vectorised fill checked equal on 200 random polygons. Own slip: Nuke -t takes bare numbers as frame ranges (--limit 2 rejected) -> --opt=value.

Owner answered OQ-16/17/24: D-035 (override only when the holder is offline/idle), D-036 (15 min), D-037 (every op signed) -> T-083, T-084 ready. Two register lines contained a literal backspace where "data\benchmarks" was written (an earlier escaping slip); fixed.

## 2026-11-17 - T-083 object leases (core prototype, D-035/D-036)

Schema v8 adds `leases`, `presence`, `members`. `set_lease` and `set_role` are ordinary command-bus operations (logged, undoable, replicated); the bus checks every operation MADE locally against leases (edits into an object or child leased by someone else are refused for every actor, undo included), roles (admin assigns; first role must be self-admin) and the override rule (supervisor only, holder without heartbeat for 15 min or never seen; evidence stored in the op). Replayed peer ops are not re-checked (checked where made; T-084 signatures will make that tamper-evident). Two copies taking the same lease while apart produce a branch candidate. 11 new unit tests; the v1-migration test had to drop the new tables too. Not done: Nuke UI for leases/presence, heartbeats over a network transport.

## 2026-11-17 - T-084 signed operations (core prototype, D-037)

No Ed25519 library exists in Nuke's Python or the venv, so the core has its own pure-Python Ed25519 (RFC 8032 reference algorithm, about 100 lines). Validation: RFC 8032 test vectors 1 and 2, and identical keys and signatures to the `cryptography` package (installed in `.venv` only as a test cross-check, also in requirements-dev for CI) on 20 random keys; 8.6 ms per sign + verify. Schema v9: `operations.signature`, `user_keys` (revoked, never deleted). A CommandBus with a Signer signs every op it makes; sync exports signatures and, once any key is registered, refuses altered, forged, unsigned, unknown-author or revoked-key ops (reported as "refused"); `verify_log` re-checks history and found a hand-edited logged op. Own slips caught by the tests: an edit to sync.import_changes deleted the line computing the conflict keys (NameError); a test assertion with mixed and/or was too loose (rewritten exact). Not done: Nuke UI for keys, and the private-key location (must be outside the shared project; a user-level folder is a system-wide change, so it needs the owner's choice).

## 2026-11-17 - CI was red for eight commits (own mistake)

The owner noticed (GitHub app) that CI failed on every job. Cause: since a83fdda (ViTMatte) `st_roto_ai.vitmatte` imported the ONNX Runtime wrapper at module level, so collecting `test_vitmatte.py` failed on CI, which installs no ONNX Runtime; collection errors stopped every job before any test ran. Locally the venv has ONNX Runtime, so it never showed, and I did not check CI after pushing - while CLAUDE.md kept saying "CI green". Fixed (71ef536): lazy import; `test_spill` also lacked `importorskip("onnxruntime")` (found once collection worked). New `tools/dev/pytest_without_ort.py` runs the suite as CI sees it. CI green on all 5 jobs including Python 3.7 (which also confirms leases/signing run on 3.7; uv can no longer install 3.7 locally). Rule added to CLAUDE.md: run it before pushing and check `gh run list` after.

## 2026-11-17 - T-082 prompt comparison on SA-V

Box-only and 3-click runs (CUDA in Nuke, 51 sequences each) added to the existing 1-click and box + click runs. Wrong object at the start: 19 / 13 / 2 / 2; mean IoU over visible frames 0.536 / 0.576 / 0.673 / 0.679. Sequences that start on the right object score the same with a click as with a box (0.696 vs 0.678), so the box mainly fixes object choice. User guide now has the table and recommends a box plus one click. Caveat recorded: prompts simulated from the truth (tight boxes, ideal clicks), tiny model only.

## 2026-11-17 - T-085 fully local operation (REQ-140)

Static guard: product code imports no network module (socket only for gethostname). Inside Nuke, an audit hook saw 0 socket/DNS/HTTP events over node, prompts, Load model, Track on CUDA, soft mattes, export, backup and package. Gap found and fixed: the bundled official ONNX Runtime Windows build has Microsoft's ETW telemetry provider on by default and ST-ROTO never switched it off since onnxruntime was first used; `st_roto_ai.runtime` now calls `disable_telemetry_events()` at import (unit test enforces it). OS connection table (`tools/offline/watch_network.py`): Nuke 17.1 NC itself opens 2 HTTPS connections to AWS eu-west-1 within the first ~2 s of every start, also with an empty script; nothing else external. Recorded as R-45 with OQ-26 (offline test with the traffic blocked needs the owner's approval).

## 2026-11-17 - T-086 difficult sequences (REQ-092)

Measured the product on 7 sequence conditions in Nuke (synthetic shot, CUDA). Start 1001, duplicate frames and an upstream Retime worked. Missing frames, discontinuous sequences and proxy mode made Track fail outright, and a mixed-resolution sequence produced wrong shapes without any error (IoU 0 on the half-res frames) - gaps in the product since T-055 that no test covered. Fixed in `st_roto_nuke.pixels` (FrameUnavailable for missing-file errors only, proxy file name on the pixel Write, fit_to_format) and in Track / Re-track / mattes (skip and report; true time positions; checkpoint carries the skipped frames). After: IoU 0.99+ everywhere, proxy 0.990. The mixed-resolution policy (fit like a default Reformat) is my proposal, D-039 / OQ-27. A first unit-test comparison was wrong (a shorter run changes num_total_frames and so the pointer encoding); corrected to compare with the same-length run.

## 2026-11-17 - T-087 offline test of the whole stack; D-039 accepted

Owner approved OQ-26 (firewall rule) and accepted D-039 (fit mixed-resolution frames to the shot format). Added an outbound block rule for Nuke17.1.exe through UAC (`tools/offline/firewall_nuke.ps1`). With it: headless empty Nuke starts normally, the ST-ROTO offline workflow test passes on CUDA, and the interactive GUI track test passes (48 frames, 24.9 s); 0 external connections in all three, only loopback. The removal UAC prompt was cancelled; asked the owner, who chose to keep the rule (D-040), recorded in CLAUDE.md so a missing network for Nuke is not mistaken for a fault.

## 2026-11-17 - T-088 traditional roto with AI disabled (REQ-010)

Added the 'disable AI (traditional roto only)' node checkbox and the ST_ROTO_AI=off session switch (22 AI controls hidden via stored knobChanged/onCreate callbacks, AI actions refused with a pointer to the traditional workflow, ViTMatte refused), and a clear message when ONNX Runtime cannot load. Writing the Nuke test exposed a real bug: 'Save Roto edits to project' did nothing until a first Track had created the shot, so a purely hand-drawn shot was never recorded; my earlier export test had created the shot by hand and so hid it. Fixed in resync. Nuke test with ORT unimportable passes (whole traditional workflow, no AI module loaded); GUI probe confirms the callback hides/shows 22/22 controls. My first version of the test also counted the empty st_roto_ai package (loaded by the runtime probe) as AI; narrowed to the runtime/tracker/matting modules and AI libraries.

## 2026-11-17 - T-089 formats and resolutions (REQ-110/111)

Measured the product Track on 12 cases. All bit depths/formats tested (PNG16, TIFF16, EXR half/float, DPX10 written by Nuke), 2.39:1 and anamorphic (pixel aspect 2) work at IoU 0.993-0.996 with correct Roto render mapping. Every plate above 1920x1080 failed in Nuke NC because ST-ROTO reads pixels by rendering and NC refuses renders above HD - so until now the product could not track 2K/4K/8K or even vertical HD on the owner's edition, which no test covered. Fixed by reacting to the refusal: a Reformat inside the node reduces the AI's frames into the allowed box (enabled only around each render) and the frame is scaled back; shapes stay full resolution; status explains it. After: 0.992-0.995 up to 8K. Raised OQ-28 (ST-ROTO's own EXR mattes are not subject to Nuke's limit; whether full-res mattes in NC are acceptable is the owner's call).

## 2026-11-17 - T-090 matte size: full resolution and fit 1920x1080 (OQ-28)

Owner asked for both. Added the 'matte size' knob (full resolution default; fit 1920x1080 = area-average of the full-resolution matte into the largest box with the plate's proportions, recorded in the EXR header). Probe in Nuke NC on 1280x720, 3840x2160 and 7680x4320 with guided and hard edges: all combinations work, Nuke reads every EXR exactly, IoU 0.995-0.996 in both modes, fitted = exact downscale of full, 3-11x smaller files, no time saved (computed at full resolution; 8K guided ~14 s/frame). Noted: above HD in NC the guided filter is guided by the reduced-then-upscaled plate. Probe result files contained temp paths with the Windows user name; redacted before committing.

## 2026-11-17 - D-041 default matte size

Owner chose fit 1920x1080 as the Non-commercial default. The node now sets 'matte size' from the edition (NC: fit 1920x1080; others: full resolution); nodes made before the knob follow the same default. Nuke test on a UHD plate: default fit, hard mattes 1920x1080, IoU 0.995; matte, AI-off, ViTMatte and sequence tests still pass.

## 2026-11-17 - T-091 hardware detection and capability report

Owner asked for five features in a row (report, memory-aware model choice, easy large model, leases/keys UI, sharper-edge study). First: 'System report' (node button + ST-ROTO menu). Core rules in st_roto.capabilities (pure; local nvidia-smi and RAM probes; edition limits labelled measured/docs), Nuke facts in st_roto_nuke.capabilities. On this machine: 13 features, 7 fully available, 6 limited/unavailable with reasons. Model VRAM needs are not measured yet (filled by T-092). Not tested: the GUI dialog itself (nuke.message), AMD/Intel GPUs.

## 2026-11-17 - T-092 memory-aware model choice

Measured Track GPU memory (total-used increase; Windows reports no per-process figure): tiny 3,730 MiB, large 6,793 MiB on the 8 GB laptop GPU, unchanged by the object count. Added model 'auto (by free GPU memory)', a pre-check that runs a non-fitting chosen model on the CPU with a clear note (never swapping it), release of other cached sessions when they are what blocks, and a CPU fallback when ONNX Runtime runs out of GPU memory mid-run. Nuke test with fault injection (CUDA pool capped at 200 MiB) passes for Track and Re-track. My first probe run failed because I passed bare numbers to Nuke's command line (frame ranges) - a pitfall already in CLAUDE.md.

## 2026-11-17 - T-093 large model where it helps

Added 're-track model' (used by every re-track) and 'Re-track flagged' (only objects with REVIEW lost flags). Nuke test on the synthetic reverse case: tiny loses frames 16-20 and 22; Re-track flagged with the large model leaves no lost frames (IoU 0.9935-0.9959 on them) and skips the cleanly tracked second object. One synthetic case; the real-footage gain of the large model is the T-080 SA-V figure. I first wrote a 'mean IoU over keyed frames' comparison, which is biased (tiny has fewer keyed frames); the results report lost frames and per-frame IoU instead.

## 2026-11-17 - T-094 collaboration in the Nuke UI

Leases, presence, roles and signing keys now in the object panel (held-by column, Take/Release/Override, Set up signing key, Set role, status line, 60 s heartbeat); logic in st_roto_nuke.collab (Qt-free), projects sign automatically when the author's key file exists; ST_ROTO_KEY_DIR for tests. Headless Nuke test with simulated co-workers exercises every rule (lease refusal, override refused while active and allowed after 15 min idle with evidence, non-supervisor refused, history verifies) and a GUI probe drives the real panel. My first assertion expected 'carol' as holder; the panel correctly shows 'carol (offline)' because the simulated carol never sent a heartbeat. Still a prototype for real teams: no network transport, and replication is not in the UI.

## 2026-11-17 - T-095 sharper-edge measurement study

Measured, without changing the product: given the right object, SAM's 256x256 mask format can lose at most ~0.027 IoU (oracle). On exact-edge composites (real objects pasted onto other videos) today's path reaches 0.926 and guided refinement or a zoom pass recover it (0.974-0.980); on real SA-V footage the same changes score lower than today's path (0.844 -> 0.806-0.833). My first trial used too-tight zoom crops (about 90x100 px with no context), and I nearly read the SA-V result as a verdict before noticing that SA-V's truth is SAM-assisted; added the oracle, a wide-context zoom and the exact-edge composite set. The two sets disagree; decision left to the owner (OQ-29).

## 2026-11-17 - T-096 precise-edge truth kit (OQ-29 b)

Owner chose to build a precise-edge truth on real footage first. Built the kit (20 most-disagreeing SA-V frames padded onto one canvas so a single AI-off ST_Roto node fits the Non-commercial node budget; magenta pointers; instructions), the exporter (holes supported) and the study's --truth mode, and proved the pipeline with a simulated artist in headless Nuke (20/20 frames, IoU 0.983-1.000 vs drawn). Mistakes found on the way: my first kit design used one node per resolution (would exceed the 10-node budget); the yellow pointer was invisible on yellow content; renaming the node dropped the inner-node cache; the first simulation drew one outline per object although some objects have two pieces. All fixed. The real comparison waits for the owner's drawing.

## 2026-11-17 - T-097 propagation controls

While waiting for the owner's edge drawing (OQ-29), built range-limited re-track (neighbour keys as unchanged guides), exclude frames (Track and Re-track, reported apart from unreadable frames) and Lock / Unlock range (locked keys guide re-tracks and are never changed; undoable via the shape generator). Nuke test passes: a large-model re-track changes every frame except exactly the locked and excluded ones; a range re-track changes exactly the range at IoU 0.993-0.996. Mistakes: a frame-list regex replacement got mangled by the Bash heredoc (known pitfall; rewrote the file with the Write tool), and the first test read the re-track record from the shape instead of its keys. The full Nuke suite then caught a regression of mine: merging guide and artist keys with dict(guides, **artist) fails for integer frame keys whenever an object has artist keys, which broke Re-track in three existing tests (my new test had no artist keys). Fixed, and the propagation test now includes an artist key.

## 2026-11-17 - T-098 holdouts, garbage mattes, merge

Measured how Nuke's Roto combines shapes before building: attribute names via the k...Attribute constants (getValue returns 0 for any name, which first misled me), Python edits need curves.changed() to re-render (my first two probe runs showed no effect for that reason), the first layer item is on top, and blend 12 subtracts but can go negative. Recipe: minus on top (inverted for garbage) plus a Clamp after the Roto; ST-ROTO's EXR combine uses the same arithmetic. Added object roles (schema v10), Set role / Role..., Merge into..., and the Clamp in new nodes (lazily in old ones). Nuke test: Nuke's render and the EXR agree at IoU 0.9987; merge and undo behave. A session pause happened mid-task because the command permission check was temporarily unavailable.

## 2026-11-17 - T-099 matte outputs and refinement

Added premultiplied / straight foreground RGB in the matte EXRs (convention in the header), edge offset (erode/dilate), edge blur and core/edge layers. The Nuke test found a real problem: the test's own Read node kept the first EXR open and the second render failed with 'Access is denied' (Windows), leaving a .part file. A probe showed no Nuke call releases the handle, so renders now go to the next version folder when target files are in use (with an explanation) and a failed replace cleans up and explains. Also: OpenEXR's Python API returns R,G,B,A as one 'RGBA' channel, which my reader did not expect.

## 2026-11-17 - Privacy slip (my mistake)

Commit 1ee7c06 (T-099) contained the Windows user name inside a truncated temp path in research/probes/2026-11-17_matte_outputs/result_file_lock.json. The privacy check printed the matches, but my one-line commit command did not stop on them and pushed. No email address was involved. Fixed forward (path redacted) and added tools/dev/commit_checked.ps1, which refuses to commit when the check finds anything; all further commits go through it. The old commit remains in the public history unless the owner decides to rewrite it (force push).

## 2026-11-17 - T-100 rough masks as prompts; D-042

Owner decided to keep the git history (D-042). Built prompts from rough masks: a Roto shape/polygon in the node, another node's alpha, or a mask file become box + interior clicks (not a SAM mask prompt, which would keep the rough edge on its frame). Nuke test with deliberately rough inputs (IoU 0.95, 0.61, 0.89 vs truth) tracked at 0.985-0.994.

## 2026-11-17 - T-101 model manager

Built the ST-ROTO Models panel and its logic: models across user / studio / plugin locations (lookup order, file verification infers its location), full re-verification, a self-test that tracks a generated disc (accuracy + time per frame), removal and import of approved, checksummed models only. Downloads remain the owner-approved tool. Loading now resolves each model's location (model_dir) everywhere. Nuke test passes (incl. import into a user location, using that copy, removing it) and a GUI probe drives the panel. The full suite caught a regression: Render mattes looked up ViTMatte's location for every edge method, which imported st_roto_ai.registry in a purely traditional (AI-off) workflow; the lookup is now made only for ViTMatte edges (AI-off, ViTMatte and matte tests pass again).

## 2026-11-17 - D-043 OQ-29 dropped

Owner chose to skip the precise-edge comparison completely: no drawing, no edge-refinement change. Recorded as D-043; the study (T-095) and the kit (T-096) stay in the repository for later. The full Nuke suite rerun after the T-101 fix was stopped on the owner's request; last verified: 33/34 before the fix, the 3 affected tests passing after it.

## 2026-11-17 - T-101 suite verified; T-102 Objects pane timeline

The full Nuke suite rerun after the T-101 fix completed on the owner's request: 34/34 pass (the earlier commit message's '33/33' was wrong in number and was unverified at the time). Built the timeline in the Objects pane (views.timeline + a painted Qt widget; click jumps frame and selects the object). The first GUI probe sampled background pixels because grab() renders at the display's 1.25 device-pixel ratio; corrected in the probe, and the colours at key, locked and flagged frames and the click behaviour are verified. Process slip: my register script failed on one row, but the commit command on the next line still ran with the previous message, so the T-102 code was pushed as 774bf45 labelled 'D-043'; fixed forward (this entry, next commit), and the commit now runs only if every step before it succeeded.

## 2026-11-17 - T-103 Windows installer

Built st_roto_setup.py (offline package, install, upgrade, rollback, repair, uninstall, status; no admin rights; marked block in .nuke/init.py) and ST-ROTO-Setup.exe (PyInstaller 6.11.1, installed into the project venv). Unit tests in CI; end to end with Nuke 17.1: a real package (tiny model) installed with Nuke's python.exe into temporary folders, Nuke loaded ST-ROTO from the installed copy and tracked on CUDA, uninstall removed everything; the .exe passed the same in a delivery folder. The owner's real .nuke and LOCALAPPDATA were checked untouched. Found: Windows refused the final folder rename right after copying (scanner/indexer) -> retry; Nuke NC exits when USERPROFILE is redirected -> tests redirect HOME only. My first draft left an 'import nuke' line outside the marked block and had a meaningless replace in the block stripper (fixed before testing); one unit-test line was written so that it never called repair (rewritten).

## 2026-11-17 - T-104 acceptance criteria and run

Wrote docs/ACCEPTANCE.md: the 20 criteria of section 30 with verification method, evidence and status (3 met for v0, 15 partly, 2 not met - other Nuke versions/editions and a defect tracker are the main missing pieces). Built tools/acceptance/run_acceptance.py (unit, headless Nuke, GUI probes, installer end to end, offline). Its first run failed one unit test intermittently; measured that Windows' clock gives the same timestamp for ~2 ms, so two backups made close together got the same file name and the second silently overwrote the first - a real data-safety bug since T-071. Fixed (exclusive name reservation with an order-preserving suffix) with a regression test; full acceptance run repeated.

## 2026-11-17 - T-105 defect register

Created DEFECTS.md (criterion 20) with the defects found today and the acceptance-run step that fails on open release blockers. While listing them, confirmed and fixed DEF-001: without roles the combined EXR matte took the maximum of the objects while Nuke's render composites them 'over' (0.5 vs 0.75 where two soft edges overlap); fixed DEF-008 (locked-frame re-prompt message). I first wrote 'verified in test_propagation_controls' for DEF-008 before that check existed; added it to the Nuke test, which passes.

## 2026-11-17 - T-106 DEF-007 fixed

Locked frames ('Lock range') are now enforced by the command bus for every AI key write or delete, not only by the re-track path; artists may still edit them. Unit test; full acceptance run repeated.

## 2026-11-17 - T-107 benchmark methodology

Published docs/BENCHMARK_METHODOLOGY.md (version 1) before any comparative test, with the metric implementation st_roto.metrics (IoU, Dice, boundary F, MAE, SAD, MSE, temporal error, HD95 contour, stability, identity; category weights and overall score). No competitor is lawfully accessible here yet; none was run and no comparison is claimed.

## 2026-11-17 - T-108 delivery packages

Built st_roto.delivery and the node's Delivery package button: outputs, project settings, models used, processing / provenance / quality reports, dependencies, checksummed manifest with verify(). Unit tests (my first expectation said an artist key on an AI shape is 'artist_created'; the product correctly records 'artist_modified_ai') and a Nuke test end to end.

## 2026-11-17 - T-109 stereo / multi-view (REQ-115)

Measured Nuke's stereo mechanics in NC first: one Read with %V serves both views; a Write renders one view with `nuke.execute(..., views=[v])`; a Write WITHOUT a named view fails in a two-view script ("cannot be executed for multiple views"). ST-ROTO's pixel path did exactly that, so no AI action could run in any stereo script (DEF-010, fixed: every render now names a view). A Roto shape is limited to one view with its attributes nv / view1 (measured with Nuke's own render; survives save + reopen).

Built: schema v11 (`objects.view`, `objects.pair`), `st_roto.stereo` (disparity search, prompt transfer, consistency check, mask helpers), node knobs *track every view (stereo)* and *prompt view*, stereo Track (prompt view first, then each other view prompted with a box + clicks moved by the measured disparity and tracked on its own pixels), per-view Roto shapes, per-view re-track and mattes, JSON round trip of view/pair, hand-drawn single-view shapes imported with their view. Stereo flags join the review flags (status, Objects pane, timeline, delivery reports). Decision D-044 (proposed data model).

Measured on a new synthetic stereo shot with exact truth per view (research/probes/2026-11-17_stereo/RESULTS.md): disparity 0.25 px mean error; transferred box IoU 0.9998; consistency check 0 false flags on correct shapes and 20/20 injected errors caught (my first vertical tolerance, 4 % of height, missed 2 of 4 - lowered to 2 % from the measured residuals). In Nuke: IoU 0.991-0.994 in both views, disparity -30.0 px (truth -30), each shape renders only in its view, mattes 0.999+.

**Mistake found by the new test:** after a stereo Track, a plain Track re-tracked the prompt `target` as a third object (the "already tracked" check compared names only). Fixed (pair key counts) and asserted in the test. Also my own slip: a stray `cat` in a shell command blocked on input and had to be stopped; the edit it carried was redone with the Edit tool.

Not done (on the board): stereo Track is not checkpointed / resumable (T-119); camera data for multi-camera and non-rectified rigs (T-120). Thresholds are provisional (synthetic data only).

## 2026-11-18 - T-110 extra channels (REQ-113)

Built a synthetic CG shot with render passes and exact truth (depth, forward/backward vectors, normals, position, Cryptomatte with manifest), then measured in Nuke: every layer passes through the ST_Roto node bit-identical; Nuke's own Cryptomatte node decodes our file at IoU 1.0 (independent check of the encoding; MurmurHash3 also equals the published test vectors); Nuke's VectorGenerator in headless NC gave unusable vectors (28 % non-zero), so the vector convention is measured from the plate instead of assumed.

Found DEF-011: Nuke's Roto composites shapes over the input alpha, so on plates that already have alpha the node's alpha was 1 almost everywhere. New nodes now replace the input alpha (linked knob), measured exact; older nodes unchanged (D-045).

Built `st_roto.channels` (Cryptomatte decode/encode, vector convention per axis, object-centric occlusion handling, channel-median spikes, multi-object check), schema v12 `channel_reports` (undoable op, kept through delete/undo, lease-aware), review flags, node knobs and buttons (List channels, prompt from Cryptomatte, Check with channels; the check works with AI off).

**Rules I had wrong at first, each caught by measurement:** (1) a relative jump rule flagged position P.Y 6 times on correct shapes (zero crossings) - replaced by a spike rule against the shot's spread; (2) my first occlusion test removed the object's own moving silhouette and hid a stuck shape (IoU 0.997) - replaced by an object-centric test; (3) bilinear vector sampling faked occlusions along every edge - nearest-pixel; (4) on the real AI track, one outline point took the passing distractor's vector (motion IoU 0.88 on a 0.99-correct frame) - points now read vectors 3 px inside the shape (0.993). Also two shell-quoting slips of mine (heredoc with nested quotes, collapsed backslashes) - redone via script files, as CLAUDE.md says.

Result: synthetic shot 0 false flags on correct shapes, 12/12 injected errors caught; in Nuke the AI track has no flags (motion IoU >= 0.981) and a wrong key is flagged by depth, motion and Cryptomatte. Not done (T-121): shapes straight from Cryptomatte, propagation along vectors, reduced render above the NC limit for the check.

## 2026-11-18 - T-111 review overlay in the viewer, settings presets (REQ-120/121)

Measured first what Nuke Non-commercial lets Python show in the viewer: no custom drawing (NDK only), and `ViewerWindow.showStatusMessage()` takes no text (no setter: my first probe assumed it did and crashed). What works: the Roto shapes' overlay colour attributes (ro/go/bo/ao), animatable per frame and drawn in the viewer while the Roto's controls are open - verified by SCREEN capture (widget.grab() does not capture OpenGL: my first capture was black); ao = 0 falls back to Nuke's default red, so lost is magenta. The Viewer's knobChanged fires on frame change.

Built: review colours keyed per frame on the shapes (run-length keys, constant on whole frames), re-applied after every sync, channel check and toggle; Show shapes in viewer; a "this frame" readout driven by the Viewer callback; settings presets (st_roto.presets: built-in / studio / user, validated, only settings, linked inner-Roto knobs). A test slip of mine: the first Nuke test used non-hex shape ids, so no shape tag matched and nothing was coloured - fixed the test (real ids are uuid hex). GUI test by screen capture passes (its first condition counted the NC dialog's yellow warning icon - fixed by comparing with an unflagged frame).

## 2026-11-18 - T-112 node family (REQ-040, REQ-292)

Measured the Non-commercial node budget precisely before designing: every look-up costs 1 (even of the same node), deleting frees nothing, a pasted graph costs 1 and returns its last node, gizmos work in NC, thisNode in callbacks is free. Researched architecture and naming (docs/RESEARCH_2026-11-18_NODE_FAMILY.md): the ten section-6 modules map to three node types - ST_Roto (main/select/track/spline/stereo), ST_RotoMatte (matte/refine/holdout) and ST_RotoOutput (output); Deep needs the NDK.

Built ST_RotoMatte (mattes of chosen objects / roles in the node graph: alpha = combined, one layer per object, plate unchanged; pass-through before rendering; validated project/shot/objects; per-view %V) and ST_RotoOutput (export, delivery, package, backup), both pasted groups with menu entries; the shared handlers now accept a shot named in a knob. Rebuilt ST_Roto's inner graph by paste: 6 -> 3 node objects at creation. **Bug found on the first product run:** the pasted pixel Write had no file name - fixed by configuring the Write that nodePaste returns. One fresh NC session with Read, ST_Roto, Track, mattes, ST_RotoMatte and ST_RotoOutput leaves 5 of 10 node objects.

## 2026-11-18 - T-113 Alembic export

Found no Alembic Python bindings, but Nuke 17.1 bundles USD 0.25.8 with its Alembic plug-in: exporting a USD stage to .abc writes a real Ogawa Alembic file. Nuke 17 reads .abc through the same USD path (GeoImport) and documents meshes, points, cameras and transforms for Alembic, not curves - so each shape is written twice: an animated closed cubic Bezier curve (exact) and an outline mesh. Verified: USD read-back within 3e-5 px, collapsed parts invisible on their frame, and Nuke's own 3D renders the meshes at IoU 0.9999 against the splines. My slips: a test passed a Windows path with backslashes to a Nuke file knob (read as escapes); the first probe expected samples only on keyed frames (usdAbc adds a hold sample at time 0). Not verified in Houdini/Maya/Blender: no independent reader on this machine.

**Privacy slip caught before commit (2026-11-18):** my T-112 budget probe wrote local temp paths (containing the Windows user name) into `result_main_budget_track.json`; `tools/dev/commit_checked.ps1` refused the commit, nothing was published. The file was redacted (`<HOME>`) and the probe now redacts the user folder itself.

## 2026-11-18 - T-114 model versions side by side, rollback (REQ-130)

Archived versions are complete mini models roots (versions/<name>/<id>/), so the existing licence / approval / checksum verification covers them and name@id runs one without activating it. Use this version verifies first, releases ONNX Runtime sessions, archives the active version and moves the chosen one in (moves: models are GBs); Roll back and a history file. Found on the way: importing a model over an installed one DELETED the old copy - it is archived now. Tested with the real SAM 2.1 tiny in temporary locations (two versions self-tested side by side on CUDA, activation with loaded sessions, rollback) and the Models panel in interactive Nuke.

## 2026-11-18 - T-115 edge decontamination, spill, chatter (REQ-101)

Decontamination solves I = aF + (1-a)B with background / foreground colours pushed out from sure pixels; spill is a channel-limit despill with automatic screen colour; both feed the mattes' RGB, recorded in the EXR header. Measured on synthetic composites with exact truth: fringe 42x lower over a green screen, 3.2x over a natural background. Chatter reduction smooths AI key trajectories (quadratic fit; artist / locked keys anchor). **Honest result:** where edges wobble per frame it cuts temporal error by 41-48 %, but on the real (already clean) track of the synthetic shot it made temporal error 12 % worse - so it is opt-in, not default. Found by the unit test: a linear fit at run ends bent real acceleration; such frames are now left unchanged.

## 2026-11-18 - T-119 stereo Track resume

Stereo runs are now a sequence of checkpointed passes (stereo.json + result per finished view + the running pass's own T-048 checkpoint). Resume continues the interrupted view and reuses the prompts already derived for the other views. Test: cancelled in the right view's pass, resumed, and compared with an uninterrupted run: identical keys (max difference 0.0) for both views.

## 2026-11-18 - T-120 multi-camera correspondence from camera data

Measured Nuke's camera model first (Nuke 17 3D; the classic path rendered nothing headless; world_matrix only via valueAt): my projection matches Nuke within 0.33 px after fixing my own window-translate sign. Built a ray-cast three-camera test shot (non-rectified) and an epipolar search. It failed in four measured ways before it worked - fixed window too short (shifts of -265 px), coarse 16 px grid, SSD preferring flat background when a view sees the object 11 % smaller, and in Nuke the AI mask tipping a weak match to the wrong object (view C tracked the wrong thing) - fixed by searching the whole line, refining the top 5 coarse candidates, NCC, and comparing every candidate at the scale its triangulated depth implies. Result: 31/32 view-frames found (horizontal search: 0); in Nuke all views IoU 0.99, epipolar flags clean, a wrong object flagged.

## 2026-11-18 - T-121 shapes from Cryptomatte, propagation along motion vectors

Cryptomatte coverage per frame through the tracker's own shape builder gives shapes at IoU 0.9975 (0.9994 with 24 points). Propagating a key along the vectors broke at the fast occluder: plain per-point warping 0.98 -> 0.03 in one frame. My first robust fix made it worse (0.0): its least-squares start was poisoned by the occluder (fitted scale 0.16); starting from the median vector fixed it (0.955 after 19 frames). In Nuke with AI disabled both work as one undo step, and propagation stops before the artist's next key.

## 2026-11-18 - Register corrections and acceptance rerun

docs/ACCEPTANCE.md listed gaps already closed (edge decontamination / spill / chatter: T-115; model versions + rollback:
T-114; benchmark methodology: T-107) and old test counts; corrected, with the remaining gaps stated more precisely
(chatter reduction opt-in, vector propagation uses renderer vectors not live-action optical flow, Alembic not checked in
a third-party application). OQ-11 closed as overtaken (T-011c/T-044). Full acceptance run after T-109..T-121
(`docs/acceptance/run_2026-11-18T044943Z.md`): all 6 steps PASS. Statuses unchanged: 3 met, 16 partly, 1 not met.

## 2026-11-18 - T-122 first public release 0.1.0 (D-046)

Owner decided: version 0.1.0 (not 1.0: section 30), public GitHub pre-release now (R-23 accepted for distribution),
tiny in the main zip, SAM 2.1 large and ViTMatte-S as separate downloads (the large model alone is 2.05 GB; GitHub
refuses files over 2 GiB). The setup learned model packages (`package-model`, `install-model`, installed
automatically when next to the main zip; checked against the package and the version's export manifest; covered by
verify / repair; carried over on upgrade). Found while preparing: NOTICE did not credit the bundled Python packages or
ViTMatte (now does); the installed copy had no VERSION file, so it would have reported 0.1.0-dev (now packaged);
the README still said "No product code exists yet" (rewritten for users). My own release check first failed on its
own assertion (the Track status does not name the model); it now checks the loaded ONNX sessions: all 6 from the
installed large model. Not tested: a second computer.

## 2026-11-18 - T-116 DirectML (AMD / Intel GPUs)

Owner approved onnxruntime-directml. 1.24.4 is the last DirectML build on PyPI. Shipped in its own folder because it is the same Python package as onnxruntime-gpu; one is chosen per Nuke session. Measured in Nuke on the RTX 5060 through DirectML: the same masks as CUDA (IoU >= 0.997 per frame), 7-20 % slower, ~35 % less GPU memory. The System report then showed that this laptop also has an integrated Intel UHD GPU: tracked on it (adapter 1) with IoU >= 0.995 vs CUDA at ~6 s/frame - the first real non-NVIDIA GPU result. One existing unit test asserted the old "DirectML not shipped" text; changed to the new fix hint. AMD stays untested (no hardware).

## 2026-11-18 - T-123 scene cuts, T-124 manual and developer guide

Scene cuts: the first detector called every inserted flash a cut (31 of 30 sequences) because the flash rule only looked forward; fixed by also checking the jump OUT of a flash. Of 7 "false" cuts in real SA-V videos, 4 were genuine camera cuts inside those videos (checked by eye) - counted apart, not hidden. Thresholds swept and chosen on the same 30 videos (no held-out set: stated in RESULTS). In Nuke the first test failed on the status text only: Track had already been limited to the segment, so nothing was trimmed and the "stopped at scene cut" note was missing; the note now depends on the segment end. Documentation: docs/MANUAL.md and docs/DEVELOPER_GUIDE.md written from the code (knob list and module API extracted, not from memory).

Full Nuke suite after T-116/T-123: 46/47 - test_cancel_and_resume_track failed because Track now renders every frame for automatic cut detection first, so its "cancel on the 6th render" landed before tracking (nothing to resume; correct behaviour). The test now switches cut detection off; 47/47 then, GUI 7/7. Cost noted: with an empty cuts knob the first Track renders each frame twice (detection + tracking).

## 2026-11-18 - T-125 install guide and generated API reference

Owner asked again for the full manual and developer docs; MANUAL.md and DEVELOPER_GUIDE.md already existed (T-124), so the remaining documentation gaps of acceptance 19 were filled: INSTALL.md and a generated API reference. While generating it, found my own scene-cut docstring saying the thresholds were set on synthetic data - they were set on the real SA-V footage; corrected.

## 2026-11-18 - T-126 owner's green-screen shots

First real production footage (owner's, permission for testing, no images in git). My mistakes on the way: the first boundary score counted the frame edge where the body leaves the frame (fixed: border strip ignored); my first prompt check placed the crew box on empty floor (fixed before the runs); my ViTMatte check script used the wrong model root; my hair "result" first ranked ViTMatte worst - a crop showed the key, not ViTMatte, was the problem, so no hair ranking is claimed. Real defects found: review flags silent on a real failure (DEF-012), ViTMatte out of memory at 4K (DEF-013, fixed with tiles), guided mattes 16 s/frame at 4K (DEF-014). The batch took ~2.5 h, mostly the large-model matte passes at 4K.
