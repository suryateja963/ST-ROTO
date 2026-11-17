"""Extra channels as hints (T-110, REQ-113): Cryptomatte, motion vectors, channel statistics, channel reports."""
import json

import numpy as np
import pytest

from st_roto import channels as ch, views
from st_roto import model as m
from st_roto.commands import CommandBus
from st_roto.geometry import mask_to_points
from st_roto.store import ProjectStore

W, H = 120, 80


def disc(cx, cy, r):
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    return r - np.hypot(xx - cx, yy - cy)


def test_murmur3_and_cryptomatte_ids():
    assert ch.murmur3_32(b"") == 0
    assert ch.murmur3_32("hello") == 0x248bfa47                                   # published test vectors
    assert ch.murmur3_32("Hello, world!", 1234) == 0xfaf6cdb3
    assert ch.murmur3_32("The quick brown fox jumps over the lazy dog") == 0x2e4ff723
    assert "%08x" % ch.name_to_id("bunny") == "13851a76"                           # Cryptomatte spec example
    f = ch.id_to_float(ch.name_to_id("bunny"))
    assert np.isfinite(f) and f != 0


def test_crypto_round_trip_with_partial_coverage():
    a = np.clip(disc(40, 40, 15) + 0.5, 0, 1).astype(np.float32)        # anti-aliased edges
    b = np.clip(disc(60, 40, 15) + 0.5, 0, 1).astype(np.float32) * (1 - a)
    bg = 1 - a - b
    ranks = ch.encode_ranks({"background": bg, "ball": a, "box": b})
    chans = {}
    for k, arr in ranks.items():
        for i, c in enumerate("RGBA"):
            chans["Crypto%s.%s" % (k, c)] = arr[..., i]
    assert np.allclose(ch.crypto_mask(chans, "Crypto", "ball"), a, atol=1e-6)
    assert np.allclose(ch.crypto_mask(chans, "Crypto", ["ball", "box"]), a + b, atol=1e-6)
    nuke_style = {k.replace(".R", ".red").replace(".G", ".green").replace(".B", ".blue").replace(".A", ".alpha"): v
                  for k, v in chans.items()}
    assert np.allclose(ch.crypto_mask(nuke_style, "Crypto", "box"), b, atol=1e-6)
    with pytest.raises(ValueError):
        ch.crypto_mask(chans, "CryptoAsset", "ball")
    attrs = ch.manifest_attributes("Crypto", ["ball", "box"])
    found = ch.find_layers({"exr/" + k: v for k, v in attrs.items()})
    assert found == {"Crypto": {"ball": ch.name_to_id("ball"), "box": ch.name_to_id("box")}}


def test_resolve_channel_names():
    c = {"R": 1, "A": 2, "depth.Z": 3, "N.X": 4, "CryptoObject00.R": 5}
    assert ch.resolve(c, "rgba.red") == 1 and ch.resolve(c, "rgba.alpha") == 2 and ch.resolve(c, "depth.Z") == 3
    assert ch.resolve(c, "CryptoObject00.red") == 5
    with pytest.raises(KeyError):
        ch.resolve(c, "P.X")
    assert ch.layers_of(["R", "G", "depth.Z", "forward.u", "forward.v"]) == ["rgba", "depth", "forward"]


def _texture(seed=1):
    rng = np.random.RandomState(seed)
    t = rng.rand(H, W).astype(np.float32)
    k = np.ones(5) / 5
    for ax in (0, 1):
        t = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), ax, t)
    return t


def test_vector_convention_detected_per_axis():
    a = _texture()
    dx, dy = 3.0, -2.0                                    # canonical: right 3, UP 2 (rows decrease)
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    b = ch._bilinear(a, xx - dx, yy - dy)                 # B(x) = A(x - d)
    u = np.full((H, W), dx, np.float32)
    v = np.full((H, W), -dy, np.float32)                  # stored y-up (Nuke)
    r = ch.choose_convention([ch.vector_errors(a, b, u, v)])
    assert r["convention"] == "u right, v up (Nuke)" and r["undetermined"] == []
    r2 = ch.choose_convention([ch.vector_errors(a, b, u, -v)], default="u right, v up (Nuke)")
    assert r2["convention"] == "u right, v down"
    # nothing moves vertically: the v sign cannot be told, the default's is used and reported
    b_h = ch._bilinear(a, xx - dx, yy)
    r3 = ch.choose_convention([ch.vector_errors(a, b_h, u, np.zeros_like(v))], default="u right, v down")
    assert "v" in r3["undetermined"] and r3["convention"] == "u right, v down"
    with pytest.raises(ValueError):
        ch.vector_errors(a, a, np.zeros_like(u), np.zeros_like(v))


def test_warp_points_moves_points_and_handles():
    pts = [[10, 10, 9, 10, 11, 10], [20, 30, 19, 30, 21, 30]]
    u = np.full((H, W), 4.0, np.float32)
    v = np.full((H, W), 2.0, np.float32)
    out = ch.warp_points(pts, u, v, "u right, v up (Nuke)")
    assert np.allclose(out, [[14, 8, 13, 8, 15, 8], [24, 28, 23, 28, 25, 28]])


def test_channel_spikes_not_trends():
    trend = {f: 20 - 0.4 * f for f in range(20)}
    assert ch.channel_jumps(trend) == {}
    sine = {f: np.sin(f / 3.0) for f in range(20)}                     # crosses zero: no flags
    assert ch.channel_jumps(sine) == {}
    spike = dict(trend)
    spike[7] = 40.0                                                    # the shape grabbed something far behind
    assert list(ch.channel_jumps(spike)) == [7]
    assert ch.channel_jumps({0: 1.0, 1: 5.0}) == {}


def test_check_object_and_flags():
    # a disc moving right 3 px/frame; frame 3's shape is wrongly left behind (stuck)
    frames = range(6)
    keys = {f: [mask_to_points(disc(30 + 3 * f, 40, 12), count=16)] for f in frames}
    keys[3] = keys[2]
    depth = {f: np.where(disc(30 + 3 * f, 40, 12) > 0, 10.0, 50.0).astype(np.float32) for f in frames}
    names = {"bg": None, "obj": None}

    def chans(f):
        cov = (disc(30 + 3 * f, 40, 12) > 0).astype(np.float32)
        r = ch.encode_ranks({"bg": 1 - cov, "obj": cov})
        c = {"depth.Z": depth[f], "forward.u": np.full((H, W), 3.0, np.float32),
             "forward.v": np.zeros((H, W), np.float32)}
        for k, arr in r.items():
            for i, s in enumerate("RGBA"):
                c["C%s.%s" % (k, s)] = arr[..., i]
        return c
    rep = ch.check_object(frames, lambda f: keys[f], chans, H, W, stats=("depth.Z",),
                          motion={"u": "forward.u", "v": "forward.v", "convention": "u right, v up (Nuke)"},
                          crypto={"layer": "C", "names": ["obj"]})
    assert sorted(rep) == list(frames) and "motion_iou" not in rep[0]
    assert rep[2]["motion_iou"] > 0.95 and rep[3]["motion_iou"] < 0.85 and rep[3]["crypto_iou"] < 0.9
    flagged = dict(ch.review_flags(rep))
    assert 3 in flagged and "motion vectors" in flagged[3] and "Cryptomatte" in flagged[3]
    assert 1 not in flagged and 2 not in flagged
    assert names                                                      # (unused helper dict keeps flake quiet)


def test_occlusion_by_another_surface_is_ignored_but_stuck_shapes_are_not():
    # object moves right 4 px; an occluder strip covers columns 50-59 on frame f only (it came from the left)
    prev = disc(40, 40, 12) > 0
    cur_true = (disc(44, 40, 12) > 0)
    strip = np.zeros((H, W), bool); strip[:, 50:60] = True
    cur = cur_true & ~strip
    fu = np.where(prev, 4.0, 0.0).astype(np.float32)
    fu[:, 30:40] = np.where(prev[:, 30:40], 4.0, 20.0)                # occluder at f-1 (cols 30-39) moves +20
    fv = np.zeros((H, W), np.float32)
    bu = np.where(cur_true, -4.0, 0.0).astype(np.float32)
    bu[strip] = -20.0
    bv = np.zeros((H, W), np.float32)
    occ = ch.occluded_object_pixels(prev, cur, fu, fv, bu, bv, "u right, v up (Nuke)")
    hidden_part = cur_true & strip
    assert occ[hidden_part].mean() > 0.9                              # object covered by the strip: ignored
    stuck = prev                                                     # shape left on the previous frame
    region = ~ch.occluded_object_pixels(prev, stuck, fu, fv, bu, bv, "u right, v up (Nuke)")
    assert ch.mask_iou(cur_true, stuck, region) < 0.85               # the stuck error still counts


def project(tmp_path):
    s = ProjectStore(str(tmp_path / "p.stroto")); bus = CommandBus(s)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "shot", "width": W, "height": H}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "obj"}}, actor=m.ACTOR_AI)
    bus.execute({"op": "create_shape", "row": {"id": "Os", "object_id": "O", "name": "obj", "point_count": 16}},
                actor=m.ACTOR_AI)
    for f in range(5):
        bus.execute({"op": "set_key", "shape_id": "Os", "frame": f,
                     "points": mask_to_points(disc(40 + f, 40, 12), count=16)}, actor=m.ACTOR_AI)
    return s, bus


def test_channel_reports_in_store_review_and_undo(tmp_path):
    s, bus = project(tmp_path)
    assert s.schema_version() == 12
    ops = [{"op": "set_channel_report", "object_id": "O", "frame": f,
            "data": {"stats": {"depth.Z": 10.0 if f != 2 else 60.0}, "motion_iou": 0.99, "crypto_iou": 0.98}}
           for f in range(5)]
    bus.execute({"op": "batch", "ops": ops})
    assert s.channel_reports("O")[2]["stats"]["depth.Z"] == 60.0
    flags = [x for x in views.review_for_object(s, "O") if x[2].startswith("channels:")]
    assert [x[0] for x in flags] == [2] and flags[0][1] == "check" and "depth.Z" in flags[0][2]
    # locked objects still get diagnostics (they never change the shape)
    bus.execute({"op": "update_object", "id": "O", "fields": {"locked": 1}})
    bus.execute({"op": "set_channel_report", "object_id": "O", "frame": 9, "data": {"motion_iou": 0.5}})
    bus.undo(); bus.undo()
    assert 9 not in s.channel_reports("O")
    # delete the object and undo: reports come back
    bus.execute({"op": "delete_subtree", "object_id": "O"})
    assert s.channel_reports("O") == {}
    bus.undo()
    assert len(s.channel_reports("O")) == 5
    bus.undo()                                                       # the batch
    assert s.channel_reports("O") == {}
    with pytest.raises(KeyError):
        bus.execute({"op": "set_channel_report", "object_id": "nope", "frame": 0, "data": {}})
    json.dumps(s.channel_reports("O"))
