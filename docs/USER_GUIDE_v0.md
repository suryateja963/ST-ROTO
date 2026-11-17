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
   **Box (recommended for parts of something bigger, e.g. a sleeve, a bag, one person in a group):** drag the corners of the **box** rectangle in the viewer around the object and press **Set box**, then add include/exclude points if needed. Measured on real footage (51 tests, SA-V):

   | prompt | wrong object at the start | mean IoU over the shot |
   |---|---|---|
   | 1 click | 19 of 51 | 0.54 |
   | 3 clicks | 13 of 51 | 0.58 |
   | box only | 2 of 51 | 0.67 |
   | box + 1 click | 2 of 51 | 0.68 |

   A click alone is as good as a box when it picks the right object (check with **Preview**); the box mainly stops SAM choosing a different object or part. Recommended: a box plus one include click. **Clear box** removes only the box; **Clear points** removes the object's box and points.
4. More objects: change **object name** (e.g. `car`) and add points for it, on any frame. The line under the points lists every prompted object. **Clear points** clears the named object, **Clear all** clears every object.
5. **Preview** shows the AI shape of the named object on its prompt frame (temporary).
6. **Load model** once per Nuke session (Nuke pauses for a few seconds once), then **Track**. All prompted objects are tracked in one pass (each frame is analysed once), forward from each object's prompt frame. The status line shows progress; **Cancel** stops it. The whole pass is **one undo step**. If you cancel, or Nuke crashes, **Resume track** continues where it stopped (same result as an uninterrupted run). Objects already tracked are skipped (status says so): use Re-track for them.
7. *points* (default auto) sets how many points each shape has; auto picks the fewest that follow the outline. Measured on real footage, auto loses less than 0.003 IoU against the AI's own mask, and 48 or 64 points add almost nothing, so keep auto unless you need more points to edit. *model*: `sam2.1-hiera-large` was clearly more accurate than the default `tiny` on real footage (mean IoU 0.736 vs 0.683 over 51 tests, mostly because it loses the object less often) and about 1.4× slower; use it for difficult shots. If an object splits into pieces (e.g. cut by something passing in front), each extra piece becomes a part shape (`hero_part2`), invisible on frames where it does not exist.
8. The result is one native, animated Roto shape per object inside the ST_Roto node (`hero_st…`), editable like any Roto shape, and recorded in the project file with AI provenance.
8. Fix a frame by editing the shape in the Roto node (or draw a shape by hand), then **Re-track object** (the named object) or **Re-track all** (every unlocked object, one pass). Your keys are kept exactly; AI fills the other frames forward and backward from them.
   **Quicker fix without drawing — Re-prompt here:** go to a frame the review flags list (or that looks wrong), drag the **box** around the object on that frame and press **Re-prompt here** (tick **with point** to also use the point handle as an include click). The named object is re-tracked in both directions with that box as an extra guide; the fix is kept for later re-tracks and the whole re-prompt is one undo step. A frame that already has your own key is guided by that key: edit the key instead.
9. The status ends with **REVIEW lost …** (object missing: fix these) or **check …** (uncertain: glance) where the AI was unsure.
10. **Mattes:** *matte size*: **full resolution** or **fit 1920x1080** (default in Nuke Non-commercial; full resolution is the default in other editions) (computed at full resolution, then area-averaged to fit 1920x1080; 3-11x smaller files, same accuracy measured; HD plates are never scaled). Choose *edges*: guided filter (no AI), **ViTMatte-S** (optional learned matting, better on hair and slightly inaccurate shapes; install with `tools/models/download_models.py vitmatte-small-composition-1k` then `tools/models/export_vitmatte_onnx.py`; its weights are Apache-2.0 but were trained on Adobe's Composition-1k data — check that suits your use) or hard. Older notes: set *soft edges* (on: a narrow band around each edge is refined against the plate, no AI model; off: hard mattes identical to the shapes), then **Render mattes (EXR)**. One EXR per frame in `<project>_mattes/<shot>/` (or *matte folder*): a layer per object (`hero.alpha` in Nuke) and all objects combined in `rgba.alpha`.
11. **Feather:** set a shape's feather in the Roto node as usual; ST-ROTO records it (undoable) and keeps it. EXR mattes approximate Nuke's feather (exact in Nuke's own render). **Copy shapes to RotoPaint** creates a RotoPaint node with native copies of every shape.
12. **Export shapes (JSON + SVG)** writes `<project>_export/<shot>/`: a JSON file with every object, key and its provenance (re-importable with **Import shapes (JSON)**, also into another project) and one SVG per keyed frame.
12. **Motion blur:** set *motion blur* to `global` (and *samples*, *shutter*) to have Nuke blur the shapes along their tracked motion.
13. **Back up now** snapshots the project into `<project>_backups/`. Automatic backups also run every 5 minutes while you work (only after changes) and when Nuke exits. If Nuke crashed or the project file is damaged, the status line says so the next time the project is opened; a damaged file is kept (`.damaged.<time>`) and the newest good backup is restored.
14. **Package project** writes a portable zip (project, mattes, exports, checksummed manifest; no model weights) next to the project. It includes your saved Nuke script. On the other machine use **ST-ROTO › Unpack project package…** (main menu): checksums are verified, plates that are not found are asked for (any frame of them), and every plate is checked against a fingerprint of the original footage, so the same plates in a new place are accepted and different footage with the same names is refused. Opening the unpacked script relinks its Read and ST_Roto nodes.
15. **ST-ROTO Objects** pane: press *Use selected ST_Roto node* (with the node selected) to list objects; rename, lock/unlock, delete, undo, redo.

## Things to know

- Shapes you edit directly in the Roto node are **never** overwritten or removed by ST-ROTO; such a shape is reported as "NOT updated (edited in Roto)". **Save Roto edits to project** (or any Track / Re-track) records your edits in the project, undoably.
- **AI input colour** (default *auto*) follows the script: Nuke's default linear sRGB, or with OCIO colour management (e.g. ACES) the working space converted through the script's OCIO config. Choose a space explicitly if your plates are, for example, already display-encoded. The choice is recorded with every AI result.
- **Formats and large plates:** any format Nuke reads works (measured: PNG/TIFF 16-bit, EXR half/float, DPX 10-bit, anamorphic pixel aspect). Nuke Non-commercial renders at most 1920x1080; for larger plates (2K, 4K, 8K, vertical) ST-ROTO lets the AI see frames reduced to fit and keeps the shapes at full resolution (status says so; measured IoU at 4K/8K equal to HD).
- **Without AI:** tick **disable AI (traditional roto only)** on the node (or set the environment variable `ST_ROTO_AI=off` for a whole Nuke session) and the AI controls disappear. Draw and edit shapes in the node's Roto, press **Save Roto edits to project**, and use mattes (guided filter or hard), export, RotoPaint copy, backups and packages as usual. This also works on a machine without the AI runtime installed.
- **Difficult sequences:** frames Nuke cannot read (missing files, gaps) are skipped and listed in the status (no key there; Roto interpolates; mattes get hard edges there). Frames of another resolution, and every frame in proxy mode, are fitted to the shot format like a default Reformat and listed; for mixed-resolution plates put a Reformat to the shot format above ST_Roto so plate and shapes line up. Proxy mode tracks on the proxy images (slightly less accurate: IoU 0.990 vs 0.995 measured); turn proxy off for final tracking. Start frames other than 0/1, negative frames, held (duplicate) frames and retimes upstream work as they are.
- **Offline:** ST-ROTO itself never uses the network (no telemetry; ONNX Runtime's Windows telemetry is switched off; measured, T-085). Nuke 17.1 Non-commercial itself contacts a server over HTTPS each time it starts; that is Nuke's behaviour, not ST-ROTO's, and it is not needed: with Nuke blocked by a firewall, Nuke and ST-ROTO work normally (measured, T-087).
- If you see "Nuke returned no node … 10 nodes per session", save, reopen the script and try again (Non-commercial limit).
- Report problems with the status text and the Script Editor output.
