#!/usr/bin/env python3
"""#624: which settings, still unmet, keep autopilot from approving a plan itself.

`unmet_text(top, ticket)` is the block `crew_autopilot.approve` appends to a refusal: one line
per unmet prerequisite, each with the key, its value now and the value needed, or "" when none
is. It is advice only. `crew_autopilot.approval_policy` decides, never reads this, and a refusal
stays a refusal whatever this returns or raises. It lives here, not in `crew_autopilot.py`,
because the `crew_autopilot*.py` modules are frozen (`tests/test_autopilot_frozen.py`).
"""
import json

import crew_common
import crew_ticket
import review_ledger


def raw_allow_cli(top):
    """`scope.allowCliApproval` as `.crew/config.json` holds it: its JSON text, "absent" or
    "unreadable". Never a decision: `crew_ticket.cli_approval_allowed` is."""
    data, state = crew_ticket._read_json(  # pylint: disable=protected-access
        crew_common.repo_config_file(top, "config.json"))
    if state != "ok":
        return "unreadable" if state == "corrupt" else "absent"
    scope = data.get("scope") if isinstance(data, dict) else None
    if not isinstance(scope, dict) or "allowCliApproval" not in scope:
        return "absent"
    return json.dumps(scope["allowCliApproval"])


def unmet_prerequisites(top, ticket):
    """Sentences naming each unmet prerequisite of a self-approval; [] when none is."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel  # it imports this lazily
    out = []
    conf = crew_autopilot.settings(top)
    if not conf["armed"]:
        out.append(f'autopilot.mode is "{conf["mode"]}", needs "plan"')
    if not crew_ticket.cli_approval_allowed(top):
        out.append(f"{crew_autopilot.ALLOW_CLI} is {raw_allow_cli(top)}, needs true (a hand edit "
                   'of .crew/config.json by the owner: "scope": {"allowCliApproval": true}; '
                   "crew_config.py --set refuses it)")
    if conf["approval"] == crew_autopilot.HUMAN:
        out.append('autopilot.approval is "human", needs "self" (or "risk" for a risk: low spec)')
    elif conf["approval"] == crew_autopilot.UNKNOWN:
        out.append("autopilot.approval could not be read; fix the config file it names")
    try:
        if review_ledger.status(top, ticket).get("state") == review_ledger.UNKNOWN:
            out.append("the review ledger is unreadable; repair it")
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        out.append("the review ledger could not be read; repair it")
    return out


def unmet_text(top, ticket):
    """The refusal's trailing block, or "" when nothing is unmet. Never raises."""
    try:
        unmet = unmet_prerequisites(top, ticket)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        unmet = [f"the prerequisites could not be listed ({type(exc).__name__}: {exc})"]
    if not unmet:
        return ""
    return ("\nFor autopilot to approve plans itself ALL of these must hold; unmet now:\n"
            + "\n".join(f"  - {item}" for item in unmet))
