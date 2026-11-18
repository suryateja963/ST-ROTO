# First real production footage: 7 green-screen shots (T-126, progress on T-118) — 2026-11-18

**Footage.** The owner's own footage, used with their permission for testing only. It was read in place and never
copied into the repository: **no image or video from these shots is in git, only numbers**. Overlay images exist
only on the owner's machine.

| | |
|---|---|
| Format | 7 shots, 289 frames, 4096x2160, 16-bit RGB TIFF, no alpha, no gaps |
| Colour space | unknown; display-referred, treated as sRGB / Rec.709 |
| Content | close-up torso (112), dancer with raised arms (113), torso + a man running in (114), long hair (115, 116), torso + gesturing man (117), wide shot of a couple with crew and lights in frame (118) |

**How it ran.** Everything went through the real product path: Nuke 17.1v3 Non-commercial, the ST_Roto node, Track,
then Re-track for the man prompted on frame 18 of 114, and Render mattes.
* Prompts: one box plus one click per person, placed by eye (`prompts.json`, normalised coordinates).
* Models: SAM 2.1 tiny and large, CUDA on an RTX 5060 Laptop.
* Non-commercial renders at most 1920x1080, so **the AI saw every frame reduced to 1920x1012**, while the shapes are
  full 4K resolution.
* Scripts: `run_shot.py` (Nuke), `run_vitmatte.py`, `measure.py`, `render_overlays.py` (writes images to a local
  folder only).

**What the shapes are measured against.** No human truth exists for this footage, so the reference is a green-screen
key made from the plates (`measure.py`, measured at 2048x1080):
* green ratio r = (G - max(R,B)) / G;
* alpha = 1 - clip((r - 0.3 s) / 0.4 s), where s is the screen's median r;
* reference = alpha >= 0.5.

| Score | What it measures |
|---|---|
| **core IoU** | IoU on pixels where the key is certain (alpha <= 0.05 or >= 0.95). Hair, motion blur and spill edges are left out. |
| **holes-filled** | core IoU with enclosed background (for example green seen between raised arms) counted as foreground. Roto shapes have no holes, and the status line says so. |
| **BF3** | boundary F-measure at 3 px (about 6 px at 4K), with a 4 px strip at the frame border ignored. My first boundary score counted the frame edge where the body leaves the frame; that was fixed. |

## Tracking

| Shot | frames | tiny core IoU mean (min) | large core IoU mean (min) | holes-filled tiny / large | BF3 tiny / large | review flags |
|---|---|---|---|---|---|---|
| 112 torso | 23 | 0.9935 (0.9917) | 0.9929 (0.9918) | 0.994 / 0.993 | 0.83 / 0.85 | none |
| 113 dancer, arms up | 37 | 0.9163 (0.8864) | 0.9143 (0.8801) | **0.989 / 0.987** | 0.72 / 0.72 | none |
| 114 torso + man entering | 103 | 0.9945 (0.9869) | 0.9929 (0.9848) | 0.994 / 0.993 | 0.81 / 0.81 | man: check 1-5 (entering) |
| 115 long hair | 26 | 0.9931 (0.9907) | 0.9920 (0.9909) | 0.995 / 0.994 | 0.80 / 0.82 | none |
| 116 long hair, turning | 27 | 0.9911 (0.9858) | 0.9895 (0.9867) | 0.995 / 0.994 | 0.79 / 0.81 | none |
| 117 torso + man | 51 | 0.9907 (0.9827) | 0.9903 (0.9802) | 0.989 / 0.989 | 0.69 / 0.75 | none |
| 118 wide, couple | 22 | **0.8935 (0.7115)** | **0.9491 (0.9355)** | 0.920 / 0.979 | 0.72 / 0.76 | **none** |

* **Five of seven shots track at 0.99 core IoU with either model.**
* **113** is limited by the product, not by the tracker. Her raised arms enclose green screen, and Roto shapes have no
  holes ("holes not represented on frames 0-25, 27-34, 36"). With the hole counted as foreground the shot scores
  0.989 / 0.987. The rest of the loss is a fast-flapping fabric tail at her side.
* **118 with tiny is a real failure.** The couple's shape misses the man's white shirt and trousers on frames 0 and
  16-21 (min 0.71). He is small in a 4K wide shot, and the AI sees him at 1920 px.
  * **No review flag was raised on any of those frames** (logged as DEF-012).
  * **The large model fixes it** (0.949, min 0.936, holes-filled 0.979).
  * Large brings no gain on the other six shots.
* **Multiple objects** (114, 117): each person stays on their own shape.
  * Leak onto clearly-green pixels: woman <= 0.012 %, man ~0.5 %.
  * The man entering 114 (motion-blurred, from frame ~6) was found by Re-track backwards from frame 18. "Check" flags
    were raised on frames 1-5, where he is entering or absent.
  * The crew member in 118 was tracked as a separate object.
* **Scene cuts:** none detected on any of the 14 runs (these are continuous shots: no false cuts).
* **Temporal jitter** (mean frame-to-frame change of core IoU): 0.0003-0.0013 on the good shots.

## Mattes (large model; EXR at "fit 1920x1080", the Non-commercial default)

**Hair edges (115, 116).** Alpha vs the key in the edge band (SAD/1000, lower = closer to the key):

| | guided filter | hard | ViTMatte-S |
|---|---|---|---|
| 115 | 4.72 | 4.85 | 6.11 |
| 116 | 4.82 | 4.92 | 6.37 |

**Read with care: the key is not a valid hair reference.** My simple key is nearly binary at hair and leaves ragged
holes along the edge. A close look at a crop showed:
* **ViTMatte** visibly recovers fine stray strands, which the hard shape cuts off, but it also softens a clean
  shoulder edge into a grey ramp;
* **the guided filter** stays close to the shape.

These numbers therefore cannot decide which method is best for hair; that needs an artist's eye or a precise matte.

**Bug found and fixed (DEF-013).** ViTMatte failed on these 4K close-ups with "Failed to allocate memory for
requested buffer of size 10487453184" (10.5 GB). It runs one pass over the whole edge zone, and its global attention
grows with the square of the area. It now runs in overlapping 1024 px tiles (overlap 256).
* Checked on 115/116 at half resolution, where one pass still fits: tiles vs one pass differ by 0.036-0.045 mean abs
  in the unknown band.
* Against the key, tiles are as close as one pass, or closer: SAD 12.8 vs 13.8 and 13.3 vs 14.7
  (`result_vitmatte_tile_study.json`).
* Full 4K: 20 s on the CPU (`result_vitmatte_tiles.json`).
* In Nuke on the GPU: 26-27 frames in ~2 min per shot.

**Despill** ("premultiplied, decontaminated" + spill auto, vs plain premultiplied):

| Shot | green excess in soft edges (plain -> despilled) | mean RGB change in the solid core |
|---|---|---|
| 113 | 0.085 -> 0.000 | 0.014 |
| 115 | 0.049 -> 0.000 | 0.001 |
| 116 | 0.041 -> 0.000 | 0.001 |
| 118 | 0.097 -> 0.000 | 0.010 |

Alpha is unchanged (the edge-band SAD is identical with and without despill).

**Holdout** (the man as holdout, 114 / 117):
* The combined matte equals woman x (1 - man): mean abs error 0.00001.
* Max 0.22 at single edge pixels. This is expected: the combined matte is computed at 4K and then reduced, while the
  layers are reduced separately.
* The holdout removed pixels on only 3 of 103 frames (114) and none in 117. The tracker gives each person only their
  visible part, so the shapes hardly overlap. Correct behaviour, but it means this footage barely exercises
  holdouts.

## Speed (RTX 5060 Laptop, 4K 16-bit TIFF plates)

* **Track:** tiny ~2.5-4 s/frame and large ~4.5-5 s/frame. Both include reading 50 MB frames, the reduced render
  and scene-cut detection. The large-model run times in `summary.json` also contain the matte passes.
* **Mattes:** the guided-filter pass at 4K took **~16 s/frame** (114: 1,662 s for 103 frames), while hard edges took
  ~0.5 s/frame. Slow at 4K: logged as DEF-014.

## Limits

* The reference is a key, not human truth.
  * It is reliable for body outlines on clean green.
  * It is unreliable for hair, motion blur and spill edges: those are excluded from the core IoU and must not be read
    as truth.
  * In 118 it also picks up floor shadow inside the region of interest.
* Colour space is unknown (treated as sRGB).
* Prompts were placed by me by eye; a different box or click can change results, especially on 118.
* 7 short shots (22-103 frames), one session, one machine, Nuke 17.1 Non-commercial only. The AI saw 1920-wide frames
  because of the edition's render limit; commercial Nuke would give it full 4K (not tested).
* This is not yet T-118's "shot completed by an artist": nobody judged the shapes or mattes for delivery.

Files: `prompts.json`, `run_shot.py`, `run_vitmatte.py`, `measure.py`, `render_overlays.py`,
`check_vitmatte_tiles.py`, `summary.json`, `result_SHOT-1xx.json` (per frame), `result_vitmatte_tiles.json`,
`result_vitmatte_tile_study.json`.
