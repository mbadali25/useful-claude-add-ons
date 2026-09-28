"""Tests for crew_config_files: the one file layer under both config writers,
repo-config delete and restore (T-0075, the successor design after review
round 2).

Everything that makes a config write safe lives in that one module -- the
lock, the strict read, the `restorable` predicate delete and restore share,
the digest a compare-and-swap checks, the atomic replace and the move-aside
rename -- so there is one construction to test here and one to sabotage.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config_files as files

_BOM = b"\xef\xbb\xbf"


@pytest.fixture(autouse=True)
def _short_lock_wait(monkeypatch):
    monkeypatch.setattr(files, "LOCK_WAIT_SECONDS", 0.1)


def _write(path, data):
    with open(path, "wb") as handle:
        handle.write(data)
    return str(path)


def _read(path):
    with open(path, "rb") as handle:
        return handle.read()


# --- restorable and the strict read ------------------------------------------

RESTORABLE_BYTES = [
    ("object", b'{"tracker": "jira"}\n', True),
    ("bom", _BOM + b'{"tracker": "jira"}\n', True),
    ("crlf", b'{\r\n  "tracker": "jira"\r\n}\r\n', True),
    ("notjson", b"{not json", False),
    ("empty", b"", False),
    ("whitespace", b"  \n\t", False),
    ("emptyobject", b"{}", False),
    ("array", b"[]", False),
    ("string", b'"x"', False),
    ("null", b"null", False),
    ("bom-notjson", _BOM + b"{nope", False),
    ("notutf8", b'{"a": "\xff"}', False),
]


@pytest.mark.parametrize("name,data,ok", RESTORABLE_BYTES,
                         ids=[r[0] for r in RESTORABLE_BYTES])
def test_restorable_accepts_a_non_empty_object_only(name, data, ok):
    problem = files.restorable(data)

    assert (problem is None) is ok, (name, problem)
    if not ok:
        assert isinstance(problem, str) and problem


@pytest.mark.parametrize("state,kind", [
    ("absent", "absent"), ("notjson", "unparsable"), ("empty", "empty"),
    ("array", "notobject")])
def test_read_strict_four_cases(tmp_path, state, kind):
    path = str(tmp_path / "config.json")
    if state != "absent":
        _write(path, {"notjson": b"{nope", "empty": b"{}",
                      "array": b"[1]"}[state])

    with pytest.raises(files.Unreadable) as caught:
        files.read_strict(path)

    assert caught.value.kind == kind
    assert path in str(caught.value)


def test_read_strict_returns_the_parsed_object_and_the_raw_bytes(tmp_path):
    raw = _BOM + b'{"a": 1}\r\n'
    path = _write(tmp_path / "c.json", raw)

    assert files.read_strict(path) == ({"a": 1}, raw)


def test_read_strict_allows_an_empty_object_only_when_asked(tmp_path):
    path = _write(tmp_path / "g.json", b"{}")

    assert files.read_strict(path, allow_empty=True) == ({}, b"{}")


def test_digest_is_sha256_of_the_bytes():
    import hashlib  # pylint: disable=import-outside-toplevel

    assert files.digest(b"abc") == hashlib.sha256(b"abc").hexdigest()


# --- the lock ------------------------------------------------------------------


def test_lock_is_o_excl_and_names_the_holder(tmp_path):
    path = str(tmp_path / "config.json")
    _write(path + ".lock", b"4242")

    with pytest.raises(files.Busy) as caught:
        with files.Lock(path):
            pass

    message = str(caught.value)
    assert path + ".lock" in message and "4242" in message
    assert "by hand" in message


def test_lock_is_released_on_exit_and_on_error(tmp_path):
    path = str(tmp_path / "config.json")
    with files.Lock(path):
        held = os.path.exists(path + ".lock")
    with pytest.raises(RuntimeError):
        with files.Lock(path):
            raise RuntimeError("boom")

    assert (held, os.path.exists(path + ".lock")) == (True, False)


# --- update_json: compare-and-swap inside the lock -----------------------------


def _add(key, value):
    def _mutate(parsed):
        parsed[key] = value
        return parsed
    return _mutate


def test_update_json_merges_inside_the_lock(tmp_path):
    path = _write(tmp_path / "c.json", b'{"keep": 1}\n')
    seen = []

    def _mutate(parsed):
        seen.append(os.path.exists(path + ".lock"))
        parsed["a"] = 1
        return parsed
    files.update_json(path, _mutate)
    files.update_json(path, _add("b", 2))

    assert seen == [True]
    assert json.loads(_read(path)) == {"keep": 1, "a": 1, "b": 2}


def test_update_json_refuses_when_the_digest_changed(tmp_path):
    path = _write(tmp_path / "c.json", b'{"old": 1}\n')
    stale = files.digest(_read(path))
    _write(path, b'{"other": 2}\n')

    with pytest.raises(files.Conflict) as caught:
        files.update_json(path, _add("a", 1), expect=stale)

    assert path in str(caught.value)
    assert _read(path) == b'{"other": 2}\n'


def test_update_json_accepts_the_current_digest(tmp_path):
    path = _write(tmp_path / "c.json", b'{"old": 1}\n')

    files.update_json(path, _add("a", 1), expect=files.digest(_read(path)))

    assert json.loads(_read(path)) == {"old": 1, "a": 1}


def test_update_json_refuses_while_the_lock_is_held(tmp_path):
    path = _write(tmp_path / "c.json", b'{"old": 1}\n')
    _write(path + ".lock", b"77")

    with pytest.raises(files.Busy) as caught:
        files.update_json(path, _add("a", 1))

    assert "77" in str(caught.value)
    assert _read(path) == b'{"old": 1}\n'


def test_update_json_keeps_crlf_and_bom(tmp_path):
    path = _write(tmp_path / "c.json", _BOM + b'{\r\n  "old": 1\r\n}\r\n')

    files.update_json(path, _add("a", 1))

    raw = _read(path)
    assert raw.startswith(_BOM)
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert json.loads(raw[len(_BOM):]) == {"old": 1, "a": 1}


def test_update_json_is_atomic_when_the_text_raises(tmp_path, monkeypatch):
    path = _write(tmp_path / "c.json", b'{"old": 1}\n')

    def _boom(*_args, **_kwargs):
        raise ValueError("cannot serialise")
    monkeypatch.setattr(files.json, "dumps", _boom)
    with pytest.raises(ValueError):
        files.update_json(path, _add("a", 1))

    assert _read(path) == b'{"old": 1}\n'
    assert sorted(os.listdir(tmp_path)) == ["c.json"]


def test_update_json_is_atomic_when_the_disk_fails(tmp_path, monkeypatch):
    path = _write(tmp_path / "c.json", b'{"old": 1}\n')

    def _boom(_fd):
        raise OSError("disk full")
    monkeypatch.setattr(files.os, "fsync", _boom)
    with pytest.raises(OSError):
        files.update_json(path, _add("a", 1))

    assert _read(path) == b'{"old": 1}\n'
    assert sorted(os.listdir(tmp_path)) == ["c.json"]


def test_update_json_create_writes_a_new_file_only_when_asked(tmp_path):
    absent = str(tmp_path / "sub" / "g.json")
    with pytest.raises(files.Unreadable):
        files.update_json(absent, _add("a", 1))
    created = os.path.exists(absent)

    files.update_json(absent, _add("a", 1), create=True)

    assert (created, json.loads(_read(absent))) == (False, {"a": 1})


def test_update_json_writes_nothing_when_mutate_returns_none(tmp_path):
    path = _write(tmp_path / "c.json", b'{"old": 1}\n')
    before = os.stat(path).st_mtime_ns

    files.update_json(path, lambda parsed: None)

    assert (_read(path), os.stat(path).st_mtime_ns) == (b'{"old": 1}\n', before)


# --- move_aside ----------------------------------------------------------------


def test_move_aside_is_a_rename_and_returns_the_bytes(tmp_path):
    src = _write(tmp_path / "config.json", b'{"a": 1}\r\n')
    dest = str(tmp_path / "config.json.bak-X")
    inode = os.stat(src).st_ino

    got = files.move_aside(src, dest)

    assert (got, os.path.exists(src)) == (b'{"a": 1}\r\n', False)
    if os.name != "nt":
        assert os.stat(dest).st_ino == inode


def test_move_aside_refuses_an_existing_destination(tmp_path):
    src = _write(tmp_path / "config.json", b'{"a": 1}')
    dest = _write(tmp_path / "config.json.bak-X", b"older")

    with pytest.raises(FileExistsError):
        files.move_aside(src, dest)

    assert (_read(src), _read(dest)) == (b'{"a": 1}', b"older")
