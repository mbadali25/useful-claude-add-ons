"""T-0029 Step 7: the scope guard refuses the never-list from a subagent, and
`review_ledger.py` no longer abbreviates its flags.

    python3 -m pytest plugin/crew/tests/test_scope_guard_wave.py -q

A wave lane is an `Agent` with `isolation: worktree`. The Step 1 spike
(`.work/tickets/T-0029/spike.md`) measured its PreToolUse payload: `agent_type`
is present (`general-purpose`) and `cwd` is the lane's own worktree. Every
case here builds that shape: a main checkout under `scope.mode: block`, a
started wave, and a lane worktree at `<main>/.claude/worktrees/agent-<id>`
set up by the real `crew_wave.lane_init` (its own copied `.crew/config.json`
and active ticket). With `agent_type` present the guard refuses
`review_ledger.py --accept|--reject` (and every abbreviation argparse would
have expanded), `crew_ticket.py approve` and `gh pr merge --admin`; without it
-- the main session, the owner's path -- nothing changes. Nothing here touches
the real repository or ~/.claude. `sabotage_wave.py` proves these can fail.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_wave
from review_fixtures import git
from scope_fixtures import FLAVOUR_MATRIX, approve_as_user, edit, make_repo, make_ticket, run_hook

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
LEDGER = os.path.join(SCRIPTS, "review_ledger.py")
LANE = "general-purpose"
PREFIXES = ("--a", "--ac", "--acc", "--acce", "--accep", "--rej", "--reje", "--rejec")


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _main(tmp_path, tickets=(("T-1", ("src/**",)),)):
    root = make_repo(tmp_path, mode="block")
    with open(root / ".gitignore", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(".claude/worktrees/\n")
    git(root, "commit", "-qam", "ignore agent worktrees")
    for ticket, touch in tickets:
        make_ticket(root, ticket, touch, files=[touch[0].replace("**", "x.py")], activate=False)
        approve_as_user(root, ticket)
    _write(root / ".work" / "INDEX.md", "".join(f"{t} | approved | high | r | title\n"
                                               for t, _ in tickets))
    crew_wave.write_set(str(root), "s", [t for t, _ in tickets], {t: [] for t, _ in tickets})
    crew_wave.start(str(root), "s")
    return root


def _lane(root, ticket, name):
    path = root / ".claude" / "worktrees" / name
    git(root, "worktree", "add", "-q", "-b", f"worktree-{name}", str(path))
    ok, reason = crew_wave.lane_init(str(path), str(root), "s", ticket)
    assert ok, reason
    return path


@pytest.fixture(name="lane")
def _lane_fixture(tmp_path):
    root = _main(tmp_path)
    return root, _lane(root, "T-1", "agent-a1")


def _shell(cwd, command, agent_type=LANE, tool="Bash"):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": {"command": command}, "cwd": str(cwd)}
    if agent_type is not None:
        payload["agent_type"] = agent_type
        payload["agent_id"] = "a1"
    return payload


def _guard(flavour, cwd, payload):
    return run_hook(flavour, "scope_guard", payload, cwd)


# --- must-block ------------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_subagent_review_ledger_accept_is_refused(flavour, lane):
    _root, wt = lane

    code, _, err = _guard(flavour, wt, _shell(wt, f"python3 {LEDGER} --ticket T-1 --accept --by me"))

    assert (code, "a lane may not accept, reject or admin-merge" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_subagent_review_ledger_reject_is_refused(flavour, lane):
    _root, wt = lane

    code, _, err = _guard(flavour, wt, _shell(wt, f"python3 {LEDGER} --ticket T-1 --reject --by me"))

    assert (code, "a lane may not" in err) == (2, True)


@pytest.mark.parametrize("flag", PREFIXES)
def test_subagent_accept_reject_abbreviation_is_refused(lane, flag):
    _root, wt = lane

    code, _, err = _guard("module", wt, _shell(wt, f"python3 {LEDGER} --ticket T-1 {flag} --by me"))

    assert (code, "a lane may not" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_subagent_crew_ticket_approve_is_refused(flavour, lane):
    _root, wt = lane

    code, _, _ = _guard(flavour, wt, _shell(wt, f"python3 {SCRIPTS}/crew_ticket.py approve --ticket T-1"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_subagent_gh_pr_merge_admin_is_refused(flavour, lane):
    _root, wt = lane

    code, _, err = _guard(flavour, wt, _shell(wt, "gh pr merge 12 --merge --admin"))

    assert (code, "admin-merge" in err) == (2, True)


@pytest.mark.parametrize("command,tool", [
    ("python3 /abs/path/review_ledger.py --ticket T-1 --accept", "Bash"),
    ("py -3 review_ledger.py --ticket T-1 --accept --by me", "Bash"),
    ("echo ok && review_ledger.py --ticket T-1 --accept", "Bash"),
    ("cd x; python -m review_ledger --ticket T-1 --reject --by me", "Bash"),
    ("& python review_ledger.py --ticket T-1 --accept --by me", "PowerShell"),
    ("python3 review_ledger.py --ticket T-1 --accept=1", "Bash"),
    ("GH_PAGER= gh pr merge --admin 12", "Bash"),
    ("gh pr merge 12 --squash --admin | cat", "Bash")])
def test_subagent_never_list_spellings_are_refused(lane, command, tool):
    _root, wt = lane

    code, _, _ = _guard("module", wt, _shell(wt, command, tool=tool))

    assert code == 2


# --- must-allow --------------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_main_session_review_ledger_accept_is_allowed(flavour, lane):
    root, _wt = lane

    code, _, _ = _guard(flavour, root, _shell(root, f"python3 {LEDGER} --ticket T-1 --accept --by me",
                                              agent_type=None))

    assert code == 0


@pytest.mark.parametrize("command", [f"python3 {LEDGER} --ticket T-1 --accept --by me",
                                     "gh pr merge 12 --admin"])
def test_main_session_never_list_is_unchanged(lane, command):
    root, _wt = lane

    assert _guard("module", root, _shell(root, command, agent_type=None))[0] == 0


@pytest.mark.parametrize("flag", ["--status", "--reserve", "--check-receipt", "--args-like"])
def test_subagent_review_ledger_status_reserve_allowed(lane, flag):
    _root, wt = lane

    code, _, _ = _guard("module", wt, _shell(wt, f"python3 {LEDGER} --root . --ticket T-1 {flag}"))

    assert code == 0


@pytest.mark.parametrize("command", [
    "python3 {s}/review_run.py --root . --ticket T-1 --scratch /tmp/x --provider claude --reserve-only",
    "python3 {s}/review_run.py --root . --ticket T-1 --scratch /tmp/x --provider claude --round 1 "
    "--output /tmp/x/out.txt --exit-code 0"])
def test_subagent_review_run_reserve_and_record_allowed(lane, command):
    _root, wt = lane

    assert _guard("module", wt, _shell(wt, command.format(s=SCRIPTS)))[0] == 0


@pytest.mark.parametrize("command", ["gh pr merge 12 --merge", "gh pr view 12 --json adminMerge",
                                     "echo --admin && gh pr merge 12"])
def test_subagent_gh_pr_merge_without_admin_allowed(lane, command):
    _root, wt = lane

    assert _guard("module", wt, _shell(wt, command))[0] == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_subagent_write_inside_own_worktree_touch_allowed(flavour, lane):
    _root, wt = lane
    payload = dict(edit(wt, wt / "src" / "app.py"), agent_type=LANE)

    assert _guard(flavour, wt, payload)[0] == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_subagent_write_outside_own_worktree_touch_refused(flavour, tmp_path):
    root = _main(tmp_path, (("T-1", ("src/**",)), ("T-2", ("other/**",))))
    one, two = _lane(root, "T-1", "agent-a1"), _lane(root, "T-2", "agent-a2")

    got = [_guard(flavour, wt, dict(edit(wt, wt / rel), agent_type=LANE))[0]
           for wt, rel in ((one, "src/app.py"), (one, "other/keep.py"),
                           (two, "other/keep.py"), (two, "src/app.py"))]

    assert got == [0, 2, 0, 2]


# --- review_ledger.py no longer abbreviates -------------------------------------------

@pytest.mark.parametrize("flag", ["--acc", "--a", "--rej", "--stat"])
def test_review_ledger_abbreviated_accept_is_an_argparse_error(tmp_path, flag):
    root = make_repo(tmp_path, mode="off")
    ledger = os.path.join(git(root, "rev-parse", "--absolute-git-dir"), "crew", "review", "T-1.json")
    _write(ledger, json.dumps({"ticket": "T-1", "budget": 2, "rounds": [
        {"round": 1, "status": "completed", "verdict": "FINDINGS"}], "refused": [],
        "state": "REVIEWED", "receipt": None}))
    with open(ledger, "rb") as handle:
        before = handle.read()

    done = subprocess.run([sys.executable, LEDGER, "--root", str(root), "--ticket", "T-1", flag,
                           "--by", "me"], capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)

    with open(ledger, "rb") as handle:
        after = handle.read()
    assert (done.returncode, after == before) == (2, True)
