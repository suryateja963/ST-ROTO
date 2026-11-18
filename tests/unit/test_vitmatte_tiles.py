"""ViTMatte-S tiling (found on real 4K plates: one pass over a close-up's edge zone needed a 10.5 GB GPU buffer).
A stand-in model checks the tiling logic without ONNX Runtime; real-model agreement is measured in
research/probes/2026-11-18_real_greenscreen (result_vitmatte_tile_study.json)."""
import numpy as np

from st_roto_nuke import mattes as mt


class FakeVM(object):
    """alpha = a smooth function of the image (no context dependence), trimap knowns kept - like ViTMatte's output."""
    def __init__(self):
        self.calls = []

    def alpha(self, rgb, tri):
        self.calls.append(tri.shape)
        a = rgb[..., 0].astype(np.float32).copy()
        a[tri >= 1.0] = 1.0
        a[tri <= 0.0] = 0.0
        return a


def scene(h, w):
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.stack([(np.sin(xx / 37.0) + np.cos(yy / 23.0) + 2) / 4.0] * 3, -1).astype(np.float32)
    tri = np.zeros((h, w), np.float32)
    tri[:, : w // 2] = 1.0
    tri[:, w // 2 - 40: w // 2 + 40] = 0.5                  # a vertical unknown band
    return rgb, tri


def test_small_region_is_one_pass_exactly():
    rgb, tri = scene(600, 900)
    vm = FakeVM()
    a = mt._vitmatte_tiled(vm, rgb, tri, tile=1024, overlap=256)
    assert vm.calls == [(600, 900)]
    assert np.array_equal(a, FakeVM().alpha(rgb, tri))


def test_large_region_tiles_blend_seamlessly_and_skip_empty_tiles():
    rgb, tri = scene(2200, 2600)
    vm = FakeVM()
    a = mt._vitmatte_tiled(vm, rgb, tri, tile=1024, overlap=256)
    ref = FakeVM().alpha(rgb, tri)
    assert a.shape == tri.shape and np.abs(a - ref).max() < 1e-5      # context-free model: tiling changes nothing
    assert all(s[0] <= 1024 and s[1] <= 1024 for s in vm.calls)       # never more than one tile per call
    assert len(vm.calls) < 16                                         # tiles without unknown pixels are skipped
    assert np.all(a[tri >= 1.0] == 1.0) and np.all(a[tri <= 0.0] == 0.0)
