# ST-ROTO node family: architecture and naming (T-112, REQ-040, master prompt section 6) — 2026-11-18

Section 6 lists ten "proposed functional modules" and asks to research the node architecture and naming before
implementing. This note records what was measured, how the modules map to nodes, and why. Evidence:
`research/probes/2026-11-18_node_family/` (Nuke 17.1v3 Non-commercial, headless).

## 1. Constraint: the Non-commercial Python node budget (measured)

| Action (fresh NC session) | Cost of the 10 Python-accessible Node objects |
|---|---|
| `nuke.nodes.X()` | 1 each |
| `nuke.toNode(name)` | 1 per CALL - looking up the same node three times costs 3 (the objects are identical) |
| deleting the Python reference + `gc.collect()` | frees nothing |
| `nuke.nodePaste(file)` of a group with 4 inner nodes | 1 (returns the last pasted node) |
| `.gizmo` via `nuke.pluginAddPath` + `nuke.createNode` | 1 (gizmos load in NC) |
| `nuke.thisNode()` inside button callbacks (4 executions) | no measurable cost |

Consequences: inner nodes must not be created one by one from Python, nor looked up repeatedly; a node's inner
graph is pasted, its buttons use `nuke.thisNode()`, and inner nodes are driven by knob expressions. The main
ST_Roto node itself was rebuilt this way: creation now costs **3** objects (was **6**: Group, Input, Roto, Clamp,
Output, Write each made from Python). A whole family workflow in one fresh session - Read, ST_Roto, Track, Render
mattes, ST_RotoMatte (+ render), ST_RotoOutput (+ export) - leaves **5 of 10** objects (`probe_main_budget.py`).

## 2. Naming

Nuke's own nodes use CamelCase class names; third-party tools use a vendor prefix so they group together in the
node menu and in scripts. ST-ROTO keeps the prefix it already uses (`ST_Roto`, D-012): `ST_Roto`, `ST_RotoMatte`,
`ST_RotoOutput`, all under Nodes › ST-ROTO. Inner nodes are prefixed `STROTO_` so scripts stay readable and
ST-ROTO finds them by name.

## 3. The ten modules → nodes

| Module (§6) | Where it lives | Why |
|---|---|---|
| 1 Main | **ST_Roto** | the hub: project link, shot, objects (D-012 single-node core) |
| 2 Select | ST_Roto (point / box / rough-mask / Cryptomatte prompts) | prompts need the tracker and the node's viewer handles (XY/BBox knobs); a separate node would add a graph hop and budget cost for no new output |
| 3 Track | ST_Roto (Track, Re-track, Re-prompt, ranges, locks) | the tracker state and the Roto shapes are one unit |
| 4 Matte | **ST_RotoMatte** | NEW: renders ST-ROTO's mattes and brings them into the node graph (alpha = combined, one layer per object, plate RGB and every other channel unchanged) |
| 5 Spline | ST_Roto's native Roto shapes (+ Copy to RotoPaint) | shapes are native Nuke Roto (REQ-041): editable without ST-ROTO |
| 6 Refine | ST_RotoMatte's refine settings (guided / ViTMatte / hard, offset, blur, core/edge) | refinement only exists as a matte operation (shapes are never changed by it) |
| 7 Holdout | ST_RotoMatte's role filter (holdout / garbage / add) + object roles (T-098) | a holdout IS a matte of the holdout objects; one node type with a filter avoids two near-identical nodes |
| 8 Deep | not a node yet | Deep-sample-native operations need the NDK (T-011b, D-011); Deep holdouts can be made today with Nuke's DeepHoldout from an ST_RotoMatte output |
| 9 Stereo | ST_Roto (track every view, per-view objects, consistency flags, T-109); ST_RotoMatte renders per view (%V) | stereo is a property of tracking and mattes, not a separate image operation |
| 10 Output | **ST_RotoOutput** | NEW: shape export (JSON + SVG), delivery package, project package, backup for a shot |

So three node types: ST_Roto, ST_RotoMatte, ST_RotoOutput. Each has: clear responsibility (above), validated
inputs (project file exists, shot exists in the project - else the shots it has are listed, object names exist,
role filter not empty), outputs documented in its tooltips and the user guide, errors in its status line.

## 4. How the family nodes connect

They are linked by DATA, not by wires: each names a project file and a shot (the name of the node feeding the
ST_Roto node). Made from the menu with an ST_Roto node selected, they copy both. So an ST_RotoMatte can sit
anywhere downstream (or in another script opening the same project), and several can render different objects or
roles of one shot. Artist edits made in the ST_Roto node's Roto are recorded by that node (Save Roto edits /
Track / Re-track); the family nodes read the project as it is.

## 5. Not done / open

* Commercial editions: D-012 foresees the full family there (plug-in nodes via the NDK, T-011b).
* Deep module: NDK (T-011b).
* A gizmo distribution (.gizmo files) was measured to work in NC, but the Python-built groups are kept: their knobs
  and callbacks come from the installed ST-ROTO version, so no gizmo files must be kept in step.
