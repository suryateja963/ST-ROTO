# Probe results — Bézier fitting of SAM masks and Nuke Roto tangent semantics

Date 2026-11-15 · Nuke 17.1v3 Non-commercial, headless · Prototype code: `prototypes/geometry/bezier_fit.py` (6 unit tests passing).
Single synthetic test image. Feasibility evidence, not a benchmark.

## 1. Fitting algorithm

Schneider (Graphics Gems 1990) least-squares cubic fitting with Newton reparameterisation and recursive splitting, plus:
- circular Gaussian smoothing of the raster contour (σ = 1.5 px);
- corner detection by turning angle (window 6, threshold 45°). Corners become cusps; all other joints share tangents (G1 smooth);
- closed-loop handling.

Threshold calibration (measured): a true 69.7° corner on a raster star measures only 55–60° after smoothing at window 6, so the first default (60°) missed the inner corners of a star. Default lowered to 45°. A smooth circle of r = 200 px turns ≈ 3.4° over the same window.

## 2. Nuke Roto tangent semantics (measured, not found in documentation)

| Question | Answer | Evidence |
|---|---|---|
| Are tangents relative to the point? | **Yes**: a new point at (100, 200) reports tangents (0, 0) | `api.json` |
| Does setting one tangent change the other? | **No**, they are independent | `result_tangent_link.json` |
| Which tangent points to the previous point? | **`leftTangent` → previous point, `rightTangent` → next point.** Swapped, a 4-point circle collapses to 0.8 % area | `result_tangent_semantics.json` |
| Scale | **Nuke tangent = 2 × (cubic Bézier handle − point).** Textbook-κ circle with 1× tangents: 83.3 % area. With 2×: IoU 0.9993, area 1.0004. Effective handle measured at 0.5013 / 0.5002 / 0.4986 × the tangent for three scales | `result_tangent_semantics.json`, `result_tangent_keys.json` |
| Artefact of animation keys? | **No.** Identical results keying at one frame, at frames 0–10, or keying the centre too; rendered at frames 1 and 5 | `result_tangent_keys.json` |
| Other | In `-t` mode `nuke.frame()` = 0 while the root range starts at 1; `Layer.remove()` takes an index | |

This mapping is essential for any ST-ROTO → native Roto export (REQ-041) and must be re-verified on every supported Nuke version (Nuke 13–16 untested).

## 3. SAM 2.1 tiny mask → Bézier Roto shape

Tolerance sweep (numpy rasterisation of the fitted spline; contour of 1,409 pixels):

| Tolerance (px) | Anchors | Max / mean deviation (px) | IoU vs SAM mask | IoU vs ground truth | Fit time |
|---|---|---|---|---|---|
| 0.5 | 76 | 0.97 / 0.27 | 0.9982 | 0.9960 | 76 ms |
| **1.0** | **20** | 1.39 / 0.46 | 0.9969 | 0.9951 | 21 ms |
| 2.0 | 12 | 1.91 / 0.63 | 0.9957 | 0.9936 | 8 ms |
| 3.0 | 10 | 3.29 / 0.93 | 0.9931 | 0.9903 | 15 ms |

Rendered by Nuke (tolerance 1.0, 20 anchors, tangent rule above):

| Shape | Points | IoU vs SAM mask | IoU vs ground truth | Centroid offset (px) |
|---|---|---|---|---|
| Polygon from the previous probe | 61 | 0.9961 | 0.9911 | 0.04, 0.01 |
| **Bézier, convention A, 2× tangents** | **20** | **0.9957** | **0.9910** | **−0.05, 0.04** |
| Bézier, convention B (wrong) | 20 | 0.9112 | 0.9066 | 7.4, −4.2 |

**Result:** the same accuracy as the polygon with a third of the points, as smooth curves an artist can edit, in a native Roto shape.

## 4. Limitations

- The max deviation (1.39 px at tol 1.0) exceeds the tolerance because tolerance applies to the smoothed contour, while deviation is measured against the raw raster contour.
- Contours come from the binary mask, not sub-pixel from SAM's logits. Sub-pixel extraction should improve edges.
- No feather, no per-point feather, no animation across frames yet. Holes (inner contours) are ignored (`RETR_EXTERNAL`).
- Tested on one smooth synthetic object and synthetic unit shapes only.
