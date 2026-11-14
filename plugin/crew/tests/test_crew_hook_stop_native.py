"""The Stop completion audit runs natively on Windows (crew 1.3.96).

`completion-audit.sh` is a wrapper for `completion_audit.py`: python resolution, a printf|tr|grep pipeline, the
blocked-once marker (printf|tr|sed, cksum|cut, rm) and then python. On Git Bash that is 15-20 forks, 40-50 s on a
loaded Windows host for a verdict python reaches in 0.2-0.6 s, and the row's 60 s limit then reads as UNKNOWN.
`crew_hook.DIRECT` now gives the row its own python route, as it already gave the PreToolUse guards.

What these tests hold:

  * the route: a Windows Stop dispatch runs `completion_audit.py` and starts no `completion-audit.sh`;
  * UNKNOWN stays UNKNOWN: a timeout is exit 2 labelled `UNKNOWN (guard timeout` in an armed repo, a crash or a
    failed launch is handed to the wrapper (never believed as a pass), and no fault is ever exit 0 when armed;
  * the wrapper's marker bookkeeping is reproduced: the same file name (a real `cksum` and the wrapper itself are
    the oracle), cleared on `stop_hook_active` and on a verdict, left alone on a timeout;
  * must-block and must-allow verdicts through the native route, and the same verdict from the wrapper;
  * speed: the native row is far below the wrapper's wall time on a trivially small input, and a hung child
    still settles as UNKNOWN well inside the limit.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_hook
import crew_hook_harness as h
import record_golden_hooks as rgh

SCRIPTS = h.SCRIPTS
FAKE_BASH = "C:/fake/bash.exe"
AUDIT = "completion-audit.sh"


def _stop(root, session="s-1", active=False):
    return json.dumps({"hook_event_name": "Stop", "session_id": session, "cwd": str(root),
                       "stop_hook_active": active}).encode()


def _result(code=0, out=b"", err=b"", timed_out=False, error=""):
    return {"exit": None if timed_out or error else code, "stdout": out, "stderr": err, "timed_out": timed_out,
            "error": error, "pid": 1}


class Spy:
    """crew_hook.run_child replaced: records every start, answers through `decide(argv)`."""

    def __init__(self, monkeypatch, decide=None):
        self.calls = []
        self.decide = decide or (lambda argv: _result())
        monkeypatch.setattr(crew_hook, "run_child", self)

    def __call__(self, argv, raw, timeout, env, cwd=None):
        self.calls.append({"argv": list(argv), "raw": raw, "env": env, "cwd": cwd})
        return self.decide(list(argv))

    def wrappers(self):
        return [c for c in self.calls if str(c["argv"][1]).endswith(".sh")]

    def direct(self):
        return [c for c in self.calls if not str(c["argv"][1]).endswith(".sh")]


@pytest.fixture(name="audit_only")
def _audit_only(monkeypatch):
    """The Stop table cut to the audit row, so a dispatch measures and judges that row alone."""
    row = crew_hook._row("Stop", "", AUDIT, 60, guard=True)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_hook, "TABLE", (row,))
    return row


def _dispatch(project, payload, tmp, armed=True, windows=True, direct=None, scripts=SCRIPTS, env_extra=None,
              deadline_s=30, bash=FAKE_BASH, real_env=False):
    """`crew_hook.dispatch` for the Stop event. A stubbed run (a Spy) needs no real environment; a real child
    gets the constructed one the golden suites use (`real_env`)."""
    if real_env:
        env = rgh.env_for(str(project), str(tmp))
        env["TMPDIR"] = str(tmp)
    else:
        env = {"CLAUDE_PROJECT_DIR": str(project), "TMPDIR": str(tmp)}
    env.update(env_extra or {})
    code, out, err = crew_hook.dispatch("Stop", "claude", payload, crew_hook.now_ms() + deadline_s * 1000, env,
                                        str(project), windows=windows, resolve_bash=lambda strict=True: (bash, ""),
                                        resolve_pwsh=lambda: (None, ""), scripts=scripts,
                                        armed_fn=lambda _root: armed, direct=direct)
    return code, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _marker(project, tmp, payload):
    return crew_hook._audit_marker(payload, {"CLAUDE_PROJECT_DIR": str(project), "TMPDIR": str(tmp)})  # pylint: disable=protected-access


# --- the route ----------------------------------------------------------------------------------

def test_a_windows_stop_runs_the_audit_in_python_and_starts_no_wrapper(audit_only, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = _stop(tmp_path)

    code, _, _ = _dispatch(tmp_path, payload, tmp_path)

    assert code == 0 and spy.wrappers() == []
    assert [os.path.basename(c["argv"][1]) for c in spy.direct()] == ["completion_audit.py"]
    call = spy.direct()[0]
    assert call["argv"][0] == sys.executable and call["raw"] == payload
    assert call["env"]["PYTHONUTF8"] == "1" and call["env"]["PYTHONIOENCODING"] == "utf-8"
    assert audit_only.timeout == 60  # the row's limit is not what changed


def test_off_windows_the_audit_still_runs_through_its_wrapper(audit_only, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    _dispatch(tmp_path, _stop(tmp_path), tmp_path, windows=False)

    assert [os.path.basename(c["argv"][1]) for c in spy.wrappers()] == [AUDIT] and spy.direct() == []


def test_the_audit_direct_route_takes_exactly_the_exits_its_wrapper_passes_through():
    spec = crew_hook.DIRECT[AUDIT]
    assert spec.module == "completion_audit.py" and spec.accept == (0, 2) and spec.args == ()
    assert spec.env["PYTHONUTF8"] == "1" and spec.env["PYTHONIOENCODING"] == "utf-8"
    text = h.read_text(os.path.join(SCRIPTS, AUDIT))
    assert 'status" -ne 0 ] && [ "$status" -ne 2 ]' in text  # the wrapper's own pass-through set


# --- UNKNOWN stays UNKNOWN ----------------------------------------------------------------------

@pytest.mark.parametrize("code", [1, 3, 127, 137])
def test_a_python_exit_the_wrapper_would_not_pass_through_is_judged_by_the_wrapper(
        code, audit_only, monkeypatch, tmp_path):
    def decide(argv):
        if argv[0] == FAKE_BASH:
            return _result(2, err=b"COMPLETION AUDIT: wrapper verdict\n")
        return _result(code, err=b"STALE-DIRECT-OUTPUT\n")

    spy = Spy(monkeypatch, decide)

    got, _, err = _dispatch(tmp_path, _stop(tmp_path), tmp_path)

    assert got == 2 and "wrapper verdict" in err and "STALE-DIRECT-OUTPUT" not in err
    assert [os.path.basename(c["argv"][1]) for c in spy.wrappers()] == [AUDIT]


def test_a_python_that_failed_to_launch_is_judged_by_the_wrapper(audit_only, monkeypatch, tmp_path):
    def decide(argv):
        if argv[0] == FAKE_BASH:
            return _result(2, err=b"COMPLETION AUDIT: wrapper verdict\n")
        return _result(error="could not start python: [WinError 5]")

    spy = Spy(monkeypatch, decide)

    got, _, err = _dispatch(tmp_path, _stop(tmp_path), tmp_path)

    assert got == 2 and "wrapper verdict" in err and len(spy.wrappers()) == 1


def test_a_python_that_cannot_be_judged_by_the_wrapper_either_is_unknown_not_a_pass(
        audit_only, monkeypatch, tmp_path):
    """The wrapper ran and also exited without a decision: that is a fault, never an allow."""
    spy = Spy(monkeypatch, lambda argv: _result(1))

    got, _, err = _dispatch(tmp_path, _stop(tmp_path), tmp_path)

    assert got == 2 and "exited 1 without a decision" in err and "failing closed" in err
    assert len(spy.wrappers()) == 1


def test_exit_2_from_the_audit_is_a_decision_and_the_wrapper_is_not_run(audit_only, monkeypatch, tmp_path):
    spy = Spy(monkeypatch, lambda argv: _result(2, err=b"COMPLETION AUDIT: not approved\n"))

    got, _, err = _dispatch(tmp_path, _stop(tmp_path), tmp_path)

    assert got == 2 and "not approved" in err and spy.wrappers() == []


def test_an_audit_that_times_out_is_unknown_when_armed_and_is_not_rerun(audit_only, monkeypatch, tmp_path):
    spy = Spy(monkeypatch, lambda argv: _result(timed_out=True))

    got, _, err = _dispatch(tmp_path, _stop(tmp_path), tmp_path)

    assert got == 2 and "UNKNOWN (guard timeout" in err and "completion-audit.sh timed out" in err
    assert "failing closed (armed repo)" in err
    assert spy.wrappers() == [] and len(spy.direct()) == 1  # not retried, not handed to the wrapper


def test_an_unarmed_repo_is_told_but_not_blocked_on_a_timeout(audit_only, monkeypatch, tmp_path):
    Spy(monkeypatch, lambda argv: _result(timed_out=True))

    got, _, err = _dispatch(tmp_path, _stop(tmp_path), tmp_path, armed=False)

    assert got == 0 and "UNKNOWN (guard timeout" in err and "not a block" in err


# --- the wrapper's marker bookkeeping, reproduced ---------------------------------------------------

CKSUM_SAMPLES = ((b"", 4294967295), (b"a", 1220704766), (rb"C:\repos\x y", 1222081875),
                 (b"/tmp/\xc3\xa9" * 40, 1962763380), (b"abc" * 300, None))


@pytest.mark.parametrize("data,expected", CKSUM_SAMPLES)
def test_the_python_cksum_is_posix_cksum(data, expected):
    got = crew_hook._posix_cksum(data)  # pylint: disable=protected-access
    if expected is not None:
        assert got == expected  # recorded from the system `cksum`
    cksum = shutil.which("cksum")
    if cksum:
        said = subprocess.run([cksum], input=data, capture_output=True, check=True, timeout=60).stdout.split()[0]
        assert got == int(said)


def test_the_marker_is_named_by_the_last_session_id_and_the_project(tmp_path):
    env = {"CLAUDE_PROJECT_DIR": "/proj/a", "TMPDIR": str(tmp_path)}
    one = json.dumps({"session_id": "first", "x": {"session_id": "s.2_ok-3"}}).encode()
    name = os.path.basename(crew_hook._audit_marker(one, env))  # pylint: disable=protected-access
    assert name == f"crew-completion-audit.s.2_ok-3-{crew_hook._posix_cksum(b'/proj/a')}"  # pylint: disable=protected-access
    bare = os.path.basename(crew_hook._audit_marker(b"{}", env))  # pylint: disable=protected-access
    assert bare.startswith("crew-completion-audit.nosession-")
    spaced = b'{"session_id"\r\n :\n "line\\nbreak"}'  # not a legal id: the wrapper's sed does not match it
    assert os.path.basename(crew_hook._audit_marker(spaced, env)).startswith("crew-completion-audit.nosession-")  # pylint: disable=protected-access


@pytest.mark.skipif(h.BASH is None, reason="no bash: the wrapper's marker name was NOT compared")
@crew_fixtures.SLOW
def test_the_marker_name_is_the_one_the_wrapper_writes(tmp_path):
    """The wrapper itself is the oracle: with no python on PATH and a config present it blocks once and leaves
    its marker, and the python route must name the same file."""
    project = tmp_path / "proj"
    (project / ".crew").mkdir(parents=True)
    (project / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    payload = _stop(project, session="sess-9")
    bin_dir = os.path.dirname(h.BASH)
    env = {"PATH": os.pathsep.join([bin_dir, os.path.join(os.path.dirname(bin_dir), "usr", "bin")]),
           "CLAUDE_PROJECT_DIR": str(project), "TMPDIR": str(tmp), "HOME": str(tmp_path)}
    done = subprocess.run([h.BASH, os.path.join(SCRIPTS, AUDIT).replace("\\", "/")], input=payload, env=env,
                          capture_output=True, cwd=str(project), timeout=300, check=False)

    written = sorted(os.listdir(str(tmp)))
    assert done.returncode == 2, done.stderr
    assert written == [os.path.basename(_marker(project, tmp, payload))], written


def test_a_stop_hook_active_stop_runs_nothing_and_ends_the_blocked_once_count(audit_only, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = _stop(tmp_path, active=True)
    marker = _marker(tmp_path, tmp_path, payload)
    open(marker, "w", encoding="utf-8").close()

    code, _, _ = _dispatch(tmp_path, payload, tmp_path)

    assert code == 0 and spy.calls == []
    assert not os.path.exists(marker)


def test_stop_hook_active_is_found_across_json_whitespace_and_line_breaks(audit_only, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = b'{"session_id": "s-1",\r\n "stop_hook_active"\r\n  :\t\n true}'

    # the wrapper's `tr -d` of CR and LF joins a name or a value that a line break splits, too
    split = b'{"session_id": "s-1", "stop_hook_ac\ntive": tr\r\nue}'

    _dispatch(tmp_path, payload, tmp_path)
    _dispatch(tmp_path, split, tmp_path)

    assert spy.calls == []


def test_a_verdict_ends_the_blocked_once_count(audit_only, monkeypatch, tmp_path):
    payload = _stop(tmp_path)
    marker = _marker(tmp_path, tmp_path, payload)
    for code in (0, 2):
        open(marker, "w", encoding="utf-8").close()
        Spy(monkeypatch, lambda argv, c=code: _result(c))

        _dispatch(tmp_path, payload, tmp_path)

        assert not os.path.exists(marker), f"exit {code} reached a verdict and must clear the marker"


def test_a_timeout_leaves_the_marker_as_the_wrapper_does(audit_only, monkeypatch, tmp_path):
    payload = _stop(tmp_path)
    marker = _marker(tmp_path, tmp_path, payload)
    open(marker, "w", encoding="utf-8").close()
    Spy(monkeypatch, lambda argv: _result(timed_out=True))

    _dispatch(tmp_path, payload, tmp_path)

    assert os.path.exists(marker)


def test_a_marker_that_cannot_be_removed_changes_nothing(audit_only, monkeypatch, tmp_path):
    payload = _stop(tmp_path)
    marker = _marker(tmp_path, tmp_path, payload)
    os.mkdir(marker)  # `rm -f` of a directory fails too; the verdict stands
    Spy(monkeypatch, lambda argv: _result(2, err=b"COMPLETION AUDIT: x\n"))

    got, _, err = _dispatch(tmp_path, payload, tmp_path)

    assert got == 2 and "COMPLETION AUDIT: x" in err


# --- the verdicts through the native route (must-block, must-allow) ----------------------------------

pytestmark_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git: the native verdict cases were NOT run")


def _repo(tmp_path):
    return rgh.build_repo(str(tmp_path), True)


def _write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as handle:
        handle.write(text)


def _run(root, tmp_path, direct, payload=None):
    return _dispatch(root, payload or _stop(root), tmp_path / "t", direct=direct, windows=True,
                     scripts=SCRIPTS, deadline_s=880, bash=h.BASH or FAKE_BASH, real_env=True)


def _out_of_scope(root):
    _write(root, "docs-out.md", "outside the ticket's Touch\n")


def _stale(root):
    _write(root, os.path.join("src", "app.py"), "x = 3\n")
    spec = os.path.join(root, ".work", "tickets", "T-1", "spec.md")
    with open(spec, encoding="utf-8") as handle:
        text = handle.read()
    _write(root, os.path.relpath(spec, root), text.replace("`src/**`", "`**`"))


def _in_scope(root):
    _write(root, os.path.join("src", "app.py"), "x = 2\n")


CASES = (("stale-approval", _stale, 2, "not approved"), ("out-of-scope", _out_of_scope, 2, "docs-out.md"),
         ("in-scope", _in_scope, 0, ""))


@pytestmark_git
@pytest.mark.parametrize("name,mutate,want,said", CASES, ids=[c[0] for c in CASES])
def test_the_native_route_blocks_and_allows_as_the_audit_decides(name, mutate, want, said, audit_only, tmp_path):
    root, _ = _repo(tmp_path)
    mutate(root)
    os.makedirs(str(tmp_path / "t"), exist_ok=True)

    code, _, err = _run(root, tmp_path, direct=True)

    assert code == want, f"{name}: stderr: {err}"
    assert said in err, err
    assert "UNKNOWN" not in err  # a decision, not a fault


@pytestmark_git
@pytest.mark.skipif(h.BASH is None, reason="no bash: the wrapper side of the parity was NOT run")
@crew_fixtures.SLOW
@pytest.mark.parametrize("name,mutate,want,said", CASES, ids=[c[0] for c in CASES])
def test_the_native_route_and_the_wrapper_give_one_verdict(name, mutate, want, said, monkeypatch, tmp_path):
    # a long row limit: the wrapper's own verdict is wanted here, not its 60 s UNKNOWN on a loaded host
    monkeypatch.setattr(crew_hook, "TABLE", (crew_hook._row("Stop", "", AUDIT, 900, guard=True),))  # pylint: disable=protected-access
    root, _ = _repo(tmp_path)
    mutate(root)
    os.makedirs(str(tmp_path / "t"), exist_ok=True)
    wrapper = _run(root, tmp_path, direct=False)
    native = _run(root, tmp_path, direct=True)

    if "UNKNOWN (guard timeout" in wrapper[2]:
        pytest.skip("the wrapper timed out on this host (the Git Bash fork cost this change removes): "
                    "its verdict was NOT compared")
    assert native[0] == wrapper[0] == want
    assert native[1:] == wrapper[1:] or said in native[2] and said in wrapper[2], (native, wrapper)


# --- speed, and a hung child -------------------------------------------------------------------------

def _fake_scripts(tmp_path, body):
    """A scripts directory whose `completion_audit.py` is `body`; the wrapper and its helper are the real ones."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in (AUDIT, "_common.sh"):
        shutil.copy(os.path.join(SCRIPTS, name), str(scripts / name))
    (scripts / "completion_audit.py").write_text(textwrap.dedent(body), encoding="utf-8", newline="\n")
    return str(scripts)


def test_a_hung_audit_settles_as_unknown_well_inside_its_limit(monkeypatch, tmp_path):
    row = crew_hook._row("Stop", "", AUDIT, 3, guard=True)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_hook, "TABLE", (row,))
    scripts = _fake_scripts(tmp_path, "import time\ntime.sleep(120)\n")
    project = tmp_path / "proj"
    project.mkdir()
    started = time.monotonic()

    code, _, err = _dispatch(project, _stop(project), tmp_path, scripts=scripts, deadline_s=60, real_env=True)

    took = time.monotonic() - started
    assert code == 2, err
    assert "UNKNOWN (guard timeout" in err and "failing closed (armed repo)" in err
    assert took < 30, f"a 3 s row took {took:.1f}s to settle"


@crew_fixtures.SLOW
def test_a_crashing_audit_never_comes_back_as_a_pass(monkeypatch, tmp_path):
    """The real round trip: python raises, the wrapper runs, finds an armed repo (a config present, so
    scope.mode is not provably off) and blocks. It never reads as exit 0, and on a host so loaded that the
    wrapper itself runs out of time it is the UNKNOWN timeout, which is also exit 2."""
    if h.BASH is None:
        pytest.skip("no bash: the wrapper fallback was NOT run")
    row = crew_hook._row("Stop", "", AUDIT, 120, guard=True)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_hook, "TABLE", (row,))
    scripts = _fake_scripts(tmp_path, "raise SystemExit(1)\n")
    project = tmp_path / "proj"
    (project / ".crew").mkdir(parents=True)
    (project / ".crew" / "config.json").write_text("{}", encoding="utf-8")
    tmp = tmp_path / "tmp"
    tmp.mkdir()

    code, _, err = _dispatch(project, _stop(project), tmp, scripts=scripts, deadline_s=200, bash=h.BASH,
                             real_env=True)

    assert code == 2, err
    assert "did not run to a verdict" in err or "UNKNOWN (guard timeout" in err, err


@pytest.mark.skipif(not h.WINDOWS or h.BASH is None,
                    reason="needs Windows and Git Bash: the Git Bash fork cost is what is being compared")
def test_the_native_row_is_far_faster_than_the_wrapper_on_a_trivial_input(audit_only, tmp_path):
    project = tmp_path / "proj"
    (project / ".crew").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True, capture_output=True)
    payload = _stop(project)

    def timed(direct):
        best = None
        for _ in range(2):
            started = time.monotonic()
            code, _, err = _dispatch(project, payload, tmp_path, direct=direct, deadline_s=120, bash=h.BASH,
                                     real_env=True)
            # the wrapper may run out of its 60 s on a loaded host (UNKNOWN): that is the slowness measured
            assert code == 0 or (not direct and "UNKNOWN (guard timeout" in err), err
            took = time.monotonic() - started
            best = took if best is None else min(best, took)
        return best

    native = timed(True)
    wrapper = timed(False)

    assert native < 5.0, f"the native row took {native:.2f}s"
    assert native * 3 < wrapper, f"native {native:.2f}s is not far below the wrapper's {wrapper:.2f}s"
