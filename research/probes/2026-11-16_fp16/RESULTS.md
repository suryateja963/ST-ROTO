# Probe results — fp16 memory attention for SAM 2.1 tracking (T-062)

Nuke 17.1v3 NC, headless, CUDA, RTX 5060 8 GB · synthetic 48-frame shot · two full runs per variant in one process.
Peak = whole-GPU memory (nvidia-smi, 100 ms sampling). Conversion: `tools/models/convert_fp16.py` (onnxconverter-common 1.16 + two fixes below).

| Model | memory attention | IoU vs PyTorch (min / mean) | IoU vs GT (mean / min) | Tracking step | Peak GPU |
|---|---|---|---|---|---|
| tiny | fp32 | 0.99544 / 0.99898 | 0.9951 / 0.9862 | 148 ms | 5.06 GB |
| tiny | **fp16** | 0.99544 / 0.99898 | 0.9951 / 0.9862 | **96 ms** | **3.92 GB** |
| tiny | fp16, Softmax/LayerNorm/… kept fp32 | 0.99325 / 0.99878 | 0.9951 / 0.9862 | 152 ms | 4.93 GB |
| large | fp32 | 0.99069 / 0.99899 | 0.9872 / 0.5727 | 192 ms | 7.77 GB |
| large | **fp16** | 0.99069 / 0.99899 | 0.9872 / 0.5727 | **98 ms** | 7.00 GB |

Raw-logit check (are the variants really different?): tiny fp32 vs fp16 max |Δlogit| 0.146 (mean per-frame max 0.06); frame 0 identical (no memory attention there); **7 of 48×256×256 low-res pixels change sign** (≤ 2 per frame). Large: max |Δlogit| 0.047, **0 sign changes**.

**Conversion pitfalls (fixed in the tool):**
1. Stale fp32 `value_info` → "Type (tensor(float16)) … does not match expected type (tensor(float))". Removed before converting.
2. The model's own explicit Cast-to-fp32 nodes (RoPE `q.float()`) survive conversion and clash with the fp16 graph. Retargeted to fp16 (32 casts tiny), except boundary casts and casts feeding fp32-kept ops.

**Decision D-029 (technical, delegated):** fp16 memory attention is the runtime default when the file exists; fp32 stays selectable (`memattn_file`). Evidence is one synthetic shot and must be re-checked on real footage (benchmark plan).

**Regression test added:** `tests/nuke/run_nuke_tests.py::test_repeated_tracking_stable`. Three 48-frame runs in one session: 10.5 / 8.3 / 8.3 s, peak 3.9 GB (limits: run 3 ≤ 1.3 × run 2, peak ≤ 6.5 GB). Passes.
