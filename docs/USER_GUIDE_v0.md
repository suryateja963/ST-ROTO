# ST-ROTO v0 — trying it in Nuke (pre-alpha)

**Status: pre-alpha development build.** One object per Track, forward tracking only, Nuke 17.1 on Windows with an NVIDIA GPU (CPU works but is slow). Tested on one synthetic shot. Nothing here is production-ready.

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
3. Go to the frame you want to prompt on. Drag the **point** handle in the viewer onto the object, press **+ Include**. Add **− Exclude** points on things that must not be included.
4. **Preview** shows the AI shape for that frame (temporary).
5. **Load model** once per Nuke session (Nuke pauses for a few seconds once), then **Track**. The status line shows progress; **Cancel** stops it.
6. The result is a native, animated Roto shape inside the ST_Roto node (`object1_st…`), editable like any Roto shape, and recorded in the project file with AI provenance.
7. **ST-ROTO Objects** pane: press *Use selected ST_Roto node* (with the node selected) to list objects; rename, lock/unlock, delete, undo, redo.

## Things to know

- Shapes you edit directly in the Roto node are **never** overwritten or removed by ST-ROTO; such a shape is reported as "NOT updated (edited in Roto)". Your edits are not yet read back into the project (planned).
- The colour conversion for the AI input assumes Nuke's default linear sRGB working space (not ACES yet).
- If you see "Nuke returned no node … 10 nodes per session", save, reopen the script and try again (Non-commercial limit).
- Report problems with the status text and the Script Editor output.
