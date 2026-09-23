"""The ticket contract: spec + plan validation, plan approval, the active
ticket, and the scope mode. crew 1.0, lane T3.

## The ticket directory

`.work/tickets/<id>/` holds `direction.md`, `spec.md` and `plan.md`.

`spec.md` must carry six `## ` sections -- Intent, Exclusions, Evidence,
Unknowns, Touch, Acceptance checks -- each with a non-empty body. `## Touch`
is one repo-relative glob or path per bullet line (`- src/app/*.py`). A bullet
may put the path in backticks and follow it with prose; a bare bullet that
contains whitespace is refused rather than guessed at.

`plan.md` is a list of steps, each carrying a `Files:` line (comma-separated
globs or paths, or bullets under an empty `Files:`), a `Test:` line and a
`Risk:` line. `validate` counts the three labels and refuses a plan where they
differ: that is "every step lists files, test and risk" measured without
guessing how the steps are headed.

## Plan paths never widen Touch

Every `Files:` entry must be COVERED by a Touch entry, and a plan entry outside
Touch is an error, never a silent widening (04-redesign.md, Lifecycle table).
"Covered" is decided conservatively -- see `covered_by`: a plain path must
match a Touch glob the way the edit guard will match it; a plan GLOB is covered
only by an identical Touch entry, a Touch directory it sits under, or a Touch
glob whose only wildcard is `*`. The check can refuse a plan glob that is in
fact a subset; it never accepts one that is wider.

## The approval receipt

`approve` writes `<git-common-dir>/crew/tickets/<id>/approval.json`:
`{plan_sha256, spec_sha256, approved_at, approved_by, history}`. The receipt
lives in the common git directory, outside every worktree, and
`scope_guard.py` refuses any Write/Edit under `<git-common-dir>/crew/` in
every mode but `off` -- so an Edit cannot forge or refresh it. `approve` is
for the USER to run (the lifecycle command tells the session to ask). Nothing
here can tell a person at a shell from a session's Bash tool; that limit is
stated, not papered over (README "Scope and approval").

`status` is `approved` (both hashes match the files now), `stale` (either
file changed since approval) or `none`. Editing spec.md or plan.md after
approval makes it stale; amending scope is edit + `approve` again.

## Successor plans

When the review ledger is NEEDS_REPLAN, `approve` records the new plan and
calls `review_ledger.continue_with_successor_plan`, which lets review continue
only for a plan hash no earlier approval of this ticket carried.

## The active ticket

`<git-common-dir>/crew/active-ticket` is a JSON map from a worktree's real
top-level path to a ticket id, written by `crew_ticket.py activate`. Keyed by
worktree because the common git directory is shared by every worktree of a
repository and two worktrees work two tickets. When this worktree has no entry,
the open ticket in `.work/INDEX.md` (`crew_state.read_work`, what `/crew:work`
already maintains) is used -- but only when `.work/tickets/<id>/` exists, so a
0.x ticket file (`.work/tickets/<id>.md`) never engages the 1.0 guard.

## Scope mode

`scope.mode` in `.crew/config.json`: `off` (the default -- the hooks do
nothing), `report`, `block`, or `auto` -- `report` for the first
`RAMP_TICKETS` tickets approved in this repository, then `block`. The count is
`<git-common-dir>/crew/scope-tickets.json`, appended on a ticket's first
approval. A config file that exists but does not parse, or an unknown value,
resolves to `block` and says so: an armed guard going permissive because its
config broke is the unknown collapsing into the safe-looking value.

Exit codes: 0 ok / approved; 1 refused, invalid, stale or none; 2 usage;
3 approved, but the review ledger refused the successor plan.
"""
import argparse
import datetime
import fnmatch
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys

import crew_common

SECTIONS = ("Intent", "Exclusions", "Evidence", "Unknowns", "Touch",
            "Acceptance checks")
MODES = ("off", "report", "block", "auto")
RAMP_TICKETS = 10

_TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_LABEL_RE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?(Files|Test|Risk)(?:\*\*|__)?\s*:(?:\*\*|__)?\s*(.*)$",
    re.IGNORECASE)
_GLOB_CHARS = ("*", "?", "[")


class TicketError(RuntimeError):
    """A ticket operation that could not be carried out."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check_ticket(ticket):
    if not isinstance(ticket, str) or not _TICKET_RE.match(ticket):
        raise TicketError(f"ticket id {ticket!r} is not a plain id "
                          "(letters, digits, '.', '_', '-'; no path separators)")
    return ticket


# --- git locations -----------------------------------------------------------

def _git(root, *args):
    try:
        done = subprocess.run(["git", "-C", root] + list(args), capture_output=True,
                              text=True, check=False, timeout=30,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def toplevel(root):
    """The worktree's real top-level directory, or None outside git."""
    top = _git(root, "rev-parse", "--show-toplevel")
    return os.path.realpath(top) if top else None


def common_dir(root):
    """`git rev-parse --git-common-dir`, absolute and real, or None."""
    path = _git(root, "rev-parse", "--git-common-dir")
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(os.path.abspath(root), path)
    return os.path.realpath(path)


def state_dir(root):
    """`<git-common-dir>/crew`, or None outside git."""
    common = common_dir(root)
    return os.path.join(common, "crew") if common else None


def ticket_dir(top, ticket):
    return os.path.join(top, ".work", "tickets", check_ticket(ticket))


def approval_path(root, ticket):
    state = state_dir(root)
    if not state:
        raise TicketError(f"{root} is not a git repository; there is nowhere to "
                          "keep an approval receipt")
    return os.path.join(state, "tickets", check_ticket(ticket), "approval.json")


def _read_json(path):
    """(data, state): state is 'absent', 'ok' or 'corrupt'."""
    text = crew_common.read_text(path)
    if text is None:
        return None, ("corrupt" if os.path.lexists(path) else "absent")
    try:
        return json.loads(text), "ok"
    except ValueError:
        return None, "corrupt"


def _write_json(path, data):
    # Temp file then os.replace: the payload is built before anything is
    # opened, and a failed write costs the temp file, never the receipt.
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)


# --- spec and plan parsing ---------------------------------------------------

def sections(text):
    """`{heading: body}` for every `## ` heading, heading case-folded."""
    found, current, lines = {}, None, []
    for line in (text or "").splitlines():
        match = _HEADING_RE.match(line)
        if match and not line.startswith("###"):
            if current is not None:
                found[current] = "\n".join(lines).strip()
            current, lines = match.group(1).strip().casefold(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        found[current] = "\n".join(lines).strip()
    return found


def _entry_problem(entry):
    """Why `entry` cannot be a scope path, or None."""
    if not entry:
        return "empty entry"
    if entry.startswith("<"):
        return f"placeholder {entry!r}"
    if entry.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", entry):
        return f"{entry!r} is absolute; Touch is repo-relative"
    if ".." in re.split(r"[\\/]+", entry):
        return f"{entry!r} contains '..'"
    return None


def _bullet_entry(text):
    """The one path a bullet names, or (None, problem)."""
    ticks = _BACKTICK_RE.findall(text)
    if ticks:
        if len(ticks) > 1:
            return None, f"one path per bullet, found {len(ticks)} in {text!r}"
        entry = ticks[0].strip()
    else:
        entry = text.strip()
        if re.search(r"\s", entry):
            return None, (f"{text!r} is not one path; put the path in backticks "
                          "if the bullet carries a comment")
    problem = _entry_problem(entry)
    return (None, problem) if problem else (entry.replace("\\", "/"), None)


def parse_touch(spec_text):
    """(entries, problems) from spec.md's `## Touch` section."""
    body = sections(spec_text).get("touch")
    if body is None:
        return [], ["spec.md has no ## Touch section"]
    entries, problems = [], []
    for line in body.splitlines():
        match = _BULLET_RE.match(line)
        if not match:
            continue
        entry, problem = _bullet_entry(match.group(1))
        if problem:
            problems.append(f"Touch: {problem}")
        else:
            entries.append(entry)
    if not entries and not problems:
        problems.append("## Touch lists no paths (one glob or path per bullet line)")
    return entries, problems


def _split_files(value):
    ticks = _BACKTICK_RE.findall(value)
    raw = ticks if ticks else [p for p in re.split(r"[,\s]+", value) if p]
    return [r.strip() for r in raw if r.strip()]


def parse_plan(plan_text):
    """(files, counts, problems): every `Files:` entry, the number of
    Files/Test/Risk labels, and anything malformed."""
    files, problems = [], []
    counts = {"files": 0, "test": 0, "risk": 0}
    lines = (plan_text or "").splitlines()
    i = 0
    while i < len(lines):
        match = _LABEL_RE.match(lines[i])
        i += 1
        if not match:
            continue
        label = match.group(1).casefold()
        counts[label] += 1
        if label != "files":
            continue
        value = match.group(2).strip()
        entries = _split_files(value) if value else []
        if not value:
            while i < len(lines) and _BULLET_RE.match(lines[i]) \
                    and not _LABEL_RE.match(lines[i]):
                entries.extend(_split_files(_BULLET_RE.match(lines[i]).group(1)))
                i += 1
        if not entries:
            problems.append(f"plan.md line {i}: Files: names no path")
        for entry in entries:
            problem = _entry_problem(entry)
            if problem:
                problems.append(f"plan Files: {problem}")
            else:
                files.append(entry.replace("\\", "/"))
    return files, counts, problems


# --- matching ------------------------------------------------------------------

def gate_matches(path, pat):
    """verify-gate's matcher (`scope_report.gate_matches`), restated here so
    the PreToolUse guard does not import crew_state on every Write. KEPT IN
    LOCKSTEP with `scope_report.gate_matches`; test_crew_ticket asserts the
    two agree."""
    cands = {pat}
    if pat.startswith("**/"):
        cands.add(pat[3:])
    cands.add(pat.replace("/**/", "/"))
    return any(fnmatch.fnmatch(path, c) for c in cands)


def path_matches(path, glob):
    """`scope_report.matches`: the gate's matcher plus a bare directory
    entry covering everything under it. Case-folded on Windows through
    fnmatch's own normcase, and by hand for the prefix form."""
    if gate_matches(path, glob):
        return True
    stem = glob.rstrip("/")
    if os.name == "nt":
        return os.path.normcase(path).startswith(os.path.normcase(stem + "/")) \
            or fnmatch.fnmatch(path, stem + "/*")
    return fnmatch.fnmatch(path, stem + "/*") or path.startswith(stem + "/")


def in_touch(path, touch):
    return any(path_matches(path, glob) for glob in touch)


def _is_glob(text):
    return any(c in text for c in _GLOB_CHARS)


def covered_by(plan_entry, touch):
    """True when every path `plan_entry` can name is inside `touch`.
    Conservative for a plan glob -- see the module docstring."""
    if not _is_glob(plan_entry):
        return in_touch(plan_entry, touch)
    for glob in touch:
        if os.path.normcase(plan_entry) == os.path.normcase(glob):
            return True
        stem = glob.rstrip("/")
        if not _is_glob(stem) and os.path.normcase(plan_entry).startswith(
                os.path.normcase(stem + "/")):
            return True
        star_only = "?" not in glob and "[" not in glob
        if star_only and "[" not in plan_entry and gate_matches(plan_entry, glob):
            return True
    return False


# --- validate -------------------------------------------------------------------

def _read(path):
    text = crew_common.read_text(path)
    if text is None:
        raise TicketError(f"{path} is missing or unreadable")
    return text


def validate(top, ticket):
    """A list of problems; empty means the spec and plan are a valid contract."""
    folder = ticket_dir(top, ticket)
    problems = []
    try:
        spec = _read(os.path.join(folder, "spec.md"))
    except TicketError as exc:
        return [str(exc)]
    found = sections(spec)
    for name in SECTIONS:
        body = found.get(name.casefold())
        if body is None:
            problems.append(f"spec.md has no ## {name} section")
        elif not body:
            problems.append(f"spec.md ## {name} is empty")
    touch, touch_problems = parse_touch(spec)
    problems.extend(touch_problems)
    try:
        plan = _read(os.path.join(folder, "plan.md"))
    except TicketError as exc:
        return problems + [str(exc)]
    files, counts, plan_problems = parse_plan(plan)
    problems.extend(plan_problems)
    if counts["files"] == 0:
        problems.append("plan.md has no step with a Files: line")
    if len(set(counts.values())) != 1:
        problems.append(f"plan.md steps must each list Files, Test and Risk: found "
                        f"{counts['files']} Files, {counts['test']} Test, "
                        f"{counts['risk']} Risk")
    for entry in files:
        if touch and not covered_by(entry, touch):
            problems.append(f"plan Files entry {entry!r} is outside spec ## Touch -- "
                            "amend the spec's Touch (and approve again), the plan "
                            "never widens it")
    return problems


# --- approval --------------------------------------------------------------------

def file_sha256(path):
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def current_hashes(top, ticket):
    folder = ticket_dir(top, ticket)
    return (file_sha256(os.path.join(folder, "plan.md")),
            file_sha256(os.path.join(folder, "spec.md")))


def read_approval(root, ticket):
    """(receipt_or_None, state) -- state 'absent', 'ok' or 'corrupt'."""
    data, state = _read_json(approval_path(root, ticket))
    if state == "ok" and not isinstance(data, dict):
        return None, "corrupt"
    return data, state


def status(root, ticket):
    """`{"status": approved|stale|none, "why": ..., "receipt": ...}`.
    A corrupt receipt is `none` with the reason: an approval nobody can read
    is not one."""
    top = toplevel(root) or os.path.abspath(root)
    try:
        receipt, state = read_approval(root, ticket)
    except TicketError as exc:
        return {"status": "none", "why": str(exc), "receipt": None}
    if state == "absent":
        return {"status": "none", "why": f"{ticket} has no approved plan", "receipt": None}
    if state == "corrupt":
        return {"status": "none", "why": f"the approval receipt for {ticket} is unreadable",
                "receipt": None}
    plan_sha, spec_sha = current_hashes(top, ticket)
    changed = [name for name, now, then in (
        ("plan.md", plan_sha, receipt.get("plan_sha256")),
        ("spec.md", spec_sha, receipt.get("spec_sha256"))) if not now or now != then]
    if changed:
        return {"status": "stale", "receipt": receipt,
                "why": (f"{' and '.join(changed)} changed since approval at "
                        f"{receipt.get('approved_at')}; approve again")}
    return {"status": "approved", "receipt": receipt,
            "why": f"approved by {receipt.get('approved_by')} at {receipt.get('approved_at')}"}


def _default_approver(root):
    name = _git(root, "config", "user.name")
    if name:
        return name
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return "unknown"


def _register_ramp(root, ticket):
    path = os.path.join(state_dir(root), "scope-tickets.json")
    data, state = _read_json(path)
    if state == "corrupt" or (state == "ok" and not isinstance(data, dict)):
        # Unreadable history is UNKNOWN; rewriting it would restart the ramp.
        return
    tickets = list((data or {}).get("tickets") or [])
    if ticket not in tickets:
        tickets.append(ticket)
        _write_json(path, {"tickets": tickets})


def approve(root, ticket, by=None):
    """Validate, then write the receipt. Returns `(receipt, successor)`;
    `successor` is None when the review ledger is not NEEDS_REPLAN, else
    `(allowed, reason)` from the ledger seam."""
    top = toplevel(root)
    if not top:
        raise TicketError(f"{root} is not a git repository")
    problems = validate(top, ticket)
    if problems:
        raise TicketError("not approved -- the contract does not validate:\n  "
                          + "\n  ".join(problems))
    plan_sha, spec_sha = current_hashes(top, ticket)
    previous, state = read_approval(root, ticket)
    if state == "corrupt":
        # The history is what tells a successor plan from the one that ran out
        # of review rounds; restarting it would let the same plan count as new.
        raise TicketError(f"the approval receipt at {approval_path(root, ticket)} is "
                          "unreadable; inspect it and remove it by hand before approving")
    history = list((previous or {}).get("history") or [])
    entry = {"plan_sha256": plan_sha, "spec_sha256": spec_sha,
             "approved_at": _now(), "approved_by": (by or "").strip() or _default_approver(root)}
    receipt = dict(entry, ticket=ticket, history=history + [entry])
    _write_json(approval_path(root, ticket), receipt)
    _register_ramp(root, ticket)
    import review_ledger  # pylint: disable=import-outside-toplevel
    ledger = review_ledger.status(root, ticket)
    successor = None
    if ledger.get("state") == review_ledger.NEEDS_REPLAN:
        successor = review_ledger.continue_with_successor_plan(root, ticket, plan_sha)
    return receipt, successor


def earlier_plan_hashes(root, ticket):
    """Plan hashes of every approval of `ticket` before the latest one."""
    receipt, state = read_approval(root, ticket)
    if state != "ok":
        return set()
    history = receipt.get("history") or []
    return {h.get("plan_sha256") for h in history[:-1] if isinstance(h, dict)}


# --- active ticket ------------------------------------------------------------------

def _active_path(root):
    state = state_dir(root)
    return os.path.join(state, "active-ticket") if state else None


def activate(root, ticket):
    check_ticket(ticket)
    top, path = toplevel(root), _active_path(root)
    if not top or not path:
        raise TicketError(f"{root} is not a git repository")
    data, state = _read_json(path)
    mapping = data if state == "ok" and isinstance(data, dict) else {}
    mapping[top] = ticket
    _write_json(path, mapping)


def deactivate(root):
    top, path = toplevel(root), _active_path(root)
    if not top or not path:
        return
    data, state = _read_json(path)
    if state == "ok" and isinstance(data, dict) and top in data:
        del data[top]
        _write_json(path, data)


def active_ticket(root):
    """(ticket_or_None, source). The ticket is returned only when its 1.0
    directory exists under this worktree."""
    top = toplevel(root)
    if not top:
        return None, "not a git repository"
    path = _active_path(root)
    data, state = _read_json(path) if path else (None, "absent")
    if state == "ok" and isinstance(data, dict) and isinstance(data.get(top), str):
        ticket = data[top]
        if _TICKET_RE.match(ticket) and os.path.isdir(ticket_dir(top, ticket)):
            return ticket, "active-ticket"
        return None, f"active-ticket names {ticket!r}, which has no .work/tickets/ directory"
    try:
        import crew_state  # pylint: disable=import-outside-toplevel
        ticket = crew_state.read_work(top).get("ticket")
    except Exception:  # pylint: disable=broad-except
        ticket = None
    if ticket and _TICKET_RE.match(ticket) and os.path.isdir(ticket_dir(top, ticket)):
        return ticket, ".work/INDEX.md"
    return None, "no active ticket"


# --- scope mode -------------------------------------------------------------------------

def configured_mode(top):
    """(value, why). `value` is one of MODES; a corrupt config or an unknown
    value is `block`, with the reason."""
    path = os.path.join(top, ".crew", "config.json")
    data, state = _read_json(path)
    if state == "absent":
        return "off", "no .crew/config.json"
    if state == "corrupt" or not isinstance(data, dict):
        return "block", ".crew/config.json exists but does not parse; failing closed"
    scope = data.get("scope")
    if scope is None:
        return "off", "scope.mode not set"
    if not isinstance(scope, dict):
        return "block", "scope in .crew/config.json is not an object; failing closed"
    value = scope.get("mode", "off")
    if value is None:
        return "off", "scope.mode not set"
    if value not in MODES:
        return "block", f"scope.mode {value!r} is not one of {'/'.join(MODES)}; failing closed"
    return value, f"scope.mode is {value}"


def effective_mode(root, ticket):
    """(mode, why) with `auto` resolved to report/block for `ticket`."""
    top = toplevel(root) or os.path.abspath(root)
    value, why = configured_mode(top)
    if value != "auto":
        return value, why
    state = state_dir(root)
    data, rstate = _read_json(os.path.join(state, "scope-tickets.json")) if state \
        else (None, "absent")
    if rstate == "corrupt" or (rstate == "ok" and not isinstance(data, dict)):
        return "block", "scope.mode auto, and the ticket count is unreadable; failing closed"
    tickets = list((data or {}).get("tickets") or [])
    position = tickets.index(ticket) if ticket in tickets else len(tickets)
    if position < RAMP_TICKETS:
        return "report", (f"scope.mode auto: ticket {position + 1} of the first "
                          f"{RAMP_TICKETS} reports")
    return "block", f"scope.mode auto: past the first {RAMP_TICKETS} tickets"


def touch_for(top, ticket):
    """Touch entries of `ticket`'s spec (empty when unreadable)."""
    text = crew_common.read_text(os.path.join(ticket_dir(top, ticket), "spec.md"))
    entries, _ = parse_touch(text or "")
    return entries


# --- CLI ------------------------------------------------------------------------------

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("validate", "approve", "status", "activate",
                                           "deactivate", "active", "touch"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--by", help="who is approving (default: git user.name)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        if args.action == "deactivate":
            deactivate(root)
            print("crew-ticket: no active ticket for this worktree")
            return 0
        if args.action == "active":
            ticket, source = active_ticket(root)
            print(ticket or "")
            sys.stderr.write(f"crew-ticket: {source}\n")
            return 0 if ticket else 1
        if not args.ticket:
            parser.error(f"{args.action} needs --ticket <id>")
        check_ticket(args.ticket)
        top = toplevel(root) or root
        if args.action == "validate":
            problems = validate(top, args.ticket)
            for problem in problems:
                print(f"INVALID: {problem}")
            if not problems:
                print(f"crew-ticket: {args.ticket} spec and plan are valid")
            return 1 if problems else 0
        if args.action == "touch":
            print("\n".join(touch_for(top, args.ticket)))
            return 0
        if args.action == "activate":
            activate(root, args.ticket)
            print(f"crew-ticket: {args.ticket} is the active ticket for this worktree")
            return 0
        if args.action == "status":
            result = status(root, args.ticket)
            print(f"{result['status']}: {result['why']}")
            return 0 if result["status"] == "approved" else 1
        receipt, successor = approve(root, args.ticket, args.by)
        print(f"crew-ticket: {args.ticket} approved by {receipt['approved_by']} "
              f"(plan {receipt['plan_sha256'][:12]}, spec {receipt['spec_sha256'][:12]})")
        if successor is not None:
            allowed, reason = successor
            print(f"crew-ticket: review {'may continue' if allowed else 'is still NEEDS_REPLAN'}"
                  f" -- {reason}")
            return 0 if allowed else 3
        return 0
    except TicketError as exc:
        sys.stderr.write(f"crew-ticket: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
