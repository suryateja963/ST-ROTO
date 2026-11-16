# ViTMatte-S as optional learned matting (D-032) — 2026-11-16

**Model.** hustvl/vitmatte-small-composition-1k, revision 6a58ad76, Apache-2.0 weights (card licence checked by `tools/models/download_models.py`), 25.8 M parameters. Trained on Composition-1k (Adobe DIM data, terms on request from Adobe): the caveat is shown in the node tooltip and in every status line of a ViTMatte render (`st_roto_ai.vitmatte.CAVEAT`). Off by default; optional download.

**Export** (`tools/models/export_vitmatte_onnx.py`): ONNX opset 17, dynamic size. ONNX vs PyTorch max |diff| 2e-6–9e-6 at 96×160, 256×256, 320×448, 512×704, 736×1280 (the exporter's "constant position size" warning concerns the pretraining grid; results stay exact at every size). ST-ROTO's numpy preprocessing equals VitMatteImageProcessor to 6e-8. Export registered (SHA-256) → verified before loading.

**Quality vs the model-free guided filter** (same known-alpha composites as probe_refine.py; SAD ×1000, lower is better; `result_vitmatte.json`):

| scene | hard shape | guided filter | ViTMatte-S |
|---|---|---|---|
| soft edge | 0.470 | **0.207** | 0.215 |
| shape 2 px off | 1.270 | 0.893 | **0.227** |
| motion blur 15 px | 1.493 | **0.518** | 0.675 |
| missed hair strands | 1.106 | 0.952 | **0.692** |

ViTMatte-S is much better when the shape is slightly off and on hair, slightly worse on motion blur, equal on soft edges → offered as a choice next to the guided filter (node knob *edges*), not as a replacement. Cost: ~0.2 s per crop on CPU; in Nuke on CUDA two HD frames incl. model load 2.1 s.

**Nuke test** `test_vitmatte_mattes`: ViTMatte EXR mattes, caveat in status, soft only around the edge, 0.5-threshold IoU vs truth 0.9999.
