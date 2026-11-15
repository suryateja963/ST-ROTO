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
    """Frames of an object's shapes that the artist should review: [(frame, level, reason)]."""
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


def part_of(shape: dict):
    """Main shape id if `shape` is an AI part shape (an extra piece of a split object, T-049), else None."""
    import json
    try:
        return (json.loads(shape.get("generator") or "{}") or {}).get("part_of")
    except ValueError:
        return None


def main_shape(store, object_id: str):
    """The object's main shape: the first (creation order) that is not a part shape; None without shapes."""
    shapes = store.shapes(object_id)
    mains = [s for s in shapes if not part_of(s)]
    return (mains or shapes or [None])[0]


def part_shapes(store, main_id: str) -> list:
    s = store.row("shapes", main_id)
    return [p for p in store.shapes(s["object_id"]) if part_of(p) == main_id] if s else []


def rename_ops(store, object_id: str, new_name: str) -> list:
    """Ops renaming an object and the shapes named after it: '<old>' -> '<new>' and AI parts '<old>_part<n>' ->
    '<new>_part<n>' (T-049). Shapes the artist named differently keep their names."""
    import re
    old = store.row("objects", object_id)["name"]
    ops = [{"op": "update_object", "id": object_id, "fields": {"name": new_name}}]
    pat = re.compile(r"^%s(_part\d+)?$" % re.escape(old))
    for s in store.shapes(object_id):
        m = pat.match(s["name"])
        if m:
            ops.append({"op": "update_shape", "id": s["id"], "fields": {"name": new_name + (m.group(1) or "")}})
    return ops
