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
    flags = dict(quality.review_frames(reports, keyed_frames=[14, 15, 18]))
    assert 14 not in flags
    assert "uncertain" in flags[15]
    assert "uncertain" in flags[16] and "lost between" in flags[16]
    assert "lost between" in flags[17] and "uncertain" not in flags[17]
    assert "low predicted mask quality" in flags[18]
    assert quality.ranges([3, 4, 5, 9, 11, 12]) == "3-5, 9, 11-12" and quality.ranges([]) == ""


def test_reports_undo_and_subtree(tmp_path):
    s = ProjectStore(str(tmp_path / "q.stroto")); bus = CommandBus(s)
    assert s.schema_version() == 3
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "o"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "o", "point_count": 2}}, actor=m.ACTOR_AI)
    bus.execute({"op": "batch", "ops": [
        {"op": "set_key", "shape_id": "P", "frame": 1, "points": [[0] * 6, [1] * 6]},
        {"op": "set_report", "shape_id": "P", "frame": 1, "object_score": 0.3, "iou_pred": 0.9},
        {"op": "set_report", "shape_id": "P", "frame": 2, "object_score": -2.0, "iou_pred": 0.2}]}, actor=m.ACTOR_AI)
    assert [r["frame"] for r in s.reports("P")] == [1, 2]
    assert [f for f, _ in views.review_for_object(s, "O")] == [1]
    bus.execute({"op": "delete_subtree", "object_id": "O"})
    assert s.reports("P") == []
    bus.undo()                                                  # reports come back with the subtree
    assert [r["frame"] for r in s.reports("P")] == [1, 2]
    bus.undo()                                                  # undo the AI batch: reports gone too
    assert s.reports("P") == [] and s.key("P", 1) is None
    s.close()
