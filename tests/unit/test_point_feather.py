"""Per-point feather (T-076): undoable artist op, protected from AI and locks, kept by delete/undo snapshots,
carried by JSON, a conflict key for sync."""
import json

import pytest

from st_roto import interchange, model as m, sync
from st_roto.commands import CommandBus, ProtectedError
from st_roto.store import ProjectStore

PTS = [[0, 0, 0, 0, 0, 0], [10, 0, 10, 0, 10, 0], [5, 8, 5, 8, 5, 8]]
PF = [[3.0, -2.0, 1.0, 0.0, -1.0, 0.0], [0.0] * 6, [0.0, 4.0, 0.0, 0.0, 0.0, 0.0]]


@pytest.fixture
def proj(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "o"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "o", "point_count": 3}})
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": PTS})
    yield s, bus
    s.close()


def test_set_undo_and_validation(proj):
    s, bus = proj
    bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": PF})
    assert s.feathers("P") == {1: PF}
    bus.undo()
    assert s.feathers("P") == {}
    bus.redo()
    assert s.feathers("P") == {1: PF}
    with pytest.raises(ValueError):
        bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 2, "data": PF[:2]})      # wrong point count
    bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": None})
    assert s.feathers("P") == {}


def test_protection(proj):
    s, bus = proj
    with pytest.raises(ProtectedError):
        bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": PF}, actor=m.ACTOR_AI)
    bus.execute({"op": "update_object", "id": "O", "fields": {"locked": 1}})
    with pytest.raises(ProtectedError):
        bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": PF})


def test_delete_and_undo_restore_feather(proj):
    s, bus = proj
    bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": PF})
    bus.execute({"op": "delete_shape", "id": "P"})
    assert s.row("shapes", "P") is None
    bus.undo()
    assert s.feathers("P") == {1: PF}
    bus.execute({"op": "delete_subtree", "object_id": "O"})
    bus.undo()
    assert s.feathers("P") == {1: PF}


def test_json_roundtrip_and_sync_key(proj, tmp_path):
    s, bus = proj
    bus.execute({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": PF})
    data = json.loads(json.dumps(interchange.export_shot(s, "S")))
    t = ProjectStore(str(tmp_path / "t.stroto")); tb = CommandBus(t)
    tb.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    ids = interchange.import_shot(tb, data, "S")
    assert t.feathers(ids["P"]) == {1: PF}
    t.close()
    assert sync.touched({"op": "set_key_feather", "shape_id": "P", "frame": 1, "data": PF}) == {("feather", "P", 1)}
