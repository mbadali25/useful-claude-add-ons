"""Whether the firewall that holds the Bridge rule filters anything.

A rule in a firewall that is switched off is stored and does nothing: `ufw allow`
succeeds on an inactive ufw, and so does `netsh ... add rule` with the profile off.
deploy.py asks here before it reports a rule, so "done" never stands for a rule
that is not enforced. Three answers, never two: ACTIVE, INACTIVE, and UNKNOWN when
the firewall could not be asked or its answer could not be read.

Nothing here turns a firewall on. Enabling one applies its default policy to every
port of the machine (an SSH session included), which is the owner's decision.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ACTIVE, INACTIVE, UNKNOWN = "active", "inactive", "unknown"
# What the last firewall step found, for a caller that sums a run up (setup_core.py):
# {"kind", "state", "port", "subnet"}; empty until a firewall step has run
REPORT: dict = {}
# What ufw itself reads at boot. Readable without root, and not translated. The variable is a test seam
UFW_CONF = Path(os.environ.get("AI_CONNECT_UFW_CONF") or "/etc/ufw/ufw.conf")
# One line per profile, the state as a number: netsh prints it as a word in the display language
PROFILE_QUERY = ("$ErrorActionPreference = 'Stop'; "
                 "Get-NetFirewallProfile | ForEach-Object { 'profile:' + $_.Name + '=' + [int]$_.Enabled }")
PROFILE_RE = re.compile(r"^profile:(\w+)=(\d+)\s*$")


def read_ufw_conf() -> str | None:
    try:
        return UFW_CONF.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def ufw_state(status_text: str | None, conf_text: str | None) -> str:
    """From `ufw status` when it answers in English, else from ENABLED= in ufw.conf (ufw's words are
    translated, the file is not). Neither readable: UNKNOWN, which is not INACTIVE."""
    first = next((line.strip().lower() for line in (status_text or "").splitlines() if line.strip()), "")
    if first == "status: inactive":
        return INACTIVE
    if first.startswith("status: active"):
        return ACTIVE
    found = re.search(r"^\s*ENABLED\s*=\s*(\w+)\s*$", conf_text or "", re.MULTILINE)
    if found is None:
        return UNKNOWN
    return ACTIVE if found.group(1).lower() == "yes" else INACTIVE if found.group(1).lower() == "no" else UNKNOWN


def ufw_added(text: str, comment: str) -> list[tuple[str, str]]:
    """(port, source) of the stored inbound TCP allow rules that carry comment, from `ufw show added`:
    the rules ufw holds whether or not it is active. Its rule lines are ufw's own command syntax."""
    rule = re.compile(r"^ufw allow from (\S+) to any port (\d+) proto tcp comment '?" + re.escape(comment) + r"'?\s*$")
    return [(m.group(2), m.group(1)) for line in text.splitlines() if (m := rule.match(line.strip()))]


def windows_profiles(text: str) -> dict[str, bool]:
    """{profile name: on} from PROFILE_QUERY's output; a profile whose state is neither 0 nor 1 is left out."""
    states = {}
    for line in text.splitlines():
        found = PROFILE_RE.match(line.strip())
        if found and found.group(2) in ("0", "1"):
            states[found.group(1).lower()] = found.group(2) == "1"
    return states


def windows_state(text: str | None, profile: str = "private") -> str:
    """The state of the one profile the Bridge rule is in."""
    states = windows_profiles(text or "")
    if profile not in states:
        return UNKNOWN
    return ACTIVE if states[profile] else INACTIVE


def note(kind: str, state: str, subnet: str, port: int) -> str | None:
    """What to say after the rule step when the rule is not known to be enforced; None when it is."""
    name = {"ufw": "ufw", "firewall-cmd": "firewalld", "netsh": "Windows Firewall (Private profile)"}[kind]
    how = {"ufw": "sudo ufw enable   (first allow what must stay reachable, e.g. sudo ufw allow OpenSSH)",
           "firewall-cmd": "sudo systemctl enable --now firewalld, then run this again to add the rule",
           "netsh": "Set-NetFirewallProfile -Profile Private -Enabled True   (elevated PowerShell)"}[kind]
    if state == ACTIVE:
        return None
    if state == INACTIVE:
        return (f"  NOT ENFORCED: {name} is off, so the rule for port {port} from {subnet} filters nothing. "
                f"Nothing here turns a firewall on: that changes every port of this machine. To enforce it: {how}")
    return (f"  NOT VERIFIED: could not tell whether {name} is on, so the rule for port {port} from {subnet} may "
            f"filter nothing. Check it yourself; to turn it on: {how}")


def remember(kind: str | None, state: str | None, subnet: str, port: int) -> None:
    REPORT.clear()
    REPORT.update(kind=kind, state=state, subnet=subnet, port=port)
