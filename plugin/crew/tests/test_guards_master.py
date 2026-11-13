"""`guards.enabled: false` stands every guard hook down (crew 1.3.87, the dispatcher half).

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

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
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


@pytest.mark.parametrize("layer", ["repo", "machine"])
@pytest.mark.parametrize("name", sorted(MUST_BLOCK))
def test_must_allow_with_the_switch_off_in_either_layer(name, layer, armed):
    root, home = armed
    if layer == "repo":
        _repo_config(root, {"enabled": False})
    else:
        _machine_config(home, {"guards": {"enabled": False}})
    result = _run("PreToolUse", MUST_BLOCK[name], root, home)
    assert not blocked(result), (name, layer, result)
    assert result[0] == 0


def test_off_wins_over_a_strict_profile_in_the_other_layer(armed):
    root, home = armed
    _repo_config(root, {"profile": "strict"})
    _machine_config(home, {"guards": {"enabled": False, "profile": "strict"}})
    assert not blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home))


def test_a_true_in_one_layer_cannot_switch_back_on_a_false_in_the_other(armed):
    root, home = armed
    _repo_config(root, {"enabled": True})
    _machine_config(home, {"guards": {"enabled": False}})
    assert not blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home))


def test_a_stop_and_a_user_prompt_are_not_refused_by_a_guard_either(armed):
    """The Stop guards (verify gate, completion audit) are guard rows too."""
    root, home = armed
    _repo_config(root, {"enabled": False})
    names = [argv[0] for row, argv in crew_hook.without_guards(crew_hook.select("Stop", "claude", None))]
    assert names == ["context-watch.sh"]
    assert not blocked(_run("Stop", {"hook_event_name": "Stop", "session_id": "s-1"}, root, home))


@pytest.mark.parametrize("text", [
    '{"guards": {"enabled": "false"}}', '{"guards": {"enabled": 0}}', '{"guards": {"enabled": null}}',
    '{"guards": {"enabled": true}}', '{"guards": 42}', '{"guards": null}', '[false]', "{not json", ""])
def test_only_the_json_literal_false_switches_them_off(text, armed):
    """Could not tell, or any other value, leaves the guards on."""
    root, home = armed
    _machine_config(home, text)
    assert blocked(_run("PreToolUse", MUST_BLOCK["cloud-guard"], root, home)), text


def test_an_unreadable_repo_layer_leaves_the_guards_on(armed):
    root, home = armed
    with open(os.path.join(root, ".crew", "config.json"), "w", encoding="utf-8") as handle:
        handle.write('{"guards": {"enabled": false,}}')
    assert crew_hook.guards_switched_off(root, home) is None


def test_a_lookup_that_raises_leaves_the_guards_on(armed, monkeypatch):
    """Could not tell is never off: a resolver that raises must read as ON."""
    import crew_common  # pylint: disable=import-outside-toplevel
    root, home = armed

    def boom(_root):
        raise OSError("planted")

    monkeypatch.setattr(crew_common, "repo_config_dir", boom)
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
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    repo = make_repo(tmp_path, mode="block")
    _repo_config(str(repo), {"enabled": False})
    assert crew_hook.guards_switched_off(str(repo)) is not None
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
    _repo_config(root, {"enabled": False})
    old = os.environ.get("HOME"), os.environ.get("USERPROFILE")
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    try:
        code, _ = crew_hook._fault("PreToolUse", root, "crew-hook: planted")  # pylint: disable=protected-access
        assert code == 0
        _repo_config(root, {"enabled": True})
        code, _ = crew_hook._fault("PreToolUse", root, "crew-hook: planted")  # pylint: disable=protected-access
        assert code == 2
    finally:
        for key, value in zip(("HOME", "USERPROFILE"), old):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
