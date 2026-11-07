"""root_policy.py: whether AI-Connect may install and run as root, and how installer.py, deploy and setup obey it.

Root is simulated with root_policy's seams (AI_CONNECT_DEPLOY_ROOT, AI_CONNECT_ROOT_HOME), so these run
the same as a normal user and as root. Every config, token and settings file lives under tmp_path; nothing
here reads or writes the real ~/.config/ai-connect or ~/.claude.
"""
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import installer
import root_policy

PLUGIN = Path(__file__).resolve().parent.parent
POSIX = os.name != "nt"
SWITCHES = (root_policy.ENV, root_policy.SEAM_ROOT, root_policy.SEAM_HOME, "AI_CONNECT_ROOT_WARNED")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """No switch from whoever runs the suite, and a HOME of the test's own."""
    for name in SWITCHES:
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def as_root(monkeypatch, home: Path) -> None:
    """This process is root, and HOME is root's own home."""
    monkeypatch.setenv(root_policy.SEAM_ROOT, "1")
    monkeypatch.setenv(root_policy.SEAM_HOME, str(home))


def config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cfg" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def assert_owner_only(directory: Path) -> None:
    if not POSIX:
        return
    assert mode(directory) == 0o700, directory
    for path in directory.rglob("*"):
        assert mode(path) == (0o700 if path.is_dir() else 0o600), path


# ---------------------------------------------------------------- precedence


def test_default_is_none_when_nothing_is_set(tmp_path):
    assert root_policy.resolve(False, {}, tmp_path / "missing.yaml") == (None, "default")


def test_config_true_and_false(tmp_path):
    assert root_policy.resolve(False, {}, config(tmp_path, "install:\n  allow_root: true\n"))[0] is True
    assert root_policy.resolve(False, {}, config(tmp_path, "install:\n  allow_root: false\n"))[0] is False


def test_env_beats_config(tmp_path):
    path = config(tmp_path, "install:\n  allow_root: false\n")
    assert root_policy.resolve(False, {root_policy.ENV: "1"}, path) == (True, root_policy.ENV)
    path = config(tmp_path, "install:\n  allow_root: true\n")
    assert root_policy.resolve(False, {root_policy.ENV: "0"}, path) == (False, root_policy.ENV)


def test_flag_beats_env_and_config(tmp_path):
    path = config(tmp_path, "install:\n  allow_root: false\n")
    assert root_policy.resolve(True, {root_policy.ENV: "0"}, path) == (True, root_policy.FLAG)


def test_empty_env_falls_through_to_config(tmp_path):
    path = config(tmp_path, "install:\n  allow_root: true\n")
    assert root_policy.resolve(False, {root_policy.ENV: " "}, path)[0] is True


@pytest.mark.parametrize("bad_env", ["maybe", "2", "allow"])
def test_unreadable_env_is_an_error_not_a_guess(tmp_path, bad_env):
    with pytest.raises(root_policy.RootPolicyError, match=root_policy.ENV):
        root_policy.resolve(False, {root_policy.ENV: bad_env}, tmp_path / "missing.yaml")


@pytest.mark.parametrize("text", ["install:\n  allow_root: sometimes\n", "install: yes-please\n", "install: [\n"])
def test_unreadable_config_is_an_error_not_a_guess(tmp_path, text):
    with pytest.raises(root_policy.RootPolicyError):
        root_policy.resolve(False, {}, config(tmp_path, text))


def test_a_malformed_config_never_shows_the_token_in_the_refusal(tmp_path):
    """PyYAML's own message quotes the offending text: here an undefined alias named after the token."""
    secret = "c0ffee" * 10 + "feed"
    path = config(tmp_path, f'client:\n  token: *{secret}\n')
    with pytest.raises(root_policy.RootPolicyError) as exc:
        root_policy.resolve(False, {}, path)
    assert "is not valid YAML (line 2" in str(exc.value)
    assert secret[:12] not in str(exc.value)


def test_a_config_without_the_key_is_the_default(tmp_path):
    assert root_policy.resolve(False, {}, config(tmp_path, "server:\n  port: 9999\n")) == (None, "default")


# ---------------------------------------------------------------- check: block and allow


def test_not_root_is_never_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(root_policy.SEAM_ROOT, "0")
    path = config(tmp_path, "install:\n  allow_root: false\n")
    assert root_policy.check(False, config_path=path) == root_policy.NOT_ROOT


def test_root_with_no_switch_goes_ahead_silently_as_before(tmp_path, monkeypatch, capsys, clean_env):
    as_root(monkeypatch, clean_env)
    assert root_policy.check(False, config_path=tmp_path / "missing.yaml") == root_policy.DEFAULT
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("how", ["env", "config"])
def test_must_block_root_when_the_switch_is_false(tmp_path, monkeypatch, clean_env, how):
    as_root(monkeypatch, clean_env)
    path = tmp_path / "missing.yaml"
    if how == "env":
        monkeypatch.setenv(root_policy.ENV, "0")
    else:
        path = config(tmp_path, "install:\n  allow_root: false\n")
    with pytest.raises(root_policy.RootPolicyError, match="refusing to run as root"):
        root_policy.check(False, config_path=path)


@pytest.mark.parametrize("how", ["flag", "env", "config"])
def test_must_allow_root_with_flag_env_or_config(tmp_path, monkeypatch, capsys, clean_env, how):
    as_root(monkeypatch, clean_env)
    path = tmp_path / "missing.yaml"
    if how == "env":
        monkeypatch.setenv(root_policy.ENV, "1")
    elif how == "config":
        path = config(tmp_path, "install:\n  allow_root: true\n")
    assert root_policy.check(how == "flag", config_path=path) == root_policy.ALLOWED
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1, err
    assert "WARNING: running as root" in err[0] and "service user" in err[0] and "not created" in err[0]


def test_allowed_root_with_another_users_home_is_refused(tmp_path, monkeypatch):
    """sudo -E: root would write root-owned secrets into the invoking user's home."""
    monkeypatch.setenv(root_policy.SEAM_ROOT, "1")
    monkeypatch.setenv(root_policy.SEAM_HOME, str(tmp_path / "root-home"))
    with pytest.raises(root_policy.RootPolicyError, match="HOME="):
        root_policy.check(True, config_path=tmp_path / "missing.yaml")


def test_quiet_check_prints_nothing(tmp_path, monkeypatch, capsys, clean_env):
    as_root(monkeypatch, clean_env)
    assert root_policy.check(True, config_path=tmp_path / "x.yaml", warn=False) == root_policy.ALLOWED
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------- file modes


@pytest.mark.skipif(not POSIX, reason="mode bits: Windows keeps the config directory's ACL instead")
def test_secure_closes_dirs_to_0700_and_files_to_0600(tmp_path):
    top = tmp_path / "ai-connect"
    (top / "peer-tokens").mkdir(parents=True)
    top.chmod(0o755)
    (top / "peer-tokens").chmod(0o775)
    for path in (top / "config.yaml", top / "user.token", top / "peer-tokens" / "a.token"):
        path.write_text("secret\n", encoding="utf-8")
        path.chmod(0o644)
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("not ours\n", encoding="utf-8")
    elsewhere.chmod(0o644)
    (top / "link").symlink_to(elsewhere)
    changed = root_policy.secure(top)
    assert mode(top) == 0o700 and mode(top / "peer-tokens") == 0o700
    for path in (top / "config.yaml", top / "user.token", top / "peer-tokens" / "a.token"):
        assert mode(path) == 0o600, path
    assert mode(elsewhere) == 0o644  # a symbolic link is not followed
    assert len(changed) == 5
    assert root_policy.secure(top) == []


# ---------------------------------------------------------------- installer.py


@pytest.fixture
def isolated_installer(monkeypatch, clean_env, tmp_path):
    cfg = clean_env / ".config" / "ai-connect" / "config.yaml"
    monkeypatch.setattr(installer, "CONFIG_PATH", cfg)
    monkeypatch.setattr(installer, "CLAUDE_SETTINGS", tmp_path / "settings.json")
    monkeypatch.setitem(installer.TOKEN_PATHS, "observer", cfg.parent / "observer.token")
    monkeypatch.setitem(installer.TOKEN_PATHS, "user", cfg.parent / "user.token")
    answers = ["bridge-1", "127.0.0.1"]
    monkeypatch.setattr("builtins.input", lambda _prompt="": answers.pop(0))
    return cfg


def test_installer_must_block_root_when_refused(isolated_installer, monkeypatch, clean_env):
    as_root(monkeypatch, clean_env)
    monkeypatch.setenv(root_policy.ENV, "0")
    with pytest.raises(SystemExit) as exc:
        installer.main(["config", "--server"])
    assert "refusing to run as root" in str(exc.value.code)
    assert not isolated_installer.exists()


@pytest.mark.parametrize("how", ["flag", "env"])
def test_installer_must_allow_root_and_keeps_secrets_owner_only(isolated_installer, monkeypatch, clean_env, capsys,
                                                                 how):
    as_root(monkeypatch, clean_env)
    argv = ["config", "--server"] + (["--allow-root"] if how == "flag" else [])
    if how == "env":
        monkeypatch.setenv(root_policy.ENV, "1")
    installer.main(argv)
    assert "WARNING: running as root" in capsys.readouterr().err
    assert isolated_installer.is_file() and (isolated_installer.parent / "user.token").is_file()
    assert_owner_only(isolated_installer.parent)


def test_installer_must_allow_root_from_the_config_key(isolated_installer, monkeypatch, clean_env, capsys):
    as_root(monkeypatch, clean_env)
    cfg = installer._example()  # pylint: disable=protected-access
    cfg["client"]["token"] = "a-real-token-not-the-placeholder"
    cfg["install"] = {"allow_root": True}
    isolated_installer.parent.mkdir(parents=True)
    isolated_installer.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    if POSIX:   # left open on purpose: the allowed root run closes it
        isolated_installer.parent.chmod(0o755)
        isolated_installer.chmod(0o644)
        (isolated_installer.parent / "stray.token").write_text("x\n", encoding="utf-8")
        (isolated_installer.parent / "stray.token").chmod(0o644)
    installer.main(["add-peer", "p2"])
    out = capsys.readouterr()
    assert "WARNING: running as root" in out.err and "Peer 'p2' added" in out.out
    assert_owner_only(isolated_installer.parent)


def test_installer_as_root_with_no_switch_runs_as_before(isolated_installer, monkeypatch, clean_env, capsys):
    as_root(monkeypatch, clean_env)
    installer.main(["config", "--server"])
    assert isolated_installer.is_file()
    assert "running as root" not in capsys.readouterr().err


# ---------------------------------------------------------------- deploy and setup


@pytest.fixture
def deploy(monkeypatch, tmp_path):
    """deploy, its config paths moved under tmp_path: an allowed root run closes CONFIG_DIR afterwards."""
    sys.path.insert(0, str(PLUGIN / "deploy"))
    import deploy as module  # pylint: disable=import-error,import-outside-toplevel
    monkeypatch.setattr(module, "CONFIG_DIR", tmp_path / "deploy-config")
    monkeypatch.setattr(module, "CONFIG_FILE", tmp_path / "deploy-config" / "config.yaml")
    return module


def test_every_deploy_verb_takes_allow_root(deploy):
    sub = next(a for a in deploy.build_parser()._actions if a.dest == "cmd")  # pylint: disable=protected-access
    for verb in ("bridge", "peer", "add-peer", "uninstall", "join", "approve", "remove", "invite"):
        assert "--allow-root" in sub.choices[verb].format_help(), verb


def test_deploy_must_block_root_when_refused(deploy, monkeypatch, clean_env, capsys):
    as_root(monkeypatch, clean_env)
    monkeypatch.setenv(root_policy.ENV, "0")
    ran = []
    monkeypatch.setattr(deploy, "cmd_add_peer", lambda args: ran.append(args) or 0)
    code = deploy.main(["add-peer", "--name", "p1", "--token-sha256", "0" * 64])
    assert code == deploy.EXIT_FAILED and not ran
    assert "refusing to run as root" in capsys.readouterr().err


def test_deploy_must_allow_root_with_the_flag_and_closes_the_config(deploy, monkeypatch, clean_env, capsys):
    as_root(monkeypatch, clean_env)
    monkeypatch.setenv(root_policy.ENV, "0")   # the flag outranks it
    deploy.CONFIG_DIR.mkdir()
    (deploy.CONFIG_DIR / "own-peer.token").write_text("t\n", encoding="utf-8")
    if POSIX:
        deploy.CONFIG_DIR.chmod(0o755)
        (deploy.CONFIG_DIR / "own-peer.token").chmod(0o644)
    ran = []
    monkeypatch.setattr(deploy, "cmd_add_peer", lambda args: ran.append(args) or 0)
    assert deploy.main(["add-peer", "--name", "p1", "--token-sha256", "0" * 64, "--allow-root"]) == 0
    assert ran and "WARNING: running as root" in capsys.readouterr().err
    assert_owner_only(deploy.CONFIG_DIR)


def test_deploy_status_runs_as_root_whatever_the_switch(deploy, monkeypatch, clean_env):
    as_root(monkeypatch, clean_env)
    monkeypatch.setenv(root_policy.ENV, "0")
    monkeypatch.setattr(deploy, "cmd_status", lambda args: 0)
    assert deploy.main(["status"]) == 0


def test_setup_must_block_root_when_refused(deploy, monkeypatch, clean_env, capsys):
    import peer_setup  # pylint: disable=import-error,import-outside-toplevel
    as_root(monkeypatch, clean_env)
    monkeypatch.setenv(root_policy.ENV, "0")
    ran = []
    monkeypatch.setattr(peer_setup, "cmd_session", lambda args: ran.append(args) or 0)
    assert peer_setup.main(["session", "--name", "s1"]) != 0 and not ran
    assert "refusing to run as root" in capsys.readouterr().err


def test_setup_must_allow_root_with_the_flag(deploy, monkeypatch, clean_env, capsys):
    import peer_setup  # pylint: disable=import-error,import-outside-toplevel
    as_root(monkeypatch, clean_env)
    ran = []
    monkeypatch.setattr(peer_setup, "cmd_session", lambda args: ran.append(args) or 0)
    assert peer_setup.main(["session", "--name", "s1", "--allow-root"]) == 0 and ran
    assert "WARNING: running as root" in capsys.readouterr().err


# ---------------------------------------------------------------- the command install.sh runs


def run_check(env_extra: dict, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in SWITCHES}
    env.update(env_extra)
    return subprocess.run([sys.executable, str(PLUGIN / "root_policy.py"), "check", *args], env=env,
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


def test_cli_check_reports_each_mode(clean_env):
    home = str(clean_env)
    base = {root_policy.SEAM_HOME: home, "HOME": home, "USERPROFILE": home}
    assert run_check({**base, root_policy.SEAM_ROOT: "0"}).stdout.strip() == "not-root"
    assert run_check({**base, root_policy.SEAM_ROOT: "1"}).stdout.strip() == "default"
    allowed = run_check({**base, root_policy.SEAM_ROOT: "1"}, "--allow-root")
    assert allowed.returncode == 0 and allowed.stdout.strip() == "allowed" and "WARNING" in allowed.stderr
    refused = run_check({**base, root_policy.SEAM_ROOT: "1", root_policy.ENV: "0"})
    assert refused.returncode == 1 and refused.stdout == "" and "refusing to run as root" in refused.stderr
    assert run_check(base, "--bogus").returncode == 2


def test_install_sh_passes_the_switch_on_and_drops_sudo_only_when_allowed():
    text = (PLUGIN / "install.sh").read_text(encoding="utf-8")
    assert 'root_policy.py" check "${ALLOW_ROOT[@]}"' in text
    assert 'installer.py" config --"$MODE" "${ALLOW_ROOT[@]}"' in text
    assert "SUDO=sudo" in text and 'SUDO=""' in text
    # No root-only step may bypass $SUDO: a bare `sudo <tool>` would need sudo even when root is allowed
    bare = [line for line in text.splitlines()
            if line.lstrip().startswith("sudo ") or line.lstrip().startswith("if sudo ")]
    assert not bare, bare
