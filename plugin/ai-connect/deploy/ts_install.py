"""The Tailscale step of `deploy bridge`, `deploy peer` and `deploy tailnet-setup`:
install Tailscale when it is missing, and log this machine in when asked to.

Debian and Ubuntu get Tailscale's own apt repository with its signing key in a
signed-by keyring; other Linux systems (and a release the repository does not
carry) get Tailscale's install script. Windows uses winget, or the MSI when
winget is missing; macOS uses Homebrew. Every command is printed before it runs,
and a dry run prints the same list and runs none of it. Some of them may stop
for a person (sudo's password, a UAC prompt, a browser login): deploy says so
first, hands the terminal to the tool, and carries on when it returns.
"""
from __future__ import annotations

import os
import platform
import re
import shlex
import sys
import tempfile
from pathlib import Path

from deploy_core import (IS_ROOT, Failure, Run, backend_state, interactive, out, tool,  # pylint: disable=import-error
                         ts_prefs, tsadmin)

PKGS = "https://pkgs.tailscale.com/stable"
INSTALL_SCRIPT_URL = "https://tailscale.com/install.sh"
APT_KEYRING = "/usr/share/keyrings/tailscale-archive-keyring.gpg"
APT_LIST = "/etc/apt/sources.list.d/tailscale.list"
APT_DISTROS = ("ubuntu", "debian", "raspbian")
WINGET_ID = "Tailscale.Tailscale"
# The cask was renamed; an older Homebrew still knows it by the second name
BREW_CASKS = ("tailscale-app", "tailscale")
# Test seams: which OS's installer to drive (linux, windows, darwin), and where os-release is
PLATFORM = os.environ.get("AI_CONNECT_DEPLOY_PLATFORM") or (
    "windows" if os.name == "nt" else "darwin" if sys.platform == "darwin" else "linux")
OS_RELEASE = Path(os.environ.get("AI_CONNECT_OS_RELEASE") or "/etc/os-release")


def installed() -> str | None:
    try:
        return tsadmin.tailscale_bin()
    except tsadmin.Failure:
        return None


def _have(name: str) -> bool:
    try:
        tool(name)
        return True
    except Failure:
        return False


def as_root(argv: list[str]) -> list[str]:
    """argv as root: unchanged when this already is root, behind sudo otherwise."""
    return argv if IS_ROOT else ["sudo", *argv]


def apt_release() -> tuple[str, str] | None:
    """(distro, codename) when this is a Debian or Ubuntu that apt can serve, else None."""
    try:
        fields = dict(line.split("=", 1) for line in OS_RELEASE.read_text(encoding="utf-8").splitlines()
                      if "=" in line)
    except OSError:
        return None
    distro = fields.get("ID", "").strip().strip('"').lower()
    codename = fields.get("VERSION_CODENAME", "").strip().strip('"').lower()
    if distro in APT_DISTROS and re.fullmatch(r"[a-z]+", codename) and _have("apt-get") and _have("install"):
        return distro, codename
    return None


def _msi_arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x86" if machine in ("x86", "i386", "i686") else "amd64"


def plans(tmp: str) -> list[tuple[str, list[list[str]]]]:
    """The ways to install here, best first: (what it is, the commands in order). tmp holds the downloads."""
    if PLATFORM == "windows":
        msi = str(Path(tmp) / "tailscale-setup.msi")
        winget = ("winget", [["winget", "install", "--id", WINGET_ID, "-e", "--accept-source-agreements",
                              "--accept-package-agreements"]])
        by_msi = ("the Tailscale MSI", [["curl", "-fsSL", f"{PKGS}/tailscale-setup-latest-{_msi_arch()}.msi",
                                         "-o", msi], ["msiexec", "/i", msi, "/passive", "/norestart"]])
        return [winget, by_msi] if _have("winget") else [by_msi]
    if PLATFORM == "darwin":
        return [(f"Homebrew cask {cask}", [["brew", "install", "--cask", cask]]) for cask in BREW_CASKS]
    script = str(Path(tmp) / "tailscale-install.sh")
    by_script = ("Tailscale's install script", [["curl", "-fsSL", INSTALL_SCRIPT_URL, "-o", script], ["sh", script]])
    release = apt_release()
    if release is None:
        return [by_script]
    distro, codename = release
    key, source = str(Path(tmp) / "tailscale-archive-keyring.gpg"), str(Path(tmp) / "tailscale.list")
    by_apt = (f"Tailscale's apt repository for {distro} {codename} (signed-by {APT_KEYRING})", [
        ["curl", "-fsSL", f"{PKGS}/{distro}/{codename}.noarmor.gpg", "-o", key],
        ["curl", "-fsSL", f"{PKGS}/{distro}/{codename}.tailscale-keyring.list", "-o", source],
        as_root(["install", "-m", "0644", key, APT_KEYRING]),
        as_root(["install", "-m", "0644", source, APT_LIST]),
        # Only this one list is refreshed: quicker, and no other repository is touched
        as_root(["apt-get", "update", "-o", f"Dir::Etc::sourcelist={APT_LIST}", "-o", "Dir::Etc::sourceparts=-",
                 "-o", "APT::Get::List-Cleanup=0"]),
        as_root(["apt-get", "install", "-y", "tailscale"]),
    ])
    return [by_apt, by_script]


def shown(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def describe(tmp: str = "<tmp>") -> None:
    """Say everything the install would run, and what will ask for the person."""
    options = plans(tmp)
    for index, (title, commands) in enumerate(options):
        out(f"  {'install with' if index == 0 else 'if that fails, with'} {title}:")
        for argv in commands:
            out(f"    $ {shown(argv)}")
    if PLATFORM == "windows":
        out("  Windows will ask for permission (UAC) to install Tailscale: answer Yes in the prompt.")
    elif PLATFORM == "darwin":
        out("  macOS may ask for your password.")
    elif not IS_ROOT:
        out("  The commands behind sudo need root: sudo may ask for your password.")


def _run_plan(title: str, commands: list[list[str]]) -> int:
    out(f"  installing with {title}")
    for argv in commands:
        out(f"    $ {shown(argv)}")
        code = interactive([tool(argv[0]), *argv[1:]])
        if code != 0:
            out(f"    exit {code}")
            return code
    return 0


def _install() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, title = 1, ""
        for title, commands in plans(tmp):
            code = _run_plan(title, commands)
            if code == 0:
                break
    if code != 0:
        raise Failure(f"installing Tailscale with {title} failed (exit {code})")
    if installed() is None:
        raise Failure("Tailscale was installed but its command line is not on PATH yet; "
                      "open a new terminal and run this again", tsadmin.EXIT_NO_TAILSCALE)


def _missing_tools() -> list[str]:
    """Tools the last-resort way to install needs and that are not on PATH."""
    with tempfile.TemporaryDirectory() as tmp:
        options = plans(tmp)
    usable = [commands for _title, commands in options
              if all(_have(argv[0]) for argv in commands)]
    if usable:
        return []
    return sorted({argv[0] for argv in options[-1][1] if not _have(argv[0])})


def step_install(r: Run, allow_install: bool) -> bool:
    """Make sure the tailscale command exists. False only in a dry run that would install it."""
    found = installed()
    if found:
        r.already(f"Tailscale installed ({found})")
        return True
    missing = _missing_tools()
    if not allow_install or missing:
        why = "--no-install-tailscale was given" if not allow_install else f"{', '.join(missing)} not found on PATH"
        hint = tsadmin.INSTALL_HINT.get({"windows": "win32"}.get(PLATFORM, PLATFORM), tsadmin.INSTALL_HINT["linux"])
        raise Failure(f"tailscale is not installed, and deploy cannot install it ({why}). Install it: {hint}",
                      tsadmin.EXIT_NO_TAILSCALE)
    describe()
    r.change(f"install Tailscale ({PLATFORM})", _install)
    return not r.dry_run


def pinned(accept_dns: bool) -> list[str]:
    """The flags that keep Tailscale out of another VPN's way: no routes from the tailnet, no exit node,
    and DNS only when asked for (MagicDNS rewrites the resolver a VPN client or DNS hook relies on).
    Never --advertise-routes or --advertise-exit-node."""
    return ["--accept-routes=false", "--exit-node=", f"--accept-dns={'true' if accept_dns else 'false'}"]


def up_argv(accept_dns: bool) -> list[str]:
    """`tailscale up` for a login by a person."""
    argv = ["tailscale", "up", *pinned(accept_dns)]
    if PLATFORM == "windows":
        argv.append("--unattended")
    return as_root(argv) if PLATFORM == "linux" else argv


def unpinned(prefs: dict, accept_dns: bool) -> list[str]:
    """What Tailscale's settings take that they should not, in words; empty when they take nothing."""
    wrong = []
    if prefs.get("RouteAll"):
        wrong.append("accepts the tailnet's routes (RouteAll)")
    if prefs.get("ExitNodeID") or prefs.get("ExitNodeIP"):
        wrong.append("sends traffic through an exit node (ExitNode)")
    if bool(prefs.get("CorpDNS")) != accept_dns:
        wrong.append("manages DNS (CorpDNS)" if prefs.get("CorpDNS")
                     else "leaves DNS alone, but --accept-dns was given")
    return wrong


def step_prefs(r: Run, accept_dns: bool = False) -> None:
    """A machine that joined before (by hand, or by an older deploy) gets the same pinned settings."""
    prefs = ts_prefs()
    if prefs is None:
        raise Failure("could not read Tailscale's settings (tailscale debug prefs)")
    wrong = unpinned(prefs, accept_dns)
    if not wrong:
        r.already("Tailscale takes no routes and no exit node" + (", and manages DNS" if accept_dns else " or DNS"))
        return
    argv = as_root(["tailscale", "set", *pinned(accept_dns)]) if PLATFORM == "linux" else \
        ["tailscale", "set", *pinned(accept_dns)]
    out(f"    $ {shown(argv)}")

    def pin() -> None:
        binary = tsadmin.tailscale_bin()
        code = interactive([tool(argv[0]), binary, *argv[2:]] if argv[0] == "sudo" else [binary, *argv[1:]])
        if code != 0:
            raise Failure(f"tailscale set failed (exit {code})")
    r.change("stop Tailscale taking what another VPN needs: it " + "; ".join(wrong), pin)


def step_login(r: Run, accept_dns: bool = False) -> bool:
    """Log this machine in to the tailnet as its user: a browser login. False in a dry run that would."""
    if backend_state() == "Running":
        r.already("this machine is on the tailnet")
        step_prefs(r, accept_dns)
        return True
    argv = up_argv(accept_dns)
    out(f"    $ {shown(argv)}")

    def login() -> None:
        out("  Tailscale needs a login. A browser window opens, or a login URL is printed below:")
        out("  sign in there, and deploy carries on by itself once this machine has joined.")
        binary = tsadmin.tailscale_bin()
        code = interactive([tool(argv[0]), binary, *argv[2:]] if argv[0] == "sudo" else [binary, *argv[1:]])
        if code != 0:
            raise Failure(f"tailscale up failed (exit {code})")
        state = backend_state()
        if state != "Running":
            raise Failure("tailscale up returned, but this machine is not on the tailnet "
                          f"(state: {state or 'unknown'})")
    r.change("log this machine in to the tailnet (browser login)", login)
    return not r.dry_run


def step_tailscale(r: Run, allow_install: bool, accept_dns: bool = False) -> bool:
    """Install, then log in. False only in a dry run that would do either; it still shows the login."""
    if not step_install(r, allow_install):
        out(f"    $ {shown(up_argv(accept_dns))}")
        out("  would: log this machine in to the tailnet (browser login)")
        return False
    return step_login(r, accept_dns)
