"""A Stop whose strict Git Bash probe could not tell (B-124 / CLDDEV-124) no longer blocks every turn forever.

On a busy Windows host the strict probe can say `unknown`: Git Bash exists but did not answer. The dispatcher used
to refuse the whole Stop before any row ran, and nothing looked at `stop_hook_active`, so a session looped on the
same block. Now, for an ARMED Stop with an `unknown` probe only:

  * rows with a believed direct route (the completion audit) run as usual; the bash-only rows (verify-gate.sh,
    context-watch.sh) are reported as unchecked and never spawned;
  * a real block from a row that ran still blocks, with the UNKNOWN notice added;
  * a continuation verify-gate.sh itself would exit on (its two literal `stop_hook_active` spellings, before the
    first NUL) is let through with a visible UNKNOWN notice;
  * a fresh Stop blocks at most `UNKNOWN_STOP_BLOCKS` times per session and project, then is let through with
    the notice; a count that cannot be told or written always blocks;
  * `absent` and `broken` Git Bash, and PreToolUse / UserPromptSubmit, block exactly as before.

Must-block cases are B*, must-allow A*. The sabotage rows in sabotage_crew_hook.py name these tests. Every test
uses tmp_path for the project, the count directory and TMPDIR; nothing touches real config or `~`.
"""
import json
import os
import pathlib

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_shell

# pylint: disable=protected-access

FAKE_BASH = "C:/fake/bash.exe"
UNKNOWN = crew_shell.Problem("Git Bash exists but did not answer: the self-test timed out (host overloaded)",
                             "unknown")
ABSENT = crew_shell.Problem("Git Bash not found (strict)", "absent")
BROKEN = crew_shell.Problem("Git Bash ran but failed its self-test (exit 1)", "broken")
BOUND = crew_hook.UNKNOWN_STOP_BLOCKS


def _result(code=0, err=b""):
    return {"exit": code, "stdout": b"", "stderr": err, "timed_out": False, "error": "", "pid": 1}


class Spy:
    """crew_hook.run_child replaced: records every start; the audit answers `audit`, everything else exit 0."""

    def __init__(self, monkeypatch, audit=None):
        self.calls = []
        self.audit = audit or _result()
        monkeypatch.setattr(crew_hook, "run_child", self)

    def __call__(self, argv, raw, timeout, env, cwd=None):
        self.calls.append(list(argv))
        return self.audit if os.path.basename(str(argv[1])) == "completion_audit.py" else _result()

    def spawned(self):
        return [os.path.basename(str(argv[1])) for argv in self.calls]

    def any_bash(self):
        return [argv for argv in self.calls if str(argv[1]).endswith(".sh") or "bash" in str(argv[0]).lower()]


@pytest.fixture(name="world")
def _world(tmp_path):
    project, state, tmp = tmp_path / "proj", tmp_path / "state", tmp_path / "tmp"
    for path in (project, state, tmp):
        path.mkdir()
    return {"project": project, "state": state, "tmp": tmp}


def _stop(session="s1", active=None):
    body = {"hook_event_name": "Stop", "session_id": session}
    raw = json.dumps(body, separators=(",", ":"))
    if active == "space":
        raw = raw[:-1] + ',"stop_hook_active": true}'
    elif active == "nospace":
        raw = raw[:-1] + ',"stop_hook_active":true}'
    return raw.encode()


def _dispatch(world, payload, problem=UNKNOWN, event="Stop", armed=True, root=None, env=None, direct=None,
              bash=None):
    if env is None:
        env = {"CLAUDE_PROJECT_DIR": str(world["project"]), "TMPDIR": str(world["tmp"])}
    resolved = (bash, "") if bash else (None, problem)
    code, out, err = crew_hook.dispatch(
        event, "claude", payload, crew_hook.now_ms() + 30000, env,
        str(world["project"]) if root is None else root, windows=True,
        resolve_bash=lambda strict=True: resolved, resolve_pwsh=lambda: (None, ""),
        armed_fn=lambda _root: armed, direct=direct, stop_state=str(world["state"]))
    return code, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _count_file(world, payload, root=None):
    return crew_hook._stop_unknown_path(payload, str(world["project"]) if root is None else root,
                                        str(world["state"]))


def _count(world, payload, root=None):
    path = _count_file(world, payload, root)
    if not os.path.exists(path):
        return None
    with open(path, encoding="ascii") as handle:
        return int(handle.read())


def _seed(world, payload, text, root=None):
    pathlib.Path(_count_file(world, payload, root)).write_text(text, encoding="ascii")


def _counts(world):
    return sorted(name for name in os.listdir(world["state"]) if name.startswith("crew-stop-unknown."))


# --- must-block -------------------------------------------------------------------------------------------------

def test_b1_a_fresh_unknown_stop_blocks_and_counts_block_1(world, monkeypatch):
    Spy(monkeypatch)
    payload = _stop()

    code, out, err = _dispatch(world, payload)

    assert code == 2 and out == ""
    assert "could not tell" in err and f"block 1 of {BOUND}" in err
    assert "Install Git for Windows" not in err
    assert _count(world, payload) == 1


def test_b2_the_second_fresh_unknown_stop_is_block_2(world, monkeypatch):
    Spy(monkeypatch)
    payload = _stop()
    _dispatch(world, payload)

    code, _, err = _dispatch(world, payload)

    assert code == 2 and f"block 2 of {BOUND}" in err
    assert _count(world, payload) == 2


@pytest.mark.parametrize("problem,words", [(ABSENT, "Install Git for Windows"), (BROKEN, "Repair or reinstall")],
                         ids=["absent", "broken"])
def test_b3_b4_absent_or_broken_git_bash_blocks_even_on_a_continuation_or_past_the_bound(world, monkeypatch,
                                                                                         problem, words):
    spy = Spy(monkeypatch)
    fresh = _stop()
    _seed(world, fresh, str(BOUND))

    for payload in (_stop(active="space"), fresh):
        code, _, err = _dispatch(world, payload, problem=problem)
        assert code == 2 and words in err, (payload, err)
        assert crew_hook.UNKNOWN_STOP not in err
    assert spy.calls == [], "absent/broken refuses the Stop before any row runs, as before"


@pytest.mark.parametrize("event", ["PreToolUse", "UserPromptSubmit"])
def test_b5_unknown_at_pretooluse_and_userpromptsubmit_still_blocks_past_the_bound(world, monkeypatch, event):
    Spy(monkeypatch)
    payload = json.dumps({"hook_event_name": event, "session_id": "s1", "tool_name": "Bash",
                          "tool_input": {"command": "ls"}, "prompt": "please approve"},
                         separators=(",", ":")).encode()
    _seed(world, payload, str(BOUND))

    code, _, err = _dispatch(world, payload, event=event, direct=False)

    assert code == 2 and "could not tell" in err
    assert crew_hook.UNKNOWN_STOP not in err


def test_b6_a_real_audit_block_past_the_bound_still_blocks_with_its_reason_and_the_notice(world, monkeypatch):
    spy = Spy(monkeypatch, audit=_result(2, b"COMPLETION AUDIT: the tree has unreviewed edits\n"))
    payload = _stop()
    _seed(world, payload, str(BOUND))

    code, _, err = _dispatch(world, payload)

    assert code == 2
    assert "COMPLETION AUDIT: the tree has unreviewed edits" in err
    assert crew_hook.UNKNOWN_STOP in err and "verify-gate.sh" in err
    assert spy.spawned() == ["completion_audit.py"]


def test_b7_a_count_file_holding_garbage_blocks_and_says_the_count_could_not_be_read(world, monkeypatch):
    Spy(monkeypatch)
    payload = _stop()
    _seed(world, payload, "not-a-number")

    code, _, err = _dispatch(world, payload)

    assert code == 2 and "could not be read" in err


def test_b8_a_count_that_cannot_be_written_blocks_and_says_so(world, monkeypatch):
    Spy(monkeypatch)
    blocker = world["state"] / "a-file"
    blocker.write_text("x", encoding="ascii")
    world = dict(world, state=blocker)

    code, _, err = _dispatch(world, _stop())

    assert code == 2 and "could not be counted" in err


_WIDE_ONLY = {
    "space-before-colon": b'{"session_id":"s1","stop_hook_active" : true}',
    "two-spaces-after": b'{"session_id":"s1","stop_hook_active":  true}',
    "tab-after": b'{"session_id":"s1","stop_hook_active":\ttrue}',
    "newline-after": b'{"session_id":"s1","stop_hook_active":\ntrue}',
}


@pytest.mark.parametrize("payload", list(_WIDE_ONLY.values()), ids=list(_WIDE_ONLY))
def test_b9_a_spelling_verify_gate_does_not_read_as_a_continuation_is_a_fresh_stop(world, monkeypatch, payload):
    assert not crew_hook._gate_continuation(payload)
    assert crew_hook._STOP_ACTIVE.search(crew_hook._flat(payload)), "the two rules must disagree on this payload"
    Spy(monkeypatch)

    code, _, err = _dispatch(world, payload)

    assert code == 2 and f"block 1 of {BOUND}" in err
    assert _count(world, payload) == 1


def test_b10_a_nul_inside_the_key_is_a_fresh_stop(world, monkeypatch):
    payload = b'{"session_id":"s1","stop_hook_ac\x00tive": true}'
    assert not crew_hook._gate_continuation(payload)
    assert crew_hook._STOP_ACTIVE.search(crew_hook._flat(payload)), "the two rules must disagree on this payload"
    Spy(monkeypatch)

    code, _, err = _dispatch(world, payload)

    assert code == 2 and f"block 1 of {BOUND}" in err
    assert _count(world, payload) == 1


def test_b11_the_literal_only_after_a_nul_is_a_fresh_stop(world, monkeypatch):
    payload = b'{"session_id":"s1"}\x00{"stop_hook_active": true}'
    assert not crew_hook._gate_continuation(payload)
    Spy(monkeypatch)

    code, _, err = _dispatch(world, payload)

    assert code == 2 and f"block 1 of {BOUND}" in err
    assert _count(world, payload) == 1


def test_b12_a_project_that_cannot_be_named_blocks_every_time_and_writes_no_count(world, monkeypatch):
    Spy(monkeypatch)

    for _ in range(BOUND + 1):
        code, _, err = _dispatch(world, _stop(), root="")
        assert code == 2 and "count could not be told" in err
    assert _counts(world) == []


# --- must-allow -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("spelling", ["space", "nospace"])
def test_a1_a_continuation_is_let_through_with_a_visible_unknown_notice(world, monkeypatch, spelling):
    spy = Spy(monkeypatch)
    payload = _stop(active=spelling)
    assert crew_hook._gate_continuation(payload)

    code, out, err = _dispatch(world, payload)

    assert code == 0, err
    message = json.loads(out)["systemMessage"]
    assert "UNKNOWN" in message and "verify-gate.sh" in message and "context-watch.sh" in message
    assert "continuation" in message and crew_hook.UNKNOWN_STOP in err
    assert _count(world, payload) is None
    assert spy.any_bash() == []


def test_a2_past_the_bound_a_fresh_stop_is_let_through_naming_the_bound(world, monkeypatch):
    Spy(monkeypatch)
    payload = _stop()
    for _ in range(BOUND):
        assert _dispatch(world, payload)[0] == 2

    code, out, _ = _dispatch(world, payload)

    assert code == 0
    message = json.loads(out)["systemMessage"]
    assert "UNKNOWN" in message and f"{BOUND}-block bound" in message
    assert "verify-gate.sh" in message and "context-watch.sh" in message


def test_a3_unarmed_is_exit_0_as_today_and_writes_no_count(world, monkeypatch):
    Spy(monkeypatch)

    code, _, err = _dispatch(world, _stop(), armed=False)

    assert code == 0 and "could not tell" in err
    assert _counts(world) == []


def test_a4_a_stop_whose_probe_answers_resets_the_count(world, monkeypatch):
    Spy(monkeypatch)
    payload = _stop()
    for _ in range(BOUND):
        _dispatch(world, payload)
    assert _count(world, payload) == BOUND

    code, _, _ = _dispatch(world, payload, bash=FAKE_BASH)

    assert code == 0 and _count(world, payload) is None
    code, _, err = _dispatch(world, payload)
    assert code == 2 and f"block 1 of {BOUND}" in err


def test_a5_another_session_has_its_own_count(world, monkeypatch):
    Spy(monkeypatch)
    for _ in range(BOUND):
        _dispatch(world, _stop("s1"))

    code, _, err = _dispatch(world, _stop("s2"))

    assert code == 2 and f"block 1 of {BOUND}" in err
    assert _dispatch(world, _stop("s1"))[0] == 0


def test_a6_the_audit_runs_directly_and_no_bash_is_started(world, monkeypatch):
    spy = Spy(monkeypatch)

    _dispatch(world, _stop())

    assert spy.spawned() == ["completion_audit.py"]
    assert spy.any_bash() == []


def test_a7_a_guard_log_row_is_written_into_an_existing_crew_dir_and_never_creates_one(world, monkeypatch):
    Spy(monkeypatch)
    _dispatch(world, _stop("s1"))
    assert not (world["project"] / ".crew").exists()

    (world["project"] / ".crew").mkdir()
    _dispatch(world, _stop("s2"))

    log = (world["project"] / ".crew" / "guard.log").read_text(encoding="utf-8")
    fields = log.strip().split("\t")
    assert fields[1:5] == ["crew-hook", "Stop", "gitbash-unknown", "blocked 1/2"], log
    assert "verify-gate.sh" in fields[5] and "context-watch.sh" in fields[5]


def test_a8_with_claude_project_dir_unset_two_projects_keep_separate_counts(world, monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    Spy(monkeypatch)
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    env = {"TMPDIR": str(world["tmp"])}
    for _ in range(BOUND):
        assert _dispatch(world, _stop(), root=str(root_a), env=env)[0] == 2

    code, _, err = _dispatch(world, _stop(), root=str(root_b), env=env)

    assert code == 2 and f"block 1 of {BOUND}" in err
    assert len(_counts(world)) == 2


def _spellings(root):
    yield os.path.join(root, ".")
    if os.name == "nt" and root[1:2] == ":":
        yield root[0].swapcase() + root[1:]


@pytest.mark.parametrize("which", [0, 1])
def test_a9_two_spellings_of_one_directory_share_one_count(world, monkeypatch, which):
    root = str(world["project"])
    spellings = list(_spellings(root))
    if which >= len(spellings):
        pytest.skip("a drive-letter spelling exists only on Windows")
    Spy(monkeypatch)
    _dispatch(world, _stop(), root=root)

    code, _, err = _dispatch(world, _stop(), root=spellings[which])

    assert code == 2 and f"block 2 of {BOUND}" in err
    assert len(_counts(world)) == 1
