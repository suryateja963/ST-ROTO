# Probe results — SAM 2.1 video tracking inside Nuke (ONNX + numpy), animated native Roto shape

Date 2026-11-15 · RTX 5060 Laptop 8 GB · Nuke 17.1v3 **Non-commercial**, headless · onnxruntime-gpu 1.26.0 in Nuke.
**One synthetic 48-frame shot** (`make_synthetic_video.py`, seed 11, 1280×720): panning textured background, a moving/rotating/scaling textured target, a similar-coloured distractor, and a grey bar crossing the target (frames ~18–30). Exact ground truth = visible part of the target. Feasibility evidence, **not a benchmark**.

## Pipeline proven

```
Nuke Read (sequence) ─► float TIFF ─► numpy ─► SAM 2.1 video (5 ONNX graphs on CUDA + numpy memory bookkeeping)
   ─► per-frame mask ─► 16-anchor Bézier with frame-to-frame point correspondence ─► ONE animated nuke.rotopaint Shape
   ─► Nuke renders all 48 frames ─► compared with mask and ground truth
```
Click once on frame 0. Everything else is automatic. 4 nodes (Non-commercial cap 10).

## 1. Port correctness (ONNX + numpy vs PyTorch transformers 5.23)

| Check | tiny | large |
|---|---|---|
| Component max abs diff vs PyTorch (encoder / memory-attention / decoders / memory encoder) | ≤ 1.1e-5 | ≤ 1.9e-4 (encoder) |
| Memory attention across 1–7 memory frames × 1–16 pointer tokens | exact (≤ 3.9e-6) | – |
| Whole tracker, same pixels as reference, per-frame mask IoU vs PyTorch (CPU) | **min 0.99997, mean 1.0** (48 frames) | – |
| Inside Nuke (our own pre-processing, CUDA), IoU vs PyTorch reference | mean 0.999, min 0.995 | mean 0.999, min 0.991 |

## 2. Quality on this shot (IoU vs exact ground truth)

| | tiny | large |
|---|---|---|
| PyTorch reference: mean / min | **0.995 / 0.986** | 0.987 / **0.573** |
| Occluded frames mean | 0.992 | 0.909 |
| In Nuke (our port, CUDA): mean / min | **0.995 / 0.986** | 0.987 / 0.573 |

**Large is worse than tiny here.** It loses half the target on frame 23, when the occluder splits it into two pieces, then recovers. The same happens in the PyTorch reference, so it is model behaviour, not a port error. One synthetic shot proves nothing general, but it shows why model choice must be measured per category (§21) and not assumed from model size.

## 3. Speed and memory in Nuke (RTX 5060 8 GB, warm, per frame)

| | tiny | large |
|---|---|---|
| Read + sRGB + resize/normalise | 60 ms | 61 ms |
| Image encoder | **67 ms** | 278 ms |
| Tracking step (memory attention + decoder + memory encoder) | **108 ms** | 110 ms |
| **Total per frame** | **≈ 0.24 s** | ≈ 0.45 s |
| Bézier fit (16 anchors) | 1.1 ms | 1.2 ms |
| Session load / first encoder call | 3.5 s / 0.8–1.3 s | 4.5 s / 1.0 s |
| Peak GPU memory, whole system (desktop ≈ 0.2 GB) | 4.75 GB | **7.83 GB of 8.15 GB, at the limit** |

## 4. Animated Roto shape (rendered by Nuke vs tracker mask)

| | tiny | large |
|---|---|---|
| Keys per control point | 48 | 48 |
| IoU vs mask: mean / min | 0.983 / **0.558 (frame 23)** | 0.991 / 0.972 |
| Typical frames | 0.98–0.99 | 0.985–0.99 |

Frame 23 (tiny): the visible target is two disjoint pieces. A single closed shape traces only the largest piece. Static single-frame shapes reached 0.996; the fixed 16-anchor animated shape costs ~0.5–1 % IoU in exchange for constant topology.

## 5. Nuke API pitfalls found (all verified)

- **Keys added to a `ShapeControlPoint` after `Shape.append()` are silently lost.** The shape stores a copy. Key everything first, then append (`probe_anim_keys.py`).
- `nuke.frame()` is 0 in `-t` mode; the Read range here was 0–47.
- See also `../2026-11-15_bezier/RESULTS.md`: tangent = 2 × Bézier handle offset, `leftTangent` → previous point.

## 6. Limitations (honest list)

1. One synthetic shot, one object, one click on frame 0. No hair, motion blur, real footage, scene cuts or long shots.
2. Forward tracking only. No reverse propagation, no corrections on tracked frames, no multiple objects yet (the upstream logic supports them; the port does not yet).
3. Split objects (two pieces) become one shape around the largest piece. **Multi-shape objects are an architecture requirement.**
4. Fixed 16 anchors for the whole shot; no adaptive point count, no feather, no motion blur.
5. Large model leaves ~0.3 GB GPU headroom on an 8 GB card. Not safe as a default here.
6. Pixel transfer via TIFF on disk. Colour handling hard-coded (sRGB re-encode).
7. The tracker keeps per-frame state in RAM, bounded to the last max(7, 16) frames plus conditioning frames. Resumable processing is not implemented.
8. Speed timings are single runs on one laptop, with the hardware logger recording; thermal state not controlled.

## Reproduce

```powershell
.venv\Scripts\python.exe research/probes/2026-11-15_video/make_synthetic_video.py
.venv\Scripts\python.exe research/probes/2026-11-15_video/reference_torch.py sam2.1-hiera-tiny     # and -large
.venv\Scripts\python.exe tools/models/export_sam2_video_onnx.py sam2.1-hiera-tiny                 # and -large
.venv\Scripts\python.exe research/probes/2026-11-15_video/validate_onnx_tracker.py sam2.1-hiera-tiny
"C:\Program Files\Nuke17.1v3\Nuke17.1.exe" --nc -t research/probes/2026-11-15_video/probe_track_in_nuke.py sam2.1-hiera-tiny
```
