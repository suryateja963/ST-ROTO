"""st_roto.calibration (T-068): bad-frame labels and threshold grid."""
from st_roto.calibration import evaluate, flags_for, label_bad
from st_roto import quality


def rec(frame, score, ipred, iou, vis=True, seq="a"):
    return {"seq": seq, "frame": frame, "object_score": score, "iou_pred": ipred, "iou_true": iou, "truth_visible": vis}


def test_label_bad():
    assert label_bad(rec(0, 2.0, 0.9, 0.95)) is False
    assert label_bad(rec(0, 2.0, 0.9, 0.5)) is True                    # wrong mask
    assert label_bad(rec(0, -1.0, 0.9, 0.0)) is True                   # visible but reported absent
    assert label_bad(rec(0, 2.0, 0.9, 0.0, vis=False)) is True         # absent but reported present
    assert label_bad(rec(0, -2.0, None, 1.0, vis=False)) is False


def test_grid_finds_the_separating_threshold_and_restores_globals():
    # frames 0-9 good with high scores; 10-12 bad with scores 0.6-0.8 (uncertain); thresholds 1.0 catches them
    rs = [rec(f, 5.0, 0.9, 0.97) for f in range(10)] + [rec(f, 0.7, 0.9, 0.6) for f in range(10, 13)] \
        + [rec(f, 5.0, 0.9, 0.97) for f in range(13, 20)]
    ev = evaluate(rs, margins=(0.5, 1.0), iou_mins=(0.0,))
    by = {(g["margin"], g["iou_min"]): g for g in ev["grid"]}
    assert by[(1.0, 0.0)]["recall"] == 1.0 and by[(1.0, 0.0)]["precision"] == 1.0
    assert by[(0.5, 0.0)]["recall"] == 0.0
    assert ev["best"]["margin"] == 1.0 and ev["bad"] == 3
    assert (quality.OBJECT_SCORE_MARGIN, quality.IOU_PRED_MIN) == (1.0, 0.7)    # module thresholds untouched
    assert flags_for(rs, 1.0, 0.0)[11] is True
