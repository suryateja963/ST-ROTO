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
- **OQ-16** Confirm reading of D-024: supervisor lock override allowed only when the lock holder is offline/idle.
- **OQ-17** Idle/offline threshold before a supervisor may override a lock.

## Architecture (Phase 2), raised 2026-11-15

- **OQ-18** Approve the architecture proposal (`ARCHITECTURE.md`, ADR-0001 to ADR-0010) as the basis for Phase 4 code? Changes can be requested per ADR.
- **OQ-19** Project data in a **SQLite database per project** plus a cache folder, with the Nuke script holding only a link (ADR-0005)? The alternative is storing everything inside the .nk script: simpler, but no transactions, larger scripts, harder crash recovery. **Recommendation:** SQLite.
- **OQ-20** Nuke 13 (Python 3.7, older CUDA) may have no GPU-capable ONNX Runtime build. If verification confirms that, should Nuke 13 get CPU-only AI (manual roto fully supported), or should the 1.0 floor move? Decision deferred until T-032 verifies the facts.
- **OQ-21** Commit f3257b8 contains two small files of SAM 2.1 parameters (Apache-2.0, ~70 KB each) committed by mistake (now removed). Rewrite history to purge them (needs a force-push to `main`) or leave them, adding the Apache NOTICE? **Recommendation:** leave them and add attribution; a force-push is disruptive and the licence permits redistribution.
