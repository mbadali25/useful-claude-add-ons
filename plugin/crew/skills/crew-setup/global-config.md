# The machine-global config walkthrough

Shared by the `crew-setup` skill, `/crew:config` and `/crew:init` Phase 1. One
source of truth.

`~/.claude/crew/config.json` sets defaults for **every crew repo on this
machine**. Until 0.16.0 nothing in crew ever wrote it or asked about it, and
writing it by hand required knowing it existed, where it lived, which keys it
took and how it layered. The failure that produced this file was not
hypothetical: a global file that carried `tier`, `roles`, `qa` and `sdp` but
**no `pm` block** silently resolved every repo on the machine to
`pm.authority: report-only`. Every file involved was valid. The behaviour was a
default nobody chose, and nothing surfaced it.

So the whole point of this walkthrough is the **source** column, not the value
column. Run it even when nothing needs changing.

## Rules that are not negotiable

- **Ask before writing outside the repo.** `~/.claude/crew/config.json` is the
  user's own configuration. `crew-setup` already refuses to delete a global
  `find-skills` on exactly this reasoning — a setup skill that quietly reaches
  into `~/.claude` is worse than the collision it fixes. Writing is the same
  rule. The script defaults to a dry run; `--apply` is the second call, after
  a yes.
- **Never silently widen authority.** State both values and what each means
  before writing either, and read the `!` line back when the plan widens it.
- **Merge, never replace.** The script merges; do not hand-write the JSON, and
  never `cat >` over the file. A user with an existing global file must not
  lose a key this walkthrough never asked about.
- **Repo facts do not go in this file, and as of 0.16.0 they do NOTHING if
  they are there.** `tracker`, `jira.project`, `obsidian.boardDir`, `graph.*`,
  `platform.*`, `verify`, `codemap`, `tier` and `roles` describe one
  repository. The script refuses them on the write path and the resolver
  filters them out on the read path — **a repo-only key in the global file
  takes effect nowhere.** That is a behaviour change: until this release they
  were inherited by every repo that did not override them, so someone who set
  a vault path globally gave every repository on the machine a board that did
  not describe it. Do not work around either guard; move the key into that
  repo's `.crew/config.json`.
- **A global value is still a DEFAULT, not a lock.** Everything that survives
  the filter is overridable per repo. One project may legitimately want a
  different reviewer, and step 1's `source` column is what shows which layer
  a value actually came from.
- **`graph.obsidian.confirmed` is not settable here, ever.** It is consent to
  write into the user's own notes outside the repo, not a capability. Only the
  user, in session, grants it. Doubly un-grantable since 0.16.0: refused on
  the write path, and dropped on the read path however it got into the file.

## 1. Show what is in effect, and where each value comes from

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root <repo> --explain
```

Every globally-settable key with its effective value and the layer that decided
it: `repo`, `global`, or `default`. Show this table before asking anything.
`--root` is optional outside a repo — with no `.crew/config.json` the `repo`
layer is simply empty, which is the right answer for a user who has no repo in
mind yet.

Then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root <repo> --check-global
```

That prints the findings `/crew:upgrade` reports too: no global file, a file
that did not parse, keys the current template defines that this file does not
set, keys the global layer IGNORES, an inert `schema`, and the effective
`pm.authority` with its source named. Both commands are reporting-only and
always exit 0 — read the output, not the status.

Read the `repo-keys` finding out in full when it fires. Those keys are doing
nothing, and a key that quietly does nothing is worse than one refused out
loud — name each and say which repo's `.crew/config.json` it belongs in.

## 2. Ask, one block at a time

Do not ask about everything. Ask about what the table above shows coming from
`default` and what the user has a real answer for. In this order:

**`pm.authority`** — always ask, even when it is already set, because this is
the key the incident was about.

> The crew manager can either recommend work and wait for you, or dispatch the
> crew itself when it spots something. This sets the default for every repo on
> this machine; a repo can still override it.
> - `report-only` (default) — it tells you what it would do, you decide.
> - `act` — it dispatches roles and refreshes diagrams on its own, reports
>   after. Removal, deletion, offboarding and rewriting `.crew/metrics.md`
>   still stop for an explicit yes, whatever this is set to.

Default `report-only` on any hesitation.

**`qa` and `dev`** — which reviewer and implementer CLI are installed on this
machine, and which model each may use. This is a machine fact: a repo cannot
know whether `codex` is on PATH. `qa.copilot.model` must be pinned to a family
that is neither the author's nor Codex's before Copilot can review at all —
`crew-providers` has the current names and two that died of churn.

Show the current per-role table before asking, rather than describing keys:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root <repo> --models
```

**`qa.roles` and `dev.roles`** — the per-role pins. Empty by default, which
means every role runs on its block's own `provider`. Offer this table, probing
each id first (`copilot -p "say ok" --model <id>` reports `Model "<id>" from
--model flag is not available` before it bills anything; an empty prompt
short-circuits before validation, so the probe needs a real one). Verified
2026-09-05:

| Slot | Suggested pin | Family |
|---|---|---|
| `dev.roles.developer`, `dev.roles.security`, `dev.roles.infrastructure-architect` | `codex` / `gpt-6-astra` | gpt |
| `dev.roles.planner` | `claude`, with a `codex` / `gpt-5.6-sol` alternate | claude |
| `qa.roles.phase1`, `qa.roles.smoke` | `codex` / `gpt-5.6-sol` | gpt |
| `qa.roles.review`, `qa.roles.gate` | `codex` / `gpt-5.6-luna` | gpt |
| a Copilot alternative | Kimi 2.7 (`kimi-k2.7-code`), or Kimi 3 (`kimi-k3`) | kimi |

Three things to say before writing any of it:

- **The family guard is evaluated FIRST, the pin second.** `gpt-5.6-sol` and
  `gpt-5.6-luna` are the same `gpt` family as `gpt-6-astra`, so on a diff
  **codex wrote** they are barred and QA falls to claude or kimi. **Pinning the
  senior developer to codex therefore means most dev work is codex-authored,
  so the Sol and Luna QA pins fire on claude-authored work and comparatively
  rarely elsewhere.** That may be exactly what the user wants. It must not be
  something they discover from a review log.
- **The planner's `alternate` is an alternate, not a replacement.** The planner
  works from an abstracted brief and `secondOpinion.sendsCode` stays `false`.
- **The `-code` suffix on Kimi 2.7 is load-bearing.** The display name is
  "Kimi 2.7"; the value that goes in the config is `kimi-k2.7-code`. Bare
  `kimi-k2.7` is rejected by the Copilot CLI.

**`qa.fallback` and `dev.fallback`** — the model a role falls back to when its
pinned model has been retired, defaulting to `claude-sonnet-5`. Different from
`qa.order`, which covers a provider that is missing or unauthorised. Say that a
fallback which fires is always announced: a review that quietly ran on the
fallback looks identical to one that ran on the pin, and the difference matters
most exactly when the pin was chosen to get a different family onto the diff.

**`secondOpinion`** — the design partner CLI, its key env var, and
`sendsCode`, which is a standing decision by the person, not by a project.

**`notify`** — the person's own chat, not the project's.

**`memory.mode` and `memory.vaultPath`** — **both** are global as of 0.16.0.
One vault per person, and a person who keeps their memory in a vault keeps it
there everywhere; making them say so once per repository was the friction that
produced this split. A repo that genuinely wants its memory in `.crew/` still
overrides `memory.mode` in its own config.

## 3. Show the plan, then write

Dry run first — this is the default, and it is what the user says yes to:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py \
  --set pm.authority='"act"' --set qa.provider='"codex"' \
  --set qa.roles='{"review": {"provider": "codex", "model": "gpt-5.6-luna"}}'
```

Each `--set` takes `path=JSON`, so a string needs its quotes (`'"act"'`), and
`true`, `false`, `null`, lists and objects are written as JSON. `qa.roles` and
`dev.roles` are set as whole objects — the table is open, so any role name is
accepted, including one this release does not ship. The output names every key
that would change, from what to what, and prints a `!` line for a widening of
`pm.authority`.

Read that back. Then, and only then, add `--apply` to the same command to
write it. A refused key exits 2 and names the key; that is the guard working,
not a bug to route around.

## 4. Say what this did not do

- It did not touch any `.crew/config.json`. The repo layer still wins over
  everything written here.
- It did not change `schema`, `tier` or `roles` anywhere — those are repo
  facts, and the tier ladder moves only through `/crew:scale`.
- If `pm.authority` changed, say the new value and that `/crew:pm authority
  <value>` overrides it per repo.
- If any per-role pin changed, run `--models` once more and read the resulting
  table back. Name which fallbacks are now armed, whether the family guard is
  barring anything, and — always alongside the bars — the `qa.order`
  fall-through line saying what reviews the diff instead. If it reads `NO
  INDEPENDENT REVIEWER`, say so in full: the review still runs, on the
  `qa-reviewer` subagent, labelled same-family. A config change nobody
  verified is a claim, not a change.
- If the `repo-keys` finding fired in step 1, say the keys are still sitting in
  the file doing nothing, and that this walkthrough did not delete them.
  Removing something from the user's own global config needs an explicit yes.
