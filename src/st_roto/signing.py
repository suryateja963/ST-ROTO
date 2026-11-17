"""Signed operations (T-084, D-037): every replicated operation is signed by its author with Ed25519.

Pure Python (RFC 8032 Ed25519, no dependency: runs in every Nuke Python, 3.7+). Validated against the RFC 8032
test vectors and, where installed, the `cryptography` package (tests/unit/test_signing.py). Not constant-time:
fine for signing one's own edits on one's own machine; the private key never leaves it.

* A user's key pair: `generate_key()` -> 32-byte seed (PRIVATE, kept in a key file outside the project database,
  `save_key` / `load_key`), `public_key(seed)` -> 32 bytes, registered in the project with the `set_user_key`
  operation (stored in `user_keys`).
* What is signed: the canonical JSON of {op_uuid, site_id, author, actor, payload} (`message`). The signature is
  stored with the operation (operations.signature) and travels in change files.
* Collaboration mode = at least one registered key. Then every operation imported from a peer must carry a valid
  signature by its author's registered key, or it is refused (`st_roto.sync.import_changes`). `verify_log`
  re-checks a project's whole history (tamper evidence for the audit).
"""
from __future__ import annotations

import binascii
import hashlib
import json
import os

# ------------------------------------------------------------------------------------------------ Ed25519
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)                                # sqrt(-1)


def _inv(x):
    return pow(x, _P - 2, _P)


def _xrecover(y, sign):
    xx = (y * y - 1) * _inv(_D * y * y + 1) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if (x * x - xx) % _P != 0:
        raise ValueError("not a curve point")
    if x == 0 and sign:
        raise ValueError("invalid point encoding")
    if x & 1 != sign:
        x = _P - x
    return x


_BY = 4 * _inv(5) % _P
_B = (_xrecover(_BY, 0), _BY, 1, _xrecover(_BY, 0) * _BY % _P)   # extended coordinates (X, Y, Z, T)
_ZERO = (0, 1, 1, 0)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s, p):
    q = _ZERO
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _encode(p):
    zi = _inv(p[2])
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decode(b):
    if len(b) != 32:
        raise ValueError("a point is 32 bytes")
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        raise ValueError("invalid point encoding")
    x = _xrecover(y, sign)
    return (x, y, 1, x * y % _P)


def _equal(p, q):
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _expand(seed):
    if len(seed) != 32:
        raise ValueError("an Ed25519 private key (seed) is 32 bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    return _encode(_mul(_expand(seed)[0], _B))


def sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(seed)
    pub = _encode(_mul(a, _B))
    r = _h(prefix + msg) % _L
    rs = _encode(_mul(r, _B))
    s = (r + _h(rs + pub + msg) * a) % _L
    return rs + int.to_bytes(s, 32, "little")


def verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        if len(sig) != 64:
            return False
        a = _decode(pub)
        r = _decode(sig[:32])
        s = int.from_bytes(sig[32:], "little")
        if s >= _L:
            return False
        h = _h(sig[:32] + pub + msg) % _L
        return _equal(_mul(s, _B), _add(r, _mul(h, a)))
    except (ValueError, TypeError):
        return False


def generate_key() -> bytes:
    return os.urandom(32)


# ------------------------------------------------------------------------------------------------ keys on disk
def save_key(path: str, seed: bytes) -> None:
    """Write a private key file (hex). Refuses to overwrite: losing a key cannot be undone."""
    if os.path.exists(path):
        raise FileExistsError(path)
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as fh:
        fh.write(binascii.hexlify(seed).decode("ascii") + "\n")


def load_key(path: str) -> bytes:
    with open(path) as fh:
        seed = binascii.unhexlify(fh.read().strip())
    if len(seed) != 32:
        raise ValueError("%s is not an ST-ROTO private key" % path)
    return seed


def key_dir() -> str:
    """Where private keys live (D-038, owner-approved): %USERPROFILE%\\.st_roto\\keys (~/.st_roto/keys elsewhere).
    Outside every project, so a key is never shared, packaged or synced with project data. Created on first use.
    The environment variable ST_ROTO_KEY_DIR overrides it (tests; studios with managed home folders)."""
    return os.environ.get("ST_ROTO_KEY_DIR") or os.path.join(os.path.expanduser("~"), ".st_roto", "keys")


def key_path(user: str, folder: str = None) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in user).strip(".") or "_"
    return os.path.join(folder or key_dir(), safe + ".strotokey")


def load_or_create_key(user: str, folder: str = None):
    """(seed, created): the user's private key from the key folder, generated and saved there if missing."""
    p = key_path(user, folder)
    if os.path.exists(p):
        return load_key(p), False
    seed = generate_key()
    save_key(p, seed)
    return seed, True


def to_hex(b: bytes) -> str:
    return binascii.hexlify(b).decode("ascii")


def from_hex(s: str) -> bytes:
    return binascii.unhexlify(s)


# ------------------------------------------------------------------------------------------------ operations
def message(op_uuid, site_id, author, actor, payload) -> bytes:
    """The exact bytes signed for an operation (canonical JSON; identical on every site)."""
    return json.dumps({"op_uuid": op_uuid, "site_id": site_id, "author": author, "actor": actor, "payload": payload},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class Signer:
    """Signs the operations a CommandBus makes, for one author."""

    def __init__(self, author: str, seed: bytes):
        self.author = author
        self.seed = seed
        self.public = public_key(seed)

    def sign_op(self, op_uuid, site_id, actor, payload) -> str:
        return to_hex(sign(self.seed, message(op_uuid, site_id, self.author, actor, payload)))


def keys_of(conn, user, active_only=True):
    sql = "SELECT public_key FROM user_keys WHERE user = ?" + (" AND revoked = 0" if active_only else "")
    return [from_hex(r["public_key"]) for r in conn.execute(sql, (user,))]


def collaboration_mode(conn) -> bool:
    return conn.execute("SELECT COUNT(*) FROM user_keys").fetchone()[0] > 0


def _self_registration(payload, author):
    if payload.get("op") == "set_user_key" and payload.get("user") == author and not payload.get("revoke"):
        return from_hex(payload["public_key"])
    return None


def verify_op(conn, op_uuid, site_id, author, actor, payload, signature, active_only=True) -> str:
    """'' if valid, else the reason. A key's own registration is self-signed by the new key."""
    keys = keys_of(conn, author, active_only)
    new = _self_registration(payload, author)
    if new is not None:
        keys.append(new)
    if not keys:
        return "author %r has no registered key" % author
    if not signature:
        return "unsigned"
    try:
        sig = from_hex(signature)
    except (binascii.Error, TypeError, ValueError):
        return "malformed signature"
    msg = message(op_uuid, site_id, author, actor, payload)
    if not any(verify(k, msg, sig) for k in keys):
        return "BAD SIGNATURE (altered, or not made by %s)" % author
    return ""


def verify_log(store) -> dict:
    """Re-check every signed operation in the project history against every key its author ever registered
    (revoked keys still prove past work). Returns {"signed", "unsigned", "bad": [(seq, why)]}. A bad signature
    means the logged operation was altered after it was made, or forged."""
    out = {"signed": 0, "unsigned": 0, "bad": []}
    for r in store.conn.execute("SELECT seq, op_uuid, site_id, author, actor, payload, signature FROM operations "
                                "ORDER BY seq"):
        if not r["signature"]:
            out["unsigned"] += 1
            continue
        out["signed"] += 1
        why = verify_op(store.conn, r["op_uuid"], r["site_id"], r["author"], r["actor"], json.loads(r["payload"]),
                        r["signature"], active_only=False)
        if why:
            out["bad"].append((r["seq"], why))
    return out


# ------------------------------------------------------------------------------------------------ key operation
class KeyRuleError(Exception):
    """A key registration or revocation is not allowed."""


def apply_set_user_key(conn, op, actor):
    """op: user, public_key (hex), revoke (bool). Inverse restores the previous state of that (user, key)."""
    from . import model as m
    if actor == m.ACTOR_AI:
        raise KeyRuleError("AI may not change keys")
    pub = op["public_key"]
    if len(from_hex(pub)) != 32:
        raise ValueError("a public key is 32 bytes")
    prev = conn.execute("SELECT revoked FROM user_keys WHERE user = ? AND public_key = ?", (op["user"], pub)).fetchone()
    if prev is None:
        conn.execute("INSERT INTO user_keys (user, public_key, revoked) VALUES (?, ?, ?)",
                     (op["user"], pub, 1 if op.get("revoke") else 0))
        return {"op": "set_user_key", "user": op["user"], "public_key": pub, "remove": True}
    if op.get("remove"):                                          # only as an undo inverse
        conn.execute("DELETE FROM user_keys WHERE user = ? AND public_key = ?", (op["user"], pub))
    else:
        conn.execute("UPDATE user_keys SET revoked = ? WHERE user = ? AND public_key = ?",
                     (1 if op.get("revoke") else 0, op["user"], pub))
    return {"op": "set_user_key", "user": op["user"], "public_key": pub, "revoke": bool(prev["revoked"])}


def check_made(conn, op, author):
    """Key rules for an operation made locally: register keys for yourself only (an admin may register or revoke
    anyone's); the remove form is reserved for undo."""
    if op.get("op") != "set_user_key":
        return
    from .leases import role
    if op.get("remove"):
        raise KeyRuleError("keys are revoked, never removed (history must stay verifiable)")
    if op["user"] != author and role(conn, author) != "admin":
        raise KeyRuleError("only the user or an admin may register or revoke %s's key" % op["user"])


def register(bus):
    """Register the public key of the bus's signer for its author (the op is self-signed by that key)."""
    if bus.signer is None:
        raise ValueError("the bus has no signer: CommandBus(store, author, signer=Signer(author, seed))")
    return bus.execute({"op": "set_user_key", "user": bus.author, "public_key": to_hex(bus.signer.public)})


def revoke(bus, user, public_hex):
    return bus.execute({"op": "set_user_key", "user": user, "public_key": public_hex, "revoke": True})
