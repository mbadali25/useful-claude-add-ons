"""T-0017: auto wrap-up before auto-clear.

`context.autoClear.wrapUp` (machine opt-in, exactly `true`; a repo `false`
vetoes, a repo `true` alone arms nothing) turns context-watch's high-context
warning into ONE wrap-up procedure -- finish the step, commit only on a
passing `Test:`, run `/crew:handoff --wrap-up`, end the turn -- and makes
auto-clear refuse unless the results are on disk: the handoff's `head:` is
HEAD, its `branch:` is the checkout, no tracked file is modified, and its
`resume:` line parses under T-0006's grammar or is `resume: none`.

Must-allow / must-block pairs, both flavours where the path exists:

  - arming: only machine `true` + armed, in-scope `enabled` + no repo `false`;
  - the check: a committed, fresh handoff passes (also with `resume: none`);
    every missing or mismatched result refuses with its reason; untracked
    files alone do not block; "could not tell" (git failing, crew_resume
    missing, ps1 with no python) refuses;
  - unarmed: plan output and context-watch's stderr, exit and marker are
    byte-identical to before;
  - escalation: a refusal is fed back once at the next non-continuation Stop,
    never on `stop_hook_active`, and exactly once across both flavours;
  - order: the check runs before the sent-marker claim.

No case reads the developer's config or process table, types a keystroke, or
commits outside a fixture repo: HOME, CLAUDE_CONFIG_DIR and
CREW_AUTOCLEAR_PROC_STUB point at fixtures and CREW_AUTOCLEAR_INHIBIT is set.
The .ps1 cases are told they are on Windows and skip without pwsh -- a skip
there means that flavour did NOT run.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_fixtures as cf

_PLUGIN = pathlib.Path(context._ROOT)  # pylint: disable=protected-access
_SCRIPTS = _PLUGIN / "hooks" / "scripts"
_BASH = cf.resolve_bash()
_PWSH = cf.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
FLAVORS = [pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh)]

SESSION = "55555555-eeee-4eee-8eee-000000000005"
KEY = crew_autocycle.session_key(SESSION)
RESUME = "/crew:done T-0001"


# --- plumbing ------------------------------------------------------------------

def _git(root, *args):
    return subprocess.run(("git", *args), cwd=str(root), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=True, timeout=30).stdout.strip()


class Repo:
    """A git fixture repo whose session crossed the threshold (a trusted
    marker), with its own HOME and machine file. Nothing is armed until
    `machine()` says so."""

    def __init__(self, tmp_path, repo_auto=None, machine_auto=None):
        self.tmp = tmp_path
        context_cfg = {"handoffPath": ".work/HANDOFF.md", "warnAt": 0.8, "budgetTokens": None,
                       "reserveTokens": 0, "autoWrapUp": True}
        if repo_auto is not None:
            context_cfg["autoClear"] = repo_auto
        self.root = cf.make_repo(tmp_path, config={"context": context_cfg})
        self.home = tmp_path / "home"
        self.gpath = self.home / ".claude" / "crew" / "config.json"
        self.machine(**(machine_auto if machine_auto is not None else {}))
        self.env = {"CLAUDE_CONFIG_DIR": str(self.home / ".claude")}

    # config ------------------------------------------------------------------
    def machine(self, **auto):
        self.gpath.parent.mkdir(parents=True, exist_ok=True)
        self.gpath.write_text(json.dumps({"context": {"autoClear": auto}}), encoding="utf-8")

    def arm(self, **extra):
        self.machine(enabled=True, wrapUp=True, method="notify", **extra)

    def cfg(self):
        return crew_autocycle.settings(str(self.root), str(self.gpath))

    # git ---------------------------------------------------------------------
    def branch(self):
        return _git(self.root, "rev-parse", "--abbrev-ref", "HEAD")

    def head(self, length=40):
        return _git(self.root, "rev-parse", "HEAD")[:length]

    def commit(self, name="step.txt", text="done\n"):
        (self.root / name).write_text(text, encoding="utf-8")
        cf.commit_file(str(self.root), name)

    # wrap-up results ---------------------------------------------------------
    def request(self):
        (self.root / ".crew" / (".handoff-requested-" + KEY)).write_text(json.dumps({
            "session_id": SESSION, "requested_at": time.time() - 30, "trusted": True,
            "why": "measured"}), encoding="utf-8")

    def handoff(self, resume=RESUME, branch="", head="", lines=None):
        branch = self.branch() if branch == "" else branch
        head = self.head(7) if head == "" else head
        rows = ["# Handoff", "written: now", "ticket: T-0001"]
        if branch is not None:
            rows.append(f"branch: {branch}")
        if head is not None:
            rows.append(f"head: {head}")
        for line in ([resume] if isinstance(resume, str) else (resume or [])):
            rows.append(f"resume: {line}")
        rows += lines or ["", "## Done", "- the step, committed", "", "## Next action", "Close T-0001."]
        path = self.root / ".work" / "HANDOFF.md"
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        stamp = time.time() + 5
        os.utime(path, (stamp, stamp))
        return path

    def wrapped(self, **kw):
        """A complete, passing wrap-up: commit, marker, fresh handoff."""
        self.commit()
        self.request()
        self.handoff(**kw)

    # runs --------------------------------------------------------------------
    def base_env(self, flavor, extra=None):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                   CREW_AUTOCLEAR_INHIBIT="1", CLAUDE_PROJECT_DIR=str(self.root))
        for name in ("TMUX", "TMUX_PANE", "DISPLAY", "OS"):
            env.pop(name, None)
        env.update(self.env)
        env.update(extra or {})
        if flavor == "ps1":
            env["OS"] = "Windows_NT"
        return env

    def autoclear(self, flavor, *args, extra=None):
        env = self.base_env(flavor, extra)
        if flavor == "ps1":
            names = {"--dry-run": "-DryRun", "--force": "-Force"}
            cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(_SCRIPTS / "auto-clear.ps1"),
                   "-Session", SESSION, "-Root", str(self.root), *[names.get(a, a) for a in args]]
        else:
            cmd = [_BASH, str(_SCRIPTS / "auto-clear.sh").replace("\\", "/"),
                   "--session", SESSION, "--root", str(self.root), *args]
        return subprocess.run(cmd, cwd=str(self.root), env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, check=False, timeout=120)

    def transcript(self, used=900_000):
        usage = {"input_tokens": used // 10, "cache_read_input_tokens": used - used // 10 - 1000,
                 "cache_creation_input_tokens": 1000, "output_tokens": 5}
        path = self.tmp / "t.jsonl"
        path.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n' + json.dumps(
            {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5",
                                              "usage": usage}}) + "\n", encoding="utf-8")
        return path

    def stop(self, flavor, active=False, used=900_000, extra=None):
        payload = json.dumps({"session_id": SESSION, "transcript_path": str(self.transcript(used)),
                              "cwd": str(self.root), "hook_event_name": "Stop",
                              "stop_hook_active": active})
        env = self.base_env(flavor, extra)
        if flavor == "ps1":
            cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(_SCRIPTS / "context-watch.ps1")]
        else:
            cmd = [_BASH, str(_SCRIPTS / "context-watch.sh").replace("\\", "/")]
        return subprocess.run(cmd, input=payload, cwd=str(self.root), env=env, capture_output=True,
                              text=True, check=False, timeout=120)

    def log(self):
        path = self.root / ".crew" / ".autoclear.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def sent_marker(self):
        return self.root / ".crew" / (".autoclear-sent-" + KEY)

    def escalated(self):
        return self.root / ".crew" / (".wrapup-escalated-" + KEY)


def _system_messages(stdout):
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line)["systemMessage"])
    return out


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


# --- Step 1: arming ------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "true", 1, False])
def test_wrapup_unarmed_without_machine_true(tmp_path, value):
    box = Repo(tmp_path)
    box.machine(enabled=True, wrapUp=value)
    assert box.cfg()["wrapUp"] is False
    assert crew_autocycle.wrapup_armed(box.cfg(), str(box.root), SESSION) is False


def test_wrapup_armed_on_machine_true(repo):
    repo.arm()
    assert repo.cfg()["wrapUp"] is True
    assert crew_autocycle.wrapup_armed(repo.cfg(), str(repo.root), SESSION) is True


def test_wrapup_repo_true_alone_arms_nothing(tmp_path):
    box = Repo(tmp_path, repo_auto={"enabled": True, "wrapUp": True})
    box.machine(enabled=True)
    assert box.cfg()["wrapUp"] is False
    assert crew_autocycle.wrapup_armed(box.cfg(), str(box.root), SESSION) is False


def test_wrapup_repo_false_vetoes(tmp_path):
    box = Repo(tmp_path, repo_auto={"wrapUp": False})
    box.arm()
    assert box.cfg()["wrapUp"] is False


def test_wrapup_repo_null_does_not_veto(tmp_path):
    box = Repo(tmp_path, repo_auto={"wrapUp": None})
    box.arm()
    assert box.cfg()["wrapUp"] is True


def test_wrapup_needs_autoclear_enabled(repo):
    repo.machine(enabled=False, wrapUp=True)
    assert crew_autocycle.wrapup_armed(repo.cfg(), str(repo.root), SESSION) is False
    repo.machine(wrapUp=True)
    assert crew_autocycle.wrapup_armed(repo.cfg(), str(repo.root), SESSION) is False


def test_wrapup_needs_scope(repo):
    repo.arm(onlySessions=["someone-else"])
    assert crew_autocycle.wrapup_armed(repo.cfg(), str(repo.root), SESSION) is False


def test_wrapup_is_a_recognised_key(repo):
    repo.arm()
    assert not [w for w in repo.cfg()["_warnings"] if "wrapUp" in w]


def test_wrapup_armed_cli_prints_on_or_off(repo):
    def cli():
        env = dict(os.environ, HOME=str(repo.home), USERPROFILE=str(repo.home))
        return subprocess.run([sys.executable, str(_SCRIPTS / "crew_autocycle.py"), "wrapup-armed",
                               "--root", str(repo.root), "--session", SESSION], env=env,
                              capture_output=True, text=True, check=False, timeout=60).stdout.strip()
    assert cli() == "off"
    repo.arm()
    assert cli() == "on"


# --- Step 1: the check ---------------------------------------------------------

def _check(box):
    return crew_autocycle.wrapup_check(str(box.root), box.cfg())


def test_check_passes_committed_fresh_handoff(repo):
    repo.arm()
    repo.wrapped()
    assert _check(repo) == (True, "")


def test_check_passes_full_length_head(repo):
    repo.arm()
    repo.commit()
    repo.handoff(head=repo.head(40))
    assert _check(repo) == (True, "")


def test_check_passes_resume_none(repo):
    repo.arm()
    repo.wrapped(resume="none")
    assert _check(repo) == (True, "")


def test_check_refuses_head_mismatch(repo):
    repo.arm()
    repo.request()
    repo.handoff()          # written BEFORE the commit
    repo.commit()
    ok, why = _check(repo)
    assert not ok
    assert "head: is not HEAD" in why


def test_check_refuses_missing_head(repo):
    repo.arm()
    repo.commit()
    repo.handoff(head=None)
    ok, why = _check(repo)
    assert not ok and "no head:" in why


def test_check_refuses_branch_mismatch(repo):
    repo.arm()
    repo.commit()
    repo.handoff(branch="some-other-branch")
    ok, why = _check(repo)
    assert not ok and "branch:" in why and "some-other-branch" in why


def test_check_refuses_missing_branch(repo):
    repo.arm()
    repo.commit()
    repo.handoff(branch=None)
    ok, why = _check(repo)
    assert not ok and "no branch:" in why


def test_check_refuses_tracked_dirty(repo):
    repo.arm()
    repo.wrapped()
    (repo.root / "README.md").write_text("changed, not committed\n", encoding="utf-8")
    ok, why = _check(repo)
    assert not ok
    assert "1 tracked file is modified" in why


def test_check_refuses_staged_but_uncommitted(repo):
    repo.arm()
    repo.wrapped()
    (repo.root / "new.txt").write_text("staged\n", encoding="utf-8")
    _git(repo.root, "add", "new.txt")
    ok, why = _check(repo)
    assert not ok and "tracked file" in why


def test_check_ignores_untracked(repo):
    repo.arm()
    repo.wrapped()
    (repo.root / "scratch.txt").write_text("untracked\n", encoding="utf-8")
    assert _check(repo) == (True, "")


def test_check_ignores_a_tracked_handoff_itself(repo):
    # The handoff has to be written after the commit (its head: is HEAD), so
    # in a repo that tracks it, it is always modified; it alone never blocks.
    repo.arm()
    repo.commit()
    repo.handoff()
    cf.commit_file(str(repo.root), ".work/HANDOFF.md")
    repo.handoff()
    assert _check(repo) == (True, "")


def _subdir_repo(tmp_path, handoff_rel=".work/HANDOFF.md"):
    """A git repo at `top` whose crew root is `top/sub`: git status names
    paths from the top, handoffPath is relative to `sub`."""
    top = tmp_path / "top"
    sub = top / "sub"
    (sub / ".crew").mkdir(parents=True)
    (top / ".work").mkdir()
    (sub / ".crew" / "config.json").write_text(json.dumps({"context": {"handoffPath": handoff_rel}}),
                                              encoding="utf-8")
    _git(top, "init", "-q")
    _git(top, "config", "user.email", "t@example.invalid")
    _git(top, "config", "user.name", "T")
    (top / "README.md").write_text("x\n", encoding="utf-8")
    for path in (top / ".work" / "HANDOFF.md", sub / handoff_rel):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "fixture")
    gpath = tmp_path / "machine.json"
    gpath.write_text(json.dumps({"context": {"autoClear": {"enabled": True, "wrapUp": True}}}),
                     encoding="utf-8")
    cfg = crew_autocycle.settings(str(sub), str(gpath))

    def write_handoff():
        branch = _git(top, "rev-parse", "--abbrev-ref", "HEAD")
        head = _git(top, "rev-parse", "HEAD")[:7]
        (sub / handoff_rel).write_text(
            f"# H\nbranch: {branch}\nhead: {head}\nresume: {RESUME}\n", encoding="utf-8")
    return top, sub, cfg, write_handoff


def test_check_exempts_the_handoff_when_root_is_a_subdirectory(tmp_path):
    _top, sub, cfg, write_handoff = _subdir_repo(tmp_path)
    write_handoff()             # sub/.work/HANDOFF.md, tracked, now modified
    assert crew_autocycle.wrapup_check(str(sub), cfg) == (True, "")


def test_check_does_not_exempt_a_top_level_namesake_from_a_subdirectory(tmp_path):
    top, sub, cfg, write_handoff = _subdir_repo(tmp_path)
    write_handoff()
    (top / ".work" / "HANDOFF.md").write_text("uncommitted work\n", encoding="utf-8")
    ok, why = crew_autocycle.wrapup_check(str(sub), cfg)
    assert not ok and "1 tracked file is modified (.work/HANDOFF.md)" in why


def test_check_exempts_a_handoff_path_git_would_quote(tmp_path):
    _top, sub, cfg, write_handoff = _subdir_repo(tmp_path, ".work/HANDÖFF notes.md")
    write_handoff()
    assert crew_autocycle.wrapup_check(str(sub), cfg) == (True, "")


def test_check_refuses_missing_resume(repo):
    repo.arm()
    repo.wrapped(resume=None)
    ok, why = _check(repo)
    assert not ok and why == "resume line: no resume line"


def test_check_refuses_two_resume_lines(repo):
    repo.arm()
    repo.wrapped(resume=[RESUME, "none"])
    ok, why = _check(repo)
    assert not ok and why == "resume line: 2 resume lines"


def test_check_refuses_excluded_command(repo):
    repo.arm()
    repo.wrapped(resume="/crew:approve T-0001")
    ok, why = _check(repo)
    assert not ok and "excluded" in why


def test_check_refuses_missing_handoff(repo):
    repo.arm()
    repo.commit()
    ok, why = _check(repo)
    assert not ok and "has not been written" in why


def test_check_refuses_when_crew_resume_missing(repo, monkeypatch):
    repo.arm()
    repo.wrapped()
    monkeypatch.setitem(sys.modules, "crew_resume", None)
    ok, why = _check(repo)
    assert not ok
    assert why == "T-0006's crew_resume is not installed"


def test_check_refuses_on_git_error(repo, monkeypatch):
    repo.arm()
    repo.wrapped()
    real = subprocess.run

    def broken(cmd, *args, **kwargs):
        if cmd and cmd[0] == "git":
            raise FileNotFoundError("git")
        return real(cmd, *args, **kwargs)  # pylint: disable=subprocess-run-check
    monkeypatch.setattr(crew_autocycle.subprocess, "run", broken)
    ok, why = _check(repo)
    assert not ok and "git" in why


def test_check_refuses_outside_a_git_repo(tmp_path):
    root = cf.make_repo(tmp_path, config={"context": {"handoffPath": ".work/HANDOFF.md"}}, git=False)
    (root / ".work" / "HANDOFF.md").write_text(
        f"# H\nbranch: main\nhead: abcdef1\nresume: {RESUME}\n", encoding="utf-8")
    cfg = crew_autocycle.settings(str(root), str(tmp_path / "absent.json"))
    ok, why = crew_autocycle.wrapup_check(str(root), cfg)
    assert not ok and "git" in why


def test_check_cli_prints_ok_or_the_reason(repo):
    def cli():
        env = dict(os.environ, HOME=str(repo.home), USERPROFILE=str(repo.home))
        return subprocess.run([sys.executable, str(_SCRIPTS / "crew_autocycle.py"), "wrapup-check",
                               "--root", str(repo.root)], env=env, capture_output=True, text=True,
                              check=False, timeout=60).stdout.strip()
    repo.arm()
    repo.commit()
    assert "has not been written" in cli()
    repo.handoff()
    assert cli() == "ok"


def _plan(box):
    return crew_autocycle.plan(str(box.root), SESSION, global_path=str(box.gpath))


def test_plan_unarmed_is_byte_identical(repo, monkeypatch):
    # A dirty tree and no head: would refuse if armed, and must not matter
    # when it is not -- whichever way wrapUp is left unarmed.
    for name, value in cf.bind_session(repo.home, SESSION).items():
        monkeypatch.setenv(name, value)
    repo.request()
    repo.handoff(head=None)
    (repo.root / "README.md").write_text("dirty\n", encoding="utf-8")
    repo.machine(enabled=True, method="notify")
    before = _plan(repo)
    assert before["status"] == "send"
    for value in (None, "true", False):
        repo.machine(enabled=True, method="notify", wrapUp=value)
        assert _plan(repo) == before, value


def test_plan_armed_refuses_with_the_wrapup_prefix(repo, monkeypatch):
    for name, value in cf.bind_session(repo.home, SESSION).items():
        monkeypatch.setenv(name, value)
    repo.arm()
    repo.request()
    repo.handoff()
    repo.commit()
    got = _plan(repo)
    assert got["status"] == "refuse"
    assert got["reason"].startswith("wrap-up: ")


def test_plan_force_skips_the_wrapup_check(repo, monkeypatch):
    for name, value in cf.bind_session(repo.home, SESSION).items():
        monkeypatch.setenv(name, value)
    repo.arm()
    got = crew_autocycle.plan(str(repo.root), SESSION, force=True, global_path=str(repo.gpath))
    assert got["status"] == "send"


# --- Step 2: context-watch sends the procedure, and escalates once ---------------

_PROCEDURE = ("crew wrap-up (context.autoClear.wrapUp) - context at 90%.",
              "Do not start a new step.",
              "No active ticket - the step is the tracked diff",
              "Run the step's Test: command now",
              "Commit only if it passes.",
              "do not commit",
              "resume: none",
              "Run /crew:handoff --wrap-up.",
              "End the turn.",
              "the handoff's head: is HEAD",
              "its branch: is the checked-out branch",
              "no tracked file is modified",
              "its resume: line parses")


def _norm(text):
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().splitlines())


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_message_is_the_procedure(repo, flavor):
    repo.arm()
    done = repo.stop(flavor)
    assert done.returncode == 2, done.stderr
    for part in _PROCEDURE:
        assert part in done.stderr, (part, done.stderr)
    assert "You are at roughly" not in done.stderr
    assert (repo.root / ".crew" / (".handoff-requested-" + KEY)).is_file()


def test_armed_message_names_handoff_wrap_up(repo):
    text = crew_autocycle.wrapup_message(str(repo.root), 91)
    assert "/crew:handoff --wrap-up" in text
    assert "context at 91%" in text


def test_armed_message_names_the_active_ticket(repo, monkeypatch):
    import crew_ticket  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(crew_ticket, "active_ticket", lambda root: ("T-0007", "fixture"))
    assert "Active ticket: T-0007" in crew_autocycle.wrapup_message(str(repo.root), 90)


@needs_bash
@needs_pwsh
def test_armed_message_parity(tmp_path):
    texts = []
    for flavor in ("sh", "ps1"):
        box = Repo(tmp_path / flavor)
        box.arm()
        done = box.stop(flavor)
        assert done.returncode == 2, done.stderr
        texts.append(_norm(done.stderr))
    assert texts[0] == texts[1]


def _marker_shape(box):
    data = json.loads((box.root / ".crew" / (".handoff-requested-" + KEY)).read_text(encoding="utf-8"))
    data.pop("requested_at")
    return data


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("auto_wrap_up", [True, False])
def test_unarmed_messages_unchanged_for_both_autowrapup_values(tmp_path, flavor, auto_wrap_up):
    seen = []
    unarmed = ({"enabled": True}, {"enabled": True, "wrapUp": None},
               {"enabled": False, "wrapUp": True}, {"wrapUp": True}, {"enabled": True, "wrapUp": "true"})
    for index, machine in enumerate(unarmed):
        box = Repo(tmp_path / str(index))
        cfg_path = box.root / ".crew" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["context"]["autoWrapUp"] = auto_wrap_up
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        box.machine(**machine)
        done = box.stop(flavor)
        seen.append((done.returncode, done.stderr, _marker_shape(box)))
    assert seen[0][0] == 2
    assert seen[0][1].startswith("You are at roughly" if auto_wrap_up else "Context:")
    assert all(item == seen[0] for item in seen), seen


@pytest.mark.parametrize("flavor", FLAVORS)
def test_repo_true_alone_sends_todays_message(tmp_path, flavor):
    box = Repo(tmp_path, repo_auto={"enabled": True, "wrapUp": True})
    box.machine(enabled=True)
    done = box.stop(flavor)
    assert done.returncode == 2
    assert done.stderr.startswith("You are at roughly")


@pytest.mark.parametrize("flavor", FLAVORS)
def test_repo_true_alone_does_not_arm_the_clear(tmp_path, flavor):
    box = Repo(tmp_path, repo_auto={"wrapUp": True})
    box.machine(enabled=True, method="notify")
    box.request()
    box.handoff(head=None)
    done = box.autoclear(flavor, "--dry-run", extra=cf.bind_session(box.home, SESSION))
    assert "autoclear: would send" in done.stdout, (done.stdout, box.log())


def _refusing(box):
    """Armed, the threshold already crossed (marker present), and the handoff
    written BEFORE the commit: the wrap-up check refuses on head."""
    box.arm()
    box.request()
    box.handoff()
    box.commit()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_escalates_once_on_refusal(repo, flavor):
    _refusing(repo)
    first = repo.stop(flavor)
    assert first.returncode == 2, first.stderr
    assert first.stderr.startswith("crew wrap-up incomplete: the handoff's head: is not HEAD")
    assert "run /crew:handoff --wrap-up again" in first.stderr
    assert repo.escalated().is_file()
    second = repo.stop(flavor)
    assert second.returncode == 0, second.stderr
    assert "crew wrap-up incomplete" not in second.stderr
    # The later Stop still hands over to auto-clear, which says why it waits.
    assert any(m.startswith("crew wrap-up: not clearing - the handoff's head: is not HEAD")
               for m in _system_messages(second.stdout)), second.stdout


@pytest.mark.parametrize("flavor", FLAVORS)
def test_never_escalates_on_stop_hook_active(repo, flavor):
    _refusing(repo)
    done = repo.stop(flavor, active=True)
    assert done.returncode == 0, done.stderr
    assert not repo.escalated().exists()
    assert "crew wrap-up incomplete" not in done.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_no_escalation_when_the_wrapup_passes(repo, flavor):
    repo.arm()
    repo.wrapped()
    done = repo.stop(flavor, extra=cf.bind_session(repo.home, SESSION))
    assert done.returncode == 0, done.stderr
    assert not repo.escalated().exists()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_no_escalation_unarmed(repo, flavor):
    repo.machine(enabled=True, method="notify")
    repo.request()
    repo.handoff()
    repo.commit()
    done = repo.stop(flavor)
    assert done.returncode == 0, done.stderr
    assert not repo.escalated().exists()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_no_escalation_after_the_clear_was_sent(repo, flavor):
    _refusing(repo)
    repo.sent_marker().write_text("", encoding="utf-8")
    done = repo.stop(flavor)
    assert done.returncode == 0, done.stderr
    assert not repo.escalated().exists()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_rearm_removes_the_escalation_marker(repo, flavor):
    _refusing(repo)
    repo.escalated().write_text("", encoding="utf-8")
    done = repo.stop(flavor, used=1000)
    assert done.returncode == 0, done.stderr
    assert not repo.escalated().exists()


@needs_bash
@needs_pwsh
def test_both_flavours_escalate_once(repo):
    _refusing(repo)
    codes = [repo.stop("sh").returncode, repo.stop("ps1").returncode]
    assert sorted(codes) == [0, 2], codes
    codes = [repo.stop("ps1").returncode, repo.stop("sh").returncode]
    assert codes == [0, 0], codes


def _no_python_path(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    cf.link_path_dirs(tools, skip=lambda name: name.startswith(("python", "py")))
    return str(tools)


@needs_pwsh
def test_ps1_without_python_reads_unarmed(repo, tmp_path):
    repo.arm()
    done = repo.stop("ps1", extra={"PATH": _no_python_path(tmp_path)})
    assert done.returncode == 2, done.stderr
    assert done.stderr.startswith("You are at roughly")
    assert "crew wrap-up" not in done.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_session_start_resets_escalation_marker(repo, flavor):
    other = repo.root / ".crew" / ".wrapup-escalated-someone-else"
    repo.escalated().write_text("", encoding="utf-8")
    other.write_text("", encoding="utf-8")
    payload = json.dumps({"session_id": SESSION, "cwd": str(repo.root), "hook_event_name": "SessionStart",
                          "source": "startup"})
    env = repo.base_env(flavor)
    if flavor == "ps1":
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(_SCRIPTS / "handoff-read.ps1")]
    else:
        cmd = [_BASH, str(_SCRIPTS / "handoff-read.sh").replace("\\", "/")]
    subprocess.run(cmd, input=payload, cwd=str(repo.root), env=env, capture_output=True, text=True,
                   check=False, timeout=120)
    assert not repo.escalated().exists()
    assert other.exists()


# --- Step 3: auto-clear shows a refusal, and the ps1 twin runs the check ----------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_dry_run_send_when_wrapup_passes(repo, flavor):
    repo.arm()
    repo.wrapped()
    done = repo.autoclear(flavor, "--dry-run", extra=cf.bind_session(repo.home, SESSION))
    assert "autoclear: would send" in done.stdout, (done.stdout, done.stderr, repo.log())
    assert "method: notify" in done.stdout


@pytest.mark.parametrize("flavor", FLAVORS)
def test_dry_run_send_with_resume_none(repo, flavor):
    repo.arm()
    repo.wrapped(resume="none")
    done = repo.autoclear(flavor, "--dry-run", extra=cf.bind_session(repo.home, SESSION))
    assert "autoclear: would send" in done.stdout, (done.stdout, repo.log())


_REFUSALS = {
    "head-missing": (lambda b: (b.commit(), b.request(), b.handoff(head=None)), "has no head: line"),
    "head-not-head": (lambda b: (b.request(), b.handoff(), b.commit()), "head: is not HEAD"),
    "branch": (lambda b: (b.commit(), b.request(), b.handoff(branch="elsewhere")), "branch: is elsewhere"),
    "dirty": (lambda b: (b.wrapped(), (b.root / "README.md").write_text("x\n", encoding="utf-8")),
              "1 tracked file is modified"),
    "resume-missing": (lambda b: b.wrapped(resume=None), "resume line: no resume line"),
    "resume-twice": (lambda b: b.wrapped(resume=[RESUME, RESUME]), "resume line: 2 resume lines"),
    "resume-excluded": (lambda b: b.wrapped(resume="/crew:approve T-0001"), "excluded from auto-resume"),
}


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("case", sorted(_REFUSALS))
def test_refusal_prints_system_message(repo, flavor, case):
    setup, reason = _REFUSALS[case]
    repo.arm()
    setup(repo)
    done = repo.autoclear(flavor, extra=cf.bind_session(repo.home, SESSION))
    messages = _system_messages(done.stdout)
    assert len(messages) == 1, (done.stdout, done.stderr)
    assert messages[0].startswith("crew wrap-up: not clearing - ")
    assert reason in messages[0]
    assert "refusing - wrap-up: " in repo.log() and reason in repo.log()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_untracked_file_alone_does_not_block(repo, flavor):
    repo.arm()
    repo.wrapped()
    (repo.root / "scratch.out").write_text("untracked\n", encoding="utf-8")
    done = repo.autoclear(flavor, "--dry-run", extra=cf.bind_session(repo.home, SESSION))
    assert "autoclear: would send" in done.stdout, (done.stdout, repo.log())


@pytest.mark.parametrize("flavor", FLAVORS)
def test_refusal_leaves_sent_marker_unclaimed(repo, flavor):
    _refusing(repo)
    done = repo.autoclear(flavor, extra=cf.bind_session(repo.home, SESSION))
    assert "refusing - wrap-up:" in repo.log(), (done.stdout, done.stderr)
    assert not repo.sent_marker().exists()
    # Fixed, the next attempt is not spent: it sends.
    repo.handoff()
    done = repo.autoclear(flavor, extra=cf.bind_session(repo.home, SESSION))
    assert repo.sent_marker().exists(), (done.stdout, done.stderr, repo.log())


@pytest.mark.parametrize("flavor", FLAVORS)
def test_unarmed_autoclear_ignores_the_wrapup_results(repo, flavor):
    repo.machine(enabled=True, method="notify")
    repo.request()
    repo.handoff(head=None, resume=None)
    (repo.root / "README.md").write_text("dirty\n", encoding="utf-8")
    done = repo.autoclear(flavor, "--dry-run", extra=cf.bind_session(repo.home, SESSION))
    assert "autoclear: would send" in done.stdout, (done.stdout, repo.log())
    assert "wrap-up" not in repo.log()


@needs_pwsh
def test_ps1_runs_wrapup_check_when_armed(repo):
    _refusing(repo)
    done = repo.autoclear("ps1", "--dry-run", extra=cf.bind_session(repo.home, SESSION))
    assert "would send" not in done.stdout
    assert "refusing - wrap-up: the handoff's head: is not HEAD" in repo.log()


@needs_pwsh
def test_ps1_no_python_refuses_armed_clear(repo, tmp_path):
    repo.arm()
    repo.wrapped()
    extra = cf.bind_session(repo.home, SESSION)
    extra["PATH"] = _no_python_path(tmp_path)
    done = repo.autoclear("ps1", extra=extra)
    assert "refusing - wrap-up: no usable python" in repo.log(), (done.stdout, done.stderr)
    assert not repo.sent_marker().exists()
    assert any("no usable python" in m for m in _system_messages(done.stdout))


@pytest.mark.parametrize("flavor", FLAVORS)
def test_crew_resume_missing_refuses_the_clear(repo, flavor, tmp_path):
    # A copy of the hook scripts without T-0006's module: "could not tell".
    import shutil  # pylint: disable=import-outside-toplevel
    scripts = tmp_path / "scripts"
    shutil.copytree(_SCRIPTS, scripts, ignore=shutil.ignore_patterns("crew_resume.py", "__pycache__", "_test"))
    repo.arm()
    repo.wrapped()
    env = repo.base_env(flavor, cf.bind_session(repo.home, SESSION))
    if flavor == "ps1":
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(scripts / "auto-clear.ps1"),
               "-Session", SESSION, "-Root", str(repo.root), "-DryRun"]
    else:
        cmd = [_BASH, str(scripts / "auto-clear.sh").replace("\\", "/"), "--session", SESSION,
               "--root", str(repo.root), "--dry-run"]
    done = subprocess.run(cmd, cwd=str(repo.root), env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False, timeout=120)
    assert "would send" not in done.stdout
    assert "T-0006's crew_resume is not installed" in repo.log(), (done.stdout, done.stderr)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_git_failing_refuses_the_clear(repo, flavor, tmp_path):
    repo.arm()
    repo.wrapped()
    bindir = tmp_path / "badgit"
    cf.write_shim(bindir, "git", "#!/bin/sh\necho 'fatal: broken' >&2\nexit 128\n",
                  "@echo off\r\necho fatal: broken 1>&2\r\nexit /b 128\r\n")
    extra = cf.bind_session(repo.home, SESSION)
    extra["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
    done = repo.autoclear(flavor, "--dry-run", extra=extra)
    assert "would send" not in done.stdout
    assert "refusing - wrap-up: git rev-parse failed (fatal: broken)" in repo.log(), (done.stdout, done.stderr)


# --- Step 4: one wrap-up path --------------------------------------------------

_HANDOFF_MD = _PLUGIN / "commands" / "handoff.md"
_AUTOPILOT_MD = _PLUGIN / "commands" / "autopilot.md"


def _wrap_up_section():
    text = _HANDOFF_MD.read_text(encoding="utf-8")
    start = text.index("With `--wrap-up`")
    end = text.index("With `--clear`")
    return text, text[start:end]


def test_handoff_documents_wrap_up_mode():
    text, section = _wrap_up_section()
    assert "argument-hint: [--clear | --wrap-up]" in text
    assert "git status --porcelain --untracked-files=no" in section
    assert "branch:" in section and "head:" in section and "after the commit" in section
    assert "resume: none" in section and "Verify first" in section
    assert "/crew:autopilot <ticket>" in section
    assert "/clear" in section and "Do not tell the user" in section
    assert len(text.splitlines()) <= 120


def test_wrap_up_mode_commits_only_on_passing_test():
    _text, section = _wrap_up_section()
    assert "only if the step's `Test:` passes" in section
    # Never "commit" without the condition beside it.
    for line in section.splitlines():
        if "commit" in line.lower() and "not commit" not in line.lower():
            assert "Test:" in line or "after the commit" in line or "committed" in line, line


@pytest.mark.skipif(not _AUTOPILOT_MD.is_file(), reason="autopilot.md absent (T-0004 not landed)")
def test_autopilot_uses_the_same_wrap_up():
    text = _AUTOPILOT_MD.read_text(encoding="utf-8")
    start = text.index("When context-watch asks for a handoff")
    bullet = text[start:text.index("Report the ticket", start)]
    assert "/crew:handoff --wrap-up" in bullet
    assert "/crew:autopilot <ticket>" in bullet
    for own in ("git commit", "/clear", "Test:"):
        assert own not in bullet, own
