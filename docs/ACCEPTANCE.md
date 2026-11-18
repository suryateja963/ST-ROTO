# ST-ROTO acceptance criteria (master prompt section 30) — status 2026-11-18

"ST-ROTO is not ready for version 1.0 merely because the plugin loads." Every criterion below has a reproducible
verification method. **Automated** = run by `tools/acceptance/run_acceptance.py` (dated reports in
`docs/acceptance/`); **manual** = steps a person performs. Status words: **met** (for this machine and edition),
**partly** (works; listed gaps remain), **not met**, **blocked** (needs something outside the project's control).
A green acceptance run does not change a status where gaps are listed.

Verified environment so far: Windows 11, Nuke 17.1v3 **Non-commercial** only, RTX 5060 Laptop 8 GB.

| # | criterion | verification method | evidence | status | gaps before 1.0 |
|---|---|---|---|---|---|
| 1 | Installation using the `.exe` | automated `installer` step: package -> install with Nuke's python -> Nuke loads the installed copy and tracks -> uninstall; owner's real set-up checked untouched | T-103, `research/probes/2026-11-17_installer` | **partly** | unsigned .exe; text menu, no wizard; not yet run on another machine or on the owner's real Nuke |
| 2 | Integration into supported Nuke installations | automated `nuke_headless` + `gui` on each supported version/edition; manual check of menus and panes | 17.1 NC: 45 headless tests + 7 GUI tests | **partly** | only Nuke 17.1 NC verified; Nuke 13-16, Indie, Nuke, NukeX, Studio not tested (REQ-030) |
| 3 | Fully functional traditional manual roto | automated: `test_traditional_roto_without_ai` (ONNX Runtime unimportable), GUI AI toggle | T-088 | **partly** | drawing tools are Nuke's own Roto; no full shot done by an artist with AI off |
| 4 | Working AI-assisted roto | automated Track / Re-track / prompts tests; SA-V benchmark | T-055..T-100; stereo / multi-camera (T-109, T-119, T-120); extra channels (T-110); SA-V 51 sequences (T-068, T-080, T-082); first real production footage: 7 owner green-screen shots, 4K (T-126: 5/7 at 0.99 core IoU vs a keyed reference, wide shot fails with tiny, fixed by large) | **partly** | no shot completed and judged by an artist (T-126 measured real footage against a key only); review flags missed a real failure (DEF-012); scribble and text prompts missing |
| 5 | Working local in-process inference | automated: Track inside Nuke on CUDA (ONNX Runtime in Nuke's Python) | T-011c, T-044, every Track test | **partly** | C++/NDK in-process routes blocked by the Non-commercial licence (T-011b, D-011) |
| 6 | Professional spline and alpha workflows | automated spline/feather/matte/role/output tests; Nuke reads EXRs back exactly | T-049, T-069/70, T-073, T-076, T-098, T-099, T-115 (edge decontamination, despill, chatter reduction) | **partly** | per-object booleans beyond holdout / garbage / merge; shape versioning UI; chatter reduction is opt-in (measured +12 % temporal error on a clean fast track) |
| 7 | Temporal tracking and propagation | automated forward/reverse, range, lock, exclude, difficult sequences | T-060, T-067, T-086, T-097, T-119 (stereo resume), T-121 (propagation along render-pass motion vectors), T-123 (scene cuts: Track stops, Re-track stays in the segment) | **partly** | optical flow computed from live-action plates (T-121 uses renderer vectors only), dissolve detection, candidate review |
| 8 | Difficult-boundary processing | automated matting tests; known-alpha composites | T-031c, T-072 (ViTMatte), T-095, T-126 (real 4K hair: ViTMatte works after tiling fix DEF-013; a key cannot judge hair) | **partly** | hair and motion-blur boundaries limited; edge refinement decision dropped (D-043) |
| 9 | Artist correction and history preservation | automated: artist keys never overwritten, undo/redo, signed history verification | T-052, T-063, T-084, T-097 | **met** (v0) | - |
| 10 | Native Nuke export | automated: native Roto shapes, RotoPaint copy, EXR mattes read by Nuke, JSON round trip | T-063, T-069/70, T-073, T-112 (ST_RotoOutput), T-113 (Alembic via Nuke's USD) | **partly** | Silhouette / Mocha formats blocked (T-077); Alembic not yet checked in a third-party application |
| 11 | Project save and recovery | automated crash recovery, damaged-file restore, packages, relink | T-071, T-075 | **met** (v0) | - |
| 12 | Offline operation | automated `offline` step: audit hook + OS connection watch; manual: firewall test | T-085, T-087 | **met** for ST-ROTO | Nuke NC itself contacts its servers at start (works when blocked) |
| 13 | Model management | automated model manager test + GUI panel | T-056, T-101, T-114 (versions side by side + rollback) | **partly** | update workflow (finding newer approved model releases) |
| 14 | Hardware-aware processing | automated memory-aware choice incl. out-of-memory injection; System report; DirectML Nuke test | T-091, T-092, T-116 (DirectML: AMD / Intel / DirectX 12) | **partly** | AMD hardware and Intel Arc untested (DirectML measured on an NVIDIA GPU and an integrated Intel UHD); free memory of non-NVIDIA GPUs cannot be read (auto picks tiny there) |
| 15 | Correct licensing and provenance | unit: registry refuses non-production licences / unapproved / changed files; manual licence review | T-030/31, T-056, `MODEL_REGISTER.md`, NOTICE | **partly** | full Foundry EULA review for distribution; ViTMatte training-data caveat stays visible |
| 16 | Verified compatibility claims | manual: `COMPATIBILITY_MATRIX.md` claims each backed by a run | T-032 (research only) | **not met** | every claim beyond Nuke 17.1 NC is unverified |
| 17 | Tested collaboration functionality | automated: leases, roles, keys, signed history (simulated co-workers), replication prototype | T-020, T-083, T-084, T-094 | **partly** | no network transport; no test with two real machines |
| 18 | Reproducible quality benchmarks | rerun the SA-V tools (`research/probes/2026-11-16_calibration`, `2026-11-16_shape_fit`) | T-068, T-080, T-082, T-107 (`docs/BENCHMARK_METHODOLOGY.md` v1 published) | **partly** | competitor benchmarks (REQ-190) not run (no lawful access to the products) |
| 19 | Complete documentation | manual review; unit test keeps the API reference in step with the code | `docs/MANUAL.md`, `docs/DEVELOPER_GUIDE.md` (T-124), `docs/INSTALL.md`, `docs/API_REFERENCE.md` (generated, T-125), `docs/USER_GUIDE_v0.md`, release notes, registers, RESULTS files | **partly** | install guide verified on one edition only (17.1 NC; other versions/editions documented as untested); not yet reviewed by an artist |
| 20 | No critical release-blocking defects | automated `defects` step: no OPEN row with 'blocks release = yes' in DEFECTS.md; every acceptance run green | DEFECTS.md (T-105): 11 recorded, 1 open (DEF-009, minor), 0 open release blockers | **partly** | criteria 1-19 still have gaps; the register is only as complete as testing so far |

**Summary:** 3 met (v0), 16 partly, 1 not met (16, compatibility claims). Blocked items: C++/NDK (licence), Silhouette/Mocha formats
(applications). The largest remaining gaps for 1.0: other Nuke versions/editions (2, 16), real production shots
by an artist (3, 4), AMD/Intel GPUs (14).

## Acceptance runs

- `docs/acceptance/run_2026-11-17T144513Z.md` (commit 0af47ac): unit FAILED - found the backup-name collision
  (two backups within one ~2 ms Windows clock tick overwrote each other); fixed in T-104.
- `docs/acceptance/run_2026-11-17T150622Z.md`: all steps PASS (unit; 34/34 headless Nuke; 5/5 GUI; installer end
  to end with the owner's set-up untouched; offline: 0 Python network events, 0 external connections).
- `docs/acceptance/run_2026-11-18T044943Z.md` (commit 45b4782, after T-109..T-121): all steps PASS (defects: 11
  recorded, 1 open minor, 0 release blockers; unit; 45/45 headless Nuke; 7/7 GUI; installer end to end with the
  owner's set-up untouched; offline: 0 Python network events, 0 external connections).
