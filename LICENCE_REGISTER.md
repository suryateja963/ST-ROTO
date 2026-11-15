# Licence Register

First issue 2026-11-15; second issue 2026-11-15. Full texts read so far: **SAM License, S-Lab 1.0, ONNX Runtime (MIT), BiRefNet (MIT), Foundry EULA (March 2026, key clauses)**. Everything else is from model cards or secondary sources. Details and sources: `docs/RESEARCH_2026-11-15_LICENCES_AND_MODELS.md`.

## Project licence

**Apache License 2.0**, approved by the project owner 2026-11-15 (D-013). Text in `LICENSE`, fetched from https://www.apache.org/licenses/LICENSE-2.0.txt, SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.

## Models

| Item | Licence as found | Commercial use | Redistribution of weights | Notes |
|---|---|---|---|---|
| SAM 2 / 2.1 | Apache-2.0 | Yes | Yes | Includes a BSD-3-Clause component (cc_torch) |
| SAM 3 | SAM License (Meta), full text read | Yes (royalty-free; restricted uses listed) | Yes, under the same agreement with a copy | Not OSI. Meta may amend; terminates on IP suit. No copyleft on our code. OQ-07 |
| Cutie | MIT | Yes | Not confirmed for weights | RITM sub-component has its own licence |
| BiRefNet | MIT | Yes | Reported yes | |
| ViTMatte | Code MIT; HF weights Apache-2.0 | Weights licence yes; training data (Adobe Composition-1k) reportedly non-commercial | Yes per card | R-11 |
| MatAnyone / MatAnyone 2 | S-Lab License 1.0, full text read | No ("non-commercial purpose") | Non-commercial only | Research-only |
| TAPIR / BootsTAPIR / TAPNext | Apache-2.0 (code and checkpoints) | Yes | Yes | Official README statement |
| OWLv2, ViTPose base, EdgeTAM | Apache-2.0 (cards) | Yes | Yes | |
| Florence-2 | MIT (card) | Yes | Yes | |
| Grounding DINO base | Apache-2.0 card; conflicting secondary claim | Unresolved | Unresolved | |
| SAM2Long, ProPainter, VideoMaMa | CC BY-NC / S-Lab / CC BY-NC | No | NC only | Research-only |
| Robust Video Matting | GPL-3.0 | Yes, under GPL terms | Under GPL terms | Incompatible with inclusion in a permissively licensed project |
| CoTracker3 | CC-BY-NC-4.0 | No | Non-commercial only | Research-only |
| Depth Anything V2 Small | Apache-2.0 | Yes | Yes | |
| Depth Anything V2 Base/Large/Giant | CC-BY-NC-4.0 | No | Non-commercial only | Research-only |

## Runtimes and platform

| Item | Licence as found | Notes |
|---|---|---|
| ONNX Runtime | MIT, © Microsoft (text read) | 1.26.0 pinned for Nuke 17.1 (CUDA 12). Reuses Nuke's CUDA DLLs, so ST-ROTO ships no NVIDIA files on this route |
| OpenEXR Python binding (`openexr` 3.5.4) | BSD-3-Clause, Academy Software Foundation (PyPI metadata; text not yet read) | EXR matte writer (T-070); installed in `.tools/nuke-py311` and `.venv` only. Redistribution permitted with notice |
| NVIDIA CUDA / cuDNN runtime DLLs | NVIDIA proprietary terms | Redistribution terms must be reviewed before bundling in the installer |
| TensorRT | NVIDIA proprietary terms | Not reviewed |
| DirectML | Not reviewed | |
| OpenVINO | Not reviewed | |
| PyTorch / libtorch | Not reviewed | |
| Foundry Nuke, NDK | Foundry EULA, updated March 2026 (key clauses read) | Clause 2.1(g): NC licence may not be used "(e) to create any commercial tools or plug ins", nor for commercial/professional purposes or in employment/business. Clause 3: no distribution of the Software incl. plug-ins/SDK. No plug-in development grant. **Never ship Foundry files.** R-23, OQ-01 |

## Outstanding

- Read every licence text in full and record the version and date.
- Audit training-data licences for each production-candidate model.
- Software Bill of Materials: not started (no dependencies exist yet).
