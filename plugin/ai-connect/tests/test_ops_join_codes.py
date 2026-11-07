"""Join codes: the format, the invite store, and exactly-once redemption (join_codes.py).

Must-block: a second redemption (sequential, concurrent, or after a crash
between marking the code used and adding the peer), an expired code, a code
for another name, a mistyped code. Must-allow: one fresh code, once. Every
file lives under tmp_path; nothing touches ~/.config.
"""

import json
import threading

import pytest
import yaml

import installer
import join_codes as jc

HOST, PORT = "100.64.0.7", 9999


@pytest.fixture
def bridge_config(tmp_path):
    path = tmp_path / "ai-connect" / "config.yaml"
    path.parent.mkdir()
    config = installer._example()  # pylint: disable=protected-access
    config["auth"]["peers"] = {"existing": jc.sha256_hex("x" * 64)}
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def peers(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["auth"]["peers"]


# --- the code -----------------------------------------------------------------

def test_code_round_trips_every_field():
    code = jc.JoinCode(host=HOST, port=PORT, fingerprint=bytes(range(32)), secret=b"s" * 16,
                       name="laptop-2", expires=1_900_000_000)
    text = jc.encode(code)
    assert set(text) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567-")
    assert jc.decode(text) == code
    # Case, spaces and line breaks from a chat client do not matter
    assert jc.decode(text.lower().replace("-", " \n")) == code
    assert jc.decode(text).tls and jc.decode(text).fingerprint_hex == bytes(range(32)).hex()


def test_code_without_fingerprint_is_plain_ws():
    code = jc.decode(jc.encode(jc.JoinCode(HOST, PORT, jc.NO_FINGERPRINT, b"s" * 16, "laptop", 1)))
    assert not code.tls and code.fingerprint_hex == ""


@pytest.mark.parametrize("damage", ["flip", "cut", "junk"])
def test_damaged_code_is_refused_by_the_checksum(damage):
    text = jc.encode(jc.JoinCode(HOST, PORT, jc.NO_FINGERPRINT, b"s" * 16, "laptop", 1_900_000_000))
    letters = text.replace("-", "")
    if damage == "flip":
        bad = letters[:20] + ("A" if letters[20] != "A" else "B") + letters[21:]
    elif damage == "cut":
        bad = letters[:-3]
    else:
        bad = letters + "!"
    with pytest.raises(jc.CodeError):
        jc.decode(bad)


def test_unknown_version_is_refused():
    text = jc.encode(jc.JoinCode(HOST, PORT, jc.NO_FINGERPRINT, b"s" * 16, "laptop", 1, version=2))
    with pytest.raises(jc.CodeError, match="version 2"):
        jc.decode(text)


def test_secret_is_128_bits_and_only_its_hash_is_stored(bridge_config):
    text = jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT)
    code = jc.decode(text)
    assert len(code.secret) == 16
    stored = jc.invites_path(bridge_config).read_text(encoding="utf-8")
    assert code.secret.hex() not in stored and text not in stored
    assert jc.sha256_hex(code.secret) in stored


# --- redemption: must-allow ---------------------------------------------------

def test_fresh_code_redeems_once_and_adds_the_peer(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    token = jc.redeem(bridge_config, code.secret, "laptop")
    assert len(token) == 64
    assert peers(bridge_config)["laptop"] == jc.sha256_hex(token)
    assert token not in bridge_config.read_text(encoding="utf-8")


# --- redemption: must-block ---------------------------------------------------

def test_second_redemption_is_refused(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    jc.redeem(bridge_config, code.secret, "laptop")
    with pytest.raises(jc.Refused, match=jc.GENERIC_REFUSAL):
        jc.redeem(bridge_config, code.secret, "laptop")


def test_concurrent_double_redemption_exactly_one_wins(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    racers = 8
    barrier = threading.Barrier(racers)
    won, refused, errors = [], [], []

    def race():
        barrier.wait()
        try:
            won.append(jc.redeem(bridge_config, code.secret, "laptop"))
        except jc.Refused:
            refused.append(1)
        except Exception as err:  # pylint: disable=broad-exception-caught
            errors.append(err)

    threads = [threading.Thread(target=race) for _ in range(racers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not errors
    assert len(won) == 1 and len(refused) == racers - 1
    assert peers(bridge_config)["laptop"] == jc.sha256_hex(won[0])


def test_expired_code_is_refused_with_the_same_answer(bridge_config):
    clock = Clock()
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 60, HOST, PORT, clock=clock))
    clock.now += 61
    with pytest.raises(jc.Refused) as err:
        jc.redeem(bridge_config, code.secret, "laptop", clock=clock)
    assert str(err.value) == jc.GENERIC_REFUSAL
    assert "laptop" not in peers(bridge_config)


def test_code_for_another_name_is_refused(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, code.secret, "desktop")
    assert "desktop" not in peers(bridge_config)


def test_unknown_secret_is_refused(bridge_config):
    jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT)
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, b"\0" * 16, "laptop")


def test_reuse_after_a_crash_between_mark_and_add_is_refused(bridge_config):
    """The code is marked used before the peer is added: a crash in between burns it, never reopens it."""
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))

    def crash(_path, _name):
        raise OSError("power cut")

    with pytest.raises(OSError):
        jc.redeem(bridge_config, code.secret, "laptop", add_peer=crash)
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, code.secret, "laptop")
    assert "laptop" not in peers(bridge_config)


def test_leftover_temp_file_from_a_crashed_write_changes_nothing(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    # What a writer killed before os.replace leaves behind
    (bridge_config.parent / ".invites.json-crashed").write_text("{", encoding="utf-8")
    assert jc.redeem(bridge_config, code.secret, "laptop")


def test_broken_invite_store_refuses_rather_than_reads_as_empty(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    jc.invites_path(bridge_config).write_text("{not json", encoding="utf-8")
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, code.secret, "laptop")


def test_new_code_for_a_name_ends_the_older_one(bridge_config):
    old = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    new = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, old.secret, "laptop")
    assert jc.redeem(bridge_config, new.secret, "laptop")


def test_invite_for_an_enrolled_name_is_refused(bridge_config):
    with pytest.raises(ValueError, match="already exists"):
        jc.create_invite(bridge_config, "existing", 3600, HOST, PORT)


def test_revoked_name_cannot_be_redeemed_by_its_pending_code(bridge_config):
    code = jc.decode(jc.create_invite(bridge_config, "laptop", 3600, HOST, PORT))
    with jc.auth_lock(bridge_config.parent):
        assert jc.cancel_invites(bridge_config, "laptop") == 1
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, code.secret, "laptop")


def test_old_entries_are_pruned_after_the_keep_window(bridge_config):
    clock = Clock()
    jc.create_invite(bridge_config, "laptop", 60, HOST, PORT, clock=clock)
    clock.now += jc.KEEP_SECONDS + 120
    jc.create_invite(bridge_config, "desktop", 60, HOST, PORT, clock=clock)
    names = [e["name"] for e in json.loads(jc.invites_path(bridge_config).read_text(encoding="utf-8"))["invites"]]
    assert names == ["desktop"]


@pytest.mark.parametrize("text,seconds", [("1h", 3600), ("30m", 1800), ("2d", 172800), ("90", 90)])
def test_expiry_parses(text, seconds):
    assert jc.parse_expiry(text) == seconds


@pytest.mark.parametrize("text", ["8d", "10s", "soon", ""])
def test_expiry_out_of_range_is_refused(text):
    with pytest.raises(ValueError):
        jc.parse_expiry(text)


def test_failure_limiter_blocks_per_address_and_in_total():
    clock = Clock(0.0)
    limiter = jc.FailureLimiter(per_ip=2, total=3, window=60, clock=clock)
    limiter.failed("a")
    assert not limiter.blocked("a")
    limiter.failed("a")
    assert limiter.blocked("a") and not limiter.blocked("b")
    limiter.failed("b")
    assert limiter.blocked("c")  # the total
    clock.now += 61
    assert not limiter.blocked("a")


def test_mask_shows_only_the_last_four():
    assert jc.mask("0123456789abcdef") == "****cdef"
    assert jc.mask("abc") == "****"
