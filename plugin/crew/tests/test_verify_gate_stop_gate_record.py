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
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import
import verify_record  # noqa: E402  pylint: disable=wrong-import-position

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
    assert "remote verb 'ssm'" in stop.stderr, stop.stderr
    assert "ssm-run.sh" not in stop.stderr.split("remote verb")[0], (
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
    assert "remote verb 'ssh'" in result.stderr, (
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


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_13_a_wrapper_naming_another_wrapper_is_deferred_generically(
        flavour, tmp_path):
    """(13, updated for round 4) outer.sh calls inner.sh; inner.sh calls
    ssh. Round 2/3 followed this chain recursively and reported the more
    specific "remote verb ssh" reason; round 4 DELETED that recursion (see
    verify_record.py's module docstring - it was itself part of the arms
    race BLOCK verify_record.py:321/383/387 exploited). outer.sh is still
    read ONE level for a verb (finds none - "bash inner.sh" names no verb
    itself) and is still classified "wrapper" via the interpreter+argument
    rule regardless, so the OUTCOME (deferred, never executed) is
    unchanged even though the REASON is now the generic one rather than
    the specific "remote verb". Proven with a side-effect marker inner.sh
    would create if it ever actually ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash outer.sh"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "ran.marker"
    (root / "outer.sh").write_text("#!/bin/sh\nbash inner.sh\n", encoding="utf-8")
    (root / "inner.sh").write_text(
        "#!/bin/sh\ntouch ran.marker\nssh remotehost true\n", encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "wrapper or inline shell" in result.stderr, result.stderr
    assert not marker.exists(), (
        "the nested wrapper actually ran on Stop despite being deferred. "
        + result.stderr
    )
    rec = _record(root)
    assert any(v.get("status") == "reach_wrapper"
               for v in rec.get("rules", {}).values()), rec


def test_15_price_refuses_a_wrapper_that_reaches_ssh_and_never_runs_it(tmp_path):
    """(15, round 2 BLOCK verify_price.py:35) --price on a rule whose
    command is an undeclared wrapper script that itself calls ssh must
    REFUSE, using the same shared scanner the gates use, and never execute
    the wrapper - proven with a side-effect file the wrapper would create
    if it ran."""
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
    priced = subprocess.run([_PY, _PRICE_PY, str(target)], cwd=str(tmp_path),
                            capture_output=True, text=True, check=False)
    assert priced.returncode == 0, priced.stderr
    assert "REFUSED" in priced.stdout, priced.stdout
    assert "remote verb 'ssh'" in priced.stdout, priced.stdout
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
    priced = subprocess.run([_PY, _PRICE_PY, str(target)],
                            capture_output=True, text=True, check=False)
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
    later."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "env": {"ENV": "test"},
                   "run": ["echo \"ENV=$ENV AWS_PROFILE=${AWS_PROFILE:-UNSET}\" > seen.txt"]}],
        "default": [], "unmapped": "ignore",
    }
    target = tmp_path / "price_env.json"
    target.write_text(json.dumps(vmap), encoding="utf-8")
    env = dict(os.environ, ENV="prod", AWS_PROFILE="caller-profile")
    priced = subprocess.run([_PY, _PRICE_PY, str(target)], cwd=str(tmp_path),
                            env=env, capture_output=True, text=True, check=False)
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
    verify_record_path = os.path.join(_ROOT, "hooks", "scripts", "verify_record.py")
    hidden_path = verify_record_path + ".hidden-for-test"
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "reach": "network", "run": ["echo remote"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    os.replace(verify_record_path, hidden_path)
    try:
        result = _run(flavour, root)
    finally:
        os.replace(hidden_path, verify_record_path)
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
    check bash correctly ran twice and failed once."""
    vmap = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 1, "run": ['test "$ENV" = dev'],
             "env": {"ENV": "dev"}},
            {"paths": ["b.py"], "seconds": 1, "run": ['test "$ENV" = dev'],
             "env": {"ENV": "DEV"}},
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
def test_24_a_compound_wrapper_invocation_is_scanned(flavour, tmp_path):
    """(24, round 3 BLOCK verify_record.py:243, updated for round 4)
    outer.sh's body is `true && bash inner.sh` - one LINE, two commands.
    Round 3 fixed this by splitting on &&/;/|/|| before wrapper detection;
    round 4 deleted that splitter entirely (see verify_record.py's module
    docstring) because the holistic, whole-token-list scan ("does an
    interpreter appear ANYWHERE, followed by a non-flag argument
    anywhere after it") already catches `bash` regardless of what
    precedes it on the line - no segmenting needed. Proven with a
    side-effect marker inner.sh would create if it ever actually ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["bash outer.sh"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    marker = root / "ran.marker"
    (root / "outer.sh").write_text("#!/bin/sh\ntrue && bash inner.sh\n",
                                    encoding="utf-8")
    (root / "inner.sh").write_text("#!/bin/sh\ntouch ran.marker\nssh dev-host true\n",
                                    encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "wrapper or inline shell" in result.stderr, result.stderr
    assert not marker.exists(), (
        "a compound wrapper invocation reaching ssh ran on Stop. " + result.stderr
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
def test_26_a_quoted_wrapper_path_is_still_resolved(flavour, tmp_path):
    """(26, round 3 FIX verify_record.py:203) `bash "local.sh"` - the
    quoted form. cmd.split() left the quote characters IN the token, so
    the resolver looked for a file literally named '"local.sh"' (with
    quote marks), which can never exist.

    local.sh calls ssh rather than just exiting clean, and the test
    asserts the rule IS deferred (reach_undeclared) - not merely that it
    "ran" or "was not deferred". A weaker assertion here (e.g. asserting
    only that the rule was not deferred, with an inert local.sh) does not
    discriminate this fix from the OTHER round-3 fix living in the same
    function: with FIX 3's existence check in place but FIX 2's
    tokenisation sabotaged back to plain split(), the mangled quoted token
    ('"local.sh"', quote marks included) resolves to NO real file, is
    correctly classified "no wrapper here" (FIX 3's own contract) rather
    than UNINSPECTED, and the rule is therefore never deferred either -
    for entirely the WRONG reason, with local.sh's real content (here:
    ssh) never actually read or scanned at all. Proven by hand: that
    sabotage left this test GREEN under the weaker assertion, silently
    masking a full reach-scan bypass. Requiring the ssh verb to actually
    surface in the notice is what catches it."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ['bash "local.sh"']}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "local.sh").write_text("#!/bin/sh\nssh dev-host true\n",
                                    encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "remote verb 'ssh'" in result.stderr, (
        "the quoted wrapper's real content (ssh) was never actually read - "
        "either it was left as a generic wrapper deferral or, worse, "
        "silently treated as no-wrapper-here and never scanned at all. "
        + result.stderr
    )
    ran_pattern = re.compile(r'verify-gate: \d+s {2}bash "local\.sh"')
    assert not ran_pattern.search(result.stderr), (
        "a quoted wrapper reaching ssh ran on Stop instead of being "
        "deferred. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_27_python_dash_m_is_now_deferred_deliberately(flavour, tmp_path):
    """(27, round 3 FIX verify_record.py:218, REVERSED by round 4's DESIGN
    CHANGE) Round 3 carved `python -m X` out as "no wrapper here" - `-m`'s
    argument is a MODULE NAME, not a file, so a bare `python3 -m pytest`
    with no coincidentally-named local file used to run undeclared. Round
    4's reject-only redesign deliberately UNDOES that carve-out: telling
    a module name apart from a file path is exactly the kind of
    case-by-case cleverness the redesign stops doing (see
    verify_record.py's module docstring), so `python3` followed by ANY
    non-flag argument - `-m`'s module name included - now defers as
    "wrapper", full stop, with no file needed to trigger it. THIS repo's
    own .crew/verify.json declares `"reach": "local"` on every one of the
    eight rules this affects (see test_28's self-check, strict)."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["python3 -m pytest --version"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "wrapper or inline shell" in result.stderr, (
        "`python3 -m pytest` ran undeclared instead of being deferred - "
        "round 4's design change (an interpreter followed by ANY "
        "argument defers, module names included) is not in effect. "
        + result.stderr
    )
    ran_pattern = re.compile(r"verify-gate: \d+s {2}python3 -m pytest --version")
    assert not ran_pattern.search(result.stderr), (
        "`python3 -m pytest` ran on Stop despite being reported deferred. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_29_bash_dash_n_parses_but_never_executes_the_named_script(
        flavour, tmp_path):
    """(29, follow-up FIX verify_record.py) `bash -n remote.sh` - `-n` is
    "read commands but do not execute them"; remote.sh is PARSED for
    syntax only and never RUN, so its own ssh call can never fire under
    THIS invocation. The scanner used to follow it anyway (same as any
    other `bash x.sh`), so THIS repo's own .crew/verify.json rules[3]
    (`bash -n scripts/install-prerequisites.sh`, a syntax-check step) was
    deferred as undeclared reach for a `curl | bash` inside that script
    that this specific invocation never runs - see test_28's self-check.

    Both directions in one test, since a fix that only suppresses
    following would be indistinguishable from one that broke wrapper
    detection outright: WITH `-n`, the rule must run clean; the SAME
    remote.sh WITHOUT `-n` must still be followed and deferred, proving
    the general wrapper-following mechanism (test_5/test_13/test_24's
    coverage) is untouched by this fix."""
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
    assert "remote verb 'ssh'" in result.stderr, (
        "`bash remote.sh` (no -n) was NOT deferred - the fix broke "
        "ordinary wrapper-following rather than just scoping it to -n. "
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
    assert "remote verb 'ssh'" in result.stderr, result.stderr
    assert not marker.exists(), (
        "the `default` fallback executed a command reach had just "
        "excluded. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_31_inline_shell_hides_no_nested_wrapper(flavour, tmp_path):
    """(31, round 4 BLOCK verify_record.py:321) `bash -c 'bash inner.sh'`
    - inner.sh is named INSIDE an inline code STRING, not as a file
    argument any wrapper-following scanner ever directly saw; a scanner
    that only followed a DIRECTLY-named wrapper file could miss it
    entirely. The reject-only design does not need to parse the inline
    string at all: `bash` followed by ANY argument (here, the whole `-c`
    payload) is already grounds for deferral on its own terms, whatever
    that argument turns out to contain. Proven via a side-effect marker
    inner.sh would create if it ran."""
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
    assert "wrapper or inline shell" in result.stderr, result.stderr
    assert not marker.exists(), (
        "an inline `bash -c` invocation hiding a nested wrapper ran on "
        "Stop. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_32_a_preceding_cd_defers_unconditionally(flavour, tmp_path):
    """(32, round 4 BLOCK verify_record.py:383) `cd tools && bash
    inner.sh` - a scanner that resolves a wrapper path against the repo
    ROOT regardless of a preceding `cd` would look for inner.sh in the
    wrong place (or not at all) when it only exists under tools/. The
    reject-only design sidesteps path resolution for this case entirely:
    a `cd` ANYWHERE in the command is itself grounds for deferral, before
    any path math is attempted - it never needs to know where the `cd`
    would actually land. Proven via a side-effect marker inner.sh would
    create if it ran."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["cd tools && bash inner.sh"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "tools").mkdir()
    marker = root / "ran.marker"
    (root / "tools" / "inner.sh").write_text(
        "#!/bin/sh\ntouch ../ran.marker\nssh example.invalid true\n",
        encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")
    result = _run(flavour, root)
    assert result.returncode == 0, result.stderr
    assert "cd` appears in the command" in result.stderr, result.stderr
    assert not marker.exists(), (
        "a `cd`-prefixed wrapper invocation ran on Stop. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_33_an_extensionless_shebangless_script_still_defers(flavour, tmp_path):
    """(33, round 4 BLOCK verify_record.py:387) `bash check` - "check" has
    no extension and no shebang line, so an extension-or-shebang "looks
    like a script" heuristic would wave it through as "not really a
    wrapper" even though bash executes it exactly the same regardless of
    either. The reject-only design needs neither: existence under the
    repo alone is enough to classify ANY token following an interpreter
    as wrapper/inline-shell (and, since this one IS readable, its content
    upgrades the reason to the more specific "remote verb"). Proven via a
    side-effect marker check would create if it ran."""
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
    assert "remote verb 'ssh'" in result.stderr, result.stderr
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


def test_28_the_real_verify_json_scans_clean_for_every_rule():
    """The self-check Codex's round-3 report asked for directly, STRICT per
    the round-3 follow-up and unchanged in intent by round 4's redesign:
    every rule in THIS repo's OWN .crew/verify.json with an undeclared
    reach must classify as "local" - zero verb matches, zero wrapper
    matches, both asserted, both failing the test rather than only
    printing.

    Round 4's DESIGN CHANGE (see verify_record.py's module docstring)
    narrowed what "local" means considerably: an interpreter followed by
    ANY argument - `-m`'s module name included - now defers as "wrapper".
    `python3 -m pytest ...` (eight rules), `bash _verify/smoke.sh` (two),
    `python3 scripts/...` and friends (the rest) all moved from local to
    wrapper under that change, and this repo's own map now declares
    `"reach": "local"` explicitly on every one of them (18 total, each
    with a one-line addition to its existing `why` explaining what makes
    it safe) rather than relying on the scanner to work it out - which is
    the whole point: static inspection rejects, the map's author
    approves, and this test is what would have caught shipping the
    redesign without also updating the map it changes the rules for."""
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
