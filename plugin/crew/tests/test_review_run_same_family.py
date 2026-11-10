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


@pytest.mark.parametrize("extra", [
    ("--reserve-only",),
    ("--reserve-only", "--round", "1"),
    ("--reserve-only", "--round", "7"),
])
def test_every_claude_reservation_with_no_authors_is_refused(setup, extra):
    """Round 5 BLOCK: --round beside --reserve-only still reserves, so it
    exempts nothing from the no-authors guard."""
    result = _run(setup, "claude", *extra)

    assert (result.returncode, "no --authors given" in result.stderr,
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, True, 0), result.stderr


def test_the_recording_call_with_no_authors_still_records_its_round(setup):
    repo, scratch, _, _ = setup
    _run(setup, "claude", "--reserve-only", "--authors", "gpt")
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['path']}\n" for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]) + "CLEAN\n",
        encoding="utf-8")

    done = _run(setup, "claude", "--round", "1", "--output", str(scratch / "out.txt"),
                "--exit-code", "0")

    assert (done.returncode, rl.status(str(repo), "T1")["rounds"][0]["status"]) == (
        0, "completed"), done.stdout + done.stderr


def _ledger_cli(setup, *args):
    return subprocess.run([sys.executable, os.path.join(_SCRIPTS, "review_ledger.py"),
                           "--root", str(setup[0]), "--ticket", "T1"] + list(args),
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False, timeout=60)


@pytest.mark.parametrize("args", [
    ("--reserve",),
    ("--reserve", "--provider", "claude"),
    ("--reserve", "--provider", "claude", "--authors", "claude"),
    ("--reserve", "--provider", "codex", "--authors", "gpt"),
    ("--reserve", "--provider", "codex", "--authors", "claude", "--author-source", "unknown"),
])
def test_the_ledger_cli_reservation_asks_the_same_family_guard(setup, args):
    result = _ledger_cli(setup, *args)

    assert (result.returncode, "same-family:" in result.stderr,
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (2, True, 0), result.stderr


@pytest.mark.parametrize("args,labelled", [
    (("--reserve", "--authors", "gpt"), False),
    (("--reserve", "--same-family", "operator chose it"), True),
])
def test_the_ledger_cli_reserves_a_cross_family_or_labelled_round(setup, args, labelled):
    result = _ledger_cli(setup, *args)

    row = rl.status(str(setup[0]), "T1")["rounds"][0]
    assert (result.returncode, row.get("same_family") is True) == (0, labelled), result.stderr


@pytest.mark.parametrize("reason", ["", " ", "two\nlines"])
def test_a_bad_same_family_reason_on_the_ledger_cli_is_a_handled_refusal(setup, reason):
    result = _ledger_cli(setup, "--reserve", "--same-family", reason)

    assert (result.returncode, "Traceback" in result.stderr,
            result.stderr.startswith("review-ledger:"),
            rl.status(str(setup[0]), "T1")["rounds_used"]) == (1, False, True, 0), result.stderr


def test_the_ledger_cli_takes_family_flags_only_with_reserve(setup):
    result = _ledger_cli(setup, "--status", "--authors", "gpt")

    assert result.returncode == 2


def test_a_same_family_round_is_named_so_in_the_metrics_row(setup):
    import review_metrics  # pylint: disable=import-outside-toplevel
    repo = setup[0]

    result = _run(setup, "codex", "--authors", "gpt", "--same-family", "chosen")

    path, problem = review_metrics.metrics_path(str(repo))
    with open(path, encoding="utf-8") as fh:
        last = fh.read().splitlines()[-1]
    assert (bool(problem), "same-family: operator choice" in last) == (False, True), (
        result.stdout + result.stderr + last)


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


# ---- `--resolve-run`: the probe is resolve_role's `available` ----------------
# (Until L-0726 this ran review.md's one-line `python3 -c` in bash.)


def _resolve(tmp_path, qa, probe_status, authors="claude"):
    """(parsed KEY=VALUE lines, completed process) of `review_run.py --resolve-run`."""
    repo = init_repo(tmp_path / "fb")
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "config.json").write_text(json.dumps({"qa": qa}), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "models.json").write_text(json.dumps({
        "qaProviders": {"codex": {"model": "gpt-6-astra"}, "kimi": {"model": "k3"}},
        "qaFallThrough": []}), encoding="utf-8")
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
         "--resolve-run", "--probe-status", str(probe_status), "--model", "gpt-6-astra",
         "--authors", authors, "--author-source", "config"],
        cwd=str(repo), capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        env=env, timeout=60)
    keys = dict(line.split("=", 1) for line in result.stdout.splitlines()
                if "=" in line and line.split("=", 1)[0].isupper())
    return keys, result


def _qa(fallback, order=("codex", "kimi", "copilot", "claude")):
    return {"provider": "auto", "order": list(order), "fallback": fallback,
            "codex": {"model": "gpt-6-astra"}, "kimi": {"model": "k3"},
            "roles": {"review": {"provider": "codex", "model": "gpt-6-astra"}}}


_ALL = ("codex", "kimi", "copilot", "claude")


@pytest.mark.parametrize("fallback,order,probe,fell,provider,model", [
    ("gpt-6.1-sol", _ALL, 6, "codex gpt-6.1-sol", "codex", "gpt-6.1-sol"),
    ("claude-sonnet-5", _ALL, 6, "kimi k3", "kimi", "k3"),
    ("claude-sonnet-5", ("codex", "claude"), 6, "INCOMPLETE", "", ""),
    # A limit (5) or no answer (7) is all of codex: a gpt fallback never lands on it.
    ("gpt-6.1-sol", _ALL, 5, "kimi k3", "kimi", "k3"),
    ("gpt-6.1-sol", _ALL, 7, "kimi k3", "kimi", "k3"),
])
def test_resolve_run_dispatches_the_resolved_fallback(tmp_path, fallback, order, probe, fell,
                                                      provider, model):
    keys, result = _resolve(tmp_path, _qa(fallback, order), probe)

    assert (keys["FALLBACK"], keys["RUN_PROVIDER"], keys["RUN_MODEL"]) == (
        fell, provider, model), result.stdout + result.stderr


@pytest.mark.parametrize("fallback,order,probe,launched", [
    ("gpt-6.1-sol", _ALL, 6, "codex gpt-6.1-sol"),
    ("claude-sonnet-5", _ALL, 6, "kimi k3"),
    ("gpt-6.1-sol", _ALL, 5, "kimi k3"),
    ("gpt-6.1-sol", _ALL, 0, "codex gpt-6-astra"),
    # No 2a reviewer (INCOMPLETE, or a probe error): nothing is launched, never Codex.
    ("claude-sonnet-5", ("codex", "claude"), 6, ""),
    ("gpt-6.1-sol", _ALL, 1, ""),
])
def test_resolve_run_launches_the_resolved_provider(tmp_path, fallback, order, probe, launched):
    keys, result = _resolve(tmp_path, _qa(fallback, order), probe)

    got = f"{keys['RUN_PROVIDER']} {keys['RUN_MODEL']}".strip()
    nxt = [line for line in result.stdout.splitlines() if line.startswith("next:")]
    assert got == launched, result.stdout + result.stderr
    assert len(nxt) == 1
    if launched:
        provider, model = launched.split()
        assert f"--provider {provider} --model {model} " in nxt[0]
    else:
        assert "--provider codex" not in nxt[0] and "--no-reviewer" in nxt[0]


@pytest.mark.parametrize("probe", [0, 1, 2])
def test_resolve_run_names_no_fallback_unless_the_probe_said_unavailable(tmp_path, probe):
    keys, result = _resolve(tmp_path, _qa("gpt-6.1-sol"), probe)

    assert "FALLBACK" not in keys, result.stdout + result.stderr
    assert keys["RUN_PROVIDER"] == ("codex" if probe == 0 else "")


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
