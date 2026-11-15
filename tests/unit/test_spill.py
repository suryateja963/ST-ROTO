"""SpillDict bounds RAM and returns identical data; tracker results identical with tiny RAM budget (needs models)."""
import json
import os

import numpy as np
import pytest

from st_roto_ai.spill import SpillDict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_spill_roundtrip_and_bound():
    d = SpillDict(max_in_ram=3)
    data = {f: {"a": np.full((4, 4), f, np.float32), "b": np.arange(f + 1)} for f in range(10)}
    for f, v in data.items():
        d[f] = v
        assert d.in_ram <= 3
    assert len(d) == 10 and d.spills >= 7 and 0 in d and 11 not in d
    for f in (0, 9, 4, 1):
        v = d.get(f)
        assert np.array_equal(v["a"], data[f]["a"]) and np.array_equal(v["b"], data[f]["b"])
        assert d.in_ram <= 3
    assert d.get(42) is None
    d.close()
    assert not os.path.exists(d.dir)


VID = os.path.join(ROOT, "models", "onnx", "sam2.1-hiera-tiny", "video")
FR = os.path.join(ROOT, "research", "probes", "2026-11-15_video", "frames")


@pytest.mark.skipif(not (os.path.exists(os.path.join(VID, "vencoder.onnx")) and os.path.exists(os.path.join(FR, "meta.json"))),
                    reason="exported model / synthetic frames not present")
def test_tracker_identical_with_tiny_ram_budget():
    cv2 = pytest.importorskip("cv2")
    from st_roto_ai.sam2 import Sam2Video
    meta = json.load(open(os.path.join(FR, "meta.json")))
    frames = [cv2.cvtColor(cv2.imread(os.path.join(FR, "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
              for i in range(9)]
    outs = {}
    for budget in (1000, 2):
        t = Sam2Video(VID, device="cpu", num_total_frames=9, max_frames_in_ram=budget)
        res = []
        for i, rgb in enumerate(frames):
            e = t.encode(rgb)
            res.append((t.add_points(0, e, [tuple(meta["click_xy"])], [1]) if i == 0 else t.track(i, e))["low_res"])
            assert t.noncond.in_ram <= budget
        outs[budget] = res
        if budget == 2:
            assert t.noncond.loads > 0          # memory reads really came from disk
        t.close()
    assert all(np.array_equal(a, b) for a, b in zip(outs[1000], outs[2]))
