"""`crew_status.py`: at most 40 lines, and it writes nothing.

Read-only is measured, not assumed: every file and directory in a real git
fixture -- `.git/` included, so an index refresh would show -- is stat'ed
before and after a run of the real script in a subprocess.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_status
from crew_fixtures import make_repo

SCRIPT = os.path.join(os.path.dirname(crew_status.__file__), "crew_status.py")


def _stat_tree(root):
    out = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            stat = os.lstat(path)
            out[os.path.relpath(path, root)] = (stat.st_mtime_ns, stat.st_size)
    return out


def _busy_repo(tmp_path):
    root = make_repo(tmp_path, config={"schema": 7, "tracker": "files",
                                       "roles": ["explorer", "qa-reviewer", "dba"]},
                     metrics=[("T-1", 0, 1)], codemap={"a": "anchor: x@0000000\n"},
                     handoff=True)
    tickets = root / ".work" / "tickets"
    tickets.mkdir()
    index = []
    for n in range(60):
        (tickets / f"T-{n:04d}.md").write_text("# t\n", encoding="utf-8")
        (tickets / f"T-{n:04d}").mkdir()
        index.append(f"T-{n:04d} | open | low | repo | t{n}")
    (root / ".work" / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    ledgers = root / ".git" / "crew" / "review"
    ledgers.mkdir(parents=True)
    for n in range(10):
        (ledgers / f"T-{n:04d}.json").write_text(json.dumps({"state": "OPEN", "rounds": [{}]}),
                                                 encoding="utf-8")
    return root


def _run(root, *args):
    return subprocess.run([sys.executable, SCRIPT, "--root", str(root), *args],
                          capture_output=True, text=True, check=False)


def test_status_is_read_only(tmp_path):
    root = _busy_repo(tmp_path)
    before = _stat_tree(root)

    done = _run(root, "--memory")

    assert (done.returncode, _stat_tree(root)) == (0, before)


def test_status_output_fits_forty_lines_on_a_busy_repo(tmp_path, monkeypatch, capsys):
    root = _busy_repo(tmp_path)
    stub = tmp_path / "crew_context.py"
    stub.write_text("for i in range(100):\n    print('stat line', i)\n", encoding="utf-8")
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(stub))

    crew_status.main(["--root", str(root), "--memory"])

    assert len(capsys.readouterr().out.splitlines()) <= 40


def test_memory_without_context_hook_says_not_installed(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(tmp_path / "absent.py"))

    lines = crew_status.collect(str(root), memory=True)

    assert lines[-1] == "memory   context hook not installed (crew_context.py absent)"


def test_memory_with_context_hook_shows_its_stats(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    stub = tmp_path / "crew_context.py"
    stub.write_text("import sys\nassert sys.argv[1:] == ['--stats']\nprint('injected 1200 chars')\n",
                    encoding="utf-8")
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(stub))

    lines = crew_status.collect(str(root), memory=True)

    assert lines[-1] == "memory   injected 1200 chars"


def test_memory_failing_context_hook_is_reported_not_hidden(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    stub = tmp_path / "crew_context.py"
    stub.write_text("import sys\nsys.exit('boom')\n", encoding="utf-8")
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(stub))

    lines = crew_status.collect(str(root), memory=True)

    assert lines[-1] == "memory   crew_context.py --stats failed (exit 1): boom"


@pytest.mark.parametrize("files,expected", [
    ({}, "config   none - run /crew:init"),
    ({"config.json": {"schema": 7, "roles": ["qa-reviewer"]}},
     "config   .crew/config.json schema 7 - run /crew:migrate"),
    ({"crew.json": {"schema": 1, "agents": ["explorer"], "tracker": {"kind": "jira"}}},
     "config   .crew/crew.json schema 1"),
])
def test_config_line_names_the_layout(tmp_path, files, expected):
    root = make_repo(tmp_path)
    for name, body in files.items():
        (root / ".crew" / name).write_text(json.dumps(body), encoding="utf-8")

    lines = crew_status.collect(str(root))

    assert lines[1] == expected


def test_memory_reports_the_requested_root_not_the_session_project(tmp_path, monkeypatch):
    """Codex FIX: CLAUDE_PROJECT_DIR=repo A, `--root` repo B -- the context
    script was left to find repo A."""
    root = make_repo(tmp_path)
    stub = tmp_path / "crew_context.py"
    stub.write_text("import os\nprint(os.environ.get('CLAUDE_PROJECT_DIR'))\n", encoding="utf-8")
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(stub))
    monkeypatch.setattr(crew_status, "_GIT_ENV",
                        dict(crew_status._GIT_ENV,  # pylint: disable=protected-access
                             CLAUDE_PROJECT_DIR=str(tmp_path / "repo-a")))

    lines = crew_status.collect(str(root), memory=True)

    assert lines[-1] == f"memory   {os.path.abspath(str(root))}"


def test_status_never_runs_a_configured_fsmonitor_hook(tmp_path):
    root = make_repo(tmp_path)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    subprocess.run(["git", "-C", str(root), "config", "core.fsmonitor", str(hook)], check=True)

    done = _run(root)

    assert (done.returncode, marker.exists()) == (0, False)


def test_corrupt_crew_json_is_reported_even_beside_a_valid_legacy_config(tmp_path):
    root = make_repo(tmp_path, config={"schema": 7, "roles": ["qa-reviewer"]})
    (root / ".crew" / "crew.json").write_text("{not json", encoding="utf-8")

    lines = crew_status.collect(str(root))

    assert lines[1] == "config   .crew/crew.json unreadable - status cannot tell the setup"


def test_index_rows_with_a_leading_pipe_are_reported_open(tmp_path):
    root = make_repo(tmp_path)
    (root / ".work" / "tickets").mkdir()
    (root / ".work" / "INDEX.md").write_text(
        "| id | status | size |\n|---|---|---|\n| T-0007 | open | low |\n", encoding="utf-8")

    lines = crew_status.collect(str(root))

    assert "open     T-0007" in lines
