# Requirements Register

First issue, 2026-11-15.

**Authoritative text.** The exact wording of every requirement is in `docs/MASTER_PROMPT.md` (verbatim copy of the owner's specification). Each row below binds *every* bullet in the cited section, not only the words in the summary column. Nothing in a summary narrows the source text. This issue registers requirements at section-group level; splitting each bullet into its own ID is task T-012.

**Source** for all rows: project owner, master prompt of 2026-11-15, section given. **Priority**: the owner states that all mandatory requirements belong to 1.0 (§28), so every row is Mandatory unless the source itself says "optional", "where suitable" or "investigate". **Status vocabulary** is the eight-step scale in §22. **Test evidence**: none exists for any row.

| ID | § | Requirement (summary; source text governs) | Priority | Depends on | Status | Verification method | Known limitations |
|---|---|---|---|---|---|---|---|
| REQ-001 | 1 | Complete roto department in Nuke combining the 15 listed capability areas | Mandatory | all | Planned | Acceptance list §30 | |
| REQ-002 | 2.1 | Never invent requirements; missing decisions recorded, researched, recommended, approved | Process | – | Implemented (as process) | `OPEN_QUESTIONS.md` review | |
| REQ-003 | 2.2 | Permanent requirements register with traceability | Process | – | Implemented (first issue) | This file | Bullet-level IDs outstanding |
| REQ-004 | 2.3 | No fake implementation; prototypes labelled | Process | – | Planned | Code review | |
| REQ-005 | 2.4 | No silent scope reduction | Process | – | Planned | Change log audit | |
| REQ-006 | 2.5 | Approval before destructive or system-wide actions; inspect workspace first | Process | – | Implemented (as process) | Development log | |
| REQ-007 | 2.6 | Persistent task board and log; verifiable milestones | Process | – | Implemented (first issue) | `TASK_BOARD.md`, `DEVELOPMENT_LOG.md` | |
| REQ-010 | 3 | Fully functional traditional roto with every AI feature disabled | Mandatory | REQ-060..066 | Planned | Shot completed in Nuke with AI disabled | |
| REQ-011 | 3 | Artist can modify, replace, correct, override and disable all AI output | Mandatory | REQ-041 | Planned | Scripted and manual tests in Nuke | |
| REQ-020 | 4 | Hardware detection and capability profiles; NVIDIA, AMD, Intel, CPU-only | Mandatory | REQ-032 | Planned | Tests per hardware class | Only one NVIDIA machine available |
| REQ-021 | 4 | Memory-aware inference: model selection, batching, tiling, caching, fallback | Mandatory | REQ-032 | Planned | Memory tests | 8 GB VRAM, 16 GB RAM target |
| REQ-022 | 4 | Report when a feature is unavailable due to hardware, driver, edition or API | Mandatory | – | Planned | Fault-injection tests | |
| REQ-030 | 5.1 | Target Nuke 13+ across Non-commercial, Indie, Nuke, NukeX, Studio; verify each; matrix. **Owner confirmed 13+ mandatory (D-017)** | Mandatory | – | Researching | `COMPATIBILITY_MATRIX.md` | **Non-commercial and Indie cannot load C++ plug-ins and cap Python at 10 nodes (Foundry). See RISK R-01, OQ-01** |
| REQ-031 | 5.2 | Integration architecture backed by evidence (Python API, NDK, gizmos, Qt, viewer, Roto) | Mandatory | – | Researching | ADRs with prototype results | |
| REQ-032 | 5.3 | AI inference executes inside the Nuke process; no external server, cloud or remote dependency | Mandatory | – | Tested inside Nuke (17.1 NC, RTX 5060) | Process and network inspection during inference | SAM 2.1 runs in-process via onnxruntime-gpu 1.26.0 (product code st_roto_ai + st_roto_nuke); GUI Track button: 48 frames in 22 s on CUDA. Other Nuke versions/GPUs untested; ORT pinned per CUDA major. |
| REQ-040 | 6 | Dedicated node family (ten proposed modules) with validated I/O, errors, docs | Mandatory | REQ-031 | Planned | Per-node tests in Nuke | Naming and split still to be researched |
| REQ-041 | 6 | Export native Roto/RotoPaint shapes editable without ST-ROTO installed | Mandatory | – | Tested inside Nuke (17.1 NC only) | Open exported script in clean Nuke | st_roto_nuke.roto_export writes fully keyed native Roto shapes from the project store; tests/nuke/run_nuke_tests.py: render vs exact spline IoU 0.9980-0.9984, vs analytic shape 0.9968-0.9978, frames -2..5. Not yet: RotoPaint, layers per object, feather, other Nuke versions, opening without ST-ROTO installed (to test). |
| REQ-042 | 6 | AI updates never silently destroy artist geometry; five provenance classes kept distinct | Mandatory | REQ-080 | Implemented (core) | Regression tests | Implemented (core, unit-tested): AI cannot overwrite, unlock or delete artist/imported/locked content; artist edits of AI keys become artist_modified_ai (tests/unit/test_store_commands.py). Not yet in Nuke. |
| REQ-050 | 7 | Structured model research with the listed fields per candidate | Mandatory | – | Researching | `MODEL_REGISTER.md` completeness | 10 candidates, many fields empty |
| REQ-051 | 7 | Modular model-adapter architecture: auto/manual selection, pinning, rollback, routing, isolation of experimental models | Mandatory | REQ-032 | Planned | Adapter tests | |
| REQ-052 | 7, 15 | Model manager shows provenance and licence | Mandatory | REQ-110 | Planned | UI test | |
| REQ-060 | 8 | Ten selection input methods | Mandatory | REQ-040 | Planned | Per-method tests | Text prompts "where supported" |
| REQ-061 | 8 | Multi-object identity, hierarchy, occlusion, reappearance, crossings, locking | Mandatory | REQ-080 | Planned | Benchmark categories | |
| REQ-062 | 8 | Ten target object categories; no single-model assumption | Mandatory | REQ-051 | Planned | Category benchmarks | |
| REQ-070 | 9 | Twenty-three difficult cases as first-class evaluation categories, with confidence, failure detection, inspection, corrective controls | Mandatory | REQ-160 | Planned | Category benchmarks | No commercially licensed video matting model identified yet |
| REQ-080 | 10 | Unified internal representation linking identity, masks, alpha, splines, tracking, confidence, corrections, history | Mandatory | – | Planned | Round-trip tests | |
| REQ-081 | 10 | Listed geometry representations; switching without silent loss | Mandatory | REQ-080 | Planned | Conversion round-trip tests | |
| REQ-082 | 10 | Listed shape operations (per-point feather, booleans, holdouts, split/merge, locking, versioning) | Mandatory | REQ-080 | Planned | Unit and in-Nuke tests | |
| REQ-090 | 11 | Forward/backward propagation and listed temporal strategies | Mandatory | REQ-051 | Planned | Temporal benchmarks | |
| REQ-091 | 11 | Listed artist controls over propagation | Mandatory | REQ-090 | Planned | In-Nuke tests | |
| REQ-092 | 11 | Listed sequence conditions (negative frames, gaps, retimes, mixed resolution, proxy) | Mandatory | REQ-090 | Planned | Edge-case sequences | |
| REQ-093 | 11 | Bounded memory, resumable processing; never load whole sequence | Mandatory | REQ-021 | Planned | Long-shot memory test | |
| REQ-100 | 12 | Listed alpha output types as first-class deliverables | Mandatory | – | Planned | Pixel comparison tests | |
| REQ-101 | 12 | Listed refinement operations; no silent alpha-convention change | Mandatory | – | Planned | Unit and visual tests | |
| REQ-110 | 13 | Listed formats via the host; metadata and bit depth preserved | Mandatory | – | Planned | Read/write comparison | Non-commercial disables some codecs |
| REQ-111 | 13 | 1080p to 8K+, anamorphic, tiling, coordinate mapping across proxy/full/viewer/source/output | Mandatory | REQ-021 | Planned | Resolution tests | Non-commercial output capped at HD |
| REQ-112 | 13.1 | Respect Nuke colour management; model conversions documented, reproducible, inspectable | Mandatory | – | Planned | Colour round-trip tests | |
| REQ-113 | 13.2 | Use and preserve extra channels | Mandatory | – | Planned | Channel preservation tests | |
| REQ-114 | 13.3 | Deep-aware functionality; never silently flatten | Mandatory ("wherever technically possible") | REQ-031 | Planned | Deep sample comparison | Deep ops need the NDK |
| REQ-115 | 13.4 | Stereo views independent with consistency checks; multi-camera when data exists | Mandatory | – | Planned | Stereo test shots | |
| REQ-120 | 14 | Listed panels, overlays and controls; native feel | Mandatory | REQ-031 | Planned | UI test plan | |
| REQ-121 | 14 | Configurable shortcuts, toolbars, layouts, themes, workspaces, presets; dark default, light option; beginner/advanced | Mandatory | REQ-120 | Planned | UI test plan | |
| REQ-122 | 14 | Non-blocking processing where Nuke permits; pause, resume, cancel, priority | Mandatory | REQ-032 | Implemented (v0), tested inside Nuke 17.1 | In-Nuke responsiveness tests | Tracking on a worker thread with cancel (st_roto.jobs, ST_Roto Cancel button). GUI mean frame gap 19 ms during tracking but 2 stalls > 100 ms (max 1.56 s) - R-40. Pause/resume/priority not implemented. |
| REQ-130 | 15 | Model manager: listed 15 functions; three storage locations; no download without approval | Mandatory | REQ-051 | Planned | Functional and offline tests | |
| REQ-140 | 16 | Fully local operation; no telemetry; no automatic transmission; no account | Mandatory | – | Planned | Offline verification test detecting outbound traffic | |
| REQ-150 | 17 | Pretrained models first; architecture ready for local learning; correction data artist-controlled; listed investigations | Mandatory (learning features: "investigate") | REQ-080 | Planned | Design review | |
| REQ-160 | 18 | Project state: listed 16 capabilities incl. autosave, crash recovery, transactions, snapshots | Mandatory | – | Implemented (core) | Crash-recovery tests | Partly implemented (core): SQLite project store, transactions, op log, undo/redo, persistence across reopen (unit-tested). Autosave/crash recovery/snapshots/packages not yet. |
| REQ-161 | 18 | Separation of data classes; portable project packages | Mandatory | REQ-160 | Planned | Package transfer test | |
| REQ-170 | 19 | Optional collaboration with the listed capabilities; solo use never degraded | Mandatory, feature optional to users | REQ-160 | Planned | Collaboration tests | Five decisions open (OQ-02..06) |
| REQ-171 | 19.1 | Fourteen approved collaboration decisions | Mandatory | REQ-170 | Planned | Collaboration tests | |
| REQ-180 | 20 | Export/interchange research and implementation; listed attributes preserved; delivery packages | Mandatory ("where suitable" for SVG, Alembic) | REQ-080 | Planned | Round-trip tests | Silhouette and Mocha formats not researched |
| REQ-190 | 21 | Benchmark against listed competitors with lawful access; methodology published first; listed metrics; no correction-time metric; honest reporting | Mandatory | – | Planned | `BENCHMARK_PLAN.md` | No ground-truth footage identified |
| REQ-200 | 22 | Listed test types; tests inside real Nuke; eight-step status scale | Mandatory | – | Planned | `TEST_PLAN.md` | Real-Nuke testing needs a licence that loads plug-ins |
| REQ-210 | 23 | Windows `.exe` installer with listed functions; non-admin where possible; manual install; offline package | Mandatory | – | Planned | Install/upgrade/repair/uninstall tests | Technology not selected |
| REQ-220 | 24 | **Licence: Apache-2.0 approved (D-013).** | Free and open source permitting listed uses; licence approved before publication; listed governance documents; no NC weights in production set | Mandatory | – | Researching | Licence review | OQ-07, OQ-08 |
| REQ-230 | 25 | Public GitHub repository with listed structure and documents; no 1.0 until all acceptance tests pass | Mandatory | – | Planned | Repository audit | No repository yet; OQ-10 |
| REQ-240 | 26 | Subagent strategy with ownership boundaries and independent review | Process | – | Planned | Log review | |
| REQ-250 | 27 | Nine phases in order; research and architecture not skipped | Process | – | Researching (Phase 1) | Phase deliverables | Phase 1 incomplete |
| REQ-260 | 28 | 1.0 not redefined without approval | Process | – | Planned | Change log audit | |
| REQ-270 | 29 | Sixteen persistent documents; ten-point milestone report | Process | – | Implemented in part | Repository contents | Seven documents not yet created |
| REQ-280 | 30 | Twenty acceptance demonstrations, each with a reproducible method | Mandatory | all | Planned | `RELEASE_CHECKLIST.md` | |
| REQ-290 | owner, 2026-11-15 | Everything built for ST-ROTO stays in `D:\ST-ROTO` | Mandatory | – | Implemented (as process) | Folder audit | Owner confirmed (D-006): covers models, caches, build output, venvs, probes, test data |
| REQ-291 | owner, 2026-11-15 | Public GitHub repository `ST-ROTO`; everything related to the project uploaded there (except model weights, caches, local tools per D-008) | Mandatory | – | In progress | Repository audit | D-007 |
| REQ-292 | owner, 2026-11-15 | Under Non-commercial, ST-ROTO works as a single-node core within the 10-node Python cap | Mandatory | REQ-040 | Planned | In-Nuke test under NC with >10 user nodes in script | D-012 |
| REQ-293 | owner, 2026-11-15 | Collaboration decisions D-022..D-025 | Mandatory | REQ-170 | Planned | Collaboration tests | OQ-16, OQ-17 |
