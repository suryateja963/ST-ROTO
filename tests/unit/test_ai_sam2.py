"""st_roto_ai SAM 2.1 adapters. Need locally exported models (not in the repository: weights are never committed,
D-008), so these tests SKIP in CI and run on the development machine. CPU only, to stay deterministic."""
import json
import os

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMG_DIR = os.path.join(ROOT, "models", "onnx", "sam2.1-hiera-tiny")
VID_DIR = os.path.join(IMG_DIR, "video")
SAM_PROBE = os.path.join(ROOT, "research", "probes", "2026-11-15_sam2")
VID_PROBE = os.path.join(ROOT, "research", "probes", "2026-11-15_video")

ort = pytest.importorskip("onnxruntime")
cv2 = pytest.importorskip("cv2")
needs_image = pytest.mark.skipif(not os.path.exists(os.path.join(IMG_DIR, "encoder.onnx")), reason="exported model not present")
needs_video = pytest.mark.skipif(not (os.path.exists(os.path.join(VID_DIR, "vencoder.onnx"))
                                      and os.path.exists(os.path.join(VID_PROBE, "ref_logits_sam2.1-hiera-tiny.npz"))
                                      and os.path.exists(os.path.join(VID_PROBE, "frames", "meta.json"))),
                                 reason="exported video model / reference / frames not present")


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def test_runtime_reports_cpu_honestly():
    from st_roto_ai.runtime import open_session
    if not os.path.exists(os.path.join(IMG_DIR, "decoder.onnx")):
        pytest.skip("exported model not present")
    sess, rep = open_session(os.path.join(IMG_DIR, "decoder.onnx"), device="cpu")
    assert rep.active == "cpu" and not rep.fallback


@needs_image
def test_image_click_to_points():
    from st_roto_ai.sam2 import Sam2Image
    from st_roto.geometry import mask_to_points, rasterize_spline, Anchor
    img = cv2.cvtColor(cv2.imread(os.path.join(SAM_PROBE, "test_image.png")), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    gt = cv2.imread(os.path.join(SAM_PROBE, "test_gt.png"), cv2.IMREAD_GRAYSCALE) > 127
    sam = Sam2Image(IMG_DIR, device="cpu")
    out = sam.predict(sam.encode(img), [(820.0, 480.0)], [1])
    assert iou(out["logits"] > 0, gt) > 0.99
    pts = mask_to_points(out["logits"])                                    # sub-pixel from logits
    anchors = [Anchor(p=np.array(p[:2]), h_in=np.array(p[2:4]), h_out=np.array(p[4:]), corner=False) for p in pts]
    shape = rasterize_spline(anchors, *gt.shape)
    assert iou(shape, out["logits"] > 0) > 0.995 and iou(shape, gt) > 0.99


@needs_video
def test_video_tracker_matches_pytorch_reference_first_frames():
    """Same pixels as the PyTorch reference would need its processor; here we use our own preprocessing and
    require near-identical masks on the first 6 frames (full 48-frame equality is in the probe)."""
    from st_roto_ai.sam2 import Sam2Video
    meta = json.load(open(os.path.join(VID_PROBE, "frames", "meta.json")))
    ref = np.load(os.path.join(VID_PROBE, "ref_logits_sam2.1-hiera-tiny.npz"))
    W, H = meta["w"], meta["h"]
    trk = Sam2Video(VID_DIR, device="cpu", num_total_frames=meta["frames"])
    for i in range(6):
        rgb = cv2.cvtColor(cv2.imread(os.path.join(VID_PROBE, "frames", "frame_%04d.png" % i)), cv2.COLOR_BGR2RGB)
        enc = trk.encode(rgb.astype(np.float32) / 255)
        out = trk.add_points(0, enc, [tuple(meta["click_xy"])], [1]) if i == 0 else trk.track(i, enc)
        mr = cv2.resize(ref["f%04d" % i].astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR) > 0
        assert iou(out["logits"] > 0, mr) > 0.995, i
