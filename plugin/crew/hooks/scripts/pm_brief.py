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
    "upgradeNeeded": (
        "this setup predates the PM and the code graph (config has no schema)",
        "run /crew:upgrade - it backs up the codemap first and reports "
        "conflicts rather than overwriting them",
    ),
    "handoffPending": (
        "a handoff note from a previous session is still in place",
        "finish or delete it - a stale handoff is injected into every "
        "session as though it were current",
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

_AUTHORITY_NOTE = (
    "The manager acts on these itself - it dispatches crew roles and refreshes "
    "diagrams without being asked. Say what you want prioritised and that wins "
    "over its own ordering. It still asks before removing a role or deleting "
    "anything."
)

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
    pairs = []
    for name in triggers:
        entry = FINDINGS.get(name)
        if not entry:
            continue
        finding, action = entry
        pairs.append((f"- {_fill(finding, fields)}", f"  -> {_fill(action, fields)}"))

    cap = max(2, int(pm.get("maxLines", 40)))
    tail = ["", _AUTHORITY_NOTE]
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
    """
    if not _auto_resume_enabled(cfg):
        return None
    handoff_text = crew_state.read_text(
        os.path.join(root, _handoff_path(cfg))
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
        lines = render(crew_state.collect(root))
        cfg = crew_state.load_config(root)
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
