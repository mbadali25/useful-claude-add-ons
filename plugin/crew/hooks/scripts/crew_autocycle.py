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

MARKER_PREFIX = ".handoff-requested-"
SENT_PREFIX = ".autoclear-sent-"
# handoff-write.sh's PreCompact skeleton. It exists so a compaction never
# leaves NO note, and it says outright that it knows no next action -- so it
# is not a handoff anybody wrote, and clearing on it loses the session.
SKELETON_MARK = "UNKNOWN - this skeleton was written automatically"
WINDOW_STUB_ENV = "CREW_AUTOCLEAR_WINDOW_STUB"
_DEFAULTS = {"method": "auto", "windowTitle": "", "command": "/clear",
             "delaySeconds": 3, "minHandoffLines": 5}
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


def settings(root, global_path=None):
    """The autoClear settings in force for `root` on this machine."""
    repo_cfg = _load(os.path.join(root, ".crew", "config.json"))
    repo = _block(repo_cfg, "context", "autoClear")
    machine = _block(_load(global_path or global_config_path()), "context", "autoClear")
    out = {}
    for key, default in _DEFAULTS.items():
        value = repo.get(key)
        if value is None:
            value = machine.get(key)
        out[key] = default if value is None else value
    out["delaySeconds"] = _num(out["delaySeconds"], _DEFAULTS["delaySeconds"])
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
    return out


_WIN_DRIVE_SLASH = re.compile(r"^/([A-Za-z])(?=/|$)")
_ABSOLUTE = re.compile(r"^(/|[a-z]:/)")


def normalise_repo_path(path, windows=None):
    """The form `onlyRepos` entries and the repo root are compared in, or ""
    for anything that is not an absolute path.

    On Windows, backslashes become slashes; on POSIX a backslash is a legal
    filename character and is left alone, or two distinct paths collapse into
    one and an unlisted repo passes `onlyRepos`. Trailing separators go,
    symlinks are resolved (`realpath`), and on Windows the Git Bash `/c/x`
    shape becomes `c:/x` and the whole path is case-folded. A RELATIVE entry
    is refused rather than resolved: it would resolve against the repo being
    asked about, so `.` would match every repository on the machine.
    `windows` lets a Linux test drive the Windows rules; realpath runs only
    on the platform it describes."""
    windows = os.name == "nt" if windows is None else windows
    if not isinstance(path, str) or not path.strip():
        return ""
    text = os.path.expanduser(path.strip())
    if windows:
        text = text.replace("\\", "/")
        text = _WIN_DRIVE_SLASH.sub(lambda m: m.group(1) + ":", text, count=1)
        if re.fullmatch(r"[A-Za-z]:", text):
            text += "/"
    if not _ABSOLUTE.match(text.lower() if windows else text):
        return ""
    if windows == (os.name == "nt"):
        text = os.path.realpath(text)
        if windows:
            text = text.replace("\\", "/")
    text = text.rstrip("/") or "/"
    if windows:
        if re.fullmatch(r"[A-Za-z]:", text):
            text += "/"
        text = text.casefold()
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
            "no window belongs to any ancestor of this hook, and no "
            "context.autoClear.windowTitle is set to fall back on")}
    hits = titled(windows)
    if len(hits) == 1:
        return {"ok": True, "window": hits[0], "how": "title fallback"}
    return {"ok": False, "reason": (
        f"{len(hits)} windows have a title containing '{title}' - refusing to guess "
        "which one is this session")}


def _tmux_pane_pid(pane):
    try:
        out = subprocess.run(["tmux", "display-message", "-p", "-t", pane, "#{pane_pid}"],
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
        else:
            method = "none"
    if method == "none":
        return {"ok": False, "reason": (
            "no usable method. Inside tmux this works with no configuration; on X11 "
            "install xdotool")}
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
                "label": f"{pane} [pane pid {pane_pid}]"}
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
    return {"ok": False, "reason": f"unknown method '{cfg['method']}' (tmux, xdotool, none, auto)"}


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
    if not force:
        ok, why = verify_handoff(root, session_id, cfg)
        if not ok:
            out["reason"] = why
            return out
    got = resolve_method(cfg, env)
    if not got["ok"]:
        out["reason"] = got["reason"]
        return out
    out.update(status="send", method=got["method"], target=got["target"], label=got["label"])
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
