"""Delivery packages (T-108, REQ-180, master prompt section 20): one zip per shot to hand over finished work.

Contents (every item the section lists):
  outputs/...                 final outputs: the matte EXRs and the JSON/SVG shape export given by the caller
  project_settings.json       the host node's settings (given by the caller) + shot description
  models.json                 metadata of every model that produced keys in this shot (from the shape generators
                              and the model manifests: repository, pinned revision, licence, approval)
  processing_report.json/.md  what was done: operations by kind / actor / author, first and last time, runs
  provenance.json             per object and shape: key origins (AI / artist / imported), generators
  quality_report.json/.md     per object: review flags (lost / check), key counts, confidence summary
  dependencies.json           ST-ROTO version, host, Python, libraries and their versions (given by the caller)
  MANIFEST.json               size + SHA-256 of every file in the package
Pure Python (no host imports); the host adapter gathers outputs, settings and dependencies.
"""
import collections
import datetime
import hashlib
import io
import json
import os
import zipfile

from . import model as m
from . import views


def _now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _json(obj):
    return json.dumps(obj, indent=1, sort_keys=True, default=str)


def models_used(store, shot_id, manifests_dir=None):
    used = {}
    for o in store.objects(shot_id):
        for s in store.shapes(o["id"]):
            for raw in [s.get("generator")] + [k.get("generator") for k in store.keys(s["id"])]:
                try:
                    g = json.loads(raw) if raw else {}
                except ValueError:
                    continue
                for src in (g, g.get("retrack") or {}):
                    name = src.get("model")
                    if name:
                        used.setdefault(name, {"objects": set()})["objects"].add(o["name"])
    out = {}
    for name, info in sorted(used.items()):
        meta = {"used_by_objects": sorted(info["objects"])}
        if manifests_dir:
            p = os.path.join(manifests_dir, name + ".json")
            if os.path.exists(p):
                src = json.load(io.open(p, encoding="utf-8"))
                meta.update({k: src.get(k) for k in ("repo", "revision", "licence", "approval")})
            else:
                meta["manifest"] = "missing"
        out[name] = meta
    return out


def processing_report(store):
    ops = store.conn.execute("SELECT kind, actor, author, ts_utc FROM operations ORDER BY seq").fetchall()
    by_kind, by_actor, by_author = collections.Counter(), collections.Counter(), collections.Counter()
    for r in ops:
        by_kind[r["kind"]] += 1; by_actor[r["actor"]] += 1; by_author[r["author"]] += 1
    return {"operations": len(ops), "by_kind": dict(by_kind), "by_actor": dict(by_actor),
            "by_author": dict(by_author), "first_utc": ops[0]["ts_utc"] if ops else None,
            "last_utc": ops[-1]["ts_utc"] if ops else None}


def provenance(store, shot_id):
    out = []
    for o in store.objects(shot_id):
        shapes = []
        for s in store.shapes(o["id"]):
            keys = store.keys(s["id"])
            shapes.append({"name": s["name"], "origin": s["origin"],
                           "key_origins": dict(collections.Counter(k["origin"] for k in keys)),
                           "frames": [keys[0]["frame"], keys[-1]["frame"]] if keys else None,
                           "generator": json.loads(s["generator"]) if s.get("generator") else None})
        out.append({"object": o["name"], "origin": o["origin"], "role": o.get("role") or "add", "shapes": shapes})
    return out


def quality_report(store, shot_id):
    out = []
    for o in store.objects(shot_id):
        flags = views.review_for_object(store, o["id"])
        scores = [r["object_score"] for s in store.shapes(o["id"]) for r in store.reports(s["id"])
                  if r["object_score"] is not None]
        ious = [r["iou_pred"] for s in store.shapes(o["id"]) for r in store.reports(s["id"]) if r["iou_pred"] is not None]
        keys = [k for s in store.shapes(o["id"]) for k in store.keys(s["id"])]
        out.append({"object": o["name"],
                    "keys": len(keys), "artist_keys": sum(1 for k in keys if k["origin"] != m.AI_GENERATED),
                    "review_lost": sorted(f for f, lvl, _ in flags if lvl == "lost"),
                    "review_check": sorted(f for f, lvl, _ in flags if lvl == "check"),
                    "ai_frames": len(scores),
                    "frames_object_absent": sum(1 for s in scores if s <= 0),
                    "predicted_iou_mean": round(sum(ious) / len(ious), 4) if ious else None})
    return out


def _md_processing(p):
    lines = ["# Processing report", "", "Operations: %d (%s .. %s)" % (p["operations"], p["first_utc"], p["last_utc"]),
             "", "| kind | count |", "|---|---|"]
    lines += ["| %s | %d |" % kv for kv in sorted(p["by_kind"].items())]
    lines += ["", "By actor: %s" % ", ".join("%s %d" % kv for kv in sorted(p["by_actor"].items())),
              "By author: %s" % ", ".join("%s %d" % kv for kv in sorted(p["by_author"].items()))]
    return "\n".join(lines) + "\n"


def _md_quality(q):
    lines = ["# Quality report", "", "Review flags are heuristic (st_roto.quality): 'lost' = object missing between "
             "visible frames, 'check' = uncertain.", "",
             "| object | keys | artist keys | REVIEW lost | check | predicted IoU (mean) |", "|---|---|---|---|---|---|"]
    from .frames import ranges
    for r in q:
        lines.append("| %s | %d | %d | %s | %s | %s |" % (r["object"], r["keys"], r["artist_keys"],
                                                         ranges(r["review_lost"]) or "-", ranges(r["review_check"]) or "-",
                                                         r["predicted_iou_mean"] if r["predicted_iou_mean"] is not None else "-"))
    return "\n".join(lines) + "\n"


def build(store, shot_id, out_zip, outputs=None, settings=None, dependencies=None, manifests_dir=None):
    """Write the delivery zip. outputs: {folder name in the package: local folder or file} (e.g. {"mattes": dir,
    "shapes": dir}). Returns {"zip", "files", "bytes"}. Refuses an empty delivery (no objects)."""
    shot = store.row("shots", shot_id)
    if shot is None:
        raise KeyError("no shot %s" % shot_id)
    if not store.objects(shot_id):
        raise ValueError("nothing to deliver: the shot has no objects")
    docs = {
        "project_settings.json": _json({"shot": {k: shot.get(k) for k in ("name", "width", "height", "first_frame",
                                                                           "last_frame", "source_path")},
                                        "settings": settings or {}}),
        "models.json": _json(models_used(store, shot_id, manifests_dir)),
        "processing_report.json": _json(processing_report(store)),
        "provenance.json": _json(provenance(store, shot_id)),
        "quality_report.json": _json(quality_report(store, shot_id)),
        "dependencies.json": _json(dependencies or {}),
    }
    docs["processing_report.md"] = _md_processing(json.loads(docs["processing_report.json"]))
    docs["quality_report.md"] = _md_quality(json.loads(docs["quality_report.json"]))
    entries = {}
    tmp = out_zip + ".part"
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for name, text in sorted(docs.items()):
            data = text.encode("utf-8")
            z.writestr(name, data)
            entries[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for label, src in sorted((outputs or {}).items()):
            if not src or not os.path.exists(src):
                continue
            files = [src] if os.path.isfile(src) else [os.path.join(dp, f) for dp, _, fs in os.walk(src) for f in fs]
            for p in sorted(files):
                if p.endswith(".part"):
                    continue
                rel = "outputs/%s/%s" % (label, os.path.relpath(p, src if os.path.isdir(src) else os.path.dirname(src)))
                rel = rel.replace("\\", "/")
                z.write(p, rel)
                h = hashlib.sha256(open(p, "rb").read()).hexdigest()
                entries[rel] = {"bytes": os.path.getsize(p), "sha256": h}
        man = {"format": "st_roto.delivery", "version": 1, "shot": shot["name"], "created_utc": _now(), "files": entries}
        z.writestr("MANIFEST.json", _json(man))
    os.replace(tmp, out_zip)
    return {"zip": out_zip, "files": len(entries) + 1, "bytes": os.path.getsize(out_zip)}


def verify(zip_path):
    """Check every file of a delivery package against its MANIFEST: [] when complete and unchanged."""
    bad = []
    with zipfile.ZipFile(zip_path) as z:
        man = json.loads(z.read("MANIFEST.json"))
        names = set(z.namelist())
        for rel, e in man["files"].items():
            if rel not in names:
                bad.append((rel, "missing")); continue
            data = z.read(rel)
            if len(data) != e["bytes"] or hashlib.sha256(data).hexdigest() != e["sha256"]:
                bad.append((rel, "changed"))
    return bad
