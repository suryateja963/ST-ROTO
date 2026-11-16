"""SA-V validation subset for calibration/benchmarks (D-031: owner-approved, CC BY 4.0, Meta).

Meta serves sav_val.tar (~16 GB) through EXPIRING links issued after a consent click on
https://ai.meta.com/datasets/segment-anything-video-downloads/ ("Download all links" -> a text file). That click is
the licence acceptance and is done by the owner. This tool then STREAMS the tar and keeps only the first N videos:
their annotated frames (every 4th 24-fps frame = the 6-fps annotation rate) and masks; it stops reading as soon as
those videos are complete. Output (git-ignored): data/benchmarks/sa-v/<video>_<object>/frames/*.jpg + masks/*.png
(the layout of tools/benchmark/calibrate_review.py --dir), raw/, MANIFEST.json (SHA-256 per file, source, licence).

Usage: .venv/Scripts/python.exe tools/benchmark/fetch_sav_subset.py --links "<links file from Meta>" [--n 30]
       (--url <direct sav_val.tar URL> also works; file:// URLs are accepted, used by the tests)
"""
import argparse, hashlib, json, os, re, shutil, sys, tarfile, time, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "benchmarks", "sa-v")
ATTRIBUTION = ("SA-V dataset (Segment Anything Video), Meta AI, CC BY 4.0, "
               "https://ai.meta.com/datasets/segment-anything-video/ - subset: first videos of the validation split, "
               "annotated frames only (6 fps), unmodified pixels; masks converted to per-object folders.")
FRAME_RE = re.compile(r"JPEGImages_24fps/([^/]+)/(\d+)\.jpg$")
MASK_RE = re.compile(r"Annotations_6fps/([^/]+)/(\d+)/(\d+)\.png$")


def find_url(links_path, name="sav_val.tar"):
    for line in open(links_path, encoding="utf-8", errors="replace"):
        for tok in re.split(r"\s+", line.strip()):
            if name in tok and tok.startswith(("http://", "https://", "file://")):
                return tok
    raise SystemExit("no %s link in %s (download the links file again: they expire)" % (name, links_path))


def stream_subset(url, n, out_raw, log=print):
    """Stream the tar; keep annotated frames + masks of the first n videos; stop when they are complete."""
    os.makedirs(out_raw, exist_ok=True)
    chosen, frames, masks = [], {}, {}
    done = {"frames": set(), "masks": set()}          # a video is done in a section once the stream moved past it
    last = {"frames": None, "masks": None}
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "st-roto-benchmark-fetch"})

    def moved(section, vid):
        if last[section] is not None and vid != last[section]:
            done[section].add(last[section])
        last[section] = vid

    with urllib.request.urlopen(req) as resp:
        tf = tarfile.open(fileobj=resp, mode="r|*")
        for m in tf:
            fm, mm = FRAME_RE.search(m.name), MASK_RE.search(m.name)
            if fm:
                vid, idx = fm.group(1), int(fm.group(2))
                moved("frames", vid)
                if vid not in chosen and len(chosen) < n:
                    chosen.append(vid)
                if vid in chosen and idx % 4 == 0:
                    dst = os.path.join(out_raw, "frames", vid, "%05d.jpg" % idx)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with tf.extractfile(m) as src, open(dst, "wb") as fh:
                        shutil.copyfileobj(src, fh)
                    frames.setdefault(vid, []).append(idx)
            elif mm:
                vid, obj, idx = mm.group(1), mm.group(2), int(mm.group(3))
                moved("masks", vid)
                if vid in chosen:
                    dst = os.path.join(out_raw, "masks", vid, obj, "%05d.png" % idx)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with tf.extractfile(m) as src, open(dst, "wb") as fh:
                        shutil.copyfileobj(src, fh)
                    masks.setdefault(vid, set()).add(obj)
            if len(chosen) == n and all(v in done["frames"] and v in done["masks"] for v in chosen):
                log("subset complete after %.0f s (stopped reading the archive)" % (time.time() - t0))
                break
    return chosen, frames, {k: sorted(v) for k, v in masks.items()}


def convert(out_raw, out_dir, chosen):
    """raw/frames/<vid>/<idx>.jpg + raw/masks/<vid>/<obj>/<idx>.png -> <vid>_<obj>/frames + masks (same names)."""
    seqs = []
    for vid in chosen:
        mdir = os.path.join(out_raw, "masks", vid)
        if not os.path.isdir(mdir):
            continue
        for obj in sorted(os.listdir(mdir)):
            names = sorted(os.listdir(os.path.join(mdir, obj)))
            seq = os.path.join(out_dir, "%s_%s" % (vid, obj))
            os.makedirs(os.path.join(seq, "frames"), exist_ok=True); os.makedirs(os.path.join(seq, "masks"), exist_ok=True)
            n = 0
            for nm in names:
                fr = os.path.join(out_raw, "frames", vid, nm[:-4] + ".jpg")
                if os.path.exists(fr):
                    shutil.copyfile(fr, os.path.join(seq, "frames", nm[:-4] + ".jpg"))
                    shutil.copyfile(os.path.join(mdir, obj, nm), os.path.join(seq, "masks", nm))
                    n += 1
            seqs.append((os.path.basename(seq), n))
    return seqs


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--links"); ap.add_argument("--url"); ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    url = a.url or find_url(a.links)
    raw = os.path.join(a.out, "raw")
    chosen, frames, masks = stream_subset(url, a.n, raw)
    seqs = convert(raw, a.out, chosen)
    files = {}
    for dp, _, fns in os.walk(a.out):
        for fn in fns:
            if fn != "MANIFEST.json":
                p = os.path.join(dp, fn)
                files[os.path.relpath(p, a.out).replace("\\", "/")] = sha256(p)
    man = {"source": "SA-V validation split (sav_val.tar)", "licence": "CC BY 4.0", "approval": "D-031",
           "attribution": ATTRIBUTION, "videos": chosen, "sequences": dict(seqs),
           "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": files}
    json.dump(man, open(os.path.join(a.out, "MANIFEST.json"), "w"), indent=1, sort_keys=True)
    print("%d videos, %d object sequences, %d files -> %s" % (len(chosen), len(seqs), len(files), a.out))
    return man


if __name__ == "__main__":
    main()
