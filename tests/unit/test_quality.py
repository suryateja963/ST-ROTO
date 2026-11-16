"""Review flags (st_roto.quality), key_reports op and its undo / subtree behaviour, schema v3."""
from st_roto import model as m, quality, views
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore


def test_review_rules():
    reports = [{"frame": 14, "object_score": 1.09, "iou_pred": 0.95},
               {"frame": 15, "object_score": 0.96, "iou_pred": 0.93},
               {"frame": 16, "object_score": -0.07, "iou_pred": 0.5},
               {"frame": 17, "object_score": -3.0, "iou_pred": 0.4},
               {"frame": 18, "object_score": 4.0, "iou_pred": 0.6}]
    raw = quality.review_frames(reports, keyed_frames=[14, 15, 18])
    flags = {f: (lvl, why) for f, lvl, why in raw}
    assert 14 not in flags
    assert flags[15][0] == quality.CHECK and "uncertain" in flags[15][1]
    assert flags[16][0] == quality.LOST and "uncertain" in flags[16][1]
    assert flags[17][0] == quality.LOST and "uncertain" not in flags[17][1]
    assert flags[18][0] == quality.CHECK and "low predicted mask quality" in flags[18][1]
    assert quality.summary(raw) == "lost 16-17; check 15, 18"
    assert quality.ranges([3, 4, 5, 9, 11, 12]) == "3-5, 9, 11-12" and quality.ranges([]) == ""


def test_reports_undo_and_subtree(tmp_path):
    s = ProjectStore(str(tmp_path / "q.stroto")); bus = CommandBus(s)
    assert s.schema_version() >= 3                                  # key_reports exist from v3 on
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "o"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "o", "point_count": 2}}, actor=m.ACTOR_AI)
    bus.execute({"op": "batch", "ops": [
        {"op": "set_key", "shape_id": "P", "frame": 1, "points": [[0] * 6, [1] * 6]},
        {"op": "set_report", "shape_id": "P", "frame": 1, "object_score": 0.3, "iou_pred": 0.9},
        {"op": "set_report", "shape_id": "P", "frame": 2, "object_score": -2.0, "iou_pred": 0.2}]}, actor=m.ACTOR_AI)
    assert [r["frame"] for r in s.reports("P")] == [1, 2]
    assert [f for f, _, _ in views.review_for_object(s, "O")] == [1]
    bus.execute({"op": "delete_subtree", "object_id": "O"})
    assert s.reports("P") == []
    bus.undo()                                                  # reports come back with the subtree
    assert [r["frame"] for r in s.reports("P")] == [1, 2]
    bus.undo()                                                  # undo the AI batch: reports gone too
    assert s.reports("P") == [] and s.key("P", 1) is None
    s.close()


def test_area_jump_flags_confidently_wrong_frame():
    """T-078: a frame whose area drops by more than 35 % against both nearest present frames is flagged CHECK,
    even with a confident score (the synthetic split frame: score 8.0, true IoU 0.42)."""
    from st_roto.quality import area_jumps, review_frames
    areas = {20: 25000.0, 21: 0.0, 22: 0.0, 23: 10766.0, 24: 25400.0, 25: 25200.0, 26: 24000.0}
    assert area_jumps(areas) == {23: 0.569}                      # lost frames (0) are skipped as neighbours
    reps = [{"frame": f, "object_score": 8.0, "iou_pred": 0.98} for f in (20, 23, 24, 25, 26)]
    flags = review_frames(reps, [20, 23, 24, 25, 26], areas)
    assert [(f, lvl) for f, lvl, _ in flags] == [(23, "check")]
    assert area_jumps({1: 100.0, 2: 80.0, 3: 100.0}) == {}        # 20 % wobble: not flagged


def test_long_absence_flags_only_exit_and_return():
    """SA-V (T-068): long absent runs are mostly real exits -> only the edges get CHECK; short runs stay LOST."""
    from st_roto import quality
    reps = [{"frame": f, "object_score": (-5.0 if 10 <= f <= 39 or f in (50, 51) else 5.0), "iou_pred": 0.95}
            for f in range(60)]
    flags = {f: (lvl, why) for f, lvl, why in quality.review_frames(reps, [], lost_max_gap=16)}
    assert flags[10][0] == quality.CHECK and "disappears" in flags[10][1]
    assert flags[39][0] == quality.CHECK and "reappears" in flags[39][1]
    assert not any(f in flags for f in range(11, 39))                 # the 28 frames in between: not flagged
    assert flags[50][0] == quality.LOST and flags[51][0] == quality.LOST
    assert quality.absent_runs(reps) == [(10, 39, 30), (50, 51, 2)]
