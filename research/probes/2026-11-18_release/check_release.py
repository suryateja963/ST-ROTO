"""Release 0.1.0 check (D-046): run INSIDE Nuke started with a temporary HOME whose .nuke/init.py was written by
ST-ROTO's setup from the RELEASE files (main zip + ST-ROTO-model-*.zip). Checks that ST-ROTO is loaded from the
installed copy, reports version 0.1.0, finds and fully verifies all three models in the installed location, tracks
3 frames with the LARGE model on CUDA and renders mattes with ViTMatte-S.
  Nuke17.1.exe --nc -t check_release.py out=<json> frames=<synthetic frames dir>"""
import json
import os
import sys
import tempfile
import traceback

args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
R = {}
try:
    import nuke
    import st_roto_nuke.node as n
    from st_roto_ai import registry
    R["st_roto_nuke_from"] = os.path.dirname(os.path.abspath(n.__file__))
    R["repo_on_path"] = any(os.path.abspath(p).lower().startswith("d:\\st-roto\\src") for p in sys.path)
    R["version"] = n._st_roto_version()
    R["models"] = {}
    for name in ("sam2.1-hiera-tiny", "sam2.1-hiera-large", "vitmatte-small-composition-1k"):
        d = registry.model_dir(name)
        rows = registry.verify_model(name, os.path.dirname(os.path.dirname(d)))
        R["models"][name] = {"dir": d, "files_checked": len(rows), "all_ok": bool(rows) and all(r["ok"] for r in rows),
                             "first": rows[0]["detail"] if rows else ""}
    vid = args["frames"]
    meta = json.load(open(os.path.join(vid, "meta.json")))
    nuke.root()["format"].setValue("HD_720")
    rd = nuke.nodes.Read(file=vid.replace("\\", "/") + "/frame_####.png", first=0, last=2)
    work = tempfile.mkdtemp(prefix="st_roto_release_")
    g = n.create(rd, os.path.join(work, "release.stroto"))
    g["stroto_object"].setValue("target"); nuke.frame(0)
    g["stroto_model"].setValue("sam2.1-hiera-large")
    g["stroto_click"].setValue([meta["click_xy"][0], meta["h"] - meta["click_xy"][1]]); n.on_add_point(g, 1)
    job = n.on_track(g, background=False)
    R["track_status"] = g["stroto_status"].value()
    from st_roto_ai import runtime                          # model files whose ONNX sessions were really loaded
    large_used = [k[0] for k in runtime._CACHE if k[0].startswith(R["models"]["sam2.1-hiera-large"]["dir"])]
    other_used = [k[0] for k in runtime._CACHE if not k[0].startswith(R["models"]["sam2.1-hiera-large"]["dir"])]
    R["sessions_large"], R["sessions_other"] = len(large_used), other_used
    R["track_ok"] = bool(job is not None and job.status == "done" and "device cuda" in R["track_status"]
                         and large_used and not other_used)
    g["stroto_edges"].setValue("ViTMatte-S (optional AI)")
    g["stroto_matte_dir"].setValue(os.path.join(work, "mattes").replace("\\", "/"))
    mj = n.on_render_mattes(g, background=False)
    R["matte_status"] = g["stroto_status"].value()
    R["matte_ok"] = bool(mj is not None and mj.status == "done" and "ViTMatte-S edges" in R["matte_status"]
                         and "mattes: 3 frames" in R["matte_status"])
    R["passed"] = bool(R["track_ok"] and R["matte_ok"] and R["version"] == "0.1.0" and not R["repo_on_path"]
                       and all(m["all_ok"] for m in R["models"].values()))
except Exception:
    R["exception"] = traceback.format_exc()
json.dump(R, open(args["out"], "w"), indent=1)
