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

## Recreating a missing or broken config

This module also heals `.crew/config.json` itself, not just its `platform`
block, for the same reason: a session opened in a crew repo whose config
disappeared or got corrupted should not sit there inert. `heal_config` is the
second thing this hook may write, and it gets the same restrictive guard as
everything else here -- see its docstring for the exact rule.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys

import crew_config
import hook_once

CONFIG_PATH = ".crew/config.json"
CONFIG_BROKEN_SUFFIX = ".broken"

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
        # A malformed config is not THIS function's business to repair -- it
        # only reports what it read. heal_config, below, is what decides
        # whether a config this broken gets recreated.
        return {}, raw
    return (data if isinstance(data, dict) else {}), raw


def heal_config(root):
    """Recreate `.crew/config.json` when it is missing, empty, or unparseable.

    Returns (cfg, message): `cfg` is None and `message` is None when there is
    nothing to heal -- either `.crew/` does not exist, or `config.json` is
    already a readable dict, in which case this function changes nothing and
    the caller falls through to its normal "not ours to touch" path.

    CRITICAL GUARD: a directory with no `.crew/` is not a crew repository and
    must not be colonized. This check runs before anything else here, and
    unlike `diff`/`apply_changes` above -- which only ever touch a `platform`
    block that already exists -- this function can create the whole file, so
    the guard matters even more here than it does there.

    Four cases, matching `_read_config_strict` in `crew_upgrade.py`:

      * Missing, or present but empty/whitespace-only (nothing to lose):
        write `crew_config.default_config()` straight away.
      * Present and parsing to an EMPTY object -- `{}`. It parses, so the
        healthy branch below used to adopt it, and the result was a repo with
        crew silently and permanently switched off: `crew_state.collect`
        derives `isCrew` from the truthiness of the parsed config, so every
        hook stood down and nothing ever said why, while `schema` read as
        current so `/crew:upgrade` answered "already current" forever. An
        empty object holds no hand-edits, which is the whole reason the
        healthy branch exists, so it belongs here with the zero-byte file. No
        backup is taken: there is nothing in it to lose.
      * Present, non-empty, but not a parseable JSON object (something IS
        there and failed to parse -- a real file, not "nothing configured"):
        back it up to `config.json.broken` first, so the original survives
        for hand recovery, then write defaults.
      * Present and a parseable object with ANY key in it, however incomplete
        or unusual: untouched. This function repairs a config that IS NOT
        ONE; it does not validate or merge defaults into one that already
        parses -- that is a different, much larger claim about what "healthy"
        means, and making it here would silently overwrite hand-edits nobody
        asked to have judged. One key is enough to be a config.
    """
    if not os.path.isdir(os.path.join(root, ".crew")):
        return None, None

    path = os.path.join(root, CONFIG_PATH)
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            raw = handle.read()
    except OSError:
        raw = None  # missing

    backed_up = False
    was_empty = False
    if raw is not None and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and parsed:
            return None, None  # healthy; not this function's problem
        if isinstance(parsed, dict):
            # `{}` -- it parses, it carries nothing, and it reads downstream
            # as "not a crew repo". Rewritten like a zero-byte file, and
            # deliberately NOT backed up: a backup of `{}` is a file whose
            # only content is the absence of content.
            was_empty = True
        else:
            # Present, non-empty, and not a usable config -- back it up.
            backup_path = path + CONFIG_BROKEN_SUFFIX
            backed_up = True
            if not os.path.exists(backup_path):
                # A previous broken session already took one; do not
                # overwrite it with a second failure -- the first is still
                # the human's best chance at recovery. Same rule as
                # crew_upgrade.backup_config.
                try:
                    shutil.copy2(path, backup_path)
                except OSError:
                    # Could not back it up (read-only checkout?). Do not
                    # destroy the original by writing over it blind --
                    # report and stop.
                    return None, (
                        f"## config - {CONFIG_PATH} is malformed and could "
                        f"NOT be backed up before rewriting - is the "
                        f"checkout read-only? Left it untouched"
                    )

    cfg = crew_config.default_config()
    text = json.dumps(cfg, indent=2) + "\n"
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
        return None, (
            f"## config - {CONFIG_PATH} is missing or malformed, and "
            f"defaults could NOT be written - is the checkout read-only?"
        )

    if backed_up:
        message = (
            f"## config - {CONFIG_PATH} was malformed; backed it up to "
            f"{CONFIG_PATH}{CONFIG_BROKEN_SUFFIX} and wrote defaults - "
            f"tracker, roles, and every other choice are back to defaults; "
            f"run /crew:init to re-record them"
        )
    elif was_empty:
        message = (
            f"## config - {CONFIG_PATH} was an empty object, which reads "
            f"everywhere downstream as `not a crew repo`; wrote defaults - "
            f"tracker, roles, and every other choice are back to defaults; "
            f"run /crew:init to re-record them"
        )
    else:
        message = (
            f"## config - {CONFIG_PATH} was missing; wrote defaults - "
            f"tracker, roles, and every other choice are back to defaults; "
            f"run /crew:init to re-record them"
        )
    return cfg, message


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

    if root is None:
        # No candidate has a *readable* config -- but one of them may still
        # be a crew repo whose config is missing or broken, which is exactly
        # what heal_config exists to fix. Resolving `root` from bare .crew/
        # presence (rather than calling heal_config here) means the actual
        # write stays gated behind the once-per-session claim below, same as
        # every other write this module makes -- two processes racing (the
        # .sh and .ps1 flavours both fire) must not both recreate the file.
        for candidate in candidates:
            if candidate and os.path.isdir(os.path.join(candidate, ".crew")):
                root = candidate
                break

    if root is None:
        # No crew here at all. Not ours to touch.
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

    heal_message = None
    if not cfg:
        try:
            healed, heal_message = heal_config(root)
        except Exception:  # pylint: disable=broad-except
            # heal_config must not be able to break a session either.
            healed, heal_message = None, None
        if healed is not None:
            cfg = healed
            raw = json.dumps(healed, indent=2) + "\n"

    if not cfg:
        # Unreadable and could not be healed (or nothing to heal at all --
        # heal_config's own guard covers the "not actually a crew repo" case
        # too, since root here may have resolved from bare .crew/ presence).
        if heal_message:
            print(heal_message)
        return 0

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
                if heal_message:
                    lines = [heal_message] + lines
                if lines:
                    print("\n".join(lines))
                return 0
        lines = report(changes, concerns(cfg, facts), facts)
        if heal_message:
            lines = [heal_message] + lines
        if lines:
            print("\n".join(lines))
    except Exception:  # pylint: disable=broad-except
        # A raising SessionStart hook breaks every session opened in the repo.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
