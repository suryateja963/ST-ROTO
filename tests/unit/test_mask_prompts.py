"""Masks as prompts (T-100, REQ-060): rough shapes / mattes / mask files -> box + interior clicks."""
import numpy as np
import pytest

pytest.importorskip("cv2")
from st_roto import prompts      # noqa: E402

H, W = 60, 100


def test_box_and_most_interior_point():
    m = np.zeros((H, W), bool); m[10:50, 20:60] = True            # 40 x 40 square
    p = prompts.from_mask(m)
    assert p["box"] == (20.0, 10.0, 60.0, 50.0)
    (x, y), = p["points"]
    assert abs(x - 40) <= 1.5 and abs(y - 30) <= 1.5


def test_pieces_get_one_click_each_largest_first_tiny_ignored():
    m = np.zeros((H, W), bool)
    m[5:45, 5:35] = True                                            # big
    m[10:30, 60:80] = True                                          # medium
    m[55:56, 95:96] = True                                          # 1 px speck (< 2 %)
    p = prompts.from_mask(m)
    assert len(p["points"]) == 2 and p["points"][0][0] < 40 and p["points"][1][0] > 55
    assert p["box"] == (5.0, 5.0, 96.0, 56.0)                       # the box still covers everything


def test_set_from_mask_replaces_the_objects_prompts_only():
    m = np.zeros((H, W), bool); m[10:50, 20:60] = True
    t = prompts.add("", 3, 1.0, 1.0, prompts.INCLUDE, obj="other")
    t = prompts.add(t, 7, 5.0, 5.0, prompts.EXCLUDE, obj="hero")
    t = prompts.set_from_mask(t, 7, m, obj="hero")
    groups = {g["name"]: g for g in prompts.objects_for_tracker(t, "hero")}
    assert groups["hero"]["labels"] == [prompts.BOX_TL, prompts.BOX_BR, prompts.INCLUDE]
    assert groups["hero"]["frame"] == 7 and groups["other"]["frame"] == 3
    with pytest.raises(ValueError, match="empty"):
        prompts.from_mask(np.zeros((H, W), bool))
