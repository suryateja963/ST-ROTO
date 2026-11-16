# Optional collaboration — architecture and implications of the owner's decisions (T-020, T-035)

Status: **Proposed** (2026-11-16). Requirements: master prompt §19, REQ-170/171/293; decisions D-022…D-025; open OQ-16/OQ-17. Collaboration stays optional: a solo artist uses every feature with no network, server or account (§19).

## 1. What already exists (measured, in the product code)

- Every edit is ONE operation in the project database, applied in a transaction and logged with author, actor, payload and **inverse** (`operations` table, ADR-0006); undo/redo are operations too.
- All objects/shapes have UUIDs (`model.new_id`), so two copies of a project share identities.
- Keys are stored per (shape, frame) with provenance (`origin`), so edits are naturally fine-grained.
- Projects travel as checksummed packages (T-071/T-075); backups and crash recovery exist.

This is the foundation of an **operation-based replication** design: peers exchange operations, not files.

## 2. Implications of each decision

| Decision | Implication for the design |
|---|---|
| **D-022** one sync system; central server when configured, otherwise peer-to-peer | One replication protocol with two transports. The server is just an always-on peer that stores and relays operations (no different merge logic). Peer discovery (LAN: mDNS) only when no server is configured. |
| **D-023** disconnected edits kept as branches; object owner chooses/merges per frame/keyframe; non-overlapping frames merge automatically | Merge unit = (shape, frame) key (+ object/shape attributes). Each operation carries a site id and a Lamport clock; each peer remembers, per other peer, the last operation it has seen. When two sites changed the **same** key since their common point, the remote version is stored as a **branch candidate** (not applied); different keys merge automatically. A review UI lists candidates per object; only the object owner (or a supervisor, D-024) resolves them; the resolution is itself an operation. |
| **D-024** ownership transferable; supervisor reassigns (audited); supervisor lock override only when holder offline/idle (OQ-16/17 to confirm) | Objects get an `owner` and locks become **leases** (holder, acquired, last-heartbeat). Presence heartbeats (§19.1 "who is working, frame, activity") feed the idle test. Ownership changes and overrides are operations → audit trail for free. The idle threshold is OQ-17 (proposal: 15 min without heartbeat). |
| **D-025** freelancers as normal artist accounts, removed by an admin | Accounts with roles (artist / supervisor / admin) per project; access revocation = key revocation + server denial; already-synced local copies cannot be recalled (documented limitation). |
| §19.1 "synchronise immediately after each change" | The command bus already has a single choke point (`execute`); a sync hook after each committed operation pushes it (queue persists across crashes; offline → queue grows, sent later: "preserve local work during network failure"). |
| §19.1 shared model libraries, admin approval of models | Reuse the model registry (T-056): a studio manifest directory with approved models; the same SHA-256 verification. |
| §19 encrypted network communication | TLS for every transport; per-user key pairs; operations signed by their author (tamper evidence in the audit). |

## 3. Schema and code changes (planned, not implemented)

- `operations`: add `op_uuid`, `site_id`, `lamport`, `signature`; new `peers(site_id, last_seen_lamport)`, `branch_candidates(op_uuid, shape_id, frame, payload, from_site, created)`.
- `objects`: add `owner_user`; new `leases(object_id, holder, acquired_utc, heartbeat_utc)`.
- `st_roto.sync`: export operations since a peer's mark; import with conflict detection per (shape, frame); transports `sync_file` (folder/USB, testable), `sync_lan`, `sync_server`.
- Nuke UI: presence column in the object panel; branch-candidate review per object.

## 4. Verification plan

1. Two copies of one package edited offline (different frames → auto-merge, same frame → branch candidate) — unit test with two SQLite files and the file transport.
2. Crash during sync → queue survives, re-sync idempotent (op_uuid de-duplication).
3. Lease expiry and supervisor override after the idle threshold (needs OQ-16/17).
4. Small / medium / large studio benchmarks (§19.1) with a local server.

## 5. Open points for the owner

- **OQ-16** confirm the reading "supervisor overrides only when the holder is offline/idle".
- **OQ-17** idle threshold (proposal 15 minutes without heartbeat).
- New: is a signed audit trail required for every operation, or only for ownership/lock/permission changes? (Proposal: every operation — cheap, and it is the audit history §19 asks for.)
