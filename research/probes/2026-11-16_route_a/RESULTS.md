# Route A: TorchScript → .cat → Nuke Inference node (T-011a) — 2026-11-16

**Setup.** Our own tiny model (hand-set weights, Apache-2.0, nothing downloaded): luminance → 5×5 box blur → sigmoid soft key, 3 channels in, 1 out. TorchScript saved with **torch 2.7.1** (= Nuke 17.1's libtorch, T-038) from a project-local CPU venv (`.tools/torch27-venv`). Probe: `make_model.py`, `probe_route_a.py`, results `result_cpu.json`, `result_gpu.json`.

**Findings (Nuke 17.1v3 Non-commercial).**
- CatFileCreator **is available in Non-commercial**, but it writes **`.catnc`** files (a `.cat` path is rejected: "The .catnc file path you have entered does not exist"; the `catFile` knob then becomes read-only). Created in 0.22 s via `nuke.execute(node, FrameRanges([1]))` (what its *create* button runs); the `createCatFile` knob is an empty Script_Knob.
- Inference node with the `.catnc`, input read raw (no colour conversion): **CPU output bit-identical to PyTorch** (max |diff| 0.0); **GPU** (`--gpu`) max |diff| 1.2e-7.
- Time per 1280×720 frame: CPU 0.027–0.035 s; GPU 0.016–0.019 s after a 2.4 s first frame (GPU initialisation).

**What route A can and cannot do.** It runs a model inside Nuke's own C++ Inference node (no Python at render time, renders on the farm like any node). It is per-frame and stateless with fixed channel I/O, so it suits per-frame models (matting/refinement such as a trimap-guided matting model, edge refinement) but **not** SAM 2.1 video tracking (memory across frames, prompts, object pointers) — that stays on route C (ONNX Runtime in Nuke's Python, ADR-0001/0002).

**Licence notes.** `.catnc` is the Non-commercial format; commercial editions use `.cat` (whether they load `.catnc` was not tested: no commercial licence here). The Foundry EULA clause on Non-commercial (no commercial tools/plug-ins, R-23) applies to anything produced with it; ST-ROTO would ship TorchScript files and create the `.cat` on the user's machine.
