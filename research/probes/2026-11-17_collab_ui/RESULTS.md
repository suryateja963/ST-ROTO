# T-094 — Collaboration in the Nuke UI: leases, presence, roles, signing keys (REQ-170/171), 2026-11-17

**Feature.** The ST-ROTO Objects panel gains a **held by** column (`you`, `bob`, `bob (idle 23 min)`,
`bob (offline)`), buttons **Take**, **Release**, **Override** (supervisors, D-035/D-036), **Set up signing key**
(creates the key in the D-038 user folder, never in the project, and registers it: the artist's changes are signed
from then on, D-037) and **Set role…** (first role = the author making themself admin; then admins assign roles), a
status line (`you: alice (admin) · key registered · collaboration on (signed changes) · online: … · idle/offline: …`)
and a presence heartbeat every 60 s while the panel is open. Opening a project signs automatically when the artist's
key file exists. Logic in `st_roto_nuke.collab` (no Qt); rules unchanged in the core (`st_roto.leases`,
`st_roto.signing`). `ST_ROTO_KEY_DIR` overrides the key folder (tests, managed home folders).

**Evidence.**

- `tests/nuke` `test_collaboration_ui` (headless Nuke, throw-away key folder, simulated bob = artist and
  carol = supervisor on the same project; `results_test_collaboration_ui.json`): role bootstrap; key created and
  registered, next change signed; take -> `you`, release -> free; bob's lease refuses alice ("object O is leased by
  bob"); carol's override refused while bob is active ("bob was active 0 min ago: a supervisor may override only
  after 15 min without activity"); bob idle 20 min -> `bob (idle 20 min)`; alice (admin, not supervisor) refused
  ("only a supervisor may override bob's lease"); carol's override succeeds and stores the evidence (holder, last
  heartbeat, idle 1,200 s, threshold 900 s); history: 5 signed ops all valid, 0 bad; after closing and reopening the
  project alice's changes are signed again automatically.
- `gui_panel_collab.py` (interactive Nuke, `result_gui_panel_collab.json`): the real panel: Set role, select row,
  Take -> cell `you`; Set up signing key -> "signing key created and registered", status line updated; Release ->
  cell empty; heartbeat recorded presence.
- The owner's real key folder (`%USERPROFILE%\.st_roto\keys`) was not created or touched by the tests.

**Not covered (still prototype for real teams).** No network transport: co-workers share a project only through
the file-based replication prototype (`st_roto.sync`), which is not wired to the UI; bob and carol were simulated in
one process. Key revocation has no button yet (core `signing.revoke`). Presence of other artists appears only after
their changes reach this project file.
