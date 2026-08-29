"""Gate for every write/destructive tool across all four servers.

Read-only by default (constraint from mcp-servers/README.md): a mutating
tool only takes action when BOTH are true -

1. an explicit environment flag is set on the server process (``1``,
   ``true``, or ``yes``), AND
2. the tool call itself passes ``confirm=True``.

Either being false returns a preview instead of acting - same shape either
way, so a caller always sees exactly what a write *would* do, and how many
things it would touch, before opting in twice.
"""

from __future__ import annotations

import os
from typing import Any


def writes_enabled(env_flag: str) -> bool:
    return os.environ.get(env_flag, "").strip().lower() in ("1", "true", "yes")


def gate(
    env_flag: str,
    *,
    confirm: bool,
    action: str,
    targets: list[Any],
) -> dict[str, Any] | None:
    """Return a blocked/dry-run response, or ``None`` if the caller may proceed.

    Call this first in every mutating tool function and return its result
    immediately if it is not ``None``.
    """
    if not confirm:
        return {
            "wouldExecute": False,
            "action": action,
            "affectedCount": len(targets),
            "targets": targets,
            "note": "No changes made. Re-call with confirm=true to execute.",
        }
    if not writes_enabled(env_flag):
        return {
            "wouldExecute": False,
            "blocked": True,
            "action": action,
            "affectedCount": len(targets),
            "targets": targets,
            "note": (
                f"Write tools are disabled on this server. Set {env_flag}=1 "
                "in its environment (see mcp-servers/README.md) to enable, "
                "then retry with confirm=true."
            ),
        }
    return None
