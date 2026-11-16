# Model Register

First issue 2026-11-15; **second issue 2026-11-15** adds rows M-11 to M-25 (see `docs/RESEARCH_2026-11-15_LICENCES_AND_MODELS.md`). Mostly desk research. **Measured so far: SAM 2.1 tiny and large only** (see M-01). Fields the master prompt (§7) requires but which are not yet established are listed as "not researched" or "not measured" rather than filled with estimates.

Classes:

- **Production-candidate**: licence appears to permit commercial use and redistribution. Still needs full licence-text review and training-data review.
- **Decision needed**: usable commercially but with conditions the owner must accept.
- **Research-only**: licence excludes commercial use or conflicts with a permissive project licence. Must stay out of the production set (§24).

| ID | Model | Task | Repository | Licence (as found) | Class | Evidence |
|---|---|---|---|---|---|---|
| M-01 | SAM 2 / SAM 2.1 (tiny, small, base+, large) | Promptable image and video segmentation | github.com/facebookresearch/sam2 | Apache-2.0 for code and checkpoints | Production-candidate | Repository README; **tiny and large downloaded, exported to ONNX and run in Nuke 17.1 NC on CUDA (`research/probes/2026-11-15_sam2/RESULTS.md`): encoder 65 ms (tiny) / 317 ms (large), click 6.7 ms, peak GPU 2.5 / 5.6 GB. Video tracking ported to ONNX + numpy (exact vs PyTorch); in Nuke ≈ 0.24 s/frame tiny, 0.45 s large; synthetic shot IoU 0.995 tiny / 0.987 large (`research/probes/2026-11-15_video/RESULTS.md`)** |
| M-02 | SAM 3 | Promptable segmentation with text/concept prompts, video tracking | github.com/facebookresearch/sam3 | SAM License (Meta, updated 19 Nov 2025). Royalty-free use, modification, redistribution; redistribution under the same agreement with a copy; restricted uses (trade controls, ITAR, military, nuclear, espionage, weapons); no reverse engineering; Meta may amend; terminates on IP suit against Meta. No copyleft on ST-ROTO code | Decision needed (OQ-07) | **Full licence text read** |
| M-03 | Cutie | Video object segmentation (mask propagation) | github.com/hkchengrex/Cutie | MIT (code). Bundled RITM GUI code follows RITM's own licence | Production-candidate, training-data review outstanding | Repository metadata and README |
| M-04 | BiRefNet | High-resolution dichotomous segmentation, per frame | github.com/ZhengPeng7/BiRefNet | MIT | Production-candidate | Model card; third-party reports. No temporal model, so per-frame shimmer is expected |
| M-05 | ViTMatte (S 25.8 M, B) | Trimap-based image matting | github.com/hustvl/ViTMatte | Code MIT; official HF weights Apache-2.0; **trained on Composition-1k (Adobe DIM dataset, reported non-commercial)** | Training-data review required (R-11) | HF card; repository; third-party dataset note |
| M-06 | MatAnyone / MatAnyone 2 | Target-assigned human video matting | github.com/pq-yang/MatAnyone, /MatAnyone2 | S-Lab License 1.0: "non-commercial purpose" only | Research-only | **Full licence text read** |
| M-07 | Robust Video Matting (RVM) | Human video matting, recurrent | github.com/PeterL1n/RobustVideoMatting | GPL-3.0 | Research-only if ST-ROTO takes a permissive licence | Repository metadata |
| M-08 | CoTracker3 | Dense point tracking | github.com/facebookresearch/co-tracker | CC-BY-NC-4.0 | Research-only | Hugging Face model card |
| M-09 | Depth Anything V2 Small | Monocular depth | github.com/DepthAnything/Depth-Anything-V2 | Apache-2.0 | Production-candidate | Repository README |
| M-10 | Depth Anything V2 Base / Large / Giant | Monocular depth | same | CC-BY-NC-4.0 per repository README. One third-party page claims Base and Large are Apache-2.0; the repository statement is treated as authoritative | Research-only | Repository README; conflict noted |

| M-11 | EdgeTAM | Efficient promptable video segmentation (SAM 2 family) | huggingface.co/facebook/EdgeTAM | Apache-2.0 | Production-candidate, verify | Secondary (HF card via search) |
| M-12 | TAPIR / BootsTAPIR / TAPNext | Point tracking | github.com/google-deepmind/tapnet | **Apache-2.0 for code and checkpoints** (README) | Production-candidate | Official README |
| M-13 | RAFT | Optical flow | github.com/princeton-vl/RAFT | BSD-3-Clause | Verify | Mirror only |
| M-14 | SEA-RAFT | Optical flow | github.com/princeton-vl/SEA-RAFT | Code BSD-3-Clause; weights not stated (re-checked 2026-11-16) | Not usable until weights terms known | Repository page |
| M-15 | SAM2Long | Long-term VOS on SAM 2 | github.com/Mark12Ding/SAM2Long | CC BY-NC 4.0 (own code) | Research-only | Secondary |
| M-16 | SAMURAI, DAM4SAM | Long-term tracking on SAM 2.1 weights | github.com/yangchris11/samurai | Not established | Not classified | – |
| M-17 | BackgroundMattingV2 | Matting with clean background plate | github.com/PeterL1n/BackgroundMattingV2 | MIT (relicensed to permit commercial use) | Candidate, locked-off shots only | Secondary |
| M-18 | VideoMaMa | Video matting | via OpenMatte table | CC BY-NC / Stability Community | Research-only | Secondary |
| M-19 | OWLv2 base | Open-vocabulary detection | google/owlv2-base-patch16-ensemble | Apache-2.0 | Production-candidate | HF card |
| M-20 | Florence-2 large | Vision-language grounding/captioning | microsoft/Florence-2-large | MIT | Production-candidate | HF card |
| M-21 | Grounding DINO base | Text-grounded detection | IDEA-Research/grounding-dino-base | Code Apache-2.0; **official weights: no licence stated**; trained on O365, GoldG, Cap4M (+COCO, OpenImage… for B) | **Resolved 2026-11-16: not in the production set** (weights terms not established) | Official README (T-030b) |
| M-22 | ViTPose base | Pose estimation | usyd-community/vitpose-base-simple | Apache-2.0 | Production-candidate | HF card |
| M-23 | RTMPose / RTMO | Pose estimation | open-mmlab/mmpose | Code Apache-2.0; weights not stated | Verify | Secondary |
| M-24 | ProPainter / DiffuEraser | Video inpainting | sczhou/ProPainter | S-Lab NC (DiffuEraser Apache but depends on ProPainter) | Research-only | Secondary |
| M-25 | CascadePSP, SegRefiner | Boundary refinement | hkchengrex/CascadePSP | Not established | Not classified | – |

## Enforcement (T-056)

The runtime loads only files listed in `models/manifests/<name>.exports.json` with matching size and SHA-256, for models whose `models/manifests/<name>.json` records a production licence (Apache-2.0, MIT, BSD), an owner approval and a pinned revision that matches the exports (`src/st_roto_ai/registry.py`). Re-run `tools/models/register_exports.py <name>` after any re-export.

## Known technical notes (from sources, not measured)

- SAM 2.1 checkpoint sizes: 38.9 M (tiny) to 224.4 M (large) parameters. Published speeds are on an A100 GPU and say nothing about an 8 GB laptop GPU.
- SAM 2 upstream recommends WSL for Windows installs; native Windows packaging is therefore a risk.
- MatAnyone 2 builds on Cutie; its licence does not transfer to Cutie.
- RVM publishes TorchScript and ONNX exports, which shows the architecture is exportable, but the licence still blocks it.

## Fields not yet established for any model

Original paper citation, maintainer status, weight format, VRAM and RAM requirement, supported runtimes after export, input/output formats, resolution and temporal limits, benchmark results, integration complexity.

## Categories from §7 with no candidate yet

Hair-specific segmentation, motion-blur reconstruction, occlusion reasoning (beyond VOS memory). No permissive video inpainting or general video matting model found.

## Gaps that matter most

1. **No commercially usable general video matting model has been identified.** MatAnyone family, VideoMaMa and RVM are licence-blocked; BackgroundMattingV2 needs a clean plate.
2. ~~No commercially usable point tracker~~ TAPIR/BootsTAPIR/TAPNext checkpoints are Apache-2.0 (M-12).
3. Training-data licences behind every "production-candidate" are unaudited. ViTMatte (Composition-1k) is the concrete case.
4. Measured runtime fact: ONNX models can run on the GPU inside Nuke 17.1 with onnxruntime-gpu 1.26.0 (`research/probes/2026-11-15_gpu_ort/RESULTS.md`).


## Added 2026-11-16 (T-030b / T-031b)

- M-03 Cutie: weights licence **not stated** on the repository (re-checked); not usable until known.
- M-26 Netflix VOID (video object removal, CogVideoX-based): reported Apache-2.0 by secondary sources — verify primary repository and base-model licence.
- Hair-specific, motion-blur reconstruction, occlusion reasoning: no permissive candidates (see `docs/RESEARCH_2026-11-16_LICENCES_AND_CATEGORIES.md`).
