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
from .convention import key_to_nuke, nuke_to_key

TAG_RE = re.compile(r"_st([0-9a-f]{8})$")
HOST = "nuke_roto"
TOLERANCE = 1e-2           # pixels; Nuke stores float32, round-trips differ at ~1e-4 for coordinates ~1000


def host_tag(shape_id: str) -> str:
    return shape_id[:8]


def shape_label(name: str, shape_id: str) -> str:
    return _safe_name(name) + "_st" + host_tag(shape_id)


def build_shape(curves_knob, label: str, keys: dict, height: float):
    """Create (not yet attached) a fully keyed nuke.rotopaint.Shape from {frame: points}.
    Keys are added BEFORE points are appended: later keys are silently lost in Nuke 17.1 (R-33)."""
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
        cps.append(cp)
    shape = rp.Shape(curves_knob)
    for cp in cps:
        shape.append(cp)
    shape.name = label
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
    shape = build_shape(curves_knob, shape_label(row["name"], shape_id), keys, height)
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
        if tag in existing:
            host_keys = read_keys(existing[tag], height)
            rec = _recorded(store, tag)
            if rec is not None and not keys_equal(host_keys, rec):
                report["conflicts"].append(existing[tag].name); continue          # edited in Roto: hands off
            if keys_equal(host_keys, db_keys) and existing[tag].name == label:
                report["unchanged"].append(label); continue
            _remove(layer, existing[tag])
            if db_keys:
                layer.append(build_shape(curves_knob, label, db_keys, height)); _record(store, s["id"], db_keys)
                report["updated"].append(label)
            else:
                _forget(store, tag); report["removed"].append(label)
        elif db_keys:
            layer.append(build_shape(curves_knob, label, db_keys, height)); _record(store, s["id"], db_keys)
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
    return report


def export_preview(curves_knob, keys: dict, height: float, label: str = "STROTO_preview"):
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
