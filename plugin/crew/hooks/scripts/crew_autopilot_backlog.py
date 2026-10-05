"""L-0541: a goal's tickets, worked one at a time -- mint on the split
approval, the picker, the run record and its caps, and the per-ticket
approval. Split out of `crew_autopilot.py` (pylint's module-length limit);
`crew_autopilot_goal.py` dispatches `goal-approve` and `goal-run` here.

    python3 crew_autopilot.py goal-approve --root . --goal <slug> [--ticket <id>]
    python3 crew_autopilot.py goal-run --root . --goal <slug> [--session <id>]
                                       [--transcript <path>] [--json]

MINT. Once `split_approved` says yes, `goal-approve` mints every proposed
ticket that has no id yet, in list order, with T-0019's `crew_ticket.mint`
(status `ready`; mint itself is unchanged and takes no risk). Each ticket's
direction.md names the goal file, the ticket's place in the list
(`goal-ticket: <slug> <n>/<m>`, MARK), its risk and its dependencies, and
each id is written to the goal file's `tickets[].id` as it returns. A
`TicketError` stops, naming the tickets minted and the ones not; a re-run
mints only what is missing, and adopts a folder whose direction.md already
carries the MARK (a mint whose id never reached the goal file), so no
ticket is minted twice.

THE PICKER. `next_goal_ticket` walks the tickets in list order (the
proposal's dependency order): a closed one (INDEX `done`, `closed`,
`merged`, `shipped`, `complete`, `completed`, or a spec header `done`) is
passed; one the owner settled (`cancelled`, `superseded`) is passed too,
unless a ticket still to work depends on it, which stops naming it; one
waiting on the owner (`needs-owner`) stops naming it; one whose state
cannot be told (no INDEX row, rows that disagree, an unreadable spec)
stops; the first open one is the answer. None left: the goal is done.

THE RUN. `goal-run` is the goal form of `resume`: armed only under
`autopilot.mode` `plan` or `backlog`, it asks `resume_target(goal=slug)`
for the ticket (the picker, the active-pointer rule), then holds the run to
its caps and records the ticket in the goal file's `runs` entry for this
session (`{"started", "session", "tickets"}`). `plan` works one ticket per
run; `backlog` goes on to the next while `autopilot.maxTicketsPerRun`
(tickets started in this session's run) and `autopilot.maxTokensPerSession`
(input + output tokens in this session's transcript) allow. A transcript
that cannot be found or read is could-not-tell, which stops. Every stop but
"the goal is done" ends with RESUME, the line a handoff carries.

PER-TICKET APPROVAL. `goal-approve --ticket <id>` runs T-0010's `approve`
for that one minted ticket of the goal: exit 0 is its `self-approved`
line; anything else stops with exactly `/crew:approve <id>`, then RESUME.
Never a line naming two ids, a range or `--confirm`.

Writes: the tickets `crew_ticket.mint` writes, and the goal file
`.work/autopilot/<slug>.json` (whole text to a temp file, then os.replace),
each write under `.work/autopilot/<slug>.lock` (an exclusive create). A lock
that is there stops, naming its path: never waited past LOCK_WAIT, never
broken.
"""
import contextlib
import datetime
import glob
import importlib
import os
import re
import time

import crew_autopilot as ap
import crew_state
import crew_ticket
from crew_common import read_text

CLOSED = ("done", "closed", "merged", "shipped", "complete", "completed")
SETTLED = ("cancelled", "superseded")
WAITING = (ap.NEEDS_OWNER,)
HEADER_CLOSED = ("done",)
TOKEN_FIELDS = ("input_tokens", "output_tokens")
RESUME = "resume: /crew:autopilot --goal {slug}"
MARK = "goal-ticket: {slug} {n}/{m}"
LOCK_WAIT = 5.0
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _goal():
    return importlib.import_module("crew_autopilot_goal")


def _top(root):
    return crew_ticket.toplevel(root) or os.path.abspath(root)


def caps(block, warnings):
    """`{"maxTicketsPerRun", "maxTokensPerSession"}` from the autopilot block:
    each a positive int, else its AUTOPILOT_DEFAULTS value with a warning."""
    out = {}
    for key in ap.BACKLOG_CAPS:
        default = crew_state.AUTOPILOT_DEFAULTS[key]
        value = block.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            warnings.append(f"autopilot.{key} is {value!r}, not a positive integer; "
                            f"using {default}")
            value = default
        out[key] = value
    return out


@contextlib.contextmanager
def goal_lock(root, slug):
    """Hold `.work/autopilot/<slug>.lock` (an exclusive create) around a goal
    file write. Taken by another writer for LOCK_WAIT seconds: GoalError,
    naming the file -- never broken, because a crashed holder and a live one
    look the same from here."""
    path = _goal().goal_path(root, slug)[:-len(".json")] + ".lock"
    deadline = time.monotonic() + LOCK_WAIT
    while True:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise _goal().GoalError(  # pylint: disable=raise-missing-from
                    f"the goal file is locked by {ap._rel(_top(root), path)}: another run "
                    "is writing it, or one that crashed left it - remove it only when no "
                    "autopilot run is working this goal")
            time.sleep(0.1)
    try:
        yield
    finally:
        os.remove(path)


def ticket_state(top, ticket):
    """`(state, why)`: `closed`, `settled` (cancelled or superseded), `waiting`
    (needs-owner), `open`, or `unknown` with why -- never read as open."""
    row = ap._index_row(top, ticket)  # pylint: disable=protected-access
    if row["other"]:
        return "unknown", f"the INDEX rows for {ticket} disagree"
    status = row["status"]
    if status is None:
        return "unknown", (f"{ticket} has no row in .work/INDEX.md"
                           + (f" ({row['why']})" if row["why"] else ""))
    if status in CLOSED:
        return "closed", ""
    if status in SETTLED:
        return "settled", f"{ticket} is {status} in .work/INDEX.md"
    if status in WAITING:
        return "waiting", f"{ticket} is {status} in .work/INDEX.md: it waits on the owner"
    spec = os.path.join(crew_ticket.ticket_dir(top, ticket), "spec.md")
    text = read_text(spec)
    if text is None and os.path.lexists(spec):
        return "unknown", f"{ap._rel(top, spec)} exists but could not be read"
    header = ap._header_status(text) if text is not None else None  # pylint: disable=protected-access
    if header in HEADER_CLOSED:
        return "closed", ""
    if header in SETTLED:
        return "settled", f"{ticket}'s spec.md header is {header}"
    return "open", ""


def next_goal_ticket(root, slug, goal=None):
    """`{"ticket", "index", "done", "stop", "reason"}` -- the module
    docstring's picker. `goal`: a read the caller already holds."""
    top = _top(root)

    def stop(reason, done=False):
        return {"ticket": None, "index": None, "done": done, "stop": True, "reason": reason}
    try:
        goal = goal if goal is not None else _goal().read_goal(top, slug)
    except _goal().GoalError as exc:
        return stop(str(exc))
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return stop(f"could not read goal {slug} ({type(exc).__name__}: {exc})")
    tickets = goal["tickets"]
    states, settled = {}, []
    for n, entry in enumerate(tickets):
        place = f"ticket {n + 1} of {len(tickets)} of goal {slug}"
        ticket = entry.get("id")
        if not isinstance(ticket, str) or not ap._INDEX_ID.fullmatch(ticket):  # pylint: disable=protected-access
            return stop(f"{place} ({ap._one_line(entry['title'])}) is not minted: the split "
                        f"approval mints it (crew_autopilot.py goal-approve --root . "
                        f"--goal {slug})")
        state, why = ticket_state(top, ticket)
        states[n] = (ticket, state, why)
        if state == "closed":
            continue
        if state == "unknown":
            return stop(f"could not tell whether {ticket} ({place}) is closed: {why}")
        if state == "waiting":
            return stop(f"{why} ({place}); the goal stops here")
        if state == "settled":
            settled.append(ticket)
            continue
        blocked = [states[d] for d in entry["depends_on"] if states[d][1] != "closed"]
        if blocked:
            dep, dep_state, dep_why = blocked[0]
            return stop(f"{ticket} ({place}) depends on {dep}, which is {dep_state}: "
                        f"{dep_why or 'not closed'} - the owner decides")
        return {"ticket": ticket, "index": n, "done": False, "stop": False,
                "reason": f"{ticket}: {place}"}
    note = f" ({', '.join(settled)} settled without work)" if settled else ""
    return stop(f"every ticket of goal {slug} is closed: the goal is done{note}", done=True)


def handoff_pick(top, slug):
    """`_handoff_ticket`'s answer for a `--goal <slug>` line: `(ticket, hint,
    stop_reason, why)` from `next_goal_ticket`."""
    pick = next_goal_ticket(top, slug)
    return pick["ticket"], f"{ap.AUTOPILOT} {ap.GOAL_FLAG} {slug}", pick["stop"] and pick["reason"], ""


def closed_in_goal(top, slug, ticket):
    """Whether `ticket` is a minted ticket of the goal that is closed or settled:
    the one active pointer a goal's next pick may replace. Any doubt is False."""
    try:
        ids = [t["id"] for t in _goal().read_goal(top, slug)["tickets"]]
        return ticket in ids and ticket_state(top, ticket)[0] in ("closed", "settled")
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False


def route_goal(top, rest):
    """`route_args` for `--goal <slug>` and `run --goal <slug>`: `sub=run` with
    `goal`, or a stop -- under a focus (T-0020), or anything but one slug in
    T-0006's grammar after the flag."""
    base = {"sub": "run", "stop": True, "ticket": "", "goal": ""}
    refusal = ap.focus_guard(top, "goal")
    if refusal:
        return dict(base, reason=refusal)
    if len(rest) != 1 or not _goal()._goal_slug_ok(rest[0]):  # pylint: disable=protected-access
        return dict(base, reason=f"{ap.AUTOPILOT} {ap.GOAL_FLAG} takes one goal slug "
                                 "([a-z0-9][a-z0-9-]{0,63})")
    return dict(base, stop=False, goal=rest[0], reason="")


# --- mint ---------------------------------------------------------------------

def _direction(goal, slug, n):
    tickets = goal["tickets"]
    entry = tickets[n]
    deps = ", ".join(f"ticket {d + 1}" + (f" ({tickets[d]['id']})" if tickets[d].get("id")
                                          else "") for d in entry["depends_on"]) or "none"
    clean = _goal()._clean_line  # pylint: disable=protected-access
    return "\n".join([
        f"Minted by /crew:autopilot for goal `{slug}` (.work/autopilot/{slug}.json), "
        f"ticket {n + 1} of {len(tickets)}, after its split approval.",
        "",
        MARK.format(slug=slug, n=n + 1, m=len(tickets)),
        f"risk: {clean(entry['risk'])}",
        f"depends on: {deps}",
        "",
        f"## {clean(entry['title'])}",
        "",
        f"Goal: {clean(goal['goal'])[:500]}",
        f"Done when: {clean(goal['proposal']['done_condition'])[:500]}",
        "",
        "Spec, plan and approval follow as for any ticket; nothing here approves it.",
        ""])


def _adopt(top, slug, n, m):
    """The ticket folder whose direction.md already carries this ticket's MARK
    line (a mint whose id never reached the goal file), or None. Two: GoalError."""
    mark = MARK.format(slug=slug, n=n, m=m)
    found = []
    for direction in sorted(glob.glob(os.path.join(glob.escape(top), ".work", "tickets", "*",
                                                   "direction.md"))):
        text = read_text(direction) or ""
        if mark in (line.strip() for line in text.splitlines()):
            found.append(os.path.basename(os.path.dirname(direction)))
    if len(found) > 1:
        raise _goal().GoalError(f"{', '.join(found)} all carry `{mark}`; the human keeps one")
    return found[0] if found else None


def mint_goal(root, slug):
    """`{"minted": [(n, id, title)], "unminted": [(n, title)], "stop", "reason",
    "warnings"}`. The caller holds the split approval (`split_approved`)."""
    goal_mod = _goal()
    top = _top(root)
    out = {"minted": [], "unminted": [], "stop": False, "reason": "", "warnings": []}
    with goal_lock(top, slug):
        goal = goal_mod.read_goal(top, slug)
        digest = goal_mod.goal_digest(goal)
        tickets = goal["tickets"]
        for n, entry in enumerate(tickets):
            if entry["id"]:
                out["minted"].append((n + 1, entry["id"], entry["title"]))
                continue
            try:
                ticket = _adopt(top, slug, n + 1, len(tickets))
                if ticket is None:
                    got = crew_ticket.mint(top, entry["title"], status="ready",
                                           direction=_direction(goal, slug, n))
                    ticket = got["ticket"]
                    out["warnings"] += list(got.get("warnings") or [])
                    if got.get("status") != "ready":
                        out["warnings"].append(f"{ticket} was minted at {got.get('status')}, "
                                               "not ready")
                if goal_mod.goal_digest(goal_mod.read_goal(top, slug)) != digest:
                    raise goal_mod.GoalError("the proposal changed while its tickets were "
                                             "being minted")
                entry["id"] = ticket
                goal_mod._write_json_atomic(goal_mod.goal_path(top, slug), goal)  # pylint: disable=protected-access
            except (crew_ticket.TicketError, goal_mod.GoalError, OSError) as exc:
                out["unminted"] = [(k + 1, t["title"]) for k, t in enumerate(tickets)
                                   if k >= n and not t["id"]]
                return dict(out, stop=True, reason=f"minting ticket {n + 1} of "
                            f"{len(tickets)} stopped: {exc}")
            out["minted"].append((n + 1, ticket, entry["title"]))
    return out


def mint_text(result):
    lines = [ap._one_line(f"minted: ticket {n} {ticket} - {title}")
             for n, ticket, title in result["minted"]]
    if result["stop"]:
        lines.append(ap._one_line(f"stop: {result['reason']}"))
        lines += [ap._one_line(f"unminted: ticket {n} - {title}")
                  for n, title in result["unminted"]]
    return lines + [ap._one_line(f"warning: {w}") for w in result["warnings"]]


# --- the run --------------------------------------------------------------------

def transcript_for(session):
    """`(path, why)`: this session's transcript,
    `<CLAUDE_CONFIG_DIR or ~/.claude>/projects/*/<session>.jsonl`, exactly one."""
    if not isinstance(session, str) or not _SESSION_RE.match(session):
        return None, f"no usable session id ({session!r})"
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"),
                                                               ".claude")
    found = glob.glob(os.path.join(glob.escape(base), "projects", "*",
                                   glob.escape(session) + ".jsonl"))
    if len(found) != 1:
        return None, (f"{len(found)} transcripts named {session}.jsonl under "
                      f"{os.path.join(base, 'projects')}")
    return found[0], ""


def session_tokens(transcript):
    """`(tokens, why)`: input + output tokens in `transcript`, or None with why."""
    tokens = importlib.import_module("crew_metrics").transcript_tokens(
        transcript, fields=TOKEN_FIELDS)
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        return None, f"the transcript {transcript} could not be read for token usage"
    return tokens, ""


def _runs(goal):
    runs = goal.get("runs")
    if not isinstance(runs, list) or not all(
            isinstance(r, dict) and isinstance(r.get("tickets"), list) for r in runs):
        raise _goal().GoalError("the goal file's runs is not a list of runs")
    return runs


def goal_run(root, slug, session=None, transcript=None):
    """`resume`'s fields (`ticket`, `source`, `stop`, `activate`, `reason`,
    ...) plus `goal`, `done`, `run` -- the module docstring's run."""
    top = _top(root)
    base = {"ticket": None, "source": f"goal:{slug}", "stop": True, "hint": "",
            "disagreement": "", "fallthrough": [], "next": None, "activate": False,
            "goal": slug, "done": False, "run": None}
    conf = ap.settings(top)
    if not conf["armed"]:
        return dict(base, reason="autopilot.mode is not plan or backlog, so no goal runs")
    picked = ap.resume_target(top, goal=slug)
    if picked["stop"]:
        return dict(base, **{k: picked[k] for k in ("source", "fallthrough")},
                    done=bool(picked.get("done")), reason=picked["reason"])
    ticket = picked["ticket"]
    if not transcript:
        transcript, why = transcript_for(session)
        if transcript is None:
            return dict(base, reason=f"could not tell this session's token use ({why}); "
                                     "autopilot.maxTokensPerSession cannot be held")
    tokens, why = session_tokens(transcript)
    if tokens is None:
        return dict(base, reason=f"could not tell this session's token use ({why})")
    limit = conf["maxTokensPerSession"]
    if tokens > limit:
        return dict(base, reason=f"this session has used {tokens} input + output tokens, "
                                 f"over autopilot.maxTokensPerSession ({limit})")
    goal_mod = _goal()
    try:
        with goal_lock(top, slug):
            goal = goal_mod.read_goal(top, slug)
            runs = _runs(goal)
            key = session if isinstance(session, str) and session else f"transcript:{transcript}"
            run = next((r for r in runs if r.get("session") == key), None)
            worked = list(run["tickets"]) if run else []
            if ticket not in worked:
                cap = conf["maxTicketsPerRun"]
                if conf["mode"] != ap.BACKLOG and worked:
                    return dict(base, reason=f"autopilot.mode is plan: one ticket per run, "
                                             f"and this run worked {worked[-1]}; "
                                             f"`backlog` goes on to {ticket}")
                if len(worked) >= cap:
                    return dict(base, reason=f"this run has started {len(worked)} tickets "
                                             f"({', '.join(worked)}), "
                                             f"autopilot.maxTicketsPerRun is {cap}")
                if run is None:
                    run = {"started": datetime.datetime.now(datetime.timezone.utc)
                                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "session": key, "tickets": []}
                    runs.append(run)
                run["tickets"].append(ticket)
                goal_mod._write_json_atomic(goal_mod.goal_path(top, slug), goal)  # pylint: disable=protected-access
                worked = list(run["tickets"])
    except (goal_mod.GoalError, OSError) as exc:
        return dict(base, reason=f"could not record the run in the goal file: {exc}")
    return dict(picked, goal=slug, done=False,
                run={"tickets": worked, "maxTicketsPerRun": conf["maxTicketsPerRun"],
                     "tokens": tokens, "maxTokensPerSession": limit})


def goal_run_text(result):
    text = ap._line(ticket=result["ticket"] or "", source=result["source"],
                    stop=int(result["stop"]), activate=int(result["activate"]),
                    goal=result["goal"], reason=result["reason"])
    text += "".join(f"\nfell through: {w}" for w in result.get("fallthrough") or [])
    if result.get("run"):
        run = result["run"]
        text += "\n" + ap._line(tickets=f"{len(run['tickets'])}/{run['maxTicketsPerRun']}",
                                tokens=f"{run['tokens']}/{run['maxTokensPerSession']}")
    if result["stop"] and not result["done"]:
        text += "\n" + RESUME.format(slug=result["goal"])
    return text


# --- per-ticket approval ------------------------------------------------------------

def ticket_approve(root, slug, ticket):
    """(exit code, text): T-0010's `approve` for one minted ticket of the goal."""
    crew_ticket.check_ticket(ticket)
    top = _top(root)
    goal = _goal().read_goal(top, slug)
    ids = [t["id"] for t in goal["tickets"]]
    resume = RESUME.format(slug=slug)
    if ticket not in ids:
        return 2, f"refused: {ticket} is not a minted ticket of goal {slug}\n{resume}"
    code, text = ap.approve(top, ticket)
    if code == 0:
        return 0, text
    return code, f"{text}\n/crew:approve {ticket}\n{resume}"
