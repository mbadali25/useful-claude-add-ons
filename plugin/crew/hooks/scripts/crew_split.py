#!/usr/bin/env python3
"""crew_split.py -- the one split rulebook (T-0052), behind /crew:split.

`/crew:split` calls it in every tracker mode, and T-0058's `/crew:autopilot
split` calls the same functions: there is one set of rules, so autopilot
gets none of its own that could drift from the command's.

The API (stable; T-0058 and T-0059 build on it):

    measure(top, ticket)            -> {plan_steps, acceptance, touch,
                                        subsystems, findings_rate,
                                        tickets_too_large}; None = unreadable
    triggers(measures, stage)       -> fired names for stage "spec"|"plan";
                                        a None measure is "unknown:<name>"
    absent_sources(top)             -> {trigger: why} for a source the repo
                                        does not have (T-0058's "unmeasured")
    parent_criteria(spec_text)      -> the Acceptance bullets, or None
    parse_proposal(text)            -> the split.md fields (no judgement)
    minted_tail(text)               -> (body, {n: id}) for a valid trailing
                                        ## Minted block, else (text, None)
    check_proposal(criteria, text)  -> (decision, problems)
    tracker_mode(top)               -> files|obsidian|jira|sdp|unknown
    check(top, ticket, ...)         -> (decision, problems); records the pass
    confirm(top, ticket, session)   -> {"ok", "reason"}
    apply(top, ticket, via, ...)    -> {"children", "parent", "warnings"}
    ticket_split_policy(top, ticket) -> {allow, policy, risk, known, reason,
                                        warnings} (T-0058, autopilot's yes)

A trigger means LOOK, never SPLIT: a split also needs `separable-criteria`
evidence, and "not too big" is a result, not a failure. `split.md` format:

    # <id> split          decision: split|slices|not-too-big
    answered: <comma-separated trigger names>
    ## Evidence
    - <evidence-key>: <measure or reason>
    ## Children                    (split only)
    ### Child 1: <title>
    risk: low|med|high
    subsystem: <codemap subsystem>
    Criteria:
    - <a parent acceptance criterion, verbatim>
    Excludes:
    - <what this child does not do>
    ## Stays on parent             (split only; `- none` when nothing stays)
    - <a parent acceptance criterion, verbatim>
    ## Minted                      (apply only: the LAST section, nothing
    - Child 1: T-0061               but `- Child N: <id>` lines)

A `## Minted` heading anywhere else, or holding anything else, is refused,
and the proposal hash covers every byte but a valid trailing block. An entry
is trusted only when an apply record exists (`split-apply.json`, written
before the first mint), the ticket has an INDEX row, and its direction.md is
exactly what apply writes for the CURRENT proposal's child (provenance lines
`origin: split of <parent>`, `split-child: <n>`, then the criteria and
exclusions); a child minted whose id never reached split.md is adopted on the
same terms, never minted twice. A minted child an edited proposal no longer
matches stops apply, naming it, with nothing written.

`confirm` is the code half of `/crew:split`'s confirmation: `check`, when it
passes, records the proposal's sha256 and the session's current human-turn id
(the `turn.id` crew_context.py's UserPromptSubmit hook writes) with a hash of
the prompt that set it (`lastPrompt`); `confirm` passes only once a different
turn id is readable for the same session, the proposal is unchanged, and the
prompt that moved it is readable, not a harness envelope (a task
notification, wake or webhook: anything opening with `<`) and not the prompt
check ran under (a loop). Could not tell is a refusal, never a yes. A
successful apply spends the check; a failed one drops it.

Accepted limits (owner decision 2026-10-04): the gate is NOT owner-proof
against the session itself. A session can schedule its own plain-text "yes"
(send_later, a routine) and that prompt passes the gate, because a scheduled
prompt delivered as plain text reads as typed. The session is also found
through `CLAUDE_CODE_SESSION_ID`, an environment variable any process can
set. The gate stops a session answering its own question in the same turn
or from a harness envelope, not a session or process that sets out to forge
the answer; the prose confirmation is what reads it. Follow-up: route split
approval through the /crew:approve harness path (TODO.md).

`apply --via autopilot` (T-0058) needs no human turn: its yes is
`ticket_split_policy`, T-0012's split rule (`crew_autopilot_goal._split_rule`)
on the parent's spec risk, asked at apply time and never read from a record.
It refuses in jira mode whatever `autopilot.approval` says -- autopilot never
creates a Jira issue; the owner runs /crew:split <KEY> -- and in sdp mode.
Any caller may pass `--via autopilot`: like `crew_ticket.approve` ("whoever
calls"), the gate is the repository's policy, not who the caller is. Out of
the box it refuses (`scope.allowCliApproval` defaults to false, autopilot to
off), and the owner opts in per repository; the policy, not the `via`
string, is what a split under `--via autopilot` answers to.

CLI (exit 0 ok, 1 refused):
    crew_split.py [measure] --root . --ticket <id> [--stage spec|plan]
    crew_split.py check --root . --ticket <id> [--proposal <f>] [--criteria-file <f>]
    crew_split.py confirm --root . --ticket <id-or-KEY>
    crew_split.py apply --root . --ticket <id> --via command|autopilot
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crew_common  # noqa: E402  pylint: disable=wrong-import-position
import crew_context  # noqa: E402  pylint: disable=wrong-import-position
import crew_state  # noqa: E402  pylint: disable=wrong-import-position
import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position
import crew_tracker  # noqa: E402  pylint: disable=wrong-import-position

# --- thresholds: each triggers a look, never a split -----------------------------------
#
# Measured 2026-09-26 on 19 review ledgers with a spec and plan (T-0052 spec,
# Evidence). Caveats: one author and mostly one reviewer family, specs read as
# amended, and the budget changed mid-history. Re-measure when 10 more ledgers
# exist and record the result here.

# T-0005 (10 steps: 8 rounds, 44 findings) and T-0030 (9 steps: 6 rounds, 33
# findings) are the only tickets past 4 rounds or 30 findings; no ticket with
# 8 steps or fewer passed 4 rounds or 26 findings. r = 0.73 with findings.
PLAN_STEPS_LOOK = 9
# T-0004's pre-split spec (the one real split) had 12 checks and T-0030 had
# 13. It misses T-0005 (10), which the step count catches. Known cost:
# T-0052's own pre-split (14), T-0051, T-0012 and T-0019 are each asked.
ACCEPTANCE_LOOK = 12
# Kept from /crew:split's table (split.md, "more than one subsystem") so both
# callers use one rule. It did not detect T-0004 (a single subsystem).
SUBSYSTEMS_LOOK = 2
# /crew:split's rule since before T-0052: fewer than two is not a split, more
# than five is an epic wearing a story's label (split.md, step 3).
CHILDREN_MIN, CHILDREN_MAX = 2, 5

EVIDENCE_KEYS = ("plan-steps", "acceptance-count", "subsystems", "findings-rate",
                 "tickets-too-large", "separable-criteria")
DECISIONS = ("split", "slices", "not-too-big")
STAGES = ("spec", "plan")
RISKS = ("low", "med", "high")
MEASURES = ("plan_steps", "acceptance", "touch", "subsystems", "findings_rate",
            "tickets_too_large")
# Who may call apply: /crew:split (a human turn) or autopilot (T-0058, the policy).
VIAS = ("command", "autopilot")
SDP_STOP = "SDP is a service desk, not where this work gets decomposed"
JIRA_STOP = ("autopilot never creates a Jira issue, whatever autopilot.approval says: "
             "the owner runs /crew:split <KEY>")
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
UNKNOWN = "unknown"
SUPERSEDED = "superseded"
PROPOSAL = "split.md"
PRE_SPLIT = "spec.pre-split.md"

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$")
_CHILD_RE = re.compile(r"^###\s+Child\s+(\d+)\s*:?\s*(.*?)\s*$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
_CHECKBOX_RE = re.compile(r"^\[[ xX]\]\s+")
_DECISION_RE = re.compile(r"\bdecision:\s*(\S+)")
_FIELD_RE = re.compile(r"^(risk|subsystem):[ \t]*(.*?)\s*$", re.IGNORECASE)
_LABEL_RE = re.compile(r"^(criteria|excludes):\s*$", re.IGNORECASE)
_STEP_RE = re.compile(r"^###\s+Step\b")
_STATUS_RE = re.compile(r"(?<![\w-])status:[ \t]*\S+")
_MINTED_RE = re.compile(r"^-[ \t]+Child[ \t]+(\d+):[ \t]*(\S+)[ \t]*$")
_MINTED_HEAD_RE = re.compile(r"(?m)^##[ \t]+Minted\b.*$")
MINTED_RULE = ("a ## Minted section is written by apply only: the last section, holding "
               "only `- Child N: <id>` lines")


class SplitError(Exception):
    """A refusal; the message names why and what was (not) written."""


# --- small helpers ---------------------------------------------------------------------

def _norm(text):
    """Whitespace collapse only: the one difference "verbatim" forgives."""
    return " ".join(text.split())


def _same(criterion, placed):
    return _norm(criterion) == _norm(placed)


def _bullet(line):
    found = _BULLET_RE.match(line)
    return _CHECKBOX_RE.sub("", found.group(1)) if found else None


def _read(path):
    """Text (utf-8, BOM dropped) or None when absent or unreadable."""
    return crew_common.read_text(path)


def _atomic_write(path, data):
    """Bytes complete or not at all: built first, temp file, then os.replace."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "xb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _top(root):
    return os.path.realpath(crew_ticket.toplevel(root) or os.path.abspath(root))


def _folder(top, ticket):
    try:
        return crew_ticket.ticket_dir(top, ticket)
    except crew_ticket.TicketError as exc:
        raise SplitError(str(exc)) from exc


# --- measures and triggers -------------------------------------------------------------

def parent_criteria(spec_text):
    """The `## Acceptance checks` bullets' text, checkbox dropped, or None
    when the spec is unreadable or has no such section."""
    if spec_text is None:
        return None
    body = crew_ticket.sections(spec_text).get("acceptance checks")
    if body is None:
        return None
    return [b for b in (_bullet(line) for line in body.splitlines()) if b]


def _acceptance(spec_text):
    body = crew_ticket.sections(spec_text).get("acceptance checks")
    if body is None:
        return None
    count = sum(1 for line in body.splitlines() if re.match(r"^\s*[-*+]\s+\[[ xX]\]", line))
    return count or None  # a section with no checkbox bullet is unread, not "0 checks"


def _subsystems(top, entries):
    """Distinct codemap subsystems whose paths cover a Touch entry (the
    longest match per entry), or None when there is no codemap to read or
    any entry is covered by none: an unplaced entry may be another
    subsystem, so the count would read low."""
    if not os.path.isdir(os.path.join(top, ".crew", "codemap")):
        return None
    subs = crew_context.subsystems(top)
    if not subs:
        return None
    named = set()
    for entry in entries:
        literal = re.split(r"[*?\[]", entry, maxsplit=1)[0]
        hits = crew_context.subsystems_for_path(subs, literal)
        if not hits:
            return None
        named.add(hits[0]["name"])
    return len(named) or None


def measure(top, ticket):
    """`{plan_steps, acceptance, touch, subsystems, findings_rate,
    tickets_too_large}`. Each is None when its source is missing or
    unreadable -- never 0, which would read as "small"."""
    top = _top(top)
    folder = _folder(top, ticket)
    spec = _read(os.path.join(folder, "spec.md"))
    plan = _read(os.path.join(folder, "plan.md"))
    got = dict.fromkeys(MEASURES)
    if spec is not None:
        got["acceptance"] = _acceptance(spec)
        if "touch" in crew_ticket.sections(spec):
            entries, _ = crew_ticket.parse_touch(spec)
            if entries:
                got["touch"] = len(entries)
                got["subsystems"] = _subsystems(top, entries)
    if plan is not None:
        # A plan with no `### Step` heading is one this cannot read, not a
        # plan of zero steps.
        got["plan_steps"] = sum(1 for line in plan.splitlines() if _STEP_RE.match(line)) or None
    rate = crew_state.read_metrics(top).get("rate")
    if rate is not None:
        got["findings_rate"] = rate
        got["tickets_too_large"] = rate > crew_state.HEALTHY_HIGH
    return got


def absent_sources(top):
    """`{trigger name: why}` for each repo-level measure whose source this
    repository does not have at all: no `.crew/codemap/` (`subsystems`), or
    no review recorded -- `.crew/metrics.md` absent, or readable with no row
    (`findings-rate`, `tickets-too-large`). measure() reports these None like
    an unreadable source; T-0058's autopilot gate names them `unmeasured`
    and does not stop on them. A source that IS there and cannot be read is
    not listed: that one stays unknown."""
    top = _top(top)
    absent = {}
    if not os.path.lexists(os.path.join(top, ".crew", "codemap")):
        absent["subsystems"] = "no .crew/codemap/ in this repository"
    path = os.path.join(top, ".crew", "metrics.md")
    why = None
    if not os.path.lexists(path):
        why = "no .crew/metrics.md (no review recorded)"
    elif os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                handle.read()
        except OSError:
            why = None
        else:
            if crew_state.read_metrics(top).get("tickets") == 0:
                why = "no review recorded in .crew/metrics.md yet"
    if why:
        absent["findings-rate"] = absent["tickets-too-large"] = why
    return absent


def triggers(measures, stage):
    """The fired trigger names, in a fixed order. A None input is reported as
    `unknown:<name>`, never skipped: could not tell is not "not fired"."""
    if stage not in STAGES:
        raise SplitError(f"stage {stage!r} is not one of {'|'.join(STAGES)}")
    rules = [("acceptance-count", "acceptance", lambda v: v >= ACCEPTANCE_LOOK),
             ("subsystems", "subsystems", lambda v: v >= SUBSYSTEMS_LOOK),
             ("findings-rate", "findings_rate", lambda v: v > crew_state.HEALTHY_HIGH),
             ("tickets-too-large", "tickets_too_large", bool)]
    if stage == "plan":
        rules.append(("plan-steps", "plan_steps", lambda v: v >= PLAN_STEPS_LOOK))
    fired = []
    for name, key, rule in rules:
        value = measures.get(key)
        if value is None:
            fired.append(f"unknown:{name}")
        elif rule(value):
            fired.append(name)
    return fired


# --- the proposal ----------------------------------------------------------------------

def _blocks(text):
    """`{heading: [lines]}` for each `## ` section, heading case-folded."""
    found, current = {}, None
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match and not line.startswith("###"):
            current = match.group(1).strip().casefold()
            found[current] = []
        elif current is not None:
            found[current].append(line)
    return found


def _children(lines):
    children, child, label = [], None, None
    for line in lines:
        head = _CHILD_RE.match(line)
        if head:
            child = {"number": int(head.group(1)), "title": head.group(2), "risk": None,
                     "subsystem": None, "criteria": [], "excludes": []}
            children.append(child)
            label = None
            continue
        if child is None:
            continue
        field = _FIELD_RE.match(line)
        if field:
            child[field.group(1).lower()] = field.group(2)
            continue
        found = _LABEL_RE.match(line.strip())
        if found:
            label = found.group(1).lower()
            continue
        item = _bullet(line)
        if item and label:
            child[label].append(item)
    return children


def minted_tail(text):
    """`(body, {number: id})` when the text ends in one `## Minted` section
    holding only `- Child N: <id>` lines (and blank lines), else `(text,
    None)` -- also None when there is no such section, or a `## Minted`
    heading sits anywhere but last. `body` is the text before it."""
    heads = list(_MINTED_HEAD_RE.finditer(text))
    if len(heads) != 1:
        return text, None
    head = heads[0]
    if not re.fullmatch(r"##[ \t]+Minted[ \t\r]*", head.group(0)):
        return text, None
    entries = {}
    for line in text[head.end():].splitlines():
        if not line.strip():
            continue
        hit = _MINTED_RE.match(line.rstrip("\r"))
        if not hit or int(hit.group(1)) in entries:
            return text, None
        entries[int(hit.group(1))] = hit.group(2)
    return text[:head.start()], entries


def parse_proposal(text):
    """The fields of a `split.md`, with no judgement: `{decision, answered,
    evidence: [(key, value)], children: [...] | None, stays: [...] | None,
    minted: {number: id}, minted_ok}`: `minted` only from a valid trailing
    block (`minted_tail`); `minted_ok` is False when a `## Minted` heading
    is anywhere else or holds anything else. `children`/`stays` are None when the section is
    absent; `- none` alone under `## Stays on parent` is an empty list."""
    text = (text or "").removeprefix("﻿")
    first = next((line for line in text.splitlines() if line.startswith("# ")), "")
    found = _DECISION_RE.search(first)
    answered = next((line.split(":", 1)[1] for line in text.splitlines()
                     if line.startswith("answered:")), "")
    blocks = _blocks(text)
    evidence = []
    for line in blocks.get("evidence", []):
        item = _bullet(line)
        if item:
            key, _, value = item.partition(":")
            evidence.append((key.strip(), value.strip()))
    stays = None
    if "stays on parent" in blocks:
        stays = [b for b in (_bullet(line) for line in blocks["stays on parent"]) if b]
        if [s.casefold() for s in stays] == ["none"]:
            stays = []
    _, minted = minted_tail(text)
    minted_ok = minted is not None or not _MINTED_HEAD_RE.search(text)
    return {"decision": found.group(1) if found else None,
            "answered": [a.strip() for a in answered.split(",") if a.strip()],
            "evidence": evidence,
            "children": _children(blocks["children"]) if "children" in blocks else None,
            "stays": stays, "minted": minted or {}, "minted_ok": minted_ok}


def _child_problems(child):
    name = f"child {child['number']}"
    label = f"{name} ({child['title']})" if child["title"] else name
    problems = []
    if not child["title"]:
        problems.append(f"{name} has no title")
    risk = (child["risk"] or "").lower()
    if risk not in RISKS:
        problems.append(f"{label} has no risk: {'|'.join(RISKS)} (got {child['risk']!r})")
    if not child["subsystem"]:
        problems.append(f"{label} names no subsystem")
    if not child["criteria"]:
        problems.append(f"{label} takes no criterion (a Criteria: bullet)")
    if not child["excludes"]:
        problems.append(f"{label} states no exclusion (an Excludes: bullet)")
    return problems


def _placement_problems(criteria, placed):
    problems = []
    for criterion in criteria:
        count = sum(1 for item in placed if _same(criterion, item))
        if count == 0:
            problems.append(f"criterion not placed in any child or on the parent: {criterion}")
        elif count > 1:
            problems.append(f"criterion placed {count} times (exactly once is the rule): "
                            f"{criterion}")
    for item in placed:
        if not any(_same(criterion, item) for criterion in criteria):
            problems.append(f"placed text is not a parent criterion: {item}")
    return problems


def check_proposal(parent_criteria_list, text):
    """`(decision, problems)`; an empty `problems` is a pass. The rules are
    /crew:split's: a known decision, evidence naming known keys, and for a
    split 2-5 children with title, risk, subsystem, criteria and exclusions,
    every parent criterion placed verbatim (whitespace aside) exactly once
    across the children and `## Stays on parent`, nothing placed that the
    parent lacks, and a `separable-criteria` evidence line."""
    got = parse_proposal(text)
    decision, problems = got["decision"], []
    if decision not in DECISIONS:
        problems.append(f"decision: {decision!r} is not one of {', '.join(DECISIONS)} "
                        "(on the # header line)")
        decision = None
    if parent_criteria_list is None:
        problems.append("the parent's acceptance criteria could not be read; nothing can be "
                        "checked as placed")
    keys = [key for key, _ in got["evidence"]]
    for key in keys:
        if key not in EVIDENCE_KEYS:
            problems.append(f"evidence key {key!r} is not one of {', '.join(EVIDENCE_KEYS)}")
    if not any(key in EVIDENCE_KEYS for key in keys):
        problems.append(f"## Evidence names no known evidence key ({', '.join(EVIDENCE_KEYS)})")
    if not got["minted_ok"]:
        problems.append(MINTED_RULE)
    if decision in ("not-too-big", "slices") and got["children"] is not None:
        problems.append(f"decision {decision} takes no ## Children section")
    if decision != "split":
        return decision, problems
    children = got["children"] or []
    if not CHILDREN_MIN <= len(children) <= CHILDREN_MAX:
        noun = "child" if len(children) == 1 else "children"
        problems.append(f"{len(children)} {noun}: a split has {CHILDREN_MIN}-{CHILDREN_MAX}")
    for child in children:
        problems += _child_problems(child)
    if got["stays"] is None:
        problems.append("no ## Stays on parent section (write `- none` when nothing stays)")
    if parent_criteria_list is not None:
        placed = [c for child in children for c in child["criteria"]] + (got["stays"] or [])
        problems += _placement_problems(parent_criteria_list, placed)
    if "separable-criteria" not in keys:
        problems.append("a split needs a separable-criteria evidence line: criteria that "
                        "cannot be verified together")
    return decision, problems


# --- tracker, records and the confirm gate ---------------------------------------------

def tracker_mode(top):
    """`files`, `obsidian`, `jira`, `sdp`, or `unknown` when the config
    cannot be read or its two files disagree. None configured is `files`,
    the config default (crew_config.py)."""
    info = crew_tracker.resolve(_top(top))
    if info["kind"] == crew_tracker.COULD_NOT_TELL:
        return UNKNOWN
    if info["kind"] == crew_tracker.NOT_CONFIGURED:
        return "files"
    return info["kind"]


def check_record_path(top, ticket):
    state = crew_ticket.state_dir(_top(top))
    if not state:
        raise SplitError(f"{top} is not a git repository; there is nowhere to keep the "
                         "split check record")
    try:
        crew_ticket.check_ticket(ticket)
    except crew_ticket.TicketError as exc:
        raise SplitError(str(exc)) from exc
    return os.path.join(state, "tickets", ticket, "split-check.json")


def _proposal_path(top, ticket, proposal=None):
    if proposal:
        return os.path.abspath(proposal)
    return os.path.join(_folder(_top(top), ticket), PROPOSAL)


def _proposal_sha(data):
    """sha256 over the proposal less a valid trailing `## Minted` block
    (`minted_tail`), which apply appends to as children return; trailing
    whitespace dropped. Every other byte is hashed, a `## Minted` heading
    anywhere else included."""
    text = data.decode("latin-1")  # lossless: every byte maps to one char
    body, entries = minted_tail(text)
    kept = body if entries is not None else text
    return hashlib.sha256(kept.encode("latin-1").rstrip()).hexdigest()


def apply_record_path(top, ticket):
    """`<git-common-dir>/crew/tickets/<id>/split-apply.json`: written by
    apply before its first mint, so a `## Minted` section with no such
    record was not written by apply."""
    return os.path.join(os.path.dirname(check_record_path(top, ticket)), "split-apply.json")


def _session_record(top, session):
    """`(data, None)` or `(None, why)`: the context hook's per-session state."""
    session = session if session is not None else os.environ.get(SESSION_ENV)
    if not session:
        return None, (f"no session id ({SESSION_ENV} is unset), so no turn record can be "
                      "tied to this session")
    path = crew_context._session_file(_top(top), session)  # pylint: disable=protected-access
    if not os.path.lexists(path):
        return None, (f"no turn record for session {session} (the UserPromptSubmit context "
                      "hook writes one; is crew's context hook on?)")
    text = _read(path)
    try:
        data = json.loads(text) if text is not None else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return None, f"the turn record for session {session} could not be read"
    return data, None


def current_turn(top, session=None):
    """`(turn_id, None)` or `(None, why)`: the hook-written human-turn id for
    this session. Absent, unreadable, empty or unattributable is a why."""
    data, why = _session_record(top, session)
    if why:
        return None, why
    turn = data.get("turn")
    ident = turn.get("id") if isinstance(turn, dict) else None
    if not isinstance(ident, str):
        return None, "the turn record for this session could not be read"
    if not ident:
        return None, "the turn record for this session holds no turn id"
    return ident, None


def current_prompt(top, session=None):
    """`(prompt, None)` or `(None, why)`: the first 500 characters of the
    prompt that last moved the turn id (crew_context's `lastPrompt`)."""
    data, why = _session_record(top, session)
    if why:
        return None, why
    prompt = data.get("lastPrompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None, ("the turn record holds no prompt, so whether a human typed the one "
                      "that moved the turn cannot tell")
    return prompt, None


def _prompt_sha(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None


def _machine_prompt(prompt):
    """True for a prompt the harness, not a person, delivers: a task
    notification, a wake, a webhook payload, a scheduled or child-session
    event -- every one an XML-shaped envelope. Any prompt that opens with `<`
    is treated as one: refusing a typed `<` costs a retype, accepting an
    envelope is a session answering itself."""
    return prompt.lstrip().startswith("<")


def check(top, ticket, proposal=None, criteria_file=None, session=None):
    """Run `check_proposal` on the ticket's proposal against its parent's
    criteria (spec.md, or `criteria_file` for a Jira issue). A `## Minted`
    section with no apply record is refused. On a pass, record the
    proposal's sha256, the current turn id and a hash of the prompt that
    moved it (None when unreadable: confirm then refuses)."""
    top = _top(top)
    path = _proposal_path(top, ticket, proposal)
    if criteria_file:
        text = _read(os.path.abspath(criteria_file))
        criteria = None if text is None else [
            b for b in (_bullet(line) for line in text.splitlines()) if b]
    else:
        criteria = parent_criteria(_read(os.path.join(_folder(top, ticket), "spec.md")))
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        return None, [f"the proposal {path} could not be read ({exc.strerror or exc})"]
    text = data.decode("utf-8", "replace")
    decision, problems = check_proposal(criteria, text)
    if parse_proposal(text)["minted"] and not os.path.lexists(apply_record_path(top, ticket)):
        problems.append(f"## Minted lists children but no apply has run for {ticket} (no "
                        f"{os.path.basename(apply_record_path(top, ticket))}); {MINTED_RULE}")
    if problems:
        return decision, problems
    turn, _ = current_turn(top, session)
    prompt, _ = current_prompt(top, session)
    # policy_at_check is for the report only: apply asks ticket_split_policy again.
    policy = ticket_split_policy(top, ticket)
    record = {"proposal": path, "proposal_sha256": _proposal_sha(data), "turn": turn,
              "prompt_sha256": _prompt_sha(prompt),
              "session": session if session is not None else os.environ.get(SESSION_ENV),
              "policy_at_check": {"allow": policy["allow"], "reason": policy["reason"]}}
    target = check_record_path(top, ticket)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    _atomic_write(target, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return decision, problems


def _read_check_record(top, ticket):
    """`(record, None)` or `(None, why)`."""
    try:
        path = check_record_path(top, ticket)
    except SplitError as exc:
        return None, str(exc)
    text = _read(path)
    if text is None:
        why = "could not be read" if os.path.lexists(path) else "does not exist"
        return None, (f"no passing check for {ticket} ({path} {why}); run crew_split.py "
                      "check first")
    try:
        record = json.loads(text)
    except ValueError:
        record = None
    if not isinstance(record, dict) or not record.get("proposal_sha256"):
        return None, f"the check record {path} could not be read"
    return record, None


def confirm(top, ticket, session=None):
    """`{"ok", "reason"}`: ok only when a passing check is recorded, the
    proposal is unchanged since, and this session's current turn id is
    readable, non-empty and different from the one check saw, moved by a
    prompt that is readable, not a harness envelope (task notification,
    wake, webhook) and not the prompt check ran under (a loop re-sending
    it). Autopilot runs its phases with no prompt in between, so it can
    never pass this. Accepted limit (owner, 2026-10-04): a session can
    schedule its own plain-text "yes" (send_later, a routine), which reads
    as typed and passes; the gate is not owner-proof against the session."""
    top = _top(top)
    record, why = _read_check_record(top, ticket)
    if why:
        return {"ok": False, "reason": why}
    try:
        with open(record.get("proposal") or _proposal_path(top, ticket), "rb") as handle:
            sha = _proposal_sha(handle.read())
    except OSError as exc:
        return {"ok": False, "reason": f"the proposal could not be read ({exc.strerror or exc})"}
    if sha != record["proposal_sha256"]:
        return {"ok": False, "reason": "the proposal changed since check passed; run check "
                                       "again and ask again"}
    session = session if session is not None else os.environ.get(SESSION_ENV)
    if record.get("session") and session and record["session"] != session:
        return {"ok": False, "reason": f"check passed in another session "
                                       f"({record['session']}); run check again here"}
    turn, why = current_turn(top, session)
    if why:
        return {"ok": False, "reason": why}
    if not record.get("turn"):
        return {"ok": False, "reason": "check recorded no turn id, so whether a human has "
                                       "answered since cannot be told; run check again"}
    if turn == record["turn"]:
        return {"ok": False, "reason": "no human prompt has arrived since check passed; "
                                       "show the proposal and end the turn for the owner's yes"}
    prompt, why = current_prompt(top, session)
    if why:
        return {"ok": False, "reason": why}
    if _machine_prompt(prompt):
        return {"ok": False, "reason": "the prompt that moved the turn is not a human-typed "
                                       "prompt (a task notification, wake or webhook); ask "
                                       "again and wait for the owner"}
    if record.get("prompt_sha256") and _prompt_sha(prompt) == record["prompt_sha256"]:
        return {"ok": False, "reason": "the prompt that moved the turn matches the one check ran "
                                       "under (only the first 500 characters are compared): a "
                                       "loop re-sending it, or the owner typed the same words "
                                       "both times (e.g. 'go' twice); ask again and have the "
                                       "owner answer in different words"}
    return {"ok": True, "reason": f"a human prompt arrived since check (turn {turn})"}


def _drop(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# --- the ticket split policy (T-0058) ---------------------------------------------------

def ticket_split_policy(top, ticket):
    """`{"allow", "policy", "risk", "known", "reason", "warnings"}` -- whether
    autopilot may apply `ticket`'s split itself. jira refuses (JIRA_STOP),
    sdp refuses (SDP_STOP), an unknown mode refuses; otherwise T-0012's split
    rule on the parent's spec risk (`crew_autopilot._ticket_risk`: missing or
    unreadable reads `high`, unknown). Asked fresh on every call; anything
    that raises refuses as could-not-tell."""
    base = {"allow": False, "policy": UNKNOWN, "risk": "high", "known": False, "warnings": []}
    try:
        # pylint: disable=import-outside-toplevel  # crew_autopilot imports this module
        import crew_autopilot
        import crew_autopilot_goal
        top = _top(top)
        mode = tracker_mode(top)
        if mode == "jira":
            return dict(base, reason=f"tracker is jira: {JIRA_STOP}")
        if mode == "sdp":
            return dict(base, reason=f"tracker is sdp: {SDP_STOP}")
        if mode == UNKNOWN:
            return dict(base, reason="the tracker mode could not be told, so autopilot "
                                     "applies no split")
        conf = crew_autopilot.settings(top)
        risk = crew_autopilot._ticket_risk(top, ticket)  # pylint: disable=protected-access
        allowed = crew_ticket.cli_approval_allowed(top)
        policy = conf["approval"]
        warnings = [w for w in conf["warnings"] if "autopilot.approval " in w
                    or "autopilot.mode " in w]
        words = (f"risk: {risk['risk']}" if risk["known"]
                 else "no risk: low|med|high in the spec header (reads as high)")
        low = risk["known"] and risk["risk"] == "low"
        result = dict(base, policy=policy, risk=risk["risk"], known=risk["known"],
                      warnings=warnings)
        why = crew_autopilot_goal._split_rule(  # pylint: disable=protected-access
            conf, warnings, allowed, low,
            f"autopilot.approval is risk and the spec has {words}, not risk: low")
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return dict(base, reason=f"could not tell whether autopilot may apply the split "
                                 f"({type(exc).__name__}: {exc})")
    if why:
        return dict(result, reason=why)
    return dict(result, allow=True, reason=f"autopilot.approval is {policy} ({words})")


# --- apply -----------------------------------------------------------------------------

def _direction(parent, child):
    lines = [f"origin: split of {parent}", f"split-child: {child['number']}",
             f"title: {child['title']}",
             f"risk: {child['risk'].lower()}", f"subsystem: {child['subsystem']}",
             f"parent's pre-split spec: `.work/tickets/{parent}/{PRE_SPLIT}`; "
             f"split proposal: `.work/tickets/{parent}/{PROPOSAL}`", "", "## Ask",
             f"Criteria (verbatim from {parent}):"]
    lines += [f"- {c}" for c in child["criteria"]]
    lines += ["", "Excludes:"] + [f"- {e}" for e in child["excludes"]]
    lines += ["", "## Options", f"Taken from the parent's approved direction "
              f"(`.work/tickets/{parent}/direction.md`).", "", "## Recommendation", "none", "",
              "## Open questions", "none"]
    return "\n".join(lines) + "\n"


def _provenance(top, child_id, parent):
    """The `split-child:` number when `child_id`'s direction.md carries
    apply's provenance for this parent (its `origin:` and `split-child:`
    lines), else None."""
    try:
        folder = crew_ticket.ticket_dir(top, child_id)
    except crew_ticket.TicketError:
        return None
    lines = (_read(os.path.join(folder, "direction.md")) or "").splitlines()[1:3]
    if len(lines) < 2 or lines[0] != f"origin: split of {parent}":
        return None
    found = re.fullmatch(r"split-child: (\d+)", lines[1])
    return int(found.group(1)) if found else None


def _indexed(top, child_id):
    """True when .work/INDEX.md holds an OPEN row for `child_id` (mint writes
    one). A row closed with a T-0037 word (`cancelled`, `superseded`) is the
    owner's way out of a stale child, so it no longer counts as minted."""
    text = _read(os.path.join(top, ".work", "INDEX.md")) or ""
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if cells[0] == child_id:
            return len(cells) > 1 and cells[1] not in crew_tracker.CLOSED_STATUSES
    return False


def _written_for(top, child_id, parent, child):
    """True when `child_id`'s direction.md is exactly what apply writes for
    this child of the CURRENT proposal (mint's header plus `_direction`)."""
    try:
        folder = crew_ticket.ticket_dir(top, child_id)
    except crew_ticket.TicketError:
        return False
    held = (_read(os.path.join(folder, "direction.md")) or "").replace("\r\n", "\n")
    return held == f"# {child_id} direction\n{_direction(parent, child)}"


def _orphans(top, parent):
    """`{number: id}` for tickets apply minted for this parent (provenance
    plus an INDEX row) -- whether or not their ids reached split.md."""
    tickets = os.path.join(top, ".work", "tickets")
    try:
        names = sorted(os.listdir(tickets))
    except OSError:
        return {}
    found = {}
    for name in names:
        number = None if name == parent else _provenance(top, name, parent)
        if number is not None and _indexed(top, name):
            found.setdefault(number, name)
    return found


def _existing_children(top, ticket, children, minted):
    """`{number: id}` of children apply already minted, each verified against
    the CURRENT proposal, or SplitError with nothing written. Trusted only
    under an apply record: a `## Minted` entry must carry provenance and an
    INDEX row, an orphan (minted, id never recorded) is found by them, and
    either must hold exactly the direction this proposal's child would get;
    a minted child the proposal no longer has, or whose child changed, is a
    stale child and stops the apply."""
    record = os.path.lexists(apply_record_path(top, ticket))
    if minted and not record:
        raise SplitError(f"{PROPOSAL}'s ## Minted lists children but no apply has run for "
                         f"{ticket}; {MINTED_RULE}; nothing was written")
    if not record:
        return {}
    live = {}
    for number, child_id in sorted(minted.items()):
        if _provenance(top, child_id, ticket) != number:
            raise SplitError(f"## Minted names {child_id} as Child {number}, but it carries no "
                             f"provenance (`origin: split of {ticket}`, `split-child: "
                             f"{number}`); nothing was written")
        if _indexed(top, child_id):
            live[number] = child_id  # a cancelled/superseded or row-less entry is minted again
    found = dict(_orphans(top, ticket))
    found.update(live)
    by_number = {child["number"]: child for child in children}
    for number, child_id in sorted(found.items()):
        child = by_number.get(number)
        if child is None or not _written_for(top, child_id, ticket, child):
            raise SplitError(f"{child_id} was minted as Child {number} for a different proposal "
                             f"(its direction no longer matches this {PROPOSAL}'s Child "
                             f"{number}); nothing was written. Either restore Child {number}'s "
                             f"text in {PROPOSAL}, or cancel the stale ticket with "
                             f"`crew_tracker.py move --ticket {child_id} --to cancelled`; then "
                             f"re-run check and ask for a new yes")
    return found


def _record_minted(path, number, ticket):
    """Set `- Child N: <id>` in the trailing `## Minted` (made on first use;
    an entry for N, a cancelled child's, is replaced in place), in the file's
    own line ending."""
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    body, entries = minted_tail(text)
    if entries is None:
        body, entries = text, {}
    entries[number] = ticket
    lines = "".join(f"- Child {n}: {t}{eol}" for n, t in entries.items())
    text = f"{body.rstrip()}{eol}{eol}## Minted{eol}{lines}"
    _atomic_write(path, text.encode("utf-8"))


def _superseded_spec(text, kids):
    """The spec with `status: superseded` on its header and `split-into:`
    under it; the rest byte-identical (line endings kept)."""
    first, sep, rest = text.partition("\n")
    eol = "\r\n" if first.endswith("\r") else "\n"
    head = first.rstrip("\r")
    head = (_STATUS_RE.sub(f"status: {SUPERSEDED}", head, count=1) if _STATUS_RE.search(head)
            else f"{head}   status: {SUPERSEDED}")
    rest = re.sub(r"\Asplit-into:[^\n]*\n", "", rest)
    return f"{head}{eol}split-into: {', '.join(kids)}{eol}{rest if sep else ''}".encode("utf-8")


def _refuse_mode(top):
    mode = tracker_mode(top)
    if mode == "sdp":
        raise SplitError(f"tracker is sdp: {SDP_STOP}; nothing was written")
    if mode == "jira":
        raise SplitError("tracker is jira: /crew:split creates Jira issues through MCP (its "
                         "Jira steps); apply writes files tickets only; nothing was written")
    if mode == UNKNOWN:
        raise SplitError("the tracker mode could not be told (.crew/crew.json or "
                         ".crew/config.json unreadable or disagreeing); nothing was written")
    kind = crew_tracker.resolve(top)["kind"]
    if kind not in ("files", "obsidian"):
        raise SplitError(f"tracker is {kind}: crew_ticket.mint writes a ticket only under a "
                         "configured files or obsidian tracker; nothing was written")


def _write_pre_split(folder, data):
    pre = os.path.join(folder, PRE_SPLIT)
    if os.path.lexists(pre):
        try:
            with open(pre, "rb") as handle:
                held = handle.read()
        except OSError as exc:
            raise SplitError(f"{PRE_SPLIT} exists and could not be read "
                             f"({exc.strerror or exc}); nothing was minted") from exc
        if held != data:
            raise SplitError(f"{PRE_SPLIT} already exists and differs from spec.md; "
                             "nothing was minted")
        return
    _atomic_write(pre, data)


def _mint_children(top, ticket, children, existing, path):
    """Mint each child not in `existing` (`_existing_children`), in order,
    recording each id in split.md; an existing child is recorded, never
    minted twice."""
    minted = dict(parse_proposal(_read(path) or "")["minted"])
    kids, warnings = [], []
    for child in children:
        number = child["number"]
        found = existing.get(number)
        if found:
            if minted.get(number) != found:
                minted[number] = found
                _record_minted(path, number, found)
            kids.append(found)
            continue
        try:
            got = crew_ticket.mint(top, child["title"], status="ready",
                                   direction=_direction(ticket, child))
        except Exception as exc:  # pylint: disable=broad-except
            done = [f"Child {c['number']}" for c in children[:len(kids)]]
            left = [f"Child {c['number']}" for c in children[len(kids):]]
            raise SplitError(
                f"mint of Child {number} ({child['title']}) failed: {exc}; minted: "
                f"{', '.join(done) or 'none'}; not minted: {', '.join(left)}; the parent's "
                f"status is unchanged. Re-run check, ask for a new yes, then apply: minted "
                f"children (## Minted in {PROPOSAL}) are skipped") from exc
        minted[number] = got["ticket"]
        _record_minted(path, number, got["ticket"])
        kids.append(got["ticket"])
        warnings += [f"{got['ticket']}: {w}" for w in got["warnings"]]
    return kids, warnings


def _read_strict(path, label):
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise SplitError(f"{label} could not be read ({exc.strerror or exc}); nothing was "
                         "written") from exc
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SplitError(f"{label} is not UTF-8 ({exc}); nothing was written") from exc


def apply(top, ticket, via, session=None):
    """Split a files/Obsidian ticket. Refused, with nothing written, in jira,
    sdp or an unknown mode, on a `via` not in VIAS, on a spec or proposal that
    is not UTF-8, on a proposal check_proposal refuses or whose decision is
    not `split`, on a `## Minted` entry apply did not write, on a parent
    already superseded, and when the approval refuses: confirm (a human turn)
    for `command`, ticket_split_policy asked now for `autopilot` (which runs
    every other check, existing-children verification included). Then, in
    order: record the apply; write spec.pre-split.md byte-identical to
    spec.md; mint each child (recording each id in split.md as it returns);
    and only after every mint returned, mark the parent's spec header and
    INDEX row `superseded`. A success spends the check record; a failure
    part-way drops it too, so a re-run needs a fresh check and yes."""
    top = _top(top)
    if via not in VIAS:
        raise SplitError(f"via {via} is not one of {'|'.join(VIAS)}; nothing was written")
    if via == "autopilot":
        policy = ticket_split_policy(top, ticket)
        if not policy["allow"]:
            raise SplitError(f"the split policy refused: {policy['reason']}; nothing was "
                             f"written - the owner runs /crew:split {ticket}")
    _refuse_mode(top)
    folder = _folder(top, ticket)
    spec_path = os.path.join(folder, "spec.md")
    spec, spec_text = _read_strict(spec_path, f"{ticket}'s spec.md")
    if re.search(rf"(?<![\w-])status:[ \t]*{SUPERSEDED}\b", crew_ticket.header_line(spec_text)):
        raise SplitError(f"{ticket} is already superseded; nothing was written")
    path = os.path.join(folder, PROPOSAL)
    _, proposal = _read_strict(path, PROPOSAL)
    decision, problems = check_proposal(parent_criteria(spec_text), proposal)
    if problems:
        raise SplitError(f"{PROPOSAL} fails the rulebook: " + "; ".join(problems))
    if decision != "split":
        raise SplitError(f"the decision is {decision}, not split; nothing to apply")
    got = parse_proposal(proposal)
    existing = _existing_children(top, ticket, got["children"], got["minted"])
    gate = confirm(top, ticket, session) if via == "command" else {"ok": True}
    if not gate["ok"]:
        raise SplitError(f"confirm refused: {gate['reason']}; nothing was written")
    check_path, record_path = check_record_path(top, ticket), apply_record_path(top, ticket)
    if not os.path.lexists(record_path):
        # --via autopilot may run with no check before it, so nothing made the folder.
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        _atomic_write(record_path, (json.dumps({"parent": ticket}) + "\n").encode("utf-8"))
    try:
        _write_pre_split(folder, spec)
        kids, warnings = _mint_children(top, ticket, got["children"], existing, path)
    except BaseException:
        _drop(check_path)
        raise
    _atomic_write(spec_path, _superseded_spec(spec_text, kids))
    _drop(check_path)
    _drop(record_path)
    report = crew_tracker.move(top, ticket, SUPERSEDED)
    lines = [crew_tracker._line(r) for r in report["results"]]  # pylint: disable=protected-access
    if crew_tracker.exit_code(report) == 1:
        raise SplitError(f"children {', '.join(kids)} minted and the spec header set, but the "
                         f"INDEX move to {SUPERSEDED} failed: {'; '.join(lines)}; run "
                         f"`crew_tracker.py move --ticket {ticket} --to {SUPERSEDED}`")
    return {"children": kids, "parent": SUPERSEDED, "warnings": warnings}


# --- CLI -------------------------------------------------------------------------------

def _fmt(value):
    return UNKNOWN if value is None else str(value)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "measure")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("measure", "check", "confirm", "apply"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--stage", choices=STAGES,
                        help="measure: default plan when plan.md exists, else spec")
    parser.add_argument("--proposal", help="check: the split.md (default the ticket's)")
    parser.add_argument("--criteria-file", help="check: the parent's criteria as bullets "
                        "(Jira, where the parent is an issue with no spec.md)")
    parser.add_argument("--via", help="apply: command (/crew:split, after a human turn) or "
                        "autopilot (ticket_split_policy)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        if args.action == "measure":
            got = measure(root, args.ticket)
            stage = args.stage or ("plan" if got["plan_steps"] is not None else "spec")
            print(" ".join(f"{k}={_fmt(got[k])}" for k in MEASURES))
            print(f"stage={stage} triggers: {', '.join(triggers(got, stage)) or 'none'}")
            print(f"tracker={tracker_mode(root)}")
            return 0
        if args.action == "check":
            decision, problems = check(root, args.ticket, args.proposal, args.criteria_file)
            for problem in problems:
                print(f"problem: {problem}")
            if problems:
                return 1
            print(f"ok decision={decision}")
            _, why = current_turn(root)
            if why:
                print(f"note: confirm will refuse: {why}")
            return 0
        if args.action == "confirm":
            gate = confirm(root, args.ticket)
            print(f"{'ok' if gate['ok'] else 'refused'}: {gate['reason']}")
            return 0 if gate["ok"] else 1
        got = apply(root, args.ticket, args.via or "")
    except (SplitError, crew_ticket.TicketError, OSError, ValueError) as exc:
        print(f"refused: {exc}")
        return 1
    for kid in got["children"]:
        print(f"child={kid}")
    print(f"parent={args.ticket} status={got['parent']}")
    for warning in got["warnings"]:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
