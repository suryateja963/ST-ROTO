"""tools/benchmark/fetch_sav_subset.py against a locally built SA-V-shaped tar (file:// URL, no network)."""
import io
import json
import os
import sys
import tarfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "benchmark"))
import fetch_sav_subset as fs   # noqa: E402


def _add(tf, name, data):
    ti = tarfile.TarInfo(name); ti.size = len(data); tf.addfile(ti, io.BytesIO(data))


def test_streams_only_the_subset_and_converts(tmp_path):
    tar = tmp_path / "sav_val.tar"
    with tarfile.open(str(tar), "w") as tf:
        for v in ("sav_001", "sav_002", "sav_003"):                     # frames of 3 videos, 24 fps
            for i in range(9):
                _add(tf, "sav_val/JPEGImages_24fps/%s/%05d.jpg" % (v, i), b"jpg%s%d" % (v.encode(), i))
        for v in ("sav_001", "sav_002", "sav_003"):                     # masks at 6 fps, two objects in sav_001
            for obj in (("000", "001") if v == "sav_001" else ("000",)):
                for i in (0, 4, 8):
                    _add(tf, "sav_val/Annotations_6fps/%s/%s/%05d.png" % (v, obj, i), b"png%d" % i)
    links = tmp_path / "links.txt"
    links.write_text("something else\nfile:///%s\n" % str(tar).replace("\\", "/"))
    out = tmp_path / "out"
    man = fs.main(["--links", str(links), "--n", "2", "--out", str(out)])
    assert man["videos"] == ["sav_001", "sav_002"] and man["licence"] == "CC BY 4.0" and man["approval"] == "D-031"
    assert man["sequences"] == {"sav_001_000": 3, "sav_001_001": 3, "sav_002_000": 3}
    assert sorted(os.listdir(out / "sav_001_000" / "frames")) == ["00000.jpg", "00004.jpg", "00008.jpg"]
    assert not (out / "raw" / "frames" / "sav_003").exists()           # not chosen: never written
    assert not os.path.exists(out / "raw" / "frames" / "sav_001" / "00001.jpg")   # only annotated (6 fps) frames
    assert json.load(open(out / "MANIFEST.json"))["files"]
