"""OQ-29 (owner, 2026-11-17: build a precise-edge truth on real footage first). Builds the drawing kit.

Picks ~20 SA-V frames (approved subset, D-031, CC BY 4.0) where the edge methods of T-095 disagree most (one frame
per object, from 4 resolutions) and writes ONE image sequence into data/edge_truth/ (git-ignored). Every frame is
padded - never scaled, so pixels and edges stay exact - onto a common 1920x1920 canvas, top-left aligned, so one
ST_Roto node holds the whole kit (Nuke Non-commercial allows Python access to only 10 nodes per session):
  plate.####.png      the original frame on the canvas (dark grey padding), frames numbered 1..n
  reference.####.png  the same frame with the object to draw outlined and boxed in magenta (SA-V's outline: ONLY to show
                              WHICH object; do not trace it - draw the true edge you see in the plate)
  manifest.json       frame number -> SA-V sequence, frame, size, why it was picked
  INSTRUCTIONS.md     what the artist does
Then: Nuke17.1.exe --nc tools/edge_truth/open_kit.py   (draw)   ->   tools/edge_truth/export_truth.py   ->
research/probes/2026-11-17_edges/edge_study.py --truth data/edge_truth
  .venv\\Scripts\\python.exe -I tools/edge_truth/make_kit.py
"""
import json
import os
import shutil

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAV = os.path.join(ROOT, "data", "benchmarks", "sa-v")
STUDY = os.path.join(ROOT, "research", "probes", "2026-11-17_edges", "edge_study.json")
OUT = os.path.join(ROOT, "data", "edge_truth")
GROUPS = {(1080, 1920): ("portrait_1080x1920", 8), (720, 1280): ("portrait_720x1280", 6),
          (1920, 1080): ("landscape_1920x1080", 3), (1280, 720): ("landscape_1280x720", 3)}


def disagreement(r):
    return max(abs(r[k][0] - r["A"][0]) for k in ("B", "C", "C2"))


def pick(rows):
    good = [r for r in rows if r["A"][0] >= 0.5]
    chosen = {}
    for size, (name, n) in GROUPS.items():
        cand = sorted((r for r in good if tuple(r["size"]) == size), key=disagreement, reverse=True)
        seen, out = set(), []
        for r in cand:
            if r["seq"] in seen:
                continue
            seen.add(r["seq"]); out.append(r)
            if len(out) == n:
                break
        chosen[name] = out
    return chosen


INSTRUCTIONS = """# Drawing the precise-edge truth (OQ-29)

Goal: about 20 frames where the edge of one object is drawn **exactly on the true edge in the image**. These become
the reference that decides whether ST-ROTO should refine AI edges (T-095). Your drawing is the truth: take care.

1. Open the kit: `"C:\\Program Files\\Nuke17.1v3\\Nuke17.1.exe" --nc D:\\ST-ROTO\\tools\\edge_truth\\open_kit.py`.
   You get a plate Read, a reference Read and an ST_Roto node (AI switched off), frames 1-{N}. Frames of different
   sizes share one canvas: the grey area is padding, ignore it.
2. Go to frame 1. Look at the **reference** Read to see WHICH object (magenta outline and box). Do not trace the
   magenta line: it is only a pointer and is not precise.
3. View the **ST_Roto** node (it shows the plate) and draw that object with Nuke's Roto tools inside the ST_Roto
   node (double-click it -> its Roto). Work at 200-400 % zoom. Put the edge where the object's edge really is (the
   middle of the transition for soft edges). Several pieces: draw each piece as its own shape on that frame.
   Holes (e.g. the gap between an arm and the body): draw the hole as its own shape and rename it so its name
   starts with `hole` - it is subtracted from the object.
4. Every shape must have a key ONLY on the frame you drew it on (Roto creates the key on the current frame: do not
   move to another frame while editing it). One frame = one object.
5. Repeat for every frame. Press **Save Roto edits to project** on the ST_Roto node often.
6. Write a line per frame in `notes.txt` next to this file if something is ambiguous (motion blur, hair, holes).
7. Tell Claude when done: it runs `tools/edge_truth/export_truth.py` and the comparison.

Time: roughly 5-15 minutes per frame.
"""


CANVAS = (1920, 1920)
PAD = (40, 40, 40)


def on_canvas(img):
    out = np.zeros((CANVAS[1], CANVAS[0], 3), np.uint8); out[:] = PAD
    out[:img.shape[0], :img.shape[1]] = img
    return out


def main():
    rows = json.load(open(STUDY))["rows"]
    chosen = pick(rows)
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    frames, i = [], 0
    for name, rs in chosen.items():
        for r in rs:
            i += 1
            img = cv2.imread(os.path.join(SAV, r["seq"], "frames", r["frame"] + ".jpg"))
            cv2.imwrite(os.path.join(OUT, "plate.%04d.png" % i), on_canvas(img))
            m = cv2.imread(os.path.join(SAV, r["seq"], "masks", r["frame"] + ".png"), cv2.IMREAD_GRAYSCALE) > 127
            ref = img.copy()
            cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            mag, th = (255, 0, 255), max(3, img.shape[1] // 400)
            cv2.drawContours(ref, cs, -1, mag, th)
            ys, xs = np.nonzero(m)
            pad = max(25, img.shape[1] // 40)
            x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
            x1, y1 = min(img.shape[1] - 1, xs.max() + pad), min(img.shape[0] - 1, ys.max() + pad)
            cv2.rectangle(ref, (int(x0), int(y0)), (int(x1), int(y1)), mag, th)
            scale = max(0.7, img.shape[1] / 1600.0)
            cv2.putText(ref, "draw THIS object (outline = pointer only)", (20, int(45 * scale)),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, mag, 2)
            cv2.imwrite(os.path.join(OUT, "reference.%04d.png" % i), on_canvas(ref))
            frames.append({"frame": i, "group": name, "seq": r["seq"], "sav_frame": r["frame"],
                           "width": r["size"][0], "height": r["size"][1], "box_frac": r["box_frac"],
                           "disagreement": round(disagreement(r), 4),
                           "study_iou": {k: round(r[k][0], 4) for k in ("A", "B", "C", "C2")}})
        print(name, len(rs), "frames")
    manifest = {"source": "SA-V subset (D-031, CC BY 4.0, Meta AI)", "canvas": list(CANVAS),
                "placement": "top-left, unscaled", "frames": frames}
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    with open(os.path.join(OUT, "INSTRUCTIONS.md"), "w", encoding="utf-8") as fh:
        fh.write(INSTRUCTIONS.replace("{N}", str(len(frames))))
    print("kit:", OUT, len(frames), "frames")


if __name__ == "__main__":
    main()
