# ST-ROTO Architecture — Proposal

**Status: ACCEPTED by the project owner on 2026-11-15 (D-026).** Assumptions marked below must still be verified; when evidence contradicts an ADR, the ADR is revised and re-approved.
Audience: the project owner (approver) and future contributors.
Every architectural claim below is either *measured* (linked probe), *decided by the owner* (D-number), or explicitly marked as an *assumption* to be tested.

Detailed decisions are in [`docs/adr/`](docs/adr/). Requirements: [`REQUIREMENTS_REGISTER.md`](REQUIREMENTS_REGISTER.md). Owner decisions: [`DECISION_REGISTER.md`](DECISION_REGISTER.md).

---

## 1. Constraints that shape everything

| Constraint | Source | Consequence |
|---|---|---|
| AI inference must run **inside the Nuke process** | §5.3 | No servers or helper processes. Runtime loaded into Nuke's Python. |
| Development licence is **Nuke Non-commercial** | D-009/D-010 | No C++ plug-ins can be run; only 10 Node objects reachable from Python per session; renders capped at 1920×1080 (all measured) |
| C++ nodes, NDK Deep, custom runtime stay **mandatory for 1.0**, deferred | D-011 | The design needs a Python core now and a C++ layer later, without rewriting the core |
| **Single-node core** under the 10-node cap | D-012 | One ST-ROTO node per shot; everything else lives inside it or in ST-ROTO's own data store |
| **Nuke 13 and later** mandatory | D-017 | Python 3.7 → 3.11, PySide2 → PySide6, several CUDA majors. The core must be version-portable. |
| **Traditional roto must work with all AI disabled** | §3 | AI is an optional layer on top of the geometry/roto core, never underneath it |
| Offline, no telemetry, local data only | §16 | No network code in the core; downloads only through the model manager with approval |
| Apache-2.0, permissive model set only in production | D-013, §24 | Model adapters carry licence metadata; research-only models are physically separated |

## 2. What has been measured (the evidence this proposal rests on)

| Fact | Evidence |
|---|---|
| ONNX Runtime GPU runs inside Nuke 17.1 NC, reusing Nuke's own CUDA 12.8 / cuDNN 9.7 DLLs (no NVIDIA files to ship) | `research/probes/2026-11-15_gpu_ort/` |
| The ORT build must match Nuke's CUDA major: 1.26.0 works on Nuke 17.1; 1.27+ (CUDA 13) silently falls back to CPU | same |
| SAM 2.1 image: encoder 65 ms (tiny) / 317 ms (large), 6.7 ms per click, in Nuke on RTX 5060 | `research/probes/2026-11-15_sam2/` |
| SAM 2.1 video tracking ported to ONNX + numpy, identical to PyTorch (IoU ≥ 0.99997); ≈ 0.24 s/frame (tiny) in Nuke | `research/probes/2026-11-15_video/` |
| Native Roto shapes (static and animated) can be written from Python; tangent = 2 × Bézier handle; keys must be set before `Shape.append` | `research/probes/2026-11-15_bezier/`, `…_video/` |
| Pixel transfer Nuke → numpy via float TIFF: ~26–90 ms/frame at 720p–1080p | probes above |
| 8 GB GPU: large-model tracking peaks at 7.8 GB | `…_video/` |

## 3. System overview

```
┌──────────────────────────── Nuke process (any edition, Nuke 13+) ─────────────────────────────┐
│                                                                                                │
│  UI layer (PySide2/6 via compat shim)                                                          │
│   ├─ Docked ST-ROTO panel: objects, layers, history, AI, model manager, jobs                   │
│   └─ Viewer interaction: clicks / boxes / scribbles → commands                                 │
│                │ commands                                                     ▲ events          │
│  ┌─────────────▼───────────────────────── st_roto core (pure Python) ─────────┴──────────────┐ │
│  │ Command bus + undo/redo + transactions (every edit is an operation, ADR-0006)             │ │
│  │ Domain model: Project ▸ Shot ▸ Object ▸ {ShapeTracks, MaskTracks, Corrections, Provenance} │ │
│  │ Geometry engine: Bézier/B-spline/polygon/raster, fitting, booleans, feather (no AI)       │ │
│  │ Temporal engine: keyframes, interpolation, propagation bookkeeping                        │ │
│  │ Job scheduler: background worker, pause/resume/cancel/priority, GPU arbiter, checkpoints  │ │
│  └──────┬───────────────────┬────────────────────────┬──────────────────────────┬───────────┘ │
│         │                   │                        │                          │             │
│  Host adapter (ADR-0003)  AI layer (optional)     Store (ADR-0005)        Exporters             │
│   Nuke API per version     ModelAdapters           SQLite project DB      Native Roto/RotoPaint │
│   pixel I/O, Roto writer   ONNX Runtime sessions   + content-addressed    EXR mattes, JSON,     │
│   10-node budget guard     hardware routing        cache                  SVG/Silhouette/Mocha  │
│                            (ADR-0001, 0007)                                                   │
│                                                                                                │
│  Later (commercial licence, D-011): C++ NDK nodes (Deep, fast pixel path, ORT C++) behind the  │
│  same core interfaces: ST-ROTO Main/Select/Track/Matte/... node family for full editions       │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Dependency rule:** core ← host adapter, AI layer, store, exporters, UI. The core imports nothing from Nuke, Qt or ONNX Runtime, so it is unit-testable outside Nuke and survives version changes. AI depends on the core, never the reverse (§3: AI must be removable).

## 4. Components

### 4.1 Domain model (ADR-0004)
- **Project ▸ Shot ▸ Object (hierarchy) ▸ Representations.** An object can own several representations at once: shape tracks (one or *several* shapes; frame 23 of the video probe needs two pieces), mask tracks (raster, per frame), and matte tracks (soft alpha).
- **Provenance on every element:** `ai_generated`, `imported_native`, `artist_created`, `artist_modified_ai`, `locked` (§6), plus the model id, revision and parameters that produced it.
- **Corrections are first-class:** an artist edit is stored as an operation over the AI result, so re-running AI can never silently overwrite it (§6, REQ-042).
- **Frames:** arbitrary integer frame numbers (negative, gaps, duplicates), time-remap metadata, per-frame resolution (§11).

### 4.2 Geometry engine (ADR-0008)
Pure numpy: adaptive Bézier fitting (static), fixed-count fitting with correspondence (animated), polygon/B-spline/raster conversions, per-point feather, booleans, holdouts, split/merge. The Nuke tangent convention lives in the host adapter, not here. Prototype: `prototypes/geometry/` (7 tests).

### 4.3 Host adapter (ADR-0003)
One adapter per Nuke API generation: pixel I/O (TIFF round-trip today, in-memory path later), native Roto/RotoPaint writer/reader, viewer overlay hooks, and a **node-budget guard**. Under Non-commercial every Python node access is counted and refused before Nuke's 10-node limit is hit, with a clear message (§4: report unavailable features).

### 4.4 AI layer (ADR-0001, ADR-0007)
- `ModelAdapter` interface: capabilities (`click`, `box`, `text`, `propagate`, `matte`, `refine`), inputs/outputs, VRAM estimate, licence, manifest.
- Runtime: ONNX Runtime in-process; one GPU arbiter so two jobs never fight for 8 GB.
- Hardware-aware routing: measured VRAM table per model × resolution, with a fallback chain (large → small → tiny → CPU), always reported to the artist.
- First adapter: SAM 2.1 (image + video), proven in probes.

### 4.5 Jobs and responsiveness (ADR-0009)
Long work (propagation, encoding) runs on a worker thread. The panel stays live; results are applied on Nuke's main thread through the command bus. Pause/resume/cancel/priority. Propagation checkpoints memory state per chunk, so long shots are resumable with bounded RAM (§11). *Assumption to test:* ORT CUDA sessions behave on a non-main thread inside the Nuke GUI. Only headless mode has been tested.

### 4.6 Store (ADR-0005)
- One **SQLite** database per project (WAL mode, transactions, schema migrations) for essential state: objects, shapes, keyframes, corrections, provenance, operation log.
- **Content-addressed cache** for regenerable data: encoder features, masks, renders, keyed by hash of source frame + model revision + parameters.
- The Nuke script holds only a small link (project id + path) on the ST-ROTO node, so scripts stay light and the project survives crashes independently.
- Autosave = the transaction log itself. Snapshots and portable packages = DB copy + manifest (+ optional cache).

### 4.7 Colour (ADR-0010)
The model input transform is an explicit, recorded step: Nuke working space → model input space (sRGB display-referred for SAM) via **PyOpenColorIO, which ships with Nuke** (measured in the audit). Never applied to output pixels. Configurable per model adapter and stored in provenance. Replaces the hard-coded sRGB re-encode used in the probes.

### 4.8 Exporters
Native Roto/RotoPaint (layers per object, fully keyed, editable without ST-ROTO), EXR mattes (per-object channels), JSON (lossless ST-ROTO schema), then SVG/Silhouette/Mocha after format research (§20).

### 4.9 Collaboration (deferred design, ADR-0006 prepares it)
Owner decisions D-022..D-025 are recorded. The operation log (every edit = an immutable, attributed operation) is the foundation for later sync, ownership, branch-and-choose conflict handling (D-023) and audit. No network code until the collaboration phase.

## 5. Node design under the 10-node cap (D-012)

| Node (per shot) | Count | Role |
|---|---|---|
| `ST_Roto` (Group, Python-driven) | 1 | Entry point, knobs, link to project DB, outputs mattes and alpha |
| inside: `Roto` | 1 | Holds all objects as layers: native, editable, exportable |
| inside: `Read` | 1 | Reads cached mattes for the current frame (AI results) |
| inside: merge/shuffle plumbing | 2–3 | Combine shapes and AI mattes into channels |

Python touches roughly 4–6 nodes, within the cap. On commercial editions the same core can drive the full node family (Main, Select, Track, Matte, …) without changing the core. *Assumption to test:* nodes inside a Group count toward the cap when Python accesses them (the measured limit counts Node objects).

## 6. Version strategy (D-017)

| Nuke | Python | Qt binding | CUDA (ORT pin) | Status |
|---|---|---|---|---|
| 13.x | 3.7 [U] | PySide2 [U] | 11.x [U] → old ORT that still supports cp37 [U] | **High risk (R-36)** |
| 14.x | 3.9 [U] | PySide2 [U] | [U] | Untested |
| 15.x | 3.10 [U] | PySide2 [U] | [U] | Untested |
| 16.x | 3.11 [U] | PySide6 [U] | [U] | Untested |
| 17.1 | 3.11.11 [M] | PySide6 6.5.3 [M] | 12.8 → ORT 1.26.0 [M] | Probed |

Core code targets **Python 3.7 syntax** (no `match`, no 3.8+ walrus in the core) with a Qt compatibility shim. The AI runtime is bundled per Nuke line. **Open risk:** whether a working ONNX Runtime GPU build exists for Nuke 13's Python 3.7 + CUDA combination must be verified before 1.0 scope is final.

## 7. Repository layout (proposed)

```
src/st_roto/          core (domain, geometry, temporal, commands, jobs)   — no Nuke/Qt/ORT imports
src/st_roto_nuke/     host adapter, node builder, viewer, native Roto I/O
src/st_roto_ai/       model adapters, runtime, routing, model manager
src/st_roto_store/    SQLite schema, migrations, cache
src/st_roto_ui/       panels (Qt shim)
tests/unit/           pure-Python tests (run in CI, any OS)
tests/nuke/           headless Nuke tests (nuke -t), per version
tools/                export/download/benchmark scripts
prototypes/           evidence code, not shipped
```

## 8. What this proposal does NOT yet settle (for owner decision)

See `OPEN_QUESTIONS.md` OQ-18 to OQ-21.
