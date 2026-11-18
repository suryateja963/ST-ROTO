"""Cache SA-V thumbnails (st_roto.scenecut.thumbnail) for fast threshold studies -> thumbs_sav.npz (git-ignored
data stays local: the file holds 64x36 thumbnails derived from CC BY 4.0 frames; not committed)."""
import glob, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from st_roto import scenecut
S = os.path.join(ROOT, "data", "benchmarks", "sa-v", "raw", "frames")
out = {}
for d in sorted(glob.glob(os.path.join(S, "*"))):
    fs = sorted(glob.glob(os.path.join(d, "*.jpg")))
    if len(fs) >= 8:
        out[os.path.basename(d)] = np.stack([scenecut.thumbnail(np.asarray(Image.open(f).convert("RGB"))) for f in fs])
np.savez_compressed(os.path.join(ROOT, "tmp", "thumbs_sav.npz"), **out); print(len(out))
