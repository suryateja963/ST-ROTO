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
