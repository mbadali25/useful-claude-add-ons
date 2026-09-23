"""UserPromptSubmit: record a plan approval when the USER types
`/crew:approve <ticket-id>`. crew 1.0, lane T3.

Why a prompt hook. `crew_ticket.py approve` is a command anyone with a shell
can run, the session included, so a receipt it writes cannot say the user
approved anything. A UserPromptSubmit payload is the one input the session
does not author: Claude Code sends it when the user submits a prompt. This
hook turns that prompt into the receipt, with `approved_via: "user-prompt"`,
the payload's `session_id` and `prompt_id`, and the sha256 of the spec.md and
plan.md bytes that `crew_ticket.approve` validated (one read, see there).

## The two prompt shapes

- RAW: the prompt is exactly `/crew:approve <id>` (surrounding whitespace
  allowed). VERIFIED against Claude Code 2.1.281 (`claude -p` with a probe
  plugin whose UserPromptSubmit hook dumped stdin): a plugin slash command
  reaches the hook unexpanded, `"prompt": "/probe:approve T-1"`.
- EXPANDED: the transcript form, `<command-name>/crew:approve</command-name>`
  with `<command-args><id></command-args>`, the prompt beginning with a
  `<command-` tag. NOT observed reaching a hook; accepted in case a harness
  version expands before UserPromptSubmit. Both tags must appear exactly once.

Anything else -- a prompt that mentions the command mid-sentence, quotes it,
or carries more than one id -- is not an approval.

## Outcomes

- Not an approve prompt: exit 0, no output. The common case, and cheap: the
  wrappers skip python entirely unless the text contains `crew:approve`.
- Approved: exit 0 with `additionalContext` naming the ticket and hashes, so
  the session learns the approval happened without being able to cause it.
- Refused (bad id, contract does not validate, not a git repository, a
  corrupt receipt): exit 2 with the reason on stderr. For UserPromptSubmit
  that blocks the prompt and shows the reason to the user, which is the point:
  the user asked for an approval and must see that none was recorded.

The session can still pipe a forged payload into this script through its
shell; `scope_guard.py` refuses a Bash/PowerShell command naming it, which
stops drift, not a deliberate forgery (README "Scope and approval").
"""
import json
import os
import re
import sys

import crew_ticket

COMMAND = "crew:approve"
_RAW_RE = re.compile(r"^\s*/crew:approve(?:\s+(.*?))?\s*$", re.DOTALL)
_NAME_RE = re.compile(r"<command-name>\s*/?crew:approve\s*</command-name>")
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)


def parse(prompt):
    """(is_approve_prompt, ticket_or_None). `ticket` is None when the prompt
    is an approve command whose argument is not exactly one token."""
    if not isinstance(prompt, str) or COMMAND not in prompt:
        return False, None
    raw = _RAW_RE.match(prompt)
    if raw:
        return True, _one_token(raw.group(1))
    if prompt.lstrip().startswith("<command-"):
        names, args = _NAME_RE.findall(prompt), _ARGS_RE.findall(prompt)
        if len(names) == 1 and len(args) == 1:
            return True, _one_token(args[0])
    return False, None


def _one_token(text):
    parts = (text or "").split()
    return parts[0] if len(parts) == 1 else None


def _payload():
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return None
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _refuse(text):
    sys.stderr.write(f"crew: /crew:approve was NOT recorded -- {text}\n")
    return 2


def handle(data):
    """Exit code for one UserPromptSubmit payload. Writes its own output."""
    if not isinstance(data, dict) or data.get("hook_event_name") != "UserPromptSubmit":
        return 0
    is_approve, ticket = parse(data.get("prompt"))
    if not is_approve:
        return 0
    if ticket is None:
        return _refuse("usage: /crew:approve <ticket-id> (exactly one id)")
    root = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = os.path.abspath(root or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    try:
        crew_ticket.check_ticket(ticket)
        receipt, successor = crew_ticket.approve(
            root, ticket, via=crew_ticket.USER_PROMPT, session=data.get("session_id"),
            prompt_id=data.get("prompt_id"))
    except crew_ticket.TicketError as exc:
        return _refuse(str(exc))
    text = (f"crew: the user approved {ticket} from their own prompt "
            f"(plan {receipt['plan_sha256'][:12]}, spec {receipt['spec_sha256'][:12]}, "
            f"approved_via user-prompt).")
    if successor is not None:
        allowed, reason = successor
        text += f" Review {'may continue' if allowed else 'is still NEEDS_REPLAN'}: {reason}."
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": text}}) + "\n")
    return 0


def main():
    try:
        return handle(_payload())
    except Exception as exc:  # pylint: disable=broad-except
        return _refuse(f"the approval hook failed ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    sys.exit(main())
