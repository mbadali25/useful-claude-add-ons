"""UserPromptSubmit: record a plan approval when the USER types
`/crew:approve <ticket-id>` -- or several, confirmed. crew 1.0, lane T3;
groups T-0024.

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

## Groups (T-0024)

One prompt may name several tickets: `/crew:approve T-4 T-5` (spaces or
commas), a range `/crew:approve T-0010..T-0012` (same prefix, start <= end,
padded like the start), or the one plain-text form, the WHOLE prompt on one
line: `[please] approve <id>[, <id>| and <id>...]` or
`approve <id> through|thru|to <id>`, where an id is prefix-dash-number.
At most MAX_GROUP tickets. A range token that is also a ticket folder is
refused as ambiguous (`crew_ticket._TICKET_RE` allows `.`).

Any request for more than one ticket, and ANY plain-text request, records
nothing on its first prompt. Every ticket is checked (`crew_ticket.precheck`)
and, if all pass, a pending list binding each ticket to its spec and plan
sha256 is written to `<git-common-dir>/crew/approval-pending/<worktree key>.json`
and the prompt is blocked with that list. The user's own next
`/crew:approve --confirm` -- one line, nothing else on it, the same
`session_id`, within PENDING_TTL seconds -- re-checks every ticket and hash
and records one receipt per ticket through `crew_ticket.approve(expect=...)`.
Not "yes": the commonest reply to any question would confirm a list.

Refuse all, never the rest: when any ticket fails, at the request or at the
confirm, nothing is recorded, nothing is left pending, and every failing id
is named. Any approval-shaped prompt clears the pending list first, and a
confirm consumes it whatever the outcome. A write failing part-way through
the confirm (no cross-file transaction exists) exits 2 naming which tickets
were recorded and which were not.

Anything else -- a prompt that mentions the command mid-sentence, quotes it,
or uses the word "approve" in a sentence -- is not an approval. A multi-line
prompt that STARTS with one is refused: an approval is one line.

## Outcomes

- A payload that is not one JSON object but contains `crew:approve`: exit 2,
  the same as a refusal -- an approval was asked for and could not be read.
- Not an approve prompt: exit 0, no output. The common case, and cheap: the
  wrappers skip python entirely unless the text contains the word `approve`.
- Approved (a single id, or a confirmed group): exit 0 with
  `additionalContext` naming each ticket and its hashes, so the session
  learns the approval happened without being able to cause it.
- Pending (a group request): exit 2 with the list on stderr, nothing recorded.
- Refused (bad id, contract does not validate, not a git repository, a
  corrupt receipt, a stale or foreign pending list): exit 2 with the reason
  on stderr. For UserPromptSubmit that blocks the prompt and shows the reason
  to the user, which is the point: the user asked for an approval and must
  see that none was recorded.

The session can still pipe a forged payload into this script through its
shell; `scope_guard.py` refuses a Bash/PowerShell command naming it, which
stops drift, not a deliberate forgery (README "Scope and approval").
"""
import collections
import hashlib
import json
import os
import re
import sys
import time
import uuid

import crew_ticket

COMMAND = "crew:approve"
CONFIRM_TOKEN = "--confirm"
MAX_GROUP = 20
PENDING_TTL = 600
NONE, SINGLE, GROUP, CONFIRM, REFUSE = "none", "single", "group", "confirm", "refuse"
_RAW_RE = re.compile(r"^\s*/crew:approve(?:\s+(.*?))?\s*$", re.DOTALL)
_NAME_RE = re.compile(r"\s*/?crew:approve\s*")
# The expanded form's tags, read at the prompt's TOP level only: a tag's
# content runs to the first matching close, so a `<command-name>` inside a
# `<command-message>` is content, never a command (review round 2).
_TOP_TAG_RE = re.compile(r"<command-(message|name|args)>(.*?)</command-\1>", re.DOTALL)
_ANY_TAG_RE = re.compile(r"</?command-(?:message|name|args)>")
# Commas separate ids only BETWEEN two of them: `T-1,T-2`, `T-1, T-2`.
_COMMA_LIST_RE = re.compile(r"[^\s,]+(?:\s*,\s*[^\s,]+|\s+[^\s,]+)*")
# Every break `str.splitlines` honours. An approval is one line: a newline in
# it is a paste, and a paste can carry ids the user did not type.
_BREAK_RE = re.compile("[\n\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
_RANGE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*-)(\d+)\.\.([A-Za-z][A-Za-z0-9]*-)(\d+)$")
# The plain-text form. A ticket here is prefix-dash-number, never a bare word,
# so "approve it" and "approve this" name nothing.
_PT_ID = r"[A-Za-z][A-Za-z0-9]*-\d+"
_PT_RANGE = _PT_ID + r"\.\." + _PT_ID
_PT_SEP = r"(?:\s*,\s*and\s+|\s*,\s*|\s+and\s+)"
_PLAIN_RE = re.compile(
    r"^\s*(?:please\s+)?approve\s+(?P<ids>"
    rf"(?P<a>{_PT_ID})\s+(?:through|thru|to)\s+(?P<b>{_PT_ID})"
    rf"|{_PT_RANGE}"
    rf"|{_PT_ID}(?:{_PT_SEP}{_PT_ID})*"
    r")\s*[.!]?\s*$", re.IGNORECASE)
_PT_SPLIT_RE = re.compile(_PT_SEP, re.IGNORECASE)
_USAGE = ("usage: /crew:approve <ticket-id> [<id> ...|<A-n>..<A-m>], then "
          "/crew:approve --confirm for more than one")

Request = collections.namedtuple("Request", "kind ids form error")


def _request(kind, ids=(), form=None, error=None):
    return Request(kind, tuple(ids), form, error)


def _refusal(form, error):
    return _request(REFUSE, form=form, error=error)


def parse(prompt, root=None):
    """The approval this prompt asks for, as a `Request(kind, ids, form, error)`.

    `kind` is NONE (not an approval: the prompt passes untouched), SINGLE
    (`/crew:approve <one id>`, recorded at once, as before), GROUP (several
    ids, a range, or any plain-text form: goes pending), CONFIRM
    (`/crew:approve --confirm`) or REFUSE (asked for and malformed; `error`
    says why). `root`, when given, is used only to refuse a range token that
    is also a ticket folder."""
    if not isinstance(prompt, str):
        return _request(NONE)
    if COMMAND in prompt:
        raw = _RAW_RE.match(prompt)
        if raw:
            if _BREAK_RE.search(prompt.strip()):
                return _refusal("slash", "an approval must be one line")
            return _one_line_only(_slash(raw.group(1), "slash", root), prompt)
        if prompt.lstrip().startswith("<command-"):
            tags, outside = _top_level(prompt)
            if any(_ANY_TAG_RE.search(content) for _, content in tags) \
                    or _ANY_TAG_RE.search(outside):
                return _refusal("expanded", "a command tag is nested inside another (or left "
                                            "unclosed): an approval must be the prompt's own "
                                            "command, never an example or a quoted message")
            names = [content for tag, content in tags if tag == "name"]
            args = [content for tag, content in tags if tag == "args"]
            if len(names) == 1 and _NAME_RE.fullmatch(names[0]) and len(args) == 1:
                # No separate break check here: a break inside the args splits
                # them into two tokens, so it can only reach _one_line_only as
                # a group, a range or a refused --confirm -- never a single id.
                request = _one_line_only(_slash(args[0], "expanded", root), args[0])
                if request.kind in (GROUP, CONFIRM) and outside.strip():
                    return _refusal("expanded", "an approval must carry no other text: "
                                                "type the command alone")
                return request
    return _plain(prompt, root)


def _top_level(prompt):
    """`(tags, outside)`: the prompt's outermost `<command-*>` tags as
    `(tag, content)` pairs in order, and the text outside all of them."""
    tags, outside, pos = [], [], 0
    for found in _TOP_TAG_RE.finditer(prompt):
        outside.append(prompt[pos:found.start()])
        tags.append((found.group(1), found.group(2)))
        pos = found.end()
    outside.append(prompt[pos:])
    return tags, "".join(outside)


def _one_line_only(request, text):
    """`request`, unless it is a group or a confirm and `text` has a line break
    anywhere but at its end. A trailing break carries nothing and a submitted
    prompt may end in one; a break BEFORE the command is a paste. The single-id
    path keeps its older, looser rule (spec Exclusions)."""
    if request.kind in (GROUP, CONFIRM) and _BREAK_RE.search(text.rstrip()):
        return _refusal(request.form, "an approval must be one line")
    return request


def _slash(text, form, root):
    tokens = [t for t in re.split(r"[\s,]+", text or "") if t]
    if not tokens:
        return _refusal(form, _USAGE)
    if "," in text and not _COMMA_LIST_RE.fullmatch(text.strip()):
        return _refusal(form, "a comma goes only between two ids (/crew:approve T-1,T-2); "
                              "nothing before the first or after the last")
    if CONFIRM_TOKEN in tokens:
        if tokens != [CONFIRM_TOKEN]:
            return _refusal(form, "--confirm takes nothing else on the line: type "
                                  "exactly /crew:approve --confirm")
        return _request(CONFIRM, form=form)
    if len(tokens) == 1 and not _RANGE_RE.match(tokens[0]):
        return _request(SINGLE, tokens, form)
    return _group_request(tokens, form, root)


def _plain(prompt, root):
    # rstrip, not strip: blank lines BEFORE the approval are part of a paste.
    lines = prompt.rstrip().splitlines()
    first = next((line for line in lines if line.strip()), None)
    found = _PLAIN_RE.match(first) if first is not None else None
    if not found:
        return _request(NONE)
    if len(lines) > 1:
        return _refusal("plain-text", "an approval must be one line")
    if found.group("a"):
        tokens = [f"{found.group('a')}..{found.group('b')}"]
    else:
        tokens = [t for t in _PT_SPLIT_RE.split(found.group("ids").strip()) if t]
    return _group_request(tokens, "plain-text", root)


def _expand(token, root):
    """(ids, error) for one range token; ids is None when `token` is no range."""
    found = _RANGE_RE.match(token)
    if not found:
        return None, None
    prefix, start, other, end = found.groups()
    if prefix != other:
        return None, f"range {token!r} mixes prefixes {prefix!r} and {other!r}"
    first, last = int(start), int(end)
    if first > last:
        return None, f"range {token!r} is reversed"
    if last - first + 1 > MAX_GROUP:
        return None, f"range {token!r} names more than {MAX_GROUP} tickets"
    if root and _is_folder(root, token):
        return None, (f"{token!r} is ambiguous: both a ticket and a range; name the "
                      "tickets one by one")
    return [f"{prefix}{n:0{len(start)}d}" for n in range(first, last + 1)], None


def _is_folder(root, token):
    top = crew_ticket.toplevel(root) or root
    try:
        return os.path.isdir(crew_ticket.ticket_dir(top, token))
    except crew_ticket.TicketError:
        return False


def _group_request(tokens, form, root):
    ids = []
    for token in tokens:
        expanded, error = _expand(token, root)
        if error:
            return _refusal(form, error)
        for ticket in expanded if expanded is not None else [token]:
            if ticket not in ids:
                ids.append(ticket)
        if len(ids) > MAX_GROUP:
            return _refusal(form, f"the request names more than {MAX_GROUP} tickets")
    if len(ids) == 1 and len(tokens) > 1:
        return _refusal(form, f"the list repeats {ids[0]} and names nothing else "
                              "(a duplicate-only list)")
    return _request(GROUP, ids, form)


def _payload():
    """(data_or_None, raw_bytes). `data` is None when stdin is not one JSON
    object; the raw bytes are kept so `main` can tell a malformed approval
    from an unrelated prompt."""
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return None, b""
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, raw
    return (data if isinstance(data, dict) else None), raw


def _refuse(text):
    sys.stderr.write(f"crew: /crew:approve was NOT recorded -- {text}\n")
    return 2


def _one_line(text):
    return " ".join(_BREAK_RE.sub(" ", str(text)).split())


def _successor_text(successor):
    """The review-ledger clause after an approval: '' when the ledger is not
    NEEDS_REPLAN. One helper, so a group confirm and a single approval say
    the same thing about the same ledger."""
    if successor is None:
        return ""
    allowed, reason = successor
    return f" Review {'may continue' if allowed else 'is still NEEDS_REPLAN'}: {reason}."


def _emit(text):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": text}}) + "\n")
    return 0


# --- the pending list (T-0024) ---------------------------------------------------

def _pending_path(root):
    """`<git-common-dir>/crew/approval-pending/<sha256(worktree top)[:16]>.json`,
    or None outside git. Per worktree: two worktrees approve two sets."""
    top, state = crew_ticket.toplevel(root), crew_ticket.state_dir(root)
    if not top or not state:
        return None
    key = hashlib.sha256(top.encode("utf-8")).hexdigest()[:16]
    return os.path.join(state, "approval-pending", f"{key}.json")


def _clear_pending(root):
    """Delete this worktree's pending list. Any approval-shaped prompt does
    this before anything else, so a list never outlives the next request."""
    path = _pending_path(root)
    if path and os.path.lexists(path):
        os.remove(path)


def _single(root, data, ticket):
    _clear_pending(root)
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
    return _emit(text + _successor_text(successor))


def _refuse_all(failing, total, what="cannot be approved"):
    lines = [f"crew: /crew:approve was NOT recorded -- {len(failing)} of {total} "
             + f"tickets {what}:"]
    lines += [f"  {ticket}: {'; '.join(_one_line(p) for p in problems)}"
              for ticket, problems in failing]
    lines.append("crew: nothing is recorded or pending; fix these and ask again.")
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def _session(data):
    session = data.get("session_id")
    return session if isinstance(session, str) and session else None


def _pending_group(root, data, request):
    """Check every ticket, then write the pending list and block the prompt
    with it. Nothing is recorded here, whatever the outcome."""
    path = _pending_path(root)
    if not path:
        return _refuse(f"{root} is not a git repository")
    _clear_pending(root)
    session = _session(data)
    if session is None:
        return _refuse("the prompt carries no session_id to bind a pending approval to")
    checks = [crew_ticket.precheck(root, ticket) for ticket in request.ids]
    failing = [(c["ticket"], c["problems"]) for c in checks if c["problems"]]
    if failing:
        return _refuse_all(failing, len(checks))
    # pylint: disable-next=protected-access
    crew_ticket._write_json(path, {
        "session_id": session, "created_at": time.time(), "form": request.form,
        "worktree": crew_ticket.toplevel(root),
        "items": [{"ticket": c["ticket"], "plan_sha256": c["plan_sha256"],
                   "spec_sha256": c["spec_sha256"]} for c in checks]})
    lines = [f"crew: approval PENDING, nothing recorded yet -- {c['ticket']} plan "
             f"{c['plan_sha256'][:12]} spec {c['spec_sha256'][:12]}" for c in checks]
    lines.append(f"crew: type `/crew:approve --confirm` (one line, this session, within "
                 f"{PENDING_TTL // 60} minutes) to record these {len(checks)}.")
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def _well_formed(pending):
    """True for a dict with a non-empty `items` list, each naming a ticket and
    both hashes as non-empty strings, and a numeric `created_at`."""
    items = pending.get("items") if isinstance(pending, dict) else None
    if not isinstance(items, list) or not items:
        return False
    keys = ("ticket", "plan_sha256", "spec_sha256")
    if not all(isinstance(i, dict) and all(isinstance(i.get(k), str) and i.get(k) for k in keys)
               for i in items):
        return False
    created = pending.get("created_at")
    return isinstance(created, (int, float)) and not isinstance(created, bool)


_NO_PENDING = ("no pending group approval in this worktree; ask for the tickets "
               "again (/crew:approve <id> <id> ...)")


def _claim_pending(path):
    """Move the pending list aside under a name only this process knows, and
    return that name -- or None when there is no list. A rename is atomic, so
    of two confirms racing on one list exactly one gets it and the other finds
    nothing: reading and then deleting let both read it, and both record."""
    claimed = f"{path}.claim-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        os.rename(path, claimed)
    except FileNotFoundError:
        return None
    return claimed


def _read_pending(path, root):
    """(pending, why): `why` is None only for a list this confirm may act on."""
    # pylint: disable-next=protected-access
    pending, state = crew_ticket._read_json(path)
    if state == "absent":
        return None, _NO_PENDING
    if state != "ok" or not _well_formed(pending):
        return None, "the pending approval list is unreadable; ask for the tickets again"
    if pending.get("worktree") != crew_ticket.toplevel(root):
        return None, "the pending approval list belongs to another worktree"
    return pending, None


def _confirm(root, data):
    """Record the pending list: same worktree, same session, within
    PENDING_TTL, every hash unchanged -- or record none of it. The list is
    deleted whatever happens (single use)."""
    path = _pending_path(root)
    if not path:
        return _refuse(f"{root} is not a git repository")
    claimed = _claim_pending(path)
    try:
        pending, why = _read_pending(claimed, root) if claimed else (None, _NO_PENDING)
    finally:
        if claimed and os.path.lexists(claimed):
            os.remove(claimed)
    if why:
        return _refuse(why)
    session = _session(data)
    if session is None or pending.get("session_id") != session:
        return _refuse("the pending list was made in another session (a /clear starts a "
                       "new one); ask for the tickets again")
    age = time.time() - pending["created_at"]
    if not 0 <= age <= PENDING_TTL:
        return _refuse(f"the pending list is {int(age)} s old, outside the {PENDING_TTL} s "
                       "window; ask for the tickets again")
    items, failing = pending["items"], []
    for item in items:
        check = crew_ticket.precheck(root, item["ticket"])
        problems = list(check["problems"])
        problems += [f"{name} changed since the approval was requested"
                     for name, key in (("spec.md", "spec_sha256"), ("plan.md", "plan_sha256"))
                     if check[key] != item[key]]
        if problems:
            failing.append((item["ticket"], problems))
    if failing:
        return _refuse_all(failing, len(items), "no longer match what you were shown")
    clauses, recorded = [], []
    for index, item in enumerate(items):
        before = _receipt_count(root, item["ticket"])
        try:
            receipt, successor = crew_ticket.approve(
                root, item["ticket"], via=crew_ticket.USER_PROMPT, session=session,
                prompt_id=data.get("prompt_id"),
                expect=(item["plan_sha256"], item["spec_sha256"]))
        except Exception as exc:  # pylint: disable=broad-except
            # ANY failure, not only a TicketError: an OSError escaping to
            # main() would say "NOT recorded" over receipts already written.
            mine = {"approved_via": crew_ticket.USER_PROMPT, "session_id": session,
                    "prompt_id": data.get("prompt_id"),
                    "plan_sha256": item["plan_sha256"], "spec_sha256": item["spec_sha256"]}
            return _partly(root, items, index, recorded, (before, mine), exc)
        recorded.append(item["ticket"])
        clauses.append(f"{item['ticket']}: plan {receipt['plan_sha256'][:12]}, spec "
                       f"{receipt['spec_sha256'][:12]}, approved_via user-prompt."
                       f"{_successor_text(successor)}")
    return _emit(f"crew: the user approved {', '.join(recorded)} from their own prompt "
                 f"(group confirm). " + " ".join(clauses))


def _receipt_count(root, ticket):
    """How many approvals `ticket`'s receipt history holds: 0 with no receipt,
    None when it cannot be read -- "could not tell", never 0."""
    try:
        receipt, state = crew_ticket.read_approval(root, ticket)
    except (crew_ticket.TicketError, OSError):
        return None
    if state == "absent":
        return 0
    history = receipt.get("history") if state == "ok" else None
    return len(history) if isinstance(history, list) else None


def _wrote(root, ticket, before, mine):
    """Whether THIS confirm's entry is in `ticket`'s receipt history: True,
    False, or None ("could not tell") when the receipt cannot be read. Keyed
    by the confirm's own session, prompt and hashes, among the entries added
    since `before` -- never by history growth, which another session's
    approval of the same ticket also causes (review round 2)."""
    try:
        receipt, state = crew_ticket.read_approval(root, ticket)
    except (crew_ticket.TicketError, OSError):
        return None
    if state == "absent":
        return False
    history = receipt.get("history") if state == "ok" else None
    if not isinstance(history, list):
        return None
    added = history[before:] if isinstance(before, int) else history
    return any(isinstance(entry, dict) and all(entry.get(k) == v for k, v in mine.items())
               for entry in added)


def _partly(root, items, index, recorded, attempt, exc):
    """A confirm failed on `items[index]` after `recorded` were written. Say
    which tickets hold a receipt from this confirm, which do not, and which
    cannot be told -- the failing ticket's receipt may have been written
    before the failure (the ledger step runs after the write)."""
    ticket = items[index]["ticket"]
    before, mine = attempt
    wrote = _wrote(root, ticket, before, mine)
    recorded, unknown = list(recorded), []
    if wrote is None:
        unknown.append(ticket)
    elif wrote:
        recorded.append(ticket)
    missing = [i["ticket"] for i in items[index:] if i["ticket"] not in recorded + unknown]
    why = _one_line(exc) if isinstance(exc, crew_ticket.TicketError) \
        else f"{type(exc).__name__}: {_one_line(exc)}"
    text = (f"crew: /crew:approve was only PARTLY recorded -- recorded: "
            f"{', '.join(recorded) or 'none'}; NOT recorded: {', '.join(missing) or 'none'}")
    if unknown:
        text += (f"; could not tell whether {ticket} was recorded (its receipt could not "
                 "be read -- check it with crew_ticket.py status)")
    sys.stderr.write(f"{text} ({ticket}: {why})\n")
    return 2


def handle(data):
    """Exit code for one UserPromptSubmit payload. Writes its own output."""
    if not isinstance(data, dict) or data.get("hook_event_name") != "UserPromptSubmit":
        return 0
    root = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = os.path.abspath(root or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    request = parse(data.get("prompt"), root)
    if request.kind == NONE:
        return 0
    if request.kind == SINGLE:
        return _single(root, data, request.ids[0])
    if request.kind == GROUP:
        return _pending_group(root, data, request)
    if request.kind == CONFIRM:
        return _confirm(root, data)
    _clear_pending(root)
    return _refuse(request.error)


def main():
    try:
        data, raw = _payload()
        # A payload that mentions the command but does not parse is an
        # approval the user asked for and nobody can read: say so, never
        # pass it as an unrelated prompt.
        if data is None and COMMAND.encode() in raw:
            return _refuse("the hook payload mentions it but is not a JSON object")
        return handle(data)
    except Exception as exc:  # pylint: disable=broad-except
        return _refuse(f"the approval hook failed ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    sys.exit(main())
