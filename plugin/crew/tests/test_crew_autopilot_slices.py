"""T-0059: a plan's `## PR slices` ship as ordered slice PRs through T-0011.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_slices.py -q

A plan whose `## PR slices` section `crew_split.parse_slices` refuses stops
at the plan phase. A valid one runs one slice at a time: `next` names
`implement` with the current slice's steps, `/crew:done` on a non-final slice
leaves the header `in-progress` and records the slice done
(`crew_autopilot.py slice-done`), `ship` opens one PR per slice against the
default branch or the stacked predecessor's branch and never ships slice
k+1 before slice k is merged (or opened, under `ship: pr`), and
`next-slice` opens the next slice's branch and review budget. The budget
reset itself is `review_ledger.open_slice`, a HARNESS path (CLAUDE.md,
T-0087): until a tooling PR lands it, `next-slice` refuses and writes
nothing, and the tests that need it stub it.

`gh` and `git push` are stubbed (test_crew_autopilot_ship's FakeGh); every
repository is built under tmp_path.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_slices
import crew_ship
import crew_ticket
import review_ledger
from review_fixtures import git
from scope_fixtures import SPEC, approve_as_user, make_repo
from test_crew_autopilot_ship import (Clock, FakeGh, _gql, _queue, _view, _pr, _checks,
                                      _write, _config)

T = "T-1"
BRANCH = "T-1-build"
MAIN = (0, json.dumps({"defaultBranchRef": {"name": "main"}}), "")


def _plan(slices=None, files=None):
    files = files or {}
    steps = "".join(f"### Step {n}: step {n}\nFiles: {files.get(n, f'src/s{n}.py')}\n"
                    f"Test: pytest\nRisk: low\n- [ ] do {n}\n\n" for n in range(1, 6))
    if slices is None:
        slices = ("### Slice 1: first\nSteps: 1, 2\nBase: main\n\n"
                  "### Slice 2: second\nSteps: 3-4\nBase: slice 1\n\n"
                  "### Slice 3: third\nSteps: 5\nBase: main\n")
    return f"# Plan\n\n{steps}## PR slices\n\n{slices}"


def _unsliced():
    return _plan().split("## PR slices", maxsplit=1)[0]


def _spec(header):
    body = SPEC.format(ticket=T, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    return f"{first} title          {header}\n{rest}"


def _ticket(tmp_path, header="status: spec   risk: high", plan=None, approve=True,
            **block):
    root = make_repo(tmp_path, mode="off")
    git(root, "checkout", "-qb", BRANCH)
    folder = root / ".work" / "tickets" / T
    _write(folder / "direction.md", "go\n")
    _write(folder / "spec.md", _spec(header))
    _write(folder / "plan.md", plan if plan is not None else _plan())
    _write(root / ".work" / "INDEX.md", f"{T} | spec | high | r | title\n")
    if approve:
        approve_as_user(root, T)
    crew_ticket.activate(str(root), T)
    _config(root, **block)
    return root


def _set_header(root, header):
    _write(root / ".work" / "tickets" / T / "spec.md", _spec(header))


def _state(root, **state):
    path = crew_autopilot_slices.slices_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"current": 1, "done": [], "shipped": []}
    data.update(state)
    _write(path, json.dumps(data))
    return path


def _read_state(root):
    with open(crew_autopilot_slices.slices_path(str(root), T), encoding="utf-8") as handle:
        return json.load(handle)


def _accepted_ledger(root, rounds=1, slices=None):
    path = review_ledger.ledger_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"ticket": T, "budget": 2, "refused": [], "state": "ACCEPTED",
            "rounds": [{"round": i + 1, "status": "completed", "provider": "x",
                        "model": None, "verdict": "CLEAN", "bundle_sha256": "a" * 64,
                        "base": "HEAD", "model_family": "gpt"} for i in range(rounds)],
            "receipt": {"kind": "clean", "round": rounds, "bundle_sha256": "a" * 64,
                        "base": "HEAD", "verdict": "CLEAN"}}
    if slices is not None:
        data["slices"] = slices
    _write(path, json.dumps(data))


def _receipt_ok(monkeypatch, ok=True):
    monkeypatch.setattr(review_ledger, "check_receipt",
                        lambda root, ticket: (ok, "receipt current" if ok else "stale"))


def _fresh(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_refresh_state", lambda root, ticket: {
        "state": "fresh", "command": "", "reason": "fresh"})


def _next(root):
    return crew_autopilot.next_phase(str(root), T)


# --- step 1 in autopilot: a refused section stops the plan phase ---------------------

def test_plan_with_refused_slices_stops_at_plan(tmp_path):
    root = _ticket(tmp_path, approve=False, plan=_plan(
        "### Slice 1: a\nSteps: 1, 3\nBase: main\n\n### Slice 2: b\nSteps: 2, 4, 5\n"
        "Base: slice 1\n"))

    got = _next(root)

    assert (got["phase"], got["stop"], "PR slices:" in got["reason"],
            "contiguous" in got["reason"]) == ("plan", True, True, True)


def test_plan_without_slices_is_unchanged(tmp_path):
    plan = _unsliced()
    root = _ticket(tmp_path, plan=plan)

    got = _next(root)

    assert (got["phase"], got["stop"], "slice" in got["reason"], got.get("slice")) == (
        "implement", False, False, None)


# --- step 2: slices run in order ----------------------------------------------------

def test_next_names_current_slice_steps(tmp_path):
    root = _ticket(tmp_path)

    got = _next(root)

    assert (got["phase"], got["stop"], got["slice"],
            got["reason"].startswith("slice 1 of 3 (first): steps 1-2 only")) == (
        "implement", False, 1, True)


def test_next_names_the_second_slice_after_next_slice(tmp_path):
    root = _ticket(tmp_path)
    _state(root, current=2, done=[1], shipped=[{"slice": 1, "pr": 7, "branch": BRANCH,
                                                "base": "main", "merge_sha": None}])
    _accepted_ledger(root, rounds=1, slices=[{"slice": 2, "after_round": 1}])

    got = _next(root)

    assert (got["phase"], got["slice"], "slice 2 of 3 (second): steps 3-4" in got["reason"]
            ) == ("implement", 2, True)


def test_unreadable_slice_state_stops(tmp_path):
    root = _ticket(tmp_path)
    path = crew_autopilot_slices.slices_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, "{not json")

    got = _next(root)

    assert (got["phase"], got["stop"], "slices.json" in got["reason"]) == (
        "slices", True, True)


@pytest.mark.parametrize("state", [
    {"current": 0, "done": [], "shipped": []},
    {"current": 4, "done": [], "shipped": []},
    {"current": True, "done": [], "shipped": []},
    {"current": 2, "done": "1", "shipped": []},
    {"current": 2, "done": [], "shipped": {}},
])
def test_slice_state_out_of_shape_stops(tmp_path, state):
    root = _ticket(tmp_path)
    path = crew_autopilot_slices.slices_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, json.dumps(state))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("slices", True)


def test_spent_counts_from_latest_slice_or_successor():
    ledger = {"rounds": [{"round": n} for n in range(1, 6)],
              "successors": [{"after_round": 1}], "slices": [{"slice": 2, "after_round": 3}]}
    later_successor = dict(ledger, successors=[{"after_round": 4}])

    assert ([r["round"] for r in crew_autopilot._current_rounds(ledger)],  # pylint: disable=protected-access
            [r["round"] for r in crew_autopilot._current_rounds(later_successor)]) == (  # pylint: disable=protected-access
        [4, 5], [5])


def test_in_progress_header_keeps_the_approval(tmp_path):
    """T-0037 left `in-progress` in STATUS_VALUES: the non-final slice's
    header edit keeps the plan approval, so the next slice needs no re-approve."""
    root = _ticket(tmp_path)
    _set_header(root, "status: in-progress   risk: high")

    assert crew_ticket.accepted(str(root), T)["status"] == "approved"


def test_non_final_slice_done_keeps_ticket_open(tmp_path, monkeypatch):
    root = _ticket(tmp_path)
    _accepted_ledger(root)
    _receipt_ok(monkeypatch)
    _set_header(root, "status: in-progress   risk: high")

    got = crew_autopilot_slices.slice_done(str(root), T)
    phase = _next(root)

    assert (got["ok"], got["reason"].startswith("slice 1 of 3 done"), _read_state(root)["done"],
            phase["phase"], phase["stop"]) == (True, True, [1], "ship", True)


def test_non_final_slice_done_armed_names_ship(tmp_path, monkeypatch):
    root = _ticket(tmp_path, header="status: in-progress   risk: high")
    _accepted_ledger(root)
    _receipt_ok(monkeypatch)
    _state(root, done=[1])
    monkeypatch.setattr(crew_ship, "_run_gh", FakeGh(
        pr_view=(1, "", f'no pull requests found for branch "{BRANCH}"\n')))

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"], got["slice"]) == (
        "ship", False, f"crew_autopilot.py ship --ticket {T}", 1)


def test_slice_done_refuses_a_done_header(tmp_path, monkeypatch):
    root = _ticket(tmp_path, header="status: done   risk: high")
    _receipt_ok(monkeypatch)

    got = crew_autopilot_slices.slice_done(str(root), T)

    assert (got["ok"], "in-progress" in got["reason"],
            os.path.exists(crew_autopilot_slices.slices_path(str(root), T))) == (False, True, False)


def test_slice_done_refuses_the_final_slice(tmp_path, monkeypatch):
    root = _ticket(tmp_path, header="status: in-progress   risk: high")
    _receipt_ok(monkeypatch)
    _state(root, current=3, done=[1, 2])

    got = crew_autopilot_slices.slice_done(str(root), T)

    assert (got["ok"], "last slice" in got["reason"], _read_state(root)["done"]) == (
        False, True, [1, 2])


def test_slice_done_refuses_without_a_standing_receipt(tmp_path, monkeypatch):
    root = _ticket(tmp_path, header="status: in-progress   risk: high")
    _receipt_ok(monkeypatch, ok=False)

    got = crew_autopilot_slices.slice_done(str(root), T)

    assert (got["ok"], "receipt" in got["reason"],
            os.path.exists(crew_autopilot_slices.slices_path(str(root), T))) == (False, True, False)


def test_slice_done_refuses_an_unsliced_ticket(tmp_path, monkeypatch):
    root = _ticket(tmp_path, header="status: in-progress   risk: high",
                   plan=_unsliced())
    _receipt_ok(monkeypatch)

    got = crew_autopilot_slices.slice_done(str(root), T)

    assert (got["ok"], "no ## PR slices" in got["reason"]) == (False, True)


def test_final_slice_done_closes(tmp_path):
    root = _ticket(tmp_path, header="status: done   risk: high", mode="off")
    _state(root, current=3, done=[1, 2])

    got = _next(root)

    assert (got["phase"], got["stop"], "closed by /crew:done" in got["reason"]) == (
        "closed", True, True)


def test_done_header_before_the_last_slice_stops(tmp_path):
    """A `status: done` header while slice 1 of 3 is current would close the
    ticket with slices 2 and 3 unbuilt: a stop, never `closed` or `ship`."""
    root = _ticket(tmp_path, header="status: done   risk: high")

    got = _next(root)

    assert (got["phase"], got["stop"], "slice 1 of 3" in got["reason"]) == (
        "slices", True, True)


def test_slice_command_reports_the_current_slice(tmp_path, capsys):
    root = _ticket(tmp_path)
    _state(root, current=3, done=[1, 2])
    capsys.readouterr()

    code = crew_autopilot.main(["slice", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out.strip()) == (
        0, "slice=3 of=3 final=yes steps=5 name=third")


def test_slice_command_unsliced(tmp_path, capsys):
    root = _ticket(tmp_path, plan=_unsliced())
    capsys.readouterr()

    code = crew_autopilot.main(["slice", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out.strip()) == (0, "slice=none")


# --- step 3: the base rule (pure) ---------------------------------------------------

SLICES = [{"n": 1, "base": "main"}, {"n": 2, "base": 1}, {"n": 3, "base": "main"},
          {"n": 4, "base": 2}]
BRANCHES = {1: BRANCH, 2: f"{BRANCH}-s2", 3: f"{BRANCH}-s3"}


def _base(n, merged):
    return crew_autopilot_slices.slice_base(n, SLICES, merged, BRANCHES, "main")


def test_base_first_slice_is_default_branch():
    assert _base(1, set()) == "main"


def test_base_independent_slice_is_default_branch_while_earlier_open():
    assert _base(3, set()) == "main"


def test_base_stacked_slice_is_predecessor_branch_while_unmerged():
    assert _base(2, set()) == BRANCH


def test_base_stacked_slice_is_default_branch_once_every_earlier_merged():
    assert _base(4, {1, 2, 3}) == "main"


def test_base_follows_the_chain_past_a_merged_predecessor():
    """Slice 4 stacks on 2, which stacked on 1: with 2 merged and 1 not (a
    stacked PR merged into 1's branch), the base is 1's branch."""
    assert _base(4, {2}) == BRANCH


# --- step 3: ship per slice ---------------------------------------------------------

class Remote:
    """GitHub's PRs by head branch: none until created, then OPEN, MERGED
    after a merge."""

    def __init__(self, root, prs=None):
        self.root = root
        self.prs = dict(prs or {})
        self.created = []

    def view(self, args):
        branch = args[2]
        pr = self.prs.get(branch)
        if pr is None:
            return (1, "", f'no pull requests found for branch "{branch}"\n')
        return _view(pr)

    def create(self, args):
        head = args[args.index("--head") + 1]
        self.created.append(list(args))
        self.prs[head] = dict(_pr("OPEN", number=10 + len(self.created),
                                  head=git(self.root, "rev-parse", "HEAD").strip()),
                              baseRefName=(args[args.index("--base") + 1]
                                           if "--base" in args else "main"))
        return (0, "https://example.test/pull/x\n", "")

    def merge(self, args):
        for branch, pr in self.prs.items():
            if str(pr["number"]) == args[2]:
                self.prs[branch] = dict(pr, state="MERGED", mergeCommit={"oid": "c" * 40})
        return (0, "", "")


def _ship_env(tmp_path, monkeypatch, current=1, done=None, shipped=None, prs=None,
              header=None, branch=None, plan=None, **block):
    final = current == 3
    root = _ticket(tmp_path, header=header or ("status: done   risk: low" if final else
                                               "status: in-progress   risk: low"),
                   plan=plan, **block)
    if branch:
        git(root, "checkout", "-qb", branch)
    _accepted_ledger(root)
    _receipt_ok(monkeypatch)
    _fresh(monkeypatch)
    _state(root, current=current, done=done if done is not None else
           (list(range(1, current + 1)) if not final else list(range(1, current))),
           shipped=shipped or [])
    remote = Remote(root, prs)
    fake = FakeGh(pr_view=remote.view, pr_create=remote.create, pr_merge=remote.merge,
                  repo_view=MAIN, pr_checks=_checks(("check", "pass")),
                  api_graphql=_gql(_queue(False, False)))
    pushes = []
    monkeypatch.setattr(crew_ship, "_run_gh", fake)
    monkeypatch.setattr(crew_ship, "_push", lambda top, b: (pushes.append(b) or (True, "")))
    clock = Clock()
    monkeypatch.setattr(crew_autopilot, "_clock", clock.time)
    monkeypatch.setattr(crew_autopilot, "_sleep", clock.sleep)
    return root, fake, remote, pushes


def _shipped(n, branch, state="OPEN", base="main", merge_sha=None):
    return {"slice": n, "pr": 10 + n, "branch": branch, "base": base, "merge_sha": merge_sha}


def test_first_slice_pr_against_default_branch(tmp_path, monkeypatch):
    root, fake, remote, pushes = _ship_env(tmp_path, monkeypatch, ship="pr")

    got = crew_autopilot.ship(str(root), T)

    create = remote.created[0]
    assert (got["action"], pushes, create[create.index("--base") + 1],
            create[create.index("--head") + 1], create[create.index("--title") + 1],
            fake.ran("pr", "merge")) == (
        "open-pr", [BRANCH], "main", BRANCH, "T-1 slice 1/3: first", [])


def test_first_slice_open_records_the_pr(tmp_path, monkeypatch):
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, ship="pr")

    crew_autopilot.ship(str(root), T)

    assert _read_state(root)["shipped"] == [
        {"slice": 1, "pr": 11, "branch": BRANCH, "base": "main", "merge_sha": None}]


def test_slice_merge_uses_merge_argv(tmp_path, monkeypatch):
    root, fake, _, _ = _ship_env(tmp_path, monkeypatch)
    head = git(root, "rev-parse", "HEAD").strip()

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "merge"), _read_state(root)["shipped"][0]["merge_sha"]
            ) == ("merged", [crew_ship.merge_argv(11, head)], "c" * 40)


def test_stacked_slice_bases_on_predecessor_branch(tmp_path, monkeypatch):
    prs = {BRANCH: _pr("OPEN", number=11)}
    root, _, remote, pushes = _ship_env(
        tmp_path, monkeypatch, current=2, shipped=[_shipped(1, BRANCH)], prs=prs,
        branch=f"{BRANCH}-s2", ship="pr")

    got = crew_autopilot.ship(str(root), T)

    create = remote.created[0]
    assert (got["action"], pushes, create[create.index("--base") + 1],
            "Stacked on #11" in create[create.index("--body") + 1]) == (
        "open-pr", [f"{BRANCH}-s2"], BRANCH, True)


def test_independent_slice_bases_on_default_branch(tmp_path, monkeypatch):
    plan = _plan("### Slice 1: first\nSteps: 1, 2\nBase: main\n\n"
                 "### Slice 2: second\nSteps: 3-4\nBase: main\n\n"
                 "### Slice 3: third\nSteps: 5\nBase: main\n")
    prs = {BRANCH: _pr("OPEN", number=11)}
    root, _, remote, _ = _ship_env(
        tmp_path, monkeypatch, current=2, shipped=[_shipped(1, BRANCH)], prs=prs,
        branch=f"{BRANCH}-s2", plan=plan, ship="pr")

    got = crew_autopilot.ship(str(root), T)

    create = remote.created[0]
    assert (got["action"], create[create.index("--base") + 1]) == ("open-pr", "main")


def test_slice_n_refused_before_n_minus_1(tmp_path, monkeypatch):
    root, fake, _, pushes = _ship_env(tmp_path, monkeypatch, current=2, shipped=[],
                                      branch=f"{BRANCH}-s2", ship="pr")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "slice 1" in got["reason"], pushes, fake.ran("pr", "create")) == (
        True, True, [], [])


def test_slice_n_refused_while_n_minus_1_open_under_merge(tmp_path, monkeypatch):
    prs = {BRANCH: _pr("OPEN", number=11)}
    root, fake, _, pushes = _ship_env(tmp_path, monkeypatch, current=2,
                                      shipped=[_shipped(1, BRANCH)], prs=prs,
                                      branch=f"{BRANCH}-s2")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "not merged" in got["reason"], pushes,
            fake.ran("pr", "create")) == (True, True, [], [])


def test_slice_n_refused_when_n_minus_1_unreadable(tmp_path, monkeypatch):
    root, fake, _, pushes = _ship_env(tmp_path, monkeypatch, current=2,
                                      shipped=[_shipped(1, BRANCH)],
                                      branch=f"{BRANCH}-s2", ship="pr")
    fake.answers["pr_view"] = None

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes) == (True, [])


def test_slice_ships_only_from_its_own_branch(tmp_path, monkeypatch):
    prs = {BRANCH: _pr("MERGED", number=11)}
    root, _, _, pushes = _ship_env(tmp_path, monkeypatch, current=2,
                                   shipped=[_shipped(1, BRANCH, merge_sha="c" * 40)], prs=prs)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], f"{BRANCH}-s2" in got["reason"], pushes) == (True, True, [])


def test_unsliced_ticket_ship_unchanged(tmp_path, monkeypatch):
    root, _, remote, _ = _ship_env(tmp_path, monkeypatch, current=3,
                                   plan=_unsliced(), ship="pr")
    os.remove(crew_autopilot_slices.slices_path(str(root), T))

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], remote.created, os.path.exists(
        crew_autopilot_slices.slices_path(str(root), T))) == (
        "open-pr", [["pr", "create", "--head", BRANCH, "--fill"]], False)


def test_merged_non_final_slice_names_next_slice(tmp_path, monkeypatch):
    root, _, _, _ = _ship_env(tmp_path, monkeypatch)
    head = git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(crew_ship, "_run_gh", FakeGh(
        pr_view=_view(dict(_pr("MERGED", number=11, head=head), baseRefName="main")),
        repo_view=MAIN))

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == (
        "next-slice", False, f"crew_autopilot.py next-slice --ticket {T}")


def test_merged_slice_pr_on_another_base_is_not_shipped(tmp_path, monkeypatch):
    """T-0059 port review r4 BLOCK: a slice PR retargeted and then merged
    elsewhere did not reach its base; next stops instead of moving on."""
    root, _, _, _ = _ship_env(tmp_path, monkeypatch)
    head = git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(crew_ship, "_run_gh", FakeGh(
        pr_view=_view(dict(_pr("MERGED", number=11, head=head), baseRefName="develop")),
        repo_view=MAIN))

    got = _next(root)

    assert (got["phase"], got["stop"], "merged into develop" in got["reason"]) == (
        "ship", True, True), got


def test_open_non_final_slice_under_pr_names_next_slice(tmp_path, monkeypatch):
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, ship="pr")
    # T-0059 port review r2: the open PR's base is read and must be the plan's.
    monkeypatch.setattr(crew_ship, "_run_gh", FakeGh(
        pr_view=_view(dict(_pr("OPEN", number=11), baseRefName="main")), repo_view=MAIN))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("next-slice", False)


# --- next-slice: the branch and the fresh review budget -----------------------------

def _remote(root, tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "HEAD:refs/heads/main")
    return bare


def _next_slice_env(tmp_path, monkeypatch, **block):
    root = _ticket(tmp_path, header="status: in-progress   risk: low", **block)
    _remote(root, tmp_path)
    _accepted_ledger(root)
    _receipt_ok(monkeypatch)
    _fresh(monkeypatch)
    head = git(root, "rev-parse", "HEAD").strip()
    _state(root, current=1, done=[1], shipped=[_shipped(1, BRANCH, merge_sha="c" * 40)])
    monkeypatch.setattr(crew_ship, "_run_gh", FakeGh(
        pr_view=_view(dict(_pr("MERGED", number=11, head=head), baseRefName="main")),
        repo_view=MAIN))
    return root


def test_next_slice_refused_without_open_slice(tmp_path, monkeypatch):
    root = _next_slice_env(tmp_path, monkeypatch)
    monkeypatch.delattr(review_ledger, "open_slice", raising=False)
    before = _read_state(root)

    got = crew_autopilot_slices.next_slice(str(root), T)

    assert (got["ok"], "open_slice" in got["reason"], _read_state(root),
            git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()) == (
        False, True, before, BRANCH)


def test_next_slice_opens_branch_budget_and_state(tmp_path, monkeypatch):
    root = _next_slice_env(tmp_path, monkeypatch)
    opened = []
    monkeypatch.setattr(review_ledger, "open_slice",
                        lambda top, ticket, n: opened.append((ticket, n)), raising=False)

    got = crew_autopilot_slices.next_slice(str(root), T)

    assert (got["ok"], opened, _read_state(root)["current"],
            git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(),
            git(root, "rev-parse", "HEAD").strip() == git(root, "rev-parse", "origin/main").strip()
            ) == (True, [(T, 2)], 2, f"{BRANCH}-s2", True)


def test_next_slice_undoes_the_branch_when_open_slice_refuses(tmp_path, monkeypatch):
    root = _next_slice_env(tmp_path, monkeypatch)

    def refuse(top, ticket, n):
        raise review_ledger.LedgerError("state is IN_REVIEW, not ACCEPTED")

    monkeypatch.setattr(review_ledger, "open_slice", refuse, raising=False)

    got = crew_autopilot_slices.next_slice(str(root), T)

    branches = git(root, "branch", "--list", f"{BRANCH}-s2").strip()
    assert (got["ok"], "IN_REVIEW" in got["reason"], _read_state(root)["current"], branches,
            git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()) == (
        False, True, 1, "", BRANCH)


def test_next_slice_refused_unless_next_names_it(tmp_path, monkeypatch):
    root = _next_slice_env(tmp_path, monkeypatch)
    _state(root, current=1, done=[], shipped=[])
    monkeypatch.setattr(review_ledger, "open_slice", lambda *a: None, raising=False)

    got = crew_autopilot_slices.next_slice(str(root), T)

    assert (got["ok"], "not next-slice" in got["reason"]) == (False, True)


# --- port review round 1 (release/1.2.0) ----------------------------------------

def test_existing_slice_pr_on_another_base_is_not_shipped(tmp_path, monkeypatch):
    """T-0059 port review BLOCK: a retargeted or hand-opened PR would merge
    into a branch the plan did not name; ship stops, nothing pushed."""
    prs = {BRANCH: dict(_pr("OPEN", number=5), baseRefName="develop")}
    root, fake, _, pushes = _ship_env(tmp_path, monkeypatch, prs=prs)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], "based on develop, not main" in got["reason"], pushes,
            fake.ran("pr", "merge")) == ("stop", True, [], []), got


def test_slice_pr_created_before_a_stop_is_recorded(tmp_path, monkeypatch):
    """T-0059 port review FIX: a PR ship opened and then stopped on (a failed
    check) is on record, so its slice's branch is known to next-slice."""
    root, fake, _, _ = _ship_env(tmp_path, monkeypatch)
    fake.answers["pr_checks"] = _checks(("check", "fail"))

    got = crew_autopilot.ship(str(root), T)

    assert got["action"] == "stop", got
    assert [(e["slice"], e["branch"]) for e in _read_state(root)["shipped"]] == [(1, BRANCH)]



def test_next_stops_on_an_open_slice_pr_with_another_base(tmp_path, monkeypatch):
    """T-0059 port review r2 BLOCK: under `ship: pr` an open slice PR whose
    base is not the plan's is never `next-slice`."""
    prs = {BRANCH: dict(_pr("OPEN", number=5), baseRefName="develop")}
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, prs=prs, ship="pr")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], "based on develop, not main" in got["reason"]) == (
        "ship", True, True), got


@pytest.mark.parametrize("rows", [[{"slice": 2}], [{"slice": 2, "after_round": "1"}],
                                  [{"slice": 2, "after_round": 9}], {"after_round": 1}])
def test_malformed_slice_rows_stop_review_as_unknown(tmp_path, monkeypatch, rows):
    """T-0059 port review r2 BLOCK: a slice boundary that cannot be read is
    UNKNOWN, never "every round counts" and never a crash."""
    root = _ticket(tmp_path, header="status: in-progress   risk: high")
    _accepted_ledger(root, rounds=1, slices=rows)

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], "UNKNOWN" in got["reason"]) == (
        "review", True, True), got


def test_slice_pr_recorded_when_the_result_names_none(tmp_path, monkeypatch):
    """T-0059 port review r2 FIX: a PR opened before ship stopped without
    naming it (the follow-up read failed) is still recorded."""
    root, _, remote, _ = _ship_env(tmp_path, monkeypatch, ship="pr")
    real = crew_autopilot._ship  # pylint: disable=protected-access

    def opened_then_lost(top, ticket, branch, create, base=None):
        real(top, ticket, branch, create, base)
        return crew_autopilot._ship_result(ticket, "stop", True, "lost")  # pylint: disable=protected-access
    monkeypatch.setattr(crew_autopilot, "_ship", opened_then_lost)

    crew_autopilot.ship(str(root), T)

    assert remote.created and [e["slice"] for e in _read_state(root)["shipped"]] == [1]
