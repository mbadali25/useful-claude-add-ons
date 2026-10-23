# crew configuration rationale

This file is the design rationale behind crew's settings: why a key lives in one layer or both, why some keys resolve to the narrower layer, and what each guard and gate does with its value. The list of keys, their values and defaults is the generated `plugin/crew/CONFIG.md`; this file explains the decisions that list cannot.

Every claim below is a `file::symbol` you can grep for, a config key named beside it, or a value printed by running the function named beside it. Citations name symbols, never line numbers, on purpose: when line numbers were last measured, 11 of 13 were wrong, each landing on real code in the wrong function. A symbol name breaks loudly when it is renamed. Headings are unnumbered, and a reference to another part of this file names its heading.

Settings are few on purpose. A key that no measured configuration ever changed became a code constant, and the twelve per-guard keys became one profile plus an overrides table. See "Removed keys and migration" at the end.

---


## The two layers

| Layer | File | Read by |
|---|---|---|
| repo | `.crew/config.json` in the repository root - or, in a linked worktree with neither `.crew/config.json` nor `.crew/crew.json`, the main checkout's (`crew_common.repo_config_dir`) | `crew_state.load_config` |
| machine-global | `~/.claude/crew/config.json` | `crew_config.py::read_global_config` |

**The repo file is `.crew/config.json`** (L-0713). `/crew:init` writes it from<!-- claim: crew-config-file:config.json -->
`templates/config.template.json`, `/crew:config` and `crew_config.py --repo` edit it, and every
gate, guard and setting reader opens it (the Python ones through `crew_common.repo_config_file`,
whose default name is `config.json`). A new repository needs no `/crew:migrate`. `.crew/crew.json` exists only where
`/crew:migrate` ran on a crew 0.20 setup: a schema-1 record of the old config, with
`.crew/config.json` left in place and still read. Where it exists, `crew_context`, `crew_resume`,
`crew_refresh_check`, `crew_diagrams` and `/crew:status` read it before `config.json`, and
`crew_tracker` reads both and refuses when they disagree; no gate or guard reads it.

Both are optional. `read_global_config` **never raises**: an absent, malformed,
or non-object global file returns `{}` and is indistinguishable from no file at
all. That contract is load-bearing — `resolve_config` is reached from a
`SessionStart` hook, and a broken file in `~/.claude/` must not wedge every
session on the machine.

Nothing in `crew_config` ever writes the global file except
`crew_config.py::write_global_config`, which its own docstring names as
the only function in crew that writes outside the repo.

### How the two are merged

`crew_config.py::resolve_config` is the single resolver. Read it as five
steps, in this order:

```python
repo_cfg = crew_state.load_config(root)
global_cfg, _ = filter_global(read_global_config())
repo_cfg = without_null_shadows(repo_cfg, global_cfg)
merged = crew_state.merge_defaults(default_config(), global_cfg)
merged = crew_state.merge_defaults(merged, repo_cfg)
if "schema" in repo_cfg:
    merged["schema"] = repo_cfg["schema"]
else:
    merged.pop("schema", None)
return merged
```

So precedence is **repo beats global beats shipped default**, with two
structural exceptions, both visible above: the global layer is pruned before it
is consulted at all (see "The invariant"), and `schema` is lifted out of the
merge entirely (see "schema").

**And exceptions that are not visible above, because they do not go
through this function at all: `install.policy`, the twelve guards (see
"guards") and `change.requireForProduction`.**
Each resolves to the *lower* of the two layers rather than to the repo's, so a
cloned repo cannot widen what the machine owner allowed. Anything reading one
through `resolve_config` gets the precedence answer and is wrong;
`crew_config.py::resolve_ratcheted` is the only correct reader, and
`resolve_install_policy` and `resolve_guard` are its two thin wrappers.
`crew_state.py::RATCHETED_KEYS` is the list, and it is the only list.

**Resolve through this function, never by re-reading `.crew/config.json`.**
That file is one layer of three and does not know about the `qa.roles` and
`dev.roles` tables at all. `skills/crew-review/SKILL.md` carries the scar: reading it directly made
both `qa.roles.review` and every value in `~/.claude/crew/config.json`
invisible to the only command that actually runs a review.

### Null shadowing

`/crew:init` writes `templates/config.template.json`, which spells out **every**
key including the ones whose default is `null`. `merge_defaults` treats an
explicit `null` as a supplied value, so it beat the global layer — and the
global file therefore did nothing for any repo that had been initialised, which
is every managed repo.

`crew_config.py::null_shadows` and `without_null_shadows`
(`crew_config.py`) fix that on the read path. The rule is deliberately
narrow, and the narrowness is the point:

- A repo `null` is dropped **only** where the global layer supplies a real
  value at that path (`_layer_supplies`, `crew_config.py::_layer_supplies`).
- A repo `null` with nothing underneath it is left alone. `context.reserveTokens:
  null` still means *off* and does not silently become `100000`.

It is not fixed inside `merge_defaults` because `crew_upgrade.upgrade_config`
shares that function, and changing null semantics there would rewrite users'
files on migration rather than only resolving them for a read
(`crew_config.py`, a comment).


### In a linked worktree

Since crew 1.0.69 (T-0088) every Python reader of the repo config opens
`crew_common.repo_config_file(root, name)`, which resolves the `.crew/`
directory in this order:

1. The worktree's own `.crew/` when it holds `config.json` **or** `crew.json`.
   Both files are then read from there and nothing is inherited, even when
   they are partial: the two checkouts' files are never merged.
2. `.git` a directory, or missing: the repository's own `.crew/`, with no git call.
3. `.git` a file (a linked worktree or a submodule): `git rev-parse
   --git-dir --git-common-dir`, each path joined to the worktree's top (no
   `--path-format`, which git before 2.31 does not know). A submodule (git-dir equals
   common-dir) or a bare common directory (not named `.git`) has no main
   checkout and reads its own `.crew/`. Otherwise the main checkout's `.crew/`,
   when it holds either file.
4. When git cannot answer, the source is `unknown`: the worktree's own `.crew/`
   is read (nothing inherited), and `/crew:status` and `/crew:config --explain`
   print that git could not tell.

**A lane made before crew 1.0.69 has a config of its own already.** Every
SessionStart heal on crew 1.0.68 or earlier wrote a default `.crew/config.json`
into a lane worktree that had none, so rule 1 applies and nothing is inherited.
`/crew:status` and `/crew:config --explain` name that case: a linked worktree
whose own file is in force while the main checkout also has one prints `the
main checkout's (<path>) is not read`. If the lane's file is a default nobody
edited, delete it (and `.crew/crew.json`, if present) to inherit; from 1.0.69
the heal path creates nothing there again.

The writers never follow it: `crew_platform` (heal and `platform-sync`),
`crew_autoclear_setup`, `crew_migrate`, `/crew:init` and the machine-global writer
keep their own-path behaviour, and the heal path creates nothing in a worktree
that inherits a config, or in one where git could not tell.

**The shell and PowerShell resolvers (crew 1.0.330, T-0096).** `crew_repo_config_dir` in
`hooks/scripts/_common.sh` sets `CREW_CFG_DIR` and `CREW_CFG_SOURCE` (`own`, `main`
or `unknown`) by rules 1-4 above, with no python; `Get-CrewRepoConfigDir`, one
body copied verbatim into `promote-gate.ps1` (and, until L-0727 slice 3
deleted them, `cloud-guard.ps1` and `auto-clear.ps1`), is its PowerShell twin. `tests/test_worktree_config_shell.py`
holds both to `crew_common.repo_config_dir` case by case and the copies
byte-identical. Windows PowerShell 5.1 cannot resolve a symlink the way
`realpath` does, so on every PowerShell (7 as well) a symlink, a junction, or an
ancestor `Get-Item` cannot read (likely a UNC share's root) in either path the
PowerShell resolver compares reads `unknown`, never `main`. It pins
`[Console]::OutputEncoding` to UTF-8 around its git call, so a non-ASCII path
survives a console on the OEM code page. In the cloud guard's bash fallback a
missing resolver (`_common.sh` failed to source) also counts as armed. Routed: the `emergency.standDown` read (`_common.sh`'s
`crew_incident_active`, `promote-gate.ps1`), the cloud guard's no-python fallback
in both flavours until slice 3, where **`unknown` counts as armed**, and
`auto-clear`'s repo veto, and (L-0680) the session hooks `notify`, `handoff-read`,
`handoff-write` and `context-watch`, whose writes stay in the worktree (except notify's:
since T-0051 `crew_notify.py` writes its dedupe state to `<git-common-dir>/crew/notify`,
shared by every worktree) and whose
handoff file is always `.work/HANDOFF.md` inside the worktree. The
verify gate (both flavours), `review_gate.py`, the gate's fingerprint and the
scope and completion wrappers' no-python proof read the resolved file too
(L-0681); in those wrappers `unknown` is never proof that `scope.mode` is off.
`.crew/verify.json` is never inherited.

## The invariant

> **What the global file may WRITE is exactly what the global layer may SUPPLY.**

One definition, `default_global_config()` (`crew_config.py::default_global_config`), enforced from
both directions:

| Direction | Function | Mechanism |
|---|---|---|
| READ — what a global file may supply | `filter_global` | `_prune` keeps only keys present in `default_global_config()`, and returns the dropped paths as `ignored` |
| WRITE — what a guided flow may set | `plan_global_write` | refuses any path for which `is_global_path` is false, by name, with the full allowed list in the message |

`is_global_path` agrees with `filter_global` by construction — both stop
descending at a template **leaf**.


**The counts are generated, not argued here.** `leaf_paths(default_global_config())` and `leaf_paths(default_config())` give the machine and repo leaf sets, and the generated `plugin/crew/CONFIG.md` states both counts and which keys are repo-only. For every path, `filter_global` and `is_global_path` (which `plan_global_write` refuses on) agree on whether it is settable. Every count this file used to carry was a fact about one commit and was wrong a few commits later, so none is repeated here: re-measure with `leaf_paths` instead of trusting a number in prose.


### The one asymmetry, and it matters

The two rules agree on **which paths**. The write path additionally rejects
**values** the read path only reports:

- `plan_global_write` runs `crew_config.py::validate_providers` on the
  *merged result*, and raises `ProviderError` for a bad `qa.provider`,
  `dev.provider`, a bad name inside `qa.order`, or a bad provider in
  `qa.roles.<r>` / `dev.roles.<r>`.
- `resolve_config` **never raises**. A bad provider already on disk is reported
  by `crew_config.py::provider_problems` and nothing more.

A reader who takes "exactly what" to mean "identical behaviour" will be
surprised the first time a write is refused for a value a file on disk is
allowed to hold. That asymmetry is deliberate: refuse at the boundary where the
value enters, report at the boundary that must not crash a session hook
(`crew_config.py`, a comment stating exactly this).

### Open tables

`leaf_paths` treats an **empty dict as a leaf**. `qa.roles` and `dev.roles` ship
as `{}`, so everything beneath them is settable in either layer without crew
enumerating the role names:

```
dev.roles.some-role-invented-in-2030.model    # allowed by both rules
```

Confirmed by running `is_global_path` on exactly that path.

### Refused by both layers

Checked by running both predicates. Each of these is a fact about one
repository or one checkout, so a global file that set it would quietly hand the
same answer to every repo on the machine:

`schema`, `tracker`, `jira.project`, `verifyGate`, `graph.out`, `obsidian.*`,
`platform.*`, `emergency.*`, and every `context.*` key other than
`context.autoClear`.

A consent to act outside the repo is never a capability a guided flow may hand
over. `plan_global_write`'s docstring states the rule: a global file that
carried such a consent would grant it to every repo on the machine.


### What a guided write does

`plan_global_write` is pure and returns `(merged, changes)`. Two rules it
enforces in code rather than prose:

- **Merge, never replace.** Every key the existing file carries that `updates`
  does not name survives byte-for-byte, *including keys this module has never
  heard of*.
- A change to `pm.authority` that **widens** is flagged with
  `widens_authority`, computed by `crew_state.authority_rank`, not by equality.
  The comment at `crew_config.py` records why: the equality form was
  correct only while `act` was the top tier, and with three tiers it was wrong
  in *both* directions — `act → autonomous` computed `False` (the widest grant
  crew offers shipping unannounced) and `autonomous → act` computed `True` (a
  warning on the safe direction, which is what teaches users to click past it).


---

## Reading a value

- The default of a key is what `default_config()` returns. For every global-settable key, `default_global_config()` returns the same value, verified by comparison, so there is no second default to keep in your head.
- A **list is a leaf.** `qa.order` and `notify.events` are replaced wholesale, never merged element-wise (`crew_config.py::leaf_paths`).
- The key tables list the keys `default_config()` DECLARES. A key read by crew code but declared by no default is invisible to `leaf_paths`, to `/crew:config --explain`, and to the global layer (`is_global_path` refuses any path absent from the global template). That is why every key crew reads is declared.
- A **consumer** is a symbol or a command file that reads the key to decide something. A Markdown command file counts: crew is prose-driven and an agent executing a command file is the code path. Where only a default block, a template or a test references a key, that key has no consumer and does not belong in the config.

---


## `schema`

| | |
|---|---|
| Type | integer |
| Current value | `8` (`crew_state.SCHEMA_CURRENT`, dumped by execution) |
| Layer | **repo only**, and exempt from inheritance *structurally* |

`schema` is absent from `default_global_config()`, so `filter_global` prunes it
from a global file and `plan_global_write` refuses to write it. But it gets a
second, stronger guarantee: even if it somehow survived the merge,
`resolve_config` overwrites it from the repo file or **pops it entirely** (see
the five-step block above). A resolved config therefore carries a `schema` only
when the repo file carried one.

This is the only key in the file handled outside the merge.

A repo config with no `schema`, or one below `SCHEMA_CURRENT` (1-7), is brought forward by
`/crew:migrate`'s upgrade stage (`crew_upgrade.upgrade_config`, the code `/crew:upgrade` ran
before T-0038 removed it). It rewrites `.crew/config.json` in place, in the same apply that
writes `.crew/crew.json`: the original is copied into the backup first and `--rollback` restores
it byte-identical. A block the upgrade cannot migrate is a conflict, and nothing is written. A
`schema` that is present but not an integer, or is 0 or less, is refused, as is one above 8.

Schema 8 (L-0725) is the move to `guards.profile` and `guards.overrides` and the removal of the keys listed in "Removed keys and migration". A schema-7 repo reads `upgradeNeeded` until `/crew:migrate` runs.

---
## `pm.authority`

**Retired in crew 1.0.** The PM agent that honoured this key was deleted;
`crew_config.py` still reads and ratchets it so a 0.20 config resolves and
`/crew:migrate` can carry it to `crew.json`'s `retired.pm`. Nothing dispatches
on it any more.

| | |
|---|---|
| Type | string enum |
| Values | `report-only` (default), `act`, `autonomous` |
| Layer | global-settable |
| Consumer | `crew_state.normalise_authority` / `authority_rank`; `crew_config.py`; `/crew:migrate` (carries it to `retired.pm`) |

`crew_state.AUTHORITIES` is `["report-only", "act", "autonomous"]` (dumped by
execution). `authority_rank` returns `report-only` 0, `act` 1, `autonomous` 2 —
and **0 for `None` and for any unrecognised string**. A typo in a permissions
field fails closed, to the least permissive tier.

The tiers are a **floor**, not a set: anything `act` may do, `autonomous` may
do.

What each tier grants, quoted verbatim from `_WIDENING_NOTES`
(`crew_config.py`) — this is the string crew itself prints on a widening:

- **`report-only`** — "the PM reports and recommends only. This is the narrowest
  tier and nothing widens into it."
- **`act`** — "the PM will dispatch roles itself and report after. It still asks
  you to choose when a decision is open. Removal, deletion and offboarding still
  stop for an explicit yes."
- **`autonomous`** — "the PM will dispatch roles itself AND stop asking you to
  choose - where it would put a decision to you it takes the option it would
  have recommended and says which. Offboarding a role, deleting a codemap or
  diagram, rewriting .crew/metrics.md, and destroying git history or tracked
  work still stop for an explicit yes."

### The stop-list, at every tier

`crew_state.AUTONOMOUS_STOPS` (dumped by execution) is the machine-readable form
of that last sentence. Five entries, id and description verbatim:

| id | needs an explicit yes |
|---|---|
| `offboard-role` | offboarding a role, or removing one from the roster |
| `delete-map` | deleting a codemap file or a diagram |
| `rewrite-metrics` | rewriting `.crew/metrics.md` |
| `git-destruction` | destroying git history or tracked work - force-push, branch delete, history rewrite, or `rm` of a tracked file |
| `clear-inflight` | clearing another runner's in-flight marker (T-0049) |

Since 1.0.41 the list also binds `/crew:autopilot` (see "autopilot"): `commands/autopilot.md`
names every id, and `test_crew_autopilot.py::test_command_names_every_autonomous_stop`
iterates this tuple against that file, so an id added here without the command
naming it fails the suite.

`_WIDENING_NOTES` is keyed on **every** member of `AUTHORITIES` on purpose, so a
tier added without a note is a `KeyError` at the point of use rather than a
warning that silently describes the wrong thing (`crew_config.py`, a
comment naming that as the failure that produced the table).

---

---

## Which keys are machine-wide, and which are repo-only

A key is settable in either layer and the repo wins, with these exceptions, each of which resolves to the narrower of the two layers instead: `install.policy`, the twelve guards (see "guards"), and `change.requireForProduction`. For the policy and guard keys "narrower" means a smaller capability; for `change.requireForProduction` the narrower value is `true`, so a repo may turn that one on and never off. The five personal `autopilot` keys combine per key by their own rule, in "Personal keys and the per-key ratchet".

`production.databases` and `production.hosts` are deliberately repo-only; "guards" says why. `notify.tokenEnv` is in both templates and honoured from the machine layer only (`crew_notify.GLOBAL_ONLY_KEYS`): it names the variable whose value becomes the credential, so a repo's value is ignored with a notice.

To find the repos to list in `context.autoClear.onlyRepos`, `/crew:migrate`'s `apply-migrate --scan-root <dir>` looks for the ones that opted in under 0.20.x (T-0106).


`crew_state.QA_PROVIDERS` and `DEV_PROVIDERS` are both
`["claude", "codex", "copilot", "kimi"]` (dumped by execution). `qa.provider`
additionally accepts `"auto"`; a `dev.provider` of `"auto"` is **not** valid —
`crew_config.py::validate_providers` checks `qa.provider` against
`QA_PROVIDERS + ["auto"]` and `dev.provider` against `DEV_PROVIDERS` alone.


`pm.maxDispatches` is coerced with `int_or` once, in
`crew_state.py::collect`, because it comes from a hand-edited JSON file and an
unguarded comparison against a string is a `TypeError` that takes out every
session in the repo.

### The session relay is pinned in its agent file, not in config

`agents/session-relay.md` (L-0797) carries messages between sessions on Haiku 5.5. Its model is the
frontmatter line `model: claude-haiku-5-5` (the full id, probed accepted in a scratch HOME on 2026-10-16), which plugin frontmatter fixes at ship
time, so there is **no** `relay.model` key and nothing in `qa.roles` or `dev.roles` for it: it is not
a role, and `/crew:model` reports roles only. To run a relay on another model, pass `model` when
dispatching it. `tests/test_session_relay.py` pins the model, the two tools (no `Read`) and the transport-only
rules.

### The coordinator and lane model pins (L-0799)

The coordinator is **a model pin on an existing role**, not a fifth role: `dev.roles.coordinator`
(`{"provider": "claude", "model": "claude-opus-5-5"}`) in the open `dev.roles` table, default
**unset**, so nothing changes for anyone who sets nothing. No agent file, persona or roster entry
backs it, and `crew_config.py --models` / `/crew:model` list it as a `role-pin` row like any pin.
`crew_wave.py start` prints `coordinator: model <id>` when the pin is a claude pin with a model;
the dispatcher prints it as-is: wave launches no coordinator, so the line reports the pin and
launches nothing. A plugin cannot change the session model, so where the main session itself
coordinates, the pin has no effect unless the owner sets the session model.

`dev.roles.developer` with `provider: claude` and a `model` is now used for wave lanes:
`crew_wave.py start` writes `Agent(subagent_type: general-purpose, isolation: worktree, model: <id>)`. `crew_wave.py start --json` carries the same pin as `launches[].model`, and the `wave` workflow (`/crew:wave`) passes it as the lane agent's `model`.
Only an explicit `dev.roles.<role>.model` counts: a `dev.claude.model` block default is not a pin and
changes nothing. Unset, a non-claude provider, or a model that is not a claude id or alias (`gpt-6`
under `provider: claude`) leaves the launch line byte-identical to 1.2.37. A role pin with a claude
model but no `provider`, under a `dev.provider` that is not claude, prints a `warning:` naming the fix
and pins nothing. The pinned text
must look like a model id or alias (letters, digits, `.`, `_`, `-`, an optional `[1m]` suffix); anything
else prints a `warning:` and pins nothing. The value is passed through verbatim, so an alias
(`sonnet`, `opus`) works wherever an explicit id is refused. Probed 2026-10-16 in a scratch HOME:
`claude -p --model` accepts `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` and `sonnet`,
and refuses `no-such-model-xyz`. Whether the in-session `Agent` tool accepts explicit ids was not probed.

### The provider keys are also where `roles` pins live

`qa.roles` and `dev.roles` are open tables, so
`dev.roles.<role>.provider` and `.model` are settable in either layer without
crew enumerating role names. A role pin **wins over** the provider block for
that role — `/crew:review` resolves `review`'s model that way
(`skills/crew-review/SKILL.md`, the `qm()` helper).

**The agent pins (L-0777).** `dev.roles.explorer`, `dev.roles.researcher` and
`dev.roles.security` route those agents: a pin that resolves to `kimi` makes
the agent hand its task to `hooks/scripts/crew_kimi_agent.py`, which runs the
Kimi Code CLI read-only and falls back to Claude when Kimi cannot run. Nothing
ships pinned, so every agent stays on Claude until you write one
(`/crew:model dev.roles.explorer '{"provider": "kimi", "model": "k3"}'`).
`explorer` and `researcher` joined `crew_state.DEV_ROLE_KINDS` so `/crew:model`
lists them. `security` is in `crew_state.REVIEWING_DEV_ROLES`: unlike every
other `dev` role it is judged against the author families, so a pin in the
family that wrote the change is BARRED, as a `qa` pin is. See the crew README,
"Agents on Kimi".

### `qa.fallback` / `dev.fallback` run on their own family's provider (L-0712)

When a pinned model is gone, `crew_state.resolve_role` falls back to the
`fallback` model **on the provider that serves its family**
(`crew_state.provider_for_model`: `gpt-*` on codex, `kimi-*` and `k3` on kimi,
`claude-*` on claude; Copilot hosts several families, so no fallback is sent
there). Until L-0712 every fallback was dispatched to `claude`, so a
`gpt-6.1-sol` fallback became a Claude read. A fallback in the author's family is
skipped for the next provider in `qa.order` (`dev.order`, else the shipped QA
order, for the dev kind) that is not the author's family and answers its probe,
on that provider's own model and effort. When none does, the result is
`incomplete`: the round is recorded INCOMPLETE and refunded rather than spent on
a same-family read. Only an explicit operator choice (`same_family_ok`) runs the
fallback same-family, and the result says `sameFamily`. A fallback model whose
family no provider serves (`gemini-*`) walks the order directly. `/crew:status`
prints the repo-wide share of same-family rounds. `/crew:review` carries this
out (crew 1.2.6): an INCOMPLETE with no reviewer is
`review_ledger.py --no-reviewer --reason <why>` (an `unreviewed` entry, no
round or budget spent), and `review_run.py --authors "$AUTHORS"` refuses an
author-family reviewer unless `--same-family "<reason>"` labels the round.


---

## Why some keys are repo-only

Repo-only keys are refused in the global file by `plan_global_write`, and pruned out of it by `filter_global` if some other tool wrote one. Each is a fact about one repository or one checkout. `verify.stopBudgetSeconds` is read by the verify gate and declared by neither default; its default is `60`.


`context.reserveTokens: null` means *off*, and survives as `null` — this is the
case `null_shadows` is deliberately narrow to protect (see "Null shadowing").

`platform.*` is written by `crew_platform.py`, which stamps the detected
machine facts into the repo config. That is why it is repo-only despite
describing a machine: the value records what *this checkout* resolved, and a
global override would make every repo on the box report the first one's answer.

`tickets.baseBranch` (T-0061) names the branch ticket branches are cut from,
for a repository that integrates on `development` rather than `main`. `null`
keeps the old default: `origin/HEAD`'s target, then `origin/main`, then `main`.
A value is tried as given when it contains `/`, then as `origin/<value>`, then
as `<value>`, and the first that names a commit is the base branch. When none
does, or `.crew/config.json` does not parse, the scope base is **could not
tell**: `scope_base.py --record` writes nothing and exits 1, `--base` and
`--changed` print nothing and exit 3, and the completion audit fails. It never
falls back to `origin/HEAD`. The key is read from the resolved repo config
(`crew_common.repo_config_file`), like `scope.mode`: a worktree with no
`.crew/` of its own reads the main checkout's.

---

## context.autoClear - machine-wide by design

`context.autoClear` is the only block shared between the two layers: its leaves
are settable in `~/.claude/crew/config.json`, and every other key under
`context` is repo-only. The argument is that how a terminal is driven to
accept a keystroke is a fact about the machine, in the same sense provider
availability is — `crew_platform.py::concerns` validates `method` against what
*this* platform can actually deliver and reports one it cannot honour.

**Crew neither causes nor tunes Claude Code's own auto-compact.** That
built-in behaviour fires whenever Claude Code itself decides to; nothing in
this block, in `context-watch`, or in auto-clear influences when or whether
it happens. This block only decides what happens *after* a handoff is
written and verified — whether, and how, to act on it.

### `context.warnAt` defaults to 0.4, and one key drives wrap-up and clear (crew 1.2.40)

`context.warnAt` is the single threshold for the handoff warning, the wrap-up
and `context.autoClear`: the latter two change what happens when the hook
fires, not when. The default is `0.4` (`0.5` from
0.19.52 to 1.2.39, `0.8` before), in `crew_state.py`, the config template, both
`context-watch` flavours and `low_context_note`. Only the unset default moved.
A `warnAt` set in `~/.claude/crew/config.json` or `.crew/config.json` keeps
its value and nothing rewrites it. A repo created while the default was `0.5`
holds a literal `"warnAt": 0.5` copied from the template, so it keeps firing at
50% until that line is edited or deleted.

### `context.autoClear` is machine-global by design, and reaches every crew repo

`context.autoClear` lives in `crew_config.py`'s machine-global layer because
*how a terminal is driven to accept a keystroke* is a fact about the machine,
not the repository — the same reasoning `method` gets above. Since it is a
machine-wide switch, the OWNER DECISION (crew 1.0 F4, reversing the file-based
gate this section used to describe) is that it works in *any* crew repo, not
only ones that have run `/crew:init` far enough to have written a
`.crew/config.json` of their own. "Crew repo" is read the same way both
senders now agree: `.crew/` the DIRECTORY exists. `auto-clear.sh`
gates on it directly; `context-watch.sh` gates its OWN
handover to auto-clear the same way, while their OWN context-window warnings
and wrap-up prompts keep requiring a real `.crew/config.json` underneath —
sizing a token budget against nothing is not a warning worth printing, so that
half of each hook stays exactly as strict as before.

**The never-create rule holds regardless.** A repo with no `.crew/` at all —
a fresh checkout, since the directory itself is git-ignored in this very repo
— gets nothing: no `.crew/`, no `.crew/.autoclear.log`, not even a silent
read that could be observed. Nothing here creates `.crew/`; the directory
gate only ever widens what happens once something else (`/crew:init`, a
worktree copy, or any other hook) has already made it exist.

**Required order in both senders, unchanged from before F4:** is `.crew/` a
directory at all → is auto-clear armed (the machine's `enabled`, then
`onlyRepos`/`onlySessions`) → only then may anything be written, even a log
line. `.crew/config.json`'s presence or absence plays no part in that order
any more. The ordering matters for a second reason beyond "is this a crew
repo": the enabled/narrowing check must ALSO run before anything is written,
or a disabled or narrowed-out repo stops being silent — it starts leaving a
`.crew/.autoclear.log` behind (even one line saying "refusing") the moment it
falls through to a refusal path instead of the silent `off` one. `auto-clear.sh`
special-cases `off` (the enabled check,
then the `onlyRepos`/`onlySessions` narrowing) as an unconditional, silent
`exit 0` reached *before* the log file or its logging function is armed —
never a `note()`/`Write-CrewAutoClearNote` call. See `plugin/crew/tests/test_auto_clear_order.py`
for the regression tests pinning this order in both flavours.

**What this replaces.** The previous account here described a "deliberate
trade-off": the machine's `enabled: true` armed nothing in a repository until
it had run `/crew:init` far enough to gain a `.crew/config.json`, and a repo
that wanted the machine switch to reach it before that point had no option
but to write one anyway — a minimal, otherwise-pointless per-repo
`context.autoClear` stanza duplicated into a config that existed only to
satisfy the file gate (`solomon/aws-managed-services` carried exactly this
workaround). That duplication is no longer needed: the directory alone is
enough, and a repo's own `context.autoClear` config is back to doing only
what it always meant to do — narrow or switch OFF what the machine turned
on, never manufacture a "not initialised" refusal the machine did not ask
for.

### `method`

| Value | What it does | Where it can run |
|---|---|---|
| `"auto"` *(default)* | Picks per platform, below. | everywhere |
| `"tmux"` | Types into the `$TMUX_PANE` whose pid is this session's own process or an ancestor of it (T-0016, below). Exact — no focus involved. | Linux, macOS, WSL, Git Bash on Windows |
| `"xdotool"` | Types into the one X11 window owned by an ancestor of this session's own process and hosting no other terminal. | Linux with `xdotool` installed |
| `"wtype"` | Refused outright: it types into whatever has focus, which Wayland offers no way to check, and the opt-in that once allowed it is gone. | Wayland (never granted) |
| `"notify"` | Types nothing. Prints a `systemMessage` saying the handoff is written and verified and it is safe to run `/clear` yourself. Never claims anything was cleared or compacted, because nothing was. | everywhere |
| `"sendkeys"` | **Removed in crew 1.2.61 (L-0727 slice 3).** The Windows-only keystroke sender lived in `auto-clear.ps1`, which is deleted; `resolve_method` and `crew_autoclear_setup.py` refuse it with "sendkeys was removed in crew 1.2.61 (L-0727); use notify or tmux", and `crew_platform` lists it for no OS. `auto` never chose it. | nowhere |
| `"none"` | Refused outright, deliberately. | everywhere |

**`auto`'s per-platform pick, an OWNER DECISION:** a tmux pane if `$TMUX` names
one and `tmux` is on PATH; else an X11 window if `$DISPLAY` is set and
`xdotool` is on PATH; else **`notify`** on native Windows (`$OS` is
`Windows_NT`, present in every process tree there — cmd, PowerShell, Git
Bash alike — and absent inside WSL, which has its own init); else refused
(`"no usable method"`). Typing into a window this hook found itself is a risk
`auto` does not get to accept on your behalf, which is why native Windows
gets `notify`, and `sendkeys` was removed.

### Which terminal: this session's own process (T-0016)

A `claude -p` child started from a session's Bash tool inherits `$TMUX`, and
its parent's pane and window are ancestors of its hook, so a target found
from the hook alone typed `/clear` into the **parent**. Both flavours
(`crew_autocycle.session_owner`/`classify`/`prove_target`, and the same
rules the deleted `auto-clear.ps1` carried natively) now bind first, after the handoff checks
and the method, before the sent-marker claim:

1. **Owner.** The nearest ancestor of the hook named by a Claude Code session
   record, `${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json`, whose
   `sessionId` is the payload's and whose `procStart` is that process's start
   time (`/proc/<pid>/stat` field 22) wherever one can be read. No
   environment variable counts: `CLAUDE_PID` and `CLAUDE_CODE_ENTRYPOINT` are
   copied into every child.
2. **Class.** `terminal` needs kind `interactive`, an entrypoint on the
   measured allowlist (`cli`), and a controlling terminal (`tty_nr` non-zero;
   native Windows has none to read, so there it rests on kind and entrypoint).
   `headless` needs positive evidence: an `sdk*` entrypoint (`claude -p` is
   `sdk-cli`, with or without a pty around it), a kind other than
   `interactive`, or `tty_nr` 0. Anything else — no record, another session's
   record, an unreadable one, a start-time mismatch, an entrypoint nobody
   measured (e.g. `remote_mobile`) — is `unknown`, and unknown is never called
   headless.
3. **What each class gets.** `headless`, whatever the method (`notify`
   included): method `notify-headless` — nothing typed, one `systemMessage` naming the handoff
   and its `resume:` line and saying the process that started this session
   must start a new one, claimed like `notify` (once per session) and logged
   in full (a `-p` parent may never show the message). `unknown`: `notify`
   is unchanged, `auto` falls back to plain `notify` (logged), an explicit
   typing method refuses with the reason. `terminal`: `notify` unchanged;
   tmux and xdotool are proven from the owner.
4. **Target, from the owner.** tmux: the pane's pid is the owner or an
   ancestor of it, and every process from the owner up to the pane is on the
   owner's tty or on none — a pane reached through a process on another tty
   is someone else's terminal (an interactive child on its own pty under its
   parent's pane, whose parent's record is in another config dir and whose
   name is not `claude`, is caught only by this), and a tty that cannot be
   read refuses. xdotool: the window is owned by a strict ancestor
   (never the claude process itself). The walk refuses when it passes
   through another Claude Code process or another live session record (a
   child under its parent's pane or window), or when the chain could not be
   read to the end (a parent that cannot be read, a loop, more than 16
   processes). xdotool also refuses a window whose owner hosts another
   terminal — any descendant outside the owner's own subtree on another
   `tty_nr`, another live session, or a process scan that fails — because
   one terminal server owns one X window for many tabs and a sibling can be
   invisible to a record scan (`tmux attach`, ssh, another config dir, a
   plain shell). A window with no owning
   process (pid ≤ 1) refuses whenever another live session record exists. A
   record whose process is gone or whose start time names a reused pid is
   not live (Claude Code leaves records behind when a session is killed); a
   LIVE process whose record cannot be read means no other session can be
   ruled out, and every check that needs that refuses. "Another Claude Code
   process" is a live record, a process named `claude`, or one named like a
   version (`2.1.289`: a native install runs from
   `~/.local/share/claude/versions/<x.y.z>`); the names are a heuristic that
   only makes the walk fail closed sooner — `node` and other names are not
   recognised, which is why the records and the tty rule carry the proof.

The chain end to end: T-0017 wrap-up → T-0016 target proof → clear → T-0006
`decide` → T-0013 typing (which takes the same binding).

**Test stubs are inert in production.** `CREW_AUTOCLEAR_PROC_STUB` (the
whole process table) and `CREW_AUTOCLEAR_WINDOW_STUB` (the window list) are
read only while `CREW_AUTOCLEAR_INHIBIT` is set, in both flavours: a repo's
`.claude/settings.json` env reaches every hook, and with the inhibit set no
keystroke is ever sent. `CREW_AUTOCLEAR_INHIBIT=spawn` (`auto-clear.sh`
only, for the suite's spawn tests) still builds and spawns the detached
sender, which stops after its sleep, before any keystroke.

**Stated limits.** Measured on Linux only (Claude Code 2.1.289,
`plugin/crew/docs/session-record-spike.md`). On native Windows `entrypoint`
is unmeasured and there is no tty: a value outside the allowlist is unknown,
and a record is bound by pid and session id with `procStart` unchecked; with
no tty, a parent session above a console window is told apart only by its
record and its process name, so one in another config dir under an
unrecognised name is not seen there (Windows Terminal's one-tab rule and the
title-fallback refusals still apply). A parent that has exited ends the walk
on Windows; one that exists but cannot be read (`Get-Process` denied, or no
parent id) refuses. On
macOS (no `/proc`), parent and tty come from `ps -o ppid=,tty=,comm=` and
`procStart` is unchecked, so a pid reused within a record's life is not
caught there.

**A shared tty proves nothing.** The tty rule tells two sessions apart only
when they sit on different ttys. A process on the session's own tty (its
shell, or a parent session started in the same terminal) counts as the
session's own, and xdotool's shared-window scan reads it the same way. A
parent session on the same tty is caught only by its live record or its
process name (`claude`, or a version number); one in another config dir
under an unrecognised name (`node`) is not seen. Two sessions on one tty
share one terminal, so a keystroke reaches whichever of them is reading it.

### `wrapUp` — auto wrap-up before the clear (T-0017)

Off by default. Armed only when the machine file says exactly
`"context.autoClear": {"wrapUp": true}`, `enabled` is armed and the session is
inside `onlyRepos`/`onlySessions`; a repo `false` vetoes it, a repo `true`
alone arms nothing (`crew_autocycle.wrapup_armed`). Unarmed, every output is
byte-identical to before.

Armed, context-watch's warning **is** the wrap-up procedure and supersedes the
ordinary warning. The procedure: start no new step; the step is
the active ticket's plan step in flight, or the tracked diff with no ticket;
run its `Test:` command and commit only if it passes; if it cannot pass, do not
commit and write `resume: none` with the reason under **Verify first**; run
`/crew:handoff --wrap-up`; end the turn. `/crew:handoff --wrap-up` is the one
wrap-up path — `/crew:autopilot`'s context-watch step runs it too.

Auto-clear then clears only when, beside the existing handoff checks, all four
hold (`crew_autocycle.wrapup_check`, run before the method, the T-0016 binding
and the sent-marker claim):

1. the handoff's `head:` is HEAD (a handoff written before the commit fails);
2. its `branch:` is the checked-out branch;
3. no tracked file is modified (`git status --porcelain --untracked-files=no`;
   untracked files and the handoff file itself do not count);
4. its `resume:` line parses under T-0006's grammar, or is `resume: none`.

Anything that cannot be told — git failing, T-0006's `crew_resume` missing, an
unreadable handoff — refuses. `auto-clear.sh --force`
skips this check along with the handoff checks; they are for testing by hand
only — `hooks.json` and context-watch never pass them, and no config key can. A refusal is logged, shown to you as a
`systemMessage` (`crew wrap-up: not clearing - <reason>`), and fed back to the
model **once**, at the session's next ordinary Stop (claimed with
`.crew/.wrapup-escalated-<session>`, reset at SessionStart and on re-arm);
a `stop_hook_active` Stop never blocks.

**Stated limits.** No hook commits, stages or reverts anything: the model
commits and crew checks the result. Crew checks that a commit happened, not
that the step's test passed — verify-gate stands down on the forced
continuation the commit is made on. On native Windows the check needs a
python: `crew-hook.ps1` (`Resolve-CrewPython`) refuses an armed repo's
`Stop` that names it (B10), so neither the wrap-up message nor the clear runs
without one.

### The delay and the dry run

**`--dry-run`'s delay line never states a number for `notify`.** `notify`
types nothing, so `delaySeconds` buys it nothing; `auto-clear.sh`
prints `delay: n/a (notify sends no keystroke)` there instead
of echoing the configured value (or a hardcoded `0`, which the deleted
`auto-clear.ps1` did until this was fixed) — either would read as a real wait that
`delaySeconds` controls, which for `notify` it never does. A keystroke
method (`tmux`, `xdotool`) still echoes the configured delay
verbatim.

---

## `resume.auto` - auto-resume after `/clear`, armed by the machine only

T-0006. When it is armed, a SessionStart after `/clear` or a manual
`/compact` reads the handoff's `resume:` line and works out whether that
command may be resumed (`crew_resume.py::decide`). **Nothing starts on its
own yet**: the 2026-09-25 spike (Claude Code 2.1.282) proved an interactive
session drops SessionStart `initialUserMessage`, so the context hook names
the exact command and the reason it did not start, and the human presses
Enter or types it. T-0013 is the typing fallback, which is no longer a setting: the sender waits a fixed 2 seconds and probes for up to 15 seconds.

| Where | Value | Effect |
|---|---|---|
| `~/.claude/crew/config.json` | `"resume": {"auto": true}` (the boolean) | arms it — the ONLY place it can be switched on |
| `~/.claude/crew/config.json` | absent, `null`, `false`, `"true"` (a string), anything else | off |
| `.crew/crew.json` **or** `.crew/config.json` | `false` | vetoes a machine `true`, from either file |
| `.crew/crew.json` or `.crew/config.json` | `true` | **nothing** — a repo can veto, never grant |

A cloned repo must not be able to start unattended work on someone else's
machine, so `crew_resume.py::settings` reads the arming value from the
machine file alone and the repo files only for a veto — the rule
`context.autoClear.enabled` follows (`crew_autocycle.py::settings`).
`resolve_config`'s repo-over-global precedence is deliberately not used.
Both repo files are read because the hooks' config split is real: the guards
read `.crew/config.json` and `/crew:migrate` writes `.crew/crew.json`. A
malformed machine file is off; a malformed repo file vetoes nothing.

**`resume.auto` is a new key on purpose.** The older context-level auto-resume
switch defaulted `true` and is still `true` in old configs; reusing it would
have armed every one of them. It is no longer a setting, and nothing but
`resume.auto` arms resume.

When armed, a `startup` or `resume` source is `off` and adds nothing to the
injected context. On `clear` and `compact`, `decide` returns `wait` — with
the reason in the injected context — for: a `compact` whose PreCompact was not a typed `/compact` (both `handoff-write`
flavours record the trigger per session, in a repo with either
`.crew/config.json` or `.crew/crew.json`, and remove the session's previous
record first, without needing python, so a compact whose own record never
lands is not manual; absent, unreadable, older than 600 s, or not replaceable is not manual,
and records and orphaned `.tmp` files older than a day are pruned); no handoff, or one archived
as stale, or one judged stale that could not be archived; the handoff is the
automatic PreCompact skeleton (its Changed files list is bare `git` output, so
a file named `resume: ...` would otherwise be read as the line); no `resume:`
line, `resume: none`, or a line the grammar refuses; a `branch:` or `head:`
that does not match the checkout (the ticket form only: a `--goal` line is
judged by its goal file instead, L-0658 -- missing, unreadable, not started,
`done` or `stopped` waits, and only `running` may run); a missing `.work/tickets/<id>/` or
`.work/autopilot/<slug>.json`; a command not installed in the plugin (a
`--goal` line is written only while that goal's `run.state` is `running`,
T-0056: `crew_autopilot.py handoff-resume` decides every writer's line, and its
`resume: none` with `kind=unknown` means it could not tell which goal runs); a
`handoff-author.json` that could not be read; no record of which session wrote
this handoff; a later handoff write could not replace or remove `handoff-author.json` (`handoff-author.json.stuck`), or the file and its directory are both read-only so it can be neither replaced nor removed; the handoff changed since its author session wrote it; the
handoff was written by another session; this session's process could not be
identified; a `<git-common-dir>/crew/resume-state.json` that cannot be read,
is not the shape `record_run` writes, or whose directory cannot be searched
(an unknown, never "nothing resumed"; fix the permissions or move it aside to
reset); a handoff already passed to `record_run`; a progress fingerprint that
cannot be computed (an unreadable `.work/INDEX.md`, one whose directory
cannot be searched, or an unlistable ticket directory counts as "cannot be
computed", never as progress); and the same command a second time with no
progress since. A `decide` that raises is `wait` with reason `internal
error`, and the handoff is still injected.

**Which session wrote the note (T-0042).** On an armed machine, a
PostToolUse Write, Edit or MultiEdit of the configured handoff makes the
context hook record `{sha256, session_id, process, at}` for this worktree in
`<git-common-dir>/crew/handoff-author.json` (temp file then `os.replace`,
under a lock).
An unarmed machine writes no such file. `decide` then waits unless the note's
sha matches the record and: after `compact`, the payload's `session_id` equals
the recorded one (it is stable across `/compact`); after `clear`, the Claude
Code process does (`session_id` changes across `/clear`). The process is the
nearest ancestor whose `/proc/<pid>/comm` is exactly `claude`, identified by
pid and start time (T-0042 spike, Claude Code 2.1.283). With no `/proc` —
native Windows, macOS — the process is unknown and every `clear` waits with
"this session's process could not be identified"; `compact` is unaffected.
A note written without Write/Edit/MultiEdit (by Bash, by hand, or before the
machine was armed) has no record and waits. A recorder that cannot read the
note, or whose write fails, leaves no entry for the worktree, never the
previous one.

**The stuck marker.** When a PreCompact can neither remove nor blank this
session's old record (python's `write_precompact_record`, or either shell
flavour's keyed removal), it leaves `precompact-<key>.stuck` beside it, and a
`compact` for that session is not manual while the marker exists or cannot be
stat'ed. The next record that lands clears it; one older than a day is pruned
with the records. `.stuck` is not `.json`, so the shells' `precompact-*.json`
sweeps never remove it. The `os.access` check stays as a second refusal.

**Accepted risks.** A full disk or quota can let an old record survive with no
marker: if the record cannot be replaced and the marker cannot be created
while the directory is still writable, an old `manual` record lives for up to
600 s. The same holds when the PreCompact payload has no readable session id
(the `precompact-*.json` sweep can fail with no key to mark). Two sessions
writing the handoff in the same instant can attribute it to the wrong one;
the record hashes the bytes it reads under a lock, which narrows the window
but does not close it. And when `crew_resume.py` can neither unlink nor blank
a stale `handoff-author.json` nor write its `.stuck` marker while `os.access`
still reports it writable (EIO, ENOSPC, an immutable attribute, a Windows file
held open), the stale author record is trusted.

**Unchanged, and reported to the owner:** a malformed repo file still vetoes
nothing. It is the same class as round 4's FIX (an unreadable veto reads as no
veto), but T-0006's approved plan chose it, so T-0042 reports it rather than
changing it; TODO.md tracks the decision. The `crew_resume.py decide` CLI applies
`crew_state.handoff_staleness` itself, read-only, and waits on a stale note.
`record_run` asks the consumed-once and loop guards again under its lock and
refuses (`ok: false`) a handoff already recorded, the same command with no
progress, a run with no fingerprint, or a state file it cannot read, which it
never overwrites: of two senders holding the same `run`, only the first may type.
If the opt-in cannot even be confirmed (the module or the machine file cannot
be read), the answer is `off`, so an unarmed machine sees exactly the
pre-T-0006 output.

---

## `install.policy`

What crew may do when a skill it routes to is **not installed**. Added by schema
5, which is the only thing that schema cut.

| Value | What crew does |
|---|---|
| `manual` *(default)* | Names the missing skill and the command. Runs nothing. |
| `ask` | Offers to install, and runs the command only after an explicit yes. |
| `auto` | Installs without asking. |

Read it with `crew_config.py --install-plan <name>`, which prints the action,
the command, and both layers' values.

### It resolves to the narrower layer, not the repo's

This was the one key that does not follow the precedence rule in "The two layers"; since schema 6
it is one of a family (the guards, see "guards"), and the rule now lives in one table,
`crew_state.RATCHETED_KEYS`, rather than in a bespoke pair of functions per key.
The reason is the threat model rather than taste. **crew reads config out of cloned
repositories.** A repo file travels inside somebody else's clone; the global
file is this machine's owner saying how much they trust crew here. Under
precedence, a repo shipping `install.policy: auto` would override an owner who
chose `manual`, and crew would start running commands because of a file the user
never wrote.

So the effective value is the **lower-ranked of the two layers**
(`crew_state.effective_ratcheted`, which `effective_install_policy` is now a
thin wrapper on). Neither layer can widen what the other allows: a repo may ask
for *less* than the machine permits and is obeyed, and may ask for more and is
refused.

Absent counts as `manual` on either side, which has a consequence worth stating
plainly because it surprises people: **`auto` requires both layers to say
`auto`.** Setting it in a repo alone does nothing. When a layer is holding the
value down, `--install-plan` says which one — a value that quietly does nothing
is worse than one refused out loud, which is the same rule
`default_global_config` applies to the keys it ignores.

### `auto` can only ever run a command from crew's own source

`auto` is defensible exactly as long as no string a repo author controls can
become a command. Two properties enforce that, and both are asserted in
`tests/test_install_policy.py`:

- **The command is looked up, never built.** `crew_state.INSTALLABLE` maps a
  plugin name to a literal argv tuple. `install_plan` consults that table
  **before** it consults the policy, so a name crew does not ship gets `report`
  and a null command *at every policy including `auto`*. There is no code path
  from a config value to a command string.
- **Commands are argv tuples, not strings.** Nothing is handed to a shell, so
  quoting cannot be escaped out of.

Adding an installable plugin is therefore a change to crew's source that goes
through review — which is precisely the property a runtime lookup would not
have.

### The migration is behaviour-neutral, and had to be

Bumping `SCHEMA_CURRENT` makes **every crew repo on every machine** report
`upgradeNeeded`, so this migration is mandatory. It lands the key as `manual`,
which is what crew already did at schema 4: nothing. Nobody's machine starts
installing anything because they upgraded.

### Why schema 5 carries one key

The obvious economy is to bundle: a schema bump prompts every repo on every
machine and costs the same for one key or six. The user ruled against it on
2026-09-12: a key shipped ahead of its consumer once cost a **mandatory
migration with a one-shot value rewrite** to undo, and keys with no consumer
were later removed outright (see "Removed keys and migration"). A key added
ahead of a need has cost more here than a second bump would cost to pay. If a real key
turns up later it gets its own bump.

Schema 6 carries six, and that is the rule being honoured rather than broken:
every one of them has a consumer landing in the same change (see "guards"). The rule was
never "one key per bump"; it was "no key without a consumer".


---

## guards - the configurable guardrails

Twelve guards, one block, one ratchet, **three vocabularies**. What crew's command guard does about each dangerous action it recognises, how much of production crew may reach, and whether a dispatched role may write outside the scope its own agent file declares. The third vocabulary, `roleWrites`, is different enough from the others to earn its own section, "guards.overrides.roleWrites".

The twelve are `terraformApply`, `forcePush`, `adminMerge`, `mergeGate`, `cloudDestructive`, `sqlDestructive`, `deployWorkflow`, `prodDatabase`, `prodServer`, `roleWrites`, `cloudGuard` and `envGuard`.

### Profile plus overrides

A layer states its guards with two keys:

- `guards.profile`: `off`, `standard` or `strict`. One word expands to a value for every guard.
- `guards.overrides.<guard>`: one guard's own tier, validated against that guard's vocabulary, for the cases the profile does not fit.

The profile table is `crew_guards.PROFILE_MAP`:

| guard | `off` (the default) | `standard` | `strict` |
|---|---|---|---|
| `cloudGuard` | off | block | block |
| `roleWrites` | off | report | block |
| `terraformApply`, `forcePush`, `mergeGate`, `cloudDestructive`, `sqlDestructive`, `deployWorkflow` | block | block | block |
| `adminMerge` | block | ask | block |
| `prodDatabase`, `prodServer` | none | none | none |
| `envGuard` | off | off | block |

`off` is exactly the old `GUARD_DEFAULTS`, so a repo that sets nothing resolves as it always did. It switches the three optional hooks (`cloudGuard`, `roleWrites`, `envGuard`) off and leaves every other guard at its narrowest tier. `standard` is the posture the owner's repo layer held before the change. `strict` turns all three hooks fully on and refuses `adminMerge`. The production levels are `none` in every profile on purpose: how much of production a machine may reach is never something a one-word profile grants.

### How one layer expands

`crew_guards.layer_guard_state` computes a layer's value for a guard in two steps. First the base, in this order:

1. A `guards.profile` that is present but malformed (not one of the three words) gives the **floor** for every guard in that layer, and nothing else in the layer can lift it, an override included.
2. Otherwise the layer's `guards.overrides.<guard>` wins over the profile. A malformed override value, or an `overrides` that is not an object, reads as the floor for that guard.
3. Otherwise the valid profile's value.
4. Otherwise the layer is silent about the guard.

The floor is `block`, or `none` for the two production guards. It is never `off`: a typo narrows, it does not switch a guard off. This is the same rule the old per-guard keys followed, now stated once for the layer.

Second, the legacy alias. A per-guard key `guards.<guard>` still present in a layer, one that has not been through `/crew:migrate`, is read, never ignored. When the base is silent, the legacy value is the layer's value alone, so an unmigrated layer resolves exactly as it did, `ask`, `allow` and `read` included. When both exist, the **narrower** of the two by that guard's own rank wins, and a difference between them is reported as a conflict. The writers (`crew_config.py set` and the config menu) never write a legacy key and refuse one, naming `guards.overrides.<guard>`. `/crew:status` and `crew_config.py --explain` say "unmigrated: run /crew:migrate" while any legacy key is present.

### The ratchet runs after the expansion

The per-guard ratchet then takes the narrower of the two layers' values, exactly as before. Nothing about the ratchet changed: it still reads both layers raw and never goes through `resolve_config`. Nothing about any guard's decision changed either. For every layer that migrates, the per-layer and the combined value of all twelve guards are byte-identical before and after, which is the property `tests/test_guards.py` holds the expansion to.

### Where each guard is read

| Guard | Tiers, widest last | Read by |
|---|---|---|
| `terraformApply`, `forcePush`, `adminMerge`, `cloudDestructive`, `sqlDestructive`, `deployWorkflow` | `block` < `ask` < `allow` | `hooks/scripts/cloud_guard.py`, while `cloudGuard` is on; `allow` on `deployWorkflow` covers nonProd only |
| `mergeGate` | `block` < `ask` < `allow` | `commands/gate.md`, `commands/promote.md` |
| `prodDatabase`, `prodServer` | `none` < `read` < `full` | `hooks/scripts/cloud_guard.py`, while `cloudGuard` is on |
| `roleWrites` | `block` < `report` < `off` | `hooks/scripts/role-write-guard.sh` and `.ps1` |
| `cloudGuard` | `block` < `report` < `off` | `hooks/scripts/cloud-guard.sh`, `.ps1` -> `cloud_guard.py` |
| `envGuard` | `block` < `report` < `off` | `hooks/scripts/env-guard.sh`, `.ps1` -> `env_guard.py` |

The lists that say what is production or which environments may run unattended stay their own keys: `production.databases` and `production.hosts`, `cloud.awsProfiles`, `cloud.awsRegions`, `cloud.azureSubscriptions`, `environments.nonProd`, `environments.prodUnattended` and `environments.workflows`. `production.*`, the `cloud.*` pins, `environments.nonProd` and `environments.workflows` are repo-only; `environments.prodUnattended` is `true` only when both layers say `true`.

Read one guard with `crew_config.py --guard <name> [--json]`, which prints the decision, both layers' values and which one is holding it down. The two shell flavours call exactly that CLI; see "One resolver, two flavours" below.


### `envGuard` — the environment-dump guard's switch (L-0772)

`off` *(default)* judges nothing; `report` writes the refusal it would make to
`.crew/guard.log` (rule, mode, decision and a fixed label, never the command or
a value) and refuses nothing; `block` refuses. A malformed value is `block`;
the narrower layer wins. There are no per-rule keys behind it, and the
credential-name pattern is fixed in `env_guard.py`. What it refuses and why:
README "Environment guard".

### What each value does

| Value | What crew does |
|---|---|
| `block` *(default)* | Refuses, exactly as the guard did before these keys existed. |
| `ask` | Refuses, prints the **exact** command, and names the one marker file that approves **that** command. Creating it and re-running lets it through for 15 minutes; the next command asks again, and so does the same command tomorrow. |
| `allow` | Runs it, prints what it let through, and appends a row to `.crew/guard.log`. |

### Production access — `prodDatabase`, `prodServer`, and `production.*`

Two guards with their own vocabulary, in the same block and on the same
ratchet.

| Value | What crew does |
|---|---|
| `none` *(default)* | Refuses every command aimed at a declared production target. |
| `read` | Permits what the guard can **positively classify** as read-only. Everything else — including everything it cannot classify — is refused. Since L-0772 an environment dump is never read-only: `printenv` left `PROD_READ_COMMANDS`, bare `env` classifies as a write, and any remote command `env_guard.findings` flags (`cat /proc/1/environ`, `ps eww`, `echo $SOME_TOKEN`) is a write (**BREAKING**, by narrowing). |
| `full` | Permits anything, and appends a row to `.crew/guard.log` for each one. |

**`ask` is not a value here, and its absence is a decision.** The other four
guards answer "may crew do this one dangerous thing", where a per-command yes
means something. These answer "how much of production may crew reach", which is
a standing posture. An `ask` would mean a marker file per distinct SQL string —
a prompt nobody reads by the tenth query, which is consent theatre rather than
consent.

**The level is global; what is production is not.** `guards.overrides.prodDatabase` and
`guards.overrides.prodServer` are settable in both layers and ratchet like the rest:
"this machine may read production" is the same sentence in every checkout.
`production.databases` and `production.hosts` are **repo-only** — absent from
`default_global_config()`, pruned out of a global file by `filter_global` and
**reported** there. `prod-db-*` names one cluster in one repo and something else
in the next, so a machine-global list would carry one repo's hostnames into
every other repo on the machine: refusing innocent commands in one place and,
worse, passing dangerous ones in another because the list describes the wrong
estate.

**With no patterns declared the guard matches nothing.** That is what lets the
strictest possible level ship as the default without changing anybody's
behaviour: an upgraded repo gains two keys whose combined effect is "refuse
access to the empty set". Declaring a pattern is the act that turns them on.
It also means an empty `production` block is not a misconfiguration to warn
about — it is the normal state of a repo that has no production estate.

**Unknown is a write, and that is the whole value of `read`.**
`crew_guards.py::classify_access` answers `read` only when it can prove it,
from named lists rather than from a "looks harmless" heuristic:

- **SQL** (`psql`, `mysql`, `mariadb`, `sqlcmd`, `mongosh`, `redis-cli`,
  `sqlite3`, `cqlsh`) — every statement in the payload must open with
  `SELECT`, `SHOW`, `EXPLAIN`, `DESCRIBE`/`DESC` or `ANALYZE`, and none may
  contain `INTO`. `WITH` is deliberately absent: `WITH x AS (...) DELETE FROM
  ...` is a write that opens with a read-looking keyword. A client invoked with
  **no** `-c`/`-e`/`--query` payload is an interactive session and therefore
  unclassifiable.
- **Remote shell** (`ssh`, `plink`) — there must BE a remote command, and every
  segment of it, split on `;` `&&` `||` `|` and `&`, must name a read-only
  program: `cat`, `head`, `tail`, `less`, `ls`, `stat`, `grep`, `wc`, `sort`,
  `cut`, `awk`, `sed`, `df`, `du`, `free`, `uptime`, `uname`, `hostname`,
  `whoami`, `id`, `ps`, `top`, `netstat`, `ss`, `journalctl`, `dmesg`, `echo`,
  `which`, `env` — or a PowerShell `Get-*` / `Test-*` / `Measure-*` /
  `Show-*` / `Find-*` / `Select-*` verb. `systemctl`, `docker`, `kubectl` and
  `ip` are read-only only on a named subcommand (`systemctl status`, never
  `systemctl restart`). Any redirect, and `sed -i`, make it a write.
- **AWS** — `aws <service> <verb>` is a read only on a `describe-`, `list-`,
  `get-`, `search-`, `lookup-`, `batch-get-` or `scan-` verb. `aws ssm
  start-session` is not on that list, and an interactive session is exactly the
  case `read` must refuse.

Everything else is a write: an unrecognised tool, a command with an unbalanced
quote, a bare login. A classifier that answered "probably fine" would make
`read` a slower `full`, and the commands it cannot read are precisely the ones
a reader would most want it to refuse.

**The guards are silent when nothing matches.** Unlike the other four, these
two fire on ordinary commands — every `ssh`, every `psql` reaches them. A crew
banner above each one is how a guard becomes noise people switch off, so the
line is printed only when a declared pattern actually matched. The row in
`.crew/guard.log` is written by `crew_config.py --record` either way, so
"nothing is silent" still holds where it means anything.

**The older, unconfigurable `prod` rule stays** — the one that blocks when
`prod` or `production` is the whole argument, or its first or last
hyphen-joined segment, to `psql`/`mysql`/`sqlcmd`/`mongo`/`az`/`aws`/`gcloud`.
It is skipped for a command **only** when a declared `production.*` pattern
already matched it, because then the configured level has answered the same
question with better information. Leaving both in would mean
`guards.overrides.prodDatabase: full` still refused `prod-db-1` — a key that reads as
configurable and is not. With nothing declared, that rule behaves exactly as it
did before schema 6.

**No python is a stand-down; a failed resolver is a refusal.** Without any
python crew can read no config at all, so refusing every `ssh` in every repo
would be the guard people switch off — and the unconfigurable rule above still
blocks on its own regex with no python, so the floor does not move. A python
that IS present and then fails is crew broken on the question of whether this
command targets production, and that blocks, loudly, in both flavours.


**`ask` is a marker, not a prompt, and it had to be.** A `PreToolUse` hook has
no interactive stdin — exit 2 blocks and the retry blocks again — so an `ask`
implemented as a question would have been `block` wearing a different name: a
key with no reachable behaviour. The marker is
`.crew/.approved-guard-<name>-<sha256(command)[:16]>`, the same shape and the
same directory as `promote-gate.sh`'s `.crew/.approved-<env>-<sha>`, which
is the repo's existing answer to this exact problem. Keying it on a digest of
the command is what keeps it one-shot in the sense that matters: a marker
naming only the guard would be a standing grant, and approving one force push
would silently approve every later one.

The marker is **not consumed on read**. Both hook flavours are registered on
Windows, so one command can be judged twice; deleting the marker on the first
read would refuse the second. It is the user's to remove.

**It expires 15 minutes after it is created** (`GUARD_APPROVAL_TTL` in
`crew_guards.py`, read by `crew_config.py::_approval_is_live`). Not consuming
it on read answers "can one command be judged twice"; it does not answer "how
long is a yes good for", and the two are separate properties. This marker is
gitignored (`.crew/*`, and it is not on the `codemap/` / `endpoints.json` /
`verify.json` un-ignore list) and nothing prunes it, so an approval with no
time bound is a
standing per-command `allow` that outlives the session, the task and the
person who gave it — `ask` in the config, `allow` on disk. The design note
asks `ask` to stop for a yes *at that moment*, and a file with no expiry is
not that moment. `promote-gate.sh`'s marker needs no bound because its key is
a commit sha, so the next commit invalidates it; keying on the command text
gives up that natural expiry, so the bound has to be explicit. A marker dated
in the *future* expires the same way: crew cannot date that yes, and an
approval it cannot date is not one. Both shells print the window, taken from
the resolver's `reason` field rather than restated in bash and PowerShell.

**Under `allow` nothing is silent.** The stderr line goes with the session; the
row in `.crew/guard.log` is the durable half, and it is written for every
decision rather than only the permissive ones — a log recording half of what a
guard did is a log you cannot reason from.

**What a `--record` row holds (crew 1.2.35).** Time, guard, policy, decision
and target, then `-` where the command would go — the same value
`env_guard.py` writes in that field. The command line itself is written only
when the operator adds **`--record-command`** (`record_command=True` on
`crew_config.guard_decision`), because a command can carry whatever was typed
inline and `.crew/guard.log` is an ordinary file in the project tree.
`--record-command` without `--record` exits 2 rather than doing nothing. The
target field is still derived from the command (a push's branch, a matched
production host or database), so it is not a redaction of everything the
command contained. With `--record-command`, tabs and newlines in the command
are normalised out before the row is written, the same way
`_common.sh::crew_incident_log` does it, so a crafted command cannot forge a
row. Rows written before 1.2.35 are not rewritten; review and delete an old
`.crew/guard.log` if it may hold commands you would not keep.

### `block` did not preserve everything, and that is stated rather than implied

`guards.overrides.terraformApply` and `guards.overrides.forcePush` at `block` are exactly what the
guard already did. **Two things are new refusals**, and no default can turn a
new refusal into an old one:

- **`guards.overrides.adminMerge`.** No crew guard refused `gh pr merge --admin` before
  schema 6, in either flavour — measured against `origin/main`, both exited 0.
- **`tofu`.** `guards.overrides.terraformApply` now covers OpenTofu as well as Terraform.
  The rule named one of two drop-in-compatible binaries and refused nothing
  when the other was installed.

Both were bypasses rather than features, and the upgrade report says so out
loud. A user told only "the default is block, so nothing changed" will meet a
command that ran yesterday being refused today and go looking for a bug in
their tooling.

**Scope, stated rather than implied:** `adminMerge` matches `gh pr merge`
carrying `--admin` in any argument position. It does **not** match a
hand-rolled `gh api -X PUT .../pulls/N/merge`, which reaches the same endpoint
without the flag. That gap is left open deliberately — a rule wide enough to
catch every `gh api` call to a merge URL is wide enough to block *reading* one,
and a guard that fires on reads is a guard people switch off.

### `forcePush: allow` honours the value everywhere, and names the branch

The design note (`docs/guard-overrides.md`) left open whether `allow` should
still refuse `main`/`master` outright. **Settled: it honours the value
everywhere** — the machine owner chose it, and a guard that keeps one secret
refusal is a guard whose configuration cannot be trusted. The compensation is
that `ask` and `allow` both print the target branch before acting, from
`crew_config.push_target`.

`unknown` is its own answer there and never collapses into a plausible-looking
`main`. A bare `git push --force` takes its branch from the upstream config,
which is not on the command line, so crew genuinely cannot tell — and
substituting a guess is the "unknown wearing the label of a check that
happened" failure this file keeps returning to.

### `environments.*` — which terraform targets may run unattended (crew 1.0.42)

Read by the cloud guard alone, and only while `guards.overrides.cloudGuard` is armed. It
lets `terraform`/`tofu apply` of a **non-destroying saved plan**, and
`workspace new` / `workspace select -or-create`, run with nobody attending
when the target is non-production — and keeps a destroy from ever doing so.

```json
{ "environments": { "nonProd": ["dev", "qa", "staging", "*-staging"],
                    "prodUnattended": false } }
```

**Three environment values, never two.** `nonProd` is a name matching a
`nonProd` glob (fnmatch, case-insensitive). `prod` is a name matching none.
`unknown` is everything crew cannot settle: no signal, a signal that is not a
literal (`TF_WORKSPACE=$WS`), signals that classify differently, or an
`environments` block it cannot read. **`unknown` is narrower than `prod`**:
`prodUnattended` allows `prod`, and nothing allows `unknown` unattended.

The names come from, and must all agree after classification:
`TF_WORKSPACE` (inline, `env`, `export`, `$env:`, then the hook's own
environment); else a literal `workspace select|new X` earlier in the same
command; else `<payload cwd>/<-chdir>/<TF_DATA_DIR or .terraform>/environment`
— used only when nothing in the command changes directory or switches
workspace, and a **missing file is unknown, not `default`** (terraform writes
no file for `default`, measured on 1.16.3, so the default workspace is always
unknown this way). Plus `-var environment=X` / `TF_VAR_environment`, and a
saved plan's sidecar. `-var-file`, `*.tfvars` and HCL are never read.

A directory change in **any** spelling makes the workspace file unusable:
`cd`/`pushd`/`Set-Location`, `env -C DIR`/`-CDIR`/`--chdir=DIR`, `sudo
-D`/`--chdir`/`-R`, `wsl --cd`/`~`, `pwsh -WorkingDirectory`/`-wd`, `parallel
--wd`, `chroot`/`unshare -w`/`nsenter -w`, a sourced file or `.ps1`, and .NET's
`CurrentDirectory`. An environment change crew cannot read makes
`TF_WORKSPACE` itself unknown: `source`/`.` of a file, `export $(...)`, `eval`
or `iex` of text built at run time (or fed from the pipeline), `set -a`,
`read`, any PowerShell `env:` drive write or `SetEnvironmentVariable`, and an
`||` chain (the next command runs only if this one failed). A plan, sidecar,
workspace file or `azureProfile.json` that is not a regular file (a FIFO, a
device) is never read: it is unknown, not a hang past the hook's budget.

**A terraform line is judged only when every word on it is a plain
literal.** Before any of the reading below, the raw command text is checked:
if it names `terraform`, `terragrunt` or `tofu` anywhere — each word read with
its quotes and escapes taken out, `$'...'` decoded, an expansion read as "could
be anything" and a brace list expanded — then every word must match
`^[A-Za-z0-9_./:=@%+,-]+$` and every operator between words must be `;`,
`&&`, `||`, `|`, `&`, `>`, `>>`, `>&`, `&>`, `<` (PowerShell's `*>` too).
Otherwise the line is **could not tell** — a quote, `$`, backquote,
backslash, glob, brace, `<(`, heredoc, here-string, comment or control
character on it, or a PowerShell `@` splat — and it is asked about when someone attends, denied when
nobody does and denied under `block`; a live one-shot marker for that exact
text still lets it through under `ask`/`allow`. Nothing else below is
consulted for it (guard.log policy `could-not-tell`). Unusual quoting on a
terraform line is asked about, not allowed; unattended, it is refused — which
includes `terraform apply "p.tfplan"`. A read-only subcommand (`terraform plan
2>$null`, `terraform workspace select "staging"`) and a line that only
mentions terraform (a commit message quoting it) are not gated for their
quoting (below). Plain lines are read exactly as before.

**Destroy is `yes`, `no` or `unknown`, and unknown counts as yes.** `yes`:
`destroy`, `apply -destroy`, `apply -replace`, `run-all destroy` (and
terragrunt's `destroy-all`, `stack run destroy`, `graph destroy`, and `exec --
terraform destroy`), `workspace delete`, a saved plan whose sidecar lists a delete. `no`: only a saved plan
whose sidecar lists none, `workspace new`, `select -or-create`. Everything
else is `unknown` — an apply with no saved plan, any terragrunt apply
(`apply-all`, `stack run apply` and `graph apply` included), a plan
with no sidecar, a stale one (the plan's sha256 changed), a malformed or
unreadable one, a plan path that is not a literal, a plan over 64 MiB, and a
saved-plan apply that is **not the only command** in the invocation. The plan
is hashed when the hook runs, before the command does, so anything beside the
apply — `terraform plan -out`, `cp`, a nested shell, an output redirect to
anything but `/dev/null`, a command substitution anywhere the shell runs one
(an unquoted heredoc body, `${...}`, `$((...))`) — could replace the plan
after crew read it. A quoted heredoc (`<<'EOF'`) is literal and counts for
nothing; PowerShell's `2>&1` is a redirection, not a command. Run the plan
and summarize steps first, then the apply on its own.

**The sidecar.** The hook cannot run `terraform show` (15 seconds, and it
must not run terraform at all), so a saved plan is summarised first, outside
it:

```bash
terraform plan -out p.tfplan
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tfplan.py" summarize p.tfplan
terraform apply p.tfplan    # a separate command, on its own
```

`summarize` writes `.crew/tfplan/<sha256 of the plan bytes>.json` with the
workspace, the `environment` variable and every address whose actions include
`delete`. The workspace is the one the **plan** is bound to, read out of the
plan file itself (its `backend.workspace`), never `workspace show` — a plan
made under `TF_WORKSPACE=production` in a directory with staging selected is
a production plan. When it cannot be read it is `null`, which the hook reads
as unknown. It writes nothing when `show` fails or times out, and never creates
`.crew/`. A plan with no changes has no `resource_changes` at all and is
refused, so its apply asks.

**The decision**, applied after `guards.overrides.terraformApply` has been ratcheted:

| policy | destroy yes/unknown | nonProd | prod, `prodUnattended` both layers | prod | unknown env |
|---|---|---|---|---|---|
| `block` | deny | deny | deny | deny | deny |
| `ask`, no live marker | ask | **allow**, logged | **allow**, logged + on screen | ask | ask |
| `ask`, live marker | allow (that command) | allow | allow | allow | allow |
| `allow` | **ask — BREAKING in 1.0.42** | allow | allow | allow | allow |

`ask` is denied when nobody is attending, as everywhere in this guard. The
guard.log policy column says why: `env:nonProd:<name>`,
`env:prod-unattended:<name>`, `env:prod:<name>`, `env:unknown`, `destroy:ask`,
and `could-not-tell` for a terraform line that is not all plain literals
(asked under `ask` and `allow` whatever its environment, denied under `block`).
"A terraform line" means one that runs terraform, terragrunt or tofu as a
command -- its command word, or a command inside `bash -c`, `eval`, `pwsh -c`
or a substitution -- not one that mentions the word in a message, a search or
a file name (README, "Cloud guard"); PowerShell lines follow the same rule. A
line that runs terraform in a way the parser does not follow (an alias, a
binary the same line copies or links and runs by its new name, zsh's
`=terraform`, a script runner such as `flock` or `ssh`, PowerShell's
`Set-Alias` or `Start-Process`) is `could-not-tell` even when every word is
plain; a read-only subcommand (`plan`, `show`, `output`, `fmt`, ...) and the
arguments of a program that is not terraform (`cp -r terraform
"$BACKUP_DIR"`) are not gated for their quoting. Options before the
subcommand are skipped as terraform and terragrunt read them (`terragrunt
--working-dir infra destroy` is a destroy).

**What the guard does not catch.** It catches terraform, terragrunt and tofu
written directly: bare or path-qualified, behind the listed wrappers
(`aws-vault exec`, `unbuffer` and `sem` among them; an option a listed
`xargs`, `parallel`, `sem`, `aws-vault` or `unbuffer` does not know makes the
line `could-not-tell`, and so does a `workspace select` that `xargs` or
`parallel` may append `-or-create` to), inside
`bash|sh|zsh -c` and `eval`, with global options before the subcommand, and
PowerShell's `&`, `.`, `terraform.exe`, `Start-Process` and `Invoke-Expression`
(a script that is not a literal string, or a parameter crew does not know,
is `could-not-tell`). On a PowerShell line, **every mention of terraform,
tofu or terragrunt must be accounted for** (any case, a word or a path's last
part, `.exe` and backtick spellings included), or the line is
`could-not-tell`: the command word of a command the guard judged (after an
optional `$x =` and a `&`/`.` with a plain name), a literal script given to
`Invoke-Expression`, or, when nothing on the line can run a value made at run
time (a launcher, an eval, an alias definition, `return`/`throw`/`exit`, or a
command word that is not a plain name), a literal argument of a plainly named
command or a string that is only printed or assigned. So `git commit -m
"terraform destroy"` and `Write-Output ("terraform" + " destroy")` are data,
while `return terraform destroy`, `$t="terraform"; Start-Process $t destroy`
and `[Diagnostics.Process]::Start("terraform","destroy")` are not. A group or
an array among terraform's own arguments is `could-not-tell` too.
`terragrunt exec -- cmd` is unwrapped like any listed wrapper. It does not try to
catch a program renamed by alias, function, symlink or copy, `env -S` escape
strings, BusyBox applets, git `!` aliases, an interpreter (`python -c`, `node
-e`), a script file, a wrapper it does not list (`strace`, `systemd-run`),
a program that runs another (`git bisect run`, `rg --pre`) or a container's
entrypoint. No command-line guard can: unattended work must run interpreters
and scripts. The real boundary is the credentials an unattended run holds:
`crew_unattended.py launch` and `unattendedCloud` below. README, "What the
guard does not catch", lists the commands.

**The always-stops.** A destroy is never applied unattended at any setting —
`terraformApply: allow` and `prodUnattended: true` included. So is an apply of
a plan crew cannot read, which means **`terraform apply -auto-approve` with no
saved plan now asks under `allow`**. Approve one command with the
`.approved-guard-terraformApply-<hash>` marker the refusal names, or summarise
a saved plan. An unknown environment is never unattended either.

**`prodUnattended` ratchets, and only the literal `true` counts.** It is true
only when the repo's `.crew/config.json` **and** the machine-global file both
say `true`; `"true"`, `1` and `null` are false. A cloned repo cannot grant
itself unattended production. `nonProd` is **repo only**, for `production.*`'s
reason — `staging` names one workspace in one checkout — so `filter_global`
prunes and reports a global list. A malformed block (`nonProd: "dev"`, a
non-bool `prodUnattended`) makes every environment unknown and forces an armed
guard to `block` mode.

**At the defaults nothing changes except the destroy rule.** With `nonProd`
empty and `prodUnattended` false, every name is `prod` or `unknown` and `ask`
asks as before. `workspace delete` is a destroy, so it is a finding in every
armed state, the layer engaged or not. `workspace new|select -or-create` are
judged only once the layer is engaged (a `nonProd` glob, or `prodUnattended`
true); then they are **new** findings: denied under `block`, and under `ask`
denied unattended for a prod or unknown target.

**Not a promotion gate.** `prodUnattended` does not stand down
`promote-gate.sh`'s `requireHuman` (`promote-gate.sh`, the `requireHuman`
check), which still applies independently: fully unattended production also
needs that off. Nor does it stand down promote-gate's review evidence
(L-0703): every gated environment needs an accepted review receipt whose
reviewed head has the deployed commit's tree, unless that environment in
`.crew/verify.json` sets `requireReview: false` plus a `reviewReason` - a map
key, not a config key, and committed like the rest of the map. Unattended
production therefore deploys only reviewed trees. `.crew/verify.json` stays promote-gate's list of environments
(and of deploy workflows: promote-gate reads a dispatch with T-0009's reader whether
or not `environments.workflows` is set, T-0062),
read from the session's project directory even when the deploy runs from a
linked worktree (whose HEAD and cleanliness are what the gate then checks);
`crew_config.py --check` warns when a `nonProd` glob covers one it marks
`requireHuman: true`.

A `.crew/verify.json` environment's `github` entry is not config, and no key
here reads it (crew-verification skill, section 4). `crew_ghdeploy.py check`
applies promote-gate's own rule (L-1503): it refuses a map either gate
refuses and prints, under each dispatch, `gated-as:` - every environment
whose `deploy` matches it under either gate, whose requirements all apply. A test
table runs both real gates beside it on the same maps and commands.

### `environments.workflows` and `guards.overrides.deployWorkflow` — workflow dispatches (T-0009)

Read by the cloud guard alone, while `guards.overrides.cloudGuard` is armed. A repo-only
map from a workflow glob to where the target environment comes from:

```json
{ "environments": { "nonProd": ["dev", "qa", "staging"],
                    "workflows": { "deploy.yml": "input:environment",
                                   "deploy-staging.yml": "staging",
                                   "deploy-prod.yml": "production" } } }
```

`input:<name>` reads the dispatch input `<name>` (a GitHub input name); any
other string is that fixed environment, classified by `nonProd` like a
terraform workspace. A key is matched with fnmatch, case-insensitively,
against the workflow **as written** on the command line; a quoted display name
with spaces (`gh workflow run 'Deploy Staging'`) is matched as that name.

**What is judged.** `gh workflow run <wf>` and the REST dispatch `gh api` sends
for it — method POST (`-X POST`, `--method POST`, `-XPOST`, or fields/`--input`
with no method, which gh sends as POST) on
`repos/<o>/<r>/actions/workflows/<wf>/dispatches`, leading `/` optional — are
parsed by one flag parser, which reads gh's clustered short flags
(`-iX POST`, `-iXPOST`, `-X=POST`), into one dispatch shape, and classified by
one function, `crew_dispatch.py::dispatch_environment`. Inputs come from
`-f`/`--raw-field` and `-F`/`--field` (`name=v` for `gh workflow run`;
`inputs[name]=v` for the REST form, whose top-level `ref` is the branch, never
an input). Every occurrence must agree. A `gh api` GET, or a POST to any other
path, is not a dispatch. A standalone `-h`/`--help` before `--` (and not a
valued option's value) prints help and sends nothing, so that line is not
judged; `--` ends gh's options, so `-- --help` is a second workflow argument.

**The dispatch grammar** (successor plan, 2026-09-27). The guard reads a line
as a dispatch when a command word dequotes to `gh`/`gh.exe` — after
assignments and wrappers, inside `bash -c`/`eval`/`pwsh -c` or a
substitution — or is made at run time, and its arguments could be `workflow
run ...` or `api <endpoint>`, a run-time word standing for any word. The
argv's shape decides, never what else the line mentions (review round 3): a
command word made at run time is bash's `$X` (which bash may split, so `$C`,
`$C deploy.yml` and `$C -f environment=x` can each be a whole dispatch), an
`xargs -I CMD CMD`/`parallel {}` placeholder, PowerShell's `& $x`, a
`Start-Process`/`-FilePath` target that is gh or made at run time, or a name
`Set-Alias`/`New-Alias`/an `alias:` path points at one; a PowerShell variable
in gh's own arguments (`gh $w run x`) is a run-time word too. Such a line is judged only when **every** word on it is a
plain literal (`[A-Za-z0-9_./:=@%+,-]`) or one whole single-quoted word with no
`'` or control character inside, and its only operators are `;`, `&&`, `||`,
`&`, a newline, `>`/`>>`/`&>`/`&>>` to a plain word, and the exact token
`2>&1` (PowerShell also refuses `,` and a leading `@`). Everything else is
**could not tell**: `|` anywhere on the line, every `<` form (`<`, `<<`,
`<<<`, `<&`, `<>`), any other `N>&M`, `>|`, `<(...)`, `>(...)`, double quotes,
`$'...'`, a backslash, `$`, a backquote, `*`, `?`, `[`, `]`, `{`, `}`, `~`,
a tab or CR inside a word, a control character; a dispatch the lexer is not
known to read (inside `bash -c`/`eval`/`pwsh -c`/`sh <<EOF`, behind `xargs`,
`parallel` or `find -exec`, an alias or a copy of `gh` made on the line, zsh's
`=gh`, a command word made at run time); gh reading its inputs from stdin or a
file (`--json`, `--input <anything>` including `-`, `-F name=@file`,
`-F name=@-`) — **crew never reads stdin**; a line whose literal reading and
the lexer's name different dispatches; and, for every dispatch-shaped line,
an `environments` block that does not validate (`workflows` must be an object
of non-blank keys to `input:<name>` or non-blank names), which also forces an
armed guard to `block` mode — in either layer: a malformed machine-global
block (`"prodUnattended": "yes"`, `null`) engages the gate and makes every
dispatch could-not-tell too, though it leaves the terraform layer's reading
and the mode as they were (the ratchet already holds a non-bool down).
**The launcher rule** (review round 4): a PowerShell launcher or alias writer
(`Start-Process`/`saps`/`start`, `Set-Alias`/`New-Alias`, a command writing an
`alias:`/`function:` path, `Invoke-Command`, `Start-Job`, ...) holding a
dispatch-shaped word — gh, `workflow`, `dispatches` (a quoted `-ArgumentList`
split on spaces and commas) or a word made at run time — is could-not-tell
unless every parameter on it is a full, value-taking name of that command
(`Start-Process`: `-FilePath`, `-ArgumentList`, `-WorkingDirectory`,
`-Credential`, `-Verb`, `-WindowStyle`, `-RedirectStandardOutput`,
`-RedirectStandardError`, `-Environment`; the aliasers: `-Name`, `-Value`,
`-Description`, `-Option`, `-Scope`; an `alias:` path writer: `-Path`,
`-LiteralPath`, `-Name`, `-Value`; any other launcher: none). A switch
(`-NoNewWindow`, `-Wait:$true`), an abbreviation (`-Fi`), a parameter alias
(`-Args`, `-PSPath`), `-RedirectStandardInput`, a common parameter or an en
dash refuses it — the accepted cost is that `Start-Process $exe -Wait
-ArgumentList 'notes.txt'` asks. A trusted line passes gh only its positional
values and `-ArgumentList`. **The same-command rule**: a command crew cannot
split (`alias`, `hash`, `source`, `ssh`, a launcher) is gated only when gh and
`workflow`/`dispatches` are in that one command — the whole line only when a
word in it is made at run time — so `alias g=gh; echo workflow` is not judged;
and `alias NAME=VALUE` whose VALUE's last command runs gh (past `env`,
`command` and the other wrappers; `alias g='echo gh'` runs echo), or `hash -p
PATH NAME` with PATH naming gh, makes NAME a copy of gh for the commands
after it — for the whole line when a loop, a function or a `trap` on it can
run earlier text later; `Set-Alias` counts for the whole line. A PowerShell
comma inside one whole single-quoted word is text; a bare one is refused. The grammar does not resolve anything: `x=staging;
gh ... -f environment=$x` is could-not-tell although bash would pass
`staging`. What a user may not expect, and the literal to write instead:
`--json`/`--input -` → `-f` fields; `"Deploy Staging"` → `'Deploy Staging'`;
unquoted `repos/{owner}/{repo}/...` or `-f inputs[environment]=x` → quote the
word; `| tee log` → `> log`; `$ENV` → the value; `bash -c 'gh ...'` → the
`gh` command itself; a PowerShell launcher or alias with a switch, an
abbreviation or a parameter alias → full parameter names and no switches, or
`gh workflow run ...` directly. Other `gh` commands (`gh pr create --title "..."`) are
never gated, and with `workflows` at `{}` (and a valid block) the gate does
not run at all.

**Unknown**, and never allowed unattended, on a literal line: no `<name>` input
given (the workflow's default is not read), conflicting values, a value or
workflow the parser still will not read as a name (a single-quoted `'$ENV'`,
`'Deploy *'`, or a name holding a character that does not show: a control, a
line or paragraph separator, a bidi or zero-width mark, or a blank other than
a plain space), a second workflow argument (gh takes one), and no workflow
named (gh prompts for one).

**The decision**, after `guards.overrides.deployWorkflow` has been ratcheted (so `ask`
means `ask` in **both** layers; a repo alone gets `block`):

| policy | nonProd | prod, `prodUnattended` both layers | prod | unknown env | could not tell |
|---|---|---|---|---|---|
| `block` | deny | deny | deny | deny | deny |
| `ask`, no live marker | **allow**, logged | **allow**, logged + on screen | ask | ask | ask |
| `ask`/`allow`, live marker | allow | allow | allow | allow | allow |
| `allow` | allow, logged | allow, logged + on screen | **ask** | **ask** | **ask** |

A deploy never destroys, so T-0005's destroy column does not apply — and
`allow` **covers nonProd only**: production without `prodUnattended` in both
layers, an unknown environment, and a line crew could not tell about still ask
when attended and are denied unattended. The approval marker is
`.approved-guard-deployWorkflow-<hash>`, keyed on the **whole command text,
byte for byte** — never a subset, so a marker for `--json < prod-one.json`
covers neither `< prod-two.json` nor the argv without its redirect — plus, for
a classified dispatch, the workflow key and environment judged, so an edit to
`environments.workflows` inside the 15-minute window does not carry an
approval across. A could-not-tell refusal names that marker.

**The contract for callers** (T-0045's autopilot dispatch, T-0072's promote
path). `crew_dispatch.dispatch_answer(text, shell, envs)` is the one public
entry point: `(state, why, scope)` with `state` in `nonProd | prod | unknown |
unlisted`, pure given `envs` (`cloud_guard.environments_config(root)`). It runs
the grammar before any parsing, so no caller reaches the parser around it;
could-not-tell is `unknown` with `scope["op"] == "line-not-literal"`; a line
with several dispatches answers for the most severe, every one listed in
`scope["dispatches"]`. The hook's own `_classify` reaches the parser only
through it. The hook's stdout is `deny`, `ask` or nothing — never `allow`.

**Unclassified.** A workflow matching no key is not judged at all — no
decision, no guard.log row — exactly as before T-0009; with `workflows` at `{}`
nothing is. `environments.workflows` does not count toward the terraform
layer's `engaged`, so listing workflows alone leaves `workspace new|select`
unjudged. Not seen: an unlisted spelling of a deploy workflow (its display
name or numeric id — list every spelling you use), the workflow YAML
(`environment:` keys, `${{ inputs.* }}`), `gh run rerun`, `gh alias`, a `gh`
copied or aliased by an earlier command, `env -S`, a script file, and `curl`.
A deploy command also declared in `.crew/verify.json` still passes through
`promote-gate.sh`, whose `requireHuman` is independent of `prodUnattended`.

### `unattendedCloud` — the identity an unattended run holds (machine only)

Read by `hooks/scripts/crew_unattended.py` (T-0044) from the machine file
`~/.claude/crew/config.json` **alone**. It is in `default_global_config()` and
`templates/global.template.json`, and absent from the repo shape: a repo's
`.crew/config.json` copy is dropped by `resolve_config`, reported as
`repoIgnored` by `/crew:config --show`, and named as ignored by the launcher. A
repo travels inside a clone written by someone else, so it must never choose
credentials on this machine — stronger than `resume.auto`, where a repo may at
least veto.

```json
"unattendedCloud": {
  "aws": {
    "readOnly": {"profile": "ro", "identity": "arn:aws:sts::123456789012:assumed-role/ReadOnlyAccess/", "region": "eu-west-1"},
    "nonProd": {"dev": {"profile": "dev-writer", "identity": "arn:aws:sts::123456789012:assumed-role/DevWriter/"}}
  }
}
```

- `identity` is the assumed-role ARN **prefix** exactly as `aws sts
  get-caller-identity` prints it, ending in `/`, and naming one role
  (`arn:<partition>:sts::<account>:assumed-role/<role>/`; a bare
  `.../assumed-role/` would admit every role and is refused). STS's ARN must start with it.
- `profile` is the `~/.aws/config` profile `aws configure export-credentials`
  exports; it must yield temporary credentials (`SessionToken` and
  `Expiration`). `region` defaults to `us-east-1`.
- `nonProd` maps an environment name to the same three keys, for
  `launch --environment NAME`. A name is usable only when the repo's
  `environments.nonProd` also classifies it as nonProd: both layers agree, as
  with `prodUnattended`. There is no production entry and none can be written.
- Any provider key other than `aws` refuses as not implemented (the provider
  seam for Azure and TFC/HCP).

The defaults name nothing (`profile`, `identity`, `region` all `null`,
`nonProd` empty), so every launch refuses with `no read-only identity named`
until the owner names one. README, "Unattended runs: sealed cloud
credentials", lists every check and refusal.

The launched session loads `~/.claude/settings.json` and the sealed
`--settings` only (`--setting-sources user`): a repo's `.claude/settings.json`
and `.claude/settings.local.json` never load, and the launcher refuses if
either has a `sandbox` key or a `Read` allow rule. Your own settings file does
load, so the launcher refuses while it sets `sandbox.excludedCommands`,
`sandbox.filesystem.disabled: true`, or a `sandbox.filesystem.allowRead` entry
that is a glob or sits at or under a credential store. Move such an entry to a
settings file the unattended run does not need, or run that tool attended.

### The ratchet is one table, not five copies

`install.policy` shipped its ratchet as a bespoke `effective_install_policy`
plus a bespoke `resolve_install_policy`. Four guards arriving beside it would
have been four more pairs — five mechanisms for one rule. One mechanism can be
wrong; five can disagree, and then only one of them gets fixed.

So: `crew_state.RATCHETED_KEYS` maps each ratcheted key to its `(tiers,
normalise, rank)` triple, `crew_state.effective_ratcheted` is the only place
that takes the minimum, and `crew_config.resolve_ratcheted` is the only place
that reads both layers raw and reports `heldDownBy`. The two old names survive
as thin wrappers so their callers and tests did not have to be rewritten to
prove the generalisation happened.

**`pm.authority` is deliberately not in that table.** It ratchets for the
*widening warning* on `/crew:config --set` (`crew_config._RATCHETED`, which is
a different table with different membership); its two layers still resolve by
ordinary precedence, because a repo raising its own PM's authority grants
capability inside that repo rather than on the machine. Neither table is
derived from the other, on purpose.

An unknown value fails closed to `block` on whichever layer carries it
(`normalise_guard_policy`), and both sides are normalised **before** they are
ranked — so a typo costs capability rather than granting it, and a widening
*from* an unknown still reads as a widening.

### Writing the repo layer, and the enum check both writers share

`/crew:config`'s menu (T-0075) writes `.crew/config.json` through one path,
`crew_config.plan_repo_write` / `write_repo_config` (CLI
`crew_config.py --set PATH=JSON --repo [--apply]`). It does not change what
either layer means on read; it marks what a repo edit changes **in force**:

- A **ratcheted** key compares `effective_ratcheted` before and after, by rank.
  Repo `guards.overrides.forcePush` `block` -> `allow` under a machine `allow` prints
  `! guards.overrides.forcePush widens to`; the same edit under a machine `block` does
  not widen, and prints `held down by the machine-global layer at block`
  instead.
- `pm.authority` resolves by precedence, so its before-value is the repo's own,
  else the machine's, ranked by `_RATCHETED`.
- Two repo-only consents are marked by value: `autopilot.mode: "plan"` and
  `verifyGate: false` (`crew_config._REPO_WIDENING`).

Every update is judged per LEAF (`crew_config.leaf_updates`, recursive), by
the one predicate both planners and the menu share, `value_allowed(dotted,
layer, value)`: a whole-block value is expanded, so
`autopilot={"mode": "plan", "bogus": 1}` is judged as `autopilot.mode` and
`autopilot.bogus` and the unknown leaf is refused, and one good leaf does not
carry a bad one. A block set to `{}`, or replaced by a scalar, is refused off
an open table (`guards: {}` refused, `qa.roles.review: {}` is "no pin").

Each judged leaf is also what is WRITTEN (`crew_config.assignments`, review
round 3): a block value is written leaf by leaf, so the block's untouched
siblings, unknown keys included, survive, and a widening is marked on the leaf
that widens (`{"guards": {"forcePush": "allow"}}` prints
`! guards.overrides.forcePush widens to`). A value at an open role table (`qa.roles`,
`dev.roles`) is written one ENTRY at a time, each entry a whole pin, so the
other roles' pins survive and a new pin never inherits the old one's model.

It refuses, naming the key and the reason: a path that is not a leaf of
`default_config()` (unknown keys, and a block emptied or replaced by a scalar,
such as `scope: {}`, that would drop a leaf the per-key rules guard),
`platform.*`, `schema`,
`scope.mode`, `scope.allowCliApproval`, `context.autoClear.onlyRepos` /
`.onlySessions`, and anything but exactly `false` or `null` for
`context.autoClear.enabled` or `resume.auto` (only the machine file arms
those). That test is by identity (`crew_config.is_repo_veto`), not `in (False,
None)`: `0 == False` in Python, and the readers (`crew_autocycle`,
`crew_resume`) compare with `is False`, so a written `0` would veto nothing. It
refuses to write when the file is absent or does not parse, rather than
creating a config from one key or overwriting the only copy -- and the menu
reads the file the same strict way, so over an absent or unparseable
`.crew/config.json` every repo row is read-only with that refusal as its
reason, rather than offered and then refused at Save.

**Enum values are checked on both writers.** `crew_config.enum_values` returns
the tuple each reader normalises against — the `RATCHETED_KEYS` tiers,
`AUTHORITIES`, `TICKET_GRANULARITIES`, `auto` + `QA_PROVIDERS`, and
`DEV_PROVIDERS` — and a value outside it is refused. This is a behaviour
change for the global `--set`: it used to write `pm.authority: "bogus"` and
read it back as `report-only`.

**The null rule** (`crew_config.null_means`). At the repo layer a `null` on a
veto-only key clears the veto, and on a key the machine file may set it
inherits the machine value (`without_null_shadows` drops it on read); either
layer, a `null` on an open key (no tuple) is unset. A `null` on an enum key at
the machine layer is refused: it is outside every tuple its reader normalises
against. A legacy `null` already in a file is tolerated; the rule judges what
is being written now. Each change carries its meaning (`null`), and the dry
run prints it.

**The merged file is judged whole** (`crew_config.merged_problems`): every
untouched known leaf of the file the write would produce is checked for what
its presence means at that layer (`_content_problem`): an enum value outside
its tuple (a legacy `null` tolerated), a consent key (`MACHINE_REFUSED`) in
the machine file, and a veto-only key holding anything but `false`/`null` in
the repo file. One already there refuses an unrelated write as `pre-existing
...`: an enum value says `fix that key first` (it can be fixed in the same
write), the other two `remove it by hand first` (no crew writer sets or
removes them). Unknown keys are never judged. JUDGEMENT: refusals of a write
are not refusals of content, so a `REPO_REFUSED` key in the repo file
(`/crew:init` and platform-sync write them) and a repo-only key in the
machine file (pruned by `filter_global` on every read) do not block a write.
Then `validate_providers` runs on the merged file at both layers, wrapped as
the layer's refusal. `qa.order` must be a list of QA providers or `null`: any
other shape (`1`, `true`, `"codex"`, an object) is refused at both layers with
exit 2, never a traceback, including when it is already in the file an
unrelated write merges onto (the menu then shows the rows it blocks read-only,
naming `qa.order`). A path past a template leaf (`pm.authority.a`) and an
object at a leaf (`pm.authority={"a": 1}`, `notify.chatId={}`) are refused at
both layers, on the update and when already in the file (`pre-existing`,
fixable in the same write). `qa.roles` and `dev.roles`, and each entry under
them, must be an object or `null`: a string, number, boolean or array there is
refused with exit 2 at both layers, the file included, since the reader drops
it and `qa.roles=1` would silently wipe every pin.

**Compare-and-swap, both files.** `write_global_config` and
`write_repo_config` re-run their plan on the bytes read inside
`crew_config_files.update_json`: an `O_CREAT|O_EXCL` lock file beside the
config (`<file>.lock`, the review ledger's construction; 3 s wait, then a
refusal naming the lock and the PID inside it), a strict read, and a
sibling-fsync-replace that keeps CRLF and a UTF-8 BOM. `--set` prints the
digest (sha256) of the bytes it planned against, `absent` when there is no
file, and `--apply --expect <digest|absent>` refuses a file that changed, or
appeared, since (`RepoWriteConflict` / `GlobalWriteConflict`, subclasses of
the refusals, so every existing `except` still catches them). Without
`--expect` the merge is onto the file under the lock. A repo write's widening
marks read the machine file, so `--set --repo` also prints `machine digest:`
and `--expect-global <digest|absent>` binds it: `write_repo_config` reads the
machine file once under the machine lock (always taken, creating its
directory when absent, never the file; taken before the repo lock, the one
nesting order) and refuses one that changed since. The machine writer now refuses an unparsable or non-object global file
instead of replacing it from the read path's `{}` collapse. A foreign writer
(an editor's save) is not serialised by the lock. An OS error from either
lock, the machine directory or the write itself is refused with exit 2,
nothing written and the path named, never a traceback.

### One resolver, two flavours

`guard.sh` and `guard.ps1` both shell out to `crew_config.py --guard`. Neither
implements config layering itself. The two files drift independently — three
bypasses fixed in #132 were open in both — and the layering rule whose entire
point is that a cloned repo cannot widen it must not have two implementations,
either of which could be the one that forgets to ratchet.

`Test-EnvArgHit` in `guard.ps1` *is* a deliberate reimplementation of its bash
counterpart, and the difference is the cost: it is a tokenizer that runs on
every command, where a subprocess would be a per-command tax. The guard
resolver runs only after a rule has already matched, so it costs nothing on the
common path.

**Fail closed, loudly.** No python, a `crew_config` that raises, a line the
shell cannot parse — every one of them is `block` with the reason said out
loud. Unlike the `prod`-argument rule, which degrades to a cruder regex, config
layering has no cruder form: "could not check" is its own outcome here and
never collapses into "checked, and fine".

### `guards.overrides.mergeGate` is read by a command, not by the guard

"May crew take a live repository's merge gate down" is not a shape a regex over
a command line can recognise, so this one key is read by `/crew:gate` and
`/crew:promote` rather than by `guard.sh`. It lives in the same block and the
same ratchet anyway — a fifth key somewhere else with its own layering rule is
how the two rules come to disagree.

It is a separate, lighter guard from `adminMerge`: `adminMerge` bypasses a
protection without touching it, and `mergeGate` removes and restores the
protection itself.


---

## change.requireForProduction - the ratchet that runs backwards

The `change` block holds one key now: `change.requireForProduction` (boolean, default `false`), in both layers. It decides whether `/crew:promote production` gate 1 needs an approved change request. Consumers: `commands/change.md`, `commands/promote.md`, `skills/crew-change/SKILL.md` and `hooks/scripts/crew_change.py`. The requester, implementor, category, SDP template and Jira issue type that `/crew:change` files a request with are fixed defaults now, or asked per request; see "Removed keys and migration".


### `requireForProduction` ratchets the other way round

It is in `crew_state.RATCHETED_KEYS` alongside `install.policy` and the
twelve guards, and it uses the same `effective_ratcheted` — the narrower of the
two layers wins. What is different is which value is narrower:

| Key | Tiers, least to most permissive |
|---|---|
| `install.policy` | `manual` < `ask` < `auto` |
| `guards.overrides.*`, the `block`/`ask`/`allow` guards | `block` < `ask` < `allow` |
| `guards.overrides.prodDatabase`, `.prodServer` | `none` < `read` < `full` |
| `change.requireForProduction` | `true` < `false` |

Requiring a change request takes a capability **away** from a promotion, so
`true` is the floor. `min(rank(repo), rank(global))` then means exactly what
the design asked for and nothing had to be added to say it: **a repo may turn
the requirement ON, and may never turn it off.** A machine-global `true` is not
defeated by a `false` in a repo somebody cloned; a repo's own `true` holds on a
machine that said nothing.

`sabotage.py`'s one-character `min` → `max` mutation covers this key along with
the other ratcheted keys, which is the point of the table: a bespoke resolver
for one more key would be one more thing that could be wrong on its own.

### The default is `false` and the floor is `true`, and they are not the same

This was the only ratcheted key in crew where "absent" and "unreadable" did
not resolve to the same value; `guards.overrides.roleWrites` (see "guards.overrides.roleWrites") is the second, added
in 0.19.92 for a mirror-image reason — there the FLOOR is the safe value and
the DEFAULT has to be the permissive one, because CLAUDE.md requires a new
blocking hook to ship disabled. Both halves below are load-bearing for this
key:

- **Absent, or an explicit `null`, resolves to `false`.** Schema 7 lands on
  every existing repo, and a mandatory migration that switched a production
  requirement on for everyone would be indefensible. A key nobody set is a
  requirement nobody asked for.
- **A value that is not a boolean resolves to `true`.** `"yes"`, the string
  `"false"`, `1`, a dict: crew cannot tell what was meant, and "could not tell"
  must not wear the label of "not required". The promotion stops and names the
  key — a refusal somebody notices within the minute, rather than a gate that
  quietly was not there.

`crew_guards.normalise_require_for_production` tests `isinstance(value, bool)`
rather than truthiness and rather than `isinstance(value, int)`. `True` and
`False` are `int` subclasses in Python, so an `int` check would have accepted
`0` as "not required" — the one direction this function must never fail in.

### What `true` actually does is prose

The key and the ratchet are code. What promote DOES about them is
`commands/promote.md`, and nothing enforces it: no hook fires on
`/crew:change`, and `promote-gate.sh` does not read `change.requireForProduction`
at all. That file's "What is enforced, and what is not" section says so by
name, in the same paragraph as the merge gate, deliberately — an unenforced
requirement that is described as enforced is worse than one honestly labelled.

### The ten-question gate is not prose

`hooks/scripts/crew_change.py` is, and it is the one part of this feature that
is mechanical. `/crew:change new` exits non-zero unless every one of questions
1–9 has an answer that is neither empty nor on `crew_change.PLACEHOLDERS`;
`close` does the same for question 10. There is no config key that relaxes it,
on purpose: the template's own rule is that missing information results in
denial, and a switch to turn that off would be a switch to file requests that
get denied.


---

## `guards.overrides.roleWrites` - mechanical enforcement of a role's write scope

Added in crew 0.19.92. `agents/pm.md:49-53` says, in prose, "You do not write
application code, tests, docs..." — and on 2026-09-19 it did exactly that for
four hours, because prose is not enforcement and nothing in the harness read
that sentence. This key and the `PreToolUse` hook it configures are the
mechanical version: a `Write` or `Edit` from a role outside its declared
scope is refused before it reaches the filesystem, rather than relied on to
not happen.

| | |
|---|---|
| Key | `guards.overrides.roleWrites` |
| Values | `block` \| `report` \| `off`, least to most permissive |
| Default | `"off"` |
| Layer | both, **narrower wins** (same ratchet as every other guard) |
| Read by | `hooks/scripts/role_write_guard.py`, via `hooks/scripts/role-write-guard.sh` / `.ps1` |
| Hook | `PreToolUse`, matcher `Write\|Edit`, registered once per shell flavour |

### What each value does

| Value | What crew does |
|---|---|
| `off` *(default)* | The hook exits before reading the policy table at all. Every write is allowed; nothing is logged. |
| `report` | Every write is allowed — including one outside the calling role's scope — and every decision is appended to `.crew/guard.log`, so an operator can see what `block` *would* have refused before turning it on. |
| `block` | A write outside the calling role's declared scope is refused (`PreToolUse` exit 2, with a message on stderr naming the role, the path and what that role may write); a write inside scope is allowed. Both are logged. |

### The default is `off`, and the floor is `block` - the second key in this file where those two differ

`change.requireForProduction` was the first. Every other guard's default equals its floor: an absent key and a
malformed value both collapse to the narrowest tier. This key splits them on
purpose, and the split runs in the OPPOSITE direction from
`change.requireForProduction`'s:

- **Absent, or an explicit `null`, resolves to `off`.** CLAUDE.md's own rule
  for a new hook that can block a turn is that it "defaults to OFF in the
  menu" until a human turns it on. An absent key is every repo that has never
  set it — which, the day this shipped, is every repo that exists — and none
  of them may go from "no such hook" to "blocking Write calls" by upgrading
  the plugin alone.
- **A value that does not name `block`, `report` or `off` resolves to
  `block`, the floor.** A typo in a hand-edited config is not the same fact
  as "nobody opted in" — CLAUDE.md's own recurring bug is exactly this,
  an unknown collapsing into the safe-looking (here: permissive) value. So a
  malformed value fails toward MORE refusal, not less, the same direction
  every other guard's `normalise_*` function fails in.

`crew_guards.normalise_role_writes` is the one function that knows this
split; `role_writes_rank` ranks through it first, so `effective_ratcheted`'s
`min(...)` still means what it means everywhere else in this file: neither
layer can widen past what the other allows, and a repo cloned with
`guards.overrides.roleWrites: off` cannot override a machine-global `block`.

### A THIRD case, beside absent and malformed-VALUE: the file itself is unreadable

Reported and fixed 2026-09-19, one commit after this key first shipped.
`normalise_role_writes` above only ever sees a raw VALUE that `_dig` already
pulled out of a parsed config — it has no way to tell "the repo file never
set `guards.overrides.roleWrites`" apart from "the repo file could not be parsed at
all", because `crew_state.load_config` collapses BOTH to `{}` before
`normalise_role_writes` is ever called. That collapse is correct for
`install.policy` and the other guards, which have always failed
OPEN on a bad config file (`read_global_config`'s own docstring: "a broken
global file must look exactly like no global file at all"). `roleWrites`
cannot inherit it: with no global override, replacing a repo's
`guards.overrides.roleWrites: block` config with invalid JSON — or with
`{"guards": 42}` — made `resolve_guard`'s effective answer `off` and let
`pm` write application code straight through, which is CLAUDE.md's own named
recurring bug landing on the one guard here that can least afford it.

`crew_config.layer_state(path)` gives `role_write_guard.py` the one extra
bit `load_config` throws away, classifying ONE config file as `"absent"`,
`"ok"` or `"corrupt"`. `"absent"` is every off-by-default repo or machine
that exists — stays `off`, unchanged. `"corrupt"` is present but
unreadable as this key needs: not valid JSON, not a JSON object, or a
`guards` key that IS PRESENT (`"guards" in parsed`, not
`parsed.get("guards") is not None`) and is not itself an object — which
covers an explicit `"guards": null` too, closing a gap the first draft of
this fix had (`.get()` cannot tell an explicit `null` from a key that was
never mentioned). A DIRECTORY at the config path is also `"corrupt"`, not
`"absent"` — `load_config`'s own `text is None` collapse could not tell
those two apart either, and the first draft of this fix inherited that
same blind spot from it. A DANGLING SYMLINK at the config path — pointing
at a target that has been moved or deleted — is `"corrupt"` too, found
one round later: presence is checked with `os.path.lexists`, not
`os.path.exists() or os.path.isdir()` (that second draft's own form),
because both of those FOLLOW a symlink to check its target, so a
dangling link answered `False` to both — the same "absent" a genuinely
unset key gets — even though something IS configured at that path and
cannot be read, which is exactly what `"corrupt"` means. `lexists` checks
the link itself, which also makes the directory case above redundant to
special-case separately; one check now covers a plain file, a directory,
and a dangling symlink alike.

`role_write_guard.py` calls `layer_state` on BOTH layers — the repo's
`.crew/config.json` and `GLOBAL_CONFIG_PATH` — and if EITHER is
`"corrupt"`, forces the effective policy to `block` UNCONDITIONALLY, not
only when the ratchet's own answer happens to be `off`. That second part
is load-bearing on its own: a corrupt repo config with a VALID,
non-`off` global policy (say `report`) resolves to `report` through the
ordinary ratchet — `report` never blocks anything — so a repo that used
to say `block` and got corrupted would silently downgrade to a policy
that never refuses, unless the corruption check runs regardless of what
the ratchet already computed. `layer_state` is a narrow, second read of
the config file(s), deliberately NOT wired into `load_config`,
`resolve_ratcheted` or any of the other ratcheted keys: widening the
collapse-detection to every guard was a bigger change than the one guard
that needed it, for behaviour the other guards have always had on purpose.
A malformed VALUE inside an otherwise-valid `guards` object (a non-string
`roleWrites`, or a string naming no known policy) is still
`normalise_role_writes`'s job alone, unchanged — this function's whole
purpose is the shape `normalise_role_writes` structurally cannot see.

### The policy table is in the hook script, not in this file

`hooks/scripts/role_write_guard.py` partitions every `agents/*.md` into three
buckets, decided by that file's own `tools:` frontmatter — not by its prose,
which is exactly the gap this hook exists to close:

- a role whose `tools:` line names neither `Write` nor `Edit` may not write
  anywhere, regardless of path (`explorer`, `researcher`, `reviewer`,
  `security` — the whole crew 1.0 roster; re-derive rather than trusting
  this list, and `tests/test_role_write_guard.py` does exactly that on every
  run);
- `pm` may write only under `.crew/**`, `TODO.md`, `.work/**` and
  `docs/diagrams/**`. crew 1.0 ships no `pm` agent; the branch stays for a
  repo-local agent of that name until the guard is retired (`TODO.md`);
  everyone else whose `tools:` line grants both Write and Edit is
  unrestricted by this hook — no shipped agent does, since 1.0.

`tests/test_role_write_guard.py::test_policy_table_matches_the_agent_files`
parses every agent file's `tools:` line and asserts the script's three sets
are exactly the partition that produces, so a `tools:` grant added or removed
with the table left alone fails a test rather than drifting silently.

### Scope is judged on the real path, not the one the tool call named

Reported and fixed 2026-09-19. `pm`'s scope check runs against the REAL,
filesystem-resolved path, never the lexical string a `Write`/`Edit` call
names: `.crew/link/app.py` matches `.crew/**` as text, but if `.crew/link`
is a symlink or a Windows junction pointing at `src/`, the write actually
lands in `src/app.py` once the tool opens it, regardless of what the
allowed-looking string said. `role_write_guard._resolve_real_target` walks
up to the deepest existing ancestor of the target (the file itself may not
exist yet — `Write` creates it) and resolves THAT, following any symlink or
junction earlier in the chain, before the scope comparison runs. Tested with
both link kinds actually created on disk — a POSIX symlink and a Windows
junction via `mklink /J`, the latter needing no elevated privileges — rather
than simulated, and SKIP-labelled wherever a given machine or user cannot
create one.

**A second round found the resolver itself had a gap, and it was the most
serious finding across this whole series.** `_resolve_real_target` started
by calling `os.path.abspath` on the raw path, and `abspath` collapses a
literal `..` LEXICALLY — before any symlink in the path is resolved.
`.crew/link/../app.py`, with `.crew/link` a symlink to `src/subdir`,
lexically normalised to `.crew/app.py`: a string that fnmatches
`.crew/**` and classified as in scope. The OS does not resolve that path
the same way — it follows `.crew/link` to `src/subdir` FIRST and applies
`..` against the RESOLVED parent afterward, landing in `src/app.py`. The
classification and the actual write disagreed, and the classification
was the permissive one: a symlink `pm` itself could stage under a path it
is trusted to write let it escape to anywhere that symlink's target's
parent could reach, just by adding `..` after it. Fixed by never calling
`abspath`/`normpath` on the raw path at all — `_resolve_real_target` now
walks the path one component at a time, resolving whatever exists on
disk as it goes, and a `..` pops the RESOLVED parent built up so far,
never a lexical one, mirroring how the kernel itself walks a path.
Verified with both a POSIX symlink and a Windows junction, driven end to
end through the real hook scripts, not simulated.

### `..` after a symlink is a platform-specific rule, not one algorithm

Reported and fixed 2026-09-19, one round after the resolve-then-pop fix
above shipped. That fix is correct on POSIX and **actively wrong on
Windows** — not merely imprecise. Win32's own path canonicaliser collapses
a literal `..` LEXICALLY, in the path string, before the filesystem or
reparse-point layer ever sees it: a junction sitting exactly where `..`
pops past it is never traversed at all. Resolve-then-pop computed the
opposite answer from real Windows in both directions:

- `src\link\..\new.py`, with `src\link` a junction to `.crew\subdir` (in
  scope): Windows collapses `src\link\..` to `src` before the junction is
  ever consulted, so the write really lands at `src\new.py` — out of
  scope, must block. Resolve-then-pop followed the junction first, landed
  in `.crew`, and wrongly allowed it.
- `.crew\link\..\app.py`, with `.crew\link` a junction to `src` (out of
  scope): Windows never consults the junction either, so the write really
  lands at `.crew\app.py` — in scope, must allow. Resolve-then-pop
  followed the junction to `src` first and wrongly blocked it.

A second, independent gap in the same walk: it split the raw path only on
`os.sep` (`\`), so a target spelled with forward slashes
(`C:/repo/.crew/link/new.py`, which tools commonly send even on Windows)
never broke into more than one component — the walk never walked
anything, and a junction anywhere in such a path went unresolved
regardless of the ordering question above.

`_resolve_real_target` now dispatches on `os.name`.
`_resolve_real_target_windows` splits on both `\` and `/`, collapses `..`
lexically first into a `..`-free path (mirroring Win32's own
canonicaliser), then walks that path resolving whatever junction or
symlink exists at each step. `_resolve_real_target_posix` is the original
resolve-then-pop walk from the paragraph above, unchanged — that ordering
is correct on a real POSIX host, where the kernel resolves each component,
including a symlink, DURING the walk and applies `..` AFTER, against the
resolved parent. Verified against both directions on a real Windows
junction, plus a real forward-slash target and a mixed-separator target,
all driven end to end through both `role-write-guard.sh` and
`role-write-guard.ps1`. The POSIX ordering has no equivalent always-running
direct unit test on this machine: `_resolve_real_target_posix`'s path
arithmetic assumes a POSIX root, a Windows drive letter breaks that
reconstruction, `os.path.lexists` never fires true against a real Windows
disk path built that way, and the walk silently degrades to pure lexical
popping — the very bug this function exists to prevent, reproduced by the
test harness rather than the code, so a "passing" test built that way
would prove nothing. Real POSIX coverage is instead an end-to-end test
correctly skipped when `os.name == "nt"`, live on any actual POSIX crew
installation.

### A different drive is proven outside the repo, not merely unverifiable

Reported and fixed 2026-09-19. `os.path.relpath` raises `ValueError` when
the two paths it compares are on different Windows drives, and that
exception used to reach the SAME catch-all as every other "cannot
resolve this" case, collapsing to `None` — "cannot classify", which `pm`
reads as out of scope and refuses. A different drive is not the same
fact as "cannot tell": it is PROVEN to be outside the repo root, the same
way a same-drive `../`-prefixed escape is. `_real_repo_relative` now
returns the sentinel `".."` for this one case specifically — the exact
string the outside-repo check already treats as a resolved escape — so a
`D:` target with the repo on `C:` gets `allow`, logged `outside-repo:
...`, instead of an incorrect refusal.

### A `\?\` extended-length path is never classified at all

Reported and fixed 2026-09-19. An earlier fix (not written up as its own
subsection here, since it shipped bundled with several others in the
same round — see `.crew/verify.json`'s history for that round) NORMALISED
Windows' `\?\` extended-length prefix away before classification:
`os.path.relpath` treats `\?\C:\repo\...` and `C:\repo` as different
mounts and raises, which read as "cannot classify" and incorrectly
refused a legitimate, in-scope write, so the fix stripped the prefix and
classified the bare remainder like any other path.

Codex round 5 found that normalising is itself unsound, not merely the
raising it replaced. `\?\` exists specifically so Win32 will SKIP its own
path normalisation for that one call — trailing dots and spaces are
preserved on disk, and a literal `..` component is never collapsed — so
stripping the prefix and classifying the remainder with this module's
ordinary (normalising) path handling answers a question about a
DIFFERENT path than the one Windows actually opens.
`\?\C:\repo\.crew.\app.py` (note the trailing dot on `.crew.`, a real,
distinct directory outside every scope `pm` is granted) stripped to
`C:\repo\.crew.\app.py`, which this module's own path handling then
further normalised to `C:\repo\.crew\app.py` — in scope, on the string
alone — while Windows itself opens a directory literally named `.crew.`,
never `.crew`. `pm` could reach any trailing-dot or trailing-space
sibling of a permitted directory this way, with the hook's own log
showing the innocuous, normalised `.crew/app.py` rather than what was
actually written.

No classifier built to be faithful to ordinary Windows path semantics
can also be faithful to a syntax whose entire purpose is bypassing those
semantics, so this module does not try. `_is_extended_length_prefix_path`
now short-circuits `main` before `_repo_relative`/`_real_repo_relative`/
`classify` ever run for such a path, and the decision is by role alone,
matching the same "scoped role" set the outermost exception handler
already treats as restricted: `pm` and every `_DENY_ROLES` member fail
CLOSED (`block`) unconditionally, regardless of `guards.overrides.roleWrites`'
configured policy; every other role, and a call with no `agent_type` at
all, allows — Claude Code itself never emits an extended-length path for
a `Write`/`Edit` call, so there is nothing here worth refusing for a role
this table already trusts with `Write`/`Edit` generally. Verified with a
real, on-disk `.crew.` directory (an ordinary, non-extended-length
`mkdir` call silently strips the trailing dot and collides with the
already-existing `.crew`, so even the test fixture needs the
extended-length form to create the directory it is testing against),
driven end to end through both `role-write-guard.sh` and
`role-write-guard.ps1`.

### A target outside the repo root entirely is not this guard's business

Reported and fixed 2026-09-19, a probe finding on the first commit — and
tightened by a second probe on the first fix, below. This guard's whole
purpose is the REPO's write scope, so `pm` writing to a harness-sanctioned
location OUTSIDE the repo — the scratchpad under
`AppData/Local/Temp/claude/<session>/scratchpad`, which every role including
`pm` is told to use — is not a scope violation at all; it was refused
anyway, because "outside every allowed prefix" and "outside the repo
entirely" collapsed to the same "not in scope" answer. Fixed with
`role_write_guard._is_outside_repo`, checked on the same REAL,
symlink/junction-resolved path (`_real_repo_relative`'s output) the in-scope
pattern match above already uses — a parent-relative escape (`os.path.
relpath` prefixes a result with `..` when the target lands outside `root`)
means the write is `allow`, logged `outside-repo: ...`.

**The first fix judged this on the LEXICAL path instead — what the tool
call SAID it was writing, never where the write actually lands — and a
second probe found that was the wrong side of the line.** `.crew/escape ->
/elsewhere`, a symlink STAGED inside `.crew/` (a prefix `pm` is trusted to
write) whose target is OUTSIDE the repo root entirely, is named lexically
INSIDE the repo, so the lexical version refused it — but the write itself
touches nothing under the repo at all, which is exactly the case this
exception exists for, symlink or not. There is no "but the tool call named
a path inside the repo" carve-out any more: the guard's business is where
the write actually lands. **The case that is still refused is a different
one** — `.crew/escape -> src/`, a symlink staged the same way but whose
target is ANOTHER IN-REPO directory outside `pm`'s permitted prefixes.
`_is_outside_repo` is `false` for `src/app.py` (still under the repo root),
so the ordinary `_pm_in_scope` pattern match above still runs and still
refuses it. `_DENY_ROLES` gets NONE of this exception either way: its
restriction is "no `Write`/`Edit` at all", not "confined to the repo", so an
outside-repo write is a different, stronger rule that role has no exception
from.

### What "unknown" means here

Two distinct unknowns reach this hook, and CLAUDE.md's rule applies to both:
an unknown must not wear the label of a decision, so both **allow**, but each
is named differently in `.crew/guard.log` rather than merged into one
unreadable "allow" row — `no-agent-type` (the hook fired with no `agent_type`
field at all — the main thread, or an older Claude Code build) and
`unknown-role:<value>` (an `agent_type` this table has no entry for: a
built-in agent, a different plugin's agent, or a typo).

**`agent_type`'s exact wire form for a plugin-scoped subagent was not
observed live against a real dispatched subagent in the session that built
this hook** — see the commit report for what was and was not verified. The
Claude Code hooks documentation describes the field only as "Agent name (for
example `"Explore"` or `"security-reviewer"`)"; this repo's own agents were
observed elsewhere in that session listed as `crew:pm`, `crew:analyst`, etc.
`role_write_guard._normalise_role` strips everything up to and including the
LAST `:` before matching, so both `"crew:pm"` and `"pm"` resolve to `"pm"`.
If the real wire form turns out to be neither, the hook still fails to the
allowing side: an unmatched value is `unknown-role`, logged and let through,
never a strand.

### Why this lives beside the other guards rather than as its own block

`install.policy`, the other guards and `change.requireForProduction`
already established the pattern this key needed: a value settable in both
layers, ratcheted to the narrower one, read through
`crew_config.py::resolve_guard` and nothing else. A bespoke
`resolve_role_writes` would have been a sixth mechanism for the rule the guards section's own
header states — "one mechanism can be wrong; two can disagree, and then only
one of them gets fixed." Adding `"roleWrites"` to `crew_guards.ALL_GUARD_NAMES`
and one branch to `crew_guards.guard_tiers` was the whole cost of reusing it.

### Without Python, a restricted role's write is always blocked

`role_write_guard.py` is what actually reads `guards.overrides.roleWrites` (both
layers, ratcheted) and pm's own path allowances. `role-write-guard.sh` /
`.ps1` are thin wrappers around it, and when no python interpreter can be
found or launched, neither wrapper falls back to re-implementing that
policy read itself — an earlier fallback tried to (parsing `roleWrites`
per layer with a bare regex, and pm's path allowances lexically), and
carried its own defects doing it: a dangling config symlink read as
absent rather than corrupt, bypassing fail-closed; the lexical pm-scope
check accepted `..` traversal and symlink escapes a real filesystem walk
would have caught; and the regex policy reader accepted truncated or
otherwise corrupt JSON as a clean `"off"`.

Rather than re-fix each of those, the no-python fallback in both flavours
now does less: it tells a restricted role (`explorer`, `researcher`,
`reviewer`, `security`, `pm`) from an unrestricted one — a floor that
needs no config to apply — and fails **closed** on the restricted side,
or on any role it cannot read at all (an unparseable payload, a non-string
`agent_type`, ...). It never reads `guards.overrides.roleWrites` and never applies
pm's path allowances. **Practically:** `off` and `report` only take
effect when python is available; without it, a restricted role's write is
refused regardless of what either config layer says, until python is
installed and the real classifier can run.


---

## `verify.stopBudgetSeconds` and the Stop gate's per-rule record

`verifyGate` and `verify.stopBudgetSeconds` are the only two config keys this
gate reads (the generated key list in `plugin/crew/CONFIG.md` shows both). Everything else about how a Stop turn is
verified is NOT a config setting — it is per-rule fields inside
`.crew/verify.json` (`reach`, `env`, `requiresCleanTree`, `seconds`) and a
machine-local record the gate keeps for itself. Documented here rather than
invented as new config keys, because that is what it actually is.

**The single marker used to mean "everything passed."** Before crew 0.19.93,
`.crew/.verify-verified-at` (the sha baseline) and `.crew/.verify-gate.fingerprint`
(the unchanged-turn skip) were written ONLY when every matched rule ran clean.
A rule priced over `verify.stopBudgetSeconds` on its own — permanently, not as
a fluke of this turn's ordering — was deferred on EVERY Stop, so neither ever
advanced again: the baseline froze, and every OTHER rule re-matched and
re-ran from that same old commit, forever. That was the actual 7+ minute Stop
gate defect this section exists to explain the fix for.

**The per-rule record replaces "everything or nothing."**
`.crew/.verify-gate.record.json` (machine-local, gitignored by the shipped
`.crew/*` template — see the ignore policy in root `CLAUDE.md`; where a repo
does not ignore it, it is crew bookkeeping, `crew_ticket.CREW_BOOKKEEPING_PATHS`,
excluded by name from the review bundle, the completion audit and the gate's
own changed list, and refused to Write/Edit by the scope guard, T-0068) now tracks status per
rule, keyed by a content hash of that rule's `paths`/`run` so it survives
`.crew/verify.json` being reordered:

- A rule that is PERMANENTLY over budget on its own no longer blocks the sha
  marker or the fingerprint. It is recorded as `"chronic"` instead, and the
  gate prints `NOT VERIFIED ON THIS TREE` for it on every subsequent Stop —
  whether or not that rule's own files changed this turn — until
  `/crew:verify --all` actually runs it clean. Its home is CI (L-0710): the
  line says `deferred to CI`, the `verify-gate` workflow runs it with no
  budget, and `/crew:done` refuses until that run's receipt is VERIFIED or
  `/crew:verify --all` has run it clean here. A
  deferral alone never exits 2 at Stop; a rule that runs and fails still does.
- **A turn where zero rules ran records nothing as verified** (L-0710). An
  empty changed set, or one for which the map selected no command (every
  match chronic, reach-excluded or unmapped and ignored), prints
  `verify-gate: 0 rules ran` and writes neither `.crew/.verify-verified-at`
  nor the fingerprint. It moves only the diff baseline,
  `.crew/.verify-gate.base-at` (HEAD), when the base did not come from the
  marker and nothing committed differs from the current base: on a default
  branch with no marker that is what keeps the next commit in scope. It is
  read as is when it is an ancestor of HEAD and through its merge-base with
  HEAD otherwise; one that cannot be read, is not a regular file or names no
  commit refuses the turn (exit 2), as does a write that fails. Nothing reads `base-at` as
  verified.
- A rule that would fit `verify.stopBudgetSeconds` alone but lost to this
  turn's contention (another rule's cost crowded it out) is "acute", not
  chronic, and still blocks the sha marker exactly as before this feature —
  that case really is unverified for THIS commit, not permanently
  unverifiable, and freezing the baseline is the correct answer for it.
- **Pricing**. A rule's cost is its declared `seconds`, or the
  smaller of that and a measurement of it on this machine
  (`.crew/.verify-gate.timings.json`), never the larger: a stale
  over-statement stops reading as chronic once one clean run measures it.
- **The tree-pass cache**. At Stop, a command that passed is credited,
  not re-run, while the tree is byte-for-byte the tree it passed on
  (`.crew/.verify-gate.passes.json`, keyed on HEAD, every ref,
  `.crew/verify.json`, `.crew/config.json` and every tracked and untracked
  path's bytes, type and mode). A rule all of whose commands are credited
  costs nothing, so an acute deferral on an unchanged tree runs what it has
  not run yet instead of the same rules again. `/crew:verify --all` never
  credits; it runs everything and saves its passes. If the tree changes
  during a run that credited something, the credits are withdrawn and the
  run does not count as verified. Any edit anywhere, or a fetch, empties it; ignored files (`node_modules`, a
  venv) are not in the key, as they are not in the fingerprint. Set
  `CREW_VERIFY_FRESH=1` in the environment to run everything for one run.
- **Quiet Stop output** (L-0796, crew 1.2.39). The Stop gate prints one verdict
  line first: `verify-gate: FAILED n cmd | PASSED n cmd | NOT VERIFIED n item(s) (reach a,
  over-budget b, dirty tree c, deferred d, skipped e, other f) | credited n |
  budget Xs/Ys | detail: .crew/.verify-gate.log`. FAILED, PASSED and credited
  count commands (`cmd`); NOT VERIFIED counts items (`item(s)`): one per rule for
  reach, over-budget, dirty tree and other, one per deferred rule, and one per
  command for skipped (exit 77) and for credits withdrawn because the tree moved
  (counted under other). On a multi-command rule the item count can therefore exceed
  the rule count. The two units are not added together. Then come the lines the gate cannot prove are informational, exactly
  as before: every `VERIFY FAILED:` block with its last 25 lines, `COULD NOT
  TELL`, a rc 77 SKIP, `UNMAPPED CHANGES`, a lock back-off, and any line the
  gate does not recognise. What moves to `.crew/.verify-gate.log` is the text the
  gate itself writes about a rule that did not fail: the pricing and
  measurement lines, declared reach and clean-tree exclusions, `deferred to
  /crew:verify`, the stop budget summary, `PASSED on this exact tree`, `COVERED
  by`, `env pinned`, the per-rule seconds and the totals, and the record's
  standing `NOT VERIFIED ON THIS TREE` lines (one line with their count stays).
  The classification is by the site that wrote the line, so a failing rule's
  own output is never classified: a test that prints `PASSED on this exact
  tree` is still shown. An unknown never reads as a pass: a deferred, skipped,
  reach-excluded or over-budget rule is counted under NOT VERIFIED, and a rule
  the gate cannot classify counts as `other`. The log is rewritten every run
  (temp file, then move) and holds the complete text of that run; if it cannot
  be written the gate prints the full text on stderr and the verdict says
  `detail: unavailable`, and a repeat Stop is never collapsed to the unchanged line while the log is unwritable. The Stop gate also remembers, per session, what it last
  reported in `.crew/.verify-gate.last-stop` (`session_id`, a SHA-256 of the
  failure text and the NOT VERIFIED counts): the same session still failing
  the same way prints `verify-gate: unchanged since last Stop (N failing, M NOT
  VERIFIED): <first failing command> | detail: .crew/.verify-gate.log |
  /crew:verify --all runs every rule` and still exits 2; the log it names holds
  that run's full failing output. A different session,
  a changed failure, a payload with no `session_id`, or a missing, unreadable
  or corrupt state file prints the full block; a passing Stop clears it. Run
  with `--verbose` (`-Verbose` in the PowerShell flavour) or
  `CREW_VERIFY_VERBOSE=1` to get the whole text on stderr as before;
  `--ci`, `--all`/`-All` and `--price` are verbose with no flag, so the CI
  receipt reader and `/crew:verify` see what they always did. Exit codes and
  the `VERIFY GATE: BLOCKED (exit 2)` stdout line are unchanged. Both files are
  dotted so the `.crew/.verify-gate.*` bookkeeping glob already covers them, and
  both are named in the fingerprint's gate-owned list (`verify_fingerprint.py`),
  so an untracked, unignored log never defeats the unchanged-tree skip. The
  PowerShell flavour buffers in memory and flushes in a `finally`; the
  `outside-scope:` line from its scope-report child is captured into the same
  buffer. A run that backs off on the lock never writes the log or the state
  file the lock holder owns, and a payload whose `session_id` is not a string
  directly in the top-level object, or that carries it more than once, reads as
  no session (full block). An exit-0 Stop clears the repeat state. If the
  buffer cannot be split, the raw text prints whole and no log or state is
  kept. The buffer, its two halves, the log and the state file are `mktemp`
  files (mode 0600), never names derived from a process id. A reach-excluded `always` or `default`
  command counts under reach, and the repeat check hashes which rules and
  commands were not run, not only how many.
- A rule declaring `"reach"` other than `"local"` is recorded as
  `"reach_declared"` and never runs on Stop — only under `/crew:verify --all`
  and the merge gate. Declaring `"reach": "local"` runs on Stop with NO
  inspection at all; that is the human saying so, and the gate takes the word
  for it.
- A rule naming no `"reach"` is classified by `verify_record.scan_reach`,
  which as of crew 0.19.9x (Codex round 6) STOPS MODELLING SHELL. Rounds 4-5
  each read further INTO a command's shell syntax to decide whether a
  wrapper it named was safe — follow the script, split it into the segments
  a shell would run separately, open a `$( ... )` substitution's own
  contents — and each round of review found a shape that defeated whatever
  the previous round had just taught the scanner to read: subshell
  parentheses glued to a path, `-n` granted by mere PRESENCE anywhere in the
  token list rather than its actual position, a command hidden inside a
  substitution the segmenter never knew to open. Five rounds of "read one
  layer deeper" is not a fixable bug; it is the wrong approach. So this scan
  no longer parses shell at all:
  - if the command string contains ANY shell metacharacter — anything that
    could combine, substitute, quote, glob, redirect or comment:
    `` ( ) $ ; & | < > ` " ' \ { } * ? [ ] ~ # ! ``, a newline, or a tab — it is
    deferred unconditionally as `"reach_syntax"`, reason `shell syntax in an
    undeclared rule — declare "reach": "local" (or network/host) to run it
    on Stop`. No exception, not even `2>&1` or a trailing `#` comment: a
    character on the list means "declare reach", full stop.
  - only once nothing on that list is present does whitespace-only
    splitting become safe (there is no quoting left to get wrong). A reach
    verb (`ssm`, `ssh`, `curl`, `aws`, `az`, `gh`, `psql`, `mysql`) anywhere
    → `"reach_undeclared"`, reason `remote verb <v>`.
  - otherwise, if the first token is a recognised interpreter
    (`bash`/`sh`/`dash`/`zsh`/`pwsh`/`powershell`/`python`/`python3`/`py`/
    `node`/`ruby`/`perl`): `-n` grants the parse-only exemption ONLY when it
    is EXACTLY the second token and there is EXACTLY ONE token after it
    (`bash -n a.sh` is parse-only; `bash a.sh -n` and `bash -n a.sh b.sh`
    are not); `-m` as the second token names a MODULE, never a file, and is
    always local (`python3 -m pytest x -q` is local); `-c`/`-Command`/
    `-File` as the second token name inline code or a script argument and
    always defer as `"reach_wrapper"`; any other token from the second
    position onward that resolves to an existing file under the repo also
    defers as `"reach_wrapper"`.
  - otherwise (not a recognised interpreter): any token at all that
    resolves to an existing file under the repo defers as `"reach_wrapper"`.
  - none of the above: runs undeclared.
  - `default`/`always` commands in `.crew/verify.json` go through this SAME
    classification on Stop — they have no `"reach"` field of their own to
    declare, so a deferred command named there is excluded from the
    fallback exactly like an undeclared rule would be, never reintroduced
    through it.
- `/crew:verify --stamp-reach` (`hooks/scripts/verify_reach.py`, L-0562)
  declares `reach` on undeclared rules from this same classification:
  `local` where the gate already runs the rule, `network` where it defers
  it for a remote verb. Syntax- and wrapper-deferred rules are left for a
  person (`--set N=...`). `reach` is hashed into the rule key, so it also
  moves each stamped rule's timings-cache and record entries to the new key;
  applying it changes neither what Stop runs nor what it costs in the
  checkout that ran it. The caches are machine-local and gitignored, so
  another checkout or worktree that pulls the stamped map prices those
  rules afresh: run `/crew:verify --all` once there.
- **What Stop says about undeclared rules (L-0733).** A map written before
  `reach` existed used to print a `rules[N] wrapper or inline shell ...` line
  per matched rule and a `NOT VERIFIED ON THIS TREE - rules[N]` line per
  record entry on every Stop. Now the first Stop that defers an undeclared
  rule prints ONE notice: how many rules matched and how many in the map have
  no `reach`, `/crew:verify --stamp-reach` (dry run, then `--apply`, and
  `--set N=local|network|host` for a wrapper or shell rule), then each
  deferred rule's reason once. It is shown once per `.crew/verify.json`
  content (`.crew/.verify-gate.reach-notice` holds the map's sha256,
  machine-local bookkeeping); after that every Stop, quiet turns included,
  says it in one line: `NOT VERIFIED ON THIS TREE - N rule(s) with no
  `reach` not run on Stop: rules[...]`. The deferral is unchanged, `--ci`
  keeps a line per rule, and `/crew:status` still counts the entries by kind.
- **An orphan** is a record entry whose rule was edited or removed since it
  was recorded (its `rule_key` changed). When the map has a new rule on the
  same `paths` (the same rule edited: `reach` or `seconds` added, `run`
  changed), the orphan is **superseded** and dropped, with a
  `dropped the obligation of rules[N] ... rules[M] on the same paths
  replaces it` line (L-0733); a rule that already sat beside it on those
  paths is not its replacement. Each entry carries `pathsKey` and `peers` for
  this; one recorded before L-0733 has neither, so it is never superseded.
  An orphan nothing replaced stays in the record, marked
  `orphaned`, because an edit does not verify anything. An undeclared-reach
  orphan does not hold the verified marker (L-0733): its live form never
  did, and `--stamp-reach` in another checkout would otherwise freeze that
  checkout's marker for good; it is counted in the one-line summary. Any
  other orphan holds the marker until `/crew:verify --all` runs, or until
  `python3 hooks/scripts/verify_record.py forget-orphans`, run from the repo
  root, drops it by name and runs nothing — for a map whose `--all` would
  reach `network`/`host` targets. The Stop line names that command.
  The record is per checkout (`.crew/.verify-gate.record.json`): `--all`
  clears only the record of the checkout it runs in, `--ci` never prunes it,
  and every orphan and `NOT VERIFIED` line ends `[record: <absolute path>]`.
- **Every exit 2 writes a line to stdout** (L-0733), `VERIFY GATE: BLOCKED
  (exit 2) ...`, in both flavours. Claude Code treats a Stop hook that exits 2
  with empty stdout and a stderr matching `no such file` or `can't open` as a
  missing hook script and lets the turn through ("Hook script appears to be
  missing ... Treating as non-blocking"), so a rule failing with
  `No such file or directory` used to be waved past.
- A rule declaring `"requiresCleanTree": true` is recorded as
  `"clean_tree_required"` and is never run on Stop either, for the same
  reason: the working tree is dirty by definition during ordinary work, so a
  rule that refuses on a dirty tree is a permanent red there and a real
  check only under `--all` against a clean checkout.
- A rule declaring `"coveredBy": "<id>"` (L-0572) names another rule's
  `"id"` as running a superset of its checks. Under `--all` or `--ci` only, its
  commands run last and are recorded as `covered` - clean, but never cached
  as a timing - when every command of that rule exited 0 earlier in the same
  run, a whole-tree snapshot taken before the first command still matches,
  and `PYTEST_ADDOPTS` is empty. Anything else runs it: a superset that
  failed, exited 77 or was killed, did not match, or changed the tree; a
  command `always` or an undeclared rule also names; an invalid declaration
  (unknown or duplicate id, itself, a chain, a superset with no runnable
  command, a different `env`), which is ignored with a named notice. Stop
  mode never credits. This repo declares `rules[9]` (the full crew suite)
  `crew-suite` and its pytest-only subsets `coveredBy` it.
- A rule whose command exits 77 is recorded as `"skipped"` — the
  `_verify/smoke.sh` and GNU automake convention for "skipped, environment
  absent". Not a pass, not a fail: it does not fail the Stop turn and it is
  not recorded as verified either.

**Who settles what Stop did not check (L-0710).** A `chronic` rule (deferred
to CI), a `skipped` one, and a Stop turn where `0 rules ran` all leave HEAD
without a clean pass, and none of them fails the turn. `/crew:done` check 2
settles them: it passes on `ci_receipt.py check` exit 0 `CI_RECEIPT VERIFIED`
(the `.github/workflows/verify-gate.yml` job ran the whole map, unbudgeted,
on exactly that committed tree) or exit 4 `NO_GATE`, or on a record with
nothing outstanding (`crew_status.py`'s `verify   no rules recorded`: a clean
pass empties it) together with `review_gate.gate_state` answering `VERIFIED`
(the marker names HEAD and the working tree still has the fingerprint that
pass wrote; a marker at HEAD alone survives an uncommitted edit). Anything
else refuses the close. No config key
changes this, and `verify.stopBudgetSeconds` decides only what Stop runs.

**`--price` writes `seconds` into `.crew/verify.json` itself, so it is an
operator command, never something a hook runs.** `.crew/verify.json` is
TRACKED in this repo (`git ls-files .crew/` lists it, per the ignore policy
in root `CLAUDE.md`), so an automatic `--price` would dirty a committed file
on every Stop. `verify-gate.sh --price [path] [--force]` /
`verify-gate.ps1 -Price [-PriceTarget path] [-PriceForce]` is reachable only
by typing the flag; the Stop hook (`hooks.json`) never passes it.

**`--ci` / `-Ci` is the gate as a pull request's CI job (crew 1.0.232), and
it is not a spelling of `--all`.** Its scope is the whole map with no budget
and no fingerprint skip, over TRACKED files only (`git ls-files`, staged
deletions and renames included): a CI workspace's untracked files (a crew
checkout, a `.venv`, build output) are not the change and do not trip
`"unmapped": "fail"`. Its reach filter is Stop's: a `"reach_declared"` rule,
an undeclared one `scan_reach` will not clear, and an `always`/`default`
command it will not clear are named and not run, because a CI runner has
none of the credentials or network paths they were written against. One
`verify-gate --ci:` line counts them; they do not fail the run, and they run
only under `--all`. A `"requiresCleanTree"` rule RUNS, because a CI checkout
is the clean tree it was sent to. A failing command, a command exiting 77
(`a skip is not a pass in CI`) and any deferral exit 2.

Under `--ci`, every path that would end having checked nothing exits 2 with
a named `verify-gate --ci:` reason, where Stop exits 0: `verifyGate: false`,
no map and no `_verify/smoke.sh`, a project directory the gate cannot enter,
no tracked files (not a git work tree, or git refused the checkout), zero
commands to run (every matched rule reach-excluded, nothing matched and
`always`/`default` added nothing, or every command blank), a lock held by
another gate run, and the `.ps1` run off Windows (use the `.sh` there). The
Stop-only stand-downs do not apply: `--ci` reads no stdin (so a
`stop_hook_active` payload cannot end it), the emergency lane does not stand
it down (an `.crew/incident.json` is named and the rules run), and the
`.deploy-in-flight` check is skipped without touching the marker.

`--ci` never writes `.crew/.verify-verified-at` or the fingerprint, even on a
full pass, and the pass line says why. It still writes the gate's other
machine-local files: the per-rule record (synced with `all` false), and the
timings and tree-pass caches as on any run. Arguments are checked strictly
in every mode: the `.sh` accepts only `--all` and `--ci` (in any position)
and `--price` (first only), so `-ci`, `--CI` or `--ci=1` is a usage error rather than a
Stop run in CI; the `.ps1` refuses an argument PowerShell's binder would
have passed through (`-Bogus`, `--ci=1`, a bare word). `--ci` with `--all`
or `--price` (`-Ci` with `-All` or `-Price`) is a usage error too. Run it from the job's checkout:
`bash <crew>/hooks/scripts/verify-gate.sh --ci`.

**The map comes from the PR head, so a PR can weaken its own gate.** `--ci`
reads `.crew/verify.json` from the checkout it is verifying: a PR that drops
a rule, narrows its `paths` or declares it `network` changes what its own
job checks. (`verifyGate: false` cannot do it: `--ci` fails on that.) With no
map, a passing `_verify/smoke.sh` passes, unscoped and unfiltered as on Stop.
Review a `.crew/verify.json` change as code, and do not treat a green `--ci`
job as evidence about a map the same PR rewrote.

**Environment pinning is unconditional, not a config key either.** Every rule
command the gate runs gets `ENV`, `AWS_PROFILE`, `AWS_DEFAULT_PROFILE`, `AWS_DEFAULT_REGION`,
`AWS_REGION`, `AZURE_SUBSCRIPTION_ID`, `ARM_SUBSCRIPTION_ID`, `KUBECONFIG`,
`TF_WORKSPACE` and `TF_VAR_environment` unset, unless that rule's own `"env"` object
declares values for them — in which case exactly those are set instead, and
the gate prints what it pinned. There is no `verify.envPinning: false` escape
hatch; a rule that genuinely needs a variable declares it, in the map, next
to the command that needs it.

**Unknown never resolves to the permissive value, in any of this.** A
`.crew/.verify-gate.record.json` that cannot be read is treated as empty —
losing only history, never fabricating a clean rule that never ran (see
`verify_record.py`'s module docstring). A `.crew/config.json` that cannot be
read leaves `verify.stopBudgetSeconds` at its compiled default (60) rather
than removing the budget. See `commands/verify.md` for the full mechanism and
`hooks/scripts/verify_record.py` / `verify_price.py` for the code.

**A rule passes only on a completion record (T-0082), not a config key.** Each
rule's wrapper writes the rule's exit status to a temp record file after the
rule ends. The rule passes only when the wrapper ended 0 and the record exists
and says 0. A rule killed or signalled (record above 128), a wrapper that
ended before writing (killed, or never started on `.ps1`), or a record that is
missing or unreadable is FAILED as "could not tell": `VERIFY FAILED` plus
`verify-gate: COULD NOT TELL (<reason>)`, status `unknown` in the command log,
counted in a summary line, and neither marker advances. Exit 77 is still SKIP
and a plain non-zero still a plain failure. The gate still has no per-rule
deadline: a hung rule is waited for. See `docs/guides/crew/src/troubleshooting.md`
("Verify gate says COULD NOT TELL") for each reason.

**Limitation (1.0): the gate does not reap background processes a rule
leaves behind; a rule must not background work — a rule that does can keep
running (and writing) after the gate returns.** Per-rule process-group
tracking and kill-on-signal shipped, then was descoped from crew 1.0 after
five consecutive review rounds each found the previous round's fix one case
short (disk fill by an orphan writer, escape on gate kill, an unlocked
registry, pid/pgid reuse in both p- and g-mode, a session-id proof that is
not ownership, a leader-exited group) — see CHANGELOG 1.0.21 and TODO.md.
Rule output is still captured through a temp file rather than a pipe, so a
backgrounded grandchild cannot wedge the gate's own read of that rule's
output (see `verify-gate.sh`'s rule-loop comment) — what is gone is the
gate reaching in afterward to kill what a rule left running.


---

## `autopilot` - `/crew:autopilot`, off until `plan`

`/crew:autopilot` (T-0004, since 1.0.41) drives one ticket through the
lifecycle phases `crew_autopilot.next_phase` names from disk, following each
phase command's procedure in-session, and stops wherever a person is needed.
Every stop names the owner decision it asks for (`decision=`, L-0666) and
never a refresh, a graph build or a review round autopilot runs itself; no
setting changes that.
`crew_ticket.py assign` (T-0019; the `/crew:autopilot assign` route lands with
L-0611) mints one ticket from a staged direction, with no key of its own, and
that ticket is approved under `autopilot.approval` like any other.
`/crew:autopilot goal` (T-0012) writes a goal file and asks for its split
approval under the same `autopilot.approval`, with no key of its own: `self`
approves the split, `risk` only when every proposed ticket is a known
`risk: low`, `human` stops, and every setting needs `scope.allowCliApproval:
true` and `mode: plan`; the owner's `/crew:approve goal:<slug>` receipt
approves it at any setting (README, "Autopilot"). Autopilot's size check after
spec and after plan (T-0058) applies a ticket's split, `crew_autopilot.py split
--apply`, under the same `autopilot.approval` and T-0012's rule on the
parent's spec risk (`crew_split.ticket_split_policy`), with no key of its own;
in `tracker: jira` it always stops for the owner's `/crew:split <KEY>`, and in
`sdp` it stops.
Since T-0050 every key in its block is **personal**: settable in the machine
file as the owner's default for every repo, combined per key with the repo's
value by the rule in "Personal keys and the per-key ratchet" (the stricter of the layers that set it wins). The
`/crew:init` template no longer spells the block.

| Key | Default | Read by | What an unexpected value does |
|---|---|---|---|
| `autopilot.mode` | `"off"` | `crew_autopilot.settings`, through `crew_config.resolve_config` | Only the exact strings `"plan"` and `"backlog"` (L-0541: a goal run goes on to the goal's next ticket; it ranks above `plan` between layers) arm it. `"Plan"`, `"plan "`, `true`, `"on"`, `null` — anything else — reads as `off`, and `settings` prints which value it saw. A typo must not arm a driver. |
| `autopilot.maxPhases` | `12` | `crew_autopilot.settings`; `next_phase` stops once the session's phase count reaches it | Anything but a positive integer (`0`, `-3`, `"12"`, `true`, `2.5`) reads as `12`, with a warning. |
| `autopilot.deploy` | `"none"` | `crew_autopilot.settings`; `crew_autopilot.deploy_allowed` (T-0072) | Only the exact strings `"none"`, `"nonprod"` and `"all"` are read as themselves. `"All"`, `"all "`, `"prod"`, `true`, `1`, `null` — anything else — read as `none`, with a warning naming the value. A machine value is the default where the repo is silent (see "Personal keys and the per-key ratchet"). |
| `autopilot.approval` | `"risk"` | `crew_autopilot.approval_policy` (T-0010): whether `crew_autopilot.py approve` may record the plan approval itself | Anything but exactly `human`, `self` or `risk` (`"Self"`, `true`, `null`) reads as `human`, with a warning. `human` always stops. A `.crew/config.json` or machine-global file that exists but is not a readable JSON object, or an `autopilot` value in either that is not an object, reads as `unknown` (could not tell): `approve` refuses, and `mode` reads `off`. Since T-0050 the machine file counts too: `read_global_config` collapses a corrupt one to `{}`, which would turn a global `human` into the default `risk`, so `crew_autopilot._unreadable_machine_autopilot` reads it raw first. An absent file or block reads the default. |
| `autopilot.questions` | `"risk"` | `crew_autopilot.question_policy` (T-0010): whether autopilot takes the researched recommendation for an open question | Same: anything else reads as `human`, which always stops; an unreadable config or non-object block reads as `unknown`, and a question stops. |
| `autopilot.maxAutoReplans` | `0` | `crew_autopilot.auto_replan_policy` (T-0074): how many successor plans one ticket may have before an out-of-rounds BLOCK round stops for the owner again; `0` is off | Anything but a non-negative integer (`true`, `"2"`, `2.5`, `-1`, `null`) reads as `0`, with a warning naming the value; an unreadable config or non-object block reads as `0`. The limit is `5`: a larger value reads as `5`, with a warning. |
| `autopilot.sleep.schedule` | `null` | `crew_sleep.resolve`, from `crew_autopilot._settings_at` (T-0053) | Only a whole `HH:MM-HH:MM` string (24-hour, zero-padded, ASCII digits, no spaces, start not equal to end) is read. `"7:00-22:00"`, `"22:00 - 07:00"`, `"24:00-07:00"`, `"22:00-22:00"`, `2200` — anything else — is could not tell, with a warning: only an override stricter than the day value applies (an override that is not a policy or cannot be read, or a non-object `autopilot.sleep`, counts as `human`). `null` is off. |
| `autopilot.sleep.approval` | `null` | `crew_autopilot._settings_at` (T-0053): `autopilot.approval` inside the window | `null` keeps the day value. Anything but exactly `human`, `self` or `risk` (`"Human"` included) counts as `human`, the strictest, with a warning: it applies asleep and, under could not tell, is the stricter value; it never reads as permission. |
| `autopilot.sleep.questions` | `null` | `crew_autopilot._settings_at` (T-0053): `autopilot.questions` inside the window | Same as `autopilot.sleep.approval`. |
| `autopilot.sleep.deploy` | `null` | `crew_sleep.deploy_overlay`, from `crew_autopilot._settings_at` (L-0654): `autopilot.deploy` inside the window, which `deploy_allowed` reads | `null` keeps the day value; exactly `nonprod` or `none` replaces it while asleep (stricter-only for a manual sleep outside the window). `all`, or anything else, is refused with a warning and the day value stands. Asleep, an effective `all` reads as `nonprod`: **production never runs unattended asleep**. A manual `wake` inside the window only tightens, so the night's cap stands (review r2). Otherwise awake, off or `unknown`, the day value stands, `all` included. |
| `autopilot.ship` | `"merge"` | `crew_autopilot.settings`; `next_phase`'s ship rows and `crew_autopilot.ship` (T-0011, since 1.0.349) | After `/crew:done`: `pr` pushes the branch, opens the PR and stops; `merge` also runs exactly `gh pr merge <n> --merge --match-head-commit <HEAD>` (never `--squash`, `--rebase` or `--admin`, and never into a merge queue) once the required checks allow. A merge commit, because a squash or rebase rewrites the ticket's commits and every codemap and diagram `anchor:` naming one then names no commit on the default branch (D-028). Anything but exactly `pr` or `merge` (`"Merge"`, `"squash"`, `true`, `null`) reads as `pr` - the non-merging direction - with a warning. |
| `autopilot.maxTicketsPerRun` | `3` | `crew_autopilot.settings`; `crew_autopilot_backlog.goal_run` (L-0541) | Tickets one goal run (one session, recorded in the goal file's `runs`) may start; the next stops the run with its `resume: /crew:autopilot --goal <slug>` line. Anything but a positive integer reads as `3`, with a warning. Repo only. |
| `autopilot.maxTokensPerSession` | `2000000` | `crew_autopilot.settings`; `crew_autopilot_backlog.goal_run` (L-0541) | Input + output tokens this session's transcript may hold before a goal run stops, each assistant message counted once (L-0728; Claude Code repeats a message's usage on every line it writes, which the count used to add up; cache tokens are not counted). A transcript that is not found, or a line that does not parse, stops as could-not-tell. Anything but a positive integer reads as `2000000`, with a warning. Repo only. |
| `autopilot.maxLanes` | `null` | `crew_wave.settings` (T-0029): how many `/crew:autopilot wave` lanes run at once | `null` is the resolved `pm.maxDispatches`; a larger value is capped to it and anything but a positive integer reads as it, each with a warning. It can only lower the dispatch limit. Repo only. |
| `autopilot.reviewPolicy` | `"stop"` | `crew_wave.settings` (T-0029): what a wave lane does with its review verdict; `crew_autopilot.settings` (T-0067, `crew_autopilot_fix.py`): what a single-ticket run does with a FINDINGS round no receipt stands on | Wave: `stop`: FINDINGS ends the lane as `findings`. `clean-only`: CLEAN goes on to the done checks. `fix-and-rereview`: fix and re-review within the ledger's two rounds. Single ticket: `stop` and `clean-only` stop at `accept-review` as before; `fix-and-rereview` makes `next` name the `fix` phase (`fix-findings <id> round <n>`) for a round with a round left and a BLOCK or FIX line, then the refresh and `/crew:review` once `.work/tickets/<id>/fixes.md`'s `## Round <n>` quotes every BLOCK and FIX line and the bundle changed. A config that cannot be read reads `unknown`, which never fixes. Anything else reads as `stop`, with a warning. No setting lets autopilot accept or reject a review. Repo only. |

**Which file.** `.crew/config.json`, through `resolve_config` — the file
`crew_ticket.cli_approval_allowed` already reads, so the approval policy T-0010
adds reads the same one. `/crew:migrate` writes `.crew/crew.json`, which crew
does not read for this key; an `autopilot` block found only there is reported
by `settings` ("move it to .crew/config.json") rather than read as `off` with
no word. Migrate carries the block to crew.json's top-level `autopilot` with
a note (`AUTOPILOT_FILE_NOTE`): that copy is never read; crew reads
`.crew/config.json`, and the personal keys also the machine-global file, where
the stricter value wins (see "Personal keys and the per-key ratchet").
`settings` prints `mode`, `maxPhases`, `deploy` and `maxAutoReplans`
on its first text line, the effective `approval` and `questions` on its second, and
`sleep=<off|awake|asleep|unknown> schedule=<window|none> approval=<override|->
questions=<override|-> source=<schedule|manual>` on its third (L-0652 adds
`until=<HH:MM>` for a manual state), and `maxTicketsPerRun` and
`maxTokensPerSession` on its fourth (L-0541); `--json` adds `day` (the two day values)
and `sleep`.

**Sleep log and morning summary (L-0653).** Every decision autopilot makes
while asleep -- an `approve` (`approved`), and each answer the command takes
(`sleep-note --kind answered`) -- is appended to `.work/autopilot/sleep-log.md`
as `- <ISO local time> | <ticket> | <kind> | <text> | <setting>`, with the
setting that allowed it (`sleep.approval=self (day risk)`). The log is local
(`.work/` is ignored; two worktrees keep two logs), append-only (one write of
one whole line, O_APPEND), never committed and never read to decide anything:
it grants nothing. Every field is folded to one line with `|` replaced, so no
field can forge an entry or a `- reported` marker. `crew_autopilot.py
sleep-summary` prints the entries the last marker does not cover, grouped by
ticket, and appends a new marker -- not while still asleep, and not when there
is nothing to report. The marker is `- reported <ISO> upto <n>`, `n` the bytes
it read, so a decision another process appends between the read and the
marker is reported next time. `wake` prints the summary after its state line
(and exits non-zero when the summary fails), and once the window has ended
`settings` warns `<n> sleep decisions are unreported`. **Delivery
(L-0656).** Holding attention pings while asleep is no longer configurable and
is fixed off, so none are held. Reported awake, the summary text goes to the
notifier once (silent, through the configured provider, only when `question`
or `blocker` is in `notify.events`), under a lock so two runs never both send,
and only once it was delivered (or no notifier is set up) marks the log
reported: a failed send exits 1 and keeps the log for the next run. Only a known awake (or off) state reports: asleep or
`unknown`, it prints and keeps everything. A delivered summary is recorded in
`.work/autopilot/summary-delivered.json` before its cleanup, so a
cleanup that fails is finished by the next run, never sent again. A log line that is neither an entry nor a marker makes
the log could-not-tell. A
log that cannot be written never undoes an approval (`warning: sleep log not
written`); a log that is there and cannot be read is said so, never "nothing
to report".

**Sleep (T-0053).** `autopilot.sleep.schedule` names one nightly window for
every day, `HH:MM-HH:MM` in the machine's local time: start inclusive, end
exclusive, and a start later than the end crosses midnight (`22:00-07:00` is
asleep from 22:00 to 06:59). Inside it, a non-null `autopilot.sleep.approval`
or `autopilot.sleep.questions` replaces the day value, so an unattended run
keeps going where the day setting would stop. `autopilot.sleep.deploy`
(L-0654) does the same for `autopilot.deploy`, but only as `nonprod` or
`none`, and asleep an effective `all` reads as `nonprod`: production never
runs unattended asleep, and `deploy_allowed`'s reason names the sleep state
when it changed the answer (`autopilot.deploy=nonprod allows nonProd (asleep
22:00-07:00; day value none)`). The window is re-resolved from
the clock on every policy read, never cached, so a run that crosses 07:00 is
back on the day values at its next decision. A window can be as long as
23h59 (`00:00-23:59`; only start equal to end is refused), and a night
override looser than the day value applies for the whole of it. Anything that
cannot be told — a malformed schedule, `autopilot.sleep` that is not an
object, a clock or resolver that fails — is `unknown`, with a warning naming
the key: per key, the **stricter** of the day value and a valid night
override applies (`human` over `risk` over `self`), so could-not-tell never
loosens a policy and never drops a tightening the owner set (review round 1,
owner decision taken on the recommendation). Each override is read on its
own, and its value rendered bounded in a warning: one that cannot be read at
all counts as `human`, and the other key keeps its own. An `autopilot.sleep`
that is not an object has no night value to read, so both keys read as
`human` (review round 2, owner decision taken on the recommendation). An
override that is readable but not a policy (`"always"`, `true`, `"Human"`)
counts as `human` too, asleep and under `unknown`, rather than keeping the day
value (landing decision, consistent with review round 2's). `settings`' third line ends with `applied=<keys|->` under `unknown`. A key under `autopilot.sleep` this version does not have
(`reviewPolicy`, until T-0029 lands it) is named "not available in this crew
version" and has no effect. An override can lower authority as well as raise
it. Everything else still binds asleep: `scope.allowCliApproval` exactly
`true`, autopilot armed, a readable ledger, every stop. While asleep the
reason of a policy a night override set, and `approve`'s line, end with
`(asleep <window>; day value <day>)`; `approve` makes one decision and its
receipt, its line and `crew_ticket.approve`'s re-check all use it, so a
window edge between the reads cannot split them. **A receipt written asleep stops standing when the window ends**
wherever the day value would not have approved it: `crew_ticket.accepted`
re-asks the policy, so in the morning the ticket reads unaccepted until the
owner types `/crew:approve <id>`; the work done overnight stays. In the same
way a `taken:` line written asleep makes `questions-check` say `valid=0` by
day when the day policy stops. The clock is local time as each process sees
it, so it follows that process's `TZ`: `approve` and `questions-check` run in
the model's shell environment, and a different `TZ` there moves the window.
crew adds no variable or flag of its own that moves the clock. Not in this version: a sleep log, a
`deploy` override (sleep leaves `deploy_allowed` unchanged), and a
machine-global `autopilot.sleep`.

**Manual sleep and wake (L-0652).** `/crew:autopilot sleep` runs
`crew_autopilot.py sleep --root . [--by <text>]` and `/crew:autopilot wake`
runs `crew_autopilot.py wake --root .`. Both keep one file,
`<git-common-dir>/crew/autopilot-sleep.json` (`{"state", "by", "at",
"until"}`, UTC-aware ISO times compared in UTC, written to a temp file and
moved into place with `os.replace`), shared by every worktree of the
repository and never read from a worktree or `.work/`. It is read only when
`lstat` says it is a regular file, opened without following a symlink or
blocking on a FIFO, re-checked with `fstat`, and read up to 64 KiB; anything
else is `unknown` (each layer has its own test). `sleep` checks the record it
is about to write with the same reader and refuses rather than report a sleep
the reader would distrust; an `until` at a wall-clock time a spring-forward
skips resolves forward to the next valid instant.
**Until L-1504, a manual sleep only tightens** (owner decision 2026-10-04,
review B1 of #427): the session can run `crew_autopilot.py sleep` itself
(`scope_guard.py` lets it through and `--by` is free text), so outside the
scheduled window a manual `asleep` applies a night value only where it is
stricter than the day value, per key, like could-not-tell; inside the window
the schedule's own night values stand. L-1504 (harness-only) makes the
approval hook accept only the owner's typed `/crew:autopilot sleep`, and
loosening is unlocked after it lands. A valid record beats the schedule until its `until`,
then the schedule decides again. `sleep` sets `asleep` until the end of the
current window if inside one, else the end of the next window, or for 12 hours
with no schedule; it exits 2 with `refused: ...` and writes nothing unless
`scope.allowCliApproval` is exactly `true`, autopilot is armed, the config and
its `autopilot.sleep` can be read, and the window is open or at least one
`autopilot.sleep` override is stricter than its day value (else it would
change nothing). `wake` never
refuses: inside the window it sets `awake` until the window's end (it never
extends past it); outside, it removes the record and says when the schedule
resumes, or that whether it is asleep cannot be told; with nothing to undo it
prints `already awake`. Fail closed: a record that is unreadable, not an
object, missing a field, with a `state` other than `asleep`/`awake`, an `at`
or `until` that is not a UTC-aware ISO time (an old naive record included), an `at` in the future, or an `until`
more than 24 wall-clock hours (or, as a backstop, 25 real hours, one cycle
across a fall-back) after `at` is `unknown` with a warning naming the file —
per key the stricter of the day value and the night override, never "not
set", so a planted file cannot loosen anything. An expired record is ignored with a warning. A manual `asleep` is
honoured only while `scope.allowCliApproval` is exactly `true` at read time
too (turning it off ends the sleep; until then it reads `unknown`). A manual
`awake` while the window is open keeps any night value stricter than the day
value, so `wake` never loosens a tightening. A policy reason a manual sleep
set ends with `(asleep by hand until <HH:MM>; day value <day>)`.

**The two policies (T-0010).** `autopilot.approval` decides the
plan-approval phase: `human` always stops for `/crew:approve`; `self` lets
`crew_autopilot.py approve --root . --ticket <id>` record the approval at any
risk; `risk` does so only when the spec's header line says `risk: low` (an
absent or unparseable risk is `high`, never `low`). At **every** setting the
approval also needs `scope.allowCliApproval` exactly `true`, autopilot armed,
and a readable review ledger. A NEEDS_REPLAN ledger does not refuse: approving
a different successor plan is the only way out of it, and the ledger still
refuses a plan approved before (`approve` then exits 3 and says so). The
receipt says `approved_via:
"autopilot"` and `approved_by: "autopilot:<policy>"`, and `crew_ticket.accepted`
re-asks the policy on every read: turn the policy to `human`, set
`allowCliApproval` false, or edit the spec, and the scope guard and the
completion audit stop honouring it. The scope guard allows exactly the bare
command `python3 [-B] <path>/crew_autopilot.py approve [--root .] --ticket <ID>`
and only while the policy says yes; `crew_ticket.py approve` stays refused.
`autopilot.questions` decides an open question: autopilot researches it
(crew:explorer for the repo, crew:researcher outside), writes
`.work/tickets/<id>/questions.md` (2-4 options per question, the
recommendation first, each with a `Cost:` line, and a `Research:` line), and
`crew_autopilot.py questions-check` validates it and says `take` or `stop`.
`self` takes the recommendation, `risk` only on `risk: low`, `human` stops; a
`taken: Option <id> by autopilot (<policy>)` line records each one under the
policy that took it. The check refuses a `taken:` line naming a policy that
never takes (only `self` or `risk` does), and any `taken:` line while the
policy in force says `stop`; switching between `self` and `risk` later does
not void an earlier honest record. Every
self-approval and every taken answer is reported by name. Autopilot approves one
ticket at a time: a group approval and its `/crew:approve --confirm` stay the
owner's, and `crew_ticket.approve` refuses an `autopilot` approval carrying a
group's hashes.

**Auto-reject and replan (T-0074).** With `autopilot.maxAutoReplans` at 1 or
more, autopilot armed, and `approval_policy` allowing the successor plan (so
under `risk` only a `risk: low` ticket, which leaves guard and
production-authority tickets to the owner), a final review round that is
FINDINGS with at least one BLOCK and no round left is no longer a stop. `next`
answers `auto-replan` with `crew_autopilot.py auto-reject --root . --ticket <id>`,
which moves the ledger REVIEWED -> NEEDS_REPLAN through `review_ledger.reject`
under the fixed name `autopilot (policy: autopilot.maxAutoReplans)` and prints
every BLOCK and FIX line; `next` then names `/crew:plan` for a successor plan
that quotes each of them, the approve phase approves it under
`autopilot.approval`, and review starts again with fresh rounds. It refuses,
writing nothing, on an INCOMPLETE round, a same-family or unknown reviewer
(`review_ledger`'s own family rule), counts and finding lines that disagree, a
round still left, or anything it cannot tell. The cap counts every successor
plan on the ledger, owner-approved ones included, and is at most `5` (a larger
value reads as `5`, with a warning); at the cap `next` stops with phase
`auto-replan-cap`, naming the cap and each successor plan. The non-stop
`replan` after a reject asks again whether the rejected round is the current
plan's and still passes the round checks above, so the reject name typed by
hand with `review_ledger.py --reject --by` gives the owner's stop, as before.
A BLOCK is never accepted by autopilot at any setting. The recommended value
when you turn it on is `2`.

**The writers.** `crew_autopilot.py` is read-only except `approve` and
`auto-reject`, and L-0652's `sleep` and `wake`, which write or remove only
`<git-common-dir>/crew/autopilot-sleep.json`. `approve` writes only when `autopilot.approval` allows it (a ticket `assign` mints is written by
`crew_ticket.py assign` and `mint`, not by this script; T-0012's `goal-propose`
and `goal-approve` write only the working file `.work/autopilot/<slug>.json`,
never a receipt). `approve` writes exactly what
`crew_ticket.approve` writes for every approval route, all under
`<git-common-dir>/crew/`: `approval.json`; the scope ramp's
`scope-tickets.json` on a ticket's first approval; and, when the review ledger
is NEEDS_REPLAN and the plan is a distinct successor, the ledger itself, moved
NEEDS_REPLAN -> IN_REVIEW (the successor continuation, a fresh review budget).
`auto-reject` writes only the review ledger, REVIEWED -> NEEDS_REPLAN.
`next`, `resume`, `settings`, `stops`, `route`, `status`, `questions-check`,
T-0072's `deploy-allowed` and T-0011's `ship` write nothing (`ship` acts outside
the checkout instead: a push, a PR and at most one merge commit), and T-0018's `route` and `status` read no policy of their own:
`status`'s lines, the approve and open-questions reasons included, read the
same under every setting, and at the approve phase it names
`/crew:approve <id>`; `next` is what names the policy's route. A policy value
that is not a policy (`approval: "bogus"`) is warned about by `settings`
(`policyWarnings`), never by `status` (T-0027); `status` keeps every other
warning, the could-not-tell one for an unreadable config included. `approve`
under such an unreadable config refuses naming that cause, not "autopilot.mode is
not plan". The one policy
effect `status` shows is `crew_ticket.accepted`'s: an `autopilot` receipt
stands only while the policy still allows it.

**When `ship: merge` merges.** Every required check (`gh pr checks <n>
--required`) reads `pass`; a `fail` always stops it, because no check is excused by name.
Pending, or no required check reported yet, waits up to 60 minutes (a fixed
value) and then stops; `skipping`, an unknown state, an unlisted failure or checks that
could not be read stop at once. A `high`-risk ticket - or one whose spec header
names no risk, which reads as `high` - never merges when every completed review
round's `model_family` is `claude` or absent: an unrecorded family counts as the
author's. **Codex, the only cross-family reviewer here, was out until
2026-10-01; while it is unavailable every review is same-family, so every
`high`-risk ticket stops at `ship: merge` with its PR open for a person to
merge.** `ship` refuses a working tree that differs from HEAD (tracked or
untracked, ignored files aside) before the push and again before the merge: a
receipt can cover edits a push does not carry. It takes HEAD once, right after
the push; the PR's head and this checkout's HEAD must still be that commit
before and after every poll and right before the merge. A merge also needs the
review receipt to still stand after the wait, on the same ledger bytes the
review families came from (a ledger replaced after the last poll stops), and a
base branch with no merge queue (a queue picks its own merge method, which may squash, and keeps
merging after `ship` stops; a queue state that cannot be read stops too). The
merge is bound with `--match-head-commit <HEAD>`, so a push after the last read
is refused by GitHub, not merged; if gh queues the PR anyway, `ship` dequeues
it once (GraphQL `dequeuePullRequest`, the only mutation it sends) and stops.
Check names and states are read verbatim, and a `gh pr checks` row that is not exactly five
tab-separated fields is unreadable: gh prints a check's name and description
unescaped, so one holding a tab never ships unattended. The settings, the
risk and the review families are re-read on every poll, and a green that lands
after the 60 minutes stops like a pending one. Unarmed, a ticket
`/crew:done` closed reads `closed` and nothing is pushed.

**What arming it does not change.** Review acceptance and brainstorm always
stop for a person, at every setting — accepting review FINDINGS with any
BLOCK (`review_ledger.py --accept`) is never automatic; the one exception is
not a setting either: a final 0-BLOCK round from a Codex or Kimi reviewer (never a
same-family Claude-fallback round, never a verdict recovered from stray lines) is accepted by the ledger-guarded
`review_ledger.py --auto-accept` (L-0510), and no config key changes that; every
`AUTONOMOUS_STOPS` id (see "pm.authority") binds it; no hook, review budget or completion
audit is relaxed. `pm.authority: autonomous` from 0.20 arms nothing —
`/crew:migrate` keeps it under `retired.pm` and its note points here.

**Production without asking (T-0072).** `autopilot.deploy` says where a deploy
may run with no person asked: `none` (the default) nowhere, `nonprod` in a
`nonProd` environment only, `all` in production too. Production needs **two
opt-ins**: `autopilot.deploy: all` in the repo's `.crew/config.json`, **and**
`environments.prodUnattended: true` in **both** config layers (see "guards", the
ratchet: a repo cannot grant it alone, and neither can the machine file). It
also needs `guards.overrides.cloudGuard` to resolve to a plain `block`, so T-0009's guard
is armed to enforce the dispatch. `crew_autopilot.deploy_allowed(root, env,
class)` answers, first match wins:

| Condition | Verdict |
|---|---|
| the checkout cannot be found (the lookup raised), `.crew/incident.json` exists in any form, or its path cannot be checked for any reason | `refuse` — an emergency may be active |
| the environment name is blank, not a string, or not printable | `ask` — could not tell which environment |
| the class is not exactly `nonProd` or `prod` (T-0005's classes; `unknown` included) | `ask` — crew could not classify it |
| either config layer could not be checked (its path cannot be stat'ed for any reason but a missing file), or is present and not ok (unreadable, not JSON, a bad `guards` or `environments` block) | `ask` — could not read that layer |
| `autopilot.mode` is not `plan`, or `autopilot.deploy` is `none` | `ask` |
| `nonProd`, with `nonprod` or `all` | `allow` |
| `prod`, with `nonprod` | `ask` |
| `prod`, with `all`, and `prodUnattended` not `true` in both layers | `ask`, naming the layer |
| `prod`, with `all`, and `guards.overrides.cloudGuard` not a plain `block` (a fail-closed `block` with a note included) | `ask` |
| `prod`, with `all`, otherwise | `allow` |

The checkout root is resolved **once** per answer, and that one root is what
the incident check, both layers and every row judge; the result names it
(`root`). Every path is probed for present, absent or could-not-tell, and
could-not-tell never reads as absent: it refuses for the incident file and
asks for a config layer. A crash inside the decision asks, and so does one
building its report or printing a value it was handed; the CLI prints
`verdict=ask` even for a crash it cannot describe. The incident check runs
before anything that can fail to import, so a crash never turns an
emergency's `refuse` into `ask`. Every production decision — `allow`, `ask`
or `refuse` — carries a report line naming the environment
(`unattended production: <env> <verdict> - <reason>`). The CLI is
`crew_autopilot.py deploy-allowed --root . --env <name> --class <class>
[--json]`: the verdict line (or one line of JSON) on stdout, the report on
stderr, exit 0. Each is one line, the verdict first: a value that is not plain
printable text (a class or environment holding whitespace included) prints as
its repr, so no input can add a line a consumer would read as a second verdict.

**The deploy phase (L-0649).** With `autopilot.deploy` `nonprod` or `all`,
once the ship phase reports the ticket's PR merged at this HEAD, `next`
answers `phase=deploy command=/crew:promote <env>` for the first environment
in `.crew/verify.json` with a `github` entry (file order, nonProd before
prod) that has no PROMOTIONS row for the sha, after calling `deploy_allowed`
with T-0009's class for the entry's dispatch and proceeding only on the exact
verdict `allow` (every non-empty report is printed in the reason). It stops
with **`deploy-target`** when the target cannot be told or is not safe to
drive — the map unreadable, an entry `crew_ghdeploy.py check` refuses,
`requireHuman`, no `shaInput`, a class unknown or mismatched, any verdict but
`allow` — and with **`failed-deploy`** when the target's newest row for the
sha is not all-pass (it never re-deploys). With every target all-pass, or no
`github` environment (promotion is then a person's), it is `closed`. `next`
stays read-only: no `gh`, no `crew_ghdeploy.py` subcommand. `allow` is necessary, not sufficient: T-0009's hook,
promote-gate (`requireHuman`, the post-deploy proof) and every other gate
still decide.

### Inert settings (T-0070)

A setting the installed crew does not act on is **named, never silently
ignored**. `.crew/config.json` once held `autopilot.approval: self` for days
before the crew that reads it (T-0010) existed, and nothing said so.
`crew_config.inert_settings` applies one rule: a resolved key that is not a
key of `default_config()` is inert — outside `platform.*` (machine facts
`platform-sync` stamps) and `schema`, and a key under an open table such as
`dev.roles` counts as known. A small `INERT_PENDING` table adds the ticket
that brings each known-but-unbuilt key, and the values that do nothing yet.
It is empty in this crew: T-0029 (`reviewPolicy`, `maxLanes` under `autopilot`),
L-0649 (`deploy: "nonprod"` or `"all"`) and L-0541 (`maxTicketsPerRun`, and
`mode: "backlog"`) each removed their rows when they landed.

Any other unknown key is named `(unknown key)`: a typo, or a key from another
crew version. A path the global filter drops from the machine file (this crew
does not read it there, so it takes effect nowhere) is named
`(global, not read)`. An entry leaves the table when its key enters
`default_config()`, which the landing ticket does; a value-level row is deleted
by that ticket.

The same list appears in four places: one `Inert settings (crew <version> does
not act on them): key=value (ticket), ...` line at SessionStart (capped at 300
characters with `+N more`), an `inert`
line in `/crew:status`, a `warning: inert:` line per `autopilot.*` key from
`crew_autopilot.py settings`, and `crew_config.py --inert`. It never refuses
anything: autopilot still runs with an inert key set.


---

## Personal keys and the per-key ratchet (T-0050)

`crew_guards.PERSONAL_KEYS` (re-exported by `crew_state`) names the keys the
owner sets once, in `~/.claude/crew/config.json`, as a default for every repo:

| Key | Kind | Order, strictest first |
|---|---|---|
| `autopilot.mode` | tiers | `off`, `plan` |
| `autopilot.maxPhases` | int-min | a smaller positive int is stricter |
| `autopilot.deploy` | tiers | `none`, `nonprod`, `all` |
| `autopilot.approval` | tiers | `human`, `risk`, `self` |
| `autopilot.questions` | tiers | `human`, `risk`, `self` |

The rule, `crew_guards.effective_personal`, applied by `resolve_config` after
its merge (so every reader, `crew_autopilot.settings` included, sees it):

- A layer **sets** a key when its value is neither absent nor `null`. A silent
  layer imposes nothing: a global `self` over a repo that says nothing is
  `self`. This is where it differs from the guard ratchet, whose absent value
  is the floor and could never carry a personal default.
- Both set it: the **stricter** wins, the repo's value on a tie, and
  `--explain` names the layer `held down by`. An unrecognised value ranks
  below the floor, wins, and is returned raw; the reader reads it as its floor
  with a warning. int-min ignores an invalid layer when the other is valid.
- No key is in both `PERSONAL_KEYS` and `RATCHETED_KEYS`. Every
  `crew_state.AUTOPILOT_DEFAULTS` key is a row or is listed in
  `REPO_ONLY_AUTOPILOT`, and a test fails until a new key picks one.
  `autopilot.maxAutoReplans` (T-0074), the `autopilot.sleep` block (T-0053)
  and T-0011's `autopilot.ship` are `REPO_ONLY_AUTOPILOT`: they read from
  `.crew/config.json` alone, and the machine file's copy is pruned.
- `scope.allowCliApproval` is **not** personal yet: its reader,
  `crew_ticket.cli_approval_allowed`, reads the repo file only and is review
  harness, so its row lands in a harness-only change. So a global
  `approval: self` still needs the repo's own `allowCliApproval: true`.

Neither template spells a personal key (`template_config()`,
`global_template_config()`), and `heal_config` writes the template, so a
default never shadows the owner's choice. A repo file written before T-0050
spells `autopilot.mode: "off"`, the strictest tier: `--explain --all` reports
each such key as a `shadow:` and `--unset <path> --repo --apply` removes it.
Nothing removes one automatically, because a deliberate repo value looks the
same.

## Backups, the profile and rebuild (T-0050)

**Backups.** Every crew writer of either config file calls
`crew_backup.backup(path)` immediately before it replaces the file:
`write_global_config`, `write_repo_config` (so every `--set`/`--unset` and the
menu's Save), the rebuild and restore below, the menu's restore,
`heal_config`, platform-sync's `apply_changes`, the autoclear setup's repo
writes and `crew_upgrade`. The raw bytes, corrupt ones included, go to
`~/.claude/crew/backups/global/<stamp>.json` or
`backups/repo/<dir>-<sha256(realpath)[:10]>/<stamp>.json` (a `source` file
names the path), 0600 files in 0700 directories, the newest 20 per file kept.
A stamp is UTC `YYYYMMDDTHHMMSSZ`, `-2`, `-3` on a same-second collision. **A
failed backup refuses the write and leaves the file untouched** (exit 4 from
the CLI). `CREW_BACKUP_DIR` overrides the root; the test suite sets it. A hand
edit is not backed up.

**The profile.** `~/.claude/crew/profile.json`, and a copy at
`<memory.vaultPath>/crew/profile.json` when the global `memory.vaultPath`
names an existing directory. It holds, per layer, every leaf that differs from
that layer's template (never `schema` or `platform.*`; unknown keys kept),
repos keyed by normalised `origin` URL or `path:<main worktree>`. Refreshed by
`--set`/`--unset --apply` and the menu's Save, captured by
`--save-profile --apply`; never written by heal, platform-sync, upgrade, the
autoclear setup, a rebuild or a restore.

**Rebuild and restore.** `--rebuild --repo|--global` writes the template plus
the profile's values (a readable repo file's `platform` block is kept). Both
copies readable and different: the newer `saved_at`, named in the dry run. One
unreadable: the other, said so. Present but unreadable with no readable
other: exit 3, could not tell. None: refused without `--no-profile`.
`--restore <stamp>` backs up the current file, then writes the stamped bytes;
an unknown stamp exits 2. Both are dry runs until `--apply`.

## `route` - plain-text command routing, off until `true`

`route.enabled` (T-0023, since 1.0.46) lets a short plain-text prompt reach a
lifecycle command or, since 1.0.345, a `/crew:autopilot` subcommand. When it is on, crew's UserPromptSubmit context hook
(`crew_context.route_item`) calls `crew_route.decide` on the prompt and, unless
the answer is `none`, puts one line FIRST in the turn's context: the
`/crew:<command> <ticket>` whose procedure Claude should run through the Skill
tool, or a request to ask the user which ticket. The hook runs nothing and
blocks nothing; the command's own checks still decide. The table of phrases,
the three outcomes and what never routes are in the plugin README's
"Plain-text lifecycle" section; `crew_route.PHRASES` is the single definition.
Since 1.0.345 (T-0057) the table also names five `/crew:autopilot` phrases
(status, assign, goal, goal resume, focus); this same key arms them, and one
whose subcommand has not landed gets a line that runs nothing.

| Key | Default | Read by | What an unexpected value does |
|---|---|---|---|
| `route.enabled` | `false` | `crew_route.settings`, through `crew_config.resolve_config` | Only the JSON value `true` arms it. `"true"`, `1`, `"yes"`, `"on"` — anything else — reads as off, and `settings` names the value it saw. A `route` that is not an object, in either file, is ignored by the merge and reported. |

**Which file.** `.crew/config.json` over the machine-global
`~/.claude/crew/config.json` over the default — `resolve_config`'s ordinary
precedence. A `route` block found only in `.crew/crew.json` is reported by
`python3 crew_route.py settings --root .` ("move it to .crew/config.json")
rather than read as off with no word.

**A machine-wide `true` reaches only repos whose file leaves the key out.**
`/crew:init` writes the whole template, which carries `"route": {"enabled":
false}`, and the repo layer wins. In a repo set up that way, delete the key
from `.crew/config.json` or set it `true` there.

**What arming it does not change.** Routing never approves: no phrase routes
to `/crew:approve`, a `continue` whose next step is approval asks instead, and
`commands/approve.md` sets `disable-model-invocation: true` besides. Under
`--harness codex` no line is emitted, because the Skill tool it names does not
exist there.


---

## `git.forbiddenTrailers` - commit trailers the owner forbids

`git.forbiddenTrailers` (T-0066, since 1.0.328) is a list of commit trailer
tokens, such as `["Co-Authored-By"]`, that the owner does not want on any commit
crew's sessions make. crew takes no side on attribution: the owner's own
instructions (CLAUDE.md, memory) decide, crew never adds a trailer, and a
harness reminder asking for one does not override them. This key states the
owner's answer mechanically. The list is the switch: `[]`, the default in both
layers, means nothing is forbidden.

| Key | Default | Read by | What an unexpected value does |
|---|---|---|---|
| `git.forbiddenTrailers` | `[]` | `crew_trailers.forbidden` | A value that is not a list of tokens (letters, digits and `-`, no `:`), a `git` that is not an object, or a config file `crew_config.layer_state` calls corrupt is **unknown**, never `[]`: `/crew:done` prints `trailers: unknown - <why>`. |

**Union, not precedence.** Both layers are read raw and their lists are
combined, case-insensitively and without duplicates. A repo can add a token and
can never remove the machine owner's: a cloned repo carrying `[]` must not
silently disarm the owner, which ordinary precedence would let it do (the same
reason the ratchet exists, see "install.policy"). The repo layer is the `.crew/config.json` in force:
a linked worktree with none of its own reads the main checkout's, and when that
cannot be told, the list is unknown.

**What reads it.** `/crew:done` runs
`crew_trailers.py --check --root . --ticket <id>` over the ticket's own commits
(`git log --first-parent <scope base>..HEAD`) and prints
`trailers: clean (<n> commits)`, one `trailers: FINDING <sha7> <Token>` per
offending commit, or `trailers: unknown - <why>` (no base, git failed, config
unreadable, or any unexpected error, printed as `<Type>: <message>`), exiting
0 / 1 / 2. `--first-parent` is a deliberate refinement of the spec's literal
`<scope base>..HEAD`: a ticket branch merges origin/main, and the plain range
would then report every commit that merge brought in (other people's, many
carrying the trailer). Following first parents keeps the ticket's own commits,
including a merge commit made on the ticket branch, and leaves out what it
merged in. The limit: a ticket commit that reaches HEAD only as a merge's second
parent (a side branch merged in with `--no-ff`) is not read; crew never makes
that shape, so check such a branch by hand. It is a report: it never refuses done and crew never rewrites the
commits, because a rewrite is the owner's decision and stales the review
receipt. A line derived from a fallback scope base says so.

**The textual rule.** A message matches when it contains
`<Token>` followed by optional spaces and `:` or `=`, case-insensitively (git
treats trailer keys that way). So prose saying "no Co-Authored-By trailers"
passes, and prose "Co-Authored-By: lines" is matched — conservative on purpose.

**Refusing at commit time** is the scope guard's half of T-0066. It touches
review/gate harness paths (`HARNESS` in `scripts/check-tooling-pr.py`), so it
lands in its own change; until then this key is reported, not enforced.

**Setting it machine-wide:**

```bash
python3 plugin/crew/hooks/scripts/crew_config.py --set 'git.forbiddenTrailers=["Co-Authored-By"]' --apply
```


---

## The no-python fallback in cloud-guard.sh and env-guard.sh

Both hooks normally resolve their guard through `crew_config.py --guard`, which needs python. When python cannot run at all, `cloud-guard.sh` and `env-guard.sh` fall back to a shell check of the config files, `crew_guard_layer_armed` in `hooks/scripts/_common.sh`. The fallback used to take the first textual match of the guard key and read a missing token as "off". That let a legacy key saying `off` win over an override saying `block`, and it let a file the shell could not make sense of count as unarmed.

The rule now is that a layer counts as **unarmed only when off can be proved**, and every doubt answers "armed". Off is proved only when all of these hold:

- the file does not exist (a file that exists but is not a readable regular file is armed);
- it reads, and its last non-blank character is the closing brace;
- it holds no `\u` escape, because a JSON escape can spell either key without the literal token (`profile`);
- every `"guards"` token is followed by an opening brace, so `{"guards":null}` and `{"guards":42}` are armed, as the python resolvers already treat a non-object block as corrupt;
- every `"profile"` token and every token of the guard's own key has the literal value `off`, and the number of values extracted equals the number of tokens found. A value split over two lines extracts nothing, so it is armed.

An unrelated `"profile"` key, for example `unattendedCloud.aws.readOnly.profile`, arms the layer: that is a refusal while python is missing, never a pass. The launchers `crew-hook.sh` and `crew-hook.ps1` carry no guard-key check, only a config-file presence check, and are unchanged.

## Removed keys and migration

Sixty keys were removed from the settings surface. Two, `tier` and `roles`, were retired because they were read only for display. The other 58 never changed behaviour from a config in any measured layer, so each is now a constant in `crew_state` at the default it held. `plugin/crew/hooks/scripts/crew_dropped.py` (`DROPPED`) is the single table: each removed key, the default it held and the constant that replaced it. Nothing else lists them, and this file does not repeat the list.

A key that narrows a safety decision when set was not removed at all. A key with a measured non-default value in a real configuration stayed.

What a person with an old config sees:

- `/crew:migrate` removes a removed key that holds its default value, and moves the repo `schema` from 7 to 8. A schema-7 repo reads `upgradeNeeded` until it runs.
- The machine file has its own path: `crew_migrate.py --global` (preview, apply and rollback).
- Migration **refuses**, writing nothing, while a removed key holds a non-default value. The refusal names each key and what its constant now is. The person removes the key, or passes `--accept-dropped <key>` for it, so no restriction disappears without someone saying so.
- A config that still carries a removed key after migration keeps working, and `crew_config.py --check` (and the SessionStart inert-settings line) names it as inert: the value has no effect and the message says which constant replaced it. See "Inert settings".
- No unknown key is deleted by migration. Keys crew has never heard of are carried untouched and reported.
- The twelve per-guard keys are not in `crew_dropped.py`: they are collapsed into `guards.profile` and `guards.overrides`, and migration writes that form. Until a layer is migrated its old keys are still read; see "guards".

## Removed keys: the measured basis, per key

Measured on 2026-10-18 and 2026-10-21 (224 and 185 `.crew/config.json` inputs on the build host, 221 and 181 readable, plus the owner's machine file; win-repo-2 ran the same probe on its two layers): none of the 58 keys below was ever set to anything but its default in any layer, and `tier` and `roles` were read only for display. Each is now a constant in `crew_state` at its old default (`crew_dropped.DROPPED` pairs key and constant).

Seven of them used to restrict something or arm a gate, and are marked below. They are not exempt: `/crew:migrate` refuses to drop one holding a non-default value until the person deletes it or passes `--accept-dropped <key>`, and until migration runs the inert-setting line names the key and says "the restriction it set is gone". Between installing this version and running `/crew:migrate`, a config holding such a value is already ignored by the readers; no measured config held one.

| Key | Old default | What a non-default value did | Restriction lost? |
|---|---|---|---|
| `tier` | `0` | display only | no |
| `roles` | `['explorer', 'reviewer']` | display only | no |
| `autopilot.ciTimeoutMinutes` | `60` | how long ship waits for CI before stopping | no |
| `autopilot.knownFailures` | `[]` | check names a merge may ignore (a widening; dropping it is the safe direction) | no |
| `autopilot.sleep.notifyHold` | `None` | held night pings until morning | no |
| `bitbucket.mergeGate.enabled` | `False` | armed the Bitbucket merge gate in /crew:promote | **yes** |
| `bitbucket.mergeGate.branch` | `None` | branch the gate watched | no |
| `bitbucket.mergeGate.preset` | `'standard'` | bound to nothing | no |
| `github.mergeGate.enabled` | `False` | armed the GitHub merge gate in /crew:promote | **yes** |
| `github.mergeGate.branch` | `None` | branch the gate watched | no |
| `change.requester` | `None` | default answer in /crew:change | no |
| `change.implementor` | `None` | default answer in /crew:change | no |
| `change.sdpTemplate` | `'Change Management Request'` | SDP template name | no |
| `change.jiraIssueType` | `'Change'` | Jira issue type | no |
| `change.category` | `None` | default answer in /crew:change | no |
| `context.autoClear.windowTitle` | `None` | extra window-title match for the auto-clear target (widened matching) | no |
| `context.autoClear.command` | `'/clear'` | text typed to clear | no |
| `context.autoClear.unsafeFocus` | `False` | accepted typing into an unconfirmed window (a widening) | no |
| `context.autoWrapUp` | `True` | turned the wrap-up instruction off | no |
| `context.autoResume` | `True` | never read | no |
| `context.budgetTokens` | `None` | pinned the context budget | no |
| `context.handoffPath` | `'.work/HANDOFF.md'` | where the handoff note lives | no |
| `context.keepTranscripts` | `5` | how many transcripts to keep | no |
| `context.staleHandoff.maxAgeHours` | `72` | when a handoff counts as stale | no |
| `context.staleHandoff.maxCommitsBehind` | `3` | when a handoff counts as stale | no |
| `docs.theme` | `None` | brand passed to doc-builder | no |
| `docs.reportTheme` | `None` | brand for reports | no |
| `emergency.ttlMinutes` | `120` | length of a declared emergency stand-down (a shorter value was a narrowing) | **yes** |
| `graph.enabled` | `True` | never read by code | no |
| `graph.tool` | `'graphify'` | never read by code | no |
| `graph.mode` | `'code-only'` | never read by code | no |
| `graph.commitHook` | `False` | never read by code | no |
| `memory.inject` | `True` | false stopped vault injection into the session (a narrowing) | **yes** |
| `memory.recall.vaults` | `[]` | restricted which vaults were recalled (a narrowing) | **yes** |
| `memory.recall.maxChars` | `800` | capped recalled text (a narrowing) | **yes** |
| `memory.recall.projects` | `[]` | restricted which projects were recalled (a narrowing) | **yes** |
| `notify.urlEnv` | `None` | armed webhook delivery (a feature, not a restriction) | no |
| `notify.questionTypes` | `None` | which question types ping | no |
| `notify.realertHours` | `6` | dedupe window for repeat pings | no |
| `obsidian.board` | `'Board.md'` | board file name | no |
| `obsidian.columns.backlog` | `'Backlog'` | lane name | no |
| `obsidian.columns.ready` | `'Ready'` | lane name | no |
| `obsidian.columns.inProgress` | `'In Progress'` | lane name | no |
| `obsidian.columns.review` | `'Review'` | lane name | no |
| `obsidian.columns.done` | `'Done'` | lane name | no |
| `pm.enabled` | `True` | turned the PM report off | no |
| `pm.mode` | `'adaptive'` | PM report mode | no |
| `pm.quietLines` | `8` | PM report length | no |
| `pm.maxLines` | `40` | PM report length | no |
| `pm.ticketGranularity` | `'system'` | how many tickets a session becomes | no |
| `resume.typeDelaySeconds` | `2` | delay before typing the resume command | no |
| `resume.readyTimeoutSeconds` | `15` | cap on the ready probe | no |
| `sdp.portal` | `None` | which SDP portal | no |
| `sdp.noteVisibility` | `'private'` | private or public notes | no |
| `sdp.closeOnDone` | `False` | close the request on done | no |
| `secondOpinion.keyEnv` | `'GEMINI_API_KEY'` | env var holding the key | no |
| `secondOpinion.sendsCode` | `False` | true allowed sending code to the second opinion (a widening) | no |
| `shellRoute.mode` | `None` | forced a shell | no |
| `shellRoute.distro` | `None` | pinned a WSL distro | no |
| `worktree.root` | `None` | where worktrees are created | no |
