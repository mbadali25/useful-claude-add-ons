"""T-0011: `/crew:autopilot` ships a ticket after `/crew:done`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py -q

`crew_autopilot.ship_decision` is the pure rule that decides whether an
unattended merge happens: it merges only on every required check `pass` (or a
failing one named EXACTLY in `autopilot.knownFailures`), waits on pending,
stops on anything it could not read, and never merges a high- or
unknown-risk ticket whose completed review rounds are all same-family
(`claude`, or no `model_family` at all). Everything that runs `gh` or
`git push` is stubbed here; no test reaches a network or a real remote.
`sabotage_autopilot.py` mutates each refusing branch to prove these tests can
fail.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_ticket
import review_ledger
from review_fixtures import git
from scope_fixtures import PLAN, SPEC, make_repo


def _check(name, state):
    return {"name": name, "state": state}


GREEN = [_check("build (3.12)", "pass"), _check("check", "pass")]


def _decide(policy="merge", risk="low", checks=None, families=("gpt",), known=()):
    return crew_autopilot.ship_decision(policy, risk, GREEN if checks is None else checks,
                                        list(families), list(known))


# --- step 1: the decision, pure ----------------------------------------------

def test_decision_pr_policy_never_merges():
    got = _decide(policy="pr", risk="low", families=("gpt",))

    assert got["action"] == "open-pr"


@pytest.mark.parametrize("policy", ["Merge", "merge ", None, "squash"])
def test_decision_policy_not_exactly_merge_opens_pr(policy):
    got = _decide(policy=policy)

    assert got["action"] == "open-pr"


def test_decision_merge_all_green():
    got = _decide()

    assert got["action"] == "merge"


def test_decision_merge_waits_on_pending():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "pending")])

    assert (got["action"], "build (3.12)" in got["reason"]) == ("wait", True)


def test_decision_merge_stops_on_unknown_state():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "unknown")])

    assert (got["action"], "build (3.12)" in got["reason"]) == ("stop", True)


def test_decision_merge_stops_on_a_state_outside_the_known_set():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "neutral")])

    assert got["action"] == "stop"


def test_decision_merge_stops_on_unreadable_checks():
    got = crew_autopilot.ship_decision("merge", "low", None, ["gpt"], [])

    assert got["action"] == "stop"


def test_decision_no_required_check_reported_waits():
    got = _decide(checks=[])

    assert got["action"] == "wait"


def test_decision_skipped_required_check_stops():
    got = _decide(checks=[_check("check", "pass"), _check("build (3.12)", "skipping")])

    assert got["action"] == "stop"


def test_decision_merge_stops_on_unlisted_failure():
    got = _decide(checks=[_check("check", "pass"), _check("shell", "fail")])

    assert (got["action"], "shell" in got["reason"]) == ("stop", True)


def test_decision_merge_allows_listed_known_failure():
    got = _decide(checks=[_check("check", "pass"),
                          _check("crew-shell-matrix (windows-latest)", "fail")],
                  known=("crew-shell-matrix (windows-latest)",))

    assert (got["action"], "crew-shell-matrix (windows-latest)" in got["reason"]) == (
        "merge", True)


def test_decision_known_failure_needs_exact_name():
    got = _decide(checks=[_check("check", "pass"),
                          _check("crew-shell-matrix (windows-latest)", "fail")],
                  known=("crew-shell-matrix",))

    assert got["action"] == "stop"


def test_decision_known_failure_is_not_a_prefix_of_the_list_entry():
    got = _decide(checks=[_check("check", "pass"), _check("shell", "fail")],
                  known=("shell (windows-latest)",))

    assert got["action"] == "stop"


def test_decision_high_risk_same_family_stops():
    got = _decide(risk="high", families=("claude", "claude"))

    assert (got["action"], "same-family" in got["reason"]) == ("stop", True)


def test_decision_missing_family_counts_as_same_family():
    got = _decide(risk="high", families=(None, ""))

    assert got["action"] == "stop"


def test_decision_no_completed_round_counts_as_same_family():
    got = _decide(risk="high", families=())

    assert got["action"] == "stop"


def test_decision_unknown_risk_counts_as_high():
    got = _decide(risk=None, families=("claude",))

    assert got["action"] == "stop"


def test_decision_family_spelling_does_not_escape_same_family():
    got = _decide(risk="high", families=("Claude ",))

    assert got["action"] == "stop"


def test_decision_high_risk_cross_family_merges():
    got = _decide(risk="high", families=("claude", "gpt"))

    assert got["action"] == "merge"


def test_decision_low_risk_same_family_merges():
    got = _decide(risk="low", families=("claude",))

    assert got["action"] == "merge"


def test_decision_same_family_stops_before_waiting_on_ci():
    got = _decide(risk="high", families=("claude",), checks=[_check("check", "pending")])

    assert got["action"] == "stop"


# --- fixtures for the phase, the adapter and the ship action -------------------

T = "T-1"
BRANCH = "T-1-build"
NO_PR = f'no pull requests found for branch "{BRANCH}"\n'


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _config(root, **block):
    path = root / ".crew" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["autopilot"] = dict({"mode": "plan"}, **block)
    _write(path, json.dumps(data))


def _done_ticket(tmp_path, index="review", header="status: done   risk: high", **block):
    """A ticket `/crew:done` closed, on branch T-1-build, activated, with
    autopilot armed (unless `block` says otherwise)."""
    root = make_repo(tmp_path, mode="off")
    git(root, "checkout", "-qb", BRANCH)
    folder = root / ".work" / "tickets" / T
    body = SPEC.format(ticket=T, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    _write(folder / "direction.md", "go\n")
    _write(folder / "spec.md", f"{first} title          {header}\n{rest}")
    _write(folder / "plan.md", PLAN.format(files="src/app.py"))
    _write(root / ".work" / "INDEX.md", f"{T} | {index} | high | r | title\n")
    crew_ticket.activate(str(root), T)
    _config(root, **block)
    return root


def _ledger(root, *families):
    path = review_ledger.ledger_path(str(root), T)
    rounds = [{"round": i + 1, "status": "completed", "provider": "x", "model": None,
               "verdict": "CLEAN", "bundle_sha256": "a" * 64, "base": "HEAD",
               "model_family": family} for i, family in enumerate(families)]
    _write(path, json.dumps({"ticket": T, "budget": 2, "rounds": rounds, "refused": [],
                             "state": "ACCEPTED", "receipt": {
                                 "kind": "clean", "round": len(rounds),
                                 "bundle_sha256": "a" * 64, "base": "HEAD",
                                 "verdict": "CLEAN"}}))


def _receipt_ok(monkeypatch, ok=True):
    monkeypatch.setattr(review_ledger, "check_receipt",
                        lambda root, ticket: (ok, "receipt current" if ok else "receipt is stale"))


def _pr(state="OPEN", number=7, head=None):
    return {"number": number, "state": state, "url": f"https://example.test/pull/{number}",
            "headRefOid": head or "0" * 40}


class FakeGh:
    """Stands in for `crew_autopilot._run_gh`: answers by the argv's first two
    words, consuming a list one call at a time (its last entry repeats), and
    records every argv it was handed."""

    def __init__(self, **answers):
        self.answers = answers
        self.calls = []

    def __call__(self, top, args):
        self.calls.append(list(args))
        key = "_".join(args[:2])
        answer = self.answers.get(key)
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        return answer

    def ran(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == list(prefix)]


def _view(pr):
    return (0, json.dumps(pr), "")


def _checks(*rows, code=0):
    return (code, "".join(f"{name}\t{state}\t1m\thttps://example.test/{i}\t\n"
                          for i, (name, state) in enumerate(rows)), "")


def _next(root):
    return crew_autopilot.next_phase(str(root), T)


# --- step 2: the ship phase ---------------------------------------------------

def test_phase_ship_after_done(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=(1, "", NO_PR)))

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == (
        "ship", False, f"crew_autopilot.py ship --ticket {T}")


def test_phase_ship_after_index_done(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path, index="done")
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=(1, "", NO_PR)))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("ship", False)


def test_phase_index_done_without_a_done_header_stays_closed(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path, index="done", header="status: review   risk: high")
    fake = FakeGh(pr_view=(1, "", NO_PR))
    monkeypatch.setattr(crew_autopilot, "_run_gh", fake)

    got = _next(root)

    assert (got["phase"], got["stop"], fake.calls) == ("closed", True, [])


def test_phase_unarmed_done_is_closed_without_reading_gh(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path, mode="off")
    fake = FakeGh(pr_view=(1, "", NO_PR))
    monkeypatch.setattr(crew_autopilot, "_run_gh", fake)

    got = _next(root)

    assert (got["phase"], got["stop"], fake.calls) == ("closed", True, [])


def test_phase_merged_pr_closes(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=_view(_pr("MERGED"))))

    got = _next(root)

    assert (got["phase"], got["stop"], "#7" in got["reason"]) == ("closed", True, True)


def test_phase_open_pr_under_pr_policy_closes_with_note(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path, ship="pr")
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=_view(_pr("OPEN"))))

    got = _next(root)

    assert (got["phase"], got["stop"], "PR #7 open, merge by hand" in got["reason"]) == (
        "closed", True, True)


def test_phase_open_pr_under_merge_policy_ships(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=_view(_pr("OPEN"))))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("ship", False)


def test_phase_gh_failure_stops(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=None))

    got = _next(root)

    assert (got["phase"], got["stop"], "could not read" in got["reason"]) == (
        "ship", True, True)


@pytest.mark.parametrize("answer", [
    (1, "", "HTTP 401: Bad credentials\n"),
    (1, "", 'no pull requests found for branch "other"\n'),
    (0, "not json", ""),
    (0, json.dumps({"number": 7}), ""),
    (0, json.dumps(["OPEN"]), ""),
])
def test_phase_gh_answer_that_is_not_a_pr_state_stops(tmp_path, monkeypatch, answer):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=answer))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("ship", True)


def test_phase_closed_unmerged_pr_stops(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=_view(_pr("CLOSED"))))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("ship", True)


def test_phase_receipt_that_no_longer_stands_stops(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch, False)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=(1, "", NO_PR)))

    got = _next(root)

    assert (got["phase"], got["stop"], "receipt" in got["reason"]) == ("ship", True, True)


def test_phase_detached_head_stops(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    git(root, "checkout", "-q", "--detach")
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(
        pr_view=(1, "", 'no pull requests found for branch "HEAD"\n')))

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("ship", True)


# --- step 2: the gh adapter -----------------------------------------------------

def test_adapter_gh_not_installed_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    assert crew_autopilot._run_gh(str(tmp_path), ["--version"]) is None  # pylint: disable=protected-access


def test_adapter_checks_parse_the_text_output(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=_checks(
        ("build (3.12)", "pending"), ("check", "pass"), ("lint", "cancel"), code=8)))

    got = crew_autopilot.read_checks(".", 7)

    assert got == [{"name": "build (3.12)", "state": "pending"},
                   {"name": "check", "state": "pass"}, {"name": "lint", "state": "fail"}]


def test_adapter_checks_asks_for_required_checks_only(monkeypatch):
    fake = FakeGh(pr_checks=_checks(("check", "pass")))
    monkeypatch.setattr(crew_autopilot, "_run_gh", fake)

    crew_autopilot.read_checks(".", 7)

    assert fake.calls == [["pr", "checks", "7", "--required"]]


@pytest.mark.parametrize("answer", [
    None,
    (4, "", "unexpected\n"),
    (1, "", "HTTP 401: Bad credentials\n"),
    (0, "check\tpending\t1m\turl\t\n", ""),
    (8, "check\tpass\t1m\turl\t\n", ""),
    (0, "no tabs here\n", ""),
    (4, "check\tpass\t1m\turl\t\n", ""),
])
def test_adapter_checks_that_cannot_be_read_are_none(monkeypatch, answer):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=answer))

    assert crew_autopilot.read_checks(".", 7) is None


def test_adapter_checks_an_unknown_bucket_reads_unknown(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=_checks(
        ("check", "neutral"), code=1)))

    got = crew_autopilot.read_checks(".", 7)

    assert crew_autopilot.ship_decision("merge", "low", got, ["gpt"], [])["action"] == "stop"


def test_adapter_no_required_checks_reported_is_empty(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=(
        1, "", f"no required checks reported on the '{BRANCH}' branch\n")))

    assert crew_autopilot.read_checks(".", 7) == []


def test_merge_argv_is_squash_without_admin():
    assert crew_autopilot.merge_argv(7) == ["pr", "merge", "7", "--squash"]


def test_push_argv_never_forces():
    assert crew_autopilot.push_argv(BRANCH) == ["git", "push", "-u", "origin", BRANCH]


# --- step 2: the ship action ------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def _ship_env(tmp_path, monkeypatch, fake, families=("gpt",), push_ok=True, **block):
    root = _done_ticket(tmp_path, **block)
    _ledger(root, *families)
    _receipt_ok(monkeypatch)
    head = git(root, "rev-parse", "HEAD").strip()
    for key, value in list(fake.answers.items()):
        if isinstance(value, list):
            fake.answers[key] = [_view(dict(v, headRefOid=head)) if isinstance(v, dict)
                                 else v for v in value]
        elif isinstance(value, dict):
            fake.answers[key] = _view(dict(value, headRefOid=head))
    fake.answers.setdefault("repo_view", (0, json.dumps({"defaultBranchRef": {"name": "main"}}),
                                          ""))
    pushes = []
    monkeypatch.setattr(crew_autopilot, "_run_gh", fake)
    monkeypatch.setattr(crew_autopilot, "_push", lambda top, branch: (
        pushes.append(branch) or (push_ok, "" if push_ok else "rejected")))
    clock = Clock()
    monkeypatch.setattr(crew_autopilot, "_clock", clock.time)
    monkeypatch.setattr(crew_autopilot, "_sleep", clock.sleep)
    return root, pushes, clock


def test_ship_merges_when_green_and_reports_what_it_rested_on(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=[(1, "", NO_PR), (1, "", NO_PR), _pr("OPEN"), _pr("OPEN"),
                           _pr("MERGED")],
                  pr_create=(0, "https://example.test/pull/7\n", ""),
                  pr_checks=_checks(("check", "pass")), pr_merge=(0, "", ""))
    root, pushes, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude", "gpt"))

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], pushes, got["pr"], got["checks"], got["families"]) == (
        "merged", False, [BRANCH], "https://example.test/pull/7",
        [{"name": "check", "state": "pass"}], ["claude", "gpt"])


def test_ship_merge_command_is_squash_without_admin(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=[(1, "", NO_PR), _pr("OPEN"), _pr("OPEN"), _pr("MERGED")],
                  pr_checks=_checks(("check", "pass")), pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    crew_autopilot.ship(str(root), T)

    assert (fake.ran("pr", "merge"), [c for c in fake.calls if "--admin" in c]) == (
        [["pr", "merge", "7", "--squash"]], [])


def test_ship_pr_policy_opens_and_never_merges(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=[(1, "", NO_PR), (1, "", NO_PR), _pr("OPEN")],
                  pr_create=(0, "", ""), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake, ship="pr")

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "create") != [], fake.ran("pr", "merge")) == (
        "open-pr", True, [])


def test_ship_timeout_pending_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_checks=_checks(("check", "pending"), code=8),
                  pr_merge=(0, "", ""))
    root, _, clock = _ship_env(tmp_path, monkeypatch, fake, ciTimeoutMinutes=2)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], fake.ran("pr", "merge"), clock.now >= 120,
            set(clock.slept) <= {30}) == ("stop", True, [], True, True)


def test_ship_waits_then_merges_when_checks_go_green(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_merge=(0, "", ""),
                  pr_checks=[_checks(("check", "pending"), code=8), _checks(("check", "pass"))])
    root, _, clock = _ship_env(tmp_path, monkeypatch, fake)
    fake.answers["pr_view"] = [fake.answers["pr_view"], fake.answers["pr_view"],
                               fake.answers["pr_view"], _view(_pr("MERGED"))]

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], clock.slept) == ("merged", [30])


def test_ship_high_risk_same_family_never_merges(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude", None))

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], fake.ran("pr", "merge")) == ("stop", True, [])


def test_ship_refuses_the_default_branch_before_pushing(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=(1, "", NO_PR), pr_merge=(0, "", ""),
                  repo_view=(0, json.dumps({"defaultBranchRef": {"name": BRANCH}}), ""))
    root, pushes, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes) == (True, [])


def test_ship_unreadable_default_branch_stops_before_pushing(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=(1, "", NO_PR), repo_view=None)
    root, pushes, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes) == (True, [])


def test_ship_push_failure_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=(1, "", NO_PR), pr_create=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake, push_ok=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], fake.ran("pr", "create")) == (True, [])


def test_ship_pr_create_failure_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=[(1, "", NO_PR), (1, "", NO_PR), _pr("OPEN")],
                  pr_create=(1, "", "GraphQL error\n"), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "gh pr create failed: GraphQL error" in got["reason"],
            fake.ran("pr", "merge")) == (True, True, [])


def test_ship_head_moved_stops_without_merging(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    fake.answers["pr_view"] = [fake.answers["pr_view"], fake.answers["pr_view"],
                               _view(_pr("OPEN", head="f" * 40))]

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], fake.ran("pr", "merge")) == (True, [])


def test_ship_merge_failure_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=[_pr("OPEN"), _pr("OPEN"), _pr("OPEN"), _pr("MERGED")],
                  pr_checks=_checks(("check", "pass")),
                  pr_merge=(1, "", "Pull request is not mergeable\n"))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"]) == ("stop", True)


def test_ship_merge_that_does_not_read_merged_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], fake.ran("pr", "merge") != []) == (True, True)


def test_ship_unreadable_ledger_stops_without_merging(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake,
                           header="status: done   risk: low")
    _write(review_ledger.ledger_path(str(root), T), "{not json")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "ledger" in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_refuses_when_next_is_not_ship(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_pr("MERGED"))
    root, pushes, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes, fake.ran("pr", "merge")) == (True, [], [])


def test_ship_unarmed_refuses(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=(1, "", NO_PR))
    root, pushes, _ = _ship_env(tmp_path, monkeypatch, fake, mode="off")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes, fake.calls) == (True, [], [])


def test_cli_ship_prints_one_line_and_the_evidence(tmp_path, monkeypatch, capsys):
    fake = FakeGh(pr_view=_pr("OPEN"), pr_checks=_checks(("check", "pass")),
                  pr_merge=(0, "", ""))
    root, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude",))
    fake.answers["pr_view"] = [fake.answers["pr_view"], fake.answers["pr_view"],
                               fake.answers["pr_view"], _view(_pr("MERGED"))]

    code = crew_autopilot.main(["ship", "--root", str(root), "--ticket", T])
    out = capsys.readouterr().out.splitlines()

    assert (code, out[0].startswith("action=stop stop=1 ") and "same-family" in out[0],
            out[1:]) == (0, True, ["checks: check=pass", "families: claude"])


def test_cli_ship_that_raises_prints_a_stop(tmp_path, monkeypatch, capsys):
    root = _done_ticket(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(crew_autopilot, "ship", boom)

    code = crew_autopilot.main(["ship", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out.startswith("action=stop stop=1 ")) == (0, True)


# --- step 3: config -----------------------------------------------------------------

def test_ship_default_merge(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.settings(str(root))

    assert (got["ship"], got["knownFailures"], got["ciTimeoutMinutes"], got["warnings"]) == (
        "merge", [], 60, [])


@pytest.mark.parametrize("value", ["Merge", "merge ", "squash", True, None, "auto"])
def test_ship_bad_value_reads_pr(tmp_path, value):
    root = make_repo(tmp_path, mode="off")
    _config(root, ship=value)

    got = crew_autopilot.settings(str(root))

    assert (got["ship"], any("autopilot.ship" in w for w in got["warnings"])) == ("pr", True)


def test_ship_pr_is_kept(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, ship="pr")

    got = crew_autopilot.settings(str(root))

    assert (got["ship"], got["warnings"]) == ("pr", [])


@pytest.mark.parametrize("value", ["windows", [1], ["ok", None], {"a": 1}, None])
def test_known_failures_bad_type_is_empty(tmp_path, value):
    root = make_repo(tmp_path, mode="off")
    _config(root, knownFailures=value)

    got = crew_autopilot.settings(str(root))

    assert (got["knownFailures"], any("knownFailures" in w for w in got["warnings"])) == (
        [], True)


def test_known_failures_list_is_kept(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, knownFailures=["crew-shell-matrix (windows-latest)"])

    got = crew_autopilot.settings(str(root))

    assert got["knownFailures"] == ["crew-shell-matrix (windows-latest)"]


@pytest.mark.parametrize("value", [0, -5, "60", True, 2.5, None])
def test_ci_timeout_bad_value_reads_60(tmp_path, value):
    root = make_repo(tmp_path, mode="off")
    _config(root, ciTimeoutMinutes=value)

    got = crew_autopilot.settings(str(root))

    assert (got["ciTimeoutMinutes"], any("ciTimeoutMinutes" in w for w in got["warnings"])) == (
        60, True)


# --- step 4: sabotage anchors ------------------------------------------------------

def test_every_ship_sabotage_anchor_is_present_exactly_once():
    from sabotage_autopilot import SHIP_MUTATIONS  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in SHIP_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        assert test.startswith("tests/test_crew_autopilot_ship.py::"), label
