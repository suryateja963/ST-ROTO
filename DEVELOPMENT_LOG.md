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
