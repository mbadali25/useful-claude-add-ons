"""T-0056: a running autopilot goal is written into every handoff -- the goal
file's run state and the one function that decides a handoff's `resume:`
line. Split out of `crew_autopilot.py` (pylint's module-length limit);
`crew_autopilot.py goal-mark` and `handoff-resume` dispatch here.

    python3 crew_autopilot.py goal-mark --root . --goal <slug> --state <s>
                                        [--ticket <id>] [--reason-file <path>]
    python3 crew_autopilot.py handoff-resume --root . [--ticket <id>]

THE RUN STATE. `goal_mark` writes the goal file's `run` block,
`{"state", "ticket", "reason", "at"}` with `state` one of RUN_STATES, through
a temp file in the same directory and `os.replace`, under the goal lock
(`crew_autopilot_backlog.goal_lock`); every other key is written back as it
was read. L-0541's `goal-run` marks `running` (with the ticket it picked),
`done` (the goal is done) and `stopped` (any other stop it makes); the
command marks `running` at each phase start and `stopped` at each stop of a
goal run. A goal file with no `run` block (proposed, not started) is not
running.

THE LINE. `handoff_resume(root, ticket)` is the only place that decides a
handoff's `resume:` line, and every writer asks it: autopilot's low-context
stop, `/crew:handoff` and the PreCompact skeleton (`handoff-write.sh`/`.ps1`).
Exactly one running goal and no unknown goal file: the goal form, even when
a ticket is given. No running goal and no unknown: the ticket form for a
ticket that has a folder, else `resume: none`. Several running goals, or any
goal file that cannot be read: `resume: none`, kind `unknown`, naming them --
never the ticket form, which would drop the goal silently. Every line is
rendered by `crew_resume.render`, so it is the grammar's own text.

`goal-mark` prints `marked=1`, or `marked=0 reason=<r>` (exit 2).
`handoff-resume` prints the `resume:` line first, then `kind=<k> reason=<r>`,
exit 0; a crash prints `resume: none` and `kind=unknown`, never a traceback
alone.
"""
import datetime
import importlib
import json
import os
import sys

import crew_autopilot as ap
import crew_goal_state as goal_state
import crew_ticket
from crew_common import read_text

RUN_STATES = ("running", "stopped", "done")
NONE = "resume: none"
KINDS = ("goal", "ticket", "none", "unknown")


class MarkError(ValueError):
    """A goal_mark that is refused; nothing was written."""


def _goal():
    return importlib.import_module("crew_autopilot_goal")


def _backlog():
    return importlib.import_module("crew_autopilot_backlog")


def _top(root):
    return crew_ticket.toplevel(root) or os.path.abspath(root)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def goal_mark(root, slug, state, ticket=None, reason="", only_if_running=False):
    """Write the goal file's `run` block; MarkError (nothing written) for a
    state outside RUN_STATES, a slug outside T-0006's grammar, a bad ticket
    id, or a goal file that is missing, unreadable or not a JSON object.
    `only_if_running` (L-0659 review r2: a goal-run the goal file chose, not
    the owner) refuses unless the goal still reads `running` under the lock,
    so a stop marked meanwhile is never overwritten. A written mark removes a
    `<slug>.stop` file (`stop_mark_fallback`); one that cannot be removed is
    a MarkError."""
    goal_mod = _goal()
    if state not in RUN_STATES:
        raise MarkError(f"state {state!r} is not one of {'|'.join(RUN_STATES)}")
    if not goal_mod._goal_slug_ok(slug):  # pylint: disable=protected-access
        raise MarkError(f"goal slug {slug!r} is not [a-z0-9][a-z0-9-]{{0,63}}")
    if ticket:
        try:
            crew_ticket.check_ticket(ticket)
        except crew_ticket.TicketError as exc:
            raise MarkError(str(exc)) from exc
    top = _top(root)
    path = goal_mod.goal_path(top, slug)
    try:
        with _backlog().goal_lock(top, slug):
            text = read_text(path)
            if text is None:
                raise MarkError(f".work/autopilot/{slug}.json is not there or could not be read")
            try:
                data = json.loads(text)
            except ValueError as exc:
                raise MarkError(f".work/autopilot/{slug}.json is not JSON") from exc
            if not isinstance(data, dict):
                raise MarkError(f".work/autopilot/{slug}.json is not a JSON object")
            if only_if_running and goal_state.run_state(top, slug)["state"] != "running":
                raise MarkError(f"goal {slug} is no longer running - /crew:autopilot --goal "
                                f"{slug} resumes it once you choose to")
            data["run"] = {"state": state, "ticket": ticket or None,
                           "reason": ap._one_line(reason or ""), "at": _now()}
            goal_mod._write_json_atomic(path, data)  # pylint: disable=protected-access
            try:
                os.remove(goal_state.stop_file(top, slug))
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise MarkError(f".work/autopilot/{slug}.stop could not be removed "
                                f"({type(exc).__name__}); the goal still reads stopped") from exc
    except goal_mod.GoalError as exc:
        raise MarkError(str(exc)) from exc


def stop_mark_fallback(root, slug, state, reason):
    """T-0056 review r4: a `stopped`/`done` mark that could not reach the goal
    file is written to `.work/autopilot/<slug>.stop` instead (whole text to a
    temp file, then os.replace), which every reader takes over a `running`
    goal file. Raises OSError when that cannot be written either."""
    path = goal_state.stop_file(_top(root), slug)
    text = json.dumps({"state": state, "reason": ap._one_line(reason or ""), "at": _now()})
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temp, path)


def read_reason_file(path):
    """`goal-mark --reason-file`: the stop reason the command wrote with its
    Write tool, so the reason (it can quote ticket text) is never put on a
    command line. Its first 200 characters, one line."""
    with open(path, encoding="utf-8") as handle:
        return ap._one_line(handle.read(4096))[:200]


def running_goals(root):
    """`{"running", "stopped", "done", "unknown"}`: the slugs of this
    checkout's goal files by their `run.state`; `unknown` holds
    `".work/autopilot/<slug>.json (<why>)"` for a file that cannot be read,
    is not a JSON object, or has a `run` block with a missing or unlisted
    state -- never dropped, never `done`. A file with no `run` block is in
    none of the lists; a staged `*.proposal.json` is not a goal file."""
    out = {"running": [], "stopped": [], "done": [], "unknown": []}
    top = _top(root)
    folder = os.path.join(top, ".work", "autopilot")
    slug_ok = _goal()._goal_slug_ok  # pylint: disable=protected-access
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".json"))
    except FileNotFoundError:
        names = []
        # A `.work` or `.work/autopilot` entry that is there but no directory
        # (a dangling link, a file) cannot say there are no goals (review r1).
        for parent in (folder, os.path.dirname(folder)):
            if os.path.lexists(parent) and not os.path.isdir(parent):
                out["unknown"].append(f"{os.path.relpath(parent, top)} (there, but not a "
                                      "directory it can read)".replace(os.sep, "/"))
                break
    except OSError as exc:  # there, and cannot be listed: never "no goals"
        out["unknown"].append(f".work/autopilot/ (could not list it: {type(exc).__name__})")
        names = []
    for path in (os.path.join(folder, n) for n in names):
        name = os.path.basename(path)[:-len(".json")]
        if name.lower().endswith(".proposal") or not slug_ok(name.lower()):
            continue
        rel = f".work/autopilot/{name}{os.path.basename(path)[-len('.json'):]}"
        if os.path.basename(path) != name.lower() + ".json":
            # On a case-insensitive filesystem `--goal <slug>` opens this file; on a
            # case-sensitive one it does not: either way it is never "no goal" (review r1).
            out["unknown"].append(f"{rel} (a goal file name that is not lowercase: rename it "
                                  f"to {name.lower()}.json)")
            continue
        text = read_text(path)
        try:
            data = json.loads(text) if text is not None else None
        except ValueError:
            out["unknown"].append(f"{rel} (could not read it as JSON)")
            continue
        if not isinstance(data, dict):
            out["unknown"].append(f"{rel} (could not read it)" if text is None
                                  else f"{rel} (not a JSON object)")
            continue
        if "run" not in data:
            continue
        run = data["run"]
        state = run.get("state") if isinstance(run, dict) else None
        if state not in RUN_STATES:
            out["unknown"].append(f"{rel} (its run state is {state!r}, not one of "
                                  f"{'|'.join(RUN_STATES)})")
            continue
        try:  # L-0659 review r3: a run state on a file that is not a goal is not one
            _goal().read_goal(top, name)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
            out["unknown"].append(f"{rel} (not a goal file: {ap._one_line(str(exc))[:120]})")
            continue
        override = goal_state.stop_override(top, name) if state == "running" else None
        if override and override["state"] == "unknown":
            out["unknown"].append(f".work/autopilot/{name}.stop (could not read it)")
            continue
        out[override["state"] if override else state].append(name)
    return out


def _armed(top):
    """Whether autopilot is armed here (T-0056 review r2): a goal file left
    `running` by a run that autopilot can no longer continue is not taken as
    running. A settings read that raises is not armed."""
    try:
        return ap.settings(top)["armed"] is True
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False


def _render(command, kind, arg):
    resume = importlib.import_module("crew_resume")
    return "resume: " + resume.render({"ok": True, "command": command, "kind": kind, "arg": arg})


def handoff_resume(root, ticket=None):
    """`{"line", "kind", "reason"}` -- the module docstring's table."""
    top = _top(root)
    goals = running_goals(top)
    if goals["unknown"]:
        return {"line": NONE, "kind": "unknown",
                "reason": "could not tell whether a goal is running: "
                          + "; ".join(goals["unknown"])}
    if len(goals["running"]) > 1:
        return {"line": NONE, "kind": "unknown",
                "reason": "could not tell which goal is running: "
                          + ", ".join(goals["running"])}
    if goals["running"] and not _armed(top):
        return {"line": NONE, "kind": "unknown",
                "reason": f"goal {goals['running'][0]} says running, but autopilot is not armed "
                          "(or its settings could not be read), so whether it still runs "
                          "could not be told"}
    if goals["running"]:
        slug = goals["running"][0]
        return {"line": _render(ap.AUTOPILOT, "goal", slug), "kind": "goal",
                "reason": f"goal {slug} is running"}
    if ticket:
        crew_ticket.check_ticket(ticket)
        if os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
            return {"line": _render(ap.AUTOPILOT, "ticket", ticket), "kind": "ticket",
                    "reason": f"no goal is running; {ticket} has a folder"}
        return {"line": NONE, "kind": "none",
                "reason": f"no goal is running and {ticket} has no .work/tickets/ folder"}
    return {"line": NONE, "kind": "none", "reason": "no goal is running and no ticket given"}


def main(args):
    if args.action == "handoff-resume":
        try:
            result = handoff_resume(args.root, args.ticket or None)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
            result = {"line": NONE, "kind": "unknown", "reason": ap._failure(exc)}
        sys.stdout.write(result["line"] + "\n"
                         + ap._one_line(ap._line(kind=result["kind"], reason=result["reason"]))
                         + "\n")
        return 0
    try:
        reason = read_reason_file(args.reason_file) if args.reason_file else args.reason
        goal_mark(args.root, args.goal, args.state, args.ticket or None, reason)
    except MarkError as exc:
        sys.stdout.write(ap._one_line(ap._line(marked=0, reason=str(exc))) + "\n")
        return 2
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        sys.stdout.write(ap._one_line(ap._line(marked=0, reason=ap._failure(exc))) + "\n")
        return 1
    sys.stdout.write("marked=1\n")
    return 0


def add_parsers(sub):
    """`goal-mark` and `handoff-resume` on crew_autopilot.py's subparsers."""
    mark = sub.add_parser("goal-mark")
    mark.add_argument("--root", default=".")
    mark.add_argument("--goal", required=True)
    mark.add_argument("--state", required=True)
    mark.add_argument("--ticket", default="")
    mark.add_argument("--reason", default="")
    mark.add_argument("--reason-file", default="")
    line = sub.add_parser("handoff-resume")
    line.add_argument("--root", default=".")
    line.add_argument("--ticket", default="")
