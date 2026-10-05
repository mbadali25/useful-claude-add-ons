"""L-0658: whether a `resume: /crew:autopilot --goal <slug>` handoff may be
taken, judged by the goal file, never by the handoff's `branch:` and
`head:` (a goal moves across ticket branches). Small and standalone so
`crew_resume.decide` can ask it without importing `crew_autopilot`; the
same answer feeds `crew_autopilot._handoff_ticket` and status's resume line.

    run_state(root, slug)        -> {"state", "ticket", "reason"}
    handoff_refusal(root, slug)  -> (kind, reason); ("", "") when usable

`state` is T-0056's `run.state` (`running`, `stopped`, `done`), or `none`
(no `run` block: proposed, not started), `missing` (no goal file) or
`unknown` (a file that cannot be read, is not a JSON object, or has a `run`
block that is not one of the three). Only `running` is usable. `unknown` is
could-not-tell, never "no goal". A `stopped` goal is named with its recorded
reason and the command that resumes it, and is never taken.
"""
import json
import os

RUN_STATES = ("running", "stopped", "done")
REASON_MAX = 200


def _clean(text):
    """One line of printable characters, at most REASON_MAX: a recorded stop
    reason is shown, so nothing in it can start a second line."""
    text = text if isinstance(text, str) else ""
    return " ".join("".join(c if c.isprintable() else " " for c in text).split())[:REASON_MAX]


def goal_file(root, slug):
    return os.path.join(root, ".work", "autopilot", f"{slug}.json")


def run_state(root, slug):
    """`{"state", "ticket", "reason"}` -- the module docstring's states."""
    path = goal_file(root, slug)
    if not os.path.lexists(path):
        return {"state": "missing", "ticket": None, "reason": ""}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"state": "unknown", "ticket": None, "reason": "could not read it as JSON"}
    if not isinstance(data, dict):
        return {"state": "unknown", "ticket": None, "reason": "it is not a JSON object"}
    if "run" not in data:
        return {"state": "none", "ticket": None, "reason": ""}
    run = data["run"]
    state = run.get("state") if isinstance(run, dict) else None
    if state not in RUN_STATES:
        return {"state": "unknown", "ticket": None,
                "reason": "its run state is not running, stopped or done"}
    ticket = run.get("ticket")
    return {"state": state, "ticket": ticket if isinstance(ticket, str) else None,
            "reason": _clean(run.get("reason"))}


def handoff_refusal(root, slug, echo=True):
    """`(kind, reason)`: why a `--goal <slug>` handoff may not be taken, or
    `("", "")`. `kind` is the run state that refused it. `echo=False` leaves
    the recorded stop reason out (status prints nothing read from the file)."""
    rel = f".work/autopilot/{slug}.json"
    got = run_state(root, slug)
    state = got["state"]
    if state == "running":
        return "", ""
    if state == "missing":
        return state, f"{rel} does not exist"
    if state == "unknown":
        return state, f"could not read {rel}: {got['reason']}"
    if state == "none":
        return state, f"goal {slug} has not started ({rel} has no run state)"
    if state == "done":
        return state, f"goal {slug} is done"
    why = f": {got['reason']}" if echo and got["reason"] else ""
    return state, (f"goal {slug} stopped{why} - /crew:autopilot --goal {slug} resumes it "
                   "once you choose to")
