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

**Which sha to record, and why it is not `HEAD`.** Use a commit that is already
on the default branch:

```bash
# On a feature branch this is the newest commit the trunk already has, which
# survives a squash, a rebase and a merge alike. On the default branch it IS
# HEAD, so the common case is unchanged.
git rev-parse --short=7 "$(git merge-base HEAD origin/main 2>/dev/null || echo HEAD)"
```

`git rev-parse --short HEAD` on a feature branch records a commit that **a
squash merge destroys**. The anchor then names an object the repository does
not contain, `git diff --name-only <anchor>..HEAD -- <paths>` cannot run, and
the map can be neither confirmed nor refuted -- while `crew_state` reports it
as `knowledgeUnverifiable` and the reader has to re-derive from scratch.

That is not hypothetical. Five maps in this repository carry
`useful-claude-add-ons@d61342c3`, written by `519754fa` -- whose subject is
"fix the codemap anchor writer" and which has one parent, because it was
squash merged. The four anchors that still resolve trace to commits made
directly on the default branch.

A merge-base anchor is slightly older than the work, and that is the right
direction to be wrong in: the per-path check then reports a superset of what
changed, so it over-reports staleness rather than under-reporting it.

**Write `.crew/codemap/INDEX.md`** — one line per subsystem: name, one-sentence
purpose, anchor sha. This is the only codemap file loaded by default.

**Freshness rule** (put this in the repo CLAUDE.md too): before relying on a
codemap note, check whether its anchor files changed since the recorded sha:
`git diff --name-only <anchor-sha>..HEAD -- <paths>`. If they did, re-verify that
section before using it. Code always wins over notes.

## 5. Map the data layer, if there is one

`## Owns data` in a subsystem note is one line per table. That is enough to say
*which* subsystem owns a table and nothing else — not its columns, not its
keys, not which code writes it. A reviewer asked whether a migration is safe,
or a DBA asked whether an index change is sound, gets nothing from it.

**Find the datasource first, and say so when there is none.** Look for
migrations, DDL, an ORM's model definitions, or a schema dump. If the repo has
no database, write no schema file and **report "no datasource found"**. Do not
write an empty one and do not infer a schema from variable names — a schema
file nobody can trace to a migration is the failure this whole command exists
to avoid.

**Write `.crew/codemap/schema-<datasource>.md`** — one per database, not per
table. It lives under `codemap/` on purpose: the anchor machinery, the
`knowledgeBehind` trigger and the per-path freshness check already walk that
directory, so a schema note goes stale as loudly as a subsystem note and costs
no new plumbing to do it.

```
# schema — <datasource>
anchor: <repo>@<short-sha>
verified: <date>
migration-head: <newest migration filename applied>

## Tables
### <table> — created `db/migrations/0042_x.sql:12`
- <column> <type> <null?> — `db/migrations/0042_x.sql:14`
- PK (<cols>) · FK <col> -> <table>.<col> — `...:19`
- INDEX <name> (<cols>) — serves `src/reports/query.py:88`

## Written by / Read by
- <table> — written `src/orders/repo.py:210`, read `src/api/list.py:44`

## Landmines
- <the column that looks nullable and is not; the table where a scan is fatal>

## Unverified
- <schema you can see in the live database with no migration to cite>
```

**Every row cites the migration or DDL line that creates it.** That is what
makes this DERIVED rather than a description, and it is the same contract the
subsystem notes carry. Use the same merge-base sha as above.

**Schema you cannot trace to a file goes in `## Unverified`, not in
`## Tables`.** A table created by hand in production, or by a migration that
was squashed away, is real and undocumented — those are different from a table
you confirmed, and collapsing the two is how a map starts getting trusted for
things it never checked. If you could not connect to anything and read only the
migrations, say that in `## Unverified` as one line.

**`## Written by / Read by` is the part reviewers actually use.** It is the
join between the schema and the code map: it answers "if I change this column,
what breaks", which is the question a migration review turns on. Derive it from
the graph where the graph can see it, and from grep where it cannot.

## 6. Generate the path-scoped rules

After any codemap note is written or refreshed, `--refresh` included, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_instructions.py" rules --root .
```

It writes `.claude/rules/<subsystem>.md` (≤30 lines, `paths:`-scoped, source hash) from each
note. Report every `wrote` and `removed` line. A `hand-written, left alone` line is a collision:
report it, never overwrite or rename it yourself. Commit the rules with the notes; CI checks them
for drift.

## Then make the knowledge executable

A code map describes; it does not verify. Onboarding is not finished until the
repo also has:

1. `.crew/verify.json` — run `/crew:verify`. Which checks a change requires is
   the part that prevents mistakes; the description only helps you find things.
2. `docs/reference/` — run `/crew:reference`. The codemap answers "where does
   this live"; the reference answers "what can this system do, and how do I call
   it". Those are different questions and the second does not fall out of the
   first. Endpoints, scheduled jobs, queue consumers, CLI commands, feature
   flags, integrations — each anchored to a file and line.
3. `.crew/secrets.md` — record where test credentials come from and which env
   var each lands in. Names and retrieval commands only, never values. See the
   `crew-verification` skill.
4. `e2e/` specs if this repo has a UI — write them in this session.
5. `context.autoClear` configured — run `crew_autoclear_setup.py plan-windows-default` (`${CLAUDE_PLUGIN_ROOT}/hooks/scripts/`; the same helper `/crew:init`'s Phase 1 uses, so a repo onboarded standalone gets the identical question). `status: unreadable` (parse failure) means say so and stop, fix by hand first. `status: already-configured` means stop, nothing to ask — a retained pre-1.0 `method: "windows"` is proposed for conversion instead, never already-configured. Otherwise, on native Windows propose `method: "notify"` and write it only on yes; elsewhere describe the tmux path and write nothing. Enabling it at all, and `sendkeys`, each need their own separate explicit yes.

Report which of the five are missing when you finish. A codemap on its own is
the least useful of the six artifacts.

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
`crew_upgrade.py` sees a `schema` at or above the current one and returns
`already current` without reconciling anything. The comparison is against
`crew_state.SCHEMA_CURRENT`, which moves — it has been 2, 3 and 4. Do not
restate the number here; this line said `2` long after the code had left it.

`--force` is not free on a repo that was never behind schema. Say these
consequences before running it, not after:

- `.crew/codemap/UPGRADE.md` is overwritten unconditionally, including its
  `schema <from> -> <current>` header — which reads as a migration on a repo
  that was already current, since `--force` runs the whole thing anyway.
  (This line used to quote the header as the literal `from schema: 1 -> 2`.
  It is interpolated from `notes["schemaFrom"]` and `crew_state.SCHEMA_CURRENT`,
  so the numbers move; do not restate them.) If a previous `/crew:upgrade` left contradictions there that
  nobody has verified yet, this run erases that list. Read the existing
  `UPGRADE.md` before running `--refresh` if one is present, and fold its
  unresolved contradictions into what you report afterward.
- `.crew/codemap.v1.bak/` is (re)confirmed if absent — on a repo that was
  never at v1, this creates a "v1 backup" that actually holds current-schema
  notes. Harmless, but say it happened; a stray backup with a misleading name
  is exactly the kind of thing that looks like evidence of a problem later.
- The config file is rewritten (reformatted and re-sorted) even though its
  content does not change — mention this if the user diffs `.crew/config.json`
  and is surprised to see churn.
- The command's own return status will say `"upgraded"` for a repo that was
  never behind. Report the reconciliation result (added facts, conflicts,
  stale anchors) instead of repeating that status verbatim.

Report any conflicts and any anchor left stale on purpose exactly as
`/crew:upgrade` does — surfaced, not resolved. Then run step 6.
