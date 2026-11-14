"""`guards.enabled: false` in the MACHINE layer stands every guard hook down (crew 1.3.89, the dispatcher half).
A repo-layer `false` is ignored (owner decision 2026-11-13): a checkout cannot turn every guard off.

The must-block half and the must-allow half run the REAL dispatcher (`crew_hook.py`) and the REAL guard
scripts against the armed fixture repo of `record_golden_hooks.build_repo` (scope guard, cloud guard, env
guard and role-write guard all at block, a plan-approved ticket T-1), under a temporary HOME. Nothing here
touches the real config. `sabotage_guards_master.py` replays one mutation per rule below (wired into `sabotage.py`): each
reintroduces a bug this switch could have, and the suite must go red.

A "block" below is what the dispatcher reports: exit 2, or a PreToolUse `permissionDecision` of `deny`.
"""
import json
import os
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_humanonly
import record_golden_hooks as rgh

CLOUD = rgh.CLOUD
ENV_DUMP = "env"
HOOK = os.path.join(rgh.SCRIPTS, "crew_hook.py")


def _tool(name, **tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": tool_input,
            "session_id": "s-1", "tool_use_id": "tu-1"}


def _run(event, payload, root, home):
    env = rgh.env_for(root, home)
    env["CREW_HOOK_DEADLINE"] = str(crew_hook.now_ms() + 90000)
    payload = dict(payload, cwd=root)
    done = subprocess.run([sys.executable, HOOK, event], input=json.dumps(payload).encode(), capture_output=True,
                          env=env, cwd=root, timeout=120, check=False)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def blocked(result):
    code, out, _ = result
    return code == 2 or '"deny"' in out or '"ask"' in out


def _repo_config(root, patch):
    path = os.path.join(root, ".crew", "config.json")
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
    config.setdefault("guards", {}).update(patch)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)


def _machine_config(home, text):
    folder = os.path.join(home, ".claude", "crew")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "config.json"), "w", encoding="utf-8") as handle:
        handle.write(text if isinstance(text, str) else json.dumps(text))


def _receipt(path, state="applied", value=False, key="guards.enabled", layer="machine", target=None, settled=None):
    """The record `crew_confirm_config.confirm` leaves behind: what makes a machine `false` the OWNER's."""
    record = {"change_id": crew_humanonly.new_change_id(), "layer": layer,
              "target": target or crew_humanonly.target_key(path), "key": key, "value": value, "state": state,
              "created": time.time(), "settled": time.time() if settled is None else settled,
              "confirmations": [], "reason": "test"}
    crew_humanonly.write_record(crew_humanonly.store_dir(path), record)
    return record


def _off(home, text=None, encoding="utf-8"):
    """The machine layer switched off AND double-confirmed, as the owner would leave it."""
    folder = os.path.join(home, ".claude", "crew")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "config.json")
    body = text if text is not None else {"guards": {"enabled": False}}
    with open(path, "w", encoding=encoding) as handle:
        handle.write(body if isinstance(body, str) else json.dumps(body))
    _receipt(path)
    return path


@pytest.fixture(name="armed")
def _armed(tmp_path):
    return rgh.build_repo(str(tmp_path), True)


# What an armed repo refuses, one payload per guard family: the cloud guard, the env-dump guard, the scope
# guard (an edit outside the approved ticket's Touch list) and the role-write guard cannot be reached from a
# payload alone, so the first three stand for the family.
MUST_BLOCK = {
    "cloud-guard": _tool("Bash", command=CLOUD),
    "env-guard": _tool("Bash", command=ENV_DUMP),
    "scope-guard": _tool("Write", file_path="docs/outside.md", content="x"),
}
MUST_ALLOW = {
    "plain-command": _tool("Bash", command="ls -la"),
    "in-scope-edit": _tool("Write", file_path="src/app.py", content="x = 2\n"),
}


@pytest.mark.parametrize("name", sorted(MUST_BLOCK))
def test_must_block_with_the_guards_on(name, armed):
    """The control: with the switch absent, the armed fixture refuses each payload."""
    root, home = armed
    assert blocked(_run("PreToolUse", MUST_BLOCK[name], root, home)), name


@pytest.mark.parametrize("name", sorted(MUST_ALLOW))
def test_must_allow_with_the_guards_on(name, armed):
    root, home = armed
    assert not blocked(_run("PreToolUse", MUST_ALLOW[name], root, home)), name


@pytest.mark.parametrize("name", sorted(MUST_BLOCK))
def test_must_allow_with_the_switch_off_in_the_machine_layer(name, armed):
    root, home = armed
    _off(home)
    result = _run("PreToolUse", MUST_BLOCK[name], root, home)
    assert not blocked(result), (name, result)
    assert result[0] == 0


@pytest.mark.parametrize("name", sorted(MUST_BLOCK))
def test_must_block_when_only_the_repo_layer_says_false(name, armed):
    """A repo file cannot stand the guards down: a repo `false` with the machine file absent still blocks."""
    root, home = armed
    _repo_config(root, {"enabled": False})
    assert blocked(_run("PreToolUse", MUST_BLOCK[name], root, home)), name


@pytest.mark.parametrize("machine", [{"guards": {"enabled": True}}, {"guards": {}}, {}])
@pytest.mark.parametrize("name", sorted(MUST_BLOCK))
def test_must_block_when_the_repo_says_false_and_the_machine_does_not(name, machine, armed):
    """A repo `false` with the machine layer `true` (or silent) still blocks."""
    root, home = armed
    _repo_config(root, {"enabled": False})
    _machine_config(home, machine)
    assert blocked(_run("PreToolUse", MUST_BLOCK[name], root, home)), (name, machine)


def test_a_repo_false_is_reported_as_ignored_and_never_as_off(armed):
    root, home = armed
    assert crew_hook.repo_switch_ignored(root) is False
    _repo_config(root, {"enabled": False})
    assert crew_hook.repo_switch_ignored(root) is True
    assert crew_hook.guards_switched_off(root, home) is None
    _off(home)
    assert crew_hook.guards_switched_off(root, home) == "machine"


def test_off_wins_over_a_strict_profile_in_the_repo_layer(armed):
    root, home = armed
    _repo_config(root, {"profile": "strict"})
    _off(home, {"guards": {"enabled": False, "profile": "strict"}})
    assert not blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home))


def test_a_true_in_the_repo_layer_cannot_switch_back_on_a_machine_false(armed):
    root, home = armed
    _repo_config(root, {"enabled": True})
    _off(home)
    assert not blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home))


def test_a_stop_and_a_user_prompt_are_not_refused_by_a_guard_either(armed):
    """The Stop guards (verify gate, completion audit) are guard rows too."""
    root, home = armed
    _off(home)
    names = [argv[0] for row, argv in crew_hook.without_guards(crew_hook.select("Stop", "claude", None))]
    assert names == [], "context-watch (a Stop hook that can block) stands down too: nothing blocks"
    assert not blocked(_run("Stop", {"hook_event_name": "Stop", "session_id": "s-1"}, root, home))


@pytest.mark.parametrize("text", [
    '{"guards": {"enabled": "false"}}', '{"guards": {"enabled": 0}}', '{"guards": {"enabled": null}}',
    '{"guards": {"enabled": true}}', '{"guards": 42}', '{"guards": null}', '[false]', "{not json", ""])
def test_only_the_json_literal_false_switches_them_off(text, armed):
    """Could not tell, or any other value, leaves the guards on."""
    root, home = armed
    _off(home, text)
    assert blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home)), text


def test_an_unreadable_machine_layer_leaves_the_guards_on(armed):
    root, home = armed
    _off(home, '{"guards": {"enabled": false,}}')
    assert crew_hook.guards_switched_off(root, home) is None


def test_a_lookup_that_raises_leaves_the_guards_on(armed, monkeypatch):
    """Could not tell is never off: a reader that raises must read as ON."""
    root, home = armed
    _off(home)

    def boom(*_args, **_kwargs):
        raise OSError("planted")

    monkeypatch.setattr(crew_hook, "_layer_says_off", boom)
    assert crew_hook.guards_switched_off(root, home) is None


def test_the_approval_hook_still_runs_with_the_guards_off(tmp_path):
    """humanOnly's double confirmation is recorded by approval-hook.sh: it must survive the switch."""
    rows = crew_hook.without_guards(crew_hook.select("UserPromptSubmit", "claude", None))
    assert "approval-hook.sh" in [argv[0] for _, argv in rows]
    guard_rows = [row.script for row, _ in crew_hook.select("PreToolUse", "claude", None) if row.guard]
    assert guard_rows
    assert crew_hook.without_guards(crew_hook.select("PreToolUse", "claude", None)) == [
        (row, argv) for row, argv in crew_hook.select("PreToolUse", "claude", None) if not row.guard]


def test_the_humanonly_opt_out_still_works_with_the_guards_off(tmp_path, monkeypatch):
    """The owner's double confirmation, end to end, with `guards.enabled: false` in BOTH layers."""
    import approval_hook  # pylint: disable=import-outside-toplevel
    import crew_confirm_config  # pylint: disable=import-outside-toplevel
    import crew_state  # pylint: disable=import-outside-toplevel
    import crew_ticket  # pylint: disable=import-outside-toplevel
    from scope_fixtures import make_repo, prompt  # pylint: disable=import-outside-toplevel
    home = tmp_path / "home" / ".claude" / "crew"
    home.mkdir(parents=True)
    path = home / "config.json"
    path.write_text(json.dumps({"guards": {"enabled": False}}), encoding="utf-8")
    _receipt(str(path))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    repo = make_repo(tmp_path, mode="block")
    assert crew_hook.guards_switched_off(str(repo)) == "machine"
    assert crew_ticket.cli_approval_allowed(str(repo)) is False
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))
    for index in (1, 2):
        data = prompt(repo, f"/crew:confirm-config {record['change_id']}")
        data["prompt_id"] = f"p-{index}"
        assert approval_hook.handle(data) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["guards"]["enabled"] is False
    assert crew_ticket.cli_approval_allowed(str(repo)) is True


def test_a_dispatcher_fault_does_not_fail_closed_with_the_guards_off(armed):
    root, home = armed
    _off(home)
    old = os.environ.get("HOME"), os.environ.get("USERPROFILE")
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    try:
        code, _ = crew_hook._fault("PreToolUse", root, "crew-hook: planted")  # pylint: disable=protected-access
        assert code == 0
        _machine_config(home, {"guards": {"enabled": True}})
        code, _ = crew_hook._fault("PreToolUse", root, "crew-hook: planted")  # pylint: disable=protected-access
        assert code == 2
        _machine_config(home, {})
        _repo_config(root, {"enabled": False})
        code, _ = crew_hook._fault("PreToolUse", root, "crew-hook: planted")  # pylint: disable=protected-access
        assert code == 2, "a repo-layer false must not relax the fail-closed fault path"
    finally:
        for key, value in zip(("HOME", "USERPROFILE"), old):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --- the owner's confirmation (decision A, crew 1.3.92) ---------------------------------------------------------

@pytest.mark.parametrize("name", sorted(MUST_BLOCK))
def test_an_unconfirmed_false_stands_nothing_down(name, armed):
    """A `false` an agent, a hook-side write or a hand edit left in the machine file, with no applied double
    confirmation behind it, reads as ON (like an unconfirmed humanOnly false reads human-only)."""
    root, home = armed
    _machine_config(home, {"guards": {"enabled": False}})
    assert blocked(_run("PreToolUse", MUST_BLOCK[name], root, home)), name
    assert crew_hook.guards_switched_off(root, home) is None
    assert crew_hook.machine_switch_unconfirmed(root, home) is True


def _case_pending(path):
    _receipt(path, state="pending")


def _case_expired(path):
    _receipt(path, state="expired")


def _case_other_file(path):
    _receipt(path, target=os.path.join(os.path.dirname(path), "elsewhere.json"))


def _case_other_key(path):
    _receipt(path, key="humanOnly.approve")


def _case_repo_layer(path):
    _receipt(path, layer="repo")


def _case_a_true_receipt(path):
    _receipt(path, value=True)


def _case_revoked_later(path):
    _receipt(path, settled=time.time() + 5)
    _receipt(path, state="revoked", value=None, settled=time.time() + 10)


def _case_unreadable_store(path):
    store = crew_humanonly.store_dir(path)
    os.makedirs(store, exist_ok=True)
    with open(os.path.join(store, "cc-00000000.json"), "w", encoding="utf-8") as handle:
        handle.write("{not json")


@pytest.mark.parametrize("seed", [_case_pending, _case_expired, _case_other_file, _case_other_key,
                                  _case_repo_layer, _case_a_true_receipt, _case_revoked_later,
                                  _case_unreadable_store])
def test_a_receipt_that_does_not_back_this_false_leaves_the_guards_on(seed, armed):
    root, home = armed
    _machine_config(home, {"guards": {"enabled": False}})
    seed(os.path.join(home, ".claude", "crew", "config.json"))
    assert blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home)), seed.__name__
    assert crew_hook.guards_switched_off(root, home) is None


def test_a_receipt_is_read_at_the_file_it_names_not_at_a_copy(armed):
    """The receipt binds to the machine config's real path: a receipt for another file's false counts nothing."""
    root, home = armed
    path = _off(home)
    other = os.path.join(root, "copy.json")
    with open(other, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"guards": {"enabled": False}}))
    assert crew_hook.guards_switched_off(root, home) == "machine"
    assert not crew_hook._owner_confirmed(other)  # pylint: disable=protected-access
    assert crew_hook._owner_confirmed(path)  # pylint: disable=protected-access


@pytest.mark.parametrize("text", [
    '{"guards": {"enabled": true, "enabled": false}}',
    '{"guards": {"enabled": false, "enabled": true}}',
    '{"guards": {"enabled": false}, "guards": {}}',
    '{"guards": {"enabled": false, "profile": "off", "profile": "strict"}}',
    '{"a": {"b": 1, "b": 2}, "guards": {"enabled": false}}'])
def test_a_duplicate_key_leaves_the_guards_on(text, armed):
    """Two JSON parsers disagree on which duplicate wins (this one used to read false; a reviewer's reads true):
    an ambiguous file cannot switch the guards off."""
    root, home = armed
    _off(home, text)
    assert blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home)), text
    assert crew_hook.guards_switched_off(root, home) is None


def test_a_utf8_bom_in_the_machine_file_still_reads(armed):
    """A Windows editor's BOM does not turn a confirmed false into 'could not tell'."""
    root, home = armed
    _off(home, encoding="utf-8-sig")
    assert crew_hook.guards_switched_off(root, home) == "machine"
    assert not blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home))


def test_a_home_redirected_into_the_checkout_stands_nothing_down(armed):
    """HOME / USERPROFILE pointed at a fake home shipped in the repo (config AND forged receipts inside it)."""
    root, _home = armed
    fake = os.path.join(root, "fakehome")
    _off(fake)
    assert crew_hook.machine_config_path(root, fake) is None
    assert crew_hook.guards_switched_off(root, fake) is None
    assert blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, fake))
    assert blocked(_run("PreToolUse", MUST_BLOCK["env-guard"], root, fake))


def test_a_home_redirected_into_the_working_directory_stands_nothing_down(armed, tmp_path, monkeypatch):
    root, _home = armed
    elsewhere = tmp_path / "somewhere"
    fake = elsewhere / "fakehome"
    _off(str(fake))
    monkeypatch.chdir(elsewhere)
    assert crew_hook.machine_config_path(root, str(fake)) is None
    assert crew_hook.guards_switched_off(root, str(fake)) is None


def test_the_real_machine_home_outside_the_project_is_used(armed):
    root, home = armed
    assert crew_hook.machine_config_path(root, home) == os.path.join(home, crew_hook.GLOBAL_CONFIG)


def test_an_approval_hook_fault_does_not_fail_closed_with_the_guards_off(tmp_path, monkeypatch):
    """approval-hook.sh is the one guard row that keeps running with the switch off. If IT faults in an armed
    repo, the fault must not become a refusal: nothing blocks while the owner has the guards off."""
    from crew_hook_harness import dispatch_fake  # pylint: disable=import-outside-toplevel
    scripts = tmp_path / "fakescripts"
    scripts.mkdir()
    crash = "import sys; sys.stdin.buffer.read(); sys.stderr.write('planted fault'); sys.exit(1)"
    for name, body in (("approval-hook.sh", crash), ("crew-context.sh", "import sys; sys.stdin.buffer.read()")):
        with open(scripts / name, "w", encoding="utf-8", newline=chr(10)) as handle:
            handle.write(body + chr(10))
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hi", "session_id": "s-1"}).encode()
    home = tmp_path / "home"
    path = _off(str(home))
    for key in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(key, str(home))
    code_off, _out, _err = dispatch_fake(monkeypatch, str(scripts), armed=True, event="UserPromptSubmit",
                                         payload=payload, env=dict(os.environ))
    assert code_off == 0
    os.unlink(path)
    code_on, _out, _err = dispatch_fake(monkeypatch, str(scripts), armed=True, event="UserPromptSubmit",
                                        payload=payload, env=dict(os.environ))
    assert code_on == 2, "the control: with the guards on, the same fault fails closed"


# --- the machine config is the owner's: an agent cannot write it (scope guard, crew 1.3.92) ---------------------

def _machine_path(home):
    return os.path.join(home, ".claude", "crew", "config.json")


@pytest.mark.parametrize("tool, args", [
    ("Write", lambda path: {"file_path": path, "content": "{}"}),
    ("Edit", lambda path: {"file_path": path, "old_string": "a", "new_string": "b"}),
    ("MultiEdit", lambda path: {"edits": [{"file_path": path, "old_string": "a", "new_string": "b"}]}),
    ("Bash", lambda path: {"command": f"echo '{{\"guards\":{{\"enabled\":false}}}}' > '{path}'"}),
    ("Bash", lambda path: {"command": "echo '{}' > ~/.claude/crew/config.json"}),
    ("Bash", lambda path: {"command": "printf x | tee $HOME/.claude/crew/config.json"}),
    ("Bash", lambda path: {"command": r"sed -i s/true/false/ ~\.claude\crew\config.json"}),
    ("Bash", lambda path: {"command": "Set-Content -Path ~/.claude/crew/config.json -Value x"}),
])
def test_an_agent_cannot_write_the_machine_config(tool, args, armed):
    root, home = armed
    _machine_config(home, {"guards": {"enabled": True}})
    result = _run("PreToolUse", _tool(tool, **args(_machine_path(home))), root, home)
    assert blocked(result), (tool, result)


@pytest.mark.parametrize("command", [
    "cat ~/.claude/crew/config.json", "ls -la ~/.claude/crew", "grep enabled ~/.claude/crew/config.json",
    "python3 crew_config.py --set guards.profile=standard"])
def test_reading_the_machine_config_and_the_sanctioned_writer_still_pass(command, armed):
    root, home = armed
    assert not blocked(_run("PreToolUse", _tool("Bash", command=command), root, home)), command


def test_a_write_to_the_machine_config_is_not_blocked_with_the_guards_off(armed):
    """Off means off: with a confirmed switch the scope guard is stood down, so nothing blocks."""
    root, home = armed
    _off(home)
    assert not blocked(_run("PreToolUse", _tool("Write", file_path=_machine_path(home), content="{}"), root, home))


def test_the_confirm_listing_names_a_pending_master_switch_proposal(tmp_path, monkeypatch):
    """`/crew:confirm-config` typed with no id lists the pending proposals: the master switch's must be one of
    them, and be marked as turning every guard off (the listing is how the owner finds the id)."""
    import approval_hook  # pylint: disable=import-outside-toplevel
    import crew_state  # pylint: disable=import-outside-toplevel
    folder = tmp_path / "home" / ".claude" / "crew"
    folder.mkdir(parents=True)
    path = folder / "config.json"
    path.write_text(json.dumps({"guards": {"enabled": True}}), encoding="utf-8")
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    now = time.time()
    record = {"change_id": crew_humanonly.new_change_id(), "layer": "machine", "key": "guards.enabled",
              "value": False, "state": "pending", "path": str(path), "target": crew_humanonly.target_key(str(path)),
              "created": now, "expires": now + 900, "confirmations": [], "settled": None, "reason": None}
    crew_humanonly.write_record(crew_humanonly.store_dir(str(path)), record)
    text = approval_hook._proposals_text(now)  # pylint: disable=protected-access
    assert record["change_id"] in text
    assert "guards.enabled: true -> false" in text and "TURNS EVERY GUARD OFF" in text


# --- the owner's files are protected in EVERY scope mode, `off` (the default) included ----------------------------

@pytest.fixture(name="unarmed")
def _unarmed(tmp_path):
    """A bare git repo: no `.crew/config.json`, so `scope.mode` is `off`, the default."""
    return rgh.build_repo(str(tmp_path), False)


@pytest.mark.parametrize("tool, args", [
    ("Write", lambda home: {"file_path": _machine_path(home), "content": "{}"}),
    ("Edit", lambda home: {"file_path": _machine_path(home), "old_string": "a", "new_string": "b"}),
    ("Write", lambda home: {"file_path": os.path.join(home, ".claude", "crew", "confirm-config", "cc-00000000.json"),
                            "content": "{}"}),
    ("Bash", lambda home: {"command": "echo '{}' > ~/.claude/crew/config.json"}),
    ("Bash", lambda home: {"command": "cp x ~/.claude/crew/confirm-config/cc-00000000.json"}),
])
def test_scope_mode_off_does_not_unprotect_the_owners_files(tool, args, unarmed):
    """With `scope.mode` off the scope guard does nothing else, but an agent could otherwise write BOTH the
    `false` and its receipt, so these two paths are refused in every mode."""
    root, home = unarmed
    assert blocked(_run("PreToolUse", _tool(tool, **args(home)), root, home)), (tool, args(home))


def test_scope_mode_off_still_allows_everything_else(unarmed):
    root, home = unarmed
    for payload in (_tool("Write", file_path="src/app.py", content="x = 2\n"),
                    _tool("Bash", command="cat ~/.claude/crew/config.json"),
                    _tool("Bash", command="python3 crew_config.py --set guards.profile=standard")):
        assert not blocked(_run("PreToolUse", payload, root, home)), payload


def test_the_owners_files_are_protected_outside_a_work_tree_too(tmp_path):
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True)
    bare = tmp_path / "notarepo"
    bare.mkdir()
    payload = _tool("Write", file_path=_machine_path(str(home)), content="{}")
    assert blocked(_run("PreToolUse", payload, str(bare), str(home)))
