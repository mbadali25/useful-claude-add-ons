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


# --- Review round 3 (T-0075): no-clobber moves, absence, regular files -------


def test_move_aside_never_replaces_a_destination_created_after_a_check(
        tmp_path, monkeypatch):
    src = _write(tmp_path / "config.json", b'{"a": 1}')
    dest = _write(tmp_path / "config.json.bak-X", b"a backup made meanwhile")
    monkeypatch.setattr(files.os.path, "lexists", lambda _p: False)
    monkeypatch.setattr(files.os.path, "exists", lambda _p: False)

    with pytest.raises(FileExistsError):
        files.move_aside(src, dest)

    assert (_read(src), _read(dest)) == (b'{"a": 1}', b"a backup made meanwhile")


def test_create_bytes_never_replaces_an_existing_file(tmp_path, monkeypatch):
    path = _write(tmp_path / "config.json", b'{"healed": true}')
    monkeypatch.setattr(files.os.path, "lexists", lambda _p: False)
    monkeypatch.setattr(files.os.path, "exists", lambda _p: False)

    with pytest.raises(FileExistsError):
        files.create_bytes(path, b'{"restored": true}')

    assert _read(path) == b'{"healed": true}'
    assert sorted(os.listdir(tmp_path)) == ["config.json"]


def test_create_bytes_writes_a_new_file(tmp_path):
    path = str(tmp_path / "config.json")

    files.create_bytes(path, b'{"restored": true}\r\n')

    assert _read(path) == b'{"restored": true}\r\n'
    assert sorted(os.listdir(tmp_path)) == ["config.json"]


def _replace(tmp_path, path, data):
    """Another writer's atomic save: a sibling, then `os.replace` onto `path`."""
    sibling = _write(tmp_path / "foreign.tmp", data)
    os.replace(sibling, path)


@pytest.mark.skipif(os.name == "nt", reason="the link-then-park move is POSIX's")
def test_move_aside_puts_back_a_file_that_replaced_the_source(tmp_path,
                                                              monkeypatch):
    src = _write(tmp_path / "config.json", b'{"original": 1}')
    dest = str(tmp_path / "config.json.bak-X")
    real_link = os.link

    def _link_then_a_foreign_save(a, b, **kwargs):
        real_link(a, b, **kwargs)
        if b == dest:
            _replace(tmp_path, src, b'{"F1": 1}')
    monkeypatch.setattr(files.os, "link", _link_then_a_foreign_save)

    with pytest.raises(files.Displaced) as caught:
        files.move_aside(src, dest)

    exc = caught.value
    assert (_read(src), _read(dest), _read(exc.parked)) == (
        b'{"F1": 1}', b'{"original": 1}', b'{"F1": 1}')
    assert exc.parked in str(exc)
    assert len(os.listdir(tmp_path)) == 3


# --- Review round 4 (T-0075): a move never unlinks a foreign file's last name -


@pytest.mark.skipif(os.name == "nt", reason="the link-then-park move is POSIX's")
def test_move_aside_keeps_a_foreign_file_through_a_second_replacement(
        tmp_path, monkeypatch):
    src = _write(tmp_path / "config.json", b'{"original": 1}')
    dest = str(tmp_path / "config.json.bak-X")
    real_link = os.link

    def _link_then_two_foreign_saves(a, b, **kwargs):
        real_link(a, b, **kwargs)
        if b == dest:
            _replace(tmp_path, src, b'{"F1": 1}')
        elif b == src:
            _replace(tmp_path, src, b'{"F2": 1}')
    monkeypatch.setattr(files.os, "link", _link_then_two_foreign_saves)

    with pytest.raises(files.Displaced) as caught:
        files.move_aside(src, dest)

    exc = caught.value
    assert (_read(exc.parked), _read(src), _read(dest)) == (
        b'{"F1": 1}', b'{"F2": 1}', b'{"original": 1}')
    held = sorted(_read(tmp_path / name) for name in os.listdir(tmp_path))
    assert held == sorted([b'{"F1": 1}', b'{"F2": 1}', b'{"original": 1}'])


@pytest.mark.skipif(os.name == "nt", reason="the link-then-park move is POSIX's")
def test_move_aside_keeps_the_backup_when_the_put_back_fails(tmp_path,
                                                             monkeypatch):
    src = _write(tmp_path / "config.json", b'{"original": 1}')
    dest = str(tmp_path / "config.json.bak-X")
    real_link = os.link

    def _link_then_a_foreign_save_then_refuse(a, b, **kwargs):
        if b == src:
            raise PermissionError(13, "Permission denied", b)
        real_link(a, b, **kwargs)
        if b == dest:
            _replace(tmp_path, src, b'{"F1": 1}')
    monkeypatch.setattr(files.os, "link", _link_then_a_foreign_save_then_refuse)

    with pytest.raises(files.Displaced) as caught:
        files.move_aside(src, dest)

    assert _read(dest) == b'{"original": 1}'
    assert _read(caught.value.parked) == b'{"F1": 1}'


@pytest.mark.skipif(os.name == "nt", reason="the link-then-park move is POSIX's")
def test_move_aside_undoes_the_link_while_the_source_is_untouched(tmp_path,
                                                                 monkeypatch):
    src = _write(tmp_path / "config.json", b'{"original": 1}')
    dest = str(tmp_path / "config.json.bak-X")

    def _no_reservation(_near):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(files, "_reserve", _no_reservation)

    with pytest.raises(OSError):
        files.move_aside(src, dest)

    assert not os.path.lexists(dest)
    assert _read(src) == b'{"original": 1}'


@pytest.mark.skipif(os.name == "nt", reason="needs a POSIX symlink and FIFO")
@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_restorable_file_refuses_what_is_not_a_regular_file(tmp_path, kind):
    target = _write(tmp_path / "real.json", b'{"tracker": "jira"}\n')
    path = str(tmp_path / "config.json")
    if kind == "symlink":
        os.symlink(target, path)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        os.mkdir(path)

    with pytest.raises(files.Unreadable) as caught:
        files.read_restorable(path)

    assert caught.value.kind == "notregular"
    assert "not a regular file" in str(caught.value)


def test_read_restorable_takes_a_regular_config(tmp_path):
    path = _write(tmp_path / "config.json", _BOM + b'{"tracker": "jira"}\r\n')

    parsed, raw = files.read_restorable(path)

    assert (parsed, raw) == ({"tracker": "jira"}, _BOM + b'{"tracker": "jira"}\r\n')


@pytest.mark.parametrize("present,expect,conflict", [
    (False, "absent", False), (True, "absent", True),
    (False, "0" * 64, True), (True, None, False)],
    ids=["absent-as-planned", "created-since", "deleted-since", "no-expect"])
def test_update_json_compares_against_absence(tmp_path, present, expect,
                                              conflict):
    path = str(tmp_path / "g.json")
    if present:
        _write(path, b'{"other": 1}\n')
    before = _read(path) if present else None

    def _mutate(parsed):
        parsed["mine"] = 1
        return parsed
    if conflict:
        with pytest.raises(files.Conflict):
            files.update_json(path, _mutate, expect=expect, create=True)
        after = _read(path) if os.path.exists(path) else None
        assert after == before
        return
    files.update_json(path, _mutate, expect=expect, create=True)

    assert json.loads(_read(path))["mine"] == 1


def test_expected_digest_token_names_absence():
    assert (files.state_digest(None), files.state_digest(b"x")) == (
        files.ABSENT, files.digest(b"x"))
