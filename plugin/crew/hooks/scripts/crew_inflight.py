"""crew_inflight.py: in-flight markers, so no two crew runners drive one ticket (T-0049).

Every crew runner -- a workflow lane, a wave lane, an autopilot run, a
priority agent started from the main session -- writes a marker for the
ticket it works before touching anything, and ends it on every exit path.
Autopilot, and every loop that picks tickets, checks before each phase: a
ticket someone else holds is left alone.

    crew_inflight.py begin  --ticket <id> --runner <kind>:<id> [--worktree <p>] [--here]
    crew_inflight.py beat   --ticket <id> --runner <r> [--phase <p>]
    crew_inflight.py end    --ticket <id> --runner <r> [--outcome <text>]
    crew_inflight.py status [--ticket <id> | --all] [--runner <r>] [--json]   read-only
    crew_inflight.py pick   --tickets <id>... --runner <r>                    read-only
    crew_inflight.py lane-lines --ticket <id> --runner <r> --worktree <p>
    crew_inflight.py clear  --ticket <id> --by <name> [--round N] [--reason <text>]
                                                            the OWNER, outside Claude Code

Every command takes `--root` (default: the current directory). A runner is
`<kind>:<id>`, kind one of autopilot, wave, workflow, agent, id
`[A-Za-z0-9._:/@-]{1,120}`; a bare `autopilot` means `autopilot:<session id>`.

Where. `<git-common-dir>/crew/inflight/<TICKET>.json` (the id upper-cased), so
every worktree of a repository sees the same markers, beside `log.jsonl` and
the lock file `.lock`. Every read-modify-write runs under that lock
(crew_holder._locked), and every write is a temp file in the same directory
then os.replace, with the text computed before any file is opened. Claude's
shell cannot hand-edit these: the scope guard refuses a write that names
`<git-common-dir>/crew`.

A marker (schema 1): ticket, state (`working`, `ended` or `cleared`), runner,
holder (crew_holder.current_holder: session, bridge session, pid, pid start,
PID namespace, machine, worktree), worktree and branch the runner works in,
head_at_begin, began_at, heartbeat_at, runner_beat_at and phase. An `ended`
record adds ended_at, head, branch, worktree and outcome; a `cleared` record
cleared_at, cleared_by, reason and released_round.

`holds` answers, for one ticket and one caller:
    free       nothing holds it                 -> go
    mine       this runner and holder hold it   -> go
    live       another runner holds it, heartbeat fresh, pid not gone
    stale      another runner's heartbeat is older than the TTL, or its pid is
               provably gone in its recorded PID namespace; or a dirty
               worktree for the ticket with no live process in it
    elsewhere  the last runner ended in another checkout: continue there
    unknown    could not tell -- an unreadable marker or ledger, a reserved
               review round with no result, a dirty worktree whose processes
               cannot be read, no session id, a git failure, an exception
Everything but free and mine is hands off. Could-not-tell is in flight,
never free. Checked in order: the marker, then the review ledger (the latest
current-plan round reserved with no result, unless the owner released that
round with `clear --round N` after it was reserved), then every OTHER
worktree whose branch is `<TICKET>` or `<TICKET>-*` (case-insensitive) or
whose active-ticket entry is the ticket (a worktree directory that no longer
exists is skipped: it holds no changes). The first signal that is not free
decides; every signal found is listed.

Stale is never taken over. No command adopts or releases another runner's
marker: `clear`, run by the owner from a terminal outside Claude Code
(CLAUDECODE and CLAUDE_CODE_SESSION_ID both absent) and with `--by`, is the
only way one is removed, and it is logged. That signal is spoofable with
`env -u`: a prose control, not an enforced one. `--round N` also releases a
reserved-but-unrecorded review round N for a relaunch; the release is carried
into later markers so the round stays released.

The heartbeat. `begin` starts `beat-loop` detached (a new session on POSIX;
DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP on Windows), T-0030's pattern. It
refreshes heartbeat_at every LOOP_SECONDS while CLAUDE_PID lives with the same
start time and the marker still names this runner and pid, and exits
otherwise; a second loop for the same holder finds the first's lock and exits.
Its log and lock live in crew_holder.private_dir("crew-inflight"). The
runner's own `beat` also sets runner_beat_at, and `status` prints both ages,
so a loop that outlives its lane is visible. The TTL and the interval are
constants, not config.

`status` and `pick` write nothing: no marker, no lock file, no log, and git
runs with GIT_OPTIONAL_LOCKS=0.

Exit codes: 0 ok, free or mine; 1 refused, or live, stale or elsewhere;
2 usage; 3 unknown or could-not-tell. The last line printed is
`result=<state> reason=<...>`. Every marker field printed goes through
crew_holder.safe: markers are written by other runners, and are data.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crew_holder  # pylint: disable=wrong-import-position
import crew_ticket  # pylint: disable=wrong-import-position
import review_ledger  # pylint: disable=wrong-import-position

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_UNKNOWN = 3

SCHEMA = 1
TTL_MINUTES = 30
BEAT_SECONDS = 600
LOOP_SECONDS = max(1, min(BEAT_SECONDS, TTL_MINUTES * 60 // 3))
STATES = ("working", "ended", "cleared")
KINDS = ("autopilot", "wave", "workflow", "agent")
LOG = "log.jsonl"
LOCK = ".lock"
FREE, MINE, LIVE, STALE, ELSEWHERE, UNKNOWN = "free", "mine", "live", "stale", "elsewhere", "unknown"
GO = (FREE, MINE)
_RUNNER_ID = re.compile(r"[A-Za-z0-9._:/@-]{1,120}")
_REQUIRED = {
    "working": ("runner", "holder", "worktree", "began_at", "heartbeat_at"),
    "ended": ("runner", "worktree", "ended_at"),
    "cleared": ("runner", "cleared_at", "cleared_by"),
}
_GIT_TIMEOUT = 30


class UsageError(Exception):
    pass


def _now():
    return crew_holder.utcnow()


def _serialise(record):
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


# --- names and paths -------------------------------------------------------------

def norm_ticket(ticket):
    crew_ticket.check_ticket(ticket)
    return ticket.upper()


def expand_runner(runner):
    """`<kind>:<id>`, checked; a bare `autopilot` is `autopilot:<session id>`,
    or None when there is no session id to name it by."""
    if runner == "autopilot":
        session = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
        return f"autopilot:{session}" if _RUNNER_ID.fullmatch(session) else None
    kind, _, ident = (runner or "").partition(":")
    if kind not in KINDS or not _RUNNER_ID.fullmatch(ident):
        raise UsageError(f"runner {runner!r} is not <kind>:<id> with kind one of {', '.join(KINDS)} "
                         "and id [A-Za-z0-9._:/@-]{1,120}")
    return runner


def inflight_dir(top):
    state = crew_ticket.state_dir(top)
    if not state:
        raise UsageError(f"{top} is not a git repository")
    return os.path.join(state, "inflight")


def marker_path(top, ticket):
    return os.path.join(inflight_dir(top), norm_ticket(ticket) + ".json")


def clear_command(top, ticket, round_number=None):
    extra = f" --round {round_number}" if round_number is not None else ""
    return (f"python3 {os.path.abspath(__file__)} clear --root {top} --ticket {norm_ticket(ticket)} "
            f"--by <your name>{extra}   (from a terminal outside Claude Code)")


# --- git ---------------------------------------------------------------------------

def _git(top, *args):
    """stdout of one git call, stripped, or None when it failed or could not run."""
    env = crew_holder.child_env()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        done = subprocess.run(["git", "-C", top] + list(args), capture_output=True, text=True, check=False,
                              timeout=_GIT_TIMEOUT, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _branch(path):
    if not os.path.isdir(path):
        return None
    return _git(path, "symbolic-ref", "--quiet", "--short", "HEAD") or None


def _head(path):
    if not os.path.isdir(path):
        return None
    return _git(path, "rev-parse", "HEAD")


# --- the marker file -----------------------------------------------------------------

def _valid(record):
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        return "not a schema-1 object"
    if not isinstance(record.get("ticket"), str) or record.get("state") not in STATES:
        return "no ticket or an unknown state"
    missing = [f for f in _REQUIRED[record["state"]] if f not in record]
    if missing:
        return f"missing {', '.join(missing)}"
    if not isinstance(record["runner"], str):
        return "runner is not text"
    if record["state"] == "working":
        holder = record["holder"]
        if not (isinstance(holder, dict) and isinstance(holder.get("session"), str)
                and isinstance(holder.get("machine"), str) and isinstance(holder.get("worktree"), str)):
            return "holder is not a holder"
    return ""


def read_marker(top, ticket):
    """(record, status, reason): status is 'absent', 'ok' or 'unknown'. A path
    that is not a regular file, bad JSON, the wrong shape, or an inflight
    directory that cannot be listed is unknown -- never absent."""
    folder = inflight_dir(top)
    path = marker_path(top, ticket)
    if os.path.lexists(folder):
        try:
            os.listdir(folder)
        except OSError as exc:
            return None, UNKNOWN, f"the inflight directory cannot be listed ({type(exc).__name__})"
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None, "absent", ""
    except OSError as exc:
        return None, UNKNOWN, f"the marker cannot be read ({type(exc).__name__})"
    if not stat.S_ISREG(info.st_mode):
        return None, UNKNOWN, "the marker path is not a regular file"
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, UNKNOWN, f"the marker does not parse ({type(exc).__name__})"
    why = _valid(record)
    if why:
        return None, UNKNOWN, f"the marker is unreadable: {why}"
    return record, "ok", ""


def write_marker(top, ticket, record):
    """Atomic: the text first, then a temp file beside the marker, then os.replace."""
    text = _serialise(record)
    path = marker_path(top, ticket)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def append_log(top, entry):
    line = json.dumps(dict(entry, at=crew_holder.stamp(_now())), sort_keys=True) + "\n"
    with open(os.path.join(inflight_dir(top), LOG), "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def _locked(top):
    folder = inflight_dir(top)
    os.makedirs(folder, exist_ok=True)
    return crew_holder._locked(os.path.join(folder, LOCK))  # pylint: disable=protected-access


# --- holds ---------------------------------------------------------------------------

def _answer(state, ticket, reason, **extra):
    base = {"state": state, "ticket": ticket, "reason": reason, "runner": None, "since": None,
            "worktree": None, "clear": "", "signals": []}
    base.update(extra)
    return base


def _age(stamp_text, now):
    when = crew_holder.parse_stamp(stamp_text)
    return None if when is None else (now - when).total_seconds()


def _marker_signal(top, ticket, record, status, why, me, runner, now, here=False):
    """Design step 1: what the marker alone says."""
    if status == UNKNOWN:
        return _answer(UNKNOWN, ticket, why)
    if status == "absent" or record["state"] == "cleared":
        return _answer(FREE, ticket, "no marker")
    who = {"runner": record.get("runner"), "worktree": record.get("worktree")}
    if record["state"] == "ended":
        caller = crew_ticket.toplevel(top) or os.path.realpath(top)
        mine_wt = os.path.normcase(os.path.realpath(record["worktree"])) == os.path.normcase(caller)
        if not here and not mine_wt and (record.get("branch") is None or record.get("branch") != _branch(caller)):
            return _answer(ELSEWHERE, ticket, f"{record['runner']} ended in another checkout: continue "
                           f"there with cd {record['worktree']} and /crew:autopilot {ticket}",
                           since=record.get("ended_at"), **who)
        return _answer(FREE, ticket, "the last runner ended in this checkout")
    holder = record["holder"]
    since = record.get("began_at")
    if runner is not None and record["runner"] == runner and crew_holder.same_holder(me, holder):
        return _answer(MINE, ticket, "this runner holds it", since=since, **who)
    age = _age(record["heartbeat_at"], now)
    if age is None or age > TTL_MINUTES * 60:
        return _answer(STALE, ticket, f"{record['runner']}'s heartbeat is "
                       f"{'unreadable' if age is None else crew_holder.age_text(age) + ' old'} "
                       f"(TTL {TTL_MINUTES}m): the owner decides; never taken over",
                       since=since, clear=clear_command(top, ticket), **who)
    if crew_holder.probe_holder(holder).state == "gone":
        return _answer(STALE, ticket, f"{record['runner']}'s pid {holder.get('pid')} is gone: the owner "
                       "decides; never adopted", since=since, clear=clear_command(top, ticket), **who)
    return _answer(LIVE, ticket, f"{record['runner']} holds it (heartbeat "
                   f"{crew_holder.age_text(age)} ago)", since=since, **who)


def current_rounds(ledger):
    """Rounds reserved under the current plan: after the latest successor."""
    rounds = ledger.get("rounds") or []
    successors = ledger.get("successors") or []
    after = successors[-1].get("after_round", 0) if successors else 0
    return rounds[after:] if isinstance(after, int) else rounds


def _released(record, number, reserved_at):
    """The owner released round `number` with `clear --round`, after it was reserved."""
    if not record or record.get("released_round") != number:
        return False
    released = crew_holder.parse_stamp(record.get("released_at") or record.get("cleared_at"))
    reserved = crew_holder.parse_stamp(reserved_at)
    return released is not None and reserved is not None and released >= reserved


def _ledger_signal(top, ticket, record):
    """Design step 2: a reserved review round with no result."""
    try:
        ledger = review_ledger.status(top, ticket)
    except (review_ledger.LedgerError, OSError, ValueError) as exc:
        return _answer(UNKNOWN, ticket, f"review ledger unreadable ({type(exc).__name__})")
    if ledger["state"] == review_ledger.UNKNOWN:
        return _answer(UNKNOWN, ticket, "review ledger unreadable")
    rounds = current_rounds(ledger)
    latest = rounds[-1] if rounds else None
    if latest is None or latest.get("status") == "completed":
        return _answer(FREE, ticket, "no reserved round")
    number = latest.get("round")
    if _released(record, number, latest.get("reserved_at")):
        return _answer(FREE, ticket, f"round {number} released by the owner")
    return _answer(UNKNOWN, ticket, f"round {number} reserved with no result: a reviewer is running or "
                   "died; the owner releases it for a relaunch", since=latest.get("reserved_at"),
                   clear=clear_command(top, ticket, number))


def _worktrees(top):
    """[(path, branch_ref_or_None)] from `git worktree list --porcelain`, or None."""
    out = _git(top, "worktree", "list", "--porcelain")
    if out is None:
        return None
    found, path, branch = [], None, None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            path, branch = line[len("worktree "):], None
        elif line.startswith("branch "):
            branch = line[len("branch "):]
        elif not line.strip() and path:
            found.append((path, branch))
            path, branch = None, None
    return found


def _active_map(top):
    path = os.path.join(crew_ticket.state_dir(top) or "", "active-ticket")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_ticket_branch(ref, ticket):
    if not ref:
        return False
    name = ref[len("refs/heads/"):].upper() if ref.startswith("refs/heads/") else ""
    return name == ticket or name.startswith(ticket + "-")


def _own_worktrees(top, marker):
    own = {os.path.normcase(crew_ticket.toplevel(top) or os.path.realpath(top))}
    if marker is not None and marker.get("state") == MINE and marker.get("worktree"):
        own.add(os.path.normcase(os.path.realpath(marker["worktree"])))
    return own


def _worktree_signal(top, ticket, marker):
    """Design step 3: another worktree for the ticket with uncommitted changes."""
    listed = _worktrees(top)
    if listed is None:
        return _answer(UNKNOWN, ticket, "git worktree list failed")
    own = _own_worktrees(top, marker)
    active = {os.path.normcase(os.path.realpath(k)): v for k, v in _active_map(top).items()}
    for path, ref in listed:
        real = os.path.normcase(os.path.realpath(path))
        if real in own or not os.path.isdir(path):
            continue
        entry = active.get(real)
        if not (_is_ticket_branch(ref, ticket) or (isinstance(entry, str) and entry.upper() == ticket)):
            continue
        dirty = _git(path, "status", "--porcelain")
        if dirty is None:
            return _answer(UNKNOWN, ticket, f"git status failed in {path}", worktree=path)
        if not dirty:
            continue
        seen, detail = crew_holder.processes_in(path)
        if seen == "live":
            return _answer(LIVE, ticket, f"{path} has uncommitted changes and live process(es) "
                           f"{', '.join(str(p) for p in detail)} in it", worktree=path,
                           runner=f"process:{detail[0]}")
        if seen == "none":
            return _answer(STALE, ticket, f"{path} has uncommitted changes and no live process seen: "
                           "the owner commits, stashes or removes it", worktree=path)
        return _answer(UNKNOWN, ticket, f"{path} has uncommitted changes and whose they are cannot be "
                       f"told ({detail})", worktree=path)
    return _answer(FREE, ticket, "no other worktree holds changes for it")


def holds(top, ticket, me, runner, now=None, here=False):
    """`{"state", "ticket", "reason", "runner", "since", "worktree", "clear",
    "signals"}` for `ticket` as seen by holder `me` running as `runner`. The
    first non-free signal of marker, ledger, worktrees decides. `me is None`
    turns free and mine into unknown. Any exception is unknown, never free.
    `here` is `begin --here`: an ended record from another checkout reads free,
    and the ledger and worktree signals are still checked. Reads only."""
    try:
        ticket = norm_ticket(ticket)
        now = now or _now()
        record, status, why = read_marker(top, ticket)
        marker = _marker_signal(top, ticket, record, status, why, me, runner, now, here)
        signals = [marker]
        if marker["state"] not in GO:
            answer = marker
        else:
            ledger = _ledger_signal(top, ticket, record)
            signals.append(ledger)
            answer = ledger
            if ledger["state"] in GO:
                trees = _worktree_signal(top, ticket, marker)
                signals.append(trees)
                answer = trees if trees["state"] not in GO else marker
        if me is None and answer["state"] in GO:
            answer = _answer(UNKNOWN, ticket, "cannot tell who is asking: CLAUDE_CODE_SESSION_ID is absent")
        answer = dict(answer, signals=[{"state": s["state"], "reason": s["reason"]} for s in signals])
        return answer
    except Exception as exc:  # pylint: disable=broad-except
        return _answer(UNKNOWN, ticket, f"could not tell ({type(exc).__name__}: {exc})")


def pick(top, tickets, me, runner):
    """The first ticket, in the caller's order, that is free or mine, and every
    one skipped on the way with its state, runner and since. `waiting` when
    none is. Writes nothing and begins nothing."""
    skipped = []
    for ticket in tickets:
        held = holds(top, ticket, me, runner)
        if held["state"] in GO:
            return {"ticket": held["ticket"], "skipped": skipped, "waiting": False}
        skipped.append(held)
    return {"ticket": None, "skipped": skipped, "waiting": True}


# --- printing ------------------------------------------------------------------------

def _result(state, reason):
    print(f"result={state} reason={crew_holder.safe(reason, 400)}")


def _code(state):
    if state in GO:
        return EXIT_OK
    return EXIT_UNKNOWN if state == UNKNOWN else EXIT_REFUSED


def _describe(held, record=None, now=None):
    s = crew_holder.safe
    parts = [f"{held['ticket']} {held['state']}"]
    if held.get("runner"):
        parts.append(f"runner={s(held['runner'])}")
    if held.get("since"):
        parts.append(f"since={s(held['since'])}")
    if held.get("worktree"):
        parts.append(f"worktree={s(held['worktree'])}")
    if record and record.get("state") == "working":
        holder = record["holder"]
        parts.append(f"holder={s(holder.get('session'))}@{s(holder.get('machine'))} pid={s(holder.get('pid'))}")
        now = now or _now()
        for field in ("heartbeat_at", "runner_beat_at"):
            age = _age(record.get(field), now)
            label = field.replace("_at", "")
            parts.append(f"{label}={'never' if age is None else crew_holder.age_text(age) + ' ago'}")
        if record.get("phase"):
            parts.append(f"phase={s(record['phase'])}")
    line = " ".join(parts)
    print(line)
    print(f"  {s(held['reason'], 400)}")
    if held.get("clear"):
        print(f"  owner clears it with: {s(held['clear'], 400)}")


# --- commands ------------------------------------------------------------------------

def _top(root):
    top = crew_ticket.toplevel(root)
    if not top:
        raise UsageError(f"{root} is not a git repository")
    return top


def _carry_release(new, old):
    """Keep an owner's round release across later markers."""
    if old and old.get("released_round") is not None:
        new["released_round"] = old["released_round"]
        new["released_at"] = old.get("released_at") or old.get("cleared_at")
    return new


def cmd_begin(args):
    top = _top(args.root)
    ticket = norm_ticket(args.ticket)
    me = crew_holder.current_holder(top)
    runner = expand_runner(args.runner)
    if me is None or runner is None:
        _result(UNKNOWN, "cannot tell who is asking: CLAUDE_CODE_SESSION_ID is absent; nothing written")
        return EXIT_UNKNOWN
    worktree = os.path.realpath(args.worktree or top)
    with _locked(top):
        held = holds(top, ticket, me, runner, here=args.here)
        if held["state"] not in GO:
            _describe(held)
            if held["state"] == ELSEWHERE:
                print("  begin --here continues it in this checkout instead (the owner's override)")
            _result(held["state"], held["reason"] + "; nothing written")
            return _code(held["state"])
        old, _status, _why = read_marker(top, ticket)
        stamp = crew_holder.stamp(_now())
        if held["state"] == MINE and old and old.get("state") == "working":
            record = dict(old, heartbeat_at=stamp)
            event = "refresh"
        else:
            record = _carry_release({
                "schema": SCHEMA, "ticket": ticket, "state": "working", "runner": runner, "holder": me,
                "worktree": worktree, "branch": _branch(worktree), "head_at_begin": _head(worktree),
                "began_at": stamp, "heartbeat_at": stamp, "runner_beat_at": None, "phase": None,
            }, old)
            event = "begin"
        write_marker(top, ticket, record)
        append_log(top, {"event": event, "ticket": ticket, "runner": runner, "session": me["session"],
                         "worktree": worktree})
    if not args.no_heartbeat:
        _start_loop(top, ticket, runner, me)
    _result(held["state"], f"{event}: {runner} holds {ticket}")
    return EXIT_OK


def _holder_change(args, change):
    """Run `change(record, stamp)` on this runner's own working marker, under the lock."""
    top = _top(args.root)
    ticket = norm_ticket(args.ticket)
    me = crew_holder.current_holder(top)
    runner = expand_runner(args.runner)
    if me is None or runner is None:
        _result(UNKNOWN, "cannot tell who is asking: CLAUDE_CODE_SESSION_ID is absent; nothing written")
        return EXIT_UNKNOWN
    with _locked(top):
        record, status, why = read_marker(top, ticket)
        if status == UNKNOWN:
            _result(UNKNOWN, why + "; nothing written")
            return EXIT_UNKNOWN
        if (status == "absent" or record["state"] != "working" or record["runner"] != runner
                or not crew_holder.same_holder(me, record["holder"])):
            holder = "nobody" if status == "absent" else f"{record['runner']} ({record['state']})"
            _result("refused", f"{ticket} is not held by {runner} in this session and process (it is "
                    f"{holder}); only the holder beats or ends a marker; nothing written")
            return EXIT_REFUSED
        new, event = change(record, crew_holder.stamp(_now()), top)
        write_marker(top, ticket, new)
        if event:
            append_log(top, {"event": event, "ticket": ticket, "runner": runner, "session": me["session"],
                             "outcome": new.get("outcome")})
    _result("ok", f"{event or 'beat'}: {ticket}")
    return EXIT_OK


def cmd_beat(args):
    def change(record, stamp, _top_dir):
        new = dict(record, heartbeat_at=stamp, runner_beat_at=stamp)
        if args.phase:
            new["phase"] = args.phase
        return new, None
    return _holder_change(args, change)


def cmd_end(args):
    def change(record, stamp, _top_dir):
        worktree = record["worktree"]
        new = _carry_release({
            "schema": SCHEMA, "ticket": record["ticket"], "state": "ended", "runner": record["runner"],
            "holder": record["holder"], "worktree": worktree, "branch": _branch(worktree),
            "head": _head(worktree), "began_at": record.get("began_at"), "ended_at": stamp,
            "outcome": args.outcome or "",
        }, record)
        return new, "end"
    return _holder_change(args, change)


def cmd_clear(args):
    top = _top(args.root)
    ticket = norm_ticket(args.ticket)
    if not crew_holder.owner_signal():
        _result("refused", "clear is the owner's, from a terminal outside Claude Code (CLAUDECODE and "
                "CLAUDE_CODE_SESSION_ID both absent); nothing written")
        return EXIT_REFUSED
    if not (args.by or "").strip():
        _result("refused", "clear needs --by <who is clearing>; nothing written")
        return EXIT_REFUSED
    with _locked(top):
        old, _status, _why = read_marker(top, ticket)
        stamp = crew_holder.stamp(_now())
        record = {"schema": SCHEMA, "ticket": ticket, "state": "cleared",
                  "runner": (old or {}).get("runner") or "none", "cleared_at": stamp,
                  "cleared_by": args.by.strip(), "reason": args.reason or "", "released_round": args.round}
        if args.round is None:
            _carry_release(record, old)
        else:
            record["released_at"] = stamp
        write_marker(top, ticket, record)
        append_log(top, {"event": "clear", "ticket": ticket, "by": record["cleared_by"],
                         "runner": record["runner"], "was": (old or {}).get("state"),
                         "released_round": args.round, "reason": record["reason"]})
    _result("ok", f"{ticket} cleared by {record['cleared_by']}"
            + (f"; review round {args.round} released" if args.round is not None else ""))
    return EXIT_OK


def cmd_status(args):
    top = _top(args.root)
    me = crew_holder.current_holder(top)
    runner = expand_runner(args.runner) if args.runner else None
    if args.all:
        folder = inflight_dir(top)
        try:
            tickets = sorted(n[:-5] for n in os.listdir(folder) if n.endswith(".json"))
        except FileNotFoundError:
            tickets = []
        except OSError as exc:
            _result(UNKNOWN, f"the inflight directory cannot be listed ({type(exc).__name__})")
            return EXIT_UNKNOWN
    elif args.ticket:
        tickets = [args.ticket]
    else:
        raise UsageError("status needs --ticket <id> or --all")
    order = (FREE, MINE, ELSEWHERE, LIVE, STALE, UNKNOWN)
    worst, found = FREE, []
    for ticket in tickets:
        held = holds(top, ticket, me, runner)
        found.append(held)
        worst = max(worst, held["state"], key=order.index)
        if not args.json:
            record, _status, _why = read_marker(top, ticket)
            _describe(held, record)
    if args.json:
        print(json.dumps(found, indent=2, sort_keys=True))
    if not tickets:
        print("no in-flight markers")
    _result(worst, f"{len(tickets)} ticket(s) checked")
    return _code(worst)


def cmd_pick(args):
    top = _top(args.root)
    me = crew_holder.current_holder(top)
    runner = expand_runner(args.runner)
    found = pick(top, args.tickets, me, runner)
    s = crew_holder.safe
    for held in found["skipped"]:
        print(f"skipped {held['ticket']} {held['state']} {s(held.get('runner') or '-')} since "
              f"{s(held.get('since') or '-')} {s(held.get('worktree') or '')}".rstrip())
        print(f"  {s(held['reason'], 400)}")
    if found["waiting"]:
        print("waiting=1")
        _result("waiting", "every ticket given is in flight; waiting on the runners above")
        return EXIT_REFUSED
    print(f"ticket={found['ticket']}")
    _result("free", f"{found['ticket']} is free for {runner}")
    return EXIT_OK


def cmd_lane_lines(args):
    top = _top(args.root)
    ticket = norm_ticket(args.ticket)
    runner = expand_runner(args.runner)
    if runner is None:
        raise UsageError("lane-lines needs an explicit runner id")
    script = os.path.abspath(__file__)
    base = f"python3 {script} {{}} --root {top} --ticket {ticket} --runner {runner}"
    print(base.format("begin") + f" --worktree {os.path.abspath(args.worktree)}")
    print(base.format("beat") + " --phase <step>")
    print(base.format("end") + " --outcome <result>")
    print("Run begin before any other command; on exit 1 or 3 stop and report in-flight with its "
          "result= line. Run beat at each step. Run end on every exit path, including failure.")
    return EXIT_OK


# --- the beat loop -------------------------------------------------------------------

def _holder_tag(runner, pid):
    return hashlib.sha256(json.dumps([runner, pid]).encode("utf-8")).hexdigest()[:16]


def loop_lock_path(ticket, runner, pid):
    return os.path.join(crew_holder.private_dir("crew-inflight"),
                        f"{norm_ticket(ticket)}-{_holder_tag(runner, pid)}.lock")


def _start_loop(top, ticket, runner, me):
    if not me.get("pid"):
        print(f"warning: CLAUDE_PID is absent, so no beat loop runs; the marker reads stale after "
              f"{TTL_MINUTES} minutes unless the runner beats", file=sys.stderr)
        return
    argv = [sys.executable, os.path.abspath(__file__), "beat-loop", "--root", top, "--ticket", ticket,
            "--runner", runner, "--pid", str(me["pid"]), "--interval", str(LOOP_SECONDS)]
    kwargs = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008 | 0x00000200}
    try:
        log = os.path.join(crew_holder.private_dir("crew-inflight"), f"{ticket}.log")
        fd = crew_holder._open_private(log, os.O_WRONLY | os.O_APPEND)  # pylint: disable=protected-access
        with os.fdopen(fd, "a", encoding="utf-8") as out:
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=out,  # pylint: disable=consider-using-with
                             env=crew_holder.child_env(), close_fds=True, **kwargs)
    except OSError as exc:
        print(f"warning: the beat loop did not start ({type(exc).__name__}); the marker reads stale "
              f"after {TTL_MINUTES} minutes unless the runner beats", file=sys.stderr)
        return
    print(f"beat every {LOOP_SECONDS}s while pid {me['pid']} lives; log: {log}")


def _loop_should_stop(top, ticket, runner, pid, first):
    probe = crew_holder.probe_pid(pid)
    if probe.state == "gone" or (first.start and probe.start and probe.start != first.start):
        return f"watched pid {pid} is gone or reused"
    record, status, _why = read_marker(top, ticket)
    if status != "ok" or record["state"] != "working" or record["runner"] != runner \
            or record["holder"].get("pid") != pid:
        return f"{ticket} is no longer working for {runner}"
    return ""


def beat_loop(top, ticket, runner, pid, interval, sleep=time.sleep):
    """Refresh heartbeat_at every `interval` while `pid` lives with its first
    start time and the marker still names `runner` and `pid`."""
    ticket = norm_ticket(ticket)
    try:
        lock = crew_holder._open_private(loop_lock_path(ticket, runner, pid), os.O_RDWR)  # pylint: disable=protected-access
    except OSError as exc:
        print(f"beat-loop: the lock could not be opened ({type(exc).__name__}); running without it")
        lock = None
    if lock is not None:
        try:
            crew_holder._lock_fd(lock, wait=False)  # pylint: disable=protected-access
        except OSError:
            os.close(lock)
            print(f"{crew_holder.stamp()} another beat loop already runs for {ticket} as this holder; exiting")
            return EXIT_OK
    try:
        first = crew_holder.probe_pid(pid)
        while True:
            with _locked(top):
                why = _loop_should_stop(top, ticket, runner, pid, first)
                if not why:
                    record, _status, _why = read_marker(top, ticket)
                    write_marker(top, ticket, dict(record, heartbeat_at=crew_holder.stamp(_now())))
            if why:
                print(f"{crew_holder.stamp()} {why}; exiting", flush=True)
                return EXIT_OK
            print(f"{crew_holder.stamp()} heartbeat {ticket}", flush=True)
            sleep(interval)
    finally:
        if lock is not None:
            os.close(lock)


def cmd_beat_loop(args):
    return beat_loop(_top(args.root), args.ticket, args.runner, args.pid, args.interval)


# --- entry point ---------------------------------------------------------------------

def _parser():
    parser = argparse.ArgumentParser(prog="crew_inflight.py", description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    specs = {"begin": cmd_begin, "beat": cmd_beat, "end": cmd_end, "status": cmd_status, "clear": cmd_clear,
             "pick": cmd_pick, "lane-lines": cmd_lane_lines, "beat-loop": cmd_beat_loop}
    for name, func in specs.items():
        cmd = sub.add_parser(name)
        cmd.set_defaults(func=func)
        cmd.add_argument("--root", default=os.getcwd())
        if name in ("begin", "beat", "end", "clear", "lane-lines", "beat-loop"):
            cmd.add_argument("--ticket", required=True)
        if name in ("begin", "beat", "end", "pick", "lane-lines", "beat-loop"):
            cmd.add_argument("--runner", required=True, help="<kind>:<id>, or autopilot")
        if name == "begin":
            cmd.add_argument("--worktree", help="the worktree this runner works in (default: --root's)")
            cmd.add_argument("--here", action="store_true",
                             help="the owner's override: continue a ticket that ended in another checkout here")
            cmd.add_argument("--no-heartbeat", action="store_true",
                             help="do not start the detached beat loop (the marker reads stale after the TTL "
                                  "unless the runner beats)")
        if name == "beat":
            cmd.add_argument("--phase")
        if name == "end":
            cmd.add_argument("--outcome")
        if name == "status":
            cmd.add_argument("--ticket")
            cmd.add_argument("--all", action="store_true")
            cmd.add_argument("--runner")
            cmd.add_argument("--json", action="store_true")
        if name == "clear":
            cmd.add_argument("--by")
            cmd.add_argument("--round", type=int)
            cmd.add_argument("--reason")
        if name == "pick":
            cmd.add_argument("--tickets", nargs="+", required=True)
        if name == "lane-lines":
            cmd.add_argument("--worktree", required=True)
        if name == "beat-loop":
            cmd.add_argument("--pid", type=int, required=True)
            cmd.add_argument("--interval", type=int, default=LOOP_SECONDS)
    return parser


def main(argv=None):
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_USAGE
    try:
        return args.func(args)
    except (UsageError, crew_ticket.TicketError) as exc:
        print(f"crew-inflight: {exc}", file=sys.stderr)
        _result("usage", str(exc))
        return EXIT_USAGE
    except Exception as exc:  # pylint: disable=broad-except
        _result(UNKNOWN, f"could not tell ({type(exc).__name__}: {exc}); nothing more was written")
        return EXIT_UNKNOWN


if __name__ == "__main__":
    sys.exit(main())
