# Decision Register

| ID | Date | Decision | Decided by | Basis |
|---|---|---|---|---|
| D-001 | 2026-11-15 | All ST-ROTO work is kept in `D:\ST-ROTO` | Project owner | Owner instruction |
| D-002 | 2026-11-15 | The owner's specification is stored verbatim as `docs/MASTER_PROMPT.md` and is the authoritative requirement text | Claude (delegated: document structure, §29 allows adapting file structure) | Avoids paraphrase drift in the requirements register |
| D-003 | 2026-11-15 | Persistent registers live at the repository root; reports live in `docs/` | Claude (delegated) | Matches the file list in §29 |
| D-004 | 2026-11-15 | Evidence labels [V] verified / [U] unverified are used in all research documents | Claude (delegated) | §2.3 and §32: no untested claim presented as fact |
| D-005 | 2026-11-15 | Models under non-commercial, GPL or unread licences are classed research-only until reviewed | Claude (delegated; conservative reading of §24) | §24 forbids restricted weights in the production set |
| D-006 | 2026-11-15 | D-001 covers everything built: code, probes, model weights, venvs, caches, build output, test data | Project owner (restated) | Owner instruction during audit |
| D-007 | 2026-11-15 | Public GitHub repository named `ST-ROTO` (https://github.com/suryateja963/ST-ROTO); everything related to the project is uploaded there | Project owner | Owner instruction |
| D-008 | 2026-11-15 | Repository excludes local tools (`.tools/`), caches, build output and model weights; commits use the owner's GitHub no-reply address, not a personal email | Claude (delegated; §16 privacy, §24 weights) | Weights redistribution must follow each licence; personal email must not be published without consent |
| D-009 | 2026-11-15 | Stay on Nuke Non-commercial for development (no developer or commercial licence for now) | Project owner | OQ-01 answer |
| D-010 | 2026-11-15 | Continue full development on Non-commercial despite EULA 2.1(g)(e) ambiguity; owner accepts that risk | Project owner | OQ-01 / R-23 answer |
| D-011 | 2026-11-15 | C++ nodes, NDK Deep and custom C++ runtime **remain mandatory for 1.0** but are deferred until a licence that loads plug-ins is available. 1.0 cannot ship before they pass | Project owner | Scope question; §28 respected (no re-scope) |
| D-012 | 2026-11-15 | Single-node core design for the Non-commercial 10-node cap: one ST-ROTO group/gizmo + docked PySide6 panel; full node family added for commercial editions | Project owner | Node-cap question |
| D-013 | 2026-11-15 | Project licence **Apache-2.0** | Project owner | OQ-08 |
| D-014 | 2026-11-15 | GitHub CLI installed via winget (system-wide) to create and manage the public repo | Project owner | OQ-10 |
| D-015 | 2026-11-15 | Approved model downloads for prototyping (into `D:\ST-ROTO`, never committed): SAM 2.1 tiny + small, EdgeTAM, BiRefNet, ViTMatte small (research use until training-data question resolved), TAPIR/BootsTAPIR, Depth Anything V2 Small | Project owner | §15 approval |
| D-016 | 2026-11-15 | SAM 3: supported as optional user download only, never bundled; SAM 2.1 default | Project owner | OQ-07 |
| D-017 | 2026-11-15 | Nuke 13 and later is mandatory for 1.0 (13, 14, 15, 16, 17 lines) | Project owner | OQ-09 |
| D-018 | 2026-11-15 | Older Nuke versions installed side by side when needed; owner downloads/installs (Foundry login) | Project owner | OQ-09 follow-up |
| D-019 | 2026-11-15 | Visual Studio Build Tools not installed now; install when a plug-in-capable licence exists | Project owner | OQ-14 |
| D-020 | 2026-11-15 | Benchmark footage: public research datasets (each licence approved by owner), owner's own footage (local only), synthetic CG footage | Project owner | OQ-13 |
| D-021 | 2026-11-15 | Competitor comparison against all listed products: free tools when ready, paid tools via trials later | Project owner | §21 |
| D-022 | 2026-11-15 | Collaboration modes: one sync system that auto-selects central server when configured, else peer-to-peer | Project owner | OQ-02 |
| D-023 | 2026-11-15 | Disconnected edits: keep both versions as branches; object owner chooses or merges per frame/keyframe; non-overlapping frames merge automatically | Project owner | OQ-03 |
| D-024 | 2026-11-15 | Owner can transfer ownership; supervisor can reassign ownership (audited); supervisor can override locks **only when the lock holder is offline/idle** (Claude's reading of two ticked options; owner may correct) | Project owner | OQ-04, OQ-05 |
| D-025 | 2026-11-15 | External freelancers: supported as normal artist accounts, removed manually by an admin | Project owner | OQ-06 |
| D-026 | 2026-11-15 | Architecture approved: `ARCHITECTURE.md` and ADR-0001..ADR-0010 accepted as the basis for Phase 4 code | Project owner ("Approved, continue building") | OQ-18 |
| D-027 | 2026-11-15 | Project data in one SQLite database per project + content-addressed cache; Nuke script holds only a link (ADR-0005) | Project owner (approved recommendation) | OQ-19 |
| D-028 | 2026-11-15 | Git history is not rewritten; Apache-2.0 attribution for the SAM 2.1 parameter files added in `NOTICE` | Project owner (approved recommendation) | OQ-21 |
| D-029 | 2026-11-16 | SAM 2.1 memory attention runs in fp16 by default (fp32 selectable); conversion via `tools/models/convert_fp16.py` | Claude (delegated technical choice) | `research/probes/2026-11-16_fp16/RESULTS.md`: identical masks on the synthetic shot (≤ 7 low-res pixels flip), −22% peak GPU (tiny), ~2× faster steps; to re-check on real footage |
| D-030 | 2026-11-16 | Nuke → numpy pixels stay on the float-TIFF file path (no Python buffer API; exact; 0.022-0.041 s/frame); in-memory transfer deferred to the NDK route | Claude (delegated technical choice) | `research/probes/2026-11-16_pixels/RESULTS.md` |
| D-031 | 2026-11-16 | Benchmark/calibration data: a small SA-V subset (CC BY 4.0, masks) approved under D-020; stored in `D:\ST-ROTO\data\benchmarks` (git-ignored), attribution in NOTICE for any published figures | Project owner | OQ-23 |
| D-032 | 2026-11-16 | Learned matting: ViTMatte-S (hustvl/vitmatte-small-composition-1k, Apache-2.0 weights) approved as an OPTIONAL download, off by default, with its training-data caveat (Composition-1k / Adobe DIM terms) shown to the user | Project owner | OQ-22 option (a) |
| D-033 | 2026-11-16 | Review rule change from real-footage calibration (T-068, SA-V): absent runs longer than 16 frames flag only their exit and return frames (CHECK) instead of every frame as LOST; score thresholds (1.0, 0.7) and area-jump 0.35 unchanged | Claude (evidence-based default; owner may override) | `research/probes/2026-11-16_calibration/RESULTS_sav.md` |
| D-034 | 2026-11-16 | Box prompt added to the ST_Roto node (in-viewer BBox knob, Set box / Clear box), next to include/exclude clicks | Project owner | OQ-25 |
| D-035 | 2026-11-17 | D-024 reading confirmed: a supervisor may override a lock **only** when the lock holder is offline or idle; never while the holder is active. Every override is an audited operation | Project owner | OQ-16 |
| D-036 | 2026-11-17 | Idle/offline threshold for a supervisor lock override: **15 minutes** without a presence heartbeat from the lock holder | Project owner | OQ-17 |
| D-037 | 2026-11-17 | Collaboration audit: **every** replicated operation is signed by its author (per-user key pair), not only ownership/lock/permission changes | Project owner | OQ-24 |

Architecture decisions: see `docs/adr/` (ADR-0001..0010 Accepted per D-026).
