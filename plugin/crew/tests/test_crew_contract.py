"""crew_contract.py: versioned interface contracts on the coordination
channel (T-0031).

Every case builds throwaway repositories under pytest's tmp_path. A bare
repository, `hub.git`, is the shared coordination remote; each side is its own
repository (its own `origin`, so its own repo key) with `hub.git` added as the
remote `coord`. Nothing here pushes anywhere else.
"""
import hashlib
import json
import os
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_contract
import crew_coord
import pytest
from review_fixtures import git
from scope_fixtures import approve_as_user, make_repo, make_ticket

CHANNEL = "test"
REF = f"refs/heads/crew-coord/{CHANNEL}"
FORCE_FLAGS = ("--force", "-f", "--force-with-lease", "--force-if-includes", "--mirror")
BODY = b"GET /widgets -> [{id, name}]\n"
BODY_2 = b"GET /widgets -> [{id, name, size}]\n"


# --- fixtures ----------------------------------------------------------------

def _bare(path):
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)
    return path


@pytest.fixture(name="hub")
def _hub(tmp_path):
    return _bare(tmp_path / "hub.git")


def _side(tmp_path, hub, name):
    root = make_repo(tmp_path, name=name)
    origin = _bare(tmp_path / f"{name}-origin.git")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "remote", "add", "coord", str(hub))
    return root


@pytest.fixture(name="wt")
def _wt(tmp_path, hub):
    return _side(tmp_path, hub, "side-a")


@pytest.fixture(name="wt_b")
def _wt_b(tmp_path, hub):
    return _side(tmp_path, hub, "side-b")


def _approved(root, ticket="T-1"):
    make_ticket(root, ticket, activate=False)
    approve_as_user(root, ticket)


def _body(tmp_path, data=BODY, name="body.txt"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _run(capsys, root, cmd, *extra):
    code = crew_contract.main([cmd, "--root", str(root), "--remote", "coord", "--channel", CHANNEL]
                              + [str(arg) for arg in extra])
    out = capsys.readouterr()
    return code, out.out + out.err


def _put(capsys, root, path, *extra, name="api"):
    return _run(capsys, root, "put", "--name", name, "--file", path, *extra)


def _build(capsys, root, version=1, ticket="T-1", name="api"):
    return _run(capsys, root, "build-against", "--name", name, "--version", version, "--ticket", ticket)


def _remote_files(hub):
    tip = git(hub, "rev-parse", "--verify", "-q", REF, check=False)
    if not tip:
        return None
    names = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", tip], cwd=hub, check=True,
                           capture_output=True, stdin=subprocess.DEVNULL).stdout.split(b"\0")
    return {name.decode(): subprocess.run(["git", "cat-file", "blob", f"{tip}:{name.decode()}"], cwd=hub,
                                          check=True, capture_output=True,
                                          stdin=subprocess.DEVNULL).stdout
            for name in names if name}


def _record(hub, version=1, name="api"):
    return json.loads(_remote_files(hub)[f"contracts/{name}/v{version}.json"])


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _repo(root):
    return crew_coord.repo_key(crew_contract.crew_ticket.toplevel(str(root)))[0]


def _binding_path(root, ticket="T-1"):
    return root / ".work" / "tickets" / ticket / "contracts.json"


def _raw_write(root, files, drop=()):
    """Write arbitrary blobs onto the channel through crew_coord's own
    commit-on-fetched-tip path, the way a buggy or hostile peer could."""
    chan = crew_coord.Channel(str(root), "coord", CHANNEL)

    def change(tree):
        for path in drop:
            tree.pop(path, None)
        tree.update(files)
        return "ok", "raw"
    result = chan.write(change, "test: raw write")
    assert result.status == "ok", result.message


@pytest.fixture(name="calls")
def _calls(monkeypatch):
    """Records the argv of every git call crew_coord's run_git makes."""
    seen = []
    real = crew_coord.run_git

    def spy(root, args, **kwargs):
        seen.append(list(args))
        return real(root, args, **kwargs)
    monkeypatch.setattr(crew_coord, "run_git", spy)
    return seen


def _pushes(calls):
    return [c for c in calls if c and c[0] == "push"]


def _channel_calls(calls):
    return [c for c in calls if c and c[0] in ("ls-remote", "fetch", "push")]


def _frozen(capsys, tmp_path, wt, ticket="T-1"):
    """v1 of `api` put and built against by `ticket` on side `wt`."""
    _approved(wt, ticket)
    assert _put(capsys, wt, _body(tmp_path))[0] == 0
    code, out = _build(capsys, wt, ticket=ticket)
    assert code == 0, out


# --- put -------------------------------------------------------------------------

def test_put_writes_v1_draft_with_the_body_hash(capsys, tmp_path, wt, hub, calls):
    code, out = _put(capsys, wt, _body(tmp_path))

    assert code == 0, out
    files = _remote_files(hub)
    assert files["contracts/api/v1.body"] == BODY
    assert json.loads(files["contracts/api/v1.json"]) == {
        "name": "api", "version": 1, "hash": _sha(BODY), "status": "draft", "built_by": []}
    log = [json.loads(line) for line in files["log.jsonl"].splitlines()]
    assert len(log) == 1 and log[0]["event"] == "contract-put" and log[0]["ticket"] == "contracts/api/v1"
    assert git(hub, "rev-list", "--count", REF) == "1"
    assert len(_pushes(calls)) == 1


def test_put_replaces_a_draft_in_place(capsys, tmp_path, wt, hub):
    _put(capsys, wt, _body(tmp_path))

    code, out = _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"))

    assert code == 0, out
    files = _remote_files(hub)
    assert files["contracts/api/v1.body"] == BODY_2
    assert _record(hub)["hash"] == _sha(BODY_2)
    assert _record(hub)["version"] == 1 and _record(hub)["status"] == "draft"
    assert "contracts/api/v2.json" not in files


def test_put_on_a_frozen_version_is_refused(capsys, tmp_path, wt, hub, calls):
    _frozen(capsys, tmp_path, wt)
    before = git(hub, "rev-parse", REF)
    pushes = len(_pushes(calls))

    code, out = _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"))

    assert code == crew_contract.EXIT_REFUSED
    assert "v1" in out and "frozen" in out
    assert f"{_repo(wt)}:T-1" in out
    assert out.rstrip().endswith("[peer-written]")
    assert git(hub, "rev-parse", REF) == before
    assert len(_pushes(calls)) == pushes


def test_new_version_needs_a_frozen_predecessor_and_a_ticket(capsys, tmp_path, wt, hub):
    two = _body(tmp_path, BODY_2, "two.txt")
    # No version yet: nothing to supersede.
    assert _put(capsys, wt, two, "--new-version", "--ticket", "T-2")[0] == crew_contract.EXIT_REFUSED
    assert _remote_files(hub) is None
    _put(capsys, wt, _body(tmp_path))
    before = git(hub, "rev-parse", REF)

    # v1 is still a draft.
    code, out = _put(capsys, wt, two, "--new-version", "--ticket", "T-2")
    assert code == crew_contract.EXIT_REFUSED and "draft" in out
    # --ticket missing, not a ticket id, or given without --new-version: usage.
    assert _put(capsys, wt, two, "--new-version")[0] == crew_contract.EXIT_USAGE
    assert _put(capsys, wt, two, "--new-version", "--ticket", "../T-2")[0] == crew_contract.EXIT_USAGE
    assert _put(capsys, wt, two, "--ticket", "T-2")[0] == crew_contract.EXIT_USAGE
    assert git(hub, "rev-parse", REF) == before

    _approved(wt, "T-1")
    assert _build(capsys, wt)[0] == 0
    code, out = _put(capsys, wt, two, "--new-version", "--ticket", "T-2")

    assert code == 0, out
    assert _record(hub, 2) == {"name": "api", "version": 2, "hash": _sha(BODY_2), "status": "draft",
                               "built_by": []}
    log = [json.loads(line) for line in _remote_files(hub)["log.jsonl"].splitlines()]
    assert log[-1]["event"] == "contract-new-version" and "T-2" in log[-1]["detail"]


def test_new_version_leaves_the_old_version_byte_identical(capsys, tmp_path, wt, hub):
    _frozen(capsys, tmp_path, wt)
    old = {k: v for k, v in _remote_files(hub).items() if k.startswith("contracts/api/v1.")}

    assert _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"), "--new-version", "--ticket", "T-2")[0] == 0
    # A draft v2 is replaced in place, and v1 still does not move.
    assert _put(capsys, wt, _body(tmp_path, b"third\n", "three.txt"))[0] == 0

    files = _remote_files(hub)
    assert {k: v for k, v in files.items() if k.startswith("contracts/api/v1.")} == old
    assert files["contracts/api/v2.body"] == b"third\n"


# --- build-against -------------------------------------------------------------------

def test_build_against_freezes_and_writes_the_binding(capsys, tmp_path, wt, hub):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))

    code, out = _build(capsys, wt)

    assert code == 0, out
    record = _record(hub)
    assert record["status"] == "built-against"
    [entry] = record["built_by"]
    assert entry["repo"] == _repo(wt) and entry["ticket"] == "T-1" and entry["hash"] == _sha(BODY)
    assert crew_coord.parse_stamp(entry["at"]) is not None
    assert json.loads(_binding_path(wt).read_text(encoding="utf-8")) == {
        "schema": 1, "bindings": [{"channel": CHANNEL, "name": "api", "version": 1, "hash": _sha(BODY)}]}
    assert crew_contract.read_bindings(str(_binding_path(wt))) == (
        [{"channel": CHANNEL, "name": "api", "version": 1, "hash": _sha(BODY)}], None)


def test_build_against_is_idempotent(capsys, tmp_path, wt, hub, calls):
    _frozen(capsys, tmp_path, wt)
    before, binding = git(hub, "rev-parse", REF), _binding_path(wt).read_bytes()
    pushes = len(_pushes(calls))

    code, out = _build(capsys, wt)

    assert code == 0, out
    assert git(hub, "rev-parse", REF) == before
    assert len(_pushes(calls)) == pushes
    assert len(_record(hub)["built_by"]) == 1
    assert _binding_path(wt).read_bytes() == binding


def test_build_against_rewrites_a_lost_binding(capsys, tmp_path, wt, hub):
    """The channel took the build, the local write did not: a re-run writes
    the binding without a second entry."""
    _frozen(capsys, tmp_path, wt)
    _binding_path(wt).unlink()

    assert _build(capsys, wt)[0] == 0

    assert len(_record(hub)["built_by"]) == 1
    assert json.loads(_binding_path(wt).read_text(encoding="utf-8"))["bindings"][0]["hash"] == _sha(BODY)


def _assert_nothing_written(hub, before, wt):
    assert git(hub, "rev-parse", "--verify", "-q", REF, check=False) == before
    assert not _binding_path(wt).exists()


def test_build_against_refuses_an_unapproved_ticket(capsys, tmp_path, wt, hub, calls):
    make_ticket(wt, "T-1", activate=False)
    _put(capsys, wt, _body(tmp_path))
    before, seen = git(hub, "rev-parse", REF), len(calls)

    code, out = _build(capsys, wt)

    assert code == crew_contract.EXIT_REFUSED
    assert "not approved" in out
    _assert_nothing_written(hub, before, wt)
    assert _channel_calls(calls[seen:]) == []


def test_build_against_refuses_a_missing_version(capsys, tmp_path, wt, hub):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))
    before = git(hub, "rev-parse", REF)

    code, out = _build(capsys, wt, version=2)

    assert code == crew_contract.EXIT_REFUSED
    assert "v2 does not exist" in out
    _assert_nothing_written(hub, before, wt)


def test_build_against_refuses_a_body_that_does_not_match_its_hash(capsys, tmp_path, wt, hub):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))
    _raw_write(wt, {"contracts/api/v1.body": b"swapped\n"})
    before = git(hub, "rev-parse", REF)

    code, out = _build(capsys, wt)

    assert code == crew_contract.EXIT_REFUSED
    assert "does not match" in out and out.rstrip().endswith("[peer-written]")
    _assert_nothing_written(hub, before, wt)


@pytest.mark.parametrize("blob", [
    b"{not json", b"[1, 2]",
    json.dumps({"name": "api", "version": 1, "hash": _sha(BODY), "status": "frozen",
                "built_by": []}).encode()],
    ids=["not-json", "not-object", "bad-status"])
def test_build_against_reads_a_corrupt_record_as_unknown(capsys, tmp_path, wt, hub, blob):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))
    _raw_write(wt, {"contracts/api/v1.json": blob})
    before = git(hub, "rev-parse", REF)

    code, out = _build(capsys, wt)

    assert code == crew_contract.EXIT_UNKNOWN
    assert "unknown" in out and "corrupt" in out
    _assert_nothing_written(hub, before, wt)


def test_build_against_when_the_fetch_fails_is_unknown(capsys, tmp_path, wt, hub):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))
    before = git(hub, "rev-parse", REF)
    git(wt, "remote", "set-url", "coord", str(tmp_path / "gone.git"))

    code, out = _build(capsys, wt)

    assert code == crew_contract.EXIT_UNKNOWN
    assert out.startswith("unknown")
    _assert_nothing_written(hub, before, wt)


@pytest.mark.parametrize("text", [
    "{not json", json.dumps({"schema": 2, "bindings": []}),
    json.dumps({"schema": 1, "bindings": [{"channel": CHANNEL, "name": "api", "version": 1}]})],
    ids=["not-json", "other-schema", "missing-field"])
def test_build_against_refuses_an_unreadable_binding_file(capsys, tmp_path, wt, hub, calls, text):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))
    _binding_path(wt).write_text(text, encoding="utf-8")
    before, seen = git(hub, "rev-parse", REF), len(calls)

    code, out = _build(capsys, wt)

    assert code == crew_contract.EXIT_UNKNOWN
    assert "contracts.json" in out
    assert git(hub, "rev-parse", REF) == before
    assert _binding_path(wt).read_text(encoding="utf-8") == text
    assert _channel_calls(calls[seen:]) == []


def test_build_against_refuses_a_binding_with_another_hash(capsys, tmp_path, wt, hub):
    _approved(wt)
    _put(capsys, wt, _body(tmp_path))
    stale = {"schema": 1, "bindings": [{"channel": CHANNEL, "name": "api", "version": 1,
                                        "hash": _sha(b"what was built\n")}]}
    _binding_path(wt).write_text(json.dumps(stale), encoding="utf-8")
    before = git(hub, "rev-parse", REF)

    code, out = _build(capsys, wt)

    assert code == crew_contract.EXIT_REFUSED
    assert "contracts.json" in out
    assert git(hub, "rev-parse", REF) == before
    assert json.loads(_binding_path(wt).read_text(encoding="utf-8")) == stale


def test_two_sides_build_against_one_version(capsys, tmp_path, wt, wt_b, hub):
    _frozen(capsys, tmp_path, wt)
    first = _record(hub)["built_by"][0]
    _approved(wt_b, "T-7")

    code, out = _build(capsys, wt_b, ticket="T-7")

    assert code == 0, out
    record = _record(hub)
    assert record["built_by"][0] == first
    assert record["built_by"][1]["repo"] == _repo(wt_b) != first["repo"]
    assert record["built_by"][1]["ticket"] == "T-7"
    assert _remote_files(hub)["contracts/api/v1.body"] == BODY
    assert json.loads(_binding_path(wt_b, "T-7").read_text(encoding="utf-8"))["bindings"][0]["hash"] == _sha(BODY)


# --- status --------------------------------------------------------------------------

def test_status_is_read_only_and_labels_peer_data(capsys, tmp_path, wt, wt_b, hub, calls):
    _frozen(capsys, tmp_path, wt)
    _put(capsys, wt, _body(tmp_path, b"other\n", "o.txt"), name="events")
    before, seen = git(hub, "rev-parse", REF), len(calls)
    snap = _snapshot(wt_b, hub)

    code, out = _run(capsys, wt_b, "status")

    assert code == 0, out
    lines = [line for line in out.splitlines() if line.startswith(("api ", "events "))]
    assert len(lines) == 2
    assert all(line.endswith("[peer-written]") for line in lines)
    api = next(line for line in lines if line.startswith("api "))
    assert "v1 built-against" in api and _sha(BODY)[:19] in api and f"{_repo(wt)}:T-1" in api
    assert "v1 draft" in next(line for line in lines if line.startswith("events "))
    assert git(hub, "rev-parse", REF) == before
    assert _pushes(calls[seen:]) == []
    assert _snapshot(wt_b, hub) == snap


def test_status_reads_a_corrupt_record_as_unknown(capsys, tmp_path, wt, hub):
    _put(capsys, wt, _body(tmp_path))
    _put(capsys, wt, _body(tmp_path, b"e\n", "e.txt"), name="events")
    _raw_write(wt, {"contracts/api/v1.json": b"{broken"})

    code, out = _run(capsys, wt, "status")

    assert code == crew_contract.EXIT_UNKNOWN
    assert any(line.startswith("api v1 unknown") and line.endswith("[peer-written]") for line in out.splitlines())
    assert any(line.startswith("events v1 draft") for line in out.splitlines())


@pytest.mark.parametrize("files", [
    {"contracts/api/v1.body": b"x"},
    {"contracts/api/v2.json": b"{}", "contracts/api/v2.body": b"x"},
    {"contracts/api/notes.txt": b"x"},
    {"contracts/stray": b"x"}],
    ids=["no-record", "gap", "stray-file", "file-not-dir"])
def test_status_reads_a_malformed_contract_tree_as_unknown(capsys, wt, files):
    _raw_write(wt, files)

    code, out = _run(capsys, wt, "status")

    assert code == crew_contract.EXIT_UNKNOWN
    assert "unknown" in out


def test_status_sanitises_peer_written_fields(capsys, tmp_path, wt, hub):
    _frozen(capsys, tmp_path, wt)
    record = _record(hub)
    record["built_by"][0]["ticket"] = "T-1\n\u202eforged line\x1b[2J"
    _raw_write(wt, {"contracts/api/v1.json": json.dumps(record).encode()})

    _, out = _run(capsys, wt, "status")

    assert "\u202e" not in out and "\x1b" not in out
    assert not any(line.startswith("forged") for line in out.splitlines())
    assert "T-1??forged line?[2J" in out


def test_status_on_a_new_channel_and_a_failed_fetch(capsys, tmp_path, wt):
    code, out = _run(capsys, wt, "status")
    assert code == 0 and "no channel yet" in out

    git(wt, "remote", "set-url", "coord", str(tmp_path / "gone.git"))
    code, out = _run(capsys, wt, "status")
    assert code == crew_contract.EXIT_UNKNOWN and out.startswith("unknown")


# --- usage ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [
    ("put", "--name", "Bad_Name", "--file", "BODY"),
    ("put", "--name=-api", "--file", "BODY"),
    ("put", "--name", "a" * 65, "--file", "BODY"),
    ("put", "--name", "api", "--file", "BIG"),
    ("put", "--name", "api", "--file", "MISSING"),
    ("build-against", "--name", "api", "--version", "0", "--ticket", "T-1"),
    ("build-against", "--name", "api", "--version=-1", "--ticket", "T-1"),
    ("build-against", "--name", "api", "--version", "v1", "--ticket", "T-1"),
    ("build-against", "--name", "api", "--version", "1", "--ticket", "../x"),
    ("build-against", "--name", "API", "--version", "1", "--ticket", "T-1"),
    ("status", "--name", "a/b")],
    ids=["underscore", "leading-dash", "too-long", "over-1mib", "missing-file", "version-0",
         "version-negative", "version-text", "ticket-path", "upper-name", "status-name"])
def test_bad_name_version_or_size_is_refused_before_any_fetch(capsys, tmp_path, wt, hub, calls, extra):
    paths = {"BODY": str(_body(tmp_path)), "MISSING": str(tmp_path / "missing.txt"),
             "BIG": str(_body(tmp_path, b"x" * (crew_contract.MAX_BODY + 1), "big.txt"))}
    cmd, *rest = extra

    code, out = _run(capsys, wt, cmd, *[paths.get(arg, arg) for arg in rest])

    assert code == crew_contract.EXIT_USAGE, out
    assert out.startswith("usage")
    assert _channel_calls(calls) == []
    assert _remote_files(hub) is None


def test_a_body_of_exactly_one_mib_is_accepted(capsys, tmp_path, wt, hub):
    data = b"y" * crew_contract.MAX_BODY

    assert _put(capsys, wt, _body(tmp_path, data, "edge.txt"))[0] == 0
    assert _remote_files(hub)["contracts/api/v1.body"] == data


# --- no force, isolation, claims, the race -----------------------------------------

def _assert_no_force(push):
    for arg in push:
        assert arg not in FORCE_FLAGS, push
        assert not arg.startswith("--force"), push
        assert not arg.startswith("+"), push


def test_push_argv_never_forces(capsys, tmp_path, wt, wt_b, calls):
    _frozen(capsys, tmp_path, wt)
    _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"), "--new-version", "--ticket", "T-2")
    _put(capsys, wt, _body(tmp_path, b"three\n", "three.txt"))
    _approved(wt_b, "T-7")
    _build(capsys, wt_b, ticket="T-7")

    pushes = _pushes(calls)
    assert len(pushes) == 5
    for push in pushes:
        _assert_no_force(push)
        assert push[:4] == ["push", "--no-verify", "--", crew_coord.PUSH_REMOTE]
        assert len(push) == 5 and push[4].endswith(f":{REF}")


def _read_or_none(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def _refs(root):
    lines = git(root, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
    return dict(line.split(" ", 1) for line in lines)


def _snapshot(root, hub):
    gitdir = git(root, "rev-parse", "--absolute-git-dir")
    tree = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                tree[os.path.relpath(path, root).replace(os.sep, "/")] = handle.read()
    crew_dir = os.path.join(gitdir, "crew")
    state = {}
    for dirpath, _, filenames in os.walk(crew_dir):
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                state[os.path.relpath(path, crew_dir)] = handle.read()
    hub_refs = _refs(hub)
    hub_refs.pop(REF, None)
    return {"tree": tree, "crew": state, "head": git(root, "rev-parse", "HEAD"),
            "symref": git(root, "symbolic-ref", "-q", "HEAD", check=False), "refs": _refs(root),
            "hub_refs": hub_refs, "status": git(root, "--no-optional-locks", "status", "--porcelain"),
            "fetch_head": _read_or_none(os.path.join(gitdir, "FETCH_HEAD")),
            "index": _read_or_none(os.path.join(gitdir, "index"))}


def test_only_the_channel_ref_and_the_binding_file_change(capsys, tmp_path, wt, hub):
    _approved(wt)
    body = _body(tmp_path)
    before = _snapshot(wt, hub)

    assert _put(capsys, wt, body)[0] == 0
    assert _snapshot(wt, hub) == before
    assert _build(capsys, wt)[0] == 0
    after = _snapshot(wt, hub)
    assert _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"), "--new-version", "--ticket", "T-2")[0] == 0
    assert _run(capsys, wt, "status")[0] == 0
    assert _snapshot(wt, hub) == after

    binding = ".work/tickets/T-1/contracts.json"
    assert binding not in before["tree"] and binding in after["tree"]
    after["tree"].pop(binding)
    assert after == before


def test_claims_survive_contract_writes(capsys, tmp_path, wt, wt_b, hub):
    claims = {"claims/x__T-9.json": b'{"peer": "bytes \\u0000 kept"}\n',
              "claims/y__T-3.json": b"not even json\n"}
    _raw_write(wt_b, claims)
    _frozen(capsys, tmp_path, wt)
    _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"), "--new-version", "--ticket", "T-2")

    files = _remote_files(hub)
    assert {k: v for k, v in files.items() if k.startswith("claims/")} == claims


def test_put_loses_the_race_to_a_freeze_and_is_refused(capsys, monkeypatch, tmp_path, wt, wt_b, hub):
    _put(capsys, wt, _body(tmp_path))
    _approved(wt_b, "T-7")
    real = crew_coord.run_git
    state = {"interleaved": False}

    def interleave(root, args, **kwargs):
        if args and args[0] == "push" and not state["interleaved"]:
            state["interleaved"] = True
            assert crew_contract.main(["build-against", "--root", str(wt_b), "--remote", "coord",
                                       "--channel", CHANNEL, "--name", "api", "--version", "1",
                                       "--ticket", "T-7"]) == 0
        return real(root, args, **kwargs)
    monkeypatch.setattr(crew_coord, "run_git", interleave)

    code, out = _put(capsys, wt, _body(tmp_path, BODY_2, "two.txt"))

    assert state["interleaved"]
    assert code == crew_contract.EXIT_REFUSED, out
    assert "frozen" in out
    assert _remote_files(hub)["contracts/api/v1.body"] == BODY
    assert _record(hub)["status"] == "built-against"


def test_module_runs_as_a_script(tmp_path, wt):
    script = os.path.join(os.path.dirname(os.path.abspath(crew_contract.__file__)), "crew_contract.py")
    done = subprocess.run([sys.executable, script, "status", "--root", str(wt), "--remote", "coord",
                           "--channel", CHANNEL], capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "no channel yet" in done.stdout
