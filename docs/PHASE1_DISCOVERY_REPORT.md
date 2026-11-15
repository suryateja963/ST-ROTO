# Phase 1 Discovery and Feasibility Report

Date: 2026-11-15. Scope: research half of Phase 1. The machine audit (master prompt §31 steps 1–2) is **not done**; see section 6.

Evidence labels used throughout the repository:

- **[V]** verified this session against the cited source.
- **[U]** unverified: from general knowledge or inference, must be checked before it is relied on.

## 1. Headline findings

1. **The development machine's Nuke edition cannot run the product as specified.** Nuke Non-commercial loads only plug-ins shipped with Nuke; OFX and NDK-compiled plug-ins are excluded [V, S1, S4]. Nuke Indie also does not load custom C++ nodes [V, S2, S3].
2. **Python in Non-commercial and Indie is capped at 10 node retrievals per script or project** [V, S2]. `nuke.allNodes()` returns only the first 10 nodes [V, S4]. A multi-node ecosystem with an object manager cannot work under that cap.
3. **Commercial Nuke cannot open Non-commercial scripts** [V, S4], so test projects made on the development machine are not reusable for commercial-edition testing.
4. **GPU:** Nuke 17.0 requires CUDA 12.8 or later [V, S5]. RTX 50-series (Blackwell) support arrived in PyTorch 2.7.0 with CUDA 12.8 [V, S6]. The RTX 5060 should therefore be usable by Nuke 17's own ML stack. Not tested on the machine.
5. **A route to in-process inference already ships with Nuke:** TorchScript models converted to `.cat` files by CatFileCreator and run by the Inference node [V, S7]. It suits image-to-image models. It does not by itself provide interactive prompting or stateful video memory [U].
6. **Native roto export is reachable from Python.** `nuke.rotopaint` exposes Shape, ShapeControlPoint, Layer, Stroke and animated control points on the `curves` knob, including feather curves [V, S8]. This supports the §6 requirement that exported shapes stay editable without ST-ROTO.
7. **Several high-profile models are not usable in a production model set.** MatAnyone and MatAnyone 2 are under NTU S-Lab License 1.0 [V, S12]; CoTracker3 is CC-BY-NC-4.0 [V, S13]; Robust Video Matting code is GPL-3.0 [V, S14]. See `MODEL_REGISTER.md`.

## 2. Edition feasibility

| Edition | C++ (NDK) nodes | Python | Consequence for ST-ROTO |
|---|---|---|---|
| Nuke / NukeX / Nuke Studio (commercial) | Supported [V, S2] | Full [V, S2] | Only editions that can run the full design |
| Nuke Indie | Not supported [V, S2, S3] | 10-node cap [V, S2] | At most a reduced Python/gizmo subset |
| Nuke Non-commercial | Not supported [V, S1, S2] | 10-node cap [V, S2] | At most a reduced Python/gizmo subset |

Foundry states that developers building tools for the wider community may qualify for a developer licence (contact info@foundry.com) [V, S3]. That is the recommended route; see OQ-01.

## 3. Build environment facts

- Windows NDK plug-ins must be built with Visual Studio 2022 (Nuke 16.0 NDK guide) [V, S9]. Nuke 17 page not checked [U].
- Documented interpreter for importing Nuke as a module: Python 3.11.7 [V, S10]. **Correction: installed Nuke 17.1v3 embeds Python 3.11.11 (`docs/MACHINE_AUDIT_2026-11-15.md`).**
- Nuke 17.0 aligns with VFX Reference Platform CY2025 [V, S11].
- The NDK exports C++ symbols, so plug-ins generally need recompiling per major.minor Nuke release [V, S15]. Supporting Nuke 13 to 17 means one binary build per supported release line.
- Nuke 13 uses an older Python and Qt binding than Nuke 16/17 [U]. Exact versions per release must be tabulated before the UI layer is designed.

## 4. In-process inference: candidate routes

| Route | In-process | Works in restricted editions | Fit | Open issues |
|---|---|---|---|---|
| A. Nuke Inference node + `.cat` (TorchScript) | Yes [V, S7] | Possibly, since it ships with Nuke [U] | Image-to-image models: matting, depth, flow | No interactive prompts; model must be TorchScript-compatible; `.cat` files from Indie are edition-locked [V, S2] |
| B. NDK C++ node linking ONNX Runtime | Yes | No [V, S1, S2] | Everything, including stateful video models | DLL version conflicts with Nuke's own CUDA/libtorch [U]; one build per Nuke release line [V, S15] |
| C. Python package (onnxruntime or torch) imported in Nuke's interpreter | Yes | Import itself is not blocked by the node cap [U] | Prototyping, UI-driven tools | DLL conflicts [U]; pixel access from Python is slow; Python ABI differs per Nuke release |
| D. NDK node linking Nuke's bundled libtorch | Yes | No | Avoids shipping a second CUDA stack | Bundled libtorch is not a documented public SDK [U] |

No route is selected. Selecting one is a Phase 2 decision and needs prototypes that can only run on the development machine.

ONNX Runtime is MIT-licensed and offers CUDA, TensorRT, DirectML and OpenVINO execution providers [V, S16]. DirectML and OpenVINO are the documented choices for AMD and Intel GPUs on Windows [V, S16]. CUDA and cuDNN runtime DLLs are NVIDIA-licensed and their redistribution terms must be reviewed before the installer bundles them [V, S17].

## 5. Feasibility on the stated hardware

8 GB VRAM and 16 GB RAM are tight. No model has been measured on this machine. Every memory figure in `MODEL_REGISTER.md` is marked "not measured". Tiling, half precision and model unloading between stages will be required [U]; the degree is unknown until measured.

## 6. What was not done, and why

| Step (§31) | State | Reason |
|---|---|---|
| 1. Inspect workspace, Git, repository | Partly done | `D:\ST-ROTO` connected and found empty. No Git repository. GitHub account/repository situation not inspected |
| 2. Inspect Python, compiler, GPU, CUDA, Nuke install | Done 2026-11-15 | See `docs/MACHINE_AUDIT_2026-11-15.md` |
| 3. Nuke API and edition limits | Done for edition limits; API audit partial | |
| 4–5. Requirements register, separation of decisions | Done, first issue | |
| 6. In-process inference research | Desk research done; no prototype | Needs the machine and a licence that loads plug-ins |
| 7. Models and licences | Partial: 10 candidates checked | Many §7 categories not yet researched (pose, detection, inpainting, hair-specific, motion-blur) |
| 8. Architecture proposal | Not done | Blocked on OQ-01 |
| Competitor research (§21) | Not done | |

## 7. Honest scope statement

The master prompt describes a product on the scale of commercial roto packages built by teams over years. Phase 1 desk research does not reduce that. No timeline is offered because none could be supported by evidence.

## Sources

- S1 Foundry support, Q: Nuke Non-commercial limitations — https://support.foundry.com/hc/en-us/articles/360001227130
- S2 Foundry, About Nuke Indie (edition comparison table) — https://learn.foundry.com/NUKE/content/getting_started/meet_nuke/about_indie.html
- S3 Foundry, Nuke Indie FAQ — https://www.foundry.com/products/nuke/nuke-indie/faq
- S4 MCV, restrictions list supplied by Foundry — https://www.mcvuk.com/what-nukes-non-commercial-licence-means-for-game-developers/
- S5 Nuke 17.0v4 release notes — https://learn.foundry.com/nuke/content/release_notes/17.0/nuke_17.0v4_releasenotes.html
- S6 PyTorch forum, Blackwell support — https://discuss.pytorch.org/t/rtx-5050-sm-120-support-timeline-when-in-stable-pytorch/224288
- S7 Foundry, Importing pre-trained PyTorch models — https://learn.foundry.com/nuke/13.2/content/comp_environment/air_tools/cfc-intro.html
- S8 Foundry, nuke.rotopaint Python reference — https://learn.foundry.com/nuke/developers/140/pythondevguide/_autosummary/nuke.rotopaint.Shape.html
- S9 NDK Developer Guide 16.0, Windows — https://learn.foundry.com/nuke/developers/160/ndkdevguide/appendixa/windows.html
- S10 Foundry, Nuke as a Python module — https://modosdk.foundry.com/nuke/content/comp_environment/script_editor/nuke_python_module.html
- S11 CG Channel, Nuke 17.0 — https://www.cgchannel.com/?p=171810
- S12 MatAnyone repository licence statement — https://github.com/pq-yang/MatAnyone
- S13 CoTracker3 model card — https://huggingface.co/facebook/cotracker3
- S14 Robust Video Matting repository — https://github.com/PeterL1n/RobustVideoMatting
- S15 Foundry, information for developers — https://thefoundry.co.uk/support/developers
- S16 ONNX Runtime execution providers — https://onnxruntime.ai/docs/execution-providers/
- S17 SeasonONNX package notes on NVIDIA redistribution — https://www.nuget.org/packages/SeasonONNX
