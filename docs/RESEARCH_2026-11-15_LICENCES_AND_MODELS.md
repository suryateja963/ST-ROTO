# Research — Licence Texts and Missing Model Categories (2026-11-15)

Tasks T-030 (licence texts) and T-031 (missing model categories). Desk research only: **no model was downloaded or run.** Not legal advice.

Evidence labels: **[V-text]** full licence text read · **[V-card]** licence field on the official model card / official README statement · **[S]** secondary source only · **[U]** not established.

## 1. Headline findings

1. **Foundry EULA (updated March 2026), clause 2.1(g): a Non-commercial licence may not be used "(e) to create any commercial tools or plug ins"**, nor "(b) for any commercial, professional, for-profit and/or on-sale purpose", nor "(c) in the course of any employment or business undertaking". "Commercial" is not defined. ST-ROTO is free and open source but intended for studio and commercial use. Whether developing it on Non-commercial is permitted is **ambiguous and must be put to Foundry** (added to OQ-01, risk R-23). [V-text, S-EULA]
2. The EULA (clause 3) prohibits distributing the Software "including any tool, plug-in, SDK or other functionality", and contains no clause granting plug-in development rights. **ST-ROTO must never redistribute Foundry files** (DLLs, `.cat` models, headers). The ONNX Runtime route tested today needs none: it reuses Nuke's installed CUDA DLLs. [V-text]
3. **SAM License (SAM 3) was misread in the first issue.** Full text: royalty-free, worldwide licence to use, reproduce, distribute, modify and make derivatives. Redistribution must be "under the terms of this Agreement" with a copy provided; **no copyleft on ST-ROTO's own code**. Restrictions: trade controls, ITAR/military/nuclear/espionage/weapons uses, no reverse engineering of the materials. Meta may amend it with immediate effect. Licence terminates if the licensee sues Meta over IP. Not an OSI licence. [V-text, S1]
4. **NTU S-Lab License 1.0 (MatAnyone) confirmed non-commercial**: grant is "for non-commercial purpose"; commercial use requires contacting the authors. Research-only stands. [V-text, S2]
5. **A commercially usable point tracker exists**: DeepMind states that all pre-trained checkpoints in `google-deepmind/tapnet` (TAPIR, BootsTAPIR, TAPNext) are Apache-2.0. Gap R-08 is closed, pending training-data review. [V-card, S5]
6. **Still no permissively licensed general-purpose video matting model.** MatAnyone/MatAnyone 2 (S-Lab NC), VideoMaMa (CC BY-NC / Stability Community), RVM (GPL-3.0). BackgroundMattingV2 is MIT and was relicensed explicitly to permit commercial use, but it needs a clean background plate. [S]
7. **ViTMatte's training-data risk is concrete.** The official HF weights carry Apache-2.0, but they were trained on Composition-1k, built from the Adobe Deep Image Matting dataset, which a third-party card reports as non-commercial. Whether dataset terms bind trained weights is a legal question → R-11 is now specific. [V-card for weights licence, S for dataset terms]
8. **Prior art: OpenMatte** (Apache-2.0, v0.1.0, 4 commits). Nuke node using SAM 2.1 + ViTMatte, but it runs the engine **out of process** via an external Python and blocks Nuke's UI, and is untested in Nuke. ST-ROTO's in-process requirement differs. Relevant to §21. [S9]
9. **No permissively licensed video inpainting found.** ProPainter is S-Lab NC; DiffuEraser is Apache-2.0 but depends on ProPainter weights. [S]

## 2. Model category coverage (master prompt §7)

| Category | Candidate | Licence (weights) | Evidence | Class |
|---|---|---|---|---|
| Promptable image/video segmentation | SAM 2.1 (tiny–large, 38.9–224.4 M params) | Apache-2.0 | V-card | Production-candidate |
| | EdgeTAM (efficient SAM 2 variant) | Apache-2.0 | S (HF card per search) | Production-candidate, verify |
| | SAM 3 (859.9 M params, gated) | SAM License | V-text | Decision needed (OQ-07) |
| Video object segmentation | Cutie | Code MIT; **weights licence not stated** | V-card (code) | Unclear until weights terms found |
| Long-term tracking | SAM2Long | CC BY-NC 4.0 (own code) | S | Research-only |
| | SAMURAI, DAM4SAM | U (zero-shot on SAM 2.1 weights) | U | Not classified |
| Point tracking | TAPIR / BootsTAPIR / TAPNext | **Apache-2.0 incl. checkpoints** | V-card | Production-candidate |
| | CoTracker3 | CC-BY-NC-4.0 | V-card | Research-only |
| Optical flow | RAFT | BSD-3-Clause | S (mirror) | Verify |
| | SEA-RAFT | Code BSD-3-Clause; weights not stated | V-card (code) | Verify weights |
| Image matting | ViTMatte (S 25.8 M / B) | Apache-2.0 (HF), code MIT; trained on Composition-1k | V-card + S | **Training-data review required** |
| Video matting | MatAnyone / MatAnyone 2 | S-Lab 1.0, non-commercial | V-text | Research-only |
| | VideoMaMa | CC BY-NC / Stability Community | S | Research-only |
| | Robust Video Matting | GPL-3.0 | V-card (code) | Research-only under permissive project licence |
| | BackgroundMattingV2 | MIT (needs background plate) | S | Candidate for locked-off shots only |
| | MODNet, VMFormer | U / "other" | S | Not classified |
| High-res dichotomous segmentation | BiRefNet (220.7 M) | MIT | V-card | Production-candidate |
| Open-vocabulary detection / grounding | OWLv2 base (155 M) | Apache-2.0 | V-card | Production-candidate |
| | Florence-2 large (776.7 M) | MIT | V-card | Production-candidate |
| | Grounding DINO base (232.8 M) | Apache-2.0 on card; one secondary source says original weights are research-use | V-card vs S | Conflict to resolve |
| Pose | ViTPose base (85.9 M) | Apache-2.0 | V-card | Production-candidate |
| | RTMPose / RTMO | Code Apache-2.0; weights not stated | S | Verify |
| Depth | Depth Anything V2 Small (24.8 M) | Apache-2.0 | V-card | Production-candidate |
| | Depth Anything V2 Base/Large/Giant | CC-BY-NC-4.0 | Earlier issue | Research-only |
| Video inpainting | ProPainter | S-Lab 1.0, non-commercial | S | Research-only |
| | DiffuEraser | Apache-2.0 but needs ProPainter | S | Research-only in practice |
| | MiniMax-Remover | U | U | Not classified |
| Boundary refinement | CascadePSP, SegRefiner | U | U | Not classified |
| Hair-specific segmentation | none found | – | – | **Gap** |
| Motion-blur reconstruction | not researched this round | – | – | Gap |
| Occlusion reasoning | via VOS memory (SAM 2.1 / Cutie); no separate model researched | – | – | Gap |

"V-card" means the licence the authors declare. It does not prove the authors had rights to their training data (R-11).

## 3. Runtimes and platform

| Item | Licence | Evidence | Note |
|---|---|---|---|
| ONNX Runtime | MIT, © Microsoft | V-text | 1.26.0 is the newest PyPI CUDA-12 build (probe 2026-11-15) |
| Foundry EULA | Proprietary, updated March 2026 | V-text (summary + excerpts) | See findings 1–2 |
| NVIDIA CUDA/cuDNN redistribution | Not read | U | Lower priority: tested route ships no NVIDIA DLLs |
| PyTorch, DirectML, OpenVINO | Not read | U | |

## 4. Still outstanding

- Cutie weights terms; SEA-RAFT and RTMPose weights terms; SAMURAI, DAM4SAM, CascadePSP, SegRefiner, MiniMax-Remover, MODNet licences.
- Adobe Deep Image Matting dataset licence text (decides ViTMatte).
- Grounding DINO weights conflict.
- Hair-specific segmentation, motion-blur reconstruction, occlusion reasoning: no candidates yet.
- Training-data audit of every production-candidate (R-11).
- NVIDIA, PyTorch, DirectML, OpenVINO licence texts.

## Sources

- S1 SAM License (SAM 3), Meta, last updated 19 Nov 2025 — https://raw.githubusercontent.com/facebookresearch/sam3/main/LICENSE
- S2 S-Lab License 1.0, MatAnyone — https://raw.githubusercontent.com/pq-yang/MatAnyone/main/LICENSE
- S3 Cutie repository — https://github.com/hkchengrex/Cutie
- S4 ViTMatte repository — https://github.com/hustvl/ViTMatte ; HF card https://huggingface.co/hustvl/vitmatte-small-composition-1k ; dataset note on https://huggingface.co/LibreYOLO/LibreViTMattes-matte
- S5 DeepMind tapnet README (checkpoint licence) — https://github.com/google-deepmind/tapnet
- S6 SEA-RAFT — https://github.com/princeton-vl/SEA-RAFT ; RAFT mirror https://gitee.com/Bai-opus/RAFT
- S7 Hugging Face model cards: facebook/sam2.1-hiera-large, facebook/sam3, ZhengPeng7/BiRefNet, google/owlv2-base-patch16-ensemble, microsoft/Florence-2-large, IDEA-Research/grounding-dino-base, usyd-community/vitpose-base-simple, depth-anything/Depth-Anything-V2-Small-hf, facebook/cotracker3 (queried 2026-11-15)
- S8 Grounding DINO weights note — https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/open-vocabulary-detection-grounding-dino-florence-2-rtdetr-rfdetr
- S9 OpenMatte — https://github.com/hamdyelshiwy/openmatte
- S10 BackgroundMattingV2 — https://github.com/PeterL1n/BackgroundMattingV2
- S11 SAM2Long / EdgeTAM / SAMURAI — https://awesome.ecosyste.ms/projects/github.com%2FMark12Ding%2FSAM2Long ; https://huggingface.co/facebook/EdgeTAM/blob/refs%2Fpr%2F1/README.md ; https://github.com/yangchris11/samurai
- S12 ProPainter / DiffuEraser — https://huggingface.co/spaces/sczhou/ProPainter/commits/main/LICENSE ; https://www.sourcepulse.org/projects/2338674
- S13 RTMPose — https://github.com/Tau-J/rtmlib ; https://huggingface.co/qualcomm/RTMPose-Body2d
- S14 ONNX Runtime licence — https://raw.githubusercontent.com/microsoft/onnxruntime/main/LICENSE ; BiRefNet licence https://raw.githubusercontent.com/ZhengPeng7/BiRefNet/main/LICENSE
- S-EULA Foundry End User License Agreement, last updated March 2026 — https://learn.foundry.com/nuke/content/eula.html
