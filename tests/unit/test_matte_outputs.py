"""Matte outputs and refinement (T-099, REQ-100/101): offset (erode/dilate), edge blur, core/edge layers, foreground
RGB premultiplied / straight with the convention written into the file."""
import json

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from st_roto import matte                                   # noqa: E402
from st_roto import model as m                              # noqa: E402
from st_roto.commands import CommandBus                     # noqa: E402
from st_roto.geometry import mask_to_points                 # noqa: E402
from st_roto.store import ProjectStore                      # noqa: E402

W, H = 120, 90


def disc(r, cx=60, cy=45):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    return (np.hypot(xx - cx, yy - cy) <= r).astype(np.float32)


def test_offset_grows_and_shrinks():
    a = disc(20)
    assert np.array_equal(matte.offset_alpha(a, 0), a)
    big, small = matte.offset_alpha(a, 3).sum(), matte.offset_alpha(a, -3).sum()
    assert abs(big - np.pi * 23 ** 2) / (np.pi * 23 ** 2) < 0.05
    assert abs(small - np.pi * 17 ** 2) / (np.pi * 17 ** 2) < 0.05


def test_blur_edge_only_softens_the_edge():
    a = disc(20)
    b = matte.blur_edge(a, 2.0)
    assert b[45, 60] == pytest.approx(1.0, abs=1e-4) and b[2, 2] == pytest.approx(0.0, abs=1e-4)
    assert 0.2 < b[45, 80] < 0.8                                   # on the edge (x = 60 + 20)
    assert abs(b.sum() - a.sum()) / a.sum() < 0.02                 # coverage preserved
    assert np.array_equal(matte.blur_edge(a, 0), a)


def test_core_edge_split():
    a = matte.blur_edge(disc(20), 1.5)
    core, edge = matte.core_edge(a, 4)
    assert (core <= a + 1e-6).all() and np.allclose(core + edge, a, atol=1e-6)
    assert core[45, 60] == pytest.approx(1.0, abs=1e-4) and edge[45, 60] == pytest.approx(0.0, abs=1e-4)
    assert edge[45, 79] > 0.1                                      # the band near the edge


def test_foreground_rgb_conventions():
    rgb = np.random.RandomState(1).rand(H, W, 3).astype(np.float32)
    a = matte.blur_edge(disc(20), 1.0)
    assert np.allclose(matte.foreground_rgb(rgb, a, "premultiplied"), rgb * a[..., None])
    assert np.array_equal(matte.foreground_rgb(rgb, a, "straight"), rgb)
    with pytest.raises(ValueError):
        matte.foreground_rgb(rgb, a, "unpremult-ish")


def test_render_mattes_writes_rgb_core_edge_and_convention(tmp_path):
    pytest.importorskip("OpenEXR")
    import OpenEXR
    from st_roto import exr
    from st_roto_nuke.mattes import render_mattes
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot", "width": W, "height": H}})
    bus.execute({"op": "create_object", "row": {"id": "A", "shot_id": "S", "name": "hero"}})
    bus.execute({"op": "create_shape", "row": {"id": "As", "object_id": "A", "name": "hero", "point_count": 24}})
    bus.execute({"op": "set_key", "shape_id": "As", "frame": 0, "points": mask_to_points(disc(20) - 0.5, count=24)},
                actor=m.ACTOR_ARTIST)
    plate_img = np.random.RandomState(2).rand(H, W, 3).astype(np.float32)
    rep = render_mattes(lambda f: plate_img, s, "S", [0], str(tmp_path / "m"), soft=False, rgb_mode="premultiplied",
                        offset_px=2, blur_px=1.0, core_edge_px=3)
    ch = exr.read_channels(rep["files"][0])
    assert {"R", "G", "B", "A", "hero.A", "core_matte.A", "edge_matte.A"} <= set(ch)
    a = ch["A"]
    assert np.allclose(np.stack([ch["R"], ch["G"], ch["B"]], -1), plate_img * a[..., None], atol=1e-5)
    assert np.allclose(ch["core_matte.A"] + ch["edge_matte.A"], a, atol=1e-5)
    assert a.sum() > disc(20).sum()                                # offset +2 grew it
    meta = json.loads(OpenEXR.File(rep["files"][0]).header()["st_roto"])
    assert meta["alpha_convention"] == "premultiplied" and meta["offset_px"] == 2 and meta["core_edge_px"] == 3
    st = render_mattes(lambda f: plate_img, s, "S", [0], str(tmp_path / "s"), soft=False, rgb_mode="straight")
    ch2 = exr.read_channels(st["files"][0])
    assert np.allclose(np.stack([ch2["R"], ch2["G"], ch2["B"]], -1), plate_img, atol=1e-6)
    assert json.loads(OpenEXR.File(st["files"][0]).header()["st_roto"])["alpha_convention"] == "straight"
    plain = render_mattes(lambda f: plate_img, s, "S", [0], str(tmp_path / "p"), soft=False)
    assert "R" not in exr.read_channels(plain["files"][0])          # default: alpha only, as before
    s.close()


def test_version_dir_and_lock_check(tmp_path):
    from st_roto import exr
    d = str(tmp_path / "mattes")
    assert exr.next_version_dir(d) == d + "_v002"
    (tmp_path / "mattes_v002").mkdir()
    assert exr.next_version_dir(d + "/") == d + "_v003"
    p = tmp_path / "a.exr"
    assert not exr.is_locked(str(p))                           # missing file: not locked
    p.write_bytes(b"x")
    assert not exr.is_locked(str(p)) and p.exists()            # free file: renamed away and back, still there


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows file sharing semantics")
def test_open_file_is_locked_on_windows(tmp_path):
    from st_roto import exr
    p = tmp_path / "b.exr"
    p.write_bytes(b"x")
    with open(str(p), "rb"):                                   # like a Nuke Read node: open without delete sharing
        assert exr.is_locked(str(p))
    assert not exr.is_locked(str(p))
