"""Export ViTMatte-S (D-032, optional) to ONNX and validate it against PyTorch on a known-alpha composite.

Output: models/onnx/vitmatte-small-composition-1k/vitmatte.onnx (dynamic H, W; multiples of 32) + validate.json.
Input  'pixel_values' [1, 4, H, W] = (RGB/255 - 0.5)/0.5 and trimap/255 (0 bg, 0.5 unknown, 1 fg), zero-padded
right/bottom to multiples of 32 (exactly VitMatteImageProcessor); output 'alphas' [1, 1, H, W].
Run: .venv/Scripts/python.exe tools/models/export_vitmatte_onnx.py
"""
import json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["HF_HOME"] = os.path.join(ROOT, ".tools", "hf-home")
sys.path.insert(0, os.path.join(ROOT, "src"))
import numpy as np    # noqa: E402
import torch          # noqa: E402
from transformers import VitMatteForImageMatting, VitMatteImageProcessor   # noqa: E402

NAME = "vitmatte-small-composition-1k"
SRC = os.path.join(ROOT, "models", "weights", NAME)
OUT = os.path.join(ROOT, "models", "onnx", NAME)


class Wrap(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, pixel_values):
        return self.m(pixel_values=pixel_values).alphas


def test_case():
    """Composite with known alpha: textured disc + one-pixel 'hair' strands (alpha 0.6) on a textured background."""
    rng = np.random.default_rng(5)
    H, W = 300, 420
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    d = np.hypot(xx - 210, yy - 150) - 90
    A = np.clip(0.5 - d / 2.0, 0, 1)
    for i in range(30):
        ang = rng.uniform(0, 2 * np.pi)
        for t in np.linspace(0, 25, 80):
            x, y = int(210 + (90 + t) * np.cos(ang + 0.01 * t)), int(150 + (90 + t) * np.sin(ang + 0.01 * t))
            if 0 <= x < W and 0 <= y < H:
                A[y, x] = max(A[y, x], 0.6)
    F = np.clip([0.75, 0.3, 0.2] + 0.05 * rng.normal(0, 1, (H, W, 3)), 0, 1)
    B = np.clip([0.15, 0.4, 0.3] + 0.08 * rng.normal(0, 1, (H, W, 3)), 0, 1)
    img = (A[..., None] * F + (1 - A[..., None]) * B)
    fg, unknown = d < -6, np.abs(d) <= 6 | (d > 0) & (d < 30)
    trimap = np.where(fg, 255, np.where((d >= -6) & (d < 30), 128, 0)).astype(np.uint8)
    return (img * 255).round().astype(np.uint8), trimap, A


def main():
    os.makedirs(OUT, exist_ok=True)
    model = VitMatteForImageMatting.from_pretrained(SRC).eval()
    proc = VitMatteImageProcessor.from_pretrained(SRC)
    img, trimap, A = test_case()
    inp = proc(images=img, trimaps=trimap, return_tensors="pt")["pixel_values"]
    with torch.no_grad():
        ref = model(pixel_values=inp).alphas.numpy()
    path = os.path.join(OUT, "vitmatte.onnx")
    t0 = time.time()
    torch.onnx.export(Wrap(model), (inp,), path, input_names=["pixel_values"], output_names=["alphas"],
                      dynamic_axes={"pixel_values": {2: "h", 3: "w"}, "alphas": {2: "h", 3: "w"}}, opset_version=17,
                      dynamo=False)
    import onnxruntime as ort
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    got = sess.run(None, {"pixel_values": inp.numpy()})[0]
    # our own numpy preprocessing must equal the processor's
    from st_roto_ai.vitmatte import preprocess
    mine = preprocess(img.astype(np.float32) / 255.0, trimap.astype(np.float32) / 255.0)
    h, w = A.shape
    res = {"export_s": round(time.time() - t0, 1), "onnx_vs_torch_max_abs": float(np.abs(got - ref).max()),
           "numpy_preprocess_vs_processor_max_abs": float(np.abs(mine - inp.numpy()).max()),
           "padded_shape": list(inp.shape),
           "alpha_SAD_k_vs_truth": round(float(np.abs(ref[0, 0, :h, :w] - A).sum()) / 1000, 3),
           "trimap_only_SAD_k_vs_truth": round(float(np.abs((trimap / 255.0 >= 0.5) * 1.0 - A).sum()) / 1000, 3)}
    json.dump(res, open(os.path.join(OUT, "validate.json"), "w"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
