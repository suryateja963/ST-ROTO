# Roto feather and RotoPaint (T-073) — 2026-11-16

**API (measured, Nuke 17.1).** Shape attributes `fx`, `fy` (feather, px), `ff` (falloff), `fo` (feather on), `ft` (type); `Attributes.set("fx", v)` sets a static value (no key). Points also have `featherCenter` / `featherLeftTangent` / `featherRightTangent` (default 0). RotoPaint's `curves` is the same `RotoKnob` type: shapes built for Roto work unchanged.

**Nuke's feather render** (`probe_feather_profile.py`, `result.json`): alpha(falloff 2) = alpha(falloff 1)² exactly (0.404² = 0.163, 0.79² = 0.624, 0.577² = 0.333). The 50 % contour lies at half the feather in every direction. The ramp's tails are not a closed form: feather 25 is nearly linear and ends at ~0.92 × feather; feather 12 on a 12-point circle is narrower (~8.5 px) and varies with the angle with the period of the control points.

**ST-ROTO's EXR matte approximation** (`st_roto.matte.feathered_alpha`: 1 − d / (0.92 · feather), raised to the falloff) vs Nuke's own render (`tests/nuke` `test_feather_and_rotopaint`, circle r = 150, feather 12): area ratio 0.998, 50 % contour within 1.0 px at every 10°, mean |error| in the feather band 0.109, max 0.45. A model building the feather curve from control points offset along their normals was tried and was not better (0.113) and was removed. **Nuke stays authoritative**: for exact feathered mattes render the ST_Roto output in Nuke.

**Round trip in Nuke.** Hand-drawn shape with feather 12 → imported with its feather; feather changed to 20 in Roto → imported (undoable); undo → Roto back to 12. 'Copy shapes to RotoPaint' → RotoPaint render identical to the Roto render (max |difference| 0.0).
