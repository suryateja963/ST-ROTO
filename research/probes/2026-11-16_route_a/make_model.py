"""T-011a route A: a tiny model of our own (hand-set weights, Apache-2.0, nothing downloaded) as TorchScript made
with torch 2.7.1 (= Nuke 17.1's libtorch, T-038), plus a reference input/output pair for an exactness check.

Model: 'soft key' - luminance (Rec.709 weights) -> 5x5 box blur -> sigmoid((x - 0.5) * 12) -> 1-channel matte.
Run with the project's torch-2.7 venv:  .tools/torch27-venv/Scripts/python.exe research/probes/2026-11-16_route_a/make_model.py
"""
import os

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))


class SoftKey(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.luma = torch.nn.Conv2d(3, 1, 1, bias=False)
        self.blur = torch.nn.Conv2d(1, 1, 5, padding=2, bias=False)
        with torch.no_grad():
            self.luma.weight[:] = torch.tensor([0.2126, 0.7152, 0.0722]).view(1, 3, 1, 1)
            self.blur.weight[:] = 1.0 / 25.0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid((self.blur(self.luma(x)) - 0.5) * 12.0)


m = SoftKey().eval()
ts = torch.jit.script(m)
ts.save(os.path.join(HERE, "softkey.pt"))
rng = np.random.default_rng(0)
H, W = 720, 1280
yy, xx = np.mgrid[0:H, 0:W]
img = np.stack([0.5 + 0.5 * np.sin(xx / 37.0), 0.5 + 0.5 * np.cos(yy / 23.0), rng.random((H, W))], 0).astype(np.float32)
with torch.no_grad():
    out = ts(torch.from_numpy(img)[None])[0, 0].numpy()
np.savez(os.path.join(HERE, "reference.npz"), input=img, output=out)
print("torch", torch.__version__, "saved softkey.pt and reference.npz", out.shape, float(out.min()), float(out.max()))
