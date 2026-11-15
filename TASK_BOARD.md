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
| T-010 | Machine audit: Python, compiler, CUDA, driver, Nuke build, Git; live headless probes in Nuke NC | `docs/MACHINE_AUDIT_2026-11-15.md`, `research/probes/2026-11-15_machine_audit/` |

## Blocked

| ID | Task | Blocked by |
|---|---|---|
| T-011b | In-process inference prototypes, routes B and D (NDK C++) | OQ-01; VS 2022 Build Tools + CMake not installed (OQ-14) |
| T-013 | Architecture proposal and ADRs | Unblocked (D-009..D-012) |
| T-020 | Collaboration architecture | Unblocked by D-022..D-025 (OQ-16/17 minor) |
| T-021 | Create GitHub repository | Unblocked (D-013, D-014): install gh, owner signs in |

## Ready (desk research, can proceed now)

| ID | Task |
|---|---|
| T-012 | Split requirements register to one ID per bullet |
| T-030b | Remaining licence texts: Cutie weights, Adobe DIM dataset, SEA-RAFT/RTMPose weights, NVIDIA, PyTorch, DirectML, OpenVINO |
| T-031b | Remaining categories: hair-specific, motion-blur reconstruction, occlusion reasoning, permissive video matting/inpainting; resolve Grounding DINO conflict |
| T-040 | Measure Nuke image ↔ numpy transfer cost in Python (needed for route C) |
| T-041 | Route C with a real model: SAM 2.1 tiny exported to ONNX, run in Nuke (needs owner approval to download weights, §15) |
| T-032 | Tabulate Python, Qt, compiler and CUDA versions for Nuke 13 to 17.1 |
| T-033 | Audit Nuke Python and NDK APIs for viewer interaction, custom knobs, Deep, stereo |
| T-034 | Competitor survey (§21) |
| T-035 | Research implications of the five collaboration decisions |
| T-036 | Identify open benchmark datasets with ground-truth mattes and their licences |
| T-011a | Route A prototype: export a permissive model to TorchScript, convert to `.cat`, run in Inference node, measured |
| T-038 | Determine libtorch version bundled with Nuke 17.1v3 |
