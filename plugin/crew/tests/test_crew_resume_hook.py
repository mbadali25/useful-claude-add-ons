"""T-0006 through the real hook wrappers: the PreCompact record both
`handoff-write` flavours leave, and what `crew-context` injects on a
SessionStart after /clear or /compact.

Every run gets its own fixture repo and its own HOME (so the machine file is
the fixture's, never the developer's). The .ps1 cases are told they are on
Windows (`OS=Windows_NT`) so they run on a Linux pwsh; off a host with pwsh
they skip and say so -- a skip there means the PowerShell flavour was NOT run.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import context_fixtures
import crew_fixtures
import crew_resume

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_PLUGIN = context._ROOT  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
FLAVORS = [pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="bash not installed - sh NOT run")),
           pytest.param("ps1", marks=pytest.mark.skipif(_PWSH is None, reason="pwsh not installed - ps1 NOT run"))]
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout.strip()


def _repo(tmp_path, machine=True, resume="/crew:done T-0001", handoff=True):
    """A crew repo with ticket T-0001, a machine file, and (by default) a
    handoff whose branch/head match the checkout."""
    root = context_fixtures.make_repo(tmp_path)
    (root / ".work" / "tickets" / "T-0001").mkdir(parents=True)
    (root / ".work" / "tickets" / "T-0001" / "spec.md").write_text("spec\n", encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True)
    if machine is not None:
        (home / ".claude" / "crew" / "config.json").write_text(
            json.dumps({"resume": {"auto": machine}}), encoding="utf-8")
    if handoff:
        text = (f"# Handoff\nwritten: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                f"ticket: T-0001\nbranch: {_git(root, 'rev-parse', '--abbrev-ref', 'HEAD')}\n"
                f"head: {_git(root, 'rev-parse', '--short', 'HEAD')}\n"
                + (f"resume: {resume}\n" if resume else "")
                + "\n## Done\n- the spec\n\n## Next action\nClose T-0001 with /crew:done.\n")
        (root / ".work" / "HANDOFF.md").write_text(text, encoding="utf-8")
    return root


def _env(root):
    home = str(root.parent / "home")
    env = dict(os.environ, HOME=home, USERPROFILE=home, CREW_AUTOCLEAR_INHIBIT="1",
               CLAUDE_PROJECT_DIR=str(root),
               CREW_VAULT_OPS=str(root.parent / "absent-vault-ops.py"),
               CREW_OBSIDIAN_CONFIG=str(root.parent / "absent-obsidian.json"))
    return env


def _run(flavor, name, root, payload, os_env=None):
    env = _env(root)
    if flavor == "ps1":
        env["OS"] = os_env or "Windows_NT"
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", os.path.join(_SCRIPTS, f"{name}.ps1")]
    else:
        if os_env:
            env["OS"] = os_env
        cmd = [_BASH, os.path.join(_SCRIPTS, f"{name}.sh").replace("\\", "/")]
    return subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True,
                          input=json.dumps(payload), check=False, timeout=120)


def _precompact(root, session, trigger):
    data = {"hook_event_name": "PreCompact", "session_id": session, "cwd": str(root),
            "transcript_path": str(root / "no-transcript.jsonl")}
    if trigger is not None:
        data["trigger"] = trigger
    return data


def _record_path(root, session):
    return os.path.join(crew_resume.state_dir(str(root)), f"precompact-{session}.json")


def _decide_compact(root, session="s1"):
    home = root.parent / "home"
    with open(root / ".work" / "HANDOFF.md", encoding="utf-8") as handle:
        text = handle.read()
    return crew_resume.decide(str(root), {"source": "compact", "session_id": session}, text, _PLUGIN,
                              global_path=str(home / ".claude" / "crew" / "config.json"))


# --- step 3: compact resumes only after a manual /compact -------------------

@needs_bash
def test_precompact_manual_compact_may_run(tmp_path):
    root = _repo(tmp_path)
    done = _run("sh", "handoff-write", root, _precompact(root, "s1", "manual"))

    got = _decide_compact(root)

    assert (done.returncode, got["action"], got["prompt"]) == (0, "run", "/crew:done T-0001"), done.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_precompact_auto_compact_waits(tmp_path, flavor):
    root = _repo(tmp_path)
    _run(flavor, "handoff-write", root, _precompact(root, "s1", "auto"))

    got = _decide_compact(root)

    assert (got["action"], got["reason"]) == ("wait", "compact was not a manual /compact")


def test_auto_compact_waits(tmp_path):
    """The sabotage target: a record that says `auto`, read by `decide`."""
    root = _repo(tmp_path)
    crew_resume.write_precompact_record(str(root), {"session_id": "s1", "trigger": "auto"})

    assert _decide_compact(root)["action"] == "wait"


@needs_bash
def test_precompact_missing_trigger_is_recorded_as_auto(tmp_path):
    root = _repo(tmp_path)
    _run("sh", "handoff-write", root, _precompact(root, "s1", None))

    with open(_record_path(root, "s1"), encoding="utf-8") as handle:
        assert json.load(handle)["trigger"] == "auto"


def test_precompact_unrecorded_compact_waits(tmp_path):
    root = _repo(tmp_path)

    got = _decide_compact(root)

    assert (got["action"], got["reason"]) == ("wait", "compact was not a manual /compact")


@needs_bash
def test_precompact_other_sessions_record_waits(tmp_path):
    root = _repo(tmp_path)
    _run("sh", "handoff-write", root, _precompact(root, "s1", "manual"))

    assert _decide_compact(root, session="s2")["action"] == "wait"


def test_precompact_record_older_than_ten_minutes_waits(tmp_path):
    root = _repo(tmp_path)
    crew_resume.write_precompact_record(str(root), {"session_id": "s1", "trigger": "manual"})
    path = _record_path(root, "s1")
    with open(path, encoding="utf-8") as handle:
        record = json.load(handle)
    record["at"] -= 601
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record))

    assert _decide_compact(root)["action"] == "wait"


def test_precompact_unreadable_record_waits(tmp_path):
    root = _repo(tmp_path)
    os.makedirs(os.path.dirname(_record_path(root, "s1")), exist_ok=True)
    with open(_record_path(root, "s1"), "w", encoding="utf-8") as handle:
        handle.write("{manual")

    assert _decide_compact(root)["action"] == "wait"


def test_precompact_session_key_is_reduced_like_the_wrap_up_marker(tmp_path):
    root = _repo(tmp_path)
    crew_resume.write_precompact_record(str(root), {"session_id": "a/b:c", "trigger": "manual"})

    assert (os.path.exists(_record_path(root, "a_b_c")), _decide_compact(root, "a/b:c")["action"]) == \
        (True, "run")


def test_precompact_without_a_session_writes_nothing(tmp_path):
    root = _repo(tmp_path)

    crew_resume.write_precompact_record(str(root), {"trigger": "manual"})

    state = crew_resume.state_dir(str(root))
    names = os.listdir(state) if os.path.isdir(state) else []
    assert [n for n in names if n.startswith("precompact-")] == []


@needs_bash
@needs_pwsh
def test_precompact_record_same_in_both_flavours(tmp_path):
    records = []
    for flavor in ("sh", "ps1"):
        base = tmp_path / flavor
        base.mkdir()
        root = _repo(base)
        done = _run(flavor, "handoff-write", root, _precompact(root, "sess-9", "manual"))
        with open(_record_path(root, "sess-9"), encoding="utf-8") as handle:
            record = json.load(handle)
        records.append((done.returncode, sorted(record), record["trigger"], isinstance(record["at"], int)))

    assert records[0] == records[1] == (0, ["at", "trigger"], "manual", True)


# --- step 4: what crew-context injects -------------------------------------

_RUN_LINE = ("Auto-resume: ready to run /crew:done T-0001. This Claude Code build does not start a turn "
             "from a hook (spike 2026-09-25): press Enter to accept it, or type it; T-0013 types it "
             "where the terminal can be identified.")


def _start(root, source="clear", session="s1"):
    return {"hook_event_name": "SessionStart", "source": source, "session_id": session,
            "cwd": str(root), "transcript_path": str(root / "fresh.jsonl")}


def _context(flavor, root, source="clear", session="s1"):
    done = _run(flavor, "crew-context", root, _start(root, source, session))
    assert done.returncode == 0, done.stderr
    out = done.stdout.strip()
    return out, (json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else "")


def _todays_handoff_item(root):
    """The handoff item exactly as crew_context built it before T-0006
    (`crew_context.py` SessionStart branch, origin/main 768a747a)."""
    import crew_context  # pylint: disable=import-outside-toplevel
    with open(root / ".work" / "HANDOFF.md", encoding="utf-8") as handle:
        handoff = handle.read()
    action = crew_context.next_action(handoff)
    lead = f"Next action: {action}\n" if action else ""
    body = handoff.strip()[: crew_context.RESUME_CHARS - 600 - len(lead)]
    return (f"## Handoff from the previous session (.work/HANDOFF.md)\n{lead}{body}\n"
            "The working tree is the source of truth; verify against git diff.")


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_and_matching_names_the_exact_command(tmp_path, flavor):
    root = _repo(tmp_path)

    _out, text = _context(flavor, root)

    assert (f"Next action: Close T-0001 with /crew:done.\n{_RUN_LINE}\n# Handoff" in text,
            "resume: /crew:done T-0001" in text) == (True, True), text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_and_refused_names_the_reason(tmp_path, flavor):
    root = _repo(tmp_path, resume="/crew:approve T-0001")

    _out, text = _context(flavor, root)

    assert ("Auto-resume did not start: /crew:approve is excluded from auto-resume. Read the handoff "
            "and continue by hand." in text, "ready to run" in text) == (True, False), text


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("machine", [None, False, "true"])
def test_unarmed_output_is_todays_output(tmp_path, flavor, machine):
    root = _repo(tmp_path, machine=machine)

    _out, text = _context(flavor, root)

    assert (_todays_handoff_item(root) in text, "Auto-resume" in text) == (True, False), text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_repo_true_alone_output_is_todays_output(tmp_path, flavor):
    root = _repo(tmp_path, machine=None)
    (root / ".crew" / "crew.json").write_text(json.dumps({"resume": {"auto": True}}), encoding="utf-8")

    _out, text = _context(flavor, root)

    assert "Auto-resume" not in text, text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_startup_output_is_todays_output(tmp_path, flavor):
    root = _repo(tmp_path)

    _out, text = _context(flavor, root, source="startup")

    assert ("Handoff note at .work/HANDOFF.md. Next action: Close T-0001 with /crew:done." in text,
            "Auto-resume" in text) == (True, False), text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_with_no_handoff_says_why(tmp_path, flavor):
    root = _repo(tmp_path, handoff=False)

    _out, text = _context(flavor, root)

    assert ("Auto-resume did not start: no handoff note. Continue by hand." in text,
            "Read the handoff" in text) == (True, False), text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_with_a_stale_handoff_says_it_was_archived(tmp_path, flavor):
    root = _repo(tmp_path)
    path = root / ".work" / "HANDOFF.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        f"head: {_git(root, 'rev-parse', '--short', 'HEAD')}", "head: 0000000"), encoding="utf-8")

    _out, text = _context(flavor, root)

    assert ("Auto-resume did not start: the handoff was archived as stale. Continue by hand." in text,
            "Read the handoff" in text, path.exists()) == (True, False, False), text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_compact_after_a_manual_compact_names_the_command(tmp_path, flavor):
    root = _repo(tmp_path)
    _run(flavor, "handoff-write", root, _precompact(root, "s1", "manual"))

    _out, text = _context(flavor, root, source="compact")

    assert _RUN_LINE in text, text


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_compact_after_an_auto_compact_waits(tmp_path, flavor):
    root = _repo(tmp_path)
    _run(flavor, "handoff-write", root, _precompact(root, "s1", "auto"))

    _out, text = _context(flavor, root, source="compact")

    assert "Auto-resume did not start: compact was not a manual /compact." in text, text


@needs_bash
@needs_pwsh
def test_exactly_one_flavour_emits_for_one_payload(tmp_path):
    root = _repo(tmp_path)

    outs = [_run(flavor, "crew-context", root, _start(root)).stdout.strip() for flavor in ("sh", "ps1")]

    assert (sum(bool(o) for o in outs), _RUN_LINE in "".join(outs)) == (1, True)


def test_never_emits_initial_user_message(tmp_path):
    """The spike (Claude Code 2.1.282) proved an interactive SessionStart drops
    `initialUserMessage`, so crew never sends it: not when armed and ready,
    not when refused, not when off. `test_auto_cycle.py`'s own assertion of
    the same thing stays true beside this one."""
    flavor = "sh" if _BASH else "ps1"
    outs = []
    for label, kwargs in (("run", {}), ("wait", {"resume": "/crew:approve T-0001"}), ("off", {"machine": None})):
        base = tmp_path / label
        base.mkdir()
        outs.append(_context(flavor, _repo(base, **kwargs))[0])

    assert ([bool(o) for o in outs], [("initialUserMessage" in o) for o in outs],
            [set(json.loads(o)["hookSpecificOutput"]) for o in outs]) == \
        ([True] * 3, [False] * 3, [{"hookEventName", "additionalContext"}] * 3)


def test_the_context_log_records_the_decision(tmp_path):
    root = _repo(tmp_path)

    _context("sh" if _BASH else "ps1", root)

    starts = [r for r in context_fixtures.log_records(root) if r.get("event") == "SessionStart"]
    assert starts[-1]["resume"] == {"action": "run", "reason": "", "prompt": "/crew:done T-0001"}


def test_decide_raising_becomes_an_internal_error_wait_and_keeps_the_handoff(tmp_path, monkeypatch):
    import crew_context  # pylint: disable=import-outside-toplevel

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    import crew_state  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(tmp_path / "home" / ".claude" / "crew" / "config.json"))
    monkeypatch.setattr(crew_resume, "decide", boom)
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))
    payload = _start(root)

    text = crew_context.run(payload, json.dumps(payload).encode())

    assert ("Auto-resume did not start: internal error." in text,
            "## Handoff from the previous session" in text) == (True, True), text


# --- round 1 BLOCK: unarmed output is 768a747a's output, WHOLE --------------
#
# `_GOLDEN` is the whole additionalContext base 768a747a's crew_context.py
# produced for `_golden_repo`, captured by running that commit's
# hooks/scripts (`git archive 768a747a plugin/crew/hooks/scripts`) against the
# fixture, with the two facts that differ per run replaced by placeholders:
# {HEAD8} (`git rev-parse --short=8 HEAD`) and {HEAD7} (the handoff's head:).
# `test_unarmed_output_matches_base_code_live` re-captures it from the base
# code itself wherever that commit is reachable (skipped in a shallow clone).

_BASE = "768a747a"
_GOLDEN_HANDOFF = ("# Handoff\nticket: T-0001\nbranch: golden\nhead: {HEAD7}\nresume: /crew:done T-0001\n\n"
                   "## Done\n- the spec\n\n## Next action\nClose T-0001 with /crew:done.\n")
_GOLDEN_RESUMED = (
    "crew context ({SOURCE}): branch golden @ {{HEAD8}}.\n"
    "Code map: 2 subsystems in .crew/codemap/; a slice arrives when you name a subsystem or touch its files.\n"
    "## Handoff from the previous session (.work/HANDOFF.md)\n"
    "Next action: Close T-0001 with /crew:done.\n"
    "# Handoff\nticket: T-0001\nbranch: golden\nhead: {{HEAD7}}\nresume: /crew:done T-0001\n\n"
    "## Done\n- the spec\n\n## Next action\nClose T-0001 with /crew:done.\n"
    "The working tree is the source of truth; verify against git diff.")
_GOLDEN = {
    "clear": _GOLDEN_RESUMED.format(SOURCE="clear"),
    "compact": _GOLDEN_RESUMED.format(SOURCE="compact"),
    "startup": ("crew context (startup): branch golden @ {HEAD8}.\n"
                "Code map: 2 subsystems in .crew/codemap/; a slice arrives when you name a subsystem or "
                "touch its files.\n"
                "Handoff note at .work/HANDOFF.md. Next action: Close T-0001 with /crew:done."),
}


def _golden_repo(tmp_path, machine=None, repo_true=False):
    root = context_fixtures.make_repo(tmp_path)
    context_fixtures.git(root, "branch", "-m", "golden")
    (root / ".work" / "tickets" / "T-0001").mkdir(parents=True)
    (root / ".work" / "tickets" / "T-0001" / "spec.md").write_text("spec\n", encoding="utf-8")
    home = tmp_path / "home" / ".claude" / "crew"
    home.mkdir(parents=True)
    if machine is not None:
        (home / "config.json").write_text(json.dumps({"resume": {"auto": machine}}), encoding="utf-8")
    if repo_true:
        (root / ".crew" / "crew.json").write_text(json.dumps({"resume": {"auto": True}}), encoding="utf-8")
    facts = {"HEAD8": _git(root, "rev-parse", "--short=8", "HEAD"),
             "HEAD7": _git(root, "rev-parse", "--short=7", "HEAD")}
    (root / ".work" / "HANDOFF.md").write_text(_GOLDEN_HANDOFF.format(**facts), encoding="utf-8")
    return root, facts


def _context_py(scripts, root, source):
    """additionalContext from `scripts`/crew_context.py for one SessionStart."""
    payload = json.dumps(_start(root, source))
    done = subprocess.run([sys.executable, os.path.join(scripts, "crew_context.py")], cwd=str(root),
                          env=_env(root), input=payload, capture_output=True, text=True, check=False,
                          timeout=120)
    assert done.returncode == 0, done.stderr
    out = done.stdout.strip()
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


_UNARMED = [
    pytest.param("clear", {}, id="clear-no-machine-file"),
    pytest.param("compact", {}, id="compact-no-machine-file"),
    pytest.param("clear", {"machine": False}, id="clear-machine-false"),
    pytest.param("clear", {"machine": "true"}, id="clear-machine-string-true"),
    pytest.param("clear", {"repo_true": True}, id="clear-repo-true-only"),
    pytest.param("startup", {"machine": True}, id="startup-armed"),
    pytest.param("startup", {}, id="startup-no-machine-file"),
]


@pytest.mark.parametrize("source,kwargs", _UNARMED)
def test_unarmed_output_is_byte_identical_to_base(tmp_path, source, kwargs):
    root, facts = _golden_repo(tmp_path, **kwargs)

    text = _context_py(_SCRIPTS, root, source)

    assert text == _GOLDEN[source].format(**facts)


def _base_scripts(tmp_path):
    repo = os.path.dirname(os.path.dirname(_PLUGIN))
    probe = subprocess.run(["git", "cat-file", "-e", _BASE + "^{commit}"], cwd=repo,
                           capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip(f"base {_BASE} is not reachable here (shallow clone?) - the golden test still ran")
    dest = tmp_path / "base"
    dest.mkdir()
    archive = subprocess.run(["git", "archive", _BASE, "plugin/crew/hooks/scripts"], cwd=repo,
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    return str(dest / "plugin" / "crew" / "hooks" / "scripts")


@pytest.mark.parametrize("source,kwargs", _UNARMED)
def test_unarmed_output_matches_base_code_live(tmp_path, source, kwargs):
    base = _base_scripts(tmp_path)
    root, _facts = _golden_repo(tmp_path, **kwargs)
    before = _context_py(base, root, source)
    shutil.rmtree(root / ".git" / "crew")

    after = _context_py(_SCRIPTS, root, source)

    assert (after, bool(before)) == (before, True)


# --- round 1 review fixes, through the hooks --------------------------------

@pytest.mark.parametrize("breakage", ["settings-raises", "import-fails"])
def test_an_unconfirmable_opt_in_is_off_not_an_internal_error(tmp_path, monkeypatch, breakage):
    """Review NIT :605. With no machine opt-in, a crew_resume that cannot even
    be imported, or whose settings() raises, must leave /clear's output as it
    was -- not add "internal error" to every session on an unarmed machine."""
    import crew_context  # pylint: disable=import-outside-toplevel

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    root = _repo(tmp_path, machine=None)
    if breakage == "settings-raises":
        monkeypatch.setattr(crew_resume, "settings", boom)
    else:
        monkeypatch.setitem(sys.modules, "crew_resume", None)
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))
    payload = _start(root)

    text = crew_context.run(payload, json.dumps(payload).encode())

    assert ("Auto-resume" in text, "## Handoff from the previous session" in text) == (False, True), text


def _no_python_path(tmp_path):
    """A PATH holding git and the coreutils handoff-write.sh uses, and no
    python -- the "crew_py_strict finds nothing" host."""
    bindir = tmp_path / "nopy-bin"
    bindir.mkdir()
    for tool in ("git", "cat", "dirname", "mkdir", "date", "cp", "ls", "tail", "xargs", "rm", "head",
                 "grep", "sed", "tr", "env", "uname", "basename", "mktemp", "sleep", "cut"):
        found = shutil.which(tool)
        if found:
            os.symlink(found, bindir / tool)
    return str(bindir)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_a_later_precompact_with_no_python_leaves_no_manual_record(tmp_path, flavor):
    """Review FIX :308, the reviewer's reproduction: a manual record, then an
    automatic compact in the same session whose hook cannot run python. The
    old `manual` must not survive to make that compact look typed."""
    if os.name == "nt":
        pytest.skip("symlinked PATH fixture is POSIX-only")
    root = _repo(tmp_path)
    crew_resume.write_precompact_record(str(root), {"session_id": "s1", "trigger": "manual"})
    env = _env(root)
    env["PATH"] = _no_python_path(tmp_path)
    if flavor == "ps1":
        env["OS"] = "Windows_NT"
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", os.path.join(_SCRIPTS, "handoff-write.ps1")]
    else:
        cmd = [_BASH, os.path.join(_SCRIPTS, "handoff-write.sh")]

    done = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True,
                          input=json.dumps(_precompact(root, "s1", "auto")), check=False, timeout=120)

    assert (done.returncode, os.path.exists(_record_path(root, "s1")), _decide_compact(root)["action"]) == \
        (0, False, "wait"), done.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_a_crew_json_only_repo_still_records_a_manual_compact(tmp_path, flavor):
    """Review NIT (handoff-write early exit): /crew:migrate may retire
    .crew/config.json. Such a repo must still get its PreCompact record, and
    the transcript and skeleton-handoff writes stay config.json-only."""
    root = _repo(tmp_path)
    (root / ".crew" / "config.json").unlink()
    (root / ".crew" / "crew.json").write_text(json.dumps({"memory": {"inject": True}}), encoding="utf-8")
    (root / ".work" / "HANDOFF.md").rename(root / ".work" / "HANDOFF.keep")

    done = _run(flavor, "handoff-write", root, _precompact(root, "s1", "manual"))

    with open(_record_path(root, "s1"), encoding="utf-8") as handle:
        trigger = json.load(handle)["trigger"]
    assert (done.returncode, trigger, (root / ".work" / "HANDOFF.md").exists(),
            (root / ".crew" / "transcripts").exists()) == (0, "manual", False, False), done.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_a_repo_with_neither_config_file_gets_no_record(tmp_path, flavor):
    root = _repo(tmp_path)
    (root / ".crew" / "config.json").unlink()

    done = _run(flavor, "handoff-write", root, _precompact(root, "s1", "manual"))

    assert (done.returncode, os.path.exists(_record_path(root, "s1"))) == (0, False)


def test_session_start_prunes_precompact_records_older_than_a_day(tmp_path, monkeypatch):
    """Review NIT :280, the SessionStart half: pruned with the claims, by the
    same age rule, even on a machine that never writes another record."""
    import crew_context  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, machine=None)
    old = _record_path(root, "gone")
    os.makedirs(os.path.dirname(old), exist_ok=True)
    with open(old, "w", encoding="utf-8") as handle:
        handle.write("{}")
    stale = time.time() - 25 * 3600
    os.utime(old, (stale, stale))
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))
    payload = _start(root, source="startup")

    crew_context.run(payload, json.dumps(payload).encode())

    assert not os.path.exists(old)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_armed_with_a_stale_handoff_that_cannot_be_archived_waits(tmp_path, flavor):
    """Review round 2 FIX crew_context.py:822. Staleness came only from whether
    archiving SUCCEEDED, so a stale note that could not be moved (here
    `.crew/handoffs` is a file) was named as ready to run."""
    root = _repo(tmp_path)
    path = root / ".work" / "HANDOFF.md"
    ten_days_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10 * 86400))
    text = path.read_text(encoding="utf-8")
    path.write_text("\n".join(f"written: {ten_days_ago}" if line.startswith("written: ") else line
                              for line in text.split("\n")), encoding="utf-8")
    (root / ".crew" / "handoffs").write_text("not a directory\n", encoding="utf-8")

    _out, text = _context(flavor, root)

    assert ("Auto-resume did not start: the handoff is stale (crew_state.handoff_staleness). Read the "
            "handoff and continue by hand." in text, "ready to run" in text, path.exists()) == \
        (True, False, True), text


def test_a_staleness_verdict_that_raises_counts_as_stale(tmp_path, monkeypatch):
    """"Could not tell" is not "fresh": an archive step that raises must not
    let `decide` treat the note as current."""
    import crew_context  # pylint: disable=import-outside-toplevel
    import crew_state  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("staleness rule failed")
    monkeypatch.setattr(crew_state, "archive_stale_handoff", boom)

    assert crew_context._handoff_verdict(str(root), {}) == (False, True)  # pylint: disable=protected-access
