"""`review_run.py` refuses to reserve a review round without a current
standards self-check (T-0085).

The refusal comes BEFORE `review_ledger.reserve`, so a refused round spends
nothing: every must-block case snapshots the ledger directory under the
throwaway repo's git-common-dir and asserts it byte-identical afterwards. The
gate applies to a ticket with an approval receipt (the precondition of
/crew:implement and /crew:fix); the fixture writes one into the throwaway
repo's own git state. Every repository here lives under pytest's tmp_path.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_incident
import crew_standards as cs
import crew_ticket
import review_ledger as rl
import scope_base
from review_fixtures import env_with_path, fake_reviewer_bin, git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")
TICKET = "T-1"


def _approve(repo):
    path = crew_ticket.approval_path(str(repo), TICKET)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ticket": TICKET, "approved_by": "fixture"}, fh)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    repo = init_repo(tmp_path / "r")
    scope_base.record(str(repo), TICKET)
    _approve(repo)
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    return repo


def _bundle(repo, scratch):
    base = scope_base.resolve(str(repo), TICKET)[0]
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]),
        encoding="utf-8")


_EDITS_AFTER_STAMPING = {
    "drop-row": (lambda t: re.sub(r"^\| GEN-03 .*\n", "", t, flags=re.M), "GEN-03: no row"),
    "placeholder": (lambda t: re.sub(r"^\| GEN-03 \| n/a \| .*\|$", "| GEN-03 | n/a | TBD |",
                                     t, flags=re.M), "GEN-03: n/a needs a reason"),
    "bad-status": (lambda t: t.replace("| GEN-03 | n/a |", "| GEN-03 | maybe |"),
                   "GEN-03: status 'maybe' is not addressed or n/a"),
    "new-reason": (lambda t: re.sub(r"^\| GEN-03 \| n/a \| .*\|$",
                                    "| GEN-03 | n/a | one text file, no shared state |",
                                    t, flags=re.M), None),
}


def _selfcheck(repo, state="current", edit=None):
    """missing | unreadable | incomplete | unstamped | current |
    stamped-then-edited (stamp a complete record, then apply `edit`, one of
    `_EDITS_AFTER_STAMPING`: `.work/` is outside the bundle, so the stamp
    stays current and only the gate's completeness re-check can see it)."""
    path = repo / ".work" / "tickets" / TICKET / "selfcheck.md"
    if state == "missing":
        return path
    if state == "unreadable":
        path.mkdir(parents=True)
        return path
    assert cs.init(str(repo), TICKET)[0] == 0
    text = re.sub(r"^\| ([A-Z]+-\d\d) \|  \|  \|$",
                  r"| \1 | n/a | the fixture change is one text file |",
                  path.read_text(encoding="utf-8"), flags=re.M)
    if state == "incomplete":
        text = re.sub(r"^\| GEN-03 .*\n", "", text, flags=re.M)
    path.write_text(text, encoding="utf-8")
    if state in ("current", "stamped-then-edited"):
        code, lines = cs.stamp(str(repo), TICKET)
        assert code == 0, lines
    if state == "stamped-then-edited":
        edited = _EDITS_AFTER_STAMPING[edit][0](path.read_text(encoding="utf-8"))
        assert edited != path.read_text(encoding="utf-8"), edit
        path.write_text(edited, encoding="utf-8")
    return path


def _ledger_snapshot(repo):
    common = git(repo, "rev-parse", "--git-common-dir")
    base = os.path.join(repo if not os.path.isabs(common) else "", common, "crew", "review")
    found = {}
    for dirpath, _, names in os.walk(base):
        for name in names:
            with open(os.path.join(dirpath, name), "rb") as fh:
                found[os.path.join(dirpath, name)] = fh.read()
    return found


def _run(repo, scratch, fakes, provider, *extra):
    argv = [sys.executable, _RUN, "--root", str(repo), "--ticket", TICKET,
            "--scratch", str(scratch), "--provider", provider] + list(extra)
    return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False, env=env_with_path(fakes, FAKE_REVIEWER_MODE="clean"),
                          timeout=120)


_PROVIDERS = {"codex": (), "claude": ("--reserve-only",)}


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
@pytest.mark.parametrize("state", ["missing", "unreadable", "incomplete", "unstamped"])
def test_run_refuses_before_reserve_without_selfcheck(repo, tmp_path, provider, state):
    _selfcheck(repo, state)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, fakes, provider, *_PROVIDERS[provider])

    assert (result.returncode, "review-run: self-check" in result.stderr,
            "crew_standards.py stamp --root . --ticket T-1" in result.stderr,
            _ledger_snapshot(repo) == before, rl.status(str(repo), TICKET)["rounds_used"]) == (
        2, True, True, True, 0), result.stderr


_STALE_BY = {"edit-a-file": "the change moved after stamping",
             "change-the-overlay": "the standards set changed since stamping"}


@pytest.mark.parametrize("change", sorted(_STALE_BY))
def test_run_refuses_stale_selfcheck(repo, tmp_path, change):
    if change == "change-the-overlay":
        # Keep the overlay out of the bundle, so only the standards digest
        # can see this change: the case tests that binding and no other.
        exclude = os.path.join(str(repo), git(repo, "rev-parse", "--git-path", "info/exclude"))
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as fh:
            fh.write(".crew/\n")
    _selfcheck(repo)
    if change == "edit-a-file":
        (repo / "change.txt").write_text("changed after stamping\n", encoding="utf-8")
    else:
        (repo / ".crew").mkdir(exist_ok=True)
        (repo / ".crew" / "standards.md").write_text(
            '---\nset: REPO\napplies-to: ["**"]\n---\n\n## REPO-01 Local\n\n**Rule.** r\n\n'
            "**Self-check.** s\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    assert (result.returncode, _STALE_BY[change] in result.stderr,
            _ledger_snapshot(repo) == before) == (2, True, True), result.stderr


def test_run_reserves_with_current_selfcheck(repo, tmp_path):
    _selfcheck(repo)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    seal = cs.read_selfcheck(str(repo), TICKET)[1] or {}
    assert (result.returncode, result.stdout.strip(),
            f"std:{seal.get('standards', 'no-stamp')[:8]}" in result.stderr) == (0, "ROUND=1", True), (
        result.stderr)


def test_run_with_current_selfcheck_launches_codex(repo, tmp_path):
    _selfcheck(repo)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "codex", "--work-dir", str(tmp_path / "w"))

    assert result.returncode == 0, result.stdout + result.stderr


def test_run_stands_down_in_an_incident_and_logs_the_skip(repo, tmp_path):
    crew_incident.declare(str(repo), "prod is down")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    skips = [row for row in crew_incident.read_skips(str(repo))
             if "standards-selfcheck" in row]
    assert (result.returncode, result.stdout.strip(), len(skips)) == (0, "ROUND=1", 1), (
        result.stderr)


def test_run_without_an_approval_receipt_says_the_gate_does_not_apply(repo, tmp_path):
    os.remove(crew_ticket.approval_path(str(repo), TICKET))
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    assert (result.returncode, result.stdout.strip(),
            "standards self-check not required" in result.stderr) == (0, "ROUND=1", True)


def test_run_with_a_corrupt_approval_receipt_still_gates(repo, tmp_path):
    with open(crew_ticket.approval_path(str(repo), TICKET), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    assert (result.returncode, "review-run: self-check" in result.stderr) == (2, True)


def test_run_refuses_an_unreadable_manifest(repo, tmp_path):
    _selfcheck(repo)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    (scratch / "manifest.json").write_text("{", encoding="utf-8")
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    assert (result.returncode, "manifest" in result.stderr,
            rl.status(str(repo), TICKET)["rounds_used"]) == (2, True, 0)


_REFUSING_EDITS = sorted(k for k, v in _EDITS_AFTER_STAMPING.items() if v[1])


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
@pytest.mark.parametrize("edit", _REFUSING_EDITS)
def test_run_refuses_a_selfcheck_edited_after_stamping(repo, tmp_path, provider, edit):
    _selfcheck(repo, "stamped-then-edited", edit)
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, fakes, provider, *_PROVIDERS[provider])

    own = f"review-run: self-check: {_EDITS_AFTER_STAMPING[edit][1]}"
    assert (result.returncode, own in result.stderr, _ledger_snapshot(repo) == before) == (
        2, True, True), result.stderr


def test_run_reserves_after_an_edit_that_keeps_the_record_complete(repo, tmp_path):
    _selfcheck(repo, "stamped-then-edited", "new-reason")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    assert (result.returncode, result.stdout.strip()) == (0, "ROUND=1"), result.stderr


_SOUND_OVERLAY = ('---\nset: REPO\napplies-to: ["**"]\n---\n\n## REPO-01 Local\n\n**Rule.** r\n\n'
                  "**Self-check.** s\n")


def test_run_refuses_a_broken_effective_set(repo, tmp_path):
    overlay = repo / ".crew" / "standards.md"
    overlay.parent.mkdir(exist_ok=True)
    overlay.write_text(_SOUND_OVERLAY, encoding="utf-8")
    _selfcheck(repo)
    overlay.write_bytes(b"---\nset: REPO\napplies-to: [\"**\"]\n---\n\xff\xfe\n")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    before = _ledger_snapshot(repo)

    result = _run(repo, scratch, fakes, "claude", "--reserve-only")

    assert (result.returncode, "review-run: self-check: .crew/standards.md: not UTF-8" in
            result.stderr, _ledger_snapshot(repo) == before) == (2, True, True), result.stderr


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
@pytest.mark.parametrize("spent", ["budget-spent", "needs-replan"])
def test_run_reports_a_spent_budget_before_the_selfcheck(repo, tmp_path, provider, spent):
    for _ in range(2):
        assert rl.reserve(str(repo), TICKET, "claude")[0]
    if spent == "needs-replan":
        assert not rl.reserve(str(repo), TICKET, "claude")[0]
    _selfcheck(repo, "missing")
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, provider, *_PROVIDERS[provider])

    assert (result.returncode, "review budget exhausted" in result.stderr,
            "self-check" in result.stderr, rl.status(str(repo), TICKET)["state"]) == (
        4, True, False, rl.NEEDS_REPLAN), result.stderr


_VERIFY_MAP = {"version": 1,
               "rules": [{"paths": ["**"], "seconds": 1, "run": ["echo RAN-ok"], "why": "fixture"}],
               "default": [], "unmapped": "ignore"}


@pytest.mark.parametrize("case", ["clean-receipt", "unverified-gate"])
def test_preflight_answers_before_the_selfcheck_is_asked_for(repo, tmp_path, case):
    """Owner decision 2026-09-30 ("Preflight first"): main's preflight runs
    first. A CLEAN receipt covering the bundle answers CLEAN with no round and
    no self-check; a tree the verify gate has not passed is refused with exit 5
    before the self-check is asked for."""
    if case == "clean-receipt":
        _selfcheck(repo)
        first_scratch = tmp_path / "first"
        _bundle(repo, first_scratch)
        assert _run(repo, first_scratch, fake_reviewer_bin(tmp_path / "bin0"), "codex",
                    "--work-dir", str(tmp_path / "w0")).returncode == 0
        os.remove(repo / ".work" / "tickets" / TICKET / "selfcheck.md")
    else:
        _selfcheck(repo, "missing")
        (repo / ".crew").mkdir(exist_ok=True)
        (repo / ".crew" / "verify.json").write_text(json.dumps(_VERIFY_MAP), encoding="utf-8")
    rounds = rl.status(str(repo), TICKET)["rounds_used"]
    scratch = tmp_path / "scratch"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")

    result = _run(repo, scratch, fakes, "codex", "--work-dir", str(tmp_path / "w"))

    expected = (0, True) if case == "clean-receipt" else (5, True)
    marker = ("CLEAN from the existing receipt" in result.stdout if case == "clean-receipt"
              else "gate UNVERIFIED" in result.stderr)
    assert (result.returncode, marker, "self-check" in result.stderr,
            rl.status(str(repo), TICKET)["rounds_used"]) == (*expected, False, rounds), (
        result.stdout + result.stderr)
