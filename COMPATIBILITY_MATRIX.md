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
