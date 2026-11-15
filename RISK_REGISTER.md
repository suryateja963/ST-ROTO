# Risk Register

First issue, 2026-11-15. Likelihood and impact: High / Medium / Low. [V] verified from a cited source in `docs/PHASE1_DISCOVERY_REPORT.md`; [U] unverified.

| ID | Risk | Evidence | L | I | Mitigation | Owner decision |
|---|---|---|---|---|---|---|
| R-01 | Development machine's Nuke edition cannot load C++ plug-ins | [V] Foundry: Non-commercial supports only shipped plug-ins | Certain | High | Developer or commercial licence | OQ-01 |
| R-02 | 10-node Python cap in Non-commercial and Indie breaks multi-node tooling | [V] Foundry edition table; **[M] reproduced in Nuke 17.1v3 NC; nodes created from Python count too** | Certain | High | Same as R-01; or a single-node design for restricted editions | OQ-01 |
| R-03 | Requirement to support Non-commercial and Indie cannot be met in full | [V] follows from R-01, R-02 | Certain | High | Record as "supported with limitations" or "unsupported"; needs scope approval | OQ-01 |
| R-04 | Scripts saved in Non-commercial cannot be opened in commercial Nuke, so test assets do not transfer | [V] | Certain | Medium | Generate test scripts from Python, not saved files | – |
| R-05 | Second CUDA/cuDNN or libtorch stack inside the Nuke process conflicts with Nuke's own libraries | [U] common failure mode with in-process runtimes | High | High | Prototype each route in §4 of the discovery report; consider static linking or DirectML | Phase 2 |
| R-06 | 8 GB VRAM and 16 GB RAM insufficient for larger models at production resolution | [U] not measured | High | High | Measure; tiling, half precision, smaller variants, unload between stages | – |
| R-07 | No commercially licensed video matting model | [V] MatAnyone family S-Lab licence; RVM GPL-3.0 | High | High | Research further candidates; trimap matting from segmentation; licence enquiry to authors | – |
| R-08 | ~~No commercially licensed point tracker~~ **Mitigated**: TAPIR/BootsTAPIR/TAPNext checkpoints Apache-2.0 (training data unaudited) | [V] DeepMind README | Low | Medium | Research alternatives; use Nuke's own tracker and optical flow | – |
| R-09 | One compiled build needed per Nuke release line; Python and Qt differ between Nuke 13 and 17 | [V] NDK is C++ symbol-based; [U] exact Python/Qt per release | Certain | Medium | Build matrix in CI; thin version-specific layer | OQ-09 |
| R-10 | Total scope far exceeds what one developer machine and one agent can verify | Scope of master prompt | Certain | High | Milestones with real acceptance tests; honest status reporting | OQ-11 |
| R-11 | Training-data terms behind "permissive" models restrict commercial use | [U] not audited | Medium | High | Audit before any model enters the production set | – |
| R-12 | SAM License conditions conflict with the project's open-source position | [V] custom licence with use restrictions | Medium | Medium | Optional separate download | OQ-07 |
| R-13 | Project licence incompatible with Foundry's NDK terms | [U] EULA not read | Low | High | Read EULA; ask Foundry alongside OQ-01 | OQ-08 |
| R-14 | NVIDIA runtime DLLs cannot be bundled in an offline installer under their terms | [U] terms not read | Medium | Medium | Read terms; DirectML fallback; user-supplied runtime | – |
| R-15 | Windows packaging of models whose upstream recommends Linux/WSL (SAM 2) | [V] upstream install note | Medium | Medium | Export to ONNX or TorchScript; avoid upstream Python packaging | – |
| R-16 | No lawful ground-truth footage for benchmarks, or no lawful access to competitors | [U] not researched | Medium | Medium | Identify open datasets; trial licences | OQ-13 |
| R-17 | Collaboration architecture designed before five open decisions are answered | Master prompt §19.2 | Medium | Medium | Do not design it until answered | OQ-02..06 |
| R-18 | ~~No terminal on the development machine~~ **Closed 2026-11-15**: Claude Code now runs locally | – | – | – | – | – |
| R-19 | Non-commercial caps output at HD and disables some codecs, limiting 4K to 8K testing | [V] Foundry | Certain | Medium | Same as R-01 | OQ-01 |
| R-20 | No C++ toolchain on the machine: Visual Studio 2022 / MSVC, CMake, Ninja absent | [M] machine audit section 3 | Certain | High (NDK routes) | Install VS 2022 Build Tools + CMake (system-wide, needs owner approval) | OQ-14 |
| R-21 | System Python is 3.12; Nuke 17.1 embeds 3.11.11, so compiled packages must target cp311 | [M] | Certain | Medium | Project-local Python 3.11 (via uv) under `D:\ST-ROTO` | - |
| R-22 | ~~Inference node GPU use unproven~~ **Closed**: GPU is used when Nuke runs with `--gpu` (terminal mode is CPU-only without it) | [M] gpu_ort probe | – | – | Tests must pass `--gpu` | – |
| R-23 | Developing ST-ROTO on a Non-commercial licence may breach Foundry EULA 2.1(g)(e) "create any commercial tools or plug ins" (ST-ROTO is free but intended for commercial users); "commercial" undefined | [V] EULA March 2026 | Unknown | High | Owner decided to continue and accepts the risk (D-010) | Accepted by owner |
| R-24 | Each Nuke release ships its own CUDA major; ONNX Runtime must be pinned to match (1.26.0 = last CUDA 12 build; 1.27+ need CUDA 13) | [M] gpu_ort probe | Certain | Medium | Per-Nuke-line runtime pin; CI check of provider DLL imports | – |
| R-25 | ViTMatte weights trained on Adobe Composition-1k, reportedly non-commercial dataset | [S] | Medium | High | Obtain Adobe DIM licence text; seek alternative or retrained weights | – |
| R-26 | 1.0 cannot ship while C++/Deep requirements wait for a plug-in-capable licence (D-011) | Owner decision | Certain | High | Build all Non-commercial-capable parts first; revisit licence before Phase 7 | D-011 |
| R-27 | Nuke 13+ mandatory (D-017): Nuke 13/14 use Python 3.7/3.9 and PySide2, older CUDA; ONNX Runtime and numpy pins differ per line | [U] versions to tabulate (T-032) | Certain | High | Version-portable Python layer; per-line runtime pins; test each line | D-017 |
