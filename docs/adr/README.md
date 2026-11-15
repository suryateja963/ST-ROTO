# Architecture Decision Records

All **Accepted** by the project owner on 2026-11-15 (D-026). See `ARCHITECTURE.md`.

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](ADR-0001.md) | In-process inference with ONNX Runtime inside Nuke's Python | Accepted |
| [ADR-0002](ADR-0002.md) | Models as ONNX graphs + numpy orchestration (no PyTorch at runtime) | Accepted |
| [ADR-0003](ADR-0003.md) | Host adapter per Nuke API generation, with a node-budget guard | Accepted |
| [ADR-0004](ADR-0004.md) | Domain model: objects with multiple representations and provenance | Accepted |
| [ADR-0005](ADR-0005.md) | Storage: SQLite project database + content-addressed cache | Accepted |
| [ADR-0006](ADR-0006.md) | Every edit is an operation (command bus + operation log) | Accepted |
| [ADR-0007](ADR-0007.md) | Hardware-aware model routing with measured VRAM tables | Accepted |
| [ADR-0008](ADR-0008.md) | Geometry engine independent of Nuke; Nuke conventions in the adapter | Accepted |
| [ADR-0009](ADR-0009.md) | Background jobs with a single GPU arbiter | Accepted |
| [ADR-0010](ADR-0010.md) | Explicit, recorded colour transform for model input (OCIO) | Accepted |
