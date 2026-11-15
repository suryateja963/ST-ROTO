# Probe results — SAM 2.1 tiny and large: ONNX export, in-process CUDA inference in Nuke, native Roto output

Date 2026-11-15 · RTX 5060 Laptop 8 GB, driver 621.24 · Nuke 17.1v3 **Non-commercial**, headless (`-t`, no `--gpu` needed for ONNX Runtime) · onnxruntime-gpu 1.26.0 inside Nuke.
Single runs on one synthetic test image. **Feasibility evidence, not a benchmark.** No product code yet.

## What was proven

A single click becomes a **native, editable Nuke Roto shape**, with SAM 2.1 running **inside the Nuke process on the GPU** under a Non-commercial licence, using 4 nodes (within the 10-node cap).

```
Read (Nuke) ─► float TIFF ─► numpy ─► SAM 2.1 encoder (ONNX, CUDA) ─► decoder (click) ─► mask
   ─► contour ─► polygon ─► nuke.rotopaint.Shape in a Roto node ─► Nuke renders it ─► compared with mask & ground truth
```

## Results

| | SAM 2.1 tiny | SAM 2.1 large |
|---|---|---|
| Weights (HF revision) | `de431c40…`, 156 MB | `665f8e2a…`, 898 MB |
| ONNX encoder / decoder size | 109 MB / 17 MB | 853 MB / 17 MB |
| **Export check: ONNX vs PyTorch mask IoU** (CPU) | **1.0** (encoder max diff 6.8e-6) | **1.0** (encoder max diff 4.9e-4) |
| Session load in Nuke | 1.91 s | 3.53 s |
| Encoder per frame, warm (CUDA, 1024²) | **65 ms** | **317 ms** |
| Decoder per click, warm (CUDA) | **6.7 ms** | **6.7 ms** |
| First encoder / decoder call | 0.98 s / 336 ms | 1.15 s / 306 ms |
| Peak GPU memory, whole system (desktop ≈ 0.18 GB) | 2.49 GB | 5.56 GB |
| SAM mask IoU vs synthetic ground truth | 0.9947 | 0.9967 |
| Roto shape control points (polygon, 1 px tolerance) | 61 | 48 |
| **Rendered Roto vs SAM mask IoU** | **0.9961** | **0.9963** |
| Rendered Roto vs ground truth IoU | 0.9911 | 0.9932 |
| Rendered Roto vs mask centroid offset (x, y px) | 0.036, 0.008 | 0.015, 0.061 |

Pixel transfer Nuke → numpy (1920×1080 RGB float32, uncompressed TIFF): **0.09 s render + 0.02 s read**. After re-encoding Nuke's linearised pixels to sRGB, they match the source PNG to 1.2e-7.

## What the numbers mean

- **Export is exact.** The ONNX graphs reproduce PyTorch masks identically for both sizes.
- **Interactive speed is there.** After one encoder pass per frame, each click costs ~7 ms, fast enough for live point-and-click in the viewer. Large is ~5× slower per frame than tiny but stays under a third of a second at 1024².
- **Large fits the 8 GB card here** (5.6 GB peak including the desktop), but leaves little headroom for Nuke's own GPU use. Hardware-aware model selection (REQ-020/021) matters.
- **Coordinate mapping is correct.** Rendered shapes sit within 0.06 px of the mask centroid. The remaining IoU gap (0.996) comes from polygon simplification and Roto anti-aliasing, not misplacement.
- The shape is a plain `nuke.rotopaint` Shape. It is saved in the script and editable without ST-ROTO (script: `out/roto_<model>.nk` → saved as `.nknc` by Non-commercial).

## Limitations and open points (honest list)

1. **One synthetic image** with a high-contrast target. Says nothing about hair, motion blur, real footage or video propagation (§9, §11). Real evaluation needs the benchmark plan.
2. **Polygon only.** Control points have no Bézier tangents and no feather. Fitting smooth Béziers with sensible point counts is the next geometry task.
3. **Image mode only.** No temporal memory yet. SAM 2.1 video propagation (memory attention/encoder) is not exported.
4. **Pixel transfer goes through disk** (TIFF). Fine at HD; an in-memory path should be investigated.
5. **Colour handling assumption:** the test image is an sRGB PNG and Nuke linearised it on read. The probe re-encoded to sRGB before inference. A documented, configurable model-input colour transform is required (§13.1). Hard-coded here.
6. **pip OpenCV 5.0 has no OpenEXR support**, so EXR cannot be read with it. Probes used float TIFF.
7. **Non-commercial caps renders at 1920×1080** (confirmed: "2048 x 1556 is not allowed"). 2K–8K tests (§13) cannot run on this licence.
8. ORT warnings (not errors): "ScatterND … indices not duplicated", "3 Memcpy nodes added", "lenient shape merge". Results were correct, but the warnings should be reviewed when the decoder is optimised.
9. Peak GPU memory is whole-system (nvidia-smi on WDDM), not per process.
10. Pre-processing resize differs slightly from the official processor (max 0.22 in normalised units). Mask impact: IoU 0.9998 vs processor pre-processing.

## Reproduce

```powershell
.venv\Scripts\python.exe tools/models/download_models.py sam2.1-hiera-tiny sam2.1-hiera-large
.venv\Scripts\python.exe tools/models/export_sam2_onnx.py sam2.1-hiera-tiny sam2.1-hiera-large
"C:\Program Files\Nuke17.1v3\Nuke17.1.exe" --nc -t research/probes/2026-11-15_sam2/probe_sam2_in_nuke.py sam2.1-hiera-tiny
"C:\Program Files\Nuke17.1v3\Nuke17.1.exe" --nc -t research/probes/2026-11-15_sam2/probe_sam2_in_nuke.py sam2.1-hiera-large
```
Package pins: `research/probes/2026-11-15_gpu_ort/requirements-nuke-py311.txt`. Weight checksums: `models/manifests/*.json`.
