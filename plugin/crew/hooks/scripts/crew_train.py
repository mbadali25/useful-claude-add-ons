"""The merge train (L-0520): gate+land serialised per overlapping Touch set,
while lanes keep implementing in parallel.

WHY. Parallel lanes that gate against a base which then moves pay for a
catch-up merge and a fresh gate round every time. The owner's rule
(2026-09-30): serialise the GATE+LAND stage, not coding. One queue per
overlapping Touch set; the head of it merges the base, gates, lands, and
releases; disjoint Touch sets never wait on each other. Nothing on the
implement path consults this module: only `review_run.py` (a gate round) and
`review_prompt.py` (the reviewer's brief) import it.

STATE. `<git-common-dir>/crew/train/`, shared by every worktree of one clone:
  state.json            {"schema": 1, "armed_at", "armed_by", "seq", "order",
                         "entries": [...]}
  state.json.lock       held for every read-modify-write of state.json
  events.jsonl          append-only: acquire, wait, release, merged,
                        force-release, check-land (each with a `seq`)
  merge-log/<id>.jsonl  one line per catch-up: head before, base sha, outcome,
                        conflicted files, rerere-replayed files
`scope_guard.py` already refuses Write/Edit, and obvious shell writes, under
`<git-common-dir>/crew/`. Lanes in separate CLONES do not share a train.

ARMED PER CLONE. `arm` creates state.json with O_CREAT|O_EXCL. Without it the
train is off and `review_run.py` behaves exactly as before; `disarm` refuses
while any entry exists. There is no config key.

THE HOLD RULE. An entry (one ticket on one base) may hold iff no HOLDING entry
on the same base overlaps it and no EARLIER-ENQUEUED WAITING entry on the same
base overlaps it. Overlapping tickets therefore gate and land one at a time in
the order they reached their gate; disjoint ones hold at once; the same Touch
on two bases is two trains. Every wait is printed and logged with each
colliding entry pair (`colliding: <mine> x <theirs>`).

OVERLAP IS CONSERVATIVE. Two Touch entries overlap when the literal prefix of
one (its case-folded segments before the first segment holding `*`, `?` or
`[`) is a segment prefix of the other's. It never says disjoint for sets that
can share a path; it may say overlap for sets that cannot (`a/*.py` and
`a/b/c.py`), which only serialises more. Refresh artifacts -- `.crew/codemap/`,
`.claude/rules/`, `docs/diagrams/`, `graphify-out/` -- are regenerated, never
hand-merged, so they are left out of every overlap and moved-path decision; a
conflict in one still fails `merge-tree` at land.

FAIL CLOSED. An undeclared Touch -- no spec.md, no `## Touch`, no bullet, a
parse problem, unreadable bytes -- overlaps everything and is named
`undeclared: <why>`. A state.json that exists but cannot be read, parsed or
has an unknown schema, a lock still held after LOCK_WAIT_SECONDS, or a git
call that fails is COULD NOT TELL: the verb exits 3 naming the path, and
nothing reads it as "not armed" or "no holder". A lock is never broken by age
(breaking locks by age is how two writers both win), and a stale-looking hold
is reported as `stale?: <evidence>` and never released automatically:
`release --force --by <who> --reason <text>` releases it and logs an event.

MERGE BASE, THEN GATE. `acquire` refuses (`merge <base> first`) while the base
holds commits not in HEAD that touch this ticket's Touch, so the gate verdict
covers the tree that lands. `catch-up` is the one catch-up: `git merge
--no-edit <base>`, never a rebase or cherry-pick, after making
`rerere.enabled`/`rerere.autoupdate` true in this worktree (`git config
--worktree` when `extensions.worktreeConfig` is already on, else `--local`;
never `--global`, never switching the extension on). It never commits a
conflicted or rerere-resolved merge: replayed files are staged and listed, the
merge is left for the lane to inspect and commit, and the merge log names
them so `review_prompt.py` can show the reviewer. A replayed resolution is
still a change to gate.

LAND. `check-land` requires, in order: the train readable; this worktree's
entry holding; the base fetched; `git merge-tree --write-tree <base> HEAD`
clean (exit 1 lists the conflicted paths; anything else, e.g. a git older than
2.38, is could not tell); the base not moved in Touch paths since HEAD's
merge-base with it (moved only outside Touch is allowed and said); a current
review receipt (`review_ledger.check_receipt`) and a verify gate VERIFIED or
NO_GATE (`review_gate.gate_state`) on HEAD. Then it prints `LAND_OK head=<sha>`
and the `gh pr merge <pr> --merge --match-head-commit <sha>` to run. Crew
never merges. After the merge, `release --merged <sha>` records the merged
paths; every overlapping entry is told once, on its next `acquire` or
`status`, to merge the base now (a merge whose paths cannot be read is told to
every entry). The notice is advice; `acquire`'s refusal is the rule.

Exit codes: 0 ok / holding; 1 refused or waiting (and "train not armed");
2 usage; 3 could not tell.
"""
import argparse
import datetime
import getpass
import json
import os
import re
import subprocess
import sys
import time

if __name__ == "__main__":
    # Before the sibling imports: the direct CLI writes no bytecode either.
    sys.dont_write_bytecode = True

import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position
import review_gate  # noqa: E402  pylint: disable=wrong-import-position
import review_ledger  # noqa: E402  pylint: disable=wrong-import-position
import scope_base  # noqa: E402  pylint: disable=wrong-import-position

SCHEMA = 1
LOCK_WAIT_SECONDS = 10.0
GIT_TIMEOUT = 120
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_UNKNOWN = 0, 1, 2, 3
REFRESH_PREFIXES = ((".crew", "codemap"), (".claude", "rules"), ("docs", "diagrams"),
                    ("graphify-out",))
UNDECLARED = "<undeclared>"
NOTICE_KINDS = ("merged", "force-release")
_REPLAYED_RE = re.compile(r"^(?:Resolved|Staged) '(.+)' using previous resolution\.$")


class TrainError(RuntimeError):
    """Could not tell: the verb refuses with exit 3."""


class NotArmed(RuntimeError):
    """The clone has no state.json: exit 1, `train not armed`."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _owner():
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return "unknown"


# --- git -------------------------------------------------------------------------------

def _git(root, *args, timeout=GIT_TIMEOUT):
    """(code, stdout, stderr); code None when git could not be started. Never
    raises: `crew_common.git_out` folds "git said no" into "could not run",
    and merge-tree's exit 1 (conflicts) versus >1 (error) matters here."""
    try:
        done = subprocess.run(["git", "-C", root] + list(args), capture_output=True,
                              text=True, check=False, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", str(exc)
    return done.returncode, done.stdout, done.stderr


def _git_ok(root, *args):
    """stdout of a git call that must succeed, else TrainError."""
    code, out, err = _git(root, *args)
    if code != 0:
        raise TrainError(f"git {' '.join(args)} failed (exit {code}): "
                         f"{(err or out).strip()[:300]}")
    return out


def _lines(text):
    return [line for line in (text or "").splitlines() if line.strip()]


def _top(root):
    top = crew_ticket.toplevel(root)
    if not top:
        raise TrainError(f"{root} is not a git worktree")
    return top


def _base(top, base):
    ref = base or scope_base._default_ref(top)  # pylint: disable=protected-access
    if not ref:
        raise TrainError("no base ref: none of origin/HEAD, origin/main, main names a "
                         "commit here; pass --base")
    return ref


def _head(top):
    return _git_ok(top, "rev-parse", "HEAD").strip()


def _lane(top, lane):
    if lane:
        return lane
    code, out, _ = _git(top, "rev-parse", "--abbrev-ref", "HEAD")
    name = out.strip() if code == 0 else ""
    return name if name and name != "HEAD" else os.path.basename(top)


# --- where the state lives ---------------------------------------------------------------

def train_dir(root):
    state = crew_ticket.state_dir(root)
    if not state:
        raise TrainError(f"{root} is not a git repository; there is no train here")
    return os.path.join(state, "train")


def _state_path(root):
    return os.path.join(train_dir(root), "state.json")


def _events_path(root):
    return os.path.join(train_dir(root), "events.jsonl")


def merge_log_path(root, ticket):
    return os.path.join(train_dir(root), "merge-log", crew_ticket.check_ticket(ticket) + ".jsonl")


def _read_file(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load(root):
    """(state, where, why): `where` is `absent`, `ok` or `could not tell`.
    Only a state.json that does not exist at all is `absent`."""
    path = _state_path(root)
    if not os.path.lexists(path):
        return None, "absent", f"{path} does not exist"
    try:
        data = json.loads(_read_file(path))
    except (OSError, ValueError) as exc:
        return None, "could not tell", f"{path} cannot be read: {exc}"
    if not isinstance(data, dict) or data.get("schema") != SCHEMA \
            or not isinstance(data.get("entries"), list) \
            or not isinstance(data.get("seq"), int):
        return None, "could not tell", (f"{path} is not a schema-{SCHEMA} train state "
                                        f"(schema {data.get('schema') if isinstance(data, dict) else None!r})")
    return data, "ok", path


def _save(path, data):
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


class _Lock:
    """O_CREAT|O_EXCL lock file, `review_ledger._Lock`'s shape: PID inside,
    waits LOCK_WAIT_SECONDS, then refuses naming the path. Never removed for
    being old."""

    def __init__(self, path):
        self.path = path + ".lock"

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() > deadline:
                    raise TrainError(
                        f"could not tell: train lock {self.path} has been held for over "
                        f"{LOCK_WAIT_SECONDS:g}s. If no crew_train.py is running, a process "
                        "died holding it -- remove that file by hand") from exc
                time.sleep(0.02)
                continue
            except OSError as exc:
                raise TrainError(f"could not tell: train lock {self.path}: {exc}") from exc
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def _mutate(root, change):
    """Run `change(state, events)` under the lock on an armed, readable state.
    `events` is a list the change appends to; they are written with the next
    seq numbers, then state.json is replaced atomically."""
    path = _state_path(root)
    if not os.path.lexists(path):
        raise NotArmed("train not armed in this clone (crew_train.py arm arms it)")
    with _Lock(path):
        state, where, why = load(root)
        if where == "absent":
            raise NotArmed("train not armed in this clone (crew_train.py arm arms it)")
        if where != "ok":
            raise TrainError(f"could not tell: {why}")
        events = []
        result = change(state, events)
        if events:
            lines = []
            for event in events:
                state["seq"] += 1
                event.setdefault("time", _now())
                event["seq"] = state["seq"]
                lines.append(json.dumps(event, sort_keys=True))
            text = "\n".join(lines) + "\n"
            with open(_events_path(root), "a", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        _save(path, state)
    return result


def read_events(root, after=0):
    """(events with seq > after, problems). An unparseable line is named,
    never silently dropped."""
    path = _events_path(root)
    try:
        text = _read_file(path)
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [f"{path} cannot be read: {exc}"]
    found, problems = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f"{path}:{number} does not parse")
            continue
        if isinstance(event, dict) and isinstance(event.get("seq"), int) \
                and event["seq"] > after:
            found.append(event)
    return found, problems


# --- Touch and overlap ------------------------------------------------------------------

def touch_of(top, ticket):
    """(entries, source). `entries` is None -- overlaps everything -- whenever
    Touch is not a readable, problem-free, non-empty list."""
    try:
        data = crew_ticket.read_contract(top, ticket)["spec.md"]
    except (OSError, crew_ticket.TicketError) as exc:
        return None, f"undeclared: spec.md unreadable ({exc})"
    spec = os.path.join(crew_ticket.ticket_dir(top, ticket), "spec.md")
    if data is None:
        why = "spec.md unreadable" if os.path.lexists(spec) else f"no spec.md at {spec}"
        return None, f"undeclared: {why}"
    entries, problems = crew_ticket.parse_touch(crew_ticket._text(data))  # pylint: disable=protected-access
    if problems or not entries:
        return None, f"undeclared: {(problems or ['## Touch lists no paths'])[0]}"
    return entries, "spec.md"


def _segments(entry):
    return [s for s in entry.replace("\\", "/").split("/") if s not in ("", ".")]


def _prefix(entry):
    out = []
    for segment in _segments(entry):
        if any(c in segment for c in crew_ticket._GLOB_CHARS):  # pylint: disable=protected-access
            break
        out.append(segment.casefold())
    return out


def _is_refresh(entry):
    segments = [s.casefold() for s in _segments(entry)]
    return any(segments[:len(p)] == list(p) for p in REFRESH_PREFIXES)


def effective(touch):
    """Touch without refresh artifacts; None stays None (everything)."""
    return None if touch is None else [e for e in touch if not _is_refresh(e)]


def entries_overlap(a, b):
    pa, pb = _prefix(a), _prefix(b)
    short, other = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return other[:len(short)] == short


def touch_overlap(mine, theirs):
    """Every colliding (mine, theirs) pair; empty means disjoint. None is an
    undeclared Touch and collides with anything."""
    if mine is None or theirs is None:
        left = [UNDECLARED] if mine is None else (mine or [UNDECLARED])
        right = [UNDECLARED] if theirs is None else (theirs or [UNDECLARED])
        return [(left[0], r) for r in right] if mine is None else [(m, UNDECLARED) for m in left]
    return [(a, b) for a in effective(mine) for b in effective(theirs) if entries_overlap(a, b)]


def meets_touch(path, touch):
    """A repo-relative file path falls inside Touch (refresh artifacts left
    out); an undeclared Touch meets every path."""
    touch = effective(touch)
    return True if touch is None else crew_ticket.in_touch(path, touch)


def _moved_paths(top, base):
    """(behind, paths): whether the base holds commits HEAD lacks, and every
    path the base changed since HEAD's merge-base with it."""
    behind = _git_ok(top, "rev-list", "--count", f"HEAD..{base}").strip()
    if behind in ("", "0"):
        return False, []
    mb = _git_ok(top, "merge-base", "HEAD", base).strip()
    return True, _lines(_git_ok(top, "diff", "--name-only", mb, base))


# --- entries ------------------------------------------------------------------------------

def _find(state, ticket, base):
    return next((e for e in state["entries"] if e.get("ticket") == ticket
                 and (base is None or e.get("base") == base)), None)


def _stale(top, entry):
    """Evidence that a hold may be dead. Printed, never acted on."""
    found = []
    since = entry.get("acquired_at") or entry.get("enqueued_at")
    try:
        then = datetime.datetime.fromisoformat(since)
        hours = (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds() / 3600
        if hours >= 1:
            found.append(f"held {hours:.1f}h")
    except (TypeError, ValueError):
        found.append("age unknown")
    if not os.path.isdir(entry.get("worktree") or ""):
        found.append(f"worktree missing ({entry.get('worktree')})")
    head, base = entry.get("head"), entry.get("base")
    if head and base:
        code, out, _ = _git(top, "rev-parse", f"{base}^{{commit}}")
        if code == 0 and out.strip() != head \
                and _git(top, "merge-base", "--is-ancestor", head, base)[0] == 0:
            found.append(f"head {head[:12]} already in {base}")
    return found


def _describe(entry):
    return f"{entry['ticket']} ({entry.get('lane')}, since " \
           f"{entry.get('acquired_at') or entry.get('enqueued_at')})"


def _blockers(state, entry):
    """[(other, pairs)] for every entry that stops `entry` holding."""
    found = []
    for other in state["entries"]:
        if other is entry or other.get("base") != entry["base"]:
            continue
        earlier = other.get("state") == "waiting" and other.get("order", 0) < entry.get("order", 0)
        if other.get("state") != "holding" and not earlier:
            continue
        pairs = touch_overlap(entry.get("touch"), other.get("touch"))
        if pairs:
            found.append((other, pairs))
    return found


def _upsert(state, top, ticket, base, lane, head, touch, source):
    entry = _find(state, ticket, base)
    if entry is None:
        state["order"] = state.get("order", 0) + 1
        entry = {"ticket": ticket, "base": base, "state": "waiting", "order": state["order"],
                 "enqueued_at": _now(), "acquired_at": None, "owner": _owner(),
                 "last_seen": state["seq"]}
        state["entries"].append(entry)
    elif entry.get("worktree") != top and entry.get("state") == "holding":
        raise TrainError(f"{ticket} on {base} is held from {entry.get('worktree')}, "
                         f"not {top}; release it there, or release --force")
    code, out, _ = _git(top, "rev-parse", "--abbrev-ref", "HEAD")
    entry.update({"worktree": top, "lane": lane,
                  "branch": out.strip() if code == 0 else None, "head": head,
                  "touch": touch, "touch_source": source})
    return entry


def _notices(root, state, entry):
    """Unseen merged/force-release events meeting `entry`'s Touch, as lines;
    advances the entry's last_seen."""
    events, problems = read_events(root, entry.get("last_seen", 0))
    out = [f"{entry['ticket']}: events: {p}" for p in problems]
    for event in events:
        if event.get("kind") not in NOTICE_KINDS or event.get("ticket") == entry["ticket"]:
            continue
        if event.get("kind") == "merged":
            paths = event.get("paths")
            hit = paths is None or any(meets_touch(p, entry.get("touch")) for p in paths)
            shown = "(paths unreadable)" if paths is None else ", ".join(
                p for p in paths if meets_touch(p, entry.get("touch")))
            if hit:
                out.append(f"{entry['ticket']}: {event['ticket']} merged "
                           f"{str(event.get('sha'))[:12]} touching {shown} - merge "
                           f"{event.get('base')} now")
        elif touch_overlap(entry.get("touch"), event.get("touch")):
            out.append(f"{entry['ticket']}: {event['ticket']}'s hold was force-released by "
                       f"{event.get('by')} ({event.get('reason')}) - check the base before "
                       "you gate")
    entry["last_seen"] = state["seq"]
    return out


# --- verbs --------------------------------------------------------------------------------

def arm(root, by=None):
    path = _state_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    events, problems = read_events(root)
    if problems:
        raise TrainError(f"could not tell: {problems[0]}")
    seq = max([e["seq"] for e in events] or [0])
    text = json.dumps({"schema": SCHEMA, "armed_at": _now(), "armed_by": by or _owner(),
                       "seq": seq, "order": 0, "entries": []}, indent=2, sort_keys=True) + "\n"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return EXIT_REFUSED, [f"train already armed in this clone ({path})"]
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return EXIT_OK, [f"train armed: {path}; review_run.py now takes the train before a "
                     "gate round in every worktree of this clone"]


def disarm(root):
    def change(state, _events):
        if state["entries"]:
            return [e["ticket"] for e in state["entries"]]
        return None
    busy = _mutate(root, change)
    if busy:
        return EXIT_REFUSED, [f"train has entries ({', '.join(busy)}); release them first"]
    os.remove(_state_path(root))
    return EXIT_OK, ["train disarmed; review_run.py no longer consults it"]


def _snapshot(root, ticket, base, lane):
    top = _top(root)
    crew_ticket.check_ticket(ticket)
    base = _base(top, base)
    touch, source = touch_of(top, ticket)
    return top, base, _lane(top, lane), _head(top), touch, source


def enqueue(root, ticket, base=None, lane=None):
    top, base, lane, head, touch, source = _snapshot(root, ticket, base, lane)

    def change(state, _events):
        entry = _upsert(state, top, ticket, base, lane, head, touch, source)
        return entry["state"]
    held = _mutate(root, change)
    return EXIT_OK, [f"{ticket} is {held} on {base} (touch: {source})"]


def acquire(root, ticket, base=None, lane=None):
    """(code, lines): 0 holding; 1 waiting, or `merge <base> first`."""
    top, base, lane, head, touch, source = _snapshot(root, ticket, base, lane)
    behind, moved = _moved_paths(top, base)
    in_touch = [p for p in moved if meets_touch(p, touch)]

    def change(state, events):
        entry = _upsert(state, top, ticket, base, lane, head, touch, source)
        lines = _notices(root, state, entry)
        blockers = [] if entry["state"] == "holding" else _blockers(state, entry)
        if blockers:
            events.append({"kind": "wait", "ticket": ticket, "lane": lane, "base": base,
                           "blockers": [{"ticket": o["ticket"], "lane": o.get("lane"),
                                         "state": o.get("state"),
                                         "paths": [list(p) for p in pairs]}
                                        for o, pairs in blockers]})
            for other, pairs in blockers:
                lines.append(f"waiting behind {_describe(other)} [{other.get('state')}]")
                lines += [f"  colliding: {mine} x {theirs}" for mine, theirs in pairs]
                lines += [f"  stale?: {e}" for e in _stale(top, other)]
            return EXIT_REFUSED, lines
        if in_touch:
            lines.append(f"merge {base} first: it moved in this ticket's Touch since HEAD's "
                         f"merge-base: {', '.join(in_touch)}")
            lines.append(f"  run crew_train.py catch-up --ticket {ticket}, then gate again")
            return EXIT_REFUSED, lines
        if entry["state"] != "holding":
            entry["state"], entry["acquired_at"] = "holding", _now()
            events.append({"kind": "acquire", "ticket": ticket, "lane": lane, "base": base,
                           "head": head})
        lines.append(f"holding {base} for {ticket} (touch: {source})")
        if behind and not in_touch:
            lines.append(f"  {base} moved outside Touch only ({len(moved)} paths)")
        return EXIT_OK, lines
    return _mutate(root, change)


def release(root, ticket, base=None, merged=None, force=False, by=None, reason=None):
    top = _top(root)
    crew_ticket.check_ticket(ticket)
    if force and not (by and reason):
        return EXIT_USAGE, ["release --force needs --by <who> and --reason <text>"]
    paths = None
    if merged:
        code, out, _ = _git(top, "diff", "--name-only", f"{merged}^1", merged)
        paths = _lines(out) if code == 0 else None

    def change(state, events):
        matches = [e for e in state["entries"] if e.get("ticket") == ticket
                   and (base is None or e.get("base") == base)]
        if not matches:
            return EXIT_REFUSED, [f"{ticket} has no train entry"
                                  + (f" on {base}" if base else "")]
        if len(matches) > 1:
            return EXIT_USAGE, [f"{ticket} is queued on several bases; pass --base"]
        entry = matches[0]
        if entry.get("worktree") != top and not force:
            return EXIT_REFUSED, [f"{ticket} is held from {entry.get('worktree')}, not here; "
                                  "release it there, or release --force --by <who> "
                                  "--reason <text>"]
        state["entries"].remove(entry)
        event = {"ticket": ticket, "lane": entry.get("lane"), "base": entry.get("base"),
                 "touch": entry.get("touch")}
        if force:
            event.update(kind="force-release", by=by, reason=reason,
                         was=entry.get("state"), worktree=entry.get("worktree"))
        elif merged:
            event.update(kind="merged", sha=merged, paths=paths)
        else:
            event.update(kind="release")
        events.append(event)
        return EXIT_OK, [f"released {ticket} on {entry.get('base')} ({event['kind']})"]
    return _mutate(root, change)


def status(root, as_json=False):
    state, where, why = load(root)
    if where == "absent":
        return EXIT_OK, [json.dumps({"armed": False, "entries": []}) if as_json else "armed: no"]
    if where != "ok":
        raise TrainError(f"could not tell: {why}")
    top = _top(root)
    notices = {}

    def change(fresh, _events):
        for entry in fresh["entries"]:
            if entry.get("worktree") == top:
                notices[entry["ticket"]] = _notices(root, fresh, entry)
        return fresh
    state = _mutate(root, change)
    if as_json:
        return EXIT_OK, [json.dumps({"armed": True, "armed_at": state.get("armed_at"),
                                     "entries": state["entries"]}, sort_keys=True)]
    lines = [f"armed: yes (since {state.get('armed_at')}, by {state.get('armed_by')})"]
    for base in sorted({e.get("base") for e in state["entries"]}):
        lines.append(f"base {base}:")
        rows = sorted((e for e in state["entries"] if e.get("base") == base),
                      key=lambda e: (e.get("state") != "holding", e.get("order", 0)))
        for entry in rows:
            lines.append(f"  {entry.get('state')} {_describe(entry)} head="
                         f"{str(entry.get('head'))[:12]} touch: {entry.get('touch_source')}")
            skipped = [t for t in entry.get("touch") or [] if _is_refresh(t)]
            if skipped:
                lines.append(f"    refresh artifacts not counted: {', '.join(skipped)}")
            if entry.get("state") == "waiting":
                for other, pairs in _blockers(state, entry):
                    lines.append(f"    behind {other['ticket']}: " + "; ".join(
                        f"{a} x {b}" for a, b in pairs))
            lines += [f"    stale?: {e}" for e in _stale(top, entry)]
            lines += ["    " + n for n in notices.get(entry["ticket"], [])]
    return EXIT_OK, lines


# --- catch-up and the merge log ---------------------------------------------------------------

def ensure_rerere(top):
    """Make rerere.enabled/autoupdate true for this worktree; the scope used."""
    code, out, _ = _git(top, "config", "--get", "--bool", "extensions.worktreeConfig")
    scope = "--worktree" if code == 0 and out.strip() == "true" else "--local"
    for key in ("rerere.enabled", "rerere.autoupdate"):
        _git_ok(top, "config", scope, key, "true")
    return scope


def _remote_of(top, base):
    remotes = _lines(_git_ok(top, "remote"))
    head, _, branch = base.partition("/")
    return (head, branch) if branch and head in remotes else (None, None)


def _fetch(top, base):
    remote, branch = _remote_of(top, base)
    if not remote:
        return f"{base} is local; not fetched"
    code, out, err = _git(top, "fetch", "--quiet", remote, branch)
    if code != 0:
        raise TrainError(f"could not tell: git fetch {remote} {branch} failed (exit {code}): "
                         f"{(err or out).strip()[:300]}")
    return f"fetched {remote} {branch}"


def _append_merge_log(root, ticket, row):
    path = merge_log_path(root, ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(row, sort_keys=True) + "\n"
    with _Lock(path):
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def catch_up(root, ticket, base=None, fetch=True, lane=None):
    """Merge the base into this worktree (never rebase), rerere on first."""
    top = _top(root)
    crew_ticket.check_ticket(ticket)
    base = _base(top, base)
    if _git(top, "rev-parse", "-q", "--verify", "MERGE_HEAD")[0] == 0:
        return EXIT_REFUSED, ["a merge is already in progress here (MERGE_HEAD); finish it "
                              "(git commit --no-edit) or git merge --abort first"]
    dirty = _lines(_git_ok(top, "status", "--porcelain", "--untracked-files=no", "--",
                           ".", ":(exclude).work"))
    if dirty:
        return EXIT_REFUSED, ["working tree is dirty; commit or stash first:"] + \
            ["  " + d for d in dirty[:20]]
    lines = [_fetch(top, base) if fetch else f"{base}: not fetched (--no-fetch)"]
    scope = ensure_rerere(top)
    lines.append(f"rerere.enabled and rerere.autoupdate are true ({scope})")
    head_before = _head(top)
    base_sha = _git_ok(top, "rev-parse", f"{base}^{{commit}}").strip()
    code, out, err = _git(top, "merge", "--no-edit", base)
    in_merge = _git(top, "rev-parse", "-q", "--verify", "MERGE_HEAD")[0] == 0
    conflicted = _lines(_git(top, "diff", "--name-only", "--diff-filter=U")[1])
    staged = set(_lines(_git(top, "diff", "--name-only", "--cached")[1]))
    said = [m.group(1) for m in (_REPLAYED_RE.match(x.strip())
                                 for x in (out + "\n" + err).splitlines()) if m]
    replayed = sorted({p for p in said if p in staged and p not in conflicted})
    if code == 0:
        outcome = "up-to-date" if _head(top) == head_before else "merged"
    elif in_merge:
        outcome = "conflicted" if conflicted or not replayed else "rerere-resolved"
    else:
        outcome = "refused"
    _append_merge_log(root, ticket, {
        "time": _now(), "ticket": ticket, "lane": _lane(top, lane), "worktree": top,
        "head_before": head_before, "base": base, "base_sha": base_sha, "outcome": outcome,
        "conflicted": conflicted, "rerere_replayed": replayed, "rerere_config": scope})
    lines.append(f"catch-up {outcome}: git merge --no-edit {base} ({base_sha[:12]})")
    if replayed:
        lines.append(f"  rerere replayed (staged, review it as a change): {', '.join(replayed)}")
    if conflicted:
        lines.append(f"  conflicted: {', '.join(conflicted)}")
    if outcome == "refused":
        lines.append("  git: " + (err or out).strip()[:300])
    if outcome in ("conflicted", "rerere-resolved"):
        lines.append("  inspect, then git commit --no-edit; the head must be gated again")
        return EXIT_REFUSED, lines
    if outcome == "refused":
        return EXIT_REFUSED, lines
    if outcome == "merged":
        lines.append("  the merged head must be gated again before check-land")
    return EXIT_OK, lines


def read_merge_log(root, ticket):
    """(rows, where, why): `where` is `absent`, `ok` or `could not tell`."""
    path = merge_log_path(root, ticket)
    try:
        text = _read_file(path)
    except FileNotFoundError:
        return [], "absent", f"{path} does not exist"
    except OSError as exc:
        return [], "could not tell", f"{path} cannot be read: {exc}"
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            return [], "could not tell", f"{path}:{number} does not parse"
        if not isinstance(row, dict):
            return [], "could not tell", f"{path}:{number} is not an object"
        rows.append(row)
    return rows, "ok", path


def merge_log(root, ticket):
    rows, where, why = read_merge_log(root, crew_ticket.check_ticket(ticket))
    if where == "absent":
        return EXIT_OK, [f"no catch-up merges recorded for {ticket}"]
    if where != "ok":
        raise TrainError(f"could not tell: {why}")
    lines = []
    for row in rows:
        lines.append(f"{row.get('time')} {row.get('outcome')} base={row.get('base')}@"
                     f"{str(row.get('base_sha'))[:12]} head_before="
                     f"{str(row.get('head_before'))[:12]}")
        if row.get("conflicted"):
            lines.append(f"  conflicted: {', '.join(row['conflicted'])}")
        if row.get("rerere_replayed"):
            lines.append(f"  rerere_replayed: {', '.join(row['rerere_replayed'])}")
    return EXIT_OK, lines


# --- check-land -----------------------------------------------------------------------------

def _merge_tree(top, base):
    code, out, err = _git(top, "merge-tree", "--write-tree", "--name-only", base, "HEAD")
    if code == 0:
        return []
    if code == 1:
        names = []
        for line in (out or "").splitlines()[1:]:
            if not line.strip():
                break
            if line not in names:
                names.append(line)
        return names or ["(merge-tree reported a conflict it did not name)"]
    raise TrainError(f"could not tell: git merge-tree --write-tree exited {code} (git 2.38+ "
                     f"needed): {(err or out).strip()[:300]}")


def check_land(root, ticket, base=None, pr=None, fetch=True):
    top = _top(root)
    crew_ticket.check_ticket(ticket)
    state, where, why = load(root)
    if where == "absent":
        raise NotArmed("train not armed in this clone; there is no hold to land under")
    if where != "ok":
        raise TrainError(f"could not tell: {why}")
    entry = next((e for e in state["entries"] if e.get("ticket") == ticket
                  and (base is None or e.get("base") == base)), None)
    if entry is None or entry.get("state") != "holding" or entry.get("worktree") != top:
        held = "no entry" if entry is None else f"{entry.get('state')} from {entry.get('worktree')}"
        return EXIT_REFUSED, [f"{ticket} does not hold the train from this worktree ({held}); "
                              f"crew_train.py acquire --ticket {ticket} first"]
    base = entry["base"]
    lines = [_fetch(top, base) if fetch else f"{base}: not fetched (--no-fetch)"]
    conflicts = _merge_tree(top, base)
    if conflicts:
        return EXIT_REFUSED, lines + [f"merge-tree: HEAD conflicts with {base} in: "
                                      f"{', '.join(conflicts)}",
                                      f"  run crew_train.py catch-up --ticket {ticket}, "
                                      "resolve, gate the merged head, then check-land again"]
    behind, moved = _moved_paths(top, base)
    in_touch = [p for p in moved if meets_touch(p, entry.get("touch"))]
    if in_touch:
        return EXIT_REFUSED, lines + [f"{base} moved in Touch paths since HEAD's merge-base: "
                                      f"{', '.join(in_touch)}",
                                      f"  run crew_train.py catch-up --ticket {ticket}, gate "
                                      "the merged head, then check-land again"]
    if behind:
        lines.append(f"base moved outside Touch only ({len(moved)} paths); the verdict on "
                     "HEAD still covers every Touch path")
    ok, message = review_ledger.check_receipt(top, ticket)
    if not ok:
        return EXIT_REFUSED, lines + [f"review receipt: {message}"]
    lines.append(f"review receipt: {message}")
    gate, reason = review_gate.gate_state(top)
    if gate not in (review_gate.VERIFIED, review_gate.NO_GATE):
        return EXIT_REFUSED, lines + [f"verify gate {gate}: {reason}"]
    lines.append(f"verify gate {gate}: {reason}")
    head = _head(top)

    def change(fresh, events):
        events.append({"kind": "check-land", "ticket": ticket, "base": base, "head": head})
    _mutate(root, change)
    lines += [f"LAND_OK head={head}",
              f"gh pr merge {pr or '<PR>'} --merge --match-head-commit {head}",
              f"then: crew_train.py release --ticket {ticket} --merged <merge sha>"]
    return EXIT_OK, lines


# --- CLI ---------------------------------------------------------------------------------------

def _parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("arm").add_argument("--by")
    sub.add_parser("disarm")
    for verb in ("enqueue", "acquire"):
        cmd = sub.add_parser(verb)
        cmd.add_argument("--ticket", required=True)
        cmd.add_argument("--base")
        cmd.add_argument("--lane")
    cmd = sub.add_parser("release")
    cmd.add_argument("--ticket", required=True)
    cmd.add_argument("--base")
    cmd.add_argument("--merged")
    cmd.add_argument("--force", action="store_true")
    cmd.add_argument("--by")
    cmd.add_argument("--reason")
    sub.add_parser("status").add_argument("--json", action="store_true")
    cmd = sub.add_parser("catch-up")
    cmd.add_argument("--ticket", required=True)
    cmd.add_argument("--base")
    cmd.add_argument("--no-fetch", action="store_true")
    cmd = sub.add_parser("check-land")
    cmd.add_argument("--ticket", required=True)
    cmd.add_argument("--base")
    cmd.add_argument("--pr")
    cmd.add_argument("--no-fetch", action="store_true")
    sub.add_parser("merge-log").add_argument("--ticket", required=True)
    return parser


def _dispatch(args):
    root = os.path.abspath(args.root)
    verbs = {
        "arm": lambda: arm(root, args.by),
        "disarm": lambda: disarm(root),
        "enqueue": lambda: enqueue(root, args.ticket, args.base, args.lane),
        "acquire": lambda: acquire(root, args.ticket, args.base, args.lane),
        "release": lambda: release(root, args.ticket, args.base, args.merged, args.force,
                                   args.by, args.reason),
        "status": lambda: status(root, args.json),
        "catch-up": lambda: catch_up(root, args.ticket, args.base, not args.no_fetch),
        "check-land": lambda: check_land(root, args.ticket, args.base, args.pr,
                                         not args.no_fetch),
        "merge-log": lambda: merge_log(root, args.ticket),
    }
    return verbs[args.verb]()


def main(argv):
    args = _parser().parse_args(argv)
    try:
        code, lines = _dispatch(args)
    except NotArmed as exc:
        code, lines = EXIT_REFUSED, [str(exc)]
    except (TrainError, crew_ticket.TicketError) as exc:
        text = str(exc)
        code = EXIT_UNKNOWN if isinstance(exc, TrainError) else EXIT_USAGE
        lines = [text if text.startswith("could not tell") or code != EXIT_UNKNOWN
                 else f"could not tell: {text}"]
    stream = sys.stdout if code == EXIT_OK else sys.stderr
    for line in lines:
        stream.write(line + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
