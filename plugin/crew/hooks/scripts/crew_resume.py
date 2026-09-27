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

from crew_common import git_out, read_text
import crew_autocycle
import crew_context
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
# A PreCompact record older than this does not describe the compact that
# just happened.
PRECOMPACT_MAX_AGE = 600

_RESUME_LINE_RE = re.compile(r"^resume:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
# [0-9], not \d: in a str pattern \d is any Unicode decimal digit.
_TICKET_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
_GOAL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _refuse(reason):
    return {"ok": False, "command": "", "arg": "", "kind": "", "reason": reason}


def parse_resume(text):
    """{ok, command, arg, kind, reason} for the handoff `text`.

    Exactly one `resume:` line, one allowlisted command, and the one argument
    its kinds allow; anything else is refused with a reason. Reasons are
    fixed strings: nothing from the line is echoed back into them."""
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
        if _auto(_load(os.path.join(root, ".crew", name))) is False:
            return {"armed": False, "reason": f"resume.auto is false in .crew/{name}"}
    return {"armed": True, "reason": ""}


# --------------------------------------------------------------------------
# where the state lives

def state_dir(root):
    return crew_context.state_dir(root)


def state_path(root):
    return os.path.join(state_dir(root), STATE_FILE)


def _worktree_key(root):
    top = git_out(root, "rev-parse", "--show-toplevel")
    return os.path.normcase(os.path.realpath(top or root))


def _read_state(root):
    """The resume-state object: {} when there is no file, None when there is
    one that cannot be read, does not parse, or is not the shape record_run
    writes. None is an unknown -- never "nothing was resumed" -- because the
    consumed-once and loop guards read their history from here (review
    round 3, T-0006)."""
    path = state_path(root)
    if not os.path.lexists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as handle:
            state = json.loads(handle.read())
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or not isinstance(state.get("worktrees", {}), dict):
        return None
    return state


def _entry(state, key):
    """This worktree's entry: {} when it has none, None when `state` is
    unknown or the entry is not the shape record_run writes."""
    if state is None:
        return None
    entry = state.get("worktrees", {}).get(key, {})
    if not isinstance(entry, dict) or not isinstance(entry.get("consumed", []), list) \
            or not isinstance(entry.get("last", {}), dict):
        return None
    return entry


_UNREADABLE_STATE = "resume-state.json exists and could not be read - move it aside to reset auto-resume"


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
    there is one and it cannot be read -- an unknown, never "no rows"."""
    path = os.path.join(root, ".work", "INDEX.md")
    if not os.path.lexists(path):
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

    HEAD, every file under `.work/tickets/<ticket>/` (path and content), the
    ticket's approval and review receipts under `<git-common-dir>/crew/`, its
    `.work/INDEX.md` row(s), and `.work/autopilot/<goal>.json` for a goal. A
    bare command (no ticket) fingerprints HEAD and the whole INDEX.md."""
    head = git_out(root, "rev-parse", "HEAD")
    if not head:
        return None
    parts = [("HEAD", head)]
    if ticket:
        tdir = os.path.join(root, ".work", "tickets", ticket)
        if not os.path.isdir(tdir):
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
    # neither is refused by _compact_was_manual as unreplaceable.
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        if not _blank(path):
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
    branch_line = _BRANCH_RE.search(handoff_text)
    branch = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch_line or not branch or branch_line.group(1) != branch:
        return _decision("wait", "the handoff's branch: line does not match the checkout", prompt, sha)
    head_line = _HEAD_RE.search(handoff_text)
    head = git_out(root, "rev-parse", "HEAD")
    if not head_line or not head or not head.lower().startswith(head_line.group(1).lower()):
        return _decision("wait", "the handoff's head: line does not match HEAD", prompt, sha)
    ticket = parsed["arg"] if parsed["kind"] == "ticket" else None
    goal = parsed["arg"] if parsed["kind"] == "goal" else None
    if ticket and not os.path.isdir(os.path.join(root, ".work", "tickets", ticket)):
        return _decision("wait", f".work/tickets/{ticket}/ does not exist", prompt, sha)
    if goal and not os.path.isfile(os.path.join(root, ".work", "autopilot", goal + ".json")):
        return _decision("wait", f".work/autopilot/{goal}.json does not exist", prompt, sha)
    name = parsed["command"].split(":", 1)[1]
    if not os.path.isfile(os.path.join(plugin_root, "commands", name + ".md")):
        return _decision("wait", f"{parsed['command']} is not installed", prompt, sha)
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
