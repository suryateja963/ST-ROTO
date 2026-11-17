# Extra channels as hints (T-110, REQ-113, master prompt §13.2) — 2026-11-18

Nuke 17.1v3 Non-commercial, RTX 5060 Laptop, SAM 2.1 tiny (ONNX, CUDA). Test data: a synthetic CG shot
(`make_synthetic_cg.py`, D-020): the 2026-11-15 scene at 960x540, 24 frames, 3x3 supersampled, with render passes
and exact truth: `rgba` (A = 1), `depth.Z`, `forward`/`backward` vectors (written u right, v up), `N`, `P`,
`CryptoObject00/01` (Cryptomatte v1.2, 4 ranks, manifest in the header). Frames are git-ignored (`out/cg/`).

## What §13.2 asks, and what ST-ROTO does now

| Channel | Use in ST-ROTO | Evidence |
|---|---|---|
| Alpha | passes through; the node's alpha is REPLACED by the shapes on new nodes (knob *replace input alpha*); another node's alpha is a prompt source (T-100) | §2, DEF-011 |
| Z-depth | *medians of* `depth.Z`: median inside each shape per frame; a spike flags the frame (shape grabbed something nearer/further) | §3 |
| Motion vectors | *motion vectors* (+ *backward*): each shape moved by the vectors must match the next frame's shape; convention measured per shot | §3, §4 |
| Cryptomatte | prompt source *Cryptomatte* (names → box + clicks), and a per-frame comparison shape vs matte | §2, §3 |
| Normals, position, any other | *medians of* any channel list (e.g. `N.Z, P.Y`) with the same spike rule | §3 |
| Artist selects channels | knobs *medians of*, *motion vectors*, *backward*, *vector convention*, *Cryptomatte layer*, *Cryptomatte objects*; *List channels* shows the input's layers and Cryptomatte names | Nuke test |
| Preserve unrelated channels | every input layer leaves the node bit-identical (max difference 0.0) | §2 |

## 1. Nuke mechanics (measured)

* A Read of the multi-layer EXR exposes every layer (`rgba, depth, forward, backward, CryptoObject00/01, N, P`) and
  the Cryptomatte header as metadata `exr/cryptomatte/<key>/name|hash|conversion|manifest`.
* A Write can render one layer (`channels = depth`) or `all`; Nuke writes rgba as `R/G/B/A` and keeps other layers'
  suffixes (`N.X`, `CryptoObject00.R`).
* The Python OpenEXR binding GROUPS `<layer>.R/G/B/A` into one 4-channel entry unless `separate_channels=True`
  (`st_roto.exr.read_channels` now asks for separate channels).
* **Nuke's VectorGenerator** in headless NC (with and without `--gpu`): output was usable on only 28 % of pixels and
  wrong in the target region; not used. Background u = −6.5 px vs the known −6.38 px pan (u positive = right).

## 2. Cryptomatte, pass-through, alpha

* `st_roto.channels.murmur3_32` equals the published MurmurHash3_x86_32 vectors ("hello" 0x248bfa47, "Hello,
  world!"/1234 0xfaf6cdb3, "The quick brown fox…" 0x2e4ff723); `name_to_id("bunny") = 13851a76` (Cryptomatte spec).
* **Independent check: Nuke's own Cryptomatte node** (Foundry's decoder) on our file, matte `target`: IoU **1.0** vs
  truth on frames 0, 10, 20 (coverage sum / truth 0.9996-1.0001). ST-ROTO's decoder gives the same.
* **Pass-through:** an ST_Roto node over the CG plate, all channels rendered: every layer except alpha identical to
  the source (max |difference| **0.0**), none missing.
* **DEF-011 found:** Nuke's Roto composites shapes OVER the input alpha by default; on this plate (A = 1) the node's
  alpha was 1 everywhere (IoU 0.058 with the shape). `Roto.replace = True`: alpha = shapes only (1 inside, 0 outside),
  other channels still bit-identical (`probe_roto_replace.py`). New nodes set it (linked knob *replace input alpha*);
  older nodes keep their behaviour. EXR mattes written by ST-ROTO were never affected.

## 3. Checks on the synthetic shot (`probe_core.py` → `result_core.json`)

Correct shapes = splines fitted to every piece of the truth mask, per frame (the occluder splits the target).

| | Result |
|---|---|
| False flags on correct shapes (depth.Z, N.Z, P.Y medians; motion with backward vectors; Cryptomatte) | **0** (motion IoU ≥ 0.998, Cryptomatte IoU ≥ 0.997) |
| Injected: wrong object (distractor) on frames 5/12/18 | 3/3 — depth, motion and Cryptomatte each catch all |
| Injected: shape shifted 30 px | 3/3 (motion 0.64-0.74, Cryptomatte 0.39-0.72) |
| Injected: shape stuck on the previous frame | 3/3 (motion 0.46-0.85; at 21 px/frame on a ~255 px object the geometric limit is ~0.83) |
| Injected: shape scaled ×1.3 | 3/3 (motion 0.53-0.61) |
| Forward vectors only (no backward layer) | 3 false flags on the occluder frames (IoU 0.28-0.71): use the backward layer |
| Time | ~0.1 s per frame and object (numpy), plus rendering |

What the rules needed (each found by measurement, not assumed):
* **Spike rule for channel medians.** The first rule (relative jump) flagged position `P.Y` 6 times on correct shapes
  (signed values crossing zero). Now: a frame must deviate from both neighbours in the same direction by more than
  25 % of the shot's p90−p10 spread (and 5 % of its value).
* **Occlusion handling must be object-centric.** A plain forward-backward test also removes the object's own
  silhouette moving over the background, which hid a stuck shape (IoU 0.997). Now only pixels where ANOTHER surface
  hides (forward → backward fails for an object pixel) or reveals (backward lands outside the previous shape) the
  object are left out, plus a 4 px margin; vectors sampled nearest-pixel (bilinear mixing across edges faked
  occlusions along every silhouette).
* **Outline points read vectors 3 px inside the shape.** On the AI track one outline point sat over the passing
  distractor and took its motion: motion IoU 0.88 on a frame whose shape was 0.99 correct. With the inset: 0.993.

## 4. Vector convention

Renderers disagree on vector signs, so ST-ROTO measures it: frame f moved by the vectors must look like frame f+1
(mean absolute difference for the 4 sign combinations, only where vectors move > 0.5 px), summed over up to 6 frame
pairs; each axis is decided only if flipping it is ≥ 2 % worse, otherwise Nuke's sign is used and reported.
On the shot: **u right, v up** found (margins u 2.25, v 1.10); single frame pairs: 20 of 23 decided both axes, 0
wrong; 3 left v undetermined (little vertical motion) — the reason for summing frames.

## 5. In Nuke (product code, `tests/nuke` `test_extra_channels`)

| Step | Result |
|---|---|
| List channels | layers rgba, depth, forward, backward, CryptoObject00/01, N, P; Cryptomatte CryptoObject: background, distractor, occluder, target |
| Prompt from Cryptomatte `target`, frame 0 → Track (CUDA) | 24/24 frames, IoU mean 0.9913, min 0.961 (frame 12, occluder) |
| Node output frame 10 | all layers bit-identical to the source; alpha vs truth IoU 0.991 |
| Check with channels (depth.Z, forward/backward, Cryptomatte), convention auto | convention measured **u right, v up**; 24 frames; motion IoU min 0.981, Cryptomatte min 0.961; **no flags** |
| Artist key on frame 12 replaced by the distractor | frame 12 flagged by depth (5.6× usual change), motion (0.01) and Cryptomatte (0.01); frame 13 by motion (from the wrong frame 12) |
| Same check with AI disabled | runs (not an AI feature) |

## Limits (honest)

* Synthetic CG data only. Real renderers' passes (filtered depth, vectors with motion blur, deep Cryptomatte with
  more ranks) are untested: thresholds are provisional.
* Not yet (on the task board, T-121): shapes made directly from Cryptomatte without AI, and propagating a hand-drawn
  shape along the motion vectors (a traditional-roto assist with AI off).
* The check renders every channel of every frame through Nuke (EXR, all layers). Plates above the Non-commercial
  render limit (1920x1080) were NOT tested with the channel check; unlike Track (T-089) it has no reduced-render
  fallback yet, so it is expected to stop with Nuke's resolution error there.
