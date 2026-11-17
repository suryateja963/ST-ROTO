"""Native Nuke Roto output (REQ-041) and safe synchronisation from the project store (REQ-042).

Shapes written by ST-ROTO are named "<name>_st<8 hex of shape id>". For every written shape the exact keys are
recorded in the project's `host_exports` table. `sync_shot` only replaces or removes a Roto shape whose current
keys still equal what ST-ROTO last wrote; a shape the artist edited in the Roto node is reported as a CONFLICT and
left untouched (importing Roto edits back into ST-ROTO is a later task).
"""
from __future__ import annotations

import json
import re

from st_roto import views
from st_roto.store import utc_now
from .convention import NUKE_TANGENT_SCALE  # noqa: F401  (per-point feather tangents, T-076)
from .convention import key_to_nuke, nuke_to_key

TAG_RE = re.compile(r"_st([0-9a-f]{8})$")
HOST = "nuke_roto"
TOLERANCE = 1e-2           # pixels; Nuke stores float32, round-trips differ at ~1e-4 for coordinates ~1000


def host_tag(shape_id: str) -> str:
    return shape_id[:8]


def shape_label(name: str, shape_id: str) -> str:
    return _safe_name(name) + "_st" + host_tag(shape_id)


FEATHER_ATTRS = ("fx", "fy", "ff")          # Roto shape attributes: feather X / Y (px), feather falloff (measured)


def feather_of(row) -> tuple:
    """(feather_x, feather_y, feather_falloff) of a stored shape row (defaults for schemas before v5)."""
    return (float(row.get("feather_x") or 0.0), float(row.get("feather_y") or 0.0),
            float(row.get("feather_falloff") if row.get("feather_falloff") is not None else 1.0))


def read_feather(shape, frame: float = 0) -> tuple:
    a = shape.getAttributes()
    return tuple(round(float(a.getValue(frame, k)), 6) for k in FEATHER_ATTRS)


def write_feather(shape, feather) -> None:
    a = shape.getAttributes()
    for k, v in zip(FEATHER_ATTRS, feather):
        a.set(k, float(v))                       # static value, no animation key (measured)


def feather_equal(a, b, tol=1e-4) -> bool:
    return all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def read_point_feather(shape) -> dict:
    """Per-point feather keys of a Roto shape {frame: [[fx, fy, lx, ly, rx, ry], ...]} in canonical units: offset
    y flipped (Nuke y up), tangents halved (Nuke tangent = 2 x handle offset, as for the shape itself). Frames =
    every key time of any point's featherCenter / feather tangents; {} when the shape has no per-point feather."""
    cps = list(shape)
    times = set()
    for cp in cps:
        for curve in (cp.featherCenter, cp.featherLeftTangent, cp.featherRightTangent):
            times.update(int(round(t)) for t in curve.getControlPointKeyTimes())
    out = {}
    s = NUKE_TANGENT_SCALE
    for f in sorted(times):
        row = []
        for cp in cps:
            c, l, r = cp.featherCenter.getPosition(f), cp.featherLeftTangent.getPosition(f), cp.featherRightTangent.getPosition(f)
            row.append([round(v, 6) + 0.0 for v in (c.x, -c.y, l.x / s, -l.y / s, r.x / s, -r.y / s)])   # +0.0: no -0.0
        out[f] = row
    return out


def point_feather_equal(a: dict, b: dict, tol: float = 1e-4) -> bool:
    if set(a) != set(b):
        return False
    return all(abs(x - y) <= tol for f in a for p, q in zip(a[f], b[f]) for x, y in zip(p, q))


def build_shape(curves_knob, label: str, keys: dict, height: float, feather=None, point_feather=None):
    """Create (not yet attached) a fully keyed nuke.rotopaint.Shape from {frame: points}, with the shape-level
    feather (fx, fy, ff) if given. Keys are added BEFORE points are appended: later keys are silently lost in
    Nuke 17.1 (R-33)."""
    import nuke.rotopaint as rp
    frames = sorted(keys)
    converted = [(f, key_to_nuke(keys[f], height)) for f in frames]
    n = len(keys[frames[0]])
    cps = []
    for i in range(n):
        (cx, cy), _, _ = converted[0][1][i]
        cp = rp.ShapeControlPoint(cx, cy)
        for f, pts in converted:
            (cx, cy), lt, rt = pts[i]
            cp.center.addPositionKey(f, rp.CVec2(cx, cy))
            cp.leftTangent.addPositionKey(f, rp.CVec2(*lt))
            cp.rightTangent.addPositionKey(f, rp.CVec2(*rt))
        for f, rows in sorted((point_feather or {}).items()):     # T-076; keys before append (R-33)
            fx, fy, lx, ly, rx, ry = rows[i]
            sc = NUKE_TANGENT_SCALE
            cp.featherCenter.addPositionKey(f, rp.CVec2(fx, -fy))
            cp.featherLeftTangent.addPositionKey(f, rp.CVec2(lx * sc, -ly * sc))
            cp.featherRightTangent.addPositionKey(f, rp.CVec2(rx * sc, -ry * sc))
        cps.append(cp)
    shape = rp.Shape(curves_knob)
    for cp in cps:
        shape.append(cp)
    shape.name = label
    if feather is not None:
        write_feather(shape, feather)
    return shape


def read_keys(shape, height: float) -> dict:
    """Read a Roto shape's keyed points back into canonical {frame: points}."""
    cps = list(shape)
    times = sorted({t for cp in cps for t in cp.center.getControlPointKeyTimes()})
    out = {}
    for t in times:
        pts = []
        for cp in cps:
            c, l, r = cp.center.getPosition(t), cp.leftTangent.getPosition(t), cp.rightTangent.getPosition(t)
            pts.append(nuke_to_key((c.x, c.y), (l.x, l.y), (r.x, r.y), height))
        out[int(round(t))] = pts
    return out


def keys_equal(a: dict, b: dict, tol: float = TOLERANCE) -> bool:
    if sorted(a) != sorted(b):
        return False
    for f in a:
        if len(a[f]) != len(b[f]):
            return False
        for p, q in zip(a[f], b[f]):
            if max(abs(x - y) for x, y in zip(p, q)) > tol:
                return False
    return True


def export_shape(store, shape_id: str, curves_knob, height: float, layer=None):
    """Write one stored shape track into a Roto node and record what was written."""
    row = store.row("shapes", shape_id)
    if row is None:
        raise KeyError("no shape %s" % shape_id)
    keys = {k["frame"]: k["points"] for k in store.keys(shape_id)}
    if not keys:
        raise ValueError("shape %s has no keys to export" % shape_id)
    shape = build_shape(curves_knob, shape_label(row["name"], shape_id), keys, height, feather_of(row),
                        store.feathers(shape_id))
    (layer if layer is not None else curves_knob.rootLayer).append(shape)
    _record(store, shape_id, keys)
    return shape


def _record(store, shape_id, keys):
    with store.transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO host_exports (host_tag, shape_id, host, fingerprint, exported_utc) "
                     "VALUES (?, ?, ?, ?, ?)", (host_tag(shape_id), shape_id, HOST,
                                                json.dumps({str(f): keys[f] for f in sorted(keys)}), utc_now()))


def _recorded(store, tag):
    r = store.conn.execute("SELECT fingerprint FROM host_exports WHERE host_tag = ? AND host = ?", (tag, HOST)).fetchone()
    return None if r is None else {int(f): v for f, v in json.loads(r[0]).items()}


def _forget(store, tag):
    with store.transaction() as conn:
        conn.execute("DELETE FROM host_exports WHERE host_tag = ? AND host = ?", (tag, HOST))


# Object roles in Nuke's own render (T-098, measured in research/probes/2026-11-17_roles): a shape's blend mode only
# acts where the shape is; the FIRST item of a Roto layer is on top; blend mode 12 ('minus') subtracts. Holdouts:
# minus; garbage: INVERTED shape, minus; both on top of the add shapes, and a Clamp (0-1) after the Roto removes the
# negative values minus leaves where nothing lies below. ST-ROTO's EXR combine (st_roto.views.combine_roles) uses the
# same arithmetic.
BLEND_ATTR, INVERT_ATTR, BLEND_MINUS = "bm", "inv", 12.0


def apply_roles(store, shot_id: str, curves_knob) -> bool:
    """Blend attributes and order of the shot's shapes from their objects' roles. Returns True if anything changed
    (then curves_knob.changed() has been called: Nuke does not re-render Python attribute edits otherwise)."""
    roles = {o["id"]: (o.get("role") or "add") for o in store.objects(shot_id)}
    tag_role = {host_tag(s["id"]): roles.get(s["object_id"], "add") for s in views.shot_shapes(store, shot_id)}
    layer = curves_knob.rootLayer
    items = list(layer)
    role_of = {}
    for it in items:
        mt = TAG_RE.search(getattr(it, "name", "") or "")
        role_of[id(it)] = tag_role.get(mt.group(1), "add") if mt else "add"
    changed = False
    for it in items:
        r = role_of[id(it)]
        want = {BLEND_ATTR: BLEND_MINUS if r != "add" else 0.0, INVERT_ATTR: 1.0 if r == "garbage" else 0.0}
        try:
            a = it.getAttributes()
        except AttributeError:
            continue
        for k, v in want.items():
            if abs(float(a.getValue(0, k)) - v) > 1e-6:
                a.set(k, v); changed = True
    top = [it for it in items if role_of[id(it)] != "add"]
    rest = [it for it in items if role_of[id(it)] == "add"]
    if [id(x) for x in items] != [id(x) for x in top + rest]:
        for idx in sorted((i for i, it in enumerate(items) if role_of[id(it)] != "add"), reverse=True):
            layer.remove(idx)                                 # Layer.remove takes an index (measured)
        for it in reversed(top):
            layer.insert(0, it)
        changed = True
    if changed:
        curves_knob.changed()
    return changed


def sync_shot(store, shot_id: str, curves_knob, height: float) -> dict:
    """Make the Roto node reflect the project, never overwriting artist edits made in the Roto node."""
    layer = curves_knob.rootLayer
    existing = {}
    for item in layer:
        m = TAG_RE.search(getattr(item, "name", "") or "")
        if m:
            existing[m.group(1)] = item
    report = {"written": [], "updated": [], "removed": [], "unchanged": [], "conflicts": []}
    seen = set()
    for s in views.shot_shapes(store, shot_id):
        tag = host_tag(s["id"]); seen.add(tag)
        db_keys = {k["frame"]: k["points"] for k in store.keys(s["id"])}
        label = shape_label(s["name"], s["id"])
        feather = feather_of(store.row("shapes", s["id"]))
        pfeather = store.feathers(s["id"])
        if tag in existing:
            host_keys = read_keys(existing[tag], height)
            rec = _recorded(store, tag)
            if rec is not None and not keys_equal(host_keys, rec):
                report["conflicts"].append(existing[tag].name); continue          # edited in Roto: hands off
            if keys_equal(host_keys, db_keys) and existing[tag].name == label:
                if not point_feather_equal(read_point_feather(existing[tag]), pfeather):
                    _remove(layer, existing[tag])                                 # per-point feather changed
                    layer.append(build_shape(curves_knob, label, db_keys, height, feather, pfeather))
                    report["updated"].append(label); continue
                if not feather_equal(read_feather(existing[tag]), feather):      # e.g. undo of a feather edit
                    write_feather(existing[tag], feather); report["updated"].append(label); continue
                report["unchanged"].append(label); continue
            _remove(layer, existing[tag])
            if db_keys:
                layer.append(build_shape(curves_knob, label, db_keys, height, feather, pfeather)); _record(store, s["id"], db_keys)
                report["updated"].append(label)
            else:
                _forget(store, tag); report["removed"].append(label)
        elif db_keys:
            layer.append(build_shape(curves_knob, label, db_keys, height, feather, pfeather)); _record(store, s["id"], db_keys)
            report["written"].append(label)
    for tag, item in existing.items():
        if tag in seen:
            continue
        rec = _recorded(store, tag)
        if rec is not None and keys_equal(read_keys(item, height), rec):
            name = item.name
            _remove(layer, item); _forget(store, tag); report["removed"].append(name)
        else:
            report["conflicts"].append(item.name)                                  # unknown or edited: keep
    report["roles_applied"] = apply_roles(store, shot_id, curves_knob)
    report["views_applied"], report["views_missing"] = apply_views(store, shot_id, curves_knob)
    return report


# Shape views (T-109, measured in research/probes/2026-11-17_stereo): attribute 'nv' = number of views the shape
# renders in, 'view1'..'view<nv>' = 1-based indices into the script's views (default: every view). Setting nv=1,
# view1=k shows the shape in view k only; it survives save + reopen.
NV_ATTR = "nv"


def _script_views():
    try:
        import nuke
        return list(nuke.views())
    except Exception:                                         # noqa: BLE001
        return []


def shape_view(item, script_views=None):
    """The one view a Roto shape is limited to, or None (several / every view)."""
    vs = _script_views() if script_views is None else script_views
    try:
        a = item.getAttributes()
        if len(vs) > 1 and int(round(a.getValue(0, NV_ATTR))) == 1:
            k = int(round(a.getValue(0, "view1")))
            return vs[k - 1] if 1 <= k <= len(vs) else None
    except (AttributeError, ValueError):
        pass
    return None


def apply_views(store, shot_id: str, curves_knob, script_views=None):
    """Limit each ST-ROTO shape to its object's view (objects.view); objects without a view render in every view.
    Returns (changed, [object views this script does not have: those shapes are shown in every view])."""
    vs = _script_views() if script_views is None else script_views
    if len(vs) < 2:
        return False, []
    obj = {o["id"]: o for o in store.objects(shot_id)}
    tag_view = {host_tag(s["id"]): obj[s["object_id"]].get("view") for s in views.shot_shapes(store, shot_id)}
    missing, changed = set(), False
    for it in curves_knob.rootLayer:
        mt = TAG_RE.search(getattr(it, "name", "") or "")
        if not mt or mt.group(1) not in tag_view:
            continue
        v = tag_view[mt.group(1)]
        if v and v not in vs:
            missing.add(v); v = None
        want = [vs.index(v) + 1] if v else list(range(1, len(vs) + 1))
        try:
            a = it.getAttributes()
        except AttributeError:
            continue
        have = [int(round(a.getValue(0, "view%d" % (i + 1)))) for i in range(int(round(a.getValue(0, NV_ATTR))))]
        if have != want:
            a.set(NV_ATTR, len(want))
            for i, k in enumerate(want):
                a.set("view%d" % (i + 1), k)
            changed = True
    if changed:
        curves_knob.changed()
    return changed, sorted(missing)


PREVIEW_LABEL = "STROTO_preview"


def import_edits(store, bus, shot_id: str, curves_knob, height: float, static_frame: int = 0) -> dict:
    """Capture artist work done in the Roto node into the project (actor = artist, one undoable batch per shape).

    * Tagged ST-ROTO shapes whose keys differ from what ST-ROTO last wrote: changed/added keys -> set_key,
      removed keys -> delete_key (edited AI keys become artist_modified_ai through the command rules).
    * Untagged shapes the artist drew in this Roto node: imported as new artist_created objects; the Roto shape is
      then renamed with its tag so later syncs recognise it.
    Not imported (reported in "skipped"): point count changed in Roto (topology changes unsupported in v0),
    locked objects/shapes, shapes whose object was deleted in the project.
    """
    import nuke.rotopaint as rp
    from st_roto import model as m
    from st_roto.commands import ProtectedError
    layer = curves_knob.rootLayer
    report = {"imported": [], "new_objects": [], "skipped": []}
    for item in list(layer):
        name = getattr(item, "name", "") or ""
        if name == PREVIEW_LABEL:
            continue
        if not isinstance(item, rp.Shape):                 # Layers (and strokes) are not imported in v0
            report["skipped"].append((name, "not a shape (layers/strokes are not imported in v0)")); continue
        match = TAG_RE.search(name)
        if match:
            tag = match.group(1)
            row = store.conn.execute("SELECT shape_id FROM host_exports WHERE host_tag = ? AND host = ?",
                                     (tag, HOST)).fetchone()
            shape = store.row("shapes", row["shape_id"]) if row else None
            if shape is None:
                report["skipped"].append((name, "its object was deleted in the project; shape kept as is")); continue
            rec = _recorded(store, tag) or {}
            host = read_keys(item, height)
            host_feather = read_feather(item, static_frame)
            feather_ops = [] if feather_equal(host_feather, feather_of(shape)) else [
                {"op": "update_shape", "id": shape["id"], "fields": dict(zip(("feather_x", "feather_y", "feather_falloff"),
                                                                              host_feather))}]
            host_pf, db_pf = read_point_feather(item), store.feathers(shape["id"])
            if len(item) == int(shape["point_count"]) and not point_feather_equal(host_pf, db_pf):
                feather_ops += [{"op": "set_key_feather", "shape_id": shape["id"], "frame": f, "data": host_pf[f]}
                                for f in sorted(host_pf) if f not in db_pf or not point_feather_equal({f: host_pf[f]}, {f: db_pf[f]})]
                feather_ops += [{"op": "set_key_feather", "shape_id": shape["id"], "frame": f, "data": None}
                                for f in sorted(db_pf) if f not in host_pf]
            if keys_equal(host, rec):
                if feather_ops:                                    # only the feather was changed in Roto
                    try:
                        bus.execute({"op": "batch", "ops": feather_ops})
                        report["imported"].append(name)
                    except ProtectedError as e:
                        report["skipped"].append((name, "protected: %s" % e))
                continue
            if any(len(p) != int(shape["point_count"]) for p in host.values()):
                report["skipped"].append((name, "point count changed in Roto (%d expected); not imported in v0"
                                          % shape["point_count"])); continue
            ops = [{"op": "set_key", "shape_id": shape["id"], "frame": f, "points": host[f]}
                   for f in sorted(host) if f not in rec or not keys_equal({f: host[f]}, {f: rec[f]})]
            ops += [{"op": "delete_key", "shape_id": shape["id"], "frame": f} for f in sorted(rec) if f not in host]
            ops += feather_ops
            try:
                bus.execute({"op": "batch", "ops": ops})
            except ProtectedError as e:
                report["skipped"].append((name, "protected: %s" % e)); continue
            _record(store, shape["id"], host)
            report["imported"].append(name)
        else:
            host = read_keys(item, height) or _static_keys(item, height, static_frame)
            if not host or len(next(iter(host.values()))) < 2:
                report["skipped"].append((name, "empty shape")); continue
            oid, sid = m.new_id(), m.new_id()
            n = len(next(iter(host.values())))
            fx, fy, ff = read_feather(item, static_frame)
            row = {"id": oid, "shot_id": shot_id, "name": name}
            sv = shape_view(item)                           # T-109: drawn for one view only -> that view's object
            if sv:
                row.update(view=sv, pair=name)
            ops = [{"op": "create_object", "row": row},
                   {"op": "create_shape", "row": {"id": sid, "object_id": oid, "name": name, "point_count": n,
                                                  "feather_x": fx, "feather_y": fy, "feather_falloff": ff}}]
            ops += [{"op": "set_key", "shape_id": sid, "frame": f, "points": host[f]} for f in sorted(host)]
            pf = read_point_feather(item)
            ops += [{"op": "set_key_feather", "shape_id": sid, "frame": f, "data": pf[f]} for f in sorted(pf)]
            bus.execute({"op": "batch", "ops": ops})
            label = shape_label(name, sid)
            _remove(layer, item)                                   # re-create with the tag (rename-safe)
            layer.append(build_shape(curves_knob, label, host, height, (fx, fy, ff), pf))
            _record(store, sid, host)
            report["new_objects"].append(label)
    return report


def _static_keys(shape, height, frame):
    """Shapes drawn without animation have no key times: read their current positions as one key at `frame`."""
    pts = []
    for cp in list(shape):
        c, l, r = cp.center.getPosition(frame), cp.leftTangent.getPosition(frame), cp.rightTangent.getPosition(frame)
        pts.append(nuke_to_key((c.x, c.y), (l.x, l.y), (r.x, r.y), height))
    return {int(frame): pts} if pts else {}


def export_preview(curves_knob, keys: dict, height: float, label: str = PREVIEW_LABEL):
    """Show a temporary, unrecorded shape (prompt preview); replaces any previous preview."""
    layer = curves_knob.rootLayer
    for item in list(layer):
        if getattr(item, "name", "") == label:
            _remove(layer, item)
    if keys:
        layer.append(build_shape(curves_knob, label, keys, height))


def _remove(layer, item):
    for i in range(len(layer)):
        if layer[i].name == item.name:
            layer.remove(i)                      # Layer.remove takes an index (measured)
            return


def _safe_name(name: str) -> str:
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    return out if out and not out[0].isdigit() else "s_" + out
