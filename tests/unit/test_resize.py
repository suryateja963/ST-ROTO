"""st_roto_ai.resize must match torch's antialiased bilinear interpolate (skips where torch is absent, e.g. CI)."""
import numpy as np
import pytest

from st_roto_ai.resize import resize_aa, mask_to_model_input

torch = pytest.importorskip("torch")
F = pytest.importorskip("torch.nn.functional")


@pytest.mark.parametrize("shape,out", [((720, 1280), (1024, 1024)), ((1080, 1920), (1024, 1024)),
                                       ((333, 517), (1024, 1024)), ((2000, 3000), (256, 256))])
def test_matches_torch_antialias(shape, out):
    rng = np.random.default_rng(0)
    img = rng.random(shape).astype(np.float32)
    ref = F.interpolate(torch.from_numpy(img)[None, None], size=out, mode="bilinear",
                        align_corners=False, antialias=True)[0, 0].numpy()
    assert np.abs(resize_aa(img, *out) - ref).max() < 1e-5


def test_mask_prompt_matches_processor_threshold():
    rng = np.random.default_rng(1)
    m = np.zeros((720, 1280), bool)
    m[100:500, 300:900] = True
    m[rng.random(m.shape) > 0.995] = True                 # speckle to stress the edges
    ref = (F.interpolate(torch.from_numpy(m.astype(np.float32))[None, None], size=(1024, 1024), mode="bilinear",
                         align_corners=False, antialias=True) >= 0.5).float()[0, 0].numpy()
    assert (mask_to_model_input(m)[0, 0] != ref).sum() == 0
