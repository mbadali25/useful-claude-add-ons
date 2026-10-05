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
import re

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
    try:
        os.lstat(path)
    except FileNotFoundError:
        # A `.work` or `.work/autopilot` entry that is there but no directory
        # (a dangling link, a file) cannot say the goal is absent (review r3).
        for parent in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
            if os.path.lexists(parent) and not os.path.isdir(parent):
                return {"state": "unknown", "ticket": None,
                        "reason": f"{os.path.basename(parent)} is not a directory it can read"}
        return {"state": "missing", "ticket": None, "reason": ""}
    except OSError as exc:  # there or not, it cannot be told: never "missing"
        return {"state": "unknown", "ticket": None,
                "reason": f"could not look it up ({type(exc).__name__})"}
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


_GOAL_RESUME_RE = re.compile(r"^resume:[ \t]*/crew:autopilot[ \t]+--goal[ \t]+"
                             r"([a-z0-9][a-z0-9-]{0,63})[ \t]*$", re.MULTILINE)


def running_goal_handoff(root, handoff_text):
    """Whether the note's one `resume:` line is `/crew:autopilot --goal <slug>`
    for a goal whose run state is `running`: `crew_state.handoff_staleness`
    then skips its branch and head drift checks (L-0658 review r2), as
    `decide` does. Any doubt -- two resume lines, a goal file that cannot be
    read -- is False, so the drift checks still run."""
    text = handoff_text if isinstance(handoff_text, str) else ""
    found = _GOAL_RESUME_RE.findall(text)
    if len(found) != 1 or len(re.findall(r"^resume:", text, re.MULTILINE)) != 1:
        return False
    try:
        return run_state(root, found[0])["state"] == "running"
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False
