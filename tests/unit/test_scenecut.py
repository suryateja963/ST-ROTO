"""T-123 scene-cut detection on synthetic sequences (real footage: research/probes/2026-11-18_scenecut)."""
import numpy as np
import pytest

from st_roto import scenecut as sc


def scene(seed, n, h=90, w=160, pan=2, palette=None):
    """A textured scene (smooth colour blobs) panning right by `pan` px per frame, plus a moving square."""
    rng = np.random.default_rng(seed)
    big = rng.random((h // 6 + 2, (w + pan * n) // 6 + 2, 3)).astype(np.float32)
    big = np.kron(big, np.ones((6, 6, 1), np.float32))[:h, :w + pan * n]
    if palette is not None:
        big = big * np.asarray(palette, np.float32)
    out = []
    for i in range(n):
        f = big[:, i * pan:i * pan + w].copy()
        x = 10 + 5 * i
        f[30:50, x % (w - 20):x % (w - 20) + 20] = (1.0, 0.9, 0.1)
        out.append(f)
    return out


def detect(frames):
    return sc.detect([sc.thumbnail(f) for f in frames])


def test_hard_cut_found_exactly():
    seq = scene(1, 10) + scene(2, 10, palette=(0.3, 0.6, 1.0))
    cuts, rep = detect(seq)
    assert cuts == [10]
    assert [r["frame"] for r in rep if r["cut"]] == [10]


def test_fast_pan_is_not_a_cut():
    assert detect(scene(3, 24, pan=12))[0] == []


def test_flash_and_one_frame_glitch_are_not_cuts():
    seq = scene(4, 16)
    white = np.ones_like(seq[0])
    cuts, rep = detect(seq[:8] + [white] + seq[8:])
    assert cuts == [] and any("flash" in r["why"] for r in rep)
    other = scene(5, 1, palette=(1.0, 0.2, 0.2))[0]
    assert detect(seq[:8] + [other] + seq[8:])[0] == []


def test_two_cuts_and_frame_numbers():
    seq = scene(6, 6) + scene(7, 6, palette=(0.2, 1.0, 0.4)) + scene(8, 6, palette=(1.0, 0.4, 0.8))
    cuts, _ = sc.detect([sc.thumbnail(f) for f in seq], frames=range(101, 119))
    assert cuts == [107, 113]


def test_uint8_and_linear_input_and_thumbnail_size():
    f = scene(9, 1, h=1080, w=1920)[0]
    t = sc.thumbnail(f)
    assert t.shape == (36, 64, 3) and 0.0 <= t.min() and t.max() <= 1.0
    t8 = sc.thumbnail((np.clip(f, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8))
    assert np.abs(t - t8).mean() < 0.01                      # same picture either way


def test_segment_and_parse():
    assert sc.segment(5, [10, 20], 0, 30) == (0, 9)
    assert sc.segment(10, [10, 20], 0, 30) == (10, 19)
    assert sc.segment(25, [10, 20], 0, 30) == (20, 30)
    assert sc.segment(5, [], 0, 30) == (0, 30)
    assert sc.parse(" 20, 10;10 ") == [10, 20] and sc.parse("") == []
    with pytest.raises(ValueError):
        sc.parse("ten")
    assert sc.format_cuts([20, 10, 10]) == "10, 20"
