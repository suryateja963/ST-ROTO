"""Read-only views of project state for UIs (object panel). Pure Python."""
from __future__ import annotations


def object_rows(store, shot_id: str) -> list:
    """One row per object: id, name, parent_id, origin, locked, shapes, keys, first/last keyed frame."""
    rows = []
    for o in store.objects(shot_id):
        r = store.conn.execute(
            "SELECT COUNT(DISTINCT s.id), COUNT(k.frame), MIN(k.frame), MAX(k.frame) "
            "FROM shapes s LEFT JOIN shape_keys k ON k.shape_id = s.id WHERE s.object_id = ?", (o["id"],)).fetchone()
        rows.append({"id": o["id"], "name": o["name"], "parent_id": o["parent_id"], "origin": o["origin"],
                     "locked": bool(o["locked"]), "shapes": r[0], "keys": r[1], "first": r[2], "last": r[3]})
    return rows


def review_for_object(store, object_id: str) -> list:
    """Frames of an object's shapes that the artist should review: [(frame, reason)]."""
    from .quality import review_frames
    out = []
    for s in store.shapes(object_id):
        keyed = [k["frame"] for k in store.keys(s["id"])]
        out += review_frames(store.reports(s["id"]), keyed)
    return sorted(out)


def shot_shapes(store, shot_id: str) -> list:
    """All shapes of a shot (id, name, object_id, object_name) in creation order."""
    return [dict(r) for r in store.conn.execute(
        "SELECT s.id, s.name, s.object_id, o.name AS object_name FROM shapes s JOIN objects o ON o.id = s.object_id "
        "WHERE o.shot_id = ? ORDER BY s.created_utc, s.id", (shot_id,))]
