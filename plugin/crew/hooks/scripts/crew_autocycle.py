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

4. **Type only into this session's OWN terminal (T-0016).** A `claude -p`
   child inherits `$TMUX`, and its parent's pane and window are ancestors of
   its hook, so rule 3 alone typed `/clear` into the PARENT. The session is
   bound to its own process -- the nearest ancestor named by a Claude Code
   session record whose `sessionId` is the payload's and whose `procStart`
   matches -- and classified terminal / headless / unknown. Only terminal is
   typed into, and the pane or window is then proven by walking up from that
   process: through another session, past a truncated chain, or into a
   window that hosts another terminal, it refuses. Headless gets one notice
   naming its handoff and the restart; unknown is never called headless.

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
`resume-plan --root R --session S --source clear|compact [--flavour sh|ps1]`
is T-0013's: the same eight lines with the rendered resume prompt as the
command, then timeout, marker and decision, then ".". `probe` reads a
`tmux capture-pane -p -e` on stdin and prints ready|busy|nonempty|noprompt.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import crew_common

MARKER_PREFIX = ".handoff-requested-"
SENT_PREFIX = ".autoclear-sent-"
# handoff-write.sh's PreCompact skeleton. It exists so a compaction never
# leaves NO note, and it says outright that it knows no next action -- so it
# is not a handoff anybody wrote, and clearing on it loses the session.
SKELETON_MARK = "UNKNOWN - this skeleton was written automatically"
WINDOW_STUB_ENV = "CREW_AUTOCLEAR_WINDOW_STUB"
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
PROC_STUB_ENV = "CREW_AUTOCLEAR_PROC_STUB"
# Measured 2026-10-04, Claude Code 2.1.289 on Linux
# (plugin/crew/docs/session-record-spike.md): an interactive session in a tmux
# pane records entrypoint "cli"; `claude -p` records "sdk-cli", with or
# without a pty around it. Both record kind "interactive", so kind alone
# proves nothing. Windows and macOS are unmeasured: an entrypoint outside
# this set is unknown, never a terminal.
TERMINAL_ENTRYPOINTS = frozenset({"cli"})
HEADLESS_ENTRYPOINT_PREFIX = "sdk"
CLAUDE_COMM = "claude"
# A native install runs as `~/.local/share/claude/versions/<x.y.z>`, so its comm
# is the version. Unmeasured beyond that path's shape: the records and the
# tty rule carry the proof, and this only makes the walk fail closed sooner.
_VERSIONED_COMM = re.compile(r"\d+\.\d+\.\d+")
INHIBIT_ENV = "CREW_AUTOCLEAR_INHIBIT"
_SCAN_LIMIT = 4096


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
    repo_cfg = _load(crew_common.repo_config_file(root, "config.json"))
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


# --------------------------------------------------------------------------
# T-0016: which process is this session, and does it have a terminal?
#
# Every process fact below is read through `_proc`, so one stub replaces the
# whole process table: CREW_AUTOCLEAR_PROC_STUB names a JSON object
# `{"self": <pid the walk starts from>, "<pid>": {"ppid", "tty", "start",
# "comm"} | null, ..., "scanFails": true?}`. When it is set it is the ONLY
# process table -- a pid it does not name does not exist -- the same standing
# as CREW_AUTOCLEAR_WINDOW_STUB, and for the same reason: no test may depend on
# the real process tree, and on native Windows the bash flavour has no other
# way to read one. No environment variable is evidence of WHICH process is
# this session (CLAUDE_PID and CLAUDE_CODE_ENTRYPOINT are copied into every
# child); the stub only replaces where facts are read from. `{"gone": true}`
# is a pid that no longer exists (the top of a chain); null is one that
# exists but cannot be read.
#
# Both stubs are honoured ONLY while CREW_AUTOCLEAR_INHIBIT is set (review
# round 1): a repo's `.claude/settings.json` env reaches every hook, so a stub
# honoured on its own could make a parent's window look like this session's.
# With the inhibit set no keystroke is ever sent, so a stub can steer nothing
# that types; every suite case sets it.

def _stubs_allowed():
    return bool(os.environ.get(INHIBIT_ENV))


def _proc_stub():
    """(table, scan_fails, start_pid) from CREW_AUTOCLEAR_PROC_STUB, or
    (None, False, None) when it is unset. A stub that is set but unreadable is
    an empty table whose scans fail: nothing in it, so nothing is proven."""
    path = os.environ.get(PROC_STUB_ENV)
    if not path or not _stubs_allowed():
        return None, False, None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}, True, None
    if not isinstance(data, dict):
        return {}, True, None
    table = {}
    for key, entry in data.items():
        if key.isdigit() and (entry is None or isinstance(entry, dict)):
            table[int(key)] = entry
    return table, data.get("scanFails") is True, _num(data.get("self"), 0) or None


def _stub_entry(entry):
    if entry is None or entry.get("gone") is True:
        return None
    tty = entry.get("tty")
    return {"ppid": _num(entry.get("ppid"), 0),
            "tty": None if tty is None or isinstance(tty, bool) else _num(tty, None),
            "start": entry.get("start"), "comm": str(entry.get("comm") or "")}


def _read_stat(pid):
    """/proc/<pid>/stat as {ppid, tty, start, comm}, or None. tty is field 7
    (tty_nr, 0 = no controlling terminal), start is field 22."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
            text = handle.read()
        rest = text.rsplit(")", 1)[1].split()
        return {"ppid": int(rest[1]), "tty": int(rest[4]), "start": int(rest[19]),
                "comm": text[text.index("(") + 1:text.rindex(")")]}
    except (OSError, IndexError, ValueError):
        return None


def _tty_token(text):
    """A `ps` tty column as a number: 0 for none (`?`, `??`, `-`), otherwise
    a stable non-zero stand-in -- only equality and zero-ness are ever used."""
    text = (text or "").strip()
    if text in ("", "?", "??", "-"):
        return 0
    return int.from_bytes(text.encode("utf-8")[-7:], "big") or 1


def _parse_ps(line):
    """One `ps -o ppid=,tty=,comm=` line as {ppid, tty, start, comm}, or None.
    No start time: `ps` gives none comparable to a record's `procStart`, so a
    record is then bound by pid and session id only (OWNER DECISION, macOS)."""
    parts = (line or "").split(None, 2)
    if len(parts) < 3:
        return None
    try:
        ppid = int(parts[0])
    except ValueError:
        return None
    return {"ppid": ppid, "tty": _tty_token(parts[1]), "start": None,
            "comm": os.path.basename(parts[2].strip())}


def _proc(pid):
    """{ppid, tty, start, comm} for `pid`, or None when it cannot be read."""
    table, _fails, _self = _proc_stub()
    if table is not None:
        return _stub_entry(table.get(pid))
    found = _read_stat(pid)
    if found is not None or os.name == "nt":
        return found
    try:
        out = subprocess.run(["ps", "-o", "ppid=,tty=,comm=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return _parse_ps(out.strip().splitlines()[0] if out.strip() else "")


def _gone(pid):
    """True only when `pid` provably no longer exists -- not when it merely
    cannot be read."""
    table, _fails, _self = _proc_stub()
    if table is not None:
        entry = table.get(pid)
        return isinstance(entry, dict) and entry.get("gone") is True
    return os.path.isdir("/proc") and not os.path.exists(f"/proc/{pid}")


def _ppid(pid):
    found = _proc(pid)
    return found["ppid"] if found else 0


def _start_pid():
    _table, _fails, start = _proc_stub()
    return start or os.getpid()


def ancestry(pid=None):
    """(chain, complete, why): `pid` (default: this process) and its
    ancestors, nearest first. `complete` is False when the walk stopped before
    reaching the top -- a parent that could not be read, a loop, or more than
    _ANCESTOR_LIMIT processes -- and `why` says which. An incomplete chain
    proves nothing about what lies above it."""
    out, pid = [], pid or _start_pid()
    while True:
        if pid in out:
            return out, False, f"the process chain loops back to pid {pid}"
        if len(out) >= _ANCESTOR_LIMIT:
            return out, False, f"the process chain is deeper than {_ANCESTOR_LIMIT} processes"
        out.append(pid)
        found = _proc(pid)
        if found is None:
            if len(out) > 1 and _gone(pid):
                # A recorded parent that has exited: the top of the chain.
                out.pop()
                return out, True, ""
            return out, False, f"the parent of pid {pid} could not be read"
        pid = found["ppid"]
        if pid <= 1:
            return out, True, ""


def ancestors(pid=None):
    """This process and its ancestors, nearest first."""
    out, pid = [], pid or _start_pid()
    while pid and pid > 1 and pid not in out and len(out) < _ANCESTOR_LIMIT:
        out.append(pid)
        pid = _ppid(pid)
    return out


def claude_config_dir(env=None):
    """`$CLAUDE_CONFIG_DIR` when set and non-empty, else `~/.claude` -- where
    Claude Code writes `sessions/<pid>.json`. A record found only under the
    other one is not this session's (measured: plugin/crew/docs/session-record-spike.md)."""
    env = os.environ if env is None else env
    value = env.get("CLAUDE_CONFIG_DIR") or ""
    return value if value else os.path.join(os.path.expanduser("~"), ".claude")


def _read_record(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def session_owner(session_id, env=None):
    """The process that IS this session: {"pid", "record", "info", "how"}, or
    {"unknown": reason}.

    The nearest ancestor of this hook named by a session record in
    `<config>/sessions/<pid>.json` whose `sessionId` is the payload's and
    whose `procStart` is that process's start time wherever the start time
    can be read (a reused pid is a different process). Anything else --
    no record, another session's record, an unreadable one, a start-time
    mismatch, a chain that could not be read to the end -- is unknown, and
    unknown is never "headless" and never "terminal"."""
    if not session_id:
        return {"unknown": "no session id, so no session record can be matched"}
    sessions = os.path.join(claude_config_dir(env), "sessions")
    chain, complete, why = ancestry()
    for pid in chain:
        path = os.path.join(sessions, f"{pid}.json")
        if not os.path.lexists(path):
            continue
        record = _read_record(path)
        if record is None:
            return {"unknown": f"the session record for pid {pid} is unreadable or not a JSON object"}
        if record.get("sessionId") != session_id:
            return {"unknown": f"the session record for pid {pid} names another session"}
        info = _proc(pid)
        start = info.get("start") if info else None
        if start is None:
            return {"pid": pid, "record": record, "info": info,
                    "how": "session record + session id (start time unreadable here)"}
        if str(record.get("procStart")) != str(start):
            return {"unknown": (f"the session record for pid {pid} has procStart "
                                f"{record.get('procStart')!r} but that process started at {start} - "
                                "a reused pid is a different process")}
        return {"pid": pid, "record": record, "info": info, "how": "session record + session id + start time"}
    if not complete:
        return {"unknown": f"no session record names a process above this hook, and {why}"}
    return {"unknown": f"no session record under {sessions} names a process above this hook"}


def classify(owner):
    """("terminal" | "headless" | "unknown", evidence).

    `terminal` needs all three: kind "interactive", an entrypoint on the
    measured allowlist, and a controlling terminal (tty_nr != 0). `headless`
    needs positive evidence: an `sdk*` entrypoint, a kind other than
    "interactive", or tty_nr 0. Anything else is unknown -- an entrypoint
    nobody measured is never assumed to have a terminal."""
    if "unknown" in owner:
        return "unknown", owner["unknown"]
    record, info = owner["record"], owner.get("info") or {}
    kind, entry, tty = record.get("kind"), record.get("entrypoint"), info.get("tty")
    if isinstance(entry, str) and entry.startswith(HEADLESS_ENTRYPOINT_PREFIX):
        return "headless", f"entrypoint {entry}"
    if isinstance(kind, str) and kind != "interactive":
        return "headless", f"kind {kind}"
    if tty == 0:
        return "headless", "no controlling terminal: tty_nr 0"
    if kind != "interactive":
        return "unknown", f"the session record for pid {owner['pid']} has no usable kind ({kind!r})"
    if entry not in TERMINAL_ENTRYPOINTS:
        return "unknown", (f"entrypoint {entry!r} is not one measured to have a terminal "
                           f"({', '.join(sorted(TERMINAL_ENTRYPOINTS))})")
    if tty is None:
        return "unknown", f"the controlling terminal of pid {owner['pid']} could not be read"
    return "terminal", f"kind interactive, entrypoint {entry}, tty_nr {tty}"


def other_sessions(owner_pid, env=None):
    """Pids of every OTHER live session record (process exists, start time
    matches where readable), or None when the records cannot be listed."""
    sessions = os.path.join(claude_config_dir(env), "sessions")
    try:
        names = os.listdir(sessions)
    except OSError:
        return None
    out = set()
    for name in names:
        match = re.fullmatch(r"(\d+)\.json", name)
        if not match or int(match.group(1)) == owner_pid:
            continue
        pid = int(match.group(1))
        record = _read_record(os.path.join(sessions, name))
        info = _proc(pid)
        if info is None:
            continue
        if record is None:
            # A live process whose record cannot be read may be a session:
            # it cannot be ruled out, so nothing is ruled out (review round 1).
            return None
        if info.get("start") is not None and str(record.get("procStart")) != str(info["start"]):
            continue
        out.add(pid)
    return out


def _process_table():
    """{pid: {ppid, tty, start, comm}} for every process, or None when the
    table cannot be read (a scan that fails proves nothing)."""
    table, fails, _self = _proc_stub()
    if table is not None:
        return None if fails else {pid: _stub_entry(e) for pid, e in table.items() if e is not None}
    try:
        names = os.listdir("/proc")
    except OSError:
        names = None
    if names is not None:
        out = {}
        for name in names:
            if name.isdigit():
                found = _read_stat(int(name))
                if found is not None:  # gone mid-scan: not a terminal anybody types into
                    out[int(name)] = found
        return out or None
    try:
        lines = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,tty=,comm="], capture_output=True,
                               text=True, timeout=10, check=False).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    out = {}
    for line in lines:
        head, _, rest = line.strip().partition(" ")
        found = _parse_ps(rest)
        if head.isdigit() and found is not None:
            out[int(head)] = found
    return out or None


def _shared_window(window_pid, owner, others):
    """"" when every terminal under the window's owning process is this
    session's, else why not. One terminal server can host many tabs, so
    proving the owner is an ancestor does not prove the window is this
    session's: every descendant of `window_pid` outside the owner's own
    subtree that has a controlling terminal must be on the owner's, and none
    may be another session. A sibling can be invisible to a record scan
    (`tmux attach`, ssh, another config dir, a plain shell), which is why this
    reads ttys, not records."""
    table = _process_table()
    if table is None:
        return (f"the processes under the window's owner (pid {window_pid}) could not be listed, so it "
                "cannot be shown that the window hosts only this session")
    children = {}
    for pid, entry in table.items():
        children.setdefault(entry["ppid"], []).append(pid)
    owner_tty = (owner.get("info") or {}).get("tty")
    seen, queue = set(), list(children.get(window_pid, ()))
    while queue:
        pid = queue.pop()
        if pid in seen or pid == owner["pid"]:
            continue
        seen.add(pid)
        if len(seen) > _SCAN_LIMIT:
            return (f"more than {_SCAN_LIMIT} processes run under the window's owner (pid {window_pid}), so "
                    "the scan for another terminal was cut short")
        if pid in others:
            return f"the window's owner (pid {window_pid}) also hosts another Claude Code session (pid {pid})"
        tty = table[pid].get("tty")
        if tty and tty != owner_tty:
            return (f"the window's owner (pid {window_pid}) also hosts another terminal (pid {pid} on "
                    f"tty_nr {tty}, this session is on {owner_tty})")
        queue.extend(children.get(pid, ()))
    return ""


def prove_target(owner, got, cfg, env=None):
    """The method's target, proven from the session's OWN process rather than
    from this hook: {"ok", "target", "label"} or {"ok": False, "reason"}.

    tmux: the pane's pid is the owner or an ancestor of it. xdotool: the
    window is owned by a strict ancestor of the owner, and hosts no other
    terminal. Either way the walk refuses when it passes through another
    Claude Code process or another live session record (a child under its
    parent's pane or window), or when the chain could not be read to the
    end. A window found by title alone, or with no owning process, refuses
    whenever another session is live: a title cannot tell two apart."""
    me = owner["pid"]
    chain, complete, why = ancestry(me)
    others = other_sessions(me, env)
    if others is None:
        return {"ok": False, "reason": ("the session records could not be listed or read, so another session "
                                        "cannot be ruled out")}

    def crossing(pid):
        comm = (_proc(pid) or {}).get("comm") or ""
        return pid in others or comm == CLAUDE_COMM or bool(_VERSIONED_COMM.fullmatch(comm))

    if got["method"] == "tmux":
        pane_pid = got.get("pane_pid") or 0
        if pane_pid not in chain:
            tail = f", and {why}" if not complete else ""
            return {"ok": False, "reason": (
                f"tmux pane {got['target']} (pane pid {pane_pid or 'unknown'}) is not this session's: it is "
                f"not an ancestor of this session's own process (pid {me}){tail}")}
        for pid in chain[1:chain.index(pane_pid) + 1]:
            if crossing(pid):
                return {"ok": False, "reason": (
                    f"the way from this session (pid {me}) up to tmux pane {got['target']} passes through "
                    f"another Claude Code session (pid {pid})")}
        # Review round 1 BLOCK: a parent session in another config dir, under
        # a comm that is not `claude`, is invisible to both checks above. The
        # pane types into ITS tty, so every process from this session up to
        # the pane must be on this session's tty or on none.
        own_tty = (owner.get("info") or {}).get("tty")
        for pid in chain[1:chain.index(pane_pid) + 1]:
            tty = (_proc(pid) or {}).get("tty")
            if tty is None:
                return {"ok": False, "reason": (
                    f"the controlling terminal of pid {pid}, between this session and tmux pane "
                    f"{got['target']}, could not be read")}
            if tty and tty != own_tty:
                return {"ok": False, "reason": (
                    f"tmux pane {got['target']} is not this session's terminal: pid {pid} is on tty_nr {tty}, "
                    f"this session (pid {me}) is on {own_tty}")}
        return {"ok": True, "target": got["target"], "label": got["label"], "owner": me}
    windows, reason = list_windows()
    if windows is None:
        return {"ok": False, "reason": f"cannot list windows: {reason}"}
    for pid in chain[1:]:
        if crossing(pid):
            return {"ok": False, "reason": (
                f"the way from this session (pid {me}) up to its window passes through another Claude Code "
                f"session (pid {pid})")}
        if not any(_num(w.get("pid"), 0) == pid for w in windows):
            continue
        found = resolve_target([pid], windows, cfg["windowTitle"])
        if not found["ok"]:
            return {"ok": False, "reason": found["reason"]}
        shared = _shared_window(pid, owner, others)
        if shared:
            return {"ok": False, "reason": shared}
        return _window_result(found, me)
    if not complete:
        return {"ok": False, "reason": f"no window belongs to a process above this session (pid {me}), and {why}"}
    if not cfg["windowTitle"]:
        return {"ok": False, "reason": (
            f"no window belongs to any ancestor of this session's process (pid {me}), and no "
            "context.autoClear.windowTitle is set to fall back on")}
    found = resolve_target([], windows, cfg["windowTitle"])
    if not found["ok"]:
        return {"ok": False, "reason": found["reason"]}
    if others:
        sibling = min(others)
        if _num(found["window"].get("pid"), 0) <= 1:
            return {"ok": False, "reason": (
                f"window {found['window'].get('id')} has no owning process, and another Claude Code session "
                f"is live (pid {sibling}), so nothing ties that window to this session")}
        return {"ok": False, "reason": (
            f"window {found['window'].get('id')} was found by its title alone, and another Claude Code "
            f"session is live (pid {sibling}) - a title cannot tell two sessions apart")}
    return _window_result(found, me)


def _window_result(found, me):
    win = found["window"]
    return {"ok": True, "target": str(win.get("id")),
            "label": (f"{win.get('title') or ''} [window {win.get('id')}, pid {win.get('pid')}, "
                      f"{found['how']}]"), "owner": me}


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
    stub = os.environ.get(WINDOW_STUB_ENV) if _stubs_allowed() else None
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
            "no window belongs to any ancestor of this hook, and no "
            "context.autoClear.windowTitle is set to fall back on")}
    hits = titled(windows)
    if len(hits) == 1:
        return {"ok": True, "window": hits[0], "how": "title fallback"}
    return {"ok": False, "reason": (
        f"{len(hits)} windows have a title containing '{title}' - refusing to guess "
        "which one is this session")}


def _tmux_pane_pid(pane):
    # Run the tmux that shutil.which found -- the one resolve_method's "on
    # PATH" check just accepted -- not a bare "tmux". On native Windows a bare
    # name reaches CreateProcess, which tries only tmux.exe, while which()
    # also honours PATHEXT (tmux.cmd, tmux.bat): the check passed, the run
    # raised OSError, and the refusal named the pane pid "unknown" for a tmux
    # that was never run. An unresolvable tmux is still 0, still refused.
    tmux = shutil.which("tmux")
    if not tmux:
        return 0
    try:
        out = subprocess.run([tmux, "display-message", "-p", "-t", pane, "#{pane_pid}"],
                             capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    return _num(out.strip(), 0)


def resolve_method(cfg, env=None):
    """{"ok", "method", "target", "label", "reason"}."""
    env = os.environ if env is None else env
    method = cfg["method"]
    if method == "auto":
        if env.get("TMUX") and shutil.which("tmux"):
            method = "tmux"
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
        pane_pid = _tmux_pane_pid(pane)
        if not pane_pid or pane_pid not in ancestors():
            return {"ok": False, "reason": (
                f"tmux pane {pane} could not be confirmed as the pane running this session "
                f"(pane pid {pane_pid or 'unknown'} is not an ancestor of this hook)")}
        return {"ok": True, "method": "tmux", "target": pane,
                "label": f"{pane} [pane pid {pane_pid}]", "pane_pid": pane_pid}
    if method == "xdotool":
        if not shutil.which("xdotool"):
            return {"ok": False, "reason": "method xdotool but xdotool is not on PATH"}
        windows, why = list_windows()
        if windows is None:
            return {"ok": False, "reason": f"cannot list windows: {why}"}
        found = resolve_target(ancestors(), windows, cfg["windowTitle"])
        if not found["ok"]:
            return {"ok": False, "reason": found["reason"]}
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
    got = resolve_method(cfg, env)
    if not got["ok"]:
        out["reason"] = got["reason"]
        return out
    # T-0016: after the handoff checks and the method, before the sender's
    # claim. Nothing types until this session's own process is proven to
    # have a terminal and the target is proven from that process.
    got = bind_to_session(root, session_id, cfg, got, env, force)
    if not got["ok"]:
        out["reason"] = got["reason"]
        return out
    if got["method"] in ("notify", "notify-headless"):
        # Nothing to wait for: there is no prompt to type into, so the delay
        # that exists for tmux/xdotool (the turn is still ending when this
        # runs) buys nothing here.
        out["delay"] = "0"
    out.update(status="send", method=got["method"], target=got["target"], label=got["label"],
               reason=got.get("notice", ""))
    return out


_RESUME_LINE = re.compile(r"^resume:[ \t]*(.*?)[ \t]*$", re.MULTILINE)


def headless_notice(root, cfg, evidence, force=False):
    """The one message a headless session gets instead of a keystroke. It
    names the handoff and its `resume:` line (read as text, not parsed) and
    says the process that started this session must restart it -- a fresh
    process is a different author, so nothing here can resume it."""
    rel = cfg["handoffPath"]
    line = "(none in the handoff)"
    path = _contained(root, rel)
    try:
        with open(path or "", encoding="utf-8", errors="replace") as handle:
            found = _RESUME_LINE.search(handle.read())
        if found and found.group(1):
            line = found.group(1)
    except OSError:
        pass
    written = (f"Its handoff at {rel} was not checked (--force)" if force
               else f"Its handoff is written and verified at {rel}")
    return (f"crew: this session has no terminal of its own ({evidence}), so nothing was cleared or "
            f"typed. {written}; resume: {line}. The process that started this session must start a new "
            "one to continue.")


def _unknown_reason(owner, evidence):
    if "unknown" in owner:
        return f"could not identify this session's process ({evidence})"
    return f"could not tell whether this session has a terminal of its own ({evidence})"


def bind_to_session(root, session_id, cfg, got, env=None, force=False):
    """T-0016: `got` (a resolved method) bound to this session's own process.

    headless -> `notify-headless` whatever the method, carrying its notice;
    unknown -> `notify` stays `notify`, `auto` falls back to plain `notify`
    (logged), and an explicitly configured typing method refuses; terminal
    -> `notify` unchanged, tmux/xdotool re-proven from the owner by
    `prove_target`."""
    owner = session_owner(session_id, env)
    cls, evidence = classify(owner)
    if cls == "headless":
        return {"ok": True, "method": "notify-headless", "target": "", "label": "",
                "notice": headless_notice(root, cfg, evidence, force)}
    if got["method"] == "notify":
        return got
    if cls == "unknown":
        reason = _unknown_reason(owner, evidence)
        if cfg["method"] == "auto":
            log_autoclear(root, f"auto-clear: {reason} - auto falls back to notify, nothing is typed")
            return {"ok": True, "method": "notify", "target": "", "label": ""}
        return {"ok": False, "reason": reason}
    proof = prove_target(owner, got, cfg, env)
    if not proof["ok"]:
        return proof
    return dict(got, target=proof["target"], label=proof["label"])


# --------------------------------------------------------------------------
# T-0013: auto-resume TYPES the resume command into its own session.
#
# Consent is T-0006's `resume.auto` (machine only, repo veto), so
# `context.autoClear.enabled` is NOT required here; the rest of the autoClear
# block -- method, windowTitle, onlyRepos, onlySessions -- is this machine's
# description of its terminal and is read exactly as `settings` reads it.

# Printed one per line by `resume-plan`, then a lone "." so a run of empty
# trailing fields survives the shell's `$(...)`, which strips trailing newlines.
RESUME_PLAN_FIELDS = ("status", "reason", "method", "target", "label", "command", "delay", "key",
                      "timeout", "marker", "decision")


def resume_typing(global_path=None):
    """(typeDelaySeconds, readyTimeoutSeconds) from the MACHINE file only. A
    value that is absent, not a whole number, or negative is the default:
    a negative sleep would kill the sender after the marker was claimed."""
    import crew_state  # pylint: disable=import-outside-toplevel
    block = _block(_load(global_path or global_config_path()), "resume")
    out = []
    for key in ("typeDelaySeconds", "readyTimeoutSeconds"):
        default = crew_state.RESUME_DEFAULTS[key]
        value, _ok = _num_checked(block.get(key), default)
        out.append(value if value >= 0 else default)
    return out[0], out[1]


def resume_plan(root, session_id, source, global_path=None, env=None, flavour="sh", plugin_root=None):
    """Everything auto-clear's resume mode needs, decided in one place.

    `plan`'s eight fields (so the senders read them unchanged), then the
    probe timeout, the per-handoff marker path and the decision JSON that
    `crew_resume.py record` takes. Order, first failure wins: T-0006's
    `decide` (off -> off; any other non-run -> refuse with its reason, after
    the narrowing below so an un-narrowed session stays silent), `in_scope`
    (off), then the method -- `resolve_method` for the sh flavour; the ps1
    flavour resolves `sendkeys` natively, so its plan stops before that."""
    out = dict.fromkeys(RESUME_PLAN_FIELDS, "")
    out["status"] = "refuse"
    try:
        import crew_context  # pylint: disable=import-outside-toplevel
        import crew_resume  # pylint: disable=import-outside-toplevel
    except Exception:  # pylint: disable=broad-except
        out["reason"] = "crew_resume could not be imported, so nothing was decided"
        return out
    crew_cfg = crew_context.load_crew_config(root)
    rel, text = crew_context._handoff(root, crew_cfg)  # pylint: disable=protected-access
    payload = {"hook_event_name": "SessionStart", "source": source, "session_id": session_id}
    decision = crew_resume.decide(
        root, payload, text, plugin_root or crew_resume._plugin_root(),  # pylint: disable=protected-access
        global_path, stale=crew_resume._is_stale(root, crew_cfg, rel, text))  # pylint: disable=protected-access
    if decision.get("action") == "off":
        out["status"] = "off"
        return out
    cfg = settings(root, global_path)
    narrowed_in = in_scope(cfg, root, session_id)
    if not narrowed_in:
        out["status"] = "off"
        return out
    if decision.get("action") != "run":
        out["reason"] = f"auto-resume is waiting: {decision.get('reason') or 'unknown'}"
        return out
    delay, timeout = resume_typing(global_path)
    key = str(decision.get("handoff_sha256") or "")[:16]
    out.update(command=decision["prompt"], delay=str(delay), timeout=str(timeout), key=key,
               marker=os.path.join(crew_resume.state_dir(root), f"resume-typed-{key}"),
               decision=json.dumps(decision, sort_keys=True))
    try:
        # Where the senders claim the marker; record_run writes beside it.
        os.makedirs(os.path.dirname(out["marker"]), exist_ok=True)
    except OSError:
        pass
    if flavour == "ps1":
        out.update(status="send", method=cfg["method"])
        return out
    got = resolve_method(cfg, env)
    if not got["ok"]:
        out["reason"] = got["reason"]
        return out
    if got["method"] == "xdotool":
        out["reason"] = ("auto-resume types through tmux (which has a ready probe) or sendkeys only; "
                         "xdotool cannot see whether the input line is ready")
        return out
    if got["method"] != "notify":
        # T-0016: the same binding as /clear, before anything is typed. A
        # headless child's SessionStart never types into its parent's pane.
        owner = session_owner(session_id, env)
        cls, evidence = classify(owner)
        if cls == "headless":
            out["reason"] = ("auto-resume types only into this session's own terminal: this session has "
                             f"no terminal of its own ({evidence})")
            return out
        if cls == "unknown":
            out["reason"] = ("auto-resume types only into this session's own terminal: "
                             f"{_unknown_reason(owner, evidence)}")
            return out
        proof = prove_target(owner, got, cfg, env)
        if not proof["ok"]:
            out["reason"] = f"auto-resume types only into this session's own terminal: {proof['reason']}"
            return out
    if got["method"] == "notify":
        out["delay"] = "0"
    out.update(status="send", method=got["method"], target=got["target"], label=got["label"])
    return out


_DIM_RUN = re.compile(r"\x1b\[2m.*?\x1b\[0m")
_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_PROMPT_GLYPH = "❯"
_RULE = "───"


def _plain(line):
    return _ESCAPE.sub("", _DIM_RUN.sub("", line))


def probe_input_line(capture):
    """ready | busy | nonempty | noprompt, for a `tmux capture-pane -p -e`.

    Pinned against Claude Code 2.1.282 by the T-0013 spike: the input line
    starts with U+276F and sits between two rule lines (U+2500). Ready is
    that line holding nothing but whitespace (NBSP included) once dim runs
    -- the placeholder -- and every other escape are removed, with no
    `esc to interrupt` anywhere (the busy /compact frame looks empty). The
    LAST such line counts. A glyph this does not know is `noprompt`, which
    the sender treats as not ready: it types nothing."""
    lines = [_plain(line) for line in (capture or "").splitlines()]
    if any("esc to interrupt" in line for line in lines):
        return "busy"
    for index in range(len(lines) - 2, 0, -1):
        line = lines[index].lstrip()
        if not line.startswith(_PROMPT_GLYPH):
            continue
        if not (lines[index - 1].lstrip().startswith(_RULE) and lines[index + 1].lstrip().startswith(_RULE)):
            continue
        return "ready" if not line[len(_PROMPT_GLYPH):].strip() else "nonempty"
    return "noprompt"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_autocycle.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--root", default=".")
    p_plan.add_argument("--session", default="")
    p_plan.add_argument("--force", action="store_true")
    p_key = sub.add_parser("key")
    p_key.add_argument("session", nargs="?", default="")
    p_resume = sub.add_parser("resume-plan")
    p_resume.add_argument("--root", default=".")
    p_resume.add_argument("--session", default="")
    p_resume.add_argument("--source", default="")
    p_resume.add_argument("--flavour", default="sh", choices=("sh", "ps1"))
    sub.add_parser("probe")
    args = parser.parse_args(argv)
    if args.cmd == "key":
        print(session_key(args.session))
        return 0
    if args.cmd == "probe":
        print(probe_input_line(sys.stdin.buffer.read().decode("utf-8", "replace")))
        return 0
    if args.cmd == "resume-plan":
        try:
            result = resume_plan(os.path.abspath(args.root), args.session, args.source, flavour=args.flavour)
        except Exception as exc:  # pylint: disable=broad-except
            result = {"status": "refuse", "reason": f"internal error: {exc.__class__.__name__}"}
        for field in RESUME_PLAN_FIELDS:
            print(" ".join(str(result.get(field, "")).splitlines()))
        print(".")
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
