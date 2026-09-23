"""crew 1.0, lane T9: the metrics harness (docs/review/04-redesign.md
"Validation").

WHERE. `.crew/metrics.jsonl`, one JSON object per line, append-only. It
replaces `.crew/metrics.md`; `/crew:migrate` (`crew_migrate.py`) writes the
historical rows there already, each carrying `_METRIC_FIELDS_1_0` set to
UNKNOWN and no `schema` key. A row this module writes always carries
`"schema": "1.0"` (or an explicit `--schema` override for a hand-reconstructed
baseline row, see `record`'s `--schema` flag) -- that key, not file identity,
is what `baseline` and `compare` use to tell a migrated 0.20 row from a
prospective 1.0 one.

APPEND-ONLY. Every write opens the file in "a" mode after the full line has
been computed as a string -- "a" never truncates, so even a write whose
argument expression raised would leave the file exactly as it was (the
CLAUDE.md `open(p, "w")` truncation trap does not apply to append mode, but
computing the full line first is kept anyway: it is what makes the write a
single `os.write`-sized call instead of several, which matters under the
lock below). Nothing here ever opens the file with "w", seeks into it, or
rewrites a previous line: rewriting metrics is an AUTONOMOUS_STOP. A stale
`escapedDefects` value is corrected by appending a new `escaped` row, not by
editing the `record` row that first wrote it -- `effective_ticket_metrics`
folds the two by taking the latest value per ticket, per field.

CONCURRENT WRITERS. `_Lock` is `review_ledger._Lock`'s O_CREAT|O_EXCL design,
reused rather than re-derived, held only around the read-then-append.

SOURCES, and what UNKNOWN means for each (never 0 -- a 0 is a real count this
module measured, an UNKNOWN is a count it could not):

  phases           the review ledger's round timestamps
                    (`review_ledger.status`) plus the ticket's approval
                    receipt (`crew_ticket.status`) plus "recorded" (now).
                    A phase this ticket has no data for is simply absent from
                    the list, not a phase with an UNKNOWN timestamp.
  activeTime        `--transcript <path>`: the sum of gaps between
                    consecutive main-chain transcript events, each gap capped
                    at `--idle-threshold-seconds` (default
                    `DEFAULT_IDLE_SECONDS`). UNKNOWN without `--transcript`:
                    no environment variable reliably names a slash command's
                    own transcript path (unlike a hook payload, which carries
                    `transcript_path` -- see `crew_context.py`), so the
                    caller must pass it explicitly or leave the field
                    UNKNOWN. This is a decision the brief left open.
  tokens            the same transcript: the sum of every main-chain
                    assistant message's `usage` fields. This over-counts
                    against a true "billed tokens" figure (context resent on
                    every turn is counted every time it appears), and is
                    reported as such -- it is the only figure obtainable
                    from a transcript alone, with no session-report tool
                    wired in. UNKNOWN without `--transcript`.
  cost              always UNKNOWN: no transcript or session-report source in
                    this repository prices a session. `--cost` (a plain
                    override) is accepted for a future wiring but nothing
                    computes it yet.
  reviewRounds      `review_ledger.status(root, ticket)["rounds"]`, verbatim
                    (round, provider, model, verdict, timestamps). UNKNOWN if
                    the ledger is corrupt.
  findingsConfirmed / findingsRejected / findingsDuplicate
                    UNKNOWN, always, from `record`. The review ledger records
                    BLOCK/FIX/NIT SEVERITY counts per round
                    (`review_verdict.parse`), not a confirmed/rejected/
                    duplicate disposition on each finding -- no source in
                    this repository derives that triage automatically. A
                    decision the brief left open: it is not guessed from the
                    severity counts, which measure something else.
  scopeBlocks       `.crew/guard.log` (`scope_guard._log`'s tab-separated
                    rows), counting rows for this ticket whose decision
                    column is "block". UNKNOWN when the log file does not
                    exist at all (the guard may never have run this ticket);
                    a real 0 when the log exists and simply has no "block"
                    row for this ticket.
  injectedChars     the context-log (`crew_context.log_path`), summing
                    `chars` for `--session <id>` (or the session recorded on
                    the ticket's approval receipt, when it was approved via
                    the user's prompt). UNKNOWN with neither.
  escapedDefects    UNKNOWN from `record`; set later, per ticket, by
                    `escaped --ticket <id> --count N --note <text>`, which
                    appends a new row rather than editing the first one.

`baseline` and `compare` read effective per-ticket metrics through
`effective_ticket_metrics`, which folds every row for a ticket id in
append order -- a later `escaped` row's fields win over an earlier `record`
row's, and an earlier `record` row's non-UNKNOWN fields survive a later row
that leaves them UNKNOWN (UNKNOWN never overwrites a known value).

Exit codes: 0 ok; 1 refused / error; 2 usage.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time

import completion_audit
import crew_context
import crew_ticket
import review_ledger

UNKNOWN = "UNKNOWN"
SCHEMA_1_0 = "1.0"
DEFAULT_IDLE_SECONDS = 300
MIN_COMPARE_TICKETS = 10

METRIC_FIELDS = (
    "phases", "activeTime", "tokens", "cost", "reviewRounds",
    "findingsConfirmed", "findingsRejected", "findingsDuplicate",
    "scopeBlocks", "injectedChars", "unapprovedScopeChanges", "escapedDefects",
)

_GUARD_LOG = os.path.join(".crew", "guard.log")
_TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class MetricsError(RuntimeError):
    """A metrics operation that could not be carried out."""


def _now():
    import datetime  # pylint: disable=import-outside-toplevel
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check_ticket(ticket):
    if not isinstance(ticket, str) or not _TICKET_RE.match(ticket):
        raise MetricsError(f"ticket id {ticket!r} is not a plain id "
                           "(letters, digits, '.', '_', '-'; no path separators)")
    return ticket


def metrics_path(root):
    return os.path.join(root, ".crew", "metrics.jsonl")


class _Lock:
    """O_CREAT|O_EXCL lock, `review_ledger._Lock`'s design, held for one
    read-then-append."""

    WAIT_SECONDS = 10.0

    def __init__(self, path):
        self.path = path + ".lock"

    def __enter__(self):
        deadline = time.monotonic() + self.WAIT_SECONDS
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() > deadline:
                    raise MetricsError(
                        f"metrics lock {self.path} has been held for over "
                        f"{self.WAIT_SECONDS:.0f}s. If nothing is recording, a process "
                        "died holding it -- remove that file by hand") from exc
                time.sleep(0.02)
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def read_rows(root):
    """(rows, unparseable): every line of metrics.jsonl that parses as a
    JSON object, in file order. A line that does not parse is counted, never
    guessed at."""
    path = metrics_path(root)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return [], 0
    rows, bad = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


def append_row(root, row):
    """Append one JSON line, atomically with respect to other appenders of
    this file, and prove the file's prior bytes are unchanged first."""
    path = metrics_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(row, sort_keys=True) + "\n"
    with _Lock(path):
        try:
            with open(path, "rb") as handle:
                before = handle.read()
        except FileNotFoundError:
            before = b""
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
        with open(path, "rb") as handle:
            after = handle.read()
        if after[:len(before)] != before:
            raise MetricsError(f"{path} changed underneath the lock; refusing -- "
                               "this must never rewrite a prior line")
    return row


# --------------------------------------------------------------------------
# sources

def _phases(root, ticket):
    """[{"phase", "at"}], built only from timestamps a source actually has."""
    phases = []
    status = crew_ticket.status(root, ticket)
    receipt = status.get("receipt") or {}
    if receipt.get("approved_at"):
        phases.append({"phase": "specApproved", "at": receipt["approved_at"]})
    ledger = review_ledger.status(root, ticket)
    for rnd in ledger.get("rounds") or []:
        number = rnd.get("round")
        if rnd.get("reserved_at"):
            phases.append({"phase": f"reviewRound{number}Reserved", "at": rnd["reserved_at"]})
        if rnd.get("completed_at"):
            phases.append({"phase": f"reviewRound{number}Completed", "at": rnd["completed_at"]})
    phases.append({"phase": "recorded", "at": _now()})
    return phases


def _review_rounds(root, ticket):
    """(rounds_list_or_UNKNOWN, source_note)."""
    path = review_ledger.ledger_path(root, ticket)
    data, state = review_ledger._load(path)  # pylint: disable=protected-access
    if state == "corrupt":
        return UNKNOWN, f"{path}: unreadable"
    if state == "absent":
        return [], f"{path}: no review ledger (0 rounds)"
    rounds = [{"round": r.get("round"), "provider": r.get("provider"),
              "model": r.get("model"), "verdict": r.get("verdict"),
              "reserved_at": r.get("reserved_at"), "completed_at": r.get("completed_at")}
              for r in data.get("rounds") or []]
    return rounds, path


def _scope_blocks(root, ticket):
    """(count_or_UNKNOWN, source_note)."""
    path = os.path.join(root, _GUARD_LOG)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return UNKNOWN, f"{path}: does not exist; the scope guard may never have run"
    count = 0
    for line in text.splitlines():
        cells = line.split("\t")
        if len(cells) >= 5 and cells[1] == "scope" and cells[3] == "block" and cells[4] == ticket:
            count += 1
    return count, path


def _injected_chars(root, ticket, session):
    """(count_or_UNKNOWN, source_note). `session` may be given explicitly or
    left None to fall back to the ticket's approval receipt."""
    if not session:
        status = crew_ticket.status(root, ticket)
        session = (status.get("receipt") or {}).get("session_id")
    if not session:
        return UNKNOWN, "no --session and no user-prompt approval session_id on this ticket"
    path = crew_context.log_path(root)
    text = crew_context.read_log(root)
    if not text and not os.path.exists(path):
        return UNKNOWN, f"{path}: does not exist"
    total = 0
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("session") == session:
            total += int(rec.get("chars") or 0)
    return total, f"{path} (session {session})"


def _unapproved_scope_changes(root, ticket):
    """(count_or_UNKNOWN, source_note) from the completion audit's own
    outside-Touch check, run read-only (no exit-code side effects here)."""
    try:
        ok, lines = completion_audit.audit(root, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return UNKNOWN, f"completion audit failed: {type(exc).__name__}: {exc}"
    if ok:
        return 0, "completion_audit.audit: every change in Touch"
    match = re.search(r"^COMPLETION AUDIT: (\d+) changed path", lines[0]) if lines else None
    if match:
        return int(match.group(1)), "completion_audit.audit"
    # A failure for a reason other than "paths outside touch" (e.g. Touch
    # itself unapproved) does not tell us a COUNT of unapproved changes.
    return UNKNOWN, f"completion_audit.audit: {lines[0] if lines else 'failed'}"


def _transcript_events(transcript):
    """[(timestamp_str, record)] for every main-chain (non-sidechain) line
    that carries a "timestamp", sorted. Never raises: an unreadable or
    missing transcript yields an empty list."""
    events = []
    try:
        with open(transcript, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except (OSError, TypeError):
        return events
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or not rec.get("timestamp"):
            continue
        if rec.get("isSidechain") is True:
            continue
        events.append((rec["timestamp"], rec))
    events.sort(key=lambda pair: pair[0])
    return events


def _parse_iso(ts):
    import datetime  # pylint: disable=import-outside-toplevel
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def active_time_seconds(transcript, idle_threshold=DEFAULT_IDLE_SECONDS):
    """Sum of gaps between consecutive main-chain transcript events, each
    capped at `idle_threshold` seconds. UNKNOWN with fewer than two usable
    timestamps -- there is no gap to measure, which is not the same as a
    measured 0."""
    events = _transcript_events(transcript)
    times = [t for t in (_parse_iso(ts) for ts, _ in events) if t is not None]
    if len(times) < 2:
        return UNKNOWN
    total = 0.0
    for prev, cur in zip(times, times[1:]):
        gap = (cur - prev).total_seconds()
        if gap > 0:
            total += min(gap, idle_threshold)
    return total


def transcript_tokens(transcript):
    """Sum of every main-chain assistant message's usage fields. UNKNOWN when
    no assistant message with usage was found."""
    events = _transcript_events(transcript)
    found = False
    total = 0
    for _, rec in events:
        if rec.get("type") != "assistant":
            continue
        message = rec.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        found = True
        total += sum(int(usage.get(k) or 0) for k in (
            "input_tokens", "output_tokens", "cache_read_input_tokens",
            "cache_creation_input_tokens"))
    return total if found else UNKNOWN


# --------------------------------------------------------------------------
# record

def record(root, ticket, transcript=None, session=None, idle_threshold=DEFAULT_IDLE_SECONDS,
           cost=None, schema=SCHEMA_1_0):
    """Build and append one row for `ticket`. Returns the row."""
    check_ticket(ticket)
    review_rounds, review_source = _review_rounds(root, ticket)
    scope_blocks, scope_source = _scope_blocks(root, ticket)
    injected, injected_source = _injected_chars(root, ticket, session)
    unapproved, unapproved_source = _unapproved_scope_changes(root, ticket)
    if transcript:
        active = active_time_seconds(transcript, idle_threshold)
        tokens = transcript_tokens(transcript)
        transcript_note = transcript
    else:
        active = UNKNOWN
        tokens = UNKNOWN
        transcript_note = "no --transcript given"
    row = {
        "schema": schema,
        "kind": "record",
        "ticket": ticket,
        "ticketId": ticket,
        "recordedAt": _now(),
        "phases": _phases(root, ticket),
        "activeTime": active,
        "tokens": tokens,
        "cost": cost if cost is not None else UNKNOWN,
        "reviewRounds": review_rounds,
        "findingsConfirmed": UNKNOWN,
        "findingsRejected": UNKNOWN,
        "findingsDuplicate": UNKNOWN,
        "scopeBlocks": scope_blocks,
        "injectedChars": injected,
        "unapprovedScopeChanges": unapproved,
        "escapedDefects": UNKNOWN,
        "source": {
            "reviewRounds": review_source, "scopeBlocks": scope_source,
            "injectedChars": injected_source, "unapprovedScopeChanges": unapproved_source,
            "activeTime": transcript_note, "tokens": transcript_note,
            "cost": "no cost source wired in" if cost is None else "--cost",
            "findingsConfirmed": "no automatic source (review ledger records severity, "
                                 "not disposition)",
            "findingsRejected": "no automatic source (review ledger records severity, "
                                "not disposition)",
            "findingsDuplicate": "no automatic source (review ledger records severity, "
                                 "not disposition)",
            "escapedDefects": "set later via `crew_metrics.py escaped`",
        },
    }
    return append_row(root, row)


def escaped(root, ticket, count, note=""):
    """Append an `escaped` row updating `ticket`'s escapedDefects. Does not
    touch the earlier `record` row -- append-only."""
    check_ticket(ticket)
    if not isinstance(count, int) or count < 0:
        raise MetricsError("--count must be a non-negative integer")
    row = {
        "schema": SCHEMA_1_0, "kind": "escaped", "ticket": ticket, "ticketId": ticket,
        "recordedAt": _now(), "escapedDefects": count, "note": note or UNKNOWN,
    }
    return append_row(root, row)


# --------------------------------------------------------------------------
# baseline / compare

def _is_legacy(row):
    return row.get("schema") in (None, "0.20", "migrated")


def _row_ticket(row):
    return row.get("ticketId") or row.get("ticket")


def effective_ticket_metrics(rows):
    """{ticketId: {field: value}}, folding every row for a ticket in file
    order. A later row's non-UNKNOWN value for a field wins; UNKNOWN never
    overwrites an earlier known value."""
    by_ticket = {}
    for row in rows:
        ticket = _row_ticket(row)
        if not ticket:
            continue
        current = by_ticket.setdefault(ticket, {})
        for field in METRIC_FIELDS:
            if field not in row:
                continue
            value = row[field]
            if value == UNKNOWN and field in current and current[field] != UNKNOWN:
                continue
            current[field] = value
        current.setdefault("_schema", row.get("schema"))
    return by_ticket


def _median(values):
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    med = statistics.median(nums) if nums else None
    return (med, len(nums), len(values) - len(nums))


def baseline(root):
    """Median activeTime/cost over every 0.20/migrated ticket in
    metrics.jsonl, with n and UNKNOWN counts. Historical rows almost always
    have UNKNOWN activeTime/cost (`/crew:migrate` marks them so) -- a
    hand-reconstructed one can be added with `record --schema 0.20
    --transcript <old-transcript>`."""
    rows, _bad = read_rows(root)
    legacy = [r for r in rows if _is_legacy(r)]
    by_ticket = effective_ticket_metrics(legacy)
    active_med, active_n, active_unknown = _median([v.get("activeTime") for v in by_ticket.values()])
    cost_med, cost_n, cost_unknown = _median([v.get("cost") for v in by_ticket.values()])
    return {
        "n": len(by_ticket),
        "medianActiveTime": active_med, "activeTimeKnown": active_n,
        "activeTimeUnknown": active_unknown,
        "medianCost": cost_med, "costKnown": cost_n, "costUnknown": cost_unknown,
    }


def _select_prospective(rows, since):
    prospective = [r for r in rows if r.get("schema") == SCHEMA_1_0]
    by_ticket = effective_ticket_metrics(prospective)
    order = []
    for row in prospective:
        ticket = _row_ticket(row)
        if ticket and ticket not in order:
            order.append(ticket)
    try:
        n = int(since)
        chosen = order[-n:] if n > 0 else []
    except (TypeError, ValueError):
        chosen = [t for t in order
                 if any(r.get("recordedAt", "") >= since for r in prospective
                        if _row_ticket(r) == t)]
    return {t: by_ticket[t] for t in chosen if t in by_ticket}


def compare(root, since):
    """Prospective 1.0 tickets (selected by `since`, a count or an ISO date)
    against the 0.20 baseline. Prints medians, % change, review-budget
    enforcement, unapproved scope changes and escaped defects, with a
    PASS/FAIL per success criterion, or INSUFFICIENT DATA below
    MIN_COMPARE_TICKETS."""
    rows, _bad = read_rows(root)
    base = baseline(root)
    prospective = _select_prospective(rows, since)
    result = {"n": len(prospective), "baseline": base, "tickets": sorted(prospective)}
    if len(prospective) < MIN_COMPARE_TICKETS:
        result["verdict"] = "INSUFFICIENT DATA"
        result["why"] = (f"{len(prospective)} prospective ticket(s), need at least "
                         f"{MIN_COMPARE_TICKETS}")
        return result
    active_med, active_n, active_unknown = _median([v.get("activeTime") for v in prospective.values()])
    cost_med, cost_n, cost_unknown = _median([v.get("cost") for v in prospective.values()])
    result["medianActiveTime"] = active_med
    result["activeTimeKnown"] = active_n
    result["activeTimeUnknown"] = active_unknown
    result["medianCost"] = cost_med
    result["costKnown"] = cost_n
    result["costUnknown"] = cost_unknown

    def pct_change(new, old):
        if not isinstance(new, (int, float)) or not isinstance(old, (int, float)) or old == 0:
            return None
        return (new - old) / old * 100

    active_pct = pct_change(active_med, base["medianActiveTime"])
    cost_pct = pct_change(cost_med, base["medianCost"])
    result["activeTimePctChange"] = active_pct
    result["costPctChange"] = cost_pct
    time_or_cost_pass = ((active_pct is not None and active_pct <= -30)
                         or (cost_pct is not None and cost_pct <= -30))
    result["criteria"] = {}
    result["criteria"]["30pctLowerActiveTimeOrCost"] = (
        "PASS" if time_or_cost_pass else
        ("INSUFFICIENT DATA" if active_pct is None and cost_pct is None else "FAIL"))

    # The ledger itself refuses a reservation past BUDGET unless an approved
    # successor plan reopened it (review_ledger.reserve), so "enforced" here
    # means "confirmable from the ledger", not "counted <= BUDGET" -- a
    # ticket with an approved successor legitimately carries more rounds.
    known_rounds = [v for v in prospective.values() if v.get("reviewRounds") != UNKNOWN]
    enforcement_rate = len(known_rounds) / len(prospective) if prospective else 0
    result["reviewBudgetEnforcementRate"] = enforcement_rate
    result["criteria"]["reviewBudgetEnforcement100pct"] = (
        "PASS" if enforcement_rate == 1.0 else "FAIL")

    scope_values = [v.get("unapprovedScopeChanges") for v in prospective.values()]
    known_scope = [v for v in scope_values if v != UNKNOWN]
    total_unapproved = sum(v for v in known_scope if isinstance(v, int))
    result["unapprovedScopeChanges"] = total_unapproved
    result["unapprovedScopeChangesUnknown"] = len(scope_values) - len(known_scope)
    result["criteria"]["zeroUnapprovedScopeChanges"] = (
        "INSUFFICIENT DATA" if len(known_scope) < len(scope_values) and total_unapproved == 0
        else ("PASS" if total_unapproved == 0 else "FAIL"))

    escaped_values = [v.get("escapedDefects") for v in prospective.values()]
    known_escaped = [v for v in escaped_values if isinstance(v, int)]
    total_escaped = sum(known_escaped)
    result["escapedDefects"] = total_escaped
    result["escapedDefectsUnknown"] = len(escaped_values) - len(known_escaped)
    baseline_escaped_known = base.get("n", 0) > 0  # baseline rarely carries this field either
    result["criteria"]["noRiseInEscapedDefects"] = (
        "INSUFFICIENT DATA" if not baseline_escaped_known else
        ("PASS" if total_escaped == 0 else "FAIL"))
    result["verdict"] = ("PASS" if all(v == "PASS" for v in result["criteria"].values())
                         else ("INSUFFICIENT DATA"
                               if any(v == "INSUFFICIENT DATA" for v in result["criteria"].values())
                               else "FAIL"))
    return result


# --------------------------------------------------------------------------
# CLI

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="append a metrics row for a ticket")
    rec.add_argument("--root", default=".")
    rec.add_argument("--ticket", required=True)
    rec.add_argument("--transcript")
    rec.add_argument("--session")
    rec.add_argument("--idle-threshold-seconds", type=int, default=DEFAULT_IDLE_SECONDS)
    rec.add_argument("--cost", type=float)
    rec.add_argument("--schema", default=SCHEMA_1_0,
                     help="1.0 (default) for a prospective ticket, or 0.20 to hand-"
                          "reconstruct a baseline row from an old transcript")

    esc = sub.add_parser("escaped", help="record escaped defects found after done")
    esc.add_argument("--root", default=".")
    esc.add_argument("--ticket", required=True)
    esc.add_argument("--count", type=int, required=True)
    esc.add_argument("--note", default="")

    base_p = sub.add_parser("baseline", help="median activeTime/cost over 0.20 tickets")
    base_p.add_argument("--root", default=".")

    cmp_p = sub.add_parser("compare", help="prospective 1.0 tickets vs the 0.20 baseline")
    cmp_p.add_argument("--root", default=".")
    cmp_p.add_argument("--since", required=True,
                       help="an integer (last N prospective tickets) or an ISO date "
                            "(YYYY-MM-DD, tickets recorded on/after it)")

    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        if args.cmd == "record":
            row = record(root, args.ticket, transcript=args.transcript, session=args.session,
                        idle_threshold=args.idle_threshold_seconds, cost=args.cost,
                        schema=args.schema)
            print(json.dumps(row, indent=2, sort_keys=True))
            return 0
        if args.cmd == "escaped":
            row = escaped(root, args.ticket, args.count, args.note)
            print(json.dumps(row, indent=2, sort_keys=True))
            return 0
        if args.cmd == "baseline":
            print(json.dumps(baseline(root), indent=2, sort_keys=True))
            return 0
        result = compare(root, args.since)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] in ("PASS", "INSUFFICIENT DATA") else 1
    except MetricsError as exc:
        sys.stderr.write(f"crew-metrics: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
