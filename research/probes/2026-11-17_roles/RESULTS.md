# T-098 — Holdouts, garbage mattes and merging objects (REQ-082 / REQ-100), 2026-11-17

## How Nuke 17.1's Roto combines shapes (measured, `probe_blend.py`, `probe_attrs.py`, `result_blend.json`)

- Shape attributes: blend mode `bm` (`kBlendingModeAttribute`), invert `inv` (`kInvertedAttribute`). `getValue`
  returns 0 for ANY name, even invented ones, so it cannot be used to discover names; the `k...Attribute` constants
  give the real ones.
- Attribute changes made from Python after a render are NOT re-rendered until `curves.changed()` is called (Nuke's
  render cache).
- The FIRST item of a Roto layer is drawn on top; a shape's blend mode only acts where the shape is.
- Blend mode 12 subtracts ("minus") and can go negative (B over nothing -> -1); 7/9 add (overlap 2); 11/13/14 give
  0 on the overlap and 1 elsewhere. No mode limits the area OUTSIDE a shape, so a garbage matte needs an inverted
  shape.

**Recipe (exact, no negative alpha):** holdout = shape with blend `minus` on top; garbage = INVERTED shape with
blend `minus` on top; a `Clamp` (alpha 0-1) after the Roto. ST-ROTO's EXR combine (`st_roto.views.combine_roles`)
uses the same arithmetic: add objects composited over each other (a + b - ab), minus every holdout, minus (1 -
garbage) for every garbage object, clamped. Several garbage objects: the matte is kept only inside ALL of them.

## Feature

- Object **role** (schema v10, `objects.role`: add / holdout / garbage), undoable, validated, kept by JSON
  export/import; node: *object role* + **Set role** (not hidden with AI off); object panel: *role* column, **Role...**.
- Combined matte (`rgba.alpha` of the EXRs, `settings.roles` in the header) and Nuke's own render follow the roles;
  each object's own EXR layer stays raw.
- New ST_Roto nodes contain `STROTO_clamp` after their Roto; older nodes get it the first time a role is set.
- **Merge into...** (panel; `views.merge_ops`): the object's shapes move to another object (keys, feather,
  provenance unchanged), the empty object is deleted; one undo step.

## Evidence

`tests/nuke` `test_roles_and_merge` (`results_test_roles_and_merge.json`): hand-drawn actor, a pole (holdout)
crossing it, an area (garbage) covering its left part. Layer order pole, area, actor; blends (12,0), (12,1), (0,0);
Nuke's render within [0, 1]; **Nuke render vs ST-ROTO EXR IoU 0.9987**; vs the expected matte 0.9974 (Nuke) /
0.9982 (EXR). Merge pole into actor: no longer cut out (0.9982); undo restores the holdout (0.9974).
Unit: `tests/unit/test_roles_merge.py` (validation + undo, the combine arithmetic incl. soft values, EXR layers
raw + combined, merge + undo, JSON round trip).

## Not covered

Soft-edge (guided / ViTMatte) combined mattes were only checked by the unit arithmetic, not against Nuke's render
(Nuke composites the hard shapes; soft edges exist only in the EXRs). Holdouts per OBJECT (cutting only one other
object rather than the combined matte) are not supported.
