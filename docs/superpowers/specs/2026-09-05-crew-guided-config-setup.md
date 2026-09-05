# crew: guided config setup, global and repo

**Status: SPEC — queued as the PR after `obsidian-vault` 0.2.0.**

Date: 2026-09-05

## Problem

The machine-global config at `~/.claude/crew/config.json` sets defaults for
every crew repo on the machine, and **nothing in crew ever writes it or asks
about it.** `skills/crew-setup/SKILL.md` says so in as many words:

> `/crew:init` writes this file; it never writes the optional machine-global one
> at `~/.claude/crew/config.json`. ... Nothing in setup creates the global file;
> a user who wants one writes it by hand.

Writing it by hand requires knowing the file exists, where it lives, which keys
it accepts, and how it layers. `templates/` ships one template, for the repo.

**This is not hypothetical.** On this machine the global file existed, carried
`tier`, `roles`, `qa` and `sdp`, and had **no `pm` block at all** — so every
crew repo silently defaulted to `pm.authority: "report-only"`. The user
believed the PM was autonomous. Nothing surfaced the discrepancy: the global
file was valid, the repos were valid, and the resulting behaviour was a default
nobody chose. It was found only because someone read the file for an unrelated
reason.

A default nobody chose, that nothing reports, is the failure this work closes.

## Scope

1. **A global config template**, alongside the existing repo one.
2. **A guided walkthrough** for the global config, with repo options offered.
3. **`/crew:upgrade` detects a global config that is missing, stale, or missing
   keys**, the same way it already detects an out-of-date repo schema.

## 1. Templates

`templates/` currently holds `config.template.json` only, and a committed test
asserts it equals `crew_config.default_config()` byte-for-byte, so drift fails
CI rather than surfacing on someone else's machine. Both properties must hold
for the new one.

- Rename or keep `config.template.json` as the repo template, and add
  `global.template.json`.
- The global template must **not** be a copy of the repo one. Most repo keys are
  meaningless globally — `tracker`, `jira.project`, `obsidian.boardDir`,
  `graph.out` and `platform.*` are facts about one repository or one checkout.
  Shipping them globally invites a user to set a vault path once and have every
  repo inherit a board that does not describe it.
- Keys that genuinely belong globally are the ones whose right answer is a
  property of the *machine or the person*, not the project: `pm.authority`,
  `qa.provider` / `qa.order` and the provider model pins, `secondOpinion`,
  `notify`, and `memory.vaultPath`.
- Add a `default_global_config()` beside `default_config()`, and extend the
  byte-for-byte test to cover the second template.

## 2. The walkthrough

Offer it from `/crew:init` (which today writes only the repo file) and make it
reachable on its own for a user who has no repo in mind. `crew-setup`'s existing
phased, resumable shape is the model — do not invent a second setup idiom.

What it must do:

- **Show what is currently in effect, and where each value comes from.**
  `crew_config.resolve_config` already layers built-in defaults, then global,
  then repo. The walkthrough should print the resolved value *and its source*,
  because "where is this coming from" is precisely the question the `pm`
  incident above could not answer.
- **Ask before writing outside the repo.** `~/.claude/crew/config.json` is the
  user's own global configuration. `crew-setup` already refuses to delete a
  global `find-skills` on exactly this reasoning — "a setup skill that quietly
  reaches into `~/.claude` is worse than the collision it fixes." Same rule
  applies to writing.
- **Never silently widen authority.** `pm.authority` is the one key where a
  wrong default is unrecoverable by the user — they either get agents they did
  not ask for, or a report when they expected work. State the two values and
  what each means before writing either.
- **Merge, never replace.** A user with an existing global file must not lose
  keys the walkthrough does not ask about.

## 3. `/crew:upgrade` catches it

`crew_upgrade.upgrade_config` operates on one config dict and `commands/
upgrade.md` is entirely about the graph and the codemap. Neither looks at the
global file.

Add a detection step that reports, without fixing anything unasked:

- No global config exists, and what that means (every repo on built-in defaults).
- A global config exists but is missing keys the current schema defines —
  the `pm` case above.
- A global config carries repo-only keys that will never take effect there.
- The effective `pm.authority` for this repo, with its source named.

`upgrade.md` §5 is already "Report — do not resolve", which is the right shape.
Follow it; do not have upgrade write the global file on its own.

## 4. `upgrade_config` migrates two blocks and claims to have migrated all of them

Reported by the user 2026-09-05: `/crew:upgrade` did not pick up the provider
and roles changes. Confirmed in `skills/crew-graph/scripts/crew_upgrade.py`.
The whole of the migration is:

```python
out["pm"]     = _merged(PM_BLOCK,    cfg.get("pm"))
out["graph"]  = _merged(GRAPH_BLOCK, cfg.get("graph"))
out["schema"] = crew_state.SCHEMA_CURRENT
```

`qa`, `dev` and `roles` are never touched — and `schema` is stamped current
regardless. Its docstring still reads "v1 config -> v2": it was written for that
one migration and never extended when 0.14.4 added the `qa`/`dev` provider table
or when 0.15.x added `infrastructure-architect`, `scribe` and `researcher`.

So a config predating 0.14.4 comes out of an upgrade marked current while
missing `qa.order` and the entire `dev` block. The downstream symptom is already
recorded in `CHANGELOG.md`: "`qa.order` absent made `/crew:model` report zero
candidates and 'no independent reviewer' for a setup that reviews fine."

Required:

- Migrate `qa` and `dev` forward from `default_config()` the way `pm` and
  `graph` already are, preserving any value the user set.
- **Migrate `roles` forward too — add the new roles, do not merely report
  them.** Decided by the user 2026-09-05, overriding the narrower proposal that
  an upgrade should report new roles and leave the choice alone. An upgrade
  brings a config up to date; a config that omits roles the release added is out
  of date, and making the user re-derive that from a report is the same "a
  default nobody chose" failure this whole document is about.

  Two things this does **not** license, because they are different decisions
  from adding capability:

  - **Removal still stops for an explicit yes.** Adding a role is reversible and
    additive; removing one destroys the coverage that would tell you whether the
    removal was right. `/crew:pm offboard` keeps its gate.
  - **`graph.obsidian.confirmed` stays un-grantable.** It is a consent flag for
    writing into the user's own notes outside the repo, not a capability, and
    the existing code is right to reset it.

  Recompute `tier` from `crew-scaling`'s tier table after adding, and say in the
  report which roles were added and what the tier moved from and to — a crew
  that silently grows is the thing `/crew:scale` exists to catch.
- The three roles added in 0.15.x are **off the tier ladder** — not rows in
  `crew-scaling`'s tier table, so `/crew:scale` will not propose them and
  `/crew:pm` will not onboard them from evidence. Adding those rows is part of
  this work, or the report above has nothing to point the user at.
- Stop stamping `schema` current unconditionally. If a block could not be
  migrated, say so rather than marking the config done.
- Fix the docstring. "v1 config -> v2" is now false and is exactly what let this
  go unnoticed.

## Constraints

- `CLAUDE.md` is binding: version bump in **both** `.claude-plugin/
  marketplace.json` and `plugin/crew/.claude-plugin/plugin.json` to the same
  value, in the **last** commit; plus `PLUGINS.md`, `README.md` counts,
  `CHANGELOG.md`, and `plugin/UPDATE.md` followed by `scripts/sync-updates.py`.
- Gates judged by **exit code**: `check-marketplace.py`, `sync-updates.py
  --check`, `validate-prompts.py`, `pytest plugin/crew/tests`, `pylint`.
- `schema` is exempted structurally inside `resolve_config` and must stay that
  way — a global file carrying a current `schema` must never make an unmigrated
  repo look current. See that function's docstring.

## Tests

- `default_global_config()` equals `global.template.json` byte-for-byte.
- Layering: a global value is overridden by a repo value; a global-only value
  survives; a repo-only key in the global file does not leak into a repo that
  did not ask for it.
- The `pm` regression specifically: a global file with no `pm` block resolves to
  `report-only` **and the walkthrough and upgrade both say so out loud.**
- A merge into an existing global file preserves unknown keys.
