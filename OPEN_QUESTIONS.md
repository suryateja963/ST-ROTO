# Open Questions

> **2026-11-15 owner answers:** OQ-01 → D-009/D-010/D-011/D-012; OQ-02..06 → D-022..D-025; OQ-07 → D-016; OQ-08 → D-013; OQ-09 → D-017/D-018; OQ-10 → D-014; OQ-13 → D-020; OQ-14 → D-019. Text below is kept for history.

First issue, 2026-11-15. Recommendations here are **not** approved requirements. Each stays open until the project owner answers.

## Blocking

### OQ-01 Development licence for Nuke
**Why it matters.** Nuke Non-commercial and Nuke Indie cannot load NDK C++ plug-ins and cap Python at 10 node retrievals (Foundry documentation). The specified C++ node family, Deep support and custom runtime cannot be run or tested on the current machine.

| Option | Effect |
|---|---|
| A. Request a developer licence from Foundry (info@foundry.com; Foundry says community tool developers may qualify) | Full specification remains achievable. Outcome depends on Foundry |
| B. Buy or rent a commercial Nuke licence | Same as A, at cost |
| C. Re-scope to what Non-commercial can run (Python, gizmos, Inference node) | Scope change under §28. Drops C++ nodes, Deep, custom runtime; object management must work within the 10-node cap |
| D. Write C++ without being able to run it | Nothing could pass status "Implemented" |

**Recommendation:** A, with C explored in parallel as the only work that can be tested today.

**New (2026-11-15):** Foundry EULA clause 2.1(g)(e) forbids using a Non-commercial licence "to create any commercial tools or plug ins" and for any professional or business purpose. ST-ROTO is free and open source but aimed at commercial users, and "commercial" is undefined. The request to Foundry should also ask in writing whether developing ST-ROTO on Non-commercial is permitted (R-23). Until answered, work on this machine is limited to research probes.

### OQ-11 First verifiable milestone
Proposed once OQ-01 is answered. Candidate: "one promptable segmentation model running in-process in Nuke on the RTX 5060, output written to a native Roto node, with measured VRAM and time".

## Collaboration (from master prompt §19.2; architecture for collaboration cannot be finalised until answered)

- **OQ-02** Central-server, peer-to-peer and hybrid as three selectable modes, or another arrangement?
- **OQ-03** How are simultaneous edits made while disconnected reconciled?
- **OQ-04** Can object ownership be transferred?
- **OQ-05** Can supervisors override locks, and under what conditions?
- **OQ-06** Is temporary external freelancer access required?

Implementation implications have not yet been researched (task T-020).

## Licensing

### OQ-07 Is the SAM License acceptable for the production model set?
Full text now read: royalty-free use, modification and redistribution; redistribution under the same agreement with a copy; restricted uses (trade controls, ITAR, military, nuclear, espionage, weapons); no reverse engineering of the materials; Meta may amend with immediate effect; terminates on IP suit against Meta. It does not impose its terms on ST-ROTO's own code. Weights are gated on Hugging Face. SAM 2.1 (Apache-2.0) has none of these conditions but lacks text/concept prompting. **Recommendation unchanged:** optional user-downloaded model with the agreement shown; SAM 2.1 default; never bundled.

### OQ-08 Project source licence
Requirement: free, open source, permits commercial use, modification, redistribution, derivatives. Candidates: Apache-2.0, MIT, BSD-3-Clause, MPL-2.0, GPL-3.0. **Recommendation:** Apache-2.0 (explicit patent grant; same licence as SAM 2 and Depth Anything V2 Small). Consequence: GPL-licensed code such as Robust Video Matting could not be incorporated. Also to confirm with Foundry's EULA: whether an NDK plug-in may be distributed under the chosen licence. Not approved.

## Scope clarifications

- **OQ-09** Lower bound "Nuke 13 and later": each release line needs its own compiled build and has different Python and Qt versions. Is every line from 13 mandatory for 1.0, or is the list to be set after measuring the cost?
- **OQ-10** GitHub: which account and repository name? No repository exists in `D:\ST-ROTO` and no account has been inspected.
- **OQ-12** Answered. Owner restated 2026-11-15: "everything we build stays in this folder". Applied to weights, build output, caches, venvs, probes and test data (D-006).
- **OQ-14** Install Visual Studio 2022 Build Tools and CMake? Required to compile any NDK C++ code (routes B/D). System-wide installs outside `D:\ST-ROTO`, so they need approval. Only useful once OQ-01 gives a licence that loads plug-ins.
- **OQ-15** Answered 2026-11-15: owner asked for a public repository named `ST-ROTO`; local Git initialised on `main` (D-007).
- **OQ-13** Benchmark footage: what footage with ground-truth mattes may lawfully be used and published?

## Still open

- **OQ-11** First verifiable milestone (Claude to propose, now that the route is known).
- **OQ-16** *(Answered 2026-11-17 → D-035: confirmed.)* Confirm reading of D-024: supervisor lock override allowed only when the lock holder is offline/idle.
- **OQ-17** *(Answered 2026-11-17 → D-036: 15 minutes.)* Idle/offline threshold before a supervisor may override a lock.
- **OQ-23** *(Answered → D-031: approved.)* (2026-11-16) Benchmark/calibration data under D-020: approve the licence of an SA-V subset (CC BY 4.0, masks, ~20-50 validation videos into `D:\ST-ROTO\data\benchmarks`)? Needed for T-068 (`docs/RESEARCH_2026-11-16_BENCHMARK_DATASETS.md`).
- **OQ-24** *(Answered 2026-11-17 → D-037: every operation signed.)* (2026-11-16) Collaboration: should every replicated operation be signed by its author (full signed audit), or only ownership/lock/permission changes? Recommendation: every operation (`docs/COLLABORATION_ARCHITECTURE.md` §5).
- **OQ-22** *(Answered → D-032: option (a) approved.)* (2026-11-16) Learned matting model for hair / fine edges. Every permissive-weight candidate (ViTMatte, BiRefNet-matting) is trained on research datasets with non-commercial or unpublished terms; ZIM and MatAnyone are non-commercial outright (`docs/RESEARCH_2026-11-16_MATTING.md`). Options: (a) ViTMatte-S as optional download, off by default, caveat shown; (b) BiRefNet_HR-matting likewise; (c) no learned matting in 1.0. **Recommendation:** (a). Model-free soft edges + motion blur proceed meanwhile (no download).

## Architecture (Phase 2), raised 2026-11-15

- **OQ-18** *(Answered → D-026: approved.)* Approve the architecture proposal (`ARCHITECTURE.md`, ADR-0001 to ADR-0010) as the basis for Phase 4 code? Changes can be requested per ADR.
- **OQ-19** *(Answered → D-027: SQLite.)* Project data in a **SQLite database per project** plus a cache folder, with the Nuke script holding only a link (ADR-0005)? The alternative is storing everything inside the .nk script: simpler, but no transactions, larger scripts, harder crash recovery. **Recommendation:** SQLite.
- **OQ-20** Nuke 13 (Python 3.7, older CUDA) may have no GPU-capable ONNX Runtime build. If verification confirms that, should Nuke 13 get CPU-only AI (manual roto fully supported), or should the 1.0 floor move? Decision deferred until T-032 verifies the facts.
- **OQ-21** *(Answered → D-028: keep history, add NOTICE.)* Commit f3257b8 contains two small files of SAM 2.1 parameters (Apache-2.0, ~70 KB each) committed by mistake (now removed). Rewrite history to purge them (needs a force-push to `main`) or leave them, adding the Apache NOTICE? **Recommendation:** leave them and add attribution; a force-push is disruptive and the licence permits redistribution.

- **OQ-28** *(Answered 2026-11-17 → D-041: both available (T-090); default fit 1920x1080 in Non-commercial.)* (2026-11-17) Mattes above HD in Nuke Non-commercial (T-089): Nuke NC will not render above 1920x1080, but ST-ROTO's EXR mattes are written by ST-ROTO's own code from the stored shapes, so on a 4K plate they would come out at 4K in NC. Tracking only uses a reduced render (Nuke's own suggestion: a Reformat). Is writing full-resolution mattes in NC acceptable to you under Foundry's NC terms, or should ST-ROTO cap its own matte output at the edition's limit too? Recommendation: cap it in NC (conservative; commercial editions are unaffected). Not blocking; unchanged until you decide.
- **OQ-27** *(Answered 2026-11-17 → D-039 accepted: keep fitting to the shot format.)* (2026-11-17) Mixed-resolution sequences (T-086, D-039 proposed): ST-ROTO now fits frames of another size to the shot format like a default Reformat and says so in the status (before: silently wrong shapes). Nuke itself shows such frames unscaled, so the artist needs a Reformat above ST_Roto for plate and shapes to line up. Keep this, or refuse mixed-resolution input with an error instead? Recommendation: keep (works, visible, reversible). Not blocking.
- **OQ-26** *(Answered 2026-11-17: firewall rule approved; T-087 passed; rule kept, D-040.)* (2026-11-17) Offline test of the whole stack: Nuke 17.1 NC contacts an AWS server at every start (T-085, R-45). To prove ST-ROTO + Nuke work with no network, may Claude add a temporary Windows Firewall rule blocking outbound traffic for `Nuke17.1.exe` (needs administrator rights; removed after the test), or will you run one test with the network disconnected? Not blocking: ST-ROTO's own code is verified offline already.
- **OQ-25** (2026-11-16) Prompting: on real footage (SA-V) one click picked the wrong object in 19 of 51 first frames; a box (+ click) in 2 of 51. Add a **box prompt** to the ST_Roto node (drag a rectangle in the viewer)? Recommendation: yes, as an additional prompt type next to clicks (`RESULTS_sav.md` §1). **Answered 2026-11-16: yes (D-034); implemented T-079.**
