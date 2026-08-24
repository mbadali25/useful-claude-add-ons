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
    return f"{parts[0]} — " + ", ".join(parts[1:])


def _health_line(state):
    health = state.get("health") or {}
    if health.get("rate") is None:
        return "health: no reviews recorded yet"
    return (
        f"health: {health['rate']} BLOCK+FIX per ticket "
        f"over {health['tickets']} — {health['verdict']}"
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


def render(state):
    """The brief's lines. Empty list means print nothing at all."""
    if not state.get("isCrew"):
        return []
    pm = state.get("pm") or {}
    if not pm.get("enabled", True):
        return []
    return [
        _crew_line(state),
        _health_line(state),
        _work_line(state),
        _knowledge_line(state),
    ]


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
    if not hook_once.claim(root, "pm-brief", payload.get("session_id")):
        return 0

    try:
        lines = render(crew_state.collect(root))
    except Exception:  # pylint: disable=broad-except
        # A SessionStart hook that raises breaks every session opened in this
        # repository. Silence is the only acceptable failure mode.
        return 0
    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
