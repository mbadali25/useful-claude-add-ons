---
description: Bring a crew setup created before the PM and the code graph up to date
allowed-tools: Read, Write, Edit, Bash, Agent
---

Bring an out-of-date crew setup up to the current schema — a v1 one with no
`schema` key, or a v2 one predating the per-role provider table. This is a
migration, not a rebuild — it must not lose or silently skip anything a human
wrote, and it must not change where any role dispatches.

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
- `schema >= 3` (the current schema) and `$ARGUMENTS` does not contain
  `--force` — print **"already current"** and stop. Do not touch the config, the codemap, or
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

## 4b. Report the machine-global config — do not resolve it

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py   --root <repo> --check-global
```

`~/.claude/crew/config.json` sets defaults for every crew repo on this machine
and nothing about this repo will ever mention it. It is reporting-only and
always exits 0 — read the output, not the status. Surface every finding it
prints:

- **`absent`** — there is no global file, so every repo on this machine falls
  back to built-in defaults.
- **`unreadable`** — it exists but did not parse as a JSON object, so it
  contributes exactly nothing, silently.
- **`missing-keys`** — keys the current template defines that this file does
  not set. This is the case the whole guided-config work exists for: a global
  file with no `pm` block resolved every repo on the machine to
  `report-only`, and the user believed the PM was autonomous.
- **`repo-keys`** — keys a global file may not set, mostly because they
  describe a repository rather than a machine (`tracker`, `jira`,
  `obsidian.boardDir`, `graph.*`, `platform`, `tier`, `roles`, `verify`,
  `codemap`). **As of 0.16.0 these are IGNORED**: the global layer is filtered
  to machine-and-person keys before it is merged, so nothing here reaches any
  repo. Say that, not "every repo inherits them" — that was true until this
  release and is now the opposite of what happens. Someone who set
  `graph.obsidian.dir` globally made a reasonable-looking mistake that used to
  fail silently; tell them to move it into that repo's `.crew/config.json`.
  The finding also names nested strays a top-level diff cannot see, and a few
  keys that are simply not globally settable (`pm.maxDispatches`).
- **`inert-schema`** — a global `schema`, which genuinely never takes effect;
  it is read from the repo file alone so a global value cannot make an
  unmigrated repo look current.
- **`authority`** — the effective `pm.authority` for this repo, with the layer
  that decided it named.

**Do not fix any of this here.** Point at `/crew:config`, which is the guided
walkthrough for that file, and which asks before writing anything outside the
repository. This command never writes the global file.

## 5. Report — do not resolve

`crew_upgrade.py` writes `.crew/codemap/UPGRADE.md` itself; read it back and
surface it, do not re-derive it by hand:

- **Contradictions** — a path the codemap claims that the graph's derived
  facts did not corroborate. These stay in the codemap untouched. Report each
  one and say a human needs to verify it by hand; the graph is not assumed
  right here; it misses generated call sites, reflection, and dynamic
  dispatch, so either side can be the one that's wrong.
- **Config** — `.crew/codemap/UPGRADE.md` now opens with a `## Config`
  section, and `crew_upgrade.py` prints the same two lines at the CLI: the
  roles the migration ADDED and the tier it moved from and to. Read both out.
  An upgrade adds every ladder role at or below the tier the config already
  declares — those are roles a later release added at a tier this repo had
  already chosen — and it never moves a repo up a tier; `/crew:scale` does
  that, and `/crew:pm offboard` is still the only thing that removes a role.
  A crew that silently grows is exactly what `/crew:scale` exists to catch,
  so state the additions even when the answer is none.
- **Schema 2 → 3** — when the report names `qa.roles`, `dev.roles`,
  `qa.fallback` or `dev.fallback`, read the whole line out. Those keys arrive
  **neutral**: the role tables are empty, so every role still runs on its
  block's own `provider`, and `fallback` only fires when a pinned model has
  been retired, which used to be a plain error. **This repo dispatches exactly
  as it did before the upgrade.** Say that explicitly — a mandatory migration
  that quietly re-routed someone's development work to a different model would
  be indefensible, and the only way a user can be sure it did not is to be
  told.
- **Blocks left unmigrated** — a `pm`, `graph`, `qa`, `dev` or `roles` value
  that arrived as the wrong type is left exactly as the user wrote it, and
  `schema` is deliberately NOT stamped current. The status is then `upgraded
  with unmigrated blocks`, and the repo still reports an upgrade as needed.
  Name each block and say it needs a hand edit before a re-run.
- **Anchors left stale on purpose** — subsystems whose `DERIVE` sections had
  nothing new to add this run keep their old `anchor:`. That is correct
  behavior, not a bug: `crew_upgrade.py` only bumps an anchor on a section it
  actually re-verified. A false freshness claim is worse than an honest stale
  one, because `crew-pm`'s freshness check and `knowledge.behind` both trust
  the anchor.

Neither list is something this command fixes on its own. Present both and
stop.

## 5b. Offer the per-role model table — do not leave them to find the keys

Schema 3 gave `qa` and `dev` a per-role provider table, and the migration
deliberately left it empty. Show the user what they now have and what they
could set, rather than mentioning a config key and moving on:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root <repo> --models
```

That prints, per role, the effective provider, model and family, which
fallbacks are armed, and whether the self-review guard is currently barring
anything. Then offer this table, probing the ids first — `copilot -p "say ok"
--model <id>` returns `Model "<id>" from --model flag is not available` before
it bills anything, and an empty prompt short-circuits before validation, so the
probe needs a real one. Verified on this machine 2026-09-05:

| Slot | Suggested pin | Family |
|---|---|---|
| `dev.roles.developer`, `dev.roles.security`, `dev.roles.infrastructure-architect` | `codex` / `gpt-6-astra` | gpt |
| `dev.roles.planner` | `claude`, with a `codex` / `gpt-5.6-sol` alternate | claude |
| `qa.roles.phase1`, `qa.roles.smoke` | `codex` / `gpt-5.6-sol` | gpt |
| `qa.roles.review`, `qa.roles.gate` | `codex` / `gpt-5.6-luna` | gpt |
| a Copilot alternative | Kimi 2.7 (`kimi-k2.7-code`), or Kimi 3 (`kimi-k3`) | kimi |

Three things to say before writing any of it:

- **Guard first, pin second.** `gpt-5.6-sol` and `gpt-5.6-luna` are the same
  `gpt` family as `gpt-6-astra`, so on a diff **codex wrote** they are barred
  and QA falls to claude or kimi. **Pinning the developer to codex therefore
  means most dev work is codex-authored, so the Sol and Luna QA pins fire on
  claude-authored work and comparatively rarely elsewhere.** That may be
  exactly what the user wants. It must not be something they discover from a
  review log.
- **The planner's `alternate` is an alternate, not a replacement.** The planner
  works from an abstracted brief and `secondOpinion.sendsCode` is `false` by
  design. Neither changes here.
- **The `-code` suffix on Kimi 2.7 is load-bearing.** Bare `kimi-k2.7` is
  rejected by the Copilot CLI; the value that goes in the config is
  `kimi-k2.7-code`.

A model table is usually a fact about the person and the machine, not about one
repository, so offer `/crew:config` for it. The repo layer still overrides it
where one project genuinely wants a different reviewer. Write nothing here
without being asked — this command reports.

## 6. Say what this run did not do

State this explicitly, every run — a migration that silently declines work
reads as one that succeeded:

- It did not touch `## Does`, `## Landmines`, or `## Unverified` in any
  codemap — those pass through byte-identical, always, by design.
- It did not resolve any contradiction between the map and the graph, and it
  did not re-verify a stale-on-purpose anchor. Both need a human, or a
  targeted `/crew:onboard --refresh <subsystem>`.
- It did not grant `graph.obsidian.confirmed` — an upgrade never sets that
  flag; only explicit consent in session does. Adding roles is not a
  counter-example: a role is a capability and reversible, and that flag is
  consent to write into the user's own notes outside the repo.
- It did not remove a role, and it did not touch `~/.claude/crew/config.json`.
- If the graph had to be built in step 3, say that graph freshness is
  commit-based: it describes the last commit, not uncommitted edits to
  tracked files.

- It did not write a single per-role model pin. Schema 3's `qa.roles` and
  `dev.roles` arrive empty and step 5b only OFFERS a table; a migration that
  chose a model for someone would be the same "a default nobody chose" failure
  the guided-config work exists to close.

**A run interrupted between the config write and the reconcile loop leaves
the repo half-upgraded.** `run()` writes the current `schema` to the config before it
starts reconciling codemaps one file at a time, so a kill mid-loop leaves
some subsystems reconciled and others untouched, with the config already
saying "current." A plain re-run then reports `already current` and does
nothing — resuming requires `--force`, same as any other re-run of step 4.
Say this if the previous run's exit status is unknown.

Finish by naming the exit status `crew_upgrade.py` returned (`upgraded`/
`upgraded with unmigrated blocks`/`already current`/`not a crew repo`/`config
unreadable`) so the state of the repo is never left implicit.
