---
description: Bring a crew setup created before the PM and the code graph up to date
allowed-tools: Read, Write, Edit, Bash, Agent
---

Bring a v1 crew setup (no `schema` key) up to the current schema. This is a
migration, not a rebuild — it must not lose or silently skip anything a human
wrote.

## 1. Detect

Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py` first. Read
its `schema` field.

- `isCrew: false` — there is no `.crew/config.json` here. Say so and stop;
  `crew_upgrade.py` would report `not a crew repo` for the same reason.
- Config present but unreadable (a BOM that survives, truncated JSON, etc.) —
  `crew_upgrade.py` reports `config unreadable` and touches nothing: no
  backup, no write. Say the config could not be parsed and stop; a migration
  tool must never write `upgrade_config({})` over a file it could not
  understand.
- `schema >= 2` and `$ARGUMENTS` does not contain `--force` — print
  **"already current"** and stop. Do not touch the config, the codemap, or
  the graph. `crew_upgrade.py` makes this same check and returns
  `already current` without writing anything; do not re-derive graph facts
  or spend a `crew:explorer` budget ahead of a call that is about to no-op.
- Otherwise, continue.

## 2. Say what is about to happen, before it happens

Before running anything that writes: tell me the codemap is backed up first.
`crew_upgrade.py` copies `.crew/codemap/` to `.crew/codemap.v1.bak/` before
any other write, and will not overwrite an existing backup — so a second run
after an interrupted first one still has the original v1 notes. If
`.crew/codemap.v1.bak/` already exists, say that the backup already on disk
is being kept, not refreshed.

## 3. Build the graph if it is missing

Check `knowledge.graph.present` from step 1's `crew_state.py` output. If
false, follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/SKILL.md`'s **Build**
section — `graphify . --no-viz --code-only`, both flags required, never
optional. If `graphify` itself is absent, that skill's **Detect** section
governs: report it and stop. An upgrade cannot derive graph facts with no
graph and no CLI to build one, and it must not install anything without
asking.

If the graph is present but not current (`knowledge.graph.current: false`),
rebuild it the same way — a stale graph would hand `crew_upgrade.py` facts
about an older commit than the codemap it is reconciling against.

## 4. Derive graph facts per subsystem, hand them to `crew_upgrade.py`

Read `${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/reconcile.md` before this step
— it is the one place the JSON shape, the KEEP/DERIVE split, and the
path-not-`path:line` comparison rule are defined, and `/crew:onboard
--refresh` reads from the same file. Do not improvise a second version here.

For every `.crew/codemap/<name>.md` (skip `INDEX.md` and `UPGRADE.md`), query
the graph — `graphify query`/`graphify explain`, or the community that file's
own paths fall into — for facts about that subsystem, and build only the
`DERIVE` headings: `Entry points`, `Owns data`, `Calls out to`. Never put
`Does`, `Landmines`, or `Unverified` in this file; `graph_reconcile.py`
ignores them, but the calling command should not be handing over facts it
was never asked to reconcile in the first place.

Write the result to one JSON file, one entry per subsystem name, then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/scripts/crew_upgrade.py \
  --root <repo> --derived <path-to-derived.json>
```

Pass `--force` here if `$ARGUMENTS` had it (step 1). Without it, a repo whose
`schema` is already current hits `run()`'s early return and writes nothing —
the whole reason `--force` exists is to run this step anyway, so the flag has
to reach the actual invocation, not just gate step 1's early exit.

A subsystem with nothing new to add can be omitted from the JSON entirely —
`crew_upgrade.py` treats a missing key the same as an empty one.

## 5. Report — do not resolve

`crew_upgrade.py` writes `.crew/codemap/UPGRADE.md` itself; read it back and
surface it, do not re-derive it by hand:

- **Contradictions** — a path the codemap claims that the graph's derived
  facts did not corroborate. These stay in the codemap untouched. Report each
  one and say a human needs to verify it by hand; the graph is not assumed
  right here; it misses generated call sites, reflection, and dynamic
  dispatch, so either side can be the one that's wrong.
- **Anchors left stale on purpose** — subsystems whose `DERIVE` sections had
  nothing new to add this run keep their old `anchor:`. That is correct
  behavior, not a bug: `crew_upgrade.py` only bumps an anchor on a section it
  actually re-verified. A false freshness claim is worse than an honest stale
  one, because `crew-pm`'s freshness check and `knowledge.behind` both trust
  the anchor.

Neither list is something this command fixes on its own. Present both and
stop.

## 6. Say what this run did not do

State this explicitly, every run — a migration that silently declines work
reads as one that succeeded:

- It did not touch `## Does`, `## Landmines`, or `## Unverified` in any
  codemap — those pass through byte-identical, always, by design.
- It did not resolve any contradiction between the map and the graph, and it
  did not re-verify a stale-on-purpose anchor. Both need a human, or a
  targeted `/crew:onboard --refresh <subsystem>`.
- It did not grant `graph.obsidian.confirmed` — an upgrade never sets that
  flag; only explicit consent in session does.
- If the graph had to be built in step 3, say that graph freshness is
  commit-based: it describes the last commit, not uncommitted edits to
  tracked files.

**A run interrupted between the config write and the reconcile loop leaves
the repo half-upgraded.** `run()` writes `schema: 2` to the config before it
starts reconciling codemaps one file at a time, so a kill mid-loop leaves
some subsystems reconciled and others untouched, with the config already
saying "current." A plain re-run then reports `already current` and does
nothing — resuming requires `--force`, same as any other re-run of step 4.
Say this if the previous run's exit status is unknown.

Finish by naming the exit status `crew_upgrade.py` returned
(`upgraded`/`already current`/`not a crew repo`/`config unreadable`) so the
state of the repo is never left implicit.
