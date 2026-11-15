"""Headless Nuke integration tests. Run:  Nuke17.1.exe --nc -t tests/nuke/run_nuke_tests.py
Writes tests/nuke/out/results.json and exits non-zero on failure. Stays under the Non-commercial 10-node cap.

test_export_animated_shape: an analytic ellipse moving/rotating over frames -2..5 is traced (sub-pixel marching
squares), fitted with a fixed-count spline, stored through the command bus, exported with st_roto_nuke.roto_export,
rendered by Nuke, and compared per frame with (a) an exact pixel-centre rasterisation of the same stored spline and
(b) the analytic ellipse. (a) checks the export conventions; (b) checks the whole mask -> shape -> Nuke chain.
"""
import json, os, sys, tempfile, traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import nuke                                               # noqa: E402
import numpy as np                                        # noqa: E402
import cv2                                                # noqa: E402

from st_roto.commands import CommandBus                   # noqa: E402
from st_roto.store import ProjectStore                    # noqa: E402
from st_roto.geometry import Anchor, fit_fixed_count, rasterize_spline, trace_contours   # noqa: E402
from st_roto_nuke.roto_export import export_shape         # noqa: E402

OUT = ROOT + "/tests/nuke/out"
os.makedirs(OUT, exist_ok=True)
W, H, K = 1280, 720, 16
FRAMES = list(range(-2, 6))                               # includes negative frames (master prompt section 11)


def ellipse_field(f):
    """Signed (approximately) distance-like field of a rotated ellipse, evaluated at pixel centres."""
    cx, cy, ax, ay, ang = 400 + 60 * f, 360 - 10 * f, 260.0, 140.0, np.radians(12 * f)
    yy, xx = np.mgrid[0:H, 0:W]
    x, y = xx + 0.5 - cx, yy + 0.5 - cy
    u = x * np.cos(ang) + y * np.sin(ang)
    v = -x * np.sin(ang) + y * np.cos(ang)
    return 1.0 - np.sqrt((u / ax) ** 2 + (v / ay) ** 2)


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def frame_file(f):
    return OUT + ("/export.%04d.tif" % f if f >= 0 else "/export.-%03d.tif" % (-f))   # Nuke: sign + 3 digits


def test_export_animated_shape(res):
    tmp = tempfile.mkdtemp()
    store = ProjectStore(os.path.join(tmp, "t.stroto"))
    bus = CommandBus(store)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh", "width": W, "height": H}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "ellipse"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "ellipse main", "point_count": K}})
    prev, stored, truth = None, {}, {}
    for f in FRAMES:
        field = ellipse_field(f)
        truth[f] = field > 0
        loop = max(trace_contours(truth[f].astype(float) - 0.5), key=len)      # from the binary mask, like AI output
        a = fit_fixed_count(loop, K, start_hint=None if prev is None else prev[0].p)
        prev = a
        stored[f] = [[float(x.p[0]), float(x.p[1]), float(x.h_in[0]), float(x.h_in[1]),
                      float(x.h_out[0]), float(x.h_out[1])] for x in a]
        bus.execute({"op": "set_key", "shape_id": "P", "frame": f, "points": stored[f]})
    nuke.root()["format"].setValue("HD_720")
    roto = nuke.nodes.Roto(output="alpha")
    shape = export_shape(store, "P", roto["curves"], H)
    w = nuke.nodes.Write(file=OUT + "/export.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, roto)
    nuke.execute(w, FRAMES[0], FRAMES[-1])
    per = {}
    for f in FRAMES:
        img = cv2.imread(frame_file(f), cv2.IMREAD_UNCHANGED)
        if img is None:
            per[f] = {"error": "render missing: " + frame_file(f)}; continue
        r = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        anchors = [Anchor(p=np.array(p[0:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:6]), corner=False) for p in stored[f]]
        per[f] = {"iou_vs_exact_raster_of_stored_spline": round(iou(r, rasterize_spline(anchors, H, W)), 5),
                  "iou_vs_analytic_ellipse": round(iou(r, truth[f]), 5)}
    res["per_frame"] = per
    res["keys_on_point0"] = len(list(shape[0].center.getControlPointKeyTimes()))
    res["thresholds"] = {"vs_exact_raster": 0.998, "vs_analytic": 0.995}
    ok = res["keys_on_point0"] == len(FRAMES) and all(
        "error" not in v and v["iou_vs_exact_raster_of_stored_spline"] > 0.998 and v["iou_vs_analytic_ellipse"] > 0.995
        for v in per.values())
    store.close()
    return ok


VIDEO = ROOT + "/research/probes/2026-11-15_video/frames"


def test_st_roto_node_track_slice(res):
    """Vertical slice through PRODUCT code: ST_Roto node -> Track (synchronous in -t) -> project DB -> native Roto."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated (research/probes/2026-11-15_video/make_synthetic_video.py)"
        return True
    import st_roto_nuke.node as stnode
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], meta["frames"]
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "slice.stroto")
    g = stnode.create(rd, proj)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]])     # canonical -> Nuke y-up
    g["stroto_click_frame"].setValue(0)
    job = stnode.on_track(g, background=False)
    res["status_knob"] = g["stroto_status"].value()
    res["job_status"] = job.status if job else None
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"
        return False
    store = ProjectStore(proj)
    objs = store.conn.execute("SELECT * FROM objects").fetchall()
    shapes = store.conn.execute("SELECT * FROM shapes").fetchall()
    res["db"] = {"objects": len(objs), "shapes": len(shapes),
                 "keys": store.conn.execute("SELECT COUNT(*) FROM shape_keys").fetchone()[0],
                 "origins": sorted(set(r["origin"] for r in store.conn.execute("SELECT origin FROM shape_keys"))),
                 "ops": len(store.operations())}
    store.close()
    w = nuke.nodes.Write(file=OUT + "/slice.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)
    nuke.execute(w, 0, n - 1)
    ious = []
    for f in range(n):
        img = cv2.imread(OUT + "/slice.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        a = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
        ious.append(iou(a, gt))
    res["iou_vs_gt"] = {"mean": round(float(np.mean(ious)), 4), "min": round(float(np.min(ious)), 4),
                        "worst_frame": int(np.argmin(ious)),
                        "mean_excluding_split_frame_23": round(float(np.mean([v for i, v in enumerate(ious) if i != 23])), 4)}
    res["nodes_accessed"] = len(nuke.allNodes())
    return (res["db"]["objects"] == 1 and res["db"]["keys"] == n and res["db"]["origins"] == ["ai_generated"]
            and res["iou_vs_gt"]["mean"] > 0.98)


def test_repeated_tracking_stable(res):
    """Regression for R-41: three full 48-frame tracking runs in one Nuke session must not slow down or exhaust
    GPU memory (before the fix: run 3 was 2.4x slower at 7.8 of 8.15 GB)."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import subprocess, threading, time
    from st_roto_ai.sam2 import Sam2Video
    meta = json.load(open(VIDEO + "/meta.json"))
    frames = [cv2.cvtColor(cv2.imread(VIDEO + "/frame_%04d.png" % i), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
              for i in range(meta["frames"])]
    peak = {"v": 0, "stop": False}

    def sample():
        while not peak["stop"]:
            o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, creationflags=0x08000000).stdout
            peak["v"] = max(peak["v"], int(o.strip() or 0)); time.sleep(0.1)
    threading.Thread(target=sample, daemon=True).start()
    secs = []
    for run in range(3):
        trk = Sam2Video(ROOT + "/models/onnx/sam2.1-hiera-tiny/video", device="cuda", num_total_frames=len(frames))
        t0 = time.time()
        for i, rgb in enumerate(frames):
            enc = trk.encode(rgb)
            trk.add_points(0, enc, [tuple(meta["click_xy"])], [1]) if i == 0 else trk.track(i, enc)
        secs.append(round(time.time() - t0, 2))
    peak["stop"] = True
    res.update({"seconds_per_run": secs, "peak_gpu_MiB": peak["v"], "memattn": trk.memattn_file,
                "limits": {"run3_vs_run2_max_ratio": 1.3, "peak_gpu_MiB_max": 6500}})
    return secs[2] <= 1.3 * secs[1] and peak["v"] <= 6500


def test_prompts_preview_sync_protection(res):
    """Prompts (include + exclude) -> Preview -> Track -> second Track -> delete/undo via the session bus, with
    Roto synchronisation that must never overwrite or remove a shape the artist edited in the Roto node."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape, read_keys, TAG_RE
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 12                                     # 12 frames keep the test short
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "sync.stroto")
    g = stnode.create(rd, proj)
    roto = stnode._INNER[g.fullName()]["roto"]
    layer = roto["curves"].rootLayer
    names = lambda: [it.name for it in layer]                                    # noqa: E731
    cx, cy = meta["click_xy"]
    g["stroto_click"].setValue([cx, vh - cy]); stnode.on_add_point(g, 1)          # include: the target
    g["stroto_click"].setValue([1050.0, vh - 560.0]); stnode.on_add_point(g, 0)   # exclude: the distractor disc
    res["points"] = g["stroto_points_info"].value()
    pj = stnode.on_preview(g, background=False)
    res["preview"] = {"status": g["stroto_status"].value(), "layer": names()}
    ok = pj.status == "done" and names() == ["STROTO_preview"]
    j1 = stnode.on_track(g, background=False)
    res["track1"] = {"status": g["stroto_status"].value(), "layer": names(), "sync": getattr(j1, "sync_report", None)}
    ok &= j1.status == "done" and len(names()) == 1 and TAG_RE.search(names()[0]) is not None
    first_label = names()[0]
    j_again = stnode.on_track(g, background=False)              # same prompts again: refused, no duplicate (T-067)
    res["track_again"] = g["stroto_status"].value()
    ok &= j_again is None and "already tracked: object1" in res["track_again"] and len(names()) == 1
    g["stroto_object"].setValue("second")                       # a second object: its own prompt point
    g["stroto_click"].setValue([cx, vh - cy]); stnode.on_add_point(g, 1)
    j2 = stnode.on_track(g, background=False)
    res["track2"] = g["stroto_status"].value()
    ok &= j2 is not None and "skipped object1" in res["track2"] and len(names()) == 2
    second_label = [x for x in names() if x != first_label][0]
    store, bus = session.project(proj)
    shot = stnode.shot_id_for(g)
    objs = {o["name"]: o["id"] for o in store.objects(shot)}
    # unedited shape: delete -> removed from Roto; undo -> written back
    bus.execute({"op": "delete_subtree", "object_id": objs["second"]})
    r_del = stnode.resync(g)
    bus.undo()
    r_undo = stnode.resync(g)
    res["unedited"] = {"after_delete": r_del, "after_undo": r_undo, "layer": names()}
    ok &= second_label in r_del["removed"] and second_label in r_undo["written"]
    # artist edits the first shape in the Roto node (simulated: replace it by a modified copy with the same name)
    item = [it for it in layer if it.name == first_label][0]
    keys = read_keys(item, vh)
    f0 = sorted(keys)[0]
    keys[f0][0][0] += 25.0                                   # move one point 25 px on one frame
    for i in range(len(layer)):
        if layer[i].name == first_label:
            layer.remove(i); break
    layer.append(build_shape(roto["curves"], first_label, keys, vh))
    bus.execute({"op": "delete_subtree", "object_id": objs["object1"]})
    r_conf = stnode.resync(g)
    res["edited"] = {"after_delete": r_conf, "layer": names()}
    ok &= first_label in r_conf["conflicts"] and first_label in names()      # kept and reported, not removed
    edited_now = read_keys([it for it in layer if it.name == first_label][0], vh)
    ok &= abs(edited_now[f0][0][0] - keys[f0][0][0]) < 1e-2                   # artist edit intact
    res["nodes_accessed_note"] = "Read + ST_Roto group + 4 internal nodes"
    return bool(ok)


def test_import_artist_edits(res):
    """Artist edits in the Roto node are captured into the project (one undoable step per shape); undo reverts the
    Roto shape too; hand-drawn shapes become artist_created objects; topology changes are reported, not guessed."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import nuke.rotopaint as rp
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape, read_keys, keys_equal, TAG_RE
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 8
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "imp.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    layer = curves.rootLayer
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]])
    job = stnode.on_track(g, background=False)
    ok = job.status == "done"
    label = [it.name for it in layer][0]
    store, bus = session.project(proj)
    sid = store.conn.execute("SELECT shape_id FROM host_exports").fetchone()[0]

    def replace(name, keys, count=None):
        for i in range(len(layer)):
            if layer[i].name == name:
                layer.remove(i); break
        if count is not None:
            keys = {f: p[:count] for f, p in keys.items()}
        layer.append(build_shape(curves, name, keys, vh))

    # 1. edit frame 3, delete the key on frame 5
    keys = read_keys([it for it in layer if it.name == label][0], vh)
    edited = {f: [list(p) for p in v] for f, v in keys.items()}
    edited[3][0][0] += 30.0; edited[3][0][2] += 30.0; edited[3][0][4] += 30.0
    del edited[5]
    replace(label, edited)
    r1 = stnode.resync(g)
    k3, k5, k2 = store.key(sid, 3), store.key(sid, 5), store.key(sid, 2)
    res["edit"] = {"import": r1["import"], "k3_origin": k3["origin"], "k5": k5, "k2_origin": k2["origin"]}
    ok &= label in r1["import"]["imported"] and k3["origin"] == "artist_modified_ai" and k5 is None \
        and k2["origin"] == "ai_generated" and abs(k3["points"][0][0] - edited[3][0][0]) < 1e-2
    # 2. undo -> project reverted; resync -> Roto shape reverted too
    bus.undo()
    r2 = stnode.resync(g)
    host = read_keys([it for it in layer if it.name == label][0], vh)
    db = {k["frame"]: k["points"] for k in store.keys(sid)}
    res["undo"] = {"sync": {k: v for k, v in r2.items() if k != "import"}, "host_equals_db": keys_equal(host, db),
                   "frames": sorted(host)}
    ok &= keys_equal(host, db) and 5 in host and store.key(sid, 3)["origin"] == "ai_generated"
    # 3. artist draws a new static shape in the Roto node
    sh = rp.Shape(curves)
    for x, y in ((100.0, 600.0), (300.0, 600.0), (300.0, 450.0), (100.0, 450.0)):
        sh.append(rp.ShapeControlPoint(x, y))
    sh.name = "hand_drawn"
    layer.append(sh)
    r3 = stnode.resync(g)
    new_label = (r3["import"]["new_objects"] or [""])[0]
    objs = {o["name"]: o for o in store.objects(stnode.shot_id_for(g))}
    res["hand_drawn"] = {"import": r3["import"], "layer": [it.name for it in layer],
                         "origin": objs.get("hand_drawn", {}).get("origin")}
    ok &= bool(TAG_RE.search(new_label)) and new_label in [it.name for it in layer] \
        and objs.get("hand_drawn", {}).get("origin") == "artist_created"
    # 4. topology change (one point removed in Roto) -> reported, not imported
    replace(label, read_keys([it for it in layer if it.name == label][0], vh), count=15)
    r4 = stnode.resync(g)
    res["topology"] = r4["import"]["skipped"]
    ok &= any(label == s[0] and "point count" in s[1] for s in r4["import"]["skipped"]) and label in r4["conflicts"]
    return bool(ok)


def test_retrack_with_corrections(res):
    """(a) Draw ONE shape by hand on frame 6 -> Re-track fills frames 0..11 in both directions, close to the truth.
    (b) Correct one AI frame -> Re-track keeps that artist key byte-identical and replaces only AI keys."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import nuke.rotopaint as rp
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 12
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "rt.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    gts = [cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127 for f in range(n)]
    # (a) artist draws the object on frame 6 only (here: traced from the ground truth, 16 points)
    pts6 = mask_to_points(gts[6].astype(float) - 0.5, count=16)
    curves.rootLayer.append(build_shape(curves, "drawn", {6: pts6}, vh))
    nuke.frame(6)
    store, bus = session.project(proj)
    shot_rows = store.conn.execute("SELECT COUNT(*) FROM shots").fetchone()[0]
    if shot_rows == 0:                                        # shot is created by the first Track/import
        bus.execute({"op": "create_shot", "row": {"id": "shot1", "name": rd.name(), "width": meta["w"], "height": vh,
                                                  "first_frame": 0, "last_frame": n - 1}})
    stnode.resync(g)
    drawn = [o for o in store.objects("shot1")][0]
    g["stroto_object"].setValue(drawn["name"])
    job = stnode.on_retrack(g, background=False)
    sid = store.shapes(drawn["id"])[0]["id"]
    keys = {k["frame"]: k for k in store.keys(sid)}
    ious = {}
    for f, k in keys.items():
        a = [__import__("st_roto.geometry", fromlist=["Anchor"]).Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]),
             h_out=np.array(p[4:]), corner=False) for p in k["points"]]
        ious[f] = round(iou(rasterize_spline(a, vh, meta["w"]), gts[f]), 4)
    res["a"] = {"status": g["stroto_status"].value(), "frames": sorted(keys), "origins": {f: k["origin"] for f, k in keys.items()},
                "iou_vs_gt": ious}
    ok = (job is not None and job.status == "done" and sorted(keys) == list(range(n))
          and keys[6]["origin"] == "artist_created" and all(keys[f]["origin"] == "ai_generated" for f in keys if f != 6)
          and min(ious.values()) > 0.97)
    # (b) correct AI frame 9 in the Roto node, re-track: frame 9 must stay exactly the artist's
    nuke.frame(9)
    label = [it.name for it in curves.rootLayer if it.name.startswith(drawn["name"])][0]
    from st_roto_nuke.roto_export import read_keys
    host = read_keys([it for it in curves.rootLayer if it.name == label][0], vh)
    host[9] = [[p[0] + 8.0, p[1], p[2] + 8.0, p[3], p[4] + 8.0, p[5]] for p in host[9]]
    for i in range(len(curves.rootLayer)):
        if curves.rootLayer[i].name == label:
            curves.rootLayer.remove(i); break
    curves.rootLayer.append(build_shape(curves, label, host, vh))
    job2 = stnode.on_retrack(g, background=False)
    k9 = store.key(sid, 9)
    res["b"] = {"status": g["stroto_status"].value(), "k9_origin": k9["origin"],
                "k9_matches_artist": max(abs(a - b) for p, q in zip(k9["points"], host[9]) for a, b in zip(p, q)) < 1e-2}
    ok &= job2 is not None and job2.status == "done" and k9["origin"] == "artist_modified_ai" and res["b"]["k9_matches_artist"]
    return bool(ok)


def test_review_flags_reverse(res):
    """Draw the object by hand on the LAST frame (47) and re-track: the reverse pass crosses the occluder where the
    model is known to lose the object (PyTorch reference: frames 17-20, 22). Those frames must be flagged for review,
    and clean frames far from the occlusion must not be."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    from st_roto import views
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], meta["frames"]
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "rev.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    gt47 = cv2.imread(VIDEO + "/gt_%04d.png" % 47, cv2.IMREAD_GRAYSCALE) > 127
    curves.rootLayer.append(build_shape(curves, "drawn", {47: mask_to_points(gt47.astype(float) - 0.5, count=16)}, vh))
    nuke.frame(47)
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "shot1", "name": rd.name(), "width": meta["w"], "height": vh,
                                              "first_frame": 0, "last_frame": n - 1}})
    stnode.resync(g)
    obj = store.objects("shot1")[0]
    g["stroto_object"].setValue(obj["name"])
    job = stnode.on_retrack(g, background=False)
    flags = views.review_for_object(store, obj["id"])
    flagged = [f for f, _, _ in flags]
    res["lost_level"] = sorted(f for f, lvl, _ in flags if lvl == "lost")
    sid = store.shapes(obj["id"])[0]["id"]
    res.update({"status": g["stroto_status"].value(), "flagged": flagged,
                "absent_frames": [r["frame"] for r in store.reports(sid) if (r["object_score"] or 0) <= 0],
                "scores_12_to_24": {r["frame"]: round(r["object_score"], 3) for r in store.reports(sid) if 12 <= r["frame"] <= 24}})
    lost = set(res["absent_frames"])
    return (job is not None and job.status == "done" and lost and lost.issubset(set(flagged))
            and set(res["lost_level"]) == lost and not any(f in flagged for f in (0, 1, 2, 40, 41, 42))
            and "REVIEW lost" in res["status"])


def test_multi_object_track(res):
    """T-067: prompts for TWO objects on one ST_Roto node (target on frame 0, distractor disc on frame 4) -> one
    Track pass -> two objects, ONE undo step for both; then 'Re-track all' fills the disc's frames 0-3 in reverse."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 12
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "multi.stroto")
    g = stnode.create(rd, proj)

    def disc(f):
        s = f / 47.0
        return 1050 - 600 * s, 560 - 120 * np.sin(np.pi * s)

    for name, frame, (x, y) in (("target", 0, meta["click_xy"]), ("disc", 4, disc(4))):
        g["stroto_object"].setValue(name)
        nuke.frame(frame)
        g["stroto_click"].setValue([x, vh - y])                             # canonical -> Nuke y-up
        stnode.on_add_point(g, 1)
    res["points_info"] = g["stroto_points_info"].value()
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    objs = {o["name"]: o for o in store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])}
    sids = {k: store.shapes(o["id"])[0]["id"] for k, o in objs.items()}
    yy, xx = np.mgrid[0:vh, 0:vw] + 0.5

    def raster(k):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
        return rasterize_spline(a, vh, vw)

    def disc_gt(f):
        cx, cy = disc(f)
        tgt = cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127    # target is drawn over the disc
        return (np.hypot(xx - cx, yy - cy) <= 85) & ~tgt

    def quality(name, gt):
        return {k["frame"]: round(iou(raster(k), gt(k["frame"])), 4) for k in store.keys(sids[name])}

    tgt_gt = lambda f: cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
    res["track"] = {"objects": sorted(objs), "target_iou": quality("target", tgt_gt), "disc_iou": quality("disc", disc_gt)}
    ok = (sorted(objs) == ["disc", "target"] and sorted(res["track"]["target_iou"]) == list(range(n))
          and sorted(res["track"]["disc_iou"]) == list(range(4, n))
          and min(res["track"]["target_iou"].values()) > 0.97 and min(res["track"]["disc_iou"].values()) > 0.97)
    # one undo step removes both objects; redo restores both
    bus.undo()
    res["after_undo_objects"] = store.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    bus.redo()
    res["after_redo_objects"] = store.conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    ok &= res["after_undo_objects"] == 0 and res["after_redo_objects"] == 2
    stnode.resync(g, import_first=False)
    # Re-track all: the disc's prompt is on frame 4 -> the reverse pass now fills frames 0-3
    job2 = stnode.on_retrack(g, background=False, every_object=True)
    res["retrack_status"] = g["stroto_status"].value()
    res["retrack"] = {"disc_iou": quality("disc", disc_gt), "target_frames": sorted(quality("target", tgt_gt))}
    ok &= (job2 is not None and job2.status == "done" and sorted(res["retrack"]["disc_iou"]) == list(range(n))
           and min(res["retrack"]["disc_iou"].values()) > 0.97 and res["retrack"]["target_frames"] == list(range(n)))
    # the Roto node shows both objects
    res["roto_shapes"] = sorted(it.name for it in stnode._INNER[g.fullName()]["roto"]["curves"].rootLayer)
    ok &= len(res["roto_shapes"]) == 2
    return bool(ok)


TESTS = (test_export_animated_shape, test_st_roto_node_track_slice, test_repeated_tracking_stable,
         test_prompts_preview_sync_protection, test_import_artist_edits, test_retrack_with_corrections,
         test_review_flags_reverse, test_multi_object_track)


def main():
    # One test per Nuke process (tools/run_nuke_tests.py): the Non-commercial 10-node Python budget is per session.
    wanted = sys.argv[1:] or [t.__name__ for t in TESTS]
    results, failed = {"nuke": nuke.NUKE_VERSION_STRING, "nc": bool(nuke.env.get("nc"))}, 0
    for t in [t for t in TESTS if t.__name__ in wanted]:
        r = {}
        try:
            ok = t(r)
        except Exception:
            ok = False; r["exception"] = traceback.format_exc()
        r["passed"] = bool(ok); failed += 0 if ok else 1
        results[t.__name__] = r
    results["failed"] = failed
    with open(OUT + "/results_%s.json" % ("_".join(wanted) if len(wanted) == 1 else "all"), "w") as fh:
        json.dump(results, fh, indent=1)
    print("NUKE_TESTS_FAILED=%d" % failed)
    sys.exit(1 if failed else 0)


main()
