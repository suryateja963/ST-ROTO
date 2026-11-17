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
    bus.undo()
    res["undo_restores"] = keys() == k1
    g["stroto_range_from"].setValue(0); g["stroto_range_to"].setValue(29)
    res["unlocked"] = stnode.on_lock_range(g, False)
    ok &= res["undo_restores"] and res["unlocked"] == [] and "locked_frames" not in json.loads(
        store.row("shapes", sid)["generator"])
    return bool(ok)


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


TESTS = (test_export_animated_shape, test_st_roto_node_track_slice, test_repeated_tracking_stable,
         test_prompts_preview_sync_protection, test_import_artist_edits, test_retrack_with_corrections,
         test_review_flags_reverse, test_multi_object_track, test_render_mattes_exr,
         test_export_import_shapes, test_crash_recovery_and_package, test_motion_blur_links,
         test_colour_auto_follows_script, test_split_object_parts, test_cancel_and_resume_track,
         test_package_script_relink, test_feather_and_rotopaint, test_point_feather_roundtrip,
         test_vitmatte_mattes, test_box_prompt, test_reprompt_here, test_offline_no_network,
         test_difficult_sequences, test_traditional_roto_without_ai, test_plate_above_render_limit,
         test_system_report, test_memory_aware_model, test_retrack_flagged_large,
         test_collaboration_ui, test_propagation_controls)


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
