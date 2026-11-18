# Scene-cut detection (T-123, REQ-090, acceptance criterion 7) — 2026-11-18

`st_roto.scenecut`: 64x36 display-encoded thumbnails; per consecutive pair the colour-histogram distance (1 -
intersection of 8x8x8 joint RGB histograms) and the mean thumbnail difference. A cut is called when the histogram
distance is >= HIST_MIN, the difference is >= 0.08, and the histogram distance is >= RATIO x the median of the 8
neighbouring pair scores. A jump is rejected as a flash or glitch if the content before it returns within 3 frames,
or if the frame after it matches one up to 2 frames before it.

## Real footage (SA-V subset, CC BY 4.0, D-031): 30 videos, 2,846 frames

The frames are **6-fps samples**, so motion between frames is ~4x larger than in a 24-fps plate: a hard test for
false alarms.

* (a) every video on its own: false cuts inside continuous shots;
* (b) every video joined to the next one: a real cut must be found exactly at the junction;
* (c) a white frame, or one frame of another video, inserted: must NOT be a cut.

The first version used RATIO 3.0 and HIST_MIN 0.35, and its flash rule only looked forward:

| | result |
|---|---|
| (b) junctions | 29 / 30 (the missed one had a histogram distance of 0.255 but stood out 5.8x) |
| (a) "false" cuts | 7 in 2,816 pairs |
| (c) flashes counted as cuts | **31 of 30** sequences: the jump back OUT of the flash was called a cut |

**Looking at the 7 by eye** (contact sheets): 4 are real camera cuts inside the SA-V videos — sav_050687 frames
10, 23 and 59 (badminton, different camera angles) and sav_006251 frame 104 (jump cut). They are counted as
"edits_in_video", not as false cuts. The other 3 are fast handheld motion that stood out only 3.1-3.3x from its
neighbours.

**Fixes:**
* the flash rule now also checks backwards (jump OUT of a flash);
* its pixel test was loosened to 0.75x, because fast motion had defeated it by 0.001;
* RATIO and HIST_MIN were swept (`sweep.py`, `result_sweep.json`).

| RATIO / HIST_MIN | junctions found | in-video edits found | false cuts | white flashes as cuts | 1-frame glitches as cuts |
|---|---|---|---|---|---|
| 3.0 / 0.35 | 29/30 | 3/4 | 4 | 2 | 2 |
| 4.0 / 0.25 | 30/30 | 4/4 | 1 | 1 | 1 |
| **5.0 / 0.25 (chosen)** | **30/30** | **4/4** | **0** | **0** | **0** |
| 6.0 / 0.25 | 27/30 | 3/4 | 0 | 0 | 0 |

**Caveat: the thresholds were chosen on this same set** (no held-out footage). RATIO 6 already misses cuts, so the
margin is modest. On real 24-fps plates motion between frames is smaller, which lowers the neighbourhood median and
should make cuts stand out more, but that was not measured. Dissolves and fades are not detected (by design); the
artist can type cut frames into the knob.

## In Nuke (`tests/nuke` `test_scene_cuts`)

Synthetic shot with a hard cut at frame 6 (frames 6-11 are the same scene with channels swapped and inverted, i.e.
another "shot" with structure the tracker could follow):
* **Track** with an empty knob detected the cut, filled the knob (`6`), stopped the object at frame 6 ("stopped at
  scene cut: target at 6 (prompt the object again after the cut)") and kept keys 0-5 only;
* **Detect cuts** found `6` (12 frames checked);
* **Re-track** on frame 2 worked on "frames 0-5 only ... the shot segment between scene cuts", and the keys stayed
  at 0-5.

Unit tests: `tests/unit/test_scenecut.py` (hard cut, fast pan, flash, glitch, two cuts with frame numbers, uint8 and
linear input, segments and parsing).

Files: `probe_sav.py` (first run, `result_sav.json`), `cache_thumbs.py` (thumbnail cache in `tmp/`, not committed),
`sweep.py`.
