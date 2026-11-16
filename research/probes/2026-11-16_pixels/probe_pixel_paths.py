"""T-046: ways to get a rendered frame from Nuke into numpy, measured (Nuke 17.1 NC, Python has no buffer API:
only Node.sample per pixel). Paths: (a) nuke.sample per pixel (extrapolated from 2,000 samples), (b) float TIFF
uncompressed + cv2 (current), (c) EXR float uncompressed + OpenEXR, (d) EXR half uncompressed + OpenEXR,
(e) TIFF 16-bit int + cv2 (quantised: not exact). Exactness vs (b) is reported.
Run: Nuke17.1.exe --nc -t research/probes/2026-11-16_pixels/probe_pixel_paths.py"""
import json, os, sys, tempfile, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")).replace("\\", "/")
sys.path[:0] = [ROOT + "/src"]
sys.path.append(ROOT + "/.tools/nuke-py311")
import numpy as np   # noqa: E402
import cv2           # noqa: E402
import nuke          # noqa: E402
import OpenEXR       # noqa: E402

TMP = tempfile.mkdtemp().replace("\\", "/")
res = {}
for fmt in ("HD_720", "HD_1080"):
    nuke.root()["format"].setValue(fmt)
    W, H = nuke.root().width(), nuke.root().height()
    src = nuke.nodes.CheckerBoard2()
    noise = nuke.nodes.Noise(); noise.setInput(0, src)          # non-trivial content
    out = {}
    # (a) per-pixel sample
    t0 = time.time()
    for i in range(2000):
        noise.sample("red", (i * 37) % W + 0.5, (i * 11) % H + 0.5)
    per = (time.time() - t0) / 2000
    out["sample_per_pixel_us"] = round(per * 1e6, 2)
    out["sample_full_frame_rgb_s_extrapolated"] = round(per * W * H * 3, 1)

    def via_write(path, ftype, dtype=None, compression=None, reader=None, key=None):
        w = nuke.nodes.Write(file=path, file_type=ftype, channels="rgb")
        if dtype: w["datatype"].setValue(dtype)
        if compression: w["compression"].setValue(compression)
        w.setInput(0, noise)
        times = []
        for k in range(4):
            t0 = time.time(); nuke.execute(w, 1, 1); t1 = time.time(); img = reader(path.replace("####", "0001")); t2 = time.time()
            times.append((t1 - t0, t2 - t1))
        nuke.delete(w)
        r = np.median([t[0] for t in times[1:]]); d = np.median([t[1] for t in times[1:]])
        out[key] = {"render_s": round(float(r), 4), "read_s": round(float(d), 4), "total_s": round(float(r + d), 4),
                    "MB": round(os.path.getsize(path.replace("####", "0001")) / 1e6, 2)}
        return img

    def read_tif(p):
        x = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        return cv2.cvtColor(x, cv2.COLOR_BGR2RGB)

    def read_exr(p):
        with OpenEXR.File(p) as f:
            ch = f.channels()
            if "RGB" in ch:
                return np.asarray(ch["RGB"].pixels, np.float32)
            return np.stack([np.asarray(ch[c].pixels, np.float32) for c in ("R", "G", "B")], -1)

    ref = via_write(TMP + "/a.####.tif", "tiff", "32 bit float", "none", read_tif, "tiff_float_uncompressed (current)")
    e32 = via_write(TMP + "/b.####.exr", "exr", "32 bit float", "none", read_exr, "exr_float_uncompressed")
    e16 = via_write(TMP + "/c.####.exr", "exr", "16 bit half", "none", read_exr, "exr_half_uncompressed")
    t16 = via_write(TMP + "/d.####.tif", "tiff", "16 bit", "none", read_tif, "tiff_16bit_int_uncompressed")
    out["exr_float_max_abs_diff_vs_tiff"] = float(np.abs(e32 - ref).max())
    out["exr_half_max_abs_diff_vs_tiff"] = float(np.abs(e16 - ref).max())
    out["tiff16_max_abs_diff_vs_tiff"] = float(np.abs(t16.astype(np.float32) / 65535.0 - np.clip(ref, 0, 1)).max())
    res["%s (%dx%d)" % (fmt, W, H)] = out
    print(fmt, json.dumps(out), flush=True)
    nuke.delete(noise); nuke.delete(src)
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json"), "w"), indent=1)
