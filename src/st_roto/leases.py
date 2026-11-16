"""Object leases, presence and roles for collaboration (T-083; decisions D-024, D-035, D-036). PROTOTYPE layer:
the rules are enforced by the command bus; heartbeats are local until a network transport replicates them.

* A lease = (object, holder, acquired). While user X holds an object's lease, edits to that object (and its shapes,
  keys, feather) by anyone else are refused. Objects without a lease are open to everyone, so a solo artist never
  sees this layer.
* `set_lease` is an ordinary operation (audited, replicated, undoable): acquire (holder = yourself), renew, release
  (holder = None). Taking a lease held by someone else is an OVERRIDE: allowed only for a project supervisor and
  only when the holder is idle/offline, i.e. no presence heartbeat for IDLE_SECONDS (15 min, D-036). The override
  op records its evidence (holder, last heartbeat, idle seconds) for the audit.
* Presence = each user's latest heartbeat (`heartbeat`); not an operation (too frequent, no undo).
* Roles (`set_role`): artist / supervisor / admin. Only an admin assigns roles; the very first assignment in a
  project must be the author making themself admin (bootstrap).
Checks run when an operation is MADE (CommandBus.execute / redo). Operations replayed from a peer were checked
where they were made (their evidence is in the payload; T-084 signatures make it tamper-evident).
"""
from __future__ import annotations

import datetime

from . import model as m

IDLE_SECONDS = 15 * 60                                       # D-036
ROLES = ("artist", "supervisor", "admin")
OVERRIDE_ROLES = ("supervisor",)                             # D-024/D-035: supervisors override (admins can
                                                             # grant themselves the role, which is audited)


class LeaseError(Exception):
    """An operation conflicts with a lease, a role rule or the idle rule."""


def _parse(ts):
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def _now(now=None):
    return now if now is not None else datetime.datetime.utcnow().replace(microsecond=0)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------------ reads
def lease(conn, object_id):
    r = conn.execute("SELECT holder, acquired_utc FROM leases WHERE object_id = ?", (object_id,)).fetchone()
    return dict(r) if r else None


def role(conn, user):
    r = conn.execute("SELECT role FROM members WHERE user = ?", (user,)).fetchone()
    return r["role"] if r else None


def last_heartbeat(conn, user):
    r = conn.execute("SELECT heartbeat_utc FROM presence WHERE user = ?", (user,)).fetchone()
    return r["heartbeat_utc"] if r else None


def idle_seconds(conn, user, now=None):
    """Seconds since the user's last heartbeat; None if never seen (= offline)."""
    hb = last_heartbeat(conn, user)
    return None if hb is None else max(0, int((_now(now) - _parse(hb)).total_seconds()))


def is_idle(conn, user, now=None):
    s = idle_seconds(conn, user, now)
    return s is None or s >= IDLE_SECONDS


def heartbeat(store, user, now=None, frame=None, activity=None):
    """Record that `user` is active (presence, §19.1: who is working, on which frame, doing what)."""
    with store.transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO presence (user, heartbeat_utc, frame, activity) VALUES (?, ?, ?, ?)",
                     (user, _iso(_now(now)), frame, activity))


def presence(conn, now=None):
    return [dict(r, idle=is_idle(conn, r["user"], now)) for r in
            conn.execute("SELECT user, heartbeat_utc, frame, activity FROM presence ORDER BY user")]


# ------------------------------------------------------------------------------------------------ ops
def apply_set_lease(conn, op, actor):
    """op: object_id, holder (None = release), by (author), override (bool), evidence (dict, overrides only)."""
    if actor == m.ACTOR_AI:
        raise LeaseError("AI may not take or release leases")
    if conn.execute("SELECT 1 FROM objects WHERE id = ?", (op["object_id"],)).fetchone() is None:
        raise KeyError("no object %s" % op["object_id"])
    prev = lease(conn, op["object_id"])
    if op.get("holder") is None:
        conn.execute("DELETE FROM leases WHERE object_id = ?", (op["object_id"],))
    else:
        conn.execute("INSERT OR REPLACE INTO leases (object_id, holder, acquired_utc) VALUES (?, ?, ?)",
                     (op["object_id"], op["holder"], op.get("acquired_utc") or _iso(_now())))
    return {"op": "set_lease", "object_id": op["object_id"], "holder": prev["holder"] if prev else None,
            "acquired_utc": prev["acquired_utc"] if prev else None, "by": op.get("by"), "override": False}


def apply_set_role(conn, op, actor):
    if actor == m.ACTOR_AI:
        raise LeaseError("AI may not change roles")
    if op.get("role") is not None and op["role"] not in ROLES:
        raise ValueError("role must be one of %s" % (ROLES,))
    prev = role(conn, op["user"])
    if op.get("role") is None:
        conn.execute("DELETE FROM members WHERE user = ?", (op["user"],))
    else:
        conn.execute("INSERT OR REPLACE INTO members (user, role) VALUES (?, ?)", (op["user"], op["role"]))
    return {"op": "set_role", "user": op["user"], "role": prev}


# ------------------------------------------------------------------------------------------------ checks
def _objects_of(conn, op):
    """Objects an editing operation writes into (shape ops resolve to their object)."""
    kind = op.get("op")
    if kind == "batch":
        out = set()
        for sub in op["ops"]:
            out |= _objects_of(conn, sub)
        return out
    sid = op.get("shape_id") if kind in ("set_key", "delete_key", "set_key_feather", "set_report") else \
        op.get("id") if kind in ("update_shape", "delete_shape") else None
    if sid:
        r = conn.execute("SELECT object_id FROM shapes WHERE id = ?", (sid,)).fetchone()
        return {r["object_id"]} if r else set()
    if kind == "create_shape":
        return {op["row"]["object_id"]}
    if kind in ("update_object", "delete_subtree"):
        return {op.get("id") or op.get("object_id")}
    if kind == "create_object" and op["row"].get("parent_id"):
        return {op["row"]["parent_id"]}
    return set()


def _held_by_other(conn, object_id, author):
    """The lease on the object or the nearest leased ancestor, if someone else holds it."""
    seen = set()
    while object_id and object_id not in seen:
        seen.add(object_id)
        ls = lease(conn, object_id)
        if ls and ls["holder"] != author:
            return object_id, ls["holder"]
        r = conn.execute("SELECT parent_id FROM objects WHERE id = ?", (object_id,)).fetchone()
        object_id = r["parent_id"] if r else None
    return None


def check_edit(conn, op, author):
    """Refuse writes into objects leased by someone else (every actor: the AI runs on the author's behalf)."""
    for oid in _objects_of(conn, op):
        hit = _held_by_other(conn, oid, author)
        if hit:
            raise LeaseError("object %s is leased by %s: ask them to release it (a supervisor may take it after "
                             "%d min without activity)" % (hit[0], hit[1], IDLE_SECONDS // 60))


def check_made(conn, op, author, now=None):
    """Rules for an operation being MADE by `author` (not replayed). May add evidence to an override op."""
    kind = op.get("op")
    if kind == "batch":
        for sub in op["ops"]:
            if sub.get("op") in ("set_lease", "set_role"):
                raise ValueError("lease and role changes are not allowed inside a batch")
    if kind == "set_role":
        members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        if members == 0:
            if not (op["user"] == author and op.get("role") == "admin"):
                raise LeaseError("the first role in a project must be its author making themself admin")
        elif role(conn, author) != "admin":
            raise LeaseError("only an admin assigns roles")
        return
    if kind == "set_lease":
        if op.get("by") != author:
            raise LeaseError("a lease operation must be made by its author (by=%r, author=%r)" % (op.get("by"), author))
        cur = lease(conn, op["object_id"])
        new = op.get("holder")
        if new is not None and new != author:
            raise LeaseError("you can only take a lease for yourself")
        if new is not None:
            op["acquired_utc"] = _iso(_now(now))              # in the payload: replicas store the same time
        if cur is None or cur["holder"] == author:
            if op.get("override"):
                raise LeaseError("nothing to override: the lease is free or yours")
            if cur is None and new is None:
                raise LeaseError("object %s has no lease to release" % op["object_id"])
            return
        # held by someone else: override rules (D-024, D-035, D-036)
        if not op.get("override"):
            raise LeaseError("object %s is leased by %s" % (op["object_id"], cur["holder"]))
        if role(conn, author) not in OVERRIDE_ROLES:
            raise LeaseError("only a supervisor may override %s's lease" % cur["holder"])
        idle = idle_seconds(conn, cur["holder"], now)
        if idle is not None and idle < IDLE_SECONDS:
            raise LeaseError("%s was active %d min ago: a supervisor may override only after %d min without "
                             "activity" % (cur["holder"], idle // 60, IDLE_SECONDS // 60))
        op["evidence"] = {"holder": cur["holder"], "holder_acquired_utc": cur["acquired_utc"],
                          "holder_last_heartbeat_utc": last_heartbeat(conn, cur["holder"]),
                          "idle_seconds": idle, "threshold_seconds": IDLE_SECONDS, "checked_utc": _iso(_now(now))}
        return
    check_edit(conn, op, author)


# ------------------------------------------------------------------------------------------------ API
def acquire(bus, object_id):
    return bus.execute({"op": "set_lease", "object_id": object_id, "holder": bus.author, "by": bus.author})


def release(bus, object_id):
    return bus.execute({"op": "set_lease", "object_id": object_id, "holder": None, "by": bus.author})


def override(bus, object_id, take=True):
    """Supervisor override of an idle holder's lease: take it (default) or just free it."""
    return bus.execute({"op": "set_lease", "object_id": object_id, "holder": bus.author if take else None,
                        "by": bus.author, "override": True})


def set_role(bus, user, role_name):
    return bus.execute({"op": "set_role", "user": user, "role": role_name})
