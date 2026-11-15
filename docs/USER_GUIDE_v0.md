# ST-ROTO v0 — trying it in Nuke (pre-alpha)

**Status: pre-alpha development build.** Several objects per node, Track forward from each prompt, Re-track in both directions; Nuke 17.1 on Windows with an NVIDIA GPU (CPU works but is slow). Tested on one synthetic shot. Nothing here is production-ready.

## Requirements on this machine

- Nuke 17.1 (Non-commercial works, within its limits: 1920×1080 max, 10 Python-accessible nodes per session)
- `D:\ST-ROTO` with the development set-up from this repository (`.tools\nuke-py311` packages, exported models in `models\onnx\`). Model weights are not in the repository; see `tools/models/`.

## Enable the plugin (your choice: changes your Nuke set-up)

Option A, environment variable for your user: set `NUKE_PATH` to `D:\ST-ROTO\nuke_plugin` (append with `;` if it already has a value).
Option B: add this line to `%USERPROFILE%\.nuke\init.py` (create the file if needed):

```python
nuke.pluginAddPath("D:/ST-ROTO/nuke_plugin")
```

Restart Nuke. You should see **Nodes › ST-ROTO › ST_Roto** and the pane **ST-ROTO Objects** (Windows › Custom).

## Workflow

1. Save your script (the project file defaults to `<script>.stroto` next to it).
2. Select your Read node, then **Nodes › ST-ROTO › ST_Roto**. View the ST_Roto node.
3. Type an **object name** (e.g. `hero`). Go to the frame you want to prompt on, drag the **point** handle in the viewer onto the object and press **+ Include**. Add **− Exclude** points on things that must not be included. Each object's points must be on one frame.
4. More objects: change **object name** (e.g. `car`) and add points for it, on any frame. The line under the points lists every prompted object. **Clear points** clears the named object, **Clear all** clears every object.
5. **Preview** shows the AI shape of the named object on its prompt frame (temporary).
6. **Load model** once per Nuke session (Nuke pauses for a few seconds once), then **Track**. All prompted objects are tracked in one pass (each frame is analysed once), forward from each object's prompt frame. The status line shows progress; **Cancel** stops it. The whole pass is **one undo step**. Objects already tracked are skipped (status says so): use Re-track for them.
7. The result is one native, animated Roto shape per object inside the ST_Roto node (`hero_st…`), editable like any Roto shape, and recorded in the project file with AI provenance.
8. Fix a frame by editing the shape in the Roto node (or draw a shape by hand), then **Re-track object** (the named object) or **Re-track all** (every unlocked object, one pass). Your keys are kept exactly; AI fills the other frames forward and backward from them.
9. The status ends with **REVIEW lost …** (object missing: fix these) or **check …** (uncertain: glance) where the AI was unsure.
10. **ST-ROTO Objects** pane: press *Use selected ST_Roto node* (with the node selected) to list objects; rename, lock/unlock, delete, undo, redo.

## Things to know

- Shapes you edit directly in the Roto node are **never** overwritten or removed by ST-ROTO; such a shape is reported as "NOT updated (edited in Roto)". **Save Roto edits to project** (or any Track / Re-track) records your edits in the project, undoably.
- The colour conversion for the AI input assumes Nuke's default linear sRGB working space (not ACES yet).
- If you see "Nuke returned no node … 10 nodes per session", save, reopen the script and try again (Non-commercial limit).
- Report problems with the status text and the Script Editor output.
