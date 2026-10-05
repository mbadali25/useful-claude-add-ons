"""T-0029: `/crew:autopilot wave` -- crew_wave.py's settings, set file, plan,
start, lane-init, lane prompt, lane-done and collect, and the router's `wave`.

    python3 -m pytest plugin/crew/tests/test_crew_wave.py -q

A wave runs an owner-designed set of approved tickets as parallel lanes, each
an `Agent` with `isolation: worktree`. Nothing here launches an agent: the
fixtures build the main checkout and the isolated worktrees under tmp_path the
way the Step 1 spike measured Claude Code placing them
(`<main>/.claude/worktrees/agent-<id>`), and never touch the real repository
or ~/.claude. `sabotage_wave.py`'s WAVE_MUTATIONS prove these can fail.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_ticket
import crew_wave
import review_ledger
from review_fixtures import git
from scope_fixtures import approve_as_user, make_repo, make_ticket

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_wave.py")


# --- fixtures ----------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _config(root, mode="block", autopilot=None, pm=None, raw=None):
    """Write `.crew/config.json`: `raw` verbatim, else a scope block (none when
    `mode` is None) plus the given autopilot and pm blocks."""
    path = root / ".crew" / "config.json"
    if raw is not None:
        _write(path, raw)
        return
    cfg = {} if mode is None else {"scope": {"mode": mode}}
    if autopilot is not None:
        cfg["autopilot"] = autopilot
    if pm is not None:
        cfg["pm"] = pm
    _write(path, json.dumps(cfg))


def _repo(tmp_path, mode="block", **kwargs):
    root = make_repo(tmp_path, mode=None)
    with open(root / ".gitignore", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(".claude/worktrees/\n")
    git(root, "commit", "-qam", "ignore agent worktrees")
    _config(root, mode=mode, **kwargs)
    return root


def _index(root, rows):
    _write(root / ".work" / "INDEX.md", "".join(row + "\n" for row in rows))


def _row(ticket, status="approved", title="title"):
    return f"{ticket} | {status} | high | r | {title}"


def _approved(root, ticket, touch=("src/**",), files=None):
    """A ticket whose plan the user approved from their own prompt."""
    make_ticket(root, ticket, touch, files=files, activate=False)
    approve_as_user(root, ticket)


def _wave(root, rows, tickets):
    """Approve every (ticket, touch) in `tickets`, then write INDEX `rows`."""
    for ticket, touch in tickets:
        _approved(root, ticket, touch, files=[touch[0].replace("**", "x.py")])
    _index(root, rows)


def _snapshot(root):
    """Every file under the checkout (tracked or not) and the git dir's crew
    state, with bytes, plus the index mtime."""
    found = {}
    common = crew_ticket.common_dir(str(root))
    for base in (str(root), os.path.join(common, "crew")):
        for folder, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in files:
                path = os.path.join(folder, name)
                with open(path, "rb") as handle:
                    found[path] = handle.read()
    return found, os.stat(os.path.join(common, "index")).st_mtime_ns


def _cli(*args):
    return subprocess.run([sys.executable, _SCRIPT] + [str(a) for a in args],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


# --- step 2: settings ------------------------------------------------------------

def test_settings_defaults_max_lanes_to_max_dispatches(tmp_path):
    root = _repo(tmp_path, pm={"maxDispatches": 7})

    got = crew_wave.settings(str(root))

    assert (got["maxLanes"], got["reviewPolicy"], got["warnings"]) == (7, "stop", [])


def test_settings_caps_max_lanes_at_max_dispatches_with_warning(tmp_path):
    root = _repo(tmp_path, pm={"maxDispatches": 4}, autopilot={"maxLanes": 9})

    got = crew_wave.settings(str(root))

    assert (got["maxLanes"], any("capped" in w for w in got["warnings"])) == (4, True)


def test_settings_max_lanes_can_lower_max_dispatches(tmp_path):
    root = _repo(tmp_path, pm={"maxDispatches": 9}, autopilot={"maxLanes": 2})

    assert crew_wave.settings(str(root))["maxLanes"] == 2


@pytest.mark.parametrize("value", [0, -1, "3", True, 2.5, [2]])
def test_settings_invalid_max_lanes_warns_and_uses_max_dispatches(tmp_path, value):
    root = _repo(tmp_path, pm={"maxDispatches": 5}, autopilot={"maxLanes": value})

    got = crew_wave.settings(str(root))

    assert (got["maxLanes"], len(got["warnings"])) == (5, 1)


@pytest.mark.parametrize("value", ["Stop", "fix", True, None, ["stop"], "clean_only"])
def test_settings_invalid_review_policy_warns_and_uses_stop(tmp_path, value):
    root = _repo(tmp_path, autopilot={"reviewPolicy": value})

    got = crew_wave.settings(str(root))

    assert (got["reviewPolicy"], len(got["warnings"])) == ("stop", 1)


@pytest.mark.parametrize("value", ["stop", "clean-only", "fix-and-rereview"])
def test_settings_review_policy_values(tmp_path, value):
    root = _repo(tmp_path, autopilot={"reviewPolicy": value})

    assert crew_wave.settings(str(root))["reviewPolicy"] == value


# --- step 2: scope precondition ----------------------------------------------------

@pytest.mark.parametrize("config", [
    {"mode": "off"}, {"mode": "report"}, {"mode": "auto"}, {"raw": "{not json"},
    {"mode": None}, {"raw": "[1, 2]"}, {"mode": "blocky"}])
def test_scope_not_enforcing_stops_the_wave(tmp_path, config):
    root = _repo(tmp_path, **config)
    _wave(root, [_row("T-1")], [("T-1", ("src/**",))])

    ok, reason = crew_wave.scope_enforcing(str(root), ["T-1"])

    assert (ok, crew_wave.SCOPE_STOP in reason, "scope.mode" in reason,
            "block" in reason) == (False, True, True, True)


def test_scope_block_lets_the_wave_run(tmp_path):
    root = _repo(tmp_path, mode="block")
    _wave(root, [_row("T-1")], [("T-1", ("src/**",))])

    assert crew_wave.scope_enforcing(str(root), ["T-1"]) == (True, "")


def test_scope_auto_past_its_ramp_is_enforcing(tmp_path):
    root = _repo(tmp_path, mode="auto")
    _wave(root, [_row("T-1")], [("T-1", ("src/**",))])
    state = os.path.join(crew_ticket.state_dir(str(root)), "scope-tickets.json")
    _write(state, json.dumps({"tickets": [f"T-{n}" for n in range(100, 110)] + ["T-1"]}))

    assert crew_wave.scope_enforcing(str(root), ["T-1"]) == (True, "")


def _linked(root, tmp_path):
    """A linked worktree of `root` with no `.crew/` config of its own."""
    git(root, "worktree", "add", "-q", "-b", "lane", str(tmp_path / "wt"))
    return tmp_path / "wt"


def test_scope_enforcing_in_a_linked_worktree_reads_the_main_checkout_config(tmp_path):
    root = _repo(tmp_path, mode="block")
    wt = _linked(root, tmp_path)

    assert crew_wave.scope_enforcing(str(wt), ["T-1"]) == (True, "")


def test_scope_enforcing_in_a_linked_worktree_its_own_config_wins(tmp_path):
    root = _repo(tmp_path, mode="block")
    wt = _linked(root, tmp_path)
    _config(wt, mode="off")

    ok, reason = crew_wave.scope_enforcing(str(wt), ["T-1"])

    assert (ok, "scope.mode is 'off'" in reason) == (False, True)


def test_scope_stop_is_a_listed_autopilot_stop():
    assert crew_wave.SCOPE_STOP in [row["id"] for rows in crew_autopilot.stops().values()
                                    for row in rows]


# --- step 2: the set file ------------------------------------------------------------

def test_set_file_round_trips(tmp_path):
    root = _repo(tmp_path)

    crew_wave.write_set(str(root), "my-set", ["T-1", "T-2"], {"T-2": ["T-1"]})
    data, state = crew_wave.read_set(str(root), "my-set")

    assert (state, data) == ("ok", {"schema": 1, "set": "my-set", "tickets": [
        {"id": "T-1"}, {"id": "T-2", "deps": ["T-1"]}]})


@pytest.mark.parametrize("slug", ["", "My-set", "-set", "a" * 65, "a/b", "../x", "a_b", "a.b"])
def test_set_slug_outside_grammar_is_refused(tmp_path, slug):
    root = _repo(tmp_path)

    with pytest.raises(crew_wave.WaveError):
        crew_wave.write_set(str(root), slug, ["T-1"])


@pytest.mark.parametrize("text", ["{not json", "[]", '{"schema": 2, "set": "s", "tickets": []}',
                                  '{"schema": 1, "set": "s", "tickets": [{"id": "../x"}]}',
                                  '{"schema": 1, "set": "s", "tickets": "T-1"}'])
def test_unreadable_set_file_is_unknown_not_empty(tmp_path, text):
    root = _repo(tmp_path)
    _write(root / ".work" / "autopilot" / "s.json", text)

    data, state = crew_wave.read_set(str(root), "s")

    assert (data, state) == (None, "corrupt")


def test_missing_set_file_is_missing(tmp_path):
    assert crew_wave.read_set(str(_repo(tmp_path)), "s") == (None, "missing")


def test_set_cli_writes_the_set(tmp_path):
    root = _repo(tmp_path)

    done = _cli("set", "--root", root, "--slug", "s", "--tickets", "T-1", "T-2",
                "--deps", "T-2=T-1", "--deps", "T-1=none")

    assert (done.returncode, crew_wave.read_set(str(root), "s")[0]["tickets"]) == (
        0, [{"id": "T-1", "deps": []}, {"id": "T-2", "deps": ["T-1"]}])


@pytest.mark.parametrize("deps", ["T-1=", "T-1=,", "T-1= ", "T-1=T-2,", "T-1=,T-2", "T-1=T-2,,T-3", "T-1"],
                         ids=["empty", "comma", "space", "trailing", "leading", "double", "no-equals"])
def test_set_cli_refuses_a_dependency_list_that_is_not_none_or_ids(tmp_path, deps):
    # Group review r5 (rush g0): `T-1=` parsed as no dependencies and skipped the unknown refusal.
    root = _repo(tmp_path)

    done = _cli("set", "--root", root, "--slug", "s", "--tickets", "T-1", "--deps", deps)

    assert (done.returncode != 0, crew_wave.read_set(str(root), "s")) == (True, (None, "missing"))


# --- step 3: plan ------------------------------------------------------------------

def _set(root, slug, tickets, deps=None):
    crew_wave.write_set(str(root), slug, tickets,
                        deps if deps is not None else {t: [] for t in tickets})


def _by_ticket(result):
    return {row["ticket"]: row for row in result["rows"]}


@pytest.mark.parametrize("how", ["never", "stale"])
def test_plan_refuses_ticket_without_current_approval(tmp_path, how):
    root = _repo(tmp_path)
    if how == "never":
        make_ticket(root, "T-1", activate=False)
    else:
        _approved(root, "T-1")
        spec = root / ".work" / "tickets" / "T-1" / "spec.md"
        spec.write_text(spec.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    _index(root, [_row("T-1")])
    _set(root, "s", ["T-1"])

    got = _by_ticket(crew_wave.plan(str(root), slug="s"))["T-1"]

    assert (got["eligible"], "approv" in got["reason"]) == (False, True)


def test_plan_refuses_direction_status_ticket(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1", "direction")], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    got = _by_ticket(crew_wave.plan(str(root), slug="s"))["T-1"]

    assert (got["eligible"], "direction" in got["reason"]) == (False, True)


@pytest.mark.parametrize("status", ["gibberish", "needs-owner", ""])
def test_plan_refuses_a_status_it_does_not_recognise(tmp_path, status):
    # Codex review round 2 (rush g0): any word but closed/direction read as open.
    root = _repo(tmp_path)
    _wave(root, [_row("T-1", status)], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    got = _by_ticket(crew_wave.plan(str(root), slug="s"))["T-1"]

    assert (got["eligible"], "cannot be told" in got["reason"]) == (False, True)


@pytest.mark.parametrize("status", ["done", "merged", "closed"])
def test_plan_refuses_closed_ticket(tmp_path, status):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1", status)], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    got = _by_ticket(crew_wave.plan(str(root), slug="s"))["T-1"]

    assert (got["eligible"], "closed" in got["reason"]) == (False, True)


def test_plan_refuses_ticket_with_no_index_row(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-9")], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    got = _by_ticket(crew_wave.plan(str(root), slug="s"))["T-1"]

    assert (got["eligible"], "INDEX" in got["reason"]) == (False, True)


def test_plan_refuses_open_dependency(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", ("other/**",))])
    _set(root, "s", ["T-1", "T-2"], {"T-1": [], "T-2": ["T-1"]})

    got = _by_ticket(crew_wave.plan(str(root), slug="s"))

    assert (got["T-1"]["eligible"], got["T-2"]["eligible"],
            "T-1 is not closed" in got["T-2"]["reason"]) == (True, False, True)


@pytest.mark.parametrize("title", ["title", "title (depends on )", "title (depends on the router)",
                                   "title (depends on T-1 or T-3)"])
def test_plan_refuses_unknown_dependencies(tmp_path, title):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1", title=title), _row("T-3", "merged")], [("T-1", ("src/**",))])

    got = _by_ticket(crew_wave.plan(str(root), tickets=["T-1"]))["T-1"]

    assert (got["eligible"], "unknown" in got["reason"]) == (False, True)


def test_plan_reads_closed_dependencies_from_the_index_row(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1", "merged"), _row("T-3", "done"),
                 _row("T-2", title="title (depends on T-1, T-3)")],
          [("T-2", ("src/**",))])

    got = _by_ticket(crew_wave.plan(str(root), tickets=["T-2"]))["T-2"]

    assert (got["eligible"], got["deps"]) == (True, ["T-1", "T-3"])


@pytest.mark.parametrize("second", [("src/app.py",), ("src/*.py",), ("src/**",), ("src",),
                                    ("src/lib/**",)])
def test_plan_refuses_overlapping_touch(tmp_path, second):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", second)])
    _set(root, "s", ["T-1", "T-2"])

    got = crew_wave.plan(str(root), slug="s")

    assert (got["wave"], [t for t, _ in got["later"]],
            "overlaps T-1" in _by_ticket(got)["T-2"]["reason"]) == (["T-1"], ["T-2"], True)


def test_plan_runs_disjoint_touch_together(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", ("other/**",))])
    _set(root, "s", ["T-1", "T-2"])

    assert crew_wave.plan(str(root), slug="s")["wave"] == ["T-1", "T-2"]


def test_plan_refuses_lanes_over_max(tmp_path):
    root = _repo(tmp_path, pm={"maxDispatches": 1})
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", ("other/**",))])
    _set(root, "s", ["T-1", "T-2"])

    got = crew_wave.plan(str(root), slug="s")

    assert (got["wave"], "maxLanes" in _by_ticket(got)["T-2"]["reason"]) == (["T-1"], True)


def _origin_version(root, version):
    _write(root / "plugin" / "crew" / ".claude-plugin" / "plugin.json",
           json.dumps({"name": "crew", "version": version}))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "plugin")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def test_plan_orders_landing_by_provisional_version(tmp_path):
    root = _repo(tmp_path)
    _origin_version(root, "1.0.50")
    _wave(root, [_row("T-1"), _row("T-2"), _row("T-3")],
          [("T-1", ("plugin/crew/a/**",)), ("T-2", ("other/**",)), ("T-3", ("plugin/crew/b/**",))])
    _set(root, "s", ["T-1", "T-2", "T-3"])

    got = crew_wave.plan(str(root), slug="s")

    assert got["land"] == [["T-1", "1.0.51"], ["T-2", "-"], ["T-3", "1.0.52"]]


def _head_version(root, version):
    """Commit crew's plugin.json at `version` on HEAD only; origin/main stays."""
    _write(root / "plugin" / "crew" / ".claude-plugin" / "plugin.json",
           json.dumps({"name": "crew", "version": version}))
    git(root, "commit", "-qam", "head version")


def test_plan_never_lowers_the_checkouts_own_version(tmp_path):
    # Group review (rush g0): run from a release branch whose HEAD declares more than
    # origin/main, the lanes were told to set main's next patch - a downgrade.
    root = _repo(tmp_path)
    _origin_version(root, "1.1.3")
    _head_version(root, "1.1.6")
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("plugin/crew/a/**",)), ("T-2", ("plugin/crew/b/**",))])
    _set(root, "s", ["T-1", "T-2"])

    assert crew_wave.plan(str(root), slug="s")["land"] == [["T-1", "1.1.7"], ["T-2", "1.1.8"]]


def test_plan_bumps_from_origin_main_when_it_is_ahead(tmp_path):
    root = _repo(tmp_path)
    _origin_version(root, "1.0.50")
    _head_version(root, "1.0.70")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "reset", "-q", "--hard", "HEAD~1")
    _wave(root, [_row("T-1")], [("T-1", ("plugin/crew/**",))])
    _set(root, "s", ["T-1"])

    assert crew_wave.plan(str(root), slug="s")["land"] == [["T-1", "1.0.71"]]


def test_plan_landing_version_unknown_when_head_has_none(tmp_path):
    root = _repo(tmp_path)
    _origin_version(root, "1.0.50")
    git(root, "rm", "-q", "plugin/crew/.claude-plugin/plugin.json")
    git(root, "commit", "-qm", "no plugin.json on HEAD")
    _wave(root, [_row("T-1")], [("T-1", ("plugin/crew/**",))])
    _set(root, "s", ["T-1"])

    assert crew_wave.plan(str(root), slug="s")["land"] == [["T-1", "unknown"]]


@pytest.mark.parametrize("version", ["1.1.6", 116, None, ["1.1.6"]], ids=["string", "number", "null", "list"])
def test_plan_landing_version_unknown_when_a_version_is_not_a_string(tmp_path, version):
    # Group review r2 (rush g0): a JSON number reached re.fullmatch and raised TypeError.
    root = _repo(tmp_path)
    _write(root / "plugin" / "crew" / ".claude-plugin" / "plugin.json",
           json.dumps({"name": "crew", "version": version}))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "plugin")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _wave(root, [_row("T-1")], [("T-1", ("plugin/crew/**",))])
    _set(root, "s", ["T-1"])

    expected = "1.1.7" if version == "1.1.6" else "unknown"
    assert crew_wave.plan(str(root), slug="s")["land"] == [["T-1", expected]]


def test_plan_landing_version_unknown_without_origin(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1")], [("T-1", ("plugin/crew/**",))])
    _set(root, "s", ["T-1"])

    assert crew_wave.plan(str(root), slug="s")["land"] == [["T-1", "unknown"]]


def test_plan_writes_nothing(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", ("src/app.py",))])
    _set(root, "s", ["T-1", "T-2"])
    before = _snapshot(root)

    done = _cli("plan", "--root", root, "--set", "s")

    assert (done.returncode, _snapshot(root) == before) == (0, True)


def test_plan_prints_the_scope_stop(tmp_path):
    root = _repo(tmp_path, mode="report")
    _wave(root, [_row("T-1")], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    done = _cli("plan", "--root", root, "--set", "s")

    assert (done.returncode, f"stop: {crew_wave.SCOPE_STOP}" in done.stdout) == (1, True)


def test_plan_text_lists_rows_wave_and_land_order(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", ("src/app.py",))])
    _set(root, "s", ["T-1", "T-2"])

    lines = _cli("plan", "--root", root, "--set", "s").stdout.splitlines()

    assert (lines[0], lines[1].startswith("T-2 refused: "), lines[2], lines[3].startswith("later: T-2"),
            lines[4]) == ("T-1 eligible", True, "wave 1: T-1", True, "land order: T-1 -")


# --- step 4: start, lane-init, relaunch ---------------------------------------------------

def _started(tmp_path, tickets=(("T-1", ("src/**",)), ("T-2", ("other/**",))), **kwargs):
    root = _repo(tmp_path, **kwargs)
    _wave(root, [_row(t) for t, _ in tickets], list(tickets))
    _set(root, "s", [t for t, _ in tickets])
    crew_wave.start(str(root), "s")
    return root


def _isolated(root, name="agent-a1", where=None):
    """A worktree the way `Agent` `isolation: worktree` places one (spike)."""
    path = where or (root / ".claude" / "worktrees" / name)
    git(root, "worktree", "add", "-q", "-b", f"worktree-{name}", str(path))
    return path


def _lane(root, ticket, slug="s"):
    return crew_wave.read_lane(str(root), slug, ticket)


def _set_lane(root, ticket, **fields):
    """Rewrite a lane file; a state only lane-init reaches gets lane-init's branch
    and a worktree when the test names none."""
    lane, _ = _lane(root, ticket)
    if fields.get("state") in crew_wave.SET_UP:
        fields.setdefault("branch", crew_wave.branch_for(ticket))
        if lane.get("worktree") is None:
            fields.setdefault("worktree", str(root / ".claude" / "worktrees" / ticket))
    lane.update(fields)
    crew_wave.write_lane(str(root), "s", ticket, lane)


def _head(root):
    return git(root, "rev-parse", "HEAD")


def _rounds(root, ticket="T-1"):
    return review_ledger.status(str(root), ticket).get("rounds_used", 0)


def test_start_writes_pending_lane_files_with_base_commit(tmp_path):
    root = _started(tmp_path)

    got = [_lane(root, t)[0] for t in ("T-1", "T-2")]

    assert [(lane["state"], lane["base"], lane["worktree"]) for lane in got] == [
        ("pending", _head(root), None)] * 2


def test_start_prints_isolated_agent_launch_per_lane(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1"), _row("T-2")], [("T-1", ("src/**",)), ("T-2", ("other/**",))])
    _set(root, "s", ["T-1", "T-2"])

    out = _cli("start", "--root", root, "--set", "s").stdout

    launches = [line for line in out.splitlines() if line.startswith("launch ")]
    assert (len(launches), all("isolation: worktree" in line for line in launches),
            out.count("isolation"), all("lane-prompt" in line for line in launches)) == (
        2, True, 2, True)


def test_start_refuses_when_scope_not_enforcing(tmp_path):
    root = _repo(tmp_path, mode="report")
    _wave(root, [_row("T-1")], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    done = _cli("start", "--root", root, "--set", "s")

    assert (done.returncode, crew_wave.SCOPE_STOP in done.stdout,
            _lane(root, "T-1")[1]) == (1, True, "missing")


def test_lane_init_refuses_main_checkout(tmp_path):
    root = _started(tmp_path)

    ok, reason = crew_wave.lane_init(str(root), str(root), "s", "T-1")

    assert (ok, "main checkout" in reason, _lane(root, "T-1")[0]["state"]) == (
        False, True, "pending")


def test_lane_init_refuses_worktree_outside_claude_worktrees(tmp_path):
    root = _started(tmp_path)
    elsewhere = _isolated(root, "x", where=tmp_path / "elsewhere")

    ok, reason = crew_wave.lane_init(str(elsewhere), str(root), "s", "T-1")

    assert (ok, ".claude/worktrees" in reason) == (False, True)


def test_lane_init_refuses_worktree_another_lane_names(tmp_path):
    root = _started(tmp_path)
    wt = _isolated(root)
    _set_lane(root, "T-2", worktree=os.path.realpath(str(wt)), state="running")

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    assert (ok, "T-2" in reason) == (False, True)


def test_lane_init_refuses_branch_checked_out_elsewhere(tmp_path):
    root = _started(tmp_path)
    git(root, "worktree", "add", "-q", "-b", "T-1-wave", str(tmp_path / "held"))
    wt = _isolated(root)

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    assert (ok, "T-1-wave" in reason, "held" in reason) == (False, True, True)


def test_lane_init_copies_ticket_folder_and_config_byte_identical_and_activates(tmp_path):
    root = _started(tmp_path)
    wt = _isolated(root)

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    same = [(root / rel).read_bytes() == (wt / rel).read_bytes() for rel in (
        ".work/tickets/T-1/spec.md", ".work/tickets/T-1/plan.md", ".crew/config.json")]
    lane = _lane(root, "T-1")[0]
    assert (ok, reason, same, crew_ticket.active_ticket(str(wt))[0], git(wt, "branch", "--show-current"),
            lane["state"], lane["worktree"]) == (
        True, "", [True] * 3, "T-1", "T-1-wave", "running", os.path.realpath(str(wt)))


def test_lane_init_copies_nested_ticket_files(tmp_path):
    # Codex review round 2 (rush g0): only the folder's top-level files were copied.
    root = _started(tmp_path)
    _write(root / ".work" / "tickets" / "T-1" / "notes" / "deep.md", "nested\n")
    wt = _isolated(root)

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    rel = ".work/tickets/T-1/notes/deep.md"
    assert (ok, reason, (wt / rel).read_bytes() == (root / rel).read_bytes()) == (True, "", True)


def test_lane_init_rerun_never_overwrites_the_lanes_own_edits(tmp_path):
    # Codex review round 3 (rush g0): a second lane-init copied the main checkout's
    # ticket files over the lane's edited ones.
    root = _started(tmp_path)
    wt = _isolated(root)
    assert crew_wave.lane_init(str(wt), str(root), "s", "T-1")[0] is True
    _write(wt / ".work" / "tickets" / "T-1" / "plan.md", "the lane's edit\n")

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    assert (ok, "nothing overwritten" in reason,
            (wt / ".work/tickets/T-1/plan.md").read_text(encoding="utf-8")) == (
        False, True, "the lane's edit\n")


def test_start_refuses_a_corrupt_start_record_and_leaves_it(tmp_path):
    # Codex review round 3 (rush g0): a corrupt start.json was rebuilt from nothing,
    # dropping its lanes from collect's report.
    root = _started(tmp_path)
    path = crew_wave.start_path(str(root), "s")
    _write(path, "{broken")

    got = _cli("start", "--root", root, "--set", "s")

    with open(path, encoding="utf-8") as handle:
        kept = handle.read()
    assert (got.returncode, "unreadable" in got.stderr, kept) == (1, True, "{broken")


def test_lane_init_checks_out_an_existing_branch(tmp_path):
    root = _started(tmp_path)
    git(root, "branch", "T-1-wave")
    wt = _isolated(root)

    ok, _ = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    assert (ok, git(wt, "branch", "--show-current")) == (True, "T-1-wave")


def test_lane_init_refuses_when_not_accepted_in_worktree(tmp_path):
    root = _started(tmp_path)
    spec = root / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\nedited after approval\n", encoding="utf-8")
    wt = _isolated(root)

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    assert (ok, "stale" in reason, crew_ticket.active_ticket(str(wt))[0]) == (False, True, None)


@pytest.mark.parametrize("mode", ["off", "report", None])
def test_lane_init_refuses_when_worktree_scope_not_block(tmp_path, mode):
    root = _started(tmp_path)
    if mode is None:
        os.remove(root / ".crew" / "config.json")
    else:
        _config(root, mode=mode)
    wt = _isolated(root)

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    assert (ok, "block" in reason, crew_ticket.active_ticket(str(wt))[0]) == (False, True, None)


def test_lane_init_refuses_a_ticket_not_in_the_started_wave(tmp_path):
    root = _started(tmp_path)
    wt = _isolated(root)

    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-7")

    assert (ok, "lane file" in reason) == (False, True)


def _gone(root, wt):
    """The owner removed a crashed lane's worktree; its branch stays."""
    git(root, "worktree", "remove", "--force", str(wt))


def test_relaunch_resumes_reserved_round_without_new_reservation(tmp_path):
    root = _started(tmp_path)
    wt = _isolated(root)
    crew_wave.lane_init(str(wt), str(root), "s", "T-1")
    review_ledger.reserve(str(root), "T-1", "claude")
    _gone(root, wt)

    out = _cli("start", "--root", root, "--set", "s").stdout

    launch = [line for line in out.splitlines() if line.startswith("launch T-1")]
    assert (len(launch), "--resume-round 1" in launch[0], _rounds(root)) == (1, True, 1)


def test_relaunch_with_an_unreadable_ledger_stops_and_reserves_nothing(tmp_path):
    # The neighbour of collect's case: an unreadable ledger is not "no round reserved".
    root = _started(tmp_path)
    _write(review_ledger.ledger_path(str(root), "T-1"), "{not json")

    got = _cli("start", "--root", root, "--set", "s")

    assert (got.returncode, "launch T-1" in got.stdout, "unreadable" in got.stderr) == (1, False, True)


def test_relaunch_never_restarts_a_started_lane_whose_file_is_missing(tmp_path):
    # Codex review round 6 (rush g0): a started lane's missing file was rewritten as pending.
    root = _started(tmp_path)
    os.remove(crew_wave.lane_path(str(root), "s", "T-1"))

    out = _cli("start", "--root", root, "--set", "s").stdout

    assert ("T-1 unknown" in out, any(l.startswith("launch T-1") for l in out.splitlines()),
            os.path.exists(crew_wave.lane_path(str(root), "s", "T-1"))) == (True, False, False)


def test_collect_keeps_a_started_lane_dropped_from_the_set_file(tmp_path):
    # Codex review round 6 (rush g0): rewriting the set hid a launched lane from the batch.
    root = _started(tmp_path)
    crew_wave.write_set(str(root), "s", ["T-1"])

    assert "T-2" in {row["ticket"] for row in _collect(root)["lanes"]}


def test_collect_reports_an_invalid_started_lane_id_and_keeps_the_valid_lanes(tmp_path):
    # Coordinator review of round 6 (rush g0): an invalid id in start.json aborted collect.
    root = _started(tmp_path)
    path = crew_wave.start_path(str(root), "s")
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    record["lanes"] += ["../oops", "T-9\n"]  # a trailing newline passes check_ticket's `$`
    text = json.dumps(record)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    report = _collect(root)

    assert ({row["ticket"] for row in report["lanes"]},
            any("../oops" in problem for problem in report["problems"]),
            any("../oops" in line for line in report["approvals"]),
            any("T-9" in problem for problem in report["problems"]),
            any("T-9" in line for line in report["approvals"])) == ({"T-1", "T-2"}, True, False, True, False)


def test_a_set_file_id_with_a_trailing_newline_is_refused_not_printed(tmp_path):
    # Codex review of the fix range, round 4 (rush g0): `T-9\n` in both the set file and
    # start.json skipped validation and reached `/crew:approve T-9\n`.
    root = _started(tmp_path)
    path = crew_wave.set_path(str(root), "s")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["tickets"].append({"id": "T-9\n"})
    text = json.dumps(data)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    with pytest.raises(crew_wave.WaveError, match="corrupt"):
        _collect(root)


def test_relaunch_skips_terminal_lanes(tmp_path):
    root = _started(tmp_path)
    _set_lane(root, "T-1", state="running")
    crew_wave.lane_done(str(root), "s", "T-1", "clean", "done checks passed")

    out = _cli("start", "--root", root, "--set", "s").stdout

    assert (any(line.startswith("launch T-1") for line in out.splitlines()),
            "T-1 skipped: clean" in out) == (False, True)


def test_relaunch_refuses_lane_whose_old_worktree_holds_the_branch(tmp_path):
    root = _started(tmp_path)
    wt = _isolated(root)
    crew_wave.lane_init(str(wt), str(root), "s", "T-1")

    out = _cli("start", "--root", root, "--set", "s").stdout

    assert (any(line.startswith("launch T-1") for line in out.splitlines()),
            os.path.realpath(str(wt)) in out) == (False, True)


def test_relaunch_blocks_an_unreadable_lane_file(tmp_path):
    root = _started(tmp_path)
    _write(root / ".work" / "autopilot" / "s" / "lanes" / "T-1.json", "{broken")

    out = _cli("start", "--root", root, "--set", "s").stdout

    assert (any(line.startswith("launch T-1") for line in out.splitlines()),
            "T-1 unknown" in out) == (False, True)


@pytest.mark.parametrize("step", ["pending", "initialised", "activated", "reserved", "recorded"])
def test_relaunch_after_crash_at_each_step(tmp_path, step):
    root = _started(tmp_path)
    if step != "pending":
        wt = _isolated(root)
        crew_wave.lane_init(str(wt), str(root), "s", "T-1")
        if step == "initialised":
            _set_lane(root, "T-1", step="initialised")
        if step in ("reserved", "recorded"):
            review_ledger.reserve(str(root), "T-1", "claude")
        if step == "recorded":
            review_ledger.record(str(root), "T-1", 1, {"provider": "claude", "verdict": "FINDINGS"})
        _gone(root, wt)
    before = _rounds(root)

    out = _cli("start", "--root", root, "--set", "s").stdout

    launch = [line for line in out.splitlines() if line.startswith("launch T-1")]
    assert (len(launch), "--resume-round" in launch[0], _rounds(root)) == (
        1, step == "reserved", before)


# --- step 5: lane-prompt and lane-done -----------------------------------------------------

FORBIDDEN = ("crew_ticket.py approve", "--admin", "gh pr merge", "CLAUDE_PLUGIN_ROOT")
ABBREVIATIONS = ("--a", "--ac", "--acc", "--acce", "--accep", "--accept",
                 "--rej", "--reje", "--rejec", "--reject")


def _prompt(root, **kwargs):
    return crew_wave.lane_prompt(str(root), "s", "T-1", **kwargs)


def test_lane_prompt_names_every_step_in_order(tmp_path):
    text = _prompt(_started(tmp_path))

    marks = ["crew_wave.py lane-init", "/crew:implement T-1", "plugin/crew/.claude-plugin/plugin.json",
             "crew_refresh_check.py", "/crew:review T-1",
             "completion_audit.py --check --ticket T-1 --root .", "crew_wave.py lane-done"]
    at = [text.find(mark) for mark in marks]
    assert (min(at) >= 0, at == sorted(at)) == (True, True)


def test_lane_prompt_bumps_every_version_place_and_reviews_once(tmp_path):
    # Codex review (rush g0): PLUGINS.md's version claim was missing, and step 2's
    # /crew:implement ends in its own /crew:review, spending a round before step 5.
    root = _started(tmp_path)
    _set_lane(root, "T-1", version="1.0.61")
    text = _prompt(root)

    step3 = next(line for line in text.splitlines() if line.startswith("3."))
    step2 = next(line for line in text.splitlines() if line.startswith("2."))
    assert ("plugin/PLUGINS.md" in step3, "not including" in step2) == (True, True)


def test_lane_prompt_review_stops_at_the_verdict_and_reruns_review_after_a_fix(tmp_path):
    # Codex review round 5 (rush g0): /crew:review's after-verdict steps (fix, re-run,
    # accept, ask) were not excluded, and fix-and-rereview never sent the lane back to step 5.
    text = _prompt(_started(tmp_path, autopilot={"reviewPolicy": "fix-and-rereview"}))

    assert ("up to its recorded verdict only" in text, "then step 5 for the next round" in text,
            "INCOMPLETE: step 8 with --state findings" in text) == (True, True, True)


def test_lane_prompt_unknown_version_stops_a_crew_change_as_a_question(tmp_path):
    # Codex review round 4 (rush g0): an unknown version let a crew change reach clean unbumped.
    root = _started(tmp_path)
    _set_lane(root, "T-1", version=crew_wave.UNKNOWN)

    step3 = next(line for line in _prompt(root).splitlines() if line.startswith("3."))

    assert ("--state question" in step3, "never reach clean unbumped" in step3) == (True, True)


def test_lane_prompt_stop_policy_clean_writes_the_question_it_reports(tmp_path):
    # Codex review round 4 (rush g0): `question` was reported with no questions.md item.
    text = _prompt(_started(tmp_path, autopilot={"reviewPolicy": "stop"}))

    assert "write the question `Run /crew:done?`" in text


def test_lane_prompt_starts_with_lane_init(tmp_path):
    steps = [line for line in _prompt(_started(tmp_path)).splitlines() if line[:2] == "1."]

    assert (len(steps), "crew_wave.py lane-init" in steps[0]) == (1, True)


@pytest.mark.parametrize("policy", ["stop", "clean-only", "fix-and-rereview"])
def test_lane_prompt_contains_no_forbidden_command(tmp_path, policy):
    text = _prompt(_started(tmp_path, autopilot={"reviewPolicy": policy}), resume_round=2)

    flags = {word.rstrip(".,;:)`\"'") for word in text.split() if word.startswith("--")}
    assert ([f for f in FORBIDDEN if f in text], sorted(flags & set(ABBREVIATIONS))) == ([], [])


def test_lane_prompt_uses_absolute_script_paths(tmp_path):
    text = _prompt(_started(tmp_path))

    words = [word.strip("`'\"(),:;") for word in text.split()]
    named = [word for word in words if word.endswith(".py")]
    assert (named != [], all(os.path.isabs(word) and os.path.isfile(word) for word in named)) == (
        True, True)


def test_lane_prompt_review_policy_variants(tmp_path):
    texts = {policy: _prompt(_started(tmp_path / policy, autopilot={"reviewPolicy": policy}))
             for policy in ("stop", "clean-only", "fix-and-rereview")}

    marks = {policy: f"autopilot.reviewPolicy {policy}:" for policy in texts}
    assert ([marks[p] in texts[p] for p in texts],
            [sorted(p for p in marks if marks[p] in texts[q]) for q in texts]) == (
        [True] * 3, [["stop"], ["clean-only"], ["fix-and-rereview"]])


def test_lane_prompt_resume_round_names_the_round(tmp_path):
    text = _prompt(_started(tmp_path), resume_round=2)

    assert ("round 2 is already reserved" in text, "--round 2" in text) == (True, True)


def test_lane_prompt_names_the_version(tmp_path):
    root = _repo(tmp_path)
    _origin_version(root, "1.0.60")
    _wave(root, [_row("T-1")], [("T-1", ("plugin/crew/**",))])
    _set(root, "s", ["T-1"])
    crew_wave.start(str(root), "s")

    assert "1.0.61" in _prompt(root)


def test_lane_prompt_refuses_a_lane_that_was_not_started(tmp_path):
    root = _repo(tmp_path)

    with pytest.raises(crew_wave.WaveError):
        _prompt(root)


@pytest.mark.parametrize("state", ["done", "merged", "running", "", "CLEAN"])
def test_lane_done_refuses_state_outside_the_four(tmp_path, state):
    root = _started(tmp_path)

    done = _cli("lane-done", "--main", root, "--set", "s", "--ticket", "T-1", "--state", state)

    assert (done.returncode != 0, _lane(root, "T-1")[0]["state"]) == (True, "pending")


@pytest.mark.parametrize("state", ["clean", "findings", "question", "failed"])
def test_lane_done_writes_the_state(tmp_path, state):
    root = _started(tmp_path)
    _set_lane(root, "T-1", state="running")

    done = _cli("lane-done", "--main", root, "--set", "s", "--ticket", "T-1", "--state", state,
                "--reason", "why")

    assert (done.returncode, _lane(root, "T-1")[0]["state"], _lane(root, "T-1")[0]["reason"]) == (
        0, state, "why")


# --- step 6: collect -------------------------------------------------------------------------

QUESTIONS = """## Q1: which store keeps the lane state?
Research: crew:explorer found two stores.
### Option {first}
Cost: {first_cost}
### Option {second}
Cost: {second_cost}
"""


def _collect(root):
    return crew_wave.collect(str(root), "s")


def _state_of(result, ticket):
    return {row["ticket"]: row for row in result["lanes"]}[ticket]


def test_collect_missing_lane_file_reads_unknown(tmp_path):
    root = _started(tmp_path)
    os.remove(root / ".work" / "autopilot" / "s" / "lanes" / "T-1.json")

    got = _state_of(_collect(root), "T-1")

    assert (got["state"], "missing" in got["reason"]) == ("unknown", True)


@pytest.mark.parametrize("text", ["{broken", "[]", '{"state": "CLEAN"}', '{"state": null}',
                                  '{"state": "clean"}'])
def test_collect_corrupt_lane_file_reads_unknown(tmp_path, text):
    root = _started(tmp_path)
    _write(root / ".work" / "autopilot" / "s" / "lanes" / "T-1.json", text)

    assert _state_of(_collect(root), "T-1")["state"] == "unknown"


@pytest.mark.parametrize("drop, value", [("set", None), ("ticket", None), ("version", None),
                                         ("set", "other"), ("ticket", "T-2"), ("version", 116),
                                         ("worktree", 7), ("base", None), ("base", ""),
                                         ("branch", None), ("branch", ""), ("worktree", "null")],
                         ids=["no-set", "no-ticket", "no-version", "other-set", "other-ticket",
                              "number-version", "number-worktree", "no-base", "empty-base",
                              "no-branch", "empty-branch", "null-worktree-not-removed"])
def test_collect_incomplete_clean_lane_file_reads_unknown(tmp_path, drop, value):
    # Group review r3 (rush g0): `{"state": "clean"}` alone was collected as a clean lane.
    root = _started(tmp_path)
    lane, _ = _lane(root, "T-1")
    lane.update(state="clean", worktree="/w", branch="T-1-wave")
    if value is None:
        del lane[drop]
    else:
        lane[drop] = None if value == "null" else value
    _write(root / ".work" / "autopilot" / "s" / "lanes" / "T-1.json", json.dumps(lane))

    got = _collect(root)

    assert (_state_of(got, "T-1")["state"], [t for t, _ in got["land"]]) == ("unknown", [])


@pytest.mark.parametrize("fields", [{"worktree": "/w"}, {"worktree": None, "removed": True}],
                         ids=["worktree", "removed"])
def test_collect_complete_clean_lane_file_reads_clean(tmp_path, fields):
    root = _started(tmp_path)
    _set_lane(root, "T-1", state="clean", branch="T-1-wave", **fields)

    assert _state_of(_collect(root), "T-1")["state"] == "clean"


def test_a_pending_lane_file_with_no_base_is_corrupt(tmp_path):
    # Group review r6: lane-init read lane["base"] from a pending file that had none.
    root = _started(tmp_path)
    lane, _ = _lane(root, "T-1")
    del lane["base"]
    _write(root / ".work" / "autopilot" / "s" / "lanes" / "T-1.json", json.dumps(lane))

    assert _lane(root, "T-1") == (None, "corrupt")


@pytest.mark.parametrize("state", ["clean", "findings", "question"])
def test_lane_done_refuses_a_set_up_state_for_a_lane_lane_init_never_set_up(tmp_path, state):
    root = _started(tmp_path)

    done = _cli("lane-done", "--main", root, "--set", "s", "--ticket", "T-1", "--state", state,
                "--reason", "why")

    assert (done.returncode, _lane(root, "T-1")[0]["state"]) == (1, "pending")


def test_a_failed_lane_needs_no_branch(tmp_path):
    root = _started(tmp_path)
    crew_wave.lane_done(str(root), "s", "T-1", "failed", "lane-init refused")

    assert _state_of(_collect(root), "T-1")["state"] == "failed"


def test_collect_unknown_when_the_wave_was_never_started(tmp_path):
    root = _repo(tmp_path)
    _wave(root, [_row("T-1")], [("T-1", ("src/**",))])
    _set(root, "s", ["T-1"])

    assert _state_of(_collect(root), "T-1")["state"] == "unknown"


@pytest.mark.parametrize("order", ["recommended-first", "recommended-second"])
def test_collect_lists_questions_recommendation_first(tmp_path, order):
    root = _started(tmp_path)
    wt = tmp_path / "lane-wt"
    rec, other = ("A (recommended): one file", "keep it in one file"), ("B: two files", "two files")
    first, second = (rec, other) if order == "recommended-first" else (other, rec)
    _write(wt / ".work" / "tickets" / "T-1" / "questions.md", QUESTIONS.format(
        first=first[0], first_cost=first[1], second=second[0], second_cost=second[1]))
    _set_lane(root, "T-1", state="question", worktree=str(wt), reason="Q1 open")

    text = crew_wave.collect_text(_collect(root))

    head = text.index("Questions (1):")
    assert (text.index("(recommended)", head) < text.index("Option B", head),
            "which store keeps the lane state?" in text) == (True, True)


def test_collect_question_file_unreadable_is_unknown(tmp_path):
    root = _started(tmp_path)
    _set_lane(root, "T-1", state="question", worktree=str(tmp_path / "gone"))

    text = crew_wave.collect_text(_collect(root))

    assert "T-1: questions.md unknown" in text


@pytest.mark.parametrize("unapproved,lines", [
    (["T-2"], ["/crew:approve T-2"]),
    (["T-2", "T-3"], ["/crew:approve T-2 T-3", "/crew:approve --confirm"])])
def test_collect_prints_exact_approve_lines(tmp_path, unapproved, lines):
    root = _repo(tmp_path)
    _approved(root, "T-1")
    for ticket in unapproved:
        make_ticket(root, ticket, ("other/**",), files=["other/x.py"], activate=False)
    ids = ["T-1"] + unapproved
    _index(root, [_row(t) for t in ids])
    _set(root, "s", ids)
    crew_wave.start(str(root), "s")

    got = _collect(root)

    assert got["approvals"] == lines


def test_collect_prints_land_order_for_clean_lanes_only(tmp_path):
    root = _started(tmp_path)
    _set_lane(root, "T-1", state="clean", version="1.0.61")
    _set_lane(root, "T-2", state="findings", version="1.0.62")

    got = _collect(root)

    assert got["land"] == [["T-1", "1.0.61"]]


def test_collect_flags_owner_accepted_receipt_written_during_lane(tmp_path):
    root = _started(tmp_path)
    _write(review_ledger.ledger_path(str(root), "T-1"), json.dumps({
        "ticket": "T-1", "budget": 2, "refused": [], "state": "ACCEPTED",
        "rounds": [{"round": 1, "status": "completed", "verdict": "FINDINGS"}],
        "receipt": {"kind": "owner-accepted", "round": 1, "verdict": "FINDINGS",
                    "accepted_by": "someone", "accepted_at": "2026-09-27T00:00:00+00:00"}}))
    _set_lane(root, "T-1", state="clean")

    got = _state_of(_collect(root), "T-1")

    assert (got["state"], "accepted without the owner" in got["reason"]) == ("failed", True)


def test_collect_unreadable_review_ledger_reads_unknown_never_clean(tmp_path):
    # Codex review (rush g0): a corrupt ledger's status has no receipt, which read as
    # "nothing accepted", so a lane file saying clean stayed clean and was landed.
    root = _started(tmp_path)
    _write(review_ledger.ledger_path(str(root), "T-1"), "{not json")
    _set_lane(root, "T-1", state="clean", version="1.0.61")

    got = _collect(root)

    assert (_state_of(got, "T-1")["state"], got["land"]) == ("unknown", [])


def test_collect_text_sections_in_order(tmp_path):
    root = _started(tmp_path)

    text = crew_wave.collect_text(_collect(root))

    at = [text.find(mark) for mark in ("T-1 pending", "Questions (", "Approvals to type:",
                                       "Land order (clean):", "Later waves:")]
    assert (min(at) >= 0, at == sorted(at)) == (True, True)


def test_collect_writes_nothing(tmp_path):
    root = _started(tmp_path)
    _set_lane(root, "T-1", state="clean", version="1.0.61")
    before = _snapshot(root)

    done = _cli("collect", "--root", root, "--set", "s")

    assert (done.returncode, _snapshot(root) == before) == (0, True)


# --- step 11: cleanup of merged lanes' worktrees ---------------------------------------------

def _origin(root, tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "main")
    return bare


def _landed(tmp_path, merge=True):
    """A started wave whose T-1 lane committed on its branch, merged into
    main and pushed (when `merge`)."""
    root = _started(tmp_path)
    _origin(root, tmp_path)
    wt = _isolated(root)
    ok, reason = crew_wave.lane_init(str(wt), str(root), "s", "T-1")
    assert ok, reason
    _write(wt / "src" / "new.py", "y = 2\n")
    git(wt, "add", "src/new.py")
    git(wt, "commit", "-qm", "lane work")
    if merge:
        git(root, "merge", "-q", "--no-ff", "T-1-wave", "-m", "land T-1")
        git(root, "push", "-q", "origin", "main")
    crew_wave.lane_done(str(root), "s", "T-1", "clean", "ok")
    return root, wt


def _cleaned(root):
    return {row["ticket"]: row for row in crew_wave.cleanup(str(root), "s")["lanes"]}


def _has_branch(root, name):
    return git(root, "branch", "--list", name) != ""


def test_cleanup_removes_a_merged_clean_lane(tmp_path):
    root, wt = _landed(tmp_path)

    got = _cleaned(root)["T-1"]

    assert (got["removed"], os.path.exists(wt), _has_branch(root, "T-1-wave")) == (True, False, False)


def test_cleanup_keeps_a_dirty_lane(tmp_path):
    root, wt = _landed(tmp_path)
    _write(wt / "src" / "app.py", "x = 99\n")

    got = _cleaned(root)["T-1"]

    assert (got["removed"], got["reason"].startswith("dirty ("), os.path.exists(wt)) == (False, True, True)


def test_cleanup_keeps_a_lane_with_untracked_files(tmp_path):
    root, wt = _landed(tmp_path)
    _write(wt / "src" / "scratch.py", "z = 3\n")

    got = _cleaned(root)["T-1"]

    assert (got["removed"], got["reason"].startswith("untracked ("), os.path.exists(wt)) == (
        False, True, True)


def test_cleanup_keeps_a_lane_with_ignored_lane_only_files(tmp_path):
    # Codex review round 5 (rush g0): `git status --porcelain` omits ignored files, so a
    # lane's own .work/ questions.md was removed with its worktree.
    root, wt = _landed(tmp_path)
    _write(wt / ".work" / "tickets" / "T-1" / "questions.md", "## Q1 lane-only\n")

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "ignored files" in got["reason"], os.path.exists(wt)) == (False, True, True)


@pytest.mark.parametrize("state", ["pending", "running"])
def test_cleanup_never_removes_a_lane_that_has_not_landed(tmp_path, state):
    # Codex review round 5 (rush g0): a fresh lane's branch sits at its base, which is
    # already on main, so a clean, just-initialised worktree was removed.
    root = _started(tmp_path)
    _origin(root, tmp_path)
    wt = _isolated(root)
    assert crew_wave.lane_init(str(wt), str(root), "s", "T-1")[0]
    _set_lane(root, "T-1", state=state)

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "not landed" in got["reason"], os.path.exists(wt)) == (False, True, True)


def test_cleanup_never_removes_a_terminal_lane_with_no_commit(tmp_path):
    root = _started(tmp_path)
    _origin(root, tmp_path)
    wt = _isolated(root)
    assert crew_wave.lane_init(str(wt), str(root), "s", "T-1")[0]
    crew_wave.lane_done(str(root), "s", "T-1", "failed", "nothing done")

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "no commit past its base" in got["reason"]) == (False, True)


def test_cleanup_never_removes_a_worktree_the_lane_did_not_record(tmp_path):
    # Codex review round 6 (rush g0): any clean worktree holding the branch was removed.
    root, wt = _landed(tmp_path)
    _set_lane(root, "T-1", worktree=str(tmp_path / "somewhere-else"))

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "not the lane's worktree" in got["reason"], os.path.exists(wt)) == (
        False, True, True)


def test_cleanup_keeps_a_lane_with_an_unmerged_commit(tmp_path):
    root, wt = _landed(tmp_path)
    _write(wt / "src" / "later.py", "w = 4\n")
    git(wt, "add", "src/later.py")
    git(wt, "commit", "-qm", "after the merge")

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "not merged" in got["reason"], os.path.exists(wt),
            _has_branch(root, "T-1-wave")) == (False, True, True, True)


def test_cleanup_never_touches_an_unmerged_lane(tmp_path):
    root, wt = _landed(tmp_path, merge=False)

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "not merged" in got["reason"], os.path.exists(wt),
            _has_branch(root, "T-1-wave")) == (False, True, True, True)


def test_cleanup_keeps_everything_after_a_failed_fetch(tmp_path):
    root, wt = _landed(tmp_path)
    git(root, "remote", "set-url", "origin", str(tmp_path / "no-such-origin.git"))

    got = _cleaned(root)["T-1"]

    assert (got["removed"], "could not tell" in got["reason"], os.path.exists(wt)) == (False, True, True)


def test_cleanup_never_force_deletes_a_branch(tmp_path):
    root, wt = _landed(tmp_path, merge=False)
    other = tmp_path / "other-clone"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.email", "t@example.com")
    git(other, "config", "user.name", "t")
    git(other, "fetch", "-q", str(root), "T-1-wave:T-1-wave")
    git(other, "merge", "-q", "--no-ff", "T-1-wave", "-m", "landed elsewhere")
    git(other, "push", "-q", "origin", "main")

    got = _cleaned(root)["T-1"]

    assert (os.path.exists(wt), _has_branch(root, "T-1-wave"), "branch -d" in got["reason"]) == (
        False, True, True)


def test_cleanup_text_reports_removed_and_kept(tmp_path):
    root, _wt = _landed(tmp_path)

    done = _cli("cleanup", "--root", root, "--set", "s")

    assert (done.returncode, "removed T-1" in done.stdout, "kept T-2" in done.stdout) == (0, True, True)


# --- step 9: the router's `wave` ---------------------------------------------------------------

def test_route_wave(tmp_path):
    got = crew_autopilot.route(str(make_repo(tmp_path, mode="off")), "wave")

    assert (got["sub"], got["stop"]) == ("wave", False)


def test_route_args_wave_set(tmp_path):
    got = crew_autopilot.route_args(str(make_repo(tmp_path, mode="off")), "wave --set my-set")

    assert (got["sub"], got["stop"], got["set"], got["tickets"], got["ticket"]) == (
        "wave", False, "my-set", [], "")


def test_route_args_wave_tickets(tmp_path):
    got = crew_autopilot.route_args(str(make_repo(tmp_path, mode="off")), "wave T-1 T-22")

    assert (got["sub"], got["stop"], got["set"], got["tickets"]) == ("wave", False, "", ["T-1", "T-22"])


def test_route_args_bare_wave(tmp_path):
    got = crew_autopilot.route_args(str(make_repo(tmp_path, mode="off")), "wave")

    assert (got["sub"], got["stop"], got["set"], got["tickets"]) == ("wave", False, "", [])


@pytest.mark.parametrize("text", ["wave --set", "wave --set My_Set", "wave --set a b",
                                  "wave T-1 --set s", "wave --set s T-1", "wave rm",
                                  "wave T-1 status", "wave --set ../x", "wave --tickets T-1"])
def test_route_args_wave_refuses_bad_arguments(tmp_path, text):
    got = crew_autopilot.route_args(str(make_repo(tmp_path, mode="off")), text)

    assert (got["stop"], got["set"], got["tickets"], bool(got["reason"])) == (True, "", [], True)


def test_route_cli_prints_wave_fields(tmp_path):
    root = make_repo(tmp_path, mode="off")
    script = os.path.join(_ROOT, "hooks", "scripts", "crew_autopilot.py")

    done = subprocess.run([sys.executable, script, "route", "--root", str(root), "--args",
                           "wave T-1 T-2"], capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)

    assert done.stdout.strip() == "sub=wave stop=0 ticket= set= tickets=T-1,T-2 reason="
