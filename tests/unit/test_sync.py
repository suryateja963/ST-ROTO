"""Replication prototype (T-020, D-023): two copies edited apart merge per (shape, frame); same-key edits wait as
branch candidates; syncing is idempotent and never echoes."""
import shutil

import pytest

from st_roto import model as m, sync
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore


def pts(v):
    return [[v, v, v, v, v, v], [v + 1, v, v + 1, v, v + 1, v]]


@pytest.fixture
def pair(tmp_path):
    a_path, b_path = str(tmp_path / "a.stroto"), str(tmp_path / "b.stroto")
    a = ProjectStore(a_path); bus = CommandBus(a, author="ana")
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "hero", "point_count": 2}})
    for f in range(6):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": f, "points": pts(f)})
    a.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    a.close()
    shutil.copyfile(a_path, b_path)                                       # B = a copy handed to another artist
    a, b = ProjectStore(a_path), ProjectStore(b_path)
    sync.fork_site(b)
    yield a, b
    a.close(); b.close()


def key(store, f):
    k = store.key("P", f)
    return k["points"][0][0] if k else None


def test_offline_edits_merge_and_conflicts_wait(pair):
    a, b = pair
    ba, bb = CommandBus(a, author="ana"), CommandBus(b, author="ben")
    ba.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(100)})      # only A: frame 1
    bb.execute({"op": "set_key", "shape_id": "P", "frame": 2, "points": pts(200)})      # only B: frame 2
    bb.execute({"op": "set_key", "shape_id": "P", "frame": 8, "points": pts(800)})      # only B: new frame
    ba.execute({"op": "set_key", "shape_id": "P", "frame": 5, "points": pts(500)})      # both: frame 5
    bb.execute({"op": "set_key", "shape_id": "P", "frame": 5, "points": pts(555)})
    r_ab = sync.import_changes(a, sync.export_changes(b))
    r_ba = sync.import_changes(b, sync.export_changes(a))
    assert r_ab["applied"] == 2 and r_ab["candidates"] == 1 and not r_ab["errors"]
    assert r_ba["candidates"] == 1 and not r_ba["errors"]                 # A's shared history is skipped, not re-applied
    for s in (a, b):                                                      # non-overlapping edits merged both ways
        assert key(s, 1) == 100 and key(s, 2) == 200 and key(s, 8) == 800
    assert key(a, 5) == 500 and key(b, 5) == 555                          # each keeps its own until resolved
    ca = sync.candidates(a)[0]
    assert ca["keys"] == [["key", "P", 5]] and ca["author"] == "ben"
    sync.resolve(ba, ca["id"], "remote")                                  # A's owner takes Ben's version
    assert key(a, 5) == 555 and sync.candidates(a) == []
    sync.resolve(bb, sync.candidates(b)[0]["id"], "local")                # B keeps its own
    assert key(b, 5) == 555
    # idempotent, no echo: syncing again changes nothing
    again = sync.import_changes(a, sync.export_changes(b))
    assert again["applied"] == 0 and again["candidates"] == 0
    origins = {r["site_id"] for r in a.conn.execute("SELECT site_id FROM operations WHERE author = 'ben'")}
    assert origins == {b.site_id()}                                       # replicated ops keep their origin


def test_protection_still_applies_to_replicated_ops(pair):
    a, b = pair
    CommandBus(a, author="ana").execute({"op": "update_object", "id": "O", "fields": {"locked": 1}})
    CommandBus(b, author="bot").execute({"op": "set_key", "shape_id": "P", "frame": 3, "points": pts(9)})
    rep = sync.import_changes(a, sync.export_changes(b))
    assert rep["errors"] and "locked" in rep["errors"][0][1] and key(a, 3) == 3   # locked object refused it


def test_same_copy_is_refused(tmp_path):
    s = ProjectStore(str(tmp_path / "x.stroto"))
    with pytest.raises(ValueError, match="same copy"):
        sync.import_changes(s, sync.export_changes(s))
    s.close()


def test_write_changes_file(pair, tmp_path):
    a, b = pair
    CommandBus(b, author="ben").execute({"op": "set_key", "shape_id": "P", "frame": 4, "points": pts(44)})
    p = str(tmp_path / "ben.changes.json")
    sync.write_changes(p, b)
    import json
    assert sync.import_changes(a, json.load(open(p)))["applied"] == 1 and key(a, 4) == 44
