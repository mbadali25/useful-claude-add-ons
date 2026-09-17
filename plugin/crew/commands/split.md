---
description: Split an oversized Jira ticket into sub-tickets, with evidence and a confirmation
argument-hint: <ISSUE-KEY> [--dry-run]
allowed-tools: Read, Write, Edit, Bash, ToolSearch, Agent
---

Split $ARGUMENTS.

## Preconditions — check all three, name the one that failed, stop

1. `.crew/config.json` -> `tracker` must be `"jira"`. **This command is Jira
   only, on purpose.** A files-mode ticket is a markdown file the user can
   split with an editor; an Obsidian card is theirs to drag. Jira is the one
   tracker where splitting means creating real issues other people will see,
   which is exactly why it needs a command with a confirmation rather than an
   improvised sequence of MCP calls.
2. The Atlassian MCP server must be connected. Check for `mcp__atlassian__*`
   in your available tools; with tool search active you may need to search
   rather than read a list.
3. An issue key must be given. Do not guess one from `.work/`, and do not
   split "the open ticket" — the wrong issue split in a shared tracker is a
   mess someone else has to clean up.

Say which precondition failed and stop. Never fall back to files mode: a silent
fallback splits the source of truth, and nobody notices until two people hold
divergent ticket state.

## 1. Read the issue before judging it

Discover the read tool and fetch the issue. Atlassian's Rovo MCP server has
changed tool names between versions, so find the read, create, link and comment
tools rather than assuming their names. A cloud instance needs a cloudId —
reuse `jira.cloudId` from `.crew/config.json` if it is cached there, and cache
it if it is not.

Read the summary, the description, the acceptance criteria, and any existing
sub-tasks or links. An issue that already has sub-tasks is usually not the one
to split.

## 2. Decide whether it is actually too large — with evidence

**Do not split on a feeling.** State which of these you are relying on:

| Evidence | Where |
|---|---|
| Findings per ticket above the healthy band | `.crew/metrics.md`, via `crew_state.py` -> `health.rate`; `HEALTHY_HIGH` is 2.0 |
| The `ticketsTooLarge` trigger is firing | `crew_state.py` output, `triggers` |
| The issue names more than one subsystem | `.crew/codemap/INDEX.md`, or `crew:explorer` |
| Acceptance criteria that cannot be verified together | the issue itself |

`health.rate` is a **repo-wide** average, not a measurement of THIS issue. It
says the tickets here tend to be too large; it does not say this one is. Say
which you have. If the only evidence is the repo-wide rate, say so plainly and
let the user decide — a high average is a reason to look, not a verdict on the
issue in front of you.

**If the issue is not too large, say so and stop.** A command that always finds
work is a command nobody can trust to say no.

## 3. Propose the split — do not create anything yet

Dispatch `crew:explorer` when the boundaries are not obvious from the issue
text; it returns a map rather than file contents, which is what you need to
tell one piece of work from two.

Propose between two and five children. Fewer than two is not a split; more than
five usually means the parent was an epic wearing a story's label, and that is
worth saying instead of manufacturing children to fill a list.

For each proposed child give:

- a summary that would make sense to someone who never saw the parent,
- the acceptance criteria that move to it, quoted from the parent,
- which subsystem it touches, named from the codemap,
- what it does NOT include, because that is the half a reader cannot infer.

Then say what stays on the parent. **Every acceptance criterion must land
somewhere.** A criterion that appears in no child and is not kept on the parent
has been deleted by a tool nobody audited — report the gap rather than
silently dropping it, and stop if you cannot place one.

## 4. Confirm before writing to Jira

Show the proposal and ask for a yes. **Creating issues is outward-facing**:
other people get notified, boards move, and an unwanted child issue has to be
deleted by hand in a UI. One confirmation covers the whole proposed set; do not
ask per child.

`--dry-run` prints the proposal and exits without asking — use it when the user
wants to see the shape before committing to the conversation.

## 5. Create, link, and record

On a yes, and only then:

1. Create each child. Prefer real sub-tasks when the project's issue types
   allow one under this parent's type; fall back to standard issues linked
   `relates to` when they do not, and **say which you used** — a "sub-task"
   that is actually a sibling behaves differently on every board.
2. Move the acceptance criteria as proposed. Quote them; do not paraphrase.
3. Comment once on the parent listing the children by key, so the split is
   visible to somebody reading the parent in a browser with no access to this
   session.
4. Update `.work/cache/<KEY>.md` for the parent and write one for each child,
   in the same shape `/crew:jira-sync` uses, so the local cache is not stale
   the moment this finishes.

Do not transition the parent, and do not close it. Whether a split parent
becomes an epic, stays open as a tracking issue, or is closed is a project
convention this command has no way to know — report that it is untouched.

## 6. Report

Name every issue created, with its key and its type, and say which acceptance
criterion went where. Then say what was NOT done: the parent was not
transitioned, no estimate was carried over unless the project auto-copies it,
and nothing was assigned — assignment is a person decision.

If `/crew:scale` or the PM raised `ticketsTooLarge`, say that splitting one
issue does not clear it. That trigger reads a rate over the whole metrics file;
it falls when future tickets are smaller, not when one old one is divided.
