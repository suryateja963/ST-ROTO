# Matting / edge refinement — licence research (2026-11-16)

Purpose: decide how ST-ROTO produces soft alpha (hair, fine edges, motion blur) on top of SAM 2.1 masks. Owner rule: licence research first; no model download without approval (§15).

Evidence levels: **V-text** = licence text read; **V-card** = model card / official README; **S** = secondary source.

## Candidates

| Model | What it does | Code / weights licence | Training data | Fits ST-ROTO? | Evidence |
|---|---|---|---|---|---|
| ViTMatte-S / -B (hustvl) | Trimap → alpha, single image. Trimap can come from the SAM mask (erode/dilate band) → object-targeted | Code MIT, HF weights Apache-2.0 | Composition-1k (Adobe Deep Image Matting dataset). Dataset obtained on request from Adobe; terms not public; folder named "Adobe-licensed images"; reported non-commercial by third parties | Best technical fit (targeted, 25.8 M params small) | V-card weights; S dataset terms (agreement text not obtainable without request) |
| BiRefNet-matting / BiRefNet_HR-matting (2048²) | Salient-object matting, no prompt (not object-targeted; would need a crop around the tracked object) | MIT (repository and HF cards) | P3M-10k, TR-humans, AM-2k, AIM-500, Human-2k, Distinctions-646, HIM2K, PPM-100 (README Model Zoo, "general matting" row) — these are research datasets, several stated as non-commercial research use | Usable as crop-and-matte; large (≈220 M), heavy on 8 GB at 2048² | V-card licence, V-card (README) datasets; dataset terms S |
| ZIM (NAVER, ICCV 2025) | Zero-shot promptable matting (SAM-like prompts → matte) | **CC BY-NC 4.0** | SA1B-Matte (derived from SA-1B) | Ideal function, licence blocks commercial use | **V-text** (LICENSE file) |
| MatAnyone / MatAnyone 2 | Target-assigned video matting | S-Lab 1.0, non-commercial | — | Research-only | V-text (2026-11-15) |
| VideoMaMa (CVPR 2026) | SAM-mask → video matte, diffusion prior | Non-commercial (CC BY-NC / Stability Community) | — | Research-only | S |
| RVM | Human video matting | GPL-3.0 | — | Blocked by Apache-2.0 project licence | V-card |
| BackgroundMattingV2 | Matting with clean plate | MIT | — | Locked-off shots only | S |

## Findings

1. **No candidate is clean on both licence and training data.** Every permissive-weight matting model found (ViTMatte, BiRefNet-matting) is trained on research datasets whose terms are, or are reported to be, non-commercial. Whether such terms bind the trained weights is a legal question (R-11), not one engineering can settle.
2. **The function ST-ROTO needs most (object-targeted soft edges) is available permissively in code, not in weights**: ViTMatte's architecture is MIT/Apache; the problem is only the training data.
3. **Model-free refinement needs no licence decision** and gives a real first step:
   - soft alpha from SAM 2.1's own mask logits (sigmoid of the upsampled logits; this is what "SAM2-Matte"-style approaches start from), restricted to a band around the edge;
   - edge-aware refinement with a guided filter on the plate (He et al. 2010; algorithm, no weights);
   - motion blur from the shape's animation using Nuke's native Roto motion blur (the shapes are real animated Roto splines), which is physically consistent with the tracked motion.
   It cannot recover individual hair strands; that needs a learned matting model.

## Proposed path (owner decision OQ-22)

- **Now (no approval needed):** model-free soft alpha + guided-filter refinement written as a separate matte channel, Roto motion blur exposed on the ST_Roto node. Same pipeline shape a model will plug into later (mask → trimap band → alpha).
- **Then, owner chooses one:**
  - (a) ViTMatte-S as an *optional, separately downloaded* refinement model, marked "training-data terms unverified" in the model registry, off by default; or
  - (b) BiRefNet_HR-matting likewise optional (crop around the tracked object); or
  - (c) no learned matting in 1.0 until a model with clean training data exists (or ST-ROTO trains one on permissively licensed / synthetic data — large effort).
  - Recommendation: (a) — smallest, object-targeted via trimap, MIT/Apache code and weights; ship it as an optional download with the training-data caveat stated to the user, and keep (c)'s model-free path as the default.

## Sources

- ViTMatte: https://github.com/hustvl/ViTMatte ; https://huggingface.co/hustvl/vitmatte-small-composition-1k
- Deep Image Matting dataset access: https://sites.google.com/view/deepimagematting ; https://mmagic.readthedocs.io/en/stable/dataset_zoo/comp1k.html
- BiRefNet: https://github.com/ZhengPeng7/BiRefNet ; https://huggingface.co/ZhengPeng7/BiRefNet_HR-matting ; https://huggingface.co/ZhengPeng7/BiRefNet-matting
- ZIM licence: https://raw.githubusercontent.com/naver-ai/ZIM/main/LICENSE ; paper https://arxiv.org/abs/2411.00626
- VideoMaMa: https://arxiv.org/abs/2601.14255 ; OpenMatte table: https://github.com/hamdyelshiwy/openmatte
