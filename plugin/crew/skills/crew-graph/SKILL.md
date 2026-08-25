---
name: crew-graph
description: Build and query a code graph of this repository with graphify, export it to an Obsidian vault, and keep it fresh on commit. Use when the user asks to build or refresh the code graph, asks what calls what or what connects to what, wants the codebase in Obsidian, or asks how a subsystem is wired.
---

# Crew Graph

Wraps `graphify`, an external CLI that builds a static code graph and answers
questions against it. This skill detects it, builds keyless, queries it
instead of loading the raw graph, and gates the one thing that touches files
outside this repo — an Obsidian vault export.

## Detect — never auto-install

```
command -v graphify
```

Absent means report it and stop; do not install anything without asking.
Offer:

```
uv tool install graphifyy
```

The package on PyPI is `graphifyy` — double-y — while the CLI it installs is
`graphify`. Every other `graphify*` name on PyPI is unaffiliated. Installing
the wrong one fails silently: `pip`/`uv` succeeds, and the command you get is
not this tool. Say the package name out loud when offering the install; don't
just say "install graphify."

The same install adds a second executable, `graphify-mcp` — see MCP server
below. Confirm with `graphify --version`.

## Build

```
graphify . --no-viz --code-only
```

This is the default, always. Both flags matter and neither is optional:

- **`--code-only`** skips docs, papers, and images. Without it, graphify
  errors on any repo that has documentation at all — which is nearly every
  real repo, this one included — with `no LLM API key found (N doc/paper/
  image file(s) need semantic extraction)`. Code-only needs no API key.
  `--code-only` dropped from a command in this skill is a bug, not a
  simplification.
- **`--no-viz`** skips the HTML visualization. It's unopenable past roughly
  5000 nodes, and an agent reads `graph.json` through the CLI, not the HTML,
  so building it is wasted work.

Output lands in `graphify-out/`: `graph.json`, `manifest.json`, `cache/`.
Measured on this repo (106 code files): 1478 nodes, 3170 edges, 1.8 MB.

**Docs, PDFs, and images are opt-in.** Extracting them needs an LLM call, so
before offering to run graphify without `--code-only`, tell the user which
API key env var graphify needs and confirm it's set — don't let them discover
the key requirement from an error after the fact.

## Query

Prefer the CLI over reading `graph.json` directly — the file is large and the
CLI already summarizes:

```
graphify query "what connects the install scripts to the skills catalog?"
```

`graphify path` and `graphify explain` are also available for tracing a
specific route or explaining a specific node; run `graphify path --help` /
`graphify explain --help` for their exact arguments rather than guessing —
this skill has only measured `graphify query`.

## Freshness

```
graphify hook install
```

installs a Git hook that rebuilds the graph on every commit, plus a union
merge driver for `graph.json`. That merge driver is the reason `graph.json`
is committed to the repo rather than gitignored — a union driver only has
something to merge if both sides are tracked. `.gitignore` covers the HTML
output, the wiki, and any Obsidian export; never `graph.json` itself.

**No stamping step, and none should be added.** graphify writes a top-level
`built_at_commit` field into `graph.json` — the full commit sha it built
from, written atomically with the graph. `crew_state._built_at_commit` reads
that field from a bounded tail of the file (measured 0.12 ms, against 10.34
ms for a full parse of a 1.8 MB graph) because it runs on every session
start. That field is the only source of truth for "what commit does this
graph describe."

Do not reintroduce a `.crew-graph-sha` sidecar. An earlier design had crew
write its own — it was strictly worse: forgettable by a build that doesn't
know to update it, driftable from the graph it sits beside, and vulnerable to
the pre-commit-hook trap where `git rev-parse HEAD` still returns the parent
commit at hook time. graphify's own record is authoritative about what
graphify built; a second copy can only be redundant or wrong. Whether
`graphify hook install` rebuilds pre-commit or post-commit doesn't matter for
the same reason — freshness never reads `git rev-parse HEAD` at hook time, it
reads what graphify stamped into the file it just wrote.

**Freshness is commit-based, not working-tree-based.** `built_at_commit`
matching HEAD means the graph describes the last *commit* — it says nothing
about uncommitted edits to tracked files. A graph can report itself current
while being stale against what's actually on disk. State this plainly when
reporting graph freshness; "graph current" is a claim about HEAD, not about
what the user is looking at right now.

## Obsidian export — refusal, not preference

Exporting into a vault writes into the user's own notes outside this repo.
Two conditions, both required, before any export runs:

1. `.crew/config.json` has `graph.obsidian.confirmed == true` — set only by
   the user explicitly approving this in the current session. An upgrade
   (`crew_upgrade.py`) never sets this flag itself; it always resets it to
   `false` unless it was already `true`, on purpose.
2. A scratch-directory proof run has been done and its output inspected:
   export with `--obsidian-dir` pointed at an empty throwaway directory,
   then look at what landed there and confirm nothing was written outside
   it. Upstream claims `--obsidian-dir` never overwrites existing notes or
   `.obsidian` config. That claim is verified once against a scratch
   directory, not trusted the first time against a vault the user actually
   cares about.

If either condition is unmet, **refuse the export and ask** — don't run it
"just this once" or treat a missing scratch-run as good enough. Default
target when both conditions hold: `<vault>/codegraphs/<repo>/`.

## MCP server — optional, off by default

`graphify-mcp` (or `python -m graphify.serve`) runs graphify as an MCP
server. It is not started automatically by anything in this skill. It's
another always-on network-adjacent surface, and starting one should be a
choice the user makes, not a side effect of building a graph.

## Config keys

`.crew/config.json`'s `graph` block, as written by `crew_upgrade.py` and
`crew-setup`:

| Key | Meaning |
|---|---|
| `graph.enabled` | Whether crew treats this repo as graph-capable. |
| `graph.tool` | Always `"graphify"` today. |
| `graph.out` | Output directory; defaults to `graphify-out`. |
| `graph.mode` | Always `"code-only"` today. |
| `graph.commitHook` | Whether `graphify hook install` has been run. |
| `graph.obsidian.enabled` | Whether an Obsidian export is configured at all. |
| `graph.obsidian.dir` | Export target, or `null`. |
| `graph.obsidian.confirmed` | The consent gate above — never set by an upgrade. |

## Refreshing an existing codemap

`/crew:upgrade` and `/crew:onboard --refresh` both fold graph facts into
`.crew/codemap/*.md`. Read `reconcile.md` before running either — it's the
one place the KEEP/DERIVE split, the conflict rule, and the anchor rule are
defined, so the two commands can't drift from each other.

## The community field

`graph.json` nodes carry a `community` key — 106 distinct values, measured on
this repo's graph. It's a node-level field, not top-level.
