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
import crew_shell
import crew_status
import review_ledger
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


def test_status_is_read_only_with_the_windows_shell_line(tmp_path, monkeypatch):
    """The subprocess test above shows the shell line only on a Windows host,
    so the same property is measured here in-process with the line forced on:
    the repo AND the machine-local cache directory are unchanged."""
    root = _busy_repo(tmp_path)
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "windows-bash")
    crew_shell.write_cache({"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"})
    cache_dir = os.path.dirname(crew_shell.probe_path())
    before = (_stat_tree(root), _stat_tree(cache_dir))

    lines = crew_status.collect(str(root), memory=True)

    assert any(line.startswith("shell    ") for line in lines)
    assert (_stat_tree(root), _stat_tree(cache_dir)) == before


def test_status_output_fits_forty_lines_on_a_busy_repo(tmp_path, monkeypatch, capsys):
    root = _busy_repo(tmp_path)
    stub = tmp_path / "crew_context.py"
    stub.write_text("for i in range(100):\n    print('stat line', i)\n", encoding="utf-8")
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(stub))
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "windows-bash")

    crew_status.main(["--root", str(root), "--memory"])

    out = capsys.readouterr().out.splitlines()
    assert len(out) <= 40
    assert any(line.startswith("shell    ") for line in out)


@pytest.mark.parametrize("host", ["linux", "macos", "wsl"])
def test_status_has_no_shell_line_off_windows(tmp_path, monkeypatch, host):
    root = make_repo(tmp_path)
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: host)
    without = crew_status.collect(str(root))
    crew_shell.write_cache({"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"})

    with_cache = crew_status.collect(str(root))

    assert "\n".join(with_cache).encode() == "\n".join(without).encode()
    assert not any(line.startswith("shell") for line in with_cache)


PWSH7 = "C:/Program Files/PowerShell/7/pwsh.exe"
_SPLIT = "direct (plain argv) / gitbash (bash syntax)"
_INSTALL = "recommend `wsl --install -d Ubuntu` in an elevated shell, then reboot"


@pytest.mark.parametrize("mode,cache,location,expected", [
    ("auto", {"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"}, "wsl-fs",
     "shell    auto -> wsl (Ubuntu-24.04) - WSL2 usable and the repo is inside WSL"),
    ("auto", {"state": "not-installed", "detail": "wsl.exe is not on PATH"}, "windows-drive",
     f"shell    auto -> {_SPLIT} - WSL not-installed (wsl.exe is not on PATH); {_INSTALL}"),
    ("powershell", {"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"}, "windows-drive",
     f"shell    powershell -> {PWSH7} (plain argv) / gitbash (bash syntax) - a bash string is never handed to pwsh"),
    ("gitbash", {"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"}, "windows-drive",
     "shell    gitbash -> gitbash - set by shellRoute.mode"),
    ("auto", None, "windows-drive",
     f"shell    auto -> {_SPLIT} - WSL never probed - run /crew:config"),
    ("auto", {"state": "broken", "detail": "wsl.exe --list --verbose timed out after 15s"}, "windows-drive",
     f"shell    auto -> {_SPLIT} - WSL broken (wsl.exe --list --verbose timed out after 15s)"),
    ("native", {"state": "usable", "distro": "Ubuntu-24.04", "detail": "ok"}, "windows-drive",
     f"shell    auto (shellRoute.mode 'native' is not a mode) -> {_SPLIT} - WSL usable but this repo is on a "
     "Windows drive and not measured (crew_shell.py measure --write)"),
])
def test_status_shell_line_on_windows(tmp_path, monkeypatch, mode, cache, location, expected):
    root = make_repo(tmp_path, config={"schema": 7, "shellRoute": {"mode": mode, "distro": None}})
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "windows-bash")
    monkeypatch.setattr(crew_shell, "repo_location", lambda _root: location)
    # Faked with repo_location, as test_crew_shell.py does: a WSL route also
    # translates the real tmp_path, which is a drive path on Windows but a POSIX
    # path on Linux CI, and to_wsl_path rightly refuses the latter.
    monkeypatch.setattr(crew_shell, "to_wsl_path", lambda p, distro=None: ("/home/u/repo", ""))
    monkeypatch.setattr(crew_shell, "resolve_pwsh", lambda *a, **k: (PWSH7, "pwsh reason"))
    if cache is not None:
        crew_shell.write_cache(cache)

    lines = crew_status.collect(str(root))

    assert expected in lines
    assert lines.index(expected) == next(i for i, line in enumerate(lines) if line.startswith("verify")) + 1


def test_status_shell_line_runs_no_subprocess(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setattr(crew_shell, "host_os", lambda *a, **k: "windows-bash")

    def forbidden(*_a, **_k):
        raise AssertionError("status ran a subprocess")
    for name in ("run", "Popen", "check_output", "call"):
        monkeypatch.setattr(crew_shell.subprocess, name, forbidden)

    line = crew_shell.status_line(str(root))

    assert line.startswith("shell    auto -> ")


def test_memory_without_context_hook_says_not_installed(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setattr(crew_status, "CONTEXT_SCRIPT", str(tmp_path / "absent.py"))

    lines = crew_status.collect(str(root), memory=True)

    assert lines[-1] == "memory   context hook not installed (crew_context.py absent)"


def test_memory_with_context_hook_shows_its_stats(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    stub = tmp_path / "crew_context.py"
    stub.write_text("import sys\nassert sys.argv[1:3] == ['--stats', '--root']\nprint('injected 1200 chars')\n",
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


def test_memory_reads_the_real_context_log_of_root_not_the_session_project(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setitem(crew_status._GIT_ENV, "CLAUDE_PROJECT_DIR", str(elsewhere))  # pylint: disable=protected-access

    lines = crew_status.collect(str(root), memory=True)

    memory = next(line for line in lines if line.startswith("memory"))
    assert memory == f"memory   crew context log: {root / '.git' / 'crew' / 'context-log.jsonl'}"


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


def _review(verdict, failure_class=None):
    return {"verdict": verdict, "counts": {"BLOCK": 0, "FIX": 1, "NIT": 0},
            "bundle_sha256": "b" * 64, "base": "c" * 40, "head": "c" * 40,
            "model_family": "gpt", "provider": "codex", "model": None,
            "failure_class": failure_class}


def test_status_review_line_shows_budget_and_refunds(tmp_path):
    root = make_repo(tmp_path)
    for verdict, failure in (("INCOMPLETE", "tool"), ("FINDINGS", None)):
        _, number, _ = review_ledger.reserve(str(root), "T1", "codex")
        review_ledger.record(str(root), "T1", number, _review(verdict, failure))

    done = _run(root)

    assert "review   T1: REVIEWED, 1/2 rounds used, 1 refunded" in done.stdout, done.stdout


def test_status_review_line_for_an_unreadable_ledger_is_unknown(tmp_path):
    root = make_repo(tmp_path)
    path = review_ledger.ledger_path(str(root), "T1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")

    done = _run(root)

    assert "review   T1: UNKNOWN (ledger unreadable)" in done.stdout, done.stdout


def _ledger_text(root, text):
    path = review_ledger.ledger_path(str(root), "T1")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.mark.parametrize("successors", ['{"x": 1}', "[1]", '"abc"', "[{}, null]"])
def test_status_review_line_for_malformed_successors_is_unknown(tmp_path, successors):
    root = make_repo(tmp_path)
    _ledger_text(root, '{"state": "REVIEWED", "rounds": [], "successors": %s}' % successors)

    done = _run(root)

    assert (done.returncode, "review   T1: UNKNOWN (ledger unreadable)" in done.stdout) == (
        0, True), done.stdout + done.stderr


def test_status_review_line_survives_rounds_that_are_not_objects(tmp_path):
    root = make_repo(tmp_path)
    _ledger_text(root, '{"state": "REVIEWED", "rounds": [1, "x"]}')

    done = _run(root)

    assert (done.returncode, "review   T1: REVIEWED, 2/2 rounds used" in done.stdout) == (
        0, True), done.stdout + done.stderr


# --- T-0049: in-flight markers ------------------------------------------------------

def _inflight_marker(root, ticket, **over):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    folder = crew_inflight.inflight_dir(str(root))
    os.makedirs(folder, exist_ok=True)
    marker = {"schema": 1, "ticket": ticket, "runner": "lane", "token": "t", "session": "s",
              "pid": None, "pid_start": None, "pidns": "", "boot_id": "", "host": "h",
              "worktree": "/elsewhere/wt", "branch": "b", "since": "2026-10-04T10:00:00+00:00",
              "heartbeat_at": "2026-10-04T10:00:00+00:00"}
    marker.update(over)
    with open(os.path.join(folder, f"{ticket}.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(marker))
    return folder


def _inflight(lines):
    return [line for line in lines if line.startswith("in-flight")]


def test_status_inflight_lines(tmp_path):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path)
    _inflight_marker(root, "T-1")
    folder = _inflight_marker(root, "T-2")
    with open(os.path.join(folder, "T-3.json"), "w", encoding="utf-8") as handle:
        handle.write("{bad")

    got = _inflight(crew_status.collect(str(root)))

    assert got[0].startswith("in-flight: T-1 stale runner=lane since=2026-10-04T10:00:00+00:00")
    assert got[0].endswith("clear: " + crew_inflight.clear_command("T-1"))
    assert got[1].startswith("in-flight: T-2 stale")
    assert got[2].startswith("in-flight: T-3 unknown") and "clear: " in got[2]
    assert len(got) == 3 and all(line.isprintable() for line in got)


def test_status_inflight_none(tmp_path):
    root = make_repo(tmp_path)
    assert _inflight(crew_status.collect(str(root))) == ["in-flight: none"]


def test_status_inflight_unknown_dir(tmp_path):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path)
    folder = crew_inflight.inflight_dir(str(root))
    os.makedirs(os.path.dirname(folder), exist_ok=True)
    with open(folder, "w", encoding="utf-8") as handle:
        handle.write("not a directory")

    got = _inflight(crew_status.collect(str(root)))

    assert len(got) == 1 and got[0].startswith("in-flight: unknown - ")


def test_status_inflight_import_error_is_unknown(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setitem(sys.modules, "crew_inflight", None)

    got = _inflight(crew_status.collect(str(root)))

    assert len(got) == 1 and got[0].startswith("in-flight: unknown - ")


def test_status_inflight_caps_at_five(tmp_path):
    root = make_repo(tmp_path)
    for n in range(8):
        _inflight_marker(root, f"T-{n}")

    got = _inflight(crew_status.collect(str(root)))

    assert (len(got), got[-1]) == (6, "in-flight: +3 more")


def test_status_inflight_is_read_only_and_fits(tmp_path):
    root = _busy_repo(tmp_path)
    for n in range(8):
        _inflight_marker(root, f"T-{n}", worktree="/w/x y")
    before = _stat_tree(root)

    done = _run(root, "--memory")

    lines = done.stdout.splitlines()
    assert (done.returncode, _stat_tree(root)) == (0, before)
    assert len(lines) <= 40 and len(_inflight(lines)) == 6
