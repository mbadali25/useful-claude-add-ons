"""Auto-resume after /clear or a manual /compact: the `resume:` handoff line
and the decision whether it may be resumed (T-0006, reduced form).

`/crew:handoff` writes one machine-readable line into the handoff's header,

    resume: /crew:done T-0001

and this module is the ONE definition of what that line may say:
`RESUME_COMMANDS` is the closed allowlist, `parse_resume` the grammar, and
`render` rebuilds the prompt from the parsed tokens -- never by copying the
line, so no text the handoff carries beyond a command and one validated
argument can reach a session. `/crew:autopilot` (T-0004) imports
`parse_resume` and never re-parses.

Nothing here starts a turn. The step-1 spike (Claude Code 2.1.282, 2026-09-25)
proved SessionStart `initialUserMessage` is dropped in every interactive
session, so crew never emits it: `crew_context` NAMES the command and the
reason it did not start, and T-0013 types it where a terminal can be driven.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

import crew_common
from crew_common import git_out, read_text
import crew_autocycle
import crew_context
import crew_goal_state
import crew_state

# The closed allowlist: (command, argument kinds). A module constant and not
# config, so no repo file can widen it. `ticket` is one ticket id, `goal` is
# `--goal <slug>`, `none` is the bare command.
RESUME_COMMANDS = (
    ("/crew:spec", "ticket"),
    ("/crew:plan", "ticket"),
    ("/crew:implement", "ticket"),
    ("/crew:review", "ticket"),
    ("/crew:done", "ticket"),
    ("/crew:autopilot", "ticket|goal|none"),
    ("/crew:status", "none"),
)

# Never resumable, named so a refusal can say "excluded" rather than
# "unknown". `/crew:approve` is human consent (`disable-model-invocation`,
# and approval-hook records it from any prompt that carries it); the rest
# either decide something only a human may (fix scope, an incident, a gate,
# a promotion, a migration, a change request) or start from nothing.
EXCLUDED = (
    "/crew:approve",
    "/crew:brainstorm",
    "/crew:fix",
    "/crew:emergency",
    "/crew:gate",
    "/crew:promote",
    "/crew:migrate",
    "/crew:change",
)

# SessionStart sources that may resume. Never `startup` (a fresh terminal is
# not a continuation) and never `resume` (`claude --resume` restores the old
# conversation, which already has its own next turn).
RESUME_SOURCES = ("clear", "compact")
# The consumed-once record keeps this many handoff hashes per worktree.
CONSUMED_KEEP = 50
STATE_FILE = "resume-state.json"
# Which session wrote the handoff (T-0042): written by the PostToolUse hook
# after a Write/Edit/MultiEdit of the handoff, on an armed machine only.
AUTHOR_FILE = "handoff-author.json"
# The process name Claude Code runs as, read from /proc/<pid>/comm. The
# T-0042 spike (Claude Code 2.1.283, Linux) measured it as the nearest
# ancestor of every hook, the same across /clear and different per terminal.
CLAUDE_COMM = "claude"
# A PreCompact record older than this does not describe the compact that
# just happened.
PRECOMPACT_MAX_AGE = 600

_RESUME_LINE_RE = re.compile(r"^resume:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
# [0-9], not \d: in a str pattern \d is any Unicode decimal digit.
_TICKET_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
_GOAL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _refuse(reason):
    return {"ok": False, "command": "", "arg": "", "kind": "", "reason": reason}


_SKELETON_GOAL_RE = re.compile(r"/crew:autopilot --goal [a-z0-9][a-z0-9-]{0,63}")


def _skeleton_goal_header(text):
    """T-0056 review r5: the PreCompact skeleton's header (before its first
    blank line, so before Changed files) may carry exactly the running goal's
    line; then only that header is read. Any other text comes back as it was."""
    if crew_autocycle.SKELETON_MARK not in (text or ""):
        return text
    header = text.replace("\r\n", "\n").split("\n\n", 1)[0]
    found = _RESUME_LINE_RE.findall(header)
    if len(found) == 1 and _SKELETON_GOAL_RE.fullmatch(found[0].strip()):
        return header
    return text


def parse_resume(text):
    """{ok, command, arg, kind, reason} for the handoff `text`.

    Exactly one `resume:` line, one allowlisted command, and the one argument
    its kinds allow; anything else is refused with a reason. Reasons are
    fixed strings: nothing from the line is echoed back into them.

    The automatic PreCompact skeleton is refused whole, before any line is
    read: its Changed files list is bare `git diff` / `git ls-files` output,
    so a file named `resume: /crew:status` would otherwise be its resume
    line (review round 4, T-0006). It names no next action by construction,
    except the one goal line (T-0056) its header may carry, which is the
    only line read from it."""
    text = _skeleton_goal_header(text)
    if crew_autocycle.SKELETON_MARK in (text or ""):
        return _refuse("the handoff is the automatic PreCompact skeleton; it names no next action")
    lines = _RESUME_LINE_RE.findall(text or "")
    if not lines:
        return _refuse("no resume line")
    if len(lines) > 1:
        return _refuse(f"{len(lines)} resume lines")
    tokens = lines[0].split()
    if not tokens:
        return _refuse("empty resume line")
    if tokens == ["none"]:
        return _refuse("resume: none")
    command, rest = tokens[0], tokens[1:]
    if command in EXCLUDED:
        return _refuse(f"{command} is excluded from auto-resume")
    kinds = dict(RESUME_COMMANDS).get(command)
    if kinds is None:
        return _refuse("the resume line names a command that is not an allowlisted /crew: command")
    kinds = kinds.split("|")
    if not rest:
        if "none" in kinds:
            return {"ok": True, "command": command, "arg": "", "kind": "none", "reason": ""}
        return _refuse(f"{command} needs a ticket id")
    if rest[0] == "--goal":
        if "goal" not in kinds:
            return _refuse(f"{command} takes a ticket id, not --goal")
        if len(rest) < 2 or not _GOAL_SLUG_RE.match(rest[1]):
            return _refuse("--goal needs a goal slug of a-z, 0-9 and -")
        if len(rest) > 2:
            return _refuse("extra text after the command")
        return {"ok": True, "command": command, "arg": rest[1], "kind": "goal", "reason": ""}
    if "ticket" not in kinds:
        return _refuse(f"{command} takes no argument: extra text after the command")
    if not _TICKET_ID_RE.match(rest[0]):
        return _refuse("the ticket id is not of the form ABC-123")
    if len(rest) > 1:
        return _refuse("extra text after the command")
    return {"ok": True, "command": command, "arg": rest[0], "kind": "ticket", "reason": ""}


def render(parsed):
    """The prompt, rebuilt from parsed tokens only; "" for a refused parse."""
    if not parsed.get("ok"):
        return ""
    command, arg, kind = parsed["command"], parsed["arg"], parsed["kind"]
    if kind == "goal":
        return f"{command} --goal {arg}"
    if kind == "ticket":
        return f"{command} {arg}"
    return command


# --------------------------------------------------------------------------
# the opt-in

def _load(path):
    """A JSON object from `path`, or {} when absent, malformed, or not an object."""
    text = read_text(path)
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _auto(cfg):
    block = cfg.get("resume")
    return block.get("auto") if isinstance(block, dict) else None


def settings(root, global_path=None):
    """{armed, reason}. A MACHINE switch a repo can veto and never grant:
    armed only when `~/.claude/crew/config.json` says `resume.auto: true`
    (the boolean, not the string) and neither `.crew/crew.json` nor
    `.crew/config.json` says `false`. A repo `true` arms nothing, because a
    cloned repo must not start unattended work on someone else's machine.
    `resolve_config`'s precedence is deliberately not used here."""
    machine = _load(global_path or crew_state.GLOBAL_CONFIG_PATH)
    if _auto(machine) is not True:
        return {"armed": False, "reason": "resume.auto is not true in ~/.claude/crew/config.json"}
    for name in ("crew.json", "config.json"):
        if _auto(_load(crew_common.repo_config_file(root, name))) is False:
            return {"armed": False, "reason": f"resume.auto is false in .crew/{name}"}
    return {"armed": True, "reason": ""}


# --------------------------------------------------------------------------
# where the state lives

def state_dir(root):
    return crew_context.state_dir(root)


def state_path(root):
    return os.path.join(state_dir(root), STATE_FILE)


def author_path(root):
    return os.path.join(state_dir(root), AUTHOR_FILE)


def author_stuck_path(root):
    """The marker `record_author` leaves when a write failed and the previous
    author record could be neither removed nor blanked: that record may vouch
    for a note its session no longer wrote last, so `_author_refusal` waits
    while the marker stands. Not a `precompact-*` name, so the PreCompact
    prune never removes it; only an author write that lands does (T-0069)."""
    return author_path(root) + ".stuck"


def _worktree_key(root):
    top = git_out(root, "rev-parse", "--show-toplevel")
    return os.path.normcase(os.path.realpath(top or root))


# --------------------------------------------------------------------------
# which session wrote the handoff

def _proc_start(pid):
    """/proc/<pid>/stat field 22 (start time in clock ticks), or None."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
            return int(handle.read().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


def session_process(pid=None):
    """{pid, start} of the nearest ancestor that is the Claude Code process,
    or None when none is found or /proc cannot say -- always None on native
    Windows, and on any host without /proc. The start time is part of the
    identity so a reused pid is a different process. No environment
    override: a variable can be copied from one session into another."""
    if os.name == "nt":
        return None
    for candidate in crew_autocycle.ancestors(pid):
        try:
            with open(f"/proc/{candidate}/comm", encoding="utf-8", errors="replace") as handle:
                comm = handle.read().strip()
        except OSError:
            return None
        if comm == CLAUDE_COMM:
            start = _proc_start(candidate)
            return None if start is None else {"pid": candidate, "start": start}
    return None


def _author_entry(root):
    """This worktree's author record: {} when there is no file or no entry,
    None when the file cannot be stat'ed, read or parsed, or is not the shape
    record_author writes. None is an unknown, never "nobody wrote it"."""
    path = author_path(root)
    absent = _absent(path)
    if absent is None:
        return None
    if absent:
        return {}
    data = _read_author(path)
    if data is None:
        return None
    entry = data["worktrees"].get(_worktree_key(root), {})
    return entry if isinstance(entry, dict) else None


def _read_author(path):
    """The author file's object, or None when it is not the shape written."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.loads(handle.read())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("worktrees", {}), dict):
        return None
    data.setdefault("worktrees", {})
    return data


def record_author(root, session_id, handoff_path):
    """(ok, reason). Record that `session_id`, in this Claude Code process,
    just wrote the handoff at `handoff_path`. The PostToolUse hook calls it
    after a Write/Edit/MultiEdit of the handoff on an armed machine.

    The note is read ONCE, under the lock, through the same reader `decide`'s
    caller uses, so the recorded sha is the sha `decide` computes. A note that
    cannot be read, or a write that fails, leaves NO entry for this worktree
    (the previous file is removed, or else blanked, where possible): a
    missing entry or an empty file waits, while a stale one would vouch for a
    note its session never saw. An author
    file that cannot be read is replaced -- it holds no history, only the
    latest writer per worktree, and a lost entry for another worktree only
    makes that worktree wait.

    A lock that cannot be taken drops the whole file -- removed, or blanked
    in place where the directory refuses the removal -- unlocked: this session
    did write the note, and the entry already there -- possibly another
    session's for the same text -- must not keep vouching for it (review
    round 1, T-0042). Unlinking races no reader into a torn file, and a
    reader that meets the blanked file reads it as unreadable and waits; the
    residual race is a holder that read identical text before this write
    and replaces the file after the drop, which content cannot tell apart."""
    path = author_path(root)
    lock = path + ".lock"
    if not crew_context.acquire_lock(lock):
        if not _drop_author(path):
            return False, "could not take the handoff-author lock, and the previous record may still stand"
        return False, "could not take the handoff-author lock"
    try:
        key = _worktree_key(root)
        data = _read_author(path) if _absent(path) is False else None
        worktrees = data["worktrees"] if data else {}
        text = read_text(handoff_path)
        entry = None
        if isinstance(session_id, str) and session_id and text is not None:
            entry = {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "session_id": session_id,
                     "process": session_process(), "at": int(time.time())}
        if entry is None:
            worktrees.pop(key, None)
        else:
            worktrees[key] = entry
        body = json.dumps({"worktrees": worktrees}, sort_keys=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.replace(tmp, path)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            # With or without an entry of its own: a write that was to
            # REMOVE this worktree's entry failed too (review round 1, T-0042).
            dropped = "" if _drop_author(path) else ", and the previous record may still stand"
            return False, f"handoff-author.json was not written: {exc.__class__.__name__}{dropped}"
        # The file is current again: a stuck marker from an earlier failure no
        # longer describes it. One that cannot be removed keeps every resume
        # waiting, which is the safe side.
        try:
            os.unlink(author_stuck_path(root))
        except OSError:
            pass
        if entry is None:
            return False, "the handoff could not be read, or no session id was given"
        return True, ""
    finally:
        crew_context.release_lock(lock)


def _drop_author(path):
    """A failed write must not leave the previous entry vouching for the new
    note. Removing the whole file is tried first: it needs no write of the
    file, only of its directory, and an author file that is gone makes every
    worktree wait. When the directory refuses that, the file is blanked in
    place (`_blank`), which needs a writable file but not a writable
    directory; an empty author file reads as unreadable and waits too
    (T-0069, T-0042 review round 2). True when no record is left vouching,
    False when the old file may still be there -- and then the stuck marker
    is left beside it (`_mark_author_stuck`), so `_author_refusal` still
    waits rather than trust it."""
    if _unlink_author(path):
        return True
    if _blank(path):
        return True
    _mark_author_stuck(path)
    return False


def _mark_author_stuck(author):
    """Leave `<author>.stuck` (`author_stuck_path`) for `_author_refusal`.
    Best effort. A marker that cannot be written either -- the usual case,
    the same read-only directory -- leaves `_author_refusal`'s
    replaceability check as the refusal: a record that neither its file nor
    its directory lets anyone replace or remove can have outlived a later
    write, so it is not trusted (`_FROZEN_AUTHOR`). True when written.

    Accepted residual (CONFIG.md, "Accepted risks"): when the unlink, the
    blank and this marker write all fail while `os.access` still reports
    the file or its directory writable -- EIO, ENOSPC, an immutable
    attribute, a Windows file held open -- nothing marks the record, and
    the stale author record is trusted."""
    path = author + ".stuck"
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": int(time.time())}))
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    return True


def _unlink_author(path):
    """True when nothing is left at `path`, False when the unlink was refused."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _absent(path):
    """True when nothing is at `path`, False when something is, None when
    that cannot be told. Only the kernel saying "no such entry"
    (FileNotFoundError, or NotADirectoryError for a file where a directory
    on the path should be) is absence; any other stat error -- a directory
    this user cannot search -- is an unknown. `os.path.lexists` returns
    False for both, which read "cannot tell" as "nothing there" (review
    round 4, T-0006)."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return None
    return False


def _read_state(root):
    """The resume-state object: {} when there is no file, None when there is
    one that cannot be read, does not parse, or is not the shape record_run
    writes, or when whether there is one cannot be told. None is an unknown
    -- never "nothing was resumed" -- because the consumed-once and loop
    guards read their history from here (review rounds 3 and 4, T-0006)."""
    path = state_path(root)
    absent = _absent(path)
    if absent is None:
        return None
    if absent:
        return {}
    try:
        with open(path, encoding="utf-8-sig") as handle:
            state = json.loads(handle.read())
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or not isinstance(state.get("worktrees"), dict):
        return None
    return state


def _entry(state, key):
    """This worktree's entry: {} when it has none, None when `state` is
    unknown or the entry is not the shape record_run writes. A PARTIAL entry
    -- "consumed" or "last", or last's prompt or fingerprint, missing -- is
    not that shape: read as defaults it said "nothing consumed, no loop
    history", which is the fresh state it cannot vouch for (T-0042)."""
    if state is None:
        return None
    worktrees = state.get("worktrees", {})
    if key not in worktrees:
        return {}
    entry = worktrees[key]
    if not isinstance(entry, dict) or not isinstance(entry.get("consumed"), list):
        return None
    last = entry.get("last")
    if not isinstance(last, dict) or not isinstance(last.get("prompt"), str) \
            or not isinstance(last.get("fingerprint"), str):
        return None
    return entry


_UNREADABLE_AUTHOR = "handoff-author.json could not be read (or its directory cannot be searched)"
_STUCK_AUTHOR = ("a later handoff write could not replace or remove handoff-author.json "
                 "(handoff-author.json.stuck), so its record may vouch for a note its session "
                 "did not write last; it clears when a later author record lands, or "
                 "delete handoff-author.json.stuck by hand")
_FROZEN_AUTHOR = ("handoff-author.json can be neither replaced nor removed (the file and its "
                  "directory are read-only), so its record may have outlived a later handoff write")
_OTHER_SESSION = "the handoff was written by another session"


def _author_refusal(root, payload, sha):
    """Why this session may not resume this note, or "" when it wrote it.

    `compact` keeps its session_id, so it is bound by that; `clear` gets a
    new session_id, so it is bound by the Claude Code process (T-0042 spike).
    An unknown on either side is a refusal, never a match."""
    entry = _author_entry(root)
    if entry is None:
        return _UNREADABLE_AUTHOR
    if not entry:
        return "no record of which session wrote this handoff"
    # A record a later write could not invalidate is never trusted: the
    # marker says so when it could be written, and when it could not, a
    # record nobody can replace or remove is as good as marked (T-0069).
    if _absent(author_stuck_path(root)) is not True:
        return _STUCK_AUTHOR
    path = author_path(root)
    if not (os.access(path, os.W_OK) or os.access(os.path.dirname(path), os.W_OK)):
        return _FROZEN_AUTHOR
    if entry.get("sha256") != sha:
        return "the handoff changed since its author session wrote it"
    if payload.get("source") == "compact":
        mine = payload.get("session_id")
        if not isinstance(mine, str) or not mine or entry.get("session_id") != mine:
            return _OTHER_SESSION
        return ""
    me = session_process()
    if me is None:
        return "this session's process could not be identified"
    if entry.get("process") != me:
        return _OTHER_SESSION
    return ""


_UNREADABLE_STATE = ("resume-state.json could not be read (or its directory cannot be searched) - "
                     "fix the permissions or move it aside to reset auto-resume")


def _already(entry, sha, prompt, fingerprint):
    """The reason `entry` forbids running (sha, prompt, fingerprint) again,
    or "" when it does not. The one statement of both guards, asked by
    `decide` and again by `record_run` under its lock."""
    if sha in entry.get("consumed", []):
        return "this handoff was already resumed"
    last = entry.get("last", {})
    if last.get("prompt") == prompt and last.get("fingerprint") == fingerprint:
        return "same command, no progress since the last auto-resume - waiting for a human"
    return ""


# --------------------------------------------------------------------------
# progress

def _file_digest(path):
    """sha256 hex of a file, "absent" when it does not exist, None when it
    exists and cannot be read (an unknown, never a value)."""
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except FileNotFoundError:
        return "absent" if not os.path.islink(path) else None
    except OSError:
        return None


def _index_rows(root, ticket):
    """The ticket's INDEX.md row(s); "" when there is no INDEX.md, None when
    there is one and it cannot be read, or whether there is one cannot be
    told -- an unknown, never "no rows"."""
    path = os.path.join(root, ".work", "INDEX.md")
    absent = _absent(path)
    if absent is None:
        return None
    if absent:
        return ""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except (OSError, ValueError):
        return None
    if not ticket:
        return text
    pattern = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(ticket)}(?![0-9])")
    return "\n".join(line for line in text.splitlines() if pattern.search(line))


def progress_fingerprint(root, ticket, goal=None):
    """sha256 over everything that moves when a ticket makes progress, or
    None when any part cannot be read -- and None is never progress.

    HEAD, every file in the ticket's folder, live or archived in `Complete/`
    (path and content; could-not-tell is None, L-0509), the
    ticket's approval and review receipts under `<git-common-dir>/crew/`, its
    `.work/INDEX.md` row(s), and `.work/autopilot/<goal>.json` for a goal. A
    bare command (no ticket) fingerprints HEAD and the whole INDEX.md."""
    head = git_out(root, "rev-parse", "HEAD")
    if not head:
        return None
    parts = [("HEAD", head)]
    if ticket:
        tdir, where, _ = crew_common.locate_ticket(root, ticket)
        if where not in (crew_common.LIVE, crew_common.COMPLETE):
            return None
        unlisted = []
        for base, dirs, files in os.walk(tdir, onerror=unlisted.append):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(base, name)
                digest = _file_digest(path)
                if digest is None or digest == "absent":
                    return None
                parts.append((os.path.relpath(path, tdir).replace("\\", "/"), digest))
        if unlisted:
            # A directory os.walk could not list: its files are missing from
            # the fingerprint, and a fingerprint that changed for that reason
            # would read as progress.
            return None
        common = state_dir(root)
        for label, path in (("approval", os.path.join(common, "tickets", ticket, "approval.json")),
                            ("review", os.path.join(common, "review", ticket + ".json"))):
            digest = _file_digest(path)
            if digest is None:
                return None
            parts.append((label, digest))
    if goal:
        digest = _file_digest(os.path.join(root, ".work", "autopilot", goal + ".json"))
        if digest is None:
            return None
        parts.append(("goal", digest))
    rows = _index_rows(root, ticket)
    if rows is None:
        return None
    parts.append(("index", rows))
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# the decision

_BRANCH_RE = crew_state._HANDOFF_BRANCH_RE  # pylint: disable=protected-access
_HEAD_RE = crew_state._HANDOFF_HEAD_RE  # pylint: disable=protected-access


def _decision(action, reason="", prompt="", sha="", fingerprint=None):
    return {"action": action, "prompt": prompt, "reason": reason,
            "handoff_sha256": sha, "fingerprint": fingerprint}


def precompact_path(root, session):
    return os.path.join(state_dir(root), f"precompact-{crew_autocycle.session_key(session)}.json")


def stuck_path(root, session):
    """The marker a PreCompact leaves when it could not replace this
    session's record: the record that survived says nothing about the latest
    compact. `.stuck`, not `.json`, so the shells' `precompact-*.json`
    sweeps never remove it; pruned by age with the records."""
    return os.path.join(state_dir(root), f"precompact-{crew_autocycle.session_key(session)}.stuck")


def _mark_stuck(root, session):
    """Best effort: a marker that cannot be written leaves _compact_was_manual's
    os.access check as the only refusal (an accepted risk, CONFIG.md §14a)."""
    path = stuck_path(root, session)
    tmp = f"{path}.{os.getpid()}.tmp"
    text = json.dumps({"at": int(time.time())})
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def write_precompact_record(root, payload):
    """PreCompact's note of how this compaction started, for `decide`.

    Both `handoff-write` flavours call this (through the `precompact` CLI,
    after their per-event claim) with the raw PreCompact payload: the
    `trigger` as given (`manual` for a typed /compact, `auto` otherwise; a
    missing one is `auto`, the way handoff-write.ps1 already reads it),
    keyed on `session_id` -- measured stable across /compact. No session, no
    record: a compact that cannot be tied to its session never resumes.
    Best effort; a failed write only means the compact waits."""
    session = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(session, str) or not session:
        return False
    trigger = payload.get("trigger")
    trigger = trigger[:32] if isinstance(trigger, str) and trigger else "auto"
    path = precompact_path(root, session)
    crew_context.prune_precompact(root)
    # The previous record goes first, so a write that fails below leaves NO
    # record (not manual) rather than an older `manual` one that would make
    # this compaction look typed. The shell flavours remove it too, before
    # python is even looked for. A record that cannot be removed is emptied
    # in place instead (an empty record is not manual); one that can be
    # neither leaves the stuck marker, which _compact_was_manual honours
    # (review round 4, T-0006: recorded, not predicted with os.access).
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        if not _blank(path):
            _mark_stuck(root, session)
            return False
    text = json.dumps({"trigger": trigger, "at": int(time.time())}, sort_keys=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    # This session's record is current again. A marker that cannot be
    # removed stays, and that session's compacts keep waiting.
    try:
        os.unlink(stuck_path(root, session))
    except OSError:
        pass
    return True


def _blank(path):
    """Empty `path` in place. Here truncate-at-open IS the point: nothing is
    written after it, so an empty file -- which reads as not manual -- is the
    whole result. False when even that is refused."""
    try:
        with open(path, "w", encoding="utf-8"):
            pass
    except OSError:
        return False
    return True


def _compact_was_manual(root, session):
    """True only for a record of THIS session that says `manual` and is at
    most PRECOMPACT_MAX_AGE old. An automatic compaction may continue the
    in-flight turn, so resuming after one would double-drive it; absent,
    unreadable, old or unreplaceable means not manual."""
    if not isinstance(session, str) or not session:
        return False
    path = precompact_path(root, session)
    # A later PreCompact that could not replace the record said so; a marker
    # whose presence cannot be told is as good as one that is there.
    if _absent(stuck_path(root, session)) is not True:
        return False
    # A record that neither its file nor its directory lets anyone replace
    # could have survived a later PreCompact that failed to remove it, so it
    # says nothing about the LATEST compact (review round 2, T-0006).
    if not (os.access(path, os.W_OK) or os.access(os.path.dirname(path), os.W_OK)):
        return False
    record = _load(path)
    at = record.get("at")
    if record.get("trigger") != "manual" or isinstance(at, bool) or not isinstance(at, (int, float)):
        return False
    return 0 <= time.time() - at <= PRECOMPACT_MAX_AGE


def decide(root, payload, handoff_text, plugin_root, global_path=None, archived=False, stale=False):
    """{action: run|wait|off, prompt, reason, handoff_sha256, fingerprint}.

    READ-ONLY: writes nothing, so a decision that is only NAMED to a human
    never uses up the handoff. `record_run` is the one writer. The checks run
    in this order and the first failure wins; every branch that cannot tell
    returns `wait`, never `run`."""
    armed = settings(root, global_path)
    if not armed["armed"]:
        return _decision("off", armed["reason"])
    source = payload.get("source") or "startup"
    if source not in RESUME_SOURCES:
        return _decision("off", f"source {source} never auto-resumes")
    if source == "compact" and not _compact_was_manual(root, payload.get("session_id")):
        return _decision("wait", "compact was not a manual /compact")
    if archived:
        return _decision("wait", "the handoff was archived as stale")
    if stale:
        return _decision("wait", "the handoff is stale (crew_state.handoff_staleness)")
    if not (handoff_text or "").strip():
        return _decision("wait", "no handoff note")
    sha = hashlib.sha256(handoff_text.encode("utf-8")).hexdigest()
    parsed = parse_resume(handoff_text)
    if not parsed["ok"]:
        return _decision("wait", parsed["reason"], sha=sha)
    prompt = render(parsed)
    if parsed["kind"] == "goal":
        # L-0658: a goal moves across ticket branches, so a goal handoff is
        # judged by its goal file's run state, never by branch: and head:.
        refused = crew_goal_state.handoff_refusal(root, parsed["arg"])[1]
        if refused:
            return _decision("wait", refused, prompt, sha)
        return _decide_rest(root, payload, parsed, prompt, sha, plugin_root)
    branch_line = _BRANCH_RE.search(handoff_text)
    branch = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch_line or not branch or branch_line.group(1) != branch:
        return _decision("wait", "the handoff's branch: line does not match the checkout", prompt, sha)
    head_line = _HEAD_RE.search(handoff_text)
    head = git_out(root, "rev-parse", "HEAD")
    if not head_line or not head or not head.lower().startswith(head_line.group(1).lower()):
        return _decision("wait", "the handoff's head: line does not match HEAD", prompt, sha)
    return _decide_rest(root, payload, parsed, prompt, sha, plugin_root)


def _decide_rest(root, payload, parsed, prompt, sha,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 plugin_root):
    """`decide` once the note is bound to this checkout: by branch and head
    for the ticket form, by the goal file for the goal form (L-0658)."""
    ticket = parsed["arg"] if parsed["kind"] == "ticket" else None
    goal = parsed["arg"] if parsed["kind"] == "goal" else None
    where, why = (crew_common.locate_ticket(root, ticket)[1:]) if ticket else (None, None)
    if where == crew_common.COULD_NOT_TELL:
        return _decision("wait", f"could not tell where {ticket} lives: {why}", prompt, sha)
    if where == crew_common.ABSENT:
        return _decision("wait", f".work/tickets/{ticket}/ does not exist (nor under "
                         f"{crew_common.ARCHIVE_DIR}/)", prompt, sha)
    name = parsed["command"].split(":", 1)[1]
    if not os.path.isfile(os.path.join(plugin_root, "commands", name + ".md")):
        return _decision("wait", f"{parsed['command']} is not installed", prompt, sha)
    refused = _author_refusal(root, payload, sha)
    if refused:
        return _decision("wait", refused, prompt, sha)
    entry = _entry(_read_state(root), _worktree_key(root))
    if entry is None:
        return _decision("wait", _UNREADABLE_STATE, prompt, sha)
    fingerprint = progress_fingerprint(root, ticket, goal)
    reason = _already(entry, sha, prompt, fingerprint)
    if reason:
        return _decision("wait", reason, prompt, sha, fingerprint)
    if fingerprint is None:
        return _decision("wait", "the progress fingerprint could not be computed", prompt, sha)
    return _decision("run", "", prompt, sha, fingerprint)


# --------------------------------------------------------------------------
# the one writer

def record_run(root, decision):
    """(ok, reason). The ONLY writer of `<git-common-dir>/crew/resume-state.json`,
    called by whatever actually STARTS the command (T-0013) -- nothing in
    T-0006 does. Temp file then `os.replace` under a lock. A False return
    means the record did not land, and the caller must then not type: an
    unrecorded run is one the consumed-once and loop guards cannot see.

    Both guards are asked AGAIN here, under the lock, so decide-then-record
    is not a check-then-act race: of two senders holding the same `run`,
    only the first record is ok (review round 3, T-0006). A state file that
    cannot be read is refused, never overwritten."""
    if not isinstance(decision, dict) or decision.get("action") != "run":
        return False, "the decision is not a run"
    sha, prompt = decision.get("handoff_sha256"), decision.get("prompt")
    fingerprint = decision.get("fingerprint")
    if not isinstance(sha, str) or not sha or not isinstance(prompt, str) or not prompt:
        return False, "the decision carries no handoff hash or prompt"
    if not isinstance(fingerprint, str) or not fingerprint:
        return False, "the decision carries no progress fingerprint"
    path = state_path(root)
    lock = path + ".lock"
    if not crew_context.acquire_lock(lock):
        return False, "could not take the resume-state lock"
    try:
        state = _read_state(root)
        key = _worktree_key(root)
        entry = _entry(state, key)
        if entry is None:
            return False, _UNREADABLE_STATE
        refused = _already(entry, sha, prompt, fingerprint)
        if refused:
            return False, refused
        worktrees = state.get("worktrees", {})
        consumed = [c for c in entry.get("consumed", []) if isinstance(c, str)]
        consumed = (consumed + [sha])[-CONSUMED_KEEP:]
        worktrees[key] = {"consumed": consumed,
                          "last": {"prompt": prompt, "fingerprint": fingerprint, "at": int(time.time())}}
        text = json.dumps({"worktrees": worktrees}, sort_keys=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return False, f"resume-state.json was not written: {exc.__class__.__name__}"
        return True, ""
    finally:
        crew_context.release_lock(lock)


# --------------------------------------------------------------------------
# CLI -- T-0013's contract: `decide --json`, then, after it has claimed a
# send, `record --decision-json -`. Exit 0 always; read `action` / `ok`.

def _is_stale(root, cfg, rel, text):
    """crew_state's staleness rule, READ-ONLY: the SessionStart hook archives
    a stale note before `decide` sees it, but this CLI can run without that
    hook having run first, so it applies the same rule without moving
    anything. A rule that cannot be evaluated counts as stale."""
    if not (text or "").strip():
        return False
    try:
        mtime = os.path.getmtime(os.path.join(root, rel))
    except OSError:
        mtime = None
    try:
        return bool(crew_state.handoff_staleness(root, text, cfg, mtime=mtime).get("stale"))
    except Exception:  # pylint: disable=broad-except
        return True


def _plugin_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd")
    dec = sub.add_parser("decide")
    dec.add_argument("--root", default="")
    dec.add_argument("--session", default="")
    dec.add_argument("--source", default="")
    dec.add_argument("--json", action="store_true")
    dec.add_argument("--global-path", default=None)
    dec.add_argument("--plugin-root", default=None)
    rec = sub.add_parser("record")
    rec.add_argument("--root", default="")
    rec.add_argument("--decision-json", default="-")
    pre = sub.add_parser("precompact")
    pre.add_argument("--root", default="")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 0
    try:
        if args.cmd == "decide":
            root = crew_context.find_root(args.root or os.getcwd())
            cfg = crew_context.load_crew_config(root)
            rel, text = crew_context._handoff(root, cfg)  # pylint: disable=protected-access
            payload = {"hook_event_name": "SessionStart", "source": args.source,
                       "session_id": args.session}
            out = decide(root, payload, text, args.plugin_root or _plugin_root(), args.global_path,
                         stale=_is_stale(root, cfg, rel, text))
            print(json.dumps(out, sort_keys=True) if args.json else f"{out['action']}: "
                  f"{out['prompt'] or out['reason']}")
        elif args.cmd == "record":
            raw = sys.stdin.read() if args.decision_json == "-" else args.decision_json
            try:
                decision = json.loads(raw)
            except ValueError:
                decision = None
            root = crew_context.find_root(args.root or os.getcwd())
            ok, reason = record_run(root, decision)
            print(json.dumps({"ok": ok, "reason": reason}, sort_keys=True))
        elif args.cmd == "precompact":
            raw = sys.stdin.buffer.read()
            try:
                payload = json.loads(raw.decode("utf-8-sig", "replace")) if raw.strip() else {}
            except ValueError:
                payload = {}
            write_precompact_record(crew_context.find_root(args.root or os.getcwd()), payload)
    except Exception as exc:  # pylint: disable=broad-except
        print(json.dumps({"action": "wait", "ok": False,
                          "reason": f"internal error: {exc.__class__.__name__}"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
