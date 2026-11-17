"""Timeline data for the Objects pane (T-102)."""
import json

import numpy as np

from st_roto import views
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.geometry import mask_to_points
from st_roto.store import ProjectStore


def disc(cx, r=10, w=64, h=48):
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    return r - np.hypot(xx - cx, yy - 24)


def test_timeline_keys_flags_locks(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot", "width": 64, "height": 48}})
    bus.execute({"op": "create_object", "row": {"id": "A", "shot_id": "S", "name": "hero"}})
    bus.execute({"op": "create_shape", "row": {"id": "As", "object_id": "A", "name": "hero", "point_count": 12}})
    for f in range(6):
        actor = m.ACTOR_ARTIST if f == 2 else m.ACTOR_AI
        bus.execute({"op": "set_key", "shape_id": "As", "frame": f, "points": mask_to_points(disc(20 + f), count=12)},
                    actor=actor)
    # lock AFTER the AI keys exist (since DEF-007 the bus refuses AI writes to locked frames)
    bus.execute({"op": "update_shape", "id": "As", "fields": {"generator": json.dumps({"locked_frames": [3, 4]})}})
    bus.execute({"op": "set_report", "shape_id": "As", "frame": 5, "object_score": -3.0, "iou_pred": 0.2})
    bus.execute({"op": "set_report", "shape_id": "As", "frame": 4, "object_score": 5.0, "iou_pred": 0.9})
    bus.execute({"op": "set_report", "shape_id": "As", "frame": 6, "object_score": 5.0, "iou_pred": 0.9})
    t = views.timeline(s, "S")
    assert len(t) == 1 and t[0]["name"] == "hero" and t[0]["role"] == "add"
    assert t[0]["keys"] == {0: "ai", 1: "ai", 2: "artist", 3: "ai", 4: "ai", 5: "ai"}
    assert t[0]["locked"] == [3, 4]
    assert t[0]["flags"].get(5) in ("lost", "check")              # absent object between present frames
    s.close()
