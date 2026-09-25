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

## Codex round 2 (2 BLOCK, 6 FIX) + the powershell-security-hardening
## specialist's SYNC_STATUS finding

 13/14. BLOCK verify-gate.sh:841 / verify_price.py:35. The reach scanner
     used to check only the outer command STRING; a wrapper script it calls
     was never followed, so `bash outer.sh` where outer.sh calls inner.sh
     which calls ssh passed unscanned. Now shared (verify_record.scan_reach)
     and bounded: it follows a wrapper chain up to depth 3, and anything it
     cannot fully read (deeper than that, over the 256 KiB per-file cap, or
     outside the repository) is UNINSPECTED - refused, not read as clean.
 15. BLOCK verify_price.py:35. --price used the same unscanned-wrapper
     heuristic as (13/14) - an undeclared wrapper that itself called ssh
     was TIMED (i.e. RUN), the exact command Stop would have refused.
 16. FIX verify-gate.sh (SKIP leaves a reusable fingerprint). A rule that
     PASSED once (writing a fingerprint) and later returns 77 on a changed
     tree left that PASS fingerprint on disk; if the tree was ever reverted
     to the state the old fingerprint covers, the outstanding SKIP silently
     fingerprint-skipped instead of being re-attempted.
 17. FIX verify-gate.sh (`--all` and a staged rename). `--diff-filter=D`
     alone misses a path git paired into an R-status instead of reporting a
     bare delete, so `git mv old.txt new.txt` staged dropped old.txt's rule
     out of `--all` entirely.
 18. FIX verify_fingerprint.py (`_corrupt_cache` non-dict top level). `[]`
     in record.json/timings.json is valid JSON that parses without raising,
     but is not the `{...}` shape either file is supposed to hold; the old
     check only asked "did json.load raise", so this shape read as clean
     and un-poisoned the digest that this same corruption should have
     invalidated.
 19. FIX verify_price.py (rc 77 pricing). --price used to time a command
     that returned 77 and write its elapsed seconds anyway - pricing a
     command that never actually ran, underpricing the real cost for the
     next environment that has it present.
 20. FIX verify_price.py (env pinning). --price ran with no env pinning at
     all, so an operator's own ENV=prod/AWS_PROFILE rode straight into a
     `seconds` measurement meant to be reusable by anyone who reads the map
     afterward.
 21. FIX verify_record.py `rule_key()` (env/reach/requiresCleanTree not
     hashed). Two rules with identical paths/run but different `env` used
     to hash to the SAME key, so a passing rule's clean result could erase
     a different rule's chronic/skipped/reach-excluded record entry that
     happened to share everything but its env.
 22. The powershell-security-hardening specialist's finding: `$syncStatus`
     (bash: `SYNC_STATUS`) started at 0 ("success") and was only reassigned
     inside the success path, so a sync that never ran at all (python
     unresolvable, verify_record.py missing, or the invocation throwing)
     silently read as "succeeded" and let both markers advance on a record
     that was never actually written.

## Codex round 3 (2 BLOCK, 3 FIX)

 23. BLOCK verify-gate.ps1:901. `@{}` and `-contains` both compare strings
     CASE-INSENSITIVELY in PowerShell; two rules running `test "$ENV" =
     dev` under ENV=dev and ENV=DEV are two DIFFERENT commands (different
     identity text), but the dedup read their identities as the same key,
     kept only the first, and this flavour exited 0 on a turn bash
     correctly ran twice and failed once.
 24. BLOCK verify_record.py:243. `true && bash inner.sh` is one LINE but
     two commands; wrapper detection only ever looked at a whole line as
     one `cmd.split()` target, so anything after `&&`/`||`/`;`/`|` -
     including a compound wrapper invocation reaching ssh - was invisible
     to the scan on both flavours.
 25. FIX verify-gate.sh:1402. The SKIP fingerprint delete lived inside the
     elif chain that also decides whether the sync succeeded, ordered
     AFTER the "sync failed" branch - so a turn that both skipped (rc 77)
     and failed to persist the record (e.g. the record's .tmp path exists
     as a directory) never reached the delete, and the earlier PASS
     fingerprint survived to fingerprint-skip the very next Stop.
 26. FIX verify_record.py:203. `cmd.split()` left quote characters IN the
     token - `bash "local.sh"` resolved to a literal 4-character path that
     could never match the real, unquoted file on disk, so a perfectly
     readable local wrapper was deferred as UNINSPECTED forever.
 27. FIX verify_record.py:218. `python -m pytest` handed "pytest" (a
     MODULE NAME, not a path) to the resolver as if it were the wrapper's
     first positional argument; failing to find a repo file called
     "pytest" read as UNINSPECTED ("could not tell") rather than what it
     actually was - no wrapper here at all. THIS repo's own .crew/verify.
     json runs `python3 -m pytest ...` in eight rules; unfixed, the merged
     gate would have deferred every one of them, forever, on every Stop.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import NoReturn

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import
import verify_record  # noqa: E402  pylint: disable=wrong-import-position

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PRICE_PY = os.path.join(_ROOT, "hooks", "scripts", "verify_price.py")

# `signal.SIGKILL` does not exist on native Windows - a bare reference to it
# raises AttributeError, not something the ValueError/OSError-shaped except
# clauses beside these cleanup calls catch, so a leftover bg/orphan pidfile
# on that platform crashed the test's OWN teardown instead of best-effort
# killing the stray process. `os.kill(pid, signal.SIGTERM)` still terminates
# the process there (CPython's Windows os.kill() calls TerminateProcess for
# any signal number it does not special-case), so SIGTERM is a real,
# portable fallback here, not a downgrade to a request the process could
# ignore.
_PORTABLE_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)

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

# rule[8] does not terminate - OPEN 2026-09-24 (TODO.md): a spawn of the real
# gate here had no timeout at all, so a hung gate (verify-gate.ps1's python
# resolver returning an unrunnable PATH shim, see verify-gate.ps1's
# Test-CrewWindowsExecutable) turned into a non-terminating `pytest
# plugin/crew/tests/ -q` - .crew/verify.json rule[8] verbatim - instead of one
# red test. Every fixture rule in this file runs in well under a second
# (echo/test/exit); 120s matches the headroom this suite already uses for a
# full gate invocation elsewhere (test_gate_command.py, test_docs_routing.py,
# test_promote_merge_gate.py) rather than inventing a new number, and is
# still short enough that a real hang fails fast instead of stalling rule[8].
_GATE_TIMEOUT = 120


def _fail_on_gate_timeout(flavour, exc) -> NoReturn:
    pytest.fail(
        f"verify-gate [{flavour}] did not terminate within "
        f"{_GATE_TIMEOUT}s - the gate hung instead of exiting "
        f"(rule[8] non-terminating repro). {exc}"
    )
    raise AssertionError("unreachable - pytest.fail always raises")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                    capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


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


def _run(flavour, root, *extra, scripts=None):
    """`scripts`: run the gate from that copy of hooks/scripts instead of the
    real one (the gate finds every sibling relative to itself)."""
    sh, ps1 = ((_SH, _PS1) if scripts is None else
               (os.path.join(scripts, "verify-gate.sh"),
                os.path.join(scripts, "verify-gate.ps1")))
    if flavour == "sh":
        cmd = [_BASH, sh, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", ps1,
               *[a.replace("--all", "-All") for a in extra]]
    try:
        return crew_fixtures.run_gate(
            cmd, input="{}", cwd=str(root),
            env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
            capture_output=True, text=True, check=False,
            timeout=_GATE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        _fail_on_gate_timeout(flavour, exc)


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

    result = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    assert result.returncode == 0, result.stderr
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["rules"][0]["seconds"] >= 1, written
    assert isinstance(written["rules"][0]["seconds"], int), written
    assert written["rules"][1]["seconds"] == 42, (
        "an already-priced rule must not be overwritten without --force. "
        + json.dumps(written)
    )

    forced = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target), "--force"],
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
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
    priced = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
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
    assert "remote verb 'ssm'" in stop.stderr, stop.stderr
    assert "ssm-run.sh" not in stop.stderr.split("remote verb")[0], (
        "the command ran on Stop despite the undeclared-reach heuristic. "
        + stop.stderr
    )

    target = tmp_path / "price_fixture2.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    priced = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
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
    try:
        result = crew_fixtures.run_gate(cmd, input="{}", cwd=str(root), env=env,
                                capture_output=True, text=True, check=False,
                                timeout=_GATE_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        _fail_on_gate_timeout(flavour, exc)
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


def test_15_price_refuses_a_wrapper_that_reaches_ssh_and_never_runs_it(tmp_path):
    """(15, round 2 BLOCK verify_price.py:35, reason updated for round 6)
    --price on a rule whose command invokes an undeclared wrapper script
    must REFUSE, using the same shared scanner the gates use, and never
    execute the wrapper - proven with a side-effect file the wrapper
    would create if it ran. wrapper.sh's own CONTENT (it calls ssh) no
    longer changes the classification - round 6 stopped reading any
    file's content at all - so the refusal reason is the generic
    "invokes an existing repo file", not "remote verb 'ssh'"; the marker
    check is what actually proves it never ran."""
    (tmp_path / "wrapper.sh").write_text(
        "#!/bin/sh\ntouch ran.marker\nssh remotehost true\n", encoding="utf-8")
    marker = tmp_path / "ran.marker"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash wrapper.sh"]}],
        "default": [], "unmapped": "ignore",
    }
    target = tmp_path / "price_wrapper.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    priced = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target)], cwd=str(tmp_path),
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    assert priced.returncode == 0, priced.stderr
    assert "REFUSED" in priced.stdout, priced.stdout
    assert "interpreter given a script argument 'wrapper.sh'" in priced.stdout, priced.stdout
    assert not marker.exists(), (
        "the wrapper actually ran under --price despite being refused. "
        + priced.stdout
    )
    assert "seconds" not in json.loads(target.read_text(encoding="utf-8"))["rules"][0]


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_16_a_skip_after_a_pass_deletes_the_stale_fingerprint(flavour, tmp_path):
    """(16, round 2 FIX) A rule that PASSES once (writing a fingerprint for
    that tree state) and later returns 77 on a DIFFERENT tree state must not
    leave the earlier PASS fingerprint sitting on disk: reverting the tree
    back to the state the PASS fingerprint covers must not silently
    fingerprint-skip an outstanding SKIP instead of re-attempting it."""
    vmap = {
        "version": 1,
        # reach: local - this fixture is testing SKIP/fingerprint
        # behaviour, not reach classification. Round 4's redesign defers
        # any `sh -c '...'` as a wrapper/inline-shell invocation on its
        # own terms (an interpreter followed by an argument), which would
        # exclude this rule from Stop before it ever ran and break what
        # this test actually checks.
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            "sh -c 'if [ -f ran.counter ]; then exit 77; else touch ran.counter; fi'"
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    fp = root / ".crew" / ".verify-gate.fingerprint"
    assert fp.exists(), "the PASS did not write a fingerprint. " + first.stderr

    (root / "a.py").write_text("y", encoding="utf-8")
    second = _run(flavour, root)
    assert "SKIP (rc 77" in second.stderr, second.stderr
    assert not fp.exists(), (
        "a SKIP after a PASS left the earlier PASS fingerprint on disk. "
        + second.stderr
    )

    (root / "a.py").write_text("x", encoding="utf-8")  # back to the PASS state
    third = _run(flavour, root)
    assert "SKIPPED, not re-run" not in third.stderr, (
        "reverting to the old PASS's tree state fingerprint-skipped an "
        "outstanding SKIP instead of re-attempting it. " + third.stderr
    )
    assert "SKIP (rc 77" in third.stderr, third.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_17_all_reaches_a_staged_rename_source(flavour, tmp_path):
    """(17, round 2 FIX) `git mv old.txt new.txt`, staged: --all must still
    select and run old.txt's rule (the rename SOURCE), not just the
    destination - a plain `--diff-filter=D` extraction misses a path git
    reports as an R-status pair instead of a bare delete."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["old.txt"], "run": ["exit 1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "old.txt").write_text("content\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(vmap), encoding="utf-8")
    _commit(root, "old.txt", ".crew/verify.json")
    _git(root, "mv", "old.txt", "new.txt")
    forced = _run(flavour, root, "--all")
    assert forced.returncode == 2, (
        "a staged rename's SOURCE path was not selected under --all. "
        + forced.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_18_a_non_dict_top_level_cache_poisons_the_fingerprint(flavour, tmp_path):
    """(18, round 2 FIX verify_fingerprint.py `_corrupt_cache`) `[]` (valid
    JSON, wrong shape) in BOTH record.json and timings.json must poison the
    fingerprint the same way malformed JSON does (see test_4) - a non-dict
    top level parses without raising, so the old check ("did json.load
    raise") read it as clean."""
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
    (root / ".crew" / ".verify-gate.record.json").write_text("[]", encoding="utf-8")
    (root / ".crew" / ".verify-gate.timings.json").write_text("[]", encoding="utf-8")
    second = _run(flavour, root)
    assert "SKIPPED, not re-run" not in second.stderr, (
        "a non-dict-but-valid-JSON cache ([]) still skipped via the "
        "fingerprint. " + second.stderr
    )
    assert "permanently over budget" in second.stderr, (
        "the chronic notice did not reappear after a []-corrupted cache "
        "re-run. " + second.stderr
    )


def test_19_price_records_rc77_as_skip_with_no_seconds(tmp_path):
    """(19, round 2 FIX verify_price.py rc 77) --price on a rule whose
    command exits 77 must record SKIP and write no `seconds` at all - not
    price a command that never actually ran, which would underprice the
    real cost once the environment IS present."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 77"]}],
        "default": [], "unmapped": "ignore",
    }
    target = tmp_path / "price_77.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    priced = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    assert priced.returncode == 0, priced.stderr
    assert "SKIP" in priced.stdout, priced.stdout
    assert "77" in priced.stdout, priced.stdout
    assert "seconds" not in json.loads(target.read_text(encoding="utf-8"))["rules"][0]


def test_20_price_pins_declared_env_and_strips_undeclared_pinned_vars(tmp_path):
    """(20, round 2 FIX verify_price.py env pinning) --price must run under
    the same env pinning the gates use: the caller's ENV=prod must NOT leak
    into a rule declaring ENV=test (the command must see "test"), and the
    caller's AWS_PROFILE (not declared by the rule) must be stripped
    entirely (the command must see it unset) rather than riding along into
    a `seconds` measurement meant to be reusable by anyone reading the map
    later.

    reach: local - this fixture tests env pinning under --price, not reach
    classification; the command's quotes/`$`/`{}`/`>` are all round-6
    shell metacharacters that would otherwise defer/refuse it outright."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "env": {"ENV": "test"}, "reach": "local",
                   "run": ["echo \"ENV=$ENV AWS_PROFILE=${AWS_PROFILE:-UNSET}\" > seen.txt"]}],
        "default": [], "unmapped": "ignore",
    }
    target = tmp_path / "price_env.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    env = dict(os.environ, ENV="prod", AWS_PROFILE="caller-profile")
    priced = crew_fixtures.run_gate([_PY, _PRICE_PY, str(target)], cwd=str(tmp_path),
                            env=env, capture_output=True, text=True, check=False,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    assert priced.returncode == 0, priced.stderr
    seen = (tmp_path / "seen.txt").read_text(encoding="utf-8")
    assert "ENV=test" in seen, seen
    assert "AWS_PROFILE=UNSET" in seen, seen


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_21_two_rules_differing_only_in_env_get_separate_record_entries(
        flavour, tmp_path):
    """(21, round 2 FIX verify_record.py rule_key()) Two rules with
    IDENTICAL paths and run text but DIFFERENT declared env (one chronic at
    999s under ENV=prod, one cheap and passing under ENV=test - the exact
    example in rule_key()'s own docstring) must hash to two DIFFERENT
    rule_key()s. paths/run must be identical between the two here, or the
    test proves nothing: rule_key() already differed on paths/run before
    this fix, so two rules that merely also happen to declare different env
    would get different keys anyway, for the wrong reason, and sabotaging
    env out of the hash would not turn this red."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 999, "env": {"ENV": "prod"},
             "run": ["echo same"]},
            {"paths": ["a.py"], "seconds": 1, "env": {"ENV": "test"},
             "run": ["echo same"]},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    rec = _record(root)
    statuses = {v.get("status") for v in rec.get("rules", {}).values()}
    assert "chronic" in statuses, (
        "the chronic ENV=prod rule's record entry is missing - it was "
        "erased by the passing ENV=test rule sharing its key despite "
        "identical paths/run. " + json.dumps(rec)
    )
    assert len(rec.get("rules", {})) == 1, (
        "expected exactly one persisted entry (the chronic rule; the "
        "passing rule clears its own key on success) but got: "
        + json.dumps(rec)
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_22_a_missing_verify_record_refuses_to_sync_and_advances_nothing(
        flavour, tmp_path):
    """(22, powershell-security-hardening specialist) $syncStatus / bash's
    SYNC_STATUS started at 0 ("success") and was only reassigned on the
    success path, so a sync that never ran at all silently read as
    succeeded and let both markers advance on a record never written.

    verify_record.py missing (not "python hidden from PATH" literally) is
    the trigger used here because it is the one both flavours' sync guard
    exercises the SAME way: on .sh, python is resolved ONCE at the top of
    the script and reused for the matcher, the env-pin lines and the sync
    call alike, so hiding python entirely trips a wholly different, much
    earlier guard before the matcher - or any notice - ever runs; only
    .ps1 resolves python separately for matching vs. syncing, so "python
    hidden" only reaches THIS code path on .ps1. Confirmed by hand against
    both real scripts (python actually hidden from PATH on .ps1; this
    file's own verify_record.py renamed away on .sh) before writing this
    in. A DECLARED reach is used so classification itself needs no python
    call and the notice reliably prints on both flavours regardless."""
    # A copy of hooks/scripts with verify_record.py removed -- never the real
    # file renamed away, which every other test (and, under pytest-xdist,
    # every other worker) running meanwhile would find missing too.
    scripts = tmp_path / "scripts"
    shutil.copytree(os.path.join(_ROOT, "hooks", "scripts"), scripts,
                    ignore=shutil.ignore_patterns("_test", "__pycache__"))
    (scripts / "verify_record.py").unlink()
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "network", "run": ["echo remote"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root, scripts=str(scripts))
    assert result.returncode == 0, result.stderr
    assert "declared reach: network" in result.stderr, result.stderr
    assert "could not sync the record" in result.stderr, (
        "the sentinel did not refuse when verify_record.py was missing. "
        + result.stderr
    )
    assert not (root / ".crew" / ".verify-verified-at").exists(), (
        "the marker advanced despite the sync being refused. " + result.stderr
    )
    assert not (root / ".crew" / ".verify-gate.fingerprint").exists(), (
        "the fingerprint was written despite the sync being refused. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_23_identity_dedup_is_case_sensitive(flavour, tmp_path):
    """(23, round 3 BLOCK verify-gate.ps1:901) Two matched rules run the
    SAME command text but declare env values differing only in CASE
    (ENV=dev vs ENV=DEV) - the resulting identity strings are byte-for-
    byte identical except for that one span of letters, a pure casing
    difference. PowerShell's `@{}` and `-contains` compare strings
    case-INSENSITIVELY by default, so the dedup used to read these two
    identities as the SAME key, keep only the first, and exit 0 on a
    check bash correctly ran twice and failed once.

    reach: local on both rules - this fixture tests identity dedup, not
    reach classification; `test "$ENV" = dev` contains the round-6 shell
    metacharacters `"` and `$`, which would otherwise defer it outright."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 1, "run": ['test "$ENV" = dev'],
             "env": {"ENV": "dev"}, "reach": "local"},
            {"paths": ["b.py"], "seconds": 1, "run": ['test "$ENV" = dev'],
             "env": {"ENV": "DEV"}, "reach": "local"},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 2, (
        "the ENV=DEV rule's own copy of the check should have FAILED "
        "('DEV' != 'dev' under case-sensitive comparison), proving it "
        "actually ran as a SEPARATE command instead of deduping with the "
        "ENV=dev rule whose identity differs only in case. " + result.stderr
    )
    assert "total across 2 rule command(s)" in result.stderr, (
        "the two rules did not run as two separate executions - "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_25_a_skip_that_also_fails_to_sync_still_deletes_the_fingerprint(
        flavour, tmp_path):
    """(25, round 3 FIX verify-gate.sh:1402) The fingerprint delete used to
    live INSIDE the elif chain that also decides whether the sync
    succeeded, ordered AFTER the "sync failed" branch - so a turn that
    BOTH skips (rc 77) AND fails to persist the record (here: the
    record's own .tmp path exists as a directory, so its write cannot
    even open) took the sync-failure branch first and never reached the
    delete. The earlier PASS fingerprint then survived to fingerprint-skip
    the very next ordinary Stop past the outstanding SKIP."""
    vmap = {
        "version": 1,
        # reach: local - see test_16's identical note; this fixture tests
        # the SKIP-fingerprint-delete ordering, not reach classification.
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            "sh -c 'if [ -f signal.flag ]; then exit 77; else exit 0; fi'"
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    fp = root / ".crew" / ".verify-gate.fingerprint"
    assert fp.exists(), "the PASS did not write a fingerprint. " + first.stderr

    (root / "signal.flag").write_text("x", encoding="utf-8")
    (root / ".crew" / ".verify-gate.record.json.tmp").mkdir()
    forced = _run(flavour, root, "--all")
    assert "SKIP (rc 77" in forced.stderr, forced.stderr
    assert "could not persist the record" in forced.stderr, forced.stderr
    assert not fp.exists(), (
        "a SKIP that ALSO failed to sync left the earlier PASS fingerprint "
        "on disk. " + forced.stderr
    )

    (root / ".crew" / ".verify-gate.record.json.tmp").rmdir()
    third = _run(flavour, root)
    assert "SKIPPED, not re-run" not in third.stderr, (
        "the outstanding SKIP fingerprint-skipped on the next ordinary "
        "Stop instead of being re-attempted. " + third.stderr
    )
    assert "SKIP (rc 77" in third.stderr, third.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_27_python_dash_m_is_local_again(flavour, tmp_path):
    """(27, control required by round 6) Round 3 carved `python -m X` out
    as local (`-m`'s argument is a MODULE NAME, not a file); round 4 UNDID
    that carve-out on purpose (an interpreter followed by ANY argument
    deferred, module names included); round 6's FINAL STRUCTURAL RULE
    brings it BACK, explicitly, as one of the small closed set of
    interpreter-flag rules: `-m` as the exact second token is always
    local, regardless of what follows - `python3 -m pytest x -q` is the
    literal example the rule names, so the shape here is that (`-m` at
    token[1], other tokens after it), with `--version` in place of a
    collection target that does not exist in this throwaway fixture repo,
    so the command ALSO genuinely exits 0 when actually run - the point
    being tested is the classification, not pytest's own collection
    behaviour. THIS repo's own .crew/verify.json, which round 4 had to
    teach `"reach": "local"` on eight `python3 -m pytest ...` rules, is
    re-checked by test_28 with this rule back in effect."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["python3 -m pytest --version"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "wrapper or inline shell" not in result.stderr, result.stderr
    assert "reach_syntax" not in result.stderr, result.stderr
    ran_pattern = re.compile(r"verify-gate: \d+s {2}python3 -m pytest --version")
    assert ran_pattern.search(result.stderr), (
        "`python3 -m pytest --version` was deferred instead of run. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_29_bash_dash_n_grants_parse_only_by_exact_position(
        flavour, tmp_path):
    """(29, control required by round 6 - `bash -n a.sh` local) `-n`
    grants the parse-only exemption ONLY when it is EXACTLY the second
    token with EXACTLY one token after it: `bash -n remote.sh` is
    parse-only (remote.sh is never executed by this invocation, so
    whatever it contains cannot run); the SAME remote.sh named without
    `-n` (`bash remote.sh`) must still defer - as a generic wrapper now,
    not "remote verb", since round 6 no longer reads any file's content
    (see verify_record.py's module docstring)."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "run": ["bash -n remote.sh"]},
            {"paths": ["b.py"], "run": ["bash remote.sh"]},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "remote.sh").write_text("#!/bin/sh\nssh dev-host true\n",
                                     encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    ran_pattern = re.compile(r"verify-gate: \d+s {2}bash -n remote\.sh")
    assert ran_pattern.search(result.stderr), (
        "`bash -n remote.sh` was deferred instead of run - -n's parse-"
        "only meaning was not honoured. " + result.stderr
    )
    assert "interpreter given a script argument 'remote.sh'" in result.stderr, (
        "`bash remote.sh` (no -n) was NOT deferred - the fix broke "
        "ordinary wrapper detection rather than just scoping -n. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_30_the_default_fallback_never_reintroduces_an_excluded_command(
        flavour, tmp_path):
    """(30, round 4 BLOCK verify-gate.sh:950) A matching rule declares
    `reach: network`, is excluded from Stop, and contributes NO commands
    to `cmds` - so `cmds` stays empty and the `default` fallback fires.
    `default`/`always` used to run with NO reach check of their own at
    all, so the fallback could execute the EXACT command reach had just
    excluded a moment earlier. `default`/`always` now go through the SAME
    classification a rule's `run` does (they have no `reach` field to
    declare, so every command there is treated as an undeclared rule
    would be). Proven via a side-effect marker the default command would
    create if it ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "network", "run": ["exit 1"]}],
        "default": ["bash inner.sh"], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "ran.marker"
    (root / "inner.sh").write_text(
        "#!/bin/sh\ntouch ran.marker\nssh example.invalid true\n",
        encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "`default` command" in result.stderr, result.stderr
    assert "interpreter given a script argument 'inner.sh'" in result.stderr, result.stderr
    assert not marker.exists(), (
        "the `default` fallback executed a command reach had just "
        "excluded. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_31_inline_shell_hides_no_nested_wrapper(flavour, tmp_path):
    """(31, round 4 BLOCK verify_record.py:321, mechanism updated for
    round 6) `bash -c 'bash inner.sh'` - inner.sh is named INSIDE an
    inline code STRING. Under round 6 the single quotes needed to pass
    that string as one shell argument are themselves shell metacharacters
    (`_SHELL_METACHARS`), so this defers as "reach_syntax" before the
    scan ever gets far enough to look at `-c` specifically - a stricter,
    earlier refusal than round 4's "interpreter followed by an argument"
    reasoning, same outcome. Proven via a side-effect marker inner.sh
    would create if it ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash -c 'bash inner.sh'"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "ran.marker"
    (root / "inner.sh").write_text(
        "#!/bin/sh\ntouch ran.marker\nssh example.invalid true\n",
        encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "shell syntax in an undeclared rule" in result.stderr, result.stderr
    assert not marker.exists(), (
        "an inline `bash -c` invocation hiding a nested wrapper ran on "
        "Stop. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_33_an_extensionless_shebangless_script_still_defers(flavour, tmp_path):
    """(33, round 4 BLOCK verify_record.py:387, reason updated for round 6)
    `bash check` - "check" has no extension and no shebang line, so an
    extension-or-shebang "looks like a script" heuristic would wave it
    through as "not really a wrapper" even though bash executes it
    exactly the same regardless of either. Round 6 needs neither:
    existence under the repo alone is enough to classify a token
    following an interpreter as wrapper - no content is read any more
    (see verify_record.py's module docstring), so the reason is the
    generic "invokes an existing repo file", not "remote verb". Proven
    via a side-effect marker check would create if it ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash check"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "ran.marker"
    (root / "check").write_text(
        "touch ran.marker\nssh example.invalid true\n", encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "interpreter given a script argument 'check'" in result.stderr, result.stderr
    assert not marker.exists(), (
        "an extensionless, shebang-less wrapper ran on Stop. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_34_a_skip_beside_a_failure_still_deletes_the_fingerprint(
        flavour, tmp_path):
    """(34, round 4 FIX verify-gate.sh:1344) `[ "$FAILED" -eq 0 ] || exit 2`
    used to run BEFORE the SKIP-fingerprint-delete code was even reached -
    a different early exit from the one test_25 covers (there, the delete
    itself runs but the SYNC afterward fails; here, the delete never runs
    at all). First pass: two commands PASS, fingerprint written. Then:
    edit the tree so ONE command returns 77 (SKIP) and the OTHER fails
    outright (rc 1) - `exit 2` used to fire on the FAILED command before
    the SKIP's fingerprint delete ever ran. Restore the tree to the exact
    state the fingerprint covers: if it survived, this turn
    fingerprint-skips the still-outstanding SKIP instead of re-attempting
    it."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "reach": "local", "run": [
                "sh -c 'if [ -f skip.flag ]; then exit 77; else exit 0; fi'"
            ]},
            {"paths": ["b.py"], "reach": "local", "run": [
                "sh -c 'if [ -f fail.flag ]; then exit 1; else exit 0; fi'"
            ]},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    fp = root / ".crew" / ".verify-gate.fingerprint"
    assert fp.exists(), "the PASS did not write a fingerprint. " + first.stderr

    (root / "skip.flag").write_text("x", encoding="utf-8")
    (root / "fail.flag").write_text("x", encoding="utf-8")
    forced = _run(flavour, root, "--all")
    assert forced.returncode == 2, forced.stderr
    assert "SKIP (rc 77" in forced.stderr, forced.stderr
    assert "VERIFY FAILED" in forced.stderr, forced.stderr
    assert not fp.exists(), (
        "a SKIP beside an outright FAILURE left the earlier PASS "
        "fingerprint on disk - the FAILED early exit ran before the "
        "SKIP delete. " + forced.stderr
    )

    (root / "skip.flag").unlink()
    (root / "fail.flag").unlink()
    third = _run(flavour, root)
    assert "SKIPPED, not re-run" not in third.stderr, (
        "the stale fingerprint (left behind by the FAILED early exit) "
        "skipped the next ordinary Stop instead of re-attempting the "
        "outstanding SKIP. " + third.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_34b_a_backgrounded_grandchild_holding_stdout_does_not_wedge_the_gate(
        flavour, tmp_path):
    """A rule's OWN command can background something and never wait on it
    (a stray `long-thing &`, a detached daemon) without wedging the GATE
    ITSELF - independent of whatever timeout an external caller sets.

    This is the class of bug behind test_34 wedging past
    GATE_SUBPROCESS_TIMEOUT_S on Windows/Git Bash: before the fix,
    `OUT=$(eval "$c" 2>&1 </dev/null)` (verify-gate.sh) / `$out = &
    $bashExe -c $c 2>&1` (verify-gate.ps1) captured a rule's output through
    a PIPE, and a pipe only ever reports EOF once every process holding its
    write end has closed it - not just the one command the gate is
    actually waiting on. The rule below backgrounds a `sleep` that ignores
    SIGTERM (`trap '' TERM`, a disposition that survives the fork,
    unlike a trap HANDLER) and inherits the rule's own stdout/stderr, so
    the foreground part returns in well under a second while the
    grandchild alone would keep a pipe-based capture blocked for its whole
    20s sleep.

    Bounded tight (10s), not at GATE_SUBPROCESS_TIMEOUT_S: the fix makes
    this return in a fraction of a second. Sabotaged by hand against
    verify-gate.sh's old `OUT=$(eval "$c" 2>&1 </dev/null)` (reverting only
    that one line, nothing else) and confirmed red - this test's own
    10s bound is comfortably under the sleep's 20s, so a regression back to
    the old pipe capture fails loudly rather than merely running slow.
    """
    # The backgrounded `sleep 20 &` outlives the gate's own return (that is
    # the point of the test - the gate must not wait on it) and ignores
    # SIGTERM by inheriting the parent shell's disposition, so it is not
    # reachable through run_gate's own process-group cleanup: by the time
    # the gate returns, the shell that backgrounded it has already exited
    # and the sleep has been reparented away from that group. Recording its
    # own pid lets the test reap it directly instead of leaving a 20s
    # orphan behind every time this test runs.
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            "sh -c \"trap '' TERM; sleep 20 & echo $! > bg.pid\""
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    started = time.time()
    try:
        result = _run(flavour, root)
        elapsed = time.time() - started
        assert result.returncode == 0, result.stderr
        assert elapsed < 10, (
            f"the gate took {elapsed:.1f}s to return - a backgrounded, "
            "SIGTERM-ignoring grandchild inheriting the rule's stdout wedged "
            "the gate's own read of that rule's output, instead of the read "
            "coming from a file that does not care who else still has it "
            f"open. stderr: {result.stderr}"
        )
    finally:
        pidfile = root / "bg.pid"
        if pidfile.exists():
            try:
                bg_pid = int(pidfile.read_text(encoding="utf-8").strip())
                os.kill(bg_pid, _PORTABLE_SIGKILL)
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_34c_a_large_rule_output_is_capped_not_read_in_full(tmp_path):
    """The other half of test_34b's fix: reading the rule's own output back
    must be BOUNDED, not proportional to however much a rule (or a stray
    background process inheriting its fd) actually wrote.

    Proven deterministically and cheaply via `CREW_VERIFY_GATE_TEST_RULE_OUT_CAP`,
    a test-only env seam verify-gate.sh reads instead of the hardcoded
    1MiB cap (see verify-gate.sh's own comment beside it - no operator-facing
    doc names this variable, and nothing outside a test process should set
    it). An earlier version of this test proved the same cap by writing
    3GiB via `yes | head -c` and timing the read; that write alone is slow
    and disk-heavy on a constrained or slow-storage CI host, which is
    exactly the failure mode this rewrite avoids - the cap itself, not the
    time it takes to exercise it at real scale, is what must be proven.

    The rule below writes 5000 repeats of `Q` (a character this suite's own
    diagnostic text never emits, so counting it in stderr cannot pick up
    something the gate printed itself) and then fails, so `verify-gate.sh`'s
    existing `echo "$OUT" | tail -25 >&2` path prints the (capped) output
    read back from the file. With the cap set to 200, at most 200 `Q`
    characters must reach stderr - not 5000 - which is only true if the
    read was actually bounded to the cap rather than reading the whole file
    and truncating for display afterward.
    """
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            "sh -c \"head -c 5000 /dev/zero | tr '\\\\0' 'Q'; exit 1\""
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               CREW_VERIFY_GATE_TEST_RULE_OUT_CAP="200")
    started = time.time()
    result = crew_fixtures.run_gate(
        [_BASH, _SH], input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, check=False,
        timeout=_GATE_TIMEOUT)
    elapsed = time.time() - started
    assert result.returncode != 0, (
        "the fixture rule deliberately exits 1; the gate must fail too. "
        + result.stderr
    )
    assert elapsed < 10, (
        f"the gate took {elapsed:.1f}s to return on a 5000-byte rule "
        f"output with a 200-byte test cap. stderr: {result.stderr}"
    )
    # The command string itself (`tr '\0' 'Q'`) contains one literal 'Q'
    # and is echoed a few times regardless of the cap (the cost-unstated
    # notice, the FAILED header, the per-rule timing line) - counting every
    # 'Q' in stderr would conflate those incidental singles with the
    # capped OUTPUT block. The output block is the one contiguous RUN of
    # 'Q' characters; its length is what the cap actually bounds.
    runs = re.findall(r"Q+", result.stderr)
    longest_run = max((len(r) for r in runs), default=0)
    assert longest_run == 200, (
        f"the longest run of 'Q' in stderr was {longest_run}, not the "
        "200-byte test cap - the rule's output was read back beyond (or "
        f"short of) the cap instead of being snapshotted at exactly it. "
        f"stderr: {result.stderr}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_34d_a_second_mktemp_failure_refuses_rather_than_wedges(tmp_path):
    """When the rule-output capture file cannot be created ANYWHERE - not
    TMPDIR, not the .crew/ fallback - the gate must refuse the rule with a
    named reason, never fall back to the pipe form. That fallback is
    exactly the shape (a backgrounded grandchild holding the read open
    forever) test_34b's fix exists to close, so silently re-opening it here
    on a mktemp failure would undo that fix on this one path.

    Root cannot be made to see an unwritable TMPDIR or .crew/ by chmod
    alone (this sandbox runs as root, which bypasses DAC permission
    checks), so the failure is induced by shadowing `mktemp` on PATH
    instead: a counting stub that runs the REAL mktemp for the gate's
    earlier, unrelated calls (CHANGED_FILE's temp file, and the python-shim
    directory when no bare `python3` is on PATH) and starts failing only
    once the per-rule loop is reached - covering BOTH the TMPDIR attempt
    and this fix's own `.crew/` fallback attempt, since neither takes a
    distinguishing argument the stub could otherwise key on. This is
    root-safe and deterministic where a permissions-based fixture is
    neither.

    The counter's calibration ("exactly two plain `mktemp` calls before the
    per-rule loop") is only true when bare `python3` already resolves on
    PATH - `verify-gate.sh`'s own `crew_py_strict`/shim-building path makes
    an EXTRA `mktemp` call to build `SHIM_DIR` when it does not, which
    would shift every later count by one and break this test's "succeeds
    for call 1 only" assumption on any host where only `python`/`py` is on
    PATH (Git Bash, some CI images). Rather than assume the AMBIENT
    environment happens to have bare `python3`, this test builds its own
    tiny `python3` shim from the resolved interpreter and puts it on PATH
    ahead of everything else, so `command -v python3` always succeeds here
    and the calibration holds on every host, not just this one.
    """
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            "sh -c \"trap '' TERM; sleep 60 &\""
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    real_mktemp = shutil.which("mktemp")
    assert real_mktemp, "need a real mktemp on PATH to build the stub"
    real_py = shutil.which("python3") or shutil.which("python") or sys.executable
    py3_dir = tmp_path / "py3stub"
    py3_dir.mkdir()
    (py3_dir / "python3").write_text(
        "#!/bin/sh\n"
        f'exec "{real_py}" "$@"\n',
        encoding="utf-8", newline="\n")
    (py3_dir / "python3").chmod(0o755)
    stub_dir = tmp_path / "mktempstub"
    stub_dir.mkdir()
    counter = tmp_path / "mktemp.count"
    counter.write_text("0", encoding="utf-8")
    # Succeeds for the FIRST call only (CHANGED_FILE - measured directly:
    # a single-rule map with python3 resolvable on PATH, so the python-shim
    # SHIM_DIR branch is never entered, makes exactly two plain `mktemp`
    # calls total before this stub) and fails every call after that, which
    # is exactly where the per-rule loop's RULE_OUT_FILE attempts (both
    # the TMPDIR one and this fix's own `.crew/` fallback) begin.
    (stub_dir / "mktemp").write_text(
        "#!/bin/sh\n"
        f'n=$(cat "{counter}")\n'
        "n=$((n + 1))\n"
        f'echo "$n" > "{counter}"\n'
        "if [ \"$n\" -le 1 ]; then\n"
        f'  exec "{real_mktemp}" "$@"\n'
        "fi\n"
        "exit 1\n",
        encoding="utf-8", newline="\n")
    (stub_dir / "mktemp").chmod(0o755)

    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               PATH=str(py3_dir) + os.pathsep + str(stub_dir) + os.pathsep
               + os.environ.get("PATH", ""))
    started = time.time()
    result = crew_fixtures.run_gate(
        [_BASH, _SH], input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, check=False,
        timeout=_GATE_TIMEOUT)
    elapsed = time.time() - started
    assert elapsed < 10, (
        f"the gate took {elapsed:.1f}s to return with mktemp failing from "
        "the per-rule loop onward - it fell back to the pipe form and "
        f"waited on the backgrounded sleep instead of refusing. "
        f"stderr: {result.stderr}"
    )
    assert result.returncode != 0, (
        "a rule refused for lack of a capture location must not read "
        "as verified. " + result.stderr
    )
    assert "cannot create an output-capture file" in result.stderr, (
        "the refusal must name why, not fail silently or generically. "
        + result.stderr
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_34e_a_backgrounded_writer_is_killed_with_the_rule_not_orphaned(
        tmp_path):
    """A rule's own PASSING foreground command can background a writer and
    never wait on it (`sh -c 'yes >>out &'`) -- test_34b/c already prove the
    gate does not WEDGE or over-read on this shape, and this is the third:
    the orphan must not be left running, appending to a file the gate has
    already recorded a verdict for, after the gate itself has returned.
    Left alive, that process can grow that file without bound until the
    disk fills, with the gate having already reported PASS.

    A small, slow writer (one byte every 50ms), never a fast one like `yes`:
    the point is to prove the process is GONE, not to race a large write
    against a deadline. The fixture's own rule ignores SIGTERM
    (`trap '' TERM`) so the assertion also exercises the grace-period KILL,
    not just the initial TERM.
    """
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            # Single-quoted at the OUTER (JSON/python) level, not double: the
            # gate's own `eval "$c"` re-parses this whole string in ITS
            # shell, so a double-quoted `$!` here (test_34b's pattern) is
            # expanded by the GATE's shell before the inner `sh -c` ever
            # sees it - always empty, since the gate has not backgrounded
            # anything of its own yet. Single-quoting the body defers every
            # expansion, including `$!`, to the inner `sh` this test
            # actually needs it from.
            "sh -c 'trap \"\" TERM; "
            "( while :; do printf x >> orphan.out; sleep 0.05; done & "
            "echo $! > orphan.pid ) ; echo started'"
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    try:
        result = _run("sh", root)
        assert result.returncode == 0, result.stderr

        pidfile = root / "orphan.pid"
        assert pidfile.exists(), (
            "the fixture rule never recorded the orphan's pid. "
            + result.stderr
        )
        orphan_pid = int(pidfile.read_text(encoding="utf-8").strip())

        # Give a killed-but-still-exiting process a moment, then confirm it
        # is gone -- os.kill with signal 0 raises ProcessLookupError once
        # the pid is reaped, and raises nothing (no signal sent) while it
        # is still alive.
        deadline = time.time() + 5
        alive = True
        while time.time() < deadline:
            try:
                os.kill(orphan_pid, 0)
            except ProcessLookupError:
                alive = False
                break
            time.sleep(0.1)
        assert not alive, (
            f"pid {orphan_pid} (the rule's backgrounded writer) was still "
            "alive up to 5s after the gate returned - it was orphaned "
            f"instead of being killed with the rest of its rule. "
            f"stderr: {result.stderr}"
        )

        out = root / "orphan.out"
        size_after_dead = out.stat().st_size if out.exists() else 0
        time.sleep(0.5)
        size_later = out.stat().st_size if out.exists() else 0
        assert size_later == size_after_dead, (
            f"orphan.out grew from {size_after_dead} to {size_later} bytes "
            "after its writer was reported dead - a second process "
            "(reparented, or missed by the group kill) kept writing."
        )
    finally:
        pidfile = root / "orphan.pid"
        if pidfile.exists():
            try:
                stray_pid = int(pidfile.read_text(encoding="utf-8").strip())
                os.kill(stray_pid, _PORTABLE_SIGKILL)
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_34f_the_tail_of_an_oversized_rule_output_survives_the_cap(tmp_path):
    """The capture must keep the END of an oversized rule's output, not the
    START - what a failing rule needs downstream is its LAST `tail -25`
    lines, which is where the actual error usually is. Reading the first
    $RULE_OUT_CAP bytes (the old `head -c` form) instead kept whatever noise
    the rule printed FIRST and discarded the one line this whole capture
    path exists to preserve.

    The fixture rule prints 2000 filler lines, then one clearly-marked
    failure line, then exits 1 - with the cap set (via the same test-only
    env seam test_34c uses) to something well under the filler's own size
    but comfortably bigger than the marker line, so the marker can only
    survive if the read came from the END of the file.

    The marker is assembled at RUNTIME (`printf 'THE-ACTUAL-FAILURE-%s\\n'
    MARKER`), not written as one contiguous literal in the rule's own
    command text: verify-gate.sh echoes that command text to stderr on its
    own account (the "VERIFY FAILED: $c" header, the per-rule timing line),
    so a marker spelled out whole in the command would show up in stderr
    via those echoes regardless of what OUT actually captured, making the
    assertion pass either way. Split across a format string and an argument,
    the contiguous marker exists only in the rule's actual OUTPUT.
    """
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "local", "run": [
            "sh -c 'i=0; while [ \"$i\" -lt 2000 ]; do "
            "echo \"noise line $i padding padding padding padding\"; "
            "i=$((i + 1)); done; "
            "printf \"THE-ACTUAL-FAILURE-%s\\n\" MARKER; exit 1'"
        ]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")

    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               CREW_VERIFY_GATE_TEST_RULE_OUT_CAP="2000")
    result = crew_fixtures.run_gate(
        [_BASH, _SH], input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, check=False,
        timeout=_GATE_TIMEOUT)
    assert result.returncode != 0, result.stderr
    assert "THE-ACTUAL-FAILURE-MARKER" in result.stderr, (
        "the rule's actual failure line did not reach stderr - the capture "
        "kept the head of the oversized output instead of its tail. "
        f"stderr: {result.stderr}"
    )
    assert "noise line 0 " not in result.stderr, (
        "the very first filler line reached stderr - the cap did not "
        f"actually bound the read to the tail. stderr: {result.stderr}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_run_gate_kills_the_whole_group_on_timeout_not_just_the_direct_child(
        tmp_path):
    """crew_fixtures.run_gate must turn a hung grandchild into a named
    TimeoutExpired within the bound, not a hang that wedges the whole test
    session. This is the harness-level twin of test_34b above: a synthetic
    script stands in for verify-gate.sh so the case does not depend on the
    product fix at all.

    NOTE on what this reproduces and what it does not: CPython's own
    `subprocess.run` on POSIX does not actually hang on this scenario -
    reading its source (3.14), the POSIX branch of its TimeoutExpired
    handler calls `process.wait()`, not `communicate()` again, and its
    internal `_communicate` loop already collected whatever output existed
    before raising. The unconditional, unbounded second `communicate()`
    this class of bug depends on is real, but it is CPython's `_mswindows`
    branch only - confirmed here by reading `inspect.getsource(subprocess.run)`
    rather than assumed. `run_gate` does not rely on that platform split:
    it always kills the whole process GROUP first (`kill_process_group`),
    so the orphan is dead before the bounded post-kill drain runs, on
    either platform.

    Sabotaged by hand: temporarily reducing `kill_process_group` to a bare
    `proc.kill()` (no `os.killpg`) reproduces the wedge even on Linux,
    because `run_gate`'s own post-kill drain (`communicate(timeout=30)`,
    mirroring what CPython's Windows branch does unconditionally) then
    blocks on the still-open pipe until the orphaned `sleep 20` exits on
    its own - elapsed measured at 20.0s against this test's 15s bound.
    Confirmed red that way, restored, confirmed green again.
    """
    script = tmp_path / "hang.sh"
    script.write_text(
        "#!/bin/sh\n"
        "trap '' TERM\n"
        "sleep 20 &\n"
        "exit 0\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o755)

    started = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        crew_fixtures.run_gate(
            [_BASH, str(script)], capture_output=True, text=True, timeout=3,
        )
    elapsed = time.time() - started
    assert elapsed < 15, (
        f"run_gate took {elapsed:.1f}s to report the timeout - the "
        "grandchild's held-open pipe still wedged the drain instead of "
        "being killed as a group before it. elapsed={elapsed:.1f}s"
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_39_subshell_parentheses_still_defer(flavour, tmp_path):
    """(39, round 6 BLOCK verify_record.py:352) `(./check.sh)` - the
    subshell parentheses stayed glued to the path under every earlier
    round's tokenising, so `_resolves_to_repo_file` was handed
    '(./check.sh)' (or './check.sh)' after quote/segment handling) and
    found no file by that literal name - classified local. Round 6 does
    not try to parse this at all: `(` and `)` are both shell
    metacharacters, so this defers unconditionally, before anything about
    the command's shape is examined. Proven via a side-effect marker
    check.sh would create if it ever actually ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["(./check.sh)"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "marker"
    (root / "check.sh").write_text("echo ran > marker\n", encoding="utf-8")
    os.chmod(root / "check.sh", 0o755)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "shell syntax in an undeclared rule" in result.stderr, result.stderr
    assert not marker.exists(), (
        "`(./check.sh)` ran on Stop instead of being deferred. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_40_dash_n_as_a_trailing_argument_is_not_parse_only(flavour, tmp_path):
    """(40, round 6 BLOCK verify_record.py:474) `bash check.sh -n` - `-n`
    was granted by mere PRESENCE anywhere in the token list, not its
    actual position, so a script argument named "-n" (or a trailing `-n`
    flag bash itself would NOT treat as parse-only in this position)
    incorrectly exempted the whole command. Round 6's rule is positional:
    `-n` is parse-only ONLY as the exact second token with exactly one
    token after it. Here `-n` is the THIRD token, so no exemption applies
    and `check.sh` (the second token) resolving to an existing repo file
    defers as a wrapper. Proven via a side-effect marker check.sh would
    create if it ever actually ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash check.sh -n"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "marker"
    (root / "check.sh").write_text("echo ran > marker\n", encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "interpreter given a script argument 'check.sh'" in result.stderr, result.stderr
    assert not marker.exists(), (
        "`bash check.sh -n` ran on Stop instead of being deferred - -n "
        "was granted the parse-only exemption from the wrong position. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_41_a_command_substitution_still_defers(flavour, tmp_path):
    """(41, round 6 BLOCK verify_record.py:543) `echo "$(true;./check.sh)"`
    - a command substitution's contents used to bypass segmentation
    entirely (round 5's segmenter split on operators OUTSIDE a `$( ... )`
    span but the substitution extractor that was supposed to open it and
    classify its contents separately had its own gap), so the executable
    `./check.sh` inside it went unexamined and the whole command
    classified local. Round 6 does not try to open substitutions at all:
    `$`, `(`, `)`, `"` and `;` are all shell metacharacters, so this
    defers unconditionally. Proven via a side-effect marker check.sh
    would create if it ever actually ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"],
                   "run": ['echo "$(true;./check.sh)"']}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "marker"
    (root / "check.sh").write_text("echo ran > marker\n", encoding="utf-8")
    os.chmod(root / "check.sh", 0o755)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "shell syntax in an undeclared rule" in result.stderr, result.stderr
    assert not marker.exists(), (
        '`echo "$(true;./check.sh)"` ran on Stop instead of being '
        "deferred. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_42_a_plain_command_with_no_metachar_stays_local(flavour, tmp_path):
    """(42, control required by round 6) `echo ok` - no shell
    metacharacter, no reach verb, no interpreter, no existing-repo-file
    argument - the plain case that must keep working undeclared."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo ok"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "shell syntax in an undeclared rule" not in result.stderr, result.stderr
    assert "wrapper or inline shell" not in result.stderr, result.stderr
    ran_pattern = re.compile(r"verify-gate: \d+s {2}echo ok$", re.M)
    assert ran_pattern.search(result.stderr), (
        "`echo ok` was deferred instead of run. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_43_a_redirection_metachar_defers_with_no_exception(flavour, tmp_path):
    """(43, control required by round 6) `echo ok 2>&1` - round 5 carved
    out an explicit exception so `&` glued to `>` (a `2>&1`-style
    redirection) would not split as a shell operator; round 6's FINAL
    STRUCTURAL RULE removes that exception entirely, by design ("no
    exceptions, not even 2>&1") - `>` and `&` are both metacharacters and
    either one alone is enough to defer, unconditionally."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo ok 2>&1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "shell syntax in an undeclared rule" in result.stderr, (
        "`echo ok 2>&1` ran undeclared instead of being deferred for "
        "shell syntax. " + result.stderr
    )
    ran_pattern = re.compile(r"verify-gate: \d+s {2}echo ok 2>&1")
    assert not ran_pattern.search(result.stderr), (
        "`echo ok 2>&1` ran on Stop despite being reported deferred. "
        + result.stderr
    )



@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_44_bash_dash_m_is_not_a_module_and_defers(flavour, tmp_path):
    """(44, round 7 BLOCK verify_record.py:306) `-m` names a module for
    Python ONLY. For bash it enables job control and the next argument is
    a script that EXECUTES - so `bash -m check.sh` on an undeclared rule
    must defer and must not run check.sh."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash -m check.sh"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "check.sh").write_text("echo ran > marker\n", encoding="utf-8")
    result = _run(flavour, root)
    assert not (root / "marker").exists(), "check.sh EXECUTED. " + result.stderr
    assert "wrapper or inline shell" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_45_perl_dash_n_is_not_parse_only_and_defers(flavour, tmp_path):
    """(45, round 7 BLOCK verify_record.py:306) `-n` is parse-only for
    POSIX shells ONLY. `perl -n check.pl` runs check.pl once per input
    line - it EXECUTES - so it must defer and must not run."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["perl -n check.pl"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "check.pl").write_text("open(F, '>marker'); close(F);\n", encoding="utf-8")
    result = _run(flavour, root)
    assert not (root / "marker").exists(), "check.pl EXECUTED. " + result.stderr
    assert "wrapper or inline shell" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_46_an_interpreter_script_outside_the_repo_still_defers(flavour, tmp_path):
    """(46, round 7 BLOCK verify_record.py:313) `python ../outside.py`
    executes a script that does not resolve INSIDE the repo. An
    interpreter given any non-flag argument is running a script wherever
    it lives, so the classification must not consult the filesystem."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["python ../outside.py"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    marker = root / "marker"
    (root.parent / "outside.py").write_text(
        f"open({str(marker)!r}, 'w').write('ran')\n", encoding="utf-8")
    result = _run(flavour, root)
    assert not marker.exists(), "../outside.py EXECUTED. " + result.stderr
    assert "wrapper or inline shell" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_47_an_interpreter_with_flags_only_stays_local(flavour, tmp_path):
    """(47, round 7 control) `python --version` names no script: flags
    only, so it is plainly local and must run undeclared."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["python --version"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "wrapper or inline shell" not in result.stderr, result.stderr
    ran_pattern = re.compile(r"verify-gate: \d+s {2}python --version$", re.M)
    assert ran_pattern.search(result.stderr), (
        "`python --version` was deferred instead of run. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_48_a_corrupt_record_holds_the_marker_until_all_rebuilds_it(flavour, tmp_path):
    """(48, round 8 BLOCK verify_record.py:54) A record that is present but
    unreadable means the obligations it held are UNKNOWN. A Stop must not
    advance the sha marker over it (an unknown never collapses into "nothing
    owed"); a --all run rebuilds the record and the marker moves again."""
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
    marker = root / ".crew" / ".verify-verified-at"
    assert marker.exists(), first.stderr
    before = marker.read_text(encoding="utf-8").strip()
    # a new commit, then corrupt the record, then an unrelated change
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True,
                   capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(["git", "commit", "-qm", "advance"], cwd=str(root),
                   check=True, capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (root / ".crew" / ".verify-gate.record.json").write_text("not json", encoding="utf-8")
    (root / "a.py").write_text("x2", encoding="utf-8")
    second = _run(flavour, root)
    assert "obligations it held are UNKNOWN" in second.stderr, second.stderr
    assert marker.read_text(encoding="utf-8").strip() == before, (
        "the sha marker advanced over a corrupt record. " + second.stderr)
    third = _run(flavour, root, "--all")
    assert third.returncode == 0, third.stderr
    rec = _record(root)
    assert isinstance(rec.get("rules"), dict), "--all did not rebuild the record"
    assert marker.read_text(encoding="utf-8").strip() != before, (
        "--all rebuilt the record but the marker did not move. " + third.stderr)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_49_editing_a_deferred_rules_paths_keeps_its_obligation(flavour, tmp_path):
    """(49, round 8 BLOCK verify_record.py:558) A chronic rule's record key
    is a content hash of the rule, so editing the rule's paths makes a NEW
    key and the old entry looks stale. It must not be pruned as if verified:
    it stays, marked orphaned and reported, and holds the marker until a
    --all run clears it."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.txt"], "seconds": 999, "run": ["echo huge"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.txt").write_text("x", encoding="utf-8")
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    assert "permanently over budget" in first.stderr, first.stderr
    # commit a.txt on its own and let one Stop persist the chronic entry and
    # advance the marker past it - so the NEXT turn's changed set is only
    # verify.json, which the widened rule does not match (Codex's repro:
    # "Next Stop runs zero commands").
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True,
                   capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(["git", "commit", "-qm", "a.txt"], cwd=str(root),
                   check=True, capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    mid = _run(flavour, root)
    assert mid.returncode == 0, mid.stderr
    marker = root / ".crew" / ".verify-verified-at"
    before = marker.read_text(encoding="utf-8").strip()
    # commit ONLY an expansion of the rule's paths list
    vmap["rules"][0]["paths"] = ["a.txt", "b.txt"]
    (root / ".crew" / "verify.json").write_text(json.dumps(vmap), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True,
                   capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(["git", "commit", "-qm", "widen the rule"], cwd=str(root),
                   check=True, capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    second = _run(flavour, root)
    assert "NOT VERIFIED ON THIS TREE" in second.stderr, second.stderr
    assert "rule edited or removed since" in second.stderr, second.stderr
    assert marker.read_text(encoding="utf-8").strip() == before, (
        "the sha marker advanced past an orphaned obligation. " + second.stderr)
    third = _run(flavour, root, "--all")
    assert third.returncode == 0, third.stderr
    assert "rule edited or removed since" not in third.stderr, third.stderr

def test_28_the_real_verify_json_scans_clean_for_every_rule():
    """The self-check Codex's round-3 report asked for directly, STRICT and
    unchanged in intent across every redesign since: every rule in THIS
    repo's OWN .crew/verify.json with an undeclared reach must classify as
    "local" - failing the test, not printing, on anything else.

    Round 4 narrowed "local" enough that 18 rules needed `"reach": "local"`
    declared explicitly (see each one's `why` for what makes it safe).
    Round 6's FINAL STRUCTURAL RULE (verify_record.py's module docstring)
    is stricter again in a different dimension - ANY shell metacharacter
    anywhere defers, no exceptions - but re-running this self-check after
    that redesign finds ZERO further rules affected: the 18 already-
    declared rules are skipped here regardless (declared reach is never
    inspected), and every remaining undeclared rule's `run` commands
    happen to contain no metacharacter, no reach verb and no existing-
    repo-file argument. That is what this test is FOR - it is the thing
    that would have caught it if that had not been true."""
    repo_root = os.path.abspath(os.path.join(_ROOT, os.pardir, os.pardir))
    real_map = os.path.join(repo_root, ".crew", "verify.json")
    with open(real_map, encoding="utf-8") as fh:
        cfg = json.load(fh)
    rules = cfg.get("rules")
    assert isinstance(rules, list) and rules, (
        "the real .crew/verify.json has no `rules` array - this self-check "
        "cannot run against it. " + real_map
    )
    non_local = []
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or rule.get("reach") is not None:
            continue  # declared reach is a different code path entirely
        status, detail = verify_record.scan_reach(rule.get("run"), repo_root)
        if status != "local":
            non_local.append((i, status, detail, rule.get("run")))
    assert not non_local, (
        "rule(s) with an undeclared reach did not scan as local against "
        "the REAL .crew/verify.json - the merged gate would defer them, "
        "on every Stop: " + json.dumps(non_local, indent=2)
    )


# --- bounded stdin: an open, never-closed pipe must not park the gate ------
#
# win-repo's parked process (pwsh -NonInteractive, 1.94s CPU, no children,
# lock held, no record written) disproved an undrained-pipe deadlock theory
# specifically, so this is NOT a re-test of that theory - it is independent
# hardening for the same unconditional-read shape, verbatim from the brief:
# `[Console]::In.ReadToEnd()` (.ps1) and `INPUT=$(cat 2>/dev/null)` (.sh) both
# block forever on a pipe that is open but never closed and never sends
# stop_hook_active. Both gates now bound that read; this proves the bound
# actually fires rather than merely existing in a comment.
_STDIN_BOUND_DEADLINE_S = 20  # generous over the ~5s read bound each flavour declares


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_40_an_open_never_closed_stdin_does_not_park_the_gate(flavour, tmp_path):
    """Neither flavour may hang waiting on stdin that is open (a real pipe,
    not a terminal - `[ -t 0 ]` / IsInputRedirected both read this as
    "redirected") but never written to and never closed. Nothing is ever
    sent, so the ONLY way this returns is the bounded read timing out and
    the gate proceeding with no payload - exactly like a plain Stop event
    with an empty body."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 0"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    if flavour == "sh":
        cmd = [_BASH, _SH]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1]
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root), env=env)
    started = time.time()
    try:
        # Deliberately NOT communicate(): it closes stdin the instant it is
        # called even with input=None, which would hand the gate a normal
        # closed pipe and prove nothing about an OPEN one. wait() alone
        # touches neither stdin nor stdout/stderr, so the pipe genuinely
        # stays open, unwritten-to, for the whole timeout.
        proc.wait(timeout=_STDIN_BOUND_DEADLINE_S)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait(timeout=10)
        raise AssertionError(
            f"the {flavour} gate did not return within "
            f"{_STDIN_BOUND_DEADLINE_S}s with stdin open and never closed - "
            "the unbounded read was not actually bounded") from exc
    finally:
        if proc.stdin:
            proc.stdin.close()
    elapsed = time.time() - started
    out = proc.stdout.read() if proc.stdout else ""
    err = proc.stderr.read() if proc.stderr else ""
    assert elapsed < _STDIN_BOUND_DEADLINE_S, (
        f"the {flavour} gate returned but took {elapsed:.1f}s - "
        f"stderr: {err}")
    assert proc.returncode == 0, (
        f"stdout: {out} stderr: {err}"
    )


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh")
def test_40b_the_ps1_gate_bounds_stdin_on_linux_too(tmp_path):
    """The .ps1 half of test_40, exercised for real rather than skipped: pwsh
    is cross-platform, so `OS=Windows_NT` (the same override
    test_ps1_python_probe.py uses to reach this file's guarded body on a
    Linux runner) lets `[Console]::IsInputRedirected` / `ReadToEndAsync`
    actually run here, on the real interpreter, instead of only being read
    as source."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 0"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root), env=env)
    started = time.time()
    try:
        proc.wait(timeout=_STDIN_BOUND_DEADLINE_S)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait(timeout=10)
        raise AssertionError(
            f"the ps1 gate did not return within {_STDIN_BOUND_DEADLINE_S}s "
            "with stdin open and never closed - the unbounded read was not "
            "actually bounded") from exc
    finally:
        if proc.stdin:
            proc.stdin.close()
    elapsed = time.time() - started
    out = proc.stdout.read() if proc.stdout else ""
    err = proc.stderr.read() if proc.stderr else ""
    assert elapsed < _STDIN_BOUND_DEADLINE_S, f"took {elapsed:.1f}s - {err}"
    assert proc.returncode == 0, f"stdout: {out} stderr: {err}"


# --- G1 review round: the stop_hook_active retry must not re-block, and the
#     bound on stdin must be TOTAL rather than per-read -------------------
#
# Two distinct defects, one shared cause: both gates used to read stdin in a
# way that only worked correctly when the bound and "did the data actually
# arrive" happened to line up. They can disagree.
#
# (1) `.ps1` discarded whatever had already arrived if `CopyToAsync` had not
#     reached EOF within the 5s `Wait`, so a complete
#     `{"stop_hook_active": true}` payload sitting in a pipe the caller kept
#     open past the bound was thrown away -- the retry hook then ran the
#     gate again and blocked again on a check it had already reported this
#     turn.
# (2) `.sh` bounded EACH LINE with its own fresh `read -t 5`, not the whole
#     read, so a producer sending complete lines slower than 5s apart -- but
#     never closing the pipe -- kept the loop's per-call timeout from ever
#     firing and parked the gate exactly as an unbounded read would.


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_50_stop_hook_active_is_honoured_despite_a_pipe_held_open(
        flavour, tmp_path):
    """A complete `stop_hook_active: true` payload must be read and acted
    on even if the sender keeps the pipe open well past the ~5s stdin
    bound. The one rule here fails unconditionally, so exit 0 can only
    come from the stop_hook_active short-circuit -- never from the checks
    themselves passing."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    cmd = ([_BASH, _SH] if flavour == "sh"
           else [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1])
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root), env=env)
    proc.stdin.write('{"stop_hook_active": true}')
    proc.stdin.flush()
    # Deliberately not closed: the payload is complete, but EOF never
    # arrives, which is exactly what a held-open retry pipe looks like.
    try:
        proc.wait(timeout=_STDIN_BOUND_DEADLINE_S)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait(timeout=10)
        raise AssertionError(
            f"the {flavour} gate did not return within "
            f"{_STDIN_BOUND_DEADLINE_S}s with a complete stop_hook_active "
            "payload sitting in a held-open pipe") from exc
    finally:
        if proc.stdin:
            proc.stdin.close()
    out = proc.stdout.read() if proc.stdout else ""
    err = proc.stderr.read() if proc.stderr else ""
    assert proc.returncode == 0, (
        f"a held-open pipe carrying a complete stop_hook_active payload "
        f"should short-circuit to exit 0 without running the checks, got "
        f"{proc.returncode}. stdout: {out} stderr: {err}"
    )


@pytest.mark.skipif(_PWSH is None, reason="needs pwsh")
def test_50b_the_ps1_gate_honours_stop_hook_active_on_linux_too(tmp_path):
    """The .ps1 half of test_50, exercised for real via the `OS=Windows_NT`
    override (see test_40b)."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root), env=env)
    proc.stdin.write('{"stop_hook_active": true}')
    proc.stdin.flush()
    try:
        proc.wait(timeout=_STDIN_BOUND_DEADLINE_S)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait(timeout=10)
        raise AssertionError(
            f"the ps1 gate did not return within {_STDIN_BOUND_DEADLINE_S}s "
            "with a complete stop_hook_active payload sitting in a "
            "held-open pipe") from exc
    finally:
        if proc.stdin:
            proc.stdin.close()
    out = proc.stdout.read() if proc.stdout else ""
    err = proc.stderr.read() if proc.stderr else ""
    assert proc.returncode == 0, f"stdout: {out} stderr: {err}"


def _trickle(stdin, lines, interval_s):
    try:
        for i in range(lines):
            stdin.write('{"partial": %d}\n' % i)
            stdin.flush()
            time.sleep(interval_s)
    except (BrokenPipeError, ValueError, OSError):
        pass  # the gate returned (or was killed) before the trickle finished


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_51_a_trickling_sh_stdin_producer_does_not_park_the_gate(tmp_path):
    """MUST-BLOCK the per-line-timeout shape. A producer that sends complete
    lines every 3s -- comfortably under the 5s a `while read -t 5` loop
    would re-arm on every iteration -- and never closes the pipe must not
    keep the gate parked: the bound has to cover the WHOLE read, not just
    each individual line. 8 lines at 3s apart is 24s of trickle, well past
    both the ~5s bound this proves and the 20s ceiling below -- a version
    that re-arms per line would still be blocked reading stdin when that
    ceiling is hit."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["exit 0"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [_BASH, _SH], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root), env=env)
    trickler = threading.Thread(
        target=_trickle, args=(proc.stdin, 8, 3), daemon=True)
    trickler.start()
    try:
        proc.wait(timeout=_STDIN_BOUND_DEADLINE_S)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait(timeout=10)
        raise AssertionError(
            f"the sh gate did not return within {_STDIN_BOUND_DEADLINE_S}s "
            "against a stdin producer trickling complete lines slower than "
            "the per-line timeout -- the read bound is re-arming per line "
            "instead of covering the whole read") from exc
    finally:
        if proc.stdin:
            proc.stdin.close()
    out = proc.stdout.read() if proc.stdout else ""
    err = proc.stderr.read() if proc.stderr else ""
    assert proc.returncode == 0, f"stdout: {out} stderr: {err}"
