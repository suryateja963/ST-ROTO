# ST-ROTO User Manual

For ST-ROTO 0.1.x (pre-release) in Foundry Nuke. Written for compositors and roto artists. It describes the current source code: **scene cuts (section 9) and AMD / Intel GPUs via DirectML (section 20) are not in the 0.1.0 download**, they come with the next release.

ST-ROTO tracks objects through a shot with AI (SAM 2.1) and turns them into **native, animated Nuke Roto shapes**, plus multi-layer EXR mattes. Every AI feature can be switched off: the same node then works as a traditional roto tool with project management, mattes and exports.

> **Status:** pre-release, not production-ready. It has been tested on Nuke 17.1 Non-commercial on Windows, using synthetic test shots and public benchmark footage. Every measured number below has its evidence in `research/probes/`. What is still missing for 1.0 is listed in `docs/ACCEPTANCE.md`.

## Contents

1. [Concepts](#1-concepts)
2. [Installing and checking your machine](#2-installing-and-checking-your-machine)
3. [The ST_Roto node at a glance](#3-the-st_roto-node-at-a-glance)
4. [Your first track](#4-your-first-track)
5. [Prompts: telling the AI what to track](#5-prompts-telling-the-ai-what-to-track)
6. [Tracking](#6-tracking)
7. [Reviewing the result](#7-reviewing-the-result)
8. [Correcting: re-track, re-prompt, lock, exclude](#8-correcting-re-track-re-prompt-lock-exclude)
9. [Scene cuts](#9-scene-cuts)
10. [Traditional roto (AI off)](#10-traditional-roto-ai-off)
11. [Shapes: points, feather, motion blur, roles](#11-shapes-points-feather-motion-blur-roles)
12. [Mattes](#12-mattes)
13. [Exports and hand-off](#13-exports-and-hand-off)
14. [Project safety: backups, recovery, packages](#14-project-safety-backups-recovery-packages)
15. [CG plates: extra channels, Cryptomatte, motion vectors](#15-cg-plates-extra-channels-cryptomatte-motion-vectors)
16. [Stereo and multi-camera](#16-stereo-and-multi-camera)
17. [The node family: ST_RotoMatte and ST_RotoOutput](#17-the-node-family-st_rotomatte-and-st_rotooutput)
18. [Panes: Objects and Models](#18-panes-objects-and-models)
19. [Presets](#19-presets)
20. [Graphics cards, models and performance](#20-graphics-cards-models-and-performance)
21. [Working with others (prototype)](#21-working-with-others-prototype)
22. [Reference](#22-reference)
23. [Troubleshooting](#23-troubleshooting)

---

## 1. Concepts

| Term | Meaning |
|---|---|
| **Project file** (`.stroto`) | ST-ROTO's own record of your work: shots, objects, shapes, every key and its history. It is saved next to your Nuke script by default (`<script>.stroto`), backed up automatically and can be packaged. |
| **Shot** | One source (the Read node, or whatever feeds ST_Roto) with its frame range and format. |
| **Object** | One thing you rotoscope, for example `hero` or `car`. It has a **role** (add, holdout or garbage) and can be locked or leased. |
| **Shape** | An object's animated spline. The **main shape** is named after the object. If the object splits into pieces (for example when something passes in front of it), extra **part shapes** (`hero_part2`) appear, and they are invisible on frames where that piece doesn't exist. |
| **Key** | The shape on one frame. Every key records where it came from: **AI**, **artist** (drawn by you), **artist-modified AI**, or **imported**. |
| **Prompt** | What you give the AI so it knows what to track: clicks, a box, or a rough mask, on one frame. |
| **Review flags** | Frames where the AI was unsure. **REVIEW lost** means the object was not found (fix these). **check** means the result is uncertain (glance at these). |

Two rules hold everywhere:
- **Your work wins.** ST-ROTO never overwrites or deletes a key you drew or edited. A shape you changed directly in Roto is reported as "NOT updated (edited in Roto)" rather than replaced.
- **One action is one undo step.** That applies to a whole Track, a Re-track or a Merge.

## 2. Installing and checking your machine

The full installation guide, including Nuke versions and editions, studios and the command line, is `docs/INSTALL.md`. In short:
1. Download `ST-ROTO-Setup.exe`, `ST-ROTO-<version>.zip` and, if you want them, the model packages, all into one folder.
2. Run the .exe and choose **1**.
3. Restart Nuke.

Then check your machine:
- **ST-ROTO › System report…** (main menu) lists what this machine and Nuke edition can do:
  - the graphics card and which AI runtime is active (CUDA or DirectML);
  - the installed models and whether each fits in GPU memory;
  - the edition's limits (render size, node budget).

  Include this report whenever you report a problem.
- **Windows › Custom › ST-ROTO Models** offers **Verify** (checks every model file) and **Self-test** (accuracy and speed on this machine).

To update or remove ST-ROTO, run the same setup: 2 repairs, 3 rolls back, 4 uninstalls.

## 3. The ST_Roto node at a glance

Create the node with **Nodes › ST-ROTO › ST_Roto**, with your Read node selected. Its panel has these sections, from top to bottom:

| Section | What is there |
|---|---|
| top | **project file**, **object name** |
| **prompts** | **point** handle and **box** in the viewer; **+ Include**, **− Exclude**, **Clear points**, **Clear all**, **Set box**, **Clear box**; *prompt from* / *source* / **Use as prompt** for rough masks; the line listing every prompted object |
| **AI** | **disable AI** tick box; *model*, *device*, *points*, *AI input colour*; **Load model**, **Preview**, **Track**, **Cancel**, **Resume track**; **Re-track object**, **Re-track all**, **Re-track flagged**, *re-track model*; *re-track range* (whole shot / from-to), **Lock range**, **Unlock range**; *exclude frames*; *scene cuts*, *stop at scene cuts*, **Detect cuts**; stereo options; **Re-prompt here**; **Reduce chatter** |
| **mattes** | *edges*, *soft edges*, *matte size*, *RGB in mattes*, *spill*, *edge offset*, *edge blur*, *core/edge width*, *object role* / **Set role**, *matte folder*, **Render mattes (EXR)** |
| output buttons | **Save Roto edits to project**, **Export shapes (JSON + SVG)**, **Export Alembic**, **Copy shapes to RotoPaint**, **Import shapes (JSON)**, **Back up now**, **Package project**, **Delivery package**, **System report** |
| **status** | what the last action did, including review flags and warnings. Read it after every action. |
| **motion blur** | Nuke's own Roto motion blur for the shapes |
| **extra channels** | channel list, Cryptomatte and motion-vector tools (CG plates) |
| presets, **review in viewer** | settings presets; **Show shapes in viewer**, *review colours on shapes*, *this frame* |

The node contains a normal Nuke **Roto** node with your shapes. Open the group (Ctrl+Enter) to edit shapes with Nuke's own tools. The node's output is your plate, with **alpha replaced by the shapes**, and every other channel passed through unchanged.

## 4. Your first track

1. **Save your Nuke script.** The project file goes next to it.
2. Select the Read node, then choose **Nodes › ST-ROTO › ST_Roto**. View the ST_Roto node.
3. Type an **object name**, for example `hero`.
4. Go to a frame where the object is clearly visible.
5. Mark the object. A box plus one click works best:
   - drag the corners of the **box** in the viewer around the object and press **Set box**;
   - drag the **point** handle onto the object and press **+ Include**.
6. Press **Preview**. The AI's selection on this frame appears as a temporary shape. If it's wrong, add **− Exclude** points or adjust the box.
7. Press **Load model** once per Nuke session. Nuke pauses for a few seconds.
8. Press **Track**. The status line shows progress, and **Cancel** stops the run.
9. Read the status line. It reports the number of keys, any review flags (**REVIEW lost …**, **check …**) and the device used.

Your object is now an animated Roto shape (`hero_st…`) inside the node.

## 5. Prompts: telling the AI what to track

**Clicks and box**

Measured on 51 real benchmark shots (SA-V):

| prompt | wrong object at the start | mean IoU over the shot |
|---|---|---|
| 1 click | 19 of 51 | 0.54 |
| 3 clicks | 13 of 51 | 0.58 |
| box only | 2 of 51 | 0.67 |
| box + 1 click | 2 of 51 | 0.68 |

- A correct click is as good as a box. The box mainly stops the AI choosing a neighbouring object or a part of the object.
- Use a box for parts of something bigger (a sleeve, a bag, one person in a crowd).
- All of an object's prompts must be on **one frame**.
- **Clear box** removes only the box. **Clear points** removes the named object's box and points. **Clear all** clears every object.

**Several objects.** Change *object name* and prompt the next object, on any frame. The line under the prompts lists every prompted object. A single **Track** tracks them all in one pass, and each frame is analysed once.

**Rough masks.** Instead of clicks you can give a rough mask:

| *prompt from* | *source* |
|---|---|
| Roto shape | the name of a shape you drew in the node's Roto (a quick polygon is enough) |
| mask node | the name of another node whose alpha holds the mask |
| mask file | an image file path (`####` = frame number) |
| Cryptomatte | Cryptomatte name(s), comma separated (CG plates; see section 15) |

Go to the frame, press **Use as prompt**, then **Track**. ST-ROTO makes a box and an include click from the mask, and the AI draws the exact shape. Measured: a rough square around an object was tracked at IoU 0.985.

## 6. Tracking

- **Track** tracks every prompted object **forward** from its prompt frame to the end of the shot. Objects that are already tracked are skipped; use Re-track for them.
- **Cancel** stops the run, and **Resume track** continues where it stopped. The same applies after a crash. The result is identical to an uninterrupted run.
- *model*:
  - **auto (by free GPU memory)** uses `sam2.1-hiera-large` when it fits in the GPU memory that is free now, otherwise `tiny`, otherwise the CPU.
  - On real footage large was clearly more accurate: mean IoU 0.736 against 0.683, mostly because it loses the object less often. It is about 1.4× slower.
  - If a model you chose doesn't fit in GPU memory, it runs on the CPU (slowly) and the status says so. If the GPU runs out of memory during a run, ST-ROTO continues on the CPU.
- *device*: **auto** uses the GPU when possible; **cpu** forces the processor.
- *points* (default **auto**) is the number of points per shape. Auto uses the fewest points that follow the outline (within 0.003 IoU of the AI's own mask). 48 or 64 points add almost nothing, so keep auto unless you want more points to edit.
- *AI input colour* (default **auto**) follows the script: Nuke's default linear sRGB, or under OCIO (for example ACES) the working space. Set it explicitly if your plates are already display-encoded.
- **Large plates in Nuke Non-commercial.** That edition renders at most 1920×1080, so for larger plates the AI sees reduced frames. Shapes stay at full resolution, and accuracy was measured as equal to HD.
- **Difficult sequences:**
  - Missing or unreadable frames are skipped and listed.
  - Frames of another size, and proxy mode, are fitted to the shot format. Turn proxy off for final tracking: it was measured slightly less accurate (IoU 0.990 against 0.995).
  - Negative frames, held frames and retimes work as they are.

## 7. Reviewing the result

- **Status line.** It ends with **REVIEW lost …**, listing frames where the object is missing (fix these), and **check …**, listing uncertain frames (glance at these).
- **Show shapes in viewer.** Shapes are drawn magenta on *lost* frames and yellow on *check* frames, with Nuke's red everywhere else. Untick *review colours on shapes* to keep Nuke's colours. *this frame* lists the flags of the frame in the viewer and the reasons for them.
- **Objects pane** (section 18). Its timeline shows each object across the shot: orange for your keys, grey for AI keys, blue for locked frames, and red or yellow marks for flags. Click the timeline to jump to a frame.

## 8. Correcting: re-track, re-prompt, lock, exclude

**Re-prompt here** is the quickest fix and needs no drawing:
1. Go to a bad frame.
2. Drag the **box** around the object and press **Re-prompt here**. Tick *with point* to also use the point handle as a click.

The object is re-tracked in both directions using this box as an extra guide. The fix is kept for later re-tracks.

**Edit and re-track:**
1. Fix the shape on one or a few frames in the node's Roto, or draw a key by hand.
2. Press **Re-track object** (the named object) or **Re-track all** (every unlocked object, in one pass).

Your keys are kept exactly as they are, and the AI fills the frames in between, forward and backward from them.

**Re-track flagged.** Set *re-track model* to `sam2.1-hiera-large` (or auto) and press **Re-track flagged**. Only objects with *REVIEW lost* flags are re-tracked, using the more accurate model. On the test shot this took 6 lost frames down to 0. A good habit: track everything with tiny first, then re-track the flagged objects with large.

**Limiting what changes:**

| Control | Effect |
|---|---|
| *re-track range* = from-to | Re-tracks change only those frames. The keys just outside the range guide the join. |
| *exclude frames* (for example `12-14, 30`) | The AI never processes or changes these frames (flashes, frames you roto by hand). |
| **Lock range** / **Unlock range** | The named object's keys on *from*..*to* are kept exactly. They also guide every later re-track. Undoable. |
| *stop at scene cuts* | Re-track stays inside the shot segment of the current frame (section 9). |

**Reduce chatter.** If an outline jitters from frame to frame, set *frames* (2 means a 5-frame window) and press **Reduce chatter** or **Reduce chatter (all)**. Each point's path is smoothed on AI frames, and your keys and locked frames don't change. Use it only where you see chatter:
- where edges really jittered it was measured to cut flicker by 41–48 %;
- on an already steady, fast-moving track it made results slightly worse (+12 % temporal error).

## 9. Scene cuts

An AI tracker shouldn't carry an object across a hard cut, because after the cut the pixels belong to another shot. ST-ROTO detects cuts and stops at them.

- *scene cuts* lists the frames that **start** a new shot, for example `48, 120`. You can type or correct the list yourself.
- **Detect cuts** looks at every frame of the source (small colour thumbnails, no AI) and fills the knob. Flashes and one-frame glitches are reported but are not counted as cuts.
- If the knob is empty, the first **Track** detects cuts by itself and fills the knob.
- With **stop at scene cuts** on (the default):
  - **Track** stops each object at the next cut after its prompt frame. Prompt the object again after the cut: it is a new shot.
  - **Re-track** works only inside the segment between cuts that holds the current frame, and never uses keys from across a cut as guides.
  - Untick it to work across cuts.
- **Measured on real footage** (30 SA-V videos, 2,846 frames sampled at 6 fps, so with about 4× the motion of a 24-fps plate):
  - all 30 joins between videos were found;
  - all 4 genuine camera cuts inside the videos were found;
  - there were 0 false cuts in 2,816 continuous frame pairs;
  - 0 flashes or one-frame glitches were counted as cuts.

  These thresholds were set on the same footage. Dissolves and fades are gradual and are **not** detected: type those frames yourself.

## 10. Traditional roto (AI off)

Tick **disable AI (traditional roto only)** on the node, or set the environment variable `ST_ROTO_AI=off` for a whole Nuke session. The AI controls disappear. Then:
1. Draw and edit shapes in the node's Roto with Nuke's own tools.
2. Press **Save Roto edits to project**. Your shapes become ST-ROTO objects with artist provenance, recorded in one undo step.
3. Use mattes (guided filter or hard edges), exports, the RotoPaint copy, backups and packages as usual.

This also works on a machine with no AI runtime or no graphics card. On CG plates, **Shapes from Cryptomatte** and **Propagate along vectors** (section 15) are traditional-roto helpers that need no AI either.

## 11. Shapes: points, feather, motion blur, roles

- **Editing.** Edit shapes in the node's Roto like any Roto shape. ST-ROTO records your edits when you press **Save Roto edits to project**, and also automatically before any Track or Re-track.
- **Feather.** Set a shape's feather, and per-point feather, in Roto as usual. ST-ROTO keeps it, and it can be undone. Nuke's own render of the node is exact. EXR mattes approximate Nuke's feather: the 50 % contour lies within 1 px.
- **Motion blur.** Set *motion blur* to `global` (with *samples*, *shutter* and *shutter offset*) and Nuke blurs the shapes along their tracked motion.
- **Roles.** Set *object name* and an *object role*, then press **Set role** (also available in the Objects pane as **Role…**):
  - **add** is a normal object.
  - **holdout** is cut out of the combined matte, for example a pole in front of the actor.
  - **garbage** means the combined matte is kept only inside it.

  The node's render and the combined EXR alpha follow the roles, and each object's own EXR layer stays unchanged.
- **Merge into…** (Objects pane) moves one object's shapes into another object, in one undo step.
- **Copy shapes to RotoPaint** creates a RotoPaint node with native copies of every shape. Its render is identical to Roto's.

## 12. Mattes

Press **Render mattes (EXR)** to write one EXR per frame to `<project>_mattes/<shot>/`, or to *matte folder* if set. Each file holds:
- **one layer per object** (`hero.alpha` in Nuke);
- **all objects combined** in `rgba.alpha`, following the roles.

| Setting | Options and effect |
|---|---|
| *edges* | **guided filter**: soft edges refined against the plate in a narrow band, no AI. **ViTMatte-S**: a learned matting model, better on hair and on shapes that are slightly off (optional; see its licence note in section 20). **hard**: identical to the shapes. |
| *matte size* | **full resolution**, or **fit 1920x1080** (the default in Non-commercial). Fit is computed at full resolution and then area-averaged: files are 3–11× smaller with the same accuracy. HD plates are never scaled. |
| *RGB in mattes* | **none**; **premultiplied** (plate × alpha, ready to merge); **straight**; **premultiplied, decontaminated** or **straight, decontaminated**, where soft edges no longer carry the old background (edge fringe measured 42× lower over a green screen, about 3× over a busy background). The EXR header records the choice. |
| *spill* | **auto / green / blue** removes screen spill from the foreground colour. It also affects genuinely green or blue foreground parts, so check them. Alpha is never changed. |
| *edge offset* | grows (+) or shrinks (−) the mattes, in pixels |
| *edge blur* | feathers the mattes |
| *core/edge width* | adds `core_matte` and `edge_matte` layers |

If a Nuke Read node still has the previous mattes open, Windows won't let ST-ROTO replace them. The render then goes to a new folder (`…_v002`) and the status says so.

## 13. Exports and hand-off

| Button | Writes |
|---|---|
| **Export shapes (JSON + SVG)** | `<project>_export/<shot>/`: a JSON file with every object, key and its provenance (re-importable with **Import shapes (JSON)**, also into another project), and one SVG per keyed frame |
| **Export Alembic** | `<project>_export/<shot>/<shot>.abc` for 3D packages: for each shape an animated closed Bezier curve and an outline mesh. Nuke 17 reads the meshes with GeoImport. Coordinates are Nuke Roto pixels (x right, y up, z = 0). Needs Nuke 14 or newer. |
| **Copy shapes to RotoPaint** | a RotoPaint node with native copies |
| **Delivery package** | a zip to hand the shot over: the latest mattes and shape export, the node's settings, the models used (with licence and approval), processing, provenance and quality reports, and a checksummed manifest. Render mattes and export shapes first. |

## 14. Project safety: backups, recovery, packages

- **Automatic backups** run every 5 minutes while you work (only after changes; set `ST_ROTO_BACKUP_SECONDS` to change the interval) and when Nuke exits. They go to `<project>_backups/`. **Back up now** makes one immediately.
- **Crash recovery.** If Nuke crashed or the project file is damaged, the status says so the next time the project opens. A damaged file is kept as `.damaged.<time>` and the newest good backup is restored.
- **Package project** writes a portable zip next to the project. It contains the project, mattes, exports, your saved Nuke script and a checksummed manifest, but no model weights.
- **Unpacking on another machine.** Use **ST-ROTO › Unpack project package…** (main menu):
  1. ST-ROTO verifies the checksums.
  2. It asks for any plates it can't find (pick any frame of them).
  3. It checks every plate against a fingerprint of the original footage. The same plates in a new location are accepted; different footage with the same file names is refused.
  4. When you open the unpacked script, its Read and ST_Roto nodes are relinked.

## 15. CG plates: extra channels, Cryptomatte, motion vectors

Every layer of the input (depth, motion vectors, normals, position, Cryptomatte and so on) passes through the ST_Roto node unchanged. Only alpha is replaced, controlled by *replace input alpha*, which is on for nodes made since this version. Older nodes add the shapes over the input's alpha, which is white on plates that already have alpha, so recreate those nodes.

- **List channels** shows the input's layers and its Cryptomatte names.
- **Prompt from Cryptomatte.** Set *prompt from* = Cryptomatte and *source* = name(s), press **Use as prompt**, then **Track**.
- **Shapes from Cryptomatte** (no AI) builds the object named in *object name* directly from the Cryptomatte name(s) in *source*, on every frame. Measured IoU against truth was 0.998.
- **Propagate along vectors** (no AI) carries a shape you drew along the plate's motion vectors:
  1. Draw the object on a frame and press **Save Roto edits to project**.
  2. Stay on that frame and choose forward, backward or both.
  3. Press **Propagate along vectors**.

  The shape follows the *motion vectors* (and *backward*) layers until the shot ends or your next key, and something passing in front doesn't drag it along. It drifts slowly (about 0.002 IoU per frame), so add a key every 10–20 frames; propagation stops at your keys.
- **Check with channels.** Fill in what your plate has:
  - *medians of* (for example `depth.Z`);
  - *motion vectors* (the forward layer);
  - *backward* (strongly recommended: without it, occlusions raise flags);
  - *Cryptomatte objects*.

  Then press the button. Frames where a shape jumps in depth, doesn't follow the vectors, or differs from its Cryptomatte matte get **check** flags. The vector sign convention is measured from the plate. This works with AI disabled too.

These tools were tested on synthetic CG shots, so the check thresholds are provisional.

## 16. Stereo and multi-camera

**Stereo**
1. Set the script up with views (Project Settings › Views, for example a Read with `%V`).
2. Prompt in the *prompt view*. Empty means the hero view.
3. Tick **track every view (stereo)** and press **Track**.

Each object is tracked in every view on that view's own pixels. ST-ROTO finds the object in the other view by a disparity search on the prompt frame, and the status says something like *found at disparity −30.0 px*. You then have:
- one object per view (`hero_left`, `hero_right`), each shown only in its own view;
- re-tracks that use the object's own view;
- **Render mattes** writing one sequence per view;
- **check** flags where the views disagree;
- **Resume track** working for stereo runs too.

**Camera rigs.** Use this when the cameras are toed-in, rolled, vertically offset or have different lenses. Name the camera nodes in *cameras*, for example `left=CamL, right=CamR`, or `A=CamA, B=CamB, C=CamC` for more views. ST-ROTO then searches along each epipolar line at the size the depth implies (on a synthetic three-camera rig it found the object on 31 of 32 view-frames). It flags shapes that sit off their epipolar line, and **Check views (cameras)** re-checks after you edit.

## 17. The node family: ST_RotoMatte and ST_RotoOutput

Create these from **Nodes › ST-ROTO**, preferably with your ST_Roto node selected so they take over its project and shot.

- **ST_RotoMatte** renders the mattes of the *objects* you name (empty means all) and/or a *roles* filter (for example only holdouts), with its own edge settings. It outputs them in the node graph:
  - alpha is the combined matte;
  - each object is a layer;
  - the plate's RGB and other channels pass through.

  Until you press **Render mattes** it passes its input through unchanged.
- **ST_RotoOutput** holds **Export shapes**, **Delivery package**, **Package project** and **Back up** for a shot.
- Both nodes have **Check**, which lists the project's shots and objects. They read the project as it is, so press *Save Roto edits to project* on the ST_Roto node first if you edited shapes by hand.

## 18. Panes: Objects and Models

**ST-ROTO Objects** (Windows › Custom). Select your ST_Roto node and press *Use selected ST_Roto node*. The pane then:
- lists every object with its keys, role, lock and review state;
- lets you rename, lock, unlock and delete objects, with undo and redo, and offers **Role…** and **Merge into…**;
- has the timeline described in section 7;
- holds the collaboration controls (section 21).

**ST-ROTO Models** (Windows › Custom). This lists every installed model with its licence, approval, revision, source and whether it fits on the GPU.
- **Verify** recomputes the SHA-256 checksum of every model file.
- **Self-test** tracks a generated test image and reports accuracy and speed on this machine.
- **Remove…** deletes a model; **Import…** adds one (approved models only).
- **Versions.** Select a model to list its versions. **Use this version** checks every file of the version and switches to it, **Roll back** returns to the previous one, **Compare (self-test all)** tests every version without switching, and **Remove version…** deletes one. Importing over an installed model keeps the old version.
- **Model locations.** Models can also live in a user or studio folder, set with `ST_ROTO_MODELS_USER` or `ST_ROTO_MODELS_STUDIO`. A model found there is used instead of the built-in one.

## 19. Presets

Choose a *preset* and press **Apply**. The built-in presets are *Quick look*, *Final quality*, *Traditional roto (AI off)*, *CG plate with passes* and *Stereo*.
- To keep your own, type a name in *new preset* and press **Save settings as**. Your presets are stored in `%USERPROFILE%\.st_roto\presets`, or in `ST_ROTO_USER_PRESET_DIR` if set.
- **Delete** removes one of your own presets.
- A studio can share presets through `ST_ROTO_PRESET_DIR`.
- Presets hold settings only, never prompts, objects, frame ranges or paths.

## 20. Graphics cards, models and performance

**AI runtimes.** ST-ROTO ships two and picks one when Nuke starts:

| Your machine | Runtime | Notes |
|---|---|---|
| NVIDIA GPU with a recent driver (CUDA 12) | **CUDA** (onnxruntime-gpu 1.26) | fastest |
| AMD, Intel, or any other DirectX 12 GPU | **DirectML** (onnxruntime-directml 1.24.4) | Measured on the same NVIDIA GPU: same shapes as CUDA, 7–20 % slower, about 35 % less GPU memory. On an integrated Intel UHD GPU: same shapes at about 6 s per frame. AMD is supported but untested. |
| no usable GPU | CPU | works, but slowly |

- **Choosing the runtime yourself.** Set `ST_ROTO_RUNTIME=cuda` or `ST_ROTO_RUNTIME=directml` before starting Nuke. With several GPUs, `ST_ROTO_DML_DEVICE=1` (2, …) selects another one for DirectML. The System report shows the active runtime and why it was chosen. The node's status says *device cuda*, *device directml* or *device cpu*.
- **GPU memory.** Measured track peaks, the same for one or several objects:

  | model | CUDA | DirectML |
  |---|---|---|
  | tiny | 3.7 GB | 2.6 GB |
  | large | 6.8 GB | 4.3 GB |

  Windows can't tell ST-ROTO how much memory an AMD or Intel GPU has free, so on DirectML *model = auto* uses tiny. Choose large yourself if your GPU has more than about 5 GB.
- **Speed** (RTX 5060 Laptop, 720p, warm): tiny about 0.35 s per frame and large about 0.55 s per frame on CUDA. Press **Load model** once per session to avoid the first-use pause.
- **ViTMatte licence note.** The ViTMatte weights are Apache-2.0 but were trained on Adobe's Composition-1k data, whose terms are reported to be non-commercial. Decide whether that suits your use.

## 21. Working with others (prototype)

The Objects pane shows *held by* (who leases each object).
- **Take** and **Release** a lease. Only the holder can change a leased object.
- A supervisor can **Override** a lease whose holder has been idle or offline for 15 minutes; the override is recorded with evidence.
- **Set up signing key** creates your private key in `%USERPROFILE%\.st_roto\keys` (never in the project), so your changes are signed.
- **Set role…** assigns team roles; the first role must be you as admin.

Sharing a project between machines is not in the UI yet: it's a tested prototype (`docs/COLLABORATION_ARCHITECTURE.md`).

## 22. Reference

### Environment variables

| Variable | Effect |
|---|---|
| `ST_ROTO_AI=off` | AI off for the whole Nuke session |
| `ST_ROTO_RUNTIME` | `auto` (default), `cuda` or `directml` |
| `ST_ROTO_DML_DEVICE` | DirectML adapter number (default 0) |
| `ST_ROTO_MODELS_USER`, `ST_ROTO_MODELS_STUDIO` | extra model locations (user location first, then studio, then the built-in copy) |
| `ST_ROTO_PRESET_DIR`, `ST_ROTO_USER_PRESET_DIR` | studio and user preset folders |
| `ST_ROTO_BACKUP_SECONDS` | automatic backup interval (default 300) |
| `ST_ROTO_KEY_DIR` | folder of your signing keys |

### Files ST-ROTO writes

| Path | What |
|---|---|
| `<script>.stroto` | the project (SQLite) |
| `<project>_backups/` | backups |
| `<project>_mattes/<shot>/` | EXR mattes (`_v002`… when the previous ones were in use) |
| `<project>_export/<shot>/` | JSON, SVG and Alembic exports |
| `%LOCALAPPDATA%\ST-ROTO\<version>\` | the installed program |
| `%USERPROFILE%\.nuke\init.py` | one marked block added by the setup |
| `%USERPROFILE%\.st_roto\` | your presets and signing keys |

### Limits of Nuke Non-commercial (measured)

- At most 10 Python-accessible nodes per Nuke session. ST_Roto uses 3. If you see "Nuke returned no node … 10 nodes per session", save the script, reopen it and try again.
- Renders are limited to 1920×1080. ST-ROTO tracks larger plates from reduced frames (section 6).
- Scripts are saved encrypted (`.nknc`).

## 23. Troubleshooting

| Symptom | What to do |
|---|---|
| No ST-ROTO menu in Nuke | Run the setup's status (or 2 = repair). Check that `%USERPROFILE%\.nuke\init.py` has the ST-ROTO block, and look in Script Editor for errors. |
| Status says *device cpu* or *FALLBACK* | Read the reason in the status line and in the **System report**. NVIDIA: update the driver (CUDA 12). Other GPUs: the DirectML runtime should be chosen automatically; check `ST_ROTO_RUNTIME`. |
| "not enough free GPU memory" | Close GPU-heavy programs, use the tiny model, or let it run on the CPU. |
| The object jumps to something else after a cut | Check *scene cuts* (**Detect cuts**) and keep *stop at scene cuts* on. |
| A shape wasn't updated after Re-track | You edited it in Roto, so it's protected ("NOT updated (edited in Roto)"). Press **Save Roto edits to project**, then re-track. |
| "frame N is locked" | Press **Unlock range** for that frame first. |
| White alpha on a plate that already had alpha | The node was made before *replace input alpha* existed: recreate it. |
| Mattes went to `…_v002` | The previous files were open in a Read node. That's expected; point your Read at the new folder. |
| Windows SmartScreen warns about the setup | The setup isn't code-signed yet: choose **More info › Run anyway**. |

When you report a problem, include:
- the status text;
- the **System report**;
- the Script Editor output.
