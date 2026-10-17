"""L-0796: the Stop gate prints one verdict line, then failures, and keeps the rest in a log.

The Stop hook used to print one line per rule for pricing, reach, deferral, tree
credit, env pinning and elapsed time, so the one or two real failures sat in
200+ identical lines every Stop. The quiet path (no --ci, --all or --verbose,
CREW_VERIFY_VERBOSE not 1) prints a verdict line, then every line that is not
gate-authored informational text, unchanged, and writes the whole verbose text
to `.crew/.verify-gate.log`.

What must hold, and what each test below pins:

* A failure, a "could not tell", an unmapped path, a lock back-off and any line
  the gate does not know are SHOWN. Classification is by emitting site, so a
  failing rule that prints text shaped like an informational line is still shown.
* An unwritable log degrades to the full text on stderr, never to silence.
* An unknown never reads as a pass: a deferred, skipped or reach-excluded rule is
  counted as NOT VERIFIED and is never in PASSED.
* Exit codes and the L-0733 stdout line are unchanged on every path.
* The unchanged-since-last-Stop line is per session and falls back to the full
  block whenever the state is missing, unreadable or for another session.

The oracle for "failures are verbatim" is a verbose run of the same fixture.
"""
import json
import os
import re
import signal
import subprocess
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_BASH = crew_fixtures.resolve_bash()
_T = crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

_BLOCKED = "VERIFY GATE: BLOCKED (exit 2)"
# What the verbose oracle holds that the quiet path is allowed to move to the log.
_INFO = re.compile(
    r"^(verify-gate: (rules\[\d+\] (priced |declared reach|requires a clean|is permanently)"
    r"|env pinned|COVERED by|PASSED on this exact tree|stop budget|\d+s  |\d+s total across"
    r"|\d+ of them (COVERED|PASSED)|\d+ command\(s\) passed on this exact tree"
    r"|NOT VERIFIED ON THIS TREE - )"
    r"|deferred to /crew:verify: )")
_OWED_SUMMARY = re.compile(r"^verify-gate: NOT VERIFIED ON THIS TREE - \d+ further obligation\(s\) owed by the record")

_BASE_MAP = {
    "version": 1,
    "rules": [
        {"paths": ["a.py"], "seconds": 5, "reach": "local", "run": ["echo RAN-cheap"], "why": "cheap"},
        {"paths": ["a.py"], "seconds": 90, "reach": "local", "run": ["echo RAN-big"], "why": "over budget"},
        {"paths": ["a.py"], "seconds": 5, "reach": "network", "run": ["echo RAN-remote"], "why": "remote"},
    ],
    "default": [],
    "unmapped": "ignore",
}


def _map_with(*extra_rules, unmapped="ignore", base=True):
    rules = (list(_BASE_MAP["rules"]) if base else []) + list(extra_rules)
    return {"version": 1, "rules": rules, "default": [], "unmapped": unmapped}


def _fail_rule(command, **kw):
    return dict({"paths": ["a.py"], "seconds": 3, "reach": "local", "run": [command], "why": "fails"}, **kw)


def _repo(tmp_path, verify_map):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root, check=True,
                   capture_output=True, text=True, timeout=_T)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(verify_map), encoding="utf-8")
    return root


def _run(root, *args, verbose="0", session: str | None = "s1", extra_env=None):
    env = crew_fixtures.isolated_home_env(root.parent / "home")
    env.update(CLAUDE_PROJECT_DIR=str(root), CREW_VERIFY_VERBOSE=verbose)
    env.update(extra_env or {})
    payload = json.dumps({"session_id": session}) if session is not None else "{}"
    return crew_fixtures.run_gate([_BASH, _SH, *args], input=payload, cwd=str(root), env=env,
                                  capture_output=True, text=True, check=False, timeout=_T)


def _lines(result):
    return result.stderr.splitlines()


def _log(root):
    return (root / ".crew" / ".verify-gate.log").read_text(encoding="utf-8")


def test_quiet_stop_prints_one_verdict_line(tmp_path):
    root = _repo(tmp_path, _map_with())

    result = _run(root)

    lines = _lines(result)
    assert result.returncode == 0
    assert lines[0].startswith(
        "verify-gate: FAILED 0 cmd | PASSED 1 cmd | NOT VERIFIED 2 item(s) (reach 1, over-budget 1, dirty tree 0, "
        "deferred 0, skipped 0, other 0) | credited 0 | budget ")
    assert lines[0].endswith("| detail: .crew/.verify-gate.log")
    assert result.stderr.count(".crew/.verify-gate.log") == 1
    for noisy in ("env pinned", "priced at", "total across", "declared reach", "RAN past"):
        assert noisy not in result.stderr
    assert "env pinned" in _log(root)
    assert "declared reach: network" in _log(root)


def test_failure_span_identical_to_verbose(tmp_path):
    body = "for i in $(seq 1 30); do echo body-line-$i; done; exit 1"
    root = _repo(tmp_path, _map_with(_fail_rule(body)))

    quiet = _run(root)
    verbose = _run(root, verbose="1")

    quiet_body = [ln for ln in _lines(quiet)[1:-1] if not _OWED_SUMMARY.match(ln)]
    verbose_kept = [ln for ln in _lines(verbose) if not _INFO.match(ln)]
    assert quiet.returncode == verbose.returncode == 2
    assert quiet_body == verbose_kept
    assert f"VERIFY FAILED: {body}" in quiet_body
    assert quiet_body.count("body-line-30") == 1
    assert "body-line-5" not in quiet_body
    assert quiet.stdout == verbose.stdout
    assert quiet.stdout.startswith(_BLOCKED)


def test_rule_output_resembling_info_line_is_not_demoted(tmp_path):
    decoys = [
        "verify-gate: PASSED on this exact tree in an earlier run - not re-run: decoy",
        "deferred to /crew:verify: decoy (9s)",
        "verify-gate: rules[7] priced at 9s, measured on this machine, below its declared 10s",
        "verify-gate: env pinned - ENV=unset",
    ]
    command = "; ".join(f"echo '{d}'" for d in decoys) + "; exit 1"
    root = _repo(tmp_path, _map_with(_fail_rule(command)))

    result = _run(root)

    assert result.returncode == 2
    for decoy in decoys:
        assert decoy in _lines(result)


def test_unknown_notice_line_still_prints(tmp_path):
    undeclared = {"paths": ["a.py"], "seconds": 5, "run": ["curl https://example.invalid/x"], "why": "undeclared reach"}
    root = _repo(tmp_path, _map_with(undeclared))

    result = _run(root)

    assert "declare no `reach`" in result.stderr
    assert "NOT VERIFIED" in _lines(result)[0]


def test_unwritable_log_degrades_to_full_output(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("exit 1")))
    (root / ".crew" / ".verify-gate.log").mkdir()

    result = _run(root)

    assert result.returncode == 2
    assert _lines(result)[0].endswith("| detail: unavailable")
    assert "verify-gate: env pinned" in result.stderr
    assert "VERIFY FAILED: exit 1" in result.stderr
    assert result.stderr.count("VERIFY FAILED: exit 1") == 1


def test_unchanged_repeat_with_unwritable_log_prints_failure_in_full(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("echo boom; exit 1")))
    (root / ".crew" / ".verify-gate.log").mkdir()

    first = _run(root)
    second = _run(root)

    assert first.returncode == second.returncode == 2
    assert "VERIFY FAILED: echo boom; exit 1" in second.stderr
    assert "unchanged since last Stop" not in second.stderr


def test_verbose_env_and_flag_restore_baseline_output(tmp_path):
    env_root = _repo(tmp_path / "env", _map_with())
    flag_root = _repo(tmp_path / "flag", _map_with())

    by_env = _run(env_root, verbose="1")
    by_flag = _run(flag_root, "--verbose", verbose="0")

    for result in (by_env, by_flag):
        assert result.returncode == 0
        assert "verify-gate: env pinned" in result.stderr
        assert "priced" in result.stderr or "declared reach" in result.stderr
        assert not result.stderr.startswith("verify-gate: FAILED")
        assert "detail:" not in result.stderr
    assert (re.sub(r"\d+s", "Ns", by_env.stderr).replace(str(env_root), "ROOT")
            == re.sub(r"\d+s", "Ns", by_flag.stderr).replace(str(flag_root), "ROOT"))
    assert not (env_root / ".crew" / ".verify-gate.log").exists()
    assert not (flag_root / ".crew" / ".verify-gate.log").exists()


@pytest.mark.parametrize("flag", ["--all", "--ci"])
def test_ci_all_price_stay_verbose(tmp_path, flag):
    root = _repo(tmp_path, _map_with())
    subprocess.run(("git", "add", "a.py"), cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    subprocess.run(("git", "commit", "-q", "-m", "track a.py"), cwd=root, check=True,
                   capture_output=True, text=True, timeout=_T)

    result = _run(root, flag)

    assert "verify-gate: env pinned" in result.stderr
    assert "| detail:" not in result.stderr
    assert not (root / ".crew" / ".verify-gate.log").exists()


def test_unchanged_same_session_prints_one_line_exit_2(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("echo boom; exit 1")))

    first = _run(root)
    second = _run(root)
    third = _run(root)

    assert first.returncode == second.returncode == third.returncode == 2
    assert _lines(first)[0].startswith("verify-gate: FAILED 1 cmd | ")
    assert _lines(second) == ["verify-gate: unchanged since last Stop (1 failing, 2 NOT VERIFIED): echo boom; exit 1"
                              " | detail: .crew/.verify-gate.log | /crew:verify --all runs every rule"]
    assert second.stdout.startswith(_BLOCKED)
    assert _lines(third) == _lines(second)
    assert "echo boom; exit 1" in _log(root)


def test_new_session_or_missing_state_prints_full_block(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("echo boom; exit 1")))
    state = root / ".crew" / ".verify-gate.last-stop"
    _run(root)

    other_session = _run(root, session="s2")
    no_session = _run(root, session=None)
    no_session_again = _run(root, session=None)
    state.unlink()
    state_removed = _run(root, session="s2")
    state.write_text("garbage without a tab", encoding="utf-8")
    state_corrupt = _run(root, session="s2")

    for result in (other_session, no_session, no_session_again, state_removed, state_corrupt):
        assert result.returncode == 2
        assert _lines(result)[0].startswith("verify-gate: FAILED 1 cmd | ")
        assert "VERIFY FAILED: echo boom; exit 1" in result.stderr
        assert "unchanged since last Stop" not in result.stderr


def test_changed_failure_set_prints_full_block(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("echo boom; exit 1")))
    _run(root)
    (root / ".crew" / "verify.json").write_text(
        json.dumps(_map_with(_fail_rule("echo other; exit 1"))), encoding="utf-8")

    result = _run(root)

    assert "VERIFY FAILED: echo other; exit 1" in result.stderr
    assert "unchanged since last Stop" not in result.stderr


def test_pass_clears_dedupe_state(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("test -f ok.flag")))
    state = root / ".crew" / ".verify-gate.last-stop"
    _run(root)
    assert state.exists()
    (root / "ok.flag").write_text("x", encoding="utf-8")

    passed = _run(root)
    (root / "ok.flag").unlink()
    again = _run(root)

    assert passed.returncode == 0
    assert again.returncode == 2
    assert "unchanged since last Stop" not in again.stderr
    assert "VERIFY FAILED: test -f ok.flag" in again.stderr


def test_not_verified_never_counted_as_passed(tmp_path):
    skipped = {"paths": ["a.py"], "seconds": 2, "reach": "local", "run": ["exit 77"], "why": "skips"}
    root = _repo(tmp_path, _map_with(skipped, base=True))

    result = _run(root)

    verdict = _lines(result)[0]
    assert result.returncode == 0
    assert "PASSED 1 cmd " in verdict
    assert "skipped 1" in verdict and "reach 1" in verdict and "over-budget 1" in verdict
    assert "NOT VERIFIED 3 item(s) " in verdict
    passed_lines = [ln for ln in _lines(result) if "PASSED" in ln]
    assert passed_lines == [verdict]
    assert "SKIP (rc 77, environment absent): exit 77" in result.stderr


@pytest.mark.parametrize("case", ["pass", "fail", "skip77", "unmapped", "backoff"])
def test_exit_codes_and_l0733_line_unchanged(tmp_path, case):
    rules = {
        "pass": [{"paths": ["a.py"], "seconds": 1, "reach": "local", "run": ["true"], "why": "p"}],
        "fail": [_fail_rule("exit 1")],
        "skip77": [{"paths": ["a.py"], "seconds": 1, "reach": "local", "run": ["exit 77"], "why": "s"}],
        "unmapped": [{"paths": ["b.py"], "seconds": 1, "reach": "local", "run": ["true"], "why": "other"}],
        "backoff": [{"paths": ["a.py"], "seconds": 1, "reach": "local", "run": ["true"], "why": "p"}],
    }[case]
    root = _repo(tmp_path, _map_with(*rules, unmapped="fail" if case == "unmapped" else "ignore", base=False))
    if case == "backoff":
        (root / ".crew" / ".verify-gate.lock").mkdir()

    quiet = _run(root)
    verbose = _run(root, verbose="1")

    expected = {"pass": 0, "fail": 2, "skip77": 0, "unmapped": 2, "backoff": 0}[case]
    assert quiet.returncode == verbose.returncode == expected
    assert quiet.stdout == verbose.stdout
    if expected == 2:
        assert quiet.stdout.startswith(_BLOCKED)
    if case == "unmapped":
        assert "UNMAPPED CHANGES - .crew/verify.json has no rule for:" in quiet.stderr
        assert "a.py" in quiet.stderr
    if case == "backoff":
        assert "NOTHING WAS VERIFIED this turn" in quiet.stderr


def test_verdict_names_its_units(tmp_path):
    local_rule = {"paths": ["a.py"], "seconds": 2, "reach": "local",
                  "run": ["echo l1", "echo l2", "echo l3"], "why": "three"}
    remote_rule = {"paths": ["a.py"], "seconds": 2, "reach": "network",
                   "run": ["echo n1", "echo n2", "echo n3"], "why": "net"}
    root = _repo(tmp_path, _map_with(local_rule, remote_rule, base=False))

    result = _run(root)

    verdict = _lines(result)[0]
    assert "PASSED 3 cmd " in verdict
    assert "NOT VERIFIED 1 item(s) (reach 1," in verdict


def test_rule_that_backgrounds_a_process_does_not_hold_the_hook_open(tmp_path):
    root = _repo(tmp_path, _map_with(_fail_rule("(sleep 8 &); true"), base=False))
    started = time.monotonic()

    result = _run(root)

    elapsed = time.monotonic() - started
    assert result.returncode == 0
    assert elapsed < 6, f"the rule's background sleep held the hook's stderr pipe open for {elapsed:.1f}s"


def _commit_all(root):
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True, text=True, timeout=_T)
    subprocess.run(("git", "commit", "-q", "-m", "map"), cwd=root, check=True,
                   capture_output=True, text=True, timeout=_T)


@pytest.mark.parametrize("verbose", ["0", "1"])
def test_own_log_and_state_do_not_defeat_the_fingerprint_skip(tmp_path, verbose):
    rule = {"paths": ["a.py"], "seconds": 3, "reach": "local", "run": ["echo ok"], "why": "ok"}
    root = _repo(tmp_path, _map_with(rule, base=False))
    (root / "a.py").rename(root / "a.py.hold")
    _commit_all(root)
    (root / "a.py.hold").rename(root / "a.py")

    runs = [_run(root, verbose=verbose) for _ in range(3)]

    assert [r.returncode for r in runs] == [0, 0, 0]
    assert "SKIPPED, not re-run" not in runs[0].stderr
    assert "SKIPPED, not re-run" in runs[1].stderr, runs[1].stderr
    assert "SKIPPED, not re-run" in runs[2].stderr, runs[2].stderr


def test_killed_run_still_names_what_it_never_checked(tmp_path):
    slow = {"paths": ["a.py"], "seconds": 5, "reach": "local", "run": ["sleep 20"], "why": "slow"}
    big = {"paths": ["a.py"], "seconds": 90, "reach": "local", "run": ["echo BIG"], "why": "over budget"}
    outputs = {}
    for verbose in ("1", "0"):
        root = _repo(tmp_path / verbose, _map_with(slow, big, base=False))
        (root / "a.py").rename(root / "a.py.hold")
        _commit_all(root)
        (root / "a.py.hold").rename(root / "a.py")
        env = crew_fixtures.isolated_home_env(root.parent / "home")
        env.update(CLAUDE_PROJECT_DIR=str(root), CREW_VERIFY_VERBOSE=verbose)
        with subprocess.Popen([_BASH, _SH], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, cwd=str(root), env=env, text=True) as proc:
            proc.stdin.write('{"session_id":"s1"}')
            proc.stdin.close()
            time.sleep(4)
            proc.send_signal(signal.SIGTERM)
            _, err = proc.communicate(timeout=_T)
        outputs[verbose] = err

    for marker in ("deferred to /crew:verify", "permanently over budget"):
        assert marker in outputs["1"]
        assert marker in outputs["0"], outputs["0"]


@pytest.mark.parametrize("flag", ["--verbos", "--bogus"])
def test_unknown_argument_message_names_verbose(tmp_path, flag):
    root = _repo(tmp_path, _map_with(base=False))

    result = _run(root, flag)

    assert result.returncode == 2
    assert "--verbose" in result.stderr
