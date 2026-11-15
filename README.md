# ST-ROTO

AI-assisted and traditional rotoscoping inside Foundry Nuke. Intended to be free and open source.

> **Licence: Apache License 2.0** (see `LICENSE`; approved by the project owner, decision D-013). Third-party models keep their own licences (`LICENCE_REGISTER.md`) and are never bundled unless their licence permits. "Nuke" is a trademark of The Foundry Visionmongers Ltd.; ST-ROTO is not affiliated with or endorsed by Foundry.
>
> Model weights are never committed here. They will be distributed separately with checksums and only where their licences permit (master prompt §24).

**Status (2026-11-15): Phase 1 done, Phase 2 architecture proposed (awaiting owner approval), Phase 3 prototypes running. No product code exists yet. Prototypes proven in Nuke 17.1 NC: SAM 2.1 click-to-mask and video tracking on GPU in-process, native static and animated Bézier Roto shapes (see `research/probes/`).**

## Read these first

1. `docs/PHASE1_DISCOVERY_REPORT.md` – what was found and what blocks progress.
2. `docs/MACHINE_AUDIT_2026-11-15.md` – measured facts about this machine and its Nuke install.
3. `research/probes/2026-11-15_gpu_ort/RESULTS.md` – GPU and in-process ONNX Runtime results.
4. `docs/RESEARCH_2026-11-15_LICENCES_AND_MODELS.md` – licence texts and model categories.
5. `OPEN_QUESTIONS.md` – decisions that need the project owner.
6. `RISK_REGISTER.md` – what could stop the project.

## Document map

| File | Purpose | State |
|---|---|---|
| `docs/MASTER_PROMPT.md` | The owner's full specification. Authoritative requirement text. | Verbatim copy |
| `REQUIREMENTS_REGISTER.md` | Requirement IDs traced to the master prompt | First issue |
| `OPEN_QUESTIONS.md` | Unresolved decisions | First issue |
| `DECISION_REGISTER.md` | Decisions made, and by whom | First issue |
| `RISK_REGISTER.md` | Risks, evidence, mitigation | First issue |
| `COMPATIBILITY_MATRIX.md` | Nuke version and edition status | First issue, nothing tested |
| `MODEL_REGISTER.md` | Candidate models and what is verified about them | First issue, partial |
| `LICENCE_REGISTER.md` | Licences of models, runtimes and dependencies | First issue, partial |
| `TASK_BOARD.md` | Work items and status | First issue |
| `DEVELOPMENT_LOG.md` | Dated log of what was actually done | First issue |

Architecture proposal (awaiting approval): `ARCHITECTURE.md`, `docs/adr/`. Not yet created: `PROJECT_CHARTER.md`, `ROADMAP.md`, `TEST_PLAN.md`, `BENCHMARK_PLAN.md`, `CHANGELOG.md`, `RELEASE_CHECKLIST.md`.
