---
description: The code graph - one-line status, the repo's sanctioned refresh with the pair check, and queries
argument-hint: [--status | --refresh | --query "<question>"]
allowed-tools: Read, Bash, Grep, Glob
---

Graph: $ARGUMENTS (no argument means `--status`)

One command for the code graph. The method behind it (detect, the install offer,
the MCP server, how to ask a question) is the `crew-graph` skill; this command
runs the mechanical parts through one script and reports what it printed.

## --status (read-only)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_graph.py status --root .
```

It prints one line:
`graph=<fresh|stale|unknown|absent> built_at=<sha|none> pair=<agree|disagree|unknown|untracked> ignore=<covered|uncovered|unknown> command=<line>`.
`command` is the graphify line `--refresh` would run here: `graphify update .`
where the repo tracks `GRAPH_REPORT.md` beside the graph, else
`graphify . --no-viz --code-only`. Quote the line; it writes nothing.

## --refresh

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_graph.py refresh --root .
```

It stops at the first step that fails, and a stop is reported verbatim, never
worked around:

1. `graphify` not on PATH - exit 2. Offer the install the skill describes; never install it.
2. The secrets denylist (`crew_graph_ignore.py`): uncovered is exit 1 and names
   the files and `crew_graph_ignore.py --write`; unknown is exit 2. Nothing is built.
3. The sanctioned command above, from the repo root (on native Windows through
   `crew_shell.py run`, which prints its `crew-shell:` route line). A non-zero
   exit is exit 1 with the tool's output.
4. The check: the built `graph.json` must carry `built_at_commit` (else exit 2),
   and where the report is tracked its `## Summary` line must match the graph's
   `nodes` and `links` counts. A mismatch is exit 1 (`pair=disagree`, four
   numbers); an unreadable report or graph, or a graph with no `links`, is exit 2.
5. Exit 0 prints the changed paths under the graph directory.

It never stages, commits or pushes. Whoever ran it commits the pair: you, or
the phase that named `/crew:graph --refresh` (`/crew:implement` step 6,
`/crew:autopilot`'s refresh phase).

## --query "<question>"

Run `--status` first. If `graph=` is anything but `fresh`, print one warning
line, `graph is <state>: answers may be out of date - /crew:graph --refresh`,
then answer anyway with `graphify query "<question>"` as the skill's **Query**
section describes. Never load `graph.json` into context to answer.
