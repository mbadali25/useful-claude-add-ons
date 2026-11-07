"""Whether AI-Connect may be installed and run as root: one switch, read the same way everywhere.

installer.py, install.sh (through `python3 root_policy.py check`), deploy and setup ask it before
they change anything. The switch, highest first:

    --allow-root                        the command line: allows root for this run
    AI_CONNECT_ALLOW_ROOT=1 | 0         the environment: allows, or refuses, root
    install.allow_root: true | false    ~/.config/ai-connect/config.yaml
    (none of them)                      the default: what every version before 0.2.7 did

The default is unchanged behaviour: nothing before 0.2.7 refused root, so with no switch set a
run as root goes ahead silently, exactly as before. `false` refuses root outright. `true` is the
supported root install: it prints a one-line warning, refuses a root whose HOME or user name is
another user's (`sudo -E`: root-owned secrets would land in that user's home), and afterwards
closes the config directory to 0700 and every file in it to 0600.

Root here is euid 0 on Linux and macOS. On Windows the switch has no effect: install.ps1 and
deploy ask for elevation (UAC) by design and run the Bridge task as the user without it, so an
elevated administrator is not treated as root. Standard library only: install.sh runs this with
the system python3 before any venv exists.
"""
from __future__ import annotations

import getpass
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

ENV = "AI_CONNECT_ALLOW_ROOT"
FLAG = "--allow-root"
CONFIG_KEY = "install.allow_root"
# Test seams. AI_CONNECT_DEPLOY_ROOT is deploy_core's: "1" means root, "0" not root (PR #709); unset
# keeps the real euid. AI_CONNECT_ROOT_HOME stands in for root's home from the password database
SEAM_ROOT = "AI_CONNECT_DEPLOY_ROOT"
SEAM_HOME = "AI_CONNECT_ROOT_HOME"

NOT_ROOT, DEFAULT, ALLOWED = "not-root", "default", "allowed"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class RootPolicyError(Exception):
    """A refusal, or a switch that cannot be read: one line, said as it is."""


def default_config_path() -> Path:
    # config_loader.CONFIG_PATH, without importing it: that needs PyYAML
    return Path.home() / ".config" / "ai-connect" / "config.yaml"


def is_root(environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    forced = {"1": True, "0": False}.get(environ.get(SEAM_ROOT, ""))
    if forced is not None:
        return forced
    if os.name == "nt":
        return False
    return os.geteuid() == 0


def _parse(value, where: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in _TRUE:
        return True
    if isinstance(value, str) and value.strip().lower() in _FALSE:
        return False
    # Never guessed: an unreadable switch is not "off" and not "on"
    raise RootPolicyError(f"{where} must be true or false (1/0, yes/no), got {value!r}")


def config_value(config_path: Path) -> bool | None:
    """install.allow_root from the config, None when the file or the key is not there."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as err:
        raise RootPolicyError(f"cannot read {config_path} for {CONFIG_KEY}: {err.strerror}") from None
    try:
        import yaml  # pylint: disable=import-outside-toplevel
    except ImportError:
        if "allow_root" not in text:
            return None
        raise RootPolicyError(f"{config_path} sets {CONFIG_KEY}, and this Python has no PyYAML to read it: "
                              f"pass {FLAG} or set {ENV}=1 or 0 instead") from None
    try:
        config = yaml.safe_load(text) or {}
    except yaml.YAMLError as err:
        raise RootPolicyError(f"cannot read {CONFIG_KEY}: {config_path} is not valid YAML ({err})") from None
    section = config.get("install") if isinstance(config, dict) else None
    if section is None:
        return None
    if not isinstance(section, dict):
        raise RootPolicyError(f"{config_path}: install must be a mapping, got {section!r}")
    if section.get("allow_root") is None:
        return None
    return _parse(section["allow_root"], f"{CONFIG_KEY} in {config_path}")


def resolve(flag: bool = False, environ: Mapping[str, str] | None = None,
            config_path: Path | None = None) -> tuple[bool | None, str]:
    """(value, where it came from): flag > environment > config > default (None)."""
    environ = os.environ if environ is None else environ
    if flag:
        return True, FLAG
    raw = environ.get(ENV)
    if raw is not None and raw.strip():
        return _parse(raw, ENV), ENV
    path = config_path or default_config_path()
    value = config_value(path)
    if value is not None:
        return value, f"{CONFIG_KEY} in {path}"
    return None, "default"


def _root_identity(environ: Mapping[str, str]) -> tuple[str | None, str | None]:
    """(home, user name) of this euid from the password database; None where it cannot be told."""
    try:
        import pwd  # pylint: disable=import-outside-toplevel
        entry = pwd.getpwuid(os.geteuid())
        home, name = entry.pw_dir, entry.pw_name
    except (ImportError, KeyError, AttributeError):
        home, name = None, None
    return environ.get(SEAM_HOME) or home, name


def _check_identity(environ: Mapping[str, str]) -> None:
    root_home, root_name = _root_identity(environ)
    home = str(Path.home())
    if root_home is not None and os.path.normpath(home) != os.path.normpath(root_home):
        raise RootPolicyError(
            f"refusing to run as root with HOME={home} (root's home is {root_home}): the config and tokens "
            "would land root-owned in another user's home. Use `sudo -i` or `sudo -H`, or run as that user")
    user = getpass.getuser()
    if root_name is not None and user != root_name:
        raise RootPolicyError(
            f"refusing to run as root with USER/LOGNAME={user} (this process is {root_name}): the service "
            "would be written for another user. Use `sudo -i` or `sudo -H`, or run as that user")


def warning(source: str, config_dir: Path) -> str:
    return (f"ai-connect: WARNING: running as root ({source}): the Bridge and MCP services run as root, with "
            f"the config and tokens owner-only (0700/0600) in {config_dir}; a dedicated service user is safer "
            "(e.g. `useradd --system --create-home ai-connect`, then install as it) and is not created for you")


def check(flag: bool = False, environ: Mapping[str, str] | None = None, config_path: Path | None = None,
          *, warn: bool = True, stream=None) -> str:
    """NOT_ROOT, DEFAULT (root, no switch set: as before 0.2.7) or ALLOWED; RootPolicyError refuses."""
    environ = os.environ if environ is None else environ
    if not is_root(environ):
        return NOT_ROOT
    path = config_path or default_config_path()
    value, source = resolve(flag, environ, path)
    if value is None:
        return DEFAULT
    if value is False:
        raise RootPolicyError(
            f"refusing to run as root: root is not allowed ({source} is false). Run as the user whose Claude "
            f"Code sessions use AI-Connect, or allow it with {FLAG}, {ENV}=1 or {CONFIG_KEY}: true")
    _check_identity(environ)
    if warn:
        print(warning(source, path.parent), file=stream or sys.stderr, flush=True)
    return ALLOWED


def secure(directory: Path) -> list[Path]:
    """Close directory to its owner: itself and every directory under it 0700, every file 0600.

    Symbolic links are neither followed nor changed. Returns what was changed. Windows has no mode
    bits to close (the config directory's ACL is the user's alone, vpn/tsadmin.py private_dir)."""
    if os.name == "nt" or not directory.is_dir() or directory.is_symlink():
        return []
    changed = []
    for here, dirs, files in os.walk(directory, followlinks=False):
        base = Path(here)
        for path, want in [(base, 0o700)] + [(base / name, 0o600) for name in files]:
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode):
                continue
            if stat.S_IMODE(st.st_mode) & 0o077:
                path.chmod(want)
                changed.append(path)
        dirs[:] = [d for d in dirs if not (base / d).is_symlink()]
    return changed


def main(argv: list[str] | None = None) -> int:
    """`root_policy.py check [--allow-root]`: prints not-root, default or allowed; exit 1 refuses."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "check" or any(a != FLAG for a in argv[1:]):
        print(f"usage: root_policy.py check [{FLAG}]", file=sys.stderr)
        return 2
    try:
        print(check(FLAG in argv[1:]))
    except RootPolicyError as err:
        print(f"ai-connect: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
