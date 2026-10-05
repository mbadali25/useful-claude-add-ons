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


# --- T-0065 item 3: the agents line --------------------------------------------


def _agents_home(tmp_path, monkeypatch, registry='{"version": 2, "plugins": {}}'):
    """A fake `~/.claude` with no agents of its own, so nothing real is read."""
    config = tmp_path / "home" / ".claude"
    (config / "plugins").mkdir(parents=True)
    (config / "plugins" / "installed_plugins.json").write_text(registry, encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))


def _verify_names(root, *agents):
    rules = [{"paths": ["**/*.php"], "run": ["true"], "agents": list(agents)}]
    (root / ".crew" / "verify.json").write_text(json.dumps({"rules": rules}), encoding="utf-8")


def test_status_flags_uncovered_verify_agent(tmp_path, monkeypatch):
    _agents_home(tmp_path, monkeypatch)
    root = make_repo(tmp_path)
    _verify_names(root, "php-developer")

    lines = crew_status.collect(str(root))

    agents = [line for line in lines if line.startswith("agents   ")]
    assert agents == ["agents   MISSING php-developer (verify.json rule: **/*.php)"]


@pytest.mark.parametrize("case", ["ok", "unknown"])
def test_status_agents_ok_and_unknown(tmp_path, monkeypatch, case):
    _agents_home(tmp_path, monkeypatch, registry='{"version": 2, "plugins": {}}' if case == "ok" else "{not json")
    root = make_repo(tmp_path)
    _verify_names(root, "security" if case == "ok" else "voltagent:security-auditor")

    agents = [line for line in crew_status.collect(str(root)) if line.startswith("agents   ")]

    if case == "ok":
        assert agents == ["agents   ok (1 named)"]
    else:
        assert len(agents) == 1 and agents[0].startswith("agents   unknown - ")
        assert "installed_plugins.json" in agents[0]


def test_status_shows_at_most_three_missing_agents(tmp_path, monkeypatch):
    _agents_home(tmp_path, monkeypatch)
    root = make_repo(tmp_path)
    _verify_names(root, "a1", "a2", "a3", "a4", "a5")

    agents = [line for line in crew_status.collect(str(root)) if line.startswith("agents   ")]

    assert len(agents) == 1
    assert agents[0].startswith("agents   MISSING a1, a2, a3 (+2 more)")
