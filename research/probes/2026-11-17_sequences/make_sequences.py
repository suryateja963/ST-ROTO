"""T-086 / REQ-092: build edge-case image sequences from the synthetic shot (research/probes/2026-11-15_video).

Each case gets out/<case>/frame_####.png (plate) and gt_####.png (truth, same size as its plate), plus
out/<case>/case.json describing the frame numbers present. Run with the project venv:
  .venv\\Scripts\\python.exe -I research/probes/2026-11-17_sequences/make_sequences.py
"""
import json
import os
import shutil

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "2026-11-15_video", "frames")
OUT = os.path.join(HERE, "out")


def put(case, num, src_index, scale=1.0):
    d = os.path.join(OUT, case)
    os.makedirs(d, exist_ok=True)
    for kind in ("frame", "gt"):
        a = os.path.join(SRC, "%s_%04d.png" % (kind, src_index))
        b = os.path.join(d, "%s_%04d.png" % (kind, num))
        if scale == 1.0:
            shutil.copyfile(a, b)
        else:
            img = cv2.imread(a, cv2.IMREAD_UNCHANGED)
            h, w = img.shape[:2]
            interp = cv2.INTER_AREA if kind == "frame" else cv2.INTER_NEAREST
            cv2.imwrite(b, cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=interp))


CASES = {
    # frame number in the sequence -> (source frame of the synthetic shot, scale)
    "start1001": {1001 + i: (i, 1.0) for i in range(10)},
    "missing": {i: (i, 1.0) for i in range(10) if i not in (4, 5)},
    "discontinuous": dict([(i, (i, 1.0)) for i in range(5)] + [(i, (i, 1.0)) for i in range(20, 25)]),
    "duplicate": {i: (min(i, 2) if i <= 4 else i - 2, 1.0) for i in range(10)},     # 2,2,2 hold then continues
    "mixed_res": {i: (i, 1.0 if i < 5 else 0.5) for i in range(10)},
    "plain": {i: (i, 1.0) for i in range(10)},                                        # for proxy and retime
}


def main():
    for case, frames in CASES.items():
        d = os.path.join(OUT, case)
        shutil.rmtree(d, ignore_errors=True)
        for num, (src, scale) in frames.items():
            put(case, num, src, scale)
        json.dump({"frames": {str(k): {"source": v[0], "scale": v[1]} for k, v in frames.items()}},
                  open(os.path.join(d, "case.json"), "w"), indent=1)
        print(case, len(frames), "frames", min(frames), "-", max(frames))


if __name__ == "__main__":
    main()
