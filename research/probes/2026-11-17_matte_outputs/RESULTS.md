# T-099 — Matte outputs and refinement (REQ-100 / REQ-101), 2026-11-17

**Feature** (ST_Roto node, mattes section; mattes only - shapes never change):

| control | effect |
|---|---|
| RGB in mattes: none / premultiplied / straight | none: alpha only (as before). premultiplied: plate RGB (scene-linear, as Nuke renders it) x combined alpha in R, G, B. straight: plate RGB unmultiplied (edge colours NOT decontaminated). Convention written in the EXR header (`st_roto` -> `alpha_convention`), never implied (REQ-12-01..04) |
| edge offset (px) | grow (+, dilation) / shrink (-, erosion) every object's matte with a round kernel (REQ-12-10/11) |
| edge blur (px) | Gaussian feather of the matte edges, sigma in px (REQ-12-12) |
| core/edge width (px) | extra layers `core_matte` (combined matte eroded by the width) and `edge_matte` (the band; core + edge = alpha) (REQ-12-09) |

Order per frame: object alphas -> offset -> blur -> combined (roles, T-098) -> core/edge -> fit size (D-041) ->
EXR. `st_roto.matte` (`offset_alpha`, `blur_edge`, `core_edge`, `foreground_rgb`), `st_roto.exr.write_mattes(rgb,
extra)`.

**Found while testing: a Nuke Read node keeps an EXR open and Windows refuses to replace it** (`probe_file_lock.py`,
`result_file_lock.json`): `Access is denied` while the Read shows the file, also after `nuke.clearRAMCache()`,
`nuke.clearDiskCache()`, the Read's reload and emptying its file knob. An artist who looks at the mattes and renders
them again would have hit a traceback (and a stray `.part` file). Fix: before writing, ST-ROTO checks the target
files (`exr.is_locked`: rename away and back); if any is in use the whole render goes to the next version folder
(`<folder>_v002`, ...), the status says why, and the open Read keeps showing the previous version. A remaining write
failure removes the `.part` file and says the file is open.

**Evidence** (`tests/nuke` `test_matte_outputs`, `results_test_matte_outputs.json`): premultiplied + core/edge 4 px +
edge blur 1.5 px, read back by Nuke: channels rgba.red/green/blue/alpha, core_matte.alpha, edge_matte.alpha; R vs
Nuke's own plate x alpha max diff 1.2e-8; Nuke's read of the file vs the file 0.0; core + edge vs alpha 6e-8. Then
straight: RGB = plate (diff 0.0), header 'straight'; frame 1 of the first render still open in a Read -> written to
`Read1_v002` with the explanation. Unit: `tests/unit/test_matte_outputs.py` (offset area within 5 %, blur keeps
coverage within 2 %, core + edge = alpha, conventions, EXR channels/header, version naming, lock check on Windows).

**Not done** (REQ-101 remainder): edge decontamination / colour recovery, spill correction, chatter reduction,
hair refinement beyond ViTMatte, motion-blur-aware boundaries in the EXRs. In Nuke NC above HD, the RGB comes from the
reduced AI render (T-089), scaled back.
