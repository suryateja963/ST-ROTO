# Machine and Workspace Audit — 2026-11-15

Master prompt §31 steps 1–2 (task T-010). Run locally by Claude Code in VS Code on the development machine. Raw evidence: `research/probes/2026-11-15_machine_audit/`.

Labels: **[M]** measured on this machine this session · **[V]** verified from a cited source · **[U]** unverified.

## 1. Workspace (`D:\ST-ROTO`)

| Item | Finding |
|---|---|
| Git | Not a Git repository [M]. Git 2.56.0 installed [M] |
| GitHub CLI (`gh`) | Not installed [M]. GitHub account/repository situation still unknown (OQ-10) |
| Contents before this session | 11 Markdown registers + `docs/MASTER_PROMPT.md` (1,590 lines, 32 sections, matches the owner's specification) + `docs/PHASE1_DISCOVERY_REPORT.md`. All written 2026-11-15 by an earlier cloud session with no terminal. No code |
| Consistency of existing documents | Honest and internally consistent. Corrections from this audit: Nuke 17.1v3 ships Python **3.11.11**, not 3.11.7 (the 3.11.7 figure is from 17.0 docs); risk R-18 (no terminal) is now closed |
| Disk | D: 397.6 GB free; C: 404.7 GB free [M] |

## 2. Hardware [M]

| Component | Measured |
|---|---|
| CPU | Intel Core i7-13700HX, 16 cores / 24 threads |
| RAM | 15.7 GB usable |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, WDDM; ~0.7 GB in use by desktop apps at idle |
| Driver | 621.24, CUDA UMD 13.5 |

## 3. Development toolchain [M]

| Tool | State | Consequence |
|---|---|---|
| System Python | 3.12.10 (`D:\softwares\Python312`); `uv` at `D:\softwares\uv` | **Not ABI-compatible with Nuke's 3.11.** Any compiled Python package used inside Nuke must be built for cp311 |
| Visual Studio / MSVC (`cl`) | **Not installed** (no `vswhere`, no VS directory) | NDK C++ plug-ins cannot be compiled. Nuke 17.1 is built with MSVC v143 (`vc143` boost DLLs, `MSC v.1935`) → VS 2022 Build Tools needed [U for exact minor] |
| CMake, Ninja | Not installed | Needed for the NDK build (Nuke ships `cmake/` config) |
| CUDA Toolkit (`nvcc`) | Not installed, `CUDA_PATH` unset | Only needed if custom CUDA kernels are written |

## 4. Nuke installation [M]

| Item | Finding |
|---|---|
| Install | `C:\Program Files\Nuke17.1v3` — Nuke **17.1v3**, built 2 Nov 2026 |
| Edition | **Non-commercial** (`nuke.env['nc'] = True`, banner "Non-commercial mode active") |
| `~/.nuke` | Does not exist; `NUKE_PATH` unset — clean, no existing plug-ins to conflict with |
| Embedded Python | 3.11.11, MSC v.1935, 64-bit |
| Qt / bindings | Qt 6, PySide6 6.5.3 |
| Python packages shipped | No numpy, no torch, no onnxruntime. Has PySide6, OpenColorIO, OpenTimelineIO, psutil, protobuf, zmq, pip |
| Bundled ML stack | libtorch (`torch_cpu.dll`, `torch_cuda.dll` 1.3 GB, `c10`, `torchvision`), CUDA runtime 12.8 (`cudart64_12` 6.14.11.12080), cuDNN **9.7.1**, cuBLAS 12, NVRTC 12.8, oneMKL. libtorch version not determined [U] |
| NDK | Headers in `include/` (DDImage, ndk, Blink, fdk, OFX); `DDImage.lib`, `Ndk.lib`; ABI tag `DDImage_ABI_17_1_1` |
| Built-in AI models | `plugins/air/`: FnHumanMatting S/M/L, FnED S/M/L, FnDeblurLarge, FnUpscaleLarge, FnUpscaleACESLarge (`.cat`). Foundry proprietary; usable only inside Nuke under the EULA |

## 5. Live tests inside Nuke Non-commercial [M]

Run with `Nuke17.1.exe --nc -t <script>` (headless). Scripts and logs in `research/probes/2026-11-15_machine_audit/`.

| Test | Result |
|---|---|
| Headless Python (`-t`) in Non-commercial | **Works.** Automated in-Nuke tests are possible on this machine |
| 10-node Python cap | **Confirmed.** After 10 Node objects, every further `nuke.nodes.X()` / `createNode` / `allNodes` access returns `None` with "Non-Commercial mode 10-node limit … reached". Nodes *created* from Python count towards it |
| Create native Roto shape via `nuke.rotopaint` (Shape + 3 ShapeControlPoints, named) | **Works** |
| Inference node + `FnHumanMattingSmall.cat` on a 1K CheckerBoard → EXR write | **Works.** Frame 1: 4.56 s (includes model load); frame 2: 0.06 s, but the input was static so this is very likely cache, not inference speed |
| GPU actually used by the Inference node | **Not demonstrated.** System GPU memory sampled every 0.5 s never rose above idle (peak 670 MiB). Either inference ran on CPU in `-t` mode or the sample missed it. To re-test with `useGPUIfAvailable` set explicitly and per-process memory |
| `import numpy / torch / onnxruntime` in Nuke | Not available (not shipped) |

## 6. What this means for the open decisions

1. **R-01/R-02 are now measured facts, not just documentation.** A Python + gizmo design under Non-commercial is limited to 10 Python-accessible nodes per session — this rules out any Python-driven multi-node tool that touches more than a handful of nodes.
2. **Route A (Inference node + `.cat`) runs in-process on this machine today.** It is the only AI route testable without a commercial/developer licence.
3. **Route C (Python packages inside Nuke) is not blocked by the edition** but requires cp311 wheels (onnxruntime-gpu / torch) installed into a project-local folder added to Nuke's path, and has a DLL-conflict risk with Nuke's own CUDA 12.8 / cuDNN 9.7.1 (R-05). Testable on this machine.
4. **Route B/D (NDK C++)** need VS 2022 Build Tools + CMake installed *and* a licence that loads plug-ins (OQ-01).
5. Nuke already ships CUDA 12.8 + cuDNN 9.7.1 — an ONNX Runtime CUDA build matched to those versions could reuse Nuke's DLLs instead of loading a second stack [U, must be prototyped].

## 7. Not done in this audit

- libtorch version shipped with Nuke.
- GPU use by the Inference node (see §5).
- GitHub account inspection (`gh` not installed; OQ-10).
- Any other Nuke versions (only 17.1v3 is installed).
