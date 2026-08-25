"""Detects the machine crew is running on and repairs `.crew/config.json`.

The problem this solves: `.crew/config.json` is committed, and the same
repository gets opened on Windows, on WSL, and on native Linux. The `platform`
block is a description of the machine, so the moment it is committed it is wrong
for everybody else - `windowsHostIp` in particular is wrong even for the same
machine after a reboot.

## The rule that keeps this safe

**Only derived facts are rewritten. Preferences are never touched.**

    rewritten   os, wsl, wslVersion, distro, shell, repoFilesystem,
                windowsHostIp        - all answers to "what machine is this",
                                       which this module can determine and the
                                       user cannot usefully hand-edit.

    reported    a preference this OS cannot honour - an autoClear.method that
                only exists on the other platform, say. Named in the brief and
                left alone.

    untouched   everything else. tracker, qa, roles, tier, notify, emergency,
                context thresholds, verifyGate. If a human chose it, it stays.

That split is the whole design. A hook that edits config is a hook that can
silently undo a decision, so the set of keys it may write is fixed here, in one
place, and does not include a single thing anybody would argue about.

## Why it writes at all, when the PM is report-only

The PM reports because its subject is *judgement* - whether a role is worth
adding is not a fact. `platform.os` is a fact, it is wrong on the other machine,
and nobody wants to be asked about it once per clone. Reporting "your platform
block says windows and you are on linux" every session, forever, would be worse
than fixing it.

It still says what it changed. A silent config edit would be indefensible.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys

import hook_once

CONFIG_PATH = ".crew/config.json"

# The only keys this module may write. Everything else in the file is somebody's
# decision. Adding to this list is a deliberate act - if a key could ever be
# hand-set to something a human means, it does not belong here.
DERIVED_KEYS = (
    "os", "wsl", "wslVersion", "distro", "shell", "repoFilesystem",
    "windowsHostIp",
)


def _first_line(path):
    try:
        with open(path, "rb") as handle:
            return handle.readline()
    except OSError:
        return b""


def _wsl_facts():
    """WSL specifics, or empty values on anything that is not WSL.

    /proc/sys/kernel/osrelease carries "microsoft" under both WSL 1 and 2; the
    version is the interesting part, because it decides whether `localhost`
    reaches the Windows host (WSL1 shares the stack, WSL2 does not).
    """
    facts = {"wsl": "no", "wslVersion": "", "distro": "", "windowsHostIp": ""}
    release = ""
    try:
        with open("/proc/sys/kernel/osrelease", encoding="utf-8",
                  errors="replace") as handle:
            release = handle.read()
    except OSError:
        return facts
    if not re.search(r"microsoft|wsl", release, re.I):
        return facts

    facts["wsl"] = "yes"
    facts["wslVersion"] = "2" if ("wsl2" in release.lower()
                                  or os.environ.get("WSL_INTEROP")) else "1"
    distro = os.environ.get("WSL_DISTRO_NAME", "")
    if not distro:
        try:
            with open("/etc/os-release", encoding="utf-8",
                      errors="replace") as handle:
                for line in handle:
                    if line.startswith("ID="):
                        distro = line.split("=", 1)[1].strip().strip('"')
                        break
        except OSError:
            pass
    facts["distro"] = distro

    # WSL2 only: the default route's gateway is the Windows host. It changes when
    # the host reboots, which is exactly why committing it is useless and
    # re-deriving it every session is not.
    if facts["wslVersion"] == "2" and shutil.which("ip"):
        try:
            out = subprocess.run(["ip", "route", "show", "default"],
                                 capture_output=True, text=True, check=False,
                                 timeout=5).stdout
            match = re.search(r"default via (\S+)", out)
            if match:
                facts["windowsHostIp"] = match.group(1)
        except (OSError, subprocess.SubprocessError):
            pass
    return facts


def detect(root=None):
    """What machine is this. Never raises."""
    root = root or os.getcwd()
    system = platform.system()
    facts = {"os": "unknown", "shell": "bash", "repoFilesystem": "native",
             "wsl": "no", "wslVersion": "", "distro": "", "windowsHostIp": ""}

    if system == "Linux":
        facts["os"] = "linux"
        facts.update(_wsl_facts())
        # A repo under /mnt/<drive>/ is on the Windows filesystem through a
        # translation layer - roughly an order of magnitude slower for the file
        # operations a test suite is made of. Worth reporting; see platform.md.
        try:
            if re.match(r"^/mnt/[a-z]/", os.path.realpath(root)):
                facts["repoFilesystem"] = "windows-mount"
        except OSError:
            pass
    elif system == "Darwin":
        facts["os"] = "macos"
    elif system == "Windows":
        # Native Windows python. Which shell crew should USE here is the
        # interesting part: PowerShell, unless this is a Git Bash session, and
        # sys.platform cannot tell those apart - MSYSTEM can.
        facts["os"] = "windows-bash" if os.environ.get("MSYSTEM") else "windows"
        facts["shell"] = "bash" if os.environ.get("MSYSTEM") else "powershell"
    elif system.startswith(("MINGW", "MSYS", "CYGWIN")):
        # A POSIX python inside Git Bash / Cygwin reports its own uname here.
        facts["os"] = "windows-bash"
    return facts


def load(root):
    """(config, raw_text). Config is {} for anything unreadable."""
    path = os.path.join(root, CONFIG_PATH)
    try:
        # newline="" so the raw text keeps its actual line endings. Without it
        # universal-newline translation turns CRLF into \n before anything can
        # see it, and apply_changes then rewrites a CRLF config as LF - a
        # whole-file diff on the machine that committed it.
        with open(path, encoding="utf-8-sig", errors="replace",
                  newline="") as handle:
            raw = handle.read()
    except OSError:
        return {}, ""
    try:
        data = json.loads(raw)
    except ValueError:
        # A malformed config is not this module's business to repair. Rewriting
        # it would mean guessing at what the human meant and losing the rest.
        return {}, raw
    return (data if isinstance(data, dict) else {}), raw


def diff(cfg, facts):
    """Which derived keys are wrong, as {key: (was, now)}.

    A key absent from the config counts as changed only when the new value is
    non-empty: an older config with no `platform` block should get one, but a
    native-Linux machine should not have `windowsHostIp: ""` written into it
    just to record that it has no Windows host.
    """
    current = cfg.get("platform")
    current = current if isinstance(current, dict) else {}
    changes = {}
    for key in DERIVED_KEYS:
        new = facts.get(key, "")
        if key not in current:
            if new not in ("", "no"):
                changes[key] = (None, new)
            continue
        was = current.get(key)
        # null and "" both mean "no value". /crew:init writes null; this module
        # writes ""; treating them as different would rewrite the file and
        # report a change on the first run in every repo, for nothing.
        if was is None and new == "":
            continue
        if was != new:
            changes[key] = (was, new)
    return changes


# Methods each platform can actually deliver a keystroke with. auto-clear.sh
# owns the POSIX ones, auto-clear.ps1 owns the Windows one; a config naming the
# other platform's method is a preference this machine cannot honour, so it is
# reported rather than rewritten.
_AUTOCLEAR_METHODS = {
    "linux": ("auto", "none", "tmux", "xdotool", "wtype"),
    "macos": ("auto", "none", "tmux"),
    "windows": ("auto", "none", "windows"),
    "windows-bash": ("auto", "none", "tmux", "windows"),
}


def concerns(cfg, facts):
    """Preferences this OS cannot honour. Reported, never changed."""
    out = []
    context = cfg.get("context")
    context = context if isinstance(context, dict) else {}
    auto = context.get("autoClear")
    auto = auto if isinstance(auto, dict) else {}
    if auto.get("enabled") is True:
        method = str(auto.get("method") or "auto")
        allowed = _AUTOCLEAR_METHODS.get(facts["os"], ("auto", "none"))
        if method not in allowed:
            out.append(
                f"context.autoClear.method is '{method}', which does not exist "
                f"on {facts['os']} - auto-clear will stand down here. "
                f"'auto' picks per platform; this repo is shared, so 'auto' is "
                f"probably what you want"
            )
    if facts["repoFilesystem"] == "windows-mount":
        out.append(
            "this clone is under /mnt/, so every file operation goes through "
            "the Windows translation layer - a suite budgeted at 90s can take "
            "minutes. Moving the clone inside WSL is usually the largest single "
            "speed win available"
        )
    # CRLF in a committed shell script fails as "bad interpreter: ...^M", which
    # reads as a missing interpreter rather than a line-ending problem. Only
    # worth saying where bash is what runs them.
    if facts["os"] in ("linux", "macos"):
        for name in ("_verify/smoke.sh", "_verify/run-all.sh", "scripts/smoke.sh"):
            if _first_line(name).endswith(b"\r\n"):
                out.append(
                    f"{name} has CRLF line endings, so bash fails on it with "
                    "'bad interpreter: ...^M'. Fix with a .gitattributes rule "
                    "(`*.sh text eol=lf`) and `git add --renormalize .`"
                )
                break
    return out


def apply_changes(root, cfg, raw, changes):
    """Write the repaired platform block. Returns True when the file changed.

    Rewrites the whole file from the parsed object, so a hand-added key survives
    only if it is valid JSON - which it has to be for anything else here to have
    worked. Indentation is normalised to two spaces, matching what /crew:init
    writes.
    """
    if not changes:
        return False
    block = cfg.get("platform")
    block = dict(block) if isinstance(block, dict) else {}
    for key, (_, new) in changes.items():
        block[key] = new
    cfg["platform"] = block

    path = os.path.join(root, CONFIG_PATH)
    text = json.dumps(cfg, indent=2) + "\n"
    # Preserve the file's existing line endings. A committed config is normally
    # LF; rewriting it as CRLF on Windows would show up as a whole-file diff on
    # somebody else's machine, which is a rude thing for a hook to do.
    if "\r\n" in raw and "\r\n" not in text:
        text = text.replace("\n", "\r\n")
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    return True


def report(changes, concern_list, facts):
    """The lines to print, or [] for "nothing worth saying"."""
    if not changes and not concern_list:
        return []
    lines = []
    if changes:
        where = facts["os"]
        if facts.get("wsl") == "yes":
            where += f" (WSL{facts.get('wslVersion') or ''})"
        # The os change is the headline: it is the one that means "this config
        # was written on a different kind of machine".
        if "os" in changes:
            was = changes["os"][0] or "unset"
            lines.append(f"## platform - config said {was}, this is {where};"
                         f" updated {len(changes)} field(s) in .crew/config.json")
        else:
            lines.append(f"## platform - {where}; updated "
                         f"{len(changes)} field(s) in .crew/config.json")
        for key in sorted(changes):
            was, new = changes[key]
            lines.append(f"- platform.{key}: {was!r} -> {new!r}")
    for concern in concern_list:
        lines.append(f"- {concern}")
    return lines


def main(argv=None):
    """SessionStart hook. Always exits 0."""
    del argv
    try:
        raw_in = sys.stdin.read()
    except OSError:
        raw_in = ""
    try:
        payload = json.loads(raw_in) if raw_in.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # Take the first candidate that actually HAS a config, rather than the first
    # that is merely set. This is the mixed-environment case that motivates the
    # whole module: a hook reached through Git Bash can be handed a POSIX path
    # (/tmp/x, /mnt/c/...) that native Windows python cannot open, and the
    # reverse holds for a Windows path handed to a WSL interpreter. Preferring
    # the candidate that resolves means the wrong-flavour path is skipped
    # instead of read as "no crew here".
    candidates = [payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR"),
                  os.getcwd()]
    root, cfg, raw = None, {}, ""
    for candidate in candidates:
        if not candidate:
            continue
        cfg, raw = load(candidate)
        if cfg:
            root = candidate
            break
    if not cfg or root is None:
        # No crew here, or an unreadable config. Either way, not ours to touch.
        return 0

    # Keyed on session+source for the same reason pm_brief is: SessionStart
    # fires once per SOURCE EVENT, so a session-id-only claim would let
    # `startup` burn it and every later /clear go unreported.
    session = payload.get("session_id")
    source = payload.get("source") or "unknown"
    if not hook_once.claim(root, "platform-sync",
                           f"{session}-{source}" if session else None):
        return 0

    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    try:
        facts = detect(root)
        changes = diff(cfg, facts)
        if changes:
            if not apply_changes(root, cfg, raw, changes):
                # Read-only checkout, or a permissions problem. Say what would
                # have changed rather than pretending it did.
                lines = report(changes, concerns(cfg, facts), facts)
                if lines:
                    lines[0] += " (could NOT be written - is it read-only?)"
                    print("\n".join(lines))
                return 0
        lines = report(changes, concerns(cfg, facts), facts)
        if lines:
            print("\n".join(lines))
    except Exception:  # pylint: disable=broad-except
        # A raising SessionStart hook breaks every session opened in the repo.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
