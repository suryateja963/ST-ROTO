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
    from st_roto import views
    main = views.main_shape(store, objs[0]["id"])
    res["db"] = {"objects": len(objs), "shapes": len(shapes),
                 "keys": store.conn.execute("SELECT COUNT(*) FROM shape_keys WHERE shape_id = ?", (main["id"],)).fetchone()[0],
                 "part_shapes": len(views.part_shapes(store, main["id"])),
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
    # main shape keyed on every frame; the piece the occluder cuts off around frame 23 is a part shape (T-049),
    # so the split frame is no longer the worst one (before: IoU ~0.6 there, mean 0.985)
    return (res["db"]["objects"] == 1 and res["db"]["keys"] == n and res["db"]["origins"] == ["ai_generated"]
            and res["iou_vs_gt"]["mean"] > 0.99 and res["iou_vs_gt"]["min"] > 0.97)


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
    current = read_keys([it for it in layer if it.name == label][0], vh)
    replace(label, current, count=len(next(iter(current.values()))) - 1)     # point count is adaptive (T-049)
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


def test_render_mattes_exr(res):
    """T-069/T-070: two tracked objects -> 'Render mattes (EXR)' -> Nuke itself reads the files: layer names, image
    orientation and values must match what ST-ROTO wrote; hard mattes must match the Roto node's own render."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import exr
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 4
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "mattes.stroto")
    g = stnode.create(rd, proj)
    for name, (x, y) in (("target", meta["click_xy"]), ("disc", (1050.0, 560.0))):
        g["stroto_object"].setValue(name); nuke.frame(0)
        g["stroto_click"].setValue([x, vh - y]); stnode.on_add_point(g, 1)
    job = stnode.on_track(g, background=False)
    ok = job is not None and job.status == "done"
    # (a) hard mattes vs the Roto node's own render of the same shapes
    g["stroto_soft"].setValue(False)
    jm = stnode.on_render_mattes(g, background=False)
    res["hard_status"] = g["stroto_status"].value()
    ok &= jm is not None and jm.status == "done"
    files = jm.result["files"]
    w = nuke.nodes.Write(file=OUT + "/roto_alpha.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)
    nuke.execute(w, 0, n - 1)
    agree = []
    for f in range(n):
        ours = exr.read_channels(files[f])["A"] > 0.5
        img = cv2.imread(OUT + "/roto_alpha.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        roto_a = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        agree.append(round(iou(ours, roto_a), 4))
    res["hard_matte_iou_vs_roto_render"] = agree
    ok &= min(agree) > 0.995
    # (b) soft mattes, read back BY NUKE: channel names, orientation, values
    g["stroto_soft"].setValue(True)
    js = stnode.on_render_mattes(g, background=False)
    res["soft_status"] = g["stroto_status"].value()
    ok &= js is not None and js.status == "done"
    r2 = nuke.nodes.Read(file=js.result["pattern"], first=0, last=n - 1)
    nuke.frame(2)
    res["nuke_channels"] = sorted(r2.channels())
    ours = exr.read_channels(js.result["files"][2])
    probe, diffs = [], []
    ys, xs = np.nonzero((ours["target.A"] > 0.02) & (ours["target.A"] < 0.98))       # soft edge pixels
    pick = list(zip(xs[::max(1, len(xs) // 20)], ys[::max(1, len(ys) // 20)]))[:20] + [(int(meta["click_xy"][0]), int(meta["click_xy"][1]))]
    for x, y in pick:
        for ch, layer in (("target.alpha", "target.A"), ("rgba.alpha", "A")):
            if ch not in res["nuke_channels"]:
                continue
            v = r2.sample(ch, x + 0.5, vh - y - 0.5)                                  # canonical -> Nuke y-up
            diffs.append(abs(v - float(ours[layer][y, x])))
    res["soft_edge_pixels"] = int(len(xs))
    res["max_abs_diff_nuke_vs_written"] = float(max(diffs)) if diffs else None
    ok &= ("target.alpha" in res["nuke_channels"] and "disc.alpha" in res["nuke_channels"]
           and "rgba.alpha" in res["nuke_channels"] and len(diffs) >= 40 and max(diffs) < 1e-6 and len(xs) > 100)
    return bool(ok)


def test_export_import_shapes(res):
    """Hand-drawn animated shape -> 'Export shapes (JSON + SVG)' -> delete the object -> 'Import shapes (JSON)':
    the object comes back (marked imported) and the Roto node again holds a shape with the same keys."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape, read_keys
    from st_roto.geometry import mask_to_points
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 3
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "ex.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    keys = {f: mask_to_points((cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127).astype(float) - 0.5,
                              count=12) for f in range(n)}
    curves.rootLayer.append(build_shape(curves, "drawn", keys, vh))
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "shot1", "name": rd.name(), "width": meta["w"], "height": vh,
                                              "first_frame": 0, "last_frame": n - 1}})
    stnode.resync(g)
    out = stnode.on_export_shapes(g)
    res["export_status"] = g["stroto_status"].value()
    ok = out is not None and os.path.exists(out["json"]) and len(out["svg"]) == n
    data = json.load(open(out["json"]))
    res["exported_objects"] = [o["name"] for o in data["objects"]]
    obj = store.objects("shot1")[0]
    bus.execute({"op": "delete_subtree", "object_id": obj["id"]})
    stnode.resync(g, import_first=False)
    res["after_delete"] = [it.name for it in curves.rootLayer]
    ok &= res["after_delete"] == []
    imp = stnode.on_import_shapes(g, out["json"])
    res["import_status"] = g["stroto_status"].value()
    objs = store.objects("shot1")
    sid = store.shapes(objs[0]["id"])[0]["id"]
    roto_shapes = [it for it in curves.rootLayer]
    res["after_import"] = {"objects": [o["name"] for o in objs], "origins": sorted({k["origin"] for k in store.keys(sid)}),
                           "roto": [it.name for it in roto_shapes]}
    back = read_keys(roto_shapes[0], vh) if roto_shapes else {}
    diff = max(abs(a - b) for f in keys for p, q in zip(keys[f], back.get(f, [])) for a, b in zip(p, q)) if back else None
    res["max_point_diff_roto_vs_original"] = diff
    ok &= (imp is not None and len(objs) == 1 and res["after_import"]["origins"] == ["imported_native"]
           and len(roto_shapes) == 1 and sorted(back) == list(range(n)) and diff is not None and diff < 1e-3)
    return bool(ok)


def test_crash_recovery_and_package(res):
    """T-071: a project left open by a process that died, with a damaged database file -> opening it from an
    ST_Roto node reports the crash, restores the newest backup (damaged file kept); 'Package project' produces a
    package that unpacks to a project passing the integrity check, with the same content."""
    import subprocess
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto import persistence
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "crash.stroto")
    s = ProjectStore(proj); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "Read1", "width": 64, "height": 48}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "kept"}})
    good = persistence.backup(proj)
    s.close()
    py = os.path.join(os.path.dirname(sys.executable), "python.exe")
    py = py if os.path.exists(py) else "C:/Program Files/Nuke17.1v3/python.exe"
    code = "import os,sys; sys.path.insert(0,%r); from st_roto.persistence import SessionMarker; " \
           "SessionMarker(%r).acquire({'app':'nuke'}); os._exit(9)" % (ROOT + "/src", proj)
    res["crasher_exit"] = subprocess.call([py, "-c", code])
    with open(proj, "r+b") as fh:
        fh.seek(0); fh.write(b"\0" * 4096)
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=1)
    g = stnode.create(rd, proj)
    store, _ = stnode._open_project(g, proj)
    rep = session.open_report(proj)
    res["report_text"] = session.report_text(proj)
    res["status"] = g["stroto_status"].value()
    res["objects_after_open"] = [o["name"] for o in store.objects("S")]
    damaged = (rep.get("recovery") or {}).get("damaged") or []
    ok = (res["crasher_exit"] == 9 and rep["previous_session"]["state"] == "crashed"
          and rep["recovery"]["action"] == "restored" and rep["recovery"]["from"] == good
          and damaged and all(os.path.exists(d) for d in damaged)
          and res["objects_after_open"] == ["kept"] and "restored backup" in res["status"])
    zp = stnode.on_package(g, os.path.join(tmp, "pkg.zip"))
    out = persistence.unpack(zp, os.path.join(tmp, "unpacked"))
    t = ProjectStore(out["project"])
    res["unpacked_objects"] = [o["name"] for o in t.objects("S")]
    t.close()
    ok &= res["unpacked_objects"] == ["kept"] and persistence.check(out["project"])["ok"]
    session.close(proj)
    res["marker_removed_on_close"] = not os.path.exists(proj + ".session.json")
    ok &= res["marker_removed_on_close"]
    return bool(ok)


def test_motion_blur_links(res):
    """T-074: the ST_Roto 'motion blur' knobs drive the inner Roto's global motion blur: a shape moving 60 px per
    frame renders with a soft trail when on, hard edges when off; the trail lies along the motion."""
    import st_roto_nuke.node as stnode
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=2)
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "mb.stroto"))
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    keys = {f: mask_to_points(80.0 - np.hypot(xx - (400 + 60 * f), yy - 360), count=12) for f in range(3)}
    curves.rootLayer.append(build_shape(curves, "mover", keys, H))
    w = nuke.nodes.Write(file=OUT + "/mb.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)

    def render(tag):
        nuke.execute(w, 1, 1)
        img = cv2.imread(OUT + "/mb.0001.tif", cv2.IMREAD_UNCHANGED)
        a = img if img.ndim == 2 else img[:, :, -1]
        soft = (a > 0.05) & (a < 0.95)
        ys, xs = np.nonzero(soft)
        return {"soft_px": int(soft.sum()), "x_extent": int(np.ptp(xs)) if len(xs) else 0,
                "y_extent": int(np.ptp(ys)) if len(ys) else 0}

    res["links"] = {n: g[n].value() for n, _, _ in stnode.MOTIONBLUR_LINKS}
    res["off"] = render("off")
    g["stroto_mb_mode"].setValue("global"); g["stroto_mb_samples"].setValue(10); g["stroto_mb_shutter"].setValue(1.0)
    roto = stnode._INNER[g.fullName()]["roto"]
    res["inner_after_set"] = {"mode": roto["motionblur_mode"].value(), "samples": roto["global_motionblur"].value(),
                              "shutter": roto["global_motionblur_shutter"].value()}
    res["on"] = render("on")
    return (res["inner_after_set"] == {"mode": "global", "samples": 10.0, "shutter": 1.0}
            # motion is 60 px/frame along x with shutter 1 -> a trail of ~60 px along x only (measured: +50 px in x,
            # -2 px in y; soft pixels 1,401 -> 17,243, the 'off' ones being Nuke's anti-aliased edge)
            and res["on"]["soft_px"] > 5 * res["off"]["soft_px"]
            and res["on"]["x_extent"] - res["off"]["x_extent"] > 40 and abs(res["on"]["y_extent"] - res["off"]["y_extent"]) < 10)


def test_colour_auto_follows_script(res):
    """T-045: 'AI input colour' = auto. Nuke colour management -> the v0 linear-sRGB transform; OCIO with the ACES cg
    config (Read converts the sRGB PNGs into ACEScg) -> an OCIO transform back to sRGB-encoded, tracking as accurate
    as before, and the OCIO transform recorded in the provenance."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import colour as ncol
    from st_roto import model as m
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 6
    r = nuke.root()
    res["nuke_mode"] = ncol.transform_id(ncol.resolve("auto"))
    r["colorManagement"].setValue("OCIO")
    r["OCIO_config"].setValue("fn-nuke_cg-config-v2.2.0_aces-v1.3_ocio-v2.4")
    r["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    res["read_colorspace"] = rd["colorspace"].value()
    res["working_space"] = r["workingSpaceLUT"].value()
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "col.stroto"))
    res["knob_default"] = g["stroto_colour"].value()
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]])
    job = stnode.on_track(g, background=False)
    res["status"] = g["stroto_status"].value()
    from st_roto_nuke import session
    store, _ = session.project(g["stroto_project"].value())
    sh = store.conn.execute("SELECT * FROM shapes").fetchone()
    gen = json.loads(sh["generator"])
    res["provenance_colour"] = gen["colour"]
    ious = []
    from st_roto.geometry import Anchor
    for k in store.keys(sh["id"]):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % k["frame"], cv2.IMREAD_GRAYSCALE) > 127
        ious.append(round(iou(rasterize_spline(a, vh, vw), gt), 4))
    res["iou_vs_gt"] = ious
    src_space = res["provenance_colour"].split("|")[-2] if res["provenance_colour"].startswith("ocio_v1:") else None
    return bool(res["nuke_mode"] == "linear_srgb_to_srgb_encoded_v0" and res["knob_default"] == "auto"
                and job is not None and job.status == "done" and src_space == res["working_space"]
                and len(ious) == n and min(ious) > 0.98)


def test_split_object_parts(res):
    """T-049: track across the occluder (frames 18-28; the object is cut in two around frame 23) with 'points' =
    auto. Extra pieces become part shapes; Nuke's own render of the ST_Roto output must match the truth on every
    frame, including the split frames (before T-049 frame 23 lost its second piece: IoU ~0.6)."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto import views, pieces
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh = meta["w"], meta["h"]
    f0, f1 = 18, 28
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=f0, last=f1)
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "split.stroto"))
    gt18 = cv2.imread(VIDEO + "/gt_%04d.png" % f0, cv2.IMREAD_GRAYSCALE) > 127
    ys, xs = np.nonzero(gt18)
    i = int(np.argmin((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2))              # a truth pixel near the centre
    nuke.frame(f0)
    g["stroto_click"].setValue([xs[i] + 0.5, vh - ys[i] - 0.5]); stnode.on_add_point(g, 1)
    res["anchors_knob"] = g["stroto_anchors"].value()
    job = stnode.on_track(g, background=False)
    res["status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, _ = session.project(g["stroto_project"].value())
    obj = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]
    main = views.main_shape(store, obj["id"])
    parts = views.part_shapes(store, main["id"])
    res["shapes"] = {"main_points": main["point_count"], "parts": [(p["name"], p["point_count"]) for p in parts]}
    res["part_real_frames"] = [sorted(k["frame"] for k in store.keys(p["id"]) if not pieces.is_collapsed(k["points"]))
                               for p in parts]
    w = nuke.nodes.Write(file=OUT + "/split.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)
    nuke.execute(w, f0, f1)
    ious = {}
    for f in range(f0, f1 + 1):
        img = cv2.imread(OUT + "/split.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        a = (img if img.ndim == 2 else img[:, :, -1]) > 0.5
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
        ious[f] = round(iou(a, gt), 4)
    res["roto_render_iou_vs_truth"] = ious
    real = set(f for fr in res["part_real_frames"] for f in fr)
    res["min_iou_split_frames"] = min(ious[f] for f in real) if real else None
    return bool(parts and real and min(ious.values()) > 0.95 and res["min_iou_split_frames"] > 0.95)


def test_cancel_and_resume_track(res):
    """T-048: a Track cancelled after 5 frames leaves a checkpoint and says how to resume; a changed colour setting
    refuses to resume; 'Resume track' finishes the run (one object, every frame, accurate) and removes it."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.track import read_checkpoint
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 12
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "resume.stroto")
    g = stnode.create(rd, proj)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    real_renderer = stnode._renderer
    calls = {"n": 0}

    def cancelling_renderer(ctx, background):
        inner = real_renderer(ctx, background)

        def get_rgb(f):
            calls["n"] += 1
            if calls["n"] == 6:
                stnode._JOBS[g.fullName()].cancel()          # what the Cancel button does, during frame 5
            return inner(f)
        return get_rgb
    stnode._renderer = cancelling_renderer
    j1 = stnode.on_track(g, background=False)
    stnode._renderer = real_renderer
    ck = stnode.checkpoint_dir(proj, rd.name())
    m = read_checkpoint(ck)
    res["after_cancel"] = {"job": j1.status, "status": g["stroto_status"].value(),
                           "checkpoint_next_frame": m and m["next_frame"]}
    ok = j1.status == "cancelled" and m is not None and m["next_frame"] == 6 and "Resume track" in res["after_cancel"]["status"]
    g["stroto_colour"].setValue("acescg_to_srgb_encoded_v1")
    j_bad = stnode.on_resume_track(g, background=False)
    res["refused"] = g["stroto_status"].value()
    ok &= j_bad is None and "changed" in res["refused"]
    g["stroto_colour"].setValue("auto")
    stnode.on_clear_points(g, every_object=True)                   # resuming does not need the node's prompts
    j2 = stnode.on_resume_track(g, background=False)
    res["resume_status"] = g["stroto_status"].value()
    store, _ = session.project(proj)
    objs = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])
    from st_roto import views
    main = views.main_shape(store, objs[0]["id"])
    ious = []
    for k in store.keys(main["id"]):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % k["frame"], cv2.IMREAD_GRAYSCALE) > 127
        ious.append(round(iou(rasterize_spline(a, vh, vw), gt), 4))
    res["objects"], res["iou_vs_gt"] = len(objs), ious
    ok &= (j2 is not None and j2.status == "done" and "(resumed)" in res["resume_status"] and len(objs) == 1
           and len(ious) == n and min(ious) > 0.98 and not os.path.exists(ck))
    return bool(ok)


def test_package_script_relink(res):
    """T-075: saved script + Track -> 'Package project' (includes the script) -> unpack elsewhere with the plates
    moved -> the unpacked script opens with its Read on the moved plates and ST_Roto on the unpacked project; the
    shot's fingerprint matches the moved plates; the shapes are in the unpacked project."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import shutil
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.packages import unpack_and_relink
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 3
    tmp = tempfile.mkdtemp().replace("\\", "/")
    work = tmp + "/work"; os.makedirs(work)
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = work + "/show.stroto"
    g = stnode.create(rd, proj)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    job = stnode.on_track(g, background=False)
    nuke.scriptSaveAs(work + "/show.nk", overwrite=1)
    store, _ = session.project(proj)
    shot = dict(store.conn.execute("SELECT * FROM shots").fetchone())
    res["fingerprint_recorded"] = bool(shot["source_fingerprint"])
    zp = stnode.on_package(g, tmp + "/pkg.zip")
    res["package_status"] = g["stroto_status"].value()
    moved = tmp + "/moved_plates"; os.makedirs(moved)
    for f in range(n):
        shutil.copyfile(VIDEO + "/frame_%04d.png" % f, moved + "/frame_%04d.png" % f)
    rep = unpack_and_relink(zp, tmp + "/job", lambda shot, miss: None, relink={VIDEO: moved})
    res["unpack"] = {"scripts": rep["scripts"], "fingerprints": rep["fingerprints"]}
    session.close_all()
    nuke.scriptClear()
    nuke.scriptOpen(rep["scripts"][0])
    from st_roto_nuke.packages import apply_relink_to_open_script
    res["encrypted_scripts"] = len(rep["encrypted_scripts"])
    res["relinked_in_script"] = apply_relink_to_open_script(script_path=rep["scripts"][0])["changed"]   # sidecar
    reads = [nd for nd in nuke.allNodes("Read")]
    groups = [nd for nd in nuke.allNodes("Group") if "stroto_project" in nd.knobs()]
    res["opened"] = {"read_file": reads[0]["file"].value() if reads else None,
                     "stroto_project": groups[0]["stroto_project"].value() if groups else None}
    t = ProjectStore(rep["project"])
    res["unpacked_keys"] = t.conn.execute("SELECT COUNT(*) FROM shape_keys").fetchone()[0]
    t.close()
    return bool(job is not None and job.status == "done" and res["fingerprint_recorded"]
                and "show.nk" in str(rep["scripts"]) and "SAVED" not in res["package_status"]
                and list(rep["fingerprints"].values()) == ["match"]
                and res["opened"]["read_file"] in (moved + "/frame_####.png", moved + "/frame_%04d.png")   # Nuke: %04d
                and os.path.normcase(os.path.abspath(res["opened"]["stroto_project"])) == os.path.normcase(os.path.abspath(rep["project"]))
                and res["unpacked_keys"] >= n)


def test_feather_and_rotopaint(res):
    """T-073: a hand-drawn shape with feather (fx=fy=12, ff=1) is imported with its feather; a feather change made
    in Roto is imported (undoable, undo syncs back); EXR mattes approximate Nuke's feather (error measured);
    'Copy shapes to RotoPaint' gives a RotoPaint node that renders like the Roto node."""
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape, read_feather
    from st_roto import exr
    from st_roto.geometry import mask_to_points
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=1)
    proj = os.path.join(tempfile.mkdtemp(), "fe.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    keys = {f: mask_to_points(150.0 - np.hypot(xx - (600 + 20 * f), yy - 360), count=12) for f in range(2)}
    curves.rootLayer.append(build_shape(curves, "soft", keys, H, (12.0, 12.0, 1.0)))
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "shot1", "name": rd.name(), "width": W, "height": H,
                                              "first_frame": 0, "last_frame": 1}})
    stnode.resync(g)
    sh = store.shapes(store.objects("shot1")[0]["id"])[0]
    res["imported_feather"] = (sh["feather_x"], sh["feather_y"], sh["feather_falloff"])
    ok = res["imported_feather"] == (12.0, 12.0, 1.0)
    item = [it for it in curves.rootLayer][0]
    a = item.getAttributes(); a.set("fx", 20.0); a.set("fy", 20.0)                    # artist edit in Roto
    r2 = stnode.resync(g)
    res["after_edit"] = store.row("shapes", sh["id"])["feather_x"]
    bus.undo()
    stnode.resync(g, import_first=False)
    res["roto_after_undo"] = read_feather([it for it in curves.rootLayer][0])
    ok &= res["after_edit"] == 20.0 and res["roto_after_undo"][0] == 12.0
    # mattes vs Nuke's own render of the same feathered shape
    g["stroto_soft"].setValue(False)
    jm = stnode.on_render_mattes(g, background=False)
    w = nuke.nodes.Write(file=OUT + "/fe.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)
    nuke.execute(w, 0, 1)
    errs = []
    for f in range(2):
        ours = exr.read_channels(jm.result["files"][f])["A"]
        img = cv2.imread(OUT + "/fe.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        nk = img if img.ndim == 2 else img[:, :, -1]
        band = (nk > 0.01) & (nk < 0.99) | (ours > 0.01) & (ours < 0.99)
        cx = 600 + 20 * f
        r50 = []
        for ang in np.radians(np.arange(0, 360, 10)):           # radius of the 50 % contour, Nuke vs ours
            rr = np.arange(130, 190, 0.25)
            x = np.clip((cx + rr * np.cos(ang)).astype(int), 0, W - 1); y = np.clip((360 + rr * np.sin(ang)).astype(int), 0, H - 1)
            r50.append(abs(rr[np.argmax(nk[y, x] < 0.5)] - rr[np.argmax(ours[y, x] < 0.5)]))
        errs.append({"band_px": int(band.sum()), "mean_abs": round(float(np.abs(ours - nk)[band].mean()), 4),
                     "max_abs": round(float(np.abs(ours - nk)[band].max()), 4),
                     "area_ratio": round(float(ours.sum() / nk.sum()), 4), "r50_max_diff_px": float(max(r50))})
    res["matte_vs_nuke_feather"] = errs
    # documented APPROXIMATION (st_roto.matte.feathered_alpha): area and 50 % contour match, tails differ
    ok &= all(e["mean_abs"] < 0.15 and abs(e["area_ratio"] - 1) < 0.01 and e["r50_max_diff_px"] <= 1.5 for e in errs)
    # RotoPaint copy renders like the Roto node
    rpn = stnode.on_copy_to_rotopaint(g)
    res["copy_status"] = g["stroto_status"].value()
    w2 = nuke.nodes.Write(file=OUT + "/rp.####.tif", file_type="tiff", channels="alpha")
    w2["datatype"].setValue("32 bit float"); w2["compression"].setValue("none"); w2.setInput(0, rpn)
    nuke.execute(w2, 0, 1)
    diffs = []
    for f in range(2):
        A = cv2.imread(OUT + "/rp.%04d.tif" % f, cv2.IMREAD_UNCHANGED); B = cv2.imread(OUT + "/fe.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        A = A if A.ndim == 2 else A[:, :, -1]; B = B if B.ndim == 2 else B[:, :, -1]
        diffs.append(round(float(np.abs(A - B).max()), 5))
    res["rotopaint_vs_roto_max_abs"] = diffs
    ok &= rpn is not None and max(diffs) < 1e-3
    return bool(ok)


def test_point_feather_roundtrip(res):
    """T-076: per-point feather (featherCenter keys) of a hand-drawn shape is imported; an edit in Roto is
    imported (undoable, undo writes it back); the RotoPaint copy renders identically (per-point feather kept)."""
    import nuke.rotopaint as rp
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import read_point_feather
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=1)
    proj = os.path.join(tempfile.mkdtemp(), "pf.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    sh = rp.Shape(curves)
    for x, y in ((500.0, 300.0), (700.0, 300.0), (700.0, 450.0), (500.0, 450.0)):
        cp = rp.ShapeControlPoint(x, y)
        for f in (0, 1):
            cp.center.addPositionKey(f, rp.CVec2(x + 10 * f, y))
        sh.append(cp)
    sh[1].featherCenter.addPositionKey(0, rp.CVec2(30.0, 30.0))       # point 1 feathered out on frame 0
    sh[1].featherCenter.addPositionKey(1, rp.CVec2(0.0, 0.0))
    sh.name = "pf"
    curves.rootLayer.append(sh)
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "shot1", "name": rd.name(), "width": W, "height": H,
                                              "first_frame": 0, "last_frame": 1}})
    stnode.resync(g)
    sid = store.shapes(store.objects("shot1")[0]["id"])[0]["id"]
    res["imported"] = store.feathers(sid)
    ok = sorted(res["imported"]) == [0, 1] and res["imported"][0][1][:2] == [30.0, -30.0]   # canonical y down
    item = [it for it in curves.rootLayer][0]
    item[1].featherCenter.addPositionKey(0, rp.CVec2(50.0, 0.0))     # artist edit in Roto
    stnode.resync(g)
    res["after_edit"] = store.feathers(sid)[0][1][:2]
    bus.undo()
    stnode.resync(g, import_first=False)
    res["roto_after_undo"] = read_point_feather([it for it in curves.rootLayer][0])[0][1][:2]
    ok &= res["after_edit"] == [50.0, 0.0] and res["roto_after_undo"] == [30.0, -30.0]
    rpn = stnode.on_copy_to_rotopaint(g)
    w1 = nuke.nodes.Write(file=OUT + "/pfr.####.tif", file_type="tiff", channels="alpha"); w1.setInput(0, g)
    w2 = nuke.nodes.Write(file=OUT + "/pfp.####.tif", file_type="tiff", channels="alpha"); w2.setInput(0, rpn)
    for w in (w1, w2):
        w["datatype"].setValue("32 bit float"); w["compression"].setValue("none")
    nuke.execute(w1, 0, 0); nuke.execute(w2, 0, 0)
    A = cv2.imread(OUT + "/pfr.0000.tif", cv2.IMREAD_UNCHANGED); B = cv2.imread(OUT + "/pfp.0000.tif", cv2.IMREAD_UNCHANGED)
    A = A if A.ndim == 2 else A[:, :, -1]; B = B if B.ndim == 2 else B[:, :, -1]
    res["soft_px_frame0"] = int(((A > 0.01) & (A < 0.99)).sum())
    res["rotopaint_vs_roto_max_abs"] = float(np.abs(A - B).max())
    ok &= res["soft_px_frame0"] > 500 and res["rotopaint_vs_roto_max_abs"] < 1e-3
    return bool(ok)


def test_vitmatte_mattes(res):
    """D-032: 'edges' = ViTMatte-S on the node -> EXR mattes via the optional model inside Nuke (verified by the
    registry), training-data caveat in the status, alpha soft only around the edge, interior/exterior exact."""
    if not os.path.exists(ROOT + "/models/onnx/vitmatte-small-composition-1k/vitmatte.onnx"):
        res["skipped"] = "ViTMatte-S not installed (optional)"; return True
    import st_roto_nuke.node as stnode
    from st_roto import exr
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 2
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "vm.stroto"))
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    stnode.on_track(g, background=False)
    g["stroto_edges"].setValue("ViTMatte-S (optional AI)")
    t0 = __import__("time").time()
    jm = stnode.on_render_mattes(g, background=False)
    res["seconds"] = round(__import__("time").time() - t0, 2)
    res["status"] = g["stroto_status"].value()
    ok = jm is not None and jm.status == "done" and "Composition-1k" in res["status"] and "ViTMatte-S edges" in res["status"]
    a = exr.read_channels(jm.result["files"][0])["A"]
    gt = cv2.imread(VIDEO + "/gt_0000.png", cv2.IMREAD_GRAYSCALE) > 127
    soft = (a > 0.02) & (a < 0.98)
    res["soft_px"] = int(soft.sum())
    res["meta_method"] = json.loads(__import__("OpenEXR").File(jm.result["files"][0]).header()["st_roto"])["method"]
    res["iou_vs_gt_at_0.5"] = round(iou(a > 0.5, gt), 4)
    ok &= res["meta_method"] == "vitmatte" and 0 < res["soft_px"] < 0.05 * a.size and res["iou_vs_gt_at_0.5"] > 0.97
    return bool(ok)


def test_box_prompt(res):
    """OQ-25/T-079: the in-viewer BBox knob -> 'Set box' -> a box-only prompt (no clicks) -> Preview and Track.
    Checks the knob's value format, the Nuke y-up -> canonical conversion, and tracking quality vs ground truth."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import prompts
    from st_roto_nuke import session
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 8
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "box.stroto")
    g = stnode.create(rd, proj)
    res["box_default"] = [float(v) for v in g["stroto_box"].value()]
    gt0 = cv2.imread(VIDEO + "/gt_0000.png", cv2.IMREAD_GRAYSCALE) > 127
    ys, xs = np.nonzero(gt0)
    x0, y0, x1, y1 = xs.min() - 4.0, ys.min() - 4.0, xs.max() + 5.0, ys.max() + 5.0   # canonical, y down
    g["stroto_object"].setValue("target")
    nuke.frame(0)
    g["stroto_box"].setValue([x0, vh - y1, x1, vh - y0])                 # Nuke y-up: (x, y, r, t)
    stnode.on_set_box(g)
    res["points_info"] = g["stroto_points_info"].value()
    o = prompts.objects_for_tracker(g["stroto_points"].value(), "target")[0]
    res["stored"] = {"points": o["points"], "labels": o["labels"]}
    ok = (o["labels"] == [2, 3] and np.allclose(o["points"], [(x0, y0), (x1, y1)])
          and res["points_info"].startswith("frame 0: box") and len(res["box_default"]) == 4
          and res["box_default"][2] > res["box_default"][0])
    jp = stnode.on_preview(g, background=False)
    res["preview_status"] = g["stroto_status"].value()
    ok &= jp is not None and jp.status == "done" and "object found" in res["preview_status"]
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    obj = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]
    sid = store.shapes(obj["id"])[0]["id"]
    q = {}
    for k in store.keys(sid):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % k["frame"], cv2.IMREAD_GRAYSCALE) > 127
        q[k["frame"]] = round(iou(rasterize_spline(a, vh, vw), gt), 4)
    res["iou"] = q
    ok &= sorted(q) == list(range(n)) and min(q.values()) > 0.97
    return bool(ok)


def test_reprompt_here(res):
    """T-081: a track that follows the WRONG object (box on the distractor disc) is fixed by 'Re-prompt here' with a
    box around the target on frame 6: frames 6-11 then follow the target; the fix is stored in the shape generator
    and kept by a later plain Re-track; the re-prompt is one undo step."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import views
    from st_roto_nuke import session
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n, fx = meta["w"], meta["h"], 12, 6
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "reprompt.stroto")
    g = stnode.create(rd, proj)
    yy, xx = np.mgrid[0:vh, 0:vw] + 0.5
    tgt_gt = lambda f: cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127

    def disc_gt(f):
        s = f / 47.0
        return (np.hypot(xx - (1050 - 600 * s), yy - (560 - 120 * np.sin(np.pi * s))) <= 85) & ~tgt_gt(f)

    def set_box(mask):
        ys, xs = np.nonzero(mask)
        g["stroto_box"].setValue([xs.min() - 4.0, vh - (ys.max() + 5.0), xs.max() + 5.0, vh - (ys.min() - 4.0)])

    g["stroto_object"].setValue("target")
    nuke.frame(0)
    set_box(disc_gt(0))                                       # the artist boxes the wrong thing
    stnode.on_set_box(g)
    job = stnode.on_track(g, background=False)
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    oid = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]["id"]
    sid = views.main_shape(store, oid)["id"]

    def target_iou():
        out = {}
        for k in store.keys(sid):
            a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
            out[k["frame"]] = round(iou(rasterize_spline(a, vh, vw), tgt_gt(k["frame"])), 4)
        return out

    res["before"] = target_iou()
    nuke.frame(fx)
    set_box(tgt_gt(fx))
    j2 = stnode.on_reprompt_here(g, background=False)
    res["reprompt_status"] = g["stroto_status"].value()
    if j2 is None or j2.status != "done":
        res["error"] = (j2.error if j2 else "no job") + " | " + res["reprompt_status"]; return False
    res["after"] = target_iou()
    gen = json.loads(store.row("shapes", sid)["generator"])
    res["fixes"] = gen.get("fixes")
    ok = (max(res["before"][f] for f in range(fx, n)) < 0.5
          and min(res["after"][f] for f in range(fx, n)) > 0.95
          and res["reprompt_status"].startswith("re-prompted frame %d" % fx)
          and [x["frame"] for x in res["fixes"] or []] == [fx] and res["fixes"][0]["labels"] == [2, 3])
    stnode.resync(g, import_first=False)
    j3 = stnode.on_retrack(g, background=False)               # plain re-track keeps the stored fix
    res["retrack_status"] = g["stroto_status"].value()
    res["after_plain_retrack"] = target_iou()
    ok &= j3 is not None and j3.status == "done" and min(res["after_plain_retrack"][f] for f in range(fx, n)) > 0.95
    ok &= [x["frame"] for x in json.loads(store.row("shapes", sid)["generator"]).get("fixes", [])] == [fx]
    bus.undo(); bus.undo()                                    # plain re-track, then the re-prompt: one step each
    res["after_undo"] = target_iou()
    ok &= res["after_undo"] == res["before"] and "fixes" not in json.loads(store.row("shapes", sid)["generator"])
    return bool(ok)


def test_difficult_sequences(res):
    """T-086 / REQ-092: a sequence with missing frames (4-5) and half-resolution frames (7-9) tracks instead of
    failing: no keys on the missing frames, every key on target (the half-res frames fitted to the shot format),
    both reported; then Re-track in PROXY mode (before T-086: 'You must specify a proxy file name') works."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import shutil
    import st_roto_nuke.node as stnode
    from st_roto import views
    from st_roto_nuke import session
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 10
    seq = tempfile.mkdtemp().replace("\\", "/")
    for f in range(n):
        if f in (4, 5):
            continue
        if f >= 7:
            img = cv2.imread(VIDEO + "/frame_%04d.png" % f)
            cv2.imwrite(seq + "/frame_%04d.png" % f, cv2.resize(img, (vw // 2, vh // 2), interpolation=cv2.INTER_AREA))
        else:
            shutil.copyfile(VIDEO + "/frame_%04d.png" % f, seq + "/frame_%04d.png" % f)
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=seq + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "seq.stroto")
    g = stnode.create(rd, proj)
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, _ = session.project(proj)
    oid = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]["id"]
    sid = views.main_shape(store, oid)["id"]

    def ious():
        out = {}
        for k in store.keys(sid):
            a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
            gt = cv2.imread(VIDEO + "/gt_%04d.png" % k["frame"], cv2.IMREAD_GRAYSCALE) > 127
            out[k["frame"]] = round(iou(rasterize_spline(a, vh, vw), gt), 4)
        return out
    res["track_iou"] = ious()
    ok = (sorted(res["track_iou"]) == [0, 1, 2, 3, 6, 7, 8, 9] and min(res["track_iou"].values()) > 0.98
          and "2 unreadable frame(s) skipped (no key): 4-5" in res["track_status"]
          and "3 frame(s) at another resolution (640x360)" in res["track_status"])
    nuke.root()["proxy_type"].setValue("scale"); nuke.root()["proxy_scale"].setValue(0.5)
    nuke.root()["proxy"].setValue(True)
    j2 = stnode.on_retrack(g, background=False)
    res["proxy_retrack_status"] = g["stroto_status"].value()
    nuke.root()["proxy"].setValue(False)
    res["proxy_retrack_iou"] = ious()
    ok &= (j2 is not None and j2.status == "done" and "proxy mode is on" in res["proxy_retrack_status"]
           and min(res["proxy_retrack_iou"].values()) > 0.97 and sorted(res["proxy_retrack_iou"]) == sorted(res["track_iou"]))
    return bool(ok)


def test_traditional_roto_without_ai(res):
    """T-088 / REQ-010 (master prompt section 3): a whole shot done with AI unavailable and switched off. ONNX
    Runtime is made unimportable (as on a machine without the AI runtime); AI buttons refuse with a clear message
    (no runtime, then 'disable AI' ticked, which also hides them); a hand-drawn animated shape in the node's Roto is
    saved to the project WITHOUT any prior Track (before T-088 it was silently not recorded), then guided-filter
    and hard mattes, ViTMatte refused, JSON/SVG export, RotoPaint copy, backup and package all work, and no AI
    module is ever imported."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    sys.modules["onnxruntime"] = None                         # 'not installed': any import raises ImportError
    import st_roto_nuke.node as stnode
    from st_roto import exr
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 3
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "manual.stroto")
    g = stnode.create(rd, proj)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    res["track_without_runtime"] = (stnode.on_track(g, background=False), g["stroto_status"].value())
    ok = res["track_without_runtime"][0] is None and "not installed" in res["track_without_runtime"][1]
    g["stroto_ai_off"].setValue(True)
    stnode.apply_ai_visibility(g)                             # what the knobChanged callback does in the GUI
    res["ai_knobs_visible"] = [k for k in stnode.AI_KNOBS if g[k].visible()]
    res["preview_when_off"] = (stnode.on_preview(g, background=False), g["stroto_status"].value())
    ok &= (res["ai_knobs_visible"] == [] and res["preview_when_off"][0] is None
           and "disabled on this node" in res["preview_when_off"][1])
    # the artist draws an animated shape by hand in the node's Roto (here: from the truth masks), then saves it
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    gt = {f: cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127 for f in range(n)}
    keys = {f: mask_to_points(gt[f].astype(float) - 0.5, count=16) for f in range(n)}
    curves.rootLayer.append(build_shape(curves, "hero", keys, vh))
    stnode.on_import_edits(g)
    res["save_status"] = g["stroto_status"].value()
    store, bus = session.project(proj)
    shot = store.conn.execute("SELECT id FROM shots").fetchone()
    objs = store.objects(shot["id"]) if shot else []
    sid = store.shapes(objs[0]["id"])[0]["id"] if objs else None
    res["saved"] = {"objects": [o["name"] for o in objs],
                    "keys": sorted(k["frame"] for k in store.keys(sid)) if sid else [],
                    "origins": sorted({k["origin"] for k in store.keys(sid)}) if sid else []}
    ok &= res["saved"] == {"objects": ["hero"], "keys": [0, 1, 2], "origins": ["artist_created"]}
    for edges in ("guided filter", "hard"):
        g["stroto_edges"].setValue(edges)
        jm = stnode.on_render_mattes(g, background=False)
        a = exr.read_channels(jm.result["files"][1])["A"] if jm is not None and jm.status == "done" else None
        res["mattes_" + edges] = (g["stroto_status"].value()[:120],
                                  None if a is None else round(iou(a > 0.5, gt[1]), 4))
        ok &= a is not None and iou(a > 0.5, gt[1]) > 0.97
    g["stroto_edges"].setValue("ViTMatte-S (optional AI)")
    res["vitmatte_when_off"] = (stnode.on_render_mattes(g, background=False), g["stroto_status"].value())
    ok &= res["vitmatte_when_off"][0] is None and "need AI" in res["vitmatte_when_off"][1]
    out = stnode.on_export_shapes(g)
    rp = stnode.on_copy_to_rotopaint(g)
    bk = stnode.on_backup(g)
    zp = stnode.on_package(g, os.path.join(tmp, "manual_pkg.zip"))
    res["export_ok"], res["rotopaint_ok"] = out is not None and os.path.exists(out["json"]), rp is not None
    res["backup_ok"], res["package_ok"] = bk is not None, zp is not None and os.path.exists(zp)
    ok &= res["export_ok"] and res["rotopaint_ok"] and res["backup_ok"] and res["package_ok"]
    # the empty st_roto_ai package itself is imported by the runtime probe of the first refused Track; no AI code
    # (runtime, tracker, matting) and no AI library may ever be loaded
    res["ai_modules_loaded"] = sorted(m for m in sys.modules if sys.modules[m] is not None and (
        m.split(".")[0] in ("onnxruntime", "torch", "transformers") or (m.startswith("st_roto_ai.") and m != "st_roto_ai")))
    ok &= res["ai_modules_loaded"] == []
    return bool(ok)


def test_plate_above_render_limit(res):
    """T-089 / REQ-111: a UHD (3840x2160) plate in Nuke Non-commercial, whose renders are capped at 1920x1080.
    Before T-089 Track failed ('bounding box exceeds the maximum resolution'); now the AI sees frames reduced into
    the allowed box through the node's STROTO_pixel_fit Reformat (enabled only around each render) and the shapes
    are at full resolution."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import views
    from st_roto_nuke import session
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    W, H, n, s = 3840, 2160, 3, 3.0
    seq = tempfile.mkdtemp().replace("\\", "/")
    gts = {}
    for f in range(n):
        cv2.imwrite(seq + "/frame_%04d.png" % f, cv2.resize(cv2.imread(VIDEO + "/frame_%04d.png" % f), (W, H)))
        gts[f] = cv2.resize(cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE), (W, H),
                            interpolation=cv2.INTER_NEAREST) > 127
    rd = nuke.nodes.Read(file=seq + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "uhd.stroto")
    g = stnode.create(rd, proj)
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([meta["click_xy"][0] * s, H - meta["click_xy"][1] * s]); stnode.on_add_point(g, 1)
    job = stnode.on_track(g, background=False)
    res["status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, _ = session.project(proj)
    oid = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]["id"]
    sid = views.main_shape(store, oid)["id"]
    res["key_iou"] = {}
    for k in store.keys(sid):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k["points"]]
        res["key_iou"][k["frame"]] = round(iou(rasterize_spline(a, H, W), gts[k["frame"]]), 4)
    fit = stnode._INNER[g.fullName()].get("fit")
    res["fit_disabled_after"] = bool(fit is not None and fit["disable"].value())
    ok = (sorted(res["key_iou"]) == list(range(n)) and min(res["key_iou"].values()) > 0.99
          and "frames reduced to 1920x1080 (from 3840x2160)" in res["status"] and res["fit_disabled_after"])
    # D-041: in Non-commercial the matte size defaults to 'fit 1920x1080'; hard mattes come out 1920x1080
    from st_roto import exr
    res["matte_size_default"] = g["stroto_matte_size"].value()
    g["stroto_edges"].setValue("hard")
    jm = stnode.on_render_mattes(g, background=False)
    res["matte_status"] = g["stroto_status"].value()[:200]
    a = exr.read_channels(jm.result["files"][1])["A"] if jm is not None and jm.status == "done" else None
    res["matte_shape"] = None if a is None else [a.shape[1], a.shape[0]]
    if a is not None:
        gt_small = cv2.resize(gts[1].astype(np.float32), (1920, 1080), interpolation=cv2.INTER_AREA) > 0.5
        res["matte_iou"] = round(iou(a > 0.5, gt_small), 4)
    ok &= (res["matte_size_default"] == ("fit 1920x1080" if nuke.env.get("nc") else "full resolution")
           and res["matte_shape"] == ([1920, 1080] if nuke.env.get("nc") else [W, H])
           and res.get("matte_iou", 0) > 0.99)
    return bool(ok)


def test_system_report(res):
    """T-091 / REQ-020, REQ-022: the node's 'System report' in real Nuke on this machine: edition, GPU, AI runtime
    and models detected; edition limits reported as limited/unavailable with reasons; with 'disable AI' ticked the
    AI features are reported unavailable with the reason; never raises."""
    import st_roto_nuke.node as stnode
    from st_roto_nuke import capabilities as ncap
    from st_roto import capabilities as cap
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=1)
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "rep.stroto"))
    f, feats, text = ncap.report(g)
    res["facts"] = {k: v for k, v in f.items() if k != "ram"}
    res["features"] = {x["feature"]: x["status"] for x in feats}
    res["text"] = text
    st = res["features"]
    ok = (f["edition"] == ("nc" if nuke.env.get("nc") else f["edition"]) and f["gpus"] and "cuda" in f["providers"]
          and st.get("AI tracking (SAM 2.1)") == cap.AVAILABLE and st.get("GPU acceleration (CUDA)") == cap.AVAILABLE
          and all(x["reason"] for x in feats))
    if nuke.env.get("nc"):
        ok &= (st.get("Python node access") == cap.LIMITED
               and st.get("Rendering ST_Roto output above 1920x1080") == cap.UNAVAILABLE)
    shown = ncap.show_report(g)                               # what the node button runs (prints headless)
    res["status_after_button"] = g["stroto_status"].value()
    ok &= shown.startswith("ST-ROTO system report") and res["status_after_button"].startswith("system report:")
    g["stroto_ai_off"].setValue(True)
    _, feats_off, _ = ncap.report(g)
    ai = [x for x in feats_off if x["feature"].startswith("AI tracking")][0]
    res["ai_off"] = ai
    ok &= ai["status"] == cap.UNAVAILABLE and "disabled" in ai["reason"]
    return bool(ok)


def test_memory_aware_model(res):
    """T-092 / REQ-021: (1) model 'auto' picks what the measured-need rule says for the GPU memory free now and
    tracks with it; (2) fault injection: ONNX Runtime's CUDA pool capped at 200 MiB -> a real out-of-memory error
    -> Track and Re-track finish on the CPU, saying so."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import capabilities as cap
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 3
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "mem.stroto"))
    g["stroto_model"].setValue(stnode.AUTO_MODEL)
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    free = cap.gpu_info()["gpus"][0]["free_mib"]
    expected = cap.plan_model(stnode.AUTO_MODEL, "auto", free, {"sam2.1-hiera-tiny": True, "sam2.1-hiera-large": True},
                              auto_choice=stnode.AUTO_MODEL)
    job = stnode.on_track(g, background=False)
    res["free_mib"], res["expected"] = free, expected
    res["auto_status"] = g["stroto_status"].value()
    ok = (job is not None and job.status == "done" and ("auto model: %s" % expected[0]) in res["auto_status"]
          and ("device cuda" in res["auto_status"]) == (expected[1] != "cpu"))
    # fault injection: cap the CUDA pool so the next sessions cannot allocate
    from st_roto_ai import runtime
    stnode._release_gpu_sessions()
    runtime.set_cuda_memory_limit(200)
    g["stroto_model"].setValue("sam2.1-hiera-tiny")
    g["stroto_object"].setValue("disc"); nuke.frame(0)
    g["stroto_click"].setValue([1050.0, vh - 560.0]); stnode.on_add_point(g, 1)
    j2 = stnode.on_track(g, background=False)
    res["oom_track_status"] = g["stroto_status"].value()
    ok &= (j2 is not None and j2.status == "done" and "ran out of memory" in res["oom_track_status"]
           and "device cpu" in res["oom_track_status"])
    g["stroto_object"].setValue("target")
    j3 = stnode.on_retrack(g, background=False)
    res["oom_retrack_status"] = g["stroto_status"].value()
    ok &= j3 is not None and j3.status == "done" and "ran out of memory; re-tracked on the CPU" in res["oom_retrack_status"]
    runtime.set_cuda_memory_limit(None)
    return bool(ok)


def test_retrack_flagged_large(res):
    """T-093: 'Re-track flagged' with re-track model = large. Setup as test_review_flags_reverse (hand-drawn key on
    frame 47, tiny re-track loses the object around the occluder) plus a cleanly tracked second object. Only the
    flagged object is re-tracked, with the large model; lost frames and IoU before/after are recorded."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points, Anchor
    from st_roto import views
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, vw, n = meta["h"], meta["w"], meta["frames"]
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "flag.stroto")
    g = stnode.create(rd, proj)
    g["stroto_object"].setValue("disc"); nuke.frame(0)                    # second object: tracks cleanly
    g["stroto_click"].setValue([1050.0, vh - 560.0]); stnode.on_add_point(g, 1)
    stnode.on_track(g, background=False)
    res["disc_status"] = g["stroto_status"].value()
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    gt47 = cv2.imread(VIDEO + "/gt_%04d.png" % 47, cv2.IMREAD_GRAYSCALE) > 127
    curves.rootLayer.append(build_shape(curves, "drawn", {47: mask_to_points(gt47.astype(float) - 0.5, count=16)}, vh))
    nuke.frame(47)
    store, bus = session.project(proj)
    stnode.resync(g)
    shot_id = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    obj = [o for o in store.objects(shot_id) if o["name"] != "disc"][0]
    disc = [o for o in store.objects(shot_id) if o["name"] == "disc"][0]
    g["stroto_object"].setValue(obj["name"])
    stnode.on_retrack(g, background=False)                               # tiny ('same as model')
    res["tiny_status"] = g["stroto_status"].value()
    sid = views.main_shape(store, obj["id"])["id"]

    def state():
        lost = sorted(f for f, lvl, _ in views.review_for_object(store, obj["id"]) if lvl == "lost")
        ious = {}
        for k in store.keys(sid):
            if 10 <= k["frame"] <= 26:
                a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False)
                     for p in k["points"]]
                gt = cv2.imread(VIDEO + "/gt_%04d.png" % k["frame"], cv2.IMREAD_GRAYSCALE) > 127
                ious[k["frame"]] = round(iou(rasterize_spline(a, vh, vw), gt), 4)
        return lost, ious
    res["tiny_lost"], res["tiny_iou_10_26"] = state()
    res["disc_flags"] = [x for x in views.review_for_object(store, disc["id"]) if x[1] == "lost"]
    disc_keys_before = {k["frame"]: k["points"] for k in store.keys(views.main_shape(store, disc["id"])["id"])}
    g["stroto_retrack_model"].setValue("sam2.1-hiera-large")
    j = stnode.on_retrack(g, background=False, every_object=True, flagged_only=True)
    res["large_status"] = g["stroto_status"].value()
    res["large_lost"], res["large_iou_10_26"] = state()
    disc_keys_after = {k["frame"]: k["points"] for k in store.keys(views.main_shape(store, disc["id"])["id"])}
    t, l = res["tiny_iou_10_26"], res["large_iou_10_26"]
    res["mean_iou_10_26"] = {"tiny": round(float(np.mean(list(t.values()))), 4) if t else None,
                             "large": round(float(np.mean(list(l.values()))), 4) if l else None}
    return bool(j is not None and j.status == "done" and res["tiny_lost"] and not res["disc_flags"]
                and "model sam2.1-hiera-large" in res["large_status"]
                and "disc (no REVIEW lost flags)" in res["large_status"] and disc_keys_after == disc_keys_before)


def test_collaboration_ui(res):
    """T-094 / REQ-170/171: the collaboration actions the object panel calls (st_roto_nuke.collab) in real Nuke, with a
    throw-away key folder (ST_ROTO_KEY_DIR) and simulated co-workers bob (artist) and carol (supervisor) on the same
    project: role bootstrap, key set-up (later changes signed, reopened sessions sign automatically), take/release,
    a lease held by bob refuses alice, supervisor override refused while bob is active and allowed (with evidence)
    after 15 min idle, non-supervisor override refused, history verifies."""
    import datetime
    from st_roto.commands import CommandBus as Bus
    from st_roto import leases, signing
    from st_roto_nuke import collab, session
    keydir = tempfile.mkdtemp()
    os.environ["ST_ROTO_KEY_DIR"] = keydir
    os.environ["USERNAME"] = "alice"
    proj = os.path.join(tempfile.mkdtemp(), "collab.stroto")
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "Read1", "width": 64, "height": 48}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
    res["me"], res["key_before"] = collab.me(proj), collab.key_state(proj)
    collab.set_role(proj, "alice", "admin")
    res["setup"] = collab.setup_key(proj)
    res["key_file"] = os.path.exists(os.path.join(keydir, "alice.strotokey"))
    collab.take(proj, "O")
    last = store.conn.execute("SELECT signature FROM operations ORDER BY seq DESC LIMIT 1").fetchone()
    res["take_signed"] = bool(last["signature"])
    res["held_after_take"] = collab.lease_text(store.conn, "O", "alice")
    collab.release(proj, "O")
    res["held_after_release"] = collab.lease_text(store.conn, "O", "alice")
    ok = (res["me"] == "alice" and res["key_before"] == "none" and res["setup"] == ("registered", True)
          and res["key_file"] and res["take_signed"] and res["held_after_take"] == "you" and res["held_after_release"] == "")
    collab.set_role(proj, "bob", "artist"); collab.set_role(proj, "carol", "supervisor")
    bob, carol = Bus(store, author="bob"), Bus(store, author="carol")
    leases.heartbeat(store, "bob", activity="painting")
    leases.acquire(bob, "O")
    res["held_by_bob"] = collab.lease_text(store.conn, "O", "alice")
    try:
        collab.take(proj, "O"); res["alice_take"] = "allowed"
    except Exception as e:
        res["alice_take"] = str(e)
    try:
        leases.override(carol, "O"); res["override_active"] = "allowed"
    except Exception as e:
        res["override_active"] = str(e)
    past = datetime.datetime.utcnow() - datetime.timedelta(minutes=20)
    leases.heartbeat(store, "bob", now=past)
    res["held_idle"] = collab.lease_text(store.conn, "O", "alice")
    try:
        collab.override(proj, "O"); res["alice_override"] = "allowed"
    except Exception as e:
        res["alice_override"] = str(e)
    leases.override(carol, "O")
    payload = json.loads(store.conn.execute("SELECT payload FROM operations ORDER BY seq DESC LIMIT 1").fetchone()["payload"])
    res["override_evidence"] = payload.get("evidence")
    res["held_after_override"] = collab.lease_text(store.conn, "O", "alice")
    res["status_line"] = collab.status_line(proj)
    res["verify"] = signing.verify_log(store)
    ok &= (res["held_by_bob"] == "bob" and "leased by bob" in res["alice_take"]
           and "after 15 min" in res["override_active"] and res["held_idle"].startswith("bob (idle 20 min)")
           and "only a supervisor" in res["alice_override"] and res["override_evidence"]
           and res["override_evidence"]["holder"] == "bob"
           and res["held_after_override"] == "carol (offline)"        # simulated carol sent no heartbeat
           and "alice (admin)" in res["status_line"] and "key registered" in res["status_line"]
           and "collaboration on" in res["status_line"] and res["verify"]["bad"] == [] and res["verify"]["signed"] >= 3)
    session.close(proj)                                       # reopen: alice's key is picked up automatically
    store2, bus2 = session.project(proj)
    res["signer_after_reopen"] = bus2.signer is not None
    ok &= res["signer_after_reopen"] and collab.key_state(proj) == "registered"
    return bool(ok)


def test_propagation_controls(res):
    """T-097 / REQ-091: Lock range, exclude frames and range-limited re-track. Track (tiny) -> lock 5-7, exclude
    12-13, Re-track with the LARGE model (so changed frames get different points): locked and excluded keys stay
    byte-identical, most others change, locked frames are listed as guides. Then re-track only 15-19 (tiny): every key
    outside 15-19 identical, inside on target; one undo restores; Unlock range clears the lock."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto import views
    from st_roto.geometry import Anchor
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, vw, n = meta["h"], meta["w"], 30
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "prop.stroto")
    g = stnode.create(rd, proj)
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    stnode.on_track(g, background=False)
    store, bus = session.project(proj)
    oid = store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"])[0]["id"]
    sid = views.main_shape(store, oid)["id"]
    keys = lambda: {k["frame"]: k["points"] for k in store.keys(sid)}           # noqa: E731
    k0 = keys()
    # an artist key too (frame 25): artist keys and locked keys must coexist as guides (regression: int-key merge)
    from st_roto.geometry import mask_to_points
    gt25 = cv2.imread(VIDEO + "/gt_%04d.png" % 25, cv2.IMREAD_GRAYSCALE) > 127
    bus.execute({"op": "set_key", "shape_id": sid, "frame": 25, "points": mask_to_points(gt25.astype(float) - 0.5,
                 count=len(k0[25]))}, actor="artist")
    stnode.resync(g, import_first=False)
    k0 = keys()
    g["stroto_range_from"].setValue(5); g["stroto_range_to"].setValue(7)
    res["locked"] = stnode.on_lock_range(g, True)
    g["stroto_exclude"].setValue("12-13")
    g["stroto_retrack_model"].setValue("sam2.1-hiera-large")
    stnode.on_retrack(g, background=False)
    res["retrack_status"] = g["stroto_status"].value()
    k1 = keys()
    k10 = [k for k in store.keys(sid) if k["frame"] == 10][0]               # re-track record lives on its keys
    res["guide_frames"] = json.loads(k10["generator"])["retrack"].get("guide_frames")
    res["unchanged_after_large"] = sorted(f for f in k1 if k1[f] == k0.get(f))
    ok = (res["locked"] == [5, 6, 7] and all(k1[f] == k0[f] for f in (5, 6, 7, 12, 13, 25))
          and len(res["unchanged_after_large"]) <= 8 and res["guide_frames"] == [5, 6, 7]
          and "excluded by you (not processed, keys unchanged): 12-13" in res["retrack_status"])
    # range-limited re-track 15-19 with tiny
    g["stroto_exclude"].setValue("")
    g["stroto_retrack_model"].setValue("same as model")
    g["stroto_range_mode"].setValue("from-to")
    g["stroto_range_from"].setValue(15); g["stroto_range_to"].setValue(19)
    stnode.on_retrack(g, background=False)
    res["range_status"] = g["stroto_status"].value()
    k2 = keys()
    res["changed_by_range"] = sorted(f for f in k2 if k2[f] != k1.get(f))
    ious = {}
    for f in range(15, 20):
        a = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in k2[f]]
        gt = cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
        ious[f] = round(iou(rasterize_spline(a, vh, vw), gt), 4)
    res["range_iou"] = ious
    ok &= (set(res["changed_by_range"]) <= set(range(15, 20)) and len(res["changed_by_range"]) >= 3
           and min(ious.values()) > 0.98 and "frames 15-19 only (keys outside unchanged)" in res["range_status"])
    # DEF-008: Re-prompt on a locked frame names the lock (not 'your own key')
    g["stroto_range_mode"].setValue("whole shot")
    nuke.frame(6)
    g["stroto_box"].setValue([200.0, 200.0, 500.0, 500.0])
    stnode.on_reprompt_here(g, background=False)
    res["reprompt_locked_status"] = g["stroto_status"].value()
    ok &= "is locked: press Unlock range" in res["reprompt_locked_status"]
    bus.undo()
    res["undo_restores"] = keys() == k1
    g["stroto_range_from"].setValue(0); g["stroto_range_to"].setValue(29)
    res["unlocked"] = stnode.on_lock_range(g, False)
    ok &= res["undo_restores"] and res["unlocked"] == [] and "locked_frames" not in json.loads(
        store.row("shapes", sid)["generator"])
    return bool(ok)


def test_roles_and_merge(res):
    """T-098 / REQ-082, REQ-100: hand-drawn objects 'actor' (the target), 'pole' (holdout, crosses the actor) and
    'area' (garbage, covers only the left part of the actor). After Set role, NUKE's own render of the node and
    ST-ROTO's EXR combined matte agree (both: actor minus pole, only inside area); the holdout/garbage shapes are on
    top of the Roto layer with blend 'minus' (+ inverted for garbage). Merge pole into actor (one undo step): the
    pole shape becomes part of the actor (no longer cut out); undo restores the holdout."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    from st_roto import exr, views
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, vw, n = meta["h"], meta["w"], 2
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "roles.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    yy, xx = np.mgrid[0:vh, 0:vw] + 0.5
    gt = {f: cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127 for f in range(n)}
    ys, xs = np.nonzero(gt[0]); cx, cy = float(np.median(xs)), float(np.median(ys))
    pole = {f: (np.abs(xx - cx) < 25) & (np.abs(yy - cy) < 220) for f in range(n)}            # vertical bar
    area = {f: np.hypot(xx - (cx - 60), yy - cy) < 110 for f in range(n)}                    # left part only
    for name, masks, cnt in (("actor", gt, 32), ("pole", pole, 16), ("area", area, 24)):
        curves.rootLayer.append(build_shape(curves, name, {f: mask_to_points(masks[f].astype(float) - 0.5, count=cnt)
                                                             for f in range(n)}, vh))
    nuke.frame(0)
    stnode.on_import_edits(g)
    store, bus = session.project(proj)
    names = sorted(o["name"] for o in store.objects(store.conn.execute("SELECT id FROM shots").fetchone()["id"]))
    res["objects"] = names
    for obj, role in (("pole", "holdout"), ("area", "garbage")):
        g["stroto_object"].setValue(obj); g["stroto_role"].setValue(role)
        stnode.on_set_role(g)
    res["role_status"] = g["stroto_status"].value()
    items = [it for it in curves.rootLayer]
    res["layer_order"] = [it.name.split("_st")[0] for it in items]
    res["blend"] = {it.name.split("_st")[0]: (it.getAttributes().getValue(0, "bm"), it.getAttributes().getValue(0, "inv"))
                    for it in items}
    g["stroto_edges"].setValue("hard")
    jm = stnode.on_render_mattes(g, background=False)
    w = nuke.nodes.Write(file=OUT + "/roles.####.tif", file_type="tiff", channels="alpha")
    w["datatype"].setValue("32 bit float"); w["compression"].setValue("none"); w.setInput(0, g)

    def nuke_alpha(f):
        nuke.execute(w, f, f)
        img = cv2.imread(OUT + "/roles.%04d.tif" % f, cv2.IMREAD_UNCHANGED)
        return (img if img.ndim == 2 else img[:, :, -1])
    expect = gt[0] & ~pole[0] & area[0]
    na = nuke_alpha(0)
    ea = exr.read_channels(jm.result["files"][0])["A"]
    res["nuke_min_max"] = [float(na.min()), float(na.max())]
    res["iou_nuke_vs_exr"] = round(iou(na > 0.5, ea > 0.5), 4)
    res["iou_nuke_vs_expected"] = round(iou(na > 0.5, expect), 4)
    res["iou_exr_vs_expected"] = round(iou(ea > 0.5, expect), 4)
    ok = (names == ["actor", "area", "pole"] and set(res["layer_order"][:2]) == {"pole", "area"}
          and res["blend"]["pole"] == (12.0, 0.0) and res["blend"]["area"] == (12.0, 1.0)
          and res["blend"]["actor"] == (0.0, 0.0) and res["nuke_min_max"][0] >= 0.0 and res["nuke_min_max"][1] <= 1.0
          and res["iou_nuke_vs_exr"] > 0.99 and res["iou_nuke_vs_expected"] > 0.98 and res["iou_exr_vs_expected"] > 0.98)
    # merge pole into actor: no longer a holdout
    shot_id = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    by = {o["name"]: o["id"] for o in store.objects(shot_id)}
    bus.execute({"op": "batch", "ops": views.merge_ops(store, by["pole"], by["actor"])})
    stnode.resync(g, import_first=False)
    res["after_merge_objects"] = sorted(o["name"] for o in store.objects(shot_id))
    na2 = nuke_alpha(1)
    res["iou_after_merge"] = round(iou(na2 > 0.5, (gt[1] | pole[1]) & area[1]), 4)
    bus.undo()
    stnode.resync(g, import_first=False)
    res["after_undo_objects"] = sorted(o["name"] for o in store.objects(shot_id))
    res["pole_role_after_undo"] = [o["role"] for o in store.objects(shot_id) if o["name"] == "pole"]
    na3 = nuke_alpha(0)
    res["iou_after_undo"] = round(iou(na3 > 0.5, expect), 4)
    ok &= (res["after_merge_objects"] == ["actor", "area"] and res["iou_after_merge"] > 0.98
           and res["after_undo_objects"] == ["actor", "area", "pole"] and res["pole_role_after_undo"] == ["holdout"]
           and res["iou_after_undo"] > 0.98)
    return bool(ok)


def test_matte_outputs(res):
    """T-099 / REQ-100, REQ-101: 'RGB in mattes' premultiplied + core/edge layers + edge blur, read back BY NUKE:
    channels rgba.red/green/blue/alpha, core_matte.alpha, edge_matte.alpha; red = Nuke's own plate red x alpha at
    sampled pixels; core + edge = alpha. Then straight: red = the plate's red. Header carries the convention."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import pixels
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import mask_to_points
    from st_roto import exr
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 2
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    g = stnode.create(rd, os.path.join(tempfile.mkdtemp(), "mo.stroto"))
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    keys = {f: mask_to_points((cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127).astype(float) - 0.5,
                              count=32) for f in range(n)}
    curves.rootLayer.append(build_shape(curves, "hero", keys, vh))
    nuke.frame(0); stnode.on_import_edits(g)
    g["stroto_edges"].setValue("hard")
    g["stroto_rgb_mode"].setValue("premultiplied"); g["stroto_core_edge"].setValue(4); g["stroto_edge_blur"].setValue(1.5)
    jm = stnode.on_render_mattes(g, background=False)
    res["status"] = g["stroto_status"].value()[-160:]
    if jm is None or jm.status != "done":
        res["error"] = getattr(jm, "error", None); return False
    # Nuke's own linear plate for frame 1 (the pixels the matte pass also received)
    wp = nuke.nodes.Write(inputs=[rd]); pth = OUT + "/mo_plate.tif"
    pixels.configure_write(wp, pth); wp["disable"].setValue(True)
    plate = pixels.render_frame(wp, 1, pth)
    ch = exr.read_channels(jm.result["files"][1])
    a = ch["A"]
    rr = nuke.nodes.Read(file=jm.result["files"][1].replace("\\", "/"), first=1, last=1)
    nuke.frame(1)
    res["nuke_channels"] = sorted(c for c in rr.channels() if c.startswith(("rgba", "core_matte", "edge_matte")))
    ys, xs = np.nonzero((a > 0.05) & (a < 0.95))
    pick = list(zip(xs[::max(1, len(xs) // 8)], ys[::max(1, len(ys) // 8)]))[:8]
    ys2, xs2 = np.nonzero(a > 0.999); pick += [(xs2[len(xs2) // 2], ys2[len(ys2) // 2])]
    d_file, d_nuke = [], []
    for x, y in pick:
        d_file.append(abs(float(ch["R"][y, x]) - float(plate[y, x, 0]) * float(a[y, x])))
        d_nuke.append(abs(rr.sample("rgba.red", x + 0.5, vh - y - 0.5) - float(ch["R"][y, x])))
    res["max_diff_R_vs_plate_x_alpha"] = max(d_file)
    res["max_diff_nuke_read_vs_file"] = max(d_nuke)
    res["core_plus_edge_err"] = float(np.abs(ch["core_matte.A"] + ch["edge_matte.A"] - a).max())
    ok = ({"rgba.red", "rgba.green", "rgba.blue", "rgba.alpha", "core_matte.alpha", "edge_matte.alpha"}
          <= set(res["nuke_channels"]) and res["max_diff_R_vs_plate_x_alpha"] < 1e-4
          and res["max_diff_nuke_read_vs_file"] < 1e-5 and res["core_plus_edge_err"] < 1e-5 and len(xs) > 50
          and "RGB premultiplied" in res["status"])
    g["stroto_rgb_mode"].setValue("straight"); g["stroto_core_edge"].setValue(0)
    js = stnode.on_render_mattes(g, background=False)
    res["straight_status"] = g["stroto_status"].value()[-300:]
    if js is None or js.status != "done":
        res["straight_error"] = getattr(js, "error", None); return False
    c2 = exr.read_channels(js.result["files"][1])
    res["straight_max_diff_vs_plate"] = float(np.abs(np.stack([c2["R"], c2["G"], c2["B"]], -1) - plate).max())
    import OpenEXR
    res["straight_header"] = json.loads(OpenEXR.File(js.result["files"][1]).header()["st_roto"])["alpha_convention"]
    # the first render's frame 1 is still open in Nuke's Read 'rr' (Windows cannot replace it): new version folder
    res["moved_from"] = js.result.get("moved_from")
    res["straight_dir"] = os.path.dirname(js.result["files"][1])
    ok &= (res["straight_max_diff_vs_plate"] < 1e-4 and res["straight_header"] == "straight" and "core_matte.A" not in c2
           and res["moved_from"] is not None and res["straight_dir"].endswith("_v002")
           and "went to a NEW folder" in res["straight_status"])
    return bool(ok)


def test_prompt_from_mask(res):
    """T-100 / REQ-060: deliberately ROUGH masks from the three sources become prompts (box + interior clicks) and
    the AI then tracks the exact objects: a crude polygon of the target drawn in the node's Roto (removed after use),
    a rough square around the distractor disc in ANOTHER Roto node (its alpha), and a shrunken mask PNG of the target
    on disk. One Track pass for all three; every key compared with the truth."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import build_shape
    from st_roto.geometry import Anchor, mask_to_points
    from st_roto import views
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, vw, n = meta["h"], meta["w"], 4
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "pm.stroto")
    g = stnode.create(rd, proj)
    curves = stnode._INNER[g.fullName()]["roto"]["curves"]
    yy, xx = np.mgrid[0:vh, 0:vw] + 0.5
    tgt = lambda f: cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127               # noqa: E731

    def disc(f):
        s = f / 47.0
        return (np.hypot(xx - (1050 - 600 * s), yy - (560 - 120 * np.sin(np.pi * s))) <= 85) & ~tgt(f)
    nuke.frame(0)
    # 1) crude polygon in the node's own Roto
    cs, _ = cv2.findContours(tgt(0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    poly = np.zeros((vh, vw), np.uint8)
    cv2.fillPoly(poly, [cv2.approxPolyDP(max(cs, key=cv2.contourArea), 6.0, True)], 1)
    rough1 = cv2.dilate(poly, np.ones((9, 9), np.uint8)) > 0
    curves.rootLayer.append(build_shape(curves, "rough", {0: mask_to_points(rough1.astype(float) - 0.5, count=10)}, vh))
    g["stroto_object"].setValue("from_shape"); g["stroto_prompt_from"].setValue("Roto shape")
    g["stroto_prompt_source"].setValue("rough")
    p1 = stnode.on_prompt_from_mask(g)
    res["shape_status"] = g["stroto_status"].value()
    res["rough_left_in_roto"] = [it.name for it in curves.rootLayer if it.name == "rough"]
    # 2) rough square around the disc in ANOTHER Roto node
    other = nuke.nodes.Roto(name="garbage_disc", output="alpha")
    other["format"].setValue("HD_720")
    ys, xs = np.nonzero(disc(0))
    sq = np.zeros((vh, vw), bool); sq[ys.min() - 12:ys.max() + 12, xs.min() - 12:xs.max() + 12] = True
    other["curves"].rootLayer.append(build_shape(other["curves"], "sq", {0: mask_to_points(sq.astype(float) - 0.5,
                                                                                         count=8)}, vh))
    g["stroto_object"].setValue("from_node"); g["stroto_prompt_from"].setValue("mask node")
    g["stroto_prompt_source"].setValue("garbage_disc")
    p2 = stnode.on_prompt_from_mask(g)
    res["node_status"] = g["stroto_status"].value()
    # 3) shrunken mask PNG on disk
    mdir = tempfile.mkdtemp().replace("\\", "/")
    cv2.imwrite(mdir + "/m.0000.png", (cv2.erode(tgt(0).astype(np.uint8), np.ones((13, 13), np.uint8)) * 255))
    g["stroto_object"].setValue("from_file"); g["stroto_prompt_from"].setValue("mask file")
    g["stroto_prompt_source"].setValue(mdir + "/m.####.png")
    p3 = stnode.on_prompt_from_mask(g)
    res["file_status"] = g["stroto_status"].value()
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()[:300]
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, _ = session.project(proj)
    shot = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    truth = {"from_shape": tgt, "from_node": disc, "from_file": tgt}
    res["iou"] = {}
    for o in store.objects(shot):
        if o["name"] not in truth:
            continue
        sid = views.main_shape(store, o["id"])["id"]
        vals = []
        for k in store.keys(sid):
            a = [Anchor(p=np.array(q[:2]), h_in=np.array(q[2:4]), h_out=np.array(q[4:]), corner=False) for q in k["points"]]
            vals.append(iou(rasterize_spline(a, vh, vw), truth[o["name"]](k["frame"])))
        res["iou"][o["name"]] = [round(min(vals), 4), round(float(np.mean(vals)), 4), len(vals)]
    rough_iou = {"shape": round(iou(rough1, tgt(0)), 4), "node_square": round(iou(sq, disc(0)), 4),
                 "file": round(iou(cv2.erode(tgt(0).astype(np.uint8), np.ones((13, 13), np.uint8)) > 0, tgt(0)), 4)}
    res["rough_mask_iou_vs_truth"] = rough_iou
    ok = (p1 is not None and p2 is not None and p3 is not None and res["rough_left_in_roto"] == []
          and "was only a prompt and was removed" in res["shape_status"]
          and sorted(res["iou"]) == ["from_file", "from_node", "from_shape"]
          and all(v[0] > 0.97 and v[2] == n for v in res["iou"].values()))
    return bool(ok)


def test_model_manager(res):
    """T-101 / REQ-052, REQ-130: model manager logic in real Nuke. Rows show the installed models with licence and
    approval; full Verify of tiny; Self-test of tiny (tracks a generated disc, IoU and time) and ViTMatte; import of
    tiny into a temporary USER location -> it is then the copy used (self-test runs from it, every file verified
    from its own location); Remove of that copy -> the plugin copy is used again."""
    from st_roto_nuke import models_ui
    from st_roto_nuke.track import model_dir
    from st_roto_ai import registry as reg
    rows = models_ui.rows()
    res["rows"] = [(r["name"], r["location"], r["active"], r["licence"], r["approval"], r["vram"]) for r in rows]
    names = {r["name"]: r for r in rows if r["location"] == "plugin"}
    ok = all(n in names and names[n]["usable"] and names[n]["active"]
             for n in ("sam2.1-hiera-tiny", "sam2.1-hiera-large", "vitmatte-small-composition-1k"))
    v = models_ui.verify("sam2.1-hiera-tiny", names["sam2.1-hiera-tiny"]["root"])
    res["verify_tiny"] = {"ok": v["ok"], "files": len(v["files"]) - 1, "seconds": v["seconds"]}
    st = models_ui.self_test("sam2.1-hiera-tiny")
    res["self_test_tiny"] = st
    sv = models_ui.self_test("vitmatte-small-composition-1k")
    res["self_test_vitmatte"] = sv
    ok &= v["ok"] and st["ok"] and st["device"] == "cuda" and sv["ok"]
    user = tempfile.mkdtemp()
    os.environ["ST_ROTO_MODELS_USER"] = user
    imp = models_ui.import_from(names["sam2.1-hiera-tiny"]["root"], "sam2.1-hiera-tiny", "user")
    res["import"] = {"files": imp["files"]}
    res["used_after_import"] = os.path.abspath(model_dir("sam2.1-hiera-tiny")).startswith(os.path.abspath(user))
    from st_roto_ai import runtime
    runtime.clear_cache()                                      # load the user copy, not the cached plugin sessions
    st2 = models_ui.self_test("sam2.1-hiera-tiny")
    res["self_test_from_user_copy"] = st2
    gone = models_ui.remove("sam2.1-hiera-tiny", user)
    res["removed"] = len(gone)
    res["used_after_remove"] = os.path.abspath(model_dir("sam2.1-hiera-tiny")).startswith(
        os.path.abspath(reg.default_models_root()))
    del os.environ["ST_ROTO_MODELS_USER"]
    ok &= (res["used_after_import"] and st2["ok"] and res["removed"] == 1 and res["used_after_remove"]
           and imp["files"] >= 5)
    return bool(ok)


def test_delivery_package(res):
    """T-108 / REQ-180: Track (CUDA) -> Render mattes -> Export shapes -> Delivery package: every section present,
    outputs included, model metadata with licence, settings from the node, verification against the manifest."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import zipfile
    import st_roto_nuke.node as stnode
    from st_roto import delivery
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 3
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "deliv.stroto")
    g = stnode.create(rd, proj)
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_click"].setValue([meta["click_xy"][0], vh - meta["click_xy"][1]]); stnode.on_add_point(g, 1)
    stnode.on_track(g, background=False)
    g["stroto_edges"].setValue("hard")
    stnode.on_render_mattes(g, background=False)
    stnode.on_export_shapes(g)
    r = stnode.on_delivery(g)
    res["status"] = g["stroto_status"].value()[-200:]
    if r is None:
        return False
    z = zipfile.ZipFile(r["zip"])
    names = z.namelist()
    res["sections"] = sorted(x for x in names if "/" not in x)
    res["mattes_in_package"] = len([x for x in names if x.startswith("outputs/mattes/") and x.endswith(".exr")])
    res["shapes_in_package"] = len([x for x in names if x.startswith("outputs/shapes/")])
    models = json.loads(z.read("models.json"))
    res["models"] = {k: (v.get("licence"), v.get("approval")) for k, v in models.items()}
    settings = json.loads(z.read("project_settings.json"))["settings"]
    res["settings_edges"] = settings.get("stroto_edges")
    deps = json.loads(z.read("dependencies.json"))
    res["deps"] = {k: deps.get(k) for k in ("nuke", "nuke_edition", "onnxruntime")}
    res["verify"] = delivery.verify(r["zip"])
    return bool(set(["MANIFEST.json", "models.json", "processing_report.md", "provenance.json", "quality_report.md",
                     "dependencies.json", "project_settings.json"]) <= set(res["sections"])
                and res["mattes_in_package"] == n and res["shapes_in_package"] >= 2
                and res["models"].get("sam2.1-hiera-tiny", (None,))[0] == "apache-2.0"
                and res["settings_edges"] == "hard" and res["deps"]["nuke"] and res["verify"] == [])


NET_EVENTS = ("socket.__new__", "socket.bind", "socket.connect", "socket.sendto", "socket.sendmsg",
              "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
              "urllib.Request", "http.client.connect", "http.client.send", "ftplib.connect", "smtplib.connect",
              "poplib.connect", "imaplib.open", "nntplib.connect", "telnetlib.Telnet.open", "webbrowser.open")


def test_offline_no_network(res):
    """T-085 / REQ-140: a whole ST-ROTO workflow (node, two prompts, Load model, Track on the GPU, soft mattes,
    JSON/SVG export, backup, package, re-open) must not use the network from Python: a sys.addaudithook hook
    records every socket creation, DNS lookup, connect/send and urllib/http/ftp/smtp/webbrowser event (with the
    calling stack) from just before ST-ROTO is first used until the end. Expected: none. (The OS-level view,
    including native code such as ONNX Runtime and Nuke itself, is tools/offline/watch_network.py.)"""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    seen = []

    def hook(event, args):
        if event in NET_EVENTS:
            import traceback as tb
            seen.append({"event": event, "args": repr(args)[:200],
                         "stack": [("%s:%d" % (f.filename, f.lineno)) for f in tb.extract_stack()[-8:-1]]})
    sys.addaudithook(hook)                                    # cannot be removed: one test per Nuke process
    import st_roto_nuke.node as stnode
    from st_roto_ai import runtime
    meta = json.load(open(VIDEO + "/meta.json"))
    vh, n = meta["h"], 6
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    tmp = tempfile.mkdtemp()
    proj = os.path.join(tmp, "offline.stroto")
    g = stnode.create(rd, proj)
    for name, (x, y) in (("target", meta["click_xy"]), ("disc", (1050.0, 560.0))):
        g["stroto_object"].setValue(name); nuke.frame(0)
        g["stroto_click"].setValue([x, vh - y]); stnode.on_add_point(g, 1)
    stnode.on_load_model(g)
    res["load_status"] = g["stroto_status"].value()
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    ok = job is not None and job.status == "done" and "cuda" in res["load_status"].lower()
    g["stroto_soft"].setValue(True)
    jm = stnode.on_render_mattes(g, background=False)
    ok &= jm is not None and jm.status == "done"
    out = stnode.on_export_shapes(g)
    ok &= out is not None and os.path.exists(out["json"])
    stnode.on_backup(g)
    zp = stnode.on_package(g, os.path.join(tmp, "offline_pkg.zip"))
    ok &= zp is not None and os.path.exists(zp)
    res["onnxruntime_telemetry_disabled"] = runtime.TELEMETRY_DISABLED
    res["network_events"] = seen
    res["network_event_count"] = len(seen)
    return bool(ok and not seen and runtime.TELEMETRY_DISABLED)


STEREO = ROOT + "/research/probes/2026-11-17_stereo/out/stereo"


def test_stereo_views(res):
    """T-109 (REQ-115) on the synthetic stereo shot (research/probes/2026-11-17_stereo, exact truth per view):
    a box prompt in the left view, 'track every view' -> target_left + target_right (each tracked on its own view's
    pixels, right prompt found by the disparity search), IoU vs each view's truth; Nuke's own render of the Roto
    per view shows each shape only in its view; mattes per view; Re-track of the right object; a plain (one view)
    Track in the stereo script, which failed before T-109 ('cannot be executed for multiple views')."""
    if not os.path.exists(STEREO + "/meta.json"):
        res["skipped"] = "stereo frames not generated (make_synthetic_stereo.py)"; return True
    import st_roto_nuke.node as stnode
    from st_roto import exr, stereo, views
    from st_roto_nuke import session
    meta = json.load(open(STEREO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 20                         # frames 14-19: the view-dependent occluder
    nuke.root()["views"].fromScript("left #ff0000\nright #00ff00")
    nuke.root()["format"].setValue("HD_720")
    res["views"] = nuke.views()
    rd = nuke.nodes.Read(file=STEREO + "/%V/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "stereo.stroto")
    g = stnode.create(rd, proj)

    def gt(view, f):
        return cv2.imread(STEREO + "/%s/gt_%04d.png" % (view, f), cv2.IMREAD_GRAYSCALE) > 127

    def set_box(name, mask):
        ys, xs = np.nonzero(mask)
        x0, y0, x1, y1 = xs.min() - 4.0, ys.min() - 4.0, xs.max() + 5.0, ys.max() + 5.0
        g["stroto_object"].setValue(name)
        g["stroto_box"].setValue([x0, vh - y1, x1, vh - y0])
        stnode.on_set_box(g)

    nuke.frame(0)
    set_box("target", gt("left", 0))
    g["stroto_stereo"].setValue(True)
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    shot = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    objs = {o["name"]: o for o in store.objects(shot)}
    res["objects"] = {k: (o["view"], o["pair"]) for k, o in objs.items()}
    ok = res["objects"] == {"target_left": ("left", "target"), "target_right": ("right", "target")}
    t = job.result["transfers"][("target", "right")]
    res["disparity_frame0"] = t if not isinstance(t, dict) else {k: round(v, 3) for k, v in t.items()}
    ok &= isinstance(t, dict) and abs(t["dx"] + 30) < 1.5 and abs(t["dy"]) < 1.0      # truth: -30 px, 0 px

    def ious(oid, view):
        sid = views.main_shape(store, oid)["id"]
        return {k["frame"]: round(iou(stereo.mask_from_keys([k["points"]], vh, vw), gt(view, k["frame"])), 4)
                for k in store.keys(sid)}
    q = {v: ious(objs["target_" + v]["id"], v) for v in ("left", "right")}
    res["iou"] = {v: {"min": min(x.values()), "mean": round(float(np.mean(list(x.values()))), 4), "frames": len(x)}
                  for v, x in q.items()}
    ok &= all(r["frames"] == n and r["min"] > 0.97 for r in res["iou"].values())
    res["stereo_flags"] = [f for f in views.review_for_object(store, objs["target_right"]["id"]) if "stereo" in f[2]]
    res["review_text"] = stnode._review_text(store, objs["target_right"]["id"])
    # Nuke's own render per view: each shape only in its own view
    wr = nuke.nodes.Write(inputs=[g])
    alpha_path = OUT + "/stereo_alpha.tif"
    wr["file"].setValue(alpha_path); wr["file_type"].setValue("tiff"); wr["datatype"].setValue("32 bit float")
    wr["channels"].setValue("rgba")
    render = {}
    for v in ("left", "right"):
        nuke.execute(wr, 10, 10, 1, views=[v])
        a = cv2.imread(alpha_path, cv2.IMREAD_UNCHANGED)[:, :, 3] > 0.5
        render[v] = {"vs_own_truth": round(iou(a, gt(v, 10)), 4),
                     "vs_other_truth": round(iou(a, gt("right" if v == "left" else "left", 10)), 4)}
    res["roto_render_frame10"] = render
    ok &= all(r["vs_own_truth"] > 0.97 and r["vs_own_truth"] - r["vs_other_truth"] > 0.1 for r in render.values())
    # mattes: one sequence per view
    g["stroto_matte_dir"].setValue(os.path.join(tempfile.mkdtemp(), "mattes").replace("\\", "/"))
    jm = stnode.on_render_mattes(g, background=False)
    res["matte_status"] = g["stroto_status"].value()
    if jm is None or jm.status != "done":
        res["matte_error"] = jm.error if jm else "no job"; return False
    mv = jm.result["views"]
    res["matte_patterns"] = {v: r["pattern"] for v, r in mv.items()}
    mi = {}
    for v, r in mv.items():
        ch = exr.read_channels(r["files"][10])
        mi[v] = round(iou(ch["A"] > 0.5, gt(v, 10)), 4)
    res["matte_iou_frame10"] = mi
    ok &= sorted(mv) == ["left", "right"] and all(x > 0.97 for x in mi.values())
    # Re-track the right object: renders the right view
    g["stroto_object"].setValue("target_right")
    jr = stnode.on_retrack(g, background=False)
    res["retrack_status"] = g["stroto_status"].value()
    ok &= jr is not None and jr.status == "done"
    q2 = ious(objs["target_right"]["id"], "right")
    res["retrack_right_iou_min"] = min(q2.values())
    ok &= min(q2.values()) > 0.97
    # one-view Track in the stereo script (failed before T-109): the distractor disc in the left view
    g["stroto_stereo"].setValue(False)
    dx, dy = 1050, 560
    disc = np.zeros((vh, vw), np.uint8); cv2.circle(disc, (dx, dy), 85, 1, -1)
    set_box("disc", disc > 0)
    jd = stnode.on_track(g, background=False)
    res["mono_status"] = g["stroto_status"].value()
    ok &= jd is not None and jd.status == "done"
    after = {o["name"]: o for o in store.objects(shot)}
    d = after.get("disc")
    res["mono_object_view"] = d and d["view"]
    res["objects_after_mono"] = sorted(after)
    ok &= d is not None and d["view"] == "left"
    ok &= sorted(after) == ["disc", "target_left", "target_right"]          # 'target' not tracked a second time
    ok &= "skipped target (already tracked" in res["mono_status"]
    return bool(ok)


CG = ROOT + "/research/probes/2026-11-18_channels/out/cg"


def test_extra_channels(res):
    """T-110 (REQ-113) on the synthetic CG shot (research/probes/2026-11-18_channels: depth, forward/backward
    vectors, normals, position, Cryptomatte; exact truth): List channels; prompt from Cryptomatte -> Track; every
    input layer passes through the node unchanged while alpha carries the shape; Check with channels (depth median,
    motion with measured convention, Cryptomatte) gives no flag on the clean track; a wrong key (the distractor)
    is flagged by all three; the check also runs with AI disabled."""
    if not os.path.exists(CG + "/meta.json"):
        res["skipped"] = "CG frames not generated (make_synthetic_cg.py)"; return True
    import st_roto_nuke.node as stnode
    from st_roto import channels as chn, exr, stereo, views
    from st_roto import model as m
    from st_roto.geometry import mask_to_points
    from st_roto_nuke import session
    meta = json.load(open(CG + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], meta["frames"]
    nuke.root()["format"].setValue(nuke.addFormat("%d %d 1 stroto_cg" % (vw, vh)))
    rd = nuke.nodes.Read(file=CG + "/cg.####.exr", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "cg.stroto")
    g = stnode.create(rd, proj)

    def gt(f):
        return cv2.imread(CG + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
    lst = stnode.on_list_channels(g)
    res["list"] = lst
    ok = all(x in lst["layers"] for x in ("rgba", "depth", "forward", "backward", "N", "P", "CryptoObject00"))
    ok &= lst["cryptomatte"].get("CryptoObject") == sorted(meta["names"])
    # prompt from Cryptomatte on frame 0
    nuke.frame(0)
    g["stroto_object"].setValue("target")
    g["stroto_prompt_from"].setValue("Cryptomatte")
    g["stroto_prompt_source"].setValue("target")
    p = stnode.on_prompt_from_mask(g)
    res["prompt_status"] = g["stroto_status"].value()
    res["crypto_map"] = g["stroto_ch_crypto_map"].value()
    ok &= p is not None and json.loads(res["crypto_map"]) == {"target": {"layer": "CryptoObject", "names": ["target"]}}
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    shot = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    obj = {o["name"]: o for o in store.objects(shot)}["target"]
    sid = views.main_shape(store, obj["id"])["id"]
    q = {k["frame"]: iou(stereo.mask_from_keys([k["points"]] + [kk["points"] for s in views.part_shapes(store, sid)
                                                                for kk in store.keys(s["id"]) if kk["frame"] == k["frame"]],
                                               vh, vw), gt(k["frame"]))
         for k in store.keys(sid)}
    res["iou"] = {"min": round(min(q.values()), 4), "mean": round(float(np.mean(list(q.values()))), 4), "frames": len(q)}
    ok &= len(q) == n and res["iou"]["mean"] > 0.97
    # pass-through: every source layer unchanged, alpha = the shapes
    wr = nuke.nodes.Write(inputs=[g])
    path = OUT + "/channels_through.exr"
    wr["file"].setValue(path); wr["file_type"].setValue("exr"); wr["datatype"].setValue("32 bit float")
    wr["channels"].setValue("all")
    nuke.execute(wr, 10, 10)
    got, src = exr.read_channels(path), exr.read_channels(CG + "/cg.0010.exr")
    diffs = {k: float(np.abs(got[k].astype(np.float64) - src[k].astype(np.float64)).max())
             for k in src if k != "A" and k in got}
    res["pass_through_max_diff"] = max(diffs.values())
    res["pass_through_missing"] = sorted(set(src) - set(got))
    res["alpha_vs_truth_frame10"] = round(iou(got["A"] > 0.5, gt(10)), 4)
    ok &= res["pass_through_max_diff"] == 0.0 and not res["pass_through_missing"] and res["alpha_vs_truth_frame10"] > 0.95
    # check with channels
    g["stroto_ch_stats"].setValue("depth.Z")
    g["stroto_ch_motion"].setValue("forward")
    g["stroto_ch_motion_back"].setValue("backward")
    jc = stnode.on_check_channels(g, background=False)
    res["check_status"] = g["stroto_status"].value()
    if jc is None or jc.status != "done":
        res["check_error"] = jc.error if jc else "no job"; return False
    rep = store.channel_reports(obj["id"])
    res["check"] = {"frames": len(rep), "conventions": {str(k): v["convention"] for k, v in jc.result["conventions"].items()},
                    "min_motion_iou": min(r["motion_iou"] for r in rep.values() if "motion_iou" in r),
                    "min_crypto_iou": min(r["crypto_iou"] for r in rep.values()),
                    "flags": [x for x in views.review_for_object(store, obj["id"]) if x[2].startswith("channels:")]}
    res["per_frame_truth_motion_crypto"] = {f: (round(q[f], 4), rep[f].get("motion_iou"), rep[f]["crypto_iou"])
                                            for f in sorted(rep)}
    ok &= len(rep) == n and not res["check"]["flags"]
    ok &= list(res["check"]["conventions"].values()) == [meta["vector_convention"]]
    # a wrong key on frame 12 (the distractor disc), as an artist edit
    p12 = (787.5 - 450 * 12 / (n - 1.0), 420 - 90 * np.sin(np.pi * 12 / (n - 1.0)))
    yy, xx = np.mgrid[0:vh, 0:vw] + 0.5
    bad = mask_to_points(64 - np.hypot(xx - p12[0], yy - p12[1]), count=int(store.row("shapes", sid)["point_count"]))
    bus.execute({"op": "set_key", "shape_id": sid, "frame": 12, "points": bad}, actor=m.ACTOR_ARTIST)
    g["stroto_ai_off"].setValue(True)                        # the channel check is not an AI feature
    jc2 = stnode.on_check_channels(g, background=False)
    res["check2_status"] = g["stroto_status"].value()
    ok &= jc2 is not None and jc2.status == "done"
    fl = [x for x in views.review_for_object(store, obj["id"]) if x[2].startswith("channels:")]
    res["flags_after_wrong_key"] = fl
    f12 = " ".join(r for f, _, r in fl if f == 12)
    ok &= "depth.Z" in f12 and "Cryptomatte" in f12 and "motion" in f12
    return bool(ok)


def test_review_overlay_and_presets(res):
    """T-111 (REQ-120/121): review colours keyed on the Roto shapes per frame (lost = magenta, check = yellow,
    Nuke's default elsewhere), switched off again; the 'this frame' readout; presets: built-in applied, own preset
    saved / re-applied (incl. a linked inner-Roto knob), refreshed list, deleted."""
    import st_roto_nuke.node as stnode
    from st_roto import model as m
    from st_roto.geometry import mask_to_points
    from st_roto_nuke import session
    from st_roto_nuke.roto_export import sync_shot
    OID, SID = "0a0b0c0d" + "0" * 24, "1a2b3c4d" + "0" * 24          # real ids are hex (shape tags)
    os.environ["ST_ROTO_USER_PRESET_DIR"] = os.path.join(tempfile.mkdtemp(), "presets")
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=9)
    proj = os.path.join(tempfile.mkdtemp(), "ov.stroto")
    g = stnode.create(rd, proj)
    store, bus = session.project(proj)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": rd.name(), "width": 1280, "height": 720,
                                              "first_frame": 0, "last_frame": 9}})
    bus.execute({"op": "create_object", "row": {"id": OID, "shot_id": "S", "name": "hero"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": SID, "object_id": OID, "name": "hero", "point_count": 12}},
                actor=m.ACTOR_AI)
    yy, xx = np.mgrid[0:720, 0:1280] + 0.5
    for f in range(10):
        if f != 4:
            bus.execute({"op": "set_key", "shape_id": SID, "frame": f,
                         "points": mask_to_points(80 - np.hypot(xx - 400 - 5 * f, yy - 360), count=12)},
                        actor=m.ACTOR_AI)
        bus.execute({"op": "set_report", "shape_id": SID, "frame": f, "object_score": -5.0 if f == 4 else 5.0,
                     "iou_pred": 0.95})
    bus.execute({"op": "set_channel_report", "object_id": OID, "frame": 7, "data": {"crypto_iou": 0.3}})
    roto = stnode._inner(g, "roto", "STROTO_shapes")
    sync_shot(store, "S", roto["curves"], 720)
    r = stnode.on_review_colours_toggled(g)
    res["flagged_frames"] = r["flagged_frames"]
    shape = list(roto["curves"].rootLayer)[0]
    a = shape.getAttributes()

    def col(f):
        return [round(a.getValue(f, n), 3) for n in ("ro", "go", "bo", "ao")]
    res["colours"] = {f: col(f) for f in (3, 4, 5, 6, 7, 8)}
    ok = (res["colours"][4] == [1.0, 0.0, 1.0, 1.0] and res["colours"][7] == [1.0, 0.85, 0.0, 1.0]
          and all(res["colours"][f][3] == 0.0 for f in (3, 5, 6, 8)))
    stnode._show_this_frame(g.fullName(), 7)
    res["this_frame_7"] = g["stroto_this_frame"].value()
    stnode._show_this_frame(g.fullName(), 2)
    res["this_frame_2"] = g["stroto_this_frame"].value()
    ok &= "hero CHECK" in res["this_frame_7"] and "Cryptomatte" in res["this_frame_7"] and "no flags" in res["this_frame_2"]
    g["stroto_review_colours"].setValue(False)
    stnode.on_review_colours_toggled(g)
    res["colours_off"] = {f: col(f) for f in (4, 7)}
    ok &= all(v[3] == 0.0 for v in res["colours_off"].values())
    # presets
    res["preset_menu"] = g["stroto_preset"].values()
    ok &= "Quick look" in res["preset_menu"] and "CG plate with passes" in res["preset_menu"]
    ra = stnode.on_apply_preset(g, "Quick look")
    res["apply_builtin"] = ra
    ok &= ra is not None and g["stroto_edges"].value() == "hard" and g["stroto_matte_size"].value() == "fit 1920x1080"
    g["stroto_band"].setValue(7)
    roto["replace"].setValue(False)
    path = stnode.on_save_preset(g, "T111 test")
    res["saved"] = bool(path and os.path.exists(path))
    ok &= res["saved"] and "T111 test" in g["stroto_preset"].values()
    g["stroto_band"].setValue(2)
    roto["replace"].setValue(True)
    rb = stnode.on_apply_preset(g, "T111 test")
    res["apply_own"] = {"band": int(g["stroto_band"].value()), "replace": bool(roto["replace"].value()),
                        "skipped": rb and rb["skipped"]}
    ok &= res["apply_own"]["band"] == 7 and res["apply_own"]["replace"] is False and not rb["skipped"]
    stnode.on_apply_preset(g, "CG plate with passes")
    res["cg_preset"] = {"stats": g["stroto_ch_stats"].value(), "replace": bool(roto["replace"].value())}
    ok &= res["cg_preset"] == {"stats": "depth.Z", "replace": True}
    ok &= stnode.on_delete_preset(g, "T111 test") is not None and "T111 test" not in g["stroto_preset"].values()
    ok &= stnode.on_delete_preset(g, "Stereo") is None and "only your own" in g["stroto_status"].value()
    return bool(ok)


def test_node_family(res):
    """T-112 (REQ-040, REQ-292): in ONE fresh Non-commercial session - Read, ST_Roto (box prompt, Track: 2 objects,
    one made a holdout), ST_RotoMatte (validation errors; Check; render; its output in the node graph: alpha = the
    combined matte, per-object layers, plate RGB unchanged; role filter), ST_RotoOutput (export, delivery) - and
    Node-object budget left over."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    import st_roto_nuke.family as fam
    from st_roto import exr
    from st_roto_nuke import session
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 8
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "fam.stroto")
    g = stnode.create(rd, proj)

    def gt(f):
        return cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127

    def set_box(name, x0, y0, x1, y1):
        g["stroto_object"].setValue(name)
        g["stroto_box"].setValue([x0, vh - y1, x1, vh - y0])
        stnode.on_set_box(g)
    nuke.frame(0)
    ys, xs = np.nonzero(gt(0))
    set_box("target", xs.min() - 4.0, ys.min() - 4.0, xs.max() + 5.0, ys.max() + 5.0)
    set_box("disc", 1050 - 95.0, 560 - 95.0, 1050 + 95.0, 560 + 95.0)
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    g["stroto_object"].setValue("disc")
    stnode.on_set_role(g, "holdout")
    m = fam.create_matte(g, proj, "")
    ok = True
    # validation
    res["err_no_shot"] = (fam.on_matte_render(m, background=False), m["stroto_status"].value())[1]
    m["stroto_shot"].setValue("Read9")
    fam.on_check(m)
    res["err_wrong_shot"] = m["stroto_status"].value()
    m["stroto_shot"].setValue(rd.name())
    m["stroto_objects"].setValue("target, nobody")
    fam.on_check(m)
    res["err_unknown_object"] = m["stroto_status"].value()
    m["stroto_objects"].setValue("")
    m["stroto_role_filter"].setValue("garbage")
    fam.on_check(m)
    res["err_no_garbage"] = m["stroto_status"].value()
    ok &= "set 'shot'" in res["err_no_shot"] and "no shot 'Read9'" in res["err_wrong_shot"] and "Read1" in res["err_wrong_shot"]
    ok &= "no object named nobody" in res["err_unknown_object"] and "no object to render" in res["err_no_garbage"]
    m["stroto_role_filter"].setValue("all roles")
    chk = fam.on_check(m)
    res["check"] = m["stroto_status"].value()
    ok &= chk is not None and sorted(chk["chosen"]) == ["disc", "target"] and "disc [holdout]" in res["check"]
    # before rendering: pass-through
    w = nuke.nodes.Write(inputs=[m])
    path = OUT + "/family_matte.exr"
    w["file"].setValue(path); w["file_type"].setValue("exr"); w["datatype"].setValue("32 bit float")
    w["channels"].setValue("all")
    nuke.execute(w, 3, 3)
    before = exr.read_channels(path)
    plate = cv2.imread(VIDEO + "/frame_0003.png")[:, :, ::-1].astype(np.float32) / 255.0
    jm = fam.on_matte_render(m, background=False)
    res["matte_status"] = m["stroto_status"].value()
    if jm is None or jm.status != "done":
        res["matte_error"] = jm.error if jm else "no job"; return False
    nuke.execute(w, 3, 3)
    after = exr.read_channels(path)
    res["after_channels"] = sorted(after)
    t3 = gt(3)
    res["alpha_vs_target_truth"] = round(iou(after["A"] > 0.5, t3), 4)
    res["target_layer_vs_truth"] = round(iou(after.get("target.A", np.zeros_like(t3, np.float32)) > 0.5, t3), 4)
    res["rgb_unchanged"] = float(max(np.abs(after[c] - before[c]).max() for c in "RGB"))
    disc = after.get("disc.A")
    res["holdout_layer_px"] = int((disc > 0.5).sum()) if disc is not None else None
    ok &= res["rgb_unchanged"] == 0.0 and res["alpha_vs_target_truth"] > 0.95 and res["target_layer_vs_truth"] > 0.95
    ok &= disc is not None and res["holdout_layer_px"] > 1000 and "Read1" in m["stroto_pattern"].value()
    # holdouts only
    m["stroto_role_filter"].setValue("holdout")
    jh = fam.on_matte_render(m, background=False)
    nuke.execute(w, 3, 3)
    hold = exr.read_channels(path)
    res["holdout_only_layers"] = sorted(k for k in hold if k.endswith(".A"))
    ok &= jh is not None and jh.status == "done" and "target.A" not in hold and "disc.A" in hold
    # output node
    o = fam.create_output(m, proj, rd.name())
    rj = fam.on_output(o, "export")
    res["export_status"] = o["stroto_status"].value()
    rdv = fam.on_output(o, "delivery")
    res["delivery_status"] = o["stroto_status"].value()
    ok &= rj is not None and os.path.exists(rj["json"]) and len(rj["svg"]) == n and rdv is not None
    res["budget_left"] = sum(1 for _ in range(12) if nuke.nodes.NoOp() is not None)
    ok &= res["budget_left"] >= 2
    return bool(ok)


def test_alembic_export(res):
    """T-113: 'Export Alembic' on an ST_Roto node: an object with a main shape (frames 1-5) and a part shape that is
    collapsed (piece absent) on frame 3. Read back through USD: curve / mesh points equal st_roto.geomexport of the
    stored keys; the part is invisible on frame 3. Nuke 17's own 3D (GeoImport + orthographic Camera3 +
    ScanlineRender2) renders the meshes on top of ST-ROTO's exact raster of the splines."""
    import st_roto_nuke.node as stnode
    from st_roto import exr, geomexport as ge, model as m
    from st_roto.geometry import mask_to_points
    from st_roto.stereo import mask_from_keys
    from st_roto_nuke import alembic, session
    if alembic.available():
        res["skipped"] = alembic.available(); return True
    W_, H_ = 640, 360
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=1, last=5)
    proj = os.path.join(tempfile.mkdtemp(), "abc.stroto")
    g = stnode.create(rd, proj)
    store, bus = session.project(proj)
    OID, SID, PID = "0a0b0c0d" + "0" * 24, "1a2b3c4d" + "0" * 24, "2a2b3c4d" + "0" * 24
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": rd.name(), "width": W_, "height": H_,
                                              "first_frame": 1, "last_frame": 5}})
    bus.execute({"op": "create_object", "row": {"id": OID, "shot_id": "S", "name": "hero arm"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": SID, "object_id": OID, "name": "hero arm", "point_count": 12}},
                actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": PID, "object_id": OID, "name": "hero arm_part2",
                                               "point_count": 8, "generator": json.dumps({"part_of": SID})}},
                actor=m.ACTOR_AI)
    yy, xx = np.mgrid[0:H_, 0:W_] + 0.5
    keys, parts = {}, {}
    for f in range(1, 6):
        u = (xx - 200 - 30 * f) / 110.0; v = (yy - 150 - 10 * f) / 60.0
        keys[f] = mask_to_points(1 - np.sqrt(u * u + v * v), count=12)
        parts[f] = mask_to_points(25 - np.hypot(xx - 520, yy - 280 + 5 * f), count=8) if f != 3 else [[520.0, 80.0] * 3] * 8
        bus.execute({"op": "set_key", "shape_id": SID, "frame": f, "points": keys[f]}, actor=m.ACTOR_AI)
        bus.execute({"op": "set_key", "shape_id": PID, "frame": f, "points": parts[f]}, actor=m.ACTOR_AI)
    r = stnode.on_export_alembic(g)
    res["status"] = g["stroto_status"].value()
    if r is None:
        return False
    res["prims"] = sorted(r["prims"])
    ok = open(r["path"], "rb").read(5) == b"Ogawa"
    back = alembic.read_back(r["path"])
    err = 0.0
    for pth, per in back.items():
        src = parts if "part2" in pth else keys
        for f, pts in per.items():
            if f not in src or (src is parts and f == 3):
                continue
            exp = ge.curve_points(src[f], H_) if pth.endswith("curveShape") else ge.mesh_polygon(src[f], H_)
            err = max(err, float(np.abs(np.array(pts) - exp).max()))
    res["read_back_max_error_px"] = err
    ok &= len(back) == 4 and err < 1e-3
    from pxr import Usd, UsdGeom
    st = Usd.Stage.Open(r["path"])
    vis = {}
    for p in st.Traverse():
        if p.GetTypeName() in ("Mesh", "BasisCurves"):
            a = UsdGeom.Imageable(p).GetVisibilityAttr()
            vis[str(p.GetPath())] = {f: str(a.Get(f)) for f in (2, 3, 4)}
    res["visibility"] = vis
    ok &= all(v[3] == "invisible" and v[2] == "inherited" for k, v in vis.items() if "part2" in k)
    ok &= all(v[3] == "inherited" for k, v in vis.items() if "part2" not in k)
    # Nuke's own 3D renders the meshes
    nuke.root()["format"].setValue(nuke.addFormat("%d %d 1 abc_test" % (W_, H_)))
    gi = nuke.nodes.GeoImport(file=r["path"].replace("\\", "/"))          # Nuke file knobs: forward slashes
    cam = nuke.nodes.Camera3()
    cam["projection_mode"].setValue("orthographic"); cam["focal"].setValue(1.0)
    cam["haperture"].setValue(float(W_)); cam["vaperture"].setValue(float(H_))
    cam["translate"].setValue([W_ / 2.0, H_ / 2.0, 100.0])
    sr = nuke.nodes.ScanlineRender2()
    sr.setInput(1, gi); sr.setInput(2, cam)
    wr = nuke.nodes.Write(file=OUT + "/abc_render.####.exr", file_type="exr", datatype="32 bit float", channels="rgba")
    wr.setInput(0, sr)
    q = {}
    for f in (1, 3, 5):
        nuke.execute(wr, f, f)
        a = exr.read_channels(OUT + "/abc_render.%04d.exr" % f)["A"] > 0.5
        ref = mask_from_keys([keys[f]] + ([parts[f]] if f != 3 else []), H_, W_)
        q[f] = round(iou(a, ref), 4)
    res["nuke_3d_render_iou"] = q
    ok &= all(x > 0.99 for x in q.values())
    return bool(ok)


def test_model_versions(res):
    """T-114 (REQ-130) with the REAL SAM 2.1 tiny model in temporary locations (the project's models are never
    touched): import v1 into a user location; v2 = the same export with one config file changed (a genuinely
    different, still working version, registered like any export); importing v2 archives v1; both self-test side by
    side on the GPU ('name@id' runs the archived one without activating it); activating v1 while ONNX Runtime
    sessions are loaded (they are released first); rollback returns to v2; history records it."""
    import shutil
    from st_roto_ai import registry as reg
    from st_roto_nuke import models_ui
    name = "sam2.1-hiera-tiny"
    plugin = reg.default_models_root()
    if not os.path.isdir(os.path.join(plugin, "onnx", name, "video")):
        res["skipped"] = "model not installed"; return True
    tmp = tempfile.mkdtemp(prefix="stroto_versions_")
    user, stage = os.path.join(tmp, "user"), os.path.join(tmp, "stage")
    os.makedirs(user)
    os.environ["ST_ROTO_MODELS_USER"] = user
    try:
        r1 = models_ui.import_from(plugin, name, "user")
        v1 = r1["version"]
        # v2: same weights, config.json with an extra (ignored) key, re-registered
        os.makedirs(os.path.join(stage, "manifests"))
        shutil.copy2(os.path.join(plugin, "manifests", name + ".json"), os.path.join(stage, "manifests"))
        shutil.copytree(os.path.join(plugin, "onnx", name), os.path.join(stage, "onnx", name))
        cfgp = os.path.join(stage, "onnx", name, "video", "config.json")
        cfg = json.load(open(cfgp))
        cfg["st_roto_test_variant"] = "T-114"
        json.dump(cfg, open(cfgp, "w"), indent=1)
        reg.build_exports_manifest(name, stage, tool="T-114 test variant")
        r2 = models_ui.import_from(stage, name, "user")
        v2 = r2["version"]
        res["ids"] = {"v1": v1, "v2": v2, "archived_on_import": r2["archived"]}
        ok = v1 != v2 and r2["archived"] == v1
        vs = models_ui.versions(name, user)
        res["versions"] = [(v["id"], v["active"], v["tool"]) for v in vs]
        ok &= [(v["id"], v["active"]) for v in vs] == [(v2, True), (v1, False)]
        ok &= reg.find_model(name) == os.path.abspath(user)
        cmp_ = models_ui.compare(name, user)
        res["compare"] = [(c["id"], c["active"], c["result"].get("ok"), c["result"].get("iou"),
                           c["result"].get("device")) for c in cmp_]
        ok &= len(cmp_) == 2 and all(c["result"].get("ok") for c in cmp_)
        # activate v1 while sessions of both versions are loaded (models_ui releases them first)
        a = models_ui.activate(name, user, v1, note="test")
        res["activate"] = a
        cfg_now = json.load(open(os.path.join(user, "onnx", name, "video", "config.json")))
        ok &= a["active"] == v1 and "st_roto_test_variant" not in cfg_now
        st = models_ui.self_test(name)
        res["self_test_after_activate"] = {"ok": st.get("ok"), "iou": st.get("iou")}
        ok &= bool(st.get("ok"))
        rb = models_ui.rollback(name, user)
        res["rollback"] = rb
        cfg_now = json.load(open(os.path.join(user, "onnx", name, "video", "config.json")))
        ok &= rb["active"] == v2 and cfg_now.get("st_roto_test_variant") == "T-114"
        res["history"] = [(h["action"], h["from"], h["to"]) for h in models_ui.history(name, user)]
        ok &= [h[0] for h in res["history"]] == ["import", "import", "activate", "activate"]
        res["plugin_untouched"] = reg.active_version(name, plugin)["id"] == v1
        ok &= res["plugin_untouched"]
    finally:
        os.environ.pop("ST_ROTO_MODELS_USER", None)
        models_ui._release_sessions()
        shutil.rmtree(tmp, ignore_errors=True)
    return bool(ok)


def test_edge_colour_and_chatter(res):
    """T-115 (REQ-101): on a real track of the synthetic shot - 'Reduce chatter' lowers the frame-to-frame jitter of
    the AI keys without losing accuracy vs truth (mean IoU, temporal error), keeps artist keys, and is one undo step;
    'Render mattes' with RGB 'premultiplied, decontaminated' and spill 'auto' records both in the EXR header, keeps
    solid-foreground pixels = plate x alpha and changes soft-edge colours."""
    if not os.path.exists(VIDEO + "/meta.json"):
        res["skipped"] = "synthetic frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import chatter, exr, metrics, model as m, views
    from st_roto.stereo import mask_from_keys
    from st_roto_nuke import session
    meta = json.load(open(VIDEO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 20
    rd = nuke.nodes.Read(file=VIDEO + "/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "ch.stroto")
    g = stnode.create(rd, proj)

    def gt(f):
        return cv2.imread(VIDEO + "/gt_%04d.png" % f, cv2.IMREAD_GRAYSCALE) > 127
    ys, xs = np.nonzero(gt(0))
    g["stroto_object"].setValue("target")
    nuke.frame(0)
    g["stroto_box"].setValue([xs.min() - 4.0, vh - ys.max() - 5.0, xs.max() + 5.0, vh - ys.min() + 4.0])
    stnode.on_set_box(g)
    job = stnode.on_track(g, background=False)
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    shot = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    obj = {o["name"]: o for o in store.objects(shot)}["target"]
    sid = views.main_shape(store, obj["id"])["id"]

    def state():
        ks = {k["frame"]: k["points"] for k in store.keys(sid)}
        masks = [mask_from_keys([ks[f]], vh, vw) for f in range(n)]
        ious = [iou(masks[f], gt(f)) for f in range(n)]
        return ks, ious, metrics.temporal_error([x.astype(np.float32) for x in masks],
                                               [gt(f).astype(np.float32) for f in range(n)])
    k0, iou0, te0 = state()
    # an artist key on frame 10 must survive untouched
    bus.execute({"op": "set_key", "shape_id": sid, "frame": 10, "points": k0[10]}, actor=m.ACTOR_ARTIST)
    rep = stnode.on_reduce_chatter(g)
    res["status"] = g["stroto_status"].value()
    if rep is None:
        return False
    k1, iou1, te1 = state()
    res["jitter"] = [round(chatter.jitter(k0), 4), round(chatter.jitter(k1), 4)]
    res["mean_iou"] = [round(float(np.mean(iou0)), 4), round(float(np.mean(iou1)), 4)]
    res["min_iou"] = [round(min(iou0), 4), round(min(iou1), 4)]
    res["temporal_error"] = [round(te0, 5), round(te1, 5)]
    ok = res["jitter"][1] < res["jitter"][0] and res["mean_iou"][1] >= res["mean_iou"][0] - 0.002
    ok &= k1[10] == k0[10]                                                     # artist key kept
    bus.undo()
    k2, _, _ = state()
    ok &= all(np.allclose(k2[f], k0[f]) for f in k0)                            # one undo step
    # decontaminated + despilled RGB in the mattes
    g["stroto_rgb_mode"].setValue("premultiplied, decontaminated")
    g["stroto_spill"].setValue("auto")
    jm = stnode.on_render_mattes(g, background=False)
    res["matte_status"] = g["stroto_status"].value()
    if jm is None or jm.status != "done":
        res["matte_error"] = jm.error if jm else "no job"; return False
    f = jm.result["files"][5]
    st = json.loads(exr.read_header(f)["st_roto"])
    res["header"] = {k: st.get(k) for k in ("alpha_convention", "edge_colour", "spill")}
    ok &= res["header"] == {"alpha_convention": "premultiplied", "edge_colour": "decontaminated", "spill": "auto"}
    ch = exr.read_channels(f)
    a = ch["A"]
    rgb = np.stack([ch["R"], ch["G"], ch["B"]], -1)
    plate = cv2.imread(VIDEO + "/frame_0005.png")[:, :, ::-1].astype(np.float32) / 255.0
    lin = np.where(plate <= 0.04045, plate / 12.92, ((plate + 0.055) / 1.055) ** 2.4)     # Nuke reads PNG as sRGB
    solid, edge = a >= 0.999, (a > 0.05) & (a < 0.95)
    res["solid_vs_plate_x_alpha"] = float(np.abs(rgb[solid] - lin[solid]).max())
    res["edge_mean_change_vs_plate_x_alpha"] = float(np.abs(rgb[edge] - lin[edge] * a[edge][:, None]).mean())
    res["edge_pixels"] = int(edge.sum())
    ok &= res["solid_vs_plate_x_alpha"] < 2e-3 and res["edge_pixels"] > 100 and \
        res["edge_mean_change_vs_plate_x_alpha"] > 1e-3
    return bool(ok)


def test_stereo_resume(res):
    """T-119: a stereo Track cancelled during the RIGHT view's pass (left finished) keeps a stereo checkpoint and
    says where a resume starts; 'Resume track' (prompts cleared) finishes it; the result equals an uninterrupted
    stereo run exactly (both views, every key) and the checkpoint is removed."""
    if not os.path.exists(STEREO + "/meta.json"):
        res["skipped"] = "stereo frames not generated"; return True
    import st_roto_nuke.node as stnode
    from st_roto import views
    from st_roto_nuke import session
    from st_roto_nuke.track import read_checkpoint, read_stereo_checkpoint
    meta = json.load(open(STEREO + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], 20
    nuke.root()["views"].fromScript("left #ff0000\nright #00ff00")
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=STEREO + "/%V/frame_####.png", first=0, last=n - 1)
    proj1 = os.path.join(tempfile.mkdtemp(), "sr1.stroto")
    g = stnode.create(rd, proj1)
    gt0 = cv2.imread(STEREO + "/left/gt_0000.png", cv2.IMREAD_GRAYSCALE) > 127
    ys, xs = np.nonzero(gt0)
    box = [xs.min() - 4.0, vh - ys.max() - 5.0, xs.max() + 5.0, vh - ys.min() + 4.0]

    def prompt():
        g["stroto_object"].setValue("target")
        nuke.frame(0)
        g["stroto_box"].setValue(box)
        stnode.on_set_box(g)
    prompt()
    g["stroto_stereo"].setValue(True)
    real = stnode._renderer
    calls = {"right": 0}

    def cancelling(ctx, background, view=None):
        inner = real(ctx, background, view)

        def get_rgb(f):
            if (view or ctx.get("view")) == "right":
                calls["right"] += 1
                if calls["right"] == 14:                         # right pass, frame ~12 (after the transfer render)
                    stnode._JOBS[g.fullName()].cancel()
            return inner(f)
        return get_rgb
    stnode._renderer = cancelling
    j1 = stnode.on_track(g, background=False)
    stnode._renderer = real
    ck = stnode.checkpoint_dir(proj1, rd.name())
    sm = read_stereo_checkpoint(ck)
    pm = read_checkpoint(os.path.join(ck, "pass_right"))
    res["after_cancel"] = {"job": j1.status, "status": g["stroto_status"].value(), "done": sm and sm["done"],
                           "right_next_frame": pm and pm["next_frame"]}
    ok = j1.status == "cancelled" and sm is not None and sm["done"] == ["left"] and pm is not None
    ok &= "continues the right view from frame %s" % pm["next_frame"] in res["after_cancel"]["status"]
    stnode.on_clear_points(g, every_object=True)                   # resuming needs no prompts on the node
    j2 = stnode.on_resume_track(g, background=False)
    res["resume_status"] = g["stroto_status"].value()
    ok &= j2 is not None and j2.status == "done" and "(resumed)" in res["resume_status"] and not os.path.exists(ck)

    def keys_of(proj):
        st, _ = session.project(proj)
        shot = st.conn.execute("SELECT id FROM shots").fetchone()["id"]
        out = {}
        for o in st.objects(shot):
            sid = views.main_shape(st, o["id"])["id"]
            out[o["name"]] = {k["frame"]: k["points"] for k in st.keys(sid)}
        return out
    resumed = keys_of(proj1)
    # an uninterrupted stereo run of the same prompt, into a second project
    proj2 = os.path.join(tempfile.mkdtemp(), "sr2.stroto")
    g["stroto_project"].setValue(proj2)
    prompt()
    j3 = stnode.on_track(g, background=False)
    ok &= j3 is not None and j3.status == "done"
    fresh = keys_of(proj2)
    res["objects"] = sorted(resumed)
    ok &= sorted(resumed) == sorted(fresh) == ["target_left", "target_right"]
    diff = 0.0
    for name in fresh:
        ok &= sorted(resumed[name]) == sorted(fresh[name]) == list(range(n))
        for f in fresh[name]:
            diff = max(diff, float(np.abs(np.array(resumed[name][f]) - np.array(fresh[name][f])).max()))
    res["max_key_difference_resumed_vs_uninterrupted"] = diff
    ok &= diff == 0.0
    return bool(ok)


MULTICAM = ROOT + "/research/probes/2026-11-18_multicam/out/mc"


def test_multicam_cameras(res):
    """T-120 on the synthetic NON-rectified three-camera shot (views A, B, C; toe-in, roll, vertical offset, window
    translate, another focal length; exact truth): box prompt in A on frame 5, 'track every view' with the camera
    nodes -> every view found along its epipolar line, IoU vs truth per view; the epipolar check is clean on the AI
    tracks; a wrong object put into view C by an artist is flagged by 'Check views (cameras)'."""
    if not os.path.exists(MULTICAM + "/meta.json"):
        res["skipped"] = "multi-camera frames not generated (make_multicam.py)"; return True
    import st_roto_nuke.node as stnode
    from st_roto import model as m, stereo, views
    from st_roto.geometry import mask_to_points
    from st_roto_nuke import session
    meta = json.load(open(MULTICAM + "/meta.json"))
    vw, vh, n = meta["w"], meta["h"], meta["frames"]
    nuke.root()["views"].fromScript("A #ff0000\nB #00ff00\nC #0000ff")
    nuke.root()["format"].setValue(nuke.addFormat("%d %d 1 mc_test" % (vw, vh)))
    rd = nuke.nodes.Read(file=MULTICAM + "/%V/frame_####.png", first=0, last=n - 1)
    proj = os.path.join(tempfile.mkdtemp(), "mc.stroto")
    g = stnode.create(rd, proj)
    cache = stnode._INNER.setdefault(g.fullName(), {})
    for v, c in meta["cameras"].items():
        cam = nuke.nodes.Camera3(name="Cam" + v)
        cam["translate"].setValue(c["translate"]); cam["rotate"].setValue(c["rotate"])
        cam["focal"].setValue(c["focal"]); cam["haperture"].setValue(c["haperture"])
        cam["win_translate"].setValue(c["win_translate"])
        cache["cam:Cam" + v] = cam                       # the test's own references (Non-commercial node budget)

    def gt(v, f):
        return cv2.imread(MULTICAM + "/%s/gt_%04d.png" % (v, f), cv2.IMREAD_GRAYSCALE) > 127
    F0 = 5
    ys, xs = np.nonzero(gt("A", F0))
    g["stroto_object"].setValue("target")
    nuke.frame(F0)
    g["stroto_box"].setValue([xs.min() - 4.0, vh - ys.max() - 5.0, xs.max() + 5.0, vh - ys.min() + 4.0])
    stnode.on_set_box(g)
    g["stroto_stereo"].setValue(True)
    g["stroto_prompt_view"].setValue("A")
    g["stroto_cameras"].setValue("A=CamA, B=CamB, C=CamC")
    job = stnode.on_track(g, background=False)
    res["track_status"] = g["stroto_status"].value()
    if job is None or job.status != "done":
        res["error"] = job.error if job else "no job"; return False
    store, bus = session.project(proj)
    shot = store.conn.execute("SELECT id FROM shots").fetchone()["id"]
    objs = {o["name"]: o for o in store.objects(shot)}
    res["objects"] = sorted(objs)
    ok = sorted(objs) == ["target_A", "target_B", "target_C"]
    ok &= "epipolar line (cameras)" in res["track_status"]
    q = {}
    for v in "ABC":
        sid = views.main_shape(store, objs["target_" + v]["id"])["id"]
        ks = {k["frame"]: k["points"] for k in store.keys(sid)}
        ious = [iou(stereo.mask_from_keys([ks[f]], vh, vw), gt(v, f)) for f in sorted(ks)]
        q[v] = {"frames": len(ious), "min": round(min(ious), 4), "mean": round(float(np.mean(ious)), 4)}
    res["iou"] = q
    ok &= all(x["frames"] == n - F0 and x["mean"] > 0.97 for x in q.values())
    epi = {v: [r.get("epipolar_px") for f, r in sorted(store.channel_reports(objs["target_" + v]["id"]).items())]
           for v in "BC"}
    res["epipolar_px_max"] = {v: max(x for x in e if x is not None) for v, e in epi.items()}
    flags = [x for v in "ABC" for x in views.review_for_object(store, objs["target_" + v]["id"])
             if "epipolar" in x[2] or "stereo" in x[2]]
    res["flags_clean_track"] = flags
    ok &= all(len(e) == n - F0 for e in epi.values()) and not flags
    # an artist puts the WRONG object (the distractor disc) into view C on frame 10
    sidc = views.main_shape(store, objs["target_C"]["id"])["id"]
    gtc = gt("C", 10)
    sf = 10 / (n - 1.0)
    from st_roto import cameras as cm
    c = meta["cameras"]["C"]
    P = cm.projection(cm.intrinsics(vw, vh, c["focal"], c["haperture"], win_translate=c["win_translate"]),
                      *cm.from_world_matrix(np.array(c["world_matrix"]).reshape(4, 4)))
    dc = cm.project(P, [[1.6 - 3.2 * sf, -0.6, -8.0]])[0][0]
    yy, xx = np.mgrid[0:vh, 0:vw] + 0.5
    npts = len(store.keys(sidc)[0]["points"])
    bus.execute({"op": "set_key", "shape_id": sidc, "frame": 10,
                 "points": mask_to_points(60 - np.hypot(xx - dc[0], yy - dc[1]), count=npts)}, actor=m.ACTOR_ARTIST)
    from st_roto_nuke.roto_export import sync_shot
    sync_shot(store, shot, stnode._inner(g, "roto", "STROTO_shapes")["curves"], vh)
    rep = stnode.on_check_views(g)
    res["check_views_status"] = g["stroto_status"].value()
    fl = [x for x in views.review_for_object(store, objs["target_C"]["id"]) if "epipolar" in x[2]]
    res["flags_after_wrong_object"] = fl
    ok &= rep is not None and [x[0] for x in fl] == [10]
    return bool(ok)


TESTS = (test_export_animated_shape, test_st_roto_node_track_slice, test_repeated_tracking_stable,
         test_prompts_preview_sync_protection, test_import_artist_edits, test_retrack_with_corrections,
         test_review_flags_reverse, test_multi_object_track, test_render_mattes_exr,
         test_export_import_shapes, test_crash_recovery_and_package, test_motion_blur_links,
         test_colour_auto_follows_script, test_split_object_parts, test_cancel_and_resume_track,
         test_package_script_relink, test_feather_and_rotopaint, test_point_feather_roundtrip,
         test_vitmatte_mattes, test_box_prompt, test_reprompt_here, test_offline_no_network,
         test_difficult_sequences, test_traditional_roto_without_ai, test_plate_above_render_limit,
         test_system_report, test_memory_aware_model, test_retrack_flagged_large,
         test_collaboration_ui, test_propagation_controls, test_roles_and_merge,
         test_matte_outputs, test_prompt_from_mask, test_model_manager,
         test_delivery_package, test_stereo_views, test_extra_channels, test_review_overlay_and_presets,
         test_node_family, test_alembic_export, test_model_versions, test_edge_colour_and_chatter,
         test_stereo_resume, test_multicam_cameras)


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
