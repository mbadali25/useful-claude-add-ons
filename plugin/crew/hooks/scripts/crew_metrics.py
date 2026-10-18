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
import crew_common
import crew_context
import crew_ticket
import review_ledger

UNKNOWN = "UNKNOWN"
SCHEMA_1_0 = "1.0"
SCHEMA_1_1 = "1.1"
# Rows that carry the measurement group fold it as one unit (B5).
MEASUREMENT_GROUP = ("tokens", "cost", "tokensBasis", "tokensAttribution", "pricesAsOf",
                     "pricesSource", "sourceTokens", "sourceCost")
DEFAULT_IDLE_SECONDS = 300
MIN_COMPARE_TICKETS = 10
# The 30% criterion compares medians; a median over fewer than this many
# KNOWN values (on either the prospective or the baseline side) is not
# trustworthy enough to PASS on -- a comparison may PASS only on sufficient
# KNOWN data.
MIN_BASELINE_KNOWN = 10

METRIC_FIELDS = (
    "phases", "activeTime", "tokens", "cost", "reviewRounds",
    "findingsConfirmed", "findingsRejected", "findingsDuplicate",
    "scopeBlocks", "injectedChars", "unapprovedScopeChanges", "escapedDefects",
)

_GUARD_LOG = os.path.join(".crew", "guard.log")
_TICKET_RE = crew_common.PLAIN_ID


class MetricsError(RuntimeError):
    """A metrics operation that could not be carried out."""


def _now():
    import datetime  # pylint: disable=import-outside-toplevel
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check_ticket(ticket):
    if not isinstance(ticket, str) or not _TICKET_RE.match(ticket):
        raise MetricsError(f"ticket id {ticket!r} is not a plain id "
                           "(letters, digits, '.', '_', '-'; no path separators)")
    if crew_common.reserved_id(ticket):
        raise MetricsError(f"{ticket!r} is reserved for the archive folder, not a ticket id")
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
        # A prior writer's final record can lack a trailing newline (a crash
        # mid-write, or a hand-edited file) -- appending straight onto that
        # would concatenate our JSON object onto the end of theirs on the
        # same physical line. Insert the missing separator first.
        prefix = "\n" if before and not before.endswith(b"\n") else ""
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(prefix + line)
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


_GUARD_LOG_FIELDS = 7  # scope_guard._log: time, "scope", mode, decision, ticket, path, reason


def _scope_blocks(root, ticket):
    """(count_or_UNKNOWN, source_note). A row that does not split into the
    shape `scope_guard._log` writes (truncated by a crash mid-write, or hand-
    edited) is not silently skipped -- it makes the whole count unreliable,
    since a block row for this ticket could be hiding inside it, so the
    result is UNKNOWN rather than a count that quietly excludes it."""
    path = os.path.join(root, _GUARD_LOG)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return UNKNOWN, f"{path}: does not exist; the scope guard may never have run"
    count = 0
    malformed = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) != _GUARD_LOG_FIELDS:
            malformed += 1
            continue
        if cells[1] == "scope" and cells[3] == "block" and cells[4] == ticket:
            count += 1
    if malformed:
        return UNKNOWN, f"{path}: {malformed} malformed/truncated row(s), count not trustworthy"
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
    matched = 0
    unmeasured = 0
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("session") != session:
            continue
        matched += 1
        chars = rec.get("chars")
        if isinstance(chars, bool) or not isinstance(chars, int):
            # A matching record with no (or non-numeric) `chars` is not a
            # real 0 -- it is a record this source could not measure, and
            # folding it into the sum would under-report a real total.
            unmeasured += 1
            continue
        total += chars
    if unmeasured:
        return UNKNOWN, (f"{path} (session {session}): {unmeasured} of {matched} matching "
                         "record(s) carry no `chars` value")
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


def _parse_iso(ts):
    """An aware UTC datetime, or None -- never raises. A non-string `ts`, a
    string that does not parse, or a string that parses to a NAIVE datetime
    (no offset) all yield None: this module's timestamps are always UTC-
    offset ISO strings, and a naive result mixed into a sort or a subtraction
    against an aware one raises, so it is treated the same as unparseable
    rather than guessed at."""
    import datetime  # pylint: disable=import-outside-toplevel
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(datetime.timezone.utc)


def _sort_key(pair):
    """(unparseable, instant): groups events whose timestamp does not parse
    after every parseable one, stably, instead of comparing raw strings --
    two equal instants in different textual forms (a `Z` suffix vs an
    explicit `+00:00`, different sub-second precision) must sort as equal,
    not by the accident of which spelling sorts first lexicographically."""
    import datetime  # pylint: disable=import-outside-toplevel
    ts, _ = pair
    parsed = _parse_iso(ts)
    return (parsed is None, parsed or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))


def _transcript_events(transcript):
    """(events, had_unparseable_line). `events` is
    [(timestamp_str, record)] for every main-chain (non-sidechain) line that
    carries a "timestamp", sorted by parsed instant. `had_unparseable_line`
    is True when at least one non-blank line in the file could not be parsed
    as JSON at all -- a corrupt or truncated line, not merely one lacking a
    timestamp. Never raises: an unreadable or missing transcript yields
    ([], False)."""
    events = []
    had_unparseable = False
    try:
        with open(transcript, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except (OSError, TypeError):
        return events, False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            had_unparseable = True
            continue
        if not isinstance(rec, dict) or not rec.get("timestamp"):
            continue
        if rec.get("isSidechain") is True:
            continue
        events.append((rec["timestamp"], rec))
    events.sort(key=_sort_key)
    return events, had_unparseable


def active_time_seconds(transcript, idle_threshold=DEFAULT_IDLE_SECONDS):
    """Sum of gaps between consecutive main-chain transcript events, each
    capped at `idle_threshold` seconds. UNKNOWN with fewer than two usable
    timestamps -- there is no gap to measure, which is not the same as a
    measured 0 -- and UNKNOWN if any line in the transcript failed to parse:
    a fragment of a corrupt file is not a trustworthy measurement of it."""
    if idle_threshold <= 0:
        raise MetricsError(f"idle threshold must be a positive number of seconds, "
                           f"got {idle_threshold!r}")
    events, had_unparseable = _transcript_events(transcript)
    if had_unparseable:
        return UNKNOWN
    times = [t for t in (_parse_iso(ts) for ts, _ in events) if t is not None]
    if len(times) < 2:
        return UNKNOWN
    total = 0.0
    for prev, cur in zip(times, times[1:]):
        gap = (cur - prev).total_seconds()
        if gap > 0:
            total += min(gap, idle_threshold)
    return total


TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens")

# List prices, USD per million tokens, keyed by model-id PREFIX (longest
# prefix wins). Read from the `claude-api` skill's model table, itself cached
# 2026-10-06 from the vendor pricing page; the cache-write multipliers are the
# published 1.25x (5-minute TTL) and 2x (1-hour TTL) of the input rate. A
# cache-read rate the table states is used as stated (Fable 5.1 0.25, Fable 5
# 1.00, Opus 5.5 0.20, Sonnet 0.20); where it states none the standard 0.1x of
# input is ASSUMED (opus-5, opus-4.x, sonnet-4-6, haiku). Haiku 5.5's rate
# above 100K prompt tokens ($0.50 in / $2.50 out) is NOT applied, so its cost
# can only be low. A model with no entry makes cost UNKNOWN, never a partial sum.
PRICES_AS_OF = "2026-10-06"
PRICES_SOURCE = ("claude-api skill model table (cached 2026-10-06; "
                 "https://platform.claude.com/docs/en/about-claude/pricing); "
                 "cache write 1.25x (5m) / 2x (1h) of input; cache read as stated "
                 "there, else assumed 0.1x of input; Haiku 5.5 >100K-prompt tier not applied")


def _price(inp, out, cache_read=None):
    read = inp * 0.1 if cache_read is None else cache_read
    return {"input": inp, "output": out, "cacheRead": read,
            "cacheWrite5m": inp * 1.25, "cacheWrite1h": inp * 2.0}


PRICES = {
    "claude-fable-5-1": _price(10.0, 50.0, 0.25),
    "claude-mythos-5-1": _price(10.0, 50.0, 0.25),
    "claude-fable-5": _price(10.0, 50.0, 1.0),
    "claude-mythos-5": _price(10.0, 50.0, 1.0),
    "claude-opus-5-5": _price(4.0, 20.0, 0.20),
    "claude-opus-5": _price(5.0, 25.0),
    "claude-opus-4-8": _price(5.0, 25.0),
    "claude-opus-4-7": _price(5.0, 25.0),
    "claude-opus-4-6": _price(5.0, 25.0),
    "claude-sonnet-5-5": _price(2.0, 10.0, 0.20),
    "claude-sonnet-5": _price(2.0, 10.0, 0.20),
    "claude-sonnet-4-6": _price(3.0, 15.0),
    "claude-haiku-5-5": _price(0.10, 0.50),
    "claude-haiku-4-5": _price(1.0, 5.0),
}

NO_MODEL = "(no model)"
KIND_KEYS = ("input", "output", "cacheRead", "cacheWrite5m", "cacheWrite1h")


def _read_jsonl(path):
    """([(line_no, record)], had_unparseable_line): every line of `path` that
    is a JSON object, with its 1-based line number. Never raises: an
    unreadable or missing file yields ([], False)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except (OSError, TypeError):
        return [], False
    records, bad = [], False
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            bad = True
            continue
        if isinstance(rec, dict):
            records.append((number, rec))
    return records, bad


def _message_key(rec, scope, number):
    """Identity of one assistant message: `message.id`, else the record's
    `uuid`, else its own position (file and line) so id-less records never
    collapse into each other. The kinds are never merged with one another."""
    message = rec.get("message")
    message_id = message.get("id") if isinstance(message, dict) else None
    if isinstance(message_id, str) and message_id:
        return ("id", message_id)
    uuid = rec.get("uuid")
    if isinstance(uuid, str) and uuid:
        return ("uuid", uuid)
    return ("pos", scope, number)


def _bad_count(value):
    return isinstance(value, bool) or not isinstance(value, int) or value < 0


def _messages(records, scope, fields, strict, include_sidechain):
    """{key: (usage, model)}: one entry per assistant message, the LAST record
    in file order being its canonical usage (Claude Code writes a message once
    per content block and the usage repeats on every line). `strict` validates
    every record's counts before the dedup, duplicates included, so a
    malformed duplicate still raises ValueError."""
    messages = {}
    for number, rec in records:
        if rec.get("type") != "assistant" or not rec.get("timestamp"):
            continue
        if rec.get("isSidechain") is True and not include_sidechain:
            continue
        message = rec.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict) or not any(k in usage for k in fields):
            # A `usage` object carrying none of the fields this module
            # recognizes is not a measurement.
            continue
        if strict and any(k in usage and _bad_count(usage[k]) for k in fields):
            raise ValueError("a usage count is not a non-negative integer")
        model = message.get("model")
        messages[_message_key(rec, scope, number)] = (
            usage, model if isinstance(model, str) and model else NO_MODEL)
    return messages


def transcript_tokens(transcript, fields=TOKEN_FIELDS, strict=False):
    """Sum of the usage `fields` (all four by default; L-0541's goal cap
    passes input and output only) over the main-chain assistant messages,
    each message counted ONCE: Claude Code repeats a message's usage on every
    line it writes for it, so a per-line sum over-counts (about 1.8x on this
    project's transcripts). UNKNOWN when no assistant message carries a
    `usage` object with at least one of `fields`, or when any line in the
    transcript failed to parse. `strict` (the goal cap's): a present field
    that is not a non-negative integer raises ValueError, so a negative count
    can never lower the total."""
    records, had_unparseable = _read_jsonl(transcript)
    if had_unparseable:
        return UNKNOWN
    token_fields = tuple(fields)
    messages = _messages(records, transcript, token_fields, strict, False)
    if not messages:
        return UNKNOWN
    return sum(int(usage.get(k) or 0) for usage, _ in messages.values() for k in token_fields)


def _kinds(usage):
    """One message's tokens split by price kind. Cache creation uses the 5m/1h
    breakdown when it adds up to the total, else all of it counts as 5m."""
    def num(source, key):
        value = source.get(key) if isinstance(source, dict) else None
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0
    created = num(usage, "cache_creation_input_tokens")
    split = usage.get("cache_creation")
    c5, c1 = num(split, "ephemeral_5m_input_tokens"), num(split, "ephemeral_1h_input_tokens")
    if c5 + c1 != created:
        c1 = min(c1, created)
        c5 = created - c1
    return {"input": num(usage, "input_tokens"), "output": num(usage, "output_tokens"),
            "cacheRead": num(usage, "cache_read_input_tokens"),
            "cacheWrite5m": c5, "cacheWrite1h": c1}


def _fold_messages(messages):
    """({model: kinds}, tokens) for a {key: (usage, model)} map, where tokens is
    {input, output, cacheRead, cacheCreation, total}."""
    by_model = {}
    for usage, model in messages.values():
        kinds = _kinds(usage)
        into = by_model.setdefault(model, dict.fromkeys(KIND_KEYS, 0))
        for key in KIND_KEYS:
            into[key] += kinds[key]
    return by_model, tokens_from_models(by_model)


def tokens_from_models(by_model):
    total = dict.fromkeys(KIND_KEYS, 0)
    for kinds in by_model.values():
        for key in KIND_KEYS:
            total[key] += kinds[key]
    creation = total["cacheWrite5m"] + total["cacheWrite1h"]
    return {"input": total["input"], "output": total["output"], "cacheRead": total["cacheRead"],
            "cacheCreation": creation, "total": sum(total.values())}


def transcript_token_kinds(transcript):
    """{"tokens": {input, output, cacheRead, cacheCreation, total}, "byModel":
    {model: {input, output, cacheRead, cacheWrite5m, cacheWrite1h}}} over the
    main-chain assistant messages, each counted once; UNKNOWN as
    `transcript_tokens` is."""
    records, had_unparseable = _read_jsonl(transcript)
    if had_unparseable:
        return UNKNOWN
    messages = _messages(records, transcript, TOKEN_FIELDS, False, False)
    if not messages:
        return UNKNOWN
    by_model, tokens = _fold_messages(messages)
    return {"tokens": tokens, "byModel": by_model}


def price_for(model, prices=None):
    """The price row whose key is the longest prefix of `model`, else None."""
    table = PRICES if prices is None else prices
    best = None
    for key in table:
        if isinstance(model, str) and model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return table[best] if best else None


def cost_usd(by_model, prices=None):
    """(USD, unpriced_models). USD is the list-price cost to 6 places, or
    UNKNOWN when any model with tokens > 0 has no price (never a partial sum);
    a model whose counts are all 0 (`<synthetic>`) needs no price."""
    total, unpriced = 0.0, []
    for model, kinds in sorted(by_model.items()):
        if not any(kinds[k] for k in KIND_KEYS):
            continue
        row = price_for(model, prices)
        if row is None:
            unpriced.append(model)
            continue
        total += sum(kinds[k] * row[k] for k in KIND_KEYS) / 1_000_000
    if unpriced:
        return UNKNOWN, unpriced
    return round(total, 6), []


# --------------------------------------------------------------------------
# attribution: which Claude Code transcripts belong to a ticket

_ID = rf"({crew_common.TICKET_ID_CORE})(?![A-Za-z0-9_]|[.-][A-Za-z0-9])"
_STAMP_LINE = re.compile(rf"(?m)^[ \t]*Ticket ID:[ \t]*{_ID}[ \t]*$")
_CREW_COMMAND = re.compile(rf"(?<![A-Za-z0-9_/])/crew:[a-z][a-z-]*[ \t]+{_ID}")
_COMMAND_TAGS = re.compile(
    rf"<command-name>\s*/crew:[a-z][a-z-]*\s*</command-name>.{{0,400}}?<command-args>\s*{_ID}", re.S)
_BRANCH_ID = re.compile(rf"^({crew_common.TICKET_ID_CORE})-")


def claude_config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def project_slug(path):
    """Claude Code's project-directory name for a path: every character
    outside [A-Za-z0-9] becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def worktrees(root):
    """[{"path": realpath, "branch": name-or-None, "main": bool}] from
    `git worktree list --porcelain` run in `root`; the first entry is the main
    checkout. When git cannot answer, `root` alone, as the main checkout."""
    import subprocess  # pylint: disable=import-outside-toplevel
    found = []
    try:
        out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=root, check=True,
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for block in out.split("\n\n"):
        path, branch = None, None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = line[len("worktree "):]
            elif line.startswith("branch "):
                branch = line[len("branch "):]
                if branch.startswith("refs/heads/"):
                    branch = branch[len("refs/heads/"):]
        if path:
            found.append({"path": os.path.realpath(path), "branch": branch, "main": not found})
    if not found:
        found.append({"path": os.path.realpath(root), "branch": None, "main": True})
    return found


def project_dirs(root):
    """The existing Claude project directories whose slug matches the realpath
    of any worktree of this repository."""
    base = os.path.join(claude_config_dir(), "projects")
    dirs = []
    for tree in worktrees(root):
        candidate = os.path.join(base, project_slug(tree["path"]))
        if os.path.isdir(candidate) and candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _user_text(rec):
    """Text a person (or a dispatching parent) typed in a user record: a string
    body or its text blocks. Tool results, meta records and everything else are
    not evidence (they quote files, which can name any ticket)."""
    if rec.get("type") != "user" or rec.get("isMeta") is True:
        return ""
    message = rec.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block["text"] for block in content
                         if isinstance(block, dict) and block.get("type") == "text"
                         and isinstance(block.get("text"), str))
    return ""


def _stamps(records):
    found = set()
    for _, rec in records:
        text = _user_text(rec)
        if text:
            for pattern in (_STAMP_LINE, _CREW_COMMAND, _COMMAND_TAGS):
                found.update(m.group(1) for m in pattern.finditer(text))
    return found


def _worktree_id(records, trees, ticket):
    """The ticket id a file's records place it in: X when every record that has
    a `cwd` lies inside ONE linked worktree whose branch starts `X-`. The main
    checkout's branch is never evidence."""
    cwds = {os.path.realpath(rec["cwd"]) for _, rec in records
            if isinstance(rec.get("cwd"), str) and rec["cwd"]}
    if not cwds:
        return None
    for tree in trees:
        if tree["main"] or not tree["branch"]:
            continue
        if all(c == tree["path"] or c.startswith(tree["path"] + os.sep) for c in cwds):
            if tree["branch"].startswith(ticket + "-"):
                return ticket
            match = _BRANCH_ID.match(tree["branch"])
            return match.group(1) if match else None
    return None


def _session_files(project_dir):
    """[(path, parent_session_path_or_None)]: the main `<session>.jsonl` files
    and every `*.jsonl` anywhere under `<session>/subagents/` (the direct
    `agent-*.jsonl` files and `workflows/wf_<id>/agent-*.jsonl`)."""
    files = []
    try:
        names = sorted(os.listdir(project_dir))
    except OSError:
        return files
    for name in names:
        full = os.path.join(project_dir, name)
        if name.endswith(".jsonl") and os.path.isfile(full):
            files.append((full, None))
        elif os.path.isdir(os.path.join(full, "subagents")):
            parent = os.path.join(project_dir, name + ".jsonl")
            for here, _dirs, found in os.walk(os.path.join(full, "subagents")):
                for leaf in sorted(found):
                    if leaf.endswith(".jsonl"):
                        files.append((os.path.join(here, leaf), parent))
    return files


def attributed_usage(root, ticket):
    """Token usage of the Claude Code transcripts that an exclusive rule ties to
    `ticket`, as an attributed LOWER BOUND. One decision per transcript file;
    its evidence set is every id in a `Ticket ID: <id>` line or a
    `/crew:<command> <id>` in its user messages plus the id of the one linked
    worktree all its records sit in. One id: the file belongs to it. Two or more:
    the file is conflicting and belongs to nobody. None: a subagent file takes
    its parent session file's owner, a main file has none. Each message id counts
    once per scan; one seen in files with different owners counts for no ticket.
    Returns {"files", "mainSessions", "subagents", "conflicting",
    "conflictingMessages", "tokens", "byModel"}; tokens and byModel are None when
    no file belongs to `ticket`. Only usage, ids, models, `cwd` and the matched
    ids are kept: no prompt text is stored or echoed."""
    check_ticket(ticket)
    trees = worktrees(root)
    scanned = {}
    for project_dir in project_dirs(root):
        for path, parent in _session_files(project_dir):
            records, _bad = _read_jsonl(path)
            ids = _stamps(records)
            tree_id = _worktree_id(records, trees, ticket)
            if tree_id:
                ids.add(tree_id)
            scanned[path] = {"parent": parent, "records": records, "ids": ids}
    owner = {}
    for path, info in scanned.items():
        if info["parent"] is None:
            owner[path] = next(iter(info["ids"])) if len(info["ids"]) == 1 else None
    for path, info in scanned.items():
        if info["parent"] is not None:
            if len(info["ids"]) == 1:
                owner[path] = next(iter(info["ids"]))
            elif info["ids"]:
                owner[path] = None
            else:
                owner[path] = owner.get(info["parent"])
    seen = {}
    for path, info in scanned.items():
        for key, value in _messages(info["records"], path, TOKEN_FIELDS, False, True).items():
            entry = seen.setdefault(key, {"owners": set(), "best": value})
            entry["owners"].add(owner[path])
            if sum(_kinds(value[0]).values()) > sum(_kinds(entry["best"][0]).values()):
                entry["best"] = value
    mine = {key: entry["best"] for key, entry in seen.items() if entry["owners"] == {ticket}}
    clash = sum(1 for entry in seen.values() if ticket in entry["owners"] and len(entry["owners"]) > 1)
    owned = [p for p in scanned if owner[p] == ticket]
    out = {"files": len(owned),
           "mainSessions": sum(1 for p in owned if scanned[p]["parent"] is None),
           "subagents": sum(1 for p in owned if scanned[p]["parent"] is not None),
           "conflicting": sum(1 for info in scanned.values()
                              if len(info["ids"]) > 1 and ticket in info["ids"]),
           "conflictingMessages": clash, "tokens": None, "byModel": None}
    if owned and mine:
        out["byModel"], out["tokens"] = _fold_messages(mine)
    return out


# --------------------------------------------------------------------------
# record

def _measurement(root, ticket, transcript, scan):
    """(tokens, cost-fields, basis, attribution, source-tokens): the measurement
    group a row carries."""
    if transcript:
        kinds = transcript_token_kinds(transcript)
        attribution = {"files": 1, "mainSessions": 1, "subagents": 0, "conflicting": 0,
                       "conflictingMessages": 0}
        basis = "single transcript, main chain (--transcript)"
        source = transcript
    elif scan:
        used = attributed_usage(root, ticket)
        attribution = {k: used[k] for k in ("files", "mainSessions", "subagents", "conflicting",
                                            "conflictingMessages")}
        kinds = UNKNOWN if used["tokens"] is None else {
            "tokens": used["tokens"], "byModel": used["byModel"]}
        basis = "attributed lower bound"
        source = ("scan of the Claude Code transcripts of this repository's worktrees "
                  "(exclusive attribution)" if used["tokens"] is not None else
                  "scan found no transcript tied to this ticket")
    else:
        return UNKNOWN, UNKNOWN, "not measured (--no-scan)", UNKNOWN, "--no-scan"
    if kinds == UNKNOWN:
        return UNKNOWN, UNKNOWN, basis, attribution, source
    return kinds["tokens"], kinds["byModel"], basis, attribution, source


def record(root, ticket, transcript=None, session=None, idle_threshold=DEFAULT_IDLE_SECONDS,
           cost=None, schema=SCHEMA_1_1, scan=True):
    """Build and append one row for `ticket`. Returns the row."""
    check_ticket(ticket)
    if transcript and not scan:
        raise MetricsError("--transcript and --no-scan contradict each other")
    review_rounds, review_source = _review_rounds(root, ticket)
    scope_blocks, scope_source = _scope_blocks(root, ticket)
    injected, injected_source = _injected_chars(root, ticket, session)
    unapproved, unapproved_source = _unapproved_scope_changes(root, ticket)
    active = active_time_seconds(transcript, idle_threshold) if transcript else UNKNOWN
    transcript_note = transcript or "no --transcript given"
    tokens, by_model, basis, attribution, tokens_source = _measurement(
        root, ticket, transcript, scan)
    if cost is not None:
        cost_value, cost_source = cost, "--cost"
    elif tokens == UNKNOWN:
        cost_value, cost_source = UNKNOWN, "no tokens measured"
    else:
        cost_value, unpriced = cost_usd(by_model)
        cost_source = ("computed from PRICES (list price)" if not unpriced else
                       "UNKNOWN: no price for model(s) " + ", ".join(unpriced))
    row = {
        "schema": schema,
        "kind": "record",
        "ticket": ticket,
        "ticketId": ticket,
        "recordedAt": _now(),
        "phases": _phases(root, ticket),
        "activeTime": active,
        "tokens": tokens,
        "cost": cost_value,
        "tokensBasis": basis,
        "tokensAttribution": attribution,
        "pricesAsOf": PRICES_AS_OF,
        "pricesSource": PRICES_SOURCE,
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
            "activeTime": transcript_note, "tokens": tokens_source,
            "cost": cost_source,
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
    overwrites an earlier known value.

    The MEASUREMENT GROUP (`tokens`, `cost`, `tokensBasis`, `tokensAttribution`,
    `pricesAsOf`, `pricesSource` and `source.tokens` / `source.cost`) folds as
    one unit: a row that carries it (a schema 1.1 measurement attempt, marked by
    `tokensBasis`) replaces the whole group, UNKNOWN values included, so a later
    attempt that could not price its tokens cannot keep an earlier cost that
    belongs to other tokens. A row without the group (an `escaped` row, a 0.20
    or 1.0 row) leaves a group already folded alone."""
    by_ticket = {}
    for row in rows:
        ticket = _row_ticket(row)
        if not ticket:
            continue
        current = by_ticket.setdefault(ticket, {})
        grouped = "tokensBasis" in row
        if grouped:
            source = row.get("source") if isinstance(row.get("source"), dict) else {}
            for name in MEASUREMENT_GROUP:
                current.pop(name, None)
            for name in MEASUREMENT_GROUP:
                if name == "sourceTokens":
                    current[name] = source.get("tokens", UNKNOWN)
                elif name == "sourceCost":
                    current[name] = source.get("cost", UNKNOWN)
                elif name in row:
                    current[name] = row[name]
        for field in METRIC_FIELDS:
            if field not in row or (grouped and field in MEASUREMENT_GROUP):
                continue
            if field in ("tokens", "cost") and "tokensBasis" in current:
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
    metrics.jsonl, with n and UNKNOWN counts, plus the same known/unknown
    split for escapedDefects (used by `compare`'s escaped-defect criterion --
    it is a real measurement, not just "the baseline file exists"). Historical
    rows almost always have UNKNOWN activeTime/cost (`/crew:migrate` marks
    them so) -- a hand-reconstructed one can be added with `record --schema
    0.20 --transcript <old-transcript>`."""
    rows, _bad = read_rows(root)
    legacy = [r for r in rows if _is_legacy(r)]
    by_ticket = effective_ticket_metrics(legacy)
    active_med, active_n, active_unknown = _median([v.get("activeTime") for v in by_ticket.values()])
    cost_med, cost_n, cost_unknown = _median([v.get("cost") for v in by_ticket.values()])
    escaped_values = [v.get("escapedDefects") for v in by_ticket.values()]
    escaped_known = [v for v in escaped_values if isinstance(v, int) and not isinstance(v, bool)]
    return {
        "n": len(by_ticket),
        "medianActiveTime": active_med, "activeTimeKnown": active_n,
        "activeTimeUnknown": active_unknown,
        "medianCost": cost_med, "costKnown": cost_n, "costUnknown": cost_unknown,
        "escapedDefectsKnown": len(escaped_known),
        "escapedDefectsUnknown": len(escaped_values) - len(escaped_known),
        "escapedDefectsSum": sum(escaped_known),
    }


def _select_prospective(rows, since):
    prospective = [r for r in rows if r.get("schema") in (SCHEMA_1_0, SCHEMA_1_1)]
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
        # Select by the ticket's `record` row timestamp, never any row --
        # an `escaped` correction appended after the cutoff must not pull a
        # ticket that was actually recorded before it into the window.
        chosen = [t for t in order
                 if any(r.get("recordedAt", "") >= since for r in prospective
                        if _row_ticket(r) == t and r.get("kind") == "record")]
    return {t: by_ticket[t] for t in chosen if t in by_ticket}


def compare(root, since):
    """Prospective 1.0 tickets (selected by `since`, a count or an ISO date)
    against the 0.20 baseline. Prints medians, % change, review-budget
    enforcement, unapproved scope changes and escaped defects, with a
    PASS/FAIL/INSUFFICIENT DATA per success criterion.

    A corrupted metrics.jsonl (any row `read_rows` could not parse) or too
    few KNOWN values feeding a criterion (below MIN_COMPARE_TICKETS on the
    prospective side, or MIN_BASELINE_KNOWN on the baseline side, for the
    median-based criterion) can never let the OVERALL verdict read PASS --
    per this module's governing rule, a comparison may PASS only on
    sufficient KNOWN data. Combining the per-criterion results: any FAIL ->
    overall FAIL (a definite failure does not get erased by unrelated
    insufficiency elsewhere); else any INSUFFICIENT DATA -> overall
    INSUFFICIENT DATA; else PASS."""
    rows, bad = read_rows(root)
    base = baseline(root)
    prospective = _select_prospective(rows, since)
    result = {"n": len(prospective), "baseline": base, "tickets": sorted(prospective),
              "unparseableRows": bad}
    if not prospective:
        result["criteria"] = {name: "INSUFFICIENT DATA" for name in (
            "30pctLowerActiveTimeOrCost", "reviewBudgetEnforcement100pct",
            "zeroUnapprovedScopeChanges", "noRiseInEscapedDefects")}
        result["verdict"] = "INSUFFICIENT DATA"
        result["why"] = "no prospective 1.0 ticket(s) selected"
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

    # A median drawn from a single known value on either side (or on the
    # baseline side) is not a criterion this comparison may PASS on -- both
    # the prospective sample and the baseline sample need at least
    # MIN_COMPARE_TICKETS / MIN_BASELINE_KNOWN known values before their
    # median means anything.
    active_side_ok = active_n >= MIN_COMPARE_TICKETS and base["activeTimeKnown"] >= MIN_BASELINE_KNOWN
    cost_side_ok = cost_n >= MIN_COMPARE_TICKETS and base["costKnown"] >= MIN_BASELINE_KNOWN
    active_drop = active_side_ok and active_pct is not None and active_pct <= -30
    cost_drop = cost_side_ok and cost_pct is not None and cost_pct <= -30
    result["criteria"] = {}
    if active_drop or cost_drop:
        result["criteria"]["30pctLowerActiveTimeOrCost"] = "PASS"
    elif active_side_ok or cost_side_ok:
        result["criteria"]["30pctLowerActiveTimeOrCost"] = "FAIL"
    else:
        result["criteria"]["30pctLowerActiveTimeOrCost"] = "INSUFFICIENT DATA"

    # The ledger itself refuses a reservation past BUDGET unless an approved
    # successor plan reopened it (review_ledger.reserve), so "enforced" here
    # means "confirmable from the ledger", not "counted <= BUDGET" -- a
    # ticket with an approved successor legitimately carries more rounds.
    # A ticket missing the field entirely (`v.get(...)` -> None) is not
    # "known" just because None != UNKNOWN.
    known_rounds = [v for v in prospective.values()
                   if "reviewRounds" in v and v.get("reviewRounds") not in (UNKNOWN, None)]
    enforcement_rate = len(known_rounds) / len(prospective)
    result["reviewBudgetEnforcementRate"] = enforcement_rate
    result["criteria"]["reviewBudgetEnforcement100pct"] = (
        "PASS" if enforcement_rate == 1.0 else "FAIL")

    # Only a genuine int counts as a known value -- a missing field (None)
    # or a non-integer must land in "unknown", never silently vanish from
    # both the known count and the sum the way `isinstance(v, int)` filtering
    # the SUM alone (while `!= UNKNOWN` filtering the known-count) allowed.
    scope_values = [v.get("unapprovedScopeChanges") for v in prospective.values()]
    known_scope = [v for v in scope_values if isinstance(v, int) and not isinstance(v, bool)]
    total_unapproved = sum(known_scope)
    result["unapprovedScopeChanges"] = total_unapproved
    result["unapprovedScopeChangesUnknown"] = len(scope_values) - len(known_scope)
    result["criteria"]["zeroUnapprovedScopeChanges"] = (
        "FAIL" if total_unapproved > 0 else
        ("INSUFFICIENT DATA" if len(known_scope) < len(scope_values) else "PASS"))

    # PASS requires the baseline to actually have measured escaped defects
    # (not merely "the baseline file has rows") AND every prospective
    # ticket's value to be known -- an unknown prospective ticket could be
    # hiding a rise. A measured rise is a definite FAIL regardless of either.
    escaped_values = [v.get("escapedDefects") for v in prospective.values()]
    known_escaped = [v for v in escaped_values if isinstance(v, int) and not isinstance(v, bool)]
    total_escaped = sum(known_escaped)
    result["escapedDefects"] = total_escaped
    result["escapedDefectsUnknown"] = len(escaped_values) - len(known_escaped)
    baseline_escaped_known = base.get("escapedDefectsKnown", 0) >= MIN_BASELINE_KNOWN
    if total_escaped > 0:
        result["criteria"]["noRiseInEscapedDefects"] = "FAIL"
    elif baseline_escaped_known and len(known_escaped) == len(escaped_values):
        result["criteria"]["noRiseInEscapedDefects"] = "PASS"
    else:
        result["criteria"]["noRiseInEscapedDefects"] = "INSUFFICIENT DATA"

    criteria_values = result["criteria"].values()
    if any(v == "FAIL" for v in criteria_values):
        verdict = "FAIL"
    elif any(v == "INSUFFICIENT DATA" for v in criteria_values):
        verdict = "INSUFFICIENT DATA"
    else:
        verdict = "PASS"
    if bad and verdict == "PASS":
        # A corrupted dataset must never let the verdict read PASS, even
        # when every row that DID parse looks clean.
        verdict = "INSUFFICIENT DATA"
        result["why"] = f"{bad} unparseable row(s) in metrics.jsonl; cannot confirm a clean PASS"
    result["verdict"] = verdict
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
    rec.add_argument("--cost", type=float,
                     help="USD; overrides the cost computed from the price table")
    rec.add_argument("--no-scan", action="store_true",
                     help="do not read Claude Code transcripts: tokens and cost UNKNOWN "
                          "(not with --transcript)")
    rec.add_argument("--schema", default=SCHEMA_1_1,
                     help="1.1 (default) for a prospective ticket, or 0.20 to hand-"
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
    if args.cmd == "record" and args.transcript and args.no_scan:
        parser.error("--transcript counts that file and --no-scan reads none; pass one")
    root = os.path.abspath(args.root)
    try:
        if args.cmd == "record":
            row = record(root, args.ticket, transcript=args.transcript, session=args.session,
                        idle_threshold=args.idle_threshold_seconds, cost=args.cost,
                        schema=args.schema, scan=not args.no_scan)
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
