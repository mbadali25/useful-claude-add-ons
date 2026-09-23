"""Turn a reviewer's raw output into ONE verdict: CLEAN, FINDINGS or INCOMPLETE.

WHY A SCRIPT. The verdict used to be read off the output by whoever ran
`/crew:review`, in prose. That is how an empty output file, or a reviewer that
exited non-zero after authenticating, reads as "no findings": the absence of a
BLOCK line looks exactly like a clean diff. The rule is small enough to state
completely, so it lives here and the command calls it.

THE CONTRACT the shared prompt asks every reviewer for:

  READ|<part file name>                  one per bundle part, after reading it
  SEVERITY|file:line|what breaks|repro   SEVERITY is BLOCK, FIX or NIT
  CLEAN                                  exactly this, alone, when no defects

THE RULE, in precedence order:

  INCOMPLETE  timed out; no exit status; non-zero exit; empty output; any line
              that is none of the above -- a code fence included, and a
              finding with any of its four fields empty; a bundle part with
              no READ line; CLEAN beside findings; CLEAN more than once;
              neither CLEAN nor a finding.
  FINDINGS    at least one BLOCK/FIX/NIT line and nothing above applies.
  CLEAN       exactly one CLEAN line (plus the READ lines), exit 0.

INCOMPLETE is never CLEAN, and nothing that went wrong can become CLEAN: every
failure path is an explicit reason, and CLEAN is only reachable when the
reason list is empty.

The READ lines are the reviewer's own report, not an observation of its file
reads -- a reviewer can claim a part it skipped. What they do catch is the
common failure: a reviewer that read part 1 of 3 and answered.

`codex exec --json` prints a JSONL event stream instead of the message itself;
`codex_final_message` extracts the last agent message and whether the turn
completed, so a Codex turn that failed is INCOMPLETE even when its process
exited 0. A non-blank line of that stream that is not a JSON object is an
error too: the stream is only trustworthy whole, and skipping what cannot be
read would let a garbled stream with a final CLEAN still read as CLEAN.
"""
import json
import re

CLEAN = "CLEAN"
FINDINGS = "FINDINGS"
INCOMPLETE = "INCOMPLETE"
SEVERITIES = ("BLOCK", "FIX", "NIT")

# SEVERITY|file:line|what breaks|repro -- every field non-blank. The repro is
# last and may itself contain `|`.
_FIELD = r"[^|]*[^|\s][^|]*"
_FINDING = re.compile(rf"^(BLOCK|FIX|NIT)\|{_FIELD}\|{_FIELD}\|.*\S.*$")
_READ = re.compile(r"^READ\|(\S+)$")


def parse(text, exit_code, timed_out=False, expected_parts=()):
    """Return a dict: verdict, counts, findings, reasons, parts_read,
    parts_missing. `exit_code` None means the status is unknown."""
    counts = {sev: 0 for sev in SEVERITIES}
    findings, unparseable, read = [], [], []
    clean_lines = 0
    for raw in (text or "").splitlines():
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

    reasons = []
    if timed_out:
        reasons.append("the reviewer timed out")
    if exit_code is None:
        reasons.append("the reviewer's exit status is unknown")
    elif exit_code != 0:
        reasons.append(f"the reviewer exited {exit_code}")
    if not (text or "").strip():
        reasons.append("the reviewer's output is empty")
    if unparseable:
        reasons.append(f"{len(unparseable)} output line(s) match no part of the contract, "
                       f"first: {unparseable[0][:120]!r}")
    missing = [name for name in expected_parts if name not in read]
    if missing:
        reasons.append(f"no READ line for {len(missing)} of {len(expected_parts)} bundle "
                       f"part(s): {', '.join(missing)}")
    if clean_lines and findings:
        reasons.append("the output says CLEAN and also lists findings")
    if clean_lines > 1:
        reasons.append("the output says CLEAN more than once")
    if not clean_lines and not findings and not reasons:
        reasons.append("the output has neither CLEAN nor a finding")

    if reasons:
        verdict = INCOMPLETE
    elif findings:
        verdict = FINDINGS
    else:
        verdict = CLEAN
    return {
        "verdict": verdict,
        "counts": counts,
        "findings": findings,
        "reasons": reasons,
        "parts_read": read,
        "parts_missing": missing,
    }


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
    for line in (jsonl or "").splitlines():
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
