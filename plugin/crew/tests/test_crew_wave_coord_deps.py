"""L-0633: cross-session dependencies `<channel>:<id>` in the autopilot wave.

    python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_wave_coord_deps.py \
        plugin/crew/tests/test_crew_wave.py -q

A wave ticket may depend on a ticket another session works, written
`<channel>:<id>` or `<channel>:<repo>:<id>`. It is closed only when the channel
`crew-coord/<channel>` was fetched and exactly one claim for that id reads
`done`. Every case builds a throwaway main checkout under tmp_path whose
`origin` is a bare repository there (crew_coord's `coord.remote` default);
peer claims are written onto it through crew_coord's own Channel, the way a
peer session writes them. Nothing is pushed anywhere else.
"""
import datetime
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_coord
import crew_ticket
import crew_wave
from review_fixtures import git
from scope_fixtures import approve_as_user, make_repo, make_ticket

CHANNEL = "peers"
REF = f"refs/heads/crew-coord/{CHANNEL}"
PEER_REPO = "example_2etest.owner.peer"
OTHER_REPO = "example_2etest.owner.other"


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
    git(root, "remote", "add", "origin", str(hub))
    return root


def _ticket(root, ticket="T-1", touch=("src/**",)):
    make_ticket(root, ticket, touch, files=[touch[0].replace("**", "x.py")], activate=False)
    approve_as_user(root, ticket)


def _index(root, rows):
    _write(root / ".work" / "INDEX.md", "".join(row + "\n" for row in rows))


def _row(ticket, status="approved", title="title"):
    return f"{ticket} | {status} | high | r | {title}"


def _wave(root, deps, rows=()):
    """T-1 approved with set-file `deps`, plus INDEX `rows`."""
    _ticket(root)
    _index(root, [_row("T-1")] + list(rows))
    crew_wave.write_set(str(root), "s", ["T-1"], {"T-1": deps})


def _stamp(minutes_ago=0):
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return when.isoformat(timespec="seconds")


def _claim(state, repo=PEER_REPO, ticket="T-0001", minutes_ago=1, session="peer-sess"):
    record = {"ticket": ticket, "repo": repo, "state": state,
              "claimed_at": _stamp(minutes_ago + 5), "heartbeat_at": _stamp(minutes_ago),
              "holder": {"session": session, "pid": 4242, "pid_start": None, "pidns": None,
                         "machine": "peer-host", "worktree": "/srv/peer"}}
    return {f"claims/{repo}__{ticket}.json": (json.dumps(record, indent=2) + "\n").encode()}


def _peer_writes(root, files, channel=CHANNEL):
    """A peer session's write: crew_coord's commit on the fetched tip."""
    chan = crew_coord.Channel(str(root), "origin", channel)

    def change(tree):
        tree.update(files)
        return "ok", "peer"
    result = chan.write(change, "peer: claim")
    assert result.status == "ok", result.message


def _row_of(root):
    return {row["ticket"]: row for row in crew_wave.plan(str(root), slug="s")["rows"]}["T-1"]


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


# --- the grammar ---------------------------------------------------------------

@pytest.mark.parametrize("value,parsed", [
    ("chan:T-0001", ("chan", None, "T-0001")),
    ("chan:repo.key:T-0001", ("chan", "repo.key", "T-0001")),
    ("chan-2:t-0001", ("chan-2", None, "T-0001")),
    ("T-0001", None),
    (":T-0001", ValueError), ("chan:", ValueError), ("chan::T-0001", ValueError),
    ("Chan:T-0001", ValueError), ("-chan:T-0001", ValueError), ("c_h:T-0001", ValueError),
    ("chan:repo:key:T-0001", ValueError), ("chan:repo__key:T-0001", ValueError),
    ("chan:Repo:T-0001", ValueError), ("chan:T-0001/x", ValueError), ("chan:T__1", ValueError),
    ("chan:T 0001", ValueError), (" chan:T-0001", ValueError), ("chan:T-0001\n", ValueError),
    ("chan:T-0001\t", ValueError)],
    ids=["short", "long", "lower-id", "plain", "empty-channel", "empty-id", "empty-repo",
         "upper-channel", "dash-channel", "underscore-channel", "fourth-part", "repo-double-underscore",
         "upper-repo", "id-slash", "id-double-underscore", "space-in-id", "leading-space",
         "trailing-newline", "trailing-tab"])
def test_cross_dep_grammar(value, parsed):
    if parsed is ValueError:
        with pytest.raises(crew_ticket.TicketError):
            crew_wave.cross_dep(value)
    else:
        assert crew_wave.cross_dep(value) == parsed


def test_set_file_accepts_and_validates_cross_deps(root):
    _ticket(root)
    crew_wave.write_set(str(root), "s", ["T-1"], {"T-1": ["T-9", "peers:T-0001", "peers:a.b:T-0002"]})

    data, state = crew_wave.read_set(str(root), "s")

    assert state == "ok"
    assert data["tickets"][0]["deps"] == ["T-9", "peers:T-0001", "peers:a.b:T-0002"]
    with pytest.raises(crew_ticket.TicketError):
        crew_wave.write_set(str(root), "t", ["T-1"], {"T-1": ["peers:"]})
    path = root / ".work" / "autopilot" / "s.json"
    data["tickets"][0]["deps"] = ["peers:a:b:T-1"]
    _write(path, json.dumps(data))
    assert crew_wave.read_set(str(root), "s") == (None, "corrupt")


def test_cli_deps_accept_a_cross_dependency(root):
    _ticket(root)

    assert crew_wave.main(["set", "--root", str(root), "--slug", "s", "--tickets", "T-1",
                           "--deps", "T-1=peers:T-0001,T-9"]) == 0
    assert crew_wave.read_set(str(root), "s")[0]["tickets"][0]["deps"] == ["peers:T-0001", "T-9"]
    assert crew_wave.main(["set", "--root", str(root), "--slug", "t", "--tickets", "T-1",
                           "--deps", "T-1=peers:a:b:T-1"]) == 1


@pytest.mark.parametrize("title,deps", [
    ("title (depends on T-0004, peers:T-0001)", ["T-0004", "peers:T-0001"]),
    ("title (depends on peers:repo.key:T-0001 and T-0004)", ["peers:repo.key:T-0001", "T-0004"]),
    ("title (depends on peers:T-0001)", ["peers:T-0001"]),
    ("title (depends on peers: T-0001)", None),
    ("title (depends on peers:a:b:T-0001)", None),
    ("title (depends on Peers:T-0001)", None),
    ("title (depends on T-0004, peers:)", None)],
    ids=["mixed", "long-then-local", "cross-only", "space", "fourth-part", "upper-channel", "empty-id"])
def test_index_row_cross_deps(title, deps):
    assert crew_wave._deps(_row("T-1", title=title), None) == deps  # pylint: disable=protected-access


def test_index_row_malformed_cross_dep_refuses_as_unknown(root):
    _ticket(root)
    _index(root, [_row("T-1", title="title (depends on peers: T-0001)")])

    got = {r["ticket"]: r for r in crew_wave.plan(str(root), tickets=["T-1"])["rows"]}["T-1"]

    assert (got["eligible"], "dependencies unknown" in got["reason"]) == (False, True)


# --- the peer claim -------------------------------------------------------------

def test_done_peer_claim_closes_the_dependency(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done"))

    got = _row_of(root)

    assert (got["eligible"], got["reason"]) == (True, "")


def test_index_row_cross_dep_done_is_eligible(root):
    _ticket(root)
    _index(root, [_row("T-1", title="title (depends on peers:T-0001)")])
    _peer_writes(root, _claim("done"))

    got = {r["ticket"]: r for r in crew_wave.plan(str(root), tickets=["T-1"])["rows"]}["T-1"]

    assert (got["eligible"], got["deps"]) == (True, ["peers:T-0001"])


def _assert_refused(root, *needles):
    got = _row_of(root)
    assert got["eligible"] is False, got
    for needle in needles:
        assert needle in got["reason"], (needle, got["reason"])
    result = crew_wave.start(str(root), "s")
    assert "T-1" not in result["plan"]["wave"]
    assert not os.path.exists(os.path.join(crew_wave.lanes_dir(str(root), "s"), "T-1.json"))
    return got["reason"]


def test_working_peer_claim_is_not_closed(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("working"))

    reason = _assert_refused(root, "peers:T-0001 is not closed", "working", "peer-sess")
    assert reason.endswith("[peer-written]")


def test_stale_working_peer_claim_is_not_closed_and_says_its_age(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("working", minutes_ago=95))

    _assert_refused(root, "is not closed", "owner unknown", "heartbeat 1h35m ago")


def test_released_peer_claim_is_not_closed(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("released"))

    _assert_refused(root, "is not closed", "released", "only done closes it")


def test_missing_peer_claim_is_unknown(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done", ticket="T-0002"))

    _assert_refused(root, "peers:T-0001 unknown", "no claim for T-0001")


def test_two_repositories_with_the_id_refuse_the_short_form(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, {**_claim("done"), **_claim("working", repo=OTHER_REPO)})

    _assert_refused(root, "unknown", "2 repositories", "peers:<repo>:T-0001")


def test_long_form_disambiguates(root):
    _wave(root, [f"peers:{PEER_REPO}:T-0001"])
    _peer_writes(root, {**_claim("done"), **_claim("working", repo=OTHER_REPO)})
    assert _row_of(root)["eligible"] is True

    crew_wave.write_set(str(root), "s", ["T-1"], {"T-1": [f"peers:{OTHER_REPO}:T-0001"]})
    assert "is not closed" in _row_of(root)["reason"]


def test_corrupt_peer_claim_is_unknown(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, {f"claims/{PEER_REPO}__T-0001.json": b"{not json"})

    _assert_refused(root, "unknown", "corrupt")


def test_absent_channel_is_unknown(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done"), channel="elsewhere")

    _assert_refused(root, "unknown", "crew-coord/peers does not exist")


def test_failed_fetch_is_unknown(root, tmp_path):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done"))
    git(root, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    _assert_refused(root, "unknown", "could not fetch crew-coord/peers")


def test_unconfigured_remote_is_unknown(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done"))
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["coord"] = {"remote": "coordhub"}
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    _assert_refused(root, "unknown", "'coordhub' (coord.remote) is not a configured remote")


@pytest.mark.parametrize("value", [{"name": "origin"}, [], "", None, 0, False],
                         ids=["object", "empty-list", "empty-string", "null", "zero", "false"])
def test_a_malformed_coord_remote_is_unknown_never_a_crash(root, value):
    """L-0633 review rounds 2 and 3: a dict in coord.remote reached the channel
    cache's key and raised TypeError; a falsey one ([], "") fell back to origin,
    where a done claim closed the dependency."""
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done"))
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["coord"] = {"remote": value}
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    _assert_refused(root, "unknown", "is not a remote name")


@pytest.mark.parametrize("value", ["malformed", ["origin"], 1],
                         ids=["string", "list", "number"])
def test_a_coord_block_that_is_not_an_object_is_unknown(root, value):
    """L-0633 review round 4: `"coord": "malformed"` read as an absent
    coord.remote, so origin's done claim closed the dependency."""
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("done"))
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["coord"] = value
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    _assert_refused(root, "unknown", "is not a remote name")


def test_a_malformed_remote_never_reads_a_valid_remotes_cached_channel(root):
    """L-0633 review round 5: repr(0) is "0", so a malformed coord.remote of 0
    hit the cache entry a binding on the remote named "0" had filled."""
    channels = {}
    git(root, "remote", "add", "0", str(root))
    crew_wave._channel_files(str(root), "peers", channels, remote="0")  # pylint: disable=protected-access
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["coord"] = {"remote": 0}
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    files, why = crew_wave._channel_files(str(root), "peers", channels)  # pylint: disable=protected-access

    assert files is None and "is not a remote name" in why


def test_coord_remote_is_read_from_config(root, hub):
    _wave(root, ["peers:T-0001"])
    git(root, "remote", "add", "coordhub", str(hub))
    _peer_writes(root, _claim("done"))
    git(root, "remote", "remove", "origin")
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["coord"] = {"remote": "coordhub"}
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    assert _row_of(root)["eligible"] is True


def test_local_dependency_refusal_comes_first_and_fetches_nothing(root, calls):
    _wave(root, ["T-9", "peers:T-0001"], rows=[_row("T-9", "approved")])

    got = _row_of(root)

    assert "dependency T-9 is not closed" in got["reason"]
    assert _channel_calls(calls) == []


def test_no_cross_dep_means_no_fetch(root, calls):
    _wave(root, ["T-9"], rows=[_row("T-9", "merged")])

    assert _row_of(root)["eligible"] is True
    assert _channel_calls(calls) == []


def test_one_fetch_per_channel_per_plan(root, calls):
    _ticket(root)
    _ticket(root, "T-2", ("other/**",))
    _index(root, [_row("T-1"), _row("T-2")])
    crew_wave.write_set(str(root), "s", ["T-1", "T-2"], {"T-1": ["peers:T-0001"], "T-2": ["peers:T-0001"]})
    _peer_writes(root, _claim("done"))
    seen = len(calls)

    result = crew_wave.plan(str(root), slug="s")

    assert result["wave"] == ["T-1", "T-2"]
    assert [c[0] for c in _channel_calls(calls[seen:])] == ["ls-remote", "fetch"]


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
    fetch_head = os.path.join(gitdir, "FETCH_HEAD")
    return {"files": found, "head": git(root, "rev-parse", "HEAD"), "refs": _refs(root),
            "fetch_head": os.path.exists(fetch_head),
            "index": os.stat(os.path.join(common, "index")).st_mtime_ns}


def test_cross_dep_check_writes_nothing(root, hub, calls):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("working"))
    before, remote, seen = _snapshot(root), _refs(hub), len(calls)

    done = crew_wave.main(["plan", "--root", str(root), "--set", "s"])

    assert done == 0
    assert _snapshot(root) == before
    assert _refs(hub) == remote
    assert [c for c in calls[seen:] if c[0] == "push"] == []
    assert [c[0] for c in _channel_calls(calls[seen:])] == ["ls-remote", "fetch"]


def test_refusal_text_is_sanitised(root):
    _wave(root, ["peers:T-0001"])
    _peer_writes(root, _claim("working", session="peer\n\u202eforged\x1b[2J"))

    reason = _row_of(root)["reason"]
    text = crew_wave.plan_text(crew_wave.plan(str(root), slug="s"))

    assert "\u202e" not in text and "\x1b" not in text and "\n" not in reason
    assert not any(line.startswith("forged") for line in text.splitlines())
    assert "peer??forged?[2J" in reason and reason.endswith("[peer-written]")
