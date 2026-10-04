"""Plain-text lifecycle routing: which `/crew:` command a short prompt asks for.

    python3 crew_route.py settings --root . [--json]
    python3 crew_route.py decide --root . --prompt "<text>" [--json]

T-0023. When `route.enabled` is exactly `true`, crew's UserPromptSubmit
context hook (`crew_context.build`) calls `decide` on the prompt and, unless
the answer is `none`, puts `render`'s one line FIRST in the turn's context.
Claude then runs that command's procedure through the Skill tool. This module
runs nothing, blocks nothing and writes nothing.

## The table (`PHRASES`) -- the single definition; T-0025 reads it

A prompt routes only when the WHOLE prompt, normalised, matches a row: strip,
collapse whitespace, drop one trailing `.` or `!`, drop one leading `please`,
`ok`, `now` or `let's`; matched case-insensitively. Never a match inside a
longer sentence, never a question (`?` is not dropped), never a prompt with a
line break, over MAX_PROMPT_CHARS, starting with `/`, `<` or a backtick.
`AMBIGUOUS` phrases ("do it", "yes", bare "done"...) route nowhere whatever a
row says: they usually answer Claude's last question, and the conversation is
the better judge of that.

No row routes to `/crew:approve`, and no answer ever names it as a route:
approval is the human's to type (T-0024 owns group approval).

## decide -- route, ask or none

  no row matches                                  none   (no line at all)
  status                                          route  /crew:status
  brainstorm <topic>                              route  /crew:brainstorm <topic>
  explicit id with a .work/tickets/<id>/ folder   route
  explicit id without one                         ask    "no such ticket"
  it/this/nothing, active-ticket pointer          route  that ticket
  it/this/nothing, broken pointer                 ask    naming the pointer problem
  it/this/nothing, exactly one open INDEX ticket  route  that ticket
  it/this/nothing, several open INDEX tickets     ask    listing them
  it/this/nothing, none                           ask    "no open ticket"
  continue: next_phase not a stop                 route  the command it names
  continue: next_phase a stop, raises, or names
            /crew:approve                         ask    with the reason

## T-0057 -- the autopilot rows

Five rows name `/crew:autopilot` subcommands. Whether a subcommand runs is
`crew_autopilot.route`'s answer at decide time; the table holds no copy, so a
row goes live the day its ticket adds the name to `crew_autopilot.AVAILABLE`.

  route raises or answers an unknown shape        ask    "could not be read"
  route does not know the name (sub empty)        none   (no line at all)
  route stops (not landed yet)                    ask    unavailable: answer the
                                                         prompt as written
  autopilot status [<id>]                         route  (an id resolves as above)
  focus on <id>                                   route, or ask with no folder
  take care of / handle / work toward <text>      route  `<command> <text>`, or ask
                                                         on a quote, $, ` or \\
  pick the goal back up                           ask    never picks a slug (T-0056)

A bare pronoun as the text ("handle it"), or text naming approve, never
matches, and `?` is accepted only where a pattern spells it (the two status
questions).

`crew_ticket.resolve_active`'s own INDEX fallback takes the FIRST open line,
so it is never the answer here: `crew_autopilot.open_index_tickets` (T-0004)
is, and only when it holds exactly one ticket. Every branch that cannot tell
returns `ask`, never `route`.

Exit 0 always; the answer is in the output.
"""
import argparse
import json
import os
import re
import sys

import crew_autopilot
import crew_common
import crew_config
import crew_state
import crew_ticket
from crew_common import read_text

MAX_PROMPT_CHARS = 80
MAX_CANDIDATES = 8
PREFIX = "crew route: "
# `render`'s line is at most this long whatever it is fed, so it always fits
# the UserPromptSubmit budget (`crew_context.TURN_CHARS`, 2000) as the first
# item: `fit` keeps whole items or none, and an over-long ask used to be
# dropped entirely (review round 1). Every variable-length field is clipped
# to its own cap below, whitespace collapsed so the line stays one line;
# `test_render_is_one_bounded_line_whatever_the_fields` holds the sum.
MAX_LINE_CHARS = 1400
FIELD_CHARS = {"intent": 32, "ticket": 64, "source": 80, "phase": 48, "command": 200,
               "reason": 480, "candidate": 48}

_ID = r"(?P<id>[a-z][a-z0-9]*-\d+)"
_REF = rf"(?:it|this|{_ID})"
# T-0057: an autopilot row's free text. No `?`: a question is never a command.
_TEXT = r"(?P<topic>[^?]+)"

# (intent, command, ticket_rule, patterns). `command` None: the disk names it
# (`continue`). Rules: `topic` -- the rest of the prompt is the argument;
# `none` -- no ticket; `ticket` -- an explicit id, or it/this/nothing;
# `continue` -- resolved as `ticket`, then `crew_autopilot.next_phase`.
PHRASES = (
    ("brainstorm", "/crew:brainstorm", "topic", (r"brainstorm (?P<topic>.+)",)),
    ("spec", "/crew:spec", "ticket", (rf"write the spec(?: for {_REF})?", rf"spec {_REF}")),
    ("plan", "/crew:plan", "ticket", (rf"plan {_REF}", rf"write the plan(?: for {_REF})?")),
    ("implement", "/crew:implement", "ticket",
     (rf"implement {_REF}", rf"start implementing(?: {_REF})?")),
    ("review", "/crew:review", "ticket",
     (rf"review {_REF}", rf"run the review(?: (?:on|for) {_REF})?")),
    ("done", "/crew:done", "ticket",
     (rf"close {_REF}(?: out)?", rf"mark {_REF} (?:as )?done")),
    ("continue", None, "continue", (r"continue", r"keep going", r"carry on")),
    ("status", "/crew:status", "none", (r"status", r"crew status")),
    # T-0057. Rules: `autopilot` -- an optional id; `autopilot-text` -- the
    # user's words are the argument; `autopilot-ticket` -- an explicit id;
    # `autopilot-resume` -- always asks. The subcommand is the command's last
    # word, and `crew_autopilot.route` says whether it runs.
    ("autopilot-status", "/crew:autopilot status", "autopilot",
     (rf"autopilot status(?: {_ID})?", r"what(?:'s|\u2019s| is) autopilot doing\??")),
    ("assign", "/crew:autopilot assign", "autopilot-text",
     (rf"take care of {_TEXT}", rf"handle {_TEXT}")),
    ("goal", "/crew:autopilot goal", "autopilot-text",
     (rf"work towards? {_TEXT}", rf"make it so {_TEXT}")),
    ("goal-resume", "/crew:autopilot run --goal", "autopilot-resume",
     (r"pick the goal back up", r"resume the goal")),
    ("focus", "/crew:autopilot focus", "autopilot-ticket", (rf"focus on {_ID}",)),
)

AMBIGUOUS = ("do it", "go", "go ahead", "yes", "ok", "sure", "done", "next", "ship it")
_PREFIXES = ("please ", "ok ", "now ", "let's ")
_WS = re.compile(r"\s+")
_CREW_COMMAND = re.compile(r"^/crew:([a-z][a-z0-9-]*)(?:\s+(.*))?$")
_APPROVE = re.compile(r"approve", re.IGNORECASE)
# T-0057: an `autopilot-text` capture that is only one of these, or names
# approve, is no match.
_PRONOUNS = ("it", "this", "that", "them", "these", "those", "everything")
# The characters `commands/autopilot.md` section 0 refuses in its arguments.
_SHELL = re.compile(r"['\"$`\\]")
_ROUTE_SHAPE = ("sub", "stop", "reason")
# Intents whose ask is about which ticket; any other ask never says "which ticket".
_TICKETED = ("spec", "plan", "implement", "review", "done", "continue", "focus")
GOAL_UNDO = "After it runs, tell the user in one line what changed and how to undo it."


def compile_table(phrases):
    """[(intent, command, rule, [compiled])] for `phrases`."""
    return [(intent, command, rule, [re.compile(p, re.IGNORECASE) for p in patterns])
            for intent, command, rule, patterns in phrases]


_COMPILED = compile_table(PHRASES)


def normalise(prompt):
    """The prompt as the table sees it, case preserved, or None when it can
    never be a route (not a string, a line break, too long, a slash command,
    markup or a backtick)."""
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    if not text or "\n" in prompt or "\r" in prompt or len(text) > MAX_PROMPT_CHARS \
            or text[0] in "/<`":
        return None
    text = _WS.sub(" ", text)
    if text[-1] in ".!":
        text = text[:-1].rstrip()
    for prefix in _PREFIXES:
        if text.casefold().startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    return text or None


def match(prompt):
    """`{"intent", "command", "rule", "ticket_arg", "topic"}` for the row the
    whole prompt matches, else None."""
    text = normalise(prompt)
    if text is None or text.casefold() in AMBIGUOUS:
        return None
    for intent, command, rule, patterns in _COMPILED:
        for pattern in patterns:
            found = pattern.fullmatch(text)
            if not found:
                continue
            groups = found.groupdict()
            ticket = groups.get("id")
            topic = (groups.get("topic") or "").strip() or None
            if rule == "autopilot-text" and ((topic or "").casefold() in _PRONOUNS
                                             or _APPROVE.search(topic or "")):
                continue
            return {"intent": intent, "command": command, "rule": rule,
                    "ticket_arg": ticket.upper() if ticket else None, "topic": topic}
    return None


def command_for(found, ticket):
    """The `/crew:` command line a match renders to for `ticket`."""
    if found["rule"] in ("topic", "autopilot-text"):
        return f"{found['command']} {found['topic']}"
    if found["rule"] in ("none", "autopilot-resume") or not found["command"] \
            or (found["rule"] == "autopilot" and not ticket):
        return found["command"]
    return f"{found['command']} {ticket}"


def _answer(outcome, found, **fields):
    """One decision dict; every key present whatever the outcome."""
    answer = {"outcome": outcome, "intent": found["intent"] if found else None,
              "command": None, "ticket": None, "source": "", "reason": "", "candidates": [],
              "phase": None, "unavailable": False}
    answer.update(fields)
    answer["candidates"] = list(answer["candidates"] or [])
    return answer


def _resolve(top, explicit):  # pylint: disable=too-many-return-statements
    """(ticket, source, reason, candidates). `ticket` None means ask: one
    return per row of the module docstring's table, so each reads alone."""
    if explicit:
        if os.path.isdir(crew_ticket.ticket_dir(top, explicit)):
            return explicit, "named in the prompt", "", []
        return None, "", f"no such ticket: {explicit} has no .work/tickets/ folder", []
    active, where, broken = crew_ticket.resolve_active(top)
    if broken:
        return None, "", f"the active-ticket pointer is broken ({where})", []
    if where == "active-ticket" and active:
        return active, "this worktree's active ticket", "", []
    candidates = crew_autopilot.open_index_tickets(top)
    if len(candidates) == 1:
        return candidates[0], ".work/INDEX.md (the only open ticket)", "", []
    if candidates:
        return None, "", "several tickets are open and this worktree has no active ticket", \
            candidates
    return None, "", "no open ticket has a .work/tickets/ folder and none is active", []


def _continue(found, top, ticket, source):
    try:
        phase = crew_autopilot.next_phase(top, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return _answer("ask", found, ticket=ticket, source=source,
                       reason=f"the next phase could not be read ({type(exc).__name__}: {exc})")
    command = phase.get("command") or ""
    if phase.get("stop") or not command:
        human = f" - the human's next command is {command}" if command else ""
        return _answer("ask", found, ticket=ticket, source=source, phase=phase.get("phase"),
                       reason=f"the files on disk stop at {phase.get('phase')}: "
                              f"{phase.get('reason')}{human}")
    if _APPROVE.search(command):
        return _answer("ask", found, ticket=ticket, source=source, phase=phase.get("phase"),
                       reason=f"the next step is {command}, and routing never approves: "
                              "the human types it")
    return _answer("route", found, command=command, ticket=ticket, source=source,
                   phase=phase.get("phase"), reason=phase.get("reason") or "")


def _gate(top, found):
    """None when `crew_autopilot.route` says the row's subcommand runs, else
    the decision: ask when it cannot be read, none when the router does not
    know the name, an `unavailable` ask when it stops."""
    sub = found["command"].split()[-1]
    try:
        got = crew_autopilot.route(top, sub)
        if not isinstance(got, dict) or any(key not in got for key in _ROUTE_SHAPE) \
                or not isinstance(got["stop"], bool):
            raise TypeError(f"route answered {got!r:.80}")
    except Exception as exc:  # pylint: disable=broad-except
        why = f"whether /crew:autopilot {sub} is available could not be read " \
              f"({type(exc).__name__}: {exc})"
        return _answer("ask", found, reason=why)
    if not got["sub"]:
        return _answer("none", None)
    if got["stop"]:
        return _answer("ask", found, reason=str(got["reason"]), unavailable=True)
    return None


def _autopilot(found, top):
    """decide for the T-0057 rows, after the gate."""
    gate = _gate(top, found)
    if gate is not None:
        return gate
    if found["rule"] == "autopilot-resume":
        return _answer("ask", found, reason="routing does not pick a goal; the user types "
                                            "/crew:autopilot run --goal <slug>")
    if found["rule"] == "autopilot-text":
        if _SHELL.search(found["topic"]):
            return _answer("ask", found, reason="autopilot's router refuses those characters "
                                                "(a quote, $, a backtick or a backslash); ask "
                                                "the user to rephrase or type the command")
        return _answer("route", found, command=command_for(found, None))
    if not found["ticket_arg"]:
        return _answer("route", found, command=command_for(found, None))
    ticket, source, reason, candidates = _resolve(top, found["ticket_arg"])
    if ticket is None:
        return _answer("ask", found, reason=reason, candidates=candidates)
    return _answer("route", found, command=command_for(found, ticket), ticket=ticket,
                   source=source)


def decide(root, prompt):
    """`{"outcome": route|ask|none, "intent", "command", "ticket", "source",
    "reason", "candidates", "phase", "unavailable"}`. Read-only."""
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    found = match(prompt)
    if found is None:
        return _answer("none", None)
    if found["rule"].startswith("autopilot"):
        return _autopilot(found, crew_ticket.toplevel(root) or os.path.abspath(root))
    if found["rule"] in ("none", "topic"):
        return _answer("route", found, command=command_for(found, None))
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    ticket, source, reason, candidates = _resolve(top, found["ticket_arg"])
    if ticket is None:
        return _answer("ask", found, reason=reason, candidates=candidates)
    if found["rule"] == "continue":
        return _continue(found, top, ticket, source)
    return _answer("route", found, command=command_for(found, ticket), ticket=ticket,
                   source=source)


def _clip(value, field):
    """`value` as one line of at most FIELD_CHARS[field] characters."""
    text = _WS.sub(" ", str(value)).strip()
    limit = FIELD_CHARS[field]
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _candidates(names):
    shown = ", ".join(_clip(name, "candidate") for name in names[:MAX_CANDIDATES])
    more = len(names) - MAX_CANDIDATES
    return shown + (f", and {more} more" if more > 0 else "")


def _run_clause(command):
    command = _clip(command or "", "command")
    parsed = _CREW_COMMAND.match(command)
    if not parsed:
        return f"Run `{command}`."
    name, args = parsed.group(1), (parsed.group(2) or "").strip()
    clause = (f"Run the /crew:{name} procedure: invoke the Skill tool with skill crew:{name}"
              + (f", args {args}" if args else ""))
    return clause + "."


def render(decision):
    """One line prefixed PREFIX, or "" for `none`."""
    outcome = decision.get("outcome")
    intent = _clip(decision.get("intent"), "intent")
    ticket = decision.get("ticket")
    ticket = _clip(ticket, "ticket") if ticket else ticket
    source = _clip(decision.get("source"), "source")
    if outcome == "route":
        run = _run_clause(decision.get("command"))
        if intent == "continue":
            phase = _clip(decision.get("phase") or "the next phase", "phase")
            head = (f"the user's prompt asks to continue {ticket} ({source}); "
                    f"the files on disk name {phase} next. "
                    "Carry on with any task already in progress in this conversation first, "
                    "then ")
            run = run[0].lower() + run[1:]
        elif ticket:
            head = f"the user's prompt asks for {intent} on {ticket} ({source}). "
        else:
            head = f"the user's prompt asks for {intent}. "
        undo = f" {GOAL_UNDO}" if intent == "goal" else ""
        return (PREFIX + head + run
                + " Its own checks still decide; if the user plainly meant something else, ask."
                + undo)
    if outcome == "ask":
        on = f" on {ticket}" if ticket else ""
        candidates = decision.get("candidates") or []
        which = f"which ticket ({_candidates(candidates)}) " if candidates else \
            ("which ticket " if not ticket and intent in _TICKETED else "")
        reason = _clip(decision.get("reason"), "reason")
        if decision.get("unavailable"):
            return (f"{PREFIX}the user's prompt reads as {intent}, but {reason}; do not run it. "
                    "If the user meant autopilot, say so in one line; otherwise answer the "
                    "prompt as written.")
        return (f"{PREFIX}the user's prompt reads as {intent}{on}, but {reason}; "
                f"ask the user {which}before running anything.")
    return ""


def _read_json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def settings(root):
    """`{"enabled", "saw", "warnings"}`. Read through `crew_config.resolve_config`
    (defaults < machine-global < `.crew/config.json`). `enabled` only when the
    resolved value `is True`; any other value is off, and named."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    block = crew_config.resolve_config(top).get("route")
    warnings = []
    if block is None:
        block = {}
    if not isinstance(block, dict):
        warnings.append(f"route is {block!r}, not an object; routing reads as off")
        block = {}
    saw = block.get("enabled")
    enabled = saw is True
    if not enabled and saw is not False:
        warnings.append(f"route.enabled is {saw!r}: only the JSON value true arms routing, so "
                        "it reads as off")
    repo = crew_state.load_config(top)
    # A non-object `route` in either file is dropped by the merge without a
    # word; named here so a `"route": true` does not read as "set and off".
    for where, layer in (("the machine-global config", crew_config.read_global_config()),
                         (".crew/config.json", repo)):
        if "route" in layer and not isinstance(layer["route"], dict):
            warnings.append(f"route in {where} is {layer['route']!r}, not an object, so it "
                            "is ignored")
    crew_json = _read_json(crew_common.repo_config_file(top, "crew.json"))
    if isinstance(crew_json, dict) and "route" in crew_json and "route" not in repo:
        warnings.append("route is set in .crew/crew.json, which crew does not read for this "
                        "key; move it to .crew/config.json")
    return {"enabled": enabled, "saw": saw, "warnings": warnings}


def _plain(result):
    return " ".join(f"{k}={v}" for k, v in result.items())


def main(argv):
    """The CLI. Exit 0 always; an exception prints `outcome=error`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("settings", "decide"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 0
    try:
        if args.action == "settings":
            result = settings(args.root)
            print(json.dumps(result) if args.json else _plain(result))
            return 0
        result = decide(args.root, args.prompt)
        if args.json:
            print(json.dumps(result))
        else:
            print(render(result) or "outcome=none")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"outcome=error reason={type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
