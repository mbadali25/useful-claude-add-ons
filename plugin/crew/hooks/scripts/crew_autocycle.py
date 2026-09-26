"""The decisions behind auto wrap-up -> auto-clear -> auto-resume, for the bash
flavour. `auto-clear.ps1` carries the same rules in PowerShell, because the
native-Windows flavour must not need a python to refuse; the suite runs both
against the same fixtures so they cannot drift.

Three rules, each one a bug that shipped:

1. **Markers are keyed on the payload's `session_id`.** The wrap-up request
   used to be one `.crew/.handoff-requested` per repository, so two terminals
   in one repo shared it: the first to cross the threshold silenced the
   other, and either one's SessionStart re-armed both.

2. **No clear without a verified handoff AND a trustworthy reading.** The
   wrap-up marker records the reading that caused it. An estimate from
   transcript size, a model whose window is a guess, a reading taken before a
   compaction, or a marker that is not this file's JSON at all (the zero-byte
   marker behind the Windows low-context `/clear`) is unknown, and unknown
   means no clear. The handoff must be this session's: written after the
   request, non-trivial, and not PreCompact's automatic skeleton.

3. **Never type into a window that is not uniquely identified.** The target is
   found by process id first (the window owned by the nearest ancestor of this
   hook), and a configured `windowTitle` is only a fallback that refuses on
   zero or several matches. `wtype` identifies nothing and is refused outright.

4. **The target is this SESSION's, not merely an ancestor's (T-0016).** A
   `claude -p` started from another session's Bash tool inherits `$TMUX_PANE`
   and has that session's pane shell among its ancestors, so rule 3 alone
   handed it the PARENT's pane (measured on Claude Code 2.1.282). So a
   keystroke method first binds the payload's `session_id` to the Claude Code
   process that owns it, through Claude Code's session record
   `~/.claude/sessions/<pid>.json` (`session_owner`): alive, the recorded
   `procStart`, an ancestor of this hook, `kind: interactive`, an entrypoint
   that is not an SDK/`-p` one, and a controlling terminal. tmux then needs
   that process's tty to BE the pane's; xdotool walks windows from it, and
   refuses a window whose owning process also sits above another live
   session -- the parent a child with its own pty was started from, or a
   sibling tab of one terminal window (`_shared_window`). The records are
   read from `$CLAUDE_CONFIG_DIR/sessions` too when that is set, and none
   found there is "could not tell", not headless. A
   session with no terminal of its own (no record, a headless kind or
   entrypoint, no controlling tty) is never typed into: `auto` tells it how a
   parent restarts it (`notify`), an explicit method refuses. Across an ssh or
   WSL boundary with no tmux on this side, `auto` is `notify` and xdotool is
   refused -- the X display is not on this host. The record is an
   undocumented Claude Code internal: if a release drops or renames it, every
   keystroke refuses, which is the direction "could not tell" must fail in.

Two methods never type anything at all. **`notify`** prints a `systemMessage`
saying the handoff is written and verified and it is safe to run the
configured command yourself -- never that anything was cleared or compacted,
because nothing was. It needs no window and is never refused for lack of one.
`auto` resolves to it on native Windows with no tmux pane, which is an OWNER
DECISION, not a capability gap: `sendkeys` (auto-clear.ps1's
`System.Windows.Forms.SendKeys`) still exists and still works, but `auto` may
never choose it -- typing into a window it found itself is a risk `auto`
does not get to accept on your behalf. Request `sendkeys` by name to opt in.
**`sendkeys` is refused here outright**, whatever `cfg["method"]` says: that
mechanism is `auto-clear.ps1`'s, and this module carries no window-typing code
of its own beyond `tmux`/`xdotool`, which are POSIX-only in the other
direction.

Also: `enabled` is a MACHINE opt-in. It is read from the machine-global
`~/.claude/crew/config.json`; a repo may switch it off but cannot switch it
on, because the thing it drives is this machine's keyboard.

And `onlyRepos` / `onlySessions` NARROW that opt-in, machine file only. Absent
(or null) changes nothing; present, the clear is armed only in a listed repo
and/or a listed session, and an empty list arms nothing. A repo's own copy of
either key is never read -- a narrowing a repo could write for itself would be
a widening. Without them, `enabled: true` arms every Claude session on the
host, which is why a scratch repo could not be tested safely beside live ones.

CLI (used by auto-clear.sh): `plan --root R --session S [--force]` prints one
value per line -- status (off|refuse|send), reason, method, target, label,
command, delay, key. Never raises; an internal error is a refusal.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

MARKER_PREFIX = ".handoff-requested-"
SENT_PREFIX = ".autoclear-sent-"
# handoff-write.sh's PreCompact skeleton. It exists so a compaction never
# leaves NO note, and it says outright that it knows no next action -- so it
# is not a handoff anybody wrote, and clearing on it loses the session.
SKELETON_MARK = "UNKNOWN - this skeleton was written automatically"
WINDOW_STUB_ENV = "CREW_AUTOCLEAR_WINDOW_STUB"
# `{pid: tty}` JSON replacing the controlling-tty read, the WINDOW_STUB
# pattern: a CI pytest process often has no tty at all, so "owner tty ==
# pane tty" cannot be built from a real one. Whoever can set it already
# controls this hook.
TTY_STUB_ENV = "CREW_AUTOCLEAR_TTY_STUB"
# Where WSL announces itself when neither WSL_DISTRO_NAME nor WSL_INTEROP
# survived (sudo scrubs both). Overridable so a suite run inside WSL can
# still exercise the non-WSL cases; it can only ADD a refusal.
WSL_INTEROP_ENV = "CREW_AUTOCLEAR_WSL_INTEROP_PATH"
_WSL_INTEROP_PATH = "/proc/sys/fs/binfmt_misc/WSLInterop"
# How long `session_owner` waits for a record naming the session. Fixed, no
# config key. The spike measured 0 ms after /clear (10 of 10 runs, the
# record already rewritten when SessionStart began) and 74 ms at a `-p`
# startup, so 2 s is a wide margin, not a guess at a slow machine.
_OWNER_WAIT_SECONDS = 2.0
_OWNER_POLL_SECONDS = 0.1
# Linux Unix98 pty majors: /dev/pts/N lives on majors 136-143.
_PTS_MAJOR_FIRST, _PTS_MAJOR_LAST = 136, 143
_DEFAULTS = {"method": "auto", "windowTitle": "", "command": "/clear",
             "delaySeconds": 3, "minHandoffLines": 5}
# Every key `settings()` actually reads from context.autoClear, in either
# layer -- `unsafeFocus` is CONFIG.md-documented but "no longer read"
# (deliberately still recognised, so it does not trip the unknown-key
# warning below). A key not in this set is either a typo (`delay` for
# `delaySeconds`) or leftover from an older schema; either way it silently
# does nothing today, which is exactly the "unknown collapsing into the
# safe-looking default" shape this file's warnings exist to surface.
_RECOGNIZED_AUTOCLEAR_KEYS = frozenset(_DEFAULTS) | {
    "enabled", "onlyRepos", "onlySessions", "unsafeFocus"}
_ANCESTOR_LIMIT = 16


def session_key(session_id):
    """The filename-safe form of a session id. Must match context-watch.sh
    (`${id//[^A-Za-z0-9_-]/_}`, first 100 chars) and the .ps1 twins."""
    key = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id or ""))[:100]
    return key or "nosession"


def global_config_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "crew", "config.json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _block(cfg, *keys):
    node = cfg
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else {}


def _num(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _num_checked(value, default):
    """Like `_num`, but also reports whether the fallback fired because
    `value` was actually SET and unusable, as opposed to simply absent --
    absent is the ordinary, silent default path (nobody configured it);
    present-and-unusable is the misconfiguration `settings()` warns about."""
    if value is None:
        return default, True
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default, False
    try:
        return int(value), True
    except (TypeError, ValueError):
        return default, False


def settings(root, global_path=None):
    """The autoClear settings in force for `root` on this machine.

    `out["_warnings"]` carries a human-readable line for every
    context.autoClear key that this resolver read but could not act on as
    configured -- an unrecognised key (most often a typo, e.g. `delay` for
    `delaySeconds`) or a `delaySeconds` that was actually set but is not a
    usable number. Both would otherwise silently fall through to the
    compiled default with no record that anything was wrong -- an unknown
    collapsing into the safe-looking value, indistinguishable from an
    operator who genuinely wanted the default."""
    repo_cfg = _load(os.path.join(root, ".crew", "config.json"))
    repo = _block(repo_cfg, "context", "autoClear")
    machine = _block(_load(global_path or global_config_path()), "context", "autoClear")
    warnings = []
    for label, block in (("repo", repo), ("machine", machine)):
        for key in block:
            if key not in _RECOGNIZED_AUTOCLEAR_KEYS:
                warnings.append(
                    f"context.autoClear.{key} in the {label} layer is not a "
                    "recognised key and is ignored")
    out = {}
    raw = {}
    for key, default in _DEFAULTS.items():
        value = repo.get(key)
        if value is None:
            value = machine.get(key)
        raw[key] = value
        out[key] = default if value is None else value
    out["delaySeconds"], delay_ok = _num_checked(raw["delaySeconds"], _DEFAULTS["delaySeconds"])
    if not delay_ok:
        warnings.append(
            f"context.autoClear.delaySeconds is set to {raw['delaySeconds']!r}, not a "
            f"usable number - using the default {out['delaySeconds']}")
    out["minHandoffLines"] = _num(out["minHandoffLines"], _DEFAULTS["minHandoffLines"])
    for key in ("method", "command", "windowTitle"):
        text = str(out[key] or "").splitlines()
        out[key] = text[0] if text else _DEFAULTS[key]
    out["enabled"] = machine.get("enabled") is True and repo.get("enabled") is not False
    # Machine only, and deliberately not in the repo-then-machine loop above.
    out["onlyRepos"] = machine.get("onlyRepos")
    out["onlySessions"] = machine.get("onlySessions")
    handoff = _block(repo_cfg, "context").get("handoffPath")
    out["handoffPath"] = handoff if isinstance(handoff, str) and handoff else ".work/HANDOFF.md"
    out["_warnings"] = warnings
    return out


def log_autoclear(root, message):
    """One line to .crew/.autoclear.log, in the same tab-separated,
    UTC-timestamped shape auto-clear.sh's own `note()` (and its .ps1 twin's
    `Write-CrewAutoClearNote`) already write -- so a config-validation
    warning from here interleaves sensibly with every refusal/sent line
    those two log. Best-effort: a write failure here must never abort a
    plan the caller still needs, the same contract `note()` has via its own
    `2>/dev/null`."""
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # errors="backslashreplace", not the default strict encoder:
        # `message` can carry a lone UTF-16 surrogate (a `\ud800` escape from
        # an unknown JSON key, decoded by `json.loads` without complaint but
        # unencodable as UTF-8), and a strict `handle.write()` then raises
        # `UnicodeEncodeError` -- a `ValueError`, not an `OSError`, so the
        # `except` below never caught it and this "best-effort" logger
        # aborted the planning call it was meant never to interrupt.
        # `backslashreplace` keeps the line readable (`\ud800` in the log)
        # instead of losing the character; the broadened `except` is the
        # other half of the same fix.
        with open(os.path.join(root, ".crew", ".autoclear.log"), "a",
                  encoding="utf-8", errors="backslashreplace") as handle:
            handle.write(f"{stamp}\t{message}\n")
    except (OSError, UnicodeError):
        pass


_WIN_DRIVE_SLASH = re.compile(r"^/([A-Za-z])(?=/|$)")
# Split by platform on purpose: a bare leading "/" is absolute on both, but
# "[a-z]:/" is a drive letter, which is only a path on Windows. A single
# alternation checked with the same pattern on POSIX let a RELATIVE entry
# like "c:/.." read as absolute there too, and a relative entry is supposed
# to be refused outright (see the docstring below) rather than quietly
# treated as rooted.
_ABSOLUTE_SLASH = re.compile(r"^/")
_ABSOLUTE_DRIVE = re.compile(r"^[a-z]:/")


def normalise_repo_path(path, windows=None):
    """The form `onlyRepos` entries and the repo root are compared in, or ""
    for anything that is not an absolute path.

    On Windows, backslashes become slashes; on POSIX a backslash is a legal
    filename character and is left alone, or two distinct paths collapse into
    one and an unlisted repo passes `onlyRepos`. Trailing separators go,
    symlinks are resolved (`realpath`), and on Windows the Git Bash `/c/x`
    shape becomes `c:/x` and the whole path is case-mapped per character
    (`.lower()`, not `.casefold()` -- casefold's Unicode special-casing
    merges distinct strings, e.g. "straße" and "strasse", which Windows'
    own case-insensitive comparison does not). A RELATIVE entry is refused
    rather than resolved: it would resolve against the repo being asked
    about, so `.` would match every repository on the machine. `windows`
    lets a Linux test drive the Windows rules; realpath runs only on the
    platform it describes.

    Leading/trailing whitespace in `path` is significant and is NOT
    stripped before comparison -- it is a legal POSIX filename character,
    and trimming it collapsed two distinct entries (a repo path and that
    same path plus a trailing space) into one, letting a listed repo whose
    name happens to end in a space authorise an unlisted, space-free repo
    of the same name. Only whitespace-ONLY input is treated as absent."""
    windows = os.name == "nt" if windows is None else windows
    if not isinstance(path, str) or not path.strip():
        return ""
    text = os.path.expanduser(path)
    if windows:
        text = text.replace("\\", "/")
        text = _WIN_DRIVE_SLASH.sub(lambda m: m.group(1) + ":", text, count=1)
        if re.fullmatch(r"[A-Za-z]:", text):
            text += "/"
    candidate = text.lower() if windows else text
    if not (_ABSOLUTE_SLASH.match(candidate) or (windows and _ABSOLUTE_DRIVE.match(candidate))):
        return ""
    if windows == (os.name == "nt"):
        text = os.path.realpath(text)
        if windows:
            text = text.replace("\\", "/")
    text = text.rstrip("/") or "/"
    if windows:
        if re.fullmatch(r"[A-Za-z]:", text):
            text += "/"
        text = text.lower()
    return text


def _scope(value):
    """None when the key does not narrow (absent or null); otherwise the list
    of string entries. A value that is present but not a list narrows to
    NOTHING -- a malformed narrowing must never read as no narrowing."""
    if value is None:
        return None
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def in_scope(cfg, root, session_id, windows=None):
    """Is this repo AND this session inside the machine's narrowing?

    Each key that is present must match; both present means both must. This
    can only ever turn an armed machine off, never an unarmed one on."""
    repos = _scope(cfg.get("onlyRepos"))
    if repos is not None:
        here = normalise_repo_path(root, windows)
        listed = {normalise_repo_path(r, windows) for r in repos} - {""}
        if not here or here not in listed:
            return False
    sessions = _scope(cfg.get("onlySessions"))
    if sessions is not None and (not session_id or session_id not in sessions):
        return False
    return True


def read_marker(root, key):
    """(marker, reason). marker is None when no wrap-up was requested."""
    path = os.path.join(root, ".crew", MARKER_PREFIX + key)
    if not os.path.isfile(path):
        return None, "no wrap-up was requested in this session"
    data = _load(path)
    if not data:
        return {}, ("the wrap-up marker is empty or not JSON, so the context reading "
                    "behind it is unknown")
    return data, ""


def _contained(root, rel):
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, rel))
    if os.path.commonpath([base, path]) != base:
        return None
    return path


def verify_handoff(root, session_id, cfg):
    """(ok, reason): may this session be cleared on the strength of its handoff?"""
    if not session_id:
        return False, "no session id, so no way to tell whose handoff this is"
    marker, why = read_marker(root, session_key(session_id))
    if marker is None or not marker:
        return False, why
    if marker.get("session_id") != session_id:
        return False, "the wrap-up marker records a different session"
    if marker.get("trusted") is not True:
        return False, ("the context reading behind the wrap-up was not trustworthy ("
                       f"{marker.get('why') or 'unknown'}) - a low or unknown reading never clears")
    requested = marker.get("requested_at")
    if isinstance(requested, bool) or not isinstance(requested, (int, float)):
        return False, "the wrap-up marker has no request time"
    path = _contained(root, cfg["handoffPath"])
    if path is None:
        return False, "handoffPath points outside the repository"
    if not os.path.isfile(path):
        return False, f"{cfg['handoffPath']} has not been written"
    if os.path.getmtime(path) <= requested:
        return False, f"{cfg['handoffPath']} predates this session's wrap-up request"
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return False, f"{cfg['handoffPath']} is unreadable"
    if SKELETON_MARK in text:
        return False, f"{cfg['handoffPath']} is the automatic PreCompact skeleton, not a handoff"
    lines = sum(1 for line in text.splitlines() if line.strip())
    if lines < cfg["minHandoffLines"]:
        return False, (f"{cfg['handoffPath']} has {lines} non-blank lines, "
                       f"minHandoffLines is {cfg['minHandoffLines']}")
    return True, ""


def _ppid(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
            return int(handle.read().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        pass
    try:
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=5, check=False).stdout
        return int(out.strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def ancestors(pid=None):
    """This process and its ancestors, nearest first."""
    out, pid = [], pid or os.getpid()
    while pid and pid > 1 and pid not in out and len(out) < _ANCESTOR_LIMIT:
        out.append(pid)
        pid = _ppid(pid)
    return out


# --- the session binding (T-0016) -------------------------------------------
#
# Rule 4 of the module docstring. Everything here answers ONE question -- is
# there a live, interactive Claude Code process that owns this session, sits
# above this hook, and has a terminal of its own -- and "could not tell" is
# never a yes. `headless` separates "this session has no terminal of its own"
# (no record, a headless kind or entrypoint, no controlling tty) from "wrong
# process" (dead, reused pid, not an ancestor, two records): only the first
# may become a `notify`, the second always refuses.

def _proc_start(pid):
    """`/proc/<pid>/stat` field 22 (starttime) as a string, or None."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
            return handle.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _alive(pid):
    # Never os.kill on Windows: there, any signal but the two console events
    # is TerminateProcess. The ancestor check that follows proves liveness on
    # its own; this only gives a dead owner its own reason.
    if os.name == "nt":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _tty_from_nr(tty_nr):
    """`/proc/<pid>/stat`'s tty_nr as tmux prints `#{pane_tty}`: "" for no
    controlling tty, `/dev/pts/N` for a Unix98 pty, None for anything else
    (left to `ps`)."""
    if tty_nr == 0:
        return ""
    major = (tty_nr >> 8) & 0xFFF
    minor = (tty_nr & 0xFF) | ((tty_nr >> 12) & 0xFFF00)
    if _PTS_MAJOR_FIRST <= major <= _PTS_MAJOR_LAST:
        return f"/dev/pts/{(major - _PTS_MAJOR_FIRST) * 256 + minor}"
    return None


def _tty_of(pid, env=None):
    """The controlling terminal of `pid`: "" when it has none, a device path
    when it has one, None when it could not be read. CREW_AUTOCLEAR_TTY_STUB
    replaces the read (a pid missing from the stub is None)."""
    env = os.environ if env is None else env
    stub = env.get(TTY_STUB_ENV)
    if stub:
        try:
            with open(stub, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        value = data.get(str(pid)) if isinstance(data, dict) else None
        if not isinstance(value, str):
            return None
        return "" if value in ("", "?") else value
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
            tty = _tty_from_nr(int(handle.read().rsplit(")", 1)[1].split()[4]))
        if tty is not None:
            return tty
    except (OSError, IndexError, ValueError):
        pass
    try:
        out = subprocess.run(["ps", "-o", "tty=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    if out in ("?", "??", "-"):
        return ""
    return out if out.startswith("/") else "/dev/" + out


def restart_recipe():
    """The one thing a parent can do for a headless child: restart it."""
    resume = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crew_resume.py")
    steps = (f"python3 {resume} decide --source clear --json, then record, "
             'then claude -p "<prompt>"')
    if os.path.isfile(resume):
        return f"a parent that started this session restarts it: {steps}"
    return ("a parent that started this session restarts it with a fresh "
            'claude -p "<prompt>" that points at the handoff (once crew_resume.py '
            f"ships: {steps})")


def _headless(reason):
    return {"ok": False, "headless": True,
            "reason": f"{reason} - it has no terminal of its own"}


def _wrong(reason):
    return {"ok": False, "headless": False, "reason": reason}


def _session_folders(env):
    """Every folder Claude Code's session records may be in: `~/.claude/
    sessions`, and `$CLAUDE_CONFIG_DIR/sessions` first when that variable
    relocates Claude Code's config. Where a relocated config keeps its
    records is unmeasured, so both are read."""
    home = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    relocated = (env.get("CLAUDE_CONFIG_DIR") or "").strip()
    if not relocated:
        return [home]
    moved = os.path.join(os.path.expanduser(relocated), "sessions")
    same = os.path.normcase(os.path.abspath(moved)) == os.path.normcase(os.path.abspath(home))
    return [home] if same else [moved, home]


def _session_records(session_id, env):
    """(matches, others, unreadable_name) over every `_session_folders`
    `*.json`. `others` is [(name, record)] for the records naming any
    OTHER session."""
    matches, others = [], []
    for folder in _session_folders(env):
        try:
            names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
        except OSError:
            continue
        for name in names:
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    record = json.load(handle)
            except (OSError, ValueError):
                return [], [], name
            if not isinstance(record, dict):
                return [], [], name
            if record.get("sessionId") == session_id:
                matches.append(record)
            else:
                others.append((name, record))
    return matches, others, None


def session_owner(session_id, env=None):
    """{"ok", "headless", "reason", "pid", "tty"}: the Claude Code process
    that owns `session_id`, proven through its session record."""
    env = os.environ if env is None else env
    if not session_id:
        return _wrong("no session id, so no session record can be matched to this hook")
    deadline = time.monotonic() + _OWNER_WAIT_SECONDS
    while True:
        matches, _others, bad = _session_records(session_id, env)
        if bad:
            return _wrong(f"the Claude Code session record {bad} is unreadable, so it "
                          "cannot be ruled out as this session's")
        if matches or time.monotonic() >= deadline:
            break
        time.sleep(_OWNER_POLL_SECONDS)
    if not matches and (env.get("CLAUDE_CONFIG_DIR") or "").strip():
        # Could not tell, never "headless": `auto` would turn that into a
        # notify telling a user at their own pane that a parent must
        # restart it.
        return _wrong("no Claude Code session record names this session in "
                      f"{' or '.join(_session_folders(env))} - CLAUDE_CONFIG_DIR is set, and "
                      "where Claude Code keeps its session records under it is unmeasured, "
                      "so a missing record cannot be read as a session with no terminal")
    if not matches:
        return _headless("no Claude Code session record names this session")
    if len(matches) > 1:
        return _wrong(f"{len(matches)} Claude Code session records name this session")
    record = matches[0]
    pid = record.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
        return _wrong("the session record has no usable pid")
    if not _alive(pid):
        return _wrong(f"the session record's pid {pid} is not running")
    started = _proc_start(pid)
    if started is not None and str(record.get("procStart")) != started:
        return _wrong(f"the session record's procStart does not match pid {pid}'s start "
                      "time - the pid was reused by another process")
    if pid not in ancestors():
        return _wrong(f"the session's process (pid {pid}) is not an ancestor of this hook")
    kind = record.get("kind")
    if kind != "interactive":
        return _headless(f"the session record's kind {kind!r}, not interactive")
    entrypoint = record.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint:
        return _wrong("the session record has no entrypoint, so it cannot say whether "
                      "the session is headless")
    if entrypoint.startswith("sdk"):
        return _headless(f"the session record's entrypoint {entrypoint!r} is a "
                         "headless (-p or SDK) session")
    tty = _tty_of(pid, env)
    if tty is None:
        return _wrong(f"could not read the controlling terminal of the session's process "
                      f"(pid {pid})")
    if tty == "":
        return _headless(f"the session's process (pid {pid}) has no controlling terminal")
    return {"ok": True, "headless": False, "reason": "", "pid": pid, "tty": tty}


def _shared_window(session_id, owner_pid, window, env):
    """"" when no OTHER live Claude Code session sits under the process that
    owns `window`; otherwise why it cannot be typed into.

    Proving the owner does not prove the window is its own. The walk from
    the owner climbs to the nearest process that owns a window, and that
    process may sit above another session too: the parent session a child
    `claude` with its own pty was started from (the walk climbs through the
    parent's process to the parent's terminal), or a sibling tab of one
    gnome-terminal / konsole / xfce4-terminal / VS Code window, where
    xdotool types into whichever tab is showing. A session UNDER the owner
    (a `claude -p` this session started) reaches the window only through
    the owner, so it is not a second holder. A record whose live pid has
    another start time is a reused pid and names nobody; a record with no
    procStart, or no readable one, cannot be proven stale and counts."""
    _matches, others, bad = _session_records(session_id, env)
    wid = window.get("id")
    if bad:
        return (f"the Claude Code session record {bad} is unreadable, so it cannot be ruled "
                f"out as another session in window {wid}")
    holders = []
    for name, record in others:
        pid = record.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
            return (f"the Claude Code session record {name} has no usable pid, so it cannot "
                    f"be ruled out as another session in window {wid}")
        if pid == owner_pid or not _alive(pid):
            continue
        started = _proc_start(pid)
        recorded = record.get("procStart")
        if started is not None and recorded is not None and str(recorded) != started:
            continue
        chain = ancestors(pid)
        if owner_pid in chain:
            continue
        holders.append((pid, name, chain))
    if not holders:
        return ""
    window_pid = _num(window.get("pid"), 0)
    if window_pid <= 1:
        return (f"window {wid} has no owning process, so it cannot be ruled out as also "
                f"hosting the live Claude Code session in {holders[0][1]}")
    for pid, name, chain in holders:
        if window_pid in chain:
            return (f"window {wid} (pid {window_pid}) {_SHARED_WINDOW} (pid {pid}, record "
                    f"{name}) - a terminal that holds several sessions in one window types "
                    "into whichever one is showing, so it cannot be proven to be this "
                    "session's")
    return ""


_SHARED_WINDOW = "also hosts another live Claude Code session"


def _boundary(env):
    """"ssh", "WSL" or "": the session runs across a boundary no keystroke
    from here can cross."""
    if any(env.get(k) for k in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
        return "ssh"
    if any(env.get(k) for k in ("WSL_DISTRO_NAME", "WSL_INTEROP")):
        return "WSL"
    if os.path.exists(env.get(WSL_INTEROP_ENV) or _WSL_INTEROP_PATH):
        return "WSL"
    return ""


def _boundary_reason(boundary):
    where = "over ssh" if boundary == "ssh" else "inside WSL"
    return (f"this session runs {where} with no tmux pane on this side, so no terminal "
            "here can be proven to be its own - run tmux where Claude runs to have it typed")


def _xdotool(*args):
    try:
        return subprocess.run(["xdotool", *args], capture_output=True, text=True,
                              timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def list_windows():
    """(windows, reason). Each window is {"id", "pid", "title"}.

    CREW_AUTOCLEAR_WINDOW_STUB names a JSON list that replaces the real window
    system. The suite uses it so no test ever enumerates, let alone types
    into, a real window."""
    stub = os.environ.get(WINDOW_STUB_ENV)
    if stub:
        try:
            with open(stub, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None, "the window stub is unreadable"
        return [w for w in data if isinstance(w, dict)], ""
    if not shutil.which("xdotool"):
        return None, "xdotool is not on PATH"
    windows = []
    for wid in _xdotool("search", "--onlyvisible", "--name", ".").split():
        pid = _num(_xdotool("getwindowpid", wid), 0)
        windows.append({"id": wid, "pid": pid, "title": _xdotool("getwindowname", wid)})
    return windows, ""


def resolve_target(ancestor_pids, windows, title):
    """{"ok", "window", "how", "reason"} -- a window only when exactly one fits."""
    needle = (title or "").lower()

    def titled(items):
        return [w for w in items if needle in str(w.get("title") or "").lower()]

    for pid in ancestor_pids:
        owned = [w for w in windows if _num(w.get("pid"), 0) == pid]
        if not owned:
            continue
        if needle:
            owned = titled(owned)
            if not owned:
                return {"ok": False, "reason": (
                    f"the terminal that owns this session (pid {pid}) has no window whose "
                    f"title contains '{title}'")}
        if len(owned) == 1:
            return {"ok": True, "window": owned[0],
                    "how": "owner pid + title" if needle else "owner pid"}
        return {"ok": False, "reason": (
            f"the terminal that owns this session (pid {pid}) has {len(owned)} windows and "
            "nothing narrows them to one - set context.autoClear.windowTitle")}
    if not needle:
        return {"ok": False, "reason": (
            "no window belongs to any ancestor of the session's own process (itself "
            "included), and no context.autoClear.windowTitle is set to fall back on")}
    hits = titled(windows)
    if len(hits) == 1:
        return {"ok": True, "window": hits[0], "how": "title fallback"}
    return {"ok": False, "reason": (
        f"{len(hits)} windows have a title containing '{title}' - refusing to guess "
        "which one is this session")}


def _tmux_pane(pane):
    """(pane pid or 0, pane tty or "") in one tmux call."""
    try:
        out = subprocess.run(["tmux", "display-message", "-p", "-t", pane,
                              "#{pane_pid} #{pane_tty}"],
                             capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return 0, ""
    fields = out.split()
    return (_num(fields[0], 0) if fields else 0), (fields[1] if len(fields) > 1 else "")


def _owner_refusal(cfg, owner):
    """A failed binding under a keystroke method: `auto` turns a HEADLESS
    session into a notify with the restart recipe; everything else refuses."""
    if owner["headless"]:
        reason = f"{owner['reason']}; {restart_recipe()}"
        if cfg["method"] == "auto":
            return {"ok": True, "method": "notify", "target": "", "label": "", "reason": reason}
        return {"ok": False, "reason": reason}
    return {"ok": False, "reason": owner["reason"]}


def resolve_method(cfg, env=None, session_id=""):
    """{"ok", "method", "target", "label", "reason"}. A keystroke method is
    bound to `session_id`'s own process first (`session_owner`); with no
    session id there is nothing to bind, so nothing is typed."""
    env = os.environ if env is None else env
    method = cfg["method"]
    boundary = _boundary(env)
    if method == "auto":
        if env.get("TMUX") and shutil.which("tmux"):
            method = "tmux"
        elif boundary:
            return {"ok": True, "method": "notify", "target": "", "label": "",
                    "reason": _boundary_reason(boundary)}
        elif env.get("DISPLAY") and shutil.which("xdotool"):
            method = "xdotool"
        # `OS=Windows_NT` is a Windows-kernel-set variable, present in every
        # process tree on a Windows box (cmd, PowerShell, Git Bash alike) and
        # absent inside WSL, which has its own init and does not inherit it.
        # That is what makes it the right test for "this hook is running on
        # native Windows" rather than `os.name`, which would also be "nt" for
        # a native-Windows python invoked from a POSIX-flavoured wrapper.
        # OWNER DECISION: `auto` never resolves to `sendkeys` here, even when
        # this flavour's own `sendkeys`-equivalent does not exist -- there is
        # no bash SendKeys, so this branch exists only to give the same
        # "handoff written, safe to run it yourself" notice a Windows user
        # gets from auto-clear.ps1, when THIS flavour is the one that won the
        # Stop hook race on that machine.
        elif env.get("OS") == "Windows_NT":
            method = "notify"
        else:
            method = "none"
    if method == "none" and cfg["method"] == "auto":
        # No terminal method at all; a session that provably has no terminal
        # of its own still gets the one thing a parent can act on.
        owner = session_owner(session_id, env)
        if owner["headless"]:
            return _owner_refusal(cfg, owner)
    if method == "none":
        return {"ok": False, "reason": (
            "no usable method. Inside tmux this works with no configuration; on X11 "
            "install xdotool; on native Windows 'notify' works with no configuration")}
    if method == "notify":
        # Never refused: it identifies no window and types nothing, so none
        # of the capability checks below apply to it.
        return {"ok": True, "method": "notify", "target": "", "label": ""}
    if method == "sendkeys":
        return {"ok": False, "reason": (
            "method sendkeys is auto-clear.ps1's job; this is the POSIX flavour. Both are "
            "registered, so the Windows one will have handled it")}
    if method == "wtype":
        return {"ok": False, "reason": (
            "method wtype types into whatever has focus and cannot identify a window, so it "
            "is refused whatever unsafeFocus says. Use tmux")}
    if method == "tmux":
        if not env.get("TMUX"):
            return {"ok": False, "reason": "method tmux but $TMUX is unset, so this session is not in a tmux pane"}
        if not shutil.which("tmux"):
            return {"ok": False, "reason": "method tmux but tmux is not on PATH"}
        pane = env.get("TMUX_PANE") or ""
        if not pane:
            return {"ok": False, "reason": "$TMUX_PANE is unset, so there is no pane to target"}
        owner = session_owner(session_id, env)
        if not owner["ok"]:
            return _owner_refusal(cfg, owner)
        pane_pid, pane_tty = _tmux_pane(pane)
        if not pane_pid or pane_pid not in ancestors():
            return {"ok": False, "reason": (
                f"tmux pane {pane} could not be confirmed as the pane running this session "
                f"(pane pid {pane_pid or 'unknown'} is not an ancestor of this hook)")}
        if not pane_tty:
            return {"ok": False, "reason": (
                f"could not read tmux pane {pane}'s terminal, so it cannot be matched to "
                "the session's own")}
        if owner["tty"] != pane_tty:
            return {"ok": False, "reason": (
                f"the session's controlling terminal {owner['tty']} is not the pane's "
                f"{pane_tty} - pane {pane} belongs to another session")}
        return {"ok": True, "method": "tmux", "target": pane,
                "label": f"{pane} [pane pid {pane_pid}]"}
    if method == "xdotool":
        if not shutil.which("xdotool"):
            return {"ok": False, "reason": "method xdotool but xdotool is not on PATH"}
        if boundary:
            return {"ok": False, "reason": (
                f"method xdotool across a{'n' if boundary == 'ssh' else ''} {boundary} "
                "boundary - the X display is not on the host this session runs on")}
        owner = session_owner(session_id, env)
        if not owner["ok"]:
            return _owner_refusal(cfg, owner)
        windows, why = list_windows()
        if windows is None:
            return {"ok": False, "reason": f"cannot list windows: {why}"}
        found = resolve_target(ancestors(owner["pid"]), windows, cfg["windowTitle"])
        if not found["ok"]:
            return {"ok": False, "reason": found["reason"]}
        shared = _shared_window(session_id, owner["pid"], found["window"], env)
        if shared:
            return {"ok": False, "reason": shared}
        win = found["window"]
        return {"ok": True, "method": "xdotool", "target": str(win.get("id")),
                "label": (f"{win.get('title') or ''} [window {win.get('id')}, "
                          f"pid {win.get('pid')}, {found['how']}]")}
    return {"ok": False, "reason": (
        f"unknown method '{cfg['method']}' (tmux, xdotool, notify, none, auto -- sendkeys is "
        "auto-clear.ps1's)")}


def plan(root, session_id, force=False, global_path=None, env=None):
    """Everything auto-clear.sh needs, decided in one place."""
    out = {"status": "refuse", "reason": "", "method": "", "target": "", "label": "",
           "command": "", "delay": "", "key": session_key(session_id)}
    cfg = settings(root, global_path)
    out.update(command=cfg["command"], delay=str(cfg["delaySeconds"]))
    if not cfg["enabled"]:
        out["status"] = "off"
        return out
    # Silent like "not opted in": outside the narrowing, this session is one
    # the machine never armed, so it must not even get a log line.
    if not in_scope(cfg, root, session_id):
        out["status"] = "off"
        return out
    # Past both silent-exit gates above: a machine that HAS opted in gets a
    # log line for anything `settings()` could not act on as configured.
    # An opted-out machine gets none of this either, matching "off is
    # silent" for the log file as a whole, not only for refusal reasons.
    for warning in cfg.get("_warnings", ()):
        log_autoclear(root, warning)
    if not force:
        ok, why = verify_handoff(root, session_id, cfg)
        if not ok:
            out["reason"] = why
            return out
    got = resolve_method(cfg, env, session_id)
    if not got["ok"]:
        out["reason"] = got["reason"]
        return out
    if got["method"] == "notify":
        # Nothing to wait for: there is no prompt to type into, so the delay
        # that exists for tmux/xdotool (the turn is still ending when this
        # runs) buys nothing here.
        out["delay"] = "0"
    out.update(status="send", method=got["method"], target=got["target"], label=got["label"],
               reason=got.get("reason", ""))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_autocycle.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--root", default=".")
    p_plan.add_argument("--session", default="")
    p_plan.add_argument("--force", action="store_true")
    p_key = sub.add_parser("key")
    p_key.add_argument("session", nargs="?", default="")
    args = parser.parse_args(argv)
    if args.cmd == "key":
        print(session_key(args.session))
        return 0
    try:
        result = plan(os.path.abspath(args.root), args.session, args.force)
    except Exception as exc:  # pylint: disable=broad-except
        result = {"status": "refuse", "reason": f"internal error: {exc}"}
    for field in ("status", "reason", "method", "target", "label", "command", "delay", "key"):
        print(" ".join(str(result.get(field, "")).splitlines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
