#!/usr/bin/env python3
"""#624: which settings, still unmet, keep autopilot from approving a plan itself.

`unmet_text(top, ticket)` is the block `crew_autopilot.approve` appends to a refusal: one line
per unmet prerequisite, each with the key, its value as written and the value needed, or "" when
none is. It is advice only. `crew_autopilot.approval_policy` decides, never reads this, and a refusal
stays a refusal whatever this returns or raises. It lives here, not in `crew_autopilot.py`,
because the `crew_autopilot*.py` modules are frozen (`tests/test_autopilot_frozen.py`).
"""
import json
import re

import crew_common
import crew_config
import crew_ticket
import review_ledger

BOUND = 40  # no echoed config value or exception text is longer than this
_PLAIN = re.compile(r"[A-Za-z0-9_.-]*")


def _bound(text):
    """`text` on one line, cut at BOUND characters with a visible marker."""
    text = " ".join(str(text).split())
    return text if len(text) <= BOUND else text[:BOUND] + "...(truncated)"


def _word(value):
    """A config value as written, safe to put in text the model reads: a bool or a short plain
    word is echoed (bounded); anything else, free text included, only as its type."""
    if value is None:
        return "absent"
    if isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, str) and _PLAIN.fullmatch(value):
        return '"' + _bound(value) + '"'
    return f"<{'string' if isinstance(value, str) else type(value).__name__}>"


def _config_path(top):
    return crew_common.repo_config_file(top, "config.json")


def _layer_note():
    """Names the machine-global layer when it sets `autopilot.mode` too: the stricter wins."""
    try:
        mode = (crew_config.read_global_config().get("autopilot") or {}).get("mode")
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return ""
    return "" if mode is None else (f"; the machine-global file sets it to {_word(mode)} too "
                                    "and the stricter layer wins")


def raw_allow_cli(top):
    """`scope.allowCliApproval` as `.crew/config.json` holds it: a bool as `true`/`false`, any
    other value only as its type (`<string>`), "absent" or "unreadable". Never a decision:
    `crew_ticket.cli_approval_allowed` is."""
    data, state = crew_ticket._read_json(_config_path(top))  # pylint: disable=protected-access
    if state != "ok":
        return "unreadable" if state == "corrupt" else "absent"
    scope = data.get("scope") if isinstance(data, dict) else None
    if not isinstance(scope, dict) or "allowCliApproval" not in scope:
        return "absent"
    value = scope["allowCliApproval"]
    return _word(value) if isinstance(value, bool) else _type_name(value)


def _type_name(value):
    return f"<{'string' if isinstance(value, str) else type(value).__name__}>"


def _mode_line(conf, top):
    """The `autopilot.mode` line: the value as written, a note when it is not a valid one."""
    saw = conf["saw"]
    valid = saw is None or saw in ("off", "plan", "backlog")
    note = "" if valid else " (not a valid value; allowed: off, plan, backlog)"
    return f'autopilot.mode is {_word(saw)}{note}, needs "plan" (or "backlog")' + _layer_note()


def _approval_line(conf, top):
    """The `autopilot.approval` line: the value as written, with why it reads as human."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    block = crew_config.resolve_config(top).get("autopilot")
    raw = block.get("approval", "risk") if isinstance(block, dict) else "risk"
    valid = isinstance(raw, str) and raw in crew_autopilot.POLICIES
    note = "" if valid else " (not a valid value; allowed: human, risk, self)"
    if valid and raw != conf["approval"]:
        note = " (a sleep-schedule override makes it human now)"
    return f'autopilot.approval is {_word(raw)}{note}, needs "self" (or "risk" for a risk: low spec)'


def unmet_prerequisites(top, ticket):
    """Sentences naming each unmet prerequisite of a self-approval; [] when none is. When the
    config cannot be read, every key that depends on it says "could not tell", never a value."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel  # it imports this lazily
    out = []
    path = _config_path(top)
    conf = crew_autopilot.settings(top)
    unreadable = bool(crew_autopilot._unreadable_autopilot(top))  # pylint: disable=protected-access
    if unreadable:
        out.append("autopilot.mode could not be told, because a config file it reads could not be "
                   f"read; fix {path} (and the machine-global file) first")
    elif not conf["armed"]:
        out.append(_mode_line(conf, top))
    if not crew_ticket.cli_approval_allowed(top):
        out.append(f"{crew_autopilot.ALLOW_CLI} is {raw_allow_cli(top)}, needs true (a hand edit "
                   f'of {path}, the file this checkout reads, by the owner: "scope": '
                   '{"allowCliApproval": true}; crew_config.py --set refuses it)')
    if unreadable or conf["approval"] == crew_autopilot.UNKNOWN:
        out.append(f"autopilot.approval could not be told; fix the config file ({path})")
    elif conf["approval"] == crew_autopilot.HUMAN:
        out.append(_approval_line(conf, top))
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
        unmet = [f"the prerequisites could not be listed ({type(exc).__name__}: {_bound(exc)})"]
    if not unmet:
        return ""
    return ("\nFor autopilot to approve plans itself ALL of these must hold; unmet now:\n"
            + "\n".join(f"  - {item}" for item in unmet))
