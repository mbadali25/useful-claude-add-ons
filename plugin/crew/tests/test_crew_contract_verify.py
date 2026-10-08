"""L-0634: a ticket's built-against contract bindings must still hold --
`crew_contract.py verify --ticket <id>` and the autopilot wave's refusal.

    python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_contract_verify.py \
        plugin/crew/tests/test_crew_contract.py plugin/crew/tests/test_crew_wave.py -q

Every case builds a throwaway repository under tmp_path whose remote `coord`
is a bare repository there (`origin` is a short URL that only gives the repo
key and is never fetched), puts a contract on
`crew-coord/<channel>` and builds an approved ticket against it with
crew_contract.py itself; a peer's later rewrite of the channel is written
through crew_coord's Channel. Nothing is pushed anywhere else.
"""
import hashlib
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_contract
import crew_coord
import crew_ticket
import crew_wave
from review_fixtures import git
from scope_fixtures import approve_as_user, make_repo, make_ticket

CHANNEL = "peers"
HUB = "coord"
REF = f"refs/heads/crew-coord/{CHANNEL}"
BODY = b"GET /widgets -> [{id, name}]\n"


# --- fixtures ----------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


@pytest.fixture(name="hub")
def _hub(tmp_path):
    bare = tmp_path / "hub.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)
    return bare


@pytest.fixture(name="root")
def _root(tmp_path, hub):
    root = make_repo(tmp_path, mode="block", name="main")
    # origin gives the repo key only and is never fetched: a short URL, since a
    # Windows tmp_path makes a local path's key pass 128 characters (G3c CI).
    # The channel lives on the remote `coord`.
    git(root, "remote", "add", "origin", "https://example.test/owner/repo.git")
    git(root, "remote", "add", HUB, str(hub))
    return root


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _ticket(root, ticket="T-1", touch=("src/**",)):
    make_ticket(root, ticket, touch, files=[touch[0].replace("**", "x.py")], activate=False)
    approve_as_user(root, ticket)


def _contract(root, *args, remote=HUB):
    return crew_contract.main([args[0], "--root", str(root), "--remote", remote] + list(args[1:]))


def _built(root, tmp_path, ticket="T-1", name="api", remote=HUB):
    """`name` v1 put on the channel and built against by the approved `ticket`."""
    body = tmp_path / f"{name}.txt"
    body.write_bytes(BODY)
    assert _contract(root, "put", "--channel", CHANNEL, "--name", name, "--file", str(body), remote=remote) == 0
    assert _contract(root, "build-against", "--channel", CHANNEL, "--name", name, "--version", "1",
                     "--ticket", ticket, remote=remote) == 0


def _files(root):
    chan = crew_coord.Channel(str(root), HUB, CHANNEL)
    tip, state, _ = chan.fetch()
    assert state == "ok"
    return chan.read(tip)


def _peer_rewrites(root, files, drop=(), remote=HUB):
    chan = crew_coord.Channel(str(root), remote, CHANNEL)

    def change(tree):
        for path in drop:
            tree.pop(path, None)
        tree.update(files)
        return "ok", "peer"
    assert chan.write(change, "peer: rewrite").status == "ok"


def _record(root, version=1):
    return json.loads(_files(root)[f"contracts/api/v{version}.json"])


def _rewrite_record(root, **changes):
    record = _record(root)
    record.update(changes)
    _peer_rewrites(root, {"contracts/api/v1.json": json.dumps(record).encode()})


def _verify(capsys, root, ticket="T-1", extra=()):
    code = crew_contract.main(["verify", "--root", str(root), "--ticket", ticket] + list(extra))
    out = capsys.readouterr()
    return code, out.out + out.err


@pytest.fixture(name="calls")
def _calls(monkeypatch):
    seen = []
    real = crew_coord.run_git

    def spy(root, args, **kwargs):
        seen.append(list(args))
        return real(root, args, **kwargs)
    monkeypatch.setattr(crew_coord, "run_git", spy)
    return seen


def _channel_calls(calls):
    return [c for c in calls if c and c[0] in ("ls-remote", "fetch", "push")]


# --- verify ------------------------------------------------------------------------

def test_verify_passes_on_an_unchanged_contract(capsys, tmp_path, root):
    _ticket(root)
    _built(root, tmp_path)
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == 0, out
    assert f"contract api v1 current: {_sha(BODY)[:19]} on crew-coord/{CHANNEL}" in out
    assert out.rstrip().endswith("[peer-written]")


def test_a_newer_draft_does_not_refuse(capsys, tmp_path, root):
    _ticket(root)
    _built(root, tmp_path)
    newer = tmp_path / "v2.txt"
    newer.write_bytes(b"v2\n")
    assert _contract(root, "put", "--channel", CHANNEL, "--name", "api", "--file", str(newer),
                     "--new-version", "--ticket", "T-2") == 0
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == 0, out
    assert "current" in out and "newer on the channel: v2 (information only)" in out


@pytest.mark.parametrize("how,needle", [
    ("record-hash", "the record's hash is"),
    ("body", "its body's sha256 is not the record's hash"),
    ("draft-again", "its status is draft"),
    ("not-in-built-by", "built_by no longer names")],
    ids=["record-hash", "body", "draft-again", "not-in-built-by"])
def test_a_changed_contract_is_a_mismatch(capsys, tmp_path, root, how, needle):
    _ticket(root)
    _built(root, tmp_path)
    if how == "record-hash":
        _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"})
        _rewrite_record(root, hash=_sha(b"edited\n"),
                        built_by=[dict(e, hash=_sha(b"edited\n")) for e in _record(root)["built_by"]])
    elif how == "body":
        _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"})
    elif how == "draft-again":
        _rewrite_record(root, status="draft", built_by=[])
    else:
        _rewrite_record(root, built_by=[dict(e, ticket="T-9") for e in _record(root)["built_by"]])
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == crew_contract.EXIT_REFUSED, out
    assert "contract api v1 changed since T-1 built against it" in out
    assert needle in out


@pytest.mark.parametrize("changes", [
    {"built_by": ["bad"]}, {"hash": "not-a-hash"}, {"status": "frozen?"}],
    ids=["malformed-built-by", "malformed-hash", "unknown-status"])
def test_a_malformed_field_stays_unknown(capsys, tmp_path, root, changes):
    """Review round 5: a malformed entry might be this build's; only a
    well-formed change is a mismatch."""
    _ticket(root)
    _built(root, tmp_path)
    _rewrite_record(root, **changes)
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == crew_contract.EXIT_UNKNOWN, out
    assert "its record is corrupt" in out


@pytest.mark.parametrize("changes,needle", [
    ({"status": "draft"}, "its status is draft"),
    ({"built_by": []}, "built_by no longer names"),
    ({"hash": _sha(b"edited\n")}, "the record's hash is")],
    ids=["status-only", "built-by-only", "hash-only"])
def test_a_one_field_edit_is_a_mismatch_not_unknown(capsys, tmp_path, root, changes, needle):
    """L-0634 review round 4: a single-field edit leaves the record inconsistent,
    which parse_record calls corrupt; it is still a change, exit 1."""
    _ticket(root)
    _built(root, tmp_path)
    _rewrite_record(root, **changes)
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == crew_contract.EXIT_REFUSED, out
    assert "contract api v1 changed since T-1 built against it" in out
    assert needle in out and "its record is corrupt" in out


@pytest.mark.parametrize("how,needle", [
    ("fetch-fails", "could not fetch crew-coord/peers"),
    ("channel-absent", "crew-coord/peers does not exist"),
    ("record-missing", "has no contracts/api/v1.json"),
    ("body-missing", "has no contracts/api/v1.body"),
    ("record-corrupt", "its record is corrupt"),
    ("bindings-not-json", "contract bindings unknown"),
    ("bindings-schema", "contract bindings unknown"),
    ("binding-field-missing", "contract bindings unknown"),
    ("bindings-emptied", "holds no bindings"),
    ("record-deeply-nested", "its record is corrupt"),
    ("remote-gone", "'coord' is not a configured remote")],
    ids=["fetch-fails", "channel-absent", "record-missing", "body-missing", "record-corrupt",
         "bindings-not-json", "bindings-schema", "binding-field-missing", "bindings-emptied",
         "record-deeply-nested", "remote-gone"])
def test_what_cannot_be_checked_is_unknown(capsys, tmp_path, root, hub, how, needle):
    _ticket(root)
    _built(root, tmp_path)
    binding = crew_contract.binding_path(str(root), "T-1")
    if how == "fetch-fails":
        git(root, "remote", "set-url", HUB, str(tmp_path / "gone.git"))
    elif how == "channel-absent":
        git(hub, "update-ref", "-d", REF)
    elif how == "record-missing":
        _peer_rewrites(root, {}, drop=["contracts/api/v1.json"])
    elif how == "body-missing":
        _peer_rewrites(root, {}, drop=["contracts/api/v1.body"])
    elif how == "record-corrupt":
        _peer_rewrites(root, {"contracts/api/v1.json": b"{corrupt"})
    elif how == "bindings-not-json":
        _write(binding, "{not json")
    elif how == "bindings-schema":
        _write(binding, json.dumps({"schema": 2, "bindings": []}))
    elif how == "binding-field-missing":
        _write(binding, json.dumps({"schema": 1, "bindings": [{"channel": CHANNEL, "name": "api",
                                                               "version": 1}]}))
    elif how == "record-deeply-nested":  # review round 6: json.loads raised RecursionError
        _peer_rewrites(root, {"contracts/api/v1.json": b"[" * 100000 + b"]" * 100000})
    elif how == "bindings-emptied":
        _write(binding, json.dumps({"schema": 1, "bindings": []}))
    else:  # the remote the binding was built on is gone (renamed)
        git(root, "remote", "rename", HUB, "elsewhere")
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == crew_contract.EXIT_UNKNOWN, out
    assert "unknown" in out and needle in out


@pytest.fixture(name="alt")
def _alt(tmp_path, root):
    """A second remote, `alt`, with its own bare repository; `coord.remote`
    is not set, so it reads the default `origin`, which is never fetched."""
    bare = tmp_path / "alt.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)
    git(root, "remote", "add", "alt", str(bare))
    return bare


def test_a_binding_is_checked_on_the_remote_it_was_built_on(capsys, tmp_path, root, alt):
    """L-0634 review round 2: a binding built with `--remote alt` was checked on
    `coord.remote` (origin), where an unchanged copy read current while the
    contract on alt had been rewritten."""
    _ticket(root)
    _built(root, tmp_path)
    (tmp_path / "api.txt").unlink()
    _built(root, tmp_path, remote="alt")
    bound = crew_contract.read_bindings(crew_contract.binding_path(str(root), "T-1"))[0]
    assert sorted(b["remote"] for b in bound) == ["alt", HUB]
    _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"}, remote="alt")
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == crew_contract.EXIT_REFUSED, out
    assert "contract api v1 changed since T-1 built against it" in out
    assert f"contract api v1 current: {_sha(BODY)[:19]} on crew-coord/{CHANNEL}" in out


def test_verify_remote_naming_another_remote_is_unknown(capsys, tmp_path, root, alt):
    _ticket(root)
    _built(root, tmp_path, remote="alt")
    capsys.readouterr()

    code, out = _verify(capsys, root, "T-1", ["--remote", HUB])

    assert code == crew_contract.EXIT_UNKNOWN, out
    assert f"built against on remote alt, not {HUB}" in out
    code, out = _verify(capsys, root, "T-1", ["--remote", "alt"])
    assert code == 0, out


def test_no_bindings_means_no_fetch(capsys, root, calls):
    _ticket(root)

    code, out = _verify(capsys, root)

    assert code == 0, out
    assert "no contract bindings" in out
    assert _channel_calls(calls) == []


def test_readme_and_docstring_state_verify_options():
    """Review round 1: the docs said every command takes --channel."""
    readme = os.path.join(os.path.dirname(os.path.abspath(context.__file__)), os.pardir, "README.md")
    with open(readme, encoding="utf-8") as handle:
        text = " ".join(handle.read().split())
    assert "`--channel` (not on `verify`, which reads each binding's channel from the binding)" in text
    assert "every command but `verify` takes `--channel`" in " ".join(crew_contract.__doc__.split())
    with pytest.raises(SystemExit):
        crew_contract._parser().parse_args(["verify", "--ticket", "T-1", "--channel", "x"])  # pylint: disable=protected-access


def test_verify_usage_is_checked_before_any_git_call(capsys, root, calls):
    code, out = _verify(capsys, root, ticket="../T-1")

    assert code == crew_contract.EXIT_USAGE and out.startswith("usage")
    assert calls == []


def _refs(root):
    lines = git(root, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
    return dict(line.split(" ", 1) for line in lines)


def _snapshot(root):
    found = {}
    common = crew_ticket.common_dir(str(root))
    for base in (str(root), os.path.join(common, "crew")):
        for folder, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in files:
                path = os.path.join(folder, name)
                with open(path, "rb") as handle:
                    found[path] = handle.read()
    gitdir = git(root, "rev-parse", "--absolute-git-dir")
    return {"files": found, "head": git(root, "rev-parse", "HEAD"), "refs": _refs(root),
            "fetch_head": os.path.exists(os.path.join(gitdir, "FETCH_HEAD")),
            "index": os.stat(os.path.join(common, "index")).st_mtime_ns}


def test_verify_writes_nothing(capsys, tmp_path, root, hub, calls):
    _ticket(root)
    _built(root, tmp_path)
    _index(root, ["T-1"])
    crew_wave.write_set(str(root), "s", ["T-1"], {"T-1": []})
    _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"})
    before, remote, seen = _snapshot(root), _refs(hub), len(calls)

    assert _verify(capsys, root)[0] == crew_contract.EXIT_REFUSED
    assert crew_wave.main(["plan", "--root", str(root), "--set", "s"]) == 0

    assert _snapshot(root) == before
    assert _refs(hub) == remote
    assert [c for c in calls[seen:] if c[0] == "push"] == []


def test_verify_messages_are_sanitised(capsys, tmp_path, root):
    _ticket(root)
    _built(root, tmp_path)
    record = _record(root)
    # A peer's corrupt record whose reason carries a control character.
    _peer_rewrites(root, {"contracts/api/v1.json": json.dumps(dict(record, status="x\n\u202ey\x1b[2J")).encode()})
    capsys.readouterr()

    code, out = _verify(capsys, root)

    assert code == crew_contract.EXIT_UNKNOWN  # a status that is neither draft nor built-against
    assert "\u202e" not in out and "\x1b" not in out
    assert not any(line.startswith("y") for line in out.splitlines())
    assert all(line.endswith("[peer-written]") for line in out.splitlines() if line.strip())


# --- the wave ------------------------------------------------------------------------

def _index(root, rows):
    _write(root / ".work" / "INDEX.md", "".join(f"{t} | approved | high | r | title\n" for t in rows))


def _plan(root, tickets):
    """The wave over `tickets`, each with no dependencies (a set file)."""
    crew_wave.write_set(str(root), "s", tickets, {t: [] for t in tickets})
    return crew_wave.plan(str(root), slug="s")


def _plan_rows(root, tickets):
    return {r["ticket"]: r for r in _plan(root, tickets)["rows"]}


def test_wave_accepts_a_ticket_whose_bindings_hold(tmp_path, root):
    _ticket(root)
    _built(root, tmp_path)
    _index(root, ["T-1"])

    got = _plan_rows(root, ["T-1"])["T-1"]

    assert (got["eligible"], got["reason"]) == (True, "")


def test_wave_refuses_a_contract_mismatch(tmp_path, root):
    _ticket(root)
    _built(root, tmp_path)
    _index(root, ["T-1"])
    _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"})

    got = _plan_rows(root, ["T-1"])["T-1"]
    text = crew_wave.plan_text(_plan(root, ["T-1"]))

    assert got["eligible"] is False
    assert "T-1 refused: contract api v1 changed since T-1 built against it" in text
    started = crew_wave.start(str(root), "s")
    assert started["plan"]["wave"] == []
    assert not os.path.exists(os.path.join(crew_wave.lanes_dir(str(root), "s"), "T-1.json"))


def test_wave_reads_a_binding_from_its_own_remote(tmp_path, root, alt):
    _ticket(root)
    _built(root, tmp_path, remote="alt")
    _index(root, ["T-1"])
    assert _plan_rows(root, ["T-1"])["T-1"]["eligible"] is True

    _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"}, remote="alt")
    got = _plan_rows(root, ["T-1"])["T-1"]

    assert got["eligible"] is False
    assert "contract api v1 changed since T-1 built against it" in got["reason"]


def test_wave_refuses_an_unknown_contract(tmp_path, root):
    _ticket(root)
    _built(root, tmp_path)
    _index(root, ["T-1"])
    _peer_rewrites(root, {"contracts/api/v1.json": b"{corrupt"})

    text = crew_wave.plan_text(_plan(root, ["T-1"]))

    assert "T-1 refused: contract api v1 unknown (its record is corrupt" in text


def test_wave_other_tickets_still_eligible(tmp_path, root):
    _ticket(root)
    _ticket(root, "T-2", ("other/**",))
    _built(root, tmp_path)
    _index(root, ["T-1", "T-2"])
    _peer_rewrites(root, {"contracts/api/v1.body": b"edited\n"})

    rows = _plan_rows(root, ["T-1", "T-2"])

    assert rows["T-1"]["eligible"] is False
    assert (rows["T-2"]["eligible"], rows["T-2"]["reason"]) == (True, "")


def test_wave_checks_contracts_after_dependencies(tmp_path, root, calls):
    _ticket(root)
    _built(root, tmp_path)
    _write(root / ".work" / "INDEX.md", "T-1 | approved | high | r | title (depends on T-9)\n"
                                        "T-9 | approved | high | r | title\n")
    seen = len(calls)

    got = crew_wave.plan(str(root), tickets=["T-1"])["rows"][0]

    assert "dependency T-9 is not closed" in got["reason"]
    assert _channel_calls(calls[seen:]) == []


def test_wave_ticket_without_bindings_fetches_nothing(root, calls):
    _ticket(root)
    _index(root, ["T-1"])
    seen = len(calls)

    assert _plan_rows(root, ["T-1"])["T-1"]["eligible"] is True
    assert _channel_calls(calls[seen:]) == []
