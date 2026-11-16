# Nuke → numpy pixel path (T-046) — 2026-11-16

**API audit (Nuke 17.1 NC Python).** No image-buffer access exists: `nuke` exposes only `Node.sample` (one pixel, one channel) and `deepSample`; no plane/tile/buffer/numpy entry points (`dir(nuke)`, node methods, `_nuke` searched). A true in-memory path therefore needs the NDK (C++), which Non-commercial cannot load (D-011).

**Measured per frame** (`probe_pixel_paths.py`, `result.json`; noise image, median of 3 after warm-up):

| Path | 1280×720 | 1920×1080 | Exact? |
|---|---|---|---|
| `Node.sample` per pixel (RGB, extrapolated) | 141 s | 680 s | yes |
| **float TIFF uncompressed + cv2 (current)** | **0.022 s** (11 MB) | **0.041 s** (25 MB) | **reference** |
| EXR float uncompressed + OpenEXR | 0.024 s | 0.041 s | yes (0.0) |
| EXR half uncompressed + OpenEXR | 0.025 s | 0.042 s | no (2.4e-4) |
| TIFF 16-bit int + cv2 | 0.015 s | 0.022 s | **no** (clips > 1: error 0.29) |

**Decision (D-030, delegated technical choice).** Keep the float-TIFF path: exact, as fast as any exact alternative, ~5–10 % of the per-frame tracking time (0.2–0.4 s). The file stays in the OS cache (effectively memory speed). Revisit with the NDK route on a plug-in-capable licence (T-011b).
