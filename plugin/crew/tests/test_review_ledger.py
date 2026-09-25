"""The two-round review budget: reserved before launch, shared across
worktrees, not resettable from the environment or the command line.

Five review rounds on one ticket is the measured failure this exists for
(`docs/review/03-codex-review.md`). Every case runs against a throwaway repo
under tmp_path; the ledger lands in THAT repo's git-common-dir.
"""
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import review_fixtures
import review_ledger as rl
import review_run
from review_fixtures import env_with_path, fake_reviewer_bin, git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_LEDGER = os.path.join(_SCRIPTS, "review_ledger.py")
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return init_repo(tmp_path / "r")


def _cli(repo, *args, env=None):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo)] + list(args),
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          env=env, check=False)


def test_reserve_grants_rounds_one_and_two(repo):
    first = rl.reserve(str(repo), "T1", "codex")
    second = rl.reserve(str(repo), "T1", "codex")

    assert (first[:2], second[:2]) == ((True, 1), (True, 2))


def test_reserve_third_round_is_refused_and_state_is_needs_replan(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")

    ok, number, _ = rl.reserve(str(repo), "T1", "codex")

    assert (ok, number, rl.status(str(repo), "T1")["state"]) == (False, None, rl.NEEDS_REPLAN)


def test_reserve_counts_a_crashed_round_with_no_result(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")

    ok, _, _ = rl.reserve(str(repo), "T1", "codex")

    assert ok is False
    assert [r["status"] for r in rl.status(str(repo), "T1")["rounds"]] == ["reserved"] * 2


def test_reserve_budget_cannot_be_reset_or_raised_by_env_or_flag(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")
    env = dict(os.environ, CREW_REVIEW_BUDGET="9", CREW_REVIEW_RESET="1",
               CREW_REVIEW_ROUNDS="9")

    flag_budget = _cli(repo, "--ticket", "T1", "--reserve", "--budget", "3", env=env)
    flag_reset = _cli(repo, "--ticket", "T1", "--reserve", "--reset", env=env)
    plain = _cli(repo, "--ticket", "T1", "--reserve", env=env)

    assert (flag_budget.returncode, flag_reset.returncode) == (2, 2)
    assert plain.returncode == 1 and "budget exhausted" in plain.stderr


def test_ledger_path_is_under_git_common_dir(repo):
    common = git(repo, "rev-parse", "--git-common-dir")
    expected = os.path.normpath(os.path.join(str(repo), common, "crew", "review", "T1.json"))

    rl.reserve(str(repo), "T1", "codex")

    assert rl.ledger_path(str(repo), "T1") == expected and os.path.exists(expected)


def test_ledger_is_shared_by_a_second_worktree(repo, tmp_path):
    other = tmp_path / "second-worktree"
    git(repo, "worktree", "add", "-q", "-b", "side", str(other))
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(other), "T1", "codex")

    ok, _, _ = rl.reserve(str(repo), "T1", "codex")

    assert rl.ledger_path(str(other), "T1") == rl.ledger_path(str(repo), "T1")
    assert ok is False


def test_reserve_refuses_an_unreadable_ledger(repo):
    path = rl.ledger_path(str(repo), "T1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")

    ok, _, message = rl.reserve(str(repo), "T1", "codex")

    assert ok is False and "UNKNOWN" in message


@pytest.mark.parametrize("ticket", ["../x", "a/b", "", ".hidden", "a\\b"])
def test_check_ticket_refuses_path_like_ids(ticket):
    with pytest.raises(rl.LedgerError):
        rl.check_ticket(ticket)


def _race(root, start, results):
    start.wait()
    ok, _, _ = rl.reserve(root, "T1", "codex")
    results.put(ok)


def test_reserve_two_concurrent_claims_on_the_last_round_exactly_one_wins(repo):
    rl.reserve(str(repo), "T1", "codex")
    ctx = multiprocessing.get_context("spawn")
    start, results = ctx.Event(), ctx.Queue()
    procs = [ctx.Process(target=_race, args=(str(repo), start, results)) for _ in range(6)]
    for proc in procs:
        proc.start()

    start.set()
    for proc in procs:
        proc.join(60)
    wins = [results.get(timeout=10) for _ in procs]

    assert wins.count(True) == 1
    assert rl.status(str(repo), "T1")["rounds_used"] == 2


def test_successor_plan_without_an_approval_receipt_is_refused_and_says_why(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")

    ok, reason = rl.continue_with_successor_plan(str(repo), "T1", "a" * 64)

    assert ok is False and "no approved plan" in reason
    assert rl.status(str(repo), "T1")["state"] == rl.NEEDS_REPLAN


def test_successor_plan_cli_refuses(repo):
    result = _cli(repo, "--ticket", "T1", "--successor-plan", "b" * 64)

    assert result.returncode == 1 and "refused" in result.stdout


def _bundle(repo, scratch):
    base = git(repo, "rev-parse", "HEAD")
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]),
        encoding="utf-8")


def _run(repo, scratch, fakes, mode, *extra, **env_extra):
    return subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1",
         "--scratch", str(scratch), "--provider", "codex"] + list(extra),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        env=env_with_path(fakes, FAKE_REVIEWER_MODE=mode, **env_extra), timeout=120)


def test_run_reserves_before_launch_so_a_crash_still_spends_the_round(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    _run(repo, scratch, fakes, "crash")

    rounds = rl.status(str(repo), "T1")["rounds"]
    assert [r["status"] for r in rounds] == ["reserved"]


def test_run_clean_writes_review_json_and_a_receipt(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "clean", "--work-dir", str(work))

    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (review["verdict"], review["round"], review["model_family"]) == ("CLEAN", 1, "gpt")
    assert rl.status(str(repo), "T1")["receipt"]["bundle_sha256"] == review["bundle_sha256"]


@pytest.mark.parametrize("mode,code", [("fail", 3), ("turnfail", 3), ("findings", 1)])
def test_run_maps_reviewer_failures_to_incomplete(repo, tmp_path, mode, code):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, mode, "--work-dir", str(work))

    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    assert result.returncode == code, result.stdout + result.stderr
    assert review["verdict"] == ("FINDINGS" if code == 1 else "INCOMPLETE")


def test_run_timeout_is_incomplete(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "hang", "--timeout", "2", "--work-dir", str(work))

    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    assert (result.returncode, review["verdict"], review["timed_out"]) == (3, "INCOMPLETE", True)


@pytest.mark.skipif(shutil.which("setsid") is None, reason="needs setsid")
@pytest.mark.skipif(os.name == "nt", reason="POSIX process semantics only")
def test_run_timeout_survives_an_escaped_descendant_holding_the_pipe(repo, tmp_path):
    """BLOCK (Codex): the fake reviewer's `escape` mode exits immediately
    after forking a detached `setsid` grandchild that inherits its
    stdout/stderr and outlives it (bounded to a few seconds, not the 60s an
    earlier version of this fixture left running -- see review_fixtures.py's
    own comment) -- the leader is gone (and reaped) long before `launch`
    gets to kill anything, so a bare `os.killpg(proc.pid, ...)` would target
    a recycled pid, and an unbounded follow-up `communicate()` would block
    on the grandchild's pipe for as long as it kept running. review_run.py
    must return in a small multiple of --timeout (bounded by
    POST_KILL_TIMEOUT), not however long the grandchild lives, and still
    report INCOMPLETE/timed_out.

    FIX: this test's own earlier version left that grandchild (a detached
    `setsid` process, outside the whole test's process tree) running for up
    to a minute after the test itself had finished, with nothing reaping or
    even identifying it. The pidfile below lets this test watch it exit on
    its own, bounded.

    BLOCK (Codex): a still-earlier version of THIS fix read the pidfile only
    after `_run` had already returned, then signalled that pid in a
    `finally` block once an identity snapshot (`crew_fixtures.
    _proc_start_ticks`) taken at that same late point matched. That
    snapshot only proves identity at the moment it is taken -- it cannot
    prove the pid still names the same process by the time the signal is
    sent, and on a busy host a short-lived unrelated process can be handed
    that exact pid in the gap between the two. So this never signals the
    grandchild at all. It is bounded by construction (`review_fixtures.
    ESCAPE_CHILD_LIFETIME_S`, sized against `review_run.POST_KILL_TIMEOUT`
    so the fixture's own timing assumption is checked here rather than
    just assumed): this test only waits for it to exit within that bound
    plus headroom, and FAILS if it has not.

    FIX (Codex): the elapsed-time assertion used to be a bare `< 20`
    ceiling, which the escaped grandchild's own (then-shorter) lifetime
    already cleared regardless of whether the second, post-kill
    `communicate()` was actually bounded -- a `communicate()` with no
    timeout at all still returns well under 20s once the grandchild itself
    exits, so that ceiling could not tell the bounded path from the
    regression it exists to catch. `review_fixtures.ESCAPE_CHILD_LIFETIME_S`
    is now sized to comfortably outlive `--timeout + POST_KILL_TIMEOUT`, and
    the assertion is tightened to that same bound (plus a small margin) --
    the bounded path meets it, and an unbounded second `communicate()` (which
    would instead wait out the grandchild's now much longer lifetime) cannot.
    """
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    pidfile = tmp_path / "escape.pid"
    timeout_s = 1

    started = time.monotonic()
    result = _run(repo, scratch, fakes, "escape", "--timeout", str(timeout_s),
                  "--work-dir", str(work), FAKE_REVIEWER_ESCAPE_PIDFILE=str(pidfile))
    elapsed = time.monotonic() - started

    # Read, and its identity recorded, in the same breath the pid is first
    # available -- not later, once more of this test has already run and the
    # pid has had longer to be reaped and reused by something unrelated. On a
    # host with no /proc (`_PROC_SUPPORTED` is Linux-only), there is no start
    # time to record, so the identity-based wait below is skipped with a
    # named reason rather than trusting a bare pid.
    grandchild_pid = (int(pidfile.read_text(encoding="utf-8").strip())
                       if pidfile.exists() else None)
    grandchild_start_ticks = (
        crew_fixtures._proc_start_ticks(grandchild_pid)  # pylint: disable=protected-access
        if grandchild_pid is not None else None)

    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    bound = timeout_s + review_run.POST_KILL_TIMEOUT + 3
    assert elapsed < bound, (
        f"review-run took {elapsed:.1f}s (bound {bound}s) - it must not block on a "
        "descendant that escaped the kill and outlived --timeout"
    )
    assert (result.returncode, review["verdict"], review["timed_out"]) == (
        3, "INCOMPLETE", True)

    if not crew_fixtures._PROC_SUPPORTED:  # pylint: disable=protected-access
        # No /proc on this host (non-Linux POSIX): a bare pid cannot prove
        # identity here, so waiting on it risks following a pid the kernel
        # already handed to an unrelated process. The assertions above
        # already proved review-run itself did not block; skipped rather
        # than guessed.
        return

    def _still_our_grandchild():
        if grandchild_pid is None or grandchild_start_ticks is None:
            return False
        if not crew_fixtures.pid_alive(grandchild_pid):
            return False
        return crew_fixtures._proc_start_ticks(  # pylint: disable=protected-access
            grandchild_pid) == grandchild_start_ticks

    liveness_bound = review_fixtures.ESCAPE_CHILD_LIFETIME_S + 5
    deadline = time.monotonic() + liveness_bound
    while _still_our_grandchild() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _still_our_grandchild(), (
        f"the escaped grandchild (pid {grandchild_pid}) was still alive "
        f"{liveness_bound}s after it should have exited on its own -- it is never "
        "signalled by this test, since by the time it is read this pid may already "
        "have been handed to an unrelated process"
    )


def test_run_missing_provider_spends_no_round(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    empty = tmp_path / "nothing-here"
    empty.mkdir()

    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1",
         "--scratch", str(scratch), "--provider", "codex"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        env=dict(os.environ, PATH=str(empty)))

    assert result.returncode == 2
    assert rl.status(str(repo), "T1")["rounds_used"] == 0


def test_run_third_round_is_refused_without_launching(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    _run(repo, scratch, fakes, "findings", "--work-dir", str(work))
    _run(repo, scratch, fakes, "findings", "--work-dir", str(work))

    third = _run(repo, scratch, fakes, "clean", "--work-dir", str(work))

    assert third.returncode == 4
    assert rl.status(str(repo), "T1")["state"] == rl.NEEDS_REPLAN


def test_claude_verdict_refuses_an_unreserved_round(repo, tmp_path):
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    (scratch / "out.txt").write_text("CLEAN\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch",
         str(scratch), "--provider", "claude", "--round", "1", "--output",
         str(scratch / "out.txt"), "--exit-code", "0", "--work-dir", str(tmp_path / "w")],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)

    assert result.returncode == 2 and "never reserved" in result.stderr
    assert not (tmp_path / "w" / "review.json").exists()


# ---- recording rules: latest round, once, by the reserved reviewer ----------

def _result(verdict, provider="codex", model=None):
    return {"verdict": verdict, "counts": {}, "bundle_sha256": "0" * 64, "base": "HEAD",
            "head": "HEAD", "provider": provider, "model": model, "model_family": "gpt"}


def test_record_an_older_round_after_the_budget_is_spent_is_refused(repo):
    """Codex BLOCK: round 1's late CLEAN turned NEEDS_REPLAN back into
    ACCEPTED and minted a receipt."""
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")
    rl.record(str(repo), "T1", 2, _result("FINDINGS"))
    rl.reserve(str(repo), "T1", "codex")

    with pytest.raises(rl.LedgerError):
        rl.record(str(repo), "T1", 1, _result("CLEAN"))

    assert (rl.status(str(repo), "T1")["state"], rl.status(str(repo), "T1")["receipt"]) == (
        rl.NEEDS_REPLAN, None)


def test_record_an_older_round_while_a_later_one_is_reserved_is_refused(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")

    with pytest.raises(rl.LedgerError, match="most recent"):
        rl.record(str(repo), "T1", 1, _result("CLEAN"))


@pytest.mark.parametrize("verdict", ["FINDINGS", "INCOMPLETE"])
def test_record_round_two_without_clean_leaves_the_ticket_reviewed(repo, verdict):
    rl.reserve(str(repo), "T1", "codex")
    rl.record(str(repo), "T1", 1, _result("FINDINGS"))
    rl.reserve(str(repo), "T1", "codex")

    state = rl.record(str(repo), "T1", 2, _result(verdict))

    assert state == rl.REVIEWED


def test_record_a_round_twice_is_refused(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.record(str(repo), "T1", 1, _result("FINDINGS"))

    with pytest.raises(rl.LedgerError, match="already has a result"):
        rl.record(str(repo), "T1", 1, _result("CLEAN"))


def test_record_after_needs_replan_is_refused_even_for_the_latest_round(repo):
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")

    with pytest.raises(rl.LedgerError, match=rl.NEEDS_REPLAN):
        rl.record(str(repo), "T1", 2, _result("CLEAN"))


@pytest.mark.parametrize("provider,model", [("claude", None), ("codex", "gpt-other")])
def test_record_by_a_reviewer_other_than_the_reserved_one_is_refused(repo, provider, model):
    rl.reserve(str(repo), "T1", "codex", "gpt-6-astra")

    with pytest.raises(rl.LedgerError, match="reserved for codex/gpt-6-astra"):
        rl.record(str(repo), "T1", 1, _result("CLEAN", provider, model))


def test_claude_result_cannot_complete_a_codex_reservation(repo, tmp_path):
    """Codex BLOCK: reserve round 1 as codex, then `review_run.py --provider
    claude --round 1` with CLEAN output. The ledger accepted it and erased the
    provider that was actually reserved."""
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    rl.reserve(str(repo), "T1", "codex")
    parts = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['name']}\n" for p in parts) + "CLEAN\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch",
         str(scratch), "--provider", "claude", "--round", "1", "--output",
         str(scratch / "out.txt"), "--exit-code", "0", "--work-dir", str(tmp_path / "w")],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)

    row = rl.status(str(repo), "T1")["rounds"][0]
    assert result.returncode == 2, result.stdout + result.stderr
    assert (row["status"], row["provider"]) == ("reserved", "codex")


def test_reserve_after_needs_replan_is_refused_without_writing(repo):
    """Codex BLOCK: every reservation attempt after NEEDS_REPLAN appended
    another `refused` entry, so a terminal state kept changing."""
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")
    with open(rl.ledger_path(str(repo), "T1"), "rb") as fh:
        before = fh.read()

    ok, number, message = rl.reserve(str(repo), "T1", "claude")

    with open(rl.ledger_path(str(repo), "T1"), "rb") as fh:
        after = fh.read()
    assert (ok, number, rl.NEEDS_REPLAN in message, after) == (False, None, True, before)
