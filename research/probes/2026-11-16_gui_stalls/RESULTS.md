# Probe results — GUI stalls and GPU memory growth during ST_Roto tracking (R-40)

Nuke 17.1v3 Non-commercial, GUI · RTX 5060 Laptop 8 GB · SAM 2.1 tiny via st_roto_ai · synthetic 48-frame shot.
Instrumented with `probe_gui_stalls.py`: 16 ms UI timer plus timestamps of every adapter call. Each UI gap > 100 ms is attributed to the calls overlapping it. Raw: `result_*.json`.

## 1. Where the stalls come from

| Run | UI stalls > 100 ms | Overlapping call |
|---|---|---|
| baseline | none | – |
| rep1 / rep2 / rep3 | 931 / 1279 / 1073 ms | `Sam2Video.__init__` (ONNX Runtime session creation, worker thread) |

Creating ORT sessions holds Python's GIL; the main thread cannot run. Per-frame inference (worker) and main-thread renders (≤ 92 ms) caused no stalls.

**Fix 1 (kept): process-wide session cache** (`st_roto_ai.runtime.open_session`). Session creation on later Track presses: ~2 ms instead of ~3 s. The first press in a Nuke session can still stall (0.2–1.6 s observed). Mitigation: load models at a time the artist chooses (T-061).

## 2. Repeated tracking got slower (found while verifying fix 1)

Three Track presses in one Nuke session, ORT defaults: 20.0 s, 15.2 s, **35.9 s**. Per-call timing showed the encoder ~5× slower in run 3. Hardware log: GPU memory 5.3 → 7.4 → 7.8 GB of 8.15 GB, not thermal (≤ 75 °C). ORT's CUDA memory pool keeps growing. Memory attention allocates ~470 MB attention buffers (4096 queries × up to ~28.7 k memory tokens × fp32) of changing size.

| Configuration | Result |
|---|---|
| ORT defaults | works, memory ratchets to 7.8 GB, 3rd run 2.4× slower |
| `cudnn_conv_algo_search=HEURISTIC` + `kSameAsRequested` | **rejected**: tracking steps ~15× slower; all runs failed after 17 frames |
| `arena_extend_strategy=kSameAsRequested` only | **rejected**: fragmentation, `BFCArena … Failed to allocate 470810624` in memory attention; all runs failed after 17 frames |
| **ORT defaults + arena shrinkage after each memory-attention run** (`memory.enable_memory_arena_shrinkage`) | **kept**: 22.5 / 16.3 / 16.4 s; memory rises and falls (3.3–6.4 GB, sampled peak 7.65 GB); only stall: 267 ms at first session creation |

Cost of shrinkage: tracking step ~145 ms vs ~108 ms (+35%). Peak memory is still close to 8 GB (R-34); fp16 memory attention or chunked attention would reduce it (not done).

## 3. Tests after the fixes

Unit 38/38 · headless Nuke 2/2 · GUI slice: 48 frames in 21.2 s, passes (single press, so it includes the first-press stall: max gap 1.6 s).
