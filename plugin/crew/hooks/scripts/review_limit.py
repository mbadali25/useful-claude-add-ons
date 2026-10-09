"""Is this Codex failure a usage, rate or quota limit? (T-0088)

Owner, 2026-09-28: "if we hit a codex limit please use claude ads the
reviewer". `/crew:review` makes one minimal real Codex call before it reserves
a round (`review_run.py --probe`); when that call, or a round's own call,
fails on a limit, the round walks to the next cross-family provider, else no
reviewer is recorded (INCOMPLETE, refunded); since L-0712 a Claude read runs
only on the operator's explicit `--same-family`, labelled and not independent.

THE PATTERNS are Codex's own messages, read from `openai/codex` at
`44fe510ce3ee61c8ef623adcbf89b901c73ddd61`, `codex-rs/protocol/src/error.rs`,
and each one was confirmed present in the installed `codex-cli 0.155.1`
binary:
  "hit your usage limit"            :701, :780, :784  UsageLimitReached
  "is out of credits"               :711, :717        UsageLimitReached (workspace)
  "hit your spend cap"              :723              UsageLimitReached (spend cap)
  "rate limit exceeded"             :98               RateLimitExceeded
  "quota exceeded"                  :157              QuotaExceeded
  "to use codex with your chatgpt plan"  :159-162     UsageNotIncluded
  "exceeded retry limit, last status: 429"  :661-673  RetryLimit on HTTP 429
Deliberately NOT limits (a different model or a retry may work, and none of
them is what the owner asked about): `:140` "Selected model is at capacity",
`:163` "We're currently experiencing high demand", `:142` "Flex capacity
unavailable". A retry limit on any status but 429 is not a limit either.

Only a FAILED call is ever judged here (exit != 0, no delivered message, or
timed out): `codex exec --json` also emits `error` events for a 429 it is
about to retry, and a run that then completes is not limited
(`codex-rs/exec/src/lib.rs:1262-1277`).

THE MARKER. A round whose call failed on a limit is recorded in
`<git-common-dir>/crew/review-limit/<ticket>.json`, under the common directory
like the ledger, so every worktree of the repository sees it. It is NOT in the
ledger's own folder: `/crew:status` lists every `*.json` there as a ledger, and
a `<ticket>.limit.json` beside them was both a phantom ticket in that listing
and, since a ticket id may contain dots, ticket `<ticket>.limit`'s ledger
path. It applies to the NEXT round only: while
its `round` equals the ledger's `rounds_used` (no round reserved since), the
next probe answers limited without a call. Once that round is reserved, or a
no-reviewer outcome (`review_ledger.py --no-reviewer`) is recorded at or after
it (L-0712), it no longer applies and Codex is probed live again. A missing, unreadable or
corrupt marker (not a dict, `round` not an int, `error` not a non-empty
string), or a ledger that cannot be read, is None: the live probe decides, so
the answer is still a real call and never a guess.

Recording is best-effort by design: `review_run.run` records only after the
round's verdict is on the ledger, and a marker that cannot be written costs the
next round a live probe, never the round's own INCOMPLETE record.
"""
import datetime
import json
import os
import re

import review_ledger

LIMIT_PATTERNS = (
    r"hit your usage limit",                    # error.rs:701, :780, :784 (UsageLimitReached)
    r"is out of credits",                       # error.rs:711, :717
    r"hit your spend cap",                      # error.rs:723
    r"rate limit exceeded",                     # error.rs:98 (RateLimitExceeded)
    r"quota exceeded",                          # error.rs:157 (QuotaExceeded)
    r"to use codex with your chatgpt plan",     # error.rs:159-162 (UsageNotIncluded)
    r"exceeded retry limit, last status: 429",  # error.rs:661-673 (RetryLimit, 429)
)
_LIMIT_RE = re.compile("|".join(LIMIT_PATTERNS), re.IGNORECASE)
MARKER_DIR = "review-limit"


def limit_line(*texts):
    """The first line of `texts` naming a Codex usage/rate/quota limit, stripped
    and cut to 300 characters, verbatim otherwise; None when none does."""
    for text in texts:
        for line in (text or "").splitlines():
            if _LIMIT_RE.search(line):
                return line.strip()[:300]
    return None


def marker_path(root, ticket):
    """`<git-common-dir>/crew/review-limit/<ticket>.json`: not the ledger's folder."""
    return os.path.join(review_ledger.common_dir(root), "crew", MARKER_DIR,
                        review_ledger.check_ticket(ticket) + ".json")


def record(root, ticket, number, provider, model, line):
    """Record that round `number`'s call failed on a limit. Atomic: the text is
    computed before any file is opened, then written to a temp file in the same
    directory and moved into place, so a failure leaves no half-written marker;
    the temp file is removed when the write or the move fails, and the OSError
    is the caller's to report."""
    path = marker_path(root, ticket)
    text = json.dumps({
        "ticket": ticket, "round": number, "provider": provider, "model": model or None,
        "error": line,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path


def recorded(root, ticket):
    """The marker dict when it applies to the NEXT round (its round equals the
    ledger's rounds_used), else None; a missing, unreadable or corrupt marker, or
    an UNKNOWN ledger, is None and the live probe decides."""
    try:
        with open(marker_path(root, ticket), encoding="utf-8") as handle:
            mark = json.load(handle)
        if not isinstance(mark, dict):
            return None
        ledger = review_ledger.status(root, ticket)
        used = ledger.get("rounds_used")
    except (OSError, ValueError, review_ledger.LedgerError):
        return None
    number, error = mark.get("round"), mark.get("error")
    # bool is an int, and True == 1: a `"round": true` must not pass for round 1.
    if not isinstance(number, int) or isinstance(number, bool) \
            or not isinstance(error, str) or not error.strip():
        return None
    if mark.get("round") != used:
        return None
    if consumed_by_no_reviewer(mark, ledger.get("unreviewed")):
        return None
    return mark


def consumed_by_no_reviewer(mark, unreviewed):
    """L-0712 round 6: a no-reviewer outcome recorded at or after the marker
    decided the round the marker was for, without reserving one, so
    rounds_used never moves past it. It is spent: the next probe calls Codex
    live, as it does once a round is reserved. Both stamps are
    `review_ledger._now()`'s UTC ISO seconds, so they compare as strings; a
    stamp that is not that shape, or an `unreviewed` that is not a list of
    objects, is could-not-tell and also spends it - the live probe then
    decides, which is a real call and never a guess."""
    at = mark.get("at")
    if unreviewed in (None, []):
        return False
    if not isinstance(unreviewed, list) or not isinstance(at, str) or len(at) != 25:
        return True
    for entry in unreviewed:
        when = entry.get("at") if isinstance(entry, dict) else None
        if not isinstance(when, str) or len(when) != 25 or when >= at:
            return True
    return False
