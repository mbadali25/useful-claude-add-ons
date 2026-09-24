"""Smoke tests for the fixture builder that every later crew test depends on.

These aren't testing crew's own scripts -- there's nothing under
hooks/scripts or skills/crew-graph/scripts yet for later tasks to add. They
exist so make_repo/head_sha/commit_with_date are proven to work before five
later tasks build on them, and so this harness lands with a green pytest run
instead of "no tests collected" (pytest exit code 5).
"""
import json
import os
import re
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

SHA_RE = re.compile(r"^[0-9a-f]{7}$")


def test_context_puts_script_dirs_on_sys_path():
    assert any(p.endswith("hooks\\scripts") or p.endswith("hooks/scripts")
               for p in sys.path)
    assert any(p.endswith("crew-graph\\scripts")
               or p.endswith("crew-graph/scripts") for p in sys.path)


def test_make_repo_default_is_a_real_git_repo(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert (root / ".crew").is_dir()
    assert (root / ".work").is_dir()
    assert (root / ".git").is_dir()
    assert SHA_RE.match(crew_fixtures.head_sha(root))


def test_make_repo_git_false_skips_commit(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, git=False)
    assert not (root / ".git").exists()


def test_make_repo_writes_config(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"provider": "jira"})
    assert '"provider"' in (root / ".crew" / "config.json").read_text(
        encoding="utf-8")


def test_make_repo_omits_config_file_when_none(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=None)
    assert not (root / ".crew" / "config.json").exists()


def test_make_repo_writes_metrics_rows(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, metrics=[("ABC-1", 2, 3), ("ABC-2", 0, 1)])
    text = (root / ".crew" / "metrics.md").read_text(encoding="utf-8")
    assert "ABC-1" in text and "2" in text and "3" in text
    assert "ABC-2" in text


def test_make_repo_writes_codemap_files(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, codemap={"auth": "# Auth\n", "billing": "# Billing\n"})
    mapdir = root / ".crew" / "codemap"
    assert (mapdir / "auth.md").read_text(encoding="utf-8") == "# Auth\n"
    assert (mapdir / "billing.md").read_text(encoding="utf-8") == "# Billing\n"


def test_make_repo_writes_work_ticket(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, work_ticket="ABC-9")
    assert "ABC-9" in (root / ".work" / "INDEX.md").read_text(
        encoding="utf-8")


def test_make_repo_writes_handoff(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, handoff=True)
    assert (root / ".work" / "HANDOFF.md").exists()


def test_make_repo_no_handoff_by_default(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert not (root / ".work" / "HANDOFF.md").exists()


def test_make_repo_graph_sha_head_matches_real_head(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha="head")
    graph = json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph["built_at_commit"] == crew_fixtures.head_sha(root, length=40)


def test_make_repo_graph_sha_literal_is_stamped_verbatim(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha="deadbee")
    graph = json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph["built_at_commit"] == "deadbee"


def test_make_repo_graph_sha_none_omits_built_at_commit(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, graph=True, graph_sha=None)
    graph = json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert "built_at_commit" not in graph


def test_make_repo_graph_without_git_omits_built_at_commit(tmp_path):
    # graph_sha defaults to "head", but with git=False there is no HEAD to
    # stamp -- the "head" branch requires git, so no field is written at
    # all. A test for a fresh, stamped graph must pass git=True (the
    # default) alongside graph=True.
    root = crew_fixtures.make_repo(tmp_path, graph=True, git=False)
    graph = json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert "built_at_commit" not in graph


def test_head_sha_length(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    assert len(crew_fixtures.head_sha(root, length=12)) == 12


def test_commit_with_date_backdates_author_and_committer(tmp_path):
    root = crew_fixtures.make_repo(tmp_path)
    (root / "later.txt").write_text("x\n", encoding="utf-8")
    crew_fixtures.commit_with_date(root, "later.txt", "2020-01-01T00:00:00")
    done = subprocess.run(
        ("git", "log", "-1", "--format=%ad", "--date=short"),
        cwd=root, check=True, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )
    assert done.stdout.strip() == "2020-01-01"


def test_git_calls_never_inherit_the_parent_stdin(tmp_path, monkeypatch):
    """Every subprocess.run the fixture builder makes must redirect stdin.

    Leaving stdin=None lets git inherit whatever OS handle pytest's fd
    capturing currently has fd 0 pointed at. That handle gets torn down and
    rebuilt on every test's setup/teardown, and on Windows -- and on a CI
    runner whose own stdin is a pipe -- an inherited-but-stale handle makes
    subprocess.Popen fail with "the handle is invalid" (Windows) or "Bad
    file descriptor" (Linux) on an unpredictable subset of tests. Pinning
    stdin=DEVNULL removes the dependency on that handle entirely, which is
    what makes ~180 sequential git calls across the suite deterministic.
    """
    calls = []
    real_run = subprocess.run

    def recording_run(*args, **kwargs):
        calls.append(kwargs)
        return real_run(*args, **kwargs)  # pylint: disable=subprocess-run-check

    monkeypatch.setattr(crew_fixtures.subprocess, "run", recording_run)

    root = crew_fixtures.make_repo(tmp_path)
    crew_fixtures.head_sha(root)
    (root / "later.txt").write_text("x\n", encoding="utf-8")
    crew_fixtures.commit_with_date(root, "later.txt", "2020-01-01T00:00:00")

    assert calls, "expected the fixture builder to have called subprocess.run"
    for kwargs in calls:
        assert kwargs.get("stdin") == subprocess.DEVNULL, (
            "a git subprocess.run call is missing stdin=subprocess.DEVNULL "
            f"-- kwargs were: {kwargs}"
        )


# --- per-flavour PATH shims (the Windows conversion, driven from Linux) -----


@pytest.mark.parametrize("native,posix", [
    ("C:\\Users\\me\\AppData\\Local\\Temp\\fakebin", "/c/Users/me/AppData/Local/Temp/fakebin"),
    ("D:/a/b/", "/d/a/b"),
    ("C:\\x\\y\\\\", "/c/x/y"),
    ("C:\\", "/c"),
    ("C:", "/c"),
    ("/usr/bin", "/usr/bin"),
    ("relative\\dir", "relative/dir"),
])
def test_windows_to_posix_matches_cygpath_shape(native, posix):
    assert crew_fixtures.windows_to_posix(native) == posix


def test_bash_on_windows_gets_a_colon_joined_posix_path():
    base = "C:\\Windows\\system32;C:\\Program Files\\Tools\\bin;"

    got = crew_fixtures.shell_path("sh", ["C:\\t\\fakebin"], base=base, windows=True,
                                   cygpath=False)

    assert got == "/c/t/fakebin:/c/Windows/system32:/c/Program Files/Tools/bin"


def test_pwsh_on_windows_keeps_a_semicolon_joined_native_path():
    got = crew_fixtures.shell_path("ps1", ["C:\\t\\fakebin"], base="C:\\Windows;C:\\x",
                                   windows=True)

    assert got == "C:\\t\\fakebin;C:\\Windows;C:\\x"


@pytest.mark.parametrize("flavor", ["sh", "ps1"])
def test_posix_path_is_colon_joined_and_untouched(flavor):
    got = crew_fixtures.shell_path(flavor, ["/tmp/fakebin"], base="/usr/bin:/bin", windows=False)

    assert got == "/tmp/fakebin:/usr/bin:/bin"


def test_a_cygpath_that_fails_falls_back_to_the_manual_conversion(tmp_path):
    missing = str(tmp_path / "no-such-cygpath")

    got = crew_fixtures.shell_path("sh", ["E:\\bin"], base="", windows=True, cygpath=missing)

    assert got == "/e/bin"


def test_a_windows_shim_gets_a_cmd_twin_the_native_which_can_find(tmp_path):
    crew_fixtures.write_shim(tmp_path, "xdotool", windows=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["xdotool", "xdotool.cmd"]
    assert (tmp_path / "xdotool").read_bytes().startswith(b"#!/bin/sh\n")
    assert (tmp_path / "xdotool.cmd").read_bytes() == b"@echo off\r\nexit /b 0\r\n"


@pytest.mark.skipif(os.name == "nt", reason="the POSIX branch: chmod is what makes it runnable")
def test_a_posix_shim_is_executable_and_has_no_cmd_twin(tmp_path):
    path = crew_fixtures.write_shim(tmp_path, "tmux", "#!/bin/sh\necho 7\n", windows=False)

    assert os.access(path, os.X_OK)
    assert [p.name for p in tmp_path.iterdir()] == ["tmux"]
    assert subprocess.run([path], capture_output=True, text=True, check=False).stdout == "7\n"


# --- gate_processes: hygiene, not a check --------------------------------

def _pid_alive(pid):
    if os.name == "nt":
        done = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
            text=True, check=False, timeout=30)
        return str(pid) in done.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_gate_processes_kills_a_still_running_child_at_teardown():
    """Drives `gate_processes` as a plain generator (`__wrapped__` is the
    undecorated function every `@pytest.fixture` carries) rather than
    through pytest's own fixture machinery -- the finalizer under test IS
    the code after `yield`, and a generator's `next()` past that point runs
    it, with no need to spin up a second pytest session just to observe a
    teardown.

    A REAL child (through `popen_gate`, killable as a whole group the same
    way a real gate spawn is), sleeping far longer than this test, proves
    the finalizer actually reaches it rather than merely not raising."""
    gen = crew_fixtures.gate_processes.__wrapped__()
    track = next(gen)
    proc = crew_fixtures.popen_gate(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    track(proc)
    assert _pid_alive(proc.pid), "sanity: the child never actually started"

    assert next(gen, "exhausted") == "exhausted", (
        "gate_processes's body must contain exactly one yield")

    deadline = time.time() + 10
    while _pid_alive(proc.pid) and time.time() < deadline:
        time.sleep(0.1)
    assert not _pid_alive(proc.pid), (
        "gate_processes's finalizer did not kill the tracked child")
