"""The verify gate and crew's own bookkeeping (T-0068), both flavours.

TSS-510: in a repository whose `.gitignore` does not ignore `.crew/`, the
gate's own records (`.crew/.verify-gate.record.json`, `.timings.json`) and
the scope base are untracked changes. Under `"unmapped": "fail"` the next
gate run reported them as UNMAPPED CHANGES, and the refresh artifacts a
ticket's own refresh step commits (`.crew/codemap/`, `docs/diagrams/`) failed
the same way. Bookkeeping is now dropped from the changed list and a refresh
artifact is never unmapped -- while an ordinary unmapped file still fails, and
a rule that names a refresh artifact still runs.

Must-allow and must-block, through `verify-gate.sh` and `verify-gate.ps1`
(pwsh with OS=Windows_NT; skipped BY NAME when pwsh does not resolve, and a
skip is NOT a pass).
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        _PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")),
]

_CODEMAP_RULE = "test -z codemap-rule-ran"


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, codemap_rule=False):
    """`src/**` -> `true`, `"unmapped": "fail"`, and NO `.crew` ignore: the
    TSS shape. Everything crew reads is committed."""
    rules = [{"paths": ["src/**"], "reach": "local", "seconds": 1, "why": "fixture",
              "run": ["true"]}]
    if codemap_rule:
        rules.append({"paths": [".crew/codemap/**"], "reach": "local", "seconds": 1,
                      "why": "fixture", "run": [_CODEMAP_RULE]})
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": rules, "always": [], "default": [], "unmapped": "fail"}),
        encoding="utf-8")
    (root / ".crew" / "config.json").write_text('{"schema": 1}', encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "fixture")
    return root


def _run(flavour, root):
    if flavour == "sh":
        cmd = [_BASH, _SH]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    return crew_fixtures.run_gate(cmd, input="{}", cwd=str(root), env=env,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _bookkeeping(flavour, root):
    """The TSS-510 sequence: a passing gate run over a real change writes the
    gate's own records; the change is committed; the scope base and the
    metrics rows are written as crew writes them. Returns the bookkeeping
    paths now untracked."""
    _write(root, "src/a.py", "x = 2\n")
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    _git(root, "add", "src")
    _git(root, "commit", "-qm", "the ticket's change")
    _write(root, ".crew/.scope-base", '{"T-1": "0000000"}\n')
    _write(root, ".crew/metrics.md", "| 2026-10-04 | T-1 | codex (r1) | 0 | 0 |\n")
    _write(root, ".crew/metrics.jsonl", '{"ticket": "T-1"}\n')
    listed = subprocess.run(["git", "ls-files", "-o", "--exclude-standard"], cwd=root,
                            check=True, capture_output=True, text=True).stdout.split()
    assert ".crew/.verify-gate.record.json" in listed, listed
    return listed


def _write(root, rel, text="x\n"):
    target = root.joinpath(*rel.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_untracked_bookkeeping_is_not_unmapped(flavour, tmp_path):
    """Must-allow: the only changes are the gate's own records, the scope
    base and the rest of crew's bookkeeping."""
    root = _repo(tmp_path)
    _bookkeeping(flavour, root)

    done = _run(flavour, root)

    assert (done.returncode, "UNMAPPED CHANGES" in done.stderr) == (0, False), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_refresh_artifact_with_no_rule_is_not_unmapped(flavour, tmp_path):
    root = _repo(tmp_path)
    _write(root, ".crew/codemap/x.md")
    _write(root, "docs/diagrams/x.mmd")

    done = _run(flavour, root)

    assert (done.returncode, "UNMAPPED CHANGES" in done.stderr) == (0, False), done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_refresh_artifact_a_rule_names_still_runs_it(flavour, tmp_path):
    """Mapped, not dropped: a rule naming the code map still runs."""
    root = _repo(tmp_path, codemap_rule=True)
    _write(root, ".crew/codemap/x.md")

    done = _run(flavour, root)

    assert done.returncode == 2 and "codemap-rule-ran" in done.stderr, done.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_ordinary_unmapped_file_still_fails(flavour, tmp_path):
    """Must-block: `lib/x.py` beside the bookkeeping is unmapped, and it is
    the only path the report names."""
    root = _repo(tmp_path)
    paths = _bookkeeping(flavour, root)
    _write(root, "lib/x.py")

    done = _run(flavour, root)

    assert done.returncode == 2 and "UNMAPPED CHANGES" in done.stderr, done.stderr
    report = done.stderr.split("UNMAPPED CHANGES", 1)[1]
    assert "lib/x.py" in report
    assert not [p for p in paths if p in report.split()], report


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_crew_content_path_is_still_unmapped(flavour, tmp_path):
    """Must-block: crew's own config is not bookkeeping; changed and named by
    no rule, it fails under `"unmapped": "fail"`."""
    root = _repo(tmp_path)
    (root / ".crew" / "config.json").write_text('{"schema": 2}', encoding="utf-8")

    done = _run(flavour, root)

    assert done.returncode == 2 and ".crew/config.json" in done.stderr, done.stderr
