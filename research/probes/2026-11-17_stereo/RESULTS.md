# Stereo / multi-view (T-109, REQ-115, master prompt §13.4) — 2026-11-17

Nuke 17.1v3 Non-commercial, RTX 5060 Laptop, SAM 2.1 tiny (ONNX, CUDA). Test data: synthetic stereo shot
(`make_synthetic_stereo.py`, D-020): the 2026-11-15 scene rendered for two rectified cameras, layers at different
depths (background 8 px, distractor 20 px, target 30 → 50 px, occluder 45 px disparity; no vertical disparity),
exact ground truth per view. Frames are git-ignored (`out/stereo/`); regenerate with the script.

## 1. Nuke mechanics (measured: `probe_nuke_views.py`, `probe_shape_views.py`, `probe_view_persist.py`)

| Question | Result |
|---|---|
| Set up views from Python | `root["views"].fromScript("left #ff0000\nright #00ff00")` → `nuke.views() == ['left', 'right']` |
| Read with `%V` | one Read node serves both views |
| Render one view through a Write | `nuke.execute(write, f, f, 1, views=[v])`: each view's pixels (own view closer than the other view on every check) |
| Execute a Write **without** naming a view in a 2-view script | **fails**: `RuntimeError: ... cannot be executed for multiple views` (the Write path has no `%V`). ST-ROTO's pixel Write did exactly this, so Track / Preview / Re-track / mattes could not run in any stereo script before T-109 (inferred from the same call; not re-run with the old product code) |
| Limit a Roto shape to one view | shape attributes `nv` (number of views) and `view1..view<nv>` (1-based indices into the script's views); default `nv=2, view1=1, view2=2`. `attrs.set("nv", 1); attrs.set("view1", k)` shows the shape only in view k (Nuke's own render: alpha 40000 in its view, 0 in the other; an unrestricted shape renders in both) |
| Survives save + reopen | yes (`.nknc`, animated keys at frames 10 and 20 intact, restriction kept) |

## 2. Core (`st_roto.stereo`), measured outside Nuke (`probe_core.py` → `result_core.json`)

* **Disparity search** (`estimate_disparity`: zero-mean masked SSD along the epipolar line, ±10 % width, ±4 px
  vertical, coarse-to-fine, sub-pixel) on the left ground-truth mask, all 48 frames: mean error **0.25 px**,
  max 0.79 px (frame 24; the generator rounds positions to whole pixels, so ~0.5 px is the floor); **0.11 s** per object.
* **Prompt transfer** (`transfer_prompt`: left box + click moved by the disparity): box IoU vs the right-view truth
  box **0.9998-0.9999** (frames 0, 20, 47); the click lands inside the right object every time.
* **Consistency check** on correct shapes (splines fitted to both views' truth, 48 frames, occluder included):
  **0 flags**. Residuals of correct shapes: top edge 5.0 px, bottom 2.5 px (view-dependent occlusion), area ratio
  1.087, disparity step 1.9 px/frame — hence the rules: vertical = top AND bottom edge off by more than
  max(3 px, 2 % of height); size ratio > 1.35; disparity jump > max(4 px, 25 % of |median|) against both neighbours;
  object in one view only.
* **Injected errors** in the right view (frames 5, 12, 25, 40 each): vertical 12 px **4/4**, scaled ×1.5 **4/4**,
  wrong object (distractor) **4/4**, horizontal 25 px **4/4**, missing **4/4** — 20/20 caught, no false flag.
  The first tolerance (4 % of height) missed the 12 px vertical error on 2 of 4 frames: lowered to 2 %.

## 3. In Nuke (product code, `tests/nuke` `test_stereo_views`, 20 frames incl. the occluder)

Box prompt in the left view, *track every view (stereo)*, Track (CUDA):

| Check | Result |
|---|---|
| Objects | `target_left` (view left, pair target), `target_right` (view right, pair target) |
| Right view found on frame 0 | disparity **−30.0 px**, dy −0.01 px (truth −30, 0) |
| IoU vs truth, every frame | left min 0.9917 / mean 0.9939; right min 0.9910 / mean 0.9938 (20/20 frames each) |
| Stereo flags on the real AI tracks | 0 |
| Nuke's own render of the node, frame 10 | left view vs left truth 0.9914 (vs right truth 0.7572); right view vs right truth 0.9924 (vs left 0.7531): each shape only in its view |
| Mattes | one EXR sequence per view (`<matte dir>/left/`, `/right/`), each with its view's object, guided edges on its own plate: IoU 0.9993 / 0.9998 at frame 10 |
| Re-track `target_right` | renders the right view; min IoU 0.991 |
| One-view Track in the stereo script (the case that failed before) | done; object `disc` gets view `left` (shown only there) |

**Bug found by this test and fixed:** after a stereo Track, a plain Track re-tracked the prompt `target` as a third
object, because "already tracked" compared names only (`target` vs `target_left`/`target_right`). Now the pair key
counts too; the test asserts the skip.

## Limits (honest)

* Thresholds are provisional: synthetic data only; no permissively licensed real stereo footage with ground truth
  found yet (benchmark datasets research, T-036, had none).
* A stereo Track is not checkpointed (no *Resume track* for stereo runs yet; mono runs are): follow-up T-119.
* Multi-camera correspondence "when camera information is available" (§13.4): views beyond two are tracked the same
  way (every view from the prompt view's disparity), but camera data (intrinsics/extrinsics, non-rectified rigs with
  large vertical disparity) is not used: follow-up T-120.
* The disparity search assumes a roughly constant disparity over the object on the prompt frame (it finds the best
  single shift); the box from it is then refined by the AI on the other view's own pixels.
