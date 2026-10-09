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
import crew_fixtures
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


def test_an_unknown_author_source_is_could_not_tell_and_refused(setup):
    result = _run(setup, "codex", "--authors", "claude", "--author-source", "unknown")

    assert (result.returncode, "author source is `unknown`" in result.stderr,
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, True, 0), result.stderr


def test_no_authors_runs_but_says_the_guard_was_not_applied(setup):
    result = _run(setup, "codex")

    assert (result.returncode, "family guard NOT applied" in result.stderr) == (0, True)


def test_a_claude_reservation_with_no_authors_is_refused_with_no_round_spent(setup):
    result = _run(setup, "claude", "--reserve-only")

    assert (result.returncode, "no --authors given" in result.stderr,
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, True, 0), result.stderr


def test_a_claude_reservation_with_no_authors_runs_labelled_on_same_family(setup):
    result = _run(setup, "claude", "--reserve-only", "--same-family", "operator chose it")

    row = rl.status(str(setup[0]), "T1")["rounds"][0]
    assert (result.returncode, row.get("same_family")) == (0, True), result.stderr


def test_the_probe_asks_the_family_guard_before_calling_codex(setup):
    _, _, fakes, _ = setup

    result = _run(setup, "codex", "--probe", "--authors", "gpt")

    assert (result.returncode, "review-run: same-family:" in result.stderr,
            os.path.exists(os.path.join(str(fakes), "calls.txt"))) == (2, True, False)


def _status_line(repo, ticket="T1"):
    import crew_status  # pylint: disable=import-outside-toplevel
    return next(line for line in crew_status._review_lines(str(repo))  # pylint: disable=protected-access
                if line.startswith(f"review   {ticket}:"))


def test_status_shows_a_no_reviewer_outcome_on_the_ticket_line(setup):
    rl.no_reviewer(str(setup[0]), "T1", "no cross-family provider")

    assert "1 with no reviewer (INCOMPLETE, refunded)" in _status_line(setup[0])


# ---- review.md's fallback line: the probe is resolve_role's `available` -----

_REVIEW_MD = os.path.join(context._ROOT, "commands", "review.md")  # pylint: disable=protected-access


def _fallback_line():
    with open(_REVIEW_MD, encoding="utf-8") as fh:
        return next(line for line in fh if line.startswith('case "$PROBE_STATUS" in'))


def _launch_lines():
    """Step 2a's own launch command, both lines, as review.md writes it."""
    with open(_REVIEW_MD, encoding="utf-8") as fh:
        lines = fh.readlines()
    at = next(i for i, line in enumerate(lines) if '--provider "$RUN_PROVIDER"' in line)
    return lines[at - 1] + lines[at]


_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="runs review.md's bash lines")


def _python3_shim(directory):
    """A `python3` on PATH that is this interpreter: Git Bash ships none, and a
    bare `bash` on a Windows runner is the WSL stub (CLAUDE.md, Landmines)."""
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / "python3"
    shim.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable.replace("\\", "/"),
                    encoding="utf-8", newline="\n")
    shim.chmod(0o755)
    return str(directory)


def _fallback(tmp_path, qa, probe_status, authors="claude"):
    repo = init_repo(tmp_path / "fb")
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "config.json").write_text(json.dumps({"qa": qa}), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    # A stand-in plugin root whose review_run.py prints the provider and model step 2a
    # launched, so a launch line that ignores the resolved fallback goes red here.
    fake = tmp_path / "fakeroot" / "hooks" / "scripts"
    fake.mkdir(parents=True, exist_ok=True)
    (fake / "review_run.py").write_text(
        "import sys\na = sys.argv\nprint('LAUNCH=[%s %s]' % (a[a.index('--provider') + 1], "
        "a[a.index('--model') + 1]))\nsys.exit(2 if not a[a.index('--provider') + 1] else 0)\n",
        encoding="utf-8")
    script = (f'PROBE_STATUS={probe_status}; QA_MODEL=gpt-6-astra; QA_KIMI_MODEL=; '
              f'AUTHORS="{authors}"\n' + _fallback_line()
              + f'CLAUDE_PLUGIN_ROOT="{(tmp_path / "fakeroot").as_posix()}"\n' + _launch_lines()
              + 'printf "FALLBACK=[%s] QA_MODEL=[%s] QA_KIMI_MODEL=[%s]\\n" "$FALLBACK" '
              '"$QA_MODEL" "$QA_KIMI_MODEL"\n')
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PATH=_python3_shim(tmp_path / "shim") + os.pathsep + os.environ.get("PATH", ""),
               CLAUDE_PLUGIN_ROOT=context._ROOT)  # pylint: disable=protected-access
    result = subprocess.run([_BASH, "-c", script], cwd=str(repo), capture_output=True,
                            text=True, stdin=subprocess.DEVNULL, check=False, env=env,
                            timeout=60)
    return result.stdout.rsplit("FALLBACK=", 1)[-1].strip(), result


def _qa(fallback, order=("codex", "kimi", "copilot", "claude")):
    return {"provider": "auto", "order": list(order), "fallback": fallback,
            "codex": {"model": "gpt-6-astra"}, "kimi": {"model": "k3"},
            "roles": {"review": {"provider": "codex", "model": "gpt-6-astra"}}}


_ALL = ("codex", "kimi", "copilot", "claude")


@needs_bash
@pytest.mark.parametrize("fallback,order,probe,expected", [
    ("gpt-6.1-sol", _ALL, 6, "[codex gpt-6.1-sol] QA_MODEL=[gpt-6.1-sol] QA_KIMI_MODEL=[]"),
    ("claude-sonnet-5", _ALL, 6, "[kimi k3] QA_MODEL=[gpt-6-astra] QA_KIMI_MODEL=[k3]"),
    ("claude-sonnet-5", ("codex", "claude"), 6,
     "[INCOMPLETE] QA_MODEL=[gpt-6-astra] QA_KIMI_MODEL=[]"),
    # A limit (5) or no answer (7) is all of codex: a gpt fallback never lands on it.
    ("gpt-6.1-sol", _ALL, 5, "[kimi k3] QA_MODEL=[gpt-6-astra] QA_KIMI_MODEL=[k3]"),
    ("gpt-6.1-sol", _ALL, 7, "[kimi k3] QA_MODEL=[gpt-6-astra] QA_KIMI_MODEL=[k3]"),
])
def test_review_md_dispatches_the_resolved_fallback(tmp_path, fallback, order, probe, expected):
    got, result = _fallback(tmp_path, _qa(fallback, order), probe)

    assert got == expected, result.stdout + result.stderr


@needs_bash
@pytest.mark.parametrize("fallback,order,probe,launched", [
    ("gpt-6.1-sol", _ALL, 6, "[codex gpt-6.1-sol]"),
    ("claude-sonnet-5", _ALL, 6, "[kimi k3]"),
    ("gpt-6.1-sol", _ALL, 5, "[kimi k3]"),
    ("gpt-6.1-sol", _ALL, 0, "[codex gpt-6-astra]"),
    # No 2a reviewer (INCOMPLETE, or a probe error): the launch is refused, never Codex.
    ("claude-sonnet-5", ("codex", "claude"), 6, "[ ]"),
    ("gpt-6.1-sol", _ALL, 1, "[ ]"),
])
def test_review_md_step_2a_launches_the_resolved_provider(tmp_path, fallback, order, probe,
                                                          launched):
    _, result = _fallback(tmp_path, _qa(fallback, order), probe)

    assert f"LAUNCH={launched}" in result.stdout, result.stdout + result.stderr


@needs_bash
@pytest.mark.parametrize("probe", [0, 1, 2])
def test_review_md_names_no_fallback_unless_the_probe_said_unavailable(tmp_path, probe):
    got, result = _fallback(tmp_path, _qa("gpt-6.1-sol"), probe)

    assert got == "[] QA_MODEL=[gpt-6-astra] QA_KIMI_MODEL=[]", result.stdout + result.stderr


@pytest.mark.parametrize("entries", [
    [{"verdict": "CLEAN", "refunded": False}],
    ["not an object"],
    {"verdict": "INCOMPLETE"},
    None,
])
def test_status_never_counts_a_malformed_no_reviewer_record_as_refunded(entries):
    import crew_status  # pylint: disable=import-outside-toplevel

    note = crew_status._unreviewed_note(entries)  # pylint: disable=protected-access

    assert note == ", no-reviewer record unreadable"


def test_an_owner_accepted_same_family_round_keeps_the_label(setup):
    repo, scratch, _, _ = setup
    _run(setup, "claude", "--reserve-only", "--authors", "claude", "--same-family", "chosen")
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['path']}\n" for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"])
        + "FIX|change.txt:1|a defect|read it\n", encoding="utf-8")
    _run(setup, "claude", "--round", "1", "--output", str(scratch / "out.txt"), "--exit-code", "0")

    receipt = rl.accept(str(repo), "T1", "owner")

    assert (receipt["kind"], receipt.get("same_family")) == ("owner-accepted", True)
