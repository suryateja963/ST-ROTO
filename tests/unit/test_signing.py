"""Signed operations (T-084, D-037): pure-Python Ed25519 validated against RFC 8032 and the `cryptography`
package; the bus signs what it makes; sync refuses forged, altered or unsigned peer operations; the history can be
re-verified (tamper evidence)."""
import json
import os
import shutil
import time

import pytest

from st_roto import signing, sync
from st_roto.commands import CommandBus
from st_roto.signing import Signer, KeyRuleError
from st_roto.store import ProjectStore

# RFC 8032 section 7.1, TEST 1 and TEST 2 (secret key, public key, message, signature)
RFC = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]


@pytest.mark.parametrize("sk,pk,msg,sig", RFC)
def test_rfc8032_vectors(sk, pk, msg, sig):
    seed, m = bytes.fromhex(sk), bytes.fromhex(msg)
    assert signing.public_key(seed).hex() == pk
    assert signing.sign(seed, m).hex() == sig
    assert signing.verify(bytes.fromhex(pk), m, bytes.fromhex(sig))


def test_matches_cryptography_package():
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    from cryptography.hazmat.primitives import serialization as ser
    for i in range(20):
        seed, msg = os.urandom(32), os.urandom(i * 7)
        ref = ed.Ed25519PrivateKey.from_private_bytes(seed)
        ref_pub = ref.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
        assert signing.public_key(seed) == ref_pub
        assert signing.sign(seed, msg) == ref.sign(msg)                 # Ed25519 is deterministic
        ref.public_key().verify(signing.sign(seed, msg), msg)          # theirs accepts ours (raises if not)
        assert signing.verify(ref_pub, msg, ref.sign(msg))              # ours accepts theirs


def test_rejects_altered_message_signature_or_key():
    seed, msg = os.urandom(32), b"set_key hero 12"
    pub, sig = signing.public_key(seed), signing.sign(seed, msg)
    assert signing.verify(pub, msg, sig)
    assert not signing.verify(pub, msg + b"!", sig)
    assert not signing.verify(pub, msg, sig[:10] + bytes([sig[10] ^ 1]) + sig[11:])
    assert not signing.verify(signing.public_key(os.urandom(32)), msg, sig)
    assert not signing.verify(pub, msg, sig[:63])                       # malformed: False, not an exception
    assert not signing.verify(b"\xff" * 32, msg, sig)


def test_speed_is_fine_for_edit_operations():
    seed = os.urandom(32)
    t0 = time.time()
    for _ in range(10):
        signing.verify(signing.public_key(seed), b"x" * 200, signing.sign(seed, b"x" * 200))
    per = (time.time() - t0) / 10
    print("sign + verify: %.1f ms" % (per * 1000))
    assert per < 0.5                                                    # one batch op per track / edit


def test_key_file_roundtrip_and_no_overwrite(tmp_path):
    p = str(tmp_path / "keys" / "ana.strotokey")
    seed = signing.generate_key()
    signing.save_key(p, seed)
    assert signing.load_key(p) == seed
    with pytest.raises(FileExistsError):
        signing.save_key(p, signing.generate_key())


def mkproject(path, author="ada", seed=None):
    st = ProjectStore(path)
    bus = CommandBus(st, author=author, signer=Signer(author, seed) if seed else None)
    bus.execute({"op": "create_shot", "row": {"id": "S", "name": "sh"}})
    bus.execute({"op": "create_object", "row": {"id": "O", "shot_id": "S", "name": "hero"}})
    bus.execute({"op": "create_shape", "row": {"id": "P", "object_id": "O", "name": "hero", "point_count": 2}})
    return st, bus


def pts(v):
    return [[v, v, v, v, v, v], [v + 1, v, v + 1, v, v + 1, v]]


def test_bus_signs_everything_it_makes_and_log_verifies(tmp_path):
    seed = signing.generate_key()
    st, bus = mkproject(str(tmp_path / "p.stroto"), seed=seed)
    signing.register(bus)
    bus.execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(1)})
    bus.undo(); bus.redo()                                              # undo/redo are signed operations too
    v = signing.verify_log(st)
    assert v["bad"] == [] and v["unsigned"] == 0 and v["signed"] == 7
    # tamper with a logged operation (e.g. someone edits the database by hand)
    seq = st.conn.execute("SELECT MAX(seq) FROM operations WHERE kind = 'set_key'").fetchone()[0]
    payload = json.loads(st.conn.execute("SELECT payload FROM operations WHERE seq = ?", (seq,)).fetchone()[0])
    payload["points"] = pts(99)
    st.conn.execute("UPDATE operations SET payload = ? WHERE seq = ?", (json.dumps(payload), seq))
    v = signing.verify_log(st)
    assert [b[0] for b in v["bad"]] == [seq] and "BAD SIGNATURE" in v["bad"][0][1]
    st.close()


def test_signer_must_match_author(tmp_path):
    st = ProjectStore(str(tmp_path / "p.stroto"))
    with pytest.raises(ValueError):
        CommandBus(st, author="ana", signer=Signer("ben", signing.generate_key()))
    with pytest.raises(ValueError):
        signing.register(CommandBus(st, author="ana"))                 # nothing to register without a signer
    st.close()


@pytest.fixture
def pair(tmp_path):
    """Copy A (ana, signing) and its fork B (ben, signing); both keys registered and synced."""
    sa, sb = signing.generate_key(), signing.generate_key()
    a_path, b_path = str(tmp_path / "a.stroto"), str(tmp_path / "b.stroto")
    a, _ = mkproject(a_path, author="ana", seed=sa)
    a.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)"); a.close()
    shutil.copyfile(a_path, b_path)
    a, b = ProjectStore(a_path), ProjectStore(b_path)
    sync.fork_site(b)
    ana, ben = CommandBus(a, author="ana", signer=Signer("ana", sa)), CommandBus(b, author="ben", signer=Signer("ben", sb))
    signing.register(ana); signing.register(ben)
    assert sync.import_changes(b, sync.export_changes(a))["applied"] == 1
    assert sync.import_changes(a, sync.export_changes(b))["applied"] == 1
    yield a, b, ana, ben, sa, sb
    a.close(); b.close()


def test_signed_peer_ops_apply(pair):
    a, b, ana, ben, sa, sb = pair
    mark = a.conn.execute("SELECT MAX(seq) FROM operations").fetchone()[0]
    ana.execute({"op": "set_key", "shape_id": "P", "frame": 3, "points": pts(3)})
    rep = sync.import_changes(b, sync.export_changes(a, mark))
    assert rep["applied"] == 1 and rep["refused"] == [] and b.key("P", 3)
    assert signing.verify_log(b)["bad"] == []                           # the peer's signature is kept in B's log


def test_altered_forged_and_unsigned_ops_are_refused(pair):
    a, b, ana, ben, sa, sb = pair
    mark = a.conn.execute("SELECT MAX(seq) FROM operations").fetchone()[0]
    ana.execute({"op": "set_key", "shape_id": "P", "frame": 4, "points": pts(4)})
    ch = sync.export_changes(a, mark)
    altered = json.loads(json.dumps(ch)); altered["ops"][0]["payload"]["points"] = pts(44)
    rep = sync.import_changes(b, altered)
    assert rep["applied"] == 0 and "BAD SIGNATURE" in rep["refused"][0][1] and b.key("P", 4) is None
    unsigned = json.loads(json.dumps(ch)); unsigned["ops"][0]["signature"] = None
    assert sync.import_changes(b, unsigned)["refused"][0][1] == "unsigned"
    # impostor: an op claiming author "ana" but signed with ben's key
    forged = json.loads(json.dumps(ch))
    o = forged["ops"][0]; o["op_uuid"] = "f" * 32
    o["signature"] = signing.to_hex(signing.sign(sb, signing.message(o["op_uuid"], forged["site_id"], "ana",
                                                                     o["actor"], o["payload"])))
    assert "BAD SIGNATURE" in sync.import_changes(b, forged)["refused"][0][1]
    # unknown author in collaboration mode
    ghost = json.loads(json.dumps(ch)); ghost["ops"][0]["author"] = "ghost"; ghost["ops"][0]["op_uuid"] = "e" * 32
    assert "no registered key" in sync.import_changes(b, ghost)["refused"][0][1]
    assert sync.import_changes(b, ch)["applied"] == 1                  # the genuine one still applies


def test_key_rules_and_revocation(pair):
    a, b, ana, ben, sa, sb = pair
    with pytest.raises(KeyRuleError):                                    # not for someone else
        ana.execute({"op": "set_user_key", "user": "ben", "public_key": signing.to_hex(signing.public_key(sa))})
    with pytest.raises(KeyRuleError):                                    # never removed (history must verify)
        ana.execute({"op": "set_user_key", "user": "ana", "public_key": signing.to_hex(ana.signer.public),
                     "remove": True})
    # ana's key is revoked (e.g. laptop lost): her OLD work still verifies, NEW ops signed with it are refused
    mark = a.conn.execute("SELECT MAX(seq) FROM operations").fetchone()[0]
    ana.execute({"op": "set_key", "shape_id": "P", "frame": 5, "points": pts(5)})
    late = sync.export_changes(a, mark)
    with pytest.raises(KeyRuleError):                                    # an artist cannot revoke someone's key
        signing.revoke(ben, "ana", signing.to_hex(ana.signer.public))
    from st_roto import leases
    leases.set_role(ben, "ben", "admin")                                 # first role on copy B: ben, self-admin
    signing.revoke(ben, "ana", signing.to_hex(ana.signer.public))
    rep = sync.import_changes(b, late)
    assert rep["applied"] == 0 and rep["refused"][0][1] == "author 'ana' has no registered key"
    assert b.key("P", 5) is None
    assert signing.verify_log(b)["bad"] == []                           # ana's earlier ops still verify


def test_solo_projects_without_keys_are_unchanged(tmp_path):
    a_path, b_path = str(tmp_path / "a.stroto"), str(tmp_path / "b.stroto")
    a, bus = mkproject(a_path)
    a.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)"); a.close()
    shutil.copyfile(a_path, b_path)
    a, b = ProjectStore(a_path), ProjectStore(b_path); sync.fork_site(b)
    mark = a.conn.execute("SELECT MAX(seq) FROM operations").fetchone()[0]
    CommandBus(a, author="ada").execute({"op": "set_key", "shape_id": "P", "frame": 1, "points": pts(1)})
    rep = sync.import_changes(b, sync.export_changes(a, mark))
    assert rep["applied"] == 1 and rep["refused"] == []
    assert signing.verify_log(b) == {"signed": 0, "unsigned": b.conn.execute(
        "SELECT COUNT(*) FROM operations").fetchone()[0], "bad": []}
    a.close(); b.close()
