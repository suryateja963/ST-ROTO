# Edge decontamination, spill correction, chatter reduction (T-115, REQ-101) — 2026-11-18

All numbers are on synthetic data with exact truth (no permissively licensed real footage with foreground-colour
or dense per-frame truth is available, D-020 / T-036).

## Edge decontamination (`st_roto.matte.decontaminate`, `probe_edge_colour.py`)

Foreground colour of soft-edge pixels from the compositing equation I = aF + (1-a)B: B pushed out from surely-
background pixels (normalised convolution, coarse-to-fine), F_solve = (I - (1-a)B)/a, blended towards the colour
pushed out from the solid foreground where alpha < 0.3 (the solve is unstable there); solid pixels keep the plate.
Scene: textured warm foreground, soft blob + 40 hair strands (fractional alpha), 13,416 soft-edge pixels.

| Background | fringe on a new grey background (mean abs, soft edge): plate colour (before T-115) | decontaminated | decontaminated with a matte 2 px too big |
|---|---|---|---|
| green screen (textured) | 0.0583 | **0.0014** (42x lower) | 0.0370 |
| natural (high-frequency texture) | 0.0526 | **0.0163** (3.2x lower) | 0.0403 |

Foreground-colour error: 0.148 → 0.0037 (green screen), 0.134 → 0.041 (natural).

## Spill correction (`st_roto.matte.despill`)

Channel-limit despill of the foreground colour (screen channel limited by the mean ('average') or max of the other
two; amount 0-1; 'auto' picks green/blue from the background: detected 'green' correctly). Green light bounced onto
the foreground near its edge: fringe 0.0287 → **0.0095** with 'average'; 'max' changed nothing on this orange
foreground (red always exceeds green). Limitation (documented): genuinely green / blue foreground colours are
reduced too.

## In the product

RGB in mattes: new modes `premultiplied, decontaminated` and `straight, decontaminated`, knob *spill* (none / auto /
green / blue). The EXR header keeps `alpha_convention` (premultiplied / straight) and adds `edge_colour`
(decontaminated / plate) and `spill` - never implied. Nuke test (`test_edge_colour_and_chatter`, real track of the
synthetic shot): header recorded; solid-foreground pixels = plate x alpha (max diff 6e-4, 8-bit source); soft-edge
colours changed (mean 0.029 over 3,445 pixels).

## Chatter reduction (`st_roto.chatter`, button *Reduce chatter*)

Each control point's path (position + handles) on AI frames is replaced by a local quadratic least-squares fit over
±radius frames (constant velocity / acceleration pass unchanged, unit-tested); artist keys and locked frames are kept
and anchor the fit; gaps and collapsed part keys split the path; run ends with < 4 samples are left alone (a lower-
order fit there bent real acceleration - found by the unit test). One undo step, written as AI (command bus
protection applies).

Controlled measurement (`probe_chatter.py`, slowly moving rotating ellipse, keys fitted like the tracker, per-frame
boundary wobble = what per-frame mask predictions do):

| per-frame wobble | temporal error before → radius 2 → radius 3 | mean IoU before → radius 3 |
|---|---|---|
| none | 5.3e-5 → 5.4e-5 → 5.7e-5 (neutral) | 0.9998 → 0.9998 |
| σ 0.5 px | 0.00294 → 0.00209 → 0.00172 (−41 %) | 0.9890 → 0.9931 |
| σ 1 px | 0.00564 → 0.00390 → 0.00312 (−45 %) | 0.9781 → 0.9865 |
| σ 2 px | 0.01041 → 0.00690 → 0.00540 (−48 %) | 0.9569 → 0.9738 |

**But on the real AI track of the synthetic shot** (already accurate: IoU 0.994; the target moves fast, rotates and
scales) it did NOT help: jitter 1.89 → 1.48 px, mean IoU 0.9939 → 0.9933, temporal error 0.00088 → 0.00099 (+12 %).
So it is an opt-in tool for shots whose edges visibly chatter, not a default; the user guide says so. Not validated
on real chattering footage (none with dense truth available).
