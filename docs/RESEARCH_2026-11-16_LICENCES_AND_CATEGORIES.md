# Remaining licence texts (T-030b) and model categories (T-031b) — 2026-11-16

Evidence: **V-text** licence text read · **V-page** official repository/page · **S** secondary · **–** not established.

## Runtimes and SDKs (T-030b)

| Item | Licence | Key terms for ST-ROTO | Evidence |
|---|---|---|---|
| PyTorch / libtorch | BSD-3-Clause style (Facebook, Idiap, DeepMind, NEC, NYU…) | keep notices; no endorsement by those names | V-text |
| DirectML | MIT (Microsoft) | the MIT text covers the repository; redistributable DLL terms not stated there | V-text |
| OpenVINO | Apache-2.0 | permissive, NOTICE | V-text |
| NVIDIA CUDA Toolkit EULA | proprietary | Attachment A lists redistributables (cudart, cuBLAS/cuBLASLt, cuFFT, …) **inside an application with material added functionality, accessed only by it** (§1.1.1(3), §1.1.2(1–2)); no standalone redistribution (§1.2.2); **§1.2.5: may not be used "in any manner that would cause it to become subject to an open source software license"**; distribution terms must stay consistent with the EULA (§1.1.2(5)) | V-text (summarised by the fetch tool; clause numbers quoted) |
| Adobe Deep Image Matting dataset | terms only on request from Adobe | not obtainable without a request | V-page (T-031 matting research) |

**Consequence.** ST-ROTO keeps reusing the CUDA/cuDNN DLLs that Nuke already ships (T-011c) and does not redistribute NVIDIA files; an installer that would bundle them needs the owner's legal review of §1.2.5 against Apache-2.0 distribution (question for NVIDIA: nvidia-compute-license-questions@nvidia.com).

## Model weights (T-030b)

| Model | Code | Weights | Training data | Class |
|---|---|---|---|---|
| Cutie (VOS) | MIT (RITM GUI part: RITM licence) | **not stated** | not stated on the README | not usable until the weights' terms are known |
| SEA-RAFT (optical flow) | BSD-3-Clause | **not stated** (Drive / HF links) | FlyingChairs/Things, Sintel, KITTI, HD1K, TartanAir, Spring (general list) | not usable until known |
| RTMPose / RTMO (pose) | Apache-2.0 (mmpose) | model cards point to mmpose's LICENSE (S) | 7 public pose datasets incl. COCO | verify each dataset's terms |
| **Grounding DINO** (conflict from 2026-11-15) | Apache-2.0 (V-page) | **not stated** on the official page | T: O365, GoldG, Cap4M; B: + COCO, OpenImage, ODinW-35, RefCOCO | **Resolved: weights licence not established → not in the production set**; the "Apache-2.0 on the HF card" refers to a conversion, not a grant by the authors |

## Missing categories (T-031b)

| Category | Finding | Evidence |
|---|---|---|
| Hair-specific segmentation/matting | No dedicated permissive model found; closest: BiRefNet-HR-matting (MIT weights, research training data, see matting research) | S |
| Motion-blur reconstruction / blur-aware matting | No permissive model found (VideoMaMa: CC BY-NC code, Stability Community weights; BSSTNet/TSRN: licence not shown). ST-ROTO covers blur with Nuke's own Roto motion blur (T-074) and model-free soft edges (blur edges 0.35× error, T-069) | S |
| Occlusion reasoning beyond VOS memory | No new permissive candidate (SAM2Long CC BY-NC). ST-ROTO: SAM 2.1 memory + review flags (lost/check) + split-object parts (T-049) | — |
| Permissive video inpainting | **Netflix VOID** (CogVideoX-based, ~5B, object + interaction removal) reported as Apache-2.0 by several secondary sources — **to verify on the primary repository and its base model's licence**; Wan VACE / Wan2.2 listed as Apache-2.0 (S); ProPainter NC; LaMa/MI-GAN weights permissive but trained on Places2 (NC terms) | S |

All of these stay out of the production set until verified (§24); none was downloaded.

## Sources

PyTorch https://raw.githubusercontent.com/pytorch/pytorch/main/LICENSE · DirectML https://raw.githubusercontent.com/microsoft/DirectML/master/LICENSE · OpenVINO https://raw.githubusercontent.com/openvinotoolkit/openvino/master/LICENSE · CUDA EULA https://docs.nvidia.com/cuda/eula/index.html · Cutie https://github.com/hkchengrex/Cutie · SEA-RAFT https://github.com/princeton-vl/SEA-RAFT · RTMPose https://github.com/Tau-J/rtmlib , https://huggingface.co/qualcomm/RTMPose_Body2d · Grounding DINO https://github.com/IDEA-Research/GroundingDINO · VOID https://try.wideframe.com/blog/netflix-void-open-source-physics-aware-video-inpainting/ , https://docs.comfy.org/tutorials/utility/void-video-inpainting · Wan VACE (issue list) https://github.com/dlopezkluever/Aiuteur/issues/8 · Places2 caution https://dev.to/phpboyscout/the-weights-were-mit-the-training-data-wasnt-206d · VideoMaMa https://studio.aifilms.ai/blog/videomama-open-source-mask-guided-video-matting
