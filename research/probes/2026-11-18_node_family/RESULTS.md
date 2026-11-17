# Node family (T-112, REQ-040 / REQ-292) — 2026-11-18

Nuke 17.1v3 Non-commercial, headless. Design and naming: `docs/RESEARCH_2026-11-18_NODE_FAMILY.md`.

## Node budget rules (`probe_budget.py`, one case per Nuke process)

| Case | Remaining of 10 |
|---|---|
| fresh session | 10 |
| 1 node created + 3 `toNode` of it | 6 (each look-up costs 1) |
| 5 nodes created, deleted, `gc.collect()` | 5 (nothing freed) |
| `nodePaste` of a group with 4 inner nodes | 9 |
| ... + 1 `toNode` | 8 |
| gizmo (`pluginAddPath` + `createNode`) | 9 (gizmos work in NC) |
| a PyScript button executed 4× using `nuke.thisNode()` | no extra cost measured |

## ST_RotoMatte inner graph (`probe_matte_graph.py`)

CG plate (RGB, alpha 1, depth, vectors, N, P, Cryptomatte) + matte EXRs (target, distractor, combined A):
* before rendering (Switch on `stroto_ready` = 0): every channel identical to the input (max diff 0.0);
* after: alpha = combined matte (0.0), `target.A`, `distractor.A` = the EXR layers (0.0), plate RGB and every
  other plate layer unchanged (0.0).
* First product run found a bug: the pasted pixel Write had no file name ("You must specify a file name"). Fixed:
  `nodePaste` returns the last pasted node (the Write), which is configured and cached at creation - so rendering
  needs no look-up either.

## Main ST_Roto rebuilt by paste (`probe_main_budget.py track`)

Counted Node objects obtained: before, creating ST_Roto cost 6; now 3 (Group, paste, one Roto look-up). In one
fresh session: Read, ST_Roto, box prompt, Track (CUDA), Render mattes, ST_RotoMatte create + render, ST_RotoOutput
create + export → **5 of 10 left** (`budget_left_after_all`).

## Product test (`tests/nuke` `test_node_family`)

One session: ST_Roto tracks 2 objects (one set to holdout); ST_RotoMatte: validation messages (no shot; wrong shot
→ lists Read1; unknown object; role filter with no object), Check, render (guided): output alpha vs truth IoU
0.9999, `target.A` 0.9999, holdout layer present, plate RGB unchanged (0.0); role filter 'holdout' → only `disc.A`;
ST_RotoOutput: export (JSON + 8 SVG), delivery package; 5 node objects left.
