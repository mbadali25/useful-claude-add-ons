"""`/crew:help`'s reader: where you are and the one command to type next, or
what any crew command is for.

    python3 crew_help.py where --root . [--ticket <id>]
    python3 crew_help.py about "<command | question | commands | ticket id>" [--root .]

T-0025. Two answers, both read-only, both printed as-is by `/crew:help`:

`where` -- at most MAX_LINES (8) lines: where you are (ticket, where it came
from, phase), what it waits on, ONE `next:` command and why, and two or three
`also:` commands for that phase. It reads state through T-0004's
`crew_autopilot.status` (which composes `resume_target` and `next_phase`, and
T-0018's waiting-on mapping) -- never INDEX, receipts or ledgers itself. A
stop phase's `next:` is what YOU type; approval is always "you type
`/crew:approve <id>`", never something help or Claude runs. When no single
ticket can be told -- several open, none, a broken pointer -- it says so and
lists the candidates; it never picks one.

`about` -- a command name (with or without `/crew:`) gives four lines:
purpose (its frontmatter `description`), when, arguments (`argument-hint`, or
none) and next. A question goes through T-0023's `crew_route.match`, the one
phrase table; this module holds no pattern of its own over prompt text. A
ticket id with a `.work/tickets/` folder is `where` for that ticket.
`commands` lists every command file by GROUPS, core first. Anything else
lists the core group.

Read-only: git runs with `GIT_OPTIONAL_LOCKS=0`, the CLI writes no bytecode,
and nothing is written. It never runs the command it names. Exit 0 always.
"""
import argparse
import os
import sys

if __name__ == "__main__":
    # Before the sibling imports: the direct CLI writes no bytecode either.
    sys.dont_write_bytecode = True

import crew_autopilot  # noqa: E402
import crew_route  # noqa: E402
import crew_ticket  # noqa: E402
import crew_common  # noqa: E402
from crew_common import read_text  # noqa: E402

MAX_LINES = 8
LINE_CHARS = 200
COMMANDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "commands")
PREFIX = "/crew:"

# The phase names T-0004's `next` reports are the keys of T-0018's
# `crew_autopilot.WAITING`; `test_every_phase_has_related_commands` holds this
# table to them. `{t}` is the ticket id.
RELATED = {
    "brainstorm": (("/crew:status", "the full picture of this repo"),
                   ("/crew:fix <one sentence>", "the light path for a small fix"),
                   ("/crew:help commands", "every command, by group")),
    "direction-approval": (("/crew:status", "the full picture of this repo"),
                           ("/crew:autopilot status {t}", "why the direction cannot be told")),
    "open-questions": (("/crew:autopilot status {t}", "this ticket's standing"),
                       ("/crew:handoff", "stopping until someone answers")),
    "spec": (("/crew:autopilot {t}", "let autopilot drive from here"),
             ("/crew:status", "the full picture of this repo")),
    "plan": (("/crew:autopilot {t}", "let autopilot drive from here"),
             ("/crew:status", "the full picture of this repo")),
    "approve": (("/crew:autopilot status {t}", "this ticket's standing"),
                ("/crew:plan {t}", "change the plan before approving it")),
    "implement": (("/crew:status", "the full picture of this repo"),
                  ("/crew:handoff", "stopping mid-way"),
                  ("/crew:autopilot {t}", "let autopilot drive")),
    "refresh": (("/crew:status", "which artifact is behind"),
                ("/crew:autopilot {t}", "let autopilot run the refresh")),
    "review": (("/crew:autopilot status {t}", "the review budget and this ticket's standing"),
               ("/crew:status", "the full picture of this repo")),
    "accept-review": (("/crew:autopilot status {t}", "the review budget and this ticket's "
                                                     "standing"),
                      ("/crew:handoff", "stopping before deciding")),
    "replan": (("/crew:autopilot status {t}", "the review budget and this ticket's standing"),
               ("/crew:status", "the full picture of this repo")),
    "stale-after-review": (("/crew:status", "which artifact is behind"),
                           ("/crew:autopilot status {t}", "this ticket's standing")),
    "done": (("/crew:status", "the full picture of this repo"),
             ("/crew:handoff", "stopping before closing")),
    "closed": (("/crew:status", "the other open tickets"),
               ("/crew:help commands", "every command, by group")),
    # Phases autopilot gained after T-0025 (crew_autopilot.WAITING).
    "auto-replan": (("/crew:autopilot status {t}", "the review ledger and this ticket's standing"),
                    ("/crew:plan {t}", "the successor plan autopilot drafts")),
    "auto-replan-cap": (("/crew:autopilot status {t}", "the successor plans already on the ledger"),
                        ("/crew:plan {t}", "write the next plan yourself")),
    "needs-owner": (("/crew:autopilot status {t}", "why the owner is needed"),
                    ("/crew:handoff", "stopping until the owner decides")),
    "drift": (("/crew:autopilot status {t}", "which changed path is outside Touch"),
              ("/crew:status", "the full picture of this repo")),
    "ship": (("/crew:autopilot status {t}", "the PR and receipt state"),
             ("/crew:status", "the full picture of this repo")),
}
NO_TICKET_RELATED = (("/crew:status", "the full picture of this repo"),
                     ("/crew:help commands", "every command, by group"))

# What you do at a stop that names no command for you to type.
STOP_NEXT = {
    "direction-approval": "you agree direction.md in /crew:brainstorm - it marks the row ready",
    "closed": "/crew:brainstorm <idea> - {t} is closed; start the next ticket",
    "open-questions": "you answer them in the ticket's files, then /crew:autopilot {t}",
    "review": "/crew:autopilot status {t} - review stopped and a human decides why",
    "accept-review": "you decide the findings: fix them and rerun /crew:review {t}, or accept",
    "refresh": "/crew:status - the refresh cannot run by itself",
    "stale-after-review": "/crew:autopilot status {t} - an artifact went stale after "
                          "the accepted review; a human decides",
    "drift": "you decide: widen the spec's Touch and re-approve, or revert the path outside it",
    "auto-replan-cap": "you decide the next plan: /crew:plan {t}, then you type /crew:approve {t}",
}

# One line each for the core commands: (when, next).
HELP = {
    "brainstorm": ("you have a request and no ticket yet; it settles a direction with you",
                   "/crew:spec <id>"),
    "spec": ("after /crew:brainstorm, to write the ticket contract", "/crew:plan <id>"),
    "plan": ("after /crew:spec, to write the step plan you then approve",
             "you type /crew:approve <id>"),
    "approve": ("you have read the plan and agree with it; only you type it",
                "/crew:implement <id>"),
    "implement": ("the plan is approved; it edits within the plan's Touch",
                  "/crew:review <id>"),
    "review": ("the implementation is done; an independent reviewer reads the diff",
               "/crew:done <id>"),
    "done": ("the review receipt is accepted; it closes the ticket after its checks",
             "/crew:brainstorm <idea> for the next one"),
    "fix": ("a small defect; every phase compressed to one step", "/crew:help"),
    "autopilot": ("you want the lifecycle driven until a person is needed",
                  "/crew:autopilot status"),
    "status": ("you want the full read-only report for this repo", "/crew:help"),
    "help": ("you are not sure what to do next, or what a command is for",
             "the command it names"),
}

# Advisory grouping (T-0025's surface recommendation). Nothing here hides,
# removes or renames a command; `test_every_command_is_in_exactly_one_group`
# fails when a command file is added without a group.
GROUPS = (
    ("core", ("brainstorm", "spec", "plan", "approve", "implement", "review", "done", "fix",
              "autopilot", "status", "help")),
    ("through-help", ("docs", "diagram", "onboard", "reference", "verify", "runbook", "handoff",
                      "init", "config", "config-setup", "model", "migrate", "upgrade", "debug",
                      "survey")),
    ("merge-candidates", ("jira-sync", "sdp-sync", "obsidian-sync")),
    ("specialist", ("change", "emergency", "gate", "promote", "split", "webtest")),
    ("removed", ("ticket", "work")),
)


def _one(text, limit=LINE_CHARS):
    """`text` as one line of at most `limit` characters."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit - 3].rstrip() + "..."


def _fill(template, ticket):
    return template.replace("{t}", ticket or "<ticket-id>")


def _also(pairs, ticket):
    return [_one(f"also: {_fill(cmd, ticket)} - {why}") for cmd, why in pairs[:3]]


def _cap(lines):
    return [_one(line) for line in lines][:MAX_LINES]


def _next_line(result):
    ticket, phase = result.get("ticket"), result.get("phase")
    command, waiting = result.get("command") or "", result.get("waiting") or ""
    why = result.get("phase_reason") or "the files on disk say so"
    if not result.get("stop") and command:
        return f"next: {command} - {why}"
    if waiting.startswith("owner - types ") and command:
        return f"next: you type {command} - {why}"
    if waiting.startswith("autopilot - run "):
        return f"next: /crew:autopilot {ticket} - it activates {ticket} for this worktree first"
    if waiting.startswith("owner - re-points") or waiting.startswith("owner - fixes"):
        return (f"next: you run crew_ticket.py activate --ticket {ticket} - this worktree's "
                "active-ticket pointer names another ticket or is broken")
    if phase in STOP_NEXT:
        return "next: " + _fill(STOP_NEXT[phase], ticket)
    return f"next: /crew:autopilot status {ticket} - it prints why the phase stopped"


def _no_ticket(top, result):
    reason = result.get("reason") or "cannot tell which ticket"
    candidates = []
    try:
        candidates = crew_autopilot.open_index_tickets(top)
    except Exception:  # pylint: disable=broad-except
        candidates = []
    lines = [f"where: no single ticket - {reason}"]
    if len(candidates) > 1 and "several open tickets" in reason:
        lines += ["waiting on: you - help cannot pick one of several open tickets",
                  "open: " + ", ".join(candidates[:12])
                  + (f", and {len(candidates) - 12} more" if len(candidates) > 12 else ""),
                  "next: /crew:help <ticket-id> - name one of them to see its phase"]
    elif "broken pointer" in reason:
        lines += ["waiting on: you - the active-ticket pointer is broken",
                  "next: you run crew_ticket.py activate --ticket <ticket-id> - re-point it"]
    elif "no open ticket" in reason:
        lines += ["waiting on: you - nothing is open",
                  "next: /crew:brainstorm <idea> - start a ticket"]
    else:
        lines += ["waiting on: you - see the reason above",
                  "next: /crew:autopilot status - the full reason"]
    return lines + _also(NO_TICKET_RELATED, None)


def where(root, ticket=None):
    """At most MAX_LINES lines: where, waiting on, next, also. Read-only."""
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    try:
        result = crew_autopilot.status(top, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return _cap([f"where: cannot tell - crew_autopilot raised {type(exc).__name__}: {exc}",
                     "waiting on: unknown",
                     "next: /crew:status - the full report says what could be read"]
                    + _also(NO_TICKET_RELATED, None))
    if not result.get("ticket"):
        return _cap(_no_ticket(top, result))
    found, phase = result["ticket"], result.get("phase")
    lines = [f"where: {found} (from {result.get('source')}) - phase {phase}",
             f"waiting on: {result.get('waiting') or 'unknown'}",
             _next_line(result)]
    lines += _also(RELATED.get(phase, NO_TICKET_RELATED), found)
    return _cap(lines)


# --- about ---------------------------------------------------------------------

def frontmatter(name):
    """`{"description", "argument-hint"}` from commands/<name>.md, or None
    when it has no frontmatter. A file that cannot be read raises OSError
    (`main` prints `help: cannot tell`): read as absent, its description and
    arguments would print as "no description" and "none"."""
    path = os.path.join(COMMANDS_DIR, f"{name}.md")
    text = read_text(path)
    if text is None:
        raise OSError(f"{path} could not be read")
    if not text.startswith("---"):
        return None
    fields = {}
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("description", "argument-hint"):
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def command_names():
    """Every command file's name, sorted. An unreadable command dir raises
    (`main` prints `help: cannot tell`): an empty list would print every
    group heading with nothing under it, as if crew had no commands."""
    return sorted(f[:-3] for f in os.listdir(COMMANDS_DIR) if f.endswith(".md"))


def _group_of(name):
    for group, names in GROUPS:
        if name in names:
            return group
    return None


def describe(name):
    """Four lines for one command: purpose, when, arguments, next."""
    fields = frontmatter(name) or {}
    when, after = HELP.get(name, (None, None))
    if when is None:
        group = _group_of(name)
        when = (f"removed in crew 1.0 - {fields.get('description', '')}" if group == "removed"
                else f"see /crew:help commands ({group or 'ungrouped'})")
        after = "/crew:help"
    return [_one(f"/crew:{name}: {fields.get('description') or 'no description'}"),
            _one(f"when: {when}"),
            _one(f"arguments: {fields.get('argument-hint') or 'none'}"),
            _one(f"next: {after}")]


def groups_text():
    """Every command by group, core first, one line each."""
    names = set(command_names())
    lines = []
    for group, members in GROUPS:
        present = [m for m in members if m in names]
        lines.append(f"{group}: " + ", ".join(present))
    stray = sorted(names - {m for _, members in GROUPS for m in members})
    if stray:
        lines.append("ungrouped: " + ", ".join(stray))
    return lines


def _core_lines(text):
    return [_one(f"no command matched `{text}`"),
            "core: " + ", ".join(dict(GROUPS)["core"]),
            "more: /crew:help commands"]


def _strip(text):
    word = " ".join(str(text).split())
    for prefix in (PREFIX, "crew:"):
        if word.casefold().startswith(prefix):
            return word[len(prefix):].strip()
    return word


def _is_ticket(top, word):
    """A live ticket folder or one archived under Complete/ (L-0509's
    resolver); an id whose place cannot be told is not taken for one."""
    _path, where, _why = crew_common.locate_ticket(top, word)
    return where in (crew_common.LIVE, crew_common.COMPLETE)


def _named(word, names):
    lowered = word.casefold()
    return lowered if lowered in names else None


def _by_word(text, words, names):
    """The first word of `words` that is a command's own name, or None. A
    name lookup, not a phrase table: no pattern is matched against `text`."""
    for token in words.split():
        name = _named(token.strip(".,!?;:`'\"").removeprefix(PREFIX), names)
        if name:
            return [_one(f"you asked: {text}")] + describe(name)
    return None


def _from_route(text, root, names, asked, depth=0):
    """The answer for a question, through `crew_route.match` only."""
    found = crew_route.match(text)
    if found is None:
        return None
    if found["intent"] == "help":
        return where(root)
    if found["intent"] == "help-topic" and depth == 0:
        topic = found.get("topic") or ""
        name = _named(_strip(topic), names)
        if name:
            return [_one(f"you asked: {asked}")] + describe(name)
        routed = _from_route(topic, root, names, asked, depth + 1)
        return routed if routed is not None else _by_word(asked, topic, names)
    command = found.get("command") or crew_autopilot.AUTOPILOT
    name = command[len(PREFIX):] if command.startswith(PREFIX) else None
    if name in names:
        return [_one(f"you asked: {asked}")] + describe(name)
    return None


def about(text, root="."):
    """The answer for `/crew:help <text>`, at most MAX_LINES lines (the
    `commands` listing excepted: one line per group)."""
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    word = _strip(text)
    if not word:
        return where(root)
    names = set(command_names())
    if word.casefold() == "commands":
        return groups_text()
    name = _named(word, names)
    if name:
        return describe(name)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    if _is_ticket(top, word):
        return where(top, word)
    routed = _from_route(word, top, names, word)
    if routed is None and not word.casefold().startswith("how do i"):
        routed = _from_route("how do i " + word, top, names, word)
    if routed is None:
        routed = _by_word(word, word, names)
    return _cap(routed) if routed is not None else _core_lines(word)


def main(argv):
    """The CLI. Exit 0 always; a crash prints one `help: cannot tell` line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("where", "about"))
    parser.add_argument("text", nargs="*")
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", default=None)
    try:
        args = parser.parse_intermixed_args(argv)
    except SystemExit:
        return 0
    try:
        if args.action == "where":
            lines = where(args.root, args.ticket) if args.ticket else where(args.root)
        else:
            lines = about(" ".join(args.text), args.root)
    except Exception as exc:  # pylint: disable=broad-except
        lines = [f"help: cannot tell - {type(exc).__name__}: {exc}",
                 "next: /crew:status - the full read-only report"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
