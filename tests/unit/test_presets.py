"""Settings presets (T-111) and review overlay helpers (views.review_levels / colour_runs)."""
import json
import os

import numpy as np
import pytest

from st_roto import model as m
from st_roto import presets, views
from st_roto.commands import CommandBus
from st_roto.geometry import mask_to_points
from st_roto.store import ProjectStore


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    u, s = tmp_path / "user", tmp_path / "studio"
    s.mkdir()
    monkeypatch.setenv("ST_ROTO_USER_PRESET_DIR", str(u))
    monkeypatch.setenv("ST_ROTO_PRESET_DIR", str(s))
    return u, s


def test_builtins_are_valid():
    for name, data in presets.BUILTIN.items():
        clean, problems = presets.validate(data["settings"])
        assert problems == [] and clean, name


def test_save_list_load_delete_and_priority(dirs):
    u, s = dirs
    names = [e["name"] for e in presets.list_presets()]
    assert "Quick look" in names and not os.path.exists(str(u))       # user folder only made when saving
    p = presets.save("My look", {"stroto_model": "sam2.1-hiera-large", "stroto_band": 4, "stroto_edge_blur": 2,
                                 "stroto_stereo": True}, "mine")
    assert os.path.exists(p)
    got = presets.load("My look")
    assert got["origin"] == "user" and got["settings"]["stroto_edge_blur"] == 2.0 and got["problems"] == []
    # a studio preset with the same name as a built-in wins over it; a user one wins over both
    with open(str(s / "q.json"), "w") as fh:
        json.dump({"format": presets.FORMAT, "version": 1, "name": "Quick look", "settings": {"stroto_band": 9}}, fh)
    assert presets.load("Quick look")["origin"] == "studio"
    presets.save("Quick look", {"stroto_band": 2})
    assert presets.load("Quick look")["settings"] == {"stroto_band": 2}
    presets.delete("Quick look")
    assert presets.load("Quick look")["origin"] == "studio"
    with pytest.raises(ValueError, match="only your own"):
        presets.delete("Quick look")
    with pytest.raises(ValueError, match="only your own"):
        presets.delete("Stereo")
    with pytest.raises(KeyError):
        presets.load("nope")


def test_validation_rejects_shot_data_and_bad_types(dirs):
    clean, problems = presets.validate({"stroto_points": "[]", "stroto_band": "4", "stroto_soft": 1,
                                        "stroto_edges": "hard"})
    assert clean == {"stroto_edges": "hard"} and len(problems) == 3
    with pytest.raises(ValueError):
        presets.save("x", {"stroto_project": "a.stroto"})
    with pytest.raises(ValueError, match="preset name"):
        presets.save("../evil", {"stroto_band": 1})


def test_broken_and_newer_files_are_reported(dirs):
    u, s = dirs
    (s / "bad.json").write_text("{not json")
    (s / "new.json").write_text(json.dumps({"format": presets.FORMAT, "version": 99, "name": "new", "settings": {}}))
    entries = {e["name"]: e for e in presets.list_presets()}
    assert "error" in entries["bad"] and "newer" in entries["new"]["error"]
    with pytest.raises(ValueError):
        presets.load("new")


def test_colour_runs_are_constant_on_whole_frames():
    C = {"lost": (1, 0, 1, 1), "check": (1, 0.85, 0, 1)}
    runs = views.colour_runs({3: "check", 4: "check", 7: "lost"}, 0, 9, C)
    frames = [f for f, _ in runs]
    assert frames == sorted(set(frames))                                  # no duplicate keys
    def at(f):                                                            # linear interpolation, as Nuke does
        ks = dict(runs)
        lo = max(k for k in ks if k <= f); hi = min(k for k in ks if k >= f)
        if lo == hi:
            return ks[lo]
        t = (f - lo) / float(hi - lo)
        return tuple(a + (b - a) * t for a, b in zip(ks[lo], ks[hi]))
    assert all(at(f) == (0, 0, 0, 0) for f in (0, 1, 2, 5, 6, 8, 9))
    assert at(3) == C["check"] and at(4) == C["check"] and at(7) == C["lost"]


def test_review_levels_worst_per_frame(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot", "width": 80, "height": 60}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "o"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "Os", "object_id": "O", "name": "o", "point_count": 12}},
                actor=m.ACTOR_AI)
    yy, xx = np.mgrid[0:60, 0:80] + 0.5
    for f in range(6):
        if f != 3:
            bus.execute({"op": "set_key", "shape_id": "Os", "frame": f,
                         "points": mask_to_points(10 - np.hypot(xx - 30 - f, yy - 30), count=12)}, actor=m.ACTOR_AI)
        bus.execute({"op": "set_report", "shape_id": "Os", "frame": f, "object_score": -5.0 if f == 3 else 5.0,
                     "iou_pred": 0.95})
    bus.execute({"op": "set_channel_report", "object_id": "O", "frame": 3, "data": {"crypto_iou": 0.2}})
    lv = views.review_levels(s, "S")["O"]
    assert lv[3][0] == "lost" and "Cryptomatte" in lv[3][1] and "lost" in lv[3][1]
