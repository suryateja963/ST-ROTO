# ST-ROTO API reference

Generated from the source by `tools/docs/build_api_reference.py` - do not edit by hand. Public names only (no leading underscore). Architecture, data model and conventions: `docs/DEVELOPER_GUIDE.md`.

## Contents

* `st_roto`: [calibration](#st_rotocalibration), [cameras](#st_rotocameras), [capabilities](#st_rotocapabilities), [channels](#st_rotochannels), [chatter](#st_rotochatter), [colour](#st_rotocolour), [commands](#st_rotocommands), [delivery](#st_rotodelivery), [exr](#st_rotoexr), [frames](#st_rotoframes), [geometry](#st_rotogeometry), [geomexport](#st_rotogeomexport), [interchange](#st_rotointerchange), [jobs](#st_rotojobs), [leases](#st_rotoleases), [matte](#st_rotomatte), [metrics](#st_rotometrics), [model](#st_rotomodel), [persistence](#st_rotopersistence), [pieces](#st_rotopieces), [presets](#st_rotopresets), [prompts](#st_rotoprompts), [quality](#st_rotoquality), [runtime_choice](#st_rotoruntime_choice), [scenecut](#st_rotoscenecut), [signing](#st_rotosigning), [stereo](#st_rotostereo), [store](#st_rotostore), [sync](#st_rotosync), [views](#st_rotoviews)
* `st_roto_ai`: [registry](#st_roto_airegistry), [resize](#st_roto_airesize), [runtime](#st_roto_airuntime), [sam2](#st_roto_aisam2), [spill](#st_roto_aispill), [vitmatte](#st_roto_aivitmatte)
* `st_roto_nuke`: [alembic](#st_roto_nukealembic), [assist](#st_roto_nukeassist), [capabilities](#st_roto_nukecapabilities), [collab](#st_roto_nukecollab), [colour](#st_roto_nukecolour), [convention](#st_roto_nukeconvention), [family](#st_roto_nukefamily), [mattes](#st_roto_nukemattes), [model_panel](#st_roto_nukemodel_panel), [models_ui](#st_roto_nukemodels_ui), [node](#st_roto_nukenode), [packages](#st_roto_nukepackages), [panel](#st_roto_nukepanel), [pixels](#st_roto_nukepixels), [roto_export](#st_roto_nukeroto_export), [session](#st_roto_nukesession), [track](#st_roto_nuketrack)

## `st_roto` - Core: pure Python 3.7+ and numpy; no Nuke, Qt or ONNX Runtime

### st_roto.calibration

Calibration of the review-flag thresholds (T-068) from tracked frames with ground truth. Pure Python + numpy.

A frame is BAD when its mask is wrong (IoU vs truth < `bad_iou`) or the object is visible in the truth but the AI
reports it absent (or vice versa). The review rules (st_roto.quality) flag a frame when |object score| < margin or
(on keyed frames) predicted IoU < iou_min, or when the object is lost between visible frames. For a grid of
(margin, iou_min) this computes how many bad frames are flagged (recall) and how many flags are real
(precision). Results on synthetic shots are PROVISIONAL; real footage needs OQ-13.

* **`label_bad(rec, bad_iou=0.9)`**
* **`flags_for(records, margin, iou_min, lost_max_gap=None)`**

  > Same rules as st_roto.quality.review_frames, per sequence (records carry 'seq'). -> [bool] aligned.

* **`evaluate(records, margins=(0.25, 0.5, 1.0, 1.5, 2.0, 3.0), iou_mins=(0.0, 0.5, 0.6, 0.7, 0.8, 0.9), bad_iou=0.9, lost_max_gap=None)`**

  > -> {"frames", "bad", "grid": [{margin, iou_min, flagged, tp, precision, recall, f1}], "best",
  > "iou_pred_vs_true_corr"}.

* **`area_jump_flags(records, threshold)`**

  > T-078 rule (st_roto.quality.area_jumps) per sequence on records carrying 'area_pred'. -> [bool] aligned.

* **`evaluate_area_jumps(records, thresholds=(0.2, 0.25, 0.35, 0.5, 0.65), margin=1.0, iou_min=0.7, bad_iou=0.9, lost_max_gap=None)`**

  > For each threshold: the area rule alone, and what it ADDS to the score rules at (margin, iou_min).
  > -> [{threshold, flagged, tp, precision, added_flags, added_tp, recall_scores, recall_combined}]


### st_roto.cameras

Camera geometry for multi-view correspondence (T-120, REQ-115 'multi-camera correspondence when camera
information is available'). Pure Python + numpy.

Conventions: a camera is (K, R, C): K the 3x3 intrinsics in ST-ROTO's canonical image space (pixels, x right,
y DOWN, origin top-left corner), R the 3x3 world-to-camera rotation, C the camera centre in world coordinates.
Nuke cameras look down their local -Z with +Y up; `from_nuke` converts its parameters (focal, apertures, window
translate/scale, world matrix) into that form, so x_image = project(P, X) matches Nuke's own render (verified in
research/probes/2026-11-18_multicam).

* **`intrinsics(width, height, focal, haperture, vaperture=None, win_translate=(0.0, 0.0), win_scale=(1.0, 1.0))`**

  > K for a Nuke camera (measured against Nuke 17's own render, research/probes/2026-11-18_multicam): the
  > horizontal aperture spans the image width and pixels are square (fy = fx; vaperture does not change the
  > projection); win_translate moves the camera WINDOW in units of half the image width, so the image content moves
  > the opposite way: +x shifts content left, +y (Nuke's y up) shifts it down. Measured: 14 projected points within
  > 0.33 px of Nuke's render for 3 non-rectified cameras incl. roll, toe-in and window translate.

* **`from_world_matrix(world4x4)`**

  > (R world->camera in canonical axes, C) from a camera's 4x4 world matrix (camera->world, Nuke axes: -Z view,
  > +Y up). Canonical camera axes: x right, y down, z forward = Nuke (x, -y, -z).

* **`projection(K, R, C)`**

  > 3x4 projection matrix P = K [R | -R C].

* **`project(P, X)`**

  > World points (N, 3) -> image points (N, 2) (canonical) and depth (N,) (positive in front).

* **`fundamental(P1, P2, C1)`**

  > F with x2^T F x1 = 0 for the same world point seen in images 1 and 2: F = [e2]x P2 P1^+, e2 = P2 C1.

* **`epipolar_line(F, x1)`**

  > Line (a, b, c), a x + b y + c = 0, normalised so (a, b) is a unit vector, in image 2 for point x1 of image 1.

* **`triangulate(P1, P2, x1, x2)`**

  > World point (3,) seen at x1 in image 1 and x2 in image 2 (linear DLT).

* **`image_scale(K1, R1, C1, K2, R2, C2, X)`**

  > How much larger an object at world point X appears in camera 2 than in camera 1 (focal / depth ratio).

* **`scale_along(cam1, cam2, x1)`**

  > shift -> how much larger camera 2 sees an object whose centre is at x1 in image 1 and at x1 + shift in
  > image 2 (depth by triangulation). cam = (K, R, C). Used to compare candidates at their own scale (T-120).

* **`line_distance(l, x)`**

  > Signed distance (px) of image point x from a normalised line.


### st_roto.capabilities

Hardware detection and capability report (REQ-020 / REQ-022, master prompt section 4: "report when a feature is
unavailable due to hardware, driver, edition or API"). T-091.

Pure Python, no Nuke / Qt / AI imports (layering rule). Two parts:
* probes of the machine that need no host: `gpu_info()` (local `nvidia-smi`, no network), `ram_info()`;
* `evaluate(facts)`: turns a facts dict (gathered by the host adapter, st_roto_nuke.capabilities) into a list of
  features, each "available", "limited" or "unavailable" with the reason and what would change it.

Edition limits marked "measured" were measured in this project (research/probes); others are from Foundry's
documentation and marked as such (docs/PHASE1_DISCOVERY_REPORT.md).

* **`vram_need(model, needs=None)`**

  > MiB of free GPU memory required before running `model` on the GPU (measured peak + 5 %), or None.
  > needs: the peak table (default MODEL_VRAM_MIB = CUDA; DML_VRAM_MIB for the DirectML build).

* **`plan_model(choice, device, free_mib, present, loaded=(), auto_choice='auto', needs=None)`**

  > Memory-aware model/device choice (T-092, REQ-021). Pure.
  > choice: a model name or `auto_choice`; device: "auto" | "cuda" | "cpu"; free_mib: free GPU memory or None
  > (no NVIDIA GPU / unknown); present: {model: installed}; loaded: models whose sessions are already on the GPU
  > (they need no new memory); needs: peak table (vram_need). Returns (model, device, note). Never silently swaps a model the artist chose:
  > if it does not fit, it runs on the CPU and the note says so (and suggests the smaller model).

* **`gpu_info(timeout=10)`**

  > NVIDIA GPUs via the local `nvidia-smi` (ships with the driver; no network). Returns
  > {"gpus": [{"index", "name", "total_mib", "used_mib", "free_mib", "driver"}], "error": str or None}.
  > Other vendors are not detected here (no AMD/Intel query tool assumed); their absence is reported, not hidden.

* **`display_adapters()`**

  > Names of the display adapters Windows knows (any vendor: AMD, Intel, NVIDIA...), via user32
  > EnumDisplayDevicesW (no process, no network). [] elsewhere or if unknown. Memory is not available this way.

* **`parse_nvidia_smi(text)`**
* **`ram_info()`**

  > {"total_mib", "available_mib"} of system RAM, or {} if unknown.

* **`evaluate(f)`**

  > facts -> [feature dicts]. Expected keys (missing ones count as unknown / absent):
  > edition ("nc" | "indie" | "commercial"), nuke_version, ai_disabled (reason or None), ai_runtime_problem (reason
  > or None), providers ([...] e.g. ["cuda", "cpu"]), gpus (gpu_info()["gpus"]), gpu_error, models ({name: bool}),
  > ocio (bool), signing_keys (int).

* **`report_text(facts, features)`**

  > Plain-text report for the artist / a support request.

* **`signing_key_count(folder=None)`**

  > Number of private signing keys in the D-038 key folder (no key content is read).


### st_roto.channels

Extra image channels as hints (T-110, REQ-113, master prompt section 13.2). Pure Python + numpy.

Channels a plate can carry besides RGB, and what ST-ROTO does with each (artist-selected per node):
* Cryptomatte (ID mattes from CG renders): an object's exact coverage per frame -> prompt (box + clicks), and a
  per-frame comparison with the tracked shape (`crypto_mask`, spec: Psyop Cryptomatte v1.2: MurmurHash3_x86_32 of
  the name, `uint32_to_float32` conversion, rank channels <layer>00.. as (id, coverage) pairs).
* Motion vectors (forward/backward, pixels per frame): the shape on frame f moved by the vectors should match the
  shape on f+1 (`warp_points`, `motion_agreement`). Renderers differ in the sign of the vertical (and sometimes
  horizontal) component, so the convention is MEASURED per shot from the pixels (`detect_vector_convention`).
* Depth (Z), position (P), normals (N) or any other layer: a robust statistic inside the object (median) per frame;
  a jump against BOTH neighbouring frames suggests the shape grabbed something else (`channel_jumps`).
Every rule only adds CHECK flags; thresholds are provisional (synthetic CG shot, research/probes/2026-11-18_channels).

* **`murmur3_32(data, seed=0)`**

  > MurmurHash3_x86_32 (Austin Appleby), as used by Cryptomatte. data: bytes or str (UTF-8).

* **`name_to_id(name)`**

  > Cryptomatte id (uint32 bit pattern of the float32 stored in the image): the hash with exponent 0 / 255
  > avoided (flip of the lowest exponent bit), per the specification.

* **`id_to_float(i)`**
* **`layer_key(layer)`**

  > Metadata key of a Cryptomatte layer: the first 7 hex digits of the hash of its name.

* **`find_layers(metadata)`**

  > {layer name: manifest {name: id (int)}} from image metadata (EXR header attributes or Nuke's
  > node.metadata(): keys like '[exr/]cryptomatte/<key>/name', '.../manifest'). Layers without a manifest get {}.

* **`rank_pairs(channels, layer)`**

  > [(id array, coverage array)] of a Cryptomatte layer from {channel name: HxW array}. Channel names may be
  > EXR style (<layer>00.R/G/B/A) or Nuke style (<layer>00.red/green/blue/alpha).

* **`crypto_mask(channels, layer, names)`**

  > Coverage (HxW float, 0..1) of the objects `names` (one name or several) in a Cryptomatte layer.

* **`encode_ranks(coverages, depth=4)`**

  > Test/tool helper: {name: HxW coverage} -> {'00': (H,W,4), '01': ...} rank channels (id, cov, id, cov),
  > highest coverage first, as a renderer writes them.

* **`manifest_attributes(layer, names)`**

  > EXR header attributes of a Cryptomatte layer (for test data and exports).

* **`displacement(u, v, convention)`**

  > (dx, dy) arrays in canonical image coordinates (x right, y DOWN) from the vector channels.

* **`warp_points(points, u, v, convention, mask=None, inset=None)`**

  > Move a shape key (stored points: x, y + absolute handles) by the vectors sampled at each point. Points
  > outside the object may sample the background's vectors; with `mask` (the object's pixels on that frame) each
  > point samples the vector of the nearest pixel at least `inset` px INSIDE the mask (default WARP_INSET): a traced
  > outline sits on or just over the object's edge, where the pixel can belong to a neighbouring object moving
  > differently (measured, T-110: one outline point took the passing distractor's vector, motion IoU 0.88 on a
  > frame whose shape was 0.99 correct). Vectors are sampled nearest-pixel (no mixing across edges).

* **`fit_affine_motion(u, v, convention, mask, max_samples=4000, iterations=4)`**

  > The dominant motion inside `mask` as a 2x3 affine map A (x' = A [x, y, 1]), robust to pixels of something
  > else in front (iteratively reweighted least squares, residuals beyond 3 x the median dropped). Returns
  > (A, inlier fraction) or (None, 0) if too few pixels.

* **`warp_points_robust(points, u, v, convention, mask, tol=2.0)`**

  > warp_points that survives occlusion (T-121, measured): each point keeps its own (inset-sampled) vector only if
  > it agrees within `tol` px with the object's dominant affine motion (fit_affine_motion); otherwise it moves with
  > the affine motion. Without this a shape propagated across an occluder took the occluder's vectors and fell
  > apart (IoU 0.98 -> 0.03 in one frame).

* **`warp_image(img, u, v, convention)`**

  > Backward-warp check helper: predicted next frame = img sampled at (x - d(x)) (approximate: uses the vectors
  > at the destination). Returns the prediction (HxW or HxWxC).

* **`vector_errors(img_a, img_b, u, v)`**

  > {convention: mean absolute difference between frame B and frame A moved by the forward vectors} where the
  > vectors move something (|d| > 0.5 px); raises ValueError if (almost) nothing moves.

* **`choose_convention(per_frame_errors, default='u right, v up (Nuke)')`**

  > Decide the vector convention from several frames' `vector_errors` (summed). Each axis's sign is decided
  > separately: the best candidate is compared with the same candidate with that axis flipped; below
  > CONVENTION_MARGIN the axis is undetermined (e.g. nothing moved vertically) and the default's sign is used.
  > Returns {"convention", "errors", "margin_u", "margin_v", "undetermined": [axes]}.

* **`detect_vector_convention(img_a, img_b, u, v)`**

  > One frame pair: `choose_convention([vector_errors(...)])`.

* **`mask_iou(a, b, region=None)`**

  > IoU of two masks, optionally only inside `region` (bool).

* **`occluded_object_pixels(prev_mask, cur_mask, fu, fv, bu, bv, convention, tol=1.0)`**

  > Pixels of frame f to leave out of the motion check because ANOTHER surface hides or reveals the object there
  > (bool mask on frame f). Object-centric on purpose: a plain forward-backward test also removes the object's own
  > silhouette moving over the background, which hides exactly the errors the check is for (measured, T-110: a
  > shape stuck on the previous frame then scored IoU 0.997).
  >   * hidden: an object pixel x of f-1 (prev_mask) moves by its forward vector (fu, fv of f-1) to y on f, and y's
  >     backward vector (bu, bv of f) does not lead back to x within `tol` px: something covers the object at y;
  >   * revealed: y inside the current shape whose backward vector leads to a point x of f-1 that does not come
  >     back (y was hidden on f-1) AND x lies OUTSIDE the previous shape: the object was hidden there by something
  >     else. (Background wrongly kept by a shape stuck on the previous frame leads back INSIDE the previous shape,
  >     so it still counts; a test on the vectors' similarity to the object's motion failed on a rotating, scaling
  >     object: measured, T-110.)

* **`masked_stat(channel, mask, erode=2)`**

  > Median of a channel inside a mask (eroded by `erode` px so edge pixels of neighbours do not count); None if
  > the mask is (nearly) empty.

* **`channel_jumps(values, threshold=None)`**

  > {frame: deviation / tolerance} for SPIKES of a per-frame statistic: the value differs from BOTH nearest
  > frames that have one, in the same direction, by more than max(threshold x robust spread over the shot
  > (p90 - p10), STAT_JUMP_REL x |value|). Smooth trends and zero crossings are never flagged.

* **`resolve(channels, name)`**

  > The array of channel `name` as the artist writes it in Nuke ('depth.Z', 'rgba.alpha', 'N.red', 'forward.u')
  > from an EXR channel dict (Nuke writes rgba as R/G/B/A and keeps other layers' suffixes). KeyError if absent.

* **`layers_of(channel_names)`**

  > Distinct layer names of a channel list ('depth.Z' -> 'depth'; R/G/B/A -> 'rgba').

* **`check_object(frames, get_keys, get_channels, height, width, stats=(), motion=None, crypto=None)`**

  > Extra-channel report of one object: {frame: {"stats": {channel: median inside the shape}, "motion_iou",
  > "crypto_iou"}} for the frames where the object has a shape.
  >
  > get_keys(f) -> [point lists] of the object's shapes on frame f ([] if none); get_channels(f) -> {channel: HxW}.
  > stats: channel names whose median inside the shape is recorded (depth.Z, P.y, N.blue, ...).
  > motion: {"u", "v" (forward vector channel names), "convention", optional "bu", "bv" (backward vectors)}:
  >   shape(f-1) moved by the forward vectors of f-1 vs shape(f); with backward vectors, pixels that fail the
  >   object-centric forward-backward check (the object hidden or revealed by something else) are left out.
  > crypto: {"layer", "names"}: shape(f) vs the Cryptomatte coverage (> 0.5) of those names.

* **`check_objects(frames, get_keys, get_channels, height, width, stats=(), motion=None, crypto=None, progress=None)`**

  > `check_object` for several objects in ONE pass over the frames (each frame's channels fetched once):
  > get_keys {object: fn(frame)}, crypto {object: {"layer", "names"}} (objects without an entry: no Cryptomatte
  > check). progress(i, n) is called per frame. Returns {object: report}.

* **`review_flags(report)`**

  > CHECK flags from an object's channel report {frame: {"stats": {channel: value}, "motion_iou": x,
  > "crypto_iou": x}} -> [(frame, reason)].


### st_roto.chatter

Chatter reduction for tracked shapes (T-115, REQ-101 'chatter reduction'). Pure Python + numpy.

AI shapes are fitted per frame, so their control points jitter by fractions of a pixel from frame to frame and the
edge 'chatters' in playback. Each point's trajectory (all six numbers: position and both handles) is replaced, on
AI frames only, by a local quadratic least-squares fit over the frames within `radius` (Savitzky-Golay style):
constant velocity and acceleration pass unchanged, frame-to-frame noise is averaged out. Artist keys and locked
frames are never changed but take part in the fits (they anchor the result). Fits never span a gap in the keys or a
collapsed part key (piece absent, T-049): those split the trajectory.

* **`smooth_keys(keys, fixed=(), radius=DEFAULT_RADIUS, strength=1.0, skip=())`**

  > keys {frame: points (N x 6)} of one shape -> {frame: smoothed points} for the frames that are NOT in `fixed`
  > (artist / locked) and not in `skip` (e.g. collapsed). strength 0..1 blends original -> fitted.

* **`jitter(keys)`**

  > Mean |second difference| of the control points over consecutive keyed frames (px): 0 for constant velocity,
  > grows with frame-to-frame noise. A simple chatter measure for reports.


### st_roto.colour

Model-input colour transforms (ADR-0010, T-045). Pure numpy; OpenColorIO is used only for `ocio` transforms.

SAM 2.1 (and most vision models) were trained on sRGB-encoded 8-bit photos, so frames are converted from the
host's working space to sRGB-encoded Rec.709 in [0, 1] before inference. Built-in transforms are DERIVED here from
the published primaries / white points (RGB->XYZ from chromaticities, Bradford chromatic adaptation), not typed-in
matrices, and are tested against published reference matrices and against OpenColorIO's ACES configs.

Every transform has a stable id that is written into the provenance of AI results (reproducibility).

* **`rgb_to_xyz(name)`**
* **`bradford(src_white, dst_white)`**
* **`conversion_matrix(src, dst='rec709')`**

  > Linear RGB in `src` primaries -> linear RGB in `dst` primaries (Bradford adaptation between whites).

* **`srgb_encode(x)`**

  > IEC 61966-2-1 piecewise sRGB curve on [0, 1].

* **`to_model_input(rgb, transform=DEFAULT)`**

  > H x W x 3 float in the source space -> sRGB-encoded Rec.709 float32 in [0, 1]. `transform`: a built-in id
  > or an `OcioTransform`.

* **`transform_id(transform)`**
* **class `OcioTransform`** (object)

  > OpenColorIO conversion `src` -> sRGB-encoded Rec.709 with a given config (file path or ocio:// URI).
  > The id records config, its cache id and both colour spaces.

  * `__init__(config, src, dst=None)`

### st_roto.commands

Every edit is an operation (ADR-0006): applied in a transaction, logged with its inverse, undoable.

An operation is a plain dict: {"op": <name>, ...arguments}. `CommandBus.execute(op, actor, author)`
  1. checks protection rules (REQ-042: AI never overwrites, unlocks or deletes artist / imported / locked work),
  2. applies the op and computes its exact inverse,
  3. appends both to the `operations` table in the SAME transaction (crash-safe, audit history),
  4. maintains in-session undo/redo stacks.
Undo applies the stored inverse (bypassing protection: it restores a previous exact state) and is itself logged.

* **class `ProtectedError`** (Exception)

  > Raised when an operation would modify content the actor is not allowed to touch.

* **class `CommandBus`**
  * `__init__(store, author='local', signer=None)` - signer: st_roto.signing.Signer for this author (T-084): every operation the bus makes is signed.
  * `execute(op, actor=m.ACTOR_ARTIST, origin=None, signature=None)` - origin=(op_uuid, site_id) and the author's `signature` when replaying an operation made elsewhere
  * `undo()`
  * `redo()`
  * `can_undo()`
  * `can_redo()`

### st_roto.delivery

Delivery packages (T-108, REQ-180, master prompt section 20): one zip per shot to hand over finished work.

Contents (every item the section lists):
  outputs/...                 final outputs: the matte EXRs and the JSON/SVG shape export given by the caller
  project_settings.json       the host node's settings (given by the caller) + shot description
  models.json                 metadata of every model that produced keys in this shot (from the shape generators
                              and the model manifests: repository, pinned revision, licence, approval)
  processing_report.json/.md  what was done: operations by kind / actor / author, first and last time, runs
  provenance.json             per object and shape: key origins (AI / artist / imported), generators
  quality_report.json/.md     per object: review flags (lost / check), key counts, confidence summary
  dependencies.json           ST-ROTO version, host, Python, libraries and their versions (given by the caller)
  MANIFEST.json               size + SHA-256 of every file in the package
Pure Python (no host imports); the host adapter gathers outputs, settings and dependencies.

* **`models_used(store, shot_id, manifests_dir=None)`**
* **`processing_report(store)`**
* **`provenance(store, shot_id)`**
* **`quality_report(store, shot_id)`**
* **`build(store, shot_id, out_zip, outputs=None, settings=None, dependencies=None, manifests_dir=None)`**

  > Write the delivery zip. outputs: {folder name in the package: local folder or file} (e.g. {"mattes": dir,
  > "shapes": dir}). Returns {"zip", "files", "bytes"}. Refuses an empty delivery (no objects).

* **`verify(zip_path)`**

  > Check every file of a delivery package against its MANIFEST: [] when complete and unchanged.


### st_roto.exr

OpenEXR matte files (T-070): one layer per object plus a combined alpha, one file per frame.

Uses the official OpenEXR Python binding (`OpenEXR`, BSD-3-Clause, Academy Software Foundation), imported lazily so
the core stays importable without it. Channel naming follows the EXR layer convention `<layer>.<channel>`; the
combined matte is the plain `A` channel, which Nuke reads as rgba.alpha (verified in tests/nuke).
Frame numbering follows Nuke's sequence convention: 4-digit padding, negative frames as sign + 3 digits
(`name.-002.exr`, measured, CLAUDE.md pitfalls).

* **`layer_name(name)`**

  > Object name -> EXR/Nuke-safe layer name (letters, digits, underscore; no leading digit).

* **`frame_path(directory, base, frame, ext='exr')`**
* **`sequence_pattern(directory, base, ext='exr')`**

  > Pattern for a Nuke Read node (forward slashes).

* **`write_mattes(path, layers, combined=True, compression='zip', half=False, attributes=None, rgb=None, extra=None)`**

  > layers: {object name: H x W float alpha}. Writes `<layer>.A` per object and, if `combined`, `A` = max over
  > objects (or the given combined alpha). Unique layer names are enforced (a clash gets a numeric suffix).
  > rgb: optional H x W x 3 foreground colour -> R, G, B (T-099; its alpha convention goes in `attributes`).
  > extra: {layer: H x W alpha} additional matte layers (e.g. core_matte, edge_matte), never clashing with objects.
  > Returns {object name: layer}.

* **`is_locked(path)`**

  > True if `path` exists and cannot be replaced right now (Windows: another program holds it open without
  > delete sharing - a Nuke Read node does, measured in T-099; clearing Nuke's caches or reloading does not
  > release it). Tested by renaming the file away and back.

* **`next_version_dir(directory)`**

  > '<dir>' -> '<dir>_v002' (or the next free _vNNN), for rendering when the current files are in use.

* **`read_channels(path)`**

  > {channel name: H x W array}. OpenEXR's Python API groups R, G, B(, A) - also inside layers, e.g.
  > CryptoObject00.R/G/B/A (measured, T-110) - unless asked for separate channels.

* **`read_header(path)`**

  > {attribute: value} of an EXR header (strings for text attributes, e.g. Cryptomatte manifests).


### st_roto.frames

Frame lists typed by artists ("12-14, 30, -2--1") and their compact text form (T-097). Pure Python 3.7.

* **`parse(text)`**

  > '12-14, 30' -> [12, 13, 14, 30] (sorted, unique). Accepts commas or spaces, negative frames ('-3--1'),
  > spaces around range dashes ('12 - 14') and reversed ranges. Raises ValueError naming the offending part.

* **`ranges(frames)`**

  > [12, 13, 14, 30] -> '12-14, 30'.


### st_roto.geometry

Bezier fitting for ST-ROTO (promoted from prototypes/geometry/bezier_fit.py on 2026-11-15, ADR-0008).

Coordinates follow st_roto.model (image space, y down); no host conventions here.

Algorithm: P. J. Schneider, "An Algorithm for Automatically Fitting Digitized Curves", Graphics Gems (1990):
least-squares cubic fit with chord-length parameterisation, Newton-Raphson reparameterisation, and
recursive splitting at the point of maximum error. Additions for roto use:
  * circular Gaussian smoothing of the pixel contour (removes raster staircase),
  * corner detection by turning angle (corners become cusp points; elsewhere tangents are shared, G1 smooth),
  * closed-loop handling.

Pure numpy so it can run both in the project venv and inside Nuke's Python 3.11.
Coordinates are whatever the caller passes (no flipping here).

* **class `Anchor`**

  > One spline vertex: position, absolute in/out handle positions, and whether it is a corner (cusp).

* **`smooth_closed(pts, sigma)`**

  > Circular Gaussian smoothing of a closed polyline (N,2).

* **`detect_corners(pts, window, angle_deg)`**

  > Indices where the turning angle between the incoming and outgoing chords (length `window`)
  > exceeds `angle_deg`; non-maximum suppression within the window.

* **`fit_closed_contour(contour, tol=1.0, smooth_sigma=1.5, corner_angle_deg=45.0, corner_window=6)`**

  > Fit a closed cubic Bezier spline to a closed contour (N,2) in pixels.
  >
  > tol: max allowed distance (px) from the smoothed contour to the curve.
  > corner_angle_deg: measured turning-angle threshold. Raster stepping + smoothing attenuate real corners
  >   (a true 69.7 deg corner measures 55-60 deg at window 6), hence 45 by default; a smooth curve of
  >   radius r turns only ~2*window/r rad over the window (circle r=200: ~3.4 deg).
  > Returns anchors in contour order; handles are absolute positions.

* **`fit_fixed_count(contour, k, start_hint=None, smooth_sigma=1.5)`**

  > Fit a closed spline with exactly `k` anchors (needed for animated Roto shapes: constant topology).
  >
  > Anchors are placed at equal arc-length spacing, starting at the contour point closest to `start_hint`
  > (e.g. anchor 0 of the previous frame) so that anchor i corresponds across frames. Handles are least-squares
  > fitted per segment (Schneider's generator) with G1 tangents estimated from the smoothed contour.

* **`trace_contours(field, level=0.0)`**

  > Marching squares: closed iso-contours where `field` crosses `level` (inside = field > level).
  >
  > `field` can be soft logits (sub-pixel accurate edges) or a binary mask converted with `mask - 0.5`.
  > Returns a list of (N,2) float arrays in canonical coordinates; outer boundaries and holes are separate loops.
  > Saddle cells are resolved by the cell-centre average.

* **`rasterize_closed(poly, height, width)`**

  > Exact even-odd rasterisation: pixel (r,c) is inside if its centre (c+0.5, r+0.5) is inside `poly`.

* **`mask_to_points(field, count=None, start_hint=None, level=0.0, tol=1.0)`**

  > Mask logits (or `binary - 0.5`) -> stored-key points [[x,y,hin_x,hin_y,hout_x,hout_y], ...] for the largest
  > region. count=None: adaptive fit (static shapes); count=k: exactly k anchors (animated shapes, constant
  > topology) with anchor 0 nearest to `start_hint`. Returns [] if the field has no region.
  > Multi-piece objects: callers needing every piece should use trace_contours directly (ADR-0004).

* **`rasterize_spline(anchors, height, width, per_segment=64)`**
* **`sample_spline(anchors, per_segment=64)`**

  > Dense closed polyline of the spline (for rasterising / error measurement).

* **`max_deviation(anchors, contour)`**

  > (max, mean) distance from each contour point to the nearest densely sampled spline point.


### st_roto.geomexport

Shape geometry for 3D interchange (T-113: Alembic, REQ-180 "where suitable"). Pure Python + numpy.

ST-ROTO shapes are 2D cubic Bezier splines in canonical image space (x right, y DOWN, absolute handles,
st_roto.model). For 3D packages they are written in PIXEL units on the z = 0 plane with y UP and the origin at the
bottom-left image corner (Nuke's 2D convention, so x/y equal the Roto values in Nuke):
    X = x,  Y = height - y,  Z = 0
Two representations per shape and frame:
  * curve: a closed (periodic) cubic Bezier curve, control points p0, out0, in1, p1, out1, in2, ..., in0 (3 per
    anchor) - the exact spline;
  * mesh: one polygon of the outline sampled `per_segment` times per Bezier segment - for readers without curve
    support (Nuke's classic 3D reads Alembic meshes but not curves).

* **`to_3d(xy, height)`**

  > (N, 2) canonical -> (N, 3) pixel units, y up, z = 0.

* **`curve_points(points, height)`**

  > Periodic cubic Bezier control points (3 per anchor) of one key, in 3D (see module doc).

* **`mesh_polygon(points, height, per_segment=16)`**

  > Outline polygon (M, 3) of one key, counter-clockwise in the y-up plane (front face towards +z).

* **`prim_name(name)`**

  > A valid USD/Alembic prim name from an object/shape name.


### st_roto.interchange

Open interchange formats (master prompt section 20): ST-ROTO JSON (full fidelity, round trip) and SVG.

JSON (`st_roto.shapes`, version 1) keeps object identity, hierarchy, names, colours, locks, provenance (origin of
objects, shapes and every key, generator records) and every keyframe, in ST-ROTO's canonical coordinate space,
which the file states explicitly. Importing creates NEW ids (no collision with existing content) and records the
content as imported (actor "import" -> origin imported_native, REQ-042: AI may not overwrite it); the original
origins stay readable in the file. SVG: one file per frame, one cubic-Bezier <path> per shape, same coordinates
(SVG's y axis also points down), for review tools, web and vector editors. Feather is not stored by ST-ROTO yet,
so neither format carries it.

* **`export_shot(store, shot_id)`**
* **`write_json(path, store, shot_id)`**
* **`import_shot(bus, data, shot_id)`**

  > Add the objects of an exported shot to `shot_id` as ONE undoable step. Returns {old id: new id}.

* **`path_data(points, closed=True)`**

  > SVG path 'd' for one stored key.

* **`svg_frame(store, shot_id, frame)`**

  > One frame as SVG: a <g> per object (id/name kept as attributes), a <path> per keyed shape on that frame
  > (no interpolation: only real keys are written).


### st_roto.jobs

Cancellable background jobs (ADR-0009). Pure Python: no Nuke, no Qt.

A job function receives the Job and calls `job.check()` regularly (raises Cancelled) and `job.report(p, msg)`.
Measured in Nuke 17.1's GUI: GPU work on a worker thread keeps the UI at full rate; cooperative cancellation
took ~39 ms (research/probes/2026-11-15_gui_threading).

* **class `Cancelled`** (Exception)
* **class `Job`**
  * `__init__(fn, name='job', on_progress=None, on_finish=None)`
  * `check()`
  * `report(progress, message='')`
  * `cancel()`
  * `start(background=True)`
  * `wait(timeout=None)`

### st_roto.leases

Object leases, presence and roles for collaboration (T-083; decisions D-024, D-035, D-036). PROTOTYPE layer:
the rules are enforced by the command bus; heartbeats are local until a network transport replicates them.

* A lease = (object, holder, acquired). While user X holds an object's lease, edits to that object (and its shapes,
  keys, feather) by anyone else are refused. Objects without a lease are open to everyone, so a solo artist never
  sees this layer.
* `set_lease` is an ordinary operation (audited, replicated, undoable): acquire (holder = yourself), renew, release
  (holder = None). Taking a lease held by someone else is an OVERRIDE: allowed only for a project supervisor and
  only when the holder is idle/offline, i.e. no presence heartbeat for IDLE_SECONDS (15 min, D-036). The override
  op records its evidence (holder, last heartbeat, idle seconds) for the audit.
* Presence = each user's latest heartbeat (`heartbeat`); not an operation (too frequent, no undo).
* Roles (`set_role`): artist / supervisor / admin. Only an admin assigns roles; the very first assignment in a
  project must be the author making themself admin (bootstrap).
Checks run when an operation is MADE (CommandBus.execute / redo). Operations replayed from a peer were checked
where they were made (their evidence is in the payload; T-084 signatures make it tamper-evident).

* **class `LeaseError`** (Exception)

  > An operation conflicts with a lease, a role rule or the idle rule.

* **`lease(conn, object_id)`**
* **`role(conn, user)`**
* **`last_heartbeat(conn, user)`**
* **`idle_seconds(conn, user, now=None)`**

  > Seconds since the user's last heartbeat; None if never seen (= offline).

* **`is_idle(conn, user, now=None)`**
* **`heartbeat(store, user, now=None, frame=None, activity=None)`**

  > Record that `user` is active (presence, §19.1: who is working, on which frame, doing what).

* **`presence(conn, now=None)`**
* **`apply_set_lease(conn, op, actor)`**

  > op: object_id, holder (None = release), by (author), override (bool), evidence (dict, overrides only).

* **`apply_set_role(conn, op, actor)`**
* **`check_edit(conn, op, author)`**

  > Refuse writes into objects leased by someone else (every actor: the AI runs on the author's behalf).

* **`check_made(conn, op, author, now=None)`**

  > Rules for an operation being MADE by `author` (not replayed). May add evidence to an override op.

* **`acquire(bus, object_id)`**
* **`release(bus, object_id)`**
* **`override(bus, object_id, take=True)`**

  > Supervisor override of an idle holder's lease: take it (default) or just free it.

* **`set_role(bus, user, role_name)`**

### st_roto.matte

Model-free soft edges for a hard shape (matting step 1, docs/RESEARCH_2026-11-16_MATTING.md). Pure numpy.

`refine_alpha(rgb, mask)`: the shape's hard mask decides what is surely inside / outside; only a band of
`band` pixels around its edge becomes soft, computed with the colour guided filter (He, Sun, Tang, "Guided Image
Filtering", ECCV 2010 / TPAMI 2013) using the plate as guide. Edges follow colour boundaries the shape missed by a
pixel or two, and partially covered pixels get partial alpha. This is an algorithm, no learned weights: it needs no
licence decision (OQ-22). It does NOT recover individual hair strands far outside the shape; that needs a learned
matting model plugged into the same mask -> band -> alpha pipeline.

Works on a crop around the edge, so cost scales with the object's outline, not the frame size.

* **`box_sum(x, r)`**

  > Sum over a (2r+1)x(2r+1) window (clipped at the borders), via an integral image. x: (H, W[, C]).

* **`box_mean(x, r)`**
* **`guided_filter(guide, src, r=4, eps=0.001)`**

  > Colour guided filter. guide (H, W, 3) float, src (H, W) float -> (H, W) float64.

* **`edge_band(mask, band)`**

  > Pixels within `band` (square window) of the mask edge: the window holds both inside and outside pixels.

* **`key_points_at(keys, frame)`**

  > Shape points at `frame` from its stored keys (sorted by frame): the key itself, a LINEAR blend of the two
  > neighbouring keys, or the first/last key held outside the keyed range. -> (points, how) with how in
  > {"key", "interpolated", "held"}, or (None, None) without keys. Linear blending differs from Nuke's own curve
  > interpolation between sparse keys; AI-tracked shapes are keyed on every frame, so it only matters for sparse,
  > hand-animated shapes (reported to the user).

* **`object_mask(store, object_id, frame, height, width)`**

  > Hard mask (bool H x W) of all shapes of an object at `frame` (union), exact pixel-centre rasterisation of
  > the stored splines. -> (mask, {shape name: how}) — see key_points_at.

* **`refine_alpha(rgb, mask, band=3, radius=8, eps=0.0001, margin=4)`**

  > Hard mask + plate -> soft alpha (H, W) float32 in [0, 1]. Outside the edge band alpha equals the mask.
  >
  > rgb: (H, W, 3) float plate in a perceptual-ish encoding (display-referred works best; the guided filter is
  > sensitive to colour differences, which are compressed in scene-linear darks). mask: (H, W) bool or {0,1}.
  > band: half-width in pixels of the zone that may become soft; radius/eps: guided-filter window and smoothness.
  > Defaults = best mean result on known-alpha composites (research/probes/2026-11-16_matting: SAD 0.59x the hard
  > shape's on average; soft edge 0.44x, motion blur 0.35x, 2 px offset edge 0.70x, missed hair 0.86x). The best
  > setting differs per scene, so hosts expose band/radius to the artist.

* **`feathered_alpha(points, feather_x, feather_y, falloff, height, width, width_factor=FEATHER_WIDTH, per_segment=16)`**

  > APPROXIMATION of Nuke Roto's shape feather for ST-ROTO's own EXR mattes (T-073): 1 inside the spline,
  > outside (1 - d / (width_factor * feather))^falloff with d the distance to the spline (per axis in units of
  > feather_x / feather_y when they differ), 0 beyond. Measured against Nuke's render (tests/nuke
  > test_feather_and_rotopaint, research/probes/2026-11-16_feather): the 50 % contour matches within ~1 px in
  > every direction and the area within 0.3 %, but the ramp's tails differ (mean |error| ~0.11 inside the feather
  > band): Nuke's ramp depends on the control points. Nuke stays authoritative: for exact feathered mattes render
  > the ST_Roto output in Nuke. (A 'feather curve from offset control points' model was tried and was not better.)

* **`object_alpha(store, object_id, frame, height, width)`**

  > Like object_mask but float alpha that includes each shape's feather (max over shapes). -> (alpha, how,
  > feathered: bool).

* **`offset_alpha(alpha, px)`**

  > Grow (px > 0, dilation) or shrink (px < 0, erosion) a matte by |px| pixels with a round kernel (REQ-12-10/11).
  > Works on soft mattes too (grey-scale morphology). 0 = unchanged.

* **`blur_edge(alpha, px)`**

  > Feather the matte edge with a Gaussian of sigma `px` pixels (REQ-12-12). Inside/outside far from an edge stay
  > 1/0. 0 = unchanged.

* **`core_edge(alpha, width)`**

  > Core matte (the matte eroded by `width` px: surely inside) and edge matte (alpha - core: the band where edge
  > work happens), both in [0, 1] (REQ-12-09 'multiple matte channels').

* **`rgb_mode_parts(mode)`**

  > 'premultiplied, decontaminated' -> ('premultiplied', True). Raises ValueError for unknown modes.

* **`foreground_rgb(rgb, alpha, mode, spill=None)`**

  > Foreground colour for a matte (REQ-12-01..04, T-099; T-115): 'premultiplied' = colour x alpha, 'straight' =
  > colour unmultiplied. '..., decontaminated': the colour of soft-edge pixels is recovered from the compositing
  > equation (`decontaminate`), else it is the plate's (which still contains the old background). spill: None,
  > 'auto' (screen colour judged from the background), 'green' or 'blue' -> `despill` of the foreground colour.
  > The convention is written into the file, never implied.

* **`estimate_layers(rgb, alpha, lo=0.02, hi=0.98)`**

  > (foreground estimate, background estimate) colours everywhere: the plate's colour pushed out from pixels that
  > are surely foreground (alpha >= hi) / surely background (alpha <= lo).

* **`decontaminate(rgb, alpha, lo=0.02, hi=0.98, solve_from=0.05, solve_full=0.3)`**

  > Edge decontamination / edge colour recovery (REQ-12, T-115): the foreground colour F of soft-edge pixels from
  > the compositing equation I = a F + (1 - a) B, with B estimated from the nearby background; where alpha is small
  > the solve is unstable, so F blends towards the colour pushed out from the solid foreground. Pixels with alpha
  > >= hi keep the plate colour; F is not defined where alpha = 0 (the solid-foreground estimate is used there).
  > Returns straight (un-premultiplied) foreground RGB.

* **`despill(rgb, colour='green', limit='average', amount=1.0)`**

  > Spill correction (REQ-12, T-115): the screen colour's channel is limited by the other two ('average' = (R+B)/2
  > for green, (R+G)/2 for blue; 'max' = the larger of them - gentler). `amount` 0..1 blends the correction. Applied
  > to foreground colour only (never to alpha). Note: genuinely green (or blue) foreground colours are reduced too -
  > the classic limitation of channel-limit despill.

* **`spill_colour_of(rgb, alpha, lo=0.02)`**

  > 'green' or 'blue': the screen colour judged from the background pixels (alpha <= lo), or None if the
  > background is not dominated by either.


### st_roto.metrics

Benchmark metrics (T-107, REQ-190, master prompt section 21.1). One implementation used for every benchmark, so
results are reproducible and comparable. Definitions and weights: docs/BENCHMARK_METHODOLOGY.md. numpy + OpenCV
(OpenCV imported lazily, only for boundary distances). Alphas are float arrays in [0, 1]; masks = alpha >= 0.5.

* **`iou(pred, gt)`**
* **`dice(pred, gt)`**
* **`mae(pred, gt)`**
* **`sad(pred, gt)`**

  > Sum of absolute differences in thousands (matting convention).

* **`mse(pred, gt)`**
* **`boundary_tolerance(shape)`**

  > Boundary match tolerance: 0.2 % of the image diagonal (a relative tolerance as in the DAVIS benchmark), at
  > least 1 px - about 4.4 px at 1920x1080.

* **`boundary_f(pred, gt, tol=None)`**
* **`hd95(pred, gt)`**

  > 95th percentile symmetric boundary distance in pixels (contour quality). inf if one side is empty.

* **`temporal_error(preds, gts)`**

  > Mean |(a_t - a_t-1) - (g_t - g_t-1)| over consecutive frames: flicker/drift the truth does not have.

* **`stability(ious, visible=None, kept=0.5)`**

  > Tracking stability over the frames where the object is visible: fraction kept (IoU >= 0.5) and the number of
  > losses (kept -> not kept transitions).

* **`identity_preservation(pred_by_obj, gt_by_obj)`**

  > Several objects on one frame: fraction of truth objects whose best-overlapping prediction is their own
  > (no swaps). pred_by_obj / gt_by_obj: {object id: alpha} with the same ids.

* **`sequence_scores(preds, gts, visible=None)`**

  > All per-sequence metrics for ONE object: preds / gts lists of alphas (same frames).

* **`category_scores(s, identity=1.0)`**

  > Normalised 0..1 (higher is better) per category, from sequence_scores (methodology section 4).

* **`overall(categories, weights=WEIGHTS)`**

### st_roto.model

Domain vocabulary shared by the store, commands and exporters (ADR-0004).

Canonical coordinate space for all geometry stored by ST-ROTO
-------------------------------------------------------------
Source-image pixel space at full resolution: x to the right, y DOWN, origin at the top-left corner of the
top-left pixel (so the centre of pixel (col,row) is (col+0.5, row+0.5)). Exporters convert to host
conventions (e.g. Nuke: y up, tangent = 2 x handle offset; see st_roto_nuke when it exists).

Shape keys store, per control point, six floats: x, y, h_in_x, h_in_y, h_out_x, h_out_y, where the
handles are ABSOLUTE positions of the cubic Bezier control points (h_in belongs to the segment arriving
at the point, h_out to the segment leaving it).

Frames are arbitrary integers (negative, gaps and non-contiguous ranges allowed: master prompt section 11).

* **`new_id()`**
* **`origin_for_write(actor, previous_origin)`**

  > Origin recorded when `actor` writes over content whose previous origin is `previous_origin`.

* **`validate_points(points, point_count)`**

  > Return points as a list of `point_count` lists of 6 finite floats, or raise ValueError.


### st_roto.persistence

Backups, crash recovery and portable project packages (T-071, master prompt section 18). Pure Python (stdlib).

What is already safe without this module: every edit is ONE SQLite transaction in WAL mode, logged with its inverse
(ADR-0006), so a crash loses at most the edit in flight, never a half-applied one. This module adds:

* `backup()`        consistent snapshot of an OPEN project (SQLite online backup API), verified, rotated;
* `AutoBackup`      background thread: snapshot every `interval` seconds, only when the operation log changed;
* `SessionMarker`   `<project>.session.json` while a process has the project open; a marker left by a process that
                    no longer runs = the previous session ended uncleanly (crash, power loss: R-38);
* `check()` / `recover()`  integrity check; a damaged file is MOVED aside (never deleted) and the newest backup
                    that passes the check is restored;
* `pack()` / `unpack()`  portable package (zip): consistent database snapshot, manifest with checksums, optional
                    mattes / exports / source frames; unpack verifies checksums, refuses unsafe paths and relinks
                    shot source paths.
Model weights are never packaged (they are referenced by id; D-008).

* **`default_backup_dir(project_path)`**
* **`check(path)`**

  > {"ok", "detail", "schema", "operations"} without modifying the file (read-only connection).

* **`last_operation(path)`**
* **`backup(project_path, backup_dir=None, keep=20, reason='auto')`**

  > Snapshot the project into `backup_dir` (default `<project>_backups/`), verify it, keep the newest `keep`
  > backups of the same `reason` (others are never rotated away). Returns the backup path.

* **`list_backups(project_path, backup_dir=None, reason=None)`**

  > Backups of this project, newest first.

* **class `AutoBackup`** (object)

  > Snapshot every `interval` seconds while the operation log keeps changing. Uses its own read-only
  > connections, so it never blocks or touches the host's connection (SQLite WAL allows concurrent readers).

  * `__init__(project_path, interval=300.0, keep=20, backup_dir=None)`
  * `start()`
  * `tick()` - One check (also callable directly, e.g. on script save). Returns a backup path or None.
  * `stop(final=True)`
* **class `SessionMarker`** (object)

  > `<project>.session.json` while this process has the project open.
  >
  > `previous` after `acquire()`: None (clean), or the marker found: with "state" = "crashed" (its process is gone
  > on this machine), "open_elsewhere" (another live process here) or "other_host" (cannot tell).

  * `__init__(project_path)`
  * `acquire(info=None)`
  * `release()`
* **`recover(project_path, backup_dir=None)`**

  > If the project fails the integrity check: move it (and its -wal/-shm) aside as `.damaged.<stamp>` and
  > restore the newest backup that passes. Returns {"action": "none"|"restored"|"failed", ...}.

* **`pack(project_path, zip_path, include_dirs=('_mattes', '_export'), include_sources=False, tool_version='', scripts=())`**

  > Portable package of an (open or closed) project. `scripts`: Nuke scripts to include (scripts/<name>); on
  > unpack their paths to the project, its folders and the plates are rewritten. Returns the manifest.

* **`unpack(zip_path, dest_dir, relink=None)`**

  > Extract a package into `dest_dir` (must be empty or new), verify every checksum, refuse paths escaping
  > `dest_dir`, then relink: shot source paths (packaged sources -> their extracted location; others via `relink`
  > {old prefix: new prefix}) and, in packaged Nuke scripts, the project path, its folders and the plate paths.
  > Relinked sources are checked against the recorded fingerprints.
  > Returns {"project", "manifest", "missing_sources", "fingerprints": {shot id: state}, "scripts"}.

* **`sequence_files(pattern)`**

  > Existing files of a Nuke-style sequence path (####, %04d) or a single file, sorted.

* **`fingerprint_sequence(pattern, first=None, last=None)`**

  > JSON fingerprint of a source sequence: SHA-256 + size of its first and last frame and how many frames of the
  > range exist (T-075). With a frame range the shot's own first/last frames are used (a folder often holds more
  > frames than the shot); without one, the first/last matching files. Returns None when nothing exists.

* **`compare_fingerprint(recorded, pattern)`**

  > {"state": "match" | "different" | "missing" | "unknown", "detail"} for a source path against a recorded
  > fingerprint ('unknown': nothing was recorded, e.g. projects from before schema v4). The recorded frame range
  > is used for the comparison.

* **`relink_text(text, mapping)`**

  > Replace path prefixes in a plain-text file (a commercial-edition .nk script), longest first, case-insensitive
  > for Windows paths, / and \ spellings.

* **`relink_shot(bus, shot_id, new_path)`**

  > Point a shot at a new source path (one undoable step) after checking it against the recorded fingerprint.
  > Returns the comparison; refuses 'different' footage unless the caller relinks via update_shot directly.

* **`frame_file(pattern, frame)`**

  > Path of one frame of a Nuke-style sequence path: '#' runs or %0Nd, negative frames as sign + (N-1) digits
  > (Nuke: 'name.-002.tif' for #### and frame -2, measured).

* **`relink_path(path, mapping)`**

  > Apply the longest matching prefix of `mapping` to one path. Windows paths compare case-insensitively and
  > with / or \ (Nuke stores 'd:/...' even when the folder was given as 'D:\...', measured).

* **`is_encrypted_script(path)`**

  > Nuke Non-commercial saves scripts encrypted (measured: '.nknc' starting 'Nuke NC mode encrypted text'):
  > paths in them cannot be rewritten as text; relink after opening the script in Nuke instead.


### st_roto.pieces

Mask sequence -> animated shapes with constant topology, for objects that split into several pieces (T-049).

A tracked object's mask can break into pieces (an occluder cuts it in two, a person's arm separates from the body).
Roto shapes need a constant point count over time, so each piece becomes its own animated shape:
  * the MAIN shape follows the piece nearest to its previous position (the largest piece at the start);
  * extra pieces become PART shapes, matched across frames by centroid distance; a part is created the first time
    an unmatched piece appears;
  * on frames where a part does not exist it gets a COLLAPSED key (every point at one position: zero area, renders
    nothing in Roto and in mattes) - Roto would otherwise hold or interpolate the neighbouring keys;
  * point counts are ADAPTIVE: the smallest count whose spline fits the piece's contour within tolerance at its
    first appearance (then constant, as Roto requires).
Holes inside a piece (e.g. a ring) are not represented yet (they would need a subtracting shape); they are counted
in `holes` so the caller can report them.

* **`outer_loops(field, level=0.0, min_area=50.0, min_fraction=0.02)`**

  > -> (outer loops sorted by area desc, number of holes). Pieces smaller than `min_area` px^2 or than
  > `min_fraction` of the largest piece are ignored (speckle).

* **`choose_count(loop, mean_tol=0.3, max_tol=1.5, counts=COUNTS)`**

  > Smallest anchor count whose fixed-count spline fits `loop` within tolerances (pixels); the largest count
  > if none does. Measured on the synthetic shot's truth masks: 16 (frame 0), 24 (frame 20), 12 (frame 30).

* **`to_points(anchors)`**
* **`centroid(points)`**
* **`collapsed(count, at)`**
* **`is_collapsed(points)`**
* **class `Sequencer`** (object)

  > Feed one mask per frame in VISIT order (`add`), then `result(frames)`.
  >
  > count: fixed main-shape point count, or "auto". `ref`: the frame whose shapes give point order and positions
  > for this one (the previous frame in visit order; a reverse pass starts again from its conditioning frame).
  > Frames the AI did not decide (artist keys) are registered with `add_known` so they can serve as references.

  * `__init__(count='auto', parts=True, min_area=50.0, min_fraction=0.02, match_px=None)`
  * `add_known(frame, points)`
  * `add(frame, field, ref=None, present=True)` - field: mask logits (or binary - 0.5) of the whole object; present=False: AI says no object here.
  * `result(frames)` - -> {"main": {frame: points}, "parts": [{frame: points}], "holes": {...}}. Parts get collapsed keys on
* **`sequencer_state(seq)`**

  > JSON-safe state of a Sequencer (checkpoints, T-048).

* **`sequencer_from_state(d)`**

### st_roto.presets

Settings presets for the ST_Roto node (T-111, REQ-120/REQ-121 'presets'). Pure Python.

A preset is a named set of NODE SETTINGS (model, edges, matte options, channels to check, ...), never shot data
(prompts, object names, frame ranges, project or output paths). Files are JSON:
    {"format": "st_roto.preset", "version": 1, "name": ..., "description": ..., "settings": {knob: value}}
Locations, highest priority first (a preset name found in several places uses the first):
    user    ST_ROTO_USER_PRESET_DIR, else %USERPROFILE%/.st_roto/presets (created when the artist saves one)
    studio  ST_ROTO_PRESET_DIR (several folders separated by os.pathsep; read-only for ST-ROTO)
    builtin BUILTIN below (shipped with ST-ROTO)

* **`user_dir()`**
* **`studio_dirs()`**
* **`file_name(name)`**
* **`validate(settings)`**

  > -> (clean settings, [problems]). Unknown knobs and values of the wrong type are dropped and reported.

* **`list_presets()`**

  > [{"name", "origin": "user"|"studio"|"builtin", "description", "path"}] - one entry per name, highest
  > priority origin first; unreadable files are listed with an "error".

* **`load(name)`**

  > {"name", "origin", "description", "settings", "problems"} of the highest-priority preset called `name`.

* **`save(name, settings, description='', directory=None)`**

  > Write a user preset (or into `directory`); replaces a user preset of the same name. Returns the path.

* **`delete(name)`**

  > Delete a USER preset; studio and built-in presets cannot be deleted from here. Returns the removed path.


### st_roto.prompts

AI prompt points (include / exclude clicks), stored as JSON on the host node. Pure Python.

A prompt is {"frame": int, "x": float, "y": float, "label": 1 | 0, "object": str} in canonical image coordinates
(y down, st_roto.model). Several objects can be prompted on one node (T-067); each object's points must be on ONE
frame (the frame its tracking starts from). Points without "object" (files written before T-067) belong to the
`default` object the caller passes (the node's current object name).

Box prompts (OQ-25, T-079): an object may have ONE box, stored as two points with SAM's corner labels
BOX_TL (2, top-left) and BOX_BR (3, bottom-right) on the object's prompt frame. On real footage (SA-V, T-068) a
single click picked the wrong object in 19 of 51 first frames, a box + click in 2 of 51. The tracker receives the
box corners first, then the clicks (SAM 2 reference order).

* **`load(text)`**
* **`dump(points)`**
* **`add(text, frame, x, y, label, obj=None)`**

  > Add a point for object `obj` (None: an untagged point, the pre-T-067 format).

* **`set_box(text, frame, x0, y0, x1, y1, obj=None)`**

  > Set (replace) the box of object `obj` on `frame`; corners in canonical coordinates, any order.

* **`clear_box(text, obj, default=None)`**

  > Remove the box of one object, keep its clicks.

* **`clear(text, obj, default=None)`**

  > Remove the points of one object (untagged points count as `default`).

* **`groups(text, default=None)`**

  > -> [{"name", "frame", "points": [(x, y)], "labels"}] per object, in order of first appearance.

* **`summary(text, default=None)`**
* **`for_tracker(text, default=None)`**

  > -> (frame, [(x, y), ...], [label, ...]) of a node with ONE prompted object; raises if there is no include
  > point. Several objects: use `objects_for_tracker`.

* **`objects_for_tracker(text, default=None)`**

  > Like `groups`, but every object needs an include point or a box (artist-readable error otherwise); box
  > corners come first (SAM 2 reference order: box, then clicks).

* **`from_mask(mask, max_pieces=3, min_fraction=0.02)`**

  > A rough mask -> the prompt measured best on real footage (T-082): its tight box + the most interior pixel of
  > each piece (largest first, at most `max_pieces`, pieces under `min_fraction` of the mask ignored). T-100: used
  > for Roto shapes / polygons, mattes from other nodes and imported mask files. SAM 2 would take a MASK prompt as
  > the final answer on its frame (a rough polygon would stay rough); a box + clicks lets it draw the object itself.
  > mask: H x W bool (canonical, y down). Returns {"box": (x0, y0, x1, y1), "points": [(x, y), ...]}.

* **`set_from_mask(text, frame, mask, obj=None)`**

  > Replace object `obj`'s prompts with the box + interior clicks of `mask` on `frame` (from_mask).


### st_roto.quality

Which AI frames should an artist review? (master prompt §9: confidence estimates, failure detection). Pure Python.

The thresholds are HEURISTICS from the synthetic test shot (research/probes/2026-11-16_corrections: a frame whose
object score was 0.025 flipped between "present" and "absent" on tiny input differences; neighbours scored 0.96
and 1.09). They must be calibrated on real footage by the benchmark programme before being trusted.

* **`area_jumps(areas, threshold=None)`**

  > {frame: relative change} for frames whose area differs by more than `threshold` from BOTH nearest frames
  > that have an area (> 0). Catches confidently wrong frames the model's own scores miss (T-078: the synthetic
  > split frame, score 8.0, predicted IoU 0.98, true IoU 0.42). Uncalibrated: CHECK level only.

* **`absent_runs(reports)`**

  > [(first_frame, last_frame, n_reports)] of consecutive absent reports (score <= 0) between present ones.

* **`review_frames(reports, keyed_frames, areas=None, lost_max_gap=None)`**

  > reports: [{"frame", "object_score", "iou_pred"}], keyed_frames: frames that currently have a key,
  > areas: optional {frame: shape area} (AI frames). Returns [(frame, level, reason), ...] sorted by frame;
  > level is LOST or CHECK. Absent runs longer than `lost_max_gap` reports (default LOST_MAX_GAP) flag only their
  > first and last frame (CHECK): real footage objects leave and return.

* **`summary(flags)`**

  > 'lost 16-20, 22; check 15, 21' or ''.

* **`ranges(frames)`**

  > [3,4,5,9] -> '3-5, 9' for compact status messages.


### st_roto.runtime_choice

Which ONNX Runtime build ST-ROTO loads into Nuke (T-116, REQ-020). Pure Python, no Nuke / ONNX Runtime import.

ST-ROTO ships two builds of ONNX Runtime, in separate folders, because both are the Python package `onnxruntime`
and only one can be imported per process:
* `.tools/nuke-py311`      onnxruntime-gpu 1.26.0: CUDA 12, NVIDIA GPUs (fastest there; uses Nuke's CUDA DLLs);
* `.tools/nuke-py311-dml`  onnxruntime-directml 1.24.4: DirectML, any DirectX 12 GPU (AMD, Intel, NVIDIA).
The choice is made once, when Nuke starts (nuke_plugin/init.py), from the environment variable ST_ROTO_RUNTIME:
  auto (default)  CUDA build if the NVIDIA driver is installed (nvcuda.dll present), else DirectML;
  cuda | directml force one build (e.g. directml on an NVIDIA machine whose driver is too old for CUDA 12).
Measured on an RTX 5060 Laptop (research/probes/2026-11-18_directml): the same masks (per-frame IoU DirectML vs CUDA
>= 0.997), DirectML 7-20 % slower, so CUDA stays first where it works.

* **`nvidia_driver_present()`**

  > True if the NVIDIA display driver's CUDA library is installed (Windows: System32\nvcuda.dll). No process is
  > started and nothing is loaded.

* **`choose(setting, nvidia, dml_available)`**

  > -> (build, reason). setting: the ST_ROTO_RUNTIME value ('' = auto); nvidia: nvidia_driver_present();
  > dml_available: the DirectML folder is installed. Never fails: an unusable request falls back with the reason.

* **`site_dirs(root, build)`**

  > Folders to append to sys.path, in order: the chosen build's onnxruntime must come before the CUDA folder
  > (which also holds numpy, OpenCV, OpenEXR used by both).

* **`active()`**

  > (build, reason) chosen at Nuke start-up, or (None, '') outside the plugin.


### st_roto.scenecut

Scene-cut detection (T-123, master prompt section 11: temporal strategies; acceptance criterion 7).

A tracker must not carry an object across a hard cut: after the cut the pixels belong to another shot, and SAM 2.1
keeps "finding" something there. Pure Python + numpy (no Nuke / OpenCV / AI): the host passes frames in.

Method (classic shot-boundary detection, made robust for VFX plates):
* every frame -> a small thumbnail (area average to about 64 x 36, display-encoded so dark plates are not flat);
* score of each pair of consecutive frames = colour-histogram distance (1 - intersection of 8x8x8 joint RGB
  histograms; insensitive to motion inside the frame) and the mean thumbnail difference;
* a CUT between f-1 and f when the histogram distance is high in absolute terms (>= HIST_MIN) AND much higher than
  around it (>= RATIO x the median of the neighbouring scores: fast camera moves raise every score, a cut only one);
* flashes, one- or two-frame glitches and strobes are NOT cuts: if the frame before the jump matches a frame
  shortly after it (within FLASH_SPAN), the content came back.
Dissolves / fades are gradual and are not detected (documented limit); the artist can type cut frames by hand.
Thresholds were chosen on real footage (30 SA-V videos; no held-out set) and checked on synthetic sequences
(research/probes/2026-11-18_scenecut, tests/unit/test_scenecut.py).

* **`thumbnail(rgb)`**

  > H x W x 3 (linear or display float, or uint8) -> THUMB float32 in [0, 1], display-encoded.

* **`histogram(t)`**
* **`distance(ta, tb, ha=None, hb=None)`**

  > (histogram distance, mean abs thumbnail difference) of two thumbnails.

* **`scores(thumbs)`**

  > Per consecutive pair: [(hist, diff)] with len(thumbs) - 1 entries (entry i = frames i -> i + 1).

* **`detect(thumbs, frames=None)`**

  > thumbs: thumbnails in shot order; frames: their frame numbers (default 0..n-1; gaps allowed). Returns the
  > frames that START a new shot, and a per-pair report [{frame, hist, diff, local, cut, why}].

* **`segment(frame, cuts, first, last)`**

  > (lo, hi) of the shot segment holding `frame` within first..last, given the cut frames (each starts a new
  > segment).

* **`parse(text)`**

  > '12, 48' -> [12, 48] (the knob holding the cuts; the artist may edit it).

* **`format_cuts(cuts)`**

### st_roto.signing

Signed operations (T-084, D-037): every replicated operation is signed by its author with Ed25519.

Pure Python (RFC 8032 Ed25519, no dependency: runs in every Nuke Python, 3.7+). Validated against the RFC 8032
test vectors and, where installed, the `cryptography` package (tests/unit/test_signing.py). Not constant-time:
fine for signing one's own edits on one's own machine; the private key never leaves it.

* A user's key pair: `generate_key()` -> 32-byte seed (PRIVATE, kept in a key file outside the project database,
  `save_key` / `load_key`), `public_key(seed)` -> 32 bytes, registered in the project with the `set_user_key`
  operation (stored in `user_keys`).
* What is signed: the canonical JSON of {op_uuid, site_id, author, actor, payload} (`message`). The signature is
  stored with the operation (operations.signature) and travels in change files.
* Collaboration mode = at least one registered key. Then every operation imported from a peer must carry a valid
  signature by its author's registered key, or it is refused (`st_roto.sync.import_changes`). `verify_log`
  re-checks a project's whole history (tamper evidence for the audit).

* **`public_key(seed)`**
* **`sign(seed, msg)`**
* **`verify(pub, msg, sig)`**
* **`generate_key()`**
* **`save_key(path, seed)`**

  > Write a private key file (hex). Refuses to overwrite: losing a key cannot be undone.

* **`load_key(path)`**
* **`key_dir()`**

  > Where private keys live (D-038, owner-approved): %USERPROFILE%\.st_roto\keys (~/.st_roto/keys elsewhere).
  > Outside every project, so a key is never shared, packaged or synced with project data. Created on first use.
  > The environment variable ST_ROTO_KEY_DIR overrides it (tests; studios with managed home folders).

* **`key_path(user, folder=None)`**
* **`load_or_create_key(user, folder=None)`**

  > (seed, created): the user's private key from the key folder, generated and saved there if missing.

* **`to_hex(b)`**
* **`from_hex(s)`**
* **`message(op_uuid, site_id, author, actor, payload)`**

  > The exact bytes signed for an operation (canonical JSON; identical on every site).

* **class `Signer`**

  > Signs the operations a CommandBus makes, for one author.

  * `__init__(author, seed)`
  * `sign_op(op_uuid, site_id, actor, payload)`
* **`keys_of(conn, user, active_only=True)`**
* **`collaboration_mode(conn)`**
* **`verify_op(conn, op_uuid, site_id, author, actor, payload, signature, active_only=True)`**

  > '' if valid, else the reason. A key's own registration is self-signed by the new key.

* **`verify_log(store)`**

  > Re-check every signed operation in the project history against every key its author ever registered
  > (revoked keys still prove past work). Returns {"signed", "unsigned", "bad": [(seq, why)]}. A bad signature
  > means the logged operation was altered after it was made, or forged.

* **class `KeyRuleError`** (Exception)

  > A key registration or revocation is not allowed.

* **`apply_set_user_key(conn, op, actor)`**

  > op: user, public_key (hex), revoke (bool). Inverse restores the previous state of that (user, key).

* **`check_made(conn, op, author)`**

  > Key rules for an operation made locally: register keys for yourself only (an admin may register or revoke
  > anyone's); the remove form is reserved for undo.

* **`register(bus)`**

  > Register the public key of the bus's signer for its author (the op is self-signed by that key).

* **`revoke(bus, user, public_hex)`**

### st_roto.stereo

Stereo and multi-view support (T-109, REQ-115, master prompt section 13.4). Pure Python + numpy.

Model: every view gets its OWN object (tracked independently, never derived frame by frame from another view).
Objects of one subject in different views share `objects.pair` (the correspondence key) and carry `objects.view`
(the Nuke view name; NULL = every view, i.e. a monoscopic object). Names follow `view_object_name`.

* `estimate_disparity` finds where an object seen in one view lies in another view (masked block matching along
  the epipolar line with a small vertical tolerance, coarse-to-fine, sub-pixel). It is used ONCE per object, on its
  prompt frame, to carry the artist's prompt to the other views (`transfer_prompt`): the other view is then tracked
  by the AI on its own pixels.
* `consistency` compares corresponding objects frame by frame (vertical alignment, size, disparity continuity,
  presence) and returns CHECK flags. The thresholds are PROVISIONAL (synthetic stereo shot, research/probes/
  2026-11-17_stereo); no permissively licensed real stereo ground truth has been found yet.

* **`view_object_name(base, view)`**
* **`key_geometry(points)`**

  > {"area", "cx", "cy", "x0", "y0", "x1", "y1"} of one closed spline key (area-weighted centroid).

* **`merge_geometry(parts)`**

  > Union of several shapes' geometry on one frame (area-weighted centroid, union box). Zero-area parts (collapsed
  > part keys, T-049) are ignored; None if nothing has area.

* **`object_geometry(store, object_id)`**

  > {frame: geometry or None} of an object (all its shapes). None = keyed but without area (object absent).

* **`counterparts(store, object_id)`**

  > Rows of the objects corresponding to `object_id` in other views (same shot and pair, other view).

* **`mask_from_keys(keys, height, width)`**

  > Union mask (HxW bool) of several shape keys (point lists) on one frame; collapsed part keys add nothing.

* **`mask_box(mask)`**

  > (x0, y0, x1, y1) pixel-edge box of a mask, or None if empty.

* **`estimate_disparity(img_a, img_b, mask, max_dx=None, max_dy=MAX_VERTICAL, margin=2)`**

  > Where the masked region of view A appears in view B: b(x + dx, y + dy) ~ a(x, y).
  >
  > img_a, img_b: HxW(x3) float images of the same frame in two views; mask: HxW bool (the object in A).
  > max_dx: horizontal search radius in pixels (default 10 % of the width); max_dy: vertical radius.
  > Returns {"dx", "dy" (sub-pixel), "error" (zero-mean masked mean squared difference at the best shift),
  > "ambiguity" (best error / best error at least 3 px away horizontally: near 1 = repetitive texture, unreliable)}
  > or raises ValueError if the mask is empty.

* **`estimate_shift_epipolar(img_a, img_b, mask, F, max_along=None, tol=3.0, margin=2, scale_of=None)`**

  > T-120: where the masked region of view A appears in view B when the cameras are KNOWN (non-rectified rigs,
  > vertical disparity, any number of views): the object's centre c must land on its epipolar line F c in B, so the
  > search runs along the part of that line inside B and only +-tol px across it, coarse-to-fine, comparing with
  > normalised cross-correlation. scale_of(shift) -> how much larger B sees the object if it is at that shift
  > (from the cameras: depth by triangulation); with it each candidate is compared with the template resampled at
  > its own scale (in SCALE_STEP steps) - needed when the views see the object at different sizes (measured: an
  > 11 % smaller view matched the wrong place without it). Assumes one shift for the whole object (a box prompt).
  > Returns {"dx", "dy", "error", "ambiguity", "line_distance", "scale"}.

* **`epipolar_distances(geo_a, geo_b, F_of)`**

  > {frame: distance (px) of the object's centroid in view B from the epipolar line of its centroid in view A}.
  > F_of(frame) -> F (A->B) or None. Centroids are not exactly corresponding points (perspective, occlusion), so
  > the check is coarse: it catches the wrong object or a shape far off, not edge detail.

* **`transfer_prompt(obj, dx, dy, box, width, height, name=None, scale=1.0, centre=None)`**

  > Prompt for another view: the object's clicks moved by (dx, dy), preceded by a box (x0, y0, x1, y1) = the
  > object's extent in the source view moved by (dx, dy) (box + click: the most reliable prompt, T-082). Points
  > that leave the image are dropped; None if the box falls (mostly) outside the image.
  > T-120: `scale` (from the known cameras: focal / depth ratio) resizes the box and the clicks about `centre`
  > (the object's centre in the source view; default the box centre) - views with another focal length or distance
  > see the object at another size.

* **`consistency(geo_a, geo_b, name_a='A', name_b='B', rectified=True)`**

  > Compare one object's geometry in two views ({frame: geometry or None}, from `object_geometry`).
  >
  > Returns {"frames": {frame: {"dx", "dy_top", "dy_bottom", "area_ratio"}}, "offset": (median dy_top, median
  > dy_bottom), "disparity": median dx, "flags": [(frame, reason)]}. Flags (CHECK level, provisional thresholds):
  >   * present in one view only (keyed frames of either object);
  >   * vertical misalignment: top AND bottom edges deviate from the shot's usual vertical offset by more than
  >     max(VERTICAL_TOL_PX, VERTICAL_TOL_FRAC x object height) (one edge alone can be a view-dependent occlusion);
  >   * size: area ratio above AREA_RATIO_MAX;
  >   * disparity jump: horizontal disparity differs from BOTH neighbouring frames by more than
  >     max(DISPARITY_JUMP_PX, DISPARITY_JUMP_FRAC x |median disparity|).
  > rectified=False (T-120: the cameras are known and the views are NOT a rectified pair - toe-in, roll, other focal
  > lengths): the vertical and size rules are skipped (such rigs violate them legitimately); the epipolar check
  > (channels.review_flags, 'epipolar_px') replaces them.

* **`review_for_object(store, object_id)`**

  > Stereo CHECK flags of an object against each corresponding object: [(frame, "check", "stereo: ...")].


### st_roto.store

Per-project SQLite store (ADR-0005, D-027).

Essential project state lives here; regenerable data (AI features, cached masks) does not.
Design rules:
  * schema versions via PRAGMA user_version with forward-only migrations;
  * WAL journal + foreign keys; every mutation happens inside a transaction (see commands.CommandBus);
  * SQL kept to features available in old SQLite builds (no RETURNING, no UPSERT) for Nuke 13's Python 3.7.

* **`utc_now()`**
* **class `ProjectStore`**

  > Open (creating if needed) an ST-ROTO project database.

  * `__init__(path)`
  * `site_id()` - This copy's replication site id (created on first use; a copied project must get a new one:
  * `schema_version()`
  * `transaction()`
  * `row(table, row_id)`
  * `objects(shot_id)`
  * `shapes(object_id)`
  * `key(shape_id, frame)`
  * `keys(shape_id)`
  * `feathers(shape_id)` - Per-point feather keys {frame: [[fx, fy, lx, ly, rx, ry], ...]} (T-076).
  * `reports(shape_id)`
  * `channel_reports(object_id)` - {frame: report dict} of an object's extra-channel checks (T-110).
  * `operations()`
  * `close()`

### st_roto.sync

Operation-based replication between copies of a project — PROTOTYPE of docs/COLLABORATION_ARCHITECTURE.md
(T-020, decisions D-022/D-023). Pure Python; transport here = a JSON file (folder / USB); network transports later.

* Every operation has a global `op_uuid` and the `site_id` where it was made (schema v6).
* `export_changes` writes the operations MADE at this site after a mark; `import_changes` replays a peer's
  operations through the command bus (protection rules still apply) unless one of them touches a key that was
  ALSO changed locally since the last sync with that peer: then it waits as a BRANCH CANDIDATE (D-023) for the
  object owner to resolve (`resolve`). Different keys (e.g. other frames) merge automatically.
* Idempotent: an operation already present (same op_uuid) is skipped; nothing is echoed back.

* **`fork_site(store)`**

  > Give a COPIED project its own site id (two copies must never share one) and remember the fork point: the
  > history up to it is shared, so the first sync with the original only compares edits made after it.

* **`touched(op)`**

  > Merge keys an operation changes: ('key', shape, frame), ('shape', id), ('object', id), ('shot', id).
  > Diagnostics (set_report) are not conflict keys: the latest AI run wins.

* **`export_changes(store, since_seq=0)`**
* **`write_changes(path, store, since_seq=0)`**

  > Export the operations made at this site after `since_seq` into a JSON file (import is idempotent, so
  > re-sending is harmless).

* **`import_changes(store, changes)`**

  > Replay a peer's operations. Returns {"applied", "skipped", "candidates", "errors"}.

* **`candidates(store, include_resolved=False)`**
* **`resolve(bus, candidate_id, take)`**

  > take='remote': apply the peer's version, replayed under its ORIGINAL operation id (so later syncs see it
  > as known); 'local': keep ours. The candidate row stays as a resolved tombstone (audit + idempotent sync).


### st_roto.views

Read-only views of project state for UIs (object panel). Pure Python.

* **`object_rows(store, shot_id)`**

  > One row per object: id, name, parent_id, origin, locked, shapes, keys, first/last keyed frame.

* **`review_for_object(store, object_id)`**

  > Frames of an object's shapes that the artist should review: [(frame, level, reason)].

* **`shot_shapes(store, shot_id)`**

  > All shapes of a shot (id, name, object_id, object_name) in creation order.

* **`part_of(shape)`**

  > Main shape id if `shape` is an AI part shape (an extra piece of a split object, T-049), else None.

* **`main_shape(store, object_id)`**

  > The object's main shape: the first (creation order) that is not a part shape; None without shapes.

* **`part_shapes(store, main_id)`**
* **`merge_ops(store, source_id, target_id)`**

  > Ops merging object `source_id` into `target_id` (T-098): every shape of the source moves to the target
  > (keys, feather, provenance and part links unchanged), then the empty source object is deleted. Run them as ONE
  > batch (one undo step). The target's main shape stays its main shape.

* **`combine_roles(alphas, roles)`**

  > Combined matte of several objects with roles (T-098), exactly as Nuke's Roto composites ST-ROTO's shapes
  > (measured, research/probes/2026-11-17_roles): 'add' objects composited over each other (a + b - a*b), then
  > every holdout subtracted, then (1 - garbage) subtracted for every garbage object, clamped to [0, 1].
  > alphas: {name: HxW float}; roles: {name: role}. Returns HxW float32 or None without objects.

* **`rename_ops(store, object_id, new_name)`**

  > Ops renaming an object and the shapes named after it: '<old>' -> '<new>' and AI parts '<old>_part<n>' ->
  > '<new>_part<n>' (T-049). Shapes the artist named differently keep their names.

* **`timeline(store, shot_id)`**

  > Per object, what the timeline in the Objects pane draws (T-102, REQ-120): [{"id", "name", "role", "keys":
  > {frame: "artist" | "ai"}, "flags": {frame: "lost" | "check"}, "locked": [frames]}] in object order. Keys of
  > every shape of the object count (a frame with any artist key is 'artist'); collapsed part keys are ignored.

* **`review_levels(store, shot_id)`**

  > {object_id: {frame: (level, reason)}} - the worst review flag per object and frame (LOST before CHECK), with
  > every reason of that frame joined. Used by the viewer overlay (T-111) and the 'this frame' readout.

* **`colour_runs(levels, first, last, colours)`**

  > Overlay colour keys for frames first..last from {frame: level}: [(frame, (r, g, b, a))] keyed at the first and
  > last frame of every run of equal colour, so linear interpolation between keys is constant on whole frames.
  > Frames without a level get (0, 0, 0, 0) = Nuke's default outline colour (measured, T-111).


## `st_roto_ai` - AI layer: ONNX Runtime + numpy; no Nuke or Qt

### st_roto_ai.registry

Model registry: licence, revision, approval and checksum verification BEFORE any model file is loaded (T-056,
master prompt sections 15 and 24, rule: no unapproved model in the production set).

Layout (dev): `models/manifests/<name>.json`         source weights: repo, pinned revision, licence, approval,
                                                     SHA-256 of every downloaded file (tools/models/download_models.py)
              `models/manifests/<name>.exports.json` derived ONNX/npz/json files the runtime loads: SHA-256 and
                                                     size of each, the tool that made them and the source revision
                                                     (tools/models/register_exports.py)
              `models/onnx/<name>/...`               the exported files (git-ignored)

`verify_file(path)` raises ModelIntegrityError unless the file is listed in its model's export manifest with the
same size and SHA-256, AND the model's source manifest records an allowed licence and an owner approval. Hashing a
2 GB model takes seconds, so a successful verification is remembered per (path, size, mtime) in memory and in
`models/.verified.json`; any change of the file invalidates it. Development escape hatch: environment variable
ST_ROTO_MODEL_VERIFY=0 (reported by `status()`; never set in a release).

* **class `ModelIntegrityError`** (RuntimeError)
* **`default_models_root()`**
* **`sha256_file(path)`**
* **`enabled()`**
* **`roots()`**

  > Model storage locations in lookup order (REQ-15: user-selected, shared studio, plugin directory): [(label,
  > root)]. A location is used only when its environment variable names an existing folder; ST-ROTO never creates
  > one by itself. Each root has the same layout: manifests/, onnx/<name>/, weights/<name>/.

* **`find_model(name)`**

  > The root whose copy of `name` is used: the first location (user, studio, plugin) that has both its manifests
  > and its exported files; the plugin root if none does (callers then report it as missing).

* **`model_dir(name)`**

  > Folder of a model's exported files in the location that is used (find_model). 'name@<version id>' names an
  > archived version (T-114) of the location that is used: versions run side by side without being activated.

* **`locate(path, models_root=None)`**

  > -> (models_root, model name, path relative to models/onnx/<name>) for a file under models/onnx/<name>/.

* **`load_manifests(name, models_root=None)`**
* **`check_source(src)`**
* **`verify_file(path, models_root=None)`**

  > Raise ModelIntegrityError unless `path` is a registered, approved, unmodified model file.
  > Returns {"model", "file", "sha256", "cached"}.

* **`models(models_root=None)`**

  > Every registered model: name, licence, revision, approval, whether weights / exports are present and
  > whether it may be used (production licence + approval). Hashes are not computed here. Without `models_root`:
  > every storage location (roots()), each row with "location", "root" and "active" (this copy is the one used).

* **`verify_model(name, root)`**

  > Full check of every exported file of `name` in `root`, ignoring remembered results (manager 'Verify'):
  > [{"file", "ok", "detail"}]. Licence / approval / revision are checked once, as the first row.

* **`remove_model(name, root)`**

  > Delete a model's exported files and source weights from `root` (manager 'Remove'); the manifests stay as the
  > record of what was installed. Returns the deleted folders.

* **`import_model(src_root, name, dst_root, note='', user='')`**

  > Manual import (REQ-15): copy model `name` (its manifests and onnx/<name>/) from another models root into
  > `dst_root` - ONLY if its source manifest records a production licence, an owner approval and a pinned revision,
  > and every exported file matches its recorded size and SHA-256. Nothing is copied otherwise.
  > T-114: a version already installed there is ARCHIVED (versions/<name>/<id>/), never deleted, so the import can be
  > rolled back; importing the version that is already active changes nothing.

* **`version_id(exports_manifest)`**
* **`version_root(root, name, vid)`**
* **`active_version(name, root)`**

  > The active version's description, or None if `root` has no installed copy of `name`.

* **`list_versions(name, root)`**

  > Active version first, then archived ones (newest archive first).

* **`history(name, root)`**
* **`verify_version(name, root, vid)`**

  > verify_model on an archived version (full SHA-256 of every file).

* **`activate_version(name, root, vid, note='', user='')`**

  > Make archived version `vid` the active one: verified first (licence, approval, revision, every file's
  > SHA-256 - nothing changes if anything fails), then the active version is archived and `vid` moved into place.
  > Callers must release loaded sessions of `name` first (Windows cannot move files a session still holds).

* **`rollback(name, root, user='')`**

  > Re-activate the version that was active before the last import / activation (history.json).

* **`remove_version(name, root, vid)`**

  > Delete an ARCHIVED version (the active one cannot be removed here).

* **`status()`**
* **`build_exports_manifest(name, models_root=None, tool='')`**

  > Hash every file under models/onnx/<name>/ into models/manifests/<name>.exports.json (run after exporting).


### st_roto_ai.resize

Antialiased bilinear resize matching torch.nn.functional.interpolate(mode="bilinear", align_corners=False,
antialias=True), in numpy (no torch at runtime, ADR-0002). Port of PyTorch's separable "aa" weight computation
(aten/src/ATen/native/UpSample.h, _compute_indices_min_size_weights_aa) with a triangle filter.

* **`resize_aa(img, out_h, out_w, dtype=np.float64)`**

  > Resize (H, W) or (H, W, C) with antialiased bilinear filtering; returns float32.
  > dtype=float64 for exact mask preparation, float32 for fast image preprocessing (BLAS).

* **`mask_to_model_input(mask, size=1024)`**

  > Binary mask (H, W) -> [1,1,size,size] float {0,1}, exactly as Sam2VideoProcessor prepares mask prompts.


### st_roto_ai.runtime

ONNX Runtime session creation with honest device reporting (ADR-0001, master prompt section 4).

ONNX Runtime silently falls back to CPU when a GPU provider cannot load (measured: onnxruntime-gpu built for
CUDA 13 inside Nuke 17.1's CUDA 12 process). `open_session` compares requested vs active providers and returns
a `DeviceReport` the UI must show to the artist.

* **class `DeviceReport`**
* **`dml_options()`**

  > DirectML EP options. ST_ROTO_DML_DEVICE picks the adapter (0 = ONNX Runtime's first, the high-performance GPU
  > on the hybrid laptop measured in T-116; 1, 2... = the others, e.g. an integrated Intel GPU).

* **`shrink_run_options()`**

  > RunOptions that return unused CUDA pool memory to the driver at the end of a run (ORT run config
  > 'memory.enable_memory_arena_shrinkage'). Use for the large, variable-shape calls (memory attention).

* **`set_cuda_memory_limit(megabytes)`**

  > Per-session cap on ORT's CUDA memory pool (None = no cap). Used by hardware-aware routing (ADR-0007).

* **`available_devices()`**

  > Devices this ONNX Runtime build was compiled for (not a guarantee that they load).

* **`open_session(path, device='auto', log_severity=3, cache=True)`**

  > Like `create_session`, but reuses a process-wide session for the same (file, device).
  >
  > Why: creating ONNX Runtime sessions holds Python's GIL; in Nuke's GUI this froze the UI for 0.9-1.3 s on every
  > Track press (research/probes/2026-11-16_gui_stalls). Cached sessions make that a once-per-Nuke-session cost.
  > ORT InferenceSession.run is safe to call from several threads.
  > Every file is verified against the model registry first (st_roto_ai.registry, T-056).

* **`loaded_model_dirs()`**

  > Folders of model files whose sessions are cached (already holding GPU / CPU memory).

* **`is_out_of_memory(err)`**

  > True if an exception from ONNX Runtime means the GPU ran out of memory (T-092).

* **`clear_cache()`**

  > Release cached sessions (frees GPU memory; ADR-0009 GPU arbiter will call this under memory pressure).

* **`create_session(path, device='auto', log_severity=3)`**

  > Create an InferenceSession on `device` ("auto" = cuda, then directml, then cpu) and report what loaded.


### st_roto_ai.sam2

SAM 2.1 adapters (image click-to-mask and video tracking) on ONNX Runtime + numpy (ADR-0002).

Graphs are produced by tools/models/export_sam2_onnx.py (image) and tools/models/export_sam2_video_onnx.py (video).
The video tracker re-implements the inference-time memory logic of transformers' Sam2VideoModel (v5.23); it was
verified frame by frame against PyTorch (mask IoU >= 0.99997, research/probes/2026-11-15_video). Supported: point
and mask prompts on any number of frames, forward and reverse tracking, several objects per pass (Sam2MultiVideo).

Input images: float32 RGB in [0,1], in the model's expected encoding (sRGB-encoded for SAM). Converting from the
host's working colour space is the host adapter's job (ADR-0010) and must be recorded in provenance.

* **`preprocess(rgb)`**

  > HxWx3 float RGB [0,1] -> 1x3x1024x1024 normalised.
  >
  > Antialiased bilinear resize (torch-equivalent, st_roto_ai.resize) like the official Sam2VideoProcessor. Plain
  > cv2 bilinear differed by up to 0.11 (normalised) and flipped a borderline object score (0.025) in the reverse
  > scenario (research/probes/2026-11-16_corrections). Remaining difference (<= 0.017) is the processor's 8-bit
  > fixed-point rounding; float input is kept unquantised on purpose (artists' footage is often float).

* **`to_model_points(points_xy, width, height)`**

  > Canonical image coordinates [(x,y), ...] -> [1,1,N,2] in the 1024x1024 model space.

* **`upscale_logits(low_res, width, height)`**

  > 256x256 mask logits -> HxW logits (bilinear). Threshold at 0 for a mask; trace at 0 for sub-pixel contours.

* **class `Sam2Image`**

  > Click/box-to-mask on single frames. `encode` once per frame, then `predict` per prompt (~7 ms on GPU).

  * `__init__(model_dir, device='auto')`
  * `encode(rgb)`
  * `predict(enc, points_xy, labels)` - points in canonical image coordinates; labels 1 = include, 0 = exclude. Returns best mask logits.
* **`preload_video(model_dir, device='auto')`**

  > Create (and cache) every session the video tracker needs. Session creation holds Python's GIL for ~1-3 s
  > (measured), so hosts call this at a moment the artist chooses; later tracking reuses the cached sessions.

* **`bf16_round(x)`**

  > float32 -> bfloat16 -> float32, round-to-nearest-even (matches torch .to(torch.bfloat16)).

* **`sine_pe_1d(pos, dim, temperature=10000.0)`**
* **class `Sam2Video`**

  > Single-object forward tracker. Usage: enc = encode(rgb); add_points(i0, enc, pts, labels); track(i, enc)...
  >
  > `frame` arguments are 0-based POSITIONS in the processed sequence (as upstream), not shot frame numbers:
  > shots may start at any number, including negatives (master prompt section 11). Callers map frame <-> position.

  * `__init__(model_dir, device='auto', num_total_frames=None, memattn_file=None, max_frames_in_ram=24, state_dir=None)`
  * `close()`
  * `encode(rgb)`
  * `add_points(frame, enc, points_xy, labels)`
  * `add_mask(frame, enc, mask)` - Mask prompt (e.g. an artist correction) on a frame: becomes a conditioning frame, exactly as upstream
  * `track(frame, enc, reverse=False)` - Track a non-conditioning frame. reverse=True mirrors upstream `track_in_reverse_time`.
  * `save_state(directory)` - Write the complete tracking state (conditioning frames, every tracked frame's memory) into `directory`
  * `load_state(directory, index)`
* **class `Sam2MultiVideo`**

  > Several objects in ONE pass (T-067): every frame is encoded once and shared; each object keeps its own memory
  > bank, object pointers and conditioning frames in its own `Sam2Video` state.
  >
  > This is exactly upstream's multi-object behaviour: `Sam2VideoModel.forward` (transformers 5.23) loops over objects
  > and runs `_run_single_frame_inference(batch_size=1)` per object ("per-object inputs can differ"); only the image
  > features are shared and memory encoding is batched, which does not change per-object results. Hence each object's
  > result here is identical to tracking it alone (tests/unit/test_ai_sam2.py), while the image encoder - the most
  > expensive graph - runs once per frame instead of once per object and frame.
  >
  > Objects may use different position mappings and sequence lengths (`num_total_frames`), so a caller can reproduce
  > a single-object run per object exactly. Sessions are process-wide cached, so adding an object is cheap.

  * `__init__(model_dir, device='auto', memattn_file=None)`
  * `add_object(key, num_total_frames=None, max_frames_in_ram=24)`
  * `report()`
  * `encode(rgb)` - Encode one frame once for every object.
  * `close()`

### st_roto_ai.spill

Bounded-RAM store for per-frame tracker state (T-065, R-42).

Behaves like a dict of {frame: {name: ndarray}}. At most `max_in_ram` entries stay in memory (least recently used
are written to `directory` as .npz and reloaded on demand), so tracker results are IDENTICAL to keeping everything
in RAM (upstream behaviour) while memory stays bounded for long shots.

* **class `SpillDict`**
  * `__init__(max_in_ram=24, directory=None)`
  * `get(key, default=None)`
  * `in_ram()`
  * `close()`
  * `export_to(directory)` - Write every entry to `directory` as f<key>.npz, skipping files already there (entries never change
  * `import_from(directory, keys)` - Adopt entries exported by `export_to` (copied into this store's own folder, loaded on demand).

### st_roto_ai.vitmatte

ViTMatte-S (hustvl/vitmatte-small-composition-1k) on ONNX Runtime: trimap-guided alpha matting (D-032, OPTIONAL).

Licence: weights Apache-2.0; TRAINED ON Composition-1k (Adobe Deep Image Matting data, terms on request from
Adobe, reported non-commercial) - the training-data caveat is shown to the user wherever this model is offered
(docs/RESEARCH_2026-11-16_MATTING.md, R-11). Off by default; download is a separate, explicit step.

Preprocessing reproduces VitMatteImageProcessor exactly (verified by tools/models/export_vitmatte_onnx.py):
RGB in [0,1] -> (x - 0.5) / 0.5, trimap in [0,1] (0 background, 0.5 unknown, 1 foreground), 4 channels,
zero-padded right/bottom to multiples of 32.

* **`model_path(models_root)`**
* **`preprocess(rgb01, trimap01, divisor=32)`**

  > rgb01 (H, W, 3) float in [0,1] (display-encoded, like the photos it was trained on), trimap01 (H, W).

* **`trimap_from_mask(mask, inner=6, outer=20)`**

  > Hard shape mask -> trimap: foreground = mask eroded by `inner` px, background = outside the mask dilated
  > by `outer` px (hair and blur extend outward), unknown (0.5) between. Square windows via box sums.

* **class `ViTMatte`** (object)
  * `__init__(models_root, device='auto')`
  * `alpha(rgb01, trimap01)` - -> (H, W) float32 alpha in [0,1]; known fg/bg of the trimap are kept exactly.

## `st_roto_nuke` - Nuke adapter

### st_roto_nuke.alembic

Alembic export of a shot's shapes (T-113, REQ-180 'Alembic where suitable').

Written through the USD library bundled with Nuke (pxr 0.25.8 in Nuke 17.1, measured: its Alembic file-format plugin
usdAbc writes genuine Ogawa .abc files). No extra dependency; available wherever Nuke ships USD (Nuke 14+; older
Nuke: the export reports that it is unavailable).

Layout (st_roto.geomexport has the coordinates: pixel units, y up, origin bottom-left, z = 0):
    /st_roto/<object>/<shape>_curve   BasisCurves, cubic bezier, periodic (the exact spline, 3 points per anchor)
    /st_roto/<object>/<shape>_mesh    Mesh, one polygon of the outline (for readers without curves, e.g. Nuke)
One time sample per keyed frame (time code = frame number, the script's fps); frames where a part shape is
collapsed (piece absent, T-049) are invisible. Alembic stores every prim as an Xform with a shape child
(usdAbc maps /a/b_curve to /a/b_curve/b_curveShape when read back - measured).

* **`available()`**

  > '' if Alembic can be written here, else the reason.

* **`write_shot(store, shot_id, path, fps=24.0, per_segment=16)`**

  > Write every object / shape of the shot. Returns {"path", "prims": {prim path: (object, shape)}, "frames"}.

* **`read_back(path)`**

  > {prim path: {frame: points [(x, y, z)]}} of every curve / mesh in an .abc (for verification).


### st_roto_nuke.assist

Traditional-roto assists from render passes (T-121; follow-up of T-110). Not AI: both work with AI disabled.

* Shapes from Cryptomatte: the named Cryptomatte objects' coverage (> 0.5) on every frame of the shot becomes a new
  ST-ROTO object with native animated shapes (main + part shapes, st_roto.pieces - the tracker's own shape builder).
  Measured on the synthetic CG shot: IoU 0.9975 (auto point count) / 0.9994 (24 points) vs truth.
* Propagate along vectors: the named object's key on the CURRENT frame is carried forward or backward along the
  plate's motion vectors (st_roto.channels.warp_points_robust: the object's dominant affine motion, robust to an
  occluder in front), frame by frame, until the shot ends or a frame with the artist's own key or a locked frame
  (that key is the next guide). AI / earlier propagated keys on the way are replaced.
Both write as ACTOR_IMPORT (provenance 'imported_native': data-derived, neither AI nor hand-drawn) with the source in
the shape / key generator, as ONE undoable batch.

* **`on_shapes_from_crypto(group, background=True, names=None)`**

  > Object 'object name' <- Cryptomatte coverage of `names` (default: the 'source' knob, comma separated) in the
  > node's Cryptomatte layer, every frame.

* **`nuke_call(fn, args, background)`**
* **`on_propagate(group, direction=None, background=True)`**

  > Carry the named object's key(s) on the CURRENT frame along the motion vectors ('forward' uses the forward
  > layer, 'backward' the backward layer; 'both' does both).


### st_roto_nuke.capabilities

Nuke side of the capability report (T-091, REQ-020/022): gathers the facts st_roto.capabilities.evaluate needs.
Never raises: every probe that fails is reported as a fact ("unknown"), because this report is what an artist sends
when something does not work. Imports no AI module unless the AI is enabled (it then loads st_roto_ai.runtime, which
switches ONNX Runtime telemetry off).

* **`edition()`**
* **`facts(group=None)`**
* **`report(group=None)`**

  > -> (facts, features, text).

* **`show_report(group=None)`**

  > Button / menu entry: the report in a dialog (GUI) or printed (headless); the summary goes to the node's
  > status line.


### st_roto_nuke.collab

Collaboration in the Nuke UI (T-094, REQ-170/171): leases, presence, roles and signing keys for the object panel.
No Qt here (the panel only calls these), so the logic is testable headless. The rules themselves live in the core
(st_roto.leases: D-024/D-035/D-036; st_roto.signing: D-037/D-038); this module only applies them as the artist.

Identity: the bus author of the open project (session.project: the OS user name). A signing key is never created
silently: `setup_key` creates it (D-038 key folder) and registers its public half in the project.

* **`me(path)`**
* **`heartbeat(path, frame=None, activity=None)`**
* **`lease_text(conn, object_id, me_)`**

  > '' (free), 'you', or 'alice' / 'alice (idle 23 min)'.

* **`take(path, object_id)`**
* **`release(path, object_id)`**
* **`override(path, object_id)`**

  > Supervisor override (D-035/D-036): allowed only when the holder has been idle/offline 15 min; the op stores
  > the evidence. Errors from the rules are raised with an artist-readable message.

* **`set_role(path, user, role_name)`**

  > The first role must be the author making themself admin; afterwards only admins assign roles.

* **`key_state(path)`**

  > 'registered' (key file present and registered here), 'not registered' (file present, not registered in this
  > project), 'missing file' (registered here but no key file on this machine), or 'none'.

* **`setup_key(path)`**

  > Create the author's signing key if needed (D-038 folder), sign this project's operations with it from now on
  > and register its public key here (a self-signed op). Returns (key_state, created).

* **`status_line(path)`**

  > 'you: alice (admin) · key registered · online: bob · idle: carol' for the panel.


### st_roto_nuke.colour

Model-input colour transform for Nuke (ADR-0010, T-045).

The transforms themselves live in `st_roto.colour` (derived matrices + optional OpenColorIO). This module picks
one for an ST_Roto node: an explicit choice on the node, or "auto", which follows the script's colour management:
  * root colorManagement = "Nuke" (nuke-default)  -> scene-linear Rec.709/sRGB -> sRGB encoded (the v0 transform);
  * root colorManagement = "OCIO"                 -> OpenColorIO processor from the script's working space
                                                     (root workingSpaceLUT) to sRGB-encoded Rec.709, using the
                                                     config file in root OCIOConfigPath.
The transform id goes into every AI result's provenance.

* **`to_model_input(rgb, transform=_c.DEFAULT)`**
* **`transform_id(transform)`**
* **`resolve(choice, root=None)`**

  > Node choice -> a transform usable by to_model_input (built-in id or OcioTransform). Main thread only.


### st_roto_nuke.convention

Nuke Roto conventions, measured on Nuke 17.1v3 (research/probes/2026-11-15_bezier, 2026-11-15_video).

ST-ROTO canonical space (st_roto.model): x right, y DOWN, origin = top-left corner of the image.
Nuke Roto space: x right, y UP, origin = bottom-left corner of the format.
Nuke ShapeControlPoint tangents are RELATIVE to the point and equal to 2 x the cubic Bezier handle offset;
`leftTangent` points to the previous control point, `rightTangent` to the next one.
These facts are re-verified per Nuke version by tests/nuke (risk R-32).

* **`point_to_nuke(x, y, height)`**

  > Canonical (y down) -> Nuke (y up). Both spaces use the image corner as origin, so no 0.5 offset here.

* **`tangents_to_nuke(px, py, hin_x, hin_y, hout_x, hout_y)`**

  > Absolute canonical handles -> (leftTangent, rightTangent) relative Nuke vectors (y flipped, scaled).

* **`key_to_nuke(points, height)`**

  > One stored key (list of [x,y,hin_x,hin_y,hout_x,hout_y]) -> list of (centre, left, right) in Nuke terms.

* **`nuke_to_key(centre, left, right, height)`**

  > Inverse of key_to_nuke for one point (used by the native Roto importer).


### st_roto_nuke.family

The ST-ROTO node family beyond the main ST_Roto node (T-112, REQ-040, master prompt section 6).

Research and naming: docs/RESEARCH_2026-11-18_NODE_FAMILY.md. Measured budget rules (Nuke 17.1 Non-commercial,
research/probes/2026-11-18_node_family): every Node object Python obtains costs 1 of 10 per session (also repeated
look-ups of the same node; deleting the reference frees nothing), but a pasted node graph costs 1 whatever its
size and `nuke.thisNode()` in button callbacks costs nothing. So each family node is a Group made by Python
(1 object) whose inner graph is PASTED (1 object) and driven by knob expressions - Python never looks inner nodes
up, except the pixel Write of ST_RotoMatte when it renders (1 object, cached for the session).

* ST_RotoMatte (Matte + Refine + Holdout modules): renders ST-ROTO's refined mattes (guided / ViTMatte / hard, edge
  offset / blur, core/edge) for chosen objects or roles of a shot and brings them into the node graph: output =
  the input with alpha = the combined matte, plus one layer per object (and core/edge); plate RGB and every other
  input channel unchanged. Before the first render it passes its input through.
* ST_RotoOutput (Output module): shape export (JSON + SVG), delivery package, project package and backup for a
  shot; passes its input through.
Both name their shot explicitly (project file + shot = the ST_Roto node's source name), so they work anywhere in the
script and validate it.

* **`create_matte(source=None, project='', shot='')`**

  > ST_RotoMatte node (Group + pasted inner graph: 2 Node objects).

* **`create_output(source=None, project='', shot='')`**

  > ST_RotoOutput node (Group + pasted pass-through: 2 Node objects).

* **`on_check(group)`**

  > Validate project / shot / objects; the status lists what the project offers. Returns a dict or None.

* **`on_cancel(group)`**
* **`on_matte_render(group, background=True)`**

  > Render the chosen objects' mattes for the whole shot (st_roto_nuke.mattes.render_mattes) and show them in this
  > node's output (inner Read via the 'mattes' pattern knob). Several views: one sequence per view (%V).

* **`on_output(group, what)`**

  > ST_RotoOutput actions, delegated to the main node's implementations (they accept family nodes).

* **`create_from_selection(kind)`**

  > Menu: a Matte / Output node below the selected node. From an ST_Roto node: its project and shot.


### st_roto_nuke.mattes

Matte pass (T-069/T-070): every object of a shot -> (refined) alpha -> one multi-layer EXR per frame.

No Nuke calls: plate frames come from an injected `get_rgb(frame)` (scene-linear, like tracking). Each object's
hard mask is the exact rasterisation of its stored splines (st_roto.matte.object_mask); with `soft=True` the edge
band is refined with the guided filter against the plate (st_roto.matte.refine_alpha, model-free). The plate is
read only when soft edges are requested.

* **`default_output_dir(project_path, shot_name)`**
* **`fit_size(w, h, box=None)`**

  > (width, height) of the shot scaled down to fit in `box` with its proportions (never up); the shot size when
  > box is None or the shot already fits.

* **`render_mattes(get_rgb, store, shot_id, frames, out_dir, soft=True, band=3, radius=8, eps=0.0001, objects=None, compression='zip', job=None, colour_transform=colour.TRANSFORM_ID, method=None, models_root=None, device='auto', out_size=None, rgb_mode=None, offset_px=0, blur_px=0.0, core_edge_px=0, spill=None)`**

  > Write `<out_dir>/<shot>_mattes.####.exr` for `frames`. objects: object ids (default: every object of the
  > shot). out_size: (width, height) box the EXRs must fit in (OQ-28: e.g. 1920x1080); mattes are computed at the
  > shot's full resolution and area-averaged down into the largest box with the shot's proportions; None = full
  > resolution. Returns {"pattern", "files", "layers": {object name: layer}, "frames_interpolated": {name: [frames]},
  > "frames_held": {...}, "plate_missing": [frames], "seconds"}. A frame whose plate cannot be read (T-086) gets a
  > hard matte (the shapes need no plate) and is listed in "plate_missing".
  > T-099 (REQ-100/101), applied to the mattes only (shapes never change), in this order: per object `offset_px`
  > (grow > 0 / shrink < 0) and `blur_px` (edge feather, Gaussian sigma), then the combined matte (roles), then
  > `core_edge_px` > 0 adds layers core_matte (combined eroded by that width) and edge_matte (the band). rgb_mode
  > 'premultiplied' / 'straight' writes the plate's scene-linear RGB (x combined alpha if premultiplied) into R, G, B;
  > the convention is in the header ('st_roto' alpha_convention) - never implied.


### st_roto_nuke.model_panel

ST-ROTO Models panel (dockable; T-101, REQ-052 / REQ-130). Shows every model in every storage location with its
licence, approval, revision, source and GPU fit; Verify / Self-test / Remove / Import. Logic: models_ui.py.
Registered by nuke_plugin/menu.py as "ST-ROTO Models". Downloads are not done here (owner-approved tool only).

* **class `ModelPanel`** (QtWidgets.QWidget)
  * `__init__(parent=None)`
  * `refresh()`
  * `verify()`
  * `self_test()`
  * `remove(confirm=None)`
  * `import_model(src_root=None, name=None)`
  * `refresh_versions()`
  * `activate()`
  * `rollback()`
  * `compare()`
  * `remove_version(confirm=None)`

### st_roto_nuke.models_ui

Model manager logic (T-101, REQ-052 / REQ-130, master prompt section 15). No Qt here: the "ST-ROTO Models" panel
(model_panel.py) only calls these, so everything is testable headless.

- rows(): every model in every storage location (user, studio, plugin; st_roto_ai.registry.roots) with licence,
  approval, pinned revision, source repository, installed / used copy, and its GPU memory need vs this GPU.
- verify(): full SHA-256 check of every file (ignores remembered results).
- self_test(): tracks a generated moving disc with the model (3 frames) and reports accuracy and time per frame -
  the model test and benchmark on this machine, no footage needed.
- remove() / import_from(): delete a copy (manifests stay as the record) / copy an approved model from another
  location (refused unless licence, approval, revision and every checksum are right).
Downloading new models stays a separate, owner-approved step (tools/models/download_models.py, CLAUDE.md rule 4).

* **`rows()`**
* **`verify(name, root)`**
* **`self_test(name, device='auto')`**

  > Track a generated orange disc moving over 3 frames from one click; IoU of every key vs the true disc and the
  > time per frame. Only for SAM 2.1 video models (the tracker); ViTMatte gets a matting run on a soft disc.

* **`remove(name, root)`**
* **`import_from(src_root, name, dst_label='user')`**

  > Copy an approved model into a configured location ('user' or 'studio'; must be set up, see roots()).

* **`versions(name, root)`**

  > Active version first, then archived ones, each with its id, revision, export tool, size, note, date.

* **`history(name, root)`**
* **`activate(name, root, vid, note='')`**

  > Verify archived version `vid` fully, then make it the one ST-ROTO uses (the current one is archived).

* **`rollback(name, root)`**
* **`remove_version(name, root, vid)`**
* **`compare(name, root, device='auto')`**

  > Self-test EVERY installed version of `name` side by side (archived ones run as 'name@id', nothing is
  > activated): [{"id", "active", "result"}].


### st_roto_nuke.node

The ST_Roto node (single-node core under the Non-commercial 10-node cap, D-012) — v0.

Structure: Group "ST_Roto" with  Input -> Roto(STROTO_shapes, alpha) -> Output, plus a disabled Write
(STROTO_pixels) that pulls pixels into numpy. 5 nodes per shot including the group.

Artist workflow (knob tab ST-ROTO):
  1. set "object name", drag the "point" handle in the viewer onto the object, press "+ Include" (or "- Exclude")
     - repeat as needed; change "object name" and add points to prompt further objects (T-067);
     or drag the "box" rectangle around the object and press "Set box" (most reliable for object parts, T-079),
     then refine with include/exclude points;
  2. "Preview" shows the AI shape of the current object on its prompt frame (temporary, not saved);
  3. "Load model" (optional, once per Nuke session) takes the one-time GPU set-up pause now;
  4. "Track" tracks every prompted object forward from its prompt frame, in one pass on a worker thread (each frame
     is rendered and encoded once); the result is stored in the project (AI provenance, ONE undo step) and
     synchronised into the Roto node without touching shapes edited there.
Python viewer clicks are not used: Non-commercial cannot load C++ overlays and Nuke offers no supported Python
mapping from viewer clicks to image coordinates; the XY knob handle is Nuke's native in-viewer point.

* **`default_matte_size()`**

  > D-041 (owner, 2026-11-17): Nuke Non-commercial -> 'fit 1920x1080' (its own output limit); other editions ->
  > 'full resolution'.

* **class `NodeBudgetError`** (RuntimeError)

  > Nuke Non-commercial / Indie returned None because the 10-Python-Node-object limit was reached (ADR-0003).

* **`create(source=None, project_path='')`**
* **`ai_disabled_reason(group)`**

  > Why AI is off for this node (session-wide environment variable or the node's checkbox), or None.

* **`ai_runtime_problem()`**

  > None if the AI runtime can load, else an artist-readable reason. Imports st_roto_ai.runtime (which switches
  > ONNX Runtime telemetry off at import), never onnxruntime directly.

* **`apply_ai_visibility(group)`**
* **`create_from_selection()`**

  > Menu entry: create an ST_Roto node below the selected node; project file defaults to <script>.stroto.

* **`current_settings(group)`**

  > This node's preset settings (st_roto.presets.SETTINGS) with their current values.

* **`on_refresh_presets(group)`**
* **`on_apply_preset(group, name=None)`**

  > Apply a preset to this node. Returns {"applied": [keys], "skipped": [(key, why)]} or None on error.

* **`on_save_preset(group, name=None, description='')`**
* **`on_delete_preset(group, name=None)`**
* **`on_review_colours_toggled(group)`**

  > knobChanged: colours on / off on the existing shapes right away (no other change).

* **`on_show_shapes(group)`**

  > T-111: open the inner Roto's controls so the shapes and their review colours are drawn in the viewer.

* **`plan_model(choice, device)`**

  > Memory-aware (model, device, note) for an AI action (T-092, REQ-021): measured GPU memory needs vs free
  > memory now (local nvidia-smi); models already loaded by this Nuke need nothing new.

* **`on_detect_cuts(group, background=True)`**

  > 'Detect cuts' (T-123): thumbnails of every source frame -> scene cuts into the knob (no AI, no undo needed:
  > it only fills a knob the artist can edit).

* **`on_lock_range(group, lock=True)`**

  > Lock (or unlock) the named object's keys on frames 'from'..'to' (T-097, REQ-11-14): stored in the main shape's
  > generator ("locked_frames", one undoable op); locked keys guide every re-track and the AI never changes them.

* **`on_set_role(group, role=None)`**

  > Set the role of the object named above (T-098): add / holdout / garbage, one undoable op; the Roto node and
  > the EXR combined matte follow it.

* **`on_delivery(group, zip_path=None)`**

  > Delivery package of this node's shot (T-108, REQ-180): st_roto.delivery with the outputs, settings and
  > dependencies gathered here.

* **`script_views()`**

  > The script's views in order (T-109); ['main'] when Nuke cannot say.

* **`prompt_view(group)`**

  > The view prompts are placed in and single-view work renders (T-109): the node's 'prompt view', else the
  > script's hero view, else its first view. None in a single-view script. Raises ValueError for an unknown view.

* **`camera_rig(group, views, frames, width, height)`**

  > T-120: {view: {frame: (K, R, C)}} from the node's 'cameras' knob (main thread), or None if it is empty.
  > 'v1=Cam1, v2=Cam2': one camera node per view; 'Cam': one node whose knobs are split per view. Raises ValueError
  > with what is wrong (unknown node, a view without camera, not a camera).

* **`stereo_on(group)`**

  > True when the node tracks every view (its checkbox, and the script has several views).

* **`on_add_point(group, label)`**
* **`on_prompt_from_mask(group)`**

  > T-100 (REQ-060): rough Roto shape / another node's alpha / a mask file on the current frame -> the named
  > object's prompt (box + interior clicks, st_roto.prompts.from_mask).

* **`on_list_channels(group)`**

  > T-110: the input's layers and Cryptomatte layers (names) in the node; returns {"layers", "cryptomatte"}.

* **`on_check_channels(group, background=True)`**

  > T-110 (REQ-113): render the chosen channels for the whole shot and check every object's shapes (channel
  > medians, motion vectors, Cryptomatte); store the reports (one undo step) -> CHECK review flags.

* **`on_set_box(group)`**

  > Store the viewer rectangle as the current object's box on the current frame (replaces its old box).

* **`on_clear_box(group)`**
* **`on_clear_points(group, every_object=False)`**

  > Clear the current object's points (or every object's).

* **`on_load_model(group)`**

  > Create the GPU sessions now, synchronously and visibly (the GIL-bound pause, R-40).

* **`on_cancel(group)`**
* **`on_preview(group, background=True)`**

  > Segment the current object on its prompt frame and show it as a temporary shape (not saved, not undoable).

* **`on_track(group, background=True, resume=False)`**

  > Track every prompted object forward from its prompt frame in one pass; store (AI provenance, one undo step)
  > and sync into the Roto node. The run is checkpointed (T-048): after Cancel, a failure or a crash,
  > `resume=True` ('Resume track') continues it from the checkpoint with identical results.

* **`on_check_views(group)`**

  > T-120 button: re-run the epipolar check of every stereo / multi-camera object (e.g. after editing shapes).

* **`on_reduce_chatter(group, every_object=False, radius=None)`**

  > T-115 (REQ-101 chatter reduction): smooth the AI keys of the named object (or every unlocked object) with
  > st_roto.chatter; artist keys, locked frames and collapsed part keys are kept and anchor the fit. One undoable
  > batch, written as AI (the command bus refuses locked content). Returns {object: (jitter before, after, keys)}.

* **`on_reprompt_here(group, background=True)`**

  > T-081: the box (+ optionally the point handle) on the CURRENT frame becomes a fix prompt of the current object,
  > which is then re-tracked in both directions (one undo step; the fix is stored with the shape).

* **`on_retrack(group, background=True, every_object=False, fix=None, flagged_only=False)`**

  > Re-track the object named in 'object name' (or every unlocked object of the shot, in one pass) using its
  > artist keys and prompts as guides (forward + reverse). All results are ONE undo step. fix: a new fix prompt for
  > the current object (on_reprompt_here). flagged_only: only objects with REVIEW lost flags (T-093). The model is
  > the node's 're-track model' (or 'model' when that says 'same as model').

* **`on_render_mattes(group, background=True)`**

  > Every object of the shot -> (soft) mattes -> multi-layer EXR sequence (T-069/T-070).

* **`is_family_node(group)`**

  > True for ST_RotoMatte / ST_RotoOutput (T-112): they name their shot in a knob and have no Roto of their own.

* **`on_export_shapes(group, out_dir=None)`**

  > Shot -> JSON (full fidelity) + one SVG per keyed frame. Returns {"json", "svg"} paths.

* **`on_export_alembic(group, path=None)`**

  > T-113: shot -> Alembic (.abc) next to the JSON export. Returns st_roto_nuke.alembic.write_shot's dict.

* **`on_import_shapes(group, path=None)`**

  > ST-ROTO JSON -> new objects in this shot (one undo step), then sync into the Roto node.

* **`on_backup(group)`**
* **`on_package(group, zip_path=None, include_sources=False, include_script=True)`**

  > Portable package of the project (T-071) including the saved Nuke script (T-075). Sources are not included
  > by default (size); unpacking relinks them.

* **`store_ro(path)`**

  > Separate store connection for worker threads, used for reading only (SQLite connections are thread-bound).

* **`resync(group, import_first=True)`**

  > Capture artist edits made in the Roto node (import_edits), then make the Roto node reflect the project
  > (sync_shot). Returns the sync report with the import report under "import". Family nodes (no Roto): None.

* **`on_import_edits(group)`**
* **`shot_id_for(group)`**
* **`on_resume_track(group, background=True)`**
* **`checkpoint_dir(project, shot_name)`**

  > Where an interrupted Track keeps its state (inside the project's cache folder, never packaged).

* **`on_copy_to_rotopaint(group)`**

  > Copy every shape of this shot (keys and feather) into a NEW RotoPaint node next to ST_Roto, fed by the same
  > plate (T-073): independent native shapes, editable and renderable without ST-ROTO.


### st_roto_nuke.packages

Unpack an ST-ROTO package inside Nuke and relink missing plates (T-075).

`unpack_and_relink(zip, dest, choose)` holds the logic; `choose(shot, missing_path)` returns a new plate path (or
None to skip) - the menu passes a file dialog, tests pass a function. Every relinked plate is checked against the
fingerprint recorded for its shot: the same footage moved elsewhere is accepted, different footage that merely
has the same names is refused. Packaged Nuke scripts get the same path changes.

* **`sequence_pattern_from_file(path)`**

  > 'D:/plates/sh010.0012.exr' -> 'D:/plates/sh010.####.exr' (last digit group before the extension).

* **`unpack_and_relink(zip_path, dest_dir, choose, relink=None)`**
* **`apply_relink_to_open_script(mapping=None, script_path=None)`**

  > Relink the script open in Nuke: every ST_Roto node's project file and the file of the Read feeding it.
  > mapping: {old prefix: new prefix}; default: the sidecar written by unpack next to `script_path` (needed for
  > Non-commercial scripts, which are encrypted). Only ST_Roto groups and their inputs are touched (10-node limit
  > in Non-commercial). Returns {"changed": [(node, knob, old, new)]}.

* **`summary(report)`**
* **`unpack_package_ui()`**

### st_roto_nuke.panel

ST-ROTO object panel (dockable). Lists the objects of the selected ST_Roto node's shot and edits them through the
command bus (artist actor): rename, lock/unlock, delete, undo, redo. After each edit the Roto node is re-synchronised;
shapes edited directly in the Roto node are never overwritten (reported instead).

Register as a dockable pane (done by nuke_plugin/menu.py):
    nukescripts.panels.registerWidgetAsPanel("st_roto_nuke.panel.ObjectPanel", "ST-ROTO Objects", "st_roto.objects")

* **class `TimelineWidget`** (QtWidgets.QWidget)

  > One row per object across the shot (T-102, REQ-120): artist keys (orange), AI keys (grey), locked frames
  > (blue band), review flags lost (red) / check (yellow) under the keys, current frame (white line). Click: jump
  > to that frame and select the object (on_pick(frame, row)).

  * `__init__(parent=None, on_pick=None)`
  * `set_data(rows, first, last, current=None)`
  * `x_of(frame)`
  * `frame_at(x)`
  * `paintEvent(event)`
  * `mousePressEvent(event)`
* **class `ObjectPanel`** (QtWidgets.QWidget)
  * `__init__(parent=None)`
  * `set_group(group)`
  * `use_selected()`
  * `refresh()`
  * `pick(frame, row)` - Timeline click: go to `frame` and select the object of `row`.
  * `rename(new_name=None)`
  * `toggle_lock()`
  * `set_object_role(role=None)`
  * `merge_into(target_name=None)` - Merge the selected object into another one (its shapes move; one undo step).
  * `delete()`
  * `undo()`
  * `take()`
  * `release()`
  * `override()`
  * `setup_key()`
  * `set_role(user=None, role_name=None)`
  * `redo()`

### st_roto_nuke.pixels

Nuke -> numpy pixel transfer (ADR-0003). v0 renders one frame at a time through a Write node to an uncompressed
float TIFF and reads it back (measured ~26-90 ms/frame at 720p-1080p). An in-memory path is task T-046.
Must run on Nuke's MAIN thread (nuke.execute); worker threads call it via nuke.executeInMainThreadWithResult.

Difficult sequences (T-086, master prompt section 11, measured in research/probes/2026-11-17_sequences):
* a frame Nuke cannot read (missing file, gap in a discontinuous sequence) raises `FrameUnavailable`; callers
  skip it and report it instead of failing the whole run;
* proxy mode: the Write node needs a proxy file name, otherwise Nuke refuses to execute it; the frame then comes
  at proxy resolution and is brought to the shot format by `fit_to_format`;
* an edition render limit (Non-commercial: 1920 x 1080) raises `ResolutionCapped`; the node then renders the
  frame reduced into that box and scales it back, so tracking still works on larger plates (T-089);
* a frame whose resolution differs from the shot (mixed-resolution sequences) is brought to the shot format the
  way Nuke's default Reformat node does (scale to the format width, centred), so shapes stay in shot coordinates.

* **class `ResolutionCapped`** (Exception)

  > The Nuke edition refuses to render this size (Non-commercial: 1920 x 1080, measured, T-089). `limit` is
  > (width, height) parsed from Nuke's message, or None if it could not be parsed.

  * `__init__(message)`
* **class `FrameUnavailable`** (Exception)

  > Nuke could not produce this frame (e.g. the file is missing). `frame` and Nuke's message are kept.

  * `__init__(frame, message)`
* **class `FrameExcluded`** (FrameUnavailable)

  > The artist excluded this frame from AI processing (T-097): skipped exactly like an unreadable frame (no key,
  > existing keys untouched, true time positions), reported as excluded.

  * `__init__(frame)`
* **`configure_write(write_node, path)`**
* **`render_frame(write_node, frame, path, view=None)`**

  > Render `frame` through `write_node` (temporarily enabled) and return HxWx3 float32 linear RGB at the size
  > Nuke produced (see `fit_to_format`). Raises FrameUnavailable when Nuke cannot read the frame.
  > view: the script view to render (T-109). In a script with several views Nuke refuses to execute a Write whose
  > file has no %V for all views ("cannot be executed for multiple views", measured), so callers always name one.

* **`render_channels(write_node, frame, path, view=None, channels='all')`**

  > Every channel (or one layer) of `frame` as {EXR channel name: HxW float array} (T-110): the pixel Write is
  > switched to a 32-bit float EXR for this render and restored afterwards (rgba comes back as R/G/B/A, other
  > layers keep Nuke's names, e.g. depth.Z, forward.u, CryptoObject00.R). Main thread. Raises FrameUnavailable.

* **`fit_to_format(img, width, height)`**

  > Bring an image of another size to width x height like Nuke's default Reformat (resize type 'width',
  > centred, black outside / cropped). Returns the image unchanged if it already has that size.

* **`temp_pixel_path(tag)`**

### st_roto_nuke.roto_export

Native Nuke Roto output (REQ-041) and safe synchronisation from the project store (REQ-042).

Shapes written by ST-ROTO are named "<name>_st<8 hex of shape id>". For every written shape the exact keys are
recorded in the project's `host_exports` table. `sync_shot` only replaces or removes a Roto shape whose current
keys still equal what ST-ROTO last wrote; a shape the artist edited in the Roto node is reported as a CONFLICT and
left untouched (importing Roto edits back into ST-ROTO is a later task).

* **`host_tag(shape_id)`**
* **`shape_label(name, shape_id)`**
* **`feather_of(row)`**

  > (feather_x, feather_y, feather_falloff) of a stored shape row (defaults for schemas before v5).

* **`read_feather(shape, frame=0)`**
* **`write_feather(shape, feather)`**
* **`feather_equal(a, b, tol=0.0001)`**
* **`read_point_feather(shape)`**

  > Per-point feather keys of a Roto shape {frame: [[fx, fy, lx, ly, rx, ry], ...]} in canonical units: offset
  > y flipped (Nuke y up), tangents halved (Nuke tangent = 2 x handle offset, as for the shape itself). Frames =
  > every key time of any point's featherCenter / feather tangents; {} when the shape has no per-point feather.

* **`point_feather_equal(a, b, tol=0.0001)`**
* **`build_shape(curves_knob, label, keys, height, feather=None, point_feather=None)`**

  > Create (not yet attached) a fully keyed nuke.rotopaint.Shape from {frame: points}, with the shape-level
  > feather (fx, fy, ff) if given. Keys are added BEFORE points are appended: later keys are silently lost in
  > Nuke 17.1 (R-33).

* **`read_keys(shape, height)`**

  > Read a Roto shape's keyed points back into canonical {frame: points}.

* **`keys_equal(a, b, tol=TOLERANCE)`**
* **`export_shape(store, shape_id, curves_knob, height, layer=None)`**

  > Write one stored shape track into a Roto node and record what was written.

* **`apply_roles(store, shot_id, curves_knob)`**

  > Blend attributes and order of the shot's shapes from their objects' roles. Returns True if anything changed
  > (then curves_knob.changed() has been called: Nuke does not re-render Python attribute edits otherwise).

* **`sync_shot(store, shot_id, curves_knob, height)`**

  > Make the Roto node reflect the project, never overwriting artist edits made in the Roto node.

* **`shape_view(item, script_views=None)`**

  > The one view a Roto shape is limited to, or None (several / every view).

* **`apply_views(store, shot_id, curves_knob, script_views=None)`**

  > Limit each ST-ROTO shape to its object's view (objects.view); objects without a view render in every view.
  > Returns (changed, [object views this script does not have: those shapes are shown in every view]).

* **`import_edits(store, bus, shot_id, curves_knob, height, static_frame=0)`**

  > Capture artist work done in the Roto node into the project (actor = artist, one undoable batch per shape).
  >
  > * Tagged ST-ROTO shapes whose keys differ from what ST-ROTO last wrote: changed/added keys -> set_key,
  >   removed keys -> delete_key (edited AI keys become artist_modified_ai through the command rules).
  > * Untagged shapes the artist drew in this Roto node: imported as new artist_created objects; the Roto shape is
  >   then renamed with its tag so later syncs recognise it.
  > Not imported (reported in "skipped"): point count changed in Roto (topology changes unsupported in v0),
  > locked objects/shapes, shapes whose object was deleted in the project.

* **`export_preview(curves_knob, keys, height, label=PREVIEW_LABEL)`**

  > Show a temporary, unrecorded shape (prompt preview); replaces any previous preview.

* **`apply_review_colours(store, shot_id, curves_knob, enabled=True, first=None, last=None)`**

  > Key every ST-ROTO shape's overlay colour per frame from its object's review flags (magenta = lost, yellow =
  > check, Nuke's default elsewhere); enabled=False removes those keys. Returns {"shapes", "flagged_frames"}.


### st_roto_nuke.session

One open project (store + command bus) per project file for the whole Nuke session, used on the MAIN thread.
Keeping the bus alive keeps undo/redo history across panel actions and Track runs.

Opening a project also (T-071): marks it as open (`<project>.session.json`), detects an unclean previous session
(crash / power loss), checks integrity, restores the newest valid backup if the file is damaged (the damaged file
is kept), and starts automatic backups (every ST_ROTO_BACKUP_SECONDS, default 300 s, only after changes; a final
backup when Nuke exits). What happened is in `open_report(path)` and shown in the node status by the caller.

* **`project(path)`**
* **`open_report(path)`**
* **`report_text(path)`**

  > Artist-readable summary of anything unusual found when the project was opened ('' if nothing).

* **`backup_now(path, reason='manual')`**
* **`close(path)`**
* **`close_all()`**

### st_roto_nuke.track

Prompts -> SAM 2.1 video tracking -> stored, keyed ST-ROTO shapes (T-055, several objects per pass: T-067).

The tracking functions contain no Nuke calls: frames come from an injected `get_rgb(frame)` (headless tests pass a
direct renderer, the GUI passes a main-thread-marshalled one). The apply functions write through the command bus as
actor "ai", so the protection rules (REQ-042) apply; a whole tracking pass is ONE undoable batch.

* **`models_root()`**

  > The PLUGIN location's onnx folder (dev layout: <repo>/models/onnx). Use model_dir(name) to load a model.

* **`model_dir(name)`**

  > Folder of model `name` in the storage location that is used (user, studio, plugin; T-101).

* **`track_objects(get_rgb, frames, objects, model='sam2.1-hiera-tiny', device='auto', job=None, anchors=ANCHORS, colour_transform=colour.TRANSFORM_ID, parts=True, checkpoint_dir=None, checkpoint_every=10, resume=False)`**

  > Track several objects forward in ONE pass (T-067): each frame is rendered and encoded once, every object
  > keeps its own tracker memory (st_roto_ai.sam2.Sam2MultiVideo).
  >
  > frames: ordered list of shot frame numbers. objects: [{"name", "frame", "points": [(x, y), ...], "labels"}];
  > each object is tracked from its own prompt frame to the end of `frames`, with exactly the positions and sequence
  > length a single-object run over that range uses, so per-object results equal tracking each object alone.
  > anchors: point count of the main shape, or "auto" (chosen on the prompt frame, st_roto.pieces.choose_count).
  > parts: pieces the object splits into become part shapes (T-049).
  > checkpoint_dir: if given, the complete state is saved there every `checkpoint_every` frames and when the job is
  > cancelled (T-048); `resume=True` continues from it (frames/objects/model/settings must match: use
  > `read_checkpoint`). A finished run removes its checkpoint. Resumed results equal an uninterrupted run.
  > Returns {"objects": [per-object result, input order], "device", "device_fallback", "device_reason"}; a
  > per-object result has "name", "keys" (main shape), "parts" ([{frame: points}], collapsed where absent),
  > "anchors", "absent_frames", "holes", "reports", "generator".

* **`track_object(get_rgb, frames, click_frame, click_xy, model='sam2.1-hiera-tiny', device='auto', job=None, anchors=ANCHORS, labels=None, colour_transform=colour.TRANSFORM_ID)`**

  > Track one object from prompt points on one frame. Returns dict with per-frame points and run metadata.
  >
  > frames: ordered list of shot frame numbers (any integers); click_frame must be the first of them (forward only).
  > click_xy: one (x, y) or a list of (x, y) in canonical image coordinates (y down); labels: 1 include / 0 exclude
  > (default: all include).

* **`retrack_plan(store, shape_id, frames, fix=None, anchors=None)`**

  > What a re-track of one object (given by its MAIN shape) starts from. Raises ValueError (artist-readable) if
  > there is nothing. The guide mask on an artist frame is the main shape's artist key united with the object's
  > part shapes at that frame (non-collapsed).
  > Fix prompts (T-081, "Re-prompt here"): {"frame", "points", "labels"} clicks/box on a frame the AI got wrong;
  > kept in the shape generator ("fixes", one per frame, a new one replaces the old) and used as conditioning frames
  > by every later re-track. Priority on one frame: artist key > fix prompt > original prompt.
  > Guide frames (T-097): keys on frames the artist LOCKED (shape generator "locked_frames") and `anchors`
  > ({frame: points}, e.g. the keys just outside a range-limited re-track) condition the tracker exactly like artist
  > keys and are never in the result, so the AI cannot change them; they are listed apart ("guide_frames") so
  > provenance and reports still distinguish them from artist keys.

* **`retrack_objects(get_rgb, store, shape_ids, frames, width, height, model='sam2.1-hiera-tiny', device='auto', job=None, colour_transform=colour.TRANSFORM_ID, parts=True, fixes=None, anchors=None)`**

  > Re-track several objects (given by their MAIN shape ids) in ONE pass (T-067). Each uses every ARTIST key of
  > its main shape (united with its parts on that frame) as a mask prompt, plus its original click prompts, and is
  > tracked forward from its first conditioning frame and in reverse to the first frame of `frames` (master prompt
  > section 11). Each frame is rendered/encoded once per sweep for all objects; per-object results equal
  > re-tracking each object alone. fixes: {main shape id: new fix prompt} (see retrack_plan). anchors: {main shape
  > id: {frame: points}} guide keys that are not changed (range-limited re-track, T-097).
  >
  > Returns {"shapes": {main shape id: {"keys": {frame: points | None}, "parts": [{frame: points}], "reports",
  > "generator"}}, "device", ...}; artist keys are not included (they are never overwritten).

* **`retrack_object(get_rgb, store, shape_id, frames, width, height, model='sam2.1-hiera-tiny', device='auto', job=None, colour_transform=colour.TRANSFORM_ID)`**

  > Re-track one stored shape (see retrack_objects). Returns "keys" {frame: points | None}, "reports",
  > "generator" and the device fields.

* **`retrack_ops(store, shape_id, result)`**

  > -> (number of AI key changes, ops). Main shape: AI keys replaced/added/removed and AI diagnostics updated;
  > parts: each result part goes to the existing part shape of the object nearest to it (same point count), or to a
  > new part shape; existing parts without a match get collapsed AI keys on the decided frames. Artist keys are
  > never touched (also enforced by the bus) and their frames carry no AI report.

* **`apply_retrack(bus, store, shape_id, result)`**

  > One undoable batch for one re-tracked shape. Returns the number of AI key changes.

* **`apply_retracks(bus, store, shapes)`**

  > Several re-tracked shapes ({shape_id: result}) as ONE undoable batch. Returns {shape_id: AI key changes}.

* **`result_ops(shot_id, object_name, result, anchors=ANCHORS)`**

  > -> (object_id, shape_id, ops) creating an AI object + main shape (+ part shapes) with keys and per-frame
  > diagnostics (diagnostics belong to the main shape).

* **`apply_result(bus, shot_id, object_name, result, anchors=ANCHORS)`**

  > Create an AI object + shape with its keys and per-frame diagnostics as ONE undoable step.
  > Returns (object_id, shape_id).

* **`apply_results(bus, shot_id, results, anchors=ANCHORS)`**

  > Several tracked objects (track_objects()["objects"]) as ONE undoable step. Returns [(object_id, shape_id)].

* **`read_checkpoint(directory)`**

  > The checkpoint's meta (with "definition": frames, objects, model, colour id, anchors, parts) or None.

* **`discard_checkpoint(directory)`**
* **`result_to_json(res)`**

  > track_objects() result -> JSON-safe dict (frame keys as strings).

* **`result_from_json(d)`**

  > Inverse of result_to_json (frame keys back to int).

* **`read_stereo_checkpoint(directory)`**

  > The stereo run's meta (views, hero, objects, frames, settings, finished passes, derived prompts) or None.

* **`write_stereo_checkpoint(directory, meta)`**
