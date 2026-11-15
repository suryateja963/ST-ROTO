# Several objects per tracking pass (T-067) — results, 2026-11-16

## Design (from upstream, not invented)

transformers 5.23 `Sam2VideoModel.forward` loops over objects and runs `_run_single_frame_inference(batch_size=1)` per object ("We avoid batched inference here because per-object inputs (clicks/masks) can differ across objects"); only image features are shared, memory encoding is batched (per-object results unchanged). `st_roto_ai.sam2.Sam2MultiVideo` does the same: one encoder call per frame, one `Sam2Video` state per object. Per-object positions/sequence length equal a single-object run, so results must be **identical** to tracking each object alone.

## Exactness

- CPU, unit tests (`tests/unit/test_multi_object.py`): 2 objects (target from frame 0, distractor disc from frame 2), 8 frames: keys, per-frame reports and provenance **identical** to single-object runs. Same for `retrack_objects` (two shapes drawn on frames 3 and 5, forward + reverse).
- GPU (CUDA, inside Nuke, this probe): max point difference single vs multi **0.0 px** on all 48 frames, both objects, tiny and large.

## Speed (48 frames, 2 objects, RTX 5060 Laptop, Nuke 17.1 NC, frames decoded beforehand)

| Model | 2 single passes | 1 multi pass | Speed-up |
|---|---|---|---|
| tiny  | 27.4 / 27.2 s | 20.3 / 19.9 s | 1.35 / 1.37 |
| large | 47.5 / 47.2 s | 30.3 / 30.3 s | 1.57 / 1.56 |

Not included: Nuke pixel render (≈0.09 s/frame HD, measured T-040), also done once per frame instead of once per object in the product.

**Own bug found by profiling.** First measurement gave 1.13 (tiny): the per-object RAM budget of the spilled tracker state was `24 // n_objects` = 12, but each step reads the previous 15 frames, so 5,208 state reloads from disk in one pass. Budget now never below 16 per object (≈2 MB/frame/object). (The first probe run also forgot to pass the model to the tracker, so "large" ran tiny; fixed before the numbers above.)

Profile of the remaining multi pass (tiny): ONNX Runtime 10.3 s of 20.2 s; contour tracing 3.3 s (per object), preprocessing resize 1.5 s + colour transform 1.6 s (per frame). CPU post-processing is a further optimisation target.

Files: `probe_multi_speed.py`, `result_*.json`, `log_*.txt`.

## Product behaviour (Nuke tests)

- `test_multi_object_track`: prompts for 2 objects on one node (frame 0 and frame 4) → one Track → 2 objects; IoU vs analytic truth target 0.994–0.996, disc 0.983–0.995; one undo removes both, redo restores; **Re-track all** fills the disc's frames 0–3 in reverse (IoU ≥ 0.983).
- Pressing Track again with the same prompts no longer creates duplicate objects: already-tracked objects are skipped with a status message (`test_prompts_preview_sync_protection`).
