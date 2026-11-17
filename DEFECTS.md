# ST-ROTO defect register

Every known defect: what is wrong, how to reproduce it, severity, status. Acceptance criterion 20 ("no critical
release-blocking defects", docs/ACCEPTANCE.md) is checked by `tools/acceptance/run_acceptance.py`: the run fails if
any row has **Blocks release = yes** and status **open**.

Severity: **critical** (data loss / wrong output without warning), **major** (feature unusable or misleading),
**minor** (workaround exists / cosmetic). Limitations of Nuke or of a licence are not defects: they are in
RISK_REGISTER.md and docs/ACCEPTANCE.md.

| ID | Found | Defect | Reproduce | Severity | Blocks release | Status | Fix / note |
|---|---|---|---|---|---|---|---|
| DEF-001 | 2026-11-17 | Combined EXR matte used the MAXIMUM of the objects, Nuke's Roto render composites them OVER each other: soft edges of two overlapping objects differed (0.5 vs 0.75) | two objects with soft/blurred edges overlapping; compare `rgba.alpha` of the EXR with the node's render | major | no | fixed | T-105: combined matte = `views.combine_roles` always; `test_combined_matte_is_over_not_max_on_soft_overlaps` |
| DEF-002 | 2026-11-17 | Backups made within one Windows clock tick (~2 ms) got the same name; the later overwrote the earlier | two `persistence.backup` calls in a row | critical | yes | fixed | T-104: exclusive name reservation; `test_backups_with_the_same_timestamp_never_overwrite` |
| DEF-003 | 2026-11-17 | Re-rendering mattes failed ("Access is denied", stray .part) while a Nuke Read showed the previous EXRs | render mattes, read them in Nuke, render again | major | no | fixed | T-099: new version folder when files are in use |
| DEF-004 | 2026-11-17 | Plates above 1920x1080 could not be tracked in Nuke Non-commercial | Track on a UHD plate in NC | major | no | fixed | T-089: reduced AI render |
| DEF-005 | 2026-11-17 | Mixed-resolution sequences gave wrong shapes without any warning | half-res frames inside a full-res sequence | critical | yes | fixed | T-086 |
| DEF-006 | 2026-11-17 | 'Save Roto edits to project' recorded nothing before a first Track | draw by hand in a new node, press Save | critical | yes | fixed | T-088 |
| DEF-007 | 2026-11-17 | 'Lock range' is enforced by the re-track path only; the command bus does not refuse AI writes to locked frames | (no current AI path writes them; a future one could) | minor | no | open | enforce in the command bus before any new AI write path |
| DEF-008 | 2026-11-17 | Re-prompt on a LOCKED frame is refused with the message for artist keys ("you have your own key") | lock frames, Re-prompt here on one of them | minor | no | fixed | T-105: "frame N is locked: press Unlock range for it first" (verified in test_propagation_controls) |
| DEF-009 | 2026-11-17 | ST-ROTO-Setup.exe is not code-signed: Windows SmartScreen warns | run the .exe on a fresh machine | minor | no | open | needs a signing certificate (owner decision) |

Earlier fixed defects are recorded in DEVELOPMENT_LOG.md and the RESULTS files of each task.
