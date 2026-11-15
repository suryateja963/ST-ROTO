# Probe results — GPU use of the Inference node, ONNX Runtime inside Nuke

Date 2026-11-15 · Machine: RTX 5060 Laptop 8 GB, driver 621.24 · Nuke 17.1v3 **Non-commercial**, headless (`-t`).
All figures are single runs on one machine. They are evidence of *feasibility*, not benchmarks.

## How to reproduce

```powershell
# 1. project Python 3.11 venv (inside D:\ST-ROTO)
$env:UV_PYTHON_INSTALL_DIR="D:\ST-ROTO\.tools\uv-python"; $env:UV_CACHE_DIR="D:\ST-ROTO\.tools\uv-cache"
uv python install 3.11 ; uv venv D:\ST-ROTO\.venv --python 3.11
uv pip install --python D:\ST-ROTO\.venv\Scripts\python.exe -r requirements-venv.txt
# 2. packages Nuke imports (cp311, appended to Nuke's sys.path by the probe)
uv pip install --python D:\ST-ROTO\.venv\Scripts\python.exe --target D:\ST-ROTO\.tools\nuke-py311 -r requirements-nuke-py311.txt
# 3. synthetic model (random weights, nothing downloaded)
D:\ST-ROTO\.venv\Scripts\python.exe make_test_model.py
# 4. probes
Nuke17.1.exe --nc        -t probe_gpu_ort.py inf_only_cpu
Nuke17.1.exe --nc --gpu  -t probe_gpu_ort.py inf_only_gpu
Nuke17.1.exe --nc --gpu  -t probe_gpu_ort.py inf_first
Nuke17.1.exe --nc --gpu  -t probe_gpu_ort.py ort_first
```

Raw output: `result_*.json`, `log_*.txt`, `err_*.txt`.

**Evidence-handling note.** The four `err_*.txt` files were accidentally overwritten with empty content by a failed redaction command. Three had identical content (one Git blob), which was recovered from Git's object store and restored, with the Windows username redacted to `<user>`. `err_inf_only_cpu.txt` is empty. It is assumed, not verified, to have been empty originally: it was the only one that did not contain the user path. The stderr logs from the earlier onnxruntime-gpu 1.32.0 runs were deleted before re-running; their key error line is quoted in section 2a.

## 1. Does the Inference node use the GPU?

Model: Foundry `FnHumanMattingSmall.cat`. Input: 1920×1080 animated Noise over CheckerBoard (new pixels every frame, cache cleared).

| Launch | Per frame (5 frames) | GPU util peak | GPU memory | Verdict |
|---|---|---|---|---|
| `-t` (no `--gpu`) | 2.741 s | 34 % (desktop baseline) | no rise | **CPU** |
| `--gpu -t` | 0.300 s / 0.248 s / 0.259 s (3 processes) | 100 % | +~1.8 GB peak (1.06 → 2.84 GB) | **GPU** |

- **Terminal mode disables the GPU unless Nuke is started with `--gpu`** (Nuke `--help`: "enables GPU usage when in terminal mode"). This explains the audit's earlier "GPU not demonstrated" result (risk R-22, now closed).
- `useGPUIfAvailable` reads `True` in both cases and is **read-only from Python** in terminal mode.
- The first GPU frame of the first `--gpu` process took 16.8 s; later processes took 1.2 s. **Explained by Nuke's own message** (in `err_inf_only_gpu.txt`): "The AIR plug-ins need to compile CUDA kernels in order to run on this GPU. This process will only be necessary once and should take about half an hour." Compiled kernels are cached in `%APPDATA%\NVIDIA\NukeComputeCache` (~2 GB). This is Nuke behaviour, outside `D:\ST-ROTO`; ST-ROTO's installer/docs must warn about it.
- GPU vs CPU speed-up for this model at 1080p: ≈ 9–11×.

## 2. Can ONNX Runtime run inside Nuke next to Nuke's own CUDA stack?

Model: `test_conv.onnx` (synthetic: 8× 3×3 conv 64 ch + ReLU, 1×1 conv, sigmoid; random weights). Input 1×3×1080×1920 float32.

### 2a. Version compatibility (decisive)

Nuke 17.1v3 ships CUDA 12.8 runtime + cuBLAS 12 + cuFFT 11 + cuDNN 9.7.1. Imports of `onnxruntime_providers_cuda.dll` read with `check_ort_cuda_deps.py`:

| onnxruntime-gpu (PyPI, cp311 win) | CUDA libraries required | Loads inside Nuke 17.1 |
|---|---|---|
| 1.23.2, 1.25.1, **1.26.0** | cublas64_12, cublasLt64_12, cudart64_12, cudnn64_9, cufft64_11 | 1.26.0 tested: **yes** |
| 1.27.0, 1.29.0, 1.31.1, 1.32.0 | cublas64_13, cublasLt64_13, cufft64_12 (CUDA 13) | 1.32.0 tested: **no**, error 126 "cublasLt64_13.dll missing", silent fall-back to CPU |

**→ onnxruntime-gpu 1.26.0 is the newest PyPI build that matches Nuke 17.1's CUDA 12 stack.** Other Nuke versions ship other CUDA versions, so the runtime has to be pinned per Nuke release line (adds to R-09).

### 2b. Runtime results with 1.26.0

| Launch / order | Active providers | Per run | GPU util | GPU memory | max |CUDA−CPU| |
|---|---|---|---|---|---|
| `-t`, ORT before/after Inference | CUDA, CPU | 0.200–0.212 s | 100 % | +~1.0 GB | 3.2e-5 |
| `--gpu -t`, Inference then ORT | CUDA, CPU | 0.219 s | — | — | 3.2e-5 |
| `--gpu -t`, ORT then Inference | CUDA, CPU | 0.195 s | 100 % | — | 3.2e-5 |
| CPU provider only (reference) | CPU | 2.63–2.73 s | — | — | — |

- ONNX Runtime CUDA does **not** depend on Nuke's `--gpu` flag (it talks to CUDA directly).
- DLLs mapped after ORT ran: `cudart64_12`, `cublas64_12`, `cublasLt64_12`, `cudnn64_9`, `nvrtc64_120_0` — **all from `C:\Program Files\Nuke17.1v3`**. No second CUDA stack was loaded; ORT reused Nuke's.
- ORT CUDA and the Inference node (libtorch CUDA) ran in the same process, in both orders, with no crash or error.
- CUDA vs CPU speed-up ≈ 13×.

## 3. What this establishes, and what it does not

Established (this machine, Nuke 17.1v3 NC):
- Route A (Inference node + `.cat`) runs on the GPU, in-process, when GPU is enabled.
- Route C (Python + ONNX Runtime CUDA) runs in-process on the GPU **without** a commercial licence and without shipping CUDA/cuDNN, provided the ORT build matches Nuke's CUDA major version.

Not established:
- Behaviour in the interactive GUI (threading, viewer responsiveness, long sessions).
- Memory behaviour with real models (SAM 2.1 etc.) at 2K–8K, and with both runtimes resident for a long time.
- Pixel transfer cost between Nuke images and numpy (Python-side pixel access under the 10-node cap).
- Other Nuke versions, other GPUs, CPU-only machines.
- Licence terms for redistributing ORT alongside Nuke (ORT is MIT; we would ship no NVIDIA DLLs on this route).
