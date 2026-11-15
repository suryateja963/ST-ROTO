# libtorch bundled with Nuke 17.1v3 (T-038) — 2026-11-16

Method: the DLLs carry no Windows version resource, so embedded strings were scanned (`find_versions.py`, `context.py`, output `result.json`).

| Item | Finding | Evidence |
|---|---|---|
| libtorch | **2.7.1** | `torch_cpu.dll`: the literal `2.7.1` stored next to the symbol `TORCH_VERSION`; `torch_cuda.dll`: `2.7.1` next to `PT_VERSION validation: expect`. The only version-like string of that form in either DLL. |
| torchvision | present (`torchvision.dll`, 8.9 MB) | version string not identified (one `2.4.6` hit is not adjacent to a version symbol: not claimed) |
| CUDA kernels | `sm_120` (Blackwell, 440 hits) plus older archs 50–86 | consistent with PyTorch ≥ 2.7 (first release with sm_120) |
| CUDA runtime | 12.8 (`cudart64_12.dll` file version 6.14.11.12080) | Windows version resource |
| cuDNN | 9.7.1.26 | Windows version resource |
| Compiler | MSVC, Visual Studio 2022 Professional | path string in torch_cpu.dll |

Consequences: TorchScript files for Nuke's Inference/CatFileCreator route (route A, T-011a) should be produced with PyTorch 2.7.x (the project venv has torch 2.15 CPU; TorchScript serialisation from a much newer torch is not guaranteed loadable by 2.7.1). ONNX Runtime 1.26 (CUDA 12) shares the same CUDA 12.8 / cuDNN 9.7 DLLs (T-011c).
