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


def _selfcheck(repo, state="current"):
    """missing | unreadable | incomplete | unstamped | current."""
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
    if state == "current":
        code, lines = cs.stamp(str(repo), TICKET)
        assert code == 0, lines
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

    _, seal, _ = cs.read_selfcheck(str(repo), TICKET)
    assert (result.returncode, result.stdout.strip(),
            f"std:{seal['standards'][:8]}" in result.stderr) == (0, "ROUND=1", True), (
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
