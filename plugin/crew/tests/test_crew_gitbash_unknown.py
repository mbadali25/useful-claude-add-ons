"""A Git Bash that exists but is slow is `could not tell`, never `not found`.

The strict resolver (crew_shell.resolve_gitbash(strict=True), the hook dispatcher's) used to run
`bash.exe -c 'exit 0'` once under a 5 s bound and treat a timeout like a missing file, so a loaded
host made every Bash, PowerShell and Edit call fail with "none was found ... Install Git for
Windows" while the file was there. Must-allow: present but slow. Must-block: truly absent, broken,
or never answering. The mutation groups that pin this are named in .crew/verify.json.
"""

import json
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_shell

DEFAULT = "C:/Program Files/Git/bin/bash.exe"


def _never(_name):
    raise AssertionError("strict mode must not read PATH")


def _nosleep(_seconds):
    pass


def _slow_then_fast(slow_runs):
    """git --exec-path fails; the first `slow_runs` self-tests time out, then bash answers."""
    seen = []

    def runner(argv, timeout):
        if argv[-1] == "--exec-path":
            return 1, b"", b""
        seen.append(timeout)
        if len(seen) <= slow_runs:
            raise subprocess.TimeoutExpired(argv, timeout)
        return 0, b"", b""
    return runner, seen


def _resolve(runner, exists=lambda _p: True, lkg=None, sleep=_nosleep):
    return crew_shell.resolve_gitbash(runner=runner, exists=exists, which=_never, strict=True,
                                      sleep=sleep, lkg=lkg)


# --- must-allow: present but slow -----------------------------------------------------

def test_a_present_but_slow_git_bash_is_allowed_once_a_retry_answers():
    runner, seen = _slow_then_fast(2)
    pauses = []

    path, reason = _resolve(runner, sleep=pauses.append)

    assert path == DEFAULT, reason
    assert len(seen) == 3 and len(pauses) == 2 and all(0 < pause < 1 for pause in pauses)


def _lkg(tmp_path, mtime=1000):
    stats = {"mtime": mtime, "size": 5}
    store = crew_shell.LastKnownGood(
        str(tmp_path / "gitbash-lkg.json"),
        stat=lambda _p: type("Stat", (), {"st_mtime": stats["mtime"], "st_size": stats["size"]})())
    return store, stats


def test_a_clean_self_test_is_remembered_and_trusted_when_the_next_one_times_out(tmp_path):
    store, _ = _lkg(tmp_path)
    assert _resolve(_slow_then_fast(0)[0], lkg=store)[0] == DEFAULT
    runner, seen = _slow_then_fast(99)

    path, reason = _resolve(runner, lkg=store)

    assert path == DEFAULT and "last known good" in reason
    assert len(seen) == 1, "the last known good answers right after the first unanswered self-test"


@pytest.mark.parametrize("stderr", [b"bash: fork: retry: Resource temporarily unavailable\n",
                                    b"1 [main] bash 7 dofork: child -1 - died\nCannot allocate memory\n"])
def test_a_bash_that_dies_on_a_resource_failure_is_unknown_not_broken(stderr):
    def runner(argv, timeout):
        return (1, b"", b"") if argv[-1] == "--exec-path" else (128, b"", stderr)

    path, reason = _resolve(runner)

    assert path is None and reason.kind == "unknown", reason


# --- must-block: never believed unrun --------------------------------------------------

def test_a_present_git_bash_that_never_answers_blocks_as_unknown_with_bounded_attempts():
    runner, seen = _slow_then_fast(99)

    path, reason = _resolve(runner)

    assert path is None and reason.kind == "unknown"
    assert len(seen) == len(crew_shell.STRICT_ATTEMPTS)
    assert sum(timeout + pause for timeout, pause in crew_shell.STRICT_ATTEMPTS) < 20
    assert "overloaded" in reason and "Install" not in reason


def test_a_genuinely_absent_git_bash_is_absent_and_runs_nothing():
    runs = []

    def runner(argv, timeout):
        runs.append(argv)
        return 1, b"", b""

    path, reason = _resolve(runner, exists=lambda _p: False)

    assert (path, reason.kind) == (None, "absent") and reason.startswith("Git Bash not found")
    assert all(argv[-1] == "--exec-path" for argv in runs)


def test_a_bash_that_exits_non_zero_cleanly_is_broken_and_is_not_retried():
    seen = []

    def runner(argv, timeout):
        if argv[-1] == "--exec-path":
            return 1, b"", b""
        seen.append(argv)
        return 127, b"", b"bash: exit: command not found\n"

    path, reason = _resolve(runner)

    assert path is None and reason.kind == "broken" and len(seen) == 1, reason


def test_git_exec_path_timing_out_with_no_candidate_file_is_unknown_not_absent():
    def runner(argv, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    path, reason = _resolve(runner, exists=lambda _p: False)

    assert path is None and reason.kind == "unknown" and "another install location" in reason


def test_a_changed_bash_exe_is_not_trusted_from_the_last_known_good(tmp_path):
    store, stats = _lkg(tmp_path)
    _resolve(_slow_then_fast(0)[0], lkg=store)
    stats["mtime"] += 60

    path, reason = _resolve(_slow_then_fast(99)[0], lkg=store)

    assert path is None and reason.kind == "unknown"


def test_the_last_known_good_never_makes_a_missing_file_pass(tmp_path):
    store, _ = _lkg(tmp_path)
    ok = _slow_then_fast(0)[0]
    _resolve(ok, lkg=store)

    path, reason = _resolve(ok, exists=lambda _p: False, lkg=store)

    assert path is None and reason.kind == "absent"


def test_an_unreadable_record_is_ignored_and_a_new_one_is_written_atomically_with_lf(tmp_path):
    store, _ = _lkg(tmp_path)
    (tmp_path / "gitbash-lkg.json").write_text("{not json", encoding="utf-8")
    assert store.recorded() is None and not store.trusts(DEFAULT)

    store.remember(DEFAULT)

    raw = (tmp_path / "gitbash-lkg.json").read_bytes()
    assert b"\r" not in raw and json.loads(raw)["path"] == DEFAULT
    assert [item.name for item in tmp_path.iterdir()] == ["gitbash-lkg.json"]
