# Multi-camera correspondence from camera data (T-120, REQ-115 / master prompt §13.4) — 2026-11-18

Nuke 17.1v3 Non-commercial; synthetic non-rectified three-camera shot with exact truth.

## 1. Nuke's camera model, measured (`probe_camera_model.py`)

* The classic 3D path (Camera2 + Card2 + ScanlineRender) rendered NOTHING headless; Nuke 17's 3D (Camera3 + GeoCard
  + ScanlineRender2) works.
* `world_matrix` must be read with `knob.valueAt(frame, i)` (row-major 4x4, translation in the last column);
  `knob.value(i)` returned uninitialised numbers.
* Projection = st_roto.cameras (intrinsics from focal / haperture, square pixels; window translate in half image
  widths, moving the WINDOW so content moves the other way - my first sign was wrong: a constant 48/29 px offset on
  camera C) : 14 points on 3 cameras (toe-in, roll, vertical offset, window translate, focal 30 / 35) within
  **0.33 px** of Nuke's render (one card clipped by the image edge: 2.4 px).

## 2. Test shot (`make_multicam.py`)

Ray-cast through those three measured cameras: background plane (z = -15), distractor disc (z = -8), textured target
ellipse (z = -5) moving and rotating; 16 frames, 960x540. In view B the target is partly outside the image on frames
0-4 (41-81 % visible).

## 3. Correspondence (`probe_correspondence.py`, view A -> B / C, every frame; scored against the exact projection of
the target's 3D centre, which the clipped-visible centroid is not)

| | B (toe-in 4°, roll 2.5°) | C (roll, offset, focal 30 vs 35, window shift) |
|---|---|---|
| T-109 horizontal search (rectified assumption) | transferred box IoU >= 0.8 on 0/16 frames | 0/16 |
| T-120 epipolar search, plain SSD, ±25 % window | 5/16 (true shifts reach -265 px) | 4/16 |
| + whole line, top-5 refinement, NCC | centre within 5 px on 15/16 | 16/16, but match ambiguity 0.995 (weak) |
| **+ scale-aware (each candidate compared at the scale its depth implies)** | **15/16** (median 1.3 px); frame 0: 41 % visible, fails | **16/16** (median 0.84 px, mean centroid error 0.61 px) |

Each step was a measured failure first: a fixed ±25 % window missed shifts of -265 px; the coarse 16 px grid ranked
a wrong place first; plain SSD preferred flat background when C saw the object 11 % smaller; and in Nuke the
product's AI mask tipped that weak match to a wrong place (view C tracked the wrong object, IoU 0) until the scale-
aware comparison.

## 4. In Nuke (`tests/nuke` `test_multicam_cameras`)

Views A, B, C (one Read with %V), Camera3 nodes per view, knob *cameras* `A=CamA, B=CamB, C=CamC`, box prompt in A on
frame 5, track every view: B found at shift -259/+35 px (scale 0.995), C at +102/+39 px (scale 0.892 - the truth);
IoU vs truth A 0.9932, B 0.9924, C 0.9931 (min 0.987); epipolar distances of the AI tracks <= 3.8 px: no flags (the
rectified-rig vertical / size rules are switched off for camera-known pairs, which violate them legitimately); an
artist key with the WRONG object in view C on frame 10: 'Check views (cameras)' flags exactly frame 10 (120 px off
its epipolar line).

## Limits (honest)

* Synthetic scene only; real multi-camera footage with truth not available. Objects more than about half outside a
  view are not found there (B frame 0).
* One shift + one scale per object (a box prompt); strongly slanted or very deep objects across views are left to
  the AI tracking on each view's own pixels.
* Camera nodes are named per view or one node with split views (the split-knob path is implemented, not tested).
