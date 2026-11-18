# DirectML: AMD / Intel / any DirectX 12 GPU (T-116, REQ-020) — 2026-11-18

Owner approved the DirectML ONNX Runtime package (2026-11-18). Package: **onnxruntime-directml 1.24.4**
(cp311 win_amd64, MIT, the last DirectML release on PyPI; wheel SHA-256
96642a787e5a6f33bf043521c0f06eb1eb663f6b830e5862a2026d03f9c90543, checked against PyPI), unpacked unchanged
into `.tools/nuke-py311-dml` (onnxruntime + DirectML.dll; its other dependencies are the ones already in
`.tools/nuke-py311`). Both builds are the Python package `onnxruntime`, so one is chosen per Nuke session
(`st_roto.runtime_choice`: auto = CUDA if the NVIDIA driver is installed, else DirectML; `ST_ROTO_RUNTIME` forces one).

## Measured inside Nuke 17.1v3 NC (`probe_dml.py`, ST-ROTO's own tracker, synthetic 48-frame 720p shot)

Hardware: RTX 5060 Laptop 8 GB (DirectML adapter 0) and the laptop's integrated **Intel UHD Graphics** (adapter 1).

| Model | Runtime | IoU vs truth (mean / min) | Masks vs CUDA (IoU mean / min) | Warm ms/frame | GPU memory peak |
|---|---|---|---|---|---|
| tiny | CUDA (onnxruntime-gpu 1.26.0) | 0.9856 / 0.5721 | - | 354 | 3,718 MiB |
| tiny | DirectML, RTX 5060 | 0.9857 / 0.5722 | 0.99975 / 0.99729 | 374 | 2,556 MiB |
| tiny | DirectML, **Intel UHD** (12 frames) | 0.994-0.996 per frame | 0.99901 / 0.99509 | **5,931** | (shared memory; NVIDIA +1 MiB: it ran on Intel) |
| large | CUDA | 0.9864 / 0.5709 | - | 545 | 6,790 MiB |
| large | DirectML, RTX 5060 | 0.9864 / 0.5709 | 0.99989 / 0.99822 | 654 | 4,299 MiB |

(The min 0.57 is the occluder frame of this shot for every runtime.) The CUDA memory peaks reproduce T-092
(3,730 / 6,793 MiB), which validates the method; DirectML needs ~35 % less memory, so the large model fits 6 GB cards.
The CUDA port was validated against PyTorch earlier (T-044, IoU >= 0.99997); DirectML agrees with it to IoU >= 0.995
on every frame, so no separate PyTorch comparison was run. Raw: `result_*.json`, `comparison.json`.

## In the product

* `nuke_plugin/init.py` + `st_roto.runtime_choice`: build chosen at start-up, reason kept for the System report.
* `st_roto_ai.runtime`: DirectML provider options; `ST_ROTO_DML_DEVICE` selects the adapter (0 = first,
  the NVIDIA GPU here; 1 = the Intel GPU).
* System report: "GPU acceleration (DirectML)" with the display adapters of every vendor (user32
  EnumDisplayDevices); free memory of non-NVIDIA GPUs cannot be read, so model *auto* takes tiny there and the report
  gives the measured DirectML needs. On an NVIDIA GPU forced to DirectML, *auto* uses the DirectML needs.
* Installer ships both folders.
* Nuke test `test_directml_track` (started with ST_ROTO_RUNTIME=directml by tools/run_nuke_tests.py): box prompt,
  Track 8 frames "device directml", IoU 0.992-0.996, System report DirectML available, ViTMatte mattes on DirectML.

## Limits

* No AMD GPU here: AMD runs through the same DirectML API but is untested. The Intel GPU tested is an integrated one
  (slow: ~6 s per frame with tiny); Intel Arc and AMD Radeon speeds are not measured.
* DirectML is in maintenance at Microsoft (1.24.4 is the last ONNX Runtime DirectML build); it works, but future
  updates may come only through Windows ML.
