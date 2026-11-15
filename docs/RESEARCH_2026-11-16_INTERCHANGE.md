# Interchange formats — research and status (2026-11-16)

Master prompt §20 asks for interchange with Nuke Roto, RotoPaint, EXR, SVG, JSON, Alembic, Silhouette, Mocha and other standards, preserving names, identity, hierarchy, animation, keys, feather, metadata, channels and coordinates.

| Format | Status | Preserves | Verified by |
|---|---|---|---|
| Nuke Roto (native shapes) | **Done** (T-053..T-064): animated native shapes, editable without ST-ROTO; edits read back | names, keys, animation (feather: not yet stored by ST-ROTO) | tests/nuke (render IoU, round trip) |
| EXR mattes | **Done** (T-070): one file per frame, `<object>.A` per object + combined `A`; ZIP; settings in header attribute `st_roto` | object identity (layer names), soft alpha | Nuke reads layers as `<object>.alpha`, combined as `rgba.alpha`; values exact (tests/nuke `test_render_mattes_exr`) |
| ST-ROTO JSON (`st_roto.shapes` v1) | **Done**: full fidelity, re-importable (new ids, one undo step, imported origin) | ids, names, hierarchy, colours, locks, provenance of objects/shapes/keys, generator records, every key, explicit coordinate statement | unit round trip; Nuke export → delete → import (point error 1.5e-5 px) |
| SVG | **Done**: one file per keyed frame, `<g>` per object, cubic `<path>` per shape, ids/names/origins as attributes | geometry per frame (SVG has no animation model used here) | unit: valid XML, path numbers exact |
| Nuke RotoPaint | Not started | — | — |
| Silhouette | **Indirect only.** No published file specification found; Silhouette exports Nuke Roto shapes itself (Boris FX docs), and ST-ROTO imports native Roto shapes drawn or pasted into its Roto node as artist objects (T-063). Direct `.sfx` write would be reverse-engineering an undocumented format | — | not testable here (no Silhouette licence) |
| Mocha Pro | **Indirect only.** Mocha exports Roto / RotoPaint / SplineWarp to Nuke and has a Python `AbstractShapeDataExporter` for custom formats (could export ST-ROTO JSON from inside Mocha). No public Mocha project format spec | — | not testable here (no Mocha licence) |
| Alembic (curves) | Deferred: needs the Alembic C++ library's Python binding (no maintained Windows wheel found); value for 2D roto is limited | — | — |

Feather: ST-ROTO does not store per-point feather yet, so no exporter carries it (to add with feather editing).

## Sources

- Silhouette export formats: https://support.borisfx.com/hc/en-us/articles/8803471683981-What-shape-formats-can-Silhouette-export ; https://borisfx.com/documentation/silhouette-2026.0/Silhouette-2026/Preferences-Input%20Output.html
- Mocha exporters: https://borisfx.com/documentation/mocha/12.5.0/python-reference/mocha/exporters/AbstractShapeDataExporter.html ; https://borisfx.com/documentation/mocha/2026.0.0/python-guide/
- OpenEXR Python binding (BSD-3-Clause): https://pypi.org/project/OpenEXR/
