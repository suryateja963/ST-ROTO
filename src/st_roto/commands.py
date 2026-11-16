"""Every edit is an operation (ADR-0006): applied in a transaction, logged with its inverse, undoable.

An operation is a plain dict: {"op": <name>, ...arguments}. `CommandBus.execute(op, actor, author)`
  1. checks protection rules (REQ-042: AI never overwrites, unlocks or deletes artist / imported / locked work),
  2. applies the op and computes its exact inverse,
  3. appends both to the `operations` table in the SAME transaction (crash-safe, audit history),
  4. maintains in-session undo/redo stacks.
Undo applies the stored inverse (bypassing protection: it restores a previous exact state) and is itself logged.
"""
from __future__ import annotations

import json

from . import leases as _leases
from . import model as m
from .store import ProjectStore, utc_now


class ProtectedError(Exception):
    """Raised when an operation would modify content the actor is not allowed to touch."""


# ------------------------------------------------------------------------------------------------ helpers
def _object_locked_chain(conn, object_id):
    """True if the object or any ancestor is locked."""
    seen = set()
    while object_id and object_id not in seen:
        seen.add(object_id)
        r = conn.execute("SELECT locked, parent_id FROM objects WHERE id = ?", (object_id,)).fetchone()
        if r is None:
            return False
        if r["locked"]:
            return True
        object_id = r["parent_id"]
    return False


def _shape_row(conn, shape_id):
    r = conn.execute("SELECT * FROM shapes WHERE id = ?", (shape_id,)).fetchone()
    if r is None:
        raise KeyError("no shape %s" % shape_id)
    return dict(r)


def _key_row(conn, shape_id, frame):
    r = conn.execute("SELECT * FROM shape_keys WHERE shape_id = ? AND frame = ?", (shape_id, frame)).fetchone()
    if r is None:
        return None
    d = dict(r); d["points"] = json.loads(d["points"])
    return d


def _subtree(conn, object_id):
    """Full snapshot of an object subtree (objects, shapes, keys), parents before children."""
    objs, frontier = [], [object_id]
    while frontier:
        oid = frontier.pop(0)
        r = conn.execute("SELECT * FROM objects WHERE id = ?", (oid,)).fetchone()
        if r is None:
            continue
        objs.append(dict(r))
        frontier.extend(x["id"] for x in conn.execute("SELECT id FROM objects WHERE parent_id = ? ORDER BY id", (oid,)))
    shapes, keys, reports, feathers = [], [], [], []
    for o in objs:
        for s in conn.execute("SELECT * FROM shapes WHERE object_id = ? ORDER BY id", (o["id"],)):
            shapes.append(dict(s))
            for k in conn.execute("SELECT * FROM shape_keys WHERE shape_id = ? ORDER BY frame", (s["id"],)):
                d = dict(k); d["points"] = json.loads(d["points"]); keys.append(d)
            reports += [dict(r) for r in conn.execute("SELECT * FROM key_reports WHERE shape_id = ? ORDER BY frame", (s["id"],))]
            feathers += [dict(r) for r in conn.execute("SELECT * FROM key_feather WHERE shape_id = ? ORDER BY frame", (s["id"],))]
    return {"objects": objs, "shapes": shapes, "keys": keys, "reports": reports, "feathers": feathers}


def _insert(conn, table, row):
    cols = sorted(row)
    conn.execute("INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(cols), ", ".join("?" * len(cols))),
                 [json.dumps(row[c]) if c == "points" else row[c] for c in cols])


# ------------------------------------------------------------------------------------------------ ops
def _create_shot(conn, op, actor):
    row = dict(op["row"]); row.setdefault("created_utc", utc_now())
    _insert(conn, "shots", row)
    return {"op": "delete_shot", "id": row["id"]}


def _delete_shot(conn, op, actor):
    row = conn.execute("SELECT * FROM shots WHERE id = ?", (op["id"],)).fetchone()
    if row is None:
        raise KeyError("no shot %s" % op["id"])
    n = conn.execute("SELECT COUNT(*) FROM objects WHERE shot_id = ?", (op["id"],)).fetchone()[0]
    if n:
        raise ProtectedError("shot %s still has %d objects" % (op["id"], n))
    conn.execute("DELETE FROM shots WHERE id = ?", (op["id"],))
    return {"op": "create_shot", "row": dict(row)}


def _create_object(conn, op, actor):
    row = dict(op["row"])
    row.setdefault("created_utc", utc_now())
    row["origin"] = m.origin_for_write(actor, None)
    row.setdefault("locked", 0)
    if row.get("parent_id") and actor == m.ACTOR_AI and _object_locked_chain(conn, row["parent_id"]):
        raise ProtectedError("cannot add an AI object under a locked parent")
    _insert(conn, "objects", row)
    return {"op": "delete_subtree", "object_id": row["id"]}


def _delete_subtree(conn, op, actor):
    snap = _subtree(conn, op["object_id"])
    if not snap["objects"]:
        raise KeyError("no object %s" % op["object_id"])
    if actor == m.ACTOR_AI:
        bad = [o["id"] for o in snap["objects"] if o["locked"] or o["origin"] != m.AI_GENERATED]
        bad += [s["id"] for s in snap["shapes"] if s["locked"] or s["origin"] != m.AI_GENERATED]
        bad += ["%s@%d" % (k["shape_id"], k["frame"]) for k in snap["keys"] if k["origin"] != m.AI_GENERATED]
        if bad:
            raise ProtectedError("AI may not delete artist/imported/locked content: %s" % bad[:5])
    conn.execute("DELETE FROM objects WHERE id = ?", (op["object_id"],))      # cascades
    return {"op": "restore_subtree", "snapshot": snap}


def _restore_subtree(conn, op, actor):
    snap = op["snapshot"]
    for o in snap["objects"]:
        _insert(conn, "objects", o)
    for s in snap["shapes"]:
        _insert(conn, "shapes", s)
    for k in snap["keys"]:
        _insert(conn, "shape_keys", k)
    for r in snap.get("reports", []):
        _insert(conn, "key_reports", r)
    for r in snap.get("feathers", []):
        _insert(conn, "key_feather", r)
    return {"op": "delete_subtree", "object_id": snap["objects"][0]["id"]}


_OBJECT_FIELDS = ("name", "locked", "color", "parent_id")
_SHOT_FIELDS = ("name", "source_path", "source_fingerprint", "width", "height", "first_frame", "last_frame")


def _update_shot(conn, op, actor):
    """Shot metadata (e.g. relinking its source, T-075); AI may not change shots."""
    r = conn.execute("SELECT * FROM shots WHERE id = ?", (op["id"],)).fetchone()
    if r is None:
        raise KeyError("no shot %s" % op["id"])
    fields = dict(op["fields"])
    for f in fields:
        if f not in _SHOT_FIELDS:
            raise ValueError("field %r not editable" % f)
    if actor == m.ACTOR_AI:
        raise ProtectedError("AI may not edit shot %s" % op["id"])
    old = {f: r[f] for f in fields}
    conn.execute("UPDATE shots SET %s WHERE id = ?" % ", ".join("%s = ?" % f for f in fields),
                 list(fields.values()) + [op["id"]])
    return {"op": "update_shot", "id": op["id"], "fields": old}


def _update_object(conn, op, actor):
    r = conn.execute("SELECT * FROM objects WHERE id = ?", (op["id"],)).fetchone()
    if r is None:
        raise KeyError("no object %s" % op["id"])
    fields = op["fields"]
    for f in fields:
        if f not in _OBJECT_FIELDS:
            raise ValueError("field %r not editable" % f)
    if actor == m.ACTOR_AI and (r["origin"] != m.AI_GENERATED or r["locked"] or "locked" in fields):
        raise ProtectedError("AI may not edit or (un)lock object %s" % op["id"])
    old = {f: r[f] for f in fields}
    conn.execute("UPDATE objects SET %s WHERE id = ?" % ", ".join("%s = ?" % f for f in fields),
                 [fields[f] for f in fields] + [op["id"]])
    return {"op": "update_object", "id": op["id"], "fields": old}


def _create_shape(conn, op, actor):
    row = dict(op["row"])
    row.setdefault("created_utc", utc_now())
    row["origin"] = m.origin_for_write(actor, None)
    row.setdefault("locked", 0); row.setdefault("closed", 1)
    if int(row["point_count"]) < 2:
        raise ValueError("a shape needs at least 2 points")
    if actor == m.ACTOR_AI and _object_locked_chain(conn, row["object_id"]):
        raise ProtectedError("cannot add an AI shape to a locked object")
    _insert(conn, "shapes", row)
    return {"op": "delete_shape", "id": row["id"]}


def _delete_shape(conn, op, actor):
    s = _shape_row(conn, op["id"])
    keys = [k for k in (_key_row(conn, s["id"], r["frame"]) for r in
            conn.execute("SELECT frame FROM shape_keys WHERE shape_id = ? ORDER BY frame", (s["id"],)))]
    if actor == m.ACTOR_AI and (s["locked"] or s["origin"] != m.AI_GENERATED
                                or any(k["origin"] != m.AI_GENERATED for k in keys)):
        raise ProtectedError("AI may not delete shape %s" % s["id"])
    reports = [dict(r) for r in conn.execute("SELECT * FROM key_reports WHERE shape_id = ? ORDER BY frame", (s["id"],))]
    feathers = [dict(r) for r in conn.execute("SELECT * FROM key_feather WHERE shape_id = ? ORDER BY frame", (s["id"],))]
    conn.execute("DELETE FROM shapes WHERE id = ?", (s["id"],))
    return {"op": "restore_shape", "shape": s, "keys": keys, "reports": reports, "feathers": feathers}


def _restore_shape(conn, op, actor):
    _insert(conn, "shapes", op["shape"])
    for k in op["keys"]:
        _insert(conn, "shape_keys", k)
    for r in op.get("reports", []):
        _insert(conn, "key_reports", r)
    for r in op.get("feathers", []):
        _insert(conn, "key_feather", r)
    return {"op": "delete_shape", "id": op["shape"]["id"]}


def _set_key_feather(conn, op, actor):
    """Per-point feather of one frame (T-076): data = [[fx, fy, lx, ly, rx, ry] per point] or None to remove.
    An artist decision: the AI never edits feather; locked shapes/objects refuse it."""
    shape = _shape_row(conn, op["shape_id"])
    frame = int(op["frame"])
    if actor == m.ACTOR_AI:
        raise ProtectedError("AI may not edit feather (shape %s)" % shape["id"])
    if shape["locked"] or _object_locked_chain(conn, shape["object_id"]):
        raise ProtectedError("shape %s is locked" % shape["id"])
    prev = conn.execute("SELECT data FROM key_feather WHERE shape_id = ? AND frame = ?", (shape["id"], frame)).fetchone()
    data = op.get("data")
    if data is None:
        conn.execute("DELETE FROM key_feather WHERE shape_id = ? AND frame = ?", (shape["id"], frame))
    else:
        data = m.validate_points(data, int(shape["point_count"]))
        conn.execute("INSERT OR REPLACE INTO key_feather (shape_id, frame, data) VALUES (?, ?, ?)",
                     (shape["id"], frame, json.dumps(data)))
    return {"op": "set_key_feather", "shape_id": shape["id"], "frame": frame,
            "data": json.loads(prev["data"]) if prev else None}


def _set_report(conn, op, actor):
    """Store the AI diagnostics of one frame (op: shape_id, frame, object_score, iou_pred; None = remove)."""
    shape = _shape_row(conn, op["shape_id"])
    frame = int(op["frame"])
    prev = conn.execute("SELECT object_score, iou_pred FROM key_reports WHERE shape_id = ? AND frame = ?",
                        (shape["id"], frame)).fetchone()
    if op.get("object_score") is None and op.get("iou_pred") is None:
        conn.execute("DELETE FROM key_reports WHERE shape_id = ? AND frame = ?", (shape["id"], frame))
    else:
        conn.execute("INSERT OR REPLACE INTO key_reports (shape_id, frame, object_score, iou_pred) VALUES (?, ?, ?, ?)",
                     (shape["id"], frame, op.get("object_score"), op.get("iou_pred")))
    return {"op": "set_report", "shape_id": shape["id"], "frame": frame,
            "object_score": prev["object_score"] if prev else None, "iou_pred": prev["iou_pred"] if prev else None}


def _check_shape_writable(conn, shape, actor, existing_key):
    if actor == m.ACTOR_AI:
        if shape["locked"] or _object_locked_chain(conn, shape["object_id"]):
            raise ProtectedError("shape %s is locked" % shape["id"])
        if existing_key is not None and existing_key["origin"] != m.AI_GENERATED:
            raise ProtectedError("AI may not overwrite %s key at frame %d of shape %s"
                                 % (existing_key["origin"], existing_key["frame"], shape["id"]))
    elif shape["locked"] or _object_locked_chain(conn, shape["object_id"]):
        raise ProtectedError("shape %s is locked; unlock it first" % shape["id"])


def _set_key(conn, op, actor):
    shape = _shape_row(conn, op["shape_id"])
    frame = int(op["frame"])
    prev = _key_row(conn, shape["id"], frame)
    _check_shape_writable(conn, shape, actor, prev)
    pts = m.validate_points(op["points"], int(shape["point_count"]))
    origin = op.get("origin_override") or m.origin_for_write(actor, prev["origin"] if prev else shape["origin"])
    conn.execute("INSERT OR REPLACE INTO shape_keys (shape_id, frame, points, origin, generator) VALUES (?, ?, ?, ?, ?)",
                 (shape["id"], frame, json.dumps(pts), origin, op.get("generator")))
    if prev is None:
        return {"op": "delete_key", "shape_id": shape["id"], "frame": frame}
    return {"op": "set_key", "shape_id": shape["id"], "frame": frame, "points": prev["points"],
            "origin_override": prev["origin"], "generator": prev["generator"]}


def _delete_key(conn, op, actor):
    shape = _shape_row(conn, op["shape_id"])
    frame = int(op["frame"])
    prev = _key_row(conn, shape["id"], frame)
    if prev is None:
        raise KeyError("no key at frame %d of shape %s" % (frame, shape["id"]))
    _check_shape_writable(conn, shape, actor, prev)
    conn.execute("DELETE FROM shape_keys WHERE shape_id = ? AND frame = ?", (shape["id"], frame))
    return {"op": "set_key", "shape_id": shape["id"], "frame": frame, "points": prev["points"],
            "origin_override": prev["origin"], "generator": prev["generator"]}


_SHAPE_FIELDS = ("name", "locked", "closed", "feather_x", "feather_y", "feather_falloff", "generator")   # generator: T-081 fixes


def _update_shape(conn, op, actor):
    s = _shape_row(conn, op["id"])
    fields = op["fields"]
    for f in fields:
        if f not in _SHAPE_FIELDS:
            raise ValueError("field %r not editable" % f)
    if actor == m.ACTOR_AI and (s["origin"] != m.AI_GENERATED or s["locked"] or "locked" in fields):
        raise ProtectedError("AI may not edit or (un)lock shape %s" % s["id"])
    old = {f: s[f] for f in fields}
    conn.execute("UPDATE shapes SET %s WHERE id = ?" % ", ".join("%s = ?" % f for f in fields),
                 [fields[f] for f in fields] + [s["id"]])
    return {"op": "update_shape", "id": s["id"], "fields": old}


def _batch(conn, op, actor):
    """Several operations as ONE undoable step (all-or-nothing: the bus wraps it in a single transaction)."""
    inverses = []
    for sub in op["ops"]:
        if sub.get("op") == "batch":
            raise ValueError("nested batches are not supported")
        fn = OPS.get(sub.get("op"))
        if fn is None:
            raise ValueError("unknown operation %r in batch" % sub.get("op"))
        inverses.append(fn(conn, sub, actor))
    return {"op": "batch", "ops": list(reversed(inverses))}


OPS = {
    "batch": _batch,
    "create_shot": _create_shot, "delete_shot": _delete_shot, "update_shot": _update_shot,
    "create_object": _create_object, "delete_subtree": _delete_subtree, "restore_subtree": _restore_subtree,
    "update_object": _update_object,
    "create_shape": _create_shape, "delete_shape": _delete_shape, "restore_shape": _restore_shape,
    "update_shape": _update_shape,
    "set_key": _set_key, "delete_key": _delete_key,
    "set_report": _set_report, "set_key_feather": _set_key_feather,
    "set_lease": _leases.apply_set_lease, "set_role": _leases.apply_set_role,
}


# ------------------------------------------------------------------------------------------------ bus
class CommandBus:
    def __init__(self, store: ProjectStore, author: str = "local"):
        self.store = store
        self.author = author
        self._undo = []          # list of (seq, op, inverse, actor)
        self._redo = []

    def execute(self, op: dict, actor: str = m.ACTOR_ARTIST, origin: tuple = None) -> int:
        """origin=(op_uuid, site_id) when replaying an operation made elsewhere (st_roto.sync)."""
        if actor not in m.ACTORS:
            raise ValueError("unknown actor %r" % actor)
        seq, inverse = self._apply_and_log(op, actor, undoes=None, check=True, origin=origin)
        self._undo.append((seq, op, inverse, actor))
        self._redo.clear()
        return seq

    def _site(self):
        if not hasattr(self, "_site_cache"):
            self._site_cache = self.store.site_id()
        return self._site_cache

    def undo(self) -> int | None:
        if not self._undo:
            return None
        seq, op, inverse, actor = self._undo.pop()
        new_seq, _ = self._apply_and_log(inverse, actor, undoes=seq, check=False)
        self._redo.append((op, actor))
        return new_seq

    def redo(self) -> int | None:
        if not self._redo:
            return None
        op, actor = self._redo.pop()
        seq, inverse = self._apply_and_log(op, actor, undoes=None, check=True)
        self._undo.append((seq, op, inverse, actor))
        return seq

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def _apply_and_log(self, op, actor, undoes, check, origin=None):
        fn = OPS.get(op.get("op"))
        if fn is None:
            raise ValueError("unknown operation %r" % op.get("op"))
        conn = self.store.conn
        with self.store.transaction():
            # Leases (T-083): an op MADE here is checked against leases, roles and the idle rule; a replayed peer
            # op was checked where it was made; undo may not write into an object someone else now leases.
            if origin is None and check:
                _leases.check_made(conn, op, self.author)
            elif origin is None:
                _leases.check_edit(conn, op, self.author)
            # Undo restores an exact previous state, so it applies as the original actor's inverse without
            # re-running protection (protection was enforced when the original op was accepted).
            inverse = fn(conn, op, actor if check else m.ACTOR_ARTIST)
            op_uuid, site = origin if origin else (m.new_id(), self._site())
            conn.execute("INSERT INTO operations (ts_utc, author, actor, kind, payload, inverse, undoes, op_uuid, "
                         "site_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (utc_now(), self.author, actor, op["op"], json.dumps(op), json.dumps(inverse), undoes,
                          op_uuid, site))
            seq = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return seq, inverse
