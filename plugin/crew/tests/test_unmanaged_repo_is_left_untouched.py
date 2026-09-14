"""A repo that never opted in must come out of a session with nothing added.

The two halves were each defensible and the pair was not:

  * `crew_config._log_guard` created `.crew/` so it could append a guard row,
    and `_maybe_log` skipped that only for a REFUSAL -- the decision that
    almost never happens in a repo crew is not managing. The production guards
    fire on every `ssh` and every `psql`, and the ordinary allowed one wrote
    the directory.
  * `crew_platform.main` resolves its root from bare `.crew/` presence when no
    candidate has a readable config, and `heal_config` then writes a full
    default `config.json` into it -- which is right for a crew repo whose
    config was deleted, and is the whole point of that function.

Composed, one allowed `ssh` in a plain repo adopted that repo into crew by the
next SessionStart, printing a "wrote defaults" banner about a config nobody
asked for. `heal_config` states the promise in capitals ("a directory with no
`.crew/` is not a crew repository and must not be colonized") and it was gone
before that line was ever consulted.

The fix is at the creation site only. `crew_platform`'s rule is deliberately
NOT changed: a crew repo whose `config.json` was deleted still has its `.crew/`
and must still be healed, and reading that directory as opt-in is what makes
that possible.

SABOTAGE-TEST THIS FILE before trusting it: see `sabotage.py`.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_platform
import crew_state

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_GUARD_SH = os.path.join(_HOOKS, "guard.sh").replace("\\", "/")

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

# An ssh to a host nobody declared: the commonest command that reaches a
# production guard, and one that is ALLOWED. The defect needed an allow, which
# is why a suite full of refusals never saw it.
_INNOCENT = "ssh deploy@" + "build-box.example.invalid" + " uptime"


class _Stdin:  # pylint: disable=too-few-public-methods
    """crew_platform.main reads sys.stdin directly."""

    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


def _plain_repo(tmp_path):
    """A repo with no `.crew/` anywhere in it."""
    root = tmp_path / "plain"
    root.mkdir()
    (root / "README.md").write_text("a repo that never asked for crew\n",
                                    encoding="utf-8")
    return root


def _session_start(root, tmp_path, monkeypatch):
    """SessionStart, with every root candidate pinned.

    `monkeypatch.chdir` is not optional: `os.getcwd()` is the third candidate
    `main` considers, so running this from the checkout let it resolve THIS
    repository and heal its config instead. conftest clears CLAUDE_PROJECT_DIR,
    the second candidate, for every test.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(
        {"cwd": str(root), "session_id": "s1", "source": "startup"})))
    return crew_platform.main()


def test_an_allowed_command_does_not_create_crew(tmp_path):
    """The creation site, on its own. `record=True` is what the hooks pass."""
    root = _plain_repo(tmp_path)

    out = crew_config.guard_decision(str(root), "prodServer", _INNOCENT,
                                     record=True)

    assert out["decision"] == "allow", out
    assert not (root / ".crew").exists(), \
        "an allowed command must not create .crew/ in a repo that has none"
    assert sorted(os.listdir(root)) == ["README.md"]


def test_a_refused_command_does_not_create_crew_either(tmp_path):
    """The half that was already right, kept honest. It is now a consequence of
    the same rule rather than a special case, so it cannot drift away from it.
    """
    root = _plain_repo(tmp_path)

    out = crew_config.guard_decision(str(root), "forcePush",
                                     "git " + "push --force origin main",
                                     record=True)

    assert out["decision"] == "block"
    assert not (root / ".crew").exists()


def test_an_allowed_command_then_a_session_start_leaves_nothing_behind(
        tmp_path, monkeypatch, capsys):
    """The composition -- the actual defect, in the order it happened.

    Asserting only the first half would pass against a fix that created `.crew/`
    somewhere else, and asserting only the second would pass today, since
    `crew_platform` has always refused a repo with no `.crew/`.
    """
    root = _plain_repo(tmp_path)

    crew_config.guard_decision(str(root), "prodServer", _INNOCENT, record=True)
    assert _session_start(root, tmp_path, monkeypatch) == 0

    assert not (root / ".crew").exists(), "the repo was adopted into crew"
    assert not (root / ".crew" / "config.json").exists()
    assert sorted(os.listdir(root)) == ["README.md"]
    assert capsys.readouterr().out == "", \
        "an unmanaged repo must not be reported on either"


@needs_bash
def test_the_same_thing_through_guard_sh(tmp_path, monkeypatch, capsys):
    """Through the hook that actually runs, because the hook is what passes
    `--record` and the hook is where a future change would put the write back.
    """
    root = _plain_repo(tmp_path)
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True)
    (home / ".claude" / "crew" / "config.json").write_text("{}", "utf-8")

    proc = subprocess.run(
        [_BASH, _GUARD_SH],
        input=json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": _INNOCENT}}),
        capture_output=True, text=True, check=False, cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
                 HOME=str(home), USERPROFILE=str(home)))

    assert proc.returncode == 0, proc.stderr
    assert not (root / ".crew").exists(), proc.stderr

    assert _session_start(root, tmp_path, monkeypatch) == 0
    assert not (root / ".crew").exists()
    capsys.readouterr()


# --- the controls: crew repos still get their log --------------------------


def test_a_crew_repo_still_records_what_it_allowed(tmp_path):
    """"Under `allow` nothing is silent" is the claim the log exists for, and
    the fix must not be "stop logging". A crew repo HAS a `.crew/`, which is
    exactly the condition the rule now turns on."""
    root = crew_fixtures.make_repo(tmp_path, config={"guards": {
        "forcePush": "allow"}}, git=False)
    path = tmp_path / "global.json"
    path.write_text(json.dumps({"guards": {"forcePush": "allow"}}), "utf-8")

    out = crew_config.guard_decision(str(root), "forcePush",
                                     "git " + "push --force origin main",
                                     str(path), record=True)

    assert out["decision"] == "allow"
    log = root / crew_state.GUARD_LOG_PATH
    assert log.is_file(), "a crew repo must still get its row"
    assert "allow" in log.read_text(encoding="utf-8")


def test_a_crew_repo_still_records_what_it_refused(tmp_path):
    """The refusal row, in the repo where there is somebody to read it. This is
    the case the old `decision == "block"` skip removed whenever `.crew/` was
    missing, and it is the reason that skip read as a safety rule at all."""
    root = crew_fixtures.make_repo(tmp_path, config={}, git=False)

    crew_config.guard_decision(str(root), "forcePush",
                               "git " + "push --force origin main",
                               record=True)

    log = root / crew_state.GUARD_LOG_PATH
    assert log.is_file()
    assert "block" in log.read_text(encoding="utf-8")


def test_a_crew_repo_with_a_deleted_config_is_still_healed(
        tmp_path, monkeypatch, capsys):
    """The reason `crew_platform`'s bare-`.crew/` rule was left alone. Fixing
    D5 there instead would have taken this with it -- and this is a repo that
    DID opt in, whose config somebody deleted.

    It doubles as the anti-vacuity check for every `_session_start` call above:
    `main` treats unreadable stdin as an empty payload and returns 0, so a
    broken `_Stdin` would make the "nothing was created" assertions pass for
    the wrong reason. Here the payload has to arrive, or nothing is healed.
    """
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    assert (root / ".crew").is_dir()
    assert not (root / ".crew" / "config.json").exists()

    assert _session_start(root, tmp_path, monkeypatch) == 0

    assert (root / ".crew" / "config.json").is_file()
    assert "missing" in capsys.readouterr().out


def test_the_log_write_is_still_best_effort(tmp_path):
    """`.crew` existing as a FILE is neither a directory to write into nor an
    absent one, and `guard_decision` must still return its decision: a guard
    that died over its own audit line would turn a logging failure into a
    blocked command, which is the worse of the two outcomes."""
    root = tmp_path / "crew-is-a-file"
    root.mkdir()
    (root / ".crew").write_text("not a directory\n", encoding="utf-8")

    out = crew_config.guard_decision(str(root), "prodServer", _INNOCENT,
                                     record=True)

    assert out["decision"] == "allow"
