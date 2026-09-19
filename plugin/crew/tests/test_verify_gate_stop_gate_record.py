"""The Stop-gate record feature: per-rule status, reach, env pinning, exit
77, and --price. Covers sabotage cases (a)-(g) from the stophook-pricing
brief.

(a) a rule priced 999 against a 60s budget must not stop the marker advancing
(b) an unchanged tree after a run with one deferred rule must skip the rules
    that passed
(c) --price on a fixture map writes integers, never 0, and never overwrites
    without --force
(d) an unreadable record means everything runs
(e) a fixture rule `reach: host` must not run on Stop, must run under --all,
    and --price must skip it
(f) a fixture rule with NO reach whose command contains `ssm-run.sh` must be
    deferred by the Stop gate and refused by --price
(g) a fixture rule exiting 77 must not make the gate exit non-zero and must
    not be recorded as verified
(h) a fixture rule `requiresCleanTree: true` must not run on Stop and must
    run under --all -- reinstated by the PM after an earlier deferral

Every case here was sabotaged by hand against the SOURCE (not just the
fixture) and confirmed red before this file was written green -- see the
developer's report for what was reverted and what the suite printed. This
file is the thing left behind to catch a regression; it does not re-run the
sabotage itself, the same way the rest of this test directory does not.

## Codex round 1 (12 findings, both flavours)

  1. CRLF from native-Windows python leaves a trailing \r on an env-pin
     variable name, so `unset "$VAR"` silently fails to unset the REAL
     variable inherited from the caller's shell.
  2. Exit 77 (SKIP) used to still let both markers advance if nothing else
     was deferred -- a SKIP is not a check.
  3. --all built CHANGED from `ls-files` alone, which omits a path staged
     for deletion (`git rm`), so a rule mapped to it silently never ran.
  4. A corrupt .crew/.verify-gate.record.json or .timings.json did not
     move the fingerprint, so a corrupted cache kept skipping forever and
     lost whatever it had recorded (a chronic notice, a cached timing).
  5. An undeclared rule's reach was scanned only in the command STRING, not
     in a wrapper script file (`bash x.sh`) that script directly invokes.
  6. Two rules sharing command TEXT but declaring different `env` collapsed
     into one `cmds` entry; only the last rule's env ever ran, and BOTH
     were recorded as verified against a command neither actually passed
     under its own environment.
  7. A verify_record.py `_save` failure (e.g. a directory where the .tmp
     file needs to go) was swallowed, and the markers still advanced.
  8. .sh hashed rule content with json.dumps' default (spaced) separators;
     .ps1 used ConvertTo-Json -Compress (no spaces) - different byte
     strings for the same rule, so a key one flavour wrote was invisible
     to the other.
  9. Reach-verb matching was substring, not word-boundary: "ssm" matched
     inside "assessment".
 10. A structurally wrong timings cache (`[]`, not `{...}`) crashed the
     .sh matcher (AttributeError on `.get`, uncaught) instead of being
     treated as absent.
 11. An edited or removed rule's OLD record entry (a different content
     hash) was never pruned, so it stayed reported forever.
 12. A subsecond (0s elapsed) unpriced rule's measurement was discarded
     outright (`if total > 0`), so it stayed mandatory-forever instead of
     being priced from the second Stop onward.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PRICE_PY = os.path.join(_ROOT, "hooks", "scripts", "verify_price.py")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")
_PY = sys.executable

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None,
                                                 reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        not sys.platform.startswith("win") or _PWSH is None,
        reason="the .ps1 gate is the native-Windows flavour")),
]


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                    capture_output=True, text=True)


def _repo(tmp_path, verify_map):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / ".crew" / "verify.json").write_text(json.dumps(verify_map),
                                                encoding="utf-8")
    return root


def _run(flavour, root, *extra):
    if flavour == "sh":
        cmd = [_BASH, _SH, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[a.replace("--all", "-All") for a in extra]]
    return subprocess.run(
        cmd, input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
    )


def _record(root):
    p = root / ".crew" / ".verify-gate.record.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_case_permanently_over_budget_does_not_block_the_marker(flavour, tmp_path):
    """(a) A rule priced 999s against the 60s default must not stop the sha
    marker / fingerprint from advancing -- see verify_record.py."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 999, "run": ["echo x"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")  # left untracked deliberately

    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "permanently over budget" in result.stderr, result.stderr
    marker = root / ".crew" / ".verify-verified-at"
    assert marker.exists(), (
        "a chronic (999s) deferral must not block the baseline. "
        + result.stderr
    )
    assert (root / ".crew" / ".verify-gate.fingerprint").exists()
    rec = _record(root)
    assert any(v.get("status") == "chronic" for v in rec.get("rules", {}).values()), rec


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_b_unchanged_tree_with_one_deferred_rule_skips_the_rest(flavour, tmp_path):
    """(b) After a run with one CHRONIC deferral, an unchanged tree must
    skip the rule that passed (the unchanged-turn fingerprint fires) rather
    than re-running it."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo cheap"]},
            {"paths": ["b.py"], "seconds": 900, "run": ["echo huge"]},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")  # both left untracked
    (root / "b.py").write_text("y", encoding="utf-8")

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    assert "echo cheap" in first.stderr

    second = _run(flavour, root)
    assert "SKIPPED, not re-run" in second.stderr, second.stderr
    assert "echo cheap" not in second.stderr.replace(
        "verify-gate: NOT VERIFIED ON THIS TREE - rules[1]: echo huge", ""
    ), "the passed rule re-ran on an unchanged tree. " + second.stderr


def test_c_price_writes_integers_never_zero_never_overwrites(tmp_path):
    """(c) --price on a fixture map. Never writes 0, never overwrites an
    already-priced rule unless --force is given."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "run": ["echo fast"]},
            {"paths": ["b.py"], "run": ["echo already"], "seconds": 42},
        ],
        "default": [], "unmapped": "ignore",
    }
    target = tmp_path / "fixture.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")

    result = subprocess.run([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["rules"][0]["seconds"] >= 1, written
    assert isinstance(written["rules"][0]["seconds"], int), written
    assert written["rules"][1]["seconds"] == 42, (
        "an already-priced rule must not be overwritten without --force. "
        + json.dumps(written)
    )

    forced = subprocess.run([_PY, _PRICE_PY, str(target), "--force"],
                            capture_output=True, text=True, check=False)
    assert forced.returncode == 0, forced.stderr
    reforced = json.loads(target.read_text(encoding="utf-8"))
    assert reforced["rules"][1]["seconds"] >= 1, reforced


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_d_an_unreadable_record_means_everything_runs(flavour, tmp_path):
    """(d) A corrupt .crew/.verify-gate.record.json must not crash the gate
    and must not cause a rule to be silently treated as verified -- it is
    read-only history, never a gate on whether a rule matches or runs."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo ran"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / ".crew" / ".verify-gate.record.json").write_text(
        "{ not json at all", encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")  # left untracked deliberately

    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "echo ran" in result.stderr, (
        "an unreadable record must not stop the rule from running. "
        + result.stderr
    )
    # The corrupt file is treated as empty and rewritten clean, not left
    # corrupt and not crashing the sync step.
    rec = _record(root)
    assert rec.get("rules", {}) == {}, rec


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_e_reach_host_is_stop_excluded_all_included_price_skipped(flavour, tmp_path):
    """(e) A fixture rule `reach: host` must not run on Stop, must run
    under --all, and --price must skip it."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "host", "run": ["echo remote"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")  # left untracked deliberately

    stop = _run(flavour, root)
    assert stop.returncode == 0, stop.stderr
    assert "echo remote" not in stop.stderr.split("declare")[0].split(
        "not run on Stop")[0] or "reach: host" in stop.stderr, stop.stderr
    assert "reach: host" in stop.stderr, stop.stderr
    # Elapsed time is real wall clock, not a fixed value -- match "Ns  echo
    # remote" rather than pinning it to 0s, which is a timing flake waiting
    # to happen rather than a claim this test needs to make.
    ran_pattern = re.compile(r"verify-gate: \d+s {2}echo remote")
    assert not ran_pattern.search(stop.stderr), (
        "a reach: host rule ran on Stop. " + stop.stderr
    )

    forced = _run(flavour, root, "--all")
    assert ran_pattern.search(forced.stderr), (
        "--all must still run a reach: host rule. " + forced.stderr
    )

    target = tmp_path / "price_fixture.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    priced = subprocess.run([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False)
    assert "SKIPPED" in priced.stdout, priced.stdout
    assert "seconds" not in json.loads(target.read_text(encoding="utf-8"))["rules"][0]


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_f_undeclared_reach_verb_is_stop_deferred_and_price_refused(flavour, tmp_path):
    """(f) A fixture rule with NO `reach` whose command contains
    `ssm-run.sh` must be deferred by the Stop gate and refused by --price."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash ssm-run.sh do-the-thing"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")  # left untracked deliberately

    stop = _run(flavour, root)
    assert stop.returncode == 0, stop.stderr
    assert "undeclared reach" in stop.stderr, stop.stderr
    assert "ssm-run.sh" not in stop.stderr.split("undeclared reach")[0], (
        "the command ran on Stop despite the undeclared-reach heuristic. "
        + stop.stderr
    )

    target = tmp_path / "price_fixture2.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    priced = subprocess.run([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False)
    assert "REFUSED" in priced.stdout, priced.stdout
    assert "seconds" not in json.loads(target.read_text(encoding="utf-8"))["rules"][0]


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_g_exit_77_is_skip_not_fail_not_verified(flavour, tmp_path):
    """(g) A fixture rule exiting 77 must not make the gate exit non-zero,
    and must not be recorded as verified -- Codex round 1 (BLOCK,
    verify-gate.sh:1174) sharpened "not recorded as verified" to mean
    NEITHER marker: a SKIP is not a check, so it must not advance the sha
    marker OR write the fingerprint either, or the very next Stop on an
    unchanged tree hits the fingerprint match and never attempts the
    skipped command again -- "verified" by a run that never actually ran
    it. This reverses the earlier, narrower contract this test asserted
    (marker advances, only the fingerprint was withheld)."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 77"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")  # left untracked deliberately

    result = _run(flavour, root)
    assert result.returncode == 0, (
        "rc 77 must not fail the gate. " + result.stderr
    )
    assert "SKIP (rc 77" in result.stderr, result.stderr
    rec = _record(root)
    assert any(v.get("status") == "skipped" for v in rec.get("rules", {}).values()), rec
    marker = root / ".crew" / ".verify-verified-at"
    assert not marker.exists(), (
        "a SKIP is not a check - it must not advance the sha marker either, "
        "or the fingerprint-skip mechanism (see the fingerprint assertion "
        "below) will hide it from ever being attempted again. " + result.stderr
    )
    fp = root / ".crew" / ".verify-gate.fingerprint"
    assert not fp.exists(), (
        "a SKIP must not write the fingerprint either. " + result.stderr
    )

    second = _run(flavour, root)
    assert "SKIP (rc 77" in second.stderr, (
        "an unchanged tree with an outstanding SKIP must attempt the "
        "command again, not silently skip via the fingerprint. "
        + second.stderr
    )


def _commit(root, *relpaths):
    _git(root, "add", *relpaths)
    _git(root, "commit", "-q", "-m", "add " + " ".join(relpaths))


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_1_crlf_from_native_python_does_not_leak_an_inherited_credential(
        flavour, tmp_path):
    """(1) BLOCK verify-gate.sh:1154. A CRLF-corrupted env-pin line must
    still result in the REAL variable being unset - the read site strips
    '\\r' regardless of whether the python source-side fix applied."""
    stub_dir = tmp_path / "crlfstub"
    stub_dir.mkdir()
    real_py = shutil.which("python3") or shutil.which("python") or sys.executable
    stub = stub_dir / "python3"
    # A CRLF-emitting python stand-in: runs the REAL interpreter and then
    # corrupts its own stdout the way native-Windows text-mode stdout does,
    # simulating the failure mode even on a python that would not normally
    # produce it in THIS environment.
    stub.write_text(
        "#!/bin/bash\n"
        "out=\"$(\"" + real_py + "\" \"$@\")\"\n"
        "printf '%s' \"$out\" | sed 's/$/\\r/'\n",
        encoding="utf-8", newline="\n",
    )
    os.chmod(stub, 0o755)
    vmap = {
        "version": 1,
        # Declares an env var (unrelated to AWS_PROFILE) so ENV_JSON is
        # non-empty and the gate's env-pin lines actually route through a
        # python subprocess - the vulnerable path. A rule with NO declared
        # env never invokes python for its pin lines at all (a pure bash
        # loop), so it would not exercise this bug either way.
        "rules": [{"paths": ["a.py"], "seconds": 1,
                   "run": ["test -z \"$AWS_PROFILE\""],
                   "env": {"SOMEVAR": "x"}}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    env = dict(os.environ, AWS_PROFILE="prod",
               PATH=str(stub_dir) + os.pathsep + os.environ.get("PATH", ""),
               CLAUDE_PROJECT_DIR=str(root))
    if flavour == "sh":
        cmd = [_BASH, _SH]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1]
    result = subprocess.run(cmd, input="{}", cwd=str(root), env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, (
        "AWS_PROFILE was not actually unset under a CRLF-corrupted "
        "env-pin read. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_2_exit_77_advances_neither_marker_nor_fingerprint(flavour, tmp_path):
    """(2) BLOCK verify-gate.sh:1174. Already covered in detail by
    test_g_exit_77_is_skip_not_fail_not_verified; this asserts the second
    half of the repro directly: Stop again on the unchanged tree must NOT
    skip via the fingerprint (which would mean the SKIP is never attempted
    again)."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 77"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    second = _run(flavour, root)
    assert "SKIPPED, not re-run" not in second.stderr, (
        "a turn with an outstanding SKIP fingerprint-skipped instead of "
        "retrying the command. " + second.stderr
    )
    assert "SKIP (rc 77" in second.stderr, second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_3_all_reaches_a_staged_deletion(flavour, tmp_path):
    """(3) BLOCK verify-gate.sh:212. `git rm` a path mapped to a failing
    rule; --all must still select and run that rule."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(vmap), encoding="utf-8")
    _commit(root, "a.py", ".crew/verify.json")
    _git(root, "rm", "-q", "a.py")
    forced = _run(flavour, root, "--all")
    assert forced.returncode == 2, (
        "a staged deletion of a path mapped to a failing rule did not run "
        "under --all. " + forced.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_4_corrupt_caches_poison_the_fingerprint(flavour, tmp_path):
    """(4) BLOCK verify-gate.sh:329. Run with one passing and one chronic
    rule, corrupt both JSON caches, then repeat Stop: it must NOT skip, and
    the chronic notice must reappear."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo cheap"]},
            {"paths": ["b.py"], "seconds": 900, "run": ["echo huge"]},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    (root / ".crew" / ".verify-gate.record.json").write_text("{ not json", encoding="utf-8")
    (root / ".crew" / ".verify-gate.timings.json").write_text("{ not json", encoding="utf-8")
    second = _run(flavour, root)
    assert "SKIPPED, not re-run" not in second.stderr, (
        "a corrupted cache still skipped via the fingerprint. " + second.stderr
    )
    assert "permanently over budget" in second.stderr, (
        "the chronic notice did not reappear after a corrupted-cache "
        "re-run. " + second.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_5_wrapper_script_body_is_scanned_for_reach(flavour, tmp_path):
    """(5) BLOCK verify-gate.sh:841. `bash _verify/smoke.sh` with no
    `reach`, whose BODY calls ssh, must be deferred on Stop - not just the
    outer wrapper command string."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash _verify/smoke.sh"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "_verify").mkdir()
    (root / "_verify" / "smoke.sh").write_text(
        "#!/bin/sh\nssh remotehost \"echo hi\"\n", encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "undeclared reach" in result.stderr, (
        "a wrapper script whose BODY reaches ssh ran unattended on Stop. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_6_env_merge_runs_each_rule_under_its_own_environment(flavour, tmp_path):
    """(6) BLOCK verify-gate.sh:850. Two matched rules run the SAME command
    text but declare DIFFERENT env; both must actually execute, each under
    its own env - not collapse into one shared execution."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 1, "run": ["test \"$ENV\" = one"],
             "env": {"ENV": "one"}},
            {"paths": ["b.py"], "seconds": 1, "run": ["test \"$ENV\" = one"],
             "env": {"ENV": "two"}},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")
    forced = _run(flavour, root, "--all")
    assert forced.returncode == 2, (
        "the rule declaring ENV=two should have FAILED its own copy of the "
        "check (ENV != one), proving both rules actually ran under their "
        "own environment rather than collapsing into one shared run. "
        + forced.stderr
    )
    # The RC-2 assertion alone is not discriminating enough: with env
    # dropped from the command identity entirely, both rules dedupe to ONE
    # execution with NEITHER env pinned, and an unset $ENV also fails the
    # check (RC 2) - for the wrong reason. Count executions directly: two
    # DISTINCT runs of the same text is the actual claim under test.
    assert "total across 2 rule command(s)" in forced.stderr, (
        "the two rules did not run as two separate executions - "
        + forced.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_7_a_save_failure_blocks_both_markers(flavour, tmp_path):
    """(7) BLOCK verify_record.py:61 (_save). A directory where the record's
    .tmp file needs to go makes the write fail; neither marker may advance,
    and the required message must be printed."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 900, "run": ["echo huge"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / ".crew" / ".verify-gate.record.json.tmp").mkdir()
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "could not persist the record" in result.stderr, result.stderr
    assert "NOT advancing the marker" in result.stderr, result.stderr
    assert not (root / ".crew" / ".verify-verified-at").exists(), (
        "the marker advanced despite a failed record write. " + result.stderr
    )


def test_8_hash_parity_sh_writes_a_key_ps1_can_read(tmp_path):
    """(8) FIX verify-gate.ps1:730. Seed a measurement under .sh, then run
    .ps1: it must find and use the SAME cache key - proving both flavours
    hash a rule's content identically.

    Sabotage note: reverting ONLY .ps1's Get-CrewRuleKey back to its native
    ConvertTo-Json -Compress + SHA1 does NOT turn this red, because
    verify-gate.sh's canonical json.dumps(..., separators=(",", ":"))
    happens to produce byte-identical output to -Compress for ordinary
    ASCII rule content - the two forms only ever differed in the ORIGINAL
    bug because .sh's OWN inline hash used python's spaced default, not
    because -Compress itself was wrong. The sabotage that actually reds
    this test reverts .sh's fallback path to that spaced default (the
    historical shape of the bug) while leaving .ps1 on its current,
    correct delegation - see the developer's report for why this test
    alone cannot distinguish "shares one function" from "two
    implementations that happen to agree on typical input", and what a
    stronger test for the delegation itself would need."""
    if _BASH is None or not sys.platform.startswith("win") or _PWSH is None:
        pytest.skip("needs both bash and the native-Windows .ps1 flavour")
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo fast"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    _run("sh", root)
    timings_path = root / ".crew" / ".verify-gate.timings.json"
    timings = json.loads(timings_path.read_text(encoding="utf-8"))
    assert timings["rules"], "the .sh side did not cache a measurement at all"
    for k in timings["rules"]:
        timings["rules"][k] = 999
    timings_path.write_text(json.dumps(timings), encoding="utf-8")
    for p in (".verify-verified-at", ".verify-gate.fingerprint", ".verify-gate.record.json"):
        f = root / ".crew" / p
        if f.exists():
            f.unlink()
    (root / "a.py").write_text("x2", encoding="utf-8")
    result = _run("ps1", root)
    assert "measured not declared" in result.stderr, (
        "PowerShell did not find the key .sh cached - the two flavours "
        "are hashing rule content differently again. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_9_reach_verb_is_word_boundary_not_substring(flavour, tmp_path):
    """(9) FIX verify-gate.sh:767. "assessment" contains "ssm" as a bare
    substring and must NOT be deferred for reach."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 1, "run": ["echo assessment"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "undeclared reach" not in result.stderr, (
        "'assessment' was deferred for reach - substring matching is back. "
        + result.stderr
    )
    assert "echo assessment" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_10_a_structurally_wrong_timings_cache_does_not_crash(flavour, tmp_path):
    """(10) FIX verify-gate.sh:787. `[]` (valid JSON, wrong shape) in
    timings.json must be treated as absent, not crash the matcher."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo ran"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / ".crew" / ".verify-gate.timings.json").write_text("[]", encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, (
        "a structurally wrong (but valid-JSON) timings cache blocked the "
        "turn instead of being treated as absent. " + result.stderr
    )
    assert "echo ran" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_11_an_edited_rules_old_record_entry_is_pruned(flavour, tmp_path):
    """(11) FIX verify_record.py:203. Defer a rule, edit its command (a new
    content hash), then --all: the OLD key must not remain reported."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 900, "run": ["echo huge"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    rec = _record(root)
    assert rec.get("rules"), "no chronic entry was recorded to begin with"
    old_key = next(iter(rec["rules"]))

    vmap2 = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 900,
                   "run": ["echo huge different now"]}],
        "default": [], "unmapped": "ignore",
    }
    (root / ".crew" / "verify.json").write_text(json.dumps(vmap2), encoding="utf-8")
    _run(flavour, root, "--all")
    rec2 = _record(root)
    assert old_key not in rec2.get("rules", {}), (
        "the old rule's record entry was not pruned after the rule was "
        "edited. " + json.dumps(rec2)
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_12_a_subsecond_measurement_is_still_cached(flavour, tmp_path):
    """(12) FIX verify_record.py:206. A fast unpriced rule (0s elapsed)
    must still be cached (as 1s, per max(1, ceil(...))), not discarded."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo fast"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    timings = json.loads(
        (root / ".crew" / ".verify-gate.timings.json").read_text(encoding="utf-8"))
    assert timings.get("rules"), (
        "a subsecond rule's measurement was discarded instead of being "
        "cached as at least 1s."
    )
    assert all(v >= 1 for v in timings["rules"].values()), timings


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_h_requires_clean_tree_is_stop_excluded_and_all_included(flavour, tmp_path):
    """(h) A fixture rule `requiresCleanTree: true` must not run on Stop
    (the tree is dirty by definition during ordinary work) and must run
    under --all, sharing the same exclusion plumbing `reach` uses."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "requiresCleanTree": True,
                   "run": ["echo clean-only"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")  # left untracked deliberately

    ran_pattern = re.compile(r"verify-gate: \d+s {2}echo clean-only")

    stop = _run(flavour, root)
    assert stop.returncode == 0, stop.stderr
    assert "requires a clean working tree" in stop.stderr, stop.stderr
    assert not ran_pattern.search(stop.stderr), (
        "a requiresCleanTree rule ran on Stop. " + stop.stderr
    )
    rec = _record(root)
    assert any(v.get("status") == "clean_tree_required"
               for v in rec.get("rules", {}).values()), rec

    forced = _run(flavour, root, "--all")
    assert ran_pattern.search(forced.stderr), (
        "--all must still run a requiresCleanTree rule. " + forced.stderr
    )
