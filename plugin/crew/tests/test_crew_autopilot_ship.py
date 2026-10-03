"""T-0011: `/crew:autopilot` ships a ticket after `/crew:done`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py -q

`crew_autopilot.ship_decision` is the pure rule that decides whether an
unattended merge happens: it merges only on every required check `pass` (or a
failing one named EXACTLY in `autopilot.knownFailures`), waits on pending,
stops on anything it could not read, and never merges a high- or
unknown-risk ticket whose completed review rounds are all same-family
(`claude`, or no `model_family` at all). Everything that runs `gh` or
`git push` is stubbed here; no test reaches a network or a real remote.
Each refusing branch was sabotaged by hand (break it, see its test red,
restore); the SHIP_MUTATIONS that make that permanent in
`sabotage_autopilot.py` are a harness-only follow-up (CLAUDE.md, T-0087).
"""
import json
import os
import subprocess

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
SHA = "a" * 40
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


NODE = "PR_kwDOtest7"


def _pr(state="OPEN", number=7, head=None):
    return {"number": number, "state": state, "url": f"https://example.test/pull/{number}",
            "headRefOid": head or "0" * 40, "id": NODE}


class FakeGh:
    """Stands in for `crew_autopilot._run_gh`: answers by the argv's first two
    words, consuming a list one call at a time (its last entry repeats) or
    calling a function with the argv, and records every argv it was handed.
    The one GraphQL mutation ship may ever send is dequeuePullRequest: any
    other fails the test that sent it."""

    def __init__(self, **answers):
        self.answers = answers
        self.calls = []

    def __call__(self, top, args):
        self.calls.append(list(args))
        if list(args[:2]) == ["api", "graphql"] and "mutation" in " ".join(args):
            assert "query=" + crew_autopilot._DEQUEUE in args, args  # pylint: disable=protected-access
        key = "_".join(args[:2])
        answer = self.answers.get(key)
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        return answer(args) if callable(answer) else answer

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
    (1, "check\tpass\t1m\turl\t\n", "output incomplete\n"),
    (1, "check\tpass\t1m\turl\t\n", ""),
    (1, "check\tpending\t1m\turl\t\n", ""),
    (0, "check\tpass\t1m\turl\t\n", "warning: something\n"),
    (8, "check\tpending\t1m\turl\t\n", "error\n"),
])
def test_adapter_checks_that_cannot_be_read_are_none(monkeypatch, answer):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=answer))

    assert crew_autopilot.read_checks(".", 7) is None


def test_adapter_checks_an_unknown_bucket_reads_unknown(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=_checks(
        ("check", "neutral"), code=0)))

    got = crew_autopilot.read_checks(".", 7)

    assert crew_autopilot.ship_decision("merge", "low", got, ["gpt"], [])["action"] == "stop"


def test_adapter_check_name_is_read_verbatim(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=(
        1, " check \tfail\t1m\turl\t\n", "")))

    got = crew_autopilot.read_checks(".", 7)

    assert crew_autopilot.ship_decision("merge", "low", got, ["gpt"], ["check"])["action"] == (
        "stop")


@pytest.mark.parametrize("bucket", ["PASS", "Pass", " pass", "pass "])
def test_adapter_bucket_is_read_verbatim(monkeypatch, bucket):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=(
        0, f"check\t{bucket}\t1m\turl\t\n", "")))

    got = crew_autopilot.read_checks(".", 7)

    assert crew_autopilot.ship_decision("merge", "low", got, ["gpt"], [])["action"] == "stop"


def _queue(enabled, queued):
    return {"data": {"repository": {"pullRequest": {"isMergeQueueEnabled": enabled,
                                                    "isInMergeQueue": queued}}}}


def _gql(data):
    return (0, json.dumps(data), "")


@pytest.mark.parametrize("answer, expected", [
    (_gql(_queue(False, False)), False),
    (_gql(_queue(True, False)), True),
    (_gql(_queue(False, True)), True),
    (None, None),
    ((1, "", "HTTP 401: Bad credentials\n"), None),
    ((0, "not json", ""), None),
    (_gql({"data": {"repository": {"pullRequest": None}}}), None),
    (_gql({"data": None}), None),
    (_gql(_queue(None, False)), None),
    (_gql(_queue("false", False)), None),
    (_gql(_queue(0, False)), None),
    (_gql({"data": {"repository": {"pullRequest": {"isInMergeQueue": False}}}}), None),
])
def test_adapter_merge_queue(monkeypatch, answer, expected):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(api_graphql=answer))

    assert crew_autopilot.read_merge_queue(".", 7) is expected


def test_adapter_merge_queue_asks_about_this_pr(monkeypatch):
    fake = FakeGh(api_graphql=_gql(_queue(False, False)))
    monkeypatch.setattr(crew_autopilot, "_run_gh", fake)

    crew_autopilot.read_merge_queue(".", 7)

    assert fake.calls[0][:8] == ["api", "graphql", "-F", "owner={owner}", "-F", "repo={repo}",
                                 "-F", "number=7"]


def test_adapter_no_required_checks_reported_is_empty(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=(
        1, "", f"no required checks reported on the '{BRANCH}' branch\n")))

    assert crew_autopilot.read_checks(".", 7) == []


def test_merge_argv_is_merge_commit_without_admin(monkeypatch):
    ran = []
    monkeypatch.setattr(crew_autopilot.subprocess, "run", lambda argv, **_kw: (
        ran.append(argv) or subprocess.CompletedProcess(argv, 0, "", "")))

    crew_autopilot._run_gh(".", crew_autopilot.merge_argv(7, SHA))  # pylint: disable=protected-access

    assert (ran, [f for f in ("--squash", "--rebase", "--admin") if f in ran[0]]) == (
        [["gh", "pr", "merge", "7", "--merge", "--match-head-commit", SHA]], [])


def test_push_argv_never_forces():
    assert crew_autopilot.push_argv(BRANCH) == ["git", "push", "-u", "origin", BRANCH]


# --- step 2: the ship action ------------------------------------------------------

class Clock:
    """A fake monotonic clock. `drift` is time a poll spends beyond its sleep
    (gh's own latency); `on_sleep` runs during each sleep, standing in for
    whatever else changes on disk while CI runs."""

    def __init__(self):
        self.now = 0.0
        self.slept = []
        self.drift = 0.0
        self.on_sleep = None

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds + self.drift
        if self.on_sleep is not None:
            self.on_sleep()


class Remote:
    """The PR as GitHub holds it: none until `gh pr create`, then OPEN at
    `head`, and MERGED once `gh pr merge` succeeds (unless `merges` is
    False: gh exits 0 and the PR stays OPEN, as when it queued it)."""

    def __init__(self, head, has_pr=True, merges=True, merge_answer=(0, "", "")):
        self.head = head
        self.has_pr = has_pr
        self.merges = merges
        self.merged = False
        self.merge_answer = merge_answer

    def view(self, _args):
        if not self.has_pr:
            return (1, "", NO_PR)
        return _view(_pr("MERGED" if self.merged else "OPEN", head=self.head))

    def create(self, _args):
        self.has_pr = True
        return (0, "https://example.test/pull/7\n", "")

    def merge(self, _args):
        self.merged = self.merges and self.merge_answer[0] == 0
        return self.merge_answer


def _ship_env(tmp_path, monkeypatch, fake, families=("gpt",), push_ok=True, has_pr=True,
              **block):
    root = _done_ticket(tmp_path, **block)
    _ledger(root, *families)
    _receipt_ok(monkeypatch)
    remote = Remote(git(root, "rev-parse", "HEAD").strip(), has_pr=has_pr)
    fake.answers.setdefault("pr_view", remote.view)
    fake.answers.setdefault("pr_create", remote.create)
    fake.answers.setdefault("pr_merge", remote.merge)
    fake.answers.setdefault("repo_view", (0, json.dumps({"defaultBranchRef": {"name": "main"}}),
                                          ""))
    fake.answers.setdefault("api_graphql", _gql(_queue(False, False)))
    pushes = []
    monkeypatch.setattr(crew_autopilot, "_run_gh", fake)
    monkeypatch.setattr(crew_autopilot, "_push", lambda top, branch: (
        pushes.append(branch) or (push_ok, "" if push_ok else "rejected")))
    clock = Clock()
    monkeypatch.setattr(crew_autopilot, "_clock", clock.time)
    monkeypatch.setattr(crew_autopilot, "_sleep", clock.sleep)
    return root, pushes, clock, remote


def _green():
    return FakeGh(pr_checks=_checks(("check", "pass")))


def _commit(root, message="later"):
    git(root, "commit", "-q", "--allow-empty", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def test_ship_merges_when_green_and_reports_what_it_rested_on(tmp_path, monkeypatch):
    fake = _green()
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude", "gpt"),
                                   has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], pushes, got["pr"], got["checks"], got["families"],
            len(fake.ran("pr", "create"))) == (
        "merged", False, [BRANCH], "https://example.test/pull/7",
        [{"name": "check", "state": "pass"}], ["claude", "gpt"], 1)


def test_ship_merge_command_is_merge_commit_without_admin(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    head = git(root, "rev-parse", "HEAD").strip()

    crew_autopilot.ship(str(root), T)

    assert (fake.ran("pr", "merge"), [c for c in fake.calls if {"--squash", "--rebase",
                                                                 "--admin"} & set(c)]) == (
        [crew_autopilot.merge_argv(7, head)], [])


def test_ship_pr_policy_opens_and_never_merges(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, ship="pr", has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "create") != [], fake.ran("pr", "merge")) == (
        "open-pr", True, [])


def test_ship_timeout_pending_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_checks=_checks(("check", "pending"), code=8))
    root, _, clock, _ = _ship_env(tmp_path, monkeypatch, fake, ciTimeoutMinutes=2)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], fake.ran("pr", "merge"), clock.now >= 120,
            set(clock.slept) <= {30}) == ("stop", True, [], True, True)


def _pending_then_green(polls=1):
    return FakeGh(pr_checks=[_checks(("check", "pending"), code=8)] * polls
                  + [_checks(("check", "pass"))])


def test_ship_waits_then_merges_when_checks_go_green(tmp_path, monkeypatch):
    fake = _pending_then_green()
    root, _, clock, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], clock.slept) == ("merged", [30])


def test_ship_green_after_the_deadline_stops(tmp_path, monkeypatch):
    fake = _pending_then_green(polls=2)
    root, _, clock, _ = _ship_env(tmp_path, monkeypatch, fake, ciTimeoutMinutes=1)
    clock.drift = 10

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], clock.now > 60, fake.ran("pr", "merge")) == ("stop", True, [])


def test_ship_rereads_the_review_families_while_waiting(tmp_path, monkeypatch):
    fake = _pending_then_green()
    root, _, clock, _ = _ship_env(tmp_path, monkeypatch, fake, families=("gpt",))
    clock.on_sleep = lambda: _ledger(root, "claude")

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], "same-family" in got["reason"], fake.ran("pr", "merge")) == (
        "stop", True, [])


def test_ship_disarmed_while_waiting_stops(tmp_path, monkeypatch):
    fake = _pending_then_green()
    root, _, clock, _ = _ship_env(tmp_path, monkeypatch, fake)
    clock.on_sleep = lambda: _config(root, mode="off")

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "merge")) == ("stop", [])


def test_ship_policy_changed_to_pr_while_waiting_never_merges(tmp_path, monkeypatch):
    fake = _pending_then_green()
    root, _, clock, _ = _ship_env(tmp_path, monkeypatch, fake)
    clock.on_sleep = lambda: _config(root, ship="pr")

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "merge")) == ("open-pr", [])


def test_ship_receipt_staled_while_waiting_stops(tmp_path, monkeypatch):
    fake = _pending_then_green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    answers = iter([(True, "receipt current")])
    monkeypatch.setattr(review_ledger, "check_receipt", lambda _root, _ticket: next(
        answers, (False, "receipt is stale")))

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "receipt" in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


@pytest.mark.parametrize("answer", [_gql(_queue(True, False)), _gql(_queue(False, True)),
                                    None, (1, "", "HTTP 502\n")])
def test_ship_merge_queue_or_unreadable_queue_never_merges(tmp_path, monkeypatch, answer):
    fake = FakeGh(pr_checks=_checks(("check", "pass")), api_graphql=answer)
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "merge queue" in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_high_risk_same_family_never_merges(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude", None))

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], fake.ran("pr", "merge")) == ("stop", True, [])


def test_ship_refuses_the_default_branch_before_pushing(tmp_path, monkeypatch):
    fake = FakeGh(repo_view=(0, json.dumps({"defaultBranchRef": {"name": BRANCH}}), ""))
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake, has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes) == (True, [])


def test_ship_unreadable_default_branch_stops_before_pushing(tmp_path, monkeypatch):
    fake = FakeGh(repo_view=None)
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake, has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes) == (True, [])


def test_ship_push_failure_stops(tmp_path, monkeypatch):
    fake = FakeGh()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, push_ok=False, has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], fake.ran("pr", "create")) == (True, [])


def test_ship_pr_create_failure_stops(tmp_path, monkeypatch):
    fake = FakeGh(pr_create=(1, "", "GraphQL error\n"), pr_checks=_checks(("check", "pass")))
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "gh pr create failed: GraphQL error" in got["reason"],
            fake.ran("pr", "merge")) == (True, True, [])


def test_ship_pr_head_moved_after_ci_stops_without_merging(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)

    def receipt(_root, _ticket):
        if fake.ran("pr", "checks"):
            remote.head = "f" * 40
        return True, "receipt current"
    monkeypatch.setattr(review_ledger, "check_receipt", receipt)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "f" * 40 in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_pr_head_that_is_not_the_push_stops_before_ci(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)
    remote.head = "f" * 40

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], fake.ran("pr", "checks"), fake.ran("pr", "merge")) == (True, [], [])


def test_ship_merge_failure_stops(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)
    remote.merge_answer = (1, "", "Pull request is not mergeable\n")

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["stop"], "not mergeable" in got["reason"]) == (
        "stop", True, True)


def test_ship_merge_that_does_not_read_merged_stops(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)
    remote.merges = False

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], fake.ran("pr", "merge") != [], "not MERGED" in got["reason"]) == (
        True, True, True)


def test_ship_unreadable_ledger_stops_without_merging(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake,
                              header="status: done   risk: low")
    _write(review_ledger.ledger_path(str(root), T), "{not json")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "ledger" in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_refuses_when_next_is_not_ship(tmp_path, monkeypatch):
    fake = FakeGh(pr_view=_view(_pr("MERGED")))
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes, fake.ran("pr", "merge")) == (True, [], [])


def test_ship_unarmed_refuses(tmp_path, monkeypatch):
    fake = FakeGh()
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake, mode="off", has_pr=False)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], pushes, fake.calls) == (True, [], [])


# --- review round 2: the checks, the commit, the ledger and the tree it rests on --

def test_read_checks_measured_row_reads_exact_name_and_bucket(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=(
        1, "crew (windows-latest)\tfail\t1m2s\thttps://example.test/1\tExit 1\n"
           "check\tpass\t0\thttps://example.test/2\t\n", "")))

    got = crew_autopilot.read_checks(".", 7)

    assert got == [{"name": "crew (windows-latest)", "state": "fail"},
                   {"name": "check", "state": "pass"}]


@pytest.mark.parametrize("answer", [
    (1, "check\tfail\tfail\t1m\turl\t\n", ""),
    (1, "check\tfail\t1m\turl\tdescription\twith a tab\n", ""),
    (0, "check\tpass\t1m\turl\n", ""),
])
def test_read_checks_tab_in_name_is_unreadable(tmp_path, monkeypatch, answer):
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_checks=answer))
    alone = crew_autopilot.read_checks(".", 7)
    fake = FakeGh(pr_checks=answer)
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, knownFailures=["check"])

    got = crew_autopilot.ship(str(root), T)

    assert (alone, got["stop"], fake.ran("pr", "merge")) == (None, True, [])


def test_ship_stops_when_a_commit_lands_after_passing_checks(tmp_path, monkeypatch):
    fake = FakeGh()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)

    def checks(_args):
        if remote.head == git(root, "rev-parse", "HEAD").strip():
            remote.head = _commit(root, "B")
        return _checks(("check", "pass"))
    fake.answers["pr_checks"] = checks

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], remote.head in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_with_no_new_commit_merges_the_head_it_pushed(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    head_a = git(root, "rev-parse", "HEAD").strip()

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "merge")) == (
        "merged", [crew_autopilot.merge_argv(7, head_a)])


def _successor_ledger(root):
    """A Claude-only ledger under a successor plan: what a high-risk merge
    must never rest on."""
    path = review_ledger.ledger_path(str(root), T)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data["successors"] = [{"after_round": len(data["rounds"]), "plan_sha256": "b" * 64}]
    data["rounds"].append(dict(data["rounds"][-1], round=len(data["rounds"]) + 1,
                               model_family="claude"))
    _write(path, json.dumps(data))


def test_ship_stops_when_the_ledger_is_replaced_after_the_last_poll(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("gpt",))

    def receipt(_root, _ticket):
        if fake.ran("pr", "checks"):
            _successor_ledger(root)
        return True, "receipt current"
    monkeypatch.setattr(review_ledger, "check_receipt", receipt)

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "ledger changed" in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_unchanged_ledger_merges_on_the_gates_families(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude", "gpt"))

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], got["families"]) == ("merged", ["claude", "gpt"])


def _queue_read_that(root, moves):
    def read(_top, _number):
        if moves:
            _commit(root, "B")
        return False
    return read


def test_ship_stops_when_head_moves_during_the_queue_read(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(crew_autopilot, "read_merge_queue", _queue_read_that(root, True))

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "HEAD moved" in got["reason"], fake.ran("pr", "merge")) == (
        True, True, [])


def test_ship_queue_read_without_a_commit_merges_with_the_pushed_head(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    head_a = git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(crew_autopilot, "read_merge_queue", _queue_read_that(root, False))

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], fake.ran("pr", "merge")) == (
        "merged", [["pr", "merge", "7", "--merge", "--match-head-commit", head_a]])


def test_ship_refuses_a_dirty_tracked_file_before_pushing(tmp_path, monkeypatch):
    fake = _green()
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    _write(root / "src" / "app.py", "x = 2\n")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "working tree" in got["reason"], pushes,
            fake.ran("pr", "merge")) == (True, True, [], [])


def test_ship_refuses_an_untracked_file_before_pushing(tmp_path, monkeypatch):
    fake = _green()
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    _write(root / "src" / "new.py", "y = 1\n")

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "working tree" in got["reason"], pushes,
            fake.ran("pr", "merge")) == (True, True, [], [])


def test_ship_ignored_file_is_not_a_dirty_tree(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    _write(root / ".work" / "scratch.txt", "notes\n")

    got = crew_autopilot.ship(str(root), T)

    assert got["action"] == "merged"


def test_ship_tree_dirtied_while_waiting_never_merges(tmp_path, monkeypatch):
    fake = _pending_then_green()
    root, pushes, clock, _ = _ship_env(tmp_path, monkeypatch, fake)
    clock.on_sleep = lambda: _write(root / "src" / "app.py", "x = 3\n")

    got = crew_autopilot.ship(str(root), T)

    assert (pushes, "working tree" in got["reason"], fake.ran("pr", "merge")) == (
        [BRANCH], True, [])


def test_ship_unreadable_tree_stops(tmp_path, monkeypatch):
    fake = _green()
    root, pushes, _, _ = _ship_env(tmp_path, monkeypatch, fake)
    real = crew_autopilot.git_out
    monkeypatch.setattr(crew_autopilot, "git_out", lambda top, *args: (
        None if args[:1] == ("status",) else real(top, *args)))

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "could not tell whether the working tree" in got["reason"],
            pushes) == (True, True, [])


def test_phase_dirty_tree_stops(tmp_path, monkeypatch):
    root = _done_ticket(tmp_path)
    _receipt_ok(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "_run_gh", FakeGh(pr_view=(1, "", NO_PR)))
    _write(root / "src" / "app.py", "x = 2\n")

    got = _next(root)

    assert (got["phase"], got["stop"], crew_autopilot.DIRTY in got["reason"]) == (
        "ship", True, True)


@pytest.mark.parametrize("queue_after", [_gql(_queue(True, True)), None])
def test_ship_dequeues_a_pr_gh_queued(tmp_path, monkeypatch, queue_after):
    fake = _green()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)
    remote.merges = False
    fake.answers["api_graphql"] = lambda args: (
        (0, "{}", "") if "query=" + crew_autopilot._DEQUEUE in args  # pylint: disable=protected-access
        else queue_after if fake.ran("pr", "merge") else _gql(_queue(False, False)))

    got = crew_autopilot.ship(str(root), T)

    dequeues = [c for c in fake.calls if "query=" + crew_autopilot._DEQUEUE in c]  # pylint: disable=protected-access
    assert (got["stop"], "merge queue" in got["reason"], "dequeued it: succeeded" in
            got["reason"], dequeues) == (True, True, True, [crew_autopilot.dequeue_argv(NODE)])


def test_ship_unreadable_queue_after_merge_dequeues_and_stops(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, remote = _ship_env(tmp_path, monkeypatch, fake)
    remote.merges = False
    answers = iter([_gql(_queue(False, False))])
    fake.answers["api_graphql"] = lambda args: (
        (1, "", "HTTP 502\n") if "query=" + crew_autopilot._DEQUEUE in args  # pylint: disable=protected-access
        else next(answers, None))

    got = crew_autopilot.ship(str(root), T)

    assert (got["stop"], "could not tell whether gh handed the PR to a merge queue" in
            got["reason"], "dequeued it: failed: HTTP 502" in got["reason"],
            fake.ran("pr", "merge") != []) == (True, True, True, True)


def test_ship_merge_that_reads_merged_never_dequeues(tmp_path, monkeypatch):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake)

    got = crew_autopilot.ship(str(root), T)

    assert (got["action"], [c for c in fake.calls if "mutation" in " ".join(c)]) == (
        "merged", [])


def test_cli_ship_prints_one_line_and_the_evidence(tmp_path, monkeypatch, capsys):
    fake = _green()
    root, _, _, _ = _ship_env(tmp_path, monkeypatch, fake, families=("claude",))

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
