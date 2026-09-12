"""Renders the crew Project Manager's session-start brief.

Reads nothing from disk itself -- crew_state does that -- so the renderer can
be tested against a literal state dict. Output is plain project information,
never instructions: text framed as out-of-band commands trips prompt-injection
defences and gets surfaced to the user instead of treated as context. See
hooks/scripts/handoff-read.sh for the same reasoning.
"""

import json
import os
import re
import sys

import crew_config
import crew_incident
import crew_state
import hook_once

# Default kept identical to crew_state.read_work's hard-coded path and to
# handoff-read.sh's own fallback, so all three agree absent an override.
_DEFAULT_HANDOFF_PATH = ".work/HANDOFF.md"

_NEXT_ACTION_RE = re.compile(r"^##\s*next action\s*$", re.IGNORECASE)


def _crew_line(state):
    roles = state.get("roles") or []
    tier = state.get("tier")
    parts = ["## crew"]
    parts.append(f"tier {tier}" if tier is not None else "tier unset")
    parts.append(f"{len(roles)} role{'' if len(roles) == 1 else 's'}")
    tracker = state.get("tracker")
    if tracker:
        parts.append(f"tracker {tracker}")
    return f"{parts[0]} - " + ", ".join(parts[1:])


def _health_line(state):
    health = state.get("health") or {}
    if health.get("rate") is None:
        return "health: no reviews recorded yet"
    return (
        f"health: {health['rate']} BLOCK+FIX per ticket "
        f"over {health['tickets']} - {health['verdict']}"
    )


def _work_line(state):
    work = state.get("work") or {}
    ticket = work.get("ticket")
    open_part = f"{ticket} open" if ticket else "no ticket open"
    handoff = "handoff pending" if work.get("handoffPending") else "no handoff"
    return f"work: {open_part}, {handoff}"


def _knowledge_line(state):
    knowledge = state.get("knowledge") or {}
    graph = knowledge.get("graph") or {}
    total = knowledge.get("subsystems", 0)
    behind = knowledge.get("behind") or []
    if total:
        maps = f"{total} subsystem{'' if total == 1 else 's'} mapped"
        maps += ", anchors current" if not behind else (
            f", {len(behind)} anchored behind HEAD"
        )
    else:
        maps = "no codemap"
    if not graph.get("present"):
        graph_part = "no graph"
    else:
        graph_part = "graph current" if graph.get("current") else "graph behind HEAD"
    return f"knowledge: {maps}; {graph_part}"


def _diagrams_line(state):
    """The diagrams state line, or None to omit it entirely.

    Omitted when there are no diagrams at all, and that is not cosmetic. Every
    quiet line is permanent -- it survives truncation while findings do not --
    so a line that always prints costs a FINDING slot at a tight `maxLines`.
    Measured: adding an unconditional line pushed the highest-priority finding
    out of a `maxLines: 7` brief entirely, which is the one thing render()'s
    truncation is built to prevent.

    "diagrams: none" also says nothing actionable. When having none matters,
    `diagramsMissing` fires and says so with a fix attached.
    """
    diagrams = crew_state.dict_or_empty(state.get("diagrams"))
    total = diagrams.get("total", 0)
    if not total:
        return None
    behind = diagrams.get("behind") or []
    fresh = "anchors current" if not behind else f"{len(behind)} behind HEAD"
    return f"diagrams: {total} drawn, {fresh}"


# One finding and exactly one next action per trigger. One action because a
# brief that lists three is a brief nobody acts on.
FINDINGS = {
    # The only findings whose text carries live numbers; see _incident_fields.
    "incidentActive": (
        "EMERGENCY LANE OPEN - {id} ({summary}), {minutesLeft}m left, "
        "{skips} gate(s) skipped so far. The verify and promote gates are "
        "standing down: nothing this session writes is being checked",
        "close it with /crew:emergency end the moment the environment is "
        "stable - that writes the report and puts the gates back",
    ),
    "incidentUnclosed": (
        "{id} expired without being closed, leaving {skips} skipped gate(s) "
        "unaccounted for. The gates are back on already",
        "run /crew:emergency end to write the debt list before it is lost",
    ),
    # See _schema_fields. The text used to be a single fixed sentence --
    # "this setup predates the PM and the code graph (config has no schema)"
    # -- which is true only of a config with no `schema` key at all, and false
    # for every schema-2 and schema-3 repo. Bumping SCHEMA_CURRENT to 4 made
    # that the whole installed population: everyone was about to be told their
    # config has no schema, at the one moment they are most likely to read it,
    # by the trigger that sorts third and therefore leads the brief.
    "upgradeNeeded": (
        "{schemaSummary}",
        "run /crew:upgrade - it backs up the codemap first and reports "
        "conflicts rather than overwriting them",
    ),
    "handoffPending": (
        "a handoff note from a previous session is still in place",
        "finish or delete it - a stale handoff is injected into every "
        "session as though it were current",
    ),
    # gizmoduck is installed, so this is enforced: a declared hit is a fact
    # (a ticket said the endpoint exists), a candidate hit is NOT -- it is a
    # regex hit on a diff line that needs research before it is treated as a
    # real endpoint at all, let alone a scanned one. Both halves are built by
    # _endpoint_fields into one summary/action pair, because at least one of
    # the two is always empty for a real trigger firing (see its docstring):
    # a state with only candidates must not still say "0 declared
    # endpoint(s)" and tell the user to run gizmoduck:scan for none of them.
    "endpointUnscanned": (
        "{endpointSummary}",
        "{endpointAction}",
    ),
    "graphStale": (
        "the code graph is missing or older than HEAD",
        "run /crew:onboard, or graphify . --no-viz --code-only to refresh it",
    ),
    "knowledgeBehind": (
        "some codemap anchors are behind HEAD, so those notes may describe "
        "code that has since changed",
        "run /crew:onboard --refresh <subsystem> before relying on them",
    ),
    "diagramsStale": (
        "{staleCount} diagram(s) are anchored behind HEAD ({staleNames}), so "
        "they draw code that has since moved",
        "run /crew:diagram refresh - it re-verifies anchors and rewrites only "
        "the diagrams whose code actually changed",
    ),
    "diagramsMissing": (
        "no {missingNames} diagram for a repo whose subsystems are already "
        "mapped",
        "run /crew:diagram <kind> to draw it from the codemap",
    ),
    "reviewNotWorking": (
        "review is finding almost nothing, which usually means it is broken "
        "rather than that the code is clean",
        "check that Codex is really running, the diff is not empty, and the "
        "base branch is right - before adding any role",
    ),
    "ticketsTooLarge": (
        "findings per ticket are high enough that the tickets are probably "
        "too large",
        "cut ticket scope rather than adding roles",
    ),
}

# One per authority. The brief has to say which mode is in effect, because the
# same list of findings means two different things: "here is what I am about to
# do" and "here is what I would do if you said so". A reader who cannot tell
# them apart either expects work that never happens, or is surprised by work
# they thought they were being asked about.
_AUTHORITY_NOTES = {
    "report-only": (
        "The manager reports and recommends; it does not act on these on its "
        "own. Say the word, or run /crew:pm assign, to have it do the work. "
        "Set pm.authority to \"act\" in .crew/config.json to make that the "
        "default."
    ),
    "act": (
        "The manager acts on these itself - it dispatches crew roles and "
        "refreshes diagrams without being asked. Say what you want prioritised "
        "and that wins over its own ordering. It researches a finding before "
        "raising it, so a question from it should arrive with what it already "
        "checked. It still asks before removing a role or deleting anything."
    ),
    "autonomous": (
        "The manager acts on these itself and settles its own open questions - "
        "where it would otherwise ask you to choose, it takes the option it "
        "would have recommended and tells you which. Say what you want "
        "prioritised and that wins over its own ordering. It still asks before "
        "offboarding a role, deleting a codemap or diagram, rewriting "
        ".crew/metrics.md, or destroying git history or tracked work."
    ),
}


def _authority_note(state):
    pm = crew_state.dict_or_empty(state.get("pm"))
    authority = crew_state.normalise_authority(pm.get("authority"))
    return _AUTHORITY_NOTES[authority]

_TRUNCATED = "More findings than fit here - run /crew:pm for the full report."


def _incident_fields(state):
    """Values the incident findings interpolate. Always every key.

    A missing key would raise KeyError inside .format() and take out the whole
    brief, which runs from SessionStart -- so the defaults are supplied here
    rather than trusted from state.
    """
    incident = crew_state.dict_or_empty(state.get("incident"))
    summary = str(incident.get("summary") or "no summary given")
    return {
        "id": incident.get("id") or "an incident",
        # A one-line brief is not the place for a paragraph someone typed at
        # 03:00 under pressure.
        "summary": summary if len(summary) <= 60 else summary[:57] + "...",
        "minutesLeft": incident.get("minutesLeft", 0),
        "skips": incident.get("skips", 0),
    }


def _names(items, limit=3):
    """`items` as a short comma list, with an overflow count. Never empty.

    A finding that names every one of nine stale diagrams is a finding nobody
    reads, and the brief has a hard line cap it would blow through besides.
    """
    items = [str(i) for i in items if str(i).strip()]
    if not items:
        return "none"
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" +{len(items) - limit} more"


def _diagram_fields(state):
    """Values the diagram findings interpolate. Always every key.

    Same contract as _incident_fields: a missing key raises KeyError inside
    .format() and takes out the whole brief.
    """
    diagrams = crew_state.dict_or_empty(state.get("diagrams"))
    behind = diagrams.get("behind") or []
    missing = diagrams.get("missing") or []
    return {
        "staleCount": len(behind),
        "staleNames": _names(behind),
        "missingNames": _names(missing),
        "diagramsDir": diagrams.get("dir") or "docs/diagrams",
    }


def _endpoint_fields(state):
    """Values the endpointUnscanned finding interpolates. Always every key.

    Same contract as _incident_fields and _diagram_fields. Declared and
    candidate hits are split here rather than left for the finding text to
    sort out, because the whole point of the split is that they must never
    be described the same way.

    Keyed on `status` (finding 10), NOT `source` -- `status` is the field
    the ledger's design makes authoritative (see crew_state.declare_endpoint
    and _unscanned_hit), and a record whose `source` and `status` disagree
    -- a bug writing `source="declared", status="candidate"` -- must still
    render here as a candidate, never as a confirmed fact. Hit dicts are
    guarded with isinstance rather than trusted, per crew_state.dict_or_empty's
    docstring warning against `.get()` on an unchecked element -- `state` can
    arrive hand-built from a test or a stale cache, not only from
    crew_state.read_endpoints.

    `endpointSummary`/`endpointAction` are pre-composed so the finding text
    never mentions a half that has no hits: a candidates-only state must not
    read "0 declared endpoint(s) have no security scan yet (none)" with an
    action telling the user to scan none of them.

    Each name carries its `location` (finding 7) when the hit has one --
    `an endpoint (src/app.py:10)` rather than the bare endpoint text -- so
    twenty candidates sharing the same generic label ("a Flask/FastAPI route
    decorator") still read as twenty distinct, findable lines rather than
    one indistinguishable repeated string.
    """
    endpoints = crew_state.dict_or_empty(state.get("endpoints"))
    raw_hits = endpoints.get("unscanned") or []
    hits = [hit for hit in raw_hits if isinstance(hit, dict)]
    candidates = [hit for hit in hits if hit.get("status") == "candidate"]
    declared = [hit for hit in hits if hit.get("status") != "candidate"]

    def _label(hit):
        endpoint = hit.get("endpoint") or "an endpoint"
        location = hit.get("location")
        return f"{endpoint} ({location})" if location else endpoint

    summary_parts = []
    if declared:
        summary_parts.append(
            f"{len(declared)} declared endpoint(s) have no security scan "
            f"yet ({_names([_label(hit) for hit in declared])})"
        )
    if candidates:
        # "also" only makes sense when a declared half is present too --
        # a candidates-only brief must not read "also lack one" with
        # nothing else in the sentence for "also" to refer to (nit 14).
        verb = "also lack one" if declared else "lack one"
        summary_parts.append(
            f"{len(candidates)} inferred candidate(s) {verb} "
            f"({_names([_label(hit) for hit in candidates])}) - "
            "candidates are NOT confirmed endpoints until researched"
        )
    summary = " and ".join(summary_parts) if summary_parts else (
        "no endpoints currently need a scan"
    )

    action_parts = []
    if declared:
        action_parts.append("run gizmoduck:scan for each declared endpoint now")
    if candidates:
        action_parts.append(
            "research each candidate first (promote it or close it with "
            "the evidence) before scanning it or reporting it as real"
        )
    action = "; ".join(action_parts) if action_parts else "no action needed"

    return {
        "declaredCount": len(declared),
        "declaredNames": _names([_label(hit) for hit in declared]),
        "candidateCount": len(candidates),
        "candidateNames": _names([_label(hit) for hit in candidates]),
        "endpointSummary": summary,
        "endpointAction": action,
    }


def _schema_fields(state):
    """The value `upgradeNeeded` interpolates. Always the key.

    Same contract as _incident_fields: a missing key raises KeyError inside
    .format() and takes out the whole brief, which runs from SessionStart.

    Three states, and they must not be described the same way:

    - no `schema` key at all -- the pre-PM config this finding's old text
      described, and now the rarest of the three;
    - a `schema` the file states and this code can read -- the common case
      after any SCHEMA_CURRENT bump, and the one the old text lied to;
    - a `schema` that will not parse (`true`, `"three"`, an explicit `null`),
      which `int_or` turns into 1 and which would otherwise be reported as a
      pre-PM config rather than as the typo it is.

    The third case includes `"schema": null` specifically, and that is the
    reason `collect()` carries `schemaKeyPresent` beside the value: `null` and
    an absent key both read back as None, so the value alone cannot separate
    "never had a schema" from "wrote a word that is not a version". Keying on
    the value alone was this function's own first draft, and Codex caught it.

    The raw value is rendered with `json.dumps`, so it reads back as the user
    typed it in the file -- `null`, `true`, `"three"` -- rather than as its
    Python spelling. `json.dumps` also guarantees ASCII output, which
    test_the_brief_is_pure_ascii requires of every line this module emits.

    Deliberately NOT a per-migration description. `commands/upgrade.md`
    section 5 enumerates what each hop does and tells the agent to read the
    relevant entry out; naming the hop here and the content there keeps one
    copy of that prose. A second copy in a one-line brief is a copy that
    drifts, and the drift would land in the sentence a user reads first.
    """
    current = crew_state.SCHEMA_CURRENT
    schema = crew_state.int_or(state.get("schema", 1), 1)

    # `schemaDeclared` ABSENT from the state dict and a config that declares
    # no schema are not the same thing, and collapsing them would reintroduce
    # the bug one level up. collect() always sets the key, so absent means a
    # hand-built state -- a test, the crew:pm agent, a stale cache -- which
    # knows only the normalised number. Fall back to that rather than to "no
    # schema", or every such caller gets told its config declares one, which
    # is the exact false sentence this function exists to remove.
    if "schemaDeclared" in state:
        declared = state["schemaDeclared"]
        key_present = bool(state.get("schemaKeyPresent"))
    else:
        declared, key_present = schema, True

    if not key_present:
        summary = ("this setup predates the PM and the code graph "
                   f"(config declares no schema; current is {current})")
    elif crew_state.int_or(declared, None) is None:
        summary = (f"config's schema is {json.dumps(declared)}, which is not "
                   f"a version number - crew is reading it as {schema}, and "
                   f"current is {current}")
    else:
        hops = current - schema
        owed = (f"the {schema} -> {current} migration" if hops == 1
                else f"the {schema} -> {current} migrations")
        summary = (f"config is at schema {schema}, current is {current} - "
                   f"{owed} has not run here" if hops == 1
                   else f"config is at schema {schema}, current is {current} - "
                        f"{owed} have not run here")
    return {"schemaSummary": summary}


def _fill(text, fields):
    """`text` with {placeholders} substituted. Returns it unchanged if it has
    none, or if it has one this does not know -- a finding that renders as a
    literal brace is ugly, and a brief that raises is invisible."""
    if "{" not in text:
        return text
    try:
        return text.format(**fields)
    except (KeyError, IndexError, ValueError):
        return text


def render(state):
    """The brief's lines. Empty list means print nothing at all."""
    if not state.get("isCrew"):
        return []
    pm = state.get("pm") or {}
    if not pm.get("enabled", True):
        return []

    quiet = [line for line in (
        _crew_line(state),
        _health_line(state),
        _work_line(state),
        _knowledge_line(state),
        _diagrams_line(state),
    ) if line]

    # An incident goes FIRST, and in the quiet lines rather than the findings,
    # so it survives both `pm.mode: quiet` and every line cap. The findings
    # below can be truncated away; "the gates are currently off" cannot be the
    # thing that got truncated.
    incident = crew_state.dict_or_empty(state.get("incident"))
    if incident.get("present"):
        quiet.insert(0, "## incident - " + crew_incident.format_status(incident))

    triggers = state.get("triggers") or []
    if pm.get("mode") != "adaptive" or not triggers:
        return quiet[: max(1, int(pm.get("quietLines", 8)))]

    # A finding and its action are one unit. Truncation cuts between units,
    # never inside one: a finding whose action was dropped names a problem and
    # says nothing about it, which is worse than omitting it entirely.
    fields = dict(_incident_fields(state))
    fields.update(_diagram_fields(state))
    fields.update(_endpoint_fields(state))
    fields.update(_schema_fields(state))
    pairs = []
    for name in triggers:
        entry = FINDINGS.get(name)
        if not entry:
            continue
        finding, action = entry
        pairs.append((f"- {_fill(finding, fields)}", f"  -> {_fill(action, fields)}"))

    cap = max(2, int(pm.get("maxLines", 40)))
    tail = ["", _authority_note(state)]
    flat = [line for pair in pairs for line in pair]

    if len(quiet) + len(flat) + len(tail) <= cap:
        return list(quiet) + flat + tail

    # No room for everything. Keep whole pairs, highest priority first --
    # crew_state returns triggers in priority order -- and spend the last line
    # on the pointer to the full report.
    room = cap - len(quiet) - 1
    if room < 2:
        # Not even one finding fits. The cap wins over the content, including
        # over the state summary: a brief that exceeds its own cap is not a
        # capped brief.
        if cap > len(quiet):
            return list(quiet) + [_TRUNCATED]
        return list(quiet)[:cap]
    kept = pairs[: room // 2]
    return (
        list(quiet)
        + [line for pair in kept for line in pair]
        + [_TRUNCATED]
    )


def _handoff_path(cfg):
    """The configured handoff path, or the shared default when absent or
    wrong-typed. A dict or a number here must not raise; see
    crew_state.dict_or_empty for the same defensive shape elsewhere.
    """
    context_cfg = crew_state.dict_or_empty(cfg.get("context"))
    path = context_cfg.get("handoffPath")
    return path if isinstance(path, str) and path else _DEFAULT_HANDOFF_PATH


def _auto_resume_enabled(cfg):
    """True only when context.autoResume is exactly the JSON boolean true.

    Not a truthiness check: config is hand-edited, and "true" (a string) or
    1 (an int) mean someone was confused, not that the flag is on. Getting
    this wrong in the permissive direction would let a stray non-boolean
    value skip the one human read of a handoff before work resumes on it.
    """
    context_cfg = crew_state.dict_or_empty(cfg.get("context"))
    return context_cfg.get("autoResume") is True


def _next_action(handoff_text):
    """The text under the handoff's '## Next action' heading, or None.

    Joined onto one line -- this becomes one line of a JSON string value,
    not a rendered document -- and stops at the next heading or end of file.
    """
    lines = handoff_text.splitlines()
    for i, line in enumerate(lines):
        if not _NEXT_ACTION_RE.match(line.strip()):
            continue
        action = []
        for later in lines[i + 1:]:
            if later.strip().startswith("##"):
                break
            if later.strip():
                action.append(later.strip())
        if action:
            return " ".join(action)
    return None


def _resume_context(root, cfg, brief_lines):
    """additionalContext for context.autoResume, or None when it does not
    apply.

    Step 0 found `initialUserMessage` confirmed only for non-interactive
    (`-p`) invocations -- see crew-context/SKILL.md for the full record of
    that test. No PTY was available in this environment to drive an actual
    interactive session, so this emits `additionalContext` rather than
    `initialUserMessage`: confirmed for all sources, at the cost of the
    session opening with the handoff already in view rather than already
    working.

    Fires only when autoResume is exactly true AND a handoff file exists at
    the configured path -- both conditions, not either.

    Checked for staleness here too, not only in handoff-read.sh's printed
    path: autoResume skips the one human read step that path still leaves in
    place (see crew-context/SKILL.md's Auto-resume section), so injecting a
    note the age/reality-drift signals already flagged would be strictly
    worse here than there. `archive_stale_handoff` both judges and, if
    warranted, archives the note in one step; a stale note is archived and
    this returns None -- nothing to resume from, which is the honest state
    once the note describing it has moved.
    """
    if not _auto_resume_enabled(cfg):
        return None
    if crew_state.archive_stale_handoff(root, cfg).get("archived"):
        return None
    # contained_path, not a bare join: this text is injected wholesale into
    # the model's context, and `handoffPath` comes from the repo's own config.
    # A cloned repo naming `../../.ssh/id_rsa` here would have it read and
    # placed in front of the model at session start -- the shortest path from
    # "checked out a repo" to "leaked a file" this plugin had.
    handoff_text = crew_state.read_text(
        crew_state.contained_path(root, _handoff_path(cfg),
                                  _DEFAULT_HANDOFF_PATH)
    )
    if not handoff_text or not handoff_text.strip():
        return None

    parts = []
    if brief_lines:
        parts.append("\n".join(brief_lines))
    parts.append("## Resuming from the previous session's handoff")
    parts.append(handoff_text.strip())
    next_action = _next_action(handoff_text)
    if next_action:
        parts.append(f"Next action: {next_action}")
    parts.append(
        "The working tree is the source of truth. Verify the notes above "
        "against git diff before acting on them."
    )
    return "\n\n".join(parts)


def main(argv=None):
    """Hook entry point. Reads the SessionStart payload from stdin. Always 0."""
    del argv
    try:
        raw = sys.stdin.read()
    except OSError:
        return 0
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    root = payload.get("cwd") or os.environ.get(
        "CLAUDE_PROJECT_DIR"
    ) or os.getcwd()

    # Both the .sh and .ps1 wrapper call this module, and SessionStart has no
    # matcher to pick one -- so whichever arrives second must print nothing.
    # Claiming here rather than in the wrappers means one implementation
    # instead of two, and no shell-specific platform guessing.
    #
    # The key includes `source`, and that is load-bearing. SessionStart fires
    # once per SOURCE EVENT -- startup, clear, compact, resume, fork -- not once
    # per session. Keying on session_id alone means the brief prints at startup
    # and stays silent after every later /clear and /compact, which is exactly
    # when a fresh session most needs its state. Including source is safe
    # whichever way session_id behaves: if it changes across /clear the key is
    # unique anyway; if it does not, source disambiguates.
    session = payload.get("session_id")
    source = payload.get("source") or "unknown"
    if not hook_once.claim(root, "pm-brief", f"{session}-{source}" if session
                           else None):
        return 0

    # A Windows console often runs an OEM codepage (cp437/cp850) that cannot
    # encode characters this module has no reason to emit. Measured: printing
    # an em-dash under cp437 raises UnicodeEncodeError and the hook exits 1.
    # Output is kept ASCII, and this is the second line of defence -- the next
    # non-ASCII string someone adds degrades to '?' rather than taking out
    # every session in the repo.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    try:
        # layered_state applies the global config layer only for a repo it
        # recognises as crew-managed -- never for a plain git repo with no
        # .crew/, which must not inherit settings from someone's global file.
        state = crew_config.layered_state(root)
        lines = render(state)
        cfg = crew_config.resolve_config(root) if state.get("isCrew") else {}
        resume = _resume_context(root, cfg, lines)
        if resume is not None:
            # The whole of stdout must be valid JSON here -- there is no
            # channel to print the plain brief alongside it, so the brief's
            # own lines are folded into the payload by _resume_context
            # rather than printed separately.
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": resume,
                },
            }))
        elif lines:
            print("\n".join(lines))
    except Exception:  # pylint: disable=broad-except
        # A SessionStart hook that raises breaks every session opened in this
        # repository. Silence is the only acceptable failure mode, and the
        # print belongs inside the guard: encoding errors happen at write time,
        # not at render time.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
