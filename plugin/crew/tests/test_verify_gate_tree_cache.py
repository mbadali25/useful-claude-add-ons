"""The verify gate's tree-pass cache (verify_record.passes_load / passes_save).

A command that passed is credited, not re-run, while the tree is byte-for-byte
the tree it passed on -- tree_snapshot(stable=True): HEAD, the deciders, and
every tracked and untracked path. MUST-ALLOW: an acutely deferred Stop on an
unchanged tree runs only what it has not run yet, and converges. MUST-BLOCK:
any edit anywhere, a rule that edits the tree while it runs, a failure,
CREW_VERIFY_FRESH=1 and a corrupt cache all mean "run it again".

Every rule appends to a log OUTSIDE the repo, so logging cannot itself change
the tree under test.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        not sys.platform.startswith("win") or _PWSH is None,
        reason="the .ps1 gate is the native-Windows flavour")),
]


def _rule(name, secs, log, extra=""):
    return {"paths": ["a.py"], "seconds": secs, "reach": "local",
            "run": [f"echo {name} >> '{log}'{extra}"], "why": name}


def _repo(tmp_path, rules):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                       timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True, capture_output=True,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root, check=True,
                   capture_output=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": rules, "default": [], "unmapped": "ignore"}), encoding="utf-8")
    return root


def _run(flavour, root, *extra, env=None):
    if flavour == "sh":
        cmd = [_BASH, _SH, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[a.replace("--all", "-All") for a in extra]]
    full = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    full.pop("CREW_VERIFY_FRESH", None)
    full.update(env or {})
    return crew_fixtures.run_gate(cmd, input="{}", cwd=str(root), env=full,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _forget_timings(root):
    """Drop the measured-timings cache between runs. A rule measured at 1s is
    priced at 1s (min(declared, measured)), which alone would let both 40s
    rules fit on the second run -- these tests must isolate the tree cache."""
    (root / ".crew" / ".verify-gate.timings.json").unlink(missing_ok=True)


def _log(path):
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def _marker(root):
    path = root / ".crew" / ".verify-verified-at"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _head(root):
    return subprocess.run(("git", "rev-parse", "HEAD"), cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_acutely_deferred_stop_converges_on_an_unchanged_tree(flavour, tmp_path):
    """MUST-ALLOW. 40 + 40 against the 60s budget: the first Stop runs A and
    defers B. The second, on the same tree, credits A and runs B -- instead
    of running A and deferring B for ever -- and the marker advances."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("A", 40, log), _rule("B", 40, log)])

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    assert _log(log) == ["A"], first.stderr
    assert _marker(root) != _head(root), first.stderr
    _forget_timings(root)

    second = _run(flavour, root)
    assert second.returncode == 0, second.stderr
    assert _log(log) == ["A", "B"], (
        "the second Stop on an unchanged tree re-ran A or never reached B. "
        + second.stderr)
    assert "PASSED on this exact tree in an earlier run - not re-run" in second.stderr
    assert _marker(root) == _head(root), second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("edit", ["the rule's own path", "an unrelated new file",
                                  "the verify map's why"])
def test_any_edit_anywhere_runs_it_again(flavour, edit, tmp_path):
    """MUST-BLOCK. The key is the whole tree, not the rule's `paths`: a rule
    reads more than the paths that trigger it."""
    log = tmp_path / "ran.log"
    rules = [_rule("A", 5, log)]
    root = _repo(tmp_path, rules)
    assert _run(flavour, root).returncode == 0
    assert _log(log) == ["A"]
    # The first run verified; un-verify so the second Stop runs the rule
    # again rather than skipping on the gate's own whole-tree fingerprint.
    for name in (".verify-verified-at", ".verify-gate.fingerprint"):
        (root / ".crew" / name).unlink(missing_ok=True)

    if edit == "the rule's own path":
        (root / "a.py").write_text("x = 2", encoding="utf-8")
    elif edit == "an unrelated new file":
        (root / "notes.txt").write_text("hi", encoding="utf-8")
    else:
        rules[0]["why"] = "edited"
        (root / ".crew" / "verify.json").write_text(json.dumps(
            {"version": 1, "rules": rules, "default": [], "unmapped": "ignore"}), encoding="utf-8")

    second = _run(flavour, root)
    assert second.returncode == 0, second.stderr
    assert _log(log) == ["A", "A"], ("after " + edit + " the cached pass was credited. "
                                     + second.stderr)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_that_edits_the_tree_leaves_no_cache(flavour, tmp_path):
    """MUST-BLOCK. The passes describe no single tree when the tree moved
    while the rules ran, so nothing is saved and the next run runs all."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("A", 40, log, " && echo y > generated.txt"),
                            _rule("B", 40, log)])
    assert _run(flavour, root).returncode == 0
    assert _log(log) == ["A"]
    assert not (root / ".crew" / ".verify-gate.passes.json").exists()
    _forget_timings(root)

    second = _run(flavour, root)
    assert _log(log) == ["A", "A"], second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_failure_is_never_cached(flavour, tmp_path):
    """MUST-BLOCK. Only "pass" is saved; a failing command runs again."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("F", 5, log, " && exit 1")])
    assert _run(flavour, root).returncode == 2
    second = _run(flavour, root)
    assert second.returncode == 2, second.stderr
    assert _log(log) == ["F", "F"], second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("how", ["fresh", "corrupt", "other-tree"])
def test_the_cache_can_always_be_refused(flavour, how, tmp_path):
    """MUST-BLOCK. CREW_VERIFY_FRESH=1, a corrupt cache and a cache for
    another tree all mean every command runs."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("A", 40, log), _rule("B", 40, log)])
    assert _run(flavour, root).returncode == 0
    passes = root / ".crew" / ".verify-gate.passes.json"
    assert passes.exists()
    env = None
    if how == "fresh":
        env = {"CREW_VERIFY_FRESH": "1"}
    elif how == "corrupt":
        passes.write_text("{ not json", encoding="utf-8")
    else:
        data = json.loads(passes.read_text(encoding="utf-8"))
        data["snapshot"] = "0" * len(data["snapshot"])
        passes.write_text(json.dumps(data), encoding="utf-8")

    _forget_timings(root)
    second = _run(flavour, root, env=env)
    assert second.returncode == 0, second.stderr
    assert _log(log) == ["A", "A"], how + ": " + second.stderr


def _unverify(root):
    """Drop both markers, so the next Stop re-matches and re-runs the rule
    rather than skipping on the gate's own whole-tree fingerprint."""
    for name in (".verify-verified-at", ".verify-gate.fingerprint"):
        (root / ".crew" / name).unlink(missing_ok=True)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_all_never_credits(flavour, tmp_path):
    """MUST-BLOCK (review r1). --all means run everything: a pass cached for
    this very tree is not credited there, though Stop would credit it."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("A", 5, log)])
    assert _run(flavour, root).returncode == 0
    assert (root / ".crew" / ".verify-gate.passes.json").exists()

    second = _run(flavour, root, "--all")
    assert second.returncode == 0, second.stderr
    assert _log(log) == ["A", "A"], "--all credited a cached pass. " + second.stderr
    assert "not re-run" not in second.stderr, second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_moved_ref_runs_it_again(flavour, tmp_path):
    """MUST-BLOCK (review r1). A rule may read a ref the working tree does not
    show (rules[39] diffs origin/main...HEAD), so a fetch that moves one is
    as much a new tree as an edit."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("A", 5, log)])
    assert _run(flavour, root).returncode == 0
    _unverify(root)
    subprocess.run(("git", "update-ref", "refs/remotes/origin/main", "HEAD"), cwd=root,
                   check=True, capture_output=True,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)

    second = _run(flavour, root)
    assert second.returncode == 0, second.stderr
    assert _log(log) == ["A", "A"], "a moved ref left the cached pass credited. " + second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_tree_that_moves_after_a_credit_withdraws_it(flavour, tmp_path):
    """MUST-BLOCK (review r1). The second Stop credits A for the tree it
    started on, then B edits the tree. A was never checked against the tree
    the run ended on, so the run is not verified: the marker stays put and
    the next Stop runs A and B again -- and, the tree now stable, converges."""
    log = tmp_path / "ran.log"
    root = _repo(tmp_path, [_rule("A", 40, log),
                            _rule("B", 40, log, " && echo y > generated.txt")])
    assert _run(flavour, root).returncode == 0
    assert _log(log) == ["A"]
    _forget_timings(root)

    second = _run(flavour, root)
    assert second.returncode == 0, second.stderr
    assert _log(log) == ["A", "B"], second.stderr
    assert "withdrawn" in second.stderr, second.stderr
    assert _marker(root) != _head(root), (
        "the marker advanced on a credit the moved tree withdrew. " + second.stderr)
    assert not (root / ".crew" / ".verify-gate.passes.json").exists()
    _forget_timings(root)

    third = _run(flavour, root)
    assert third.returncode == 0, third.stderr
    assert _log(log) == ["A", "B", "A"], third.stderr
    _forget_timings(root)
    fourth = _run(flavour, root)
    assert fourth.returncode == 0, fourth.stderr
    assert _log(log) == ["A", "B", "A", "B"], fourth.stderr
    assert _marker(root) == _head(root), fourth.stderr
