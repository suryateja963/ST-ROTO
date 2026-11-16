"""st_roto.prompts, st_roto.views and the schema v2 migration."""
import sqlite3

import pytest

from st_roto import prompts, views
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore


def test_prompts_roundtrip_and_rules():
    t = prompts.add("", 12, 100.5, 40.0, prompts.INCLUDE)
    t = prompts.add(t, 12, 300.0, 80.0, prompts.EXCLUDE)
    assert prompts.summary(t) == "frame 12: 1 include, 1 exclude"
    frame, xy, labels = prompts.for_tracker(t)
    assert frame == 12 and xy == [(100.5, 40.0), (300.0, 80.0)] and labels == [1, 0]
    with pytest.raises(ValueError):
        prompts.add(t, 13, 1, 1, prompts.INCLUDE)               # different frame
    with pytest.raises(ValueError):
        prompts.for_tracker(prompts.add("", 1, 1, 1, prompts.EXCLUDE))   # no include point
    with pytest.raises(ValueError):
        prompts.load('[{"frame":1,"x":1,"y":1,"label":5}]')
    assert prompts.summary("") == "no points"


def test_object_rows(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "hero", "point_count": 2}}, actor=m.ACTOR_AI)
    for f in (-3, 5):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": f, "points": [[0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1]]}, actor=m.ACTOR_AI)
    rows = views.object_rows(s, "S")
    assert rows == [{"id": "O", "name": "hero", "parent_id": None, "origin": "ai_generated", "locked": False,
                     "shapes": 1, "keys": 2, "first": -3, "last": 5}]
    assert views.shot_shapes(s, "S")[0]["object_name"] == "hero"
    s.close()


def test_v1_project_migrates_to_current(tmp_path):
    from st_roto.store import SCHEMA_VERSION
    p = str(tmp_path / "old.stroto")
    s = ProjectStore(p)
    for t in ("host_exports", "key_reports"):                  # every table added after v1
        s.conn.execute("DROP TABLE %s" % t)
    s.conn.execute("ALTER TABLE shots DROP COLUMN source_fingerprint")   # column added in v4
    for c in ("feather_x", "feather_y", "feather_falloff"):                 # columns added in v5
        s.conn.execute("ALTER TABLE shapes DROP COLUMN %s" % c)
    s.conn.execute("DROP INDEX idx_operations_uuid")                       # v6 additions
    for c in ("op_uuid", "site_id"):
        s.conn.execute("ALTER TABLE operations DROP COLUMN %s" % c)
    for t in ("sync_peers", "branch_candidates", "key_feather"):        # v6 + v7 tables
        s.conn.execute("DROP TABLE %s" % t)
    s.conn.execute("PRAGMA user_version = 1"); s.close()        # a genuine v1 file
    s2 = ProjectStore(p)
    assert s2.schema_version() == SCHEMA_VERSION
    for t in ("host_exports", "key_reports"):
        assert s2.conn.execute("SELECT name FROM sqlite_master WHERE name=?", (t,)).fetchone() is not None
    assert "source_fingerprint" in [r[1] for r in s2.conn.execute("PRAGMA table_info(shots)")]
    s2.close()


def test_rename_ops_carry_parts(tmp_path):
    s = ProjectStore(str(tmp_path / "r.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "obj"}})
    for sid, name in (("A", "obj"), ("B", "obj_part2"), ("C", "my hand"), ("D", "objective")):
        bus.execute({"op": "create_shape", "row": {"id": sid, "object_id": "O", "name": name, "point_count": 2}})
    bus.execute({"op": "batch", "ops": views.rename_ops(s, "O", "hero")})
    names = {sh["id"]: sh["name"] for sh in s.shapes("O")}
    assert names == {"A": "hero", "B": "hero_part2", "C": "my hand", "D": "objective"}
    assert s.row("objects", "O")["name"] == "hero"
    s.close()


def test_box_prompt_set_replace_order_and_summary():
    """OQ-25/T-079: one box per object (corner labels 2/3), replaced on re-set, sent to the tracker FIRST."""
    import pytest
    t = prompts.add("", 5, 50, 60, prompts.INCLUDE, obj="car")
    t = prompts.set_box(t, 5, 120, 90, 10, 20, obj="car")            # corners in any order -> normalised
    t = prompts.set_box(t, 5, 12, 22, 118, 88, obj="car")            # replaces the first box
    g = prompts.objects_for_tracker(t, "car")[0]
    assert g["labels"] == [prompts.BOX_TL, prompts.BOX_BR, prompts.INCLUDE]
    assert g["points"] == [(12.0, 22.0), (118.0, 88.0), (50.0, 60.0)]
    assert prompts.summary(t, "car") == "frame 5: box + 1 include, 0 exclude"
    only_box = prompts.set_box("", 3, 0, 0, 40, 30, obj="dog")      # a box alone is a valid prompt
    assert prompts.objects_for_tracker(only_box, "dog")[0]["labels"] == [2, 3]
    assert prompts.load(prompts.clear_box(t, "car", "car")) == [prompts.load(t)[0]]   # clicks kept
    with pytest.raises(ValueError, match="one frame"):
        prompts.set_box(t, 6, 0, 0, 40, 30, obj="car")
    with pytest.raises(ValueError, match="too small"):
        prompts.set_box("", 1, 10, 10, 11, 40, obj="car")
    with pytest.raises(ValueError, match="include point or a box"):
        prompts.objects_for_tracker(prompts.add("", 1, 1, 1, prompts.EXCLUDE, obj="x"), "x")
