# T-086 — Difficult frame sequences (REQ-092, master prompt §11), 2026-11-17

**Question.** Does the product (ST_Roto node: Track, Re-track, mattes) work on the sequence conditions §11 lists?

**Method.** `make_sequences.py` builds variants of the synthetic shot (frames + truth, `out/`, git-ignored);
`probe_sequences.py <case>` runs the real node in Nuke 17.1 NC (SAM 2.1 tiny, CUDA, one click on the first frame),
then Re-track and soft mattes, and scores every key against the truth of the image Nuke actually showed on that
frame (identified by pixel comparison, so retimes are scored correctly). `summarise.py` prints the results
(`out/result_<case>.json`, kept locally).

## Before T-086

| case | result |
|---|---|
| start frame 1001 (1001-1010) | works, IoU 0.994-0.996 |
| duplicate frames (a 3-frame hold) | works, 0.994-0.996 |
| retimed (Retime node, speed 0.5, upstream) | works, 0.993-0.996: ST-ROTO tracks what Nuke shows |
| **missing frames** (4-5 deleted) | **Track failed**: `Read error: No such file or directory` |
| **discontinuous** (0-4, 20-24) | **Track failed** (same) |
| **proxy mode on** (scale 0.5) | **Track failed**: `You must specify a proxy file name to write to` |
| **mixed resolution** (frames 5-9 at 640x360 in a 1280x720 shot) | **silently wrong**: no error, shapes of frames 5-9 in the wrong place (IoU 0.0) |

## Fixes

- `st_roto_nuke.pixels`: an unreadable frame raises `FrameUnavailable` (Nuke's missing-file errors only; any other
  render error still fails the run). The pixel Write node gets a proxy file name. `fit_to_format` brings a frame of
  another size to the shot format like Nuke's default Reformat (scale to the format width, centred).
- Track / Re-track skip unreadable frames: no key there (Roto interpolates), the tracker keeps true time positions
  (the memory of skipped positions is simply absent, the same mechanism upstream SAM 2 uses when a memory frame does
  not exist). An unreadable prompt / conditioning frame is a clear error. Checkpoints carry the skipped frames, so
  Resume reports them too.
- Mattes: a frame whose plate cannot be read gets a hard matte (shapes need no plate) and is listed.
- Every status names the skipped frames and the refitted frames (with their size, and a proxy-mode warning).

## After T-086 (same probe)

| case | Track | Re-track | mattes | key IoU |
|---|---|---|---|---|
| missing 4-5 | done, 8 keys, "2 unreadable frame(s) skipped (no key): 4-5" | done, same note | 10 EXR, 4-5 hard edges (listed) | 0.994-0.996 |
| discontinuous 0-4, 20-24 | done, "15 unreadable frame(s) skipped: 5-19" | done | 25 EXR | 0.994-0.996 except frame 23: 0.566 (*) |
| mixed resolution | done, "5 frame(s) at another resolution (640x360) were fitted to 1280x720 like a default Reformat: frames 5-9" | done | done | 0.993-0.996 |
| proxy on (0.5) | done, refit note + "proxy mode is on: full accuracy needs proxy off" | done | done | 0.990-0.992 (vs 0.994-0.996 at full resolution) |
| start 1001, duplicate | unchanged | done | done | 0.994-0.996 |

(*) Frame 23 is the synthetic shot's known split frame: the occluder cuts the object in two and the cut-off piece
is a separate part shape (T-049); only the main shape is scored here. Same as without a gap (T-055/T-049), so not
caused by the 15-frame gap. After the gap the object was found again at 0.995 on frame 20.

Regression tests: `tests/unit/test_sequences.py` (fit_to_format in CI; locally: skipped frames reported, keys before
the gap identical to a run without the gap, prompt on an unreadable frame refused, cancel + resume across a gap
identical) and `tests/nuke` `test_difficult_sequences` (missing + half-res frames, then Re-track in proxy mode:
passes, IoU >= 0.985 with 320x180 proxy frames).

## Decision taken (reversible, reported to the owner)

**Frames of another resolution are fitted to the shot format like a default Reformat** and the shapes live in the
shot format. Nuke itself shows such a frame at its own size (bottom-left, unscaled), so on those frames the plate
and the shapes only line up if the artist puts a Reformat to the shot format above ST_Roto, which the status
suggests by naming the frames. Alternatives: refuse mixed-resolution input with an error, or track each frame in
its own size and place shapes bottom-left. Recorded as D-039 (proposed).

## Not covered

- Variable frame rate: Nuke sequences have one rate per script; what reaches ST_Roto is frames, whatever the source
  rate (a retime upstream is covered above). Containers with variable rate (movies) were not tested.
- Real footage for these cases (synthetic shot only); Retime with blending filters (only `filter none` measured);
  Read nodes set to 'on error: nearest frame / black' give images, which ST-ROTO tracks like any other frame.
