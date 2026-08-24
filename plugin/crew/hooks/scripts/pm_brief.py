"""Renders the crew Project Manager's session-start brief.

Reads nothing from disk itself -- crew_state does that -- so the renderer can
be tested against a literal state dict. Output is plain project information,
never instructions: text framed as out-of-band commands trips prompt-injection
defences and gets surfaced to the user instead of treated as context. See
hooks/scripts/handoff-read.sh for the same reasoning.
"""

import json
import os
import sys

import crew_state
import hook_once


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


# One finding and exactly one next action per trigger. One action because a
# brief that lists three is a brief nobody acts on.
FINDINGS = {
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
        "run /crew:onboard, or graphify . --no-viz to refresh it",
    ),
    "knowledgeBehind": (
        "some codemap anchors are behind HEAD, so those notes may describe "
        "code that has since changed",
        "run /crew:onboard --refresh <subsystem> before relying on them",
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
    "The manager reports and recommends; it does not change roles, tier, or "
    "delete anything without being asked."
)

_TRUNCATED = "More findings than fit here - run /crew:pm for the full report."


def render(state):
    """The brief's lines. Empty list means print nothing at all."""
    if not state.get("isCrew"):
        return []
    pm = state.get("pm") or {}
    if not pm.get("enabled", True):
        return []

    quiet = [
        _crew_line(state),
        _health_line(state),
        _work_line(state),
        _knowledge_line(state),
    ]

    triggers = state.get("triggers") or []
    if pm.get("mode") != "adaptive" or not triggers:
        return quiet[: max(1, int(pm.get("quietLines", 8)))]

    # A finding and its action are one unit. Truncation cuts between units,
    # never inside one: a finding whose action was dropped names a problem and
    # says nothing about it, which is worse than omitting it entirely.
    pairs = []
    for name in triggers:
        entry = FINDINGS.get(name)
        if not entry:
            continue
        finding, action = entry
        pairs.append((f"- {finding}", f"  -> {action}"))

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
        if lines:
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
