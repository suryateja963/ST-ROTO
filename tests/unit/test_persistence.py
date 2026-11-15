"""Backups, crash detection, recovery and portable packages (T-071)."""
import json
import os
import subprocess
import sys
import textwrap
import zipfile

import pytest

from st_roto import persistence as ps
from st_roto.commands import CommandBus
from st_roto.store import ProjectStore

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
PTS = [[0, 0, 0, 0, 0, 0], [5, 5, 5, 5, 5, 5]]


def _make(path, source_path=None):
    s = ProjectStore(path); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh", "width": 8, "height": 8,
                                              "source_path": source_path}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "o"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "p", "point_count": 2}})
    return s, bus


def test_backup_of_open_project_is_consistent_and_rotated(tmp_path):
    p = str(tmp_path / "proj.stroto")
    s, bus = _make(p)
    for f in range(3):
        bus.execute({"op": "set_key", "shape_id": "P", "frame": f, "points": PTS})     # WAL, not checkpointed
    paths = [ps.backup(p, keep=2) for _ in range(3)]
    assert ps.list_backups(p) == sorted(paths[1:], reverse=True)                      # rotated to 2
    b = ProjectStore(paths[-1])
    assert [k["frame"] for k in b.keys("P")] == [0, 1, 2]                             # includes WAL content
    b.close()
    manual = ps.backup(p, keep=1, reason="manual")
    ps.backup(p, keep=1)
    assert manual in ps.list_backups(p) and len(ps.list_backups(p, reason="auto")) == 1  # other reasons kept
    s.close()


def test_autobackup_only_when_changed(tmp_path):
    p = str(tmp_path / "a.stroto")
    s, bus = _make(p)
    ab = ps.AutoBackup(p, interval=3600).start()
    assert ab.tick() is None                                                          # no change since start
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": PTS})
    assert ab.tick() is not None and ab.tick() is None
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 2, "points": PTS})
    ab.stop()                                                                         # final backup on stop
    assert len(ab.backups) == 2 and not ab.errors
    s.close()


def test_crash_is_detected_and_clean_close_is_not(tmp_path):
    p = str(tmp_path / "c.stroto")
    _make(p)[0].close()
    code = textwrap.dedent("""
        import os, sys
        sys.path.insert(0, %r)
        from st_roto.persistence import SessionMarker
        SessionMarker(%r).acquire({"app": "test"})
        os._exit(3)                       # crash: marker never released
    """ % (SRC, p))
    assert subprocess.call([sys.executable, "-c", code]) == 3
    m = ps.SessionMarker(p)
    prev = m.acquire()
    assert prev["state"] == "crashed" and prev["app"] == "test"
    m.release()
    assert not os.path.exists(p + ".session.json")
    m2 = ps.SessionMarker(p)
    assert m2.acquire() is None                                                       # clean
    assert ps.SessionMarker(p).acquire() is None                                      # same process: not "elsewhere"
    m2.release()


def test_live_other_process_is_reported(tmp_path):
    p = str(tmp_path / "l.stroto")
    proc = subprocess.Popen([sys.executable, "-c", textwrap.dedent("""
        import sys, time
        sys.path.insert(0, %r)
        from st_roto.persistence import SessionMarker
        SessionMarker(%r).acquire(); print("ready", flush=True); time.sleep(30)
    """ % (SRC, p))], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
        assert ps.SessionMarker(p).acquire()["state"] == "open_elsewhere"
    finally:
        proc.kill(); proc.wait()


def test_recover_moves_damaged_file_aside_and_restores_backup(tmp_path):
    p = str(tmp_path / "r.stroto")
    s, bus = _make(p)
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 7, "points": PTS})
    good = ps.backup(p)
    s.close()
    assert ps.recover(p)["action"] == "none"
    with open(p, "r+b") as fh:                                                        # damage the database
        fh.seek(0); fh.write(b"\0" * 4096)
    assert not ps.check(p)["ok"]
    rep = ps.recover(p)
    assert rep["action"] == "restored" and rep["from"] == good and rep["damaged"]
    assert all(os.path.exists(d) for d in rep["damaged"])                            # never deleted
    t = ProjectStore(p)
    assert t.key("P", 7) is not None
    t.close()


def test_pack_unpack_with_sources_and_relink(tmp_path):
    srcdir = tmp_path / "plates"; srcdir.mkdir()
    for f in (1, 2):
        (srcdir / ("plate.%04d.exr" % f)).write_bytes(b"frame%d" % f)
    p = str(tmp_path / "work" / "show.stroto"); os.makedirs(os.path.dirname(p))
    s, bus = _make(p, str(srcdir / "plate.####.exr").replace("\\", "/"))
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": PTS})
    os.makedirs(str(tmp_path / "work" / "show_mattes" / "sh"))
    (tmp_path / "work" / "show_mattes" / "sh" / "m.0001.exr").write_bytes(b"matte")
    z = str(tmp_path / "show.zip")
    man = ps.pack(p, z, include_sources=True)                                         # project is still OPEN
    s.close()
    assert set(man["files"]) == {"project.stroto", "sources/S/plate.0001.exr", "sources/S/plate.0002.exr",
                                 "mattes/sh/m.0001.exr"}
    out = ps.unpack(z, str(tmp_path / "elsewhere"))
    assert out["missing_sources"] == []
    t = ProjectStore(out["project"])
    assert t.key("P", 1)["points"] == [[float(v) for v in q] for q in PTS]
    sp = t.row("shots", "S")["source_path"]
    assert sp.startswith(str(tmp_path / "elsewhere").replace("\\", "/")) and sp.endswith("plate.####.exr")
    t.close()
    assert os.path.exists(str(tmp_path / "elsewhere" / "show_mattes" / "sh" / "m.0001.exr"))
    with pytest.raises(ValueError):                                                   # destination must be empty
        ps.unpack(z, str(tmp_path / "elsewhere"))
    # without sources: relink by prefix, missing sources reported
    s2 = ProjectStore(p); s2.close()
    z2 = str(tmp_path / "nosrc.zip")
    ps.pack(p, z2)
    new_root = tmp_path / "moved"; new_root.mkdir()
    out2 = ps.unpack(z2, str(tmp_path / "x2"), relink={str(srcdir).replace("\\", "/"): str(new_root)})
    assert out2["missing_sources"][0]["source_path"].startswith(str(new_root).replace("\\", "/"))


def test_unpack_refuses_tampered_or_unsafe_packages(tmp_path):
    p = str(tmp_path / "t.stroto")
    _make(p)[0].close()
    z = str(tmp_path / "t.zip")
    ps.pack(p, z)
    bad = str(tmp_path / "bad.zip")
    with zipfile.ZipFile(z) as zin, zipfile.ZipFile(bad, "w") as zout:
        man = json.loads(zin.read("manifest.json"))
        man["files"]["../evil.txt"] = {"sha256": "0", "bytes": 1}
        zout.writestr("manifest.json", json.dumps(man))
        zout.writestr("project.stroto", zin.read("project.stroto"))
        zout.writestr("../evil.txt", "x")
    with pytest.raises(ValueError, match="unsafe"):
        ps.unpack(bad, str(tmp_path / "u"))
    bad2 = str(tmp_path / "bad2.zip")
    with zipfile.ZipFile(z) as zin, zipfile.ZipFile(bad2, "w") as zout:
        zout.writestr("manifest.json", zin.read("manifest.json"))
        zout.writestr("project.stroto", b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        ps.unpack(bad2, str(tmp_path / "u2"))
    assert not os.path.exists(str(tmp_path / "evil.txt"))
