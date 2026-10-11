"""The Tailscale step of `deploy bridge`, `deploy peer` and `deploy tailnet-setup`:
install Tailscale when it is missing, and log this machine in when asked to.

Linux runs Tailscale's own install script, Windows winget (or the MSI when winget
is missing), macOS Homebrew. Each of them may stop for a person: sudo's password,
a UAC prompt, a browser login. deploy says so first, hands the terminal to the
tool, and carries on when it returns.
"""
from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path

from deploy_core import Failure, Run, backend_state, interactive, must, out, run, tool, tsadmin  # pylint: disable=import-error

INSTALL_SCRIPT_URL = "https://tailscale.com/install.sh"
WINGET_ID = "Tailscale.Tailscale"
MSI_URL = "https://pkgs.tailscale.com/stable/tailscale-setup-latest-{arch}.msi"
# The cask was renamed; an older Homebrew still knows it by the second name
BREW_CASKS = ("tailscale-app", "tailscale")
# Test seam: which OS's installer to drive (linux, windows, darwin)
PLATFORM = os.environ.get("AI_CONNECT_DEPLOY_PLATFORM") or (
    "windows" if os.name == "nt" else "darwin" if sys.platform == "darwin" else "linux")


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


def _install_linux() -> None:
    curl = tool("curl")
    out("  Tailscale's install script needs root: sudo may ask for your password below.")
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "tailscale-install.sh"
        must(run([curl, "-fsSL", INSTALL_SCRIPT_URL, "-o", str(script)], timeout=120), "download of install.sh")
        code = interactive([tool("sh"), str(script)])
    if code != 0:
        raise Failure(f"Tailscale's install script failed (exit {code})")


def _msi_arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x86" if machine in ("x86", "i386", "i686") else "amd64"


def _install_windows() -> None:
    out("  Windows will ask for permission (UAC) to install Tailscale: answer Yes in the prompt.")
    if _have("winget"):
        code = interactive([tool("winget"), "install", "--id", WINGET_ID, "-e", "--accept-source-agreements",
                            "--accept-package-agreements"])
        if code != 0:
            raise Failure(f"winget install {WINGET_ID} failed (exit {code})")
        return
    out("  winget not found, using the MSI instead.")
    with tempfile.TemporaryDirectory() as tmp:
        msi = Path(tmp) / "tailscale-setup.msi"
        must(run([tool("curl"), "-fsSL", MSI_URL.format(arch=_msi_arch()), "-o", str(msi)], timeout=300),
             "download of the Tailscale MSI")
        code = interactive([tool("msiexec"), "/i", str(msi), "/passive", "/norestart"])
    if code != 0:
        raise Failure(f"the Tailscale MSI failed (exit {code})")


def _install_darwin() -> None:
    brew = tool("brew")
    out("  Homebrew installs the Tailscale app; macOS may ask for your password.")
    code = 1
    for cask in BREW_CASKS:
        code = interactive([brew, "install", "--cask", cask])
        if code == 0:
            return
    raise Failure(f"brew install --cask {BREW_CASKS[0]} failed (exit {code})")


INSTALLERS = {"linux": _install_linux, "windows": _install_windows, "darwin": _install_darwin}
NEEDS = {"linux": ("curl", "sh"), "windows": (), "darwin": ("brew",)}


def _install() -> None:
    INSTALLERS[PLATFORM]()
    if installed() is None:
        raise Failure("Tailscale was installed but its command line is not on PATH yet; "
                      "open a new terminal and run this again", tsadmin.EXIT_NO_TAILSCALE)


def step_install(r: Run, allow_install: bool) -> bool:
    """Make sure the tailscale command exists. False only in a dry run that would install it."""
    found = installed()
    if found:
        r.already(f"Tailscale installed ({found})")
        return True
    missing = [name for name in NEEDS[PLATFORM] if not _have(name)]
    if PLATFORM == "windows" and not _have("winget") and not (_have("curl") and _have("msiexec")):
        missing = ["winget"]
    if not allow_install or missing:
        why = "--no-install-tailscale was given" if not allow_install else f"{', '.join(missing)} not found on PATH"
        hint = tsadmin.INSTALL_HINT.get({"windows": "win32"}.get(PLATFORM, PLATFORM), tsadmin.INSTALL_HINT["linux"])
        raise Failure(f"tailscale is not installed, and deploy cannot install it ({why}). Install it: {hint}",
                      tsadmin.EXIT_NO_TAILSCALE)
    r.change(f"install Tailscale ({PLATFORM})", _install)
    return not r.dry_run


def step_login(r: Run) -> bool:
    """Log this machine in to the tailnet as its user: a browser login. False in a dry run that would."""
    if backend_state() == "Running":
        r.already("this machine is on the tailnet")
        return True

    def login() -> None:
        out("  Tailscale needs a login. A browser window opens, or a login URL is printed below:")
        out("  sign in there, and deploy carries on by itself once this machine has joined.")
        up = [tsadmin.tailscale_bin(), "up"] + (["--unattended"] if PLATFORM == "windows" else [])
        code = interactive(up if PLATFORM != "linux" or getattr(os, "geteuid", lambda: 0)() == 0
                           else [tool("sudo"), *up])
        if code != 0:
            raise Failure(f"tailscale up failed (exit {code})")
        state = backend_state()
        if state != "Running":
            raise Failure("tailscale up returned, but this machine is not on the tailnet "
                          f"(state: {state or 'unknown'})")
    r.change("log this machine in to the tailnet (browser login)", login)
    return not r.dry_run
