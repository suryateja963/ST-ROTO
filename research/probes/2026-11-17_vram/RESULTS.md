# T-092 — GPU memory per model and memory-aware model choice (REQ-021), 2026-11-17

## Measurement

`measure_vram.py` runs a product Track (`track_once.py`, headless Nuke 17.1 NC, synthetic 1280x720 shot, 24 frames)
and polls `nvidia-smi` every 0.2 s. Windows reports no per-process GPU memory on this laptop (WDDM: "N/A"), so the
figure is the increase of the GPU's total used memory over the idle baseline just before Nuke starts (CUDA context
and ONNX Runtime pools included). RTX 5060 Laptop GPU, 8,151 MiB. `vram.json`.

| model | objects | peak increase | time (24 frames) |
|---|---|---|---|
| sam2.1-hiera-tiny | 1 | 3,730 MiB | 13.3 s |
| sam2.1-hiera-tiny | 2 | 3,720 MiB | 16.7 s |
| sam2.1-hiera-large | 1 | 6,793 MiB | 19.9 s |
| sam2.1-hiera-large | 2 | 6,792 MiB | 23.0 s |

The number of objects does not change the peak. The large model needs ~83 % of this 8 GB card: it does not fit if
other programs (or Nuke's own GPU work in the GUI) hold more than ~1 GB.

## Feature

- `st_roto.capabilities.MODEL_VRAM_MIB` = the measured peaks; `vram_need` adds 5 %; `plan_model` (pure) decides.
- Node model choice **auto (by free GPU memory)**: the large model if it fits in the GPU memory free now, else tiny,
  else tiny on the CPU (status says why).
- A model the artist chose is never swapped: if it does not fit, it runs on the CPU and the status says so (and that
  the tiny model would fit, when it would). Models already loaded by this Nuke count as fitting; if memory held by
  another cached model is what is missing, those sessions are released and the check repeated.
- Out of memory during a run (ONNX Runtime allocation failure): GPU sessions released, Track continues on the CPU
  from its last checkpoint (or from the start), Re-track runs again on the CPU; the status says so.
- The System report (T-091) now shows each model's need against the free memory.

## Tests

- `tests/unit/test_capabilities.py`: needs with margin, auto choice, never swapping a chosen model, loaded models.
- `tests/nuke` `test_memory_aware_model` (CUDA, this machine): 7,620 MiB free -> auto chose large (needs ~7,132)
  and tracked on CUDA; **fault injection** (ORT CUDA pool capped at 200 MiB): Track finished on the CPU ("the GPU ran
  out of memory; continued on the CPU from frame 0") and Re-track too ("re-tracked on the CPU").

## Not covered

- Out of memory in the MIDDLE of a run (resume from a mid-run checkpoint on the CPU): the injected failure happens
  at the first allocation; the resume path itself is tested by T-048 on the CPU.
- Other GPUs and resolutions (720p measured; SAM works at 1024x1024 internally, so plate size should matter little -
  not measured above 720p).
- GPU memory used by Nuke's own GPU nodes in the GUI is only seen as "less free memory" at the time of the check.
