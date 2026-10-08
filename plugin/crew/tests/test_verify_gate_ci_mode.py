"""`verify-gate.sh --ci` / `verify-gate.ps1 -Ci`: the gate as a pull request's CI job.

Scope is the whole map over TRACKED files (no Stop budget, no fingerprint
skip), the reach filter is Stop's (a `network`/`host` rule, or an undeclared
one the scan cannot clear, is named and not run), `requiresCleanTree` rules
RUN (a CI checkout is clean), and the verdict is stricter than both: rc 77,
any deferral, and every path that ends having checked nothing exit 2. Neither
marker is ever written.

MUST-BLOCK: a failing rule, rc 77, `--all --ci`, a disabled gate, no map and
no smoke, every matched rule reach-excluded, no rule matching anything, no
tracked files (not a git work tree), a project dir that cannot be entered, an
unknown argument, `--ci` with `--price`, an incident file, a held lock, and a
`stop_hook_active` payload on stdin (each with a failing rule where a silent
exit 0 would otherwise hide it). MUST-ALLOW: a passing map (exit 0, no
marker), a `network` rule whose command would fail, an undeclared rule with
shell syntax, an `always` command with shell syntax, a `requiresCleanTree`
rule, a rule on a file the branch never changed, a matching fingerprint left
by Stop (the rules still run), and an untracked unmapped file under
`"unmapped": "fail"`.

The .ps1 flavour runs wherever pwsh exists: `OS=Windows_NT` gets it past its
flavour guard on Linux and macOS, the seam `scope_fixtures.run_hook` uses.
"""
import json
import os
import shutil
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

# Rule time (L-1503): every .ps1 case is `slow` - deselected from the
# promote/verify rule's default run, run by CI's `-m slow` jobs
# (crew-shell-matrix (ubuntu-latest), crew-windows-slow) - except the one
# parity case on _FLAVOURS_DEFAULT. Every .sh case runs by default.
_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=[pytest.mark.skipif(_PWSH is None, reason="needs pwsh"),
                               pytest.mark.slow]),
]
_FLAVOURS_DEFAULT = [
    _FLAVOURS[0],
    pytest.param("ps1", marks=pytest.mark.skipif(_PWSH is None, reason="needs pwsh")),
]

_MARKER = os.path.join(".crew", ".verify-verified-at")
_FINGERPRINT = os.path.join(".crew", ".verify-gate.fingerprint")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, rules, always=None, unmapped="ignore"):
    """A repo whose every file is COMMITTED, so a diff against any base is
    empty and only a whole-map scope reaches a rule at all. verify.json is
    committed too: an untracked file is in every scope."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": rules, "always": always or [], "default": [],
         "unmapped": unmapped}), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _rule(run, **extra):
    rule = {"paths": ["a.py"], "seconds": 1, "why": "fixture", "run": [run]}
    rule.update(extra)
    return rule


def _touch(path):
    """A rule command that leaves evidence it RAN, outside the repo so the run
    does not move the tree it is checking."""
    return f"echo ran > '{path}'"


def _run(flavour, root, *args, payload="{}", cwd=None):
    if flavour == "sh":
        cmd = [_BASH, _SH, *args]
    else:
        flags = {"--ci": "-Ci", "--all": "-All", "--price": "-Price"}
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[flags.get(a, a) for a in args]]
    # OS=Windows_NT: the .ps1's flavour guard proceeds only on Windows; this
    # is the seam the suite uses to run it under pwsh elsewhere. The .sh
    # ignores it.
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    return crew_fixtures.run_gate(cmd, input=payload, cwd=str(cwd or root), env=env,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


@pytest.mark.parametrize("flavour", _FLAVOURS_DEFAULT)
def test_a_passing_map_exits_0_and_records_nothing(flavour, tmp_path):
    """MUST-ALLOW, and the marker half: a full pass under --ci exits 0, says
    it did not record the pass, and leaves neither marker on disk."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert out.is_file(), done.stderr
    assert not (root / _MARKER).exists(), done.stderr
    assert not (root / _FINGERPRINT).exists(), done.stderr
    assert "were NOT advanced - --ci never writes them, by design" in done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_on_a_file_the_branch_never_changed_still_runs(flavour, tmp_path):
    """MUST-ALLOW: the scope is the whole map. Every file is committed, so a
    Stop run sees nothing to check; --ci still reaches the rule."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])

    stop = _run(flavour, root)
    assert stop.returncode == 0, stop.stderr
    assert not out.exists(), "fixture: Stop should see no changed file at all"

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert out.is_file(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_failing_local_rule_blocks(flavour, tmp_path):
    """MUST-BLOCK."""
    root = _repo(tmp_path, [_rule("exit 1", reach="local")])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "VERIFY FAILED: exit 1" in done.stderr
    assert not (root / _MARKER).exists(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_skip_is_not_a_pass_in_ci(flavour, tmp_path):
    """MUST-BLOCK: rc 77 ends a Stop turn quietly; a PR job has no next turn,
    so it fails and says why."""
    root = _repo(tmp_path, [_rule("exit 77", reach="local")])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "1 command(s) exited 77 (SKIP) - a skip is not a pass in CI" in done.stderr
    assert not (root / _MARKER).exists(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_network_rule_is_excluded_named_and_does_not_fail(flavour, tmp_path):
    """MUST-ALLOW: a declared `network` rule is not run under --ci (its
    command would fail here), is named, and is counted in the summary. A
    local rule beside it runs, so the job did check something."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule("exit 1", reach="network"), _rule(_touch(out), reach="local")])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert "rules[0] declared reach: network" in done.stderr
    assert "verify-gate --ci: 1 rule(s) and 0" in done.stderr
    assert "they run only under --all" in done.stderr
    assert "were NOT advanced - reach-excluded rules did not run" in done.stderr
    assert "VERIFY FAILED" not in done.stderr
    assert out.is_file(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_undeclared_rule_with_shell_syntax_is_excluded_like_stop(flavour, tmp_path):
    """MUST-ALLOW: no `reach`, and shell syntax the scan will not read, is
    excluded exactly as on Stop rather than run on a CI runner."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule("echo x > /dev/null; exit 1"), _rule(_touch(out), reach="local")])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert out.is_file(), done.stderr
    assert "rules[0] shell syntax in an undeclared rule" in done.stderr
    assert "VERIFY FAILED" not in done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_always_command_is_reach_filtered_too(flavour, tmp_path):
    """MUST-ALLOW: `always` has no `reach` of its own, so its commands get the
    undeclared classification under --ci as on Stop."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")],
                 always=["echo x > /dev/null; exit 1"])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert "`always` command" in done.stderr
    assert "verify-gate --ci: 0 rule(s) and 1" in done.stderr
    assert out.is_file(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_requires_clean_tree_rule_runs(flavour, tmp_path):
    """MUST-ALLOW: Stop never runs it; a CI checkout is the clean tree it was
    pushed to, so --ci does."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local", requiresCleanTree=True)])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert out.is_file(), done.stderr
    assert "requires a clean working tree" not in done.stderr


@pytest.mark.parametrize("order", [("--all", "--ci"), ("--ci", "--all")],
                         ids=["all-ci", "ci-all"])
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_all_and_ci_together_is_a_usage_error(flavour, order, tmp_path):
    """MUST-BLOCK: the two disagree on reach and on the markers, so the pair is
    refused rather than resolved by a precedence nobody asked for."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])

    done = _run(flavour, root, *order)

    assert done.returncode == 2, done.stderr
    assert "cannot be combined" in done.stderr
    assert not out.exists(), done.stderr
    assert not (root / _MARKER).exists(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_disabled_gate_fails_in_ci_rather_than_passing_unchecked(flavour, tmp_path):
    """MUST-BLOCK: `verifyGate: false` exits 0 on Stop; under --ci that would
    be a green job that checked nothing."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])
    (root / ".crew" / "config.json").write_text('{"verifyGate": false}', encoding="utf-8")

    ci = _run(flavour, root, "--ci")
    stop = _run(flavour, root)

    assert ci.returncode == 2 and "the gate is off" in ci.stderr, ci.stderr
    assert stop.returncode == 0, stop.stderr
    assert not out.exists()


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_no_map_and_no_smoke_fails_in_ci(flavour, tmp_path):
    """MUST-BLOCK: nothing to verify is not a pass in CI (Stop still exits 0)."""
    root = _repo(tmp_path, [])
    (root / ".crew" / "verify.json").unlink()

    ci = _run(flavour, root, "--ci")
    stop = _run(flavour, root)

    assert ci.returncode == 2 and "nothing to verify" in ci.stderr, ci.stderr
    assert stop.returncode == 0, stop.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_no_map_with_a_passing_smoke_passes_in_ci(flavour, tmp_path):
    """MUST-ALLOW: with no map, the smoke harness is what CI checks."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [])
    (root / ".crew" / "verify.json").unlink()
    (root / "_verify").mkdir()
    (root / "_verify" / "smoke.sh").write_text(f"{_touch(out)}\nexit 0\n", encoding="utf-8")

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert out.is_file()


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_every_matched_rule_reach_excluded_fails(flavour, tmp_path):
    """MUST-BLOCK: the only matching rule is `network`, so nothing runs; a
    green job would have checked nothing."""
    root = _repo(tmp_path, [_rule("exit 0", reach="network")])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "zero commands to run - 1 rule(s) matched, all excluded for reach" in done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_no_rule_matching_anything_fails(flavour, tmp_path):
    """MUST-BLOCK: a map whose rules match no tracked file, with no
    `always`/`default`, runs nothing."""
    rule = _rule("exit 0", reach="local")
    rule["paths"] = ["nothing-here/*.txt"]
    root = _repo(tmp_path, [rule])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "zero commands to run - no rule matched any tracked file" in done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_no_tracked_files_fails(flavour, tmp_path):
    """MUST-BLOCK: not a git work tree, so git lists nothing; Stop reads that
    as "nothing changed" and exits 0, --ci must not."""
    root = tmp_path / "plain"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": [_rule("exit 1", reach="local")], "unmapped": "ignore"}),
        encoding="utf-8")

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "verify-gate --ci: no tracked files found" in done.stderr
    # The refusal is the --ci one and the gate stops there: since L-0710 a
    # gate that went on into the quiet-turn path would still exit 2 (its
    # baseline write refuses outside a repo), so the exit code alone no
    # longer proves this guard (L-0710 review round 3, sabotage vacuous).
    assert done.stderr.rstrip().endswith("nothing was checked"), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_project_dir_that_cannot_be_entered_fails(flavour, tmp_path):
    """MUST-BLOCK: CLAUDE_PROJECT_DIR names nothing; the gate must not run
    against wherever the job started, nor exit 0."""
    out = tmp_path / "ran.txt"
    start = _repo(tmp_path, [_rule(_touch(out), reach="local")])

    done = _run(flavour, tmp_path / "missing", "--ci", cwd=start)

    assert done.returncode == 2, done.stderr
    assert "verify-gate --ci: cannot cd into" in done.stderr
    assert not out.exists(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_stop_fingerprint_never_skips_a_ci_run(flavour, tmp_path):
    """MUST-ALLOW the rules to run: a Stop run passes and leaves a fingerprint
    over exactly the paths --ci then lists (both tracked files modified), and
    --ci must still run the rule rather than skip on it."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])
    (root / "a.py").write_text("x = 2", encoding="utf-8")
    vj = root / ".crew" / "verify.json"
    vj.write_text(vj.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    stop = _run(flavour, root)
    assert stop.returncode == 0, stop.stderr
    assert (root / _FINGERPRINT).is_file(), "fixture: Stop left no fingerprint. " + stop.stderr
    out.unlink()

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert "checks were SKIPPED" not in done.stderr
    assert out.is_file(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_untracked_unmapped_file_is_not_in_scope(flavour, tmp_path):
    """MUST-ALLOW: a CI workspace's untracked files (a crew checkout, a .venv)
    are not the change and must not trip `"unmapped": "fail"`."""
    out = tmp_path / "ran.txt"
    rule = _rule(_touch(out), reach="local")
    rule["paths"] = ["a.py", ".crew/verify.json"]  # every TRACKED file is mapped
    root = _repo(tmp_path, [rule], unmapped="fail")
    (root / "stray.bin").write_text("untracked", encoding="utf-8")

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert "UNMAPPED CHANGES" not in done.stderr
    assert out.is_file(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_incident_does_not_stand_a_ci_run_down(flavour, tmp_path):
    """MUST-BLOCK: the emergency lane exits 0 on Stop; under --ci the rules
    run, so a failing one fails the job, and the incident is named."""
    root = _repo(tmp_path, [_rule("exit 1", reach="local")])
    (root / ".crew" / "incident.json").write_text(
        json.dumps({"expiresAtEpoch": 4102444800}), encoding="utf-8")

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "incident.json is present" in done.stderr
    assert "VERIFY FAILED: exit 1" in done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_held_lock_fails_rather_than_backing_off_green(flavour, tmp_path):
    """MUST-BLOCK: on Stop a held lock backs off with exit 0; a CI job that
    backed off checked nothing."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])
    lock = root / ".crew" / ".verify-gate.lock"
    lock.mkdir()
    (lock / "token").write_text("sh-1-1-1\n", encoding="utf-8")

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "verify-gate --ci: backed off: the lock at" in done.stderr
    assert not out.exists(), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_stop_hook_active_payload_does_not_end_a_ci_run(flavour, tmp_path):
    """MUST-BLOCK: the retry payload exits 0 on Stop; --ci reads no stdin, so
    a failing rule still fails."""
    root = _repo(tmp_path, [_rule("exit 1", reach="local")])

    done = _run(flavour, root, "--ci", payload='{"stop_hook_active": true}')

    assert done.returncode == 2, done.stderr
    assert "VERIFY FAILED: exit 1" in done.stderr


# PowerShell binds `-ci` and `--CI` to -Ci itself (case-insensitive), so the
# .ps1's unknown forms are the ones its binder does not take: an unknown
# switch, `--ci=1`, and a bare word (which would bind to -PriceTarget).
_UNKNOWN = [pytest.param("sh", a, id=f"sh-{a}", marks=_FLAVOURS[0].marks)
            for a in ("-ci", "--CI", "--ci=1", "--bogus")]
_UNKNOWN += [pytest.param("ps1", a, id=f"ps1-{a}", marks=_FLAVOURS[1].marks)
             for a in ("-Bogus", "--ci=1", "stray")]


@pytest.mark.parametrize("flavour,arg", _UNKNOWN)
def test_an_unknown_argument_is_a_usage_error(flavour, arg, tmp_path):
    """MUST-BLOCK: a misspelt --ci must not run as a Stop gate in CI."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])

    done = _run(flavour, root, arg)

    assert done.returncode == 2, done.stderr
    assert f"unknown argument '{arg}'" in done.stderr
    assert not out.exists(), done.stderr


@pytest.mark.parametrize("order", [("--ci", "--price"), ("--price", "--ci")],
                         ids=["ci-price", "price-ci"])
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_ci_and_price_together_is_a_usage_error(flavour, order, tmp_path):
    """MUST-BLOCK: --price writes the map; it is not a gate run."""
    root = _repo(tmp_path, [_rule("exit 0", reach="local")])
    before = (root / ".crew" / "verify.json").read_text(encoding="utf-8")

    done = _run(flavour, root, *order)

    assert done.returncode == 2, done.stderr
    assert "cannot be combined" in done.stderr
    assert (root / ".crew" / "verify.json").read_text(encoding="utf-8") == before


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh")
@pytest.mark.slow
def test_the_ps1_with_ci_off_windows_fails_instead_of_standing_down(tmp_path):
    """MUST-BLOCK: the flavour guard's silent exit 0 is for the hook pair. A CI
    job calling the .ps1 with -Ci on Linux or macOS (pwsh is preinstalled on
    ubuntu runners) must not get a green job that checked nothing."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])
    env = {k: v for k, v in os.environ.items() if k != "OS"}
    env["CLAUDE_PROJECT_DIR"] = str(root)

    done = crew_fixtures.run_gate([_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-Ci"],
                                  input="{}", cwd=str(root), env=env, capture_output=True,
                                  text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)

    # Refused at parameter binding (the flavour guard must stay the first
    # statement), which PowerShell reports as exit 1: non-zero is the point.
    assert done.returncode != 0, done.stderr
    assert "native-Windows flavour" in done.stderr
    assert not out.exists()


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_map_of_blank_commands_checks_nothing_and_fails(flavour, blank, tmp_path):
    """MUST-BLOCK: a blank command runs and "passes" without checking anything."""
    root = _repo(tmp_path, [_rule(blank, reach="local")], always=[blank])

    done = _run(flavour, root, "--ci")

    assert done.returncode == 2, done.stderr
    assert "zero commands" in done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_deploy_marker_is_left_alone_and_does_not_block(flavour, tmp_path):
    """MUST-ALLOW: the deploy-in-flight record check is a session concern, not
    a CI one: --ci runs the rules, passes, and leaves the marker as it was."""
    out = tmp_path / "ran.txt"
    root = _repo(tmp_path, [_rule(_touch(out), reach="local")])
    marker = root / ".crew" / ".deploy-in-flight"
    marker.write_text("qa abc123\n", encoding="utf-8")

    done = _run(flavour, root, "--ci")

    assert done.returncode == 0, done.stderr
    assert out.is_file()
    assert marker.read_text(encoding="utf-8") == "qa abc123\n"
