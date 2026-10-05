"""`review_run.py` takes the merge train (L-0520, wired by L-0526) before it reserves a gate
round: once the clone is armed, an overlapping ticket's round is refused with
exit 6 and NOTHING is reserved; an unarmed clone reviews exactly as before.

Two linked worktrees of one throwaway repository stand in for two lanes. The
tickets carry no approval receipt, so the standards self-check does not apply
and the round reaches `review_ledger.reserve` -- the step every must-block
case proves was never reached, by snapshotting the ledger directory under the
throwaway repository's git-common-dir. Everything lives under tmp_path.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_train
import review_ledger
import review_run
import scope_base
from review_fixtures import git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")


def _spec(top, ticket, touch):
    folder = top / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text(
        f"# {ticket}\n\n## Touch\n\n" + "".join(f"- `{p}`\n" for p in touch), encoding="utf-8")


@pytest.fixture(name="lanes")
def _lanes(tmp_path):
    repo = init_repo(tmp_path / "r")
    found = {"repo": repo}
    for ticket, name in (("T-1", "wt1"), ("T-2", "wt2")):
        path = tmp_path / name
        git(repo, "worktree", "add", "-q", "-b", name, str(path), "main")
        _spec(path, ticket, ["a.txt"])
        scope_base.record(str(path), ticket)
        (path / "a.txt").write_text(f"{ticket}\n", encoding="utf-8")
        found[ticket] = path
    return found


def _ledger_snapshot(repo):
    base = os.path.join(crew_train.crew_ticket.state_dir(str(repo)), "review")
    found = {}
    for dirpath, _, names in os.walk(base):
        for name in names:
            with open(os.path.join(dirpath, name), "rb") as fh:
                found[os.path.join(dirpath, name)] = fh.read()
    return found


def _bundle(top, ticket, scratch):
    """The review bundle the pre-review checks (L-0574) read: built by
    review_patch.py against the ticket's recorded base, as /crew:review does."""
    base = scope_base.resolve(str(top), ticket)[0]
    subprocess.run([sys.executable, _PATCH, "--root", str(top), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=120)


def _run(top, ticket, tmp_path):
    scratch = tmp_path / f"scratch-{ticket}"
    scratch.mkdir(exist_ok=True)
    _bundle(top, ticket, scratch)
    return subprocess.run(
        [sys.executable, _RUN, "--root", str(top), "--ticket", ticket, "--scratch",
         str(scratch), "--provider", "claude", "--reserve-only"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120)


def _train(top, *argv):
    return crew_train.main(["--root", str(top)] + list(argv))


def test_unarmed_clone_reviews_as_before(lanes, tmp_path):
    done = _run(lanes["T-1"], "T-1", tmp_path)

    assert done.returncode == 0, done.stderr
    assert "ROUND=1" in done.stdout
    assert "train" not in done.stderr


def test_second_overlapping_gate_round_is_refused_unspent(lanes, tmp_path):
    assert _train(lanes["repo"], "arm") == 0
    first = _run(lanes["T-1"], "T-1", tmp_path)
    assert first.returncode == 0 and "ROUND=1" in first.stdout, first.stderr
    assert "train: holding main for T-1" in first.stderr
    before = _ledger_snapshot(lanes["repo"])

    second = _run(lanes["T-2"], "T-2", tmp_path)

    assert second.returncode == review_run.EXIT_TRAIN == 6, second.stderr
    assert "train: waiting behind T-1" in second.stderr
    assert "no round reserved" in second.stderr
    assert _ledger_snapshot(lanes["repo"]) == before
    assert _train(lanes["T-1"], "release", "--ticket", "T-1") == 0
    third = _run(lanes["T-2"], "T-2", tmp_path)
    assert third.returncode == 0 and "ROUND=1" in third.stdout, third.stderr


def test_unreadable_train_refuses_the_round(lanes, tmp_path):
    assert _train(lanes["repo"], "arm") == 0
    state = pathlib.Path(crew_train.train_dir(str(lanes["repo"]))) / "state.json"
    state.write_text("{not json", encoding="utf-8")
    before = _ledger_snapshot(lanes["repo"])

    done = _run(lanes["T-1"], "T-1", tmp_path)

    assert done.returncode == 6, done.stderr
    assert "train: could not tell" in done.stderr and "no round reserved" in done.stderr
    assert _ledger_snapshot(lanes["repo"]) == before


def test_train_step_follows_the_clean_receipt_and_the_verify_gate(lanes, tmp_path,
                                                                    monkeypatch, capsys):
    assert _train(lanes["repo"], "arm") == 0
    assert _run(lanes["T-1"], "T-1", tmp_path).returncode == 0
    (lanes["T-2"] / ".crew").mkdir(exist_ok=True)
    (lanes["T-2"] / ".crew" / "verify.json").write_text('{"rules": []}', encoding="utf-8")

    red = _run(lanes["T-2"], "T-2", tmp_path)

    assert red.returncode == review_run.EXIT_UNVERIFIED, red.stderr
    assert "train" not in red.stderr
    monkeypatch.setattr(review_ledger, "check_receipt", lambda root, t: (True, "fixture"))
    monkeypatch.setattr(review_ledger, "_load",
                        lambda path: ({"receipt": {"kind": "clean"}}, "ok"))
    scratch = tmp_path / "s-clean"
    scratch.mkdir()
    code = review_run.main(["--root", str(lanes["T-2"]), "--ticket", "T-2", "--scratch",
                            str(scratch), "--provider", "claude", "--reserve-only"])
    assert code == 0 and "ALREADY_CLEAN=1" in capsys.readouterr().out


def test_train_crash_refuses_never_reserves(lanes, tmp_path, monkeypatch, capsys):
    assert _train(lanes["repo"], "arm") == 0
    before = _ledger_snapshot(lanes["repo"])

    def boom(*_args, **_kwargs):
        raise RuntimeError("fixture crash")
    monkeypatch.setattr(crew_train, "acquire", boom)
    scratch = tmp_path / "s-crash"
    scratch.mkdir()
    _bundle(lanes["T-1"], "T-1", scratch)
    code = review_run.main(["--root", str(lanes["T-1"]), "--ticket", "T-1", "--scratch",
                            str(scratch), "--provider", "claude", "--reserve-only"])

    assert code == 6
    assert "fixture crash" in capsys.readouterr().err
    assert _ledger_snapshot(lanes["repo"]) == before


# --- L-0526 review round 1: budget first, and the train before the later gates ---------------

def _entries(repo):
    state, where, why = crew_train.load(str(repo))
    assert where == "ok", why
    return {(e["ticket"], e["state"]) for e in state["entries"]}


def _spend_budget(lanes, tmp_path):
    """T-1 reserves both rounds while holding the train, then releases it."""
    for number in (1, 2):
        done = _run(lanes["T-1"], "T-1", tmp_path)
        assert done.returncode == 0 and f"ROUND={number}" in done.stdout, done.stderr
    assert review_ledger.status(str(lanes["T-1"]), "T-1").get("rounds_left") == 0
    assert _train(lanes["T-1"], "release", "--ticket", "T-1") == 0


def test_a_spent_budget_is_refused_without_taking_the_train(lanes, tmp_path):
    assert _train(lanes["repo"], "arm") == 0
    _spend_budget(lanes, tmp_path)

    spent = _run(lanes["T-1"], "T-1", tmp_path)

    assert spent.returncode == review_run.EXIT_REFUSED == 4, spent.stderr
    assert "train" not in spent.stderr
    assert ("T-1", "holding") not in _entries(lanes["repo"])
    other = _run(lanes["T-2"], "T-2", tmp_path)
    assert other.returncode == 0 and "ROUND=1" in other.stdout, other.stderr


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a POSIX FIFO")
def test_a_train_state_that_is_a_fifo_refuses_and_never_blocks(lanes, tmp_path):
    """Review of 84c841e6: a FIFO state.json with no writer would block
    crew_train's plain open forever; the gate round refuses (exit 6) instead."""
    assert _train(lanes["repo"], "arm") == 0
    state = pathlib.Path(crew_train.train_dir(str(lanes["T-1"]))) / "state.json"
    state.unlink()
    os.mkfifo(state)

    refused = _run(lanes["T-1"], "T-1", tmp_path)

    assert refused.returncode == review_run.EXIT_TRAIN == 6, refused.stderr
    assert "is not a regular file" in refused.stderr


def test_an_unreadable_ledger_is_refused_without_taking_the_train(lanes, tmp_path):
    """Review of ee01a3ca: a corrupt ledger reads UNKNOWN, `reserve` refuses it
    (exit 4), so it must not take the train first and hold it."""
    assert _train(lanes["repo"], "arm") == 0
    path = pathlib.Path(review_ledger.ledger_path(str(lanes["T-1"]), "T-1"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    refused = _run(lanes["T-1"], "T-1", tmp_path)

    assert refused.returncode == review_run.EXIT_REFUSED == 4, refused.stderr
    assert ("T-1", "holding") not in _entries(lanes["repo"])


def test_an_unreadable_ledger_is_answered_before_the_later_checks(lanes, tmp_path, monkeypatch,
                                                                 capsys):
    """Review of 6ec829c9: the pre-review checks and the standards self-check
    are skipped for an unreadable ledger as for a spent one, so the ledger
    refusal (exit 4) is what the author sees, not an unrelated check."""
    assert _train(lanes["repo"], "arm") == 0
    later = []
    monkeypatch.setattr(review_ledger, "status",
                        lambda root, ticket: {"state": review_ledger.UNKNOWN})
    monkeypatch.setattr(review_run, "prereview_gate", lambda a: later.append("pre") or 5)
    monkeypatch.setattr(review_run, "standards_gate", lambda a: later.append("std") or 2)
    monkeypatch.setattr(review_ledger, "reserve",
                        lambda *a, **k: (False, None, "refused: ledger is corrupt"))
    scratch = tmp_path / "s-unknown"
    scratch.mkdir()
    code = review_run.main(["--root", str(lanes["T-1"]), "--ticket", "T-1", "--scratch",
                            str(scratch), "--provider", "claude", "--reserve-only"])

    assert (code, later) == (4, [])
    assert "train" not in capsys.readouterr().err


def test_a_needs_replan_ticket_never_calls_acquire(lanes, tmp_path, monkeypatch, capsys):
    assert _train(lanes["repo"], "arm") == 0
    called = []
    monkeypatch.setattr(crew_train, "acquire", lambda *a, **k: called.append(a) or (0, []))
    monkeypatch.setattr(review_ledger, "status",
                        lambda root, ticket: {"state": review_ledger.NEEDS_REPLAN})
    monkeypatch.setattr(review_ledger, "reserve",
                        lambda *a, **k: (False, None, "refused: NEEDS_REPLAN"))
    scratch = tmp_path / "s-replan"
    scratch.mkdir()
    code = review_run.main(["--root", str(lanes["T-1"]), "--ticket", "T-1", "--scratch",
                            str(scratch), "--provider", "claude", "--reserve-only"])

    assert code == 4 and called == []
    assert "train" not in capsys.readouterr().err


def _approve(top, ticket):
    path = pathlib.Path(crew_train.crew_ticket.approval_path(str(top), ticket))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ticket": ticket, "approved_by": "fixture"}), encoding="utf-8")


def test_the_train_answers_before_the_pre_review_checks(lanes, tmp_path):
    """T-2 has no bundle, so the pre-review checks would refuse it (exit 5,
    COULD NOT CHECK); waiting for the train is said first."""
    assert _train(lanes["repo"], "arm") == 0
    assert _run(lanes["T-1"], "T-1", tmp_path).returncode == 0
    scratch = tmp_path / "s-nobundle"
    scratch.mkdir()

    done = subprocess.run(
        [sys.executable, _RUN, "--root", str(lanes["T-2"]), "--ticket", "T-2", "--scratch",
         str(scratch), "--provider", "claude", "--reserve-only"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120)

    assert done.returncode == 6, done.stderr
    assert "waiting behind T-1" in done.stderr and "pre-review" not in done.stderr


def test_the_train_answers_before_the_standards_self_check(lanes, tmp_path):
    """T-2 is approved with no self-check, so the standards gate would refuse
    it (exit 2); waiting for the train is said first."""
    assert _train(lanes["repo"], "arm") == 0
    assert _run(lanes["T-1"], "T-1", tmp_path).returncode == 0
    _approve(lanes["T-2"], "T-2")

    done = _run(lanes["T-2"], "T-2", tmp_path)

    assert done.returncode == 6, done.stderr
    assert "waiting behind T-1" in done.stderr and "self-check:" not in done.stderr
    assert _train(lanes["T-1"], "release", "--ticket", "T-1") == 0
    assert _run(lanes["T-2"], "T-2", tmp_path).returncode == review_run.EXIT_USAGE


def test_the_claude_second_call_records_without_asking_the_train(lanes, tmp_path):
    assert _train(lanes["repo"], "arm") == 0
    assert _run(lanes["T-1"], "T-1", tmp_path).returncode == 0
    assert _train(lanes["T-1"], "release", "--ticket", "T-1") == 0
    assert _run(lanes["T-2"], "T-2", tmp_path).returncode == 0
    scratch = tmp_path / "scratch-T-1"
    (scratch / "out.txt").write_text("CLEAN\n", encoding="utf-8")

    done = subprocess.run(
        [sys.executable, _RUN, "--root", str(lanes["T-1"]), "--ticket", "T-1", "--scratch",
         str(scratch), "--provider", "claude", "--round", "1", "--output",
         str(scratch / "out.txt"), "--exit-code", "0"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, timeout=120)

    assert done.returncode != review_run.EXIT_TRAIN, done.stderr
    assert "train" not in done.stderr


def test_the_probe_never_reaches_the_train(lanes, tmp_path, monkeypatch, capsys):
    assert _train(lanes["repo"], "arm") == 0

    def boom(*_args, **_kwargs):
        raise AssertionError("the probe asked the train")
    monkeypatch.setattr(crew_train, "load", boom)
    monkeypatch.setattr(crew_train, "acquire", boom)
    monkeypatch.setattr(review_run, "probe", lambda args: (review_run.PROBE_OK, "fixture"))
    scratch = tmp_path / "s-probe"
    scratch.mkdir()
    code = review_run.main(["--root", str(lanes["T-1"]), "--ticket", "T-1", "--scratch",
                            str(scratch), "--provider", "codex", "--probe"])

    assert code == 0 and "PROBE=ok" in capsys.readouterr().out
