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

## Minting (T-0019)

`mint` is the one way code creates a ticket: one past the highest `T-`
number over `.work/tickets/` folders and INDEX rows, claimed by an exclusive
`os.mkdir`, direction.md written complete or not at all, and only then the
INDEX row (and, under obsidian, the vault note and Kanban card) through
`crew_tracker.create`, then `move` to `ready`. `mint` never opens INDEX for
writing itself. A tracker `id taken` releases the folder and takes the next
id; any other failure releases it and raises. Under jira, sdp, no tracker or
a tracker that could not tell, it refuses before claiming anything.
`assign` is `/crew:autopilot assign`'s: it checks a staging file under
`.work/autopilot/` and that autopilot is armed, then mints once. Both live
here, not in `crew_autopilot.py`, whose one writer stays `approve`.

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
import stat
import subprocess
import sys
import time

import crew_common

SECTIONS = ("Intent", "Exclusions", "Evidence", "Unknowns", "Touch",
            "Acceptance checks")
MODES = ("off", "report", "block", "auto")
RAMP_TICKETS = 10
USER_PROMPT = "user-prompt"
CLI = "cli"
# T-0010: `crew_autopilot.py approve`'s receipt. It stands only while
# `scope.allowCliApproval` is true AND `crew_autopilot.approval_policy` still
# allows it for the spec as it is now (`accepted`).
AUTOPILOT = "autopilot"
# The approval digest (T-0026). The header's status value is the one thing it
# normalises, and only a value from this closed list; see `_canonical`.
STATUS_VALUES = ("spec", "planned", "approved", "in-progress", "review", "done", "merged")
DIGEST_SCHEME = "crew-approval/2"
_STATUS_PLACEHOLDER = b"<status>"
_BOM = b"\xef\xbb\xbf"
_STATUS_ALTERNATION = b"|".join(re.escape(v.encode("ascii")) for v in STATUS_VALUES)
_STATUS_RE = re.compile(rb"(?<=[ \t])status:[ \t]+(" + _STATUS_ALTERNATION + rb")(?=[ \t]|\Z)")
# Where line 1 ends: every break `str.splitlines` honours, as UTF-8 bytes, so
# `_canonical`'s line 1 is the one `sections` and `parse_touch` read. Splitting
# on `\n` alone made a bare-CR spec one long line 1 (T-0026 review round 3).
_LINE_BREAK_RE = re.compile(rb"[\n\r\x0b\x0c\x1c-\x1e]|\xc2\x85|\xe2\x80[\xa8\xa9]")
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
        done = subprocess.run([crew_common.require_tool("git"), "-C", root] + list(args), capture_output=True,
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


# --- the spec header --------------------------------------------------------------

_RISK_RE = re.compile(r"\brisk:\s*(low|med|high)(?=\s|$)", re.IGNORECASE)


def header_line(spec_text):
    """The spec's first `# ` line -- the template's `# <id> <title>
    status: spec   risk: low|med|high` (commands/spec.md) -- or ''."""
    for line in (spec_text or "").splitlines():
        if line.startswith("# "):
            return line
    return ""


def parse_risk(spec_text):
    """`{"risk", "known"}` from the header line ONLY; a `risk:` in the body
    does not count. Absent, empty or unrecognised (`risk: lo`, `risk: LOW!`)
    reads as `high` with `known` False, never `low`: the policy that will
    trust this (T-0010) must not have an unknown collapse into the permissive
    value -- root CLAUDE.md's recurring bug."""
    header = header_line(spec_text)
    found = _RISK_RE.search(header)
    if found:
        return {"risk": found.group(1).lower(), "known": True}
    return {"risk": "high", "known": False}


# --- approval --------------------------------------------------------------------

def _sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _line_one_end(data):
    """The offset of the first line break in `data`, or -1 when it has none."""
    match = _LINE_BREAK_RE.search(data)
    return -1 if match is None else match.start()


def _canonical(data):
    """`(bytes, normalised)`: `data` with the header's status VALUE replaced by
    `_STATUS_PLACEHOLDER`, or `data` untouched and False.

    Only line 1 is examined -- the bytes before the first line break, where a
    break is anything `str.splitlines` splits on (`\n`, `\r`, `\r\n`, `\x0b`,
    `\x0c`, `\x1c`-`\x1e`, U+0085, U+2028, U+2029). So it is the line the spec
    parser reads as line 1 whatever the file's line endings, mixed ones
    included. It must start with `# ` (after an optional UTF-8 BOM), hold
    exactly one `status:` counted case-insensitively, and that one must be the
    token `status:<spaces/tabs><value>` with `value` in STATUS_VALUES followed
    by a space, a tab or the end of the line. Anything else -- no token, two,
    an unknown value, a header that moved -- normalises nothing, so the edit
    that caused it stales the approval."""
    cut = _line_one_end(data)
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
    `scope.allowCliApproval` to exactly `true`. In a linked worktree with no
    config of its own that is the main checkout's file (T-0088)."""
    data, state = _read_json(crew_common.repo_config_file(top, "config.json"))
    scope = data.get("scope") if state == "ok" and isinstance(data, dict) else None
    return isinstance(scope, dict) and scope.get("allowCliApproval") is True


def _autopilot_policy(top, ticket):
    """`crew_autopilot.approval_policy`, imported lazily (it imports this
    module). Raises whatever the import or the call raises."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    return crew_autopilot.approval_policy(top, ticket)


def _autopilot_refusal(top, ticket):
    """None while an `autopilot` receipt for `ticket` still stands, else why
    not. Could not tell -- the module missing, the call raising, an answer
    that is not a dict -- is a refusal, never a yes."""
    if not cli_approval_allowed(top):
        return "scope.allowCliApproval is not exactly true"
    try:
        decision = _autopilot_policy(top, ticket)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return (f"whether autopilot.approval still allows it could not be told "
                f"({type(exc).__name__})")
    if isinstance(decision, dict) and decision.get("allow") is True:
        return None
    reason = decision.get("reason") if isinstance(decision, dict) else None
    return f"autopilot.approval no longer allows it ({reason or 'no reason given'})"


def accepted(root, ticket):
    """`status`, with an `approved` receipt that did not come from the user's
    prompt demoted to `unaccepted` unless `scope.allowCliApproval` is true --
    and an `autopilot` one unless `crew_autopilot.approval_policy` also still
    allows it. This is what the scope guard and the Stop audit act on."""
    result = status(root, ticket)
    if result["status"] != "approved":
        return result
    via = (result["receipt"] or {}).get("approved_via")
    top = toplevel(root) or os.path.abspath(root)
    if via == AUTOPILOT:
        refusal = _autopilot_refusal(top, ticket)
        if refusal is None:
            return result
        return dict(result, status="unaccepted", touch=[],
                    why=(f"its approval was recorded by autopilot, and {refusal}; the user "
                         f"types `/crew:approve {ticket}`"))
    if via == USER_PROMPT or cli_approval_allowed(top):
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


def _expected_pair(expect):
    if (not isinstance(expect, (tuple, list)) or len(expect) != 2
            or not all(isinstance(v, str) and v for v in expect)):
        raise TicketError(f"expect must be (plan_sha256, spec_sha256), not {expect!r}")
    return expect


def approve(root, ticket, by=None, via=CLI, session=None, prompt_id=None, expect=None):
    """Validate, then write the receipt. Returns `(receipt, successor)`;
    `successor` is None when the review ledger is not NEEDS_REPLAN, else
    `(allowed, reason)` from the ledger seam.

    spec.md and plan.md are read once; the bytes validated are the bytes
    hashed. `via` is `cli` (this module's CLI, tests, CI), `user-prompt`
    (`approval_hook.py`, which also passes the prompt's session and id) or
    `autopilot` (`crew_autopilot.py approve`; refused here unless
    `crew_autopilot.approval_policy` allows, whoever calls).

    `expect`, when given, is the `(plan_sha256, spec_sha256)` the user
    confirmed (T-0024's group confirm). Bytes that hash to anything else are
    refused before anything is written: the receipt is bound to the version
    the user saw, never to a later edit. A group confirm is the owner's own
    prompt, so `via=autopilot` with an `expect` is refused outright: autopilot
    approves one ticket at a time, through its policy only."""
    if via not in (CLI, USER_PROMPT, AUTOPILOT):
        raise TicketError(f"approved_via {via!r} is not {CLI}, {USER_PROMPT} or {AUTOPILOT}")
    if via == AUTOPILOT and expect is not None:
        raise TicketError(f"not approved -- {ticket}: a group confirm is owner-only; "
                          "autopilot approves one ticket at a time through its policy")
    if expect is not None:
        expect = _expected_pair(expect)
    top = toplevel(root)
    if not top:
        raise TicketError(f"{root} is not a git repository")
    if via == AUTOPILOT:
        refusal = _autopilot_refusal(top, ticket)
        if refusal is not None:
            raise TicketError(f"not approved -- an autopilot approval, and {refusal}")
    contract = read_contract(top, ticket)
    if expect is not None:
        moved = [name for name, want in (("spec.md", expect[1]), ("plan.md", expect[0]))
                 if _sha(contract[name]) != want]
        if moved:
            raise TicketError(f"{ticket}: {' and '.join(moved)} changed since the "
                              "approval was requested")
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


_INDEX_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _cell_id(cell):
    """The cell's content when it is one id-shaped token -- a letter and a
    digit, so an index column such as `1` or a word such as `done` is not --
    casefolded; else None. Backticks and bold marks around it are ignored."""
    text = cell.strip().strip("`*").strip()
    if _INDEX_TOKEN_RE.fullmatch(text) and re.search(r"[A-Za-z]", text) \
            and re.search(r"\d", text):
        return text.casefold()
    return None


def _prose_names(line, key):
    """True when prose `line` names the ticket (casefolded `key`) as a whole
    token in any case. One sentence-final `.` is read as punctuation; a
    trailing `-` never is, since `T-1-` is a different valid id."""
    return any(tok.casefold() == key or (tok.endswith(".") and tok[:-1].casefold() == key)
               for tok in _INDEX_TOKEN_RE.findall(line))


def _index_closed(top, ticket):
    """`(closed, why)` from `.work/INDEX.md`: True, False, or None ("could not
    tell", with `why`). Its own matcher, not crew_state's: that one knows only
    upper-case prefix-number keys, so a lower-case or suffixed id -- both
    valid `_TICKET_RE` ids -- read as open (review round 2). A table row's id
    cell is its first id-shaped cell (`_cell_id`), matched whole and in any
    case; its status is the next cell. A row naming the ticket as a whole
    cell that is NOT its id cell, or with no status cell, cannot be told
    (review round 3). A prose line closes it with a `crew_state._DONE_RE`
    marker, the rule `crew_autopilot._is_open` applies."""
    import crew_state  # pylint: disable=import-outside-toplevel
    path = os.path.join(top, ".work", "INDEX.md")
    text = crew_common.read_text(path)
    if text is None:
        if os.path.lexists(path):
            return None, "could not read .work/INDEX.md"
        return False, None
    key, unknown = ticket.casefold(), None
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # Two bars make a table row; one makes a row only when the first
        # cell is an id (`t-0050 |`), so a prose line with a stray bar still
        # gets the prose rule.
        table = line.count("|") >= 2 or (line.count("|") == 1 and _cell_id(cells[0]))
        if table:
            ids = [(i, _cell_id(c)) for i, c in enumerate(cells) if _cell_id(c)]
            first = ids[0] if ids else None
            if first and first[1] == key:
                status = cells[first[0] + 1].lower() if first[0] + 1 < len(cells) else ""
                if status in crew_state._TABLE_DONE_WORDS:  # pylint: disable=protected-access
                    return True, None
                if not status:
                    unknown = f"its row {line.strip()!r} has no status cell"
            elif any(cid == key for _, cid in ids):
                unknown = (f"row {line.strip()!r} names it in a cell that is not the "
                           "row's id cell")
            continue
        if _prose_names(line, key) and crew_state._DONE_RE.search(line):  # pylint: disable=protected-access
            return True, None
    if unknown:
        return None, unknown
    return False, None


def precheck(root, ticket):
    """`{"ticket", "problems", "plan_sha256", "spec_sha256"}`: whether `ticket`
    could be approved now, from ONE `read_contract`. The hashes are of the
    bytes checked, None when there is nothing to hash. Every problem is
    listed, not the first: a group approval names each one (T-0024)."""
    result = {"ticket": ticket, "problems": [], "plan_sha256": None, "spec_sha256": None}
    problems = result["problems"]
    try:
        check_ticket(ticket)
    except TicketError as exc:
        problems.append(str(exc))
        return result
    top = toplevel(root)
    if not top:
        problems.append(f"{root} is not a git repository")
        return result
    if not os.path.isdir(ticket_dir(top, ticket)):
        problems.append(f"no ticket folder .work/tickets/{ticket}/")
        return result
    contract = read_contract(top, ticket)
    result["plan_sha256"], result["spec_sha256"] = _sha(contract["plan.md"]), \
        _sha(contract["spec.md"])
    problems.extend(validate(top, ticket, contract))
    closed, why = _index_closed(top, ticket)
    if closed is None:
        problems.append(f"could not tell from .work/INDEX.md whether {ticket} is closed ({why})")
    elif closed:
        problems.append(f"{ticket} is closed in .work/INDEX.md")
    _, state = read_approval(root, ticket)
    if state == "corrupt":
        problems.append(f"the approval receipt at {approval_path(root, ticket)} is "
                        "unreadable; inspect it and remove it by hand before approving")
    return result


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
    # T-0061: the scope base is recorded at branch cut, not on the first
    # `--record` after commits exist. Imported here so the PreToolUse import
    # path stays `crew_common` alone. The pointer is already written, so a
    # failure below is reported and never stops the ticket being active.
    try:
        import scope_base  # pylint: disable=import-outside-toplevel
        sha, status = scope_base.record(top, ticket)
        return sha, status, scope_base.record_message(top, ticket, sha, status)
    except Exception as exc:  # pylint: disable=broad-except
        return None, None, (f"scope-base: could not record a start for {ticket} "
                            f"({type(exc).__name__}: {exc}); the active ticket is set\n")


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
    path = crew_common.repo_config_file(top, "config.json")
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


# --- minting (T-0019) ------------------------------------------------------------------

MINT_STATUSES = ("ready", "direction")
MINT_ATTEMPTS = 20
TITLE_MAX = 120
# A `.work/tickets/` folder that holds a `T-` number, and (below) an INDEX
# line's first `T-<n>`, the id cell of every row crew writes. [0-9], not \d,
# which is any Unicode digit. `mint` makes `T-` plus at least 4 digits.
_MINT_FOLDER_RE = re.compile(r"T-([0-9]+)\Z")
_MINT_ROW_RE = re.compile(r"(?<![A-Z0-9])T-([0-9]+)")
_MINT_KINDS = ("files", "obsidian")
_MINT_RETRY_PAUSE = 0.02
_MINT_LOCK_WAIT = 30.0


def _mint_taken(top):
    """The `T-` numbers held by `.work/tickets/T-*` folders and by the first
    `T-<n>` of every INDEX line. An INDEX or tickets folder that exists but
    cannot be read raises: could not tell is a refusal, never "nothing
    taken". An absent one holds nothing (the tracker creates INDEX).

    INDEX is read under the INDEX lock every mint's `create` and `move` hold
    (L-1510): Windows refuses to open a file another process is `os.replace`ing
    (a sharing violation), which read as unreadable and killed a concurrent
    mint. The lock is taken and released here, before the folder claim, and
    `_mint_claim` takes it again; it is never nested, and is the only lock mint
    holds. A lock held past the wait, or one that cannot be created, refuses."""
    import crew_config_files  # pylint: disable=import-outside-toplevel
    taken = set()
    tickets = os.path.join(top, ".work", "tickets")
    try:
        names = os.listdir(tickets)
    except FileNotFoundError:
        names = []
    except OSError as exc:
        raise TicketError(f".work/tickets could not be listed ({exc.strerror or exc}); "
                          "which ids are taken cannot be told") from exc
    for name in names:
        found = _MINT_FOLDER_RE.match(name)
        if found:
            taken.add(int(found.group(1)))
    index = os.path.join(top, ".work", "INDEX.md")
    try:
        with crew_config_files.Lock(index, _MINT_LOCK_WAIT):
            text = crew_common.read_text(index)
    except crew_config_files.Busy as exc:
        raise TicketError(f".work/INDEX.md could not be read under its lock ({exc}); which "
                          "ids are taken cannot be told") from exc
    except OSError as exc:
        raise TicketError(f".work/INDEX.md's lock could not be taken ({exc}); which ids are "
                          "taken cannot be told") from exc
    if text is None and os.path.lexists(index):
        raise TicketError(".work/INDEX.md exists but could not be read; which ids are "
                          "taken cannot be told")
    for line in (text or "").splitlines():
        found = _MINT_ROW_RE.search(line)
        if found:
            taken.add(int(found.group(1)))
    return taken


def _mint_gate(top):
    """Refuse unless the tracker is one whose `create` writes the row here."""
    import crew_tracker  # pylint: disable=import-outside-toplevel
    info = crew_tracker.resolve(top)
    kind = info["kind"]
    if kind not in _MINT_KINDS:
        detail = "; ".join(info.get("problems") or [])
        raise TicketError(
            f"tracker is {kind}{f' ({detail})' if detail else ''}: mint writes a ticket only "
            f"under a files or obsidian tracker, whose create writes the INDEX row; follow "
            f"brainstorm.md step 1 instead")


def _mint_title_problem(title):
    import crew_tracker  # pylint: disable=import-outside-toplevel
    if not isinstance(title, str) or not title.strip():
        return "the title is empty"
    if len(title) > TITLE_MAX:
        return f"the title is {len(title)} characters, over {TITLE_MAX}"
    if not crew_tracker.title_ok(title):
        return "the title must be one line with no '|'"
    return None


def _mint_write_direction(folder, ticket, body):
    """direction.md complete or not at all: the whole text is built first,
    written to a temp file, fsynced, then `os.replace`d. On any failure the
    temp and the direction are removed and the error re-raised."""
    text = f"# {ticket} direction\n{body}" + ("" if body.endswith("\n") else "\n")
    data = text.encode("utf-8")
    path = os.path.join(folder, "direction.md")
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        for stale in (tmp, path):
            try:
                os.remove(stale)
            except OSError:
                pass
        raise


def _mint_release(folder):
    """Take back a claimed folder: its direction.md, then the folder itself.
    Only what mint wrote; a folder someone else wrote into stays, and the
    returned text says so."""
    try:
        os.remove(os.path.join(folder, "direction.md"))
    except FileNotFoundError:
        pass
    except OSError as exc:
        return f"; {folder}/direction.md could not be removed ({exc.strerror or exc})"
    try:
        os.rmdir(folder)
    except OSError as exc:
        return f"; {folder} could not be removed ({exc.strerror or exc})"
    return ""


def _mint_lines(crew_tracker, report):
    return [crew_tracker._line(r) for r in report["results"]]  # pylint: disable=protected-access


def _mint_failures(crew_tracker, report):
    """`tracker: <line>` for each half of `report` that did not update."""
    return [f"tracker: {line}" for r, line in zip(report["results"], _mint_lines(crew_tracker, report))
            if crew_tracker._EXIT.get(r["state"], 0)]  # pylint: disable=protected-access


def _mint_row(top, ticket, title):
    """(outcome, report): `written`, `incomplete`, `taken` or `failed` for one
    `create`. The row is written when the files half reports `updated`; when a
    later half (the board, under obsidian) did not update, the mint is
    `incomplete`: the row cannot be atomically taken back, so the ticket is
    kept at `direction` and mint refuses (review round 2, :1161)."""
    import crew_tracker  # pylint: disable=import-outside-toplevel
    report = crew_tracker.create(top, ticket, title)
    results = report["results"]
    if any(r["backend"] == "files" and r["state"] == crew_tracker.UPDATED for r in results):
        return ("incomplete" if crew_tracker.exit_code(report) else "written"), report
    if any(str(r.get("reason") or "").startswith(crew_tracker.TAKEN) for r in results):
        return "taken", report
    return "failed", report


def _mint_indexed(top, ticket):
    """Whether INDEX holds a row whose first `T-` number is `ticket`'s: True,
    False, or None when INDEX cannot be read (could not tell). Asked under the
    INDEX lock, so no other mint is writing it."""
    index = os.path.join(top, ".work", "INDEX.md")
    text = crew_common.read_text(index)
    if text is None:
        return None if os.path.lexists(index) else False
    number = int(ticket[2:])
    for line in text.splitlines():
        found = _MINT_ROW_RE.search(line)
        if found and int(found.group(1)) == number:
            return True
    return False


def _mint_made_note(report):
    """Whether this `create` wrote the obsidian ticket note (its claim)."""
    import crew_tracker  # pylint: disable=import-outside-toplevel
    return any(r["backend"] == "obsidian-note" and r["state"] == crew_tracker.UPDATED
               for r in (report or {}).get("results", []))


def _mint_drop_note(top, ticket):
    """Take back the obsidian note a `create` of this mint wrote, when no row
    came of it (review round 2, :1255). Only a note that still names this
    repo's repo-id is removed; anything else stays and the text says so."""
    import crew_tracker  # pylint: disable=import-outside-toplevel
    # pylint: disable=protected-access
    info = crew_tracker.resolve(top)
    if info["kind"] != "obsidian":
        return ""
    paths, problem = crew_tracker._vault_paths(top, info["settings"], [("note", f"{ticket}.md")])
    if problem:
        return f"; its obsidian note could not be found to remove ({problem})"
    owner, detail, exists = crew_tracker._card_owner(paths, crew_tracker.repo_id(top))
    if not exists:
        return ""
    if owner != crew_tracker.OURS:
        return f"; {paths['noteShown']} kept: it is not provably this mint's ({detail})"
    try:
        os.remove(paths["note"])
    except OSError as exc:
        return f"; {paths['noteShown']} could not be removed ({exc.strerror or exc})"
    return ""


def _mint_create(top, ticket, title, folder):
    """`(outcome, report, made_note)` from `_mint_row`, retried while the
    tracker fails for a reason other than `id taken`; `made_note` says a
    `create` of this mint wrote the obsidian note. A `create` that raises
    anything unwinds: the folder is released unless INDEX already holds the
    row (or could not be read), and then it is kept and the error says so. An
    `Exception` becomes a TicketError; anything else (KeyboardInterrupt) is
    re-raised as it is, after the same unwind."""
    outcome, report, made_note = "failed", None, False
    for _ in range(MINT_ATTEMPTS):
        try:
            outcome, report = _mint_row(top, ticket, title)
            made_note = made_note or _mint_made_note(report)
        except BaseException as exc:
            indexed = _mint_indexed(top, ticket)
            if indexed is False:
                tail = (f"; nothing was minted{_mint_release(folder)}"
                        f"{_mint_drop_note(top, ticket) if made_note else ''}")
            elif indexed:
                tail = f"; {ticket} kept: its INDEX row was written before the tracker raised"
            else:
                tail = (f"; {ticket} kept: INDEX could not be read, so whether its row was "
                        "written cannot be told")
            if not isinstance(exc, Exception):
                raise
            raise TicketError(f"{ticket} claimed but the tracker raised "
                              f"{type(exc).__name__}: {exc}{tail}") from exc
        if outcome != "failed":
            break
        time.sleep(_MINT_RETRY_PAUSE)
    return outcome, report, made_note


def _mint_row_status(top, ticket):
    """The status cell of `ticket`'s INDEX row, or None when INDEX cannot be
    read or holds no such row (could not tell)."""
    text = crew_common.read_text(os.path.join(top, ".work", "INDEX.md"))
    for line in (text or "").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) > 1 and cells[0] == ticket:
            return cells[1]
    return None


def _mint_ready(top, ticket):
    """`(state, warnings)` for the `move` to `ready`. A move that fails or
    raises leaves the ticket at `direction` with a warning. When the files
    half did land (the INDEX row is `ready`) and a later half failed (the
    board), the row is put back to `direction`, so the stop mint reports is
    the one autopilot reads (review round 2, :1225); whatever happens, the
    state returned is the row's own, never one INDEX does not hold."""
    import crew_tracker  # pylint: disable=import-outside-toplevel
    try:
        report = crew_tracker.move(top, ticket, "ready")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        warnings = [f"tracker: move to ready raised {type(exc).__name__}: {exc}"]
    else:
        if crew_tracker.exit_code(report) == 0:
            return "ready", []
        warnings = _mint_failures(crew_tracker, report)
    if _mint_row_status(top, ticket) == "ready":
        try:
            back = crew_tracker.move(top, ticket, "direction", reopen=True)
            warnings += [f"{w} (moving back to direction)"
                         for w in _mint_failures(crew_tracker, back)]
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            warnings.append(f"tracker: move back to direction raised {type(exc).__name__}: {exc}")
        if _mint_row_status(top, ticket) == "direction":
            warnings.append(f"{ticket} put back to direction in INDEX after the failed move")
    state = _mint_row_status(top, ticket)
    if state is None:
        raise TicketError(f"{ticket} kept, but its INDEX status cannot be told after a failed "
                          f"move to ready: {'; '.join(warnings)}")
    return state, warnings


def _mint_claim(top, ticket, title, folder, direction, status):
    """`(outcome, warnings, state)` for a folder already claimed: the
    direction, then the tracker row, then (for `ready`) the move. Both tracker
    calls run under one lock beside INDEX, serialising mints: the tracker's
    replace re-reads before it writes, but a write landing between that
    re-read and the replace is lost, and `create` and `move` both rewrite
    INDEX, so no mint calls either while another holds the lock."""
    import crew_config_files  # pylint: disable=import-outside-toplevel
    import crew_tracker  # pylint: disable=import-outside-toplevel
    if direction is not None:
        try:
            _mint_write_direction(folder, ticket, direction)
        except BaseException:
            _mint_release(folder)
            raise
    state, moved, entered = "direction", [], False
    try:
        with crew_config_files.Lock(os.path.join(top, ".work", "INDEX.md"), _MINT_LOCK_WAIT):
            entered = True
            outcome, report, made_note = _mint_create(top, ticket, title, folder)
            if outcome == "written" and status == "ready":
                state, moved = _mint_ready(top, ticket)
    except crew_config_files.Busy as exc:
        raise TicketError(f"{ticket} claimed but not minted: {exc}"
                          f"{_mint_release(folder)}") from exc
    except BaseException as exc:
        # Any other failure taking the lock (an OSError creating the lock
        # file, review round 2, :1245) reached no tracker: the folder and
        # direction go. One raised inside it was already unwound there.
        if entered:
            raise
        tail = _mint_release(folder)
        if not isinstance(exc, Exception):
            raise
        raise TicketError(f"{ticket} claimed but not minted: {exc}{tail}") from exc
    lines = _mint_lines(crew_tracker, report)
    if outcome in ("taken", "failed") and made_note:
        dropped = _mint_drop_note(top, ticket)
        lines = lines + ([dropped[2:]] if dropped else [])
    if outcome == "taken":
        return "taken", lines, state
    if outcome == "failed":
        raise TicketError(f"{ticket} claimed but its tracker row was not written: "
                          f"{'; '.join(lines)}{_mint_release(folder)}")
    if outcome == "incomplete":
        raise TicketError(f"{ticket} kept at direction, not minted complete: its INDEX row is "
                          f"written but {'; '.join(_mint_failures(crew_tracker, report))}; "
                          "nothing was moved to ready")
    return "written", _mint_failures(crew_tracker, report) + moved, state


def mint(root, title, status="ready", direction=None):
    """Create one ticket: `{"ticket", "folder", "status", "warnings"}`.

    The id is one past the highest `T-` number over `.work/tickets/` folders
    and INDEX rows, claimed by an exclusive `os.mkdir` (a folder that exists
    is skipped). `direction`, a body, is written to direction.md under a
    `# <id> direction` header before the tracker is asked; then
    `crew_tracker.create` writes the INDEX row (and, under obsidian, the note
    and card) and, for `ready`, `crew_tracker.move` moves it there, both under
    the INDEX lock. A tracker `id taken` releases the folder (and the note
    this mint wrote) and takes the next id; a direction write that raises, a
    lock that cannot be taken, or a `create` that keeps failing or raises
    before its row is in INDEX, releases the folder (and that note) and
    raises. A `create` whose row lands but whose card does not keeps the
    ticket at `direction` and raises, saying so. A move that fails or raises
    leaves the ticket at `direction`, with a warning: a row the move did set
    to `ready` is put back, and `status` is always what the INDEX row holds.
    Refused before anything is claimed: a bad title or status, an unreadable
    INDEX, a tracker whose create does not write the row here."""
    if status not in MINT_STATUSES:
        raise TicketError(f"status {status!r} is not one of {'|'.join(MINT_STATUSES)}")
    problem = _mint_title_problem(title)
    if problem:
        raise TicketError(problem)
    if direction is not None and not isinstance(direction, str):
        raise TicketError("the direction must be text")
    top = os.path.realpath(toplevel(root) or os.path.abspath(root))
    _mint_gate(top)
    tickets = os.path.join(top, ".work", "tickets")
    os.makedirs(tickets, exist_ok=True)
    number = 0
    for _ in range(MINT_ATTEMPTS):
        number = max(_mint_taken(top) | {number}) + 1
        ticket = f"T-{number:04d}"
        folder = os.path.join(tickets, ticket)
        try:
            os.mkdir(folder)
        except FileExistsError:
            continue
        outcome, warnings, state = _mint_claim(top, ticket, title, folder, direction, status)
        if outcome == "taken":
            _mint_release(folder)
            continue
        return {"ticket": ticket, "folder": folder, "status": state, "warnings": warnings}
    raise TicketError(f"no free ticket id after {MINT_ATTEMPTS} attempts (last tried "
                      f"T-{number:04d}); nothing was minted")


def _read_regular(path):
    """A staged file's text (utf-8-sig, universal newlines), or TicketError
    when it is not a regular file. Opened non-blocking and checked on the open
    descriptor, so a FIFO with no writer is refused at once instead of
    hanging the open (review round 2, :1377)."""
    nonblock = getattr(os, "O_NONBLOCK", 0)
    flags = os.O_RDONLY | nonblock | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise TicketError(f"{path} is not a regular file")
        # Only undo what was done: Windows has no O_NONBLOCK, and its
        # os.set_blocking works on pipes only (WinError 87 on a file).
        if nonblock:
            os.set_blocking(fd, True)
        handle = os.fdopen(fd, encoding="utf-8-sig")
    except BaseException:
        os.close(fd)
        raise
    with handle:
        return handle.read()


# --- /crew:autopilot assign (T-0019) ---------------------------------------------------

# Provenance only: nothing that grants or refuses an approval reads it (the
# owner's 2026-09-26 "Follow the policy"; test_origin_line_changes_no_policy).
ORIGIN_ASSIGN = "origin: /crew:autopilot assign"
STAGING = ".work/autopilot"
ASSIGN_SECTIONS = ("ask", "options", "recommendation", "open questions")
RISKS = ("low", "med", "high")
_FIELD_RE = re.compile(r"^(title|risk):[ \t]*(.*?)\s*$")


def check_direction(text):
    """`(fields, problems)` for a staging file. `fields` holds `title` and
    `risk` (lower-cased), each the first `title:` / `risk:` line before the
    first `## ` heading -- never a line inside `## Ask`, which is the owner's
    text verbatim; a leading BOM is not part of the first line. `problems`
    names a missing or empty title and each of the four sections that is
    absent or empty."""
    fields, problems = {"title": None, "risk": None}, []
    text = (text or "").removeprefix("\ufeff")
    for line in text.splitlines():
        if _HEADING_RE.match(line):
            break
        found = _FIELD_RE.match(line)
        if found and fields[found.group(1)] is None:
            fields[found.group(1)] = found.group(2)
    if fields["risk"] is not None:
        fields["risk"] = fields["risk"].lower()
    if not fields["title"]:
        problems.append("no title: line (or an empty one) before the first ## heading")
    found = sections(text)
    for name in ASSIGN_SECTIONS:
        if name not in found:
            problems.append(f"no ## {name} section")
        elif not found[name]:
            problems.append(f"## {name} is empty")
    return fields, problems


def _assign_armed(top):
    """Whether autopilot is armed, imported lazily (crew_autopilot imports
    this module). Could not tell is a refusal naming the cause."""
    try:
        import crew_autopilot  # pylint: disable=import-outside-toplevel
        got = crew_autopilot.settings(top)
    except Exception as exc:  # pylint: disable=broad-except
        raise TicketError(f"whether autopilot is armed could not be told "
                          f"({type(exc).__name__}: {exc}); nothing was minted") from exc
    return isinstance(got, dict) and got.get("armed") is True


def assign(root, direction_file):
    """`/crew:autopilot assign`'s one write: `{"ticket", "folder", "status",
    "risk", "warnings"}`. Refused, with nothing minted, when the file is not
    under `<top>/.work/autopilot/` (resolved, symlinks followed), autopilot is
    not armed, or `check_direction` finds a problem. Then `mint` exactly once,
    `ready`, with the origin line, `title:`, `risk:` and the file's sections
    as the direction. Writes no receipt: approval is `autopilot.approval`'s,
    through `crew_autopilot.py approve`, like any other ticket's."""
    top = os.path.realpath(toplevel(root) or os.path.abspath(root))
    staging = os.path.join(top, *STAGING.split("/"))
    os.makedirs(staging, exist_ok=True)
    staging = os.path.realpath(staging)
    path = direction_file if os.path.isabs(direction_file) else os.path.join(root, direction_file)
    real = os.path.realpath(path)
    if not real.startswith(staging + os.sep):
        raise TicketError(f"{direction_file} is not under {STAGING}/ (it resolves to {real}); "
                          "nothing was minted")
    if not _assign_armed(top):
        raise TicketError("autopilot is not armed (autopilot.mode is not plan in "
                          ".crew/config.json); nothing was minted")
    try:
        text = _read_regular(real)
    except TicketError as exc:
        raise TicketError(f"{direction_file}: {exc}; nothing was minted") from exc
    except (OSError, ValueError) as exc:
        raise TicketError(f"{direction_file} could not be read ({type(exc).__name__}: "
                          f"{exc}); nothing was minted") from exc
    fields, problems = check_direction(text)
    if problems:
        raise TicketError(f"{direction_file}: " + "; ".join(problems) + "; nothing was minted")
    warnings, risk = [], fields["risk"]
    if risk not in RISKS:
        warnings.append(f"risk: {risk!r} is not {'|'.join(RISKS)}; written as high")
        risk = "high"
    start = next(i for i, line in enumerate(text.splitlines(keepends=True))
                 if _HEADING_RE.match(line.rstrip("\r\n")) and not line.startswith("###"))
    rest = "".join(text.splitlines(keepends=True)[start:])
    body = f"{ORIGIN_ASSIGN}\ntitle: {fields['title']}\nrisk: {risk}\n\n{rest}"
    got = mint(top, fields["title"], status="ready", direction=body)
    return dict(got, risk=risk, warnings=warnings + got["warnings"])


# --- CLI ------------------------------------------------------------------------------

def _mint_main(parser, args, root):
    """`mint` and `assign`: `ticket=<id>` (assign adds ` risk=<r>`) and each
    `warning:`, exit 0; `refused: <why>`, exit 1. The scope guard refuses a
    shell command naming `crew_ticket` with the word "approve", so a caller
    holding free text (assign, T-0012's goal) passes it in a file, never as
    an argument: assign has no --title, and reads title and risk from the file."""
    try:
        if args.action == "assign":
            if not args.direction_file:
                parser.error("assign needs --direction-file <staging file>")
            # Mint-only options are refused, never ignored (review round 2,
            # :1439): the title is the staging file's, the status `ready`.
            for flag, value in (("--title", args.title), ("--status", args.mint_status)):
                if value is not None:
                    raise TicketError(f"assign takes no {flag}: the staging file sets the "
                                      "title, and assign mints ready; nothing was minted")
            got = assign(root, args.direction_file)
            print(f"ticket={got['ticket']} risk={got['risk']}")
        else:
            if args.title is None:
                parser.error("mint needs --title <title>")
            body = None
            if args.direction_file:
                try:
                    body = _read_regular(args.direction_file)
                except (OSError, ValueError) as exc:
                    raise TicketError(f"{args.direction_file} could not be read "
                                      f"({type(exc).__name__}: {exc})") from exc
            got = mint(root, args.title, status=args.mint_status or "ready", direction=body)
            print(f"ticket={got['ticket']}")
    except (TicketError, OSError) as exc:
        print(f"refused: {exc}")
        return 1
    for warning in got["warnings"]:
        print(f"warning: {warning}")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("validate", "approve", "status", "activate",
                                           "deactivate", "active", "touch", "mint", "assign"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--by", help="who is approving (default: git user.name)")
    parser.add_argument("--title", help="mint: the new ticket's title")
    parser.add_argument("--status", dest="mint_status", default=None,
                        help=f"mint: the new row's status, {'|'.join(MINT_STATUSES)} (mint "
                             "refuses any other, exit 1)")
    parser.add_argument("--direction-file",
                        help="mint: a direction body to write; assign: the staging file")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.action in ("mint", "assign"):
        return _mint_main(parser, args, root)
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
            sys.stderr.write(activate(root, args.ticket)[2])
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
