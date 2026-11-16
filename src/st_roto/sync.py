"""Operation-based replication between copies of a project — PROTOTYPE of docs/COLLABORATION_ARCHITECTURE.md
(T-020, decisions D-022/D-023). Pure Python; transport here = a JSON file (folder / USB); network transports later.

* Every operation has a global `op_uuid` and the `site_id` where it was made (schema v6).
* `export_changes` writes the operations MADE at this site after a mark; `import_changes` replays a peer's
  operations through the command bus (protection rules still apply) unless one of them touches a key that was
  ALSO changed locally since the last sync with that peer: then it waits as a BRANCH CANDIDATE (D-023) for the
  object owner to resolve (`resolve`). Different keys (e.g. other frames) merge automatically.
* Idempotent: an operation already present (same op_uuid) is skipped; nothing is echoed back.
"""
from __future__ import annotations

import json

from . import model as m
from .commands import CommandBus
from .store import utc_now


def fork_site(store) -> str:
    """Give a COPIED project its own site id (two copies must never share one) and remember the fork point: the
    history up to it is shared, so the first sync with the original only compares edits made after it."""
    import uuid
    sid = uuid.uuid4().hex
    fork_seq = store.conn.execute("SELECT COALESCE(MAX(seq), 0) FROM operations").fetchone()[0]
    with store.transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('site_id', ?)", (sid,))
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('fork_seq', ?)", (str(fork_seq),))
    return sid


def _fork_seq(store) -> int:
    r = store.conn.execute("SELECT value FROM meta WHERE key = 'fork_seq'").fetchone()
    return int(r[0]) if r else 0


def touched(op: dict) -> set:
    """Merge keys an operation changes: ('key', shape, frame), ('shape', id), ('object', id), ('shot', id).
    Diagnostics (set_report) are not conflict keys: the latest AI run wins."""
    kind = op.get("op")
    if kind == "batch":
        out = set()
        for sub in op["ops"]:
            out |= touched(sub)
        return out
    if kind in ("set_key", "delete_key"):
        return {("key", op["shape_id"], int(op["frame"]))}
    if kind == "set_key_feather":
        return {("feather", op["shape_id"], int(op["frame"]))}
    if kind in ("update_shape", "delete_shape", "restore_shape"):
        return {("shape", op.get("id") or op.get("shape", {}).get("id"))}
    if kind in ("update_object", "delete_subtree"):
        return {("object", op.get("id") or op.get("object_id"))}
    if kind == "restore_subtree":
        return {("object", op["snapshot"]["objects"][0]["id"])}
    if kind in ("update_shot", "delete_shot"):
        return {("shot", op["id"])}
    if kind == "set_lease":                                 # two sites taking the same lease: owner resolves
        return {("lease", op["object_id"])}
    if kind == "set_role":
        return {("role", op["user"])}
    return set()                                            # create_* (new ids) and set_report


def _ops(store, where, args):
    return [dict(r) for r in store.conn.execute(
        "SELECT seq, op_uuid, site_id, author, actor, payload FROM operations WHERE %s ORDER BY seq" % where, args)]


def export_changes(store, since_seq: int = 0) -> dict:
    site = store.site_id()
    ops = _ops(store, "site_id = ? AND seq > ?", (site, since_seq))
    return {"format": "st_roto.changes", "version": 1, "site_id": site, "base_seq": _fork_seq(store),
            "last_seq": max([o["seq"] for o in ops] or [since_seq]),
            "ops": [{"seq": o["seq"], "op_uuid": o["op_uuid"], "author": o["author"], "actor": o["actor"],
                     "payload": json.loads(o["payload"])} for o in ops]}


def write_changes(path: str, store, since_seq: int = 0) -> dict:
    """Export the operations made at this site after `since_seq` into a JSON file (import is idempotent, so
    re-sending is harmless)."""
    data = export_changes(store, since_seq)
    with open(path + ".part", "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    import os
    os.replace(path + ".part", path)
    return data


def import_changes(store, changes: dict) -> dict:
    """Replay a peer's operations. Returns {"applied", "skipped", "candidates", "errors"}."""
    if changes.get("format") != "st_roto.changes":
        raise ValueError("not an ST-ROTO changes file")
    peer = changes["site_id"]
    if peer == store.site_id():
        raise ValueError("these changes come from this same copy (site id): fork_site() the copy first")
    row = store.conn.execute("SELECT their_last_seq, my_seq_at_sync FROM sync_peers WHERE site_id = ?", (peer,)).fetchone()
    # first sync: the shared history ends at the fork point (ours, or the peer's if the peer is the copy)
    my_mark = row["my_seq_at_sync"] if row else max(_fork_seq(store), int(changes.get("base_seq") or 0))
    local_keys = set()
    for o in _ops(store, "seq > ? AND (site_id = ? OR site_id IS NULL)", (my_mark, store.site_id())):
        local_keys |= touched(json.loads(o["payload"]))
    report = {"applied": 0, "skipped": 0, "candidates": 0, "errors": []}
    for o in changes["ops"]:
        if store.conn.execute("SELECT 1 FROM operations WHERE op_uuid = ?", (o["op_uuid"],)).fetchone() or \
                store.conn.execute("SELECT 1 FROM branch_candidates WHERE op_uuid = ?", (o["op_uuid"],)).fetchone():
            report["skipped"] += 1
            continue
        keys = touched(o["payload"])
        clash = keys & local_keys
        if clash:
            with store.transaction() as conn:
                conn.execute("INSERT INTO branch_candidates (op_uuid, from_site, author, actor, payload, keys, created_utc) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)", (o["op_uuid"], peer, o["author"], o["actor"],
                                                             json.dumps(o["payload"]), json.dumps(sorted(clash)), utc_now()))
            report["candidates"] += 1
            continue
        try:
            CommandBus(store, author=o["author"]).execute(o["payload"], actor=o["actor"], origin=(o["op_uuid"], peer))
            report["applied"] += 1
        except Exception as e:                              # protection or missing parent: keep going, report
            report["errors"].append((o["op_uuid"], "%s: %s" % (type(e).__name__, e)))
    mine = store.conn.execute("SELECT COALESCE(MAX(seq), 0) FROM operations").fetchone()[0]
    with store.transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO sync_peers (site_id, their_last_seq, my_seq_at_sync, synced_utc) "
                     "VALUES (?, ?, ?, ?)", (peer, changes["last_seq"], mine, utc_now()))
    return report


def candidates(store, include_resolved: bool = False) -> list:
    where = "" if include_resolved else "WHERE resolution IS NULL"
    return [dict(r, payload=json.loads(r["payload"]), keys=json.loads(r["keys"]))
            for r in store.conn.execute("SELECT * FROM branch_candidates %s ORDER BY id" % where)]


def resolve(bus, candidate_id: int, take: str) -> None:
    """take='remote': apply the peer's version, replayed under its ORIGINAL operation id (so later syncs see it
    as known); 'local': keep ours. The candidate row stays as a resolved tombstone (audit + idempotent sync)."""
    store = bus.store
    r = store.conn.execute("SELECT * FROM branch_candidates WHERE id = ?", (candidate_id,)).fetchone()
    if r is None:
        raise KeyError("no candidate %s" % candidate_id)
    if r["resolution"]:
        raise ValueError("candidate %s already resolved (%s)" % (candidate_id, r["resolution"]))
    if take not in ("remote", "local"):
        raise ValueError("take must be 'remote' or 'local'")
    if take == "remote":
        bus.execute(json.loads(r["payload"]), actor=m.ACTOR_ARTIST, origin=(r["op_uuid"], r["from_site"]))
    with store.transaction() as conn:
        conn.execute("UPDATE branch_candidates SET resolution = ?, resolved_utc = ? WHERE id = ?",
                     (take + " by " + bus.author, utc_now(), candidate_id))
