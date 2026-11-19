"""Durable ids for tracker posts, so a timed-out post is never duplicated (R-72).

    python3 crew_tracker.py event begin  --ticket ABC-12 --event done
    python3 crew_tracker.py event record --ticket ABC-12 --event done --state posted|unknown|failed [--ref <id>]
    python3 crew_tracker.py event post   --ticket T-0042 --event done      (files, obsidian)
    python3 crew_tracker.py events       --ticket ABC-12 [--json]

An event id is `crew-evt-` plus 20 hex characters of sha256 over the repo id,
the ticket, the event kind and its discriminator, joined by \\x1f: the same in
every session and after a crash, so the remote copy, carrying the plain last
line `crew-event: <id>`, is the proof of a post. The ledger is one file per
event under `<git-common-dir>/crew/tickets/<ID>/events/`, shared by every
worktree, claimed with O_CREAT|O_EXCL|O_NOFOLLOW and updated by a full write
to an exclusive temp, then `os.replace`. It holds no body: id, kind,
discriminator, ticket, state, time, attempts and the remote ref.

`begin` answers, one line `<answer>: <id>`:

- `post`: no record existed; this call claimed it (state `intent`).
- `in-flight`: an `intent` younger than IN_FLIGHT_SECONDS; another session is
  posting. Do not post; report.
- `check-remote`: any other record (`intent` older, `unknown`, `failed`): search
  the remote for the marker before anything is posted.
- `skip`: already `posted`.
- `could not tell`: the record cannot be read; exit 1, never `post`.

A timeout or a missing answer is recorded `unknown`, never `failed`.
"""
import datetime
import hashlib
import json
import os
import secrets
import stat
import time

import crew_common

EVENT_KINDS = ("approved-spec", "progress", "review-round", "fix", "done", "land", "clean-up")
# Kinds that happen once per ticket: their discriminator is fixed.
FIXED_DISCRIMINATOR = {"done": "1", "clean-up": "1"}
RECORD_STATES = ("posted", "unknown", "failed")
INTENT, POSTED = "intent", "posted"
IN_FLIGHT_SECONDS = 120
MARKER = "crew-event: "
COULD_NOT_TELL = "could not tell"

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_CLAIM_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _BINARY
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _BINARY
_SEP = "\x1f"
_EMPTY_RETRIES = 20  # a claim is opened, then written: an empty file is a writer mid-write


class UsageError(ValueError):
    """A request the CLI answers with exit 2."""


def discriminator(kind, disc):
    """The discriminator for event `kind`, or UsageError."""
    if kind not in EVENT_KINDS:
        raise UsageError(f"event kind {kind!r} is not one of {', '.join(EVENT_KINDS)}")
    fixed = FIXED_DISCRIMINATOR.get(kind)
    if fixed is not None:
        if disc not in (None, fixed):
            raise UsageError(f"{kind} happens once per ticket; its discriminator is fixed at {fixed}")
        return fixed
    if not disc or _SEP in disc or "\n" in disc:
        raise UsageError(f"{kind} repeats, so it needs --disc (one line)")
    return disc


def event_id(repo, ticket, kind, disc):
    """`crew-evt-<20 hex>`: deterministic over the four parts."""
    raw = _SEP.join((repo, ticket, kind, disc)).encode("utf-8")
    return "crew-evt-" + hashlib.sha256(raw).hexdigest()[:20]


def marker(eid):
    """The plain last line of every posted body."""
    return MARKER + eid


def ledger_dir(common, ticket):
    """`<git-common-dir>/crew/tickets/<ID>/events`, the ticket id checked."""
    if not isinstance(ticket, str) or not crew_common.TICKET_ID.match(ticket):
        raise UsageError(f"ticket id {ticket!r} is not a ticket id")
    return os.path.join(common, "crew", "tickets", ticket, "events")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode(record):
    return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load(path):
    """`(record, problem)`: (None, None) absent, (dict, None) read, else a problem.
    A link, or anything but a regular file, at the name is a problem, never followed."""
    for _ in range(_EMPTY_RETRIES):
        try:
            seen = os.lstat(path)
        except FileNotFoundError:
            return None, None
        except OSError as exc:
            return None, f"{path}: {exc.strerror or exc}"
        if not stat.S_ISREG(seen.st_mode):
            return None, f"{path} is not a regular file; refusing to follow it"
        try:
            fd = os.open(path, _READ_FLAGS)
            with os.fdopen(fd, "rb") as handle:
                raw = handle.read()
        except FileNotFoundError:
            return None, None
        except OSError as exc:
            return None, f"{path}: {exc.strerror or exc}"
        if raw:
            return _decode(raw, path)
        time.sleep(0.05)
    return None, f"{path} is empty"


def _decode(raw, path):
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, f"{path} is not valid JSON"
    if not isinstance(record, dict) or not isinstance(record.get("state"), str):
        return None, f"{path} has no state"
    return record, None


def _age(path):
    try:
        return time.time() - os.lstat(path).st_mtime
    except OSError:
        return None


def _answer(record, age):
    """What `begin` says for an existing record."""
    state = record.get("state")
    if state == POSTED:
        return "skip"
    if state == INTENT and age is not None and age < IN_FLIGHT_SECONDS:
        return "in-flight"
    if state in (INTENT,) + RECORD_STATES:
        return "check-remote"
    return COULD_NOT_TELL


def _claim(path, record):
    """True when this call created the record, False when one was there."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, _CLAIM_FLAGS, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(_encode(record))
    return True


def _replace(path, record):
    """The full record to an exclusive temp beside `path`, then os.replace."""
    temp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.{secrets.token_hex(6)}.tmp")
    fd = os.open(temp, _CLAIM_FLAGS, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_encode(record))
        os.replace(temp, path)
    except BaseException:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise


def _fresh(eid, ticket, kind, disc, state):
    return {"id": eid, "kind": kind, "discriminator": disc, "ticket": ticket, "state": state,
            "time": _now(), "attempts": 1, "ref": None}


def begin(ledger, eid, ticket, kind, disc):
    """`(answer, problem)`: answer is post, in-flight, check-remote, skip or could not tell."""
    path = os.path.join(ledger, eid + ".json")
    if _claim(path, _fresh(eid, ticket, kind, disc, INTENT)):
        return "post", None
    record, problem = _load(path)
    if problem:
        return COULD_NOT_TELL, problem
    if record is None:
        # Gone between the claim and the read (deleted by hand): claim it again.
        _replace(path, _fresh(eid, ticket, kind, disc, INTENT))
        return "post", None
    answer = _answer(record, _age(path))
    if answer == COULD_NOT_TELL:
        return answer, f"{path} has state {record.get('state')!r}, which crew does not know"
    return answer, None


def record_outcome(ledger, eid, state, ref=None):
    """`(line, problem)` after writing `state` into the existing record."""
    if state not in RECORD_STATES:
        raise UsageError(f"--state must be one of {', '.join(RECORD_STATES)}")
    path = os.path.join(ledger, eid + ".json")
    record, problem = _load(path)
    if problem:
        return None, problem
    if record is None:
        return None, f"no claim for {eid}; run event begin first"
    record.update(state=state, time=_now(), attempts=int(record.get("attempts") or 0) + (
        1 if record.get("state") != INTENT else 0))
    if ref:
        record["ref"] = ref
    _replace(path, record)
    return f"recorded: {eid} {state}", None


def post_local(ledger, eid, ticket, kind, disc):
    """files/obsidian: the ledger is the record. `(line, problem)`."""
    path = os.path.join(ledger, eid + ".json")
    if _claim(path, _fresh(eid, ticket, kind, disc, POSTED)):
        return f"posted: {eid}", None
    record, problem = _load(path)
    if problem:
        return None, problem
    if record is not None and record.get("state") == POSTED:
        return f"unchanged: {eid} already posted", None
    _replace(path, _fresh(eid, ticket, kind, disc, POSTED))
    return f"posted: {eid}", None


def list_events(ledger):
    """`(records, problems)` for every event file of one ticket. Writes nothing."""
    try:
        names = sorted(n for n in os.listdir(ledger) if n.endswith(".json") and not n.startswith("."))
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [f"{ledger}: {exc.strerror or exc}"]
    records, problems = [], []
    for name in names:
        record, problem = _load(os.path.join(ledger, name))
        if problem:
            problems.append(problem)
        elif record is not None:
            records.append(record)
    records.sort(key=lambda r: (str(r.get("time")), str(r.get("id"))))
    return records, problems


def list_cli(ledger, as_json):
    """`(exit code, lines)` for `events`."""
    records, problems = list_events(ledger)
    if as_json:
        return (1 if problems else 0), [json.dumps({"events": records, "problems": problems},
                                                   indent=2, sort_keys=True)]
    lines = [f"{r.get('id')} {r.get('kind')} {r.get('discriminator')} {r.get('state')}" for r in records]
    lines += [f"{COULD_NOT_TELL}: {p}" for p in problems]
    return (1 if problems else 0), lines or ["no events"]


_LOCAL_KINDS = ("files", "obsidian")
_REMOTE_KINDS = ("jira", "sdp")


def event_cli(ledger, repo, tracker_kind, args):
    """`(exit code, lines)` for `event begin|record|post`."""
    try:
        if repo is None:
            return 1, [f"{COULD_NOT_TELL}: this repo's identity, so no event id"]
        disc = discriminator(args.event, args.disc)
        eid = event_id(repo, args.ticket, args.event, disc)
        if args.op == "post":
            if tracker_kind not in _LOCAL_KINDS:
                raise UsageError(f"event post is for files and obsidian; {tracker_kind} posts through "
                                 "event begin, the marker search and event record")
            line, problem = post_local(ledger, eid, args.ticket, args.event, disc)
        elif tracker_kind not in _REMOTE_KINDS:
            raise UsageError(f"event {args.op} is for jira and sdp; {tracker_kind} uses event post")
        elif args.op == "begin":
            answer, problem = begin(ledger, eid, args.ticket, args.event, disc)
            line = None if problem else f"{answer}: {eid}"
        else:
            line, problem = record_outcome(ledger, eid, args.state, args.ref)
    except UsageError as exc:
        return 2, [f"event: {exc}"]
    except OSError as exc:
        return 1, [f"{COULD_NOT_TELL}: {exc.strerror or exc}"]
    if problem:
        return 1, [f"{COULD_NOT_TELL}: {problem}"]
    return 0, [line]
