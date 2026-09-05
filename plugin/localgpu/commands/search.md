---
description: Semantic search of this repo on the local GPU - file:line plus a three-line excerpt
argument-hint: <query> [--k N] [--glob <pattern>] [--root <path>]
allowed-tools: Read, Bash, Grep, mcp__localgpu__search_code
---

Find code by meaning rather than by string. `$ARGUMENTS` is the query, plus
optional flags.

| Flag | Maps to | Default |
|---|---|---|
| `--k N` | `k` | 10 |
| `--glob <pattern>` | `path_glob` | none |
| `--root <path>` | `root` | every indexed root |

This calls the `search_code(query, k=10, root=None, path_glob=None)` MCP tool.
Prefer the tool directly when you are mid-task; this command exists for when the
user wants to run a search themselves and read the hits.

## Is this the right tool

Answer before searching, and say so out loud when the answer is no:

| The user is looking for | Use |
|---|---|
| An exact symbol, string, error code, or config key | `Grep`. It is faster and it cannot miss |
| Every call site of a known function | `Grep` |
| "Where does this repo handle X" with no known name for X | `search_code` |
| Code that does something similar to a description | `search_code` |

Embedding search finds ideas, so it is strictly worse than `Grep` at anything you
could have typed exactly. Routing a lexical question here and then reporting three
near-misses is worse than not having the tool.

## What comes back, and what does not

Each hit is `path:line` plus **at most three lines** of excerpt. That is the whole
contract. It is enough to judge whether a location is the one you wanted, and
deliberately not enough to work from.

**Do not ask this tool for more.** When a hit looks right, `Read` that file at that
line range. Returning files instead of locations turns a cheap lookup into a
context-budget event and destroys the reason the lookup was worth doing — the same
rule `crew:explorer` follows.

Show the hits with their scores. The tool already prints them — cosine similarity
to three decimals, best first — so relaying its output keeps them. A top hit at a
weak score means the index has nothing close, not that the top hit is the answer,
and a ranked list stripped of its scores hides exactly that.

One line of output is a diagnosis rather than a hit: `[file changed or gone since
indexing - run index_refresh()]` in place of an excerpt means the locator survived
and the file behind it did not. That is staleness, not a miss, and re-running the
search will not fix it.

## Scope the search before widening `k`

The reflex when results are poor is to raise `--k`. That is usually wrong: more
hits from the same weak neighbourhood is more noise at the same signal.

Reach for these first:

- `--glob "**/*.ps1"` when the question is already language-scoped. It filters
  before ranking, so ten hits are ten PowerShell hits rather than ten hits of
  which two are. The match is forgiving — it is tried against the whole path and
  against the basename — so `*.ps1` and `**/*.ps1` both work.
- `--root` once a second repository is indexed on this machine. Without it, hits
  from another project appear in the list looking identical to local ones.
- A different query. Describe the behaviour rather than naming the abstraction;
  the index embedded the code, not the vocabulary someone hoped it used.

## Nothing came back

Do not re-run with synonyms until something appears. Diagnose in this order — each
step rules out the next one's cause:

1. `index_status()` — does the root list contain the file you expect?
2. Is the index stale? A file written since the last refresh has no vector.
3. Does `ignore` exclude it?
4. Was the question lexical all along? Go to `Grep` and say why.

Then say which of the four it was. "No results" with no diagnosis sends the user
to rebuild an index that was fine.
