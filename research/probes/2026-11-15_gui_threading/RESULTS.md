# Probe results — AI work on a worker thread inside the interactive Nuke GUI (R-37, ADR-0009)

Date 2026-11-15 · Nuke 17.1v3 **Non-commercial, GUI mode** · RTX 5060 8 GB · onnxruntime-gpu 1.26.0 · `probe_gui_threading.py` (`result.json`).

| Phase | Main-thread 16 ms timer: mean gap | p99 | max | gaps > 100 ms |
|---|---|---|---|---|
| Idle baseline (2 s) | 16.0 ms | 19.1 | 28.4 | 0 |
| **SAM 2.1 tiny encoder ×40 on a worker thread (CUDA, 60.7 ms each)** | **16.0 ms** | **16.8** | **17.7** | **0** |
| Same encoder ×10 on the main thread (for contrast) | 59.2 ms | 60.0 | 60.1 | 0 (but every frame blocked ~60 ms) |
| After / during cancellation test | 16.1 ms | 17.3 | 40.0 | 0 |

- ORT CUDA sessions run correctly on a non-main thread inside the Nuke GUI. **The GUI stays at full rate.**
- `nuke.executeInMainThreadWithResult` from the worker ran on the main thread (`True`) and created a native Roto shape (3 points).
- Cooperative cancellation (flag checked between runs) stopped the job **38.8 ms** after the request.

**Conclusion:** ADR-0009 (worker threads + main-thread application of results) works in Nuke 17.1. Not yet tested: Nuke 13–16 (PySide2), several concurrent jobs, very long jobs, GPU contention with Nuke's own GPU nodes.
