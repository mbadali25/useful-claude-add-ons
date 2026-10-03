"""The merge train (L-0520): gate+land serialised per overlapping Touch set,
while lanes keep implementing in parallel.

WHY. Parallel lanes that gate against a base which then moves pay for a
catch-up merge and a fresh gate round every time. The owner's rule
(2026-09-30): serialise the GATE+LAND stage, not coding. One queue per
overlapping Touch set; the head of it merges the base, gates, lands, and
releases; disjoint Touch sets never wait on each other. Nothing on the
implement path consults this module; `test_crew_train.py` allows only
`review_run.py` (a gate round) and `review_prompt.py` (the reviewer's brief) to
import it, and in this release neither does yet: lanes call the CLI before the
gate round, and those two callers are L-0526.

STATE. `<git-common-dir>/crew/train/`, shared by every worktree of one clone:
  state.json            {"schema": 1, "armed_at", "armed_by", "seq", "order",
                         "entries": [...]}
  state.json.lock       held for every read-modify-write of state.json
  events.jsonl          append-only: acquire, wait, release, merged,
                        force-release, check-land (each with a `seq`)
  merge-log/<id>.jsonl  one line per catch-up: head before, base sha, outcome,
                        conflicted, rerere-replayed and rerere-forgotten files
`scope_guard.py` already refuses Write/Edit, and obvious shell writes, under
`<git-common-dir>/crew/`. Lanes in separate CLONES do not share a train.

ARMED PER CLONE. `arm` publishes a complete state.json with `os.link`, which
fails if it exists. Without it the train is off and every verb but `arm`,
`status`, `catch-up` and `merge-log` says `train not armed`; `disarm` refuses
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
hand-merged, so they are left out of the OVERLAP decision only. The moved-path
checks (`acquire`'s `merge <base> first`, `check-land`) and the merged-path
notices judge the full Touch (L-0558): a base that moved a path this ticket
names is a tree its verdict did not cover.

FAIL CLOSED. An undeclared Touch -- no spec.md, no `## Touch`, no bullet, a
parse problem, unreadable bytes -- overlaps everything and is named
`undeclared: <why>`. state.json is "not armed" only when it is proven missing
(ENOENT under an ancestor that is a directory, `_absent`); one that cannot be
looked up, read or parsed, has an unknown schema or a malformed entry, a lock
still held after LOCK_WAIT_SECONDS, or a git call that fails is COULD NOT
TELL: the verb exits 3 naming the path, and nothing reads it as "not armed"
or "no holder". The lock is removed only while it still holds its owner's
token; `arm` publishes a complete state.json with `os.link`. CLI values are
checked before use: a ref (`--base`, `--merged`) may not start with `-`,
`--pr` is digits, and no value carries a control character (exit 2). Every
top-level state field a verb reads (`schema`, `seq`, `order`, `entries`,
`armed_at`, `armed_by`) is shape-checked at load, and every events.jsonl record (an object
with a positive integer `seq`, a known `kind`, a `ticket`); a malformed record
is a `could not tell whether ... concerns you` notice to every entry, and
`arm` refuses on it. Events are written BEFORE state.json, and both are rolled
back if either fails, so no state change commits unlogged. A lock is never broken by age
(breaking locks by age is how two writers both win), and a stale-looking hold
is reported as `stale?: <evidence>` and never released automatically:
`release --force --by <who> --reason <text>` releases it and logs an event.

MERGE BASE, THEN GATE. `acquire` refuses (`merge <base> first`) while the base
holds commits not in HEAD that touch this ticket's Touch, so the gate verdict
covers the tree that lands. `catch-up` is the one catch-up: `git -c
rerere.autoupdate=false merge --no-edit <sha>` (the SHA the fetch returned,
not `<base>` by name), never a rebase or cherry-pick, after making `rerere.enabled` true in this worktree (`git config
--worktree` when `extensions.worktreeConfig` is already on, else `--local`;
never `--global`, never switching the extension on). It never writes
`rerere.autoupdate` (owner, 2026-09-30) and never commits a conflicted or
rerere-resolved merge: replayed files are left in the working tree UNSTAGED
and listed, for the lane to inspect and `git add`; each VERSION_FILES path
still unmerged has its rerere resolution forgotten and its conflict markers
restored, for the lane to resolve by hand; the merge log names both
(`merge-log`), for the reviewer. A replayed resolution is still a change to
gate.

LAND. `check-land` requires, in order: the train readable; this worktree's
entry holding; the base fetched (`+refs/heads/<branch>:refs/remotes/<remote>/
<branch>`, and the base must then name FETCH_HEAD's commit, else could not
tell; every later step judges that SHA, never `<base>` by name, since another
worktree's fetch can move the shared ref); `git merge-tree --write-tree <sha> HEAD`
clean (exit 1 lists the conflicted paths; anything else, e.g. a git older than
2.38, is could not tell); the base not moved in Touch paths since HEAD's
merge-base with it (moved only outside Touch is allowed and said); a current
review receipt (`review_ledger.check_receipt`) and a verify gate VERIFIED or
NO_GATE (`review_gate.gate_state`) on HEAD. A catch-up refusal names the landing
order (catch-up, resolve, bump the version one past the base, refresh artifacts,
commit, gate the merged head, review again if the receipt reads stale,
check-land), so the gated tree is the landed tree.
Then it prints `LAND_OK head=<sha>`
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
import shutil
import stat
import subprocess
import tempfile
import sys
import time
import uuid

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
EVENT_KINDS = ("acquire", "wait", "release", "merged", "force-release", "check-land")
_REPLAYED_RE = re.compile(r"^(?:Resolved|Staged) '(.+)' using previous resolution\.$")
_PR_RE = re.compile(r"^[0-9]{1,10}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
STATES = ("waiting", "holding")
# Never rerere (owner, 2026-09-30, "Keep rerere, no autoupdate"): the shared
# rr-cache replayed another lane's crew-version resolution into T-0028 and
# set a wrong version without a word. After a catch-up merge, each of these
# still unmerged has its recorded resolution forgotten and its conflict
# markers restored, for the lane to resolve by hand.
VERSION_FILES = ("plugin/crew/.claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                 "plugin/PLUGINS.md", "CHANGELOG.md")


class TrainError(RuntimeError):
    """Could not tell: the verb refuses with exit 3."""


class NotArmed(RuntimeError):
    """The clone has no state.json: exit 1, `train not armed`."""


class Refused(RuntimeError):
    """A decided refusal raised from inside a mutation: exit 1."""


class Usage(ValueError):
    """A CLI value that is not acceptable: exit 2."""


def _plain(value, name, ref=False):
    """`value` unchanged when it is safe to store, print and pass to git; else
    Usage. A ref (`--base`, `--merged`) may not start with `-`, so git never
    reads it as an option, and carries no whitespace."""
    if value is None:
        return None
    if not isinstance(value, str) or not value or _CONTROL_RE.search(value):
        raise Usage(f"--{name} {value!r}: empty or carries a control character")
    if ref and (value.startswith("-") or re.search(r"\s", value)):
        raise Usage(f"--{name} {value!r}: not a ref (it starts with '-' or holds whitespace)")
    return value


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _owner():
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return "unknown"


# --- git -------------------------------------------------------------------------------

def _git_exe():
    """git as an absolute path (PYTHON-06), or None when it is not on PATH."""
    found = shutil.which("git")
    return os.path.abspath(found) if found else None


def _git_env():
    """The child's environment, built here (PYTHON-08): never a credential
    prompt (a fetch that needs one fails, which is could-not-tell), and no
    optional index locks taken by read-only calls."""
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")


def _git(root, *args, timeout=GIT_TIMEOUT):
    """(code, stdout, stderr); code None when git could not be started. Never
    raises: `crew_common.git_out` folds "git said no" into "could not run",
    and merge-tree's exit 1 (conflicts) versus >1 (error) matters here.
    Output is decoded as UTF-8 with `surrogateescape`, so a path git prints
    in another encoding round-trips unchanged (PYTHON-01)."""
    exe = _git_exe()
    if not exe:
        return None, "", "git is not on PATH"
    try:
        done = subprocess.run([exe, "-C", root] + list(args), capture_output=True,
                              encoding="utf-8", errors="surrogateescape", check=False,
                              timeout=timeout, stdin=subprocess.DEVNULL, env=_git_env())
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


def _records(text):
    """Split on "\n" only, a trailing "\r" stripped (PYTHON-03): never
    `splitlines()`, which also breaks inside a record on U+2028, `\x85` and
    the other characters it treats as line ends."""
    return [line[:-1] if line.endswith("\r") else line for line in (text or "").split("\n")]


def _lines(text):
    return [line for line in _records(text) if line.strip()]


def _top(root):
    top = crew_ticket.toplevel(root)
    if not top:
        raise TrainError(f"{root} is not a git worktree")
    return top


def _base(top, base):
    ref = _plain(base, "base", ref=True) or scope_base._default_ref(top)  # pylint: disable=protected-access
    if not ref:
        raise TrainError("no base ref: none of origin/HEAD, origin/main, main names a "
                         "commit here; pass --base")
    code, _out, err = _git(top, "rev-parse", "--verify", "--quiet", "--end-of-options",
                           f"{ref}^{{commit}}")
    if code == 1:
        raise Usage(f"--base {ref!r} names no commit here")
    if code != 0:
        raise TrainError(f"could not tell whether {ref!r} names a commit: {err.strip()[:200]}")
    return ref


def _head(top):
    return _git_ok(top, "rev-parse", "HEAD").strip()


def _lane(top, lane):
    if lane:
        return _plain(lane, "lane")
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


def _absent(path):
    """(True, None) only when `path` is missing (ENOENT) under an ancestor
    that is a readable directory; (False, None) when it exists; (None, why)
    when that cannot be told (GEN-01)."""
    try:
        os.lstat(path)
        return False, None
    except FileNotFoundError:
        pass
    except OSError as exc:
        return None, f"{path} cannot be looked up: {exc}"
    parent = os.path.dirname(path)
    while True:
        try:
            mode = os.lstat(parent).st_mode
        except FileNotFoundError:
            up = os.path.dirname(parent)
            if up == parent:
                return None, f"no ancestor of {path} exists"
            parent = up
            continue
        except OSError as exc:
            return None, f"{parent} cannot be looked up: {exc}"
        if not stat.S_ISDIR(mode):
            return None, f"{parent} is not a directory, so {path} cannot be looked up"
        return True, None


def _entry_problem(entry):
    if not isinstance(entry, dict):
        return "an entry is not an object"
    for key in ("ticket", "base", "worktree"):
        if not isinstance(entry.get(key), str) or not entry.get(key):
            return f"an entry's {key!r} is not a non-empty string"
    if entry.get("state") not in STATES:
        return f"{entry['ticket']}'s state {entry.get('state')!r} is not one of {STATES}"
    if not isinstance(entry.get("order"), int) or isinstance(entry.get("order"), bool):
        return f"{entry['ticket']}'s order is not an integer"
    touch = entry.get("touch")
    if touch is not None and not (isinstance(touch, list)
                                  and all(isinstance(t, str) for t in touch)):
        return f"{entry['ticket']}'s touch is neither null nor a list of strings"
    last = entry.get("last_seen")
    if not isinstance(last, int) or isinstance(last, bool):
        return f"{entry['ticket']}'s last_seen is not an integer"
    for key in ("lane", "head", "touch_source", "enqueued_at", "owner"):
        if not isinstance(entry.get(key), str):
            return f"{entry['ticket']}'s {key} is not a string"
    for key in ("acquired_at", "branch"):
        if entry.get(key) is not None and not isinstance(entry.get(key), str):
            return f"{entry['ticket']}'s {key} is neither null nor a string"
    return None


def _count(value):
    """A non-negative int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _state_problem(data):
    """Why a parsed state.json is not a schema-1 train state, or None. Every
    top-level field a verb reads is checked here, so a malformed one is could
    not tell at load, never a TypeError inside a verb (L-0558)."""
    # `_count` first: `True == 1` and `1.0 == 1`, so `!= SCHEMA` alone accepts
    # a boolean or float schema (L-0558 review round 1).
    if not isinstance(data, dict) or not _count(data.get("schema")) \
            or data.get("schema") != SCHEMA:
        return (f"it is not a schema-{SCHEMA} train state (schema "
                f"{data.get('schema') if isinstance(data, dict) else None!r})")
    for key in ("seq", "order"):
        if not _count(data.get(key)):
            return f"its {key!r} is {data.get(key)!r}, not a non-negative integer"
    if not isinstance(data.get("entries"), list):
        return "its 'entries' is not a list"
    for key in ("armed_at", "armed_by"):
        if not isinstance(data.get(key), str):
            return f"its {key!r} is {data.get(key)!r}, not a string"
    return None


def load(root):
    """(state, where, why): `where` is `absent`, `ok` or `could not tell`.
    Only a state.json proven missing (`_absent`) is `absent`; every entry is
    shape-checked, and one malformed entry makes the whole state unknown."""
    path = _state_path(root)
    missing, why = _absent(path)
    if missing is None:
        return None, "could not tell", why
    if missing:
        return None, "absent", f"{path} does not exist"
    try:
        data = json.loads(_read_file(path))
    except (OSError, ValueError) as exc:
        return None, "could not tell", f"{path} cannot be read: {exc}"
    problem = _state_problem(data)
    if problem:
        return None, "could not tell", f"{path}: {problem}"
    for entry in data["entries"]:
        problem = _entry_problem(entry)
        if problem:
            return None, "could not tell", f"{path}: entries: {problem}"
    return data, "ok", path


def _save(path, data):
    """Replace `path` whole (PYTHON-04): full text first, a private temp in
    the same directory, fsync, `os.replace`; the temp is removed if the
    replace did not happen. Held under the state lock (GEN-02)."""
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


class _Lock:
    """O_CREAT|O_EXCL lock file, `review_ledger._Lock`'s shape: PID inside,
    waits LOCK_WAIT_SECONDS, then refuses naming the path. Never removed for
    being old."""

    def __init__(self, path):
        self.path = path + ".lock"
        self.token = f"{os.getpid()} {uuid.uuid4().hex}"

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
            try:
                os.write(fd, self.token.encode())
            finally:
                os.close(fd)
            return self

    def __exit__(self, *exc):
        """Remove the lock only while it still holds this instance's token."""
        try:
            with open(self.path, encoding="utf-8") as fh:
                mine = fh.read() == self.token
            if mine:
                os.remove(self.path)
        except OSError:
            pass


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _commit(root, path, state, lines):
    """Write `lines` to the events file, then replace state.json; nothing is
    committed unless both land. Events FIRST (L-0558, review round 2 of
    L-0520): the reverse order let an append that failed after a good save
    leave a hold nobody logged, or a release nobody was told of. If the
    append or the save fails, the events file is truncated back to its size
    before this call (removed when this call created it) and the verb is
    could not tell. A process killed between the two leaves an event whose
    state change did not happen; `_mutate` numbers past it, so no seq is
    reused, and every event is advice beside `acquire`'s refusal."""
    if not lines:
        try:
            _save(path, state)
        except OSError as exc:
            raise TrainError(f"could not tell: writing {path} failed: {exc}") from exc
        return
    events = _events_path(root)
    data = ("\n".join(lines) + "\n").encode("utf-8")
    created = not os.path.lexists(events)
    try:
        fd = os.open(events, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0),
                     0o644)
    except OSError as exc:
        raise TrainError(f"could not tell: {events} cannot be opened for append: {exc}; "
                         f"nothing was written and {path} is unchanged") from exc
    size, failure, undo = None, None, "nothing was written"
    try:
        size = os.fstat(fd).st_size
        _write_all(fd, data)
        os.fsync(fd)
        _save(path, state)
    except OSError as exc:
        failure = exc
        if size is not None:
            try:
                os.ftruncate(fd, size)
                undo = f"{events} truncated back to {size} bytes"
            except OSError as again:
                undo = f"{events} could NOT be truncated back to {size} bytes ({again}); inspect it"
    finally:
        os.close(fd)
    if failure is None:
        return
    if created and size == 0 and "NOT" not in undo:
        try:
            os.remove(events)
            undo = f"{events} removed (this call created it)"
        except OSError as again:
            undo += f"; it could not be removed ({again})"
    raise TrainError(f"could not tell: writing {path} or its events failed: {failure}; {undo}; "
                     f"{path} is unchanged") from failure


def _last_seq(root):
    """The highest integer seq any line of the events file carries, or 0.
    Unreadable lines are `read_events`' business; this only keeps a seq
    from being reused after an event outlived its state change."""
    try:
        text = _read_file(_events_path(root))
    except OSError:
        return 0
    best = 0
    for line in _records(text):
        try:
            seq = json.loads(line).get("seq") if line.strip() else None
        except (ValueError, AttributeError):
            continue
        if isinstance(seq, int) and not isinstance(seq, bool):
            best = max(best, seq)
    return best


def _mutate(root, change):
    """Run `change(state, events)` under the lock on an armed, readable state.
    `events` is a list the change appends to; they are numbered with the next
    seqs and written by `_commit`, which replaces state.json only after them."""
    path = _state_path(root)
    missing, why = _absent(path)
    if missing is None:
        raise TrainError(f"could not tell: {why}")
    if missing:
        raise NotArmed("train not armed in this clone (crew_train.py arm arms it)")
    with _Lock(path):
        state, where, why = load(root)
        if where == "absent":
            raise NotArmed("train not armed in this clone (crew_train.py arm arms it)")
        if where != "ok":
            raise TrainError(f"could not tell: {why}")
        events = []
        result = change(state, events)
        lines = []
        if events:
            state["seq"] = max(state["seq"], _last_seq(root))
        for event in events:
            state["seq"] += 1
            event.setdefault("time", _now())
            event["seq"] = state["seq"]
            lines.append(json.dumps(event, sort_keys=True))
        _commit(root, path, state, lines)
    return result


def _event_problem(event):
    """Why a parsed events.jsonl record is not a train event, or None."""
    if not isinstance(event, dict):
        return "not an object"
    seq = event.get("seq")
    if not _count(seq) or seq < 1:
        return f"seq {seq!r} is not a positive integer"
    if event.get("kind") not in EVENT_KINDS:
        return f"kind {event.get('kind')!r} is not one of {', '.join(EVENT_KINDS)}"
    if not isinstance(event.get("ticket"), str) or not event.get("ticket"):
        return f"ticket {event.get('ticket')!r} is not a non-empty string"
    return None


def read_events(root, after=0):
    """(events with seq > after, problems). An unparseable line, or a valid
    JSON line without an event's shape (L-0558), is named, never silently
    dropped and never handed to a reader that would index a missing field,
    whatever its seq."""
    path = _events_path(root)
    try:
        text = _read_file(path)
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [f"{path} cannot be read: {exc}"]
    found, problems = [], []
    for number, line in enumerate(_records(text), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            problems.append(f"{path}:{number} does not parse")
            continue
        problem = _event_problem(event)
        if problem:
            # Whatever its seq (L-0558 review round 2): a malformed record at
            # or below `after` is still malformed shared history, reported on
            # every read until someone repairs the file.
            problems.append(f"{path}:{number} is not a train event ({problem})")
            continue
        if event["seq"] > after:
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
    """A repo-relative file path falls inside the FULL Touch; an undeclared
    Touch meets every path. Refresh artifacts are dropped from the overlap
    decision only (`touch_overlap`), never from this one: a base that moved a
    path this ticket's Touch names is a tree its verdict did not cover
    (L-0558, review round 2 of L-0520)."""
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
        raise Refused(f"{ticket} on {base} is held from {entry.get('worktree')}, "
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
    out = [f"{entry['ticket']}: could not tell whether {p} concerns you - check the base "
           "before you gate" for p in problems]
    for event in events:
        if event.get("kind") not in NOTICE_KINDS or event.get("ticket") == entry["ticket"]:
            continue
        if event.get("kind") == "merged":
            paths = event.get("paths")
            if not (isinstance(paths, list) and all(isinstance(p, str) for p in paths)):
                paths = None  # missing or malformed: told to everyone (PYTHON-10)
            hit = paths is None or any(meets_touch(p, entry.get("touch")) for p in paths)
            shown = "(paths unreadable)" if paths is None else ", ".join(
                p for p in paths if meets_touch(p, entry.get("touch")))
            if hit:
                out.append(f"{entry['ticket']}: {event['ticket']} merged "
                           f"{str(event.get('sha'))[:12]} touching {shown} - merge "
                           f"{event.get('base')} now")
        elif not (event.get("touch") is None or (isinstance(event.get("touch"), list) and all(
                isinstance(t, str) for t in event["touch"]))):
            out.append(f"{entry['ticket']}: {event.get('ticket')}'s hold was force-released by "
                       f"{event.get('by')} ({event.get('reason')}), its Touch unreadable - check "
                       "the base before you gate")
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
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        # os.link: the complete file appears at once or not at all, and it
        # fails if state.json already exists (GEN-02) -- no reader ever sees a
        # created-but-empty state.json.
        os.link(tmp, path)
    except FileExistsError:
        return EXIT_REFUSED, [f"train already armed in this clone ({path})"]
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return EXIT_OK, [f"train armed: {path}; every worktree of this clone now queues "
                     "gate+land through it (acquire before each gate round)"]


def disarm(root):
    path = _state_path(root)
    missing, why = _absent(path)
    if missing is None:
        raise TrainError(f"could not tell: {why}")
    if missing:
        raise NotArmed("train not armed in this clone; nothing to disarm")
    with _Lock(path):
        state, where, why = load(root)
        if where != "ok":
            raise TrainError(f"could not tell: {why}")
        if state["entries"]:
            return EXIT_REFUSED, [f"train has entries ({', '.join(e['ticket'] for e in state['entries'])}); "
                                  "release them first"]
        os.remove(path)
    return EXIT_OK, ["train disarmed"]


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
    merged = _plain(merged, "merged", ref=True)
    by, reason = _plain(by, "by"), _plain(reason, "reason")
    paths = None
    if merged:
        code, out, _ = _git(top, "diff", "--name-only", f"{merged}^1", merged, "--")
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
        return EXIT_OK, [json.dumps({"armed": False, "entries": [], "notices": []}) if as_json
                         else "armed: no"]
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
                                     "entries": state["entries"],
                                     "notices": [n for t in sorted(notices) for n in notices[t]]},
                                    sort_keys=True)]
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
                lines.append(f"    refresh artifacts not counted for overlap: {', '.join(skipped)}")
            if entry.get("state") == "waiting":
                for other, pairs in _blockers(state, entry):
                    lines.append(f"    behind {other['ticket']}: " + "; ".join(
                        f"{a} x {b}" for a, b in pairs))
            lines += [f"    stale?: {e}" for e in _stale(top, entry)]
            lines += ["    " + n for n in notices.get(entry["ticket"], [])]
    return EXIT_OK, lines


# --- catch-up and the merge log ---------------------------------------------------------------

def ensure_rerere(top):
    """Make rerere.enabled true for this worktree; the scope used. Never
    rerere.autoupdate (owner, 2026-09-30): a replay is left unstaged for the
    lane to inspect, and the catch-up merge passes `-c rerere.autoupdate=false`
    for that one invocation, so a user's own setting cannot stage one."""
    code, out, err = _git(top, "config", "--get", "--bool", "extensions.worktreeConfig")
    if code not in (0, 1):
        raise TrainError(f"could not tell whether extensions.worktreeConfig is on (git config "
                         f"exit {code}: {err.strip()[:200]}); rerere was not configured")
    scope = "--worktree" if code == 0 and out.strip() == "true" else "--local"
    _git_ok(top, "config", scope, "rerere.enabled", "true")
    return scope


def _both_sides(top, path):
    """Whether the index holds stage 2 and stage 3 for `path`."""
    stages = set()
    for line in _lines(_git_ok(top, "ls-files", "-u", "--", path)):
        meta = line.split("\t", 1)[0].split()
        if len(meta) == 3:
            stages.add(meta[2])
    return {"2", "3"} <= stages


def _forget_version_files(top, unmerged):
    """For each VERSION_FILES path the merge left unmerged: `git rerere
    forget` (which leaves the replayed bytes in the working tree) and then
    `git checkout -m` (which puts the conflict markers back). Returns the
    paths whose recorded resolution was forgotten; git prints `Forgot
    resolution for '<path>'` only when there was one (git 2.53.0). A path
    is restored whether or not that line was seen, so a git that words it
    differently still leaves the file conflicted. Only a path holding both
    sides in the index (stages 2 and 3) is touched: a modify/delete conflict
    is never rerere'd, and `checkout -m` cannot rebuild it ("does not have
    all necessary versions"), so it stays as the merge left it. (`git rerere
    status` cannot filter: it omits a path rerere just resolved.)"""
    forgotten = []
    for path in VERSION_FILES:
        if path not in unmerged or not _both_sides(top, path):
            continue
        code, out, err = _git(top, "rerere", "forget", "--", path)
        if code != 0:
            raise TrainError(f"git rerere forget -- {path} failed (exit {code}): "
                             f"{(err or out).strip()[:200]}")
        if f"Forgot resolution for '{path}'" in out + err:
            forgotten.append(path)
        _git_ok(top, "checkout", "-m", "--", path)
    return forgotten


def _remote_of(top, base):
    remotes = _lines(_git_ok(top, "remote"))
    head, _, branch = base.partition("/")
    return (head, branch) if branch and head in remotes else (None, None)


def _base_sha(top, base):
    return _git_ok(top, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}").strip()


def _fetch(top, base, fetch=True):
    """(line, sha): the commit every later step judges. Fetches
    `<remote>/<branch>` INTO the ref judged: a bare `git fetch <remote>
    <branch>` updates only FETCH_HEAD when `remote.<remote>.fetch` is unset,
    leaving `<base>` stale (L-0558), so the refspec is explicit; then `<base>`
    must name the commit FETCH_HEAD does, or could not tell. The SHA is
    returned and used from then on, never `<base>` by name again: another
    worktree's fetch can move the shared remote-tracking ref at any moment
    (L-0558 review round 2). A local base, or `fetch=False`, is resolved
    once, here."""
    if not fetch:
        return f"{base}: not fetched (--no-fetch)", _base_sha(top, base)
    remote, branch = _remote_of(top, base)
    if not remote:
        return f"{base} is local; not fetched", _base_sha(top, base)
    refspec = f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"
    code, out, err = _git(top, "fetch", "--quiet", remote, refspec)
    if code != 0:
        raise TrainError(f"could not tell: git fetch {remote} {refspec} failed (exit {code}): "
                         f"{(err or out).strip()[:300]}")
    shas = []
    for ref in ("FETCH_HEAD", base):
        code, out, err = _git(top, "rev-parse", "--verify", "--quiet", "--end-of-options",
                              f"{ref}^{{commit}}")
        if code != 0:
            raise TrainError(f"could not tell: {ref} names no commit after git fetch {remote} "
                             f"{refspec} (exit {code}): {err.strip()[:200]}")
        shas.append(out.strip())
    if shas[0] != shas[1]:
        raise TrainError(f"could not tell: {base} is {shas[1][:12]} after git fetch {remote} "
                         f"{refspec}, but FETCH_HEAD is {shas[0][:12]}; the ref judged is not the "
                         "one fetched")
    return f"fetched {remote} {branch} into {base} ({shas[0][:12]})", shas[0]


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
    dirty = _lines(_git_ok(top, "status", "--porcelain", "--untracked-files=normal", "--",
                           ".", ":(exclude).work"))
    if dirty:
        return EXIT_REFUSED, ["working tree is dirty; commit or stash first:"] + \
            ["  " + d for d in dirty[:20]]
    line, base_sha = _fetch(top, base, fetch)
    lines = [line]
    scope = ensure_rerere(top)
    lines.append(f"rerere.enabled is true ({scope}); crew never sets rerere.autoupdate, and "
                 "this merge runs with it off")
    head_before = _head(top)
    code, out, err = _git(top, "-c", "rerere.autoupdate=false", "merge", "--no-edit", base_sha)
    unknown = None
    conflicted = replayed = forgotten = None
    try:
        probe = _git(top, "rev-parse", "-q", "--verify", "MERGE_HEAD")[0]
        if code is None or probe not in (0, 1):
            raise TrainError(f"git merge exit {code}, MERGE_HEAD probe exit {probe}")
        in_merge = probe == 0
        unmerged = _lines(_git_ok(top, "diff", "--name-only", "--diff-filter=U"))
        staged = set(_lines(_git_ok(top, "diff", "--name-only", "--cached")))
        said = {m.group(1) for m in (_REPLAYED_RE.match(x.strip())
                                     for x in _records(out + "\n" + err)) if m}
        slipped = sorted(p for p in said & set(VERSION_FILES) if p not in unmerged)
        if slipped:
            raise TrainError(f"rerere resolved version files the merge left staged: "
                             f"{', '.join(slipped)}")
        forgotten = _forget_version_files(top, unmerged) if in_merge else []
        replayed = sorted(p for p in said if (p in unmerged or p in staged)
                          and p not in VERSION_FILES)
        conflicted = [p for p in unmerged if p not in replayed]
        if code == 0:
            outcome = "up-to-date" if _head(top) == head_before else "merged"
        elif in_merge:
            outcome = "conflicted" if conflicted or not replayed else "rerere-resolved"
        else:
            outcome = "refused"
    except TrainError as exc:
        outcome, unknown = "could not tell", str(exc)
    _append_merge_log(root, ticket, {
        "time": _now(), "ticket": ticket, "lane": _lane(top, lane), "worktree": top,
        "head_before": head_before, "base": base, "base_sha": base_sha, "outcome": outcome,
        "conflicted": conflicted, "rerere_replayed": replayed, "rerere_forgotten": forgotten,
        "rerere_config": scope})
    lines.append(f"catch-up {outcome}: git merge --no-edit {base_sha[:12]} (the {base} fetched)")
    if unknown:
        lines.append(f"  could not tell what the merge left: {unknown}; inspect the worktree "
                     "(git status) before anything else")
        return EXIT_UNKNOWN, lines
    if replayed:
        lines.append("  rerere replayed into the working tree, NOT staged (inspect each as a "
                     f"change, then git add it): {', '.join(replayed)}")
    if forgotten:
        lines.append("  rerere resolution forgotten (version file, never replayed - resolve it "
                     f"by hand): {', '.join(forgotten)}")
    if conflicted:
        lines.append(f"  conflicted: {', '.join(conflicted)}")
    if outcome == "refused":
        lines.append("  git: " + (err or out).strip()[:300])
    if outcome in ("conflicted", "rerere-resolved"):
        lines.append("  resolve or inspect each file, git add it, then git commit --no-edit; the "
                     "head must be gated again")
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
        missing, why = _absent(path)
        if missing:
            return [], "absent", f"{path} does not exist"
        return [], "could not tell", why or f"{path} appeared while it was read"
    except OSError as exc:
        return [], "could not tell", f"{path} cannot be read: {exc}"
    rows = []
    for number, line in enumerate(_records(text), 1):
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
        if row.get("rerere_forgotten"):
            lines.append(f"  rerere_forgotten: {', '.join(row['rerere_forgotten'])}")
    return EXIT_OK, lines


# --- check-land -----------------------------------------------------------------------------

def _merge_tree(top, base):
    code, out, err = _git(top, "merge-tree", "--write-tree", "--name-only", base, "HEAD")
    if code == 0:
        return []
    if code == 1:
        names = []
        for line in _records(out)[1:]:
            if not line.strip():
                break
            if line not in names:
                names.append(line)
        return names or ["(merge-tree reported a conflict it did not name)"]
    raise TrainError(f"could not tell: git merge-tree --write-tree exited {code} (git 2.38+ "
                     f"needed): {(err or out).strip()[:300]}")


# The landing order every catch-up refusal names (L-0522): bump and refresh
# come BEFORE the gate, so the tree the gate passed is the tree that lands.
LANDING_ORDER = ("bump the version one past the base, refresh artifacts, commit, gate the "
                 "merged head, review it again if review_ledger.py --check-receipt reads "
                 "stale, then check-land again")


def check_land(root, ticket, base=None, pr=None, fetch=True):
    top = _top(root)
    crew_ticket.check_ticket(ticket)
    if pr is not None and not _PR_RE.match(str(pr)):
        raise Usage(f"--pr {pr!r} is not a pull request number")
    base = _plain(base, "base", ref=True)
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
    # HEAD is read ONCE, before any check, and every check below judges it;
    # the final step refuses if HEAD moved meanwhile (GEN-03).
    head = _head(top)
    line, base_sha = _fetch(top, base, fetch)
    lines = [line]
    conflicts = _merge_tree(top, base_sha)
    if conflicts:
        return EXIT_REFUSED, lines + [f"merge-tree: HEAD conflicts with {base} in: "
                                      f"{', '.join(conflicts)}",
                                      f"  run crew_train.py catch-up --ticket {ticket}, "
                                      f"resolve, {LANDING_ORDER}"]
    behind, moved = _moved_paths(top, base_sha)
    in_touch = [p for p in moved if meets_touch(p, entry.get("touch"))]
    if in_touch:
        return EXIT_REFUSED, lines + [f"{base} moved in Touch paths since HEAD's merge-base: "
                                      f"{', '.join(in_touch)}",
                                      f"  run crew_train.py catch-up --ticket {ticket}, "
                                      f"{LANDING_ORDER}"]
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

    def change(fresh, events):
        # Re-checked under the lock, at the moment LAND_OK is decided: the hold
        # can be force-released and HEAD can move while the checks above ran.
        now = next((e for e in fresh["entries"] if e.get("ticket") == ticket
                    and e.get("base") == base), None)
        if now is None or now.get("state") != "holding" or now.get("worktree") != top:
            raise Refused(f"{ticket} lost its hold on {base} while check-land ran "
                          f"({'no entry' if now is None else now.get('state')}); nothing to land "
                          f"- crew_train.py acquire --ticket {ticket} and check again")
        if _head(top) != head:
            raise Refused(f"HEAD moved while check-land ran (checked {head[:12]}); gate the new "
                          "head, then check-land again")
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
    except (NotArmed, Refused) as exc:
        code, lines = EXIT_REFUSED, [str(exc)]
    except Usage as exc:
        code, lines = EXIT_USAGE, [str(exc)]
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
