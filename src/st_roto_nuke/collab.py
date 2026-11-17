"""Collaboration in the Nuke UI (T-094, REQ-170/171): leases, presence, roles and signing keys for the object panel.
No Qt here (the panel only calls these), so the logic is testable headless. The rules themselves live in the core
(st_roto.leases: D-024/D-035/D-036; st_roto.signing: D-037/D-038); this module only applies them as the artist.

Identity: the bus author of the open project (session.project: the OS user name). A signing key is never created
silently: `setup_key` creates it (D-038 key folder) and registers its public half in the project.
"""
from __future__ import annotations

from st_roto import leases, signing
from . import session

ACTIVITY_SECONDS = 60          # the panel sends a presence heartbeat at most this often while it is open


def me(path):
    return session.project(path)[1].author


def heartbeat(path, frame=None, activity=None):
    store, bus = session.project(path)
    leases.heartbeat(store, bus.author, frame=frame, activity=activity)


def lease_text(conn, object_id, me_):
    """'' (free), 'you', or 'alice' / 'alice (idle 23 min)'."""
    ls = leases.lease(conn, object_id)
    if not ls:
        return ""
    if ls["holder"] == me_:
        return "you"
    idle = leases.idle_seconds(conn, ls["holder"])
    if idle is None:
        return "%s (offline)" % ls["holder"]
    if idle >= leases.IDLE_SECONDS:
        return "%s (idle %d min)" % (ls["holder"], idle // 60)
    return ls["holder"]


def take(path, object_id):
    store, bus = session.project(path)
    leases.heartbeat(store, bus.author, activity="take lease")
    return leases.acquire(bus, object_id)


def release(path, object_id):
    store, bus = session.project(path)
    leases.heartbeat(store, bus.author, activity="release lease")
    return leases.release(bus, object_id)


def override(path, object_id):
    """Supervisor override (D-035/D-036): allowed only when the holder has been idle/offline 15 min; the op stores
    the evidence. Errors from the rules are raised with an artist-readable message."""
    store, bus = session.project(path)
    leases.heartbeat(store, bus.author, activity="override lease")
    return leases.override(bus, object_id, take=True)


def set_role(path, user, role_name):
    """The first role must be the author making themself admin; afterwards only admins assign roles."""
    store, bus = session.project(path)
    if role_name not in leases.ROLES:
        raise ValueError("role must be one of %s" % ", ".join(leases.ROLES))
    return leases.set_role(bus, user, role_name)


def key_state(path):
    """'registered' (key file present and registered here), 'not registered' (file present, not registered in this
    project), 'missing file' (registered here but no key file on this machine), or 'none'."""
    import os
    store, bus = session.project(path)
    have_file = os.path.exists(signing.key_path(bus.author))
    registered = signing.keys_of(store.conn, bus.author)
    if have_file and bus.signer is not None and bus.signer.public in registered:
        return "registered"
    if have_file:
        return "not registered"
    if registered:
        return "missing file"
    return "none"


def setup_key(path):
    """Create the author's signing key if needed (D-038 folder), sign this project's operations with it from now on
    and register its public key here (a self-signed op). Returns (key_state, created)."""
    store, bus = session.project(path)
    seed, created = signing.load_or_create_key(bus.author)
    if bus.signer is None or bus.signer.public != signing.public_key(seed):
        bus.signer = signing.Signer(bus.author, seed)
    if bus.signer.public not in signing.keys_of(store.conn, bus.author):
        signing.register(bus)
    return key_state(path), created


def status_line(path):
    """'you: alice (admin) · key registered · online: bob · idle: carol' for the panel."""
    store, bus = session.project(path)
    conn = store.conn
    role = leases.role(conn, bus.author)
    online, idle = [], []
    for p in leases.presence(conn):
        if p["user"] == bus.author:
            continue
        (idle if p["idle"] else online).append(p["user"])
    parts = ["you: %s%s" % (bus.author, " (%s)" % role if role else ""), "key %s" % key_state(path)]
    if signing.collaboration_mode(conn):
        parts.append("collaboration on (signed changes)")
    if online:
        parts.append("online: " + ", ".join(online))
    if idle:
        parts.append("idle/offline: " + ", ".join(idle))
    return " · ".join(parts)
