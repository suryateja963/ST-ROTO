"""Pure-Python tests of the Nuke convention helpers (no Nuke needed)."""
import random

from st_roto_nuke.convention import key_to_nuke, nuke_to_key, point_to_nuke, tangents_to_nuke


def test_point_flip():
    assert point_to_nuke(10, 0, 1080) == (10.0, 1080.0)
    assert point_to_nuke(10, 1080, 1080) == (10.0, 0.0)


def test_tangent_scale_and_direction():
    left, right = tangents_to_nuke(100, 100, 90, 100, 110, 104)
    assert left == (-20.0, -0.0) and right == (20.0, -8.0)        # x2, y flipped


def test_roundtrip_random():
    rnd = random.Random(3)
    for _ in range(200):
        p = [rnd.uniform(-500, 2500) for _ in range(6)]
        (c, lt, rt), = key_to_nuke([p], 1556.0)
        back = nuke_to_key(c, lt, rt, 1556.0)
        assert max(abs(a - b) for a, b in zip(p, back)) < 1e-9
