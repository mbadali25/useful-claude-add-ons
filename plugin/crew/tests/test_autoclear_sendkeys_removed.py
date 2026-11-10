"""`sendkeys` was removed in crew 1.2.61 (L-0727 slice 3) together with
`auto-clear.ps1`. Every layer that used to name it must now refuse it, never
offer it, never write it, and never let an owner's real configuration grow a
new line because of the removal.

  - resolution: refused on every platform and environment, and `auto` never
    resolves to it;
  - the platform table and the key metadata no longer list it, and the
    platform concern names the removal;
  - the setup helper refuses to write it (no consent opens it again) and never
    offers it in a proposal;
  - the owner's real machine and repo configs, copied into a hermetic home,
    load and report identically with and without a `sendkeys` method, and
    no output line mentions it;
  - the documents that describe auto-clear do not offer it.
"""
import copy
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autoclear_setup as setup
import crew_autocycle
import crew_keys
import crew_platform

_PLUGIN = pathlib.Path(context._ROOT)  # pylint: disable=protected-access
_SCRIPTS = _PLUGIN / "hooks" / "scripts"
_REMOVED = "removed in crew 1.2.61"

_ENVS = [
    pytest.param({}, id="bare"),
    pytest.param({"OS": "Windows_NT"}, id="windows-nt"),
    pytest.param({"OS": "Windows_NT", "TMUX": "/tmp/fake,1,0", "TMUX_PANE": "%7"}, id="windows-nt-tmux"),
    pytest.param({"TMUX": "/tmp/fake,1,0", "TMUX_PANE": "%7"}, id="tmux"),
    pytest.param({"DISPLAY": ":0"}, id="x11"),
    pytest.param({"WAYLAND_DISPLAY": "wayland-0"}, id="wayland"),
    pytest.param({"OS": ""}, id="os-empty"),
]


# --- resolution ----------------------------------------------------------------

def test_sendkeys_removed_text_is_the_agreed_sentence():
    assert crew_autocycle.SENDKEYS_REMOVED == (
        "sendkeys was removed in crew 1.2.61 (L-0727); use notify or tmux")


@pytest.mark.parametrize("env", _ENVS)
def test_resolve_method_refuses_sendkeys_on_every_platform(env):
    got = crew_autocycle.resolve_method({"method": "sendkeys"}, env)

    assert got == {"ok": False, "reason": crew_autocycle.SENDKEYS_REMOVED}


@pytest.mark.parametrize("env", _ENVS)
def test_resolve_method_refuses_sendkeys(env):
    got = crew_autocycle.resolve_method({"method": "sendkeys"}, env)

    assert got["ok"] is False
    assert got["reason"] == crew_autocycle.SENDKEYS_REMOVED


@pytest.mark.parametrize("env", _ENVS)
def test_auto_never_resolves_to_sendkeys(env):
    got = crew_autocycle.resolve_method({"method": "auto"}, env)

    assert got.get("method") != "sendkeys"
    assert "sendkeys" not in json.dumps(got)


def test_auto_resolves_to_notify_on_native_windows_with_no_capability():
    got = crew_autocycle.resolve_method(
        {"method": "auto"}, {"OS": "Windows_NT", "TMUX": "", "DISPLAY": "", "TMUX_PANE": ""})

    assert got.get("ok") is True
    assert got["method"] == "notify"


# --- the platform table and the key metadata -------------------------------------

def test_no_platform_lists_sendkeys_as_a_method():
    assert [name for name, methods in crew_platform._AUTOCLEAR_METHODS.items()  # pylint: disable=protected-access
            if "sendkeys" in methods] == []


def test_the_windows_platforms_keep_notify_and_lose_only_sendkeys():
    table = crew_platform._AUTOCLEAR_METHODS  # pylint: disable=protected-access

    assert table["windows"] == ("auto", "none", "notify")
    assert table["windows-bash"] == ("auto", "none", "notify", "tmux")


def test_the_key_metadata_lists_no_sendkeys_value():
    assert "sendkeys" not in crew_keys.AUTOCLEAR_METHOD_VALUES


@pytest.mark.parametrize("os_name", ["windows", "windows-bash", "linux", "macos"])
def test_the_platform_concern_names_the_removal_for_sendkeys(os_name):
    cfg = {"context": {"autoClear": {"enabled": True, "method": "sendkeys"}}}

    found = crew_platform.concerns(cfg, {"os": os_name, "repoFilesystem": "native"})

    assert len(found) == 1
    assert "sendkeys" in found[0] and _REMOVED in found[0]
    assert "does not exist" not in found[0]


# --- the setup helper ----------------------------------------------------------------

def test_write_autoclear_method_refuses_sendkeys_and_writes_nothing(tmp_path):
    path = str(tmp_path / "config.json")

    with pytest.raises(PermissionError) as raised:
        setup.write_autoclear_method("sendkeys", path=path)

    assert _REMOVED in str(raised.value)
    assert not os.path.exists(path)


def test_write_autoclear_method_refuses_sendkeys_without_touching_an_existing_file(tmp_path):
    path = tmp_path / "config.json"
    original = json.dumps({"context": {"autoClear": {"method": "notify"}}})
    path.write_text(original, encoding="utf-8")

    with pytest.raises(PermissionError):
        setup.write_autoclear_method("sendkeys", path=str(path))

    assert path.read_text(encoding="utf-8") == original


def test_write_autoclear_method_no_longer_takes_a_consent_parameter(tmp_path):
    with pytest.raises(TypeError):
        setup.write_autoclear_method("notify", consent=True, path=str(tmp_path / "config.json"))  # pylint: disable=unexpected-keyword-arg


def _cli(*args):
    return subprocess.run([sys.executable, str(_SCRIPTS / "crew_autoclear_setup.py"), *args],
                          capture_output=True, text=True, check=False, timeout=60,
                          stdin=subprocess.DEVNULL)


@pytest.mark.parametrize("extra", [[], ["--yes"]], ids=["no-yes", "yes"])
def test_apply_method_cli_exits_2_for_sendkeys_with_the_text_on_stderr(tmp_path, extra):
    path = tmp_path / "config.json"

    done = _cli("--global-path", str(path), "apply-method", "sendkeys", *extra)

    assert done.returncode == 2, done.stdout + done.stderr
    assert _REMOVED in done.stderr
    assert done.stdout.strip() == ""
    assert not path.exists()


@pytest.mark.parametrize("state", ["fresh", "legacy-windows", "configured"])
def test_plan_windows_default_never_offers_sendkeys(tmp_path, state):
    path = tmp_path / "config.json"
    if state == "legacy-windows":
        path.write_text(json.dumps({"context": {"autoClear": {"method": "windows"}}}), encoding="utf-8")
    if state == "configured":
        path.write_text(json.dumps({"context": {"autoClear": {"method": "notify"}}}), encoding="utf-8")

    done = _cli("--global-path", str(path), "plan-windows-default")

    assert done.returncode == 0, done.stderr
    plan = json.loads(done.stdout)
    assert plan["updates"] in ({}, {"context.autoClear.method": "notify"})
    assert "sendkeys" not in json.dumps(plan["updates"]).lower()
    assert "sendkeys" not in json.dumps(plan.get("changes", [])).lower()
    mentions = [part for part in re.split(r"(?<=[.;])\s+", plan["message"]) if "sendkeys" in part.lower()]
    assert all(_REMOVED in part or "pre-1.0" in part for part in mentions), mentions


# --- the owner's real configs (A13) -----------------------------------------------------

# The machine-global file lives under the operator's real home, which the
# suite's home audit (L-0709) refuses to open from a test; only the repo file,
# which sits outside any home, is copied here. The machine file's check is the
# same load run by hand, outside pytest.
_OWNER_REPO_CONFIG = pathlib.Path("/repos/personal/useful-claude-add-ons/.crew/config.json")


def _owner_configs():
    return {"repo": _OWNER_REPO_CONFIG} if _OWNER_REPO_CONFIG.is_file() else {}


def _without_sendkeys(value):
    """The same document with every `method: sendkeys` key dropped."""
    if isinstance(value, dict):
        return {key: _without_sendkeys(item) for key, item in value.items()
                if not (key == "method" and item == "sendkeys")}
    if isinstance(value, list):
        return [_without_sendkeys(item) for item in value]
    return copy.deepcopy(value)


def _load_through_the_tools(base, machine_text, repo_text):
    home = base / "home"
    repo = base / "repo"
    (home / ".claude" / "crew").mkdir(parents=True)
    (repo / ".crew").mkdir(parents=True)
    machine_path = home / ".claude" / "crew" / "config.json"
    if machine_text is not None:
        machine_path.write_text(machine_text, encoding="utf-8")
    if repo_text is not None:
        (repo / ".crew" / "config.json").write_text(repo_text, encoding="utf-8")
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), CLAUDE_PROJECT_DIR=str(repo))
    env.pop("CLAUDE_CONFIG_DIR", None)
    outputs = []
    for script, args in (("crew_config.py", ["--all"]), ("crew_status.py", [])):
        done = subprocess.run(
            [sys.executable, str(_SCRIPTS / script), "--root", str(repo),
             *(["--global-path", str(machine_path)] if script == "crew_config.py" else []), *args],
            cwd=str(repo), env=env, capture_output=True, text=True, check=False, timeout=120,
            stdin=subprocess.DEVNULL)
        assert done.returncode == 0, done.stdout + done.stderr
        outputs.append((done.stdout + done.stderr).replace(str(base), "<base>"))
    return outputs


@pytest.mark.skipif(not _owner_configs(), reason=(
    f"{_OWNER_REPO_CONFIG} does not exist on this host, so there is no real owner repo config to load"))
def test_the_owner_repo_config_loads_with_no_sendkeys_line_and_no_new_line(tmp_path):
    repo_text = _OWNER_REPO_CONFIG.read_text(encoding="utf-8")

    loaded = _load_through_the_tools(tmp_path / "as-is", None, repo_text)

    stripped = json.dumps(_without_sendkeys(json.loads(repo_text)), indent=2)
    stripped_loaded = _load_through_the_tools(tmp_path / "stripped", None, stripped)
    for output in loaded:
        assert [line for line in output.splitlines() if "sendkeys" in line.lower()] == []
    assert loaded == stripped_loaded


# --- the documents do not offer it ------------------------------------------------------

_DOCUMENTS = ["skills/crew-setup/phases.md", "commands/onboard.md", "commands/migrate.md",
              "skills/crew-context/SKILL.md", "CONFIG.md"]


@pytest.mark.parametrize("relative", _DOCUMENTS)
def test_the_documents_only_mention_sendkeys_to_say_it_was_removed(relative):
    text = (_PLUGIN / relative).read_text(encoding="utf-8")

    offers = [block.strip() for block in re.split(r"\n\s*\n", text)
              if "sendkeys" in block.lower() and "removed" not in block.lower()]

    assert offers == [], f"{relative} still names sendkeys without saying it was removed: {offers}"
