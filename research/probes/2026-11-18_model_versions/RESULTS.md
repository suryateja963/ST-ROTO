# Model versions side by side, with rollback (T-114, REQ-130) — 2026-11-18

Nuke 17.1v3 Non-commercial, RTX 5060 Laptop (CUDA), real SAM 2.1 tiny export, temporary model locations (the
project's own models are never moved by the tests).

## Design (`st_roto_ai.registry`, `st_roto_nuke.models_ui`, Models panel)

* A model has ONE active version per storage location (the existing layout `manifests/<name>*.json` +
  `onnx/<name>/`, which every loader uses) and any number of ARCHIVED versions, each a complete mini models root:
  `<location>/versions/<name>/<id>/{manifests/, onnx/<name>/, version.json}`. The same verification therefore
  applies to archived versions (licence in the production set, owner approval, pinned revision, every file's size
  and SHA-256), and `name@<id>` loads one SIDE BY SIDE without activating it (`registry.model_dir`).
* Version id = first 12 hex digits of SHA-256 over the export manifest (source revision + every file's SHA-256 and
  size): two exports of the same weights with different tools or settings are different versions.
* Importing over an installed model now ARCHIVES the old one (before T-114 it was deleted). Importing the active
  version again changes nothing.
* Use this version: full verification of the archived version first (nothing changes if anything fails), then
  the active one is archived and the chosen one MOVED into place (models are GBs: moves, not copies); loaded ONNX
  Runtime sessions are released first. Roll back: re-activate the version used before the last change.
  `versions/<name>/history.json` records every import / activation / removal (UTC, from, to, user, note).
* Source weights (`weights/<name>/`) are not versioned: the runtime never loads them.

## Tests

| Test | Result |
|---|---|
| Unit `test_model_versions.py` (fake model) | import archives, same-version import is a no-op, list / ids / sizes, `name@id` resolves and verifies, rollback both ways, history, tampered archive refused with NOTHING changed, unknown id refused, remove, nothing left to roll back reported, `models()` ignores `versions/` |
| Nuke `test_model_versions` (real SAM 2.1 tiny) | v1 = the project's export, v2 = same export with one config key added and re-registered (tool "T-114 test variant"); importing v2 archived v1; **both self-tested side by side on CUDA**: IoU 0.9966 / 0.9966 / 0.9935 each; activating v1 while sessions of both were loaded worked (released first); self-test after activation passed; rollback → v2; history import, import, activate, activate; plugin copy untouched |
| GUI `gui_model_versions.py` (interactive Nuke, Models panel) | versions column 2; versions table USED / kept; Use this version switches; Roll back returns; Remove version deletes the archived one |

## Not done / limits

* Not measured whether Windows would refuse the move WITHOUT releasing sessions first (ST-ROTO always releases).
* An approval workflow for model UPDATES (new upstream revisions) is still the owner-approved download tool
  (CLAUDE.md rule 4); this task manages versions that are already approved and registered.
