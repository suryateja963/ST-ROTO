# Stereo Track checkpoints + Resume (T-119, follow-up of T-109) — 2026-11-18

Nuke 17.1v3 Non-commercial, CUDA, synthetic stereo shot (`research/probes/2026-11-17_stereo`), 20 frames.

## Design

A stereo Track is a sequence of passes (prompt view, then each other view). It now keeps, in the shot's checkpoint
folder (`<project>_cache/track_resume/<shot>/`):
* `stereo.json`: views, prompt view, the prompt-view objects, frames, model / colour / anchors / parts, the prompts
  derived for each other view (with their disparity reports), and which passes are finished;
* `result_<view>.json`: the full result of each finished pass (frame keys restored exactly on load);
* `pass_<view>/`: the running pass's own checkpoint every 10 frames and on Cancel (T-048 machinery).
Resume reloads finished passes, continues the interrupted pass from its checkpoint, reuses the derived prompts (no
new disparity search) and runs the remaining views; it refuses if the AI input colour, the script's views or the
prompt view changed. Out of GPU memory mid-stereo-run now continues on the CPU from the checkpoint (before: redone).
A finished run removes the whole checkpoint.

## Test (`tests/nuke` `test_stereo_resume`)

| Step | Result |
|---|---|
| Cancel during the right view's pass | job cancelled; `stereo.json` done = [left]; right pass checkpoint next frame 13; status: "'Resume track' continues the right view from frame 13 (finished: left)" |
| Resume track (node prompts cleared) | done (resumed): target_left + target_right, 20 keys each; checkpoint removed |
| vs an uninterrupted stereo run of the same prompt (second project) | identical: max key difference **0.0** over both views and all 20 frames |
