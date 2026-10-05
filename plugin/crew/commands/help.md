---
description: What to do next, and what any crew command is for
argument-hint: "[command | question | commands | ticket id]"
allowed-tools: Bash, Read
---

Contextual help. **Read-only**: this command edits nothing, writes no file and
never runs the command it recommends - it prints, and the user (or
`/crew:autopilot`) runs it.

## Run it

With no argument - where you are and the one command to type next:

```bash
python3 -B "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_help.py" where --root .
```

With an argument (a command name with or without `/crew:`, a question such as
"how do i write the spec", `commands` for every command by group, or a ticket id).
Leave out any quote, `$`, backtick or backslash in the arguments first:

```bash
python3 -B "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_help.py" about --root . -- '$ARGUMENTS'
```

On Git Bash without `python3`, use `python` or `py -3` with the same arguments.
If none resolves, say so and stop - do not reconstruct the answer by hand.

## Print it verbatim

Print the script's output as-is and add nothing: no summary, no advice, no
second recommendation. `where` is at most 8 lines by construction.

Do not run the `next:` command. When it reads "you type `/crew:approve <id>`",
approval is the user's to type - never run `crew_ticket.py approve` or anything
that records an approval.
