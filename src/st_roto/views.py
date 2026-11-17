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
    shapes = store.shapes(object_id)
    areas = _object_areas(store, shapes)
    for s in shapes:
        keyed = [k["frame"] for k in store.keys(s["id"])]
        reps = store.reports(s["id"])
        out += review_frames(reps, keyed, areas if reps else None)
    return sorted(out)


def _object_areas(store, shapes) -> dict:
    """{frame: area} of an object (all its shapes' keys; collapsed part keys add 0), polygon area of the spline."""
    import numpy as np
    from .geometry import Anchor, sample_spline
    areas = {}
    for s in shapes:
        for k in store.keys(s["id"]):
            pts = k["points"]
            poly = sample_spline([Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:6]), corner=False)
                                  for p in pts], 16)
            x, y = poly[:, 0], poly[:, 1]
            areas[k["frame"]] = areas.get(k["frame"], 0.0) + 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return areas


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


def merge_ops(store, source_id: str, target_id: str) -> list:
    """Ops merging object `source_id` into `target_id` (T-098): every shape of the source moves to the target
    (keys, feather, provenance and part links unchanged), then the empty source object is deleted. Run them as ONE
    batch (one undo step). The target's main shape stays its main shape."""
    if source_id == target_id:
        raise ValueError("cannot merge an object into itself")
    src, tgt = store.row("objects", source_id), store.row("objects", target_id)
    if src is None or tgt is None:
        raise KeyError("no such object")
    if src["shot_id"] != tgt["shot_id"]:
        raise ValueError("objects of different shots cannot be merged")
    ops = [{"op": "update_shape", "id": s["id"], "fields": {"object_id": target_id}} for s in store.shapes(source_id)]
    ops.append({"op": "delete_subtree", "object_id": source_id})
    return ops


def combine_roles(alphas: dict, roles: dict):
    """Combined matte of several objects with roles (T-098), exactly as Nuke's Roto composites ST-ROTO's shapes
    (measured, research/probes/2026-11-17_roles): 'add' objects composited over each other (a + b - a*b), then
    every holdout subtracted, then (1 - garbage) subtracted for every garbage object, clamped to [0, 1].
    alphas: {name: HxW float}; roles: {name: role}. Returns HxW float32 or None without objects."""
    import numpy as np
    out = None
    for n, a in alphas.items():
        if roles.get(n, "add") == "add":
            a = np.asarray(a, np.float32)
            out = a.copy() if out is None else out + a - out * a
    if out is None:
        out = np.zeros_like(np.asarray(next(iter(alphas.values())), np.float32)) if alphas else None
        if out is None:
            return None
    for n, a in alphas.items():
        r = roles.get(n, "add")
        if r == "holdout":
            out = out - np.asarray(a, np.float32)
        elif r == "garbage":
            out = out - (1.0 - np.asarray(a, np.float32))
    return np.clip(out, 0.0, 1.0).astype(np.float32)


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


def timeline(store, shot_id: str) -> list:
    """Per object, what the timeline in the Objects pane draws (T-102, REQ-120): [{"id", "name", "role", "keys":
    {frame: "artist" | "ai"}, "flags": {frame: "lost" | "check"}, "locked": [frames]}] in object order. Keys of
    every shape of the object count (a frame with any artist key is 'artist'); collapsed part keys are ignored."""
    import json as _json
    from . import model as m
    from .pieces import is_collapsed
    out = []
    for o in store.objects(shot_id):
        keys, locked = {}, set()
        for s in store.shapes(o["id"]):
            gen = _json.loads(s["generator"]) if s.get("generator") else {}
            locked.update(int(f) for f in gen.get("locked_frames", []))
            for k in store.keys(s["id"]):
                if not k["points"] or is_collapsed(k["points"]):
                    continue
                kind = "ai" if k["origin"] == m.AI_GENERATED else "artist"
                if keys.get(k["frame"]) != "artist":
                    keys[k["frame"]] = kind
        flags = {}
        for f, level, _why in review_for_object(store, o["id"]):
            if flags.get(f) != "lost":
                flags[f] = level
        out.append({"id": o["id"], "name": o["name"], "role": o.get("role") or "add", "keys": keys,
                    "flags": flags, "locked": sorted(locked)})
    return out
