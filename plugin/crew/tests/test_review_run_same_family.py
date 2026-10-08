"""L-0712: review_run.py's family guard. A reviewer of the author's family
(or one whose family cannot be told) is refused before anything is reserved,
unless the operator passes `--same-family <reason>`, which labels the round.
Every case runs against a throwaway repo under tmp_path with a fake codex."""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_fixtures
import review_ledger as rl
from review_fixtures import env_with_path, fake_reviewer_bin, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")


@pytest.fixture(name="setup")
def _setup(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    review_fixtures.bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    return repo, scratch, fakes, tmp_path / "work"


def _run(setup, provider, *extra):
    repo, scratch, fakes, work = setup
    argv = [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch",
            str(scratch), "--provider", provider, "--work-dir", str(work)] + list(extra)
    return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False, env=env_with_path(fakes, FAKE_REVIEWER_MODE="clean"),
                          timeout=120)


@pytest.mark.parametrize("provider,extra,authors", [
    ("claude", ("--reserve-only",), "claude"),
    ("codex", (), "gpt"),
    ("codex", (), "claude gpt"),
])
def test_an_author_family_reviewer_is_refused_with_no_round_spent(setup, provider, extra,
                                                                  authors):
    result = _run(setup, provider, *extra, "--authors", authors)

    assert (result.returncode, "review-run: same-family:" in result.stderr,
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, True, 0), result.stderr


def test_an_empty_authors_is_could_not_tell_and_refused(setup):
    result = _run(setup, "codex", "--authors", "")

    assert (result.returncode, "could not tell" in result.stderr,
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, True, 0), result.stderr


def test_a_cross_family_reviewer_runs_unlabelled(setup):
    result = _run(setup, "codex", "--authors", "claude")

    row = rl.status(str(setup[0]), "T1")["rounds"][0]
    assert (result.returncode, row["status"], "same_family" in row) == (0, "completed", False), (
        result.stdout + result.stderr)


def test_an_explicit_same_family_choice_runs_and_is_labelled(setup):
    reserved = _run(setup, "claude", "--reserve-only", "--authors", "claude",
                    "--same-family", "codex limit")

    row = rl.status(str(setup[0]), "T1")["rounds"][0]
    assert (reserved.returncode, row["same_family"], row["same_family_reason"]) == (
        0, True, "codex limit"), reserved.stderr


def test_a_same_family_clean_round_labels_review_json_and_receipt(setup):
    repo, scratch, _, work = setup
    _run(setup, "claude", "--reserve-only", "--authors", "claude", "--same-family", "chosen")
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['path']}\n" for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]) + "CLEAN\n",
        encoding="utf-8")

    done = _run(setup, "claude", "--round", "1", "--output", str(scratch / "out.txt"),
                "--exit-code", "0")

    review = json.loads((work / "review.json").read_text(encoding="utf-8"))
    receipt = rl.status(str(repo), "T1")["receipt"] or {}
    assert (review["verdict"], review["same_family"], receipt.get("same_family")) == (
        "CLEAN", True, True), done.stdout + done.stderr
    assert "SAME-FAMILY by the operator's choice" in done.stdout


def test_same_family_on_a_cross_family_reviewer_is_ignored_and_said(setup):
    result = _run(setup, "codex", "--authors", "claude", "--same-family", "habit")

    row = rl.status(str(setup[0]), "T1")["rounds"][0]
    assert ("--same-family ignored" in result.stderr, "same_family" in row) == (True, False)


def test_an_empty_same_family_reason_is_refused_before_anything_is_reserved(setup):
    result = _run(setup, "claude", "--reserve-only", "--authors", "claude",
                  "--same-family", " ")

    assert (result.returncode, rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, 0)
