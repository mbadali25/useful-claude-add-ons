"""Turn a reviewer's raw output into ONE verdict: CLEAN, FINDINGS or INCOMPLETE.

WHY A SCRIPT. The verdict used to be read off the output by whoever ran
`/crew:review`, in prose. That is how an empty output file, or a reviewer that
exited non-zero after authenticating, reads as "no findings": the absence of a
BLOCK line looks exactly like a clean diff. The rule is small enough to state
completely, so it lives here and the command calls it.

THE CONTRACT the shared prompt asks every reviewer for:

  READ|<the path exactly as listed, or its bare file name>
                                         one per bundle part, after reading it
  SEVERITY|file:line|what breaks|repro   SEVERITY is BLOCK, FIX or NIT
  CLEAN                                  exactly this, alone, when no defects

THE RULE, in precedence order:

  INCOMPLETE  timed out; no exit status; non-zero exit; empty output; a reason
              found outside the text (`prior_reasons`: a Codex stream error, a
              bundle or webtest check); a bundle part with no READ line; CLEAN
              beside findings; CLEAN more than once; any line that is none of
              the above (a "stray" line) unless it is recovered, below;
              neither CLEAN nor a finding.
  FINDINGS    at least one BLOCK/FIX/NIT line and nothing above applies.
  CLEAN       exactly one CLEAN line (plus the READ lines), exit 0, and no
              other line at all.

RECOVERY (L-0576). Stray lines are ignored -- listed in `ignored`, not made a
reason -- only when every one of these holds: at least one finding parsed;
no other reason applies (so no CLEAN line, every part READ, exit 0, no
timeout, no prior reason); and no stray line is `contract_like`. A
contract-like line is one that might be a contract line the parser failed to
read -- after markdown decoration is stripped it starts with BLOCK, FIX, NIT,
READ or CLEAN in any case (`- FIX|...`, `fix|...`, `Clean.`, a finding with an
empty field), or it holds three or more `|` -- or one that admits the review
fell short (`_SHORTFALL`: "incomplete", "skipped", "truncated", "could not
review", "ran out", ...). Those are "could not tell", and the round stays
INCOMPLETE. What is left is prose, a heading or a code fence beside findings
that parsed: the findings count, and the ignored lines are kept for a person
to read. The `_SHORTFALL` net is wording, so it cannot be complete; that is
why recovery never reaches CLEAN and the ignored lines are always reported.

INCOMPLETE is never CLEAN, and nothing that went wrong can become CLEAN: every
failure path is an explicit reason, and CLEAN is only reachable when the
reason list is empty and there was a CLEAN line and no finding -- a recovered
round always has a finding, so it is never CLEAN.

An INCOMPLETE is classed by `failure_class`, in precedence order: `tree` when
the bundle or webtest check found the tree moved; `tool` when the answer never
arrived intact (timed out, no exit status, non-zero exit, empty output, a
failed or unreadable Codex stream) -- its contract reasons are then
consequences, not the reviewer's; otherwise `reviewer`. Only `tool` is
refunded by the ledger (T-0087).

A READ line counts for a part when its path, with `\\` read as `/` and
normalised, IS that part's path as listed in the prompt, or when it has no
directory and is that part's file name (`_covers`). A READ line naming
anything else -- a path outside the bundle, the same file name in another
directory -- counts for no part, and is not a reason of its own: the part it
failed to cover is the missing part. `READ_FORM` is that rule as the prompt
states it, quoted by `review_prompt.py` so the two cannot drift apart (T-0079:
the prompt listed full paths and asked for bare names while this compared
bare names only, and honest rounds read as INCOMPLETE).

The READ lines are the reviewer's own report, not an observation of its file
reads -- a reviewer can claim a part it skipped. What they do catch is the
common failure: a reviewer that read part 1 of 3 and answered.

`codex exec --json` prints a JSONL event stream instead of the message itself;
`codex_final_message` extracts the last agent message and whether the turn
completed, so a Codex turn that failed is INCOMPLETE even when its process
exited 0. A non-blank line of that stream that is not a JSON object is an
error too: the stream is only trustworthy whole, and skipping what cannot be
read would let a garbled stream with a final CLEAN still read as CLEAN.

Reviewer output and the event stream are split on "\\n" only, never
`str.splitlines()`: its extra breaks (U+2028, U+2029, U+0085 and the C0
separators) cut a Codex event mid-JSON, which scored T-0072 round 4
INCOMPLETE. A "\\r\\n" end is stripped with the rest of the line's whitespace.
"""
import json
import posixpath
import re

CLEAN = "CLEAN"
FINDINGS = "FINDINGS"
INCOMPLETE = "INCOMPLETE"
SEVERITIES = ("BLOCK", "FIX", "NIT")
# The only verdicts there are: the ledger, review.json and autopilot use these.
VERDICTS = (CLEAN, FINDINGS, INCOMPLETE)
# The finding line as every prose statement of it must read (agents/reviewer.md,
# commands/review.md, the eval prompt); `_FINDING` below is its parser.
FINDING_FORM = "SEVERITY|file:line|what breaks|how to reproduce"
# Whose fault an INCOMPLETE was (`failure_class`); only TOOL is refunded.
TOOL, REVIEWER, TREE = "tool", "reviewer", "tree"
# `codex exec --json` vocabulary, from codex-rs/exec/src/exec_events.rs
# (plugin/crew/docs/external-tool-formats.md carries the citations).
CODEX_EVENT_TYPES = ("thread.started", "turn.started", "turn.completed", "turn.failed",
                     "item.started", "item.updated", "item.completed", "error")
CODEX_ITEM_TYPES = ("agent_message", "reasoning", "command_execution", "file_change",
                    "mcp_tool_call", "collab_tool_call", "web_search", "todo_list", "error")

# SEVERITY|file:line|what breaks|repro -- every field non-blank. The repro is
# last and may itself contain `|`.
_FIELD = r"[^|]*[^|\s][^|]*"
_FINDING = re.compile(rf"^(BLOCK|FIX|NIT)\|{_FIELD}\|{_FIELD}\|.*\S.*$")
# The READ form the prompt states, and the one rule `_covers` applies.
READ_FORM = "READ|<the path exactly as listed, or its bare file name>"
# The token is the rest of the line: a listed path may contain a space.
_READ = re.compile(r"^READ\|(.*\S.*)$")
# A stray line that may be a contract line the parser failed to read, or an
# admission that the review fell short (L-0576): one that starts with a
# contract keyword in any case once markdown decoration is stripped; a row of
# three or more `|`; or one matching a `_SHORTFALL` pattern anywhere. Such a
# line is "could not tell" and keeps the round INCOMPLETE; only a stray line
# that is none of these is harmless enough to ignore beside findings.
_DECORATION = re.compile(r"^(?:[\s`*_>#+-]|\d+[.)])+")
_KEYWORD = r"BLOCK|FIX|NIT|READ|CLEAN"
_ON_BARE = (re.compile(rf"^(?:{_KEYWORD})\b", re.IGNORECASE),)
# An admission that the review itself fell short reads as could-not-tell too,
# not as prose to ignore -- the wording here is a net, so it errs wide.
_SHORTFALL = (r"\bincomplete\b",
              r"\b(?:skip|skipped|skipping|skimm?ed|truncated|partial|partially|unread)\b",
              r"\b(?:ran|run|running) out\b|\btimed? ?out\b",
              r"\b(?:did not|didn't|could not|couldn't|cannot|can't|unable to|was not able to"
              r"|not able to|not fully|never)\b.{0,40}\b(?:read|review|reviewed|open|opened"
              r"|load|loaded|see|saw|access|finish|finished|check|checked|cover|covered)\b")
_ON_LINE = (re.compile(r"\|.*\|.*\|"),) + tuple(
    re.compile(p, re.IGNORECASE) for p in _SHORTFALL)


def contract_like(line):
    """True when `line` might be a contract line the parser could not read."""
    bare = _DECORATION.sub("", line)
    return (any(p.search(bare) for p in _ON_BARE)
            or any(p.search(line) for p in _ON_LINE))


def _norm(path):
    return posixpath.normpath(path.strip().replace("\\", "/"))


def _covers(token, listed):
    """A READ token counts for a listed part when it IS that part's listed
    path, or when it has no directory and is that part's file name."""
    token, listed = _norm(token), _norm(listed)
    if token == listed:
        return True
    return "/" not in token and token == posixpath.basename(listed)


def parse(text, exit_code, timed_out=False, expected_parts=(), prior_reasons=()):
    """Return a dict: verdict, counts, findings, reasons, ignored, parts_read,
    parts_missing, delivered. `ignored` lists the harmless stray lines a
    FINDINGS round was recovered despite; it is empty otherwise.
    `prior_reasons` are INCOMPLETE reasons found outside the text (a Codex
    stream error, a bundle or webtest check); they lead `reasons` and, like
    every other reason, rule recovery out. `exit_code` None means the status is unknown;
    `delivered` is whether an answer arrived intact at all (see
    `failure_class`)."""
    counts = {sev: 0 for sev in SEVERITIES}
    findings, unparseable, read = [], [], []
    clean_lines = 0
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line == CLEAN:
            clean_lines += 1
            continue
        match = _READ.match(line)
        if match:
            read.append(match.group(1))
            continue
        match = _FINDING.match(line)
        if match:
            counts[match.group(1)] += 1
            findings.append(line)
            continue
        unparseable.append(line)

    reasons = list(prior_reasons)
    if timed_out:
        reasons.append("the reviewer timed out")
    if exit_code is None:
        reasons.append("the reviewer's exit status is unknown")
    elif exit_code != 0:
        reasons.append(f"the reviewer exited {exit_code}")
    if not (text or "").strip():
        reasons.append("the reviewer's output is empty")
    missing = [part for part in expected_parts if not any(_covers(t, part) for t in read)]
    if missing:
        reasons.append(f"no READ line for {len(missing)} of {len(expected_parts)} bundle "
                       f"part(s): {', '.join(missing)}")
    if clean_lines and findings:
        reasons.append("the output says CLEAN and also lists findings")
    if clean_lines > 1:
        reasons.append("the output says CLEAN more than once")
    # Recovery (L-0576): stray lines are ignored only beside findings, with no
    # other reason (CLEAN beside findings is one), and none contract-like.
    # CLEAN is exact: with no finding there is nothing to recover.
    ignored = []
    if unparseable:
        if (findings and not reasons
                and not any(contract_like(line) for line in unparseable)):
            ignored = unparseable
        else:
            reasons.append(f"{len(unparseable)} output line(s) match no part of the contract, "
                           f"first: {unparseable[0][:120]!r}")
    if not clean_lines and not findings and not reasons:
        reasons.append("the output has neither CLEAN nor a finding")

    if reasons:
        verdict = INCOMPLETE
    elif findings:
        verdict = FINDINGS
    else:
        verdict = CLEAN
    delivered = not timed_out and exit_code == 0 and bool((text or "").strip())
    return {
        "verdict": verdict,
        "counts": counts,
        "findings": findings,
        "reasons": reasons,
        "ignored": ignored,
        "parts_read": read,
        "parts_missing": missing,
        "delivered": delivered,
    }


def failure_class(verdict, delivered, tree):
    """None unless INCOMPLETE; then tree > tool (answer not delivered) > reviewer."""
    if verdict != INCOMPLETE:
        return None
    if tree:
        return TREE
    return REVIEWER if delivered else TOOL


def _event_type(event):
    """(kind, payload) for both Codex JSONL shapes: the current
    `{"type": ..., "item": {...}}` and the older `{"msg": {"type": ...}}`."""
    if isinstance(event.get("msg"), dict):
        return event["msg"].get("type"), event["msg"]
    return event.get("type"), event


def codex_final_message(jsonl):
    """From `codex exec --json` stdout, return (message, error). `message` is
    the last agent message, or None. `error` is None only when a turn
    completed and no failure event was seen."""
    message, completed, error = None, False, None
    for line in (jsonl or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if not isinstance(event, dict):
            if error is None:
                error = f"unparseable Codex event line: {line[:120]!r}"
            continue
        kind, body = _event_type(event)
        if kind == "item.completed" and isinstance(body.get("item"), dict):
            item = body["item"]
            if item.get("type") in ("agent_message", "assistant_message"):
                message = item.get("text", message)
        elif kind == "agent_message":
            message = body.get("message", message)
        elif kind == "task_complete":
            completed = True
            message = body.get("last_agent_message") or message
        elif kind == "turn.completed":
            completed = True
        elif kind in ("turn.failed", "error", "stream_error"):
            detail = body.get("error") if isinstance(body.get("error"), dict) else body
            error = str(detail.get("message") or kind)
    if error is None and not completed:
        error = "the Codex event stream has no completed turn"
    return message, error
