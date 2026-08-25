---
description: Learn this codebase once and write a durable, verifiable code map
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
argument-hint: [--refresh <subsystem>]
---

Build the code map for this repo. This is the expensive one-time cost. Do it
properly or do not do it — a half-accurate map is worse than none, because it
gets trusted.

## 1. Build or refresh the graph first

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/SKILL.md`'s **Build** section
— `graphify . --no-viz --code-only`, both flags required — if no graph is
present, or if it is present but not current. If `graphify` is absent, that
skill's **Detect** section governs: report it and stop; do not install
anything without asking.

Graph freshness is commit-based: `built_at_commit` matching HEAD means the
graph describes the last commit, not the working tree. Say this plainly if
you are about to write a codemap against a repo with uncommitted changes —
the graph cannot see them.

## 2. Derive the subsystem list from the graph, not by guessing

Read the node-level `community` key in `graph.json` — that partition is the
subsystem list, not a directory listing or a guess from filenames. Cap at 6
subsystems per run, same as before: spawn `crew:explorer` once per subsystem,
in parallel, not one agent over the whole repo. Only its summary reaches this
conversation. If the repo's graph has more than 6 communities, do it in
several runs and say which areas are still unmapped.

## 3. Fill the DERIVE sections from the graph

For each subsystem, build `## Entry points`, `## Owns data`, and
`## Calls out to` directly from the graph — `graphify query`/`graphify
explain` against that subsystem's community, per
`${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/reconcile.md`'s DERIVE list. Do not
send `crew:explorer` after facts an AST parser already has; that duplicates
work and costs a full context load per subsystem for no gain.

## 4. Spawn `crew:explorer` only for what the graph cannot answer

`## Does`, `## Landmines`, and `## Unverified` need judgment a graph can't
produce — this is the only part of the map an explorer is for now. This is
where the cost saving is: an explorer that used to re-derive entry points and
call sites now only writes the two sentences of intent, the landmine, and
what it could not confirm.

**Write `.crew/codemap/<subsystem>.md`**, each under 60 lines:
```
# <subsystem>
anchor: <repo>@<short-sha>
verified: <date>

## Does
<2 sentences>

## Entry points
- `path:line` — <what calls this and when>

## Owns data
- <table/collection> via `path`

## Calls out to
- <service/repo> at `path:line`

## Landmines
- <the thing that breaks when touched>

## Unverified
- <what you inferred but could not confirm>
```

**Anchors are the whole point.** Every claim names a file path. A map without
anchors cannot be re-verified, so it silently rots and you keep trusting it.

**Write `.crew/codemap/INDEX.md`** — one line per subsystem: name, one-sentence
purpose, anchor sha. This is the only codemap file loaded by default.

**Freshness rule** (put this in the repo CLAUDE.md too): before relying on a
codemap note, check whether its anchor files changed since the recorded sha:
`git diff --name-only <anchor-sha>..HEAD -- <paths>`. If they did, re-verify that
section before using it. Code always wins over notes.

## Then make the knowledge executable

A code map describes; it does not verify. Onboarding is not finished until the
repo also has:

1. `.crew/verify.json` — run `/crew:verify`. Which checks a change requires is
   the part that prevents mistakes; the description only helps you find things.
2. `.crew/secrets.md` — record where test credentials come from and which env
   var each lands in. Names and retrieval commands only, never values. See the
   `crew-verification` skill.
3. `e2e/` specs if this repo has a UI — delegate to `crew:browser-tester`.

Report which of the three are missing when you finish. A codemap on its own is
the least useful of the four artifacts.

## `--refresh <subsystem>`

Re-map one area after big changes, without re-running the whole thing on a
schedule — that is the cost onboarding was avoiding.

This follows `${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/reconcile.md` — the
same path `/crew:upgrade` uses, not a second implementation. Rebuild the graph
if it is stale (step 1), derive that one subsystem's `DERIVE` facts (step 3),
write them as a one-entry JSON file, then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/scripts/crew_upgrade.py \
  --root <repo> --derived <path-to-derived.json> --force
```

`--force` is required here even on an up-to-date schema: without it,
`crew_upgrade.py` sees `schema >= 2` and returns `already current` without
reconciling anything. The config rewrite this forces is a no-op merge of
already-current blocks; the reconciliation is the part `--refresh` is for.
Report any conflicts and any anchor left stale on purpose exactly as
`/crew:upgrade` does — surfaced, not resolved.
