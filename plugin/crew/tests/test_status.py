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
import tool_fixtures
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


def _graph_ignore_line(out):
    lines = [line for line in out.splitlines() if line.startswith("graph-ignore")]
    assert len(lines) == 1, out
    return lines[0]


def _uncovered_repo(tmp_path):
    root = make_repo(tmp_path)
    (root / ".env").write_text("PW=x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "env"], cwd=root, check=True,
                   capture_output=True)
    return root


def test_status_flags_uncovered_denylisted_path(tmp_path):
    """T-0064: graphify's post-commit hook bypasses crew, so this line is the
    warning that the next build would read a secrets-denylisted file."""
    root = _uncovered_repo(tmp_path)

    line = _graph_ignore_line(_run(root).stdout)

    assert (line.startswith("graph-ignore  UNCOVERED"), ".env" in line,
            "crew_graph_ignore.py --write" in line) == (True, True, True), line


@pytest.mark.parametrize("case,prefix", [
    ("covered", "graph-ignore  ok"),
    ("unknown", "graph-ignore  unknown - "),
], ids=["covered", "unknown"])
def test_status_graph_ignore_ok_and_unknown(tmp_path, case, prefix):
    root = _uncovered_repo(tmp_path)
    if case == "covered":
        (root / ".graphifyignore").write_text(".env\n", encoding="utf-8")
    else:
        (root / ".claude").mkdir()
        (root / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")

    line = _graph_ignore_line(_run(root).stdout)

    assert line.startswith(prefix), line


# ESC and LF cannot be in a Windows file name; U+202E (a format character) and
# U+2028 (a line separator) can, and must be escaped the same way.
_HOSTILE = (("Z\x1b[2J.PEM", "ID_RSA\ngraph-ignore  ok") if sys.platform != "win32"
            else ("Z\u202e[2J.PEM", "ID_RSA\u2028graph-ignore  ok"))


def test_status_graph_ignore_line_escapes_hostile_names(tmp_path):
    """A tracked name carrying ESC, or a newline that would forge a second
    `graph-ignore  ok` line, is printed in its escaped form, never raw."""
    root = make_repo(tmp_path)
    for name in _HOSTILE:
        (root / name).write_text("k\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "--", *_HOSTILE], cwd=root, check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "keys"], cwd=root, check=True,
                   capture_output=True)

    out = _run(root).stdout
    line = _graph_ignore_line(out)

    assert (any(c in out for c in "\x1b\u202e\u2028"), ascii(_HOSTILE[0]) in line,
            ascii(_HOSTILE[1]) in line) == (
        False, True, True), out


def test_status_graph_ignore_line_is_read_only(tmp_path):
    root = _uncovered_repo(tmp_path)
    before = _stat_tree(root)

    done = _run(root)

    assert (done.returncode, "UNCOVERED" in done.stdout, _stat_tree(root)) == (0, True, before)


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


# --- T-0070: inert settings, and the approvals that actually need you -------

def test_status_names_inert_settings(tmp_path):
    root = make_repo(tmp_path, config={"autopilot": {"maxTicketsPerRun": 3}})
    lines = [l for l in crew_status.collect(str(root)) if l.startswith("inert")]
    assert lines == ["inert    autopilot.maxTicketsPerRun=3 (L-0541)"]


def test_status_is_quiet_without_inert_settings(tmp_path):
    root = make_repo(tmp_path, config={"autopilot": {"mode": "plan", "approval": "self"}})
    assert [l for l in crew_status.collect(str(root)) if l.startswith("inert")] == []


def test_status_escapes_control_characters_in_inert_settings(tmp_path):
    from test_crew_config_inert import INERT_HOSTILE, assert_inert_escaped  # pylint: disable=import-outside-toplevel
    root = make_repo(tmp_path, config=INERT_HOSTILE)
    assert_inert_escaped("\n".join(crew_status.collect(str(root))))


def _approvals_repo(tmp_path):
    # pylint: disable=import-outside-toplevel
    import crew_ticket
    from scope_fixtures import make_repo as scope_repo, make_ticket
    root = scope_repo(tmp_path)        # scope.allowCliApproval is unset: false
    for ticket in ("T-1", "T-2", "T-3", "T-4", "T-5", "T-6", "T-7"):
        make_ticket(root, ticket, activate=False)
    t4 = root / ".work" / "tickets" / "T-4" / "spec.md"
    t4.write_text(t4.read_text(encoding="utf-8").replace(
        "# T-4\n", "# T-4 widget    status: planned   risk: low\n"), encoding="utf-8")
    for ticket in ("T-2", "T-4"):
        crew_ticket.approve(str(root), ticket, by="owner", via=crew_ticket.USER_PROMPT)
    crew_ticket.approve(str(root), "T-3", by="owner", via=crew_ticket.CLI)
    plan = root / ".work" / "tickets" / "T-2" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    # T-0026: the header's status value alone never makes a receipt stale.
    t4.write_text(t4.read_text(encoding="utf-8").replace("status: planned", "status: review"),
                  encoding="utf-8")
    (root / ".work" / "tickets" / "T-6" / "plan.md").unlink()
    spec7 = root / ".work" / "tickets" / "T-7" / "spec.md"
    spec7.write_text(spec7.read_text(encoding="utf-8").replace("## Intent\n", "## Other\n"),
                     encoding="utf-8")
    rows = ["| Ticket | Status | Title |", "| --- | --- | --- |"]
    rows += [f"| T-{n} | {'merged' if n == 5 else 'open'} | t{n} |" for n in range(1, 8)]
    (root / ".work" / "INDEX.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root


def test_status_approvals_lists_only_what_needs_you(tmp_path):
    root = _approvals_repo(tmp_path)
    done = _run(root, "--approvals")
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    # Each paste line is the command alone (T-0070 port review BLOCK: a reason
    # on the same line parsed as a group of three ids); its reason follows.
    assert lines[0:6:2] == ["/crew:approve T-1", "/crew:approve T-2", "/crew:approve T-3"], lines
    assert lines[1] == "  why: no approval"
    assert lines[3].startswith("  why: stale: ")
    assert lines[5].startswith("  why: unaccepted: ")
    assert lines[6:] == [
        "1 ticket with a spec and plan that do not validate is not listed: T-7"]
    for absent in ("T-4", "T-5", "T-6"):
        assert absent not in done.stdout


def test_status_approvals_paste_line_approves_one_ticket(tmp_path):
    """The printed line, pasted whole, is the approval hook's single form."""
    import approval_hook  # pylint: disable=import-outside-toplevel
    root = _approvals_repo(tmp_path)
    lines = _run(root, "--approvals").stdout.splitlines()

    got = [approval_hook.parse(line) for line in lines if line.startswith("/crew:approve")]
    assert [(r.kind, r.ids) for r in got] == [
        (approval_hook.SINGLE, (t,)) for t in ("T-1", "T-2", "T-3")]


def test_status_approvals_reads_the_main_index_from_a_linked_worktree(tmp_path):
    """T-0070 port review FIX: a linked worktree with no INDEX of its own reads
    the main checkout's rows, never `could not tell (no .work/INDEX.md)`."""
    import shutil  # pylint: disable=import-outside-toplevel
    root = _approvals_repo(tmp_path / "main")
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "-q", "-b", "wt", str(wt)],
                   check=True, capture_output=True)
    shutil.rmtree(wt / ".work", ignore_errors=True)
    shutil.copytree(root / ".work" / "tickets" / "T-1", wt / ".work" / "tickets" / "T-1")

    lines = _run(wt, "--approvals").stdout.splitlines()

    assert lines[:2] == ["/crew:approve T-1", "  why: no approval"], lines


def test_status_approvals_cannot_tell_when_the_main_index_is_unreadable(tmp_path):
    """T-0070 port review r2 BLOCK: a linked worktree WITH a local INDEX still
    reads the main checkout's rows, so an unreadable main INDEX is could not
    tell, never `nothing needs approval`."""
    root = _approvals_repo(tmp_path / "main")
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "-q", "-b", "wt", str(wt)],
                   check=True, capture_output=True)
    (wt / ".work").mkdir(exist_ok=True)
    (wt / ".work" / "INDEX.md").write_text("| Ticket | Status | Title |\n| --- | --- | --- |\n",
                                           encoding="utf-8")
    (root / ".work" / "INDEX.md").write_bytes(b"| T-1 | open | \xff\xfe |\n")

    lines = _run(wt, "--approvals").stdout.splitlines()

    assert len(lines) == 1 and lines[0].startswith("could not tell ("), lines
    assert "is not UTF-8" in lines[0], lines


def test_status_approvals_names_a_main_checkout_with_no_index(tmp_path):
    """T-0070 port review r3: a linked worktree whose main checkout has no
    INDEX says so under its answer, so `nothing needs approval` never reads as
    a verdict on rows the main checkout does not have."""
    root = _approvals_repo(tmp_path / "main")
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "-q", "-b", "wt", str(wt)],
                   check=True, capture_output=True)
    (wt / ".work").mkdir(exist_ok=True)
    (wt / ".work" / "INDEX.md").write_text("| Ticket | Status | Title |\n| --- | --- | --- |\n",
                                           encoding="utf-8")
    (root / ".work" / "INDEX.md").unlink()

    lines = _run(wt, "--approvals").stdout.splitlines()

    assert lines[0] == "nothing needs approval", lines
    assert lines[1].startswith("note: the main checkout (") and "no .work/INDEX.md" in lines[1]


def test_status_approvals_cannot_tell_when_the_two_indexes_disagree(tmp_path):
    """T-0070 port review r7 BLOCK: a ticket closed here and open in the main
    checkout (or the reverse) is left out of the walk; could not tell."""
    root = _approvals_repo(tmp_path / "main")
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "-q", "-b", "wt", str(wt)],
                   check=True, capture_output=True)
    (wt / ".work").mkdir(exist_ok=True)
    (wt / ".work" / "INDEX.md").write_text("| T-1 | done | x |\n", encoding="utf-8")

    lines = _run(wt, "--approvals").stdout.splitlines()

    assert len(lines) == 1 and lines[0].startswith("could not tell (") and "T-1" in lines[0], lines


def test_status_approvals_says_nothing_needs_approval(tmp_path):
    root = make_repo(tmp_path, config={})
    (root / ".work" / "INDEX.md").write_text("| Ticket | Status | Title |\n| --- | --- | --- |\n",
                                             encoding="utf-8")
    done = _run(root, "--approvals")
    assert (done.returncode, done.stdout.strip()) == (0, "nothing needs approval")


def _corrupt_index(index):
    index.write_bytes(b"| T-1 | open | t\xff\xfe1 |\n")


def _index_is_a_directory(index):
    index.mkdir()


# An INDEX crew cannot read is "could not tell", never "nothing needs approval":
# T-1..T-3 below each still have a spec and a plan that need approving.
@pytest.mark.parametrize("damage,reason", [
    (os.unlink, "no .work/INDEX.md"),
    (_corrupt_index, ".work/INDEX.md is not UTF-8"),
    # open() on a directory raises IsADirectoryError on POSIX and
    # PermissionError on Windows (EACCES from CreateFile): both are an
    # unreadable INDEX, and the reason names what was raised.
    (_index_is_a_directory, ".work/INDEX.md could not be read: "
     + ("PermissionError" if os.name == "nt" else "IsADirectoryError")),
])
def test_status_approvals_says_unknown_when_the_index_cannot_be_read(tmp_path, damage, reason):
    root = _approvals_repo(tmp_path)
    index = root / ".work" / "INDEX.md"
    index.unlink()
    if damage is not os.unlink:
        damage(index)
    done = _run(root, "--approvals")
    assert (done.returncode, done.stdout.strip()) == (0, f"could not tell ({reason})"), \
        done.stdout + done.stderr


def test_status_approvals_is_read_only(tmp_path):
    root = _approvals_repo(tmp_path)
    before = _stat_tree(root)
    done = _run(root, "--approvals")
    assert (done.returncode, _stat_tree(root)) == (0, before)


def test_status_tree_runs_the_git_which_resolves(tmp_path, monkeypatch):
    # L-1508: the tree line judges the git PATH resolves the way bash, pwsh
    # and shutil.which do (PATHEXT: git.cmd). The failing git is NOT on PATH:
    # a bare "git" runs the real one and a clean fixture reads "tree clean".
    root = make_repo(tmp_path)
    tool_fixtures.which_only(monkeypatch, tmp_path / "resolved", "git")

    first = crew_status.collect(str(root))[0]

    assert first.endswith("?@?  tree unknown"), first


def test_status_tree_is_unknown_when_git_does_not_resolve(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    tool_fixtures.which_none(monkeypatch, "git")

    first = crew_status.collect(str(root))[0]

    assert first.endswith("?@?  tree unknown"), first


# --- T-0037: needs-owner gets its own line; cancelled and superseded none ---

def _tickets_with(tmp_path, rows):
    root = make_repo(tmp_path)
    (root / ".work" / "tickets").mkdir()
    (root / ".work" / "INDEX.md").write_text(rows, encoding="utf-8", newline="\n")
    return crew_status._ticket_lines(str(root))  # pylint: disable=protected-access


def test_status_lists_needs_owner_line(tmp_path):
    rows = "".join(f"T-{n} | needs-owner | low | r | t\n" for n in range(1, 8)) + "T-9 | review | low | r | t\n"

    assert _tickets_with(tmp_path, rows) == [
        "tickets  0 ticket dir(s), 0 legacy file(s)", "open     T-9",
        "owner    T-1, T-2, T-3, T-4, T-5 (+2) (needs-owner)"]


def test_status_hides_closed_words(tmp_path):
    rows = "T-1 | cancelled | low | r | t\n| T-2 | Superseded | low | r | t |\nT-3 | Needs-Owner | low | r | t\n"

    assert _tickets_with(tmp_path, rows) == [
        "tickets  0 ticket dir(s), 0 legacy file(s)", "owner    T-3 (needs-owner)"]


def test_status_unchanged_without_new_words(tmp_path):
    """Today's words only: exactly the lines status printed before T-0037."""
    rows = ("| id | status |\n|---|---|\n| T-1 | open | low |\nT-2 | in progress | low\n"
            "T-3 | done | low\nT-4 | review | low\nT-5 | spec | low\n")

    assert _tickets_with(tmp_path, rows) == [
        "tickets  0 ticket dir(s), 0 legacy file(s)", "open     T-1, T-2, T-4"]
# --- T-0039: the gitignore line ---------------------------------------------------------

def _gitignore_line(lines):
    found = [line for line in lines if line.startswith("gitignore ")]
    assert len(found) == 1, lines
    return found[0]


def test_status_gitignore_line_current(tmp_path):
    root = make_repo(tmp_path)
    assert subprocess.run([sys.executable, os.path.join(os.path.dirname(SCRIPT), "crew_gitignore.py"),
                           "apply", "--root", str(root)], capture_output=True, check=False).returncode == 0

    lines = crew_status.collect(str(root))

    assert _gitignore_line(lines) == "gitignore current"
    assert lines.index("gitignore current") == next(
        i for i, line in enumerate(lines) if line.startswith("codemap")) + 1


def test_status_gitignore_line_missing_names_languages(tmp_path):
    root = make_repo(tmp_path)
    (root / "app.py").write_text("", encoding="utf-8")
    (root / ".gitignore").write_text(".env\n.env.*\n*.pem\n*.key\n*.p12\n*.pfx\nid_rsa\nid_ed25519\n"
                                     ".DS_Store\nThumbs.db\n[Dd]esktop.ini\n*.swp\n.idea/\n.vscode/*\n",
                                     encoding="utf-8")

    line = _gitignore_line(crew_status.collect(str(root)))

    assert line == "gitignore 8 missing (python)"


def test_status_gitignore_line_owner(tmp_path):
    root = make_repo(tmp_path)
    (root / "server.pem").write_text("k", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "server.pem"], check=True)

    line = _gitignore_line(crew_status.collect(str(root)))

    assert line == "gitignore owner: 1 tracked secret-shaped file(s) - server.pem"


def test_status_gitignore_line_unknown_when_git_fails(tmp_path, monkeypatch):
    root = make_repo(tmp_path, git=False)

    lines = crew_status.collect(str(root))

    assert _gitignore_line(lines) == "gitignore unknown (not a git repository)"
    monkeypatch.setitem(sys.modules, "crew_gitignore", None)  # the import itself fails
    lines = crew_status.collect(str(make_repo(tmp_path / "second")))
    assert _gitignore_line(lines) == "gitignore unknown (crew_gitignore.py not importable)"
    assert len(lines) <= crew_status.MAX_LINES


# --- L-0551: the waiting line and --owner ---------------------------------------

def _waiting_repo(tmp_path, approvals=2):
    """`approvals` tickets each awaiting approval (spec and plan, no receipt)."""
    import scope_fixtures  # pylint: disable=import-outside-toplevel
    root = scope_fixtures.make_repo(tmp_path, mode="off")
    rows = []
    for n in range(1, approvals + 1):
        ticket = f"T-{n}"
        folder = root / ".work" / "tickets" / ticket
        folder.mkdir(parents=True)
        (folder / "direction.md").write_text("go\n", encoding="utf-8")
        body = scope_fixtures.SPEC.format(ticket=ticket, touch="- `src/**`")
        first, rest = body.split("\n", 1)
        (folder / "spec.md").write_text(f"{first} t          status: spec   risk: high\n{rest}",
                                        encoding="utf-8")
        (folder / "plan.md").write_text(scope_fixtures.PLAN.format(files="src/app.py"),
                                        encoding="utf-8")
        rows.append(f"{ticket} | ready | high | r | t")
    (root / ".work").mkdir(exist_ok=True)
    (root / ".work" / "INDEX.md").write_text("".join(f"{row}\n" for row in rows), encoding="utf-8")
    return root


def _waiting(out):
    return [line for line in out.splitlines() if line.startswith("waiting ")]


def test_default_report_has_a_waiting_line(tmp_path):
    done = _run(_waiting_repo(tmp_path))

    assert _waiting(done.stdout) == ["waiting  2 on you (/crew:status --owner)"], done.stdout


def test_waiting_line_says_nothing_on_you(tmp_path):
    assert _waiting(_run(_waiting_repo(tmp_path, approvals=0)).stdout) == ["waiting  nothing on you"]


def test_waiting_line_names_unread_and_unknown_counts():
    got = {"state": "ok", "why": "", "items": [("T-1", "approve", "x")], "unread": ["T-2"],
           "unknown": [("T-3", "RuntimeError"), ("T-4", "OSError")]}

    assert crew_status.waiting_line(got) == (
        "waiting  1 on you (/crew:status --owner), 1 in review not read, 2 could not tell")


def test_waiting_line_is_unknown_when_autopilot_cannot_be_imported(tmp_path, monkeypatch):
    root = _waiting_repo(tmp_path)
    real = crew_status.importlib.import_module

    def broken(name, *args):
        if name == "crew_autopilot_owner":
            raise ImportError("broken install")
        return real(name, *args)

    monkeypatch.setattr(crew_status.importlib, "import_module", broken)
    lines = crew_status.collect(str(root))

    assert [l for l in lines if l.startswith("waiting ")] == [
        "waiting  unknown (crew_autopilot_owner could not be imported: ImportError)"]


def test_waiting_line_is_unknown_without_an_index(tmp_path):
    root = _waiting_repo(tmp_path, approvals=0)
    (root / ".work" / "INDEX.md").unlink()

    assert _waiting(_run(root).stdout) == ["waiting  unknown (no .work/INDEX.md)"]


def test_owner_view_lists_one_line_per_ticket_with_its_command(tmp_path):
    done = _run(_waiting_repo(tmp_path), "--owner")

    assert (done.returncode, done.stdout.splitlines()) == (0, [
        "waiting  2 on you (/crew:status --owner)",
        "T-1  approve  /crew:approve T-1", "T-2  approve  /crew:approve T-2"]), done.stdout


def test_owner_view_is_read_only(tmp_path):
    import review_ledger as ledger  # pylint: disable=import-outside-toplevel,reimported
    root = _waiting_repo(tmp_path, approvals=3)
    for ticket, rounds, receipt in (
            ("T-2", [{"round": 1, "status": "completed", "verdict": "FINDINGS",
                      "bundle_sha256": "a" * 64, "base": "HEAD"}], None),
            ("T-3", [{"round": 1, "status": "completed", "verdict": "CLEAN",
                      "bundle_sha256": "a" * 64, "base": "HEAD"}],
             {"kind": "clean", "round": 1, "bundle_sha256": "a" * 64, "base": "HEAD",
              "verdict": "CLEAN"})):
        path = ledger.ledger_path(str(root), ticket)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ticket": ticket, "budget": 2, "rounds": rounds,
                                     "refused": [], "state": "REVIEWED", "receipt": receipt}))
    (root / "src" / "app.py").write_text("x = 3\n", encoding="utf-8")  # uncommitted
    before = _stat_tree(root)

    done = _run(root, "--owner")

    assert (done.returncode, _stat_tree(root) == before) == (0, True), done.stdout


def test_owner_view_fits_forty_lines(tmp_path):
    lines = _run(_waiting_repo(tmp_path, approvals=60), "--owner").stdout.splitlines()

    assert (len(lines), lines[0], lines[-1]) == (
        crew_status.MAX_LINES, "waiting  60 on you (/crew:status --owner)", "... 22 more")


@pytest.mark.parametrize("other", ["--memory", "--approvals"])
def test_owner_and_memory_together_are_refused(tmp_path, other):
    done = _run(_waiting_repo(tmp_path), "--owner", other)

    assert (done.returncode, done.stdout) == (2, "")


def test_owner_view_never_cuts_a_command():
    """L-0551 review r1 FIX: an 80-character ticket id keeps its whole command."""
    long_id = "T-" + "9" * 78
    got = {"state": "ok", "why": "", "items": [(long_id, "approve", f"/crew:approve {long_id}")],
           "unread": [long_id], "unknown": []}
    original = crew_status._owner_read  # pylint: disable=protected-access
    try:
        crew_status._owner_read = lambda root: got  # pylint: disable=protected-access
        lines = crew_status.owner_lines(".")
    finally:
        crew_status._owner_read = original  # pylint: disable=protected-access

    assert (lines[1].endswith(f"/crew:approve {long_id}"),
            lines[2].endswith(f"/crew:autopilot status {long_id}")) == (True, True)


def test_waiting_line_counts_held_and_blocked():
    got = {"state": "ok", "why": "", "items": [("T-1", "approve", "x")], "unread": [],
           "held": ["T-2", "T-3"], "blocked": ["T-4"], "unknown": []}

    assert crew_status.waiting_line(got) == (
        "waiting  1 on you (/crew:status --owner), 2 held, 1 blocked")


def test_waiting_line_with_nothing_on_you_still_shows_held_and_blocked():
    got = {"state": "ok", "why": "", "items": [], "unread": [], "held": ["T-2"],
           "blocked": ["T-4"], "unknown": []}

    assert crew_status.waiting_line(got) == "waiting  nothing on you, 1 held, 1 blocked"


def test_owner_view_is_read_only_with_a_next_md(tmp_path):
    root = _waiting_repo(tmp_path, approvals=2)
    (root / ".work" / "INDEX.md").write_text("T-1 | hold | high | r | t\nT-2 | ready | high | r | t\n",
                                            encoding="utf-8")
    (root / ".work" / "tickets" / "T-1" / "next.md").write_text("reason: r\nrevisit: 2000-01-01\n",
                                                              encoding="utf-8")
    before = _stat_tree(root)

    done = _run(root, "--owner")

    assert (done.returncode, _stat_tree(root) == before, done.stdout.splitlines()[1].startswith(
        "T-1  revisit  revisit 2000-01-01 (due)")) == (0, True, True), done.stdout
