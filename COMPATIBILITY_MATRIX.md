# Compatibility Matrix

First issue, 2026-11-15. **Nothing has been tested. No ST-ROTO code exists.** The only entries other than "Not yet tested" are those fixed by Foundry's published edition restrictions.

Status vocabulary (§5.1): Fully supported · Supported with limitations · Experimental · Unsupported · Not yet tested.

## By edition (applies to every Nuke version)

| Edition | C++ node family | Python-only components | Basis |
|---|---|---|---|
| Nuke | Not yet tested | Not yet tested | |
| NukeX | Not yet tested | Not yet tested | |
| Nuke Studio | Not yet tested | Not yet tested | |
| Nuke Indie | Unsupported (by Foundry restriction) | Not yet tested; limited by the 10-node Python cap | Foundry edition table |
| Nuke Non-commercial | Unsupported (by Foundry restriction) | Not yet tested; limited by the 10-node Python cap | Foundry support article and edition table |

## By version (commercial editions)

| Nuke | Status | Known build facts |
|---|---|---|
| 13.x | Not yet tested | Python and Qt versions to be tabulated |
| 14.x | Not yet tested | NDK guide names Visual Studio 2019 |
| 15.x | Not yet tested | |
| 16.x | Not yet tested | NDK guide names Visual Studio 2022 |
| 17.0 | Not yet tested | CUDA 12.8 or later; VFX Reference Platform CY2025; Python 3.11.7 documented |
| 17.1 | Not yet tested (ST-ROTO). Installed on dev machine as 17.1v3 Non-commercial | Python 3.11.11, PySide6 6.5.3 / Qt 6, CUDA runtime 12.8, cuDNN 9.7.1, bundled libtorch, MSVC v143, ABI `DDImage_ABI_17_1_1` [M] |

## Runtime facts measured on Nuke 17.1v3 (not ST-ROTO support claims)

| Item | Result |
|---|---|
| Inference node GPU in terminal mode | Only with `--gpu` |
| onnxruntime-gpu 1.26.0 CUDA EP in-process | Works; reuses Nuke's CUDA 12 DLLs |
| onnxruntime-gpu 1.27+ (CUDA 13) | Fails to load CUDA EP, silent CPU fallback |

## Hardware

| Target | Status |
|---|---|
| NVIDIA RTX 5060 Laptop, 8 GB (development machine) | Not yet tested (driver 621.24, CUDA UMD 13.5 measured) |
| Other NVIDIA | Not yet tested |
| AMD GPU | Not yet tested |
| Intel GPU | Not yet tested |
| CPU only | Not yet tested |


## Measured 2026-11-16 (T-038)

Nuke 17.1v3 (Windows): libtorch **2.7.1**, CUDA runtime 12.8, cuDNN 9.7.1, CUDA kernels incl. sm_120. Evidence: `research/probes/2026-11-16_nuke_libtorch/RESULTS.md`.

## Nuke 13 → 17.1: Python, Qt, compiler, CUDA (T-032, 2026-11-16)

Sources: Foundry release notes (v1 of each line) and NDK developer guides; VFX Reference Platform table; **17.1 measured on this machine** (Python, PySide, CUDA runtime, cuDNN, libtorch: T-010, T-038). "–" = not stated by the source.

| Nuke | VFX platform | Python | Qt / Python binding | OCIO | OpenEXR | NDK compiler (Windows) | GPU / CUDA (driver) | libtorch |
|---|---|---|---|---|---|---|---|---|
| 13.0 | CY2020 (Python 3.7) | **3.7.7** | PySide2 5.12.6 (patched) | – | 2.4.2 | **VS 2017** | CUDA 10.1+ drivers (≥ 418.96 Win), compute ≥ 3.0 | – |
| 14.0 | CY2022 | **3.9.1** | Qt 5.15.2, PySide2 5.15 | 2.1.2 | 3.1.4 | **VS 2019** | – (GPU section exists, versions not quoted) | – |
| 15.0 | CY2023 | 3.10 (platform) | Qt/PySide2 5.15 (platform) | 2.2 | – | – | CUDA 11.8+ (≥ 522.06 Win) | – |
| 16.0 | CY2024 | **3.11** | **Qt 6.5, PySide6 6.5** | 2.3 | 3.2 | **VS 2022** | CUDA 11.8+ (≥ 522.06 Win) | – |
| 17.0 | CY2025 | 3.11 (platform) | Qt/PySide6 6.5 (platform) | 2.4.2 | 3.3.6 | – | CUDA 11.8+; cuDNN ≥ 9.7.0 | – |
| **17.1v3 (measured)** | CY2025 | **3.11.11** | **PySide6 6.5.3** | 2.4.2 (PyOpenColorIO) | – | – | CUDA runtime **12.8**, cuDNN **9.7.1** | **2.7.1** |

**Consequences for ST-ROTO.**
- Two Qt bindings (PySide2 for 13–15, PySide6 for 16+): `st_roto_nuke.panel` already falls back PySide6 → PySide2; other UI code must keep doing so.
- Python 3.7 floor: the core stays 3.7-compatible (CI runs the suite on real 3.7, D-017).
- NDK C++ (route B/D, T-011b) needs one build per line with the matching compiler (VS 2017 / 2019 / 2022) and CMake (from 12.1) — part of OQ-14.
- AI runtime: ONNX Runtime GPU builds must match each line's bundled CUDA/cuDNN (17.1: onnxruntime-gpu 1.26.0, CUDA 12; R-09). For 13.x (CUDA 10.1-era drivers) a GPU-capable ORT build is unlikely → OQ-20 (CPU-only AI on Nuke 13?) stays open until measured on a Nuke 13 install.
- Route A (Inference/.cat, T-011a) needs TorchScript made with each line's libtorch (17.1: 2.7.1); earlier lines' libtorch versions are not stated by Foundry and must be measured per install (method: `research/probes/2026-11-16_nuke_libtorch`).

Sources: https://learn.foundry.com/nuke/17.1/content/release_notes/13.0/nuke_13.0v1_releasenotes.html · https://learn.foundry.com/nuke/17.1/content/release_notes/14.0/nuke_14.0v1_releasenotes.html · https://learn.foundry.com/nuke/17.1/content/release_notes/15.0/nuke_15.0v1_releasenotes.html · https://learn.foundry.com/nuke/17.1/content/release_notes/16.0/nuke_16.0v1_releasenotes.html · https://learn.foundry.com/nuke/17.1/content/release_notes/17.0/nuke_17.0v1_releasenotes.html · https://learn.foundry.com/nuke/developers/130/ndkdevguide/appendixa/windows.html · https://learn.foundry.com/nuke/developers/140/ndkdevguide/appendixa/windows.html · https://learn.foundry.com/nuke/developers/160/ndkdevguide/appendixa/windows.html · https://vfxplatform.com/platform_history.html
