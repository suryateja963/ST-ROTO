# T-089 — Formats, bit depths and resolutions (REQ-110 / REQ-111, master prompt §13), 2026-11-17

**Method.** `make_formats.py` writes variants of the synthetic shot (6 frames each, plate + truth at the plate's size;
`out/`, git-ignored); DPX is written by Nuke itself (10-bit). `probe_formats.py <case>` runs the PRODUCT Track (ST_Roto
node, SAM 2.1 tiny, CUDA, Nuke 17.1 NC), scores every key against the truth at full plate resolution and renders the
node's own Roto (frame 2) to check the output coordinate mapping. `summarise.py` prints the table.

## Formats and bit depths (1280x720)

| source | Nuke reports | Track | key IoU | Roto render IoU (f2) |
|---|---|---|---|---|
| PNG 16-bit | 16-bit fixed | done | 0.9926-0.9963 | 0.9954 |
| TIFF 16-bit | 16-bit fixed | done | 0.9926-0.9963 | 0.9954 |
| EXR half (scene-linear) | 16-bit half float | done | 0.9926-0.9963 | 0.9954 |
| EXR float (scene-linear) | 32-bit float | done | 0.9926-0.9963 | 0.9954 |
| DPX 10-bit (written by Nuke) | 10-bit fixed | done | 0.9927-0.9963 | 0.9954 |

The pixel path reads 32-bit float from Nuke whatever the source depth, so results are identical across depths.

## Resolutions and aspect ratios

| plate | before T-089 | after T-089 | key IoU (full res) | time, 6 frames |
|---|---|---|---|---|
| 1920x804 (2.39:1) | done | done | 0.9936-0.9955 | 7 s |
| 1280x720, **pixel aspect 2.0 (anamorphic)** | done | done | 0.9926-0.9963; Roto render 0.9954 (shapes in pixel coordinates, Nuke displays them de-squeezed) | 7 s |
| 2048x1080 (DCI 2K) | **failed** | done | 0.9934-0.9955 | 9 s |
| 1080x1920 (vertical) | **failed** | done | 0.9923-0.9931 | 8 s |
| 3840x2160 (UHD) | **failed** | done | 0.9935-0.9953 | 16 s |
| 4096x2160 (DCI 4K) | **failed** | done | 0.9935-0.9951 | 16 s |
| 7680x4320 (8K UHD) | **failed** | done | 0.9934-0.9951 | 36 s |

**Before:** every plate wider or taller than 1920x1080 failed: *"The bounding box exceeds the maximum resolution
allowed in Non-commercial mode (1920 x 1080). This could be resolved by adding a Reformat node before the Write
node."* ST-ROTO reads pixels by rendering, so in Nuke NC it could not track anything above HD.

**Fix:** `pixels.render_frame` raises `ResolutionCapped` (limit parsed from Nuke's message); the node then inserts a
Reformat (`STROTO_pixel_fit`, to box, distort) between its Input and its pixel Write, sized to the largest box within
the limit with the plate's proportions, enabled only around each render (saved scripts keep it disabled), and scales
the frame back to the plate size. Shapes are stored at full resolution; the status says "this Nuke edition renders at
most 1920x1080, so the AI saw frames reduced to 1920x1080 (from 7680x4320); shapes are full resolution, accuracy
slightly lower". The rule reacts to the edition's own refusal, so other editions' limits are handled the same way;
commercial Nuke is unaffected (no refusal, full-resolution frames). SAM 2.1 works at 1024x1024 internally, so a
1920x1080 input loses little: measured key IoU at 4K/8K equals the HD results.

Tests: `tests/nuke` `test_plate_above_render_limit` (UHD: keys 0.9947-0.9953, status, Reformat left disabled),
`tests/unit/test_sequences.py::test_resolution_cap_message_is_parsed`.

## Not covered / limits

- **Output mapping above HD cannot be rendered in NC** (Nuke refuses to render the node's Roto there); keys are
  verified by rasterising the stored splines at full resolution. Above-HD rendering needs a commercial licence.
- **Question for the owner (OQ-28):** ST-ROTO's EXR mattes are written by ST-ROTO's own code from the stored shapes,
  not by Nuke's renderer, so in NC they would be produced at full plate resolution (e.g. 4K) although Nuke itself
  will not output above HD. Whether that is acceptable under Foundry's Non-commercial terms is the owner's call;
  behaviour left unchanged and not tested above HD.
- ProRes / MOV, RED, ARRIRAW, BRAW, CinemaDNG: need sample media (and, for camera RAW, Nuke's readers in this
  edition); not tested. Any format Nuke can read reaches ST-ROTO the same way (rendered float pixels), but this is
  not measured.
- Metadata preservation (REQ-110) is not ST-ROTO's job in this design (it never rewrites plates); not tested.
- Tiling for very large plates: not needed by the tracker (it reads whole frames at <= the edition's limit, or full
  frames in commercial Nuke: 8K float RGB = 0.4 GB per frame in RAM, not measured in commercial Nuke).
