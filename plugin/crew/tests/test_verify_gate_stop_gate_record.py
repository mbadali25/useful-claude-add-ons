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
    """(g) A fixture rule exiting 77 must not make the gate exit non-zero
    and must not be recorded as verified."""
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
    assert marker.exists(), (
        "a skip must not block the baseline either (it is neither pass nor "
        "fail). " + result.stderr
    )


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
