"""Open interchange formats (master prompt section 20): ST-ROTO JSON (full fidelity, round trip) and SVG.

JSON (`st_roto.shapes`, version 1) keeps object identity, hierarchy, names, colours, locks, provenance (origin of
objects, shapes and every key, generator records) and every keyframe, in ST-ROTO's canonical coordinate space,
which the file states explicitly. Importing creates NEW ids (no collision with existing content) and records the
content as imported (actor "import" -> origin imported_native, REQ-042: AI may not overwrite it); the original
origins stay readable in the file. SVG: one file per frame, one cubic-Bezier <path> per shape, same coordinates
(SVG's y axis also points down), for review tools, web and vector editors. Feather is not stored by ST-ROTO yet,
so neither format carries it.
"""
from __future__ import annotations

import json
from xml.sax.saxutils import quoteattr

from . import model as m

FORMAT = "st_roto.shapes"
VERSION = 1
COORDINATES = ("pixels of the full-resolution source; x right, y DOWN; origin = top-left corner of the top-left "
               "pixel (pixel centres at +0.5). Each point = [x, y, in_handle_x, in_handle_y, out_handle_x, "
               "out_handle_y]; handles are ABSOLUTE cubic Bezier control points.")


def export_shot(store, shot_id: str) -> dict:
    shot = store.row("shots", shot_id)
    if shot is None:
        raise KeyError("no shot %s" % shot_id)
    objs = []
    for o in store.objects(shot_id):
        shapes = []
        for s in store.shapes(o["id"]):
            shapes.append({"id": s["id"], "name": s["name"], "closed": bool(s["closed"]), "locked": bool(s["locked"]),
                           "origin": s["origin"], "point_count": s["point_count"],
                           "feather": {"x": s.get("feather_x", 0.0), "y": s.get("feather_y", 0.0),
                                       "falloff": s.get("feather_falloff", 1.0)},
                           "generator": json.loads(s["generator"]) if s["generator"] else None,
                           "keys": [{"frame": k["frame"], "origin": k["origin"], "points": k["points"]}
                                    for k in store.keys(s["id"])],
                           "point_feather": [{"frame": f, "data": d} for f, d in sorted(store.feathers(s["id"]).items())]})
        objs.append({"id": o["id"], "name": o["name"], "parent_id": o["parent_id"], "origin": o["origin"],
                     "locked": bool(o["locked"]), "color": o["color"], "role": o.get("role") or "add",
                     "view": o.get("view"), "pair": o.get("pair"), "shapes": shapes})
    return {"format": FORMAT, "version": VERSION, "coordinates": COORDINATES,
            "shot": {k: shot[k] for k in ("id", "name", "source_path", "width", "height", "first_frame", "last_frame")},
            "objects": objs}


def write_json(path: str, store, shot_id: str):
    data = export_shot(store, shot_id)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    import os
    os.replace(tmp, path)
    return data


def import_shot(bus, data: dict, shot_id: str) -> dict:
    """Add the objects of an exported shot to `shot_id` as ONE undoable step. Returns {old id: new id}."""
    if data.get("format") != FORMAT:
        raise ValueError("not an ST-ROTO shapes file")
    if int(data.get("version", 0)) > VERSION:
        raise ValueError("file version %s is newer than this ST-ROTO (%d)" % (data.get("version"), VERSION))
    ids = {o["id"]: m.new_id() for o in data["objects"]}
    ops, pending = [], list(data["objects"])
    done = set()
    while pending:                                         # parents before children
        progressed = False
        for o in list(pending):
            if o["parent_id"] and o["parent_id"] in ids and o["parent_id"] not in done:
                continue
            row = {"id": ids[o["id"]], "shot_id": shot_id, "name": o["name"], "color": o.get("color"),
                   "parent_id": ids.get(o["parent_id"]), "role": o.get("role") or "add"}
            for f in ("view", "pair"):                      # T-109 (absent in files written before it)
                if o.get(f):
                    row[f] = o[f]
            ops.append({"op": "create_object", "row": row})
            for s in o["shapes"]:
                sid = ids[s["id"]] = m.new_id()
                gen = dict(s.get("generator") or {}, imported_from={"format": FORMAT, "shape_id": s["id"],
                                                                    "origin": s.get("origin")})
                fe = s.get("feather") or {}
                ops.append({"op": "create_shape", "row": {
                    "id": sid, "object_id": row["id"], "name": s["name"], "point_count": s["point_count"],
                    "closed": int(bool(s.get("closed", True))), "generator": json.dumps(gen, sort_keys=True),
                    "feather_x": float(fe.get("x", 0.0)), "feather_y": float(fe.get("y", 0.0)),
                    "feather_falloff": float(fe.get("falloff", 1.0))}})
                ops += [{"op": "set_key", "shape_id": sid, "frame": k["frame"], "points": k["points"]} for k in s["keys"]]
                ops += [{"op": "set_key_feather", "shape_id": sid, "frame": pf["frame"], "data": pf["data"]}
                        for pf in s.get("point_feather", [])]
                if s.get("locked"):
                    ops.append({"op": "update_shape", "id": sid, "fields": {"locked": 1}})
            done.add(o["id"]); pending.remove(o); progressed = True
        if not progressed:
            raise ValueError("object hierarchy has a cycle or a missing parent")
    # locks last: a locked object refuses key writes, for every actor
    ops += [{"op": "update_object", "id": ids[o["id"]], "fields": {"locked": 1}} for o in data["objects"] if o.get("locked")]
    bus.execute({"op": "batch", "ops": ops}, actor=m.ACTOR_IMPORT)
    return ids


def _fmt(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def path_data(points, closed=True) -> str:
    """SVG path 'd' for one stored key."""
    if not points:
        return ""
    d = ["M %s %s" % (_fmt(points[0][0]), _fmt(points[0][1]))]
    n = len(points)
    for i in range(n if closed else n - 1):
        a, b = points[i], points[(i + 1) % n]
        d.append("C %s %s %s %s %s %s" % tuple(_fmt(v) for v in (a[4], a[5], b[2], b[3], b[0], b[1])))
    if closed:
        d.append("Z")
    return " ".join(d)


def svg_frame(store, shot_id: str, frame: int) -> str:
    """One frame as SVG: a <g> per object (id/name kept as attributes), a <path> per keyed shape on that frame
    (no interpolation: only real keys are written)."""
    shot = store.row("shots", shot_id)
    w, h = int(shot["width"] or 0), int(shot["height"] or 0)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" data-frame="%d">'
           % (w, h, w, h, frame)]
    for o in store.objects(shot_id):
        parts = []
        for s in store.shapes(o["id"]):
            k = store.key(s["id"], frame)
            if k:
                parts.append('  <path id=%s data-name=%s data-origin=%s fill="white" d="%s"/>' % (
                    quoteattr("shape-" + s["id"]), quoteattr(s["name"]), quoteattr(k["origin"]),
                    path_data(k["points"], bool(s["closed"]))))
        if parts:
            out.append(' <g id=%s data-name=%s>' % (quoteattr("object-" + o["id"]), quoteattr(o["name"])))
            out += parts
            out.append(" </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"
