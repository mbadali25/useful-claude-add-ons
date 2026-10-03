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


# --- L-0602: the verify line is /crew:done check 2's evidence -------------------
#
# Clean ONLY after a fully clean `verify-gate.sh --all` at HEAD on a committed
# tree, with nothing outstanding; every other state is a named refusal. The
# allow cases and most block cases drive the real gate.

import crew_fixtures  # noqa: E402  pylint: disable=wrong-import-position
import review_gate  # noqa: E402  pylint: disable=wrong-import-position
import verify_record  # noqa: E402  pylint: disable=wrong-import-position
from review_fixtures import git, init_repo  # noqa: E402  pylint: disable=wrong-import-position

CLEAN = crew_status.VERIFY_CLEAN
_GATE_SH = os.path.join(os.path.dirname(crew_status.__file__), "verify-gate.sh")
_GATE_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_GATE_BASH is None, reason="runs the real verify-gate.sh")
_RECORD = os.path.join(".crew", ".verify-gate.record.json")
_MARKER = os.path.join(".crew", ".verify-verified-at")


def _gate_map(run="test ! -e ../flag"):
    return {"version": 1,
            "rules": [{"paths": ["**"], "run": [run], "reach": "local", "seconds": 1}],
            "default": [], "unmapped": "ignore"}


def _gate_repo(tmp_path, verify_map=None):
    root = init_repo(tmp_path / "r")
    (root / ".gitignore").write_text(".crew/*\n!.crew/verify.json\n", encoding="utf-8")
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(json.dumps(verify_map or _gate_map()),
                                                encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "map")
    return root


def _run_gate(root, *args):
    return crew_fixtures.run_gate(
        [_GATE_BASH, _GATE_SH, *args], input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _clean_repo(tmp_path):
    root = _gate_repo(tmp_path)
    done = _run_gate(root, "--all")
    assert done.returncode == 0, done.stderr
    return root


def _line(root):
    return crew_status._verify_line(str(root))  # pylint: disable=protected-access


def _write_record(root, data):
    (root / _RECORD).write_text(json.dumps(data), encoding="utf-8")


def _refused(line, word):
    return (line.startswith(CLEAN), word in line)


@needs_bash
def test_verify_line_is_clean_after_a_clean_all_on_a_committed_tree(tmp_path):
    root = _clean_repo(tmp_path)

    line = _line(root)

    assert line.startswith(CLEAN) and git(root, "rev-parse", "HEAD")[:12] in line, line


@needs_bash
def test_verify_line_is_clean_after_a_clean_all_and_a_quiet_stop_after_it(tmp_path):
    root = _clean_repo(tmp_path)
    assert _run_gate(root).returncode == 0

    assert _line(root).startswith(CLEAN)


@needs_bash
def test_verify_line_refuses_a_stop_only_pass(tmp_path):
    root = _gate_repo(tmp_path)
    (root / "seed.txt").write_text("edited\n", encoding="utf-8")
    assert _run_gate(root).returncode == 0
    git(root, "commit", "-qam", "edit")
    assert _run_gate(root).returncode == 0

    assert _refused(_line(root), "no clean --all at HEAD") == (False, True)


@needs_bash
def test_verify_line_refuses_after_a_failed_all_at_the_same_head(tmp_path):
    root = _clean_repo(tmp_path)
    (tmp_path / "flag").write_text("", encoding="utf-8")
    assert _run_gate(root, "--all").returncode == 2

    assert _refused(_line(root), "no clean --all at HEAD") == (False, True)


@needs_bash
def test_verify_line_refuses_a_clean_all_at_an_older_head(tmp_path):
    root = _clean_repo(tmp_path)
    (root / "new.txt").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "later")

    assert _refused(_line(root), "no clean --all at HEAD") == (False, True)


@needs_bash
def test_verify_line_refuses_a_dirty_tree_even_when_the_fingerprint_matches(tmp_path):
    root = _clean_repo(tmp_path)
    (root / "seed.txt").write_text("dirty\n", encoding="utf-8")
    assert _run_gate(root).returncode == 0
    assert review_gate.gate_state(str(root))[0] == review_gate.VERIFIED

    assert _refused(_line(root), "differ from HEAD") == (False, True)


@needs_bash
def test_verify_line_refuses_a_staged_deletion_masked_by_a_directory(tmp_path):
    root = _clean_repo(tmp_path)
    git(root, "rm", "-q", "seed.txt")
    assert _run_gate(root).returncode == 0
    (root / "seed.txt").mkdir()

    assert _refused(_line(root), "differ from HEAD") == (False, True)


@needs_bash
def test_verify_line_refuses_an_untracked_file(tmp_path):
    root = _clean_repo(tmp_path)
    (root / "new.txt").write_text("x\n", encoding="utf-8")

    assert _refused(_line(root), "NOT VERIFIED") == (False, True)


@needs_bash
def test_verify_line_refuses_a_clean_record_when_the_marker_is_missing(tmp_path):
    root = _clean_repo(tmp_path)
    (root / _MARKER).unlink()
    assert verify_record.read_record_meta(str(root)) == ("ok", {}, git(root, "rev-parse", "HEAD"))

    assert _refused(_line(root), "NOT VERIFIED") == (False, True)


@needs_bash
def test_verify_line_refuses_an_unreadable_marker_as_unknown(tmp_path):
    root = _clean_repo(tmp_path)
    (root / _MARKER).unlink()
    (root / _MARKER).mkdir()

    assert _refused(_line(root), "verify   UNKNOWN") == (False, True)


@needs_bash
@pytest.mark.parametrize("record", [{"rules": {}}, {"rules": {}, "all_clean_at": None},
                                    {"rules": {}, "all_clean_at": "d" * 40}],
                         ids=["missing", "null", "other"])
def test_verify_line_refuses_without_a_clean_all_at_head(tmp_path, record):
    root = _clean_repo(tmp_path)
    _write_record(root, record)

    assert _refused(_line(root), "no clean --all at HEAD") == (False, True)


@needs_bash
@pytest.mark.parametrize("entry, expected", [
    ({"status": "skipped"}, "verify   1 skipped"),
    ({"status": "chronic"}, "verify   1 chronic"),
    ({"status": "reach_undeclared"}, "verify   1 reach_undeclared"),
    ({"status": "chronic", "orphaned": True}, "verify   1 chronic"),
], ids=["skipped", "chronic", "reach", "orphaned"])
def test_verify_line_refuses_an_outstanding_rule_even_after_a_clean_all(tmp_path, entry,
                                                                        expected):
    root = _clean_repo(tmp_path)
    head = git(root, "rev-parse", "HEAD")
    _write_record(root, {"rules": {"k": dict(entry, label="rules[0]", reason="x", sha=head)},
                         "all_clean_at": head})
    assert review_gate.gate_state(str(root))[0] == review_gate.VERIFIED

    assert _line(root) == expected


@needs_bash
@pytest.mark.parametrize("case, expected", [
    ("corrupt", "verify   UNKNOWN (gate record unreadable)"),
    ("absent", "verify   no gate record yet"),
])
def test_verify_line_refuses_a_bad_record(tmp_path, case, expected):
    root = _clean_repo(tmp_path)
    if case == "corrupt":
        (root / _RECORD).write_text("{not json", encoding="utf-8")
    else:
        (root / _RECORD).unlink()

    assert _line(root) == expected


def test_verify_line_refuses_when_git_cannot_be_read(tmp_path):
    root = tmp_path / "not-a-repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "verify.json").write_text(json.dumps(_gate_map()), encoding="utf-8")
    (root / _MARKER).write_text("0" * 40 + "\n", encoding="utf-8")
    _write_record(root, {"rules": {}, "all_clean_at": "0" * 40})

    assert _refused(_line(root), "verify   UNKNOWN") == (False, True)


@pytest.mark.parametrize("case", ["no-map", "stood-down"])
def test_verify_line_refuses_with_no_gate(tmp_path, case):
    root = init_repo(tmp_path / "r")
    (root / ".crew").mkdir()
    if case == "stood-down":
        (root / ".crew" / "verify.json").write_text(json.dumps(_gate_map()), encoding="utf-8")
        (root / ".crew" / "config.json").write_text('{"verifyGate": false}', encoding="utf-8")
    head = git(root, "rev-parse", "HEAD")
    _write_record(root, {"rules": {}, "all_clean_at": head})

    assert _refused(_line(root), "verify   no gate") == (False, True)


@needs_bash
def test_verify_line_refuses_while_the_gate_lock_is_held(tmp_path):
    root = _clean_repo(tmp_path)
    (root / ".crew" / ".verify-gate.lock").mkdir()

    assert _refused(_line(root), "gate running") == (False, True)


def _wrap_gate_state(monkeypatch, on_call):
    real = review_gate.gate_state
    calls = []

    def wrapper(root):
        calls.append(root)
        on_call(len(calls))
        return real(root)

    monkeypatch.setattr(review_gate, "gate_state", wrapper)


@needs_bash
def test_verify_line_rereads_the_record_after_the_gate_state(tmp_path, monkeypatch):
    root = _clean_repo(tmp_path)
    head = git(root, "rev-parse", "HEAD")

    def add_entry(n):
        if n == 1:
            _write_record(root, {"rules": {"k": {"status": "skipped", "label": "r",
                                                 "reason": "x", "sha": head}},
                                 "all_clean_at": head})

    _wrap_gate_state(monkeypatch, add_entry)

    assert _refused(_line(root), "moved while it was read") == (False, True)


@needs_bash
def test_verify_line_refuses_when_head_moves_during_the_read(tmp_path, monkeypatch):
    root = _clean_repo(tmp_path)

    def commit(n):
        if n == 1:
            git(root, "commit", "-q", "--allow-empty", "-m", "moved")

    _wrap_gate_state(monkeypatch, commit)

    assert _line(root).startswith(CLEAN) is False


@needs_bash
def test_verify_line_refuses_a_tree_edited_during_the_read(tmp_path, monkeypatch):
    root = _clean_repo(tmp_path)

    def edit(n):
        if n == 2:
            (root / "seed.txt").write_text("edited mid-read\n", encoding="utf-8")

    _wrap_gate_state(monkeypatch, edit)

    assert _line(root).startswith(CLEAN) is False


@needs_bash
@pytest.mark.parametrize("case", ["marker", "tree"])
def test_verify_line_refuses_a_change_at_the_tail_of_the_read(tmp_path, monkeypatch, case):
    root = _clean_repo(tmp_path)
    real = crew_status._git  # pylint: disable=protected-access
    calls = []

    def tail(r, *args):
        if args == ("rev-parse", "HEAD"):
            calls.append(args)
            if len(calls) == 2:
                if case == "marker":
                    (root / _MARKER).unlink()
                else:
                    (root / "seed.txt").write_text("edited at the tail\n", encoding="utf-8")
        return real(r, *args)

    monkeypatch.setattr(crew_status, "_git", tail)

    assert _line(root).startswith(CLEAN) is False


@needs_bash
def test_status_is_read_only_when_the_gate_state_is_computed(tmp_path):
    root = _clean_repo(tmp_path)
    sentinel = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{sentinel}'\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    git(root, "config", "core.fsmonitor", str(hook))
    before = _stat_tree(root)

    done = _run(root)

    assert (done.returncode, sentinel.exists(), _stat_tree(root) == before,
            any(line.startswith(CLEAN) for line in done.stdout.splitlines())) == (
                0, False, True, True), done.stdout + done.stderr
