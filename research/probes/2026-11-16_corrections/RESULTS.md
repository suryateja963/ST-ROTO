# Probe results — mask prompts (artist corrections), reverse tracking, re-track (T-060)

Nuke 17.1v3 NC · RTX 5060 8 GB · SAM 2.1 tiny · synthetic 48-frame shot. Not a benchmark.

## 1. Mask prompts in the ONNX port

Upstream `_use_mask_as_output` contains `aten::_upsample_bilinear2d_aa`, which ONNX opset 17 cannot export. Split instead:
- `maskptr.onnx` holds only the neural part (object pointer from the decoder fed with the downsampled mask; the exporter pruned the unused `s0`/`s1` inputs);
- the rest is numpy: logits = mask × 20 − 10, antialiased downsample to 256 (`st_roto_ai.resize`, a port of PyTorch's AA weights), mask-based object score and pointer gating.

Checks at export: pointer max diff 0.0 (tiny) / 1.1e-6 (large); numpy low-res logits vs upstream 9.5e-7. `resize_aa` vs `torch.interpolate(antialias=True)`: < 1e-5 on four size pairs, 0 differing mask pixels after the 0.5 threshold (unit tests).

## 2. Two reference scenarios vs PyTorch (transformers 5.23, CPU)

| Scenario | PyTorch vs GT (mean / min) | ONNX in Nuke (CUDA, fp16) vs PyTorch (min / mean) | ONNX vs GT (mean / min) | Time (ONNX) |
|---|---|---|---|---|
| **correction**: click f0 + GT mask f24, forward | 0.9948 / 0.9925 | 0.9928 / 0.9983 | 0.9949 / 0.9923 | 13.5 s |
| **reverse**: click f47, reverse to f0 | 0.8788 / **0.0** | 0.0 / 0.9788 | 0.8582 / 0.0 | 10.1 s |

- Correction helps: worst frame vs GT 0.9923 against 0.9862 with the click alone.
- Reverse tracking **loses the object in PyTorch too** (frames 17–20, 22 behind the occluder). ONNX loses one extra frame (16).
- **Port exactness proven separately:** fed with the official processor's pixels on CPU (`validate_scenarios_cpu.py`), the ONNX tracker matches PyTorch on all 48 reverse frames (low-res IoU 1.0, max logit diff 0.016). Frame 16's object score is **0.025**, at the decision threshold, so tiny preprocessing differences flip it. Same result with fp32 memory attention, so not caused by D-029.
- Preprocessing changed to the torch-equivalent antialiased resize (max normalised diff vs processor 0.114 → 0.017; 44 ms/frame at 720p). The flip on frame 16 remains: the processor quantises to 8 bits; ST-ROTO keeps float input on purpose.
- **Product consequence:** near-threshold object scores must be surfaced to the artist (confidence / review flags), task T-066.
- Metric bug found in my own probe: IoU of two empty masks was reported as 0; fixed (counts as agreement).

## 3. Re-track with corrections (ST_Roto "Re-track object")

Every artist key of an object (artist_created / artist_modified_ai / imported) becomes a mask prompt, plus the original click prompt. Tracking runs forward from the first conditioning frame and in reverse to the first frame. Only AI keys are replaced (one undoable batch); artist keys are never touched.

`tests/nuke/run_nuke_tests.py::test_retrack_with_corrections` (12 frames):
- **one hand-drawn shape on frame 6 → keys on all 12 frames**, AI frames IoU vs GT 0.9942–0.9964 (frame 6 artist 0.9981);
- correcting frame 9 in Roto, then re-track: frame 9 kept exactly (artist_modified_ai), 10 AI keys replaced.

## Limitations
- Tracker keeps every tracked frame's memory (~2 MB/frame) as upstream; long shots need bounded/disk-backed state (T-065, R-42).
- Single object per tracker; one shape per object used for re-tracking (the first).
- Masks from artist splines are rasterised hard (no feather).
