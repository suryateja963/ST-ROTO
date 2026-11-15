"""Unit tests for st_roto.store and st_roto.commands (persistence, undo/redo, REQ-042 protection)."""
import os
import sqlite3

import pytest

from st_roto import model as m
from st_roto.commands import CommandBus, ProtectedError
from st_roto.store import ProjectStore, SCHEMA_VERSION


def pts(n, dx=0.0):
    return [[10.0 * i + dx, 5.0, 10.0 * i - 2 + dx, 5.0, 10.0 * i + 2 + dx, 5.0] for i in range(n)]


@pytest.fixture
def env(tmp_path):
    store = ProjectStore(str(tmp_path / "proj.stroto"))
    bus = CommandBus(store, author="tester")
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh010", "width": 1920, "height": 1080}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "body", "point_count": 4}})
    yield store, bus
    store.close()


def test_schema_and_pragmas(tmp_path):
    s = ProjectStore(str(tmp_path / "a.stroto"))
    assert s.schema_version() == SCHEMA_VERSION
    assert s.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert s.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    s.close()


def test_newer_schema_is_refused(tmp_path):
    p = str(tmp_path / "future.stroto")
    s = ProjectStore(p); s.conn.execute("PRAGMA user_version = 99"); s.close()
    with pytest.raises(RuntimeError):
        ProjectStore(p)


def test_persistence_across_reopen(env, tmp_path):
    store, bus = env
    bus.execute({"op": "set_key", "shape_id": "P", "frame": -5, "points": pts(4)})   # negative frame allowed
    path = store.path
    store.close()
    s2 = ProjectStore(path)
    k = s2.key("P", -5)
    assert k["points"] == pts(4) and k["origin"] == m.ARTIST_CREATED
    assert [o["kind"] for o in s2.operations()] == ["create_shot", "create_object", "create_shape", "set_key"]
    s2.close()


def test_undo_redo_key_roundtrip(env):
    store, bus = env
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)})
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4, dx=3)})
    assert store.key("P", 1)["points"] == pts(4, dx=3)
    bus.undo()
    assert store.key("P", 1)["points"] == pts(4)
    bus.undo()
    assert store.key("P", 1) is None
    bus.redo(); bus.redo()
    assert store.key("P", 1)["points"] == pts(4, dx=3)
    assert not bus.can_redo()


def test_new_edit_clears_redo(env):
    store, bus = env
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)})
    bus.undo()
    assert bus.can_redo()
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 2, "points": pts(4)})
    assert not bus.can_redo()


def test_delete_subtree_undo_restores_everything(env):
    store, bus = env
    bus.execute({"op": "create_object", "row": {"id": "C", "shot_id": "S", "parent_id": "O", "name": "arm"}})
    bus.execute({"op": "create_shape", "row": {"id": "Q", "object_id": "C", "name": "arm", "point_count": 4}})
    for f in (1, 2, 3):
        bus.execute({"op": "set_key", "shape_id": "Q", "frame": f, "points": pts(4, dx=f)})
    before = (store.objects("S"), store.shapes("C"), store.keys("Q"))
    bus.execute({"op": "delete_subtree", "object_id": "O"})
    assert store.objects("S") == [] and store.keys("Q") == []
    bus.undo()
    assert (store.objects("S"), store.shapes("C"), store.keys("Q")) == before


def test_ai_cannot_overwrite_artist_key(env):
    store, bus = env
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)})          # artist
    n_ops = len(store.operations())
    with pytest.raises(ProtectedError):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4, dx=9)}, actor=m.ACTOR_AI)
    assert store.key("P", 1)["points"] == pts(4)                  # unchanged
    assert len(store.operations()) == n_ops                       # nothing logged (transaction rolled back)


def test_artist_edit_of_ai_key_becomes_artist_modified(env):
    store, bus = env
    bus.execute({"op": "create_shape", "row": {"id": "A", "object_id": "O", "name": "ai", "point_count": 4}},
                actor=m.ACTOR_AI)
    bus.execute({"op": "set_key", "shape_id": "A", "frame": 7, "points": pts(4)}, actor=m.ACTOR_AI)
    assert store.key("A", 7)["origin"] == m.AI_GENERATED
    bus.execute({"op": "set_key", "shape_id": "A", "frame": 7, "points": pts(4, dx=1)})   # artist correction
    assert store.key("A", 7)["origin"] == m.ARTIST_MODIFIED_AI
    with pytest.raises(ProtectedError):                           # AI may not re-overwrite the correction
        bus.execute({"op": "set_key", "shape_id": "A", "frame": 7, "points": pts(4, dx=5)}, actor=m.ACTOR_AI)
    bus.execute({"op": "set_key", "shape_id": "A", "frame": 8, "points": pts(4)}, actor=m.ACTOR_AI)  # new frame OK
    bus.undo()                                                    # undo restores exact origin too
    bus.undo()
    assert store.key("A", 7)["origin"] == m.AI_GENERATED


def test_locks(env):
    store, bus = env
    bus.execute({"op": "update_object", "id": "O", "fields": {"locked": 1}})
    with pytest.raises(ProtectedError):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)})          # artist: unlock first
    with pytest.raises(ProtectedError):
        bus.execute({"op": "update_object", "id": "O", "fields": {"locked": 0}}, actor=m.ACTOR_AI)  # AI can't unlock
    bus.execute({"op": "update_object", "id": "O", "fields": {"locked": 0}})
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)})


def test_ai_cannot_delete_artist_object(env):
    store, bus = env
    with pytest.raises(ProtectedError):
        bus.execute({"op": "delete_subtree", "object_id": "O"}, actor=m.ACTOR_AI)
    assert store.row("objects", "O") is not None


def test_invalid_points_rollback(env):
    store, bus = env
    n_ops = len(store.operations())
    with pytest.raises(ValueError):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(3)})          # wrong count
    with pytest.raises(ValueError):
        bad = pts(4); bad[0][0] = float("nan")
        bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": bad})
    assert store.key("P", 1) is None and len(store.operations()) == n_ops


def test_unknown_op_and_actor(env):
    store, bus = env
    with pytest.raises(ValueError):
        bus.execute({"op": "format_disk"})
    with pytest.raises(ValueError):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)}, actor="robot")


def test_shot_with_objects_cannot_be_deleted(env):
    store, bus = env
    with pytest.raises(ProtectedError):
        bus.execute({"op": "delete_shot", "id": "S"})


def test_undo_is_logged(env):
    store, bus = env
    seq = bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(4)})
    useq = bus.undo()
    ops = {o["seq"]: o for o in store.operations()}
    assert ops[useq]["undoes"] == seq and ops[useq]["kind"] == "delete_key"
