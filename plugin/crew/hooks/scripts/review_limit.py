"""Is this Codex failure a usage, rate or quota limit? (T-0088)

Owner, 2026-09-28: "if we hit a codex limit please use claude ads the
reviewer". `/crew:review` makes one minimal real Codex call before it reserves
a round (`review_run.py --probe`); when that call, or a round's own call,
fails on a limit, the round runs on the Claude reviewer, announced as
same-family and not independent.

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
`<git-common-dir>/crew/review/<ticket>.limit.json`, beside the ledger, so every
worktree of the repository sees it. It applies to the NEXT round only: while
its `round` equals the ledger's `rounds_used` (no round reserved since), the
next probe answers limited without a call. Once that round is reserved, it no
longer applies and Codex is probed live again. A missing, unreadable or
corrupt marker, or a ledger that cannot be read, is None: the live probe
decides, so the answer is still a real call and never a guess.
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
MARKER_SUFFIX = ".limit.json"


def limit_line(*texts):
    """The first line of `texts` naming a Codex usage/rate/quota limit, stripped
    and cut to 300 characters, verbatim otherwise; None when none does."""
    for text in texts:
        for line in (text or "").splitlines():
            if _LIMIT_RE.search(line):
                return line.strip()[:300]
    return None
