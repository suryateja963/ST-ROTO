# Alembic export (T-113, REQ-180 "Alembic where suitable") — 2026-11-18

Nuke 17.1v3 Non-commercial, headless.

## How to write Alembic here (measured, `probe_usd_abc.py`)

* No Alembic Python bindings ship with Nuke or the project venv (the PyPI package named "alembic" is an unrelated
  database tool). Nuke 17.1 bundles **USD 0.25.8** (`pxr`, `FnUSD`) with its Alembic file-format plug-in
  (`UsdAbc`): `Sdf.FileFormat.FindByExtension("abc")` is available, and exporting a stage to `.abc` writes a genuine
  Alembic file (Ogawa signature `4f67617761`).
* usdAbc stores each prim as an Xform with a shape child (`/a/b_curve` reads back as `/a/b_curve/b_curveShape`) and
  adds a sample at time 0 equal to the first sample (a hold before the first frame; harmless).
* Nuke 17 reads `.abc` with the new USD-based 3D system (`GeoImport`; Nuke's own `create.py` routes `.abc` there,
  classic ReadGeo2 now handles `.fbx` / `.obj`). Nuke's documentation lists meshes, point clouds, cameras and
  transforms for Alembic import - NOT curves. So ST-ROTO writes both:

## Format written (`st_roto_nuke.alembic`, `st_roto.geomexport`)

`/st_roto/<object>/<shape>_curve`: BasisCurves, cubic Bezier, periodic: the exact spline (3 control points per
anchor: point, out-handle, next point's in-handle). `/st_roto/<object>/<shape>_mesh`: one outline polygon (16 samples
per segment, counter-clockwise = front towards +z). Pixel units, y up, origin bottom-left, z = 0 (= Nuke's Roto
coordinates); one time sample per keyed frame at the script's fps; collapsed part keys (piece absent) are
`invisible` on that frame.

## Verified

| Check | Result |
|---|---|
| USD read-back of curves and meshes vs st_roto.geomexport of the stored keys | max error 1.5e-5 - 3.0e-5 px (float32) |
| Part shape collapsed on frame 3 | invisible on 3, visible on 2 and 4 (both prims) |
| **Nuke's own 3D** (GeoImport + orthographic Camera3: focal 1, apertures = image size, + ScanlineRender2) renders the exported meshes vs ST-ROTO's exact raster of the splines | IoU **0.9999** on frames 1, 3, 5 (product test; probe the same) |

## Not verified (honest)

* No independent Alembic implementation was available on this machine: the file is written AND read by USD's
  usdAbc (Nuke 17 also reads .abc through it). Opening the file in Houdini / Maya / Blender is untested (T-118: needs
  those applications or the owner).
* Older Nuke versions without USD cannot export Alembic; the button then says why (`alembic.available()`).
