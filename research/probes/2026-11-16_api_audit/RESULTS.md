# Nuke API audit: viewer interaction, custom knobs, Deep, stereo (T-033) — 2026-11-16

Measured in Nuke 17.1v3 **Non-commercial**, headless (`probe_api.py`, `result.json`), plus earlier GUI findings (T-059, T-051). NDK facts are from Foundry's NDK guide; they cannot be tested here (Non-commercial does not load plug-ins, D-011).

| Need (master prompt) | Python API (measured) | NDK (C++) | ST-ROTO now |
|---|---|---|---|
| Click on the object in the viewer (§8 prompts) | `ViewerWindow` has activeInput, view/setView, frameControl, show/hideStatusMessage, isOverlayShown, getGLCameraMatrix — **no mouse/pick events in image coordinates** | `Op::build_handles` / `draw_handle`, viewer events: full interactive overlays | Native `XY_Knob` handle dragged in the viewer + Include/Exclude buttons (T-059) |
| Boxes / regions as prompts | `BBox_Knob`, `Box3_Knob`, `UV_Knob`, `XYZ_Knob` exist (native viewer handles) | custom handles | not yet (box prompts: REQ-060) |
| Custom UI inside the node | `PyCustom_Knob` (Qt widget in the properties panel) **works in Non-commercial** | custom knobs (`Knob` subclasses) | object panel as a docked Qt pane (T-059) |
| React to edits | `addKnobChanged`, `addOnUserCreate`, `addUpdateUI` callbacks | knob_changed | not used (explicit buttons; callbacks to evaluate for auto-sync) |
| Deep (§13.3) | Deep nodes create in NC (DeepRead, DeepMerge, DeepToImage, DeepFromImage, DeepHoldout2, DeepRecolor); `Node.deepSample/deepSampleCount` (per pixel: slow, cf. T-046) | `DeepOp` / `DeepPixelOp`: deep-aware roto operators | not started; Deep holdouts can be built from ST-ROTO mattes with Nuke's own Deep nodes (node graph), deep-native ops need the NDK |
| Stereo / multi-view (§13.4) | `nuke.views()`, `Root.addView` works in NC; OneView / JoinViews exist; `nuke.execute(..., views=[...])` renders per view | view-aware Ops | not started; feasible in Python: track each view (render per view), consistency check between views |
| GPU kernels for edge ops | BlinkScript node creates in NC | Blink / CUDA in C++ | edge refinement in numpy (st_roto.matte) |

**Conclusions.**
1. A true click-in-viewer prompt tool is NDK-only (commercial editions); the Python path keeps native handles (XY / BBox knobs) — box prompts can be added the same way (next step for REQ-060).
2. Stereo support is reachable in Python (per-view rendering + independent tracking + cross-view check), no NDK needed.
3. Deep: ST-ROTO can drive Nuke's Deep nodes from its mattes (holdouts) in Python; deep-sample-native roto needs the NDK (route B, T-011b).
4. `PyCustom_Knob` allows richer in-node UI under Non-commercial (instead of only buttons), within the 10-node budget since it is a knob, not a node.
