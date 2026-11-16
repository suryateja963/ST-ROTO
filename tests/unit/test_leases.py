"""Object leases, presence and roles (T-083; D-024, D-035, D-036)."""
import datetime

import pytest

from st_roto import leases, model as m, sync
from st_roto.commands import CommandBus, ProtectedError
from st_roto.leases import LeaseError, IDLE_SECONDS
from st_roto.store import ProjectStore, SCHEMA_VERSION


def pts(v):
    return [[v, v, v, v, v, v], [v + 1, v, v + 1, v, v + 1, v]]


def ago(seconds):
    return datetime.datetime.utcnow().replace(microsecond=0) - datetime.timedelta(seconds=seconds)


@pytest.fixture
def proj(tmp_path):
    st = ProjectStore(str(tmp_path / "p.stroto"))
    admin = CommandBus(st, author="ada")
    admin.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    admin.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
    admin.execute({"op": "create_object", "row": {"id": "C", "shot_id": "S", "name": "arm", "parent_id": "O"}})
    admin.execute({"op": "create_shape", "row": {"id": "P", "object_id": "C", "name": "arm", "point_count": 2}})
    admin.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(1)})
    leases.set_role(admin, "ada", "admin")
    leases.set_role(admin, "sam", "supervisor")
    leases.set_role(admin, "ana", "artist")
    leases.set_role(admin, "ben", "artist")
    yield st
    st.close()


def test_schema_has_lease_tables(proj):
    assert proj.schema_version() == SCHEMA_VERSION >= 8
    for t in ("leases", "presence", "members"):
        proj.conn.execute("SELECT * FROM %s" % t)


def test_unleased_objects_are_open_and_solo_use_is_unaffected(proj):
    ben = CommandBus(proj, author="ben")
    ben.execute({"op": "set_key", "shape_id": "P", "frame": 2, "points": pts(2)})
    assert proj.key("P", 2)


def test_lease_blocks_others_including_children_and_ai(proj):
    ana, ben = CommandBus(proj, author="ana"), CommandBus(proj, author="ben")
    leases.acquire(ana, "O")                                            # parent object
    assert leases.lease(proj.conn, "O")["holder"] == "ana"
    ana.execute({"op": "set_key", "shape_id": "P", "frame": 3, "points": pts(3)})   # holder edits the child
    for op in ({"op": "set_key", "shape_id": "P", "frame": 4, "points": pts(4)},
               {"op": "update_object", "id": "C", "fields": {"name": "x"}},
               {"op": "delete_key", "shape_id": "P", "frame": 1},
               {"op": "batch", "ops": [{"op": "set_key", "shape_id": "P", "frame": 5, "points": pts(5)}]}):
        with pytest.raises(LeaseError):
            ben.execute(op)
    with pytest.raises(LeaseError):                                      # AI runs on ben's behalf: refused too
        ben.execute({"op": "set_key", "shape_id": "P", "frame": 6, "points": pts(6)}, actor=m.ACTOR_AI)
    with pytest.raises(LeaseError):
        leases.acquire(ben, "O")                                         # no stealing
    leases.release(ana, "O")
    ben.execute({"op": "set_key", "shape_id": "P", "frame": 4, "points": pts(4)})


def test_only_self_and_only_real_changes(proj):
    ana = CommandBus(proj, author="ana")
    with pytest.raises(LeaseError):
        ana.execute({"op": "set_lease", "object_id": "O", "holder": "ben", "by": "ana"})    # for someone else
    with pytest.raises(LeaseError):
        ana.execute({"op": "set_lease", "object_id": "O", "holder": "ana", "by": "ben"})    # forged author
    with pytest.raises(LeaseError):
        leases.release(ana, "O")                                         # nothing to release
    with pytest.raises(LeaseError):
        leases.override(ana, "O")                                        # nothing to override
    with pytest.raises(LeaseError):
        ana.execute({"op": "set_lease", "object_id": "O", "holder": "ana", "by": "ana"}, actor=m.ACTOR_AI)
    with pytest.raises(ValueError):
        ana.execute({"op": "batch", "ops": [{"op": "set_lease", "object_id": "O", "holder": "ana", "by": "ana"}]})


def test_supervisor_override_only_after_15_min_idle(proj):
    ana, sam, ben = (CommandBus(proj, author=u) for u in ("ana", "sam", "ben"))
    leases.acquire(ana, "O")
    leases.heartbeat(proj, "ana", now=ago(IDLE_SECONDS - 60))            # active 14 min ago
    with pytest.raises(LeaseError, match="only after 15 min"):
        leases.override(sam, "O")
    leases.heartbeat(proj, "ana", now=ago(IDLE_SECONDS + 5))             # idle 15 min
    with pytest.raises(LeaseError, match="only a supervisor"):
        leases.override(ben, "O")                                        # artists never override
    leases.override(sam, "O")
    assert leases.lease(proj.conn, "O")["holder"] == "sam"
    row = proj.conn.execute("SELECT author, payload FROM operations WHERE kind = 'set_lease' ORDER BY seq DESC").fetchone()
    import json
    ev = json.loads(row["payload"])["evidence"]
    assert row["author"] == "sam" and ev["holder"] == "ana" and ev["idle_seconds"] >= IDLE_SECONDS
    assert ev["threshold_seconds"] == 900
    with pytest.raises(LeaseError):                                      # ana is now the outsider
        ana.execute({"op": "set_key", "shape_id": "P", "frame": 7, "points": pts(7)})
    sam.undo()                                                           # override is undoable: ana holds it again
    assert leases.lease(proj.conn, "O")["holder"] == "ana"


def test_never_seen_holder_counts_as_offline(proj):
    ana, sam = CommandBus(proj, author="ana"), CommandBus(proj, author="sam")
    leases.acquire(ana, "O")                                             # ana never sent a heartbeat here
    assert leases.is_idle(proj.conn, "ana")
    leases.override(sam, "O", take=False)                                # free it without taking it
    assert leases.lease(proj.conn, "O") is None


def test_roles_admin_only_and_bootstrap(proj, tmp_path):
    ben = CommandBus(proj, author="ben")
    with pytest.raises(LeaseError, match="only an admin"):
        leases.set_role(ben, "ben", "supervisor")
    with pytest.raises(ValueError):
        leases.set_role(CommandBus(proj, author="ada"), "ben", "boss")
    fresh = ProjectStore(str(tmp_path / "f.stroto"))
    zed = CommandBus(fresh, author="zed")
    with pytest.raises(LeaseError, match="first role"):
        leases.set_role(zed, "zed", "supervisor")
    leases.set_role(zed, "zed", "admin")
    assert leases.role(fresh.conn, "zed") == "admin"
    fresh.close()


def test_undo_cannot_write_into_someone_elses_lease(proj):
    ben, ana = CommandBus(proj, author="ben"), CommandBus(proj, author="ana")
    ben.execute({"op": "set_key", "shape_id": "P", "frame": 9, "points": pts(9)})
    leases.acquire(ana, "O")
    with pytest.raises(LeaseError):
        ben.undo()
    assert proj.key("P", 9)


def test_presence_lists_idle_state(proj):
    leases.heartbeat(proj, "ana", frame=12, activity="editing hero")
    leases.heartbeat(proj, "ben", now=ago(IDLE_SECONDS * 2))
    p = {r["user"]: r for r in leases.presence(proj.conn)}
    assert p["ana"]["frame"] == 12 and not p["ana"]["idle"] and p["ben"]["idle"]


def test_lease_ops_replicate_and_conflict(tmp_path):
    import shutil
    a_path, b_path = str(tmp_path / "a.stroto"), str(tmp_path / "b.stroto")
    a = ProjectStore(a_path); ada = CommandBus(a, author="ada")
    ada.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    ada.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
    a.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)"); a.close()
    shutil.copyfile(a_path, b_path)
    a, b = ProjectStore(a_path), ProjectStore(b_path); sync.fork_site(b)
    leases.acquire(CommandBus(a, author="ana"), "O")
    rep = sync.import_changes(b, sync.export_changes(a))
    assert rep["applied"] == 1 and leases.lease(b.conn, "O")["holder"] == "ana"
    assert leases.lease(b.conn, "O")["acquired_utc"] == leases.lease(a.conn, "O")["acquired_utc"]
    # both sites take a lease on a second object while apart -> the remote one waits as a branch candidate
    CommandBus(a, author="ada").execute({"op": "create_object", "row": {"id": "Q", "shot_id": "S", "name": "q"}})
    sync.import_changes(b, sync.export_changes(a))
    leases.acquire(CommandBus(a, author="ana"), "Q")
    leases.acquire(CommandBus(b, author="ben"), "Q")
    rep = sync.import_changes(b, sync.export_changes(a))
    assert rep["candidates"] == 1 and leases.lease(b.conn, "Q")["holder"] == "ben"
    a.close(); b.close()


def test_protected_error_still_raised_for_locks(proj):
    ana = CommandBus(proj, author="ana")
    ana.execute({"op": "update_object", "id": "C", "fields": {"locked": 1}})
    with pytest.raises(ProtectedError):
        ana.execute({"op": "set_key", "shape_id": "P", "frame": 8, "points": pts(8)})
