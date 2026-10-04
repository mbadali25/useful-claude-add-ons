---
description: Split an oversized ticket into 2-5 children, with evidence and one confirmation, in any tracker but SDP
argument-hint: <ticket-id-or-ISSUE-KEY> [--dry-run]
allowed-tools: Read, Write, Edit, Bash, ToolSearch, Agent
---

Split $ARGUMENTS. `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_split.py` holds the rules;
this file is the procedure around them.

## Preconditions — name the one that failed, stop

1. Under `/crew:autopilot`, stop and name `/crew:autopilot split <id>` (T-0058).
   This command's confirmation is a human's, and `crew_split.py confirm`
   refuses a session answering its own question.
2. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py resolve --root .`
   picks the path. `sdp`: stop — SDP is a service desk, not where this work gets decomposed.
   `files`/`obsidian`: an id with a `.work/tickets/<id>/spec.md`. `jira`: the
   Atlassian MCP server is connected (search for `mcp__atlassian__*`), and an
   issue key is given — do not guess one from `.work/` or split "the open
   ticket"; the wrong issue split in a shared tracker is someone else's mess.

Never fall back to files mode from Jira: a silent fallback splits the source
of truth, and nobody notices until two people hold divergent ticket state.

## 1. Read the ticket before judging it

Files/Obsidian: read `spec.md`, `plan.md` and `direction.md`. Jira: discover
the read tool and fetch the issue (Rovo's tool names change between versions,
so find the read, create, link and comment tools rather than assuming them); a
cloud instance needs a cloudId — reuse `jira.cloudId` from `.crew/config.json`
if cached, and cache it if not. Read the summary, description, acceptance
criteria and existing sub-tasks or links; an issue that already has sub-tasks
is usually not the one to split.

## 2. Decide whether it is too large — with evidence

**Do not split on a feeling.** Run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_split.py --root . --ticket <id>`: it prints
the measures and the fired triggers (`unknown:<name>` is a measure it could
not read, never "small"). The thresholds, and the evidence each rests
on, are constants in `crew_split.py`. A trigger means look, never split. Name
the evidence keys you rely on (`EVIDENCE_KEYS`); a split needs
`separable-criteria`: criteria that cannot be verified together.

The findings rate is **repo-wide**: it says tickets here tend to be too large,
not that this one is. If it is your only evidence, say so and let the user
decide.

**If the ticket is not too large, say so and stop** — write
`decision: not-too-big`. A command that always finds work is a command nobody
can trust to say no.

## 3. Propose the split — do not create anything yet

Dispatch `crew:explorer` when the boundaries are not obvious; it returns a map,
which is what tells one piece of work from two. Write the proposal to
`.work/tickets/<id>/split.md` in the rulebook's format (`crew_split.py`'s
docstring): 2-5 children, each with a title that makes sense to someone who
never saw the parent, a `risk:`, a `subsystem:` from the codemap, the
`Criteria:` it takes **quoted verbatim**, and the `Excludes:` a reader cannot
infer; then `## Stays on parent`. Every acceptance criterion lands exactly
once, or the split stops.

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_split.py check --root . --ticket <id>`
before showing it (Jira: put the issue's criteria, quoted, one bullet each in
a file and add `--criteria-file <f>`). Fix every `problem:` it prints; never
show a proposal it refused.

## 4. Confirm — one yes for the whole set

Show the proposal and ask for a yes, then **end the turn**. Creating tickets is
outward-facing (in Jira, other people get notified and an unwanted child is
deleted by hand), so one confirmation covers the set; do not ask per child.
`--dry-run` prints the proposal and exits without asking.

## 5. Create

On the owner's yes, and only then. **Files/Obsidian:** run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_split.py apply --root . --ticket <id> --via command`.
It runs the confirm gate, keeps the parent's text as `spec.pre-split.md`,
mints each child `ready` with a direction pointing back, and only then marks the parent
`superseded` with a `split-into:` line. A `refused:` is the answer: report it.
If a `warning:` names the board, run `/crew:obsidian-sync`.

**Jira:** run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_split.py confirm --root . --ticket <KEY>`
and stop on a `refused:`. Then:

1. Create each child. Prefer real sub-tasks when the project's issue types
   allow one under this parent's type; fall back to standard issues linked
   `relates to` when they do not, and **say which you used** — a "sub-task"
   that is actually a sibling behaves differently on every board.
2. Move the acceptance criteria as proposed. Quote them; do not paraphrase.
3. Comment once on the parent listing the children by key, so the split is
   visible to somebody reading the parent with no access to this session.
4. Update `.work/cache/<KEY>.md` for the parent and write one for each child,
   in the shape `/crew:jira-sync` uses.

Do not transition the parent, and do not close it. Whether a split Jira parent
becomes an epic, stays open, or is closed is a project convention this command
cannot know — report that it is untouched.

## 6. Report

Name every ticket created, with its id or key (and in Jira its type), and say
which acceptance criterion went where. Files/Obsidian: the parent is now
`superseded`. Jira: the parent was not transitioned. No estimate was carried
over unless the project auto-copies it, and nothing was assigned — assignment
is a person decision.

If the `tickets-too-large` trigger fired, say that splitting one ticket does
not clear it: it reads a rate over the whole metrics file, and falls when
future tickets are smaller, not when one old one is divided.
