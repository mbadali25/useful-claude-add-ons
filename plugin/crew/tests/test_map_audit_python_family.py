"""`map-audit.sh` resolves the python FAMILY, like every other script here.

Reported 2026-09-22. `map-audit.sh:7` invoked a bare `python3 - << 'PY'`.
Git Bash ships without `python3`, so on a machine carrying `python` but not
`python3` -- which is most Windows installs, and CLAUDE.md's own named
landmine -- the audit died at 127 while `resolve-tools.sh:20`, reading the
same `.crew/verify.json` from the same directory, resolved fine.

This was always LOUD (127 is not 0), so it is the smaller of the two defects
fixed in this change: an inconsistency, not a silent pass. What 127 is not is
*legible* -- it is the shell saying a name was not found, with nothing naming
which name or what to do -- so the no-python path now says so itself.

`map-audit.sh` is read-only and is not a hook: it gates nothing and blocks
nothing, so the hardened execute-probe `_common.sh`'s `crew_py_strict` uses is
deliberately NOT ported here. A WindowsApps stub would still make this script
print nothing and exit non-zero -- which is the loud shape, not the silent one
the pm-pulse fix was about. Recorded in TODO.md rather than fixed.

Everything below drives the real script. `map-audit.sh` uses only shell
builtins around the python call, so a PATH holding nothing but the
interpreter under test is enough to run it -- which is what makes "python3
is absent" testable at all on a POSIX host.
"""
import json
import os
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_MAP_AUDIT = os.path.join(_ROOT, "skills", "crew-setup", "scripts",
                          "map-audit.sh")

_BASH = crew_fixtures.resolve_bash()
pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")

# Printed by the audit itself, so "it ran" is read off its output rather than
# inferred from a status. The bare-`python3` version produced none of this.
_REPORT_MARKER = "== checks on disk with no rule (they never run) =="


def _repo_with_map(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "verify.json").write_text(
        json.dumps({"rules": [{"paths": ["**/*.py"], "run": ["true"]}],
                    "always": [], "default": []}),
        encoding="utf-8")
    return root


def _pathdir_with(tmp_path, names):
    """A directory holding `names`, each a copy of the real interpreter.

    A copy rather than a symlink: on Windows a symlink needs a privilege the
    test runner may not hold, and the point of the directory is only that
    `command -v <name>` finds something that really runs.
    """
    real = shutil.which("python3") or shutil.which("python")
    assert real, "this test needs a real interpreter to copy"
    d = tmp_path / "onlypath"
    d.mkdir()
    for name in names:
        dest = d / name
        shutil.copy2(real, dest)
        os.chmod(dest, 0o755)
    return d


def _run(root, path_dir):
    return subprocess.run(
        [_BASH, _MAP_AUDIT], capture_output=True, text=True, check=False,
        stdin=subprocess.DEVNULL,
        env={"PATH": str(path_dir), "CLAUDE_PROJECT_DIR": str(root)},
        cwd=str(root))


def test_python_without_python3_still_audits(tmp_path):
    """Must-allow, and the reported case. `python` exists, `python3` does
    not -- Git Bash's own layout. Sabotaging the resolver back to a bare
    `python3` turns this red with exit 127 and an empty report."""
    root = _repo_with_map(tmp_path)
    proc = _run(root, _pathdir_with(tmp_path, ("python",)))

    assert _REPORT_MARKER in proc.stdout, (
        "the audit must run with only `python` on PATH. exit %d stdout %r "
        "stderr %r" % (proc.returncode, proc.stdout[:200], proc.stderr[:200]))
    assert proc.returncode == 0, proc.stderr[:200]


def test_python3_is_still_preferred_when_present(tmp_path):
    """Must-allow twin: the fix must not have reordered the family."""
    root = _repo_with_map(tmp_path)
    proc = _run(root, _pathdir_with(tmp_path, ("python3", "python")))

    assert _REPORT_MARKER in proc.stdout, proc.stdout[:200]
    assert proc.returncode == 0, proc.stderr[:200]


def test_no_python_at_all_names_itself_instead_of_exiting_127(tmp_path):
    """Must-block: no interpreter under any name. The script has to say so
    in its own words -- a bare 127 from the shell names nothing."""
    root = _repo_with_map(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    proc = _run(root, empty)

    assert "map-audit: no python found" in proc.stderr, (
        "the script must name the failure itself. exit %d stderr %r"
        % (proc.returncode, proc.stderr[:200]))
    assert proc.returncode != 0, (
        "and must not exit 0 -- an audit that printed no report did not "
        "find nothing, it did not run. stdout: " + proc.stdout[:200])
    assert _REPORT_MARKER not in proc.stdout


def test_absent_map_is_unchanged(tmp_path):
    """Must-allow: the early return above the python call is untouched."""
    root = tmp_path / "plain"
    (root / ".crew").mkdir(parents=True)

    proc = _run(root, _pathdir_with(tmp_path, ("python3",)))

    assert proc.returncode == 0, proc.stderr[:200]
    assert "run /crew:verify" in proc.stdout, proc.stdout[:200]
