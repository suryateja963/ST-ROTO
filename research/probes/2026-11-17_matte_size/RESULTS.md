# OQ-28 — EXR mattes at full resolution and fitted into 1920x1080, 2026-11-17

**Owner's instruction (2026-11-17):** "Let's do it both full resolution and 1920x1080. Test them, report back results."

**Implementation.** Node knob **matte size**: *full resolution* (default, as before) or *fit 1920x1080*. Mattes are
always computed at the shot's full resolution (shapes rasterised exactly, guided filter against the plate) and, for
*fit*, area-averaged (`cv2.INTER_AREA`) into the largest box within 1920x1080 with the shot's proportions; plates
that already fit are never scaled. The EXR header records `size` and `shot_size`; the status says
"(fitted from WxH)". `st_roto_nuke.mattes.fit_size`, `render_mattes(out_size=...)`.

**Method.** `probe_matte_size.py <case>`: PRODUCT node in Nuke 17.1 NC, one Track (tiny, CUDA; above HD through the
reduced AI render of T-089), then mattes for every combination; frame 2 measured: EXR size, IoU (matte > 0.5 vs truth
at that size), soft pixels, fit vs area-downscaled full matte, and **Nuke itself reading the EXR** (format, channels,
values at 10 sample pixels). Plates: synthetic shot, `research/probes/2026-11-17_formats/out`.

## Results (6 frames each)

| plate | matte size | edges | EXR size | time | MB/frame | IoU vs truth | Nuke reads it | fit = downscaled full |
|---|---|---|---|---|---|---|---|---|
| 1280x720 | full | guided | 1280x720 | 2.2 s | 0.04 | 0.9999 | yes, diff 0.0 | – |
| 1280x720 | full | hard | 1280x720 | 0.2 s | 0.02 | 0.9963 | yes, diff 0.0 | – |
| 1280x720 | fit 1920x1080 | both | **1280x720 (unchanged)** | same | same | same | yes, diff 0.0 | – |
| 3840x2160 | full | guided | 3840x2160 | 19.2 s | 0.20 | 0.9963 | yes, diff 0.0 | – |
| 3840x2160 | full | hard | 3840x2160 | 1.8 s | 0.09 | 0.9952 | yes, diff 0.0 | – |
| 3840x2160 | fit 1920x1080 | guided | 1920x1080 | 18.5 s | 0.06 | 0.9952 | yes, diff 0.0 | 0.0 |
| 3840x2160 | fit 1920x1080 | hard | 1920x1080 | 1.1 s | 0.03 | 0.9950 | yes, diff 0.0 | 0.0 |
| 7680x4320 | full | guided | 7680x4320 | 85.4 s | 0.55 | 0.9955 | yes, diff 0.0 | – |
| 7680x4320 | full | hard | 7680x4320 | 5.7 s | 0.33 | 0.9951 | yes, diff 0.0 | – |
| 7680x4320 | fit 1920x1080 | guided | 1920x1080 | 82.4 s | 0.05 | 0.9947 | yes, diff 0.0 | 0.0 |
| 7680x4320 | fit 1920x1080 | hard | 1920x1080 | 2.3 s | 0.03 | 0.9946 | yes, diff 0.0 | 0.0 |

(Times are for all 6 frames.)

## Findings

1. **Both modes work in Nuke 17.1 NC up to 8K.** Nuke reads both sizes exactly (layer `target.alpha` and
   `rgba.alpha`, value difference 0.0). Reading large EXRs is not restricted in NC; only rendering is.
2. **Accuracy is the same** (IoU 0.995-0.996 either way). *Fit* mattes are exactly the area-average of the full
   ones (max difference 0.0); hard mattes become slightly soft at the fitted size (898 / 1,382 soft pixels), which is
   the correct anti-aliased result of downsizing.
3. **Fit saves disk, not time:** 3-11x smaller files, but the matte is still computed at full resolution, so the
   guided filter takes as long (8K: ~14 s/frame). A faster *fit* would compute at the reduced size; not done (it
   would change the edge result).
4. **Caveat for soft edges above HD in NC:** the guided filter's plate guide comes through the reduced AI render
   (1920x1080, scaled back up), so full-resolution soft edges at 4K/8K are guided by an upscaled plate - the shape is
   exact, the fine edge detail is not true 4K. Commercial Nuke renders the plate at full resolution.
5. HD and smaller plates: both settings give identical files.

## Licence note

Owner's decision (2026-11-17, D-041): **fit 1920x1080 is the default in Nuke Non-commercial**; full resolution
stays the default in other editions. Verified by `tests/nuke` `test_plate_above_render_limit` (UHD plate in NC:
knob defaults to fit, hard mattes 1920x1080, IoU 0.995). Tests: `tests/unit/test_exr_mattes.py::
test_mattes_fitted_into_a_box`; this probe (`result_hd.json`, `result_uhd4k.json`, `result_uhd8k.json`).
