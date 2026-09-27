anchor: useful-claude-add-ons@05cf5bc9
verified: 2026-09-27

## Re-derive provenance

Full re-derivation, not a re-point. The previous anchor (`5d1fc5fd`) predates
crew 1.0 (`6c497a14`, PR #225): a per-path check against `6c497a14` found 37 of
the old note's 44 cited, still-existing paths changed and 9 cited paths gone
entirely (`pm_brief.py`, `pm-pulse.sh`, `pm-brief.sh`, `agents/pm.md`, and the
54-agent roster files among them), so re-pointing would have produced correct
line numbers describing a crew that no longer exists. Read in full this pass:
`plugin/crew/hooks/hooks.json`, `_common.sh`, `role_write_guard.py`,
`role-write-guard.sh`, `auto-clear.sh`, `crew_autoclear_setup.py`,
`crew_state.py`'s roster/config block (:986-1353), `crew_guards.py`'s guard
vocabulary block (:91-537), `crew_context.py`, `event_claim.py`'s module
docstring, and the four agent files. Read in part (specific functions/ranges
only, cited in place below): `crew_config.py`, `crew_endpoints.py`,
`context-watch.sh`, `verify-gate.sh`, `crew_migrate.py`, `crew_status.py`,
`crew_metrics.py`, `crew_ticket.py`, `crew_recall.py`, `TODO.md`. Not read:
agent/command prose beyond their frontmatter and the sections cited below;
`review_ledger.py`, `review_patch.py`, `review_prompt.py`, `review_run.py`,
`review_verdict.py`; `webtest_guard.py`, `webtest_rules.py`,
`webtest_scaffold.py`; `crew_change.py`, `crew_incident.py`,
`crew_platform.py`; any `.ps1` file's body past its `Resolve-CrewPython`
definition; any test file's contents (existence and size only).
Re-verified per-path from `f2bb919b` to `adf8d1dd` for T-0008, and from
`adf8d1dd` to `8d447a7d` for its review round 3; see the last two sections.

# crew

The `crew` plugin: a small, honest virtual dev team for one interactive
session at a time — one Claude session owns a ticket from brainstorm through
done, dispatching four read-only subagents and calling on-demand `stack-*`
skills, gated by deterministic hooks. Registered in
`.claude-plugin/marketplace.json` like every other entry here.

## Inventory

Counted by walking the directories at this anchor:

| | Count | How counted |
|---|---|---|
| Agents | 4 | `.md` files in `plugin/crew/agents/` — `explorer.md`, `researcher.md`, `reviewer.md`, `security.md` |
| Commands | 34 | `.md` files in `plugin/crew/commands/` |
| Skills | 29 | subdirectories of `plugin/crew/skills/` (includes 8 `stack-*` skills) |

`.claude-plugin/marketplace.json:217` states the identical three numbers (4
agents, 34 commands, 29 skills) in its `crew` entry's description, so this
site is current — this pass did not re-run the previous note's wider
count-disagreement sweep across `README.md`/`plugin/README.md`/
`INSTALLATION.md`/the install scripts; see "Unverified at this anchor".

## The roster, replaced wholesale

Crew 0.x shipped 54 agents (13 tiered roles + 40 specialists) plus a standing
`pm` agent that dispatched them. Crew 1.0 (`docs/review/04-redesign.md`,
"Roster: 54 agents -> 4", cited in comment at
`plugin/crew/hooks/scripts/crew_state.py:1219-1224`) replaces that with:

- **Four read-only subagents on a tier ladder**, `ROLE_TIERS`
  (`plugin/crew/hooks/scripts/crew_state.py:1228-1233`): `explorer` and
  `reviewer` at tier 0, `security` at tier 1, `researcher` at tier 2. None of
  the four grants `Write` or `Edit` — confirmed by reading each agent file's
  frontmatter (`explorer.md`, `researcher.md`, `reviewer.md`, `security.md`,
  all `tools: Read, Grep, Glob, Bash, Skill`).
- **No specialist roles.** `SPECIALIST_ROLES` is now `frozenset()`
  (`plugin/crew/hooks/scripts/crew_state.py:1243`) — domain knowledge that
  used to be a specialist agent now lives in the on-demand `stack-*` skills
  (`stack-angular`, `stack-bash`, `stack-dotnet`, `stack-powershell`,
  `stack-python`, `stack-sql`, `stack-terraform`, `stack-web`), which are
  never dispatched as a role.
- **No standing PM agent file.** `plugin/crew/agents/pm.md` does not exist at
  this anchor (`find . -iname pm.md` returns nothing). The interactive session
  itself is the "unnamed PM": it implements, dispatches the four subagents,
  and is never itself given an `agent_type`. `PM_DEFAULTS`
  (`plugin/crew/hooks/scripts/crew_state.py:1082-1095`) and `pm.authority`
  (`AUTHORITY_DEFAULT = "report-only"`, `:1052`; three values —
  `report-only`/`act`/`autonomous`, `normalise_authority` at `:1275-1286`)
  still exist as config that governs how far that unnamed session may act
  without asking, and `AUTONOMOUS_STOPS`
  (`plugin/crew/hooks/scripts/crew_state.py:1065-1072`) still names the four
  things even `autonomous` may not do unasked (`offboard-role`, `delete-map`,
  `rewrite-metrics`, `git-destruction`).
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:1246-1255`) still
  distinguishes a deliberately-onboarded off-ladder role from a typo, even
  though `SPECIALIST_ROLES` is empty today.

**DERIVED, and worth flagging as a candidate stale-code finding, not just a
roster fact.** `role_write_guard.py` — the `PreToolUse` `Write|Edit` guard —
still carries PM-specific logic and a docstring that names removed roles:

- `_DENY_ROLES` (`plugin/crew/hooks/scripts/role_write_guard.py:230-235`) is
  exactly the four shipped agents (`explorer`, `researcher`, `reviewer`,
  `security`) — consistent with the roster above, each denied any write
  because none grants `Write`/`Edit` in its `tools:` line.
- `_UNRESTRICTED_ROLES` is `frozenset()` (`:241`) — empty since crew 1.0,
  because no shipped agent writes.
- `_PM_ROLE = "pm"` (`:243`) and `_PM_ALLOWED_PATTERNS` (`:250-259`,
  `.crew/**`, `TODO.md`, `.work/**`, `docs/diagrams/**`) are still live code,
  and `classify` (`:539-592`) still special-cases `role == "pm"` at `:582-589`
  — but nothing in this checkout ever sets `agent_type` to `"pm"` any more:
  the unnamed interactive session sends no `agent_type` at all, and
  `classify`'s own first branch, `if role is None: return True, "no-agent-type"`
  (`:572-573`), is what actually governs it — unconditionally allowed,
  never reaching the `pm`-scoped branch. The module's own docstring at
  `:62-63` still reads "`crew`'s own agents are registered as `crew:pm`,
  `crew:analyst`, etc." — both names are agents this release does not ship.
  This is either intentional back-compat (an external caller or a
  hand-typed `agent_type` could still say `pm`) or dead code the 1.0 cutover
  missed; the code does not say which, and this note does not guess. **A
  decision for scribe to record, not this note to file**, since it is a
  judgement about intent this note cannot settle by reading further.
- `plugin/crew/evals/` carries the same signal at the directory-name level:
  `pm-answers-status-mid-pass/`, `pm-does-not-write-code/` and
  `qa-reviewer-stays-read-only/` are eval fixtures named after roles this
  release does not ship (`pm`, `qa-reviewer` — `reviewer` is the 1.0 name).
  Confirmed present with `case.yaml`/`prompt.md`/`graders/` each, **not read
  for content**; whether they were updated to target `reviewer` internally
  or are simply unmigrated fixtures is unverified at this anchor.

## Lifecycle commands

Crew 1.0's lifecycle is `brainstorm -> spec -> plan -> approve -> implement ->
review -> done`, one command per phase (`/crew:fix` is the same phases, each
compressed to one step, `plugin/crew/commands/fix.md:2`). `docs/diagrams/process-crew-lifecycle.mmd`
draws it:

| Command | Does | Replaces |
|---|---|---|
| `/crew:brainstorm` (`plugin/crew/commands/brainstorm.md`) | Mints a ticket and settles an approved direction; loads `crew-brainstorm` (method adapted from `superpowers:brainstorming`, notice in `plugin/crew/NOTICE.md`) | new in 1.0 |
| `/crew:spec` (`plugin/crew/commands/spec.md:7-8`) | Fills the ticket contract (Intent/Exclusions/Evidence/Unknowns/Touch/Acceptance checks) from an approved direction; Touch is one path or glob per bullet, because `/crew:approve` reads it a bullet at a time (`:38-43`, since crew 1.0.27) | `/crew:ticket` |
| `/crew:plan` (`plugin/crew/commands/plan.md:8-9`) | Turns an approved spec into a step plan; the old standalone second-opinion step is now step 3, optional, inside this phase | redefined |
| `/crew:approve` (`plugin/crew/commands/approve.md:5`, `disable-model-invocation: true`) | Typed by the user only: the UserPromptSubmit `approval-hook` records `<git-common-dir>/crew/tickets/<id>/approval.json`, bound to the sha256 of `spec.md` and `plan.md` (`:7-16`); the command body only relays the result | new in 1.0 |
| `/crew:implement` (`plugin/crew/commands/implement.md:8-9`) | Implements an approved plan, then tests/docs/review; loads `crew-execute` (adapted from `superpowers:executing-plans`) | `/crew:work` |
| `/crew:review` (`plugin/crew/commands/review.md`) | Independent QA review of the working diff (Codex, Copilot, or the `crew:reviewer` Claude fallback) | (unchanged name; internals rewritten) |
| `/crew:done` (`plugin/crew/commands/done.md:7-8`) | Closes a ticket; four checks (review receipt, clean verify gate, passing completion audit, current artifacts), any one failing refuses the close, no partial close. Check 4 (`:46-57`, since crew 1.0.36) runs `crew_refresh_check.py` and refuses on any `stale` or `unknown` line **without refreshing** - a write there would stale check 1's receipt (`:52-55`) | new in 1.0 |

`/crew:ticket` and `/crew:work` are now **removal stubs with no behaviour**
(`plugin/crew/commands/ticket.md`, `plugin/crew/commands/work.md`, each a
`Read`-only, no-op command that tells the user the lifecycle name and stops)
— confirmed by reading both files in full, not merely their frontmatter.

`review.md` dispatches `crew:reviewer` at this anchor
(`plugin/crew/commands/review.md:449,464`), **not** the pre-1.0
`qa-reviewer` — `TODO.md`'s "T2 (lane D) deferred items" entry recorded this
as an open item ("`review.md` still dispatches `qa-reviewer`; switch to
`reviewer` in T4") but the code at `6c497a14` shows it already done; a
`grep -rl qa-reviewer` across commands/agents/hooks at this anchor returns
only `reviewer.md` itself (naming its own predecessor in prose) and
`crew_migrate.py` (translating an old config's role name during migration).

## Hooks

`plugin/crew/hooks/hooks.json` registers **eight** events and **34** hook
entries across **13** distinct scripts (26 files, one `.sh` + one `.ps1`
each — every bash `command` has a `shell: "powershell"` sibling on the same
event, per CLAUDE.md's Windows rule), re-derived by parsing the JSON:

| Event | Entries | Line | Scripts |
|---|---|---|---|
| `SessionStart` | 6 | `plugin/crew/hooks/hooks.json:3` | `handoff-read`, `platform-sync`, `crew-context` |
| `UserPromptSubmit` | 4 | `:11` | `crew-context`, `approval-hook` |
| `PreToolUse` | 8 | `:17` | `promote-gate` (`Bash`/`PowerShell`), `role-write-guard` (`Write\|Edit`), `cloud-guard` (`Bash\|PowerShell`), `scope-guard` (`Write\|Edit\|MultiEdit\|NotebookEdit\|Bash\|PowerShell`) |
| `PostToolUse` | 4 | `:35` | `crew-context` (`Read\|Edit\|Write\|MultiEdit`, and again on an `mcp__.*(obsidian\|vault\|basic[-_]memory).*` matcher) |
| `SubagentStart` | 2 | `:45` | `crew-context` |
| `PreCompact` | 2 | `:49` | `handoff-write` |
| `Notification` | 2 | `:53` | `notify` |
| `Stop` | 6 | `:57` | `verify-gate`, `context-watch`, `completion-audit` |

This is a materially different shape from the pre-1.0 hooks file (5 events,
20 entries, 10 scripts) — new events (`UserPromptSubmit`, `PostToolUse`,
`SubagentStart`) exist because `crew-context` (context-budget/handoff-carry)
and `approval-hook` (plan-approval-by-user-prompt) are new hooks, and
`PreToolUse` grew from 2 pairs to 4 (`cloud-guard`, `scope-guard` are new).

**Role-write-guard fails closed without python.**
`plugin/crew/hooks/scripts/role-write-guard.sh:348-354` resolves its own
private python (`_resolve_role_write_python`, `:43-` — hand-copied from
`_common.sh`'s `crew_py_strict`, not shared, "because it is the one hook
that can BLOCK a tool call and its test suite patches this file textually",
comment at `:34-41`); if no candidate resolves at all, or one resolves but
the interpreter then fails to launch (`role-write-guard.sh:367-382`, any
exit status other than 0 or 2), `_role_write_fallback_decision`
(`:326-346`) blocks (`exit 2`) any restricted role and only allows an
unrestricted one through, unjudged, with a named reason on stderr — "could
not tell" never collapses into "allowed".

**Event claims dedupe emitting hooks on Windows.** `event_claim.py`'s module
docstring (`plugin/crew/hooks/scripts/event_claim.py:1-16`) states the
problem it exists for: every hook is registered twice (bash + PowerShell),
and on Windows both flavours run for one event since no `.sh` may stand
itself down by OS (CLAUDE.md's own landmine). For a **blocking** hook
(scope-guard, completion-audit, cloud-guard, role-write-guard, approval-hook,
verify-gate) that is only wasted latency and both flavours still run — a
claim would let whichever flavour lost its python decide alone, which is
worse than the duplicate cost. For a hook that only **emits** (a chat ping,
a handoff skeleton), it is a visible duplicate, so `notify.sh` and
`handoff-write.sh` (confirmed by `grep -rl event_claim`) take a claim before
emitting: one atomic `O_CREAT|O_EXCL` file per generation
(`plugin/crew/hooks/scripts/event_claim.py:29-38`), so both flavours racing
for the same event have exactly one winner.

**Context-watch's forced-continuation marker is now session-scoped, not
repo-scoped.** `plugin/crew/hooks/scripts/context-watch.sh:59-60` defines
`MARKER=".crew/.handoff-requested-${SESSION_KEY}"` and
`SENT_MARKER=".crew/.autoclear-sent-${SESSION_KEY}"` — both keyed on
`SESSION_KEY`, so two concurrent sessions on the same repo no longer share
one marker (a correction to the previous anchor's description, which had a
single per-repository marker). `stop_hook_active`
(`plugin/crew/hooks/scripts/context-watch.sh:45`) is still checked first,
and the fail-closed-once branch that asks Claude for a precautionary
handoff and `exit 2`s still exists in the file at this anchor (confirmed
present; the exact line range was **not re-verified word-for-word against
the previous note's account of it** — see "Unverified at this anchor").

## Config, the guard vocabulary, and the ratchet

**DERIVED at this anchor by importing `crew_config` and executing both
default functions.** Re-measured 2026-09-27 at the T-0009 anchor (118 / 66 / 52 at the T-0005
anchor `a26ad8c0`, 116 / 65 / 51 at 6c497a14; T-0005 added `environments.prodUnattended` to
both layers and the repo-only `environments.nonProd`, T-0009 `guards.deployWorkflow` to both
layers and the repo-only `environments.workflows`), module resolved from this checkout, not an
installed plugin cache:

| | Leaves | Source |
|---|---|---|
| `default_config()` | **120** | `plugin/crew/hooks/scripts/crew_config.py:240` |
| `default_global_config()` | **67** | `plugin/crew/hooks/scripts/crew_config.py:376` |
| repo-only | **53** | the set difference |

Treat these as a fact about one commit, not a standing figure. Re-measure
from `plugin/crew/hooks/scripts/` rather than trusting the table:

```
python3 -c "import crew_config as c; r=set(c.leaf_paths(c.default_config())); g=set(c.leaf_paths(c.default_global_config())); print(len(r), len(g), len(r-g), len(g-r))"
```

The fourth figure (global leaves absent from the repo template) should be
0. This table previously read 114/63 at 6c497a14; executing the same
functions gives 116/65, so the earlier figures were a miscount, not drift.

These are new counts, not the pre-1.0 note's 103/60/43 carried forward —
`change.*`, `guards.cloudGuard` and the memory/recall keys (`TODO.md`'s
"T6 deferred items" names `memory.recall.vaults`, `memory.recall.maxChars`,
`memory.inject` as still needing `CONFIG.md` rows) all landed since. Not
re-measured against the pre-1.0 checkout — there is no reason to, since the
whole config module changed under the redesign — so "up from 103/60/43" is
deliberately not claimed here.

**Guards now come in four name-groups, not three, all still ranked through
one ratchet table.** `plugin/crew/hooks/scripts/crew_guards.py`:

| Group | Names | Vocabulary | Line |
|---|---|---|---|
| `GUARD_NAMES` | `terraformApply`, `forcePush`, `adminMerge`, `mergeGate`, `cloudDestructive`, `sqlDestructive`, `deployWorkflow` (7) | `block`/`ask`/`allow`, `guard_policy_rank` (`:421`) | `:106-107` |
| `PROD_GUARD_NAMES` | `prodDatabase`, `prodServer` (2) | `none`/`read`/`full`, `prod_level_rank` (`:450`) | `:128` |
| `ROLE_WRITE_GUARD_NAMES` | `roleWrites` (1) | `block`/`report`/`off`, default `off` not floor, `role_writes_rank` (`:486`) | `:151` |
| `CLOUD_GUARD_NAMES` | `cloudGuard` (1) — **new since the previous anchor** | same vocabulary and functions as `roleWrites`, its own words | `:190` |

`ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:196-197`) is the
concatenation of all four — **eleven** guard names in total (T-0009 appended `deployWorkflow`
to `GUARD_NAMES`).
`cloud_guard.py`'s own docstring (`:1-6`) states what `cloudGuard` actually
is: a switch, not a policy — turning it on is what makes the seven
`GUARD_NAMES` policies (which existed and ratcheted but governed nothing
since the pre-1.0 command guard was removed) mean something again for the
`Bash`/`PowerShell` `PreToolUse` matcher.

**The environment layer (T-0005, crew 1.0.41).** `cloud_guard.py`'s ENVIRONMENTS docstring
paragraph (`plugin/crew/hooks/scripts/cloud_guard.py:34-56`) states it: a terraform finding is
also judged by its target environment (`nonProd`, `prod` or `unknown`, from `TF_WORKSPACE`, an
in-sequence literal `workspace select|new`, `.terraform/environment`, `-var environment=` /
`TF_VAR_environment`, or a saved plan's sidecar) and by whether it destroys (`yes`, `no`,
`unknown`, and `unknown` counts as `yes`); `_terraform_verdict` (`:2993`) decides. The sidecar
is `.crew/tfplan/<sha256>.json`, written outside the hook by
`plugin/crew/hooks/scripts/crew_tfplan.py` (`summarize`, `:174`; `main`, `:237`), which reads
the plan's workspace out of the plan file itself (`plan_workspace`, `:123`). The config is
`crew_guards.ENVIRONMENTS_DEFAULTS` (`plugin/crew/hooks/scripts/crew_guards.py:260-261`):
`environments.nonProd` is repo-only, `environments.prodUnattended` ratchets (below), and T-0009's
repo-only `environments.workflows` is left out of the terraform layer's `engaged`. DERIVED from
the docstrings and definitions cited; the verdict table itself is `plugin/crew/CONFIG.md`'s
`environments.*` section, not re-derived here.

**The literal-word allowlist (T-0005 Steps 8-10).** Before the lexer reads
anything, `scan` calls
`_literal_gate` (`plugin/crew/hooks/scripts/cloud_guard.py:2802`, called at `:2851`, and only at
depth 0 - the raw command, never the lexer's own nested extractions): a line that RUNS terraform,
terragrunt or tofu and holds a word that is not a plain literal (`crew_guards.first_non_literal`,
`plugin/crew/hooks/scripts/crew_guards.py:1216`) yields one `terraformApply` finding whose scope
`op` is `OP_UNREADABLE_LINE`; `_terraform_verdict` answers it before reading any plan or
environment (ask, denied unattended; `block` denies). "Runs" is Step 9's trigger,
`crew_guards.command_trigger` (`:1812`; `command_names_terraform` `:1823` returns its word): its
own bash reader, `_GateReader` (`:1261`), splits the raw text into argv lists, and `_argv_trigger`
(`:1595`) fires on a command word that dequotes to one of the three after `_unwrap`'s wrappers, on
a `bash -c`/`eval`/`pwsh -c` payload or substitution that does, or on an unreadable command word
when the line names terraform, `destroy`, `apply` or `workspace`. Anything the reader does not
read with certainty falls back to Step 8's any-word trigger, `crew_guards.names_terraform`
(`:1204`). PowerShell lines use the same command-word rule since Step 10, `crew_guards.ps_trigger`
(`:1788`, per command `_ps_argv_trigger` `:1735`), read with the lexer's `_lex_ps`: `&`, `.`,
`terraform.exe`, a path, `Start-Process`, `pwsh -c`, `bash -c`, `Invoke-Expression`, `$(...)`.
The trigger returns `(word, unseen)`: `unseen` marks a command the lexer is not known to read (an
opaque script runner such as `flock` or `ssh` whose own words name terraform, `find -exec`'s found
path, zsh's `=terraform`, the reader's give-up, an alias, and the name a line copies or links
terraform to, run with a destroy/apply/workspace operand - `_copies_terraform` `:1672`), and an
unseen line is could-not-tell even when every word is plain. Since Step 10 there is no
unknown-wrapper fallback and no data-command exemption: an argument naming terraform is data
unless the command word is terraform (README "What the guard does not catch" lists what that
leaves out). A read-only terraform/tofu subcommand (`_tf_read_only`, `:1543`) does not trigger.
The helpers live in `crew_guards.py` because `cloud_guard.py` sits at `.pylintrc`'s
max-module-lines (3400 of 3400 at `a26ad8c0`, and again at the T-0009 anchor, whose classifier
lives in `crew_guards.py` for the same reason); `cloud_guard._GATE_HELPERS` (`:2798`) passes the
lexer's `_unwrap`, `_shell_args`, `_pwsh_payload`, `_ps_normalise`, `_head_name` and `_lex_ps` in,
so `crew_guards` still imports nothing from it. The lexer's own terraform reading skips options
before the subcommand (`_tf_skip_options` `:1549`, used by `_terraform_destructive` `:1561`), so
`terragrunt --working-dir infra destroy` is a destroy. DERIVED from the code cited.

**Workflow dispatches (T-0009).** `gh workflow run <wf>` and its REST twin, `gh api` POST on
`repos/<o>/<r>/actions/workflows/<wf>/dispatches`, are parsed by `crew_guards.dispatch_scopes`
(`plugin/crew/hooks/scripts/crew_guards.py:2108`; the two parsers `_dispatch_from_run` `:2006` and
`_dispatch_from_api` `:2021`, `xargs`/`parallel` through `_fed_dispatch` `:2056`) into one scope
shape, and classified by one function, `dispatch_environment` (`:2156`), against the repo-only
`environments.workflows` map: a workflow matching no key returns None and is not judged; what
crew cannot tell is `unknown`. `deploy_verdict` (`:2201`) is T-0005's table with
`guards.deployWorkflow` as the base policy, except that `allow` covers nonProd only.
`cloud_guard.py` holds only the call sites: `_classify`'s `gh` branch
(`plugin/crew/hooks/scripts/cloud_guard.py:2268`) and `_judge_one` (`:3094`, through
`judge_dispatch`, `crew_guards.py:2245`); the classes `ENV_NONPROD`/`ENV_PROD`/`ENV_UNKNOWN`
are now defined in `crew_guards.py` (`:1858`) and imported by `cloud_guard.py` (`:131`). The
map is read by `cloud_guard.environments_config` (`:2545`) and validated by
`crew_config.environments_block_problem` (`plugin/crew/hooks/scripts/crew_config.py:1001`).
DERIVED from the code cited.

**The ratchet registry (`_RATCHETED`, `plugin/crew/hooks/scripts/crew_config.py:2445-2568`)
now holds 15 keys**, built in seven steps (a literal dict of two at `:2445`, four `.update()`
calls at `:2460`, `:2484`, `:2495` and `:2505`, and two single-key assignments at `:2541` and
`:2564`) rather than one table: `pm.authority`, `install.policy`, the 7 `GUARD_NAMES` keys, the 2
`PROD_GUARD_NAMES` keys, `guards.roleWrites`, `guards.cloudGuard`,
`change.requireForProduction` and `environments.prodUnattended` (T-0005, crew 1.0.41) =
2 + 7 + 2 + 1 + 1 + 1 + 1 = 15 (T-0009 added `guards.deployWorkflow` through the
`GUARD_NAMES` update, and `:2471` then replaces that key's `allow` widening note, adding no
key). Counted by reading the construction sites and confirmed with
`len(crew_config._RATCHETED)` at the T-0009 anchor, not by trusting the literal alone — the
literal at `:2445-2456` holds only 2. (Before T-0005 this said "five steps" for 13 keys; the
sites were already six then — the literal, four `.update()` calls and one assignment.) The
same key is registered in `crew_guards.RATCHETED_KEYS`
(`plugin/crew/hooks/scripts/crew_guards.py:555-559`).

## `.crew/config.json` vs `.crew/crew.json` — the open 1.0.x authority question

**DERIVED, and this is the open TODO the task description names.** Two
different modules read two different files as "the repo's crew config", and
they disagree:

- `crew_config.py` (used by `verify-gate.sh`, `promote-gate.sh`,
  `role-write-guard.ps1`'s config lookups, and everything the ratchet/guard
  machinery above touches) reads **only** `.crew/config.json`
  (`plugin/crew/hooks/scripts/crew_config.py:1259`, and the module's own
  docstring at `:1` — "Owns the single definition of a fresh
  `.crew/config.json`").
- `crew_context.py`'s `load_crew_config`
  (`plugin/crew/hooks/scripts/crew_context.py:121-132`) tries `.crew/crew.json`
  **first**, falling back to `.crew/config.json` only if `crew.json` is
  absent — its own docstring: "1.0's `.crew/crew.json`, else 0.x's
  `config.json`".
- Only `/crew:migrate` (`crew_migrate.py`, `--apply`) ever writes
  `.crew/crew.json`; `/crew:init` still writes only `.crew/config.json`
  (`TODO.md:3945`, "T2 (lane D, additive) deferred items", filed
  2026-09-23, still open at this anchor; it was `:3854` at `6c497a14` and
  `:3884` at `f2bb919b`). `crew_migrate.py`'s own module
  docstring (`:1-4`) frames this as "one-time move of a 0.20 crew setup onto
  the 1.0 layout" and its schema table (`:11,26-40`) treats `crew.json`
  schema 1 as the target, `config.json` schema <= 7 as "kept, retireable".
- **Net effect: a freshly-`/crew:init`'d repo has no `crew.json` at all, so
  every module reads `.crew/config.json` — consistent for that repo. A repo
  that has run `/crew:migrate --apply` has both files, and which one
  governs depends on which hook script asked** — `crew_context.py`'s
  consumers (the context/handoff hooks) read `crew.json` first;
  everything routed through `crew_config.py` (the guards, the verify gate,
  `/crew:config`, `/crew:model`) still reads `config.json` only, and
  `apply_migrate_to_repo`'s own docstring
  (`plugin/crew/hooks/scripts/crew_autoclear_setup.py:501-507`) names
  the specific consequence for auto-clear: "`crew_status.py` reads it
  [`crew.json`] only to report the migration schema... converting
  `crew.json` alone [does nothing for autoClear behaviour, which
  `crew_config.py` still reads from `config.json`]". This is a real,
  present-tense inconsistency, not a hypothetical — flagging it is this
  note's job; **deciding which file should win, or whether `crew_config.py`
  should learn to read `crew.json` too, is a decision for scribe to record,
  not this note's to make.**

`SCHEMA_CURRENT` for `config.json` is still **7**
(`plugin/crew/hooks/scripts/crew_state.py:178`) — unchanged by the 1.0
redesign; the new `crew.json` format is a wholly separate schema (schema 1,
`crew_migrate.py:26`), so the redesign shipped without bumping the format
most of the codebase still actually reads.

## Auto-clear

Owner decision, crew 1.0 lane F4 (`auto-clear.sh:67-80`), reversing the
pre-1.0 file-based gate: **gated on the `.crew/` DIRECTORY existing, not on
`.crew/config.json`.** `context.autoClear` is a machine-global switch read
by `crew_config.py`, so it must work in any crew repo without that repo
having its own config — and "crew repo" is read the same way by both the
bash and PowerShell flavours: `[ -d .crew ] || exit 0` at `:80`, checked
**before** `note()` (`:83-89`) can create `.crew/.autoclear.log` as a side
effect, so a fresh checkout with no `.crew/` at all stays completely silent
and gets nothing created.

- **`context.autoClear.enabled` is machine-global-only under 1.0** —
  `crew_autoclear_setup.py:294-330` documents the change from 0.20.x, where
  a repo could carry its own copy; a repo copy is now ignored (only the
  global file's `enabled` can turn auto-clear on at all), because a
  repo-settable "on" defeats the point of a switch meant to describe the
  operator's own machine.
- **`method: "notify"` is the native-Windows default**, resolving from
  `"auto"` "on native Windows with no tmux pane"
  (`crew_autoclear_setup.py:223-232`). **`sendkeys` is opt-in only** and
  needs an explicit yes (the module docstring, `:9`, and
  `write_autoclear_method`'s consent gate at `:252-255`, in the function
  spanning `:239-256`) — because it "drives real
  keystrokes... cannot confirm which tab of its own inside Windows Terminal"
  it is typing into (`:117-120`), a concern distinct from, and in addition
  to, the machine-global gate above.
- `crew_autoclear_setup.py` is called from **three** places, confirmed by
  grep and by reading each call site: `/crew:init`'s Phase 1
  (`plugin/crew/skills/crew-setup/phases.md:180-186`, `plan-windows-default`),
  `/crew:onboard` (`plugin/crew/commands/onboard.md:199`, the identical
  helper, "so a repo onboarded standalone gets the identical question"),
  and `/crew:migrate` (`plugin/crew/commands/migrate.md:78`,
  `apply-migrate`).

## verify-gate's temp-file rule capture

`plugin/crew/hooks/scripts/verify-gate.sh` (1863 lines) captures each rule's
output to a temp file rather than a pipe, specifically to avoid a
backgrounded-and-abandoned grandchild process wedging the gate's own read
forever (`:1600-1643`) — `mktemp`, falling back to a repo-local
`.crew/.verify-rule-out.XXXXXX` if `TMPDIR` is unwritable (`:1600-1603`);
refusing the rule outright with a named reason if neither location is
writable (`:1697-1704`), rather than falling back to the old pipe form.

- **The captured output is capped at 1 MiB (1048576 bytes), read as the
  LAST N bytes (`tail -c`), not the first.** `RULE_OUT_CAP`
  (`verify-gate.sh:1663`) defaults to 1048576 and is clamped into `[1,
  1048576]` (`:1677-1683`); a rule that legitimately writes more than that
  before backgrounding something no longer turns a bounded gate into an
  unbounded read. `tail -c`, not `head -c` (`:1684-1694`): what a failing
  rule needs downstream is its actual error, which for noisy output sits at
  the end.
- **Per-rule process-group tracking and kill-on-signal was DESCOPED from
  crew 1.0 entirely**, per the comment at `verify-gate.sh:1628-1639` and
  CHANGELOG 1.0.21 (both cited in the file itself, `:599-600`): a signalled
  gate no longer TERM/KILLs whatever a rule's own escaped background work
  left running. What remains is only the isolation and prompt-signal
  properties the file's own test fixtures require (a rule's `exit N` exits
  only the rule, not the whole gate; a trapped signal on the gate itself is
  still handled promptly via `wait`). This is a documented limitation, not
  a bug — `CONFIG.md`'s own limitation entry is cited in the same comment,
  **not re-read this pass**.

**Correction to the previous anchor's account of `crew_py`/`crew_py_strict`
— this changed under the hood, not just in line numbers.** At the previous
anchor, `crew_py()` (`_common.sh`) only asked `command -v` and returned the
first resolvable name, never running it; only `crew_py_strict()` actually
executed a candidate. **At this anchor, `crew_py()` itself
(`plugin/crew/hooks/scripts/_common.sh:59-116`) now probes**: it walks every
`python3`/`python`/`py` match on PATH (`type -ap`, `:110`), actually runs
each with a bounded per-candidate timeout inside an overall 8-second deadline
(`:78-107`), and returns the first one that runs `-c pass` successfully,
falling back to the first PATH match only if the whole budget is spent with
nothing proven (`:111-114`). Both functions are explicitly **not memoized**
any more — a comment at each (`:60-69`, `:142-`) records that an earlier
cached version was reported 2026-09-24 and removed rather than repaired,
because every call site invokes it inside a `$(...)` subshell where a cache
was discarded before the next call regardless.

- **`crew_py_strict` is now the majority resolver, not a five-caller
  exception.** Grepping every `.sh` under `plugin/crew/hooks/scripts/` for
  `crew_py_strict` (excluding its own definition in `_common.sh`) finds it in
  **11** scripts: `notify.sh`, `handoff-write.sh`, `context-watch.sh`,
  `approval-hook.sh`, `crew-context.sh`, `cloud-guard.sh`,
  `platform-sync.sh`, `scope-guard.sh`, `auto-clear.sh`, `verify-gate.sh`
  (two call sites, `PY` at `:737` and `SHIM_PY` at `:1435`), and
  `completion-audit.sh:67`. **Only two scripts still call plain
  `crew_py()`**: `handoff-read.sh` (`:36,46`) and `promote-gate.sh:37`, plus
  four more plain call sites *within* `verify-gate.sh` itself
  (`PRICE_PY` at `:18`, `REPORT_PY` at `:275`, `FP_PY` at `:372`,
  `SCOPE_PY` at `:681`) that degrade to a no-op or a narrower error rather
  than gating the whole run.
- **A committed parity test now exists** —
  `plugin/crew/tests/test_context_watch_python_resolver.py` and
  `plugin/crew/tests/test_verify_gate_python_resolver.py`, both confirmed
  present, **neither read this pass**. `_common.sh:135-140`'s own comment
  says one of them "asserts the two copies still agree" (`crew_py_strict`
  vs. `role-write-guard.sh`'s private `_resolve_role_write_python`) — a
  guard against the "hand-copy with no guard is this repository's most
  repeated defect" risk the previous anchor's note flagged as unmitigated.
  Whether the test actually catches a divergence was **not sabotage-tested**
  this pass.
- **`Resolve-CrewPython` is still hand-copied, not shared, across all 11
  `.ps1` hooks that call it** — `grep -rl "function Resolve-CrewPython"`
  returns 11 files (`cloud-guard.ps1`, `crew-context.ps1`,
  `platform-sync.ps1`, `notify.ps1`, `completion-audit.ps1`,
  `role-write-guard.ps1`, `verify-gate.ps1`, `scope-guard.ps1`,
  `approval-hook.ps1`, `handoff-read.ps1`, `handoff-write.ps1`); there is no
  shared `_common.ps1` (confirmed absent by directory listing). Whether an
  equivalent PowerShell-side parity test exists for these 11 copies the way
  it does for the bash pair above was **not checked** this pass.

## `crew_endpoints.py` — the ledger now fails closed under an OS lock

Changed since `f2bb919b` by T-0003 (crew 1.0.35, `a1828a5d`), re-read at the
cited lines: `_ENDPOINTS_PATH_PARTS`
(`plugin/crew/hooks/scripts/crew_endpoints.py:49`), `declare_endpoint`
(`:566`), `infer_endpoints` (`:734`), `gizmoduck_installed` (`:822`),
`_is_monorepo` (`:904`), `scan_artifact_path` (`:991`), `record_scan_artifact`
(`:1044`), `_endpoint_needle` (`:1128`), `_artifact_confirms_scan` (`:1163`),
`read_endpoints` (`:1248`). The two read-modify-write paths,
`declare_endpoint` and `record_scan_artifact`, now hold an OS advisory lock on
a persistent `.crew/endpoints.json.oslock` across the whole cycle (comment at
`:258-290`; `_acquire_endpoints_lock`, `:510`), and a lock or write failure is
returned as an error rather than reported as a landed write -
`crew_state.py`'s `--record-scan-artifact` exits 3 on it
(`plugin/crew/hooks/scripts/crew_state.py:3273-3279`). Function bodies past
those lines were not read. `.crew/endpoints.json` still does not exist in this
checkout; `git ls-files .crew/` still returns only the codemap `.md` files
plus `.crew/verify.json`.

## `.claude/rules/` - generated from this directory, and gated against it

New on main since `6c497a14` (#227, #228). `python3 plugin/crew/hooks/scripts/crew_instructions.py
rules --root .` writes one `.claude/rules/<subsystem>.md` per code-map note that yields any paths
(`expected_rules`, `plugin/crew/hooks/scripts/crew_instructions.py:169`; `render_rule`, `:123`):
a `paths:` frontmatter derived from the note's own citations, a `crew:generated` marker carrying
the sha256 of everything the rule is rendered from (`rule_digest`, `:105`), the note's anchor,
INDEX.md's Covers cell for it, and the note's Landmines headlines (else its Entry points), capped at
`RULES_MAX_LINES` = 30 (`:81`). `--check` (`rules`, `:191`) writes nothing and reports each rule
file missing, stale or orphaned; a hand-written file at a generated path is never overwritten and
fails `--check`. `.crew/verify.json` rule 23 (`.crew/verify.json:256`) runs `--check` for any change under
`.claude/rules/**` or `.crew/codemap/**`, so **a code-map edit without a regeneration fails the Stop
gate** - see `verification-harness.md`. DERIVED from the source above; the command was run by
T-0015 against this refresh.

## The artifact refresh check (T-0008, crew 1.0.36)

`plugin/crew/hooks/scripts/crew_refresh_check.py` answers one read-only
question: are the code maps, diagrams and code graph that THIS ticket's
changed paths reach still current (module docstring, `:1-8`)? It narrows
`crew_freshness.py`'s per-artifact questions to the paths the ticket changed
(`plugin/crew/hooks/scripts/scope_base.py` `resolve` plus `completion_audit.changed_paths`, minus
`RELEASE_BOOKKEEPING`, `:181`), so a raw anchor lag is not staleness; each
artifact reads `fresh`/`stale`/`unknown` (`:152-154`) with the refresh command
to run, documents read `not measured`, and a scope base that hides or may
hide the change - a fallback, or (since review round 3) a recorded base with
a commit behind it naming the ticket (`_named_behind`, `:537`) - makes the
whole answer `unknown`, and every artifact measured against that base with it
(`_unconfirmed`, `:554`; `ticket_freshness`, `:576`). It is a CLI the
commands call, not a hook - `plugin/crew/hooks/hooks.json` is unchanged since
`f2bb919b`.

- `/crew:implement` step 6 (`plugin/crew/commands/implement.md:85-104`) runs
  it after `/crew:docs` and before `/crew:review` (`:92`), runs each named
  refresh, commits, and re-runs until `fresh`; a `stop` ends the loop.
- `/crew:done` Check 4 (`plugin/crew/commands/done.md:46-57`) runs it again
  and refuses on `stale` or `unknown` without refreshing (`:52-55`).
- `REFRESH_ARTIFACT_PATHS` (`plugin/crew/hooks/scripts/crew_refresh_check.py:168-173`: the code map,
  `docs.diagramsDir`, `graph.out`, `.claude/rules`) is the one definition.
  The scope guard (`_refresh_artifact`,
  `plugin/crew/hooks/scripts/scope_guard.py:186-197`) and the completion audit
  (`_outside_refresh_artifacts`,
  `plugin/crew/hooks/scripts/completion_audit.py:177-187`) let a ticket write
  those paths without a Touch entry **only while its approval is current**;
  with no current approval nothing is exempt.
- Tests: `plugin/crew/tests/test_refresh_check.py`,
  `plugin/crew/tests/test_scope_guard_refresh_artifacts.py`,
  `plugin/crew/tests/test_completion_audit_refresh_artifacts.py`, with mutations in
  `plugin/crew/tests/sabotage_refresh.py`; `.crew/verify.json:257-273` (rule
  24) maps them, `implement.md`, `done.md`, and since review round 3
  `scope_guard.py`, `completion_audit.py`, `crew_freshness.py` and
  `scope_base.py` with their own suites, to one pytest rule. Confirmed
  present, **not run and not read** by this note.

`docs/diagrams/process-crew-lifecycle.mmd` drew `/crew:done` as "all three
or nothing" at `adf8d1dd`; T-0008's refresh commit `b7b02842` redrew it as
"all four or nothing" (its `:125`).

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:986` — `TRIGGERS`, a 15-entry
  tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2883` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:240` / `:376` —
  `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2445` — `_RATCHETED`, the
  15-key ratchet table (six construction steps).
- `plugin/crew/hooks/scripts/role_write_guard.py:539` — `classify`, the
  decision function; `:684` — `main()`.
- `plugin/crew/hooks/scripts/role-write-guard.sh:348` — where the strict
  private-resolver result feeds the guard's fail-closed fallback.
- `plugin/crew/hooks/scripts/event_claim.py` — no single entry point read
  this pass beyond the module docstring; called from `notify.sh` and
  `handoff-write.sh` only.
- `plugin/crew/hooks/scripts/crew_context.py:121` — `load_crew_config`, the
  one function that reads `crew.json` before `config.json`.
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py` — no single `main()`
  confirmed at a specific line this pass; called with subcommands
  (`plan-windows-default`, `apply-migrate`) from the three sites named
  above.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:576` — `ticket_freshness`,
  the library entry point; `main()` at `:676`.
- `plugin/crew/hooks/scripts/crew_endpoints.py:566` — `declare_endpoint`,
  the only writer of *declared* records. Not the only writer of
  `.crew/endpoints.json`, whatever its docstring says (`:569-570`):
  `record_scan_artifact` (`:1044`) writes the document too (`:1089`), and
  the lock comment (`:258-261`) names both.

## Owns data

- `.crew/codemap/` — this directory, read by `crew_freshness.py`'s
  `read_knowledge` (location **not re-verified this pass** — the previous
  anchor cited `plugin/crew/hooks/scripts/crew_freshness.py:375-459`; this
  pass did not open `crew_freshness.py` at all, so that citation is carried
  forward unread and should be treated as unconfirmed at this anchor, not
  as re-derived).
- `.crew/config.json` — the schema-7 format `crew_config.py` reads/writes;
  see "the open 1.0.x authority question" above for why this is not the
  whole story.
- `.crew/crew.json` — the schema-1 format only `/crew:migrate` writes and
  only `crew_context.py`'s consumers prefer.
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1228-1233`)
  — 4 roles, all tiered, none a specialist.
- `crew_state.PM_DEFAULTS` (`:1082-1095`) and `crew_state.AUTHORITY_DEFAULT`
  (`:1052`) — the unnamed session's own dispatch authority.
- `crew_guards.ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:196-197`)
  — 11 guard names across 4 vocabularies.
- `.crew/metrics.jsonl` — append-only, one JSON object per line, replacing
  the pre-1.0 `.crew/metrics.md` (`crew_metrics.py`'s module docstring,
  **not otherwise read**). Still machine-local: the `.gitignore` un-ignore
  list at this anchor is still exactly three paths — `!.crew/codemap/`,
  `!.crew/endpoints.json`, `!.crew/verify.json` — confirmed by reading
  `.gitignore:279-330` directly; `metrics.jsonl` is not among them.
- `.crew/endpoints.json` and its lock file `.crew/endpoints.json.oslock`
  (created on first use, never deleted); see above.

## Calls out to

- `crew_context.py` -> `obsidian-vault`'s CLI, via `crew_recall.py` (module
  docstring only, **not read**: "crew does not search vaults itself...
  calls that plugin's read-only contract and nothing else").
- `crew_autoclear_setup.py` -> `~/.claude/crew/config.json` (the
  machine-global file), the only writer path for `context.autoClear`.
- `verify-gate.sh` -> `.crew/verify.json` (the rule map) and, per rule, a
  fresh subshell + temp file (see above) rather than a direct pipe.
- `role-write-guard.sh`/`.ps1` -> `role_write_guard.py`, piped the raw hook
  JSON on stdin, judged, and exited 0 or 2 only.
- `crew_migrate.py` -> both `.crew/config.json` (read) and `.crew/crew.json`
  (write, `--apply` only), with `--rollback` restoring a backup
  byte-identical (module docstring, **not read further**).

## Unverified at this anchor

- No hook was executed and no pytest run was made part of this pass; every
  claim about *behaviour* is read from source, not observed running under
  Claude Code.
- `plugin/crew/hooks/scripts/crew_freshness.py` was **not opened this
  pass** — every citation into it above is carried forward from the
  previous anchor's note **unread**, and is flagged as such in place. This
  is the single biggest gap in this re-derivation: the map-freshness
  machinery this very file's own `anchor:` line depends on was not
  re-checked.
- `plugin/crew/tests/test_context_watch_python_resolver.py` and
  `test_verify_gate_python_resolver.py` were confirmed present, not read;
  no sabotage test was run against either.
- `review_ledger.py`, `review_patch.py`, `review_prompt.py`, `review_run.py`,
  `review_verdict.py` — the review pipeline `/crew:review` and `/crew:done`
  depend on — were located but not opened.
- `webtest_guard.py`, `webtest_rules.py`, `webtest_scaffold.py` — new
  scripts since the previous anchor, backing `/crew:webtest` — were located
  but not opened.
- `crew_change.py`, `crew_incident.py`, `crew_platform.py`, `crew_ticket.py`,
  `crew_status.py`, `crew_metrics.py`, `crew_recall.py` were read only at
  their module docstrings, not their function bodies.
- The 11 `.ps1` hooks' bodies past their `Resolve-CrewPython` definitions
  were not read; whether any PowerShell-side equivalent of the bash parity
  test exists is unknown.
- `plugin/crew/evals/pm-*`, `developer-*` and `qa-reviewer-stays-read-only`
  fixture contents were not read; whether they were internally updated to
  target the 1.0 roster is unverified.
- The previous anchor's wide count-disagreement sweep (README.md,
  plugin/README.md, INSTALLATION.md, both install scripts, against the
  4/34/29 inventory above) was **not repeated** this pass — only
  `.claude-plugin/marketplace.json`'s own crew entry was checked, and found
  current.
- `context-watch.sh`'s fail-closed-once branch (the precautionary-handoff
  `exit 2` path) was confirmed present but not re-read line-for-line against
  the previous anchor's detailed account of it; only the marker's
  session-scoping (a real change) was independently verified.
- `CONFIG.md`'s own limitation entry for the descoped per-rule
  process-group kill, cited by `verify-gate.sh`'s comment, was not opened.

## Why this note has no Landmines section

Unchanged policy, restated because it still applies: `.crew/codemap/INDEX.md`
assigns landmines to `CLAUDE.md` explicitly — this directory holds the map,
not the judgement calls. Nothing found this pass rises to a crew-specific
landmine distinct from what is already recorded above as a DERIVED fact
(the stale `pm`/`qa-reviewer` references, the two-file config split) or
already a JUDGEMENT flagged for scribe.

## What this file does not cover

Agent role definitions and command bodies are not traced here beyond their
frontmatter and the sections cited above. `crew:reference` and `crew:roster`
are the tools for the finer grain. Config is covered here only in outline —
`plugin/crew/CONFIG.md` is the full reference and the authority where the
two disagree. The other subsystem notes in `.crew/codemap/` cover their own
areas; `INDEX.md` is the table of contents. The `6c497a14` re-derivation left
its anchor column to the integrator; T-0015 re-filled that column from
`grep -m1 '^anchor:'` when it re-anchored every note to `f2bb919b`.

## Re-anchor provenance - `6c497a14` -> `f2bb919b`, 2026-09-25 (T-0015)

`git diff --name-only 6c497a14 f2bb919b -- <the 39 tracked paths this note cites>` returns six:
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `README.md`, `TODO.md`,
`plugin/crew/commands/fix.md`, `plugin/crew/commands/spec.md`. No hook script this note cites changed (`verify-gate.ps1` and
`auto-clear.ps1` did, and this note names them only in the `Resolve-CrewPython` copy list, which
still holds: `grep -rl "function Resolve-CrewPython" plugin/crew/hooks/scripts` returns the same 11).
Each changed file:

- `plugin/crew/commands/spec.md` - T-0001 (1.0.26/1.0.27) rewrote the Touch template and added the
  one-path-per-bullet paragraph (`:38-43`). The `:8-9` citation was off by one before that change
  too - the "Replaces `/crew:ticket`" sentence is `:7-8` at both anchors - and is corrected.
- `plugin/crew/commands/fix.md` - T-0001 rewrote the step-2 spec template (the `## 2. Spec` heading
  at `:31` and the sections below it); the one citation here, `:2` (the `description:` line), did
  not move.
- `TODO.md` - 30 lines inserted after `:16`; the one live citation moved `:3854` -> `:3884` (re-read,
  same bullet).
- `.claude-plugin/marketplace.json` - crew `version` (`:218`) only; `:217`'s 4/34/29 counts are
  unchanged and still match disk (re-counted).
- `.crew/verify.json` - rule 22 appended; the `.claude/rules/` section above is new for it.
- `README.md` - two install-URL pins only; cited here in the Unverified sweep list.

Also added, not caused by the diff: `/crew:approve`'s row and the `approve` phase in the lifecycle
line. `approve.md` is unchanged since `6c497a14`; the `6c497a14` table omitted it.

## Re-anchor provenance - `f2bb919b` -> `adf8d1dd`, 2026-09-25 (T-0008)

`git diff --name-only f2bb919b adf8d1dd -- <the paths this note cites>` returned
`.claude-plugin/marketplace.json`, `.crew/codemap/INDEX.md`, `.crew/verify.json`, `TODO.md`,
`docs/diagrams/process-crew-lifecycle.mmd`, `plugin/crew/commands/done.md`,
`plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_endpoints.py` and
`plugin/crew/hooks/scripts/crew_state.py`. Each citation into them was re-read with `grep -n`:

- `crew_state.py` - one hunk at `:3270-3276`, below every line cited here; all hold.
- `crew_endpoints.py` - T-0003 rewrote it; the section above is re-derived and every line moved
  (`declare_endpoint` `:255` -> `:566`, and the rest as listed there). The "only writer" claim was
  already wrong at `f2bb919b` (`record_scan_artifact` wrote the file then too) and is corrected.
- `TODO.md` - `:3884` -> `:3945`, same bullet.
- `done.md` - three checks -> four; the `:7-8` citation holds, its claim is updated.
- `implement.md` - step 6 gained the refresh; `:8-9` holds.
- `.crew/verify.json` - one rule appended after rule 22, which did not move (`:243`).
- `marketplace.json` - crew `version` only; `:217`'s counts still match disk.
- `INDEX.md` - still assigns landmines to `CLAUDE.md`; its freshness citations moved, none cited here.
- `process-crew-lifecycle.mmd` - new since `f2bb919b`; noted above as predating T-0008.

`plugin/crew/hooks/scripts/crew_freshness.py` is still not opened by this note.

## Re-anchor provenance - `adf8d1dd` -> `8d447a7d`, 2026-09-25 (T-0008 review round 3)

`git diff --name-only adf8d1dd 8d447a7d -- <the paths this note cites>` returned
`.crew/codemap/INDEX.md`, `.crew/verify.json`, `TODO.md`, `docs/diagrams/process-crew-lifecycle.mmd`,
`plugin/crew/hooks/scripts/completion_audit.py`, `plugin/crew/hooks/scripts/crew_refresh_check.py`,
`plugin/crew/tests/sabotage_refresh.py` and `plugin/crew/tests/test_refresh_check.py`. Each
citation into them was re-read with `grep -n`:

- `crew_refresh_check.py` - `_named_behind` and `_unconfirmed` inserted above `ticket_freshness`,
  which moved `:549` -> `:576`, `main()` `:645` -> `:676`. `:1-8`, `:152-154`, `:168-173` and
  `:181` are above the change and hold.
- `completion_audit.py` - `_stdin_path` inserted at `:103`; `_outside_refresh_artifacts` moved
  `:167-177` -> `:177-187`.
- `.crew/verify.json` - one path added to rule 7, so rule 22 moved `:243` -> `:244`; rule 23 grew
  four script paths and three test files, now `:245-261`.
- `TODO.md` - two version strings at `:5000-5001`; `:3945` holds.
- `process-crew-lifecycle.mmd` - the "all three or nothing" sentence was already false after
  `b7b02842`; corrected above (review round 3 NIT).
- `INDEX.md`, the two test files - cited by name only.

## Re-anchor provenance - `8d447a7d` -> `fc54def6`, 2026-09-25 (T-0005)

`8d447a7d` is T-0008's pre-rebase round-3 commit; T-0008 landed on main by rebase-merge as
`95120430`/`768a747a`, so the anchor names a commit that is not an ancestor of HEAD.
`git diff --name-only 8d447a7d fc54def6 -- <the paths this note cites>` returns T-0008's own
refresh outputs (`.claude/rules/*`, `.crew/codemap/*`, `process-crew-lifecycle.mmd`), the
version files, and T-0005's changes: `.crew/verify.json`, `TODO.md`, `plugin/crew/CONFIG.md`,
`cloud_guard.py`, `crew_config.py`, `crew_guards.py`, `crew_state.py`, `crew_tfplan.py` (new) and
the `crew-cloud`/`crew-setup` skills. Each citation into them was re-read at `fc54def6`:

- `crew_state.py` - three import lines added (`:74`, `:102-103`); every citation below them moved
  by +3 (`TRIGGERS` `:983` -> `:986`, `ROLE_TIERS` `:1225-1230` -> `:1228-1233`, and the rest).
- `crew_guards.py` - `ENVIRONMENTS_DEFAULTS` and its rank functions inserted at `:240-271`; the
  three rank functions moved (`:378` -> `:410`, `:407` -> `:439`, `:443` -> `:475`); the name
  groups at `:104-195` did not. `RATCHETED_KEYS` gained `environments.prodUnattended`.
- `crew_config.py` - `default_config`/`default_global_config` `:239`/`:367` -> `:240`/`:374`;
  `_RATCHETED` `:2342` -> `:2418`, now 14 keys (the paragraph above, which also corrects the
  step count); `:1158` -> `:1234`. The leaf table is re-measured: 118 / 66 / 52.
- `.crew/verify.json` - one rule inserted at index 6 (the cloud-guard suites, `:117-126`), so
  every rule from the old 6 on is one higher: the `.claude/rules/` check is rule 23 at `:255`, the
  refresh-check suite rule 24 at `:256-272`. The history sections above keep the numbers true at
  their own anchors.
- `cloud_guard.py`, `crew_tfplan.py` - new section above, "The environment layer".
- `TODO.md` - lines appended at `:5052-5059`; `:3945` holds. `CONFIG.md` - cited by name only.
- The two skills - `crew-setup` gained the `environments` line in its config template; neither is
  cited at a line here.

## Re-anchor provenance - `fc54def6` -> `2170d72e`, 2026-09-26 (T-0005 review round 2)

`git diff --name-only fc54def6 2170d72e -- <the paths this note cites>` returns only what round 2
changed: `plugin/crew/hooks/scripts/cloud_guard.py` (the WHAT IT RECOGNISES table gained one line, so
the ENVIRONMENTS paragraph moved `:32-54` -> `:33-55`, re-read and byte-identical; the lexer
and `_tf_workspace` changes are below every other citation into it, none of which this note
states by line) and `plugin/crew/CONFIG.md` (three lines added inside the destroy paragraph;
this note cites CONFIG.md by name and section only). Nothing else moved.

Then `2170d72e` -> `22adb579`: only `cloud_guard.py` changed (`_expansion_subs` renamed a local,
below `:33-55`, which was re-read unchanged).

Then `22adb579` -> `496ee9b4` (T-0005 review round 3): of the paths this note cites, only
`cloud_guard.py` changed - the bash lexer (`_bash_close`, the fail-closed doubt count in `scan`,
the CR re-reads, PowerShell quote/CR normalisation, every terragrunt `workspace` word). Lines
`:1-6` and `:33-55` were diffed against `22adb579` and are byte-identical. `_terraform_verdict`
moved `:2655` -> `:2903`; this note said `:2549`, which was already wrong at `22adb579` (it read
`:2655` there), so the citation was stale before this round and is corrected now.

Then `496ee9b4` -> `3a57b2d2` (T-0005 Step 8, the literal-word allowlist): of the paths this note
cites, `cloud_guard.py` (the allowlist gate in `scan`, its verdict branch, a docstring paragraph
after `:55`), `crew_guards.py` (`import re` at `:30`, so every line below it moved +1, and the
allowlist helpers appended at the end), `plugin/crew/CONFIG.md` (cited by name and section only)
and `.crew/verify.json` (`crew_guards.py` added to the cloud-guard rule's paths, so rule 23 moved
`:255` -> `:256` and rule 24 `:256-272` -> `:257-273`) changed. `:1-6` and `:33-55` of
`cloud_guard.py` were diffed against `496ee9b4` and are byte-identical. Re-taken by content:
`ALL_GUARD_NAMES` `:195-196`, the guard table's lines, `ENVIRONMENTS_DEFAULTS` `:251`,
`RATCHETED_KEYS["environments.prodUnattended"]` `:545-549`, `_terraform_verdict` `:2942`. The
historical re-verify notes above keep the numbers of their own anchors.

Then `3a57b2d2` -> `1e210476` (T-0005 Step 9, gate on the command being run): `git diff
--name-only 3a57b2d2 1e210476 -- <the paths this note cites>` returns `cloud_guard.py`,
`crew_guards.py`, `plugin/crew/CONFIG.md` (cited by name and section only), the version files
(crew stepped back to 1.0.37 and re-set to 1.0.41, byte-identical to `3a57b2d2`) and, under
`plugin/crew/**`, the Step 9 tests and README. In `cloud_guard.py`, `:1-6` and `:33-55` are
byte-identical (the first hunk starts at `:57`); the docstring grew three lines and the
`crew_guards` import two, so `_terraform_verdict` moved `:2942` -> `:2953`, `_literal_gate`
`:2769` -> `:2777`, and its call `:2802` -> `:2813` (now depth 0 only). In `crew_guards.py` every
line above `:1084` is unchanged, so `ALL_GUARD_NAMES` `:195-196`, the guard table,
`ENVIRONMENTS_DEFAULTS` `:251` and `RATCHETED_KEYS["environments.prodUnattended"]` `:545-549`
hold (re-read); `names_terraform` moved `:1189` -> `:1194` and `first_non_literal` `:1201` ->
`:1206`, and the Step 9 trigger is appended from `:1216`. Re-taken by content, corrected above.

Then `1e210476` -> `aa7f9841` (T-0005 review round 5, kF0AM1): `git diff --name-only 1e210476
aa7f9841 -- <the paths this note cites>` returns `cloud_guard.py`, `crew_guards.py`,
`plugin/crew/CONFIG.md` (cited by name and section only), the version files (crew stepped back to
1.0.37 in `675752f6` and re-set to 1.0.41 in `aa7f9841`, byte-identical to `1e210476`) and, under
`plugin/crew/**`, the round-5 tests, README and BUDGETS. In `cloud_guard.py` the first hunk starts
at `:60`, so `:1-6` and `:33-55` hold; the docstring grew seven lines and the import is unchanged
in length, so `_literal_gate` moved `:2777` -> `:2789`, its call `:2813` -> `:2840`, and
`_terraform_verdict` `:2953` -> `:2980`. In `crew_guards.py` the first hunk starts at `:1515`, so
`ALL_GUARD_NAMES` `:195-196`, the guard table, `ENVIRONMENTS_DEFAULTS` `:251`,
`RATCHETED_KEYS["environments.prodUnattended"]` `:545-549`, `names_terraform` `:1194`,
`first_non_literal` `:1206` and `_GateReader` `:1252` hold (re-read); `_argv_trigger` moved
`:1518` -> `:1606`, and `command_trigger`, `_tf_read_only` and `ps_unseen` are new. Re-taken by
content, corrected above.

Then `aa7f9841` -> `d2085450` (T-0005 review round 5 neighbours): `git diff --name-only aa7f9841
d2085450 -- <the paths this note cites>` returns `crew_guards.py` (git's data exemption narrowed
to `_GIT_DATA`, `rg` dropped, the copy flag shared with nested scripts; first hunk at `:1531`), the
version files (stepped back and re-set, byte-identical to `aa7f9841`) and, under `plugin/crew/**`,
the round-5 tests. `cloud_guard.py` did not change. `_tf_read_only` moved `:1543` -> `:1552`,
`_argv_trigger` `:1606` -> `:1625`, `ps_unseen` `:1727` -> `:1750`, `command_trigger` `:1755` ->
`:1778`, `command_names_terraform` `:1766` -> `:1789`; everything above `:1531` holds. Re-taken by
content, corrected above.

Then `d2085450` -> `a26ad8c0` (T-0005 Step 10, direct use only): `git diff --name-only d2085450
a26ad8c0 -- <the paths this note cites>` returns `cloud_guard.py`, `crew_guards.py`,
`plugin/crew/CONFIG.md` (cited by name and section only), the version files (crew stepped back to
1.0.37 in `2602e4ad` and re-set to 1.0.41 in `a26ad8c0`, byte-identical to `d2085450`) and, under
`plugin/crew/**`, the Step 10 tests, README, BUDGETS and the crew-cloud skill. In `cloud_guard.py`
the first change is at `:57`, so `:1-6` and `:33-55` hold; `_literal_gate` moved `:2789` ->
`:2802`, its call `:2840` -> `:2851`, `_terraform_verdict` `:2980` -> `:2993`, `_GATE_HELPERS`
`:2785` -> `:2798`. In `crew_guards.py` the first change is at `:1249`, so `ALL_GUARD_NAMES`
`:195-196`, the guard table, `ENVIRONMENTS_DEFAULTS` `:251`,
`RATCHETED_KEYS["environments.prodUnattended"]` `:545-549`, `names_terraform` `:1194` and
`first_non_literal` `:1206` hold (re-read); `_GateReader` `:1252` -> `:1251`, `_tf_read_only`
`:1552` -> `:1533`, `_argv_trigger` `:1625` -> `:1585`, `command_trigger` `:1778` -> `:1802`,
`command_names_terraform` `:1789` -> `:1813`; `ps_unseen` and `cloud_guard._ps_unseen` are gone,
`ps_trigger` and `_ps_argv_trigger` are new. Re-taken by content, corrected above.

## Re-anchor provenance - `a26ad8c0` -> `05cf5bc9`, 2026-09-27 (T-0009)

`git diff --name-only a26ad8c0 05cf5bc9 -- <the paths this note cites>` returns `cloud_guard.py`,
`crew_guards.py`, `crew_config.py`, `plugin/crew/CONFIG.md` (cited by name and section only; the
new `environments.workflows` subsection sits inside section 16, so section numbers hold) and,
under `plugin/crew/**`, the T-0009 tests, templates, skills, README and BUDGETS. Every cited line
of the three modules was re-taken by content with a line-level diff against `a26ad8c0`. In
`crew_guards.py` `import json` (`:29`) moves everything below it +1 and the
`ENVIRONMENTS_DEFAULTS` comment +9 more, so the guard table, `ALL_GUARD_NAMES` `:196-197`,
`first_non_literal` `:1216`, the trigger functions and `RATCHETED_KEYS` `:555-559` moved;
`ENVIRONMENTS_DEFAULTS` itself changed (`:260-261`, `workflows` added) and was re-read; the
dispatch section is appended at `:1829`. In `cloud_guard.py` the docstring gained one line and
the import block one, and `ENV_*`'s definition moved to `crew_guards.py`, so `:34-56` is the
ENVIRONMENTS paragraph and `_literal_gate` `:2802`, `_GATE_HELPERS` `:2798` and
`_terraform_verdict` `:2993` hold; the file is still 3400 lines. In `crew_config.py` a comment
inside `default_config` (+2 from `:352`), the `workflows` validation (+23 more by `:1055`), the
`deployWorkflow` prose (+2 more by `:2285`) and its allow note (+11 more by `:2568`) moved
`default_global_config` `:376`, `_RATCHETED` `:2445` and its sites. The
leaf counts (120 / 67 / 53), the guard count (11) and `len(crew_config._RATCHETED)` (15) were
re-executed, not read. The T-0009 paragraph above is new and DERIVED from the code it cites.
