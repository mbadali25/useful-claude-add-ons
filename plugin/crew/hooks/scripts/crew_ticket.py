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
`{plan_sha256, spec_sha256, plan_digest, spec_digest, digest, approved_at,
approved_by, approved_via, history}`. The receipt lives in the common git
directory, outside every worktree, and `scope_guard.py` refuses any Write/Edit under
`<git-common-dir>/crew/` in every mode but `off` -- so an Edit cannot forge or
refresh it.

Approval comes from the USER'S PROMPT. `approval_hook.py` (UserPromptSubmit)
records it when the prompt the user typed is `/crew:approve <id>`, with
`approved_via: "user-prompt"` and the prompt's `session_id` and `prompt_id`.
The `approve` CLI below stays for tests and CI and writes
`approved_via: "cli"`; the scope guard and the Stop audit accept a `cli`
receipt (or one with no `approved_via`, from before the field existed) only
when `.crew/config.json` sets `scope.allowCliApproval: true` -- see
`accepted`. The scope guard also refuses a Bash/PowerShell command that
invokes `crew_ticket.py approve` or the approval hook, or writes under
`<git-common-dir>/crew/`. That stops drift and accidental bypass; a session
with a shell can still forge local state on purpose, and README "Scope and
approval" says so.

READ ONCE. `approve` reads spec.md and plan.md once, validates those bytes
and hashes the same bytes, so a file edited between the check and the hash
is never approved unvalidated. `status` likewise hashes the bytes it parses
Touch from and returns that Touch: a caller never pairs one read's approval
with another read's scope.

`status` is `approved` (both files match the receipt now), `stale` (either
file changed since approval) or `none`. Editing spec.md or plan.md after
approval makes it stale -- except the header's `status:` value, below;
amending scope is edit + approve again.

## The approval digest (T-0026)

One edit does not stale it: the lifecycle commands moving the header's
`status:` VALUE (spec -> planned -> review -> done). `plan_digest` and
`spec_digest` are `approval_digest` of each file, which replaces that value --
and nothing else -- with a placeholder, and only when line 1 is a `# ` header
holding exactly one `status:` whose value is in STATUS_VALUES (`_canonical`).
Any other byte, the `risk:` and the title included, stales it as before.
`plan_sha256`/`spec_sha256` stay the raw full-file sha256: the review ledger's
successor-plan identity reads them unchanged. A receipt with no `digest` key
(written before this) is compared raw, so it verifies on unchanged files and
goes stale once on its first status edit. A `digest` naming any other scheme,
or a `/2` receipt missing a digest field, is `stale` -- never a raw fallback.

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

A pointer that is BROKEN -- this worktree's entry names a ticket with no
directory or is not a ticket id, or the file does not parse -- never falls
back to INDEX.md and never reads as "no active ticket": `resolve_active`
reports it as broken, and the guard and the audit refuse under `block`. A
stale or planted pointer must not be the way every write gets through.

## Scope mode

`scope.mode` in `.crew/config.json`: `off` (the default -- the hooks do
nothing), `report`, `block`, or `auto` -- `report` for the first
`RAMP_TICKETS` tickets approved in this repository, then `block`. The count is
`<git-common-dir>/crew/scope-tickets.json`, appended on a ticket's first
approval. A config file that exists but does not parse, or an unknown value,
resolves to `block` and says so: an armed guard going permissive because its
config broke is the unknown collapsing into the safe-looking value.

## Touch globs are segment-aware

`*`, `?` and `[...]` match within ONE path segment and never cross `/`;
`**` as a whole segment matches zero or more segments. `src/*.py` is the
files directly in `src/`, not `src/a/b.py`. A Touch entry with no wildcard
also covers everything under it as a directory. This is deliberately NOT
`scope_report.gate_matches` (python fnmatch, where `*` consumes `/`): Touch
is an allow-list, and a `*` that silently spans directories widens it.

Exit codes: 0 ok / approved; 1 refused, invalid, stale or none; 2 usage;
3 approved, but the review ledger refused the successor plan.
"""
import argparse
import datetime
import fnmatch
import functools
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
USER_PROMPT = "user-prompt"
CLI = "cli"
# The approval digest (T-0026). The header's status value is the one thing it
# normalises, and only a value from this closed list; see `_canonical`.
STATUS_VALUES = ("spec", "planned", "approved", "in-progress", "review", "done", "merged")
DIGEST_SCHEME = "crew-approval/2"
_STATUS_PLACEHOLDER = b"<status>"
_BOM = b"\xef\xbb\xbf"
_STATUS_ALTERNATION = b"|".join(re.escape(v.encode("ascii")) for v in STATUS_VALUES)
_STATUS_RE = re.compile(rb"(?<=[ \t])status:[ \t]+(" + _STATUS_ALTERNATION + rb")(?=[ \t\r]|\Z)")
_V1 = object()  # `status`'s marker for a receipt with no `digest` key at all

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


def _segments(text):
    return [s for s in text.split("/") if s not in ("", ".")]


def glob_match(path, glob, plan=False):
    """Segment-aware match of `path` against Touch `glob` (module docstring).
    `*`/`?`/`[...]` stay inside one segment (fnmatch per segment, which
    case-folds on Windows); a `**` segment spans zero or more segments.

    `plan=True` judges a plan GLOB as though it were a path: a plan segment
    carrying `**` names any depth, so only a Touch `**` segment covers it."""
    pat, names = _segments(glob), _segments(path)

    @functools.lru_cache(maxsize=None)
    def walk(i, j):
        if i == len(pat):
            return j == len(names)
        if pat[i] == "**":
            return any(walk(i + 1, k) for k in range(j, len(names) + 1))
        if j == len(names) or (plan and "**" in names[j]):
            return False
        return fnmatch.fnmatch(names[j], pat[i]) and walk(i + 1, j + 1)

    return walk(0, 0)


def path_matches(path, glob):
    """`path` is inside Touch entry `glob`: a segment-aware glob match, or --
    for an entry with no wildcard -- anything under it as a directory."""
    if glob_match(path, glob):
        return True
    stem = glob.rstrip("/")
    return not _is_glob(stem) and glob_match(path, stem + "/**")


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
        if star_only and "[" not in plan_entry and "?" not in plan_entry \
                and glob_match(plan_entry, glob, plan=True):
            return True
    return False


# --- validate -------------------------------------------------------------------

def _read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except (OSError, ValueError):
        return None


def _text(data):
    """`crew_common.read_text`'s decoding, applied to bytes already read."""
    text = data.decode("utf-8", errors="replace")
    return text[1:] if text.startswith("\ufeff") else text


def read_contract(top, ticket):
    """`{"spec.md": bytes_or_None, "plan.md": bytes_or_None}` -- ONE read of
    each file. Everything that validates, hashes or parses Touch for one
    decision works from these bytes."""
    folder = ticket_dir(top, ticket)
    return {name: _read_bytes(os.path.join(folder, name)) for name in ("spec.md", "plan.md")}


def validate(top, ticket, contract=None):
    """A list of problems; empty means the spec and plan are a valid contract.
    `contract` is `read_contract`'s result; read here when not given."""
    folder = ticket_dir(top, ticket)
    contract = contract if contract is not None else read_contract(top, ticket)
    problems = []
    if contract.get("spec.md") is None:
        return [f"{os.path.join(folder, 'spec.md')} is missing or unreadable"]
    spec = _text(contract["spec.md"])
    found = sections(spec)
    for name in SECTIONS:
        body = found.get(name.casefold())
        if body is None:
            problems.append(f"spec.md has no ## {name} section")
        elif not body:
            problems.append(f"spec.md ## {name} is empty")
    touch, touch_problems = parse_touch(spec)
    problems.extend(touch_problems)
    if contract.get("plan.md") is None:
        return problems + [f"{os.path.join(folder, 'plan.md')} is missing or unreadable"]
    files, counts, plan_problems = parse_plan(_text(contract["plan.md"]))
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

def _sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _canonical(data):
    """`(bytes, normalised)`: `data` with the header's status VALUE replaced by
    `_STATUS_PLACEHOLDER`, or `data` untouched and False.

    Only line 1 is examined -- the bytes before the first `\n`, any `\r` kept.
    It must start with `# ` (after an optional UTF-8 BOM), hold exactly one
    `status:` counted case-insensitively, and that one must be the token
    `status:<spaces/tabs><value>` with `value` in STATUS_VALUES followed by a
    space, a tab, `\r` or the end of the line. Anything else -- no token, two,
    an unknown value, a header that moved -- normalises nothing, so the edit
    that caused it stales the approval."""
    cut = data.find(b"\n")
    head, rest = (data, b"") if cut < 0 else (data[:cut], data[cut:])
    body = head.removeprefix(_BOM)
    if not body.startswith(b"# "):
        return data, False
    if head.lower().count(b"status:") != 1:
        return data, False
    match = _STATUS_RE.search(head)
    if match is None:
        return data, False
    start, end = match.span(1)
    return head[:start] + _STATUS_PLACEHOLDER + head[end:] + rest, True


def approval_digest(data):
    """The `crew-approval/2` digest of one file's bytes, or None for None.

    sha256 over the scheme, a NUL, whether the header was normalised, a NUL,
    then the canonical bytes. The flag is domain separation: a raw file that
    happens to hold the placeholder text can never equal a normalised one."""
    if data is None:
        return None
    canonical, normalised = _canonical(data)
    flag = b"normalised" if normalised else b"raw"
    return hashlib.sha256(DIGEST_SCHEME.encode("ascii") + b"\0" + flag + b"\0"
                          + canonical).hexdigest()


def current_hashes(top, ticket):
    contract = read_contract(top, ticket)
    return _sha(contract["plan.md"]), _sha(contract["spec.md"])


def read_approval(root, ticket):
    """(receipt_or_None, state) -- state 'absent', 'ok' or 'corrupt'."""
    data, state = _read_json(approval_path(root, ticket))
    if state == "ok" and not isinstance(data, dict):
        return None, "corrupt"
    return data, state


def status(root, ticket):
    """`{"status": approved|stale|none, "why", "receipt", "touch"}`.

    spec.md and plan.md are read ONCE; the hashes compared with the receipt
    and the `touch` returned both come from those bytes, so an `approved`
    status never travels with a Touch read from a later version of the spec.
    `touch` is empty unless the status is `approved`. A corrupt receipt is
    `none` with the reason: an approval nobody can read is not one."""
    top = toplevel(root) or os.path.abspath(root)
    try:
        receipt, state = read_approval(root, ticket)
    except TicketError as exc:
        return {"status": "none", "why": str(exc), "receipt": None, "touch": []}
    if state == "absent":
        return {"status": "none", "why": f"{ticket} has no approved plan", "receipt": None,
                "touch": []}
    if state == "corrupt":
        return {"status": "none", "why": f"the approval receipt for {ticket} is unreadable",
                "receipt": None, "touch": []}
    contract = read_contract(top, ticket)
    scheme = receipt.get("digest", _V1)
    if scheme is _V1:
        measure, keys = _sha, ("plan_sha256", "spec_sha256")
    elif scheme == DIGEST_SCHEME:
        measure, keys = approval_digest, ("plan_digest", "spec_digest")
        unusable = [k for k in keys if not isinstance(receipt.get(k), str)]
        if unusable:
            return {"status": "stale", "receipt": receipt, "touch": [],
                    "why": (f"the approval receipt has no usable {' or '.join(unusable)}; "
                            "approve again")}
    else:
        return {"status": "stale", "receipt": receipt, "touch": [],
                "why": (f"approval receipt digest scheme {scheme!r} is not one this "
                        "crew reads; approve again")}
    changed = [name for name, now, then in (
        ("plan.md", measure(contract["plan.md"]), receipt.get(keys[0])),
        ("spec.md", measure(contract["spec.md"]), receipt.get(keys[1])))
        if not now or now != then]
    if changed:
        return {"status": "stale", "receipt": receipt, "touch": [],
                "why": (f"{' and '.join(changed)} changed since approval at "
                        f"{receipt.get('approved_at')}; approve again")}
    touch, _ = parse_touch(_text(contract["spec.md"]))
    return {"status": "approved", "receipt": receipt, "touch": touch,
            "why": (f"approved by {receipt.get('approved_by')} at "
                    f"{receipt.get('approved_at')} via "
                    f"{receipt.get('approved_via') or 'an unrecorded route'}")}


def cli_approval_allowed(top):
    """True only when `.crew/config.json` parses and sets
    `scope.allowCliApproval` to exactly `true`."""
    data, state = _read_json(os.path.join(top, ".crew", "config.json"))
    scope = data.get("scope") if state == "ok" and isinstance(data, dict) else None
    return isinstance(scope, dict) and scope.get("allowCliApproval") is True


def accepted(root, ticket):
    """`status`, with an `approved` receipt that did not come from the user's
    prompt demoted to `unaccepted` unless `scope.allowCliApproval` is true.
    This is what the scope guard and the Stop audit act on."""
    result = status(root, ticket)
    if result["status"] != "approved":
        return result
    via = (result["receipt"] or {}).get("approved_via")
    if via == USER_PROMPT or cli_approval_allowed(toplevel(root) or os.path.abspath(root)):
        return result
    return dict(result, status="unaccepted", touch=[],
                why=(f"its approval was recorded via {via or 'an unrecorded route'}, not "
                     f"the user's prompt; the user types `/crew:approve {ticket}`"))


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


def approve(root, ticket, by=None, via=CLI, session=None, prompt_id=None):
    """Validate, then write the receipt. Returns `(receipt, successor)`;
    `successor` is None when the review ledger is not NEEDS_REPLAN, else
    `(allowed, reason)` from the ledger seam.

    spec.md and plan.md are read once; the bytes validated are the bytes
    hashed. `via` is `cli` (this module's CLI, tests, CI) or `user-prompt`
    (`approval_hook.py`, which also passes the prompt's session and id)."""
    if via not in (CLI, USER_PROMPT):
        raise TicketError(f"approved_via {via!r} is not {CLI} or {USER_PROMPT}")
    top = toplevel(root)
    if not top:
        raise TicketError(f"{root} is not a git repository")
    contract = read_contract(top, ticket)
    problems = validate(top, ticket, contract)
    if problems:
        raise TicketError("not approved -- the contract does not validate:\n  "
                          + "\n  ".join(problems))
    plan_sha, spec_sha = _sha(contract["plan.md"]), _sha(contract["spec.md"])
    previous, state = read_approval(root, ticket)
    if state == "corrupt":
        # The history is what tells a successor plan from the one that ran out
        # of review rounds; restarting it would let the same plan count as new.
        raise TicketError(f"the approval receipt at {approval_path(root, ticket)} is "
                          "unreadable; inspect it and remove it by hand before approving")
    history = list((previous or {}).get("history") or [])
    entry = {"plan_sha256": plan_sha, "spec_sha256": spec_sha,
             "plan_digest": approval_digest(contract["plan.md"]),
             "spec_digest": approval_digest(contract["spec.md"]), "digest": DIGEST_SCHEME,
             "approved_at": _now(), "approved_by": (by or "").strip() or _default_approver(root),
             "approved_via": via}
    if via == USER_PROMPT:
        entry["session_id"] = session if isinstance(session, str) else None
        entry["prompt_id"] = prompt_id if isinstance(prompt_id, str) else None
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


def resolve_active(root):
    """(ticket_or_None, source, broken). `broken` is True when this
    worktree's active-ticket pointer exists but cannot be honoured -- the
    file does not parse, the entry is not a ticket id, or it names a ticket
    with no `.work/tickets/<id>/` directory. A broken pointer never falls back
    to INDEX.md; the caller refuses under `block` (module docstring)."""
    top = toplevel(root)
    if not top:
        return None, "not a git repository", False
    path = _active_path(root)
    data, state = _read_json(path) if path else (None, "absent")
    if state == "corrupt" or (state == "ok" and not isinstance(data, dict)):
        return None, f"the active-ticket pointer {path} does not parse", True
    if state == "ok" and top in data:
        ticket = data[top]
        if isinstance(ticket, str) and _TICKET_RE.match(ticket) \
                and os.path.isdir(ticket_dir(top, ticket)):
            return ticket, "active-ticket", False
        return None, (f"active-ticket names {ticket!r}, which has no .work/tickets/ "
                      "directory"), True
    try:
        import crew_state  # pylint: disable=import-outside-toplevel
        ticket = crew_state.read_work(top).get("ticket")
    except Exception:  # pylint: disable=broad-except
        ticket = None
    if ticket and _TICKET_RE.match(ticket) and os.path.isdir(ticket_dir(top, ticket)):
        return ticket, ".work/INDEX.md", False
    return None, "no active ticket", False


def active_ticket(root):
    """(ticket_or_None, source) -- `resolve_active` without the broken flag.
    The ticket is returned only when its 1.0 directory exists."""
    ticket, source, _broken = resolve_active(root)
    return ticket, source


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
    """Touch entries of `ticket`'s spec (empty when unreadable). For display;
    a decision takes Touch from `status`, which hashed the same bytes."""
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
        print(f"crew-ticket: {args.ticket} approved by {receipt['approved_by']} via cli "
              f"(plan {receipt['plan_sha256'][:12]}, spec {receipt['spec_sha256'][:12]})")
        if not cli_approval_allowed(top):
            print("crew-ticket: a cli approval satisfies the scope guard only with "
                  f"scope.allowCliApproval true; the user types `/crew:approve {args.ticket}`")
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
