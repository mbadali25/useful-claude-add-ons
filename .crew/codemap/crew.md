anchor: useful-claude-add-ons@926443d8
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
`crew_state.py`'s roster/config block (:996-1363), `crew_guards.py`'s guard
vocabulary block (:92-538), `crew_context.py`, `event_claim.py`'s module
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
Re-verified per-path from `f2bb919b` to `adf8d1dd` for T-0008, from
`adf8d1dd` to `8d447a7d` for its review round 3, to `c35edda5` for
T-0034, and to `8ebbdedc` for T-0026's landing; on T-0006's branch, from
`8d447a7d` to `6d35ef8c` for T-0006 and from `6d35ef8c` to `2bb92f32` for its
review round 3; both to `a0c0847e` for T-0006's landing; on T-0004's
branch from `a0c0847e` to `07ca3972`; on T-0042's branch from `6f96e627` to `068db4ff`;
on T-0021's branch, from `c35edda5` to
`7b667587` for T-0021 and to `385eadd5` and `bcb77ce2` for its review rounds 1
and 2; and to `c2ae46ab` for its review round 3 and merge of main. See the last
sections.

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
| Commands | 35 | `.md` files in `plugin/crew/commands/` (35 since T-0004 added `autopilot.md`) |
| Skills | 29 | subdirectories of `plugin/crew/skills/` (includes 8 `stack-*` skills) |

`.claude-plugin/marketplace.json:217` states the identical three numbers (4
agents, 35 commands, 29 skills) in its `crew` entry's description, and `:218`
the version, 1.0.48 (T-0010), matching `plugin/crew/.claude-plugin/plugin.json:3`, so this
site is current — this pass did not re-run the previous note's wider
count-disagreement sweep across `README.md`/`plugin/README.md`/
`INSTALLATION.md`/the install scripts; see "Unverified at this anchor".

## The roster, replaced wholesale

Crew 0.x shipped 54 agents (13 tiered roles + 40 specialists) plus a standing
`pm` agent that dispatched them. Crew 1.0 (`docs/review/04-redesign.md`,
"Roster: 54 agents -> 4", cited in comment at
`plugin/crew/hooks/scripts/crew_state.py:1241-1246`) replaces that with:

- **Four read-only subagents on a tier ladder**, `ROLE_TIERS`
  (`plugin/crew/hooks/scripts/crew_state.py:1250-1255`): `explorer` and
  `reviewer` at tier 0, `security` at tier 1, `researcher` at tier 2. None of
  the four grants `Write` or `Edit` — confirmed by reading each agent file's
  frontmatter (`explorer.md`, `researcher.md`, `reviewer.md`, `security.md`,
  all `tools: Read, Grep, Glob, Bash, Skill`).
- **No specialist roles.** `SPECIALIST_ROLES` is now `frozenset()`
  (`plugin/crew/hooks/scripts/crew_state.py:1265`) — domain knowledge that
  used to be a specialist agent now lives in the on-demand `stack-*` skills
  (`stack-angular`, `stack-bash`, `stack-dotnet`, `stack-powershell`,
  `stack-python`, `stack-sql`, `stack-terraform`, `stack-web`), which are
  never dispatched as a role.
- **No standing PM agent file.** `plugin/crew/agents/pm.md` does not exist at
  this anchor (`find . -iname pm.md` returns nothing). The interactive session
  itself is the "unnamed PM": it implements, dispatches the four subagents,
  and is never itself given an `agent_type`. `PM_DEFAULTS`
  (`plugin/crew/hooks/scripts/crew_state.py:1104-1117`) and `pm.authority`
  (`AUTHORITY_DEFAULT = "report-only"`, `:1062`; three values —
  `report-only`/`act`/`autonomous`, `normalise_authority` at `:1297-1308`)
  still exist as config that governs how far that unnamed session may act
  without asking, and `AUTONOMOUS_STOPS`
  (`plugin/crew/hooks/scripts/crew_state.py:1075-1082`) still names the four
  things even `autonomous` may not do unasked (`offboard-role`, `delete-map`,
  `rewrite-metrics`, `git-destruction`). Since T-0004 they bind
  `/crew:autopilot` too (comment at `:1084-1089`).
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:1268-1277`) still
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
| `/crew:approve` (`plugin/crew/commands/approve.md:5`, `disable-model-invocation: true`) | Typed by the user only: the UserPromptSubmit `approval-hook` records `<git-common-dir>/crew/tickets/<id>/approval.json`, bound to the digest of `spec.md` and `plan.md` (`:7-16`; since T-0026 a `crew-approval/2` digest that normalises only the header's status value, so the lifecycle's status edits keep the approval); the command body only relays the result | new in 1.0 |
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
default functions.** Measured 2026-09-27 on T-0023's merge of main (`502cb137`, T-0005
landed) into T-0023, module resolved from this checkout
(`plugin/crew/hooks/scripts/crew_config.py`), not an installed plugin cache:

| | Leaves | Source |
|---|---|---|
| `default_config()` | **124** | `plugin/crew/hooks/scripts/crew_config.py:240` |
| `default_global_config()` | **68** | `plugin/crew/hooks/scripts/crew_config.py:393` |
| repo-only | **56** | the set difference |

Treat these as a fact about one commit, not a standing figure. Re-measure
from `plugin/crew/hooks/scripts/` rather than trusting the table:

```
python3 -c "import crew_config as c; r=set(c.leaf_paths(c.default_config())); g=set(c.leaf_paths(c.default_global_config())); print(len(r), len(g), len(r-g), len(g-r))"
```

The fourth figure (global leaves absent from the repo template) should be
0. This table previously read 114/63 at 6c497a14; executing the same
functions gives 116/65, so the earlier figures were a miscount, not drift.
Re-executed at `6d35ef8c`: 117 / 66 / 51 / 0 - T-0006 added `resume.auto` to
both templates, so repo-only is unchanged. Re-executed at `07ca3972`: 119 / 66
/ 53 / 0 - T-0004 added `autopilot.mode` and `autopilot.maxPhases` to
`default_config()` only (`:376-381` on the merge, "REPO ONLY, absent from
`default_global_config()`"); the same functions at `a0c0847e`, run from a
`git archive` of `plugin/crew`, give 117 / 66 / 51 / 0. Re-executed on the T-0005 landing
merge: 121 / 67 / 54 / 0 - T-0005 added `environments.prodUnattended` to both templates and
`environments.nonProd` to `default_config()` only. Re-executed on T-0023's merge of main: 122 /
68 / 54 / 0 - T-0023 added `route.enabled` to both `default_config()` (`:389`) and
`default_global_config()` (`:563`), so repo-only is unchanged. Re-executed on T-0023's merge of
`db14619c` (T-0042 and T-0021 landed): 122 / 68 / 54 / 0 - neither added a config leaf.
Re-executed on T-0010-solo's merge of `67caa4b8` (T-0018 landed), at `c817782f`: 124 / 68 / 56 / 0
- T-0010 added `autopilot.approval` and `autopilot.questions`, repo-only through the same
`autopilot` block (123 / 67 / 56 on T-0010-solo before the merge).
`plugin/crew/tests/test_crew_config.py:281` asserts 124. T-0004's `CHANGELOG.md` entry now says
"117 -> 119" (`:577-578`; `:436-437` at `bebbb97f`, before T-0018's entry went in above it; `:390-391` at `db14619c`, before T-0023's; `:276-277` at `f0b12ee6`, before T-0021's; `:228-229` at `2b18f7ab`, before T-0042's), matching the `07ca3972` execution; it said "116 -> 118" when this
paragraph was first written. T-0005's entry states no leaf count; T-0023's says 121 -> 122;
T-0010's says 122 -> 124.

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
| `GUARD_NAMES` | `terraformApply`, `forcePush`, `adminMerge`, `mergeGate`, `cloudDestructive`, `sqlDestructive` (6) | `block`/`ask`/`allow`, `guard_policy_rank` (`:411`) | `:105-106` |
| `PROD_GUARD_NAMES` | `prodDatabase`, `prodServer` (2) | `none`/`read`/`full`, `prod_level_rank` (`:440`) | `:127` |
| `ROLE_WRITE_GUARD_NAMES` | `roleWrites` (1) | `block`/`report`/`off`, default `off` not floor, `role_writes_rank` (`:476`) | `:150` |
| `CLOUD_GUARD_NAMES` | `cloudGuard` (1) — **new since the previous anchor** | same vocabulary and functions as `roleWrites`, its own words | `:189` |

`ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:195-196`) is the
concatenation of all four — **ten** guard names in total.
`cloud_guard.py`'s own docstring (`:1-6`) states what `cloudGuard` actually
is: a switch, not a policy — turning it on is what makes the six
`GUARD_NAMES` policies (which existed and ratcheted but governed nothing
since the pre-1.0 command guard was removed) mean something again for the
`Bash`/`PowerShell` `PreToolUse` matcher.

**The environment layer (T-0005, crew 1.0.42).** `cloud_guard.py`'s ENVIRONMENTS docstring
paragraph (`plugin/crew/hooks/scripts/cloud_guard.py:33-55`) states it: a terraform finding is
also judged by its target environment (`nonProd`, `prod` or `unknown`, from `TF_WORKSPACE`, an
in-sequence literal `workspace select|new`, `.terraform/environment`, `-var environment=` /
`TF_VAR_environment`, or a saved plan's sidecar) and by whether it destroys (`yes`, `no`,
`unknown`, and `unknown` counts as `yes`); `_terraform_verdict` (`:2975`) decides. The sidecar
is `.crew/tfplan/<sha256>.json`, written outside the hook by
`plugin/crew/hooks/scripts/crew_tfplan.py` (`summarize`, `:174`; `main`, `:237`), which reads
the plan's workspace out of the plan file itself (`plan_workspace`, `:123`). The config is
`crew_guards.ENVIRONMENTS_DEFAULTS` (`plugin/crew/hooks/scripts/crew_guards.py:251`):
`environments.nonProd` is repo-only, `environments.prodUnattended` ratchets (below). DERIVED from
the docstrings and definitions cited; the verdict table itself is `plugin/crew/CONFIG.md`'s
`environments.*` section, not re-derived here.

**The literal-word allowlist (T-0005 Steps 8-10).** Before the lexer reads
anything, `scan` calls
`_literal_gate` (`plugin/crew/hooks/scripts/cloud_guard.py:2784`, called at `:2833`, and only at
depth 0 - the raw command, never the lexer's own nested extractions): a line that RUNS terraform,
terragrunt or tofu and holds a word that is not a plain literal (`crew_guards.first_non_literal`,
`plugin/crew/hooks/scripts/crew_guards.py:1206`) yields one `terraformApply` finding whose scope
`op` is `OP_UNREADABLE_LINE`; `_terraform_verdict` answers it before reading any plan or
environment (ask, denied unattended; `block` denies). "Runs" is Step 9's trigger,
`crew_guards.command_trigger` (`:1873`; `command_names_terraform` `:1884` returns its word): its
own bash reader, `_GateReader` (`:1251`), splits the raw text into argv lists, and `_argv_trigger`
(`:1642`) fires on a command word that dequotes to one of the three after `_unwrap`'s wrappers, on
a `bash -c`/`eval`/`pwsh -c` payload or substitution that does, or on an unreadable command word
when the line names terraform, `destroy`, `apply` or `workspace`. Anything the reader does not
read with certainty falls back to Step 8's any-word trigger, `crew_guards.names_terraform`
(`:1194`). PowerShell lines use the same command-word rule since Step 10, `crew_guards.ps_trigger`
(`:1849`, per command `_ps_argv_trigger` `:1783`), read with the lexer's `_lex_ps`: `&`, `.`,
`terraform.exe`, a path, `Start-Process`, `pwsh -c`, `bash -c`, `Invoke-Expression`, `$(...)`.
The trigger returns `(word, unseen)`: `unseen` marks a command the lexer is not known to read (an
opaque script runner such as `flock` or `ssh` whose own words name terraform, `find -exec`'s found
path, zsh's `=terraform`, the reader's give-up, an alias, and the name a line copies or links
terraform to, run with a destroy/apply/workspace operand - `_copies_terraform` `:1720`), and an
unseen line is could-not-tell even when every word is plain. Since Step 10 there is no
unknown-wrapper fallback and no data-command exemption: an argument naming terraform is data
unless the command word is terraform (README "What the guard does not catch" lists what that
leaves out). A read-only terraform/tofu subcommand (`_tf_read_only`, `:1585`, which reads terragrunt past its options and `run-all`) does not trigger.
The helpers live in `crew_guards.py` because `cloud_guard.py` sits at `.pylintrc`'s
max-module-lines (3380 of 3400 at `02d1513b`); `cloud_guard._GATE_HELPERS` (`:2780`) passes the
lexer's `_unwrap`, `_shell_args`, `_pwsh_payload`, `_ps_normalise`, `_head_name` and `_lex_ps` in,
so `crew_guards` still imports nothing from it. The lexer's own terraform reading skips options
before the subcommand (`crew_guards.tf_skip_options` `:1541`, used by `_terraform_destructive`
`:1540`), so `terragrunt --working-dir infra destroy` is a destroy, and `_unwrap` reads a listed
wrapper's options as GNU getopt does (`crew_guards.skip_wrapper_options` `:1560`). DERIVED from the code cited.

**The ratchet registry (`_RATCHETED`, `plugin/crew/hooks/scripts/crew_config.py:2444-2556`)
now holds 14 keys**, built in seven steps (a literal dict of two at `:2444`, four `.update()`
calls at `:2459`, `:2472`, `:2483` and `:2493`, and two single-key assignments at `:2529` and
`:2552`) rather than one table: `pm.authority`, `install.policy`, the 6 `GUARD_NAMES` keys, the 2
`PROD_GUARD_NAMES` keys, `guards.roleWrites`, `guards.cloudGuard`,
`change.requireForProduction` and `environments.prodUnattended` (T-0005) =
2 + 6 + 2 + 1 + 1 + 1 + 1 = 14. Counted by reading the construction sites and confirmed with
`len(crew_config._RATCHETED)` on the T-0005 landing merge and again on T-0023's merge of main
(14), not by trusting the literal alone — the literal at `:2444-2455` holds only 2. (Before T-0005 this said "five steps" for 13 keys; the
sites were already six then — the literal, four `.update()` calls and one assignment.) The
same key is registered in `crew_guards.RATCHETED_KEYS`
(`plugin/crew/hooks/scripts/crew_guards.py:545-549`). `autopilot.*` is not ratcheted
(T-0004 added no `_RATCHETED` entry).

## `.crew/config.json` vs `.crew/crew.json` — the open 1.0.x authority question

**DERIVED, and this is the open TODO the task description names.** Two
different modules read two different files as "the repo's crew config", and
they disagree:

- `crew_config.py` (used by `verify-gate.sh`, `promote-gate.sh`,
  `role-write-guard.ps1`'s config lookups, and everything the ratchet/guard
  machinery above touches) reads **only** `.crew/config.json`
  (`plugin/crew/hooks/scripts/crew_config.py:1260`, and the module's own
  docstring at `:1` — "Owns the single definition of a fresh
  `.crew/config.json`").
- `crew_context.py`'s `load_crew_config`
  (`plugin/crew/hooks/scripts/crew_context.py:121-132`) tries `.crew/crew.json`
  **first**, falling back to `.crew/config.json` only if `crew.json` is
  absent — its own docstring: "1.0's `.crew/crew.json`, else 0.x's
  `config.json`".
- Only `/crew:migrate` (`crew_migrate.py`, `--apply`) ever writes
  `.crew/crew.json`; `/crew:init` still writes only `.crew/config.json`
  (`TODO.md:3963`, "T2 (lane D, additive) deferred items", filed
  2026-09-23, still open at this anchor; it was `:3854` at `6c497a14`,
  `:3884` at `f2bb919b` and `:3952` at `1e0706ac`). `crew_migrate.py`'s own module
  docstring (`:1-4`) frames this as "one-time move of a 0.20 crew setup onto
  the 1.0 layout" and its schema table (`:11,26-41`) treats `crew.json`
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
  present-tense inconsistency, not a hypothetical. T-0004's
  `crew_autopilot.settings` (`plugin/crew/hooks/scripts/crew_autopilot.py:683`)
  sides with `config.json` explicitly: it reads through
  `crew_config.resolve_config` and warns when `autopilot` is set in
  `crew.json` but not `config.json` ("crew does not read [it] for this key;
  move it to .crew/config.json", `:698-702`). T-0023's
  `crew_route.settings` (`plugin/crew/hooks/scripts/crew_route.py:296`) does
  the same for `route` (`:321-324`) - and it is the sharper case, because
  its only caller is `crew_context.route_item`, inside the one hook that reads
  `crew.json` first for `memory.inject`: one hook, two files, by key.
  Flagging it is this
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

## Auto-resume after `/clear` (T-0006, crew 1.0.40; T-0042, crew 1.0.43)

`plugin/crew/hooks/scripts/crew_resume.py` owns the `resume:` line a handoff
carries (read in full at `6d35ef8c`, its changed functions re-read at `2bb92f32`, and every
function T-0042 touched re-read at `068db4ff`; every line citation below re-taken with `grep -n`
at `53f5482c`): the closed
allowlist `RESUME_COMMANDS` (`:37`, a module constant so no repo can widen it), the grammar
(`parse_resume`, `:91`; ticket digits are ASCII `[0-9]`, `:83`; the automatic PreCompact
skeleton - `crew_autocycle.SKELETON_MARK` - is refused whole before any line is read, `:102-103`),
the opt-in (`settings`, `:172` - armed only when the
machine file `~/.claude/crew/config.json` says `resume.auto: true`; a repo
`false` in `.crew/crew.json` or `.crew/config.json` vetoes, a repo `true`
grants nothing) and the read-only `decide` (`:667`), where the first failing
check wins and every "could not tell" is `wait`, never `run`. It registers no
hook. `crew_context.py`'s SessionStart branch calls it through
`resume_decision` (`plugin/crew/hooks/scripts/crew_context.py:661`) for
`clear`/`compact` only, after `_handoff_verdict` (`:638`), which passes the
staleness VERDICT on rather than whether the archive move succeeded, and a
rule that raises as stale; `resume_line` (`:687`) renders the one injected
line. Nothing starts on its own - the command is named, never sent as
`initialUserMessage`. On `PreCompact` both `handoff-write` flavours call its
`precompact` CLI (`write_precompact_record`,
`plugin/crew/hooks/scripts/crew_resume.py:577`); `decide` trusts a `manual`
record for 600 s and never one it could not have replaced
(`_compact_was_manual`, `:643`). A record a later PreCompact could neither remove nor empty
is MARKED, not predicted: `precompact-<key>.stuck` (`stuck_path` `:552`, `_mark_stuck` `:560`;
the shell flavours write the same marker, `plugin/crew/hooks/scripts/handoff-write.sh:52-53`,
`plugin/crew/hooks/scripts/handoff-write.ps1:327-328`), and a compact is not manual while that
marker exists or cannot be stat'ed; `crew_context.prune_precompact` ages it out with the records.

A handoff resumes only in the session that wrote it (T-0042). On an armed machine every
`PostToolUse` Write/Edit/MultiEdit of the configured handoff is recorded by
`crew_context.record_handoff_author` (`plugin/crew/hooks/scripts/crew_context.py:615`, called
through the never-raising `_record_author_logged` `:1021` from `run` `:996`, before the
`memory.inject` gate) into `<git-common-dir>/crew/handoff-author.json` (`record_author`,
`plugin/crew/hooks/scripts/crew_resume.py:270`: the note's sha256, `session_id`, and
`session_process()` `:220` - the nearest `claude` ancestor as `{pid, start}`, `None` on any host
without `/proc`). A recorder that cannot take the author lock, or whose write fails - including
one that was only REMOVING this worktree's entry - drops the whole file (`_drop_author` `:331`)
and says when even that failed, so the previous entry never vouches for a note another session
wrote last (T-0042 review round 1). `decide` asks `_author_refusal` (`:409`) after the command checks and before
the state file: `compact` must match the session id, `clear` the process; a missing, unreadable
or sha-mismatched record, or an unidentifiable process, is a `wait`, never a match. `record_run`
(`:728`) is the only writer of
`<git-common-dir>/crew/resume-state.json`, and nothing in the plugin calls it
yet (T-0013's contract). A state file that exists and cannot be read or is not
the shape `record_run` writes is an unknown (`_read_state` `:362`, `_entry` `:384`
return `None`): `decide` waits and `record_run` refuses rather than overwriting it. A PARTIAL
record is that shape too (T-0042, before review round 2): a file with no `worktrees` key, or an
entry of this worktree missing `consumed`, `last`, or last's string `prompt`/`fingerprint`, is
`None`, not "nothing consumed, no loop history"; no entry for this worktree is still `{}`.
Whether it exists at all goes through `_absent` (`:345`): only `FileNotFoundError` /
`NotADirectoryError` is absence, any other stat error is `None` - the round-4 FIX, since
`os.path.lexists` read an unsearchable directory as "no file". `.work/INDEX.md` goes through the
same helper (`_index_rows` `:466`), so an unstat-able index makes the fingerprint unknown.
`record_run` asks consumed-once and the loop guard again under its lock through
the same `_already` (`:439`) `decide` uses, so of two senders holding one `run`
only the first gets `ok`. Tests: `plugin/crew/tests/test_crew_resume.py`,
`plugin/crew/tests/test_crew_resume_hook.py`; mutations
`plugin/crew/tests/sabotage_resume.py` (72 by `len(RESUME_MUTATIONS)` at `53f5482c`); `.crew/verify.json`
rule 26 (`:282-292`).

## `/crew:autopilot` (T-0004, crew 1.0.41)

DERIVED at `89f73d79` (T-0018) and on T-0010-solo (T-0010), re-read together at `c817782f`.
`plugin/crew/commands/autopilot.md` (110 lines since T-0010, 100 since T-0018,
`allowed-tools: Read, Write, Edit, Bash, Agent, Skill`, `:4`) first
routes its whole argument string, single-quoted (`## 0. Route`, `:14-27`), then either
prints `status` (`## 1. status`, `:29-36`, read-only, armed or not) or drives
one ticket through the phase commands **in-session**, following each
command's own procedure; the run refuses unless armed (`:46-47`). The reader
behind it, `plugin/crew/hooks/scripts/crew_autopilot.py` (1436 lines), is
read-only except T-0010's `approve`, only when `approval_policy` allows, which writes what
`crew_ticket.approve` writes for every route: `approval.json`, `scope-tickets.json` on a
ticket's first approval, and a distinct successor plan's NEEDS_REPLAN -> IN_REVIEW ledger move
(module docstring, `:1-121`; the owner's carve-out of 2026-09-27),
with eight subcommands: `next`, `resume`, `settings`, `stops`, `route`, `status`, and
T-0010's `approve` and `questions-check` - script subcommands, not `/crew:autopilot` ones.
`next_phase` (`:516`) names the next phase from files on disk, first match wins (the table at
`:58-81`); `resume_target` (`:612`) picks the ticket (the handoff's `resume:` line only
when its branch and head match, per `plugin/crew/commands/autopilot.md:48-49`);
`settings` (`:683`) arms only on the exact string `plan`, falls back to
`maxPhases` 12 for anything not a positive int, and warns on each. `stops`
(`:1009`) lists every stop from code: `crew_state.AUTONOMOUS_STOPS`,
`FIXED_STOPS` (`:163`, nine), `PROCEDURE_STOPS` (`:180`, three) and
`HUMAN_STOPS` (`:186`, four - brainstorm, plan approval, review acceptance,
open questions; plan approval and open questions wait for a person unless T-0010's policy
allows).

T-0018 (crew 1.0.43) added the router and `status`. `route_args` (`:1054`)
takes the command's `$ARGUMENTS` whole - Claude Code 2.1.283 substitutes
`$0` with the first argument and leaves an out-of-range `$N` literal, so a
positional `$1`/`$2` never carried the ticket - and `route` (`:1025`) decides
the subcommand: `SUBCOMMANDS` (`:199`), of which only `status` and `run` are
`AVAILABLE`; `assign`/`goal`/`focus` stop naming T-0019/T-0012/T-0020; a
bare INDEX-shaped id or existing `.work/tickets/<id>/` is `run`; any other
word - `approve` and `questions-check` included - a second word that is not a ticket, or a
third word stops (`run --goal` stops naming T-0012); `route --first <token>` routes one token
alone. `status` (`:1249`) composes `settings`, `resume_target` or `next_phase`,
`review_ledger.status` and `crew_resume`, and `status_text` (`:1288`) caps it
at 12 lines; `--json` prints the same dict as one line of JSON (`main`, `:1347`), inside the
cap (round 5); what it cannot tell reads `unknown`. Neither reads the approval policy: `status`
composes `resume_target` / `next_phase` / `_phase` with `policy=False` (T-0010 review round 3),
so its approve and open-questions reasons are the fixed `POLICY_FREE_APPROVE` /
`POLICY_FREE_QUESTIONS` (`:832`, `:835`) and at the approve phase it names `/crew:approve <id>`
under every setting (`test_route_and_status_unaffected_by_approval_policy`,
`test_status_at_approve_reads_the_same_under_an_allowing_policy`); the one policy effect it shows is
`crew_ticket.accepted`'s demotion of an `autopilot` receipt the policy no longer allows. Its `resume:` line reads usable
only where bare `/crew:autopilot` - `resume_target` itself - would take it (`_resume_line`,
`:1204`; `_takes`, `:1108`), asked only after `_resume_line`'s own read of the handoff passes the
branch, head and folder checks, so a file rewritten after `resume_target` read it is never
vouched for by that earlier read (round 5), and says `unknown` when `resume_target` raised, or when
`.work/HANDOFF.md` exists but cannot be read (`_read_handoff`, `:552`, which `resume`'s
fall-through shares - only a file that is not there reads `no .work/HANDOFF.md`; a dangling
or looping symlink, or a `.work` that is a dangling symlink, is there and reads `unknown`, round 5). A `next` stop
made on the active-ticket pointer rather than the phase waits on re-pointing it (`_repoint`,
`:1138`), never on the owner typing the phase's command, and offers driving the active ticket
only while it is not closed - read by `_closed` (`:1168`) from INDEX.md's status and spec.md's
`status: done` header directly, so no `direction.md` cannot hide either; a `spec.md` that exists
but cannot be read makes `_closed` return None, and the offer becomes "could not tell whether
<active> is still open" (round 4). A `stop=0` phase names
bare `/crew:autopilot` only when that drives the same ticket (`_waiting`, `:1114`). Every drive
suggestion goes through `_drive` (`:1159`), which writes `/crew:autopilot run <id>` for an id that
is exactly a `SUBCOMMANDS` name - `route` would read the bare name as the subcommand - and the
bare `/crew:autopilot <id>` otherwise. Its `review:`
line (`_review`, `:1184`) prints a rounds count only for a ledger state in `LEDGER_STATES`
(`:1084`); a state of `UNKNOWN`, or one review_ledger never writes, reads `unknown`.
`plugin/crew/commands/autopilot.md` runs every `crew_autopilot.py` line as `python3 -B`, and the
script itself sets `sys.dont_write_bytecode` under `__main__` before its sibling imports
(`:129-131`), so neither the command nor the direct CLI writes a bytecode cache into the plugin;
a module importing it keeps its own setting. Defaults live in
`crew_state.AUTOPILOT_DEFAULTS` (`plugin/crew/hooks/scripts/crew_state.py:1094`,
`{"mode": "off", "maxPhases": 12, "approval": "risk", "questions": "risk"}` since T-0010), deep-copied into `default_config()`
(`plugin/crew/hooks/scripts/crew_config.py:381`). It registers no hook -
`plugin/crew/hooks/hooks.json` is unchanged since `a0c0847e`.

`crew_ticket.parse_risk` (`plugin/crew/hooks/scripts/crew_ticket.py:509`)
also landed in T-0004: it reads `risk:` from the spec header line only, and
an absent or unrecognised value reads as `high` with `known: False`, never
`low`. Its consumer is T-0010's `_ticket_risk` (`plugin/crew/hooks/scripts/crew_autopilot.py:738`).
Tests: `plugin/crew/tests/test_crew_autopilot.py`,
`plugin/crew/tests/test_crew_autopilot_status.py`,
`plugin/crew/tests/test_lifecycle_commands.py`; mutations
`plugin/crew/tests/sabotage_autopilot.py` (`STATUS_MUTATIONS` appended to
`AUTOPILOT_MUTATIONS`); `.crew/verify.json` rule 27 (`:293-301`).
Confirmed present, **not run** by this note.

**T-0010 (approval and questions policies, DERIVED on T-0010-solo, crew 1.0.48 on T-0018's main).**
`approval_policy` (`plugin/crew/hooks/scripts/crew_autopilot.py:766`) returns `allow` only when
`crew_ticket.cli_approval_allowed` is true (`scope.allowCliApproval` exactly `true`, at every
setting), the review ledger is not UNKNOWN (NEEDS_REPLAN does not refuse since review round 1:
a distinct successor plan is its only way out, and `review_ledger.continue_with_successor_plan`
refuses a plan approved before, so `approve` exits 3), and then `self` (any risk) or
`risk` on a known `risk: low`; `human` never; a settings read that raises is `policy: unknown`,
refused. `question_policy` (`:804`) is `take|stop` by the same rule without the
`allowCliApproval` term. `approve` (`:855`) also needs `mode: plan`, then calls
`crew_ticket.approve(..., via=crew_ticket.AUTOPILOT)` - the module's one writing path, which lands
`approval.json`; on a ticket's first approval, the scope ramp's `scope-tickets.json`
(`crew_ticket._register_ramp`, `plugin/crew/hooks/scripts/crew_ticket.py:704`, as for every
route); and, for a distinct successor plan under a NEEDS_REPLAN ledger, the ledger moved
NEEDS_REPLAN -> IN_REVIEW (`review_ledger.continue_with_successor_plan`, `plugin/crew/hooks/scripts/review_ledger.py:419`). `questions_check` (`:972`) validates
`.work/tickets/<id>/questions.md` against `QUESTIONS_SHAPE` (`:880`) and refuses a `taken:` line
naming a policy that never takes (only `self`/`risk` do; the name is history, not compared with
today's) or any `taken:` while the policy in force says `stop`. `next` appends
`_approval_hint` (`:840`) / `_question_hint` (`:849`) to the `approve` and `open-questions`
stops (`:448` for approve), which stay `stop=1`; `commands/autopilot.md` section 3 (`:72-80`)
runs the policy on exactly those two `stop=1` lines before stopping, with `python3 -B`, and
states the `questions.md` shape `questions_check` enforces (review round 2). `main` (`:1347`)
sends both to `_policy_main` (`:1330`) before T-0018's branches. In
`plugin/crew/hooks/scripts/crew_ticket.py`: `AUTOPILOT = "autopilot"` (`:144`), `_autopilot_refusal`
(`:653`), `accepted` (`:670`) demotes an `autopilot` receipt unless that refusal is None, and
`approve` (`:716`) refuses an `autopilot` via the policy denies. `scope_guard.py`'s
`_AUTOPILOT_APPROVE_RE` / `_AUTOPILOT_BARE_RE` (`plugin/crew/hooks/scripts/scope_guard.py:118-122`) and
`_autopilot_refusal` (`:237`) allow only the bare command while the policy says yes;
`shell_refusal` (`:265`) runs `_reading_refusal` (`:281`) on each reading `_joined` (`:257`)
gives - the command as written and with line continuations joined (`_BASH_CONTINUATION_RE` /
`_PS_CONTINUATION_RE`, `:126-127`) - while the bare-command rule judges the command as written.
Tests `plugin/crew/tests/test_crew_autopilot_policy.py` plus new cases in `test_crew_ticket.py`,
`test_scope_guard.py`, `test_crew_autopilot_status.py` and `test_crew_route.py`; mutations
`POLICY_MUTATIONS` in `sabotage_autopilot.py` (47, `plugin/crew/tests/sabotage_autopilot.py:371`),
registered at `plugin/crew/tests/sabotage.py:77` and `:3053`; `.crew/verify.json` rule 28
(`:302-308`), which also maps `commands/autopilot.md` since review round 2.

## Plain-text lifecycle routing (T-0023, crew 1.0.43)

DERIVED at `eba11657`, re-read after review round 1. `plugin/crew/hooks/scripts/crew_route.py`
(359 lines) decides whether a short plain-text prompt names a lifecycle command. The table
is `PHRASES` (`:81`): brainstorm, spec, plan, implement, review, done,
continue, status - no approve row. `match` (`:131`) matches the WHOLE prompt
after `normalise` (`:111`) refuses a line break, more than `MAX_PROMPT_CHARS`
(`:61`, 80), or a leading `/`, `<` or backtick; `AMBIGUOUS` (`:95`) phrases
("do it", "yes", bare "done"...) return None whatever a row says. `decide`
(`:210`) returns `route`, `ask` or `none`; `_resolve` (`:169`) takes an
explicit id only with a `.work/tickets/<id>/` folder, then
`crew_ticket.resolve_active`'s `active-ticket` source, then
`crew_autopilot.open_index_tickets` with exactly one ticket - never
`resolve_active`'s own first-open-line INDEX answer. `continue` goes through
`_continue` (`:190`) to `crew_autopilot.next_phase`; a stop, an exception, or
a command naming approve is an `ask`. `render` (`:253`) clips every
variable-length field it reads to its own `FIELD_CHARS` cap with `_clip`
(`:229`), so the line is at most `MAX_LINE_CHARS` (`:70`, 1400) and always
fits the UserPromptSubmit budget (`crew_context.TURN_CHARS`, 2000) as the
first item: `fit` keeps whole items or none, and before review round 1 a long
open question dropped the ask entirely. `settings` (`:296`) reads
`crew_config.resolve_config` and arms only on `is True`. The one consumer is
`crew_context.route_item` (`plugin/crew/hooks/scripts/crew_context.py:838`),
called first in the UserPromptSubmit branch (`:936`): Claude harness only,
`crew_route` imported inside a `try`, so any exception drops only the route
line and logs `route: "error"` (`:1069` keeps that log line when nothing else
is emitted). No new hook and no new skill: `plugin/crew/hooks/hooks.json` is
unchanged. Tests: `plugin/crew/tests/test_crew_route.py`,
`plugin/crew/tests/test_crew_route_hook.py`; mutations
`plugin/crew/tests/sabotage_route.py` (registered at
`plugin/crew/tests/sabotage.py:79`); `.crew/verify.json` rule 30 (`:317-325`),
the last.

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
(`plugin/crew/hooks/scripts/crew_state.py:3295-3301`). Function bodies past
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
fails `--check`. `.crew/verify.json` rule 24 (`.crew/verify.json:263`) runs `--check` for any change under
`.claude/rules/**` or `.crew/codemap/**`, so **a code-map edit without a regeneration fails the Stop
gate** - see `verification-harness.md`. DERIVED from the source above; the command was run by
T-0015 against this refresh.

## The tracker interface (T-0021, crew 1.0.43)

DERIVED at `2a9e0989` (review round 4's fixes; set to 1.0.43 at `d276b268`;
first derived at `7b667587`, re-derived at `bcb77ce2` and `c2ae46ab`).
`plugin/crew/hooks/scripts/crew_tracker.py` is the one module that writes a
tracker, and the only crew code that writes outside the repository (an
Obsidian vault). A CLI the commands call, not a hook.

- `resolve` (`:210`) reads BOTH config shapes - `.crew/crew.json`
  `tracker.kind` and `.crew/config.json` `tracker` (`_side`, `:139`) - and
  answers `could not tell` when both state a kind and they differ; for
  obsidian, when the two files yield a different effective vault, `boardDir`,
  `board` or lane names, defaults and the `memory.vaultPath` fallback applied,
  a value only one file yields included (`_effective` `:176`,
  `_effective_disagreements` `:197`); for jira/sdp, when their blocks differ
  whole, a block only one file carries included. `not configured` when
  neither states one. Every write refuses on `could not tell` (`_gate`,
  `:270`).
- Status -> lane is the table `LANE_FOR_STATUS` (`:90`), `ready` (brainstorm's
  approval) included, mapped to the backlog lane; a status absent from it is
  refused with nothing written (`move`, `:1356`). `STATUS_ORDER` (`:89`) is
  read by `_backwards` (`:590`): a move backwards, or from a status crew does
  not know, is `could not update` unless `--reopen`.
- Files backend: the `.work/INDEX.md` row whose id cell matches exactly
  (`_files_create` `:602`, `_files_move` `:628`, `_files_read` `:656`); a row
  with no status cell is `could not update` / `could not read`; `create` on
  any id INDEX holds, the same title included, is refused with a reason
  beginning `id taken` (`_held`, `:578`; `TAKEN`, `:83`). `title_ok`
  (`:568`) refuses `|` and every break `str.splitlines` honours. Obsidian =
  files + the board (`_obsidian_create` `:1218`, `_obsidian_move` `:1263`,
  `_obsidian_read` `:1302`); a move whose INDEX half refuses writes no board
  (`:1297`), as a create whose INDEX half refuses writes no card (`:1251`).
  Jira/SDP answer `delegated` with `<sync> <KEY> --push --to <status>` at
  `_PUSH_AT` (`:113`: `in-progress`, `done`) and `nothing to push` otherwise
  (`_push` `:1332`, `_delegated` `:1327`); CLI exit codes 0/1/3/2
  (`exit_code` `:264`, `main` `:1410`).
- Obsidian `create`'s order (review round 4): INDEX first (`_index_holds`
  `:1192`, called at `:1220`, before `_vault_paths`), so a vault failure never
  hides a held id; then vault, identity, board and owner check; then the
  claim, the note's exclusive create (`:1245`), before the INDEX row and the
  card. A note that appeared after the owner check makes that create fail,
  and `create` answers `id taken` (`:1246`, reason from `_lost_claim`
  `:1208`) with nothing written after it. A note that was already this repo's
  is not re-created, and the INDEX row decides under its atomic update.
- Every write goes through `_atomic_update` (`:385`): the temp is created by
  `_write_temp` (`:372`) via `_write_new` (`:359`) with `_TEMP_FLAGS` (`:289`,
  `O_EXCL|O_NOFOLLOW`) under a random name, so a planted link is never
  followed; `_carry` (`:343`) gives it the target's owner and mode from
  `_ownership` (`:327`) - a new file takes its directory's owner only as root;
  then re-read the target (`:411`), `os.replace`, at most `WRITE_TRIES`
  (`:107`) recomputes.
- Vault confinement is `_vault_paths` (`:923`): realpath, `.obsidian/`
  required, relative `boardDir` without `..`, a string bare `board`,
  `commonpath` inside the vault (`:956`), the vault's device and inode
  recorded (`:948`), and each board or note file inside the worktree only when
  `git check-ignore` says ignored (`:967`, per file, so a vault that contains
  the repo is covered). It runs before either half writes. The write then
  pins its directory (`_pinned` `:1069`): where `_DIR_FD` (`:296`) holds,
  `_open_pinned` (`:999`) opens the checked vault (inode matched) and walks the
  real path's components with `_DIR_FLAGS` (`:291`, `O_DIRECTORY|O_NOFOLLOW`),
  every read, temp, replace and note create is relative to that fd, and
  `_pinned_check` (`:1025`) repeats the walk and matches device and inode
  before the temp, before the replace and after it, because the fd follows its
  directory if it is renamed out of the vault; a note written into a directory
  that left is unlinked through the fd (`_create_note_once` `:1111`).
  Elsewhere (Windows) `_parent_check` (`:1054`) re-checks the directory's
  realpath at the same three points.
- Card ownership on a shared board (`boardDir` unset): the ticket note's
  `repo-id:` (`_NOTE_REPO_ID` `:1154`, trailing `\r` excluded so a CRLF note
  reads as written; `_card_owner` `:1158` -> ours / foreign / unknown). The id
  is `repo_id` (`:530`): the origin URL through `normal_url` (`:491`,
  lowercased, `.git` stripped; an ssh origin - scp-style or a scheme in
  `_SSH_SCHEMES` `:488` - keeps its username and drops a password, every other
  scheme drops the whole userinfo); for a local origin (`_local_path` `:513`,
  a `file://` path percent-decoded as git decodes it), an absolute path's
  realpath, and for a relative one - `../origin/app.git` names a different
  repository from each checkout - the git common dir's realpath, as with no
  origin; `None` (git could not say) refuses via `_no_identity` (`:1187`).
  `_foreign` (`:1177`) refuses create, move and read; unknown refuses create
  and move with the `repo-id:` fix (`_unclaimed` `:1182`) and is a caveat on
  read. There is no claim by title: a card's text matching this repo's INDEX
  title is not an owner. `repo_name` (`:556`) is a human label only.
- The board is edited, never regenerated: `parse_board` (`:738`, lines split
  on LF alone by `_board_lines` `:697`; the done lane must carry exactly one
  `**Complete**`, `_complete_markers` `:777`), `find_card` (`:801`; a card is
  the first id on its first line), `move_card` (`:862`; a card already in its
  lane is repaired in place by `_checkbox` `:849`, which also gives a card
  with no box one (`_BOX` `:846`), and one above `**Complete**` in Done is
  moved below it), `add_card` (`:889`), written by `_board_write` (`:1083`).
  The ticket note (`_note_text` `:1102`) is an exclusive create
  (`_create_note_once` `:1111`, `_NOTE_FLAGS` `:290`).
- Called by `brainstorm.md:28` and `:81`, `spec.md:46`, `plan.md:60`,
  `implement.md:36` and `:110`, `done.md:63` and `fix.md:27`, `:73`, `:81`,
  `:89`, `:91` (all under `plugin/crew/commands/`); brainstorm and fix take
  the next free id on `id taken`, stop on any other failed `create`, and
  create the ticket folder only after a `create` that succeeded;
  `jira-sync.md` and `sdp-sync.md` honour `--to`; `crew_status.py` prints its
  tracker line from `resolve` (`plugin/crew/hooks/scripts/crew_status.py:63`).
- Tests: `plugin/crew/tests/test_crew_tracker.py`, fixtures under
  `plugin/crew/tests/tracker_fixtures/`, 81 mutations in
  `plugin/crew/tests/sabotage_tracker.py` (two of them RED only as root: the
  owner tests skip without it); one `.crew/verify.json` rule (`:309-316` since T-0010's rule 28 went in above it; `:302-309` after T-0018 landed, `:301-308` before).
  JUDGEMENT: the Kanban plugin's acceptance of the edited board was checked by
  byte comparison only, never by opening Obsidian.

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

- `/crew:implement` step 6 (`plugin/crew/commands/implement.md:89-111`) runs
  it after `/crew:docs` and before `/crew:review` (`:96`), runs each named
  refresh, commits, and re-runs until `fresh`; a `stop` ends the loop.
- `/crew:done` Check 4 (`plugin/crew/commands/done.md:46-57`) runs it again
  and refuses on `stale` or `unknown` without refreshing (`:52-55`).
- `REFRESH_ARTIFACT_PATHS` (`plugin/crew/hooks/scripts/crew_refresh_check.py:168-173`: the code map,
  `docs.diagramsDir`, `graph.out`, `.claude/rules`) is the one definition.
  The scope guard (`_refresh_artifact`,
  `plugin/crew/hooks/scripts/scope_guard.py:209-220`) and the completion audit
  (`_outside_refresh_artifacts`,
  `plugin/crew/hooks/scripts/completion_audit.py:177-187`) let a ticket write
  those paths without a Touch entry **only while its approval is current**;
  with no current approval nothing is exempt.
- Tests: `plugin/crew/tests/test_refresh_check.py`,
  `plugin/crew/tests/test_scope_guard_refresh_artifacts.py`,
  `plugin/crew/tests/test_completion_audit_refresh_artifacts.py`, with mutations in
  `plugin/crew/tests/sabotage_refresh.py`; `.crew/verify.json:264-280` (rule
  25) maps them, `implement.md`, `done.md`, and since review round 3
  `scope_guard.py`, `completion_audit.py`, `crew_freshness.py` and
  `scope_base.py` with their own suites, to one pytest rule. Confirmed
  present, **not run and not read** by this note.

`docs/diagrams/process-crew-lifecycle.mmd` drew `/crew:done` as "all three
or nothing" at `adf8d1dd`; T-0008's refresh commit `b7b02842` redrew it as
"all four or nothing" (its `:165`).

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:996` — `TRIGGERS`, a 15-entry
  tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2905` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:240` / `:393` —
  `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2444` — `_RATCHETED`, the
  14-key ratchet table (seven construction steps).
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
- `plugin/crew/hooks/scripts/crew_resume.py:667` — `decide`, read-only;
  `main()` is the `decide` / `record` / `precompact` CLI.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:576` — `ticket_freshness`,
  the library entry point; `main()` at `:676`.
- `plugin/crew/hooks/scripts/crew_autopilot.py:516` — `next_phase`, read-only;
  `main()` at `:1347` is the `next` / `resume` / `settings` / `stops` /
  `route` / `status` / `approve` / `questions-check` CLI
  `plugin/crew/commands/autopilot.md` calls.
- `plugin/crew/hooks/scripts/crew_route.py:210` — `decide`, read-only
  route / ask / none for a prompt; `main()` at `:332` is the `settings` /
  `decide` CLI. Its hook caller is `crew_context.route_item`
  (`plugin/crew/hooks/scripts/crew_context.py:838`).
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
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1250-1255`)
  — 4 roles, all tiered, none a specialist.
- `crew_state.PM_DEFAULTS` (`:1104-1117`) and `crew_state.AUTHORITY_DEFAULT`
  (`:1062`) — the unnamed session's own dispatch authority.
- `crew_state.AUTOPILOT_DEFAULTS` (`:1094`) — the repo-only `autopilot` block, with T-0010's
  `approval` and `questions` keys.
- `crew_guards.ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:195-196`)
  — 10 guard names across 4 vocabularies.
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
  their module docstrings, not their function bodies (`crew_ticket.parse_risk`
  excepted, read in full at `07ca3972`).
- The 11 `.ps1` hooks' bodies past their `Resolve-CrewPython` definitions
  were not read; whether any PowerShell-side equivalent of the bash parity
  test exists is unknown.
- `plugin/crew/evals/pm-*`, `developer-*` and `qa-reviewer-stays-read-only`
  fixture contents were not read; whether they were internally updated to
  target the 1.0 roster is unverified.
- The previous anchor's wide count-disagreement sweep (README.md,
  plugin/README.md, INSTALLATION.md, both install scripts, against the
  4/35/29 inventory above) was **not repeated** this pass — only
  `.claude-plugin/marketplace.json`'s own crew entry was checked, and found
  current. Both install scripts changed between `a0c0847e` and `07ca3972`;
  their counts were not re-read.
- `crew_autopilot.py` was read at its docstring, constants, `settings`,
  `stops` and `next_phase`'s docstring only; `_phase`, `_review_phase` and
  `resume_target`'s bodies were not read, and no autopilot test was run.
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

## Re-anchor provenance - `8d447a7d` -> `c35edda5`, 2026-09-25 (T-0034)

`8d447a7d` was rebase-merged to `main` as `95120430`; `git diff --name-only 8d447a7d 768a747a`
returns only code-map, diagram, rule and graph files plus the crew 1.0.37 release bookkeeping, so
`768a747a` stands in for it. `git diff --name-only 768a747a c35edda5` returns
`.claude-plugin/marketplace.json`, `.gitattributes`, `CHANGELOG.md`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/hooks/scripts/crew_refresh_check.py` and
`plugin/crew/tests/test_completion_audit.py`. This note cites `marketplace.json` and `crew_refresh_check.py` of those; each citation was
re-read with `grep -n`/`sed -n`:

- `crew_refresh_check.py` - `:363` reworded in place (`rel.split("/", maxsplit=1)[0]`, pylint
  C0207, same result), line count unchanged. `:1-8`, `:152-154`, `:168-173`, `:181`,
  `_named_behind` `:537`, `_unconfirmed` `:554`, `ticket_freshness` `:576` and `main()` `:676`
  all hold.
- `marketplace.json` - crew `version` `:218` (now 1.0.38) only; `:217`'s 4/34/29 counts are
  unchanged.
- `.gitattributes`, `test_completion_audit.py` - not cited by this note.

`crew_upgrade.py --root . --derived <one-entry json> --force` printed `not a crew repo`: this
worktree has no `.crew/config.json`, so it reconciled nothing and wrote nothing. This pass is the
per-path re-verify above, re-anchored by hand.

## Re-anchor provenance - `c35edda5` -> `8ebbdedc`, 2026-09-26 (T-0026 landing)

`8ebbdedc` is the crew 1.0.39 bump on top of the T-0026 merge (`563f54c3`). Of the paths this
note cites, `git diff --name-only c35edda5 8ebbdedc` returns `.claude-plugin/marketplace.json`,
`.crew/verify.json`, `TODO.md`, `plugin/crew/commands/approve.md`, `done.md`, `implement.md`,
`plan.md` and `plugin/crew/hooks/scripts/crew_ticket.py`. Each citation into them was re-read
with `grep -n`/`sed -n`:

- `approve.md` - `:13` now says the receipt is bound to "the digest of both files", not their
  sha256; `:5` and `:7-16` hold. The table row is corrected above.
- `plan.md` - `:8-9` holds; `:59-61` now set `spec.md`'s status, not `plan.md`'s.
- `implement.md` - step 7 (`:106-111`) gained one line saying the status edit keeps the
  approval; `:8-9` and step 6 `:85-104` hold.
- `done.md` - step 1 gained one line (`:61-62`); `:7-8`, check 4 `:46-57` and `:52-55` hold.
- `.crew/verify.json` - T-0026's rule inserted at `:167-172` as rule 10, so rule 22 -> 23
  (`:244` -> `:251`) and rule 23 -> 24 (`:245-261` -> `:252-268`); corrected above.
- `crew_ticket.py` - read at its module docstring only, as before; the "approval receipt"
  section now describes the `crew-approval/2` digest. No line of it is cited here.
- `marketplace.json` - crew `version` `:218` (now 1.0.39) only; `:217`'s 4/34/29 counts are
  unchanged.
- `TODO.md` - one entry marked CLOSED by T-0026 at `:5018`; `:3945` holds.

## Re-anchor provenance - `8d447a7d` -> `6d35ef8c`, 2026-09-26 (T-0006)

`8d447a7d` is T-0008's pre-rebase commit; its tree matches `origin/main` `768a747a` for every
path this note cites. `git diff --name-only 8d447a7d 6d35ef8c -- <the paths this note cites>`
returned T-0006's own files: `.claude-plugin/marketplace.json`, `.crew/verify.json`, `TODO.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_context.py`,
`plugin/crew/hooks/scripts/crew_state.py`, `plugin/crew/CONFIG.md` and `plugin/crew/README.md`.
Every citation into them was re-mapped with a line diff and re-read with `grep -n`:

- `crew_state.py` - `RESUME_DEFAULTS` inserted at `:684`, so everything below moved +10
  (`TRIGGERS` `:983` -> `:993`, `ROLE_TIERS` `:1225-1230` -> `:1235-1240`, `PM_DEFAULTS`,
  `AUTHORITY_DEFAULT`, `normalise_authority`, `known_role`, `evaluate_triggers`, the `:3270`
  hunk). `:643` and the lines above it hold.
- `crew_config.py` - a `resume` block added inside `default_config()` (+5 at `:301`) and
  `default_global_config()` (+4 at `:498`), so `default_global_config()` `:367` -> `:372` and
  `_RATCHETED` `:2342` -> `:2351`; `default_config()` `:239` holds.
  Leaf counts re-executed, above.
- `crew_context.py` - `load_crew_config` `:121-132` holds; the SessionStart branch is described
  in the new auto-resume section.
- `TODO.md` - one entry added at the top, so `:3945` -> `:3952`.
- `.crew/verify.json` - one rule appended last (rule 24); rules 0-23 and their lines hold.
- `marketplace.json` - crew `version` only (1.0.40); `:217`'s counts still match disk.
- `CONFIG.md`, `README.md` - cited by name only here.

## Re-anchor provenance - `6d35ef8c` -> `2bb92f32`, 2026-09-26 (T-0006 review round 3)

`git diff --name-only 6d35ef8c 2bb92f32 -- <the paths this note cites>` returned
`.crew/verify.json`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_resume.py` and the three T-0006 test files; the version files
(`.claude-plugin/marketplace.json`, `plugin/crew/.claude-plugin/plugin.json`) end where they
started, at 1.0.40. Every citation into them was re-mapped with a line diff and re-read with
`grep -n` at `2bb92f32`:

- `crew_resume.py` - the ticket-id regex gained a comment line (+1 from `:75`), and
  `_read_state` / `_entry` / `_already` grew above `progress_fingerprint`: `parse_resume`
  `:83` -> `:84`, `settings` `:157` -> `:158`, `write_precompact_record` `:296` -> `:333`,
  `_compact_was_manual` `:354` -> `:391`, `decide` `:374` -> `:411`, `record_run` `:434` ->
  `:469`; `RESUME_COMMANDS` `:37` holds.
- `.crew/verify.json` - rule 24's `seconds` and `why` only; it is still the last rule, and no
  rule's lines moved.
- `CONFIG.md`, `README.md`, the test files - cited by name only.

## Re-anchor provenance - `8ebbdedc` + `2bb92f32` -> `a0c0847e`, 2026-09-26 (T-0006 landing)

`a0c0847e` is the crew 1.0.40 bump on top of `1cec9572`, the merge of T-0006 (`cb125d51`, whose
code-map anchor was `2bb92f32`) into main at `d3844c76` (anchor `8ebbdedc`). Both anchors' notes
were joined in the merge; the provenance sections above record each line separately. Of the paths
this note cites, `git diff --name-only 8ebbdedc a0c0847e` returns T-0006's files and
`git diff --name-only 2bb92f32 a0c0847e` returns T-0026's and T-0034's. A citation can only be wrong at
the merge when the file changed on both sides, or when a line from one side cites a file the other
side changed. Each such citation was re-read with `grep -n`/`sed -n` at `a0c0847e`:

- `.crew/verify.json` - changed on both sides. T-0026's rule 10 (`:167-172`) and T-0006's rule
  (appended last) both landed, so T-0006's rule is **rule 25** at `:270-280`, not rule 24 as its
  branch numbered it; corrected in the auto-resume section above. Rule 23 `:251` and rule 24
  `:252-268` hold. 26 rules, 285 lines.
- `TODO.md` - changed on both sides; `:3952` still reads "`/crew:init` still writes
  `.crew/config.json`...", unchanged, because T-0026's closure is below it (`:5025`, `:5018` on main before T-0006's seven lines above it).
- `plan.md`, `approve.md`, `implement.md`, `done.md`, `crew_refresh_check.py`, `crew_ticket.py` -
  changed on main only; T-0006 cites none of them, and main's citations (`:8-9`, `:5`, `:85-104`,
  `:46-57`, `:168-173`, `:576`) stand at `a0c0847e`.
- `crew_state.py`, `crew_config.py`, `crew_context.py`, `CONFIG.md`, `crew_resume.py` - changed on
  T-0006 only; its round-3 citations stand, and main's lines citing them were already re-mapped on
  T-0006's branch before the merge.
- `marketplace.json` - crew `version` `:218` is 1.0.40; `:217`'s 4/34/29 counts are unchanged.

`crew_refresh_check.py --root . --ticket T-0006` named this note; nothing was executed for it
beyond the re-reads above.

## Re-anchor provenance - `a0c0847e` -> `07ca3972`, 2026-09-26 (T-0004)

Of the paths this note cites, `git diff --name-only a0c0847e 07ca3972` returns
`.claude-plugin/marketplace.json`, `.crew/codemap/INDEX.md`, `.crew/verify.json`, `README.md`,
`TODO.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/commands/migrate.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `crew_migrate.py`, `crew_state.py`, `crew_ticket.py`
and both `scripts/install-prerequisites.*`. Each citation into them was re-read with
`grep -n`/`sed -n` at `07ca3972`:

- `crew_state.py` - `AUTOPILOT_DEFAULTS` and its comment inserted at `:1081-1088`, so everything
  below moved +8: `PM_DEFAULTS` `:1089-1102` -> `:1097-1110`, the roster comment `:1226-1231` ->
  `:1234-1239`, `ROLE_TIERS` `:1235-1240` -> `:1243-1248`, `SPECIALIST_ROLES` `:1250` -> `:1258`,
  `known_role` `:1253-1262` -> `:1261-1270`, `normalise_authority` `:1282-1293` -> `:1290-1301`,
  `evaluate_triggers` `:2890` -> `:2898`, the `--record-scan-artifact` exit-3 branch
  `:3280-3286` -> `:3288-3294`. `SCHEMA_CURRENT` `:175`, `TRIGGERS` `:993`, `AUTHORITY_DEFAULT`
  `:1059` and `AUTONOMOUS_STOPS` `:1072-1079` hold.
- `crew_config.py` - the `autopilot` block inserted at `:369-374` inside `default_config()`:
  `default_global_config()` `:372` -> `:378`, the `.crew/config.json` read `:1167` -> `:1173`,
  `_RATCHETED` `:2351-2440` -> `:2357-2446` (literal `:2351-2362` -> `:2357-2368`, still 13 keys).
  `default_config()` `:239` and the docstring `:1` hold. Leaf counts re-executed: 117/66/51 ->
  119/66/53.
- `crew_migrate.py` - the `notes` sentence at `:36` grew a line, so the schema table `:26-40` ->
  `:26-41`; `:1-4`, `:11` and `:26` hold.
- `migrate.md` - `:25-26` reworded in place (the autonomous note now names `/crew:autopilot`);
  `:78` holds.
- `crew_ticket.py` - `parse_risk` added at `:505`; no line of this file was cited before.
- `.crew/verify.json` - rule 26 (T-0004) appended at `:281-288`; rule 25 `:270-280` holds but is
  no longer the last. Rules 23 `:251` and 24 `:252-268` hold. 27 rules, 293 lines.
- `TODO.md` - seven lines inserted after `:4142`; `:3952` holds.
- `marketplace.json` - `:217` now says 35 commands (was 34), `:218` is 1.0.41; both match disk
  and `plugin/crew/.claude-plugin/plugin.json:3`.
- `INDEX.md` - still assigns landmines to `CLAUDE.md` (`:184`).
- `CONFIG.md`, `plugin/crew/README.md`, `README.md`, the install scripts - cited by name only.

New since `a0c0847e`, not re-anchored from anything: the `/crew:autopilot` section and its
entry point, and `crew_autopilot.settings`'s place in the config-authority section.

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

Then `a26ad8c0` -> `02d1513b` (T-0005 review round 7): `git diff --name-only a26ad8c0 02d1513b
-- <the paths this note cites>` returns `cloud_guard.py`, `crew_guards.py`, the version files
(stepped back to 1.0.37 and re-set to 1.0.41, byte-identical to `a26ad8c0`) and, under
`plugin/crew/**`, the round-7 tests and the Windows tfplan shim. In `cloud_guard.py` the first
change is the `crew_guards` import at `:129`, so `:1-6` and `:33-55` hold; `_tf_skip_options` moved
into `crew_guards` as `tf_skip_options` (`:1541`), `_terraform_destructive` `:1559` -> `:1540`,
`_GATE_HELPERS` `:2798` -> `:2780`, `_literal_gate` `:2802` -> `:2784`, its call `:2851` -> `:2833`,
`_terraform_verdict` `:2993` -> `:2975`. In `crew_guards.py` the first change is at `:1533`, so
everything the note cites above it holds (re-read); `_tf_read_only` `:1533` -> `:1585`,
`_argv_trigger` `:1585` -> `:1642`, `_copies_terraform` `:1662` -> `:1720`, `_ps_argv_trigger`
`:1725` -> `:1783`, `ps_trigger` `:1778` -> `:1849`, `command_trigger` `:1802` -> `:1873`,
`command_names_terraform` `:1813` -> `:1884`; `skip_wrapper_options` (`:1560`) is new. Re-taken by
content, corrected above.

## Re-anchor provenance - `6f96e627` + `02d1513b` -> `2b18f7ab`, 2026-09-26 (T-0005 landing)

`2b18f7ab` is the crew 1.0.42 bump on top of `4ed4b763`, the merge of T-0005 (`4e0abc8f`) into
main at `1e0706ac`. Both lines' provenance is above, side by side. A citation can only be wrong at
the merge when its file changed on both sides, or when a line from one side cites a file the other
side changed; each such citation was re-mapped with a line diff of the cited file and re-read with
`grep -n`/`sed -n` on the merged tree. The bump commit replaced `1.0.41` with `1.0.42` in place in
the version files and in T-0005's own version statements (no line added or removed, except one
line in `CHANGELOG.md`'s T-0005 bump note).

- `crew_state.py` - changed on both sides. Main's citations below T-0005's three import lines moved
  +3: `SCHEMA_CURRENT` `:175` -> `:178`, `TRIGGERS` `:993` -> `:996`, `AUTHORITY_DEFAULT` `:1059` ->
  `:1062`, `AUTONOMOUS_STOPS` `:1072-1079` -> `:1075-1082`, the autopilot comment `:1081-1086` ->
  `:1084-1089`, `AUTOPILOT_DEFAULTS` `:1087` -> `:1090`, `PM_DEFAULTS` `:1097-1110` -> `:1100-1113`,
  the roster comment `:1234-1239` -> `:1237-1242`, `ROLE_TIERS` -> `:1246-1251`, `SPECIALIST_ROLES`
  -> `:1261`, `known_role` -> `:1264-1273`, `normalise_authority` -> `:1293-1304`,
  `evaluate_triggers` `:2898` -> `:2901`, the exit-3 branch `:3288-3294` -> `:3291-3297`, the
  roster/config block read in full `:993-1360` -> `:996-1363`.
- `crew_config.py` - changed on both sides: `default_config()` `:240` (T-0005's number) holds,
  `default_global_config()` -> `:385`, the `autopilot` block `:369-374` -> `:376-381`, the
  `.crew/config.json` read -> `:1249`, `_RATCHETED` -> `:2433-2545` (literal `:2433-2444`,
  `.update()` calls `:2448`, `:2461`, `:2472`, `:2482`, assignments `:2518`, `:2541`; 14 keys, seven
  construction steps). Leaf counts re-executed: 121 / 67 / 54 / 0.
- `crew_guards.py`, `cloud_guard.py`, `crew_tfplan.py` - changed on T-0005 only, so its citations
  stand; main's guard-vocabulary range `:91-505` is `:92-538` on the merge.
- `.crew/verify.json` - changed on both sides. T-0005's cloud-guard rule is rule 6 (`:117-127`), so
  main's rules from 6 on are one higher: the `.claude/rules/` check is **rule 24** (`:263`), the
  refresh-check suite **rule 25** (`:264-280`), auto-resume **rule 26** (`:282-292`) and
  autopilot **rule 27** (`:293-300`). 28 rules, 305 lines. Corrected above.
- `test_crew_config.py` - both sides edited the leaf-count assertion; the merge asserts 121 at `:277`.
- `CHANGELOG.md` - the T-0004 leaf-count sentence is corrected above; T-0005's 1.0.42 entry sits
  above T-0004's 1.0.41.
- `marketplace.json` - `:217` is main's (35 commands), `:218` is 1.0.42; both match disk
  (`ls plugin/crew/commands/*.md` 35, agents 4, skills 29) and `plugin/crew/.claude-plugin/plugin.json:3`.
- `TODO.md` - T-0005's lines are appended at the end; `:3952` holds.
- `CONFIG.md`, `plugin/crew/README.md`, the crew-cloud skill - cited by name or section only.

`crew_refresh_check.py --root . --ticket T-0005` named this note. No suite was executed for it; the
landing's suite results are in its PR.

## Re-anchor provenance - `6f96e627` -> `068db4ff`, 2026-09-26 (T-0042)

`6f96e627` is T-0004's landing of `07ca3972`; `git diff --name-only 6f96e627 1e0706ac` returns
only refresh artifacts (`.claude/rules/`, `.crew/codemap/`, `docs/diagrams/`, `graphify-out/`),
so every citation above held at `1e0706ac`. Of the paths this note cites,
`git diff --name-only 1e0706ac 068db4ff` returns `.claude-plugin/marketplace.json`,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md`, `plugin/crew/.claude-plugin/plugin.json`,
`plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `crew_context.py`, `crew_resume.py`, both
`handoff-write` flavours and the three auto-resume test files. Each line citation into them was
re-mapped through the `-U0` hunks of that diff and re-read with `sed -n` at `068db4ff`:

- `crew_resume.py` - rewritten in the auto-resume section above, not re-pointed: T-0042 added
  the author binding (`AUTHOR_FILE` `:72`, `session_process` `:220`, `record_author` `:270`,
  `_author_refusal` `:386`), `_absent` `:331`, the `.stuck` marker (`:529`, `:537`) and the
  skeleton refusal in `parse_resume` (`:102-103`). Moved: `parse_resume` `:84` -> `:91`, the
  ticket regex `:76` -> `:83`, `settings` `:158` -> `:172`, `_read_state` `:190` -> `:348`,
  `_entry` `:209` -> `:370`, `_already` `:224` -> `:416`, `write_precompact_record` `:333` ->
  `:554`, `_compact_was_manual` `:391` -> `:620`, `decide` `:411` -> `:644`, `record_run`
  `:469` -> `:705`. `RESUME_COMMANDS` `:37` holds.
- `crew_context.py` - `record_handoff_author` (`:615`) and `_record_author_logged` (`:987`) are
  new; `_handoff_verdict` `:604` -> `:638`, `resume_decision` `:627` -> `:661`, `resume_line`
  `:653` -> `:687`. `load_crew_config` `:121-132` holds.
- `.crew/verify.json` - rule 25's `seconds` and `why` changed in place; `:270-280` holds, as do
  `:251`, `:252-268` and rule 26 `:281-288`.
- `TODO.md` - eleven lines inserted above; `:3952` -> `:3963`, same bullet re-read.
- `CHANGELOG.md` - the 1.0.42 entry inserted at the top; the "116 -> 118" line `:65` -> `:101`.
- `marketplace.json` / `plugin.json` - crew `version` only, now 1.0.42 (`:218`, `:3`); `:217`'s
  4/35/29 counts still match disk.
- `handoff-write.sh` / `.ps1` - cited by name, plus the `.stuck` lines added to the section above.
- `CONFIG.md`, `plugin/crew/README.md`, the test files - cited by name only.

New since `6f96e627`, not re-anchored from anything: the handoff-author binding and `.stuck`
marker paragraphs of the auto-resume section.

## Re-anchor provenance - `068db4ff` -> `07eefac5`, 2026-09-26 (T-0042 review round 1)

`07eefac5` is the crew 1.0.42 re-set after the round-1 fixes. Of the paths this note cites,
`git diff --name-only 068db4ff 07eefac5` returns `crew_resume.py`, `sabotage_resume.py`,
`test_crew_resume.py`, `.crew/verify.json`, `CHANGELOG.md` and the refresh artifacts; the version
files were stepped to 1.0.41 and back, so they read as they did. Each line citation into them was
re-mapped through the `-U0` hunks and re-read with `sed -n` at `07eefac5`:

- `crew_resume.py` - `record_author`'s docstring (+7), its lock branch (+2), its cleanup (+1)
  and `_drop_author` (+4) sit between `:283` and `:331`, so every citation below moves +14:
  `_absent` `:331` -> `:345`, `_read_state` `:348` -> `:362`, `_entry` `:370` -> `:384`,
  `_author_refusal` `:386` -> `:400`, `_already` `:416` -> `:430`, `_index_rows` `:443` ->
  `:457`, `stuck_path` `:529` -> `:543`, `_mark_stuck` `:537` -> `:551`,
  `write_precompact_record` `:554` -> `:568`, `_compact_was_manual` `:620` -> `:634`, `decide`
  `:644` -> `:658`, `record_run` `:705` -> `:719`. `settings` `:172`, `session_process` `:220`
  and `record_author` `:270` hold; `_drop_author` `:331` is newly cited.
- `sabotage_resume.py` - 69 mutations by `len(RESUME_MUTATIONS)`.
- `CHANGELOG.md` - seven lines added inside the 1.0.42 entry; the leaf-count line `:101` ->
  `:108`, and re-reading it found "117 -> 119", not the "116 -> 118" this note had quoted -
  `6f96e627` corrected it before the previous anchor, so that sentence was already stale there.
- `.crew/verify.json` - rule 25's `seconds` and `why` changed in place; 293 lines, every cited
  range stands.
- `test_crew_resume.py` - cited by name only.

## Re-anchor provenance - `2b18f7ab` + `07eefac5` -> `53f5482c`, 2026-09-27 (T-0042 merges main)

`53f5482c` is T-0042's rule-26 re-measure on top of `b7727a88`, the merge of origin/main `502cb137`
(T-0005 landed; `2b18f7ab..502cb137` touched refresh artifacts only) into T-0042's branch, plus
`03cfab27` (a partial `resume-state.json` is an unknown) and `52778dd1` (crew 1.0.43). Both lines'
provenance is above. Main-side citations were mapped through `git diff -U0 2b18f7ab 53f5482c`, the
branch-side ones through `git diff -U0 07eefac5 53f5482c`, and every moved one re-read with `sed -n`
on `53f5482c`:

- `crew_resume.py` - changed on T-0042 only. `_entry` grew (+9 inside it), so everything below
  `:384` moved: `_author_refusal` `:400` -> `:409`, `_already` `:430` -> `:439`, `_index_rows`
  `:457` -> `:466`, `stuck_path` `:543` -> `:552`, `_mark_stuck` `:551` -> `:560`,
  `write_precompact_record` `:568` -> `:577`, `_compact_was_manual` `:634` -> `:643`, `decide`
  `:658` -> `:667` (the auto-resume paragraph still said `:644`, the `068db4ff` number; corrected),
  `record_run` `:719` -> `:728`. `:37`, `:83`, `:91`, `:102-103`, `:172`, `:220`, `:270`, `:331`,
  `:345`, `:362`, `:384` hold. The partial-state sentence is new.
- `crew_context.py` - changed on T-0042 only, not since `07eefac5`; `:615`, `:638`, `:661`,
  `:687`, `:962`, `:987` hold.
- `CHANGELOG.md` - T-0042's entry (48 lines) sits above T-0005's; main's `:228-229` -> `:276-277`.
- `.crew/verify.json` - rule 26's `why`/`seconds` in place; `:282-292` holds. 28 rules, 305 lines.
- `TODO.md` - T-0042's eleven lines above, T-0005's appended; `:3963` holds.
- `marketplace.json` / `plugin.json` - `:218` / `:3` now 1.0.43; `:217` unchanged.
- `sabotage_resume.py` - 72 mutations (three added for the partial state).

## Re-anchor provenance - T-0010-solo's branch line, `2b18f7ab` -> `50e67586`, 2026-09-27 (crew 1.0.43 on its branch)

T-0010's code commit was cherry-picked off `origin/main` (`502cb137`) as `0fc5b069`, apart from
T-0018 and T-0024, and the version set in `50e67586`. Every `path:line` citation this note makes into
a path T-0010 changed was mapped from the `2b18f7ab` tree with `difflib`; each one that moved
was re-pointed and compared line for line with the anchor tree at `50e67586`.

- `crew_state.py` - `AUTOPILOT_DEFAULTS` grew a comment and two keys (`:1090` -> `:1094`);
  every later citation moved by 4 (`:1237-1242`, `:1246-1251`, `:1261`, `:1264-1273`,
  `:1100-1113`, `:1293-1304`, `:2901`, `:3291-3297`), content identical.
- `crew_autopilot.py` - T-0010's docstring section and policy functions were inserted, so the
  autopilot paragraph's citations were re-derived with `grep -n`: docstring `:1-104`, table
  `:41-64`, `FIXED_STOPS` `:142`, `PROCEDURE_STOPS` `:159`, `HUMAN_STOPS` `:165`, `next_phase`
  `:480`, `resume_target` `:551`, `settings` `:621`, `stops` `:925`, `main` `:964`; 1022 lines.
  T-0010's own symbols are newly cited in the T-0010 paragraph.
- `crew_ticket.py` - `parse_risk` `:505` -> `:509`. `scope_guard.py` - `:186-197` -> `:201-212`.
- `autopilot.md` - 118 lines (120 before); `:4`, `:13-20` and the branch/head rule `:29-30` hold.
- `test_crew_config.py` - the leaf-count assertion is `:280` (123); leaf table re-executed
  (123 / 67 / 56 / 0). `CHANGELOG.md` - T-0004's leaf sentence `:228-229` -> `:256-257`.
- `.crew/verify.json` - rule 27 `:293-300` holds (its last line gained a comma); T-0010's rule
  28 is `:301-306`. `marketplace.json:218`, `plugin.json:3` - 1.0.43.

## Re-anchor provenance - `53f5482c` + `50e67586` -> `89c9ee9a`, 2026-09-27 (T-0010-solo merges main, crew 1.0.44)

`89c9ee9a` is T-0010's crew 1.0.44 version commit on top of `132c1758`, the merge of origin/main
`f0b12ee6` (T-0042 landed at 1.0.43) into T-0010-solo. Both lines' provenance is above. Main-side
citations were mapped through `git diff origin/main 89c9ee9a`, the branch-side ones through
`git diff 708db116 89c9ee9a`, with `difflib` over every repo-relative `path:line` citation, and
every moved or merge-set one re-read with `sed -n` at `89c9ee9a`:

- `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py` and the T-0010 tests -
  changed on T-0010 only; the branch's citations (`next_phase` `:480`, `main` `:964`,
  `parse_risk` `:509`, `AUTOPILOT_DEFAULTS` `:1094`) hold.
- `crew_resume.py`, `crew_context.py`, `handoff-write.*`, `sabotage_resume.py` - changed on T-0042
  only; main's citations (`decide` `:667`, `:615`, `:638`, `:661`, `:687`) hold; 72 mutations.
- `CHANGELOG.md` - T-0010's entry moved above T-0042's as 1.0.44, so T-0004's leaf sentence is
  `:307-308` (`:304-305` on the merge). Corrected above.
- `.crew/verify.json` - both sides' rules merged: 29 rules, 311 lines; rule 26 `:282-292`,
  rule 27 `:293-300`, rule 28 `:301-306`.
- `test_crew_config.py:280` still asserts 123 (T-0042 adds no config key), so the leaf table's
  123 / 67 / 56 / 0 stands; not re-executed on the merge.
- `marketplace.json:218`, `plugin.json:3` - 1.0.44; `:217`'s 4/35/29 counts unchanged. Corrected
  above.

## Re-anchor provenance - `89c9ee9a` -> `8314d670` -> `35fcebcb`, 2026-09-27 (T-0010 review round 1 fixes)

`8314d670` fixes the four FIX findings of T-0010's review round 1. Its citations were checked
per path through `git diff 89c9ee9a 8314d670`, every moved one re-read with `grep -n`/`sed -n`
at `8314d670`:

- `crew_autopilot.py` (1034 lines) - the module docstring grew three lines, so the `next` table
  is `:44-67` and the docstring `:1-107`; `next_phase` `:480` -> `:484`, `resume_target` `:555`,
  `settings` `:625`, `_ticket_risk` `:680`, `approval_policy` `:708`, `question_policy` `:746`,
  `_approval_hint` `:771`, `_question_hint` `:780`, `approve` `:786`, `QUESTIONS_SHAPE` `:808`,
  `questions_check` `:900`, `stops` `:937`, `main` `:976`; `FIXED_STOPS` `:145`,
  `PROCEDURE_STOPS` `:162`, `HUMAN_STOPS` `:168`. The T-0010 paragraph's claims changed with the
  code: a NEEDS_REPLAN ledger no longer refuses, and a `taken:` line's policy is history.
- `scope_guard.py` (445 lines at `35fcebcb`, which split each reading's checks into
  `_reading_refusal` `:281`) - `_AUTOPILOT_APPROVE_RE` / `_AUTOPILOT_BARE_RE` `:118-122`, the
  two continuation regexes `:126-127`, `_refresh_artifact` `:201-212` -> `:209-220`,
  `_autopilot_refusal` `:237`, `_joined` `:257`, `shell_refusal` `:265`.
- `autopilot.md` - 119 lines; `:4`, `:13-20` and `:29-30` sit above the edit and hold.
- `CHANGELOG.md` - T-0010's entry grew, so T-0004's leaf sentence is `:315-316`.
- `sabotage_autopilot.py` - `POLICY_MUTATIONS` still `:167`, now 33 entries; `AUTOPILOT_MUTATIONS`
  31. `README.md` and `CONFIG.md` changed in place or below every line cited here.
- `6fa7fb13` changed one test in `test_crew_autopilot_policy.py` (cited by name only); no claim
  moved. Re-anchored there.

## Re-anchor provenance - `c35edda5` -> `7b667587`, 2026-09-26 (T-0021)

`git diff --name-only c35edda5 7b667587` returns T-0021's code, prose and release files (listed in
its commits). This note cites five of them with a line; each was re-read with `grep -n`/`sed -n`:

- `implement.md` - the tracker call added to step 1 moved step 6 `:85-104` -> `:88-107` and its
  review line `:92` -> `:95`. `:8-9` holds.
- `.crew/verify.json` - one rule appended after rule 23 (now `:262-269`); rule 22 `:244` and rule
  23 `:245-261` hold (only its closing line gained a comma).
- `spec.md:7-8`, `plan.md:8-9`, `done.md:7-8` and `:46-57`, `fix.md:2` - above every T-0021 edit;
  hold.
- `marketplace.json:217` - the counts line, unchanged; crew's version (`:218`) is now 1.0.46.
- `TODO.md:3945` - T-0021 appended at the end of the file; holds.

New this pass: the "tracker interface" section above, read from source at `7b667587`.

## Re-anchor provenance - `7b667587` -> `385eadd5`, 2026-09-26 (T-0021 review round 1)

`git diff --name-only 7b667587 385eadd5` returns T-0021's refresh (`bc6432b1`), the version step-back (`764c2244`) and review round 1's fix commit (`385eadd5`): `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `brainstorm.md`, `obsidian-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set). This note cites `crew_tracker.py` and `brainstorm.md` with lines; both were re-read:

- `crew_tracker.py` - every line in the tracker-interface section was re-grepped at `385eadd5`
  (`def`/assignment lines) and rewritten; the section also gains the temp-file, ownership and
  card-owner mechanics the fix added. Mutation count 24 -> 42, counted from
  `TRACKER_MUTATIONS`.
- `brainstorm.md` - `:29` holds; the approval step now calls the tracker at `:80`.
- `marketplace.json:217` and `TODO.md:3945` - not in the diff's net change / above the T-0021
  edit at the end of `TODO.md`; hold.

## Re-anchor provenance - `385eadd5` -> `bcb77ce2`, 2026-09-26 (T-0021 review round 2)

`git diff --name-only 385eadd5 bcb77ce2` returns the round-1 refresh (`59de6d56`), the version
step-back (`f11c72d0`) and review round 2's fix commit (`bcb77ce2`): `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `fix.md`, `implement.md`, `jira-sync.md`,
`sdp-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The
version files net to no change (1.0.46 stepped back and re-set). This note cites three of them
with lines; each was re-read:

- `crew_tracker.py` - the tracker-interface section was rewritten from source at `bcb77ce2`,
  every line re-grepped (`def`/assignment lines); it gains repo identity, the effective-settings
  comparison, the held-id refusal, boundary-only Jira/SDP pushes, `STATUS_ORDER`/`--reopen` and
  the pinned-directory writes. Mutation count 42 -> 63, counted from `TRACKER_MUTATIONS`.
- `implement.md` - step 1's call holds at `:36` (one line added after it); step 6 is now
  `:89-111` with the refresh check at `:96` and the `--to review` call at `:109`, moved there
  from step 7 so the card reaches Review before `/crew:review`. `:8-9` holds.
- `fix.md` - `:2`, `:28`, `:69`, `:77` hold; the two step-4 calls, now prefixed, are `:85`
  and `:87`.

## Re-anchor provenance - `2b18f7ab` + `bcb77ce2` -> `c2ae46ab`, 2026-09-27 (T-0021 review round 3 and its merge of main)

The merge `86ea912f` joins main's `2b18f7ab` with T-0021's `bcb77ce2`; review round 3's fix commit
`629fb518` sits under it and the crew 1.0.43 bump `c2ae46ab` on top. `git diff --name-only 2b18f7ab
c2ae46ab` returns only T-0021's files (its code, commands, tests, fixtures, release files,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md`). Every citation in this note's body into those files
was re-mapped from the side of the merge its line came from (`git blame`: main's lines against
`2b18f7ab`, T-0021's against `bcb77ce2`) with a line diff, and each one whose line moved or changed
was re-read at `c2ae46ab`. Corrected here: the tracker section is re-derived at `c2ae46ab` for
review round 3 (the pinned directory re-walk, relative local origins, no title claim, `id taken`,
the wider `resolve` comparison, the board gated on the INDEX half, in-lane repair, one
`**Complete**`), every `crew_tracker.py` line in it re-grepped; its command call sites are
`brainstorm.md:28`/`:81`, `fix.md:27`/`:72`/`:80`/`:88`/`:90`, `implement.md:110` and `done.md:63`;
`crew_status.py`'s `_tracker_line` is `:63`; the tracker rule is `.crew/verify.json:301-308`; crew's
version at `.claude-plugin/marketplace.json:218` is 1.0.43. The lifecycle table's `spec.md`,
`plan.md`, `implement.md` and `done.md` line ranges were re-read and hold. No test suite was executed for
this note.

## Re-anchor provenance - `c2ae46ab` -> `5832b32a`, 2026-09-27 (T-0021 test escape)

`git diff --name-only c2ae46ab 5832b32a` returns the version files (stepped to 1.0.42 and re-set to
1.0.43, net unchanged), `TODO.md` (one follow-up appended) and
`plugin/crew/tests/test_crew_tracker.py`, where three lines now spell U+2028/U+2029 as escapes
instead of raw characters (the same strings at run time). This note cites that test file by name
only, so no citation moved. No test suite was executed for this note.

## Re-anchor provenance - `5832b32a` -> `d276b268`, 2026-09-27 (T-0021 review round 4)

`git diff --name-only 5832b32a d276b268` returns `plugin/crew/hooks/scripts/crew_tracker.py`,
`plugin/crew/commands/brainstorm.md`, `plugin/crew/commands/fix.md`, three test files
(`test_crew_tracker.py`, `test_lifecycle_commands.py`, `sabotage_tracker.py`),
`plugin/crew/README.md`, `CHANGELOG.md`, two guide sources with their six built outputs, and the
version files (stepped to 1.0.42 and re-set to 1.0.43, net unchanged). The tracker-interface
section was re-derived from source at `2a9e0989` (`crew_tracker.py` is identical at `d276b268`):
every line it cites was re-mapped with a line diff against `5832b32a`, and the new ones
(`_SSH_SCHEMES`, `_BOX`, `_index_holds`, `_lost_claim`, the claim at `:1245-1246`) were grepped.
Its command call sites: `brainstorm.md:28`/`:81` hold (the file kept its line count); `fix.md:27`
holds and `:72`/`:80`/`:88`/`:90` moved to `:73`/`:81`/`:89`/`:91`; `fix.md:2` holds. README,
CHANGELOG and the test files are cited by name only. No test suite was executed for this note.

## Re-anchor provenance - `d276b268` -> `d9cdb54c`, 2026-09-27 (T-0021 round-4 suite fixes)

`git diff --name-only d276b268 d9cdb54c` returns `plugin/crew/tests/sabotage_tracker.py`,
`plugin/crew/BUDGETS.md` and the version files (stepped to 1.0.42 and re-set to 1.0.43, net
unchanged). One mutation, "tracker rewrites an existing ticket note", now names
`test_create_loses_the_note_race_says_id_taken`: an existing note that is this repo's is not
re-created since round 4, so only the claim reaches the exclusive open. The count stays 81, and
this note cites the file by name only. No citation moved. No test suite was executed for this note.

## Re-anchor provenance - `f0b12ee6` + `74f52fae` -> `12682e41`, 2026-09-27 (T-0021 lands on T-0042's main)

`6df1231a` merges T-0021's reviewed head `74f52fae` into main `f0b12ee6` (T-0042 landed as crew
1.0.43, PR #242), and `12682e41` bumps crew to 1.0.44. The two sides share no source file: the
paths both changed since `502cb137` are `CHANGELOG.md`, `TODO.md`, `.crew/verify.json`,
`plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, the version files and
the refresh artifacts. The conflicting provenance sections keep both sides, T-0042's first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on the merge and corrected: the version,
1.0.44, at `.claude-plugin/marketplace.json:218` and `plugin/crew/.claude-plugin/plugin.json:3`;
T-0004's "117 -> 119" `CHANGELOG.md:276-277` -> `:390-391` (T-0021's entry now sits above
T-0042's). `.crew/verify.json` is 313 lines and 29 rules: rule 26 carries T-0042's pricing
(62s, `seconds`/`why` changed in place) and T-0021's tracker rule is rule 28 at `:301-308`.
`crew_resume.py`, `crew_context.py` and `crew_tracker.py` each changed on one side only, so
their citations stand. No test suite was executed for this note.

## Re-anchor provenance - `6f96e627` -> `eba11657`, 2026-09-26 (T-0023)

`6f96e627` -> `1e0706ac` changed only the refresh artifacts themselves (T-0004's refresh commit
and its merge). Of the paths this note cites, `git diff --name-only 1e0706ac eba11657` returns
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `crew_context.py`, `plugin/crew/tests/sabotage.py`
and `plugin/crew/tests/test_crew_config.py`. Every `path:line` citation into them was mapped
through a line-level diff of the two revisions and each moved or modified one re-read at
`eba11657`:

- `crew_config.py` - the `route` block inserted at `:375-382` (end of `default_config()`) and
  `:547-549` (end of `default_global_config()`): `default_global_config()` `:378` -> `:386`, the
  `.crew/config.json` read `:1173` -> `:1184`, `_RATCHETED` `:2357-2446` -> `:2368-2457` (still
  13 keys). `default_config()` `:239` and the autopilot line `:374` hold. Leaf counts
  re-executed: 119/66/53 -> 120/67/53.
- `crew_context.py` - `route_item` and its section header inserted at `:801-831` (`def` at
  `:804`) and called at `:902-904`; the log-keep condition became two lines at `:1019-1020`. `load_crew_config` `:121-132` and `resume_decision`'s call
  `:627` are above every hunk and hold.
- `test_crew_config.py` - the leaf-count assertion `:275` -> `:277` (now 120, and it also
  asserts `route.enabled` is declared at `:276`).
- `CHANGELOG.md` - the 1.0.42 entry inserted at the top, so T-0004's leaf-count line `:65` ->
  `:99`; re-read, it says "117 -> 119", which corrected this note's own misquotation above.
- `plugin.json:3` / `marketplace.json:218` - crew's `version` 1.0.41 -> 1.0.42, corrected in
  the Inventory paragraph; `:217`'s counts are unchanged (no command, agent or skill added).
- `.crew/verify.json` - rule 27 (T-0023) appended at `:289-297`; rule 26 `:281-288` holds but is
  no longer the last. 28 rules.
- `sabotage.py` - `ROUTE_MUTATIONS` imported at `:78` and appended at `:3050`.
- `CONFIG.md`, `plugin/crew/README.md`, `PLUGINS.md` - cited by name only here.

New since `6f96e627`, not re-anchored from anything: the plain-text routing section, its entry
point, and the `crew_route.settings` sentence in the config-authority section.


## Re-anchor provenance - `eba11657` -> `311388b7`, 2026-09-27 (T-0023)

Per-path re-verify. Of the paths this note cites, `git diff --name-only eba11657 311388b7`
returns only `plugin/crew/tests/test_crew_route.py` (its `_cli` helper now isolates `HOME` and
`USERPROFILE` for the child process). This note cites that file by name only, in the plain-text
routing section, so no citation moved. `plugin.json`, `marketplace.json` and `PLUGINS.md` were
stepped back and re-set to 1.0.42 twice in the range and are byte-identical to `eba11657`.

## Re-anchor provenance - `2b18f7ab` + `488053fc` -> `a1acd9b7`, 2026-09-27 (T-0023 merge of main)

`3c968175` merges main at `502cb137` (T-0005 landed, its notes anchored `2b18f7ab`) into T-0023 at
`488053fc` (review round 1's fixes); `f6abe8c1` re-sets crew to 1.0.43 and `a1acd9b7` re-prices
`.crew/verify.json` rule 28 in place. Both lines' provenance is above. A citation can only be
wrong at the merge when its file changed on both sides, or when a line from one side cites a file
the other side changed. Each line of this note was classified by origin (main's text or
T-0023's), its citations into such files re-mapped with a line diff from that side's revision to
the merged tree (`502cb137` or `fa4d8cd5`), and each moved one re-read by content with
`grep -n`/`sed -n`; citations the line diff attributed to the wrong file were discarded, not
applied. `crew_config.py` changed on both sides: `default_global_config()` `:393`, the `route` blocks `:389`/`:563`, the `.crew/config.json` read `:1260`, `_RATCHETED` `:2444-2556` (14 keys, re-counted). Leaf counts re-executed: 122 / 68 / 54 / 0. `test_crew_config.py` asserts 122 at `:279`. `.crew/verify.json` has 29 rules: autopilot rule 27 `:293-300`, routing rule 28 `:301-309`. `crew_route.py` changed in round 1 (`_clip`, `MAX_LINE_CHARS`), so the routing section's citations were re-taken by content (`PHRASES` `:81` through `main` `:332`). `CHANGELOG.md`'s T-0004 leaf-count line is `:273-274` after the 1.0.43 entry grew. `crew_state.py`, `crew_context.py`, `crew_guards.py` and `cloud_guard.py` changed on one side only, so those citations stand. The version is 1.0.43 (`marketplace.json:218`, `plugin.json:3`).

## Re-anchor provenance - `db14619c` + `ad74ed35` -> `e463ca53`, 2026-09-27 (T-0023 lands on T-0021's main)

`c68b40bd` merges origin/main `db14619c` (T-0042 landed as crew 1.0.43, PR #242; T-0021 as
1.0.45, PR #243) into T-0023's `ad74ed35`, and `e463ca53` bumps crew to 1.0.46. The files both
sides changed since `502cb137` are `CHANGELOG.md`, `.crew/verify.json`, `plugin/crew/README.md`,
`plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_context.py`,
`plugin/crew/tests/sabotage.py`, the version files and the refresh artifacts. The conflicting
provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every
bare `:N` that follows a path, was mapped from the side its line came from onto the merged tree
with a line diff (`git show <side>:<path>` against the merge); each one that moved was re-read
with `sed -n` and corrected, and hits the diff attributed to the wrong file (a bare `:N` after
an unrelated path) were discarded rather than applied: `crew_context.py`
carries T-0023's `route_item` hunk on main's tree, so main's `_record_author_logged` `:987` ->
`:1021` and `run` `:962` -> `:996`, and T-0023's `route_item` `:804` -> `:838`, its call `:902` ->
`:936` and the route-error log `:1020` -> `:1069`. `sabotage.py` imports `ROUTE_MUTATIONS` at
`:79` (T-0021's tracker import holds `:78`); `.crew/verify.json` rule 29 is T-0023's routing
rule at `:309-317`, after T-0021's tracker rule 28 at `:301-308`. The version is 1.0.46 at
`.claude-plugin/marketplace.json:218` and `plugin/crew/.claude-plugin/plugin.json:3`. Config
leaves re-executed on the merge: 122 / 68 / 54 / 0. T-0004's "117 -> 119" is now
`CHANGELOG.md:436-437` (T-0023's entry sits first). `crew_tracker.py`, `crew_resume.py` and
`role_write_guard.py` changed on one side only, so their citations stand. On the merge,
`test_crew_route.py`, `test_crew_route_hook.py`, `test_crew_context.py`, `test_crew_tracker.py`
and `test_crew_config.py` ran: 588 passed.

## Re-anchor provenance - `6f96e627` -> `5536c2c8`, 2026-09-26 (T-0018)

`crew_refresh_check.py --root . --ticket T-0018` named this note. Of the paths it cites,
`git diff --name-only 6f96e627 5536c2c8` returns `.claude-plugin/marketplace.json`,
`.crew/verify.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`,
`plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/autopilot.md`,
`plugin/crew/hooks/scripts/crew_autopilot.py` and the autopilot tests. Each citation into them was
re-read with `grep -n`/`sed -n` at `5536c2c8`:

- `crew_autopilot.py` - two usage lines in the docstring (`:1-13` -> `:1-15`), T-0018's
  constants at `:149-158` and `route`/`route_args`/`status` after `stops`: `FIXED_STOPS`
  `:116` -> `:118`, `PROCEDURE_STOPS` `:133` -> `:135`, `HUMAN_STOPS` `:139` -> `:141`,
  `next_phase` `:451` -> `:464`, `resume_target` `:522` -> `:535`, `settings` `:592` -> `:605`,
  its crew.json warning `:612-616` -> `:625-629`, `stops` `:621` -> `:634`, `main` `:639` -> `:847`.
- `autopilot.md` - compressed 120 -> 100 lines; the arming refusal `:13-20` -> `:41-42`, the
  branch/head rule `:29-30` -> `:43-44`; `allowed-tools` `:4` holds.
- `.crew/verify.json` - rule 26 gained one path, `:281-288` -> `:281-289`; 27 rules, 294 lines.
- `marketplace.json` `:218` and `plugin.json:3` - 1.0.42.
- `README.md`, `CHANGELOG.md`, `BUDGETS.md`, `PLUGINS.md` - cited by name only here.

## Re-anchor provenance - `5536c2c8` -> `4ff7e764`, 2026-09-26 (T-0018 review round 1)

`crew_refresh_check.py --root . --ticket T-0018` named this note after the round-1 fix commit. Of
the paths it cites, `git diff --name-only 5536c2c8 4ff7e764` returns `CHANGELOG.md`,
`plugin/crew/README.md`, `plugin/crew/commands/autopilot.md`,
`plugin/crew/hooks/scripts/crew_autopilot.py` and the autopilot tests. Each citation into them
was re-read with `grep -n`/`sed -n` at `4ff7e764`:

- `crew_autopilot.py` - one usage line added to the docstring (`:1-15` -> `:1-16`), so every
  T-0004 citation moved by one: `FIXED_STOPS` `:119`, `PROCEDURE_STOPS` `:136`, `HUMAN_STOPS`
  `:142`, `SUBCOMMANDS` `:152`, `next_phase` `:465`, `resume_target` `:536`, `settings` `:606`,
  its crew.json warning `:626-630`, `stops` `:635`, `route` `:651`, `route_args` `:680`. The
  round-1 additions pushed `status` `:774` -> `:802`, `status_text` `:809` -> `:837`, `main`
  `:847` -> `:875`; `_repoint` (`:740`) and `_resume_line` (`:766`) are newly cited. 956 lines.
- `autopilot.md` - still 100 lines; `## 0. Route` `:13-22` -> `:12-26`, `## 1. status`
  `:24-31` -> `:28-35`, the arming refusal `:41-42` -> `:45-46`, the branch/head rule `:43-44`
  -> `:47-48`; `allowed-tools` `:4` holds.
- `README.md`, `CHANGELOG.md` and the tests - cited by name only here.

## Re-anchor provenance - `4ff7e764` -> `29a987b0`, 2026-09-26 (T-0018 review round 2)

`crew_refresh_check.py --root . --ticket T-0018` named this note after the round-2 fix commit. Of
the paths it cites, `git diff --name-only 4ff7e764 29a987b0` returns `.crew/verify.json`,
`CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_autopilot.py` and the autopilot tests. Each
citation into them was re-read with `grep -n`/`sed -n` at `29a987b0`:

- `crew_autopilot.py` - every change sits below `_reserved_round` (`:711`), so every T-0004 and
  `route` citation above it holds (`:1-16`, `:119`, `:136`, `:142`, `:152`, `:465`, `:536`,
  `:606`, `:626-630`, `:635`, `:651`, `:680`). `_bare` (`:720`), `_takes` (`:729`) and `_waiting`
  (`:735`) are newly cited; `_repoint` `:740` -> `:759`, `_resume_line` `:766` -> `:793`,
  `status` `:802` -> `:838`, `status_text` `:837` -> `:875`, `main` `:875` -> `:913`. 994 lines.
  The `_resume_line` claim is rewritten: it now defers to `resume_target`, not
  `_handoff_ticket`.
- `.crew/verify.json` - rule 26's `seconds` and `why` changed in place; `:281-289` holds, 294
  lines.
- `CHANGELOG.md` and the tests - cited by name only here, except `CHANGELOG.md:65` (the config
  key count paragraph), which did not match "116 -> 118" at `4ff7e764` either and is left as it
  was, outside this refresh.

## Re-anchor provenance - `29a987b0` -> `c87ac3f4`, 2026-09-26 (T-0018 review round 3)

`crew_refresh_check.py --root . --ticket T-0018` named this note after the round-3 fix commit. Of
the paths it cites, `git diff --name-only 29a987b0 c87ac3f4` returns `.crew/verify.json`,
`CHANGELOG.md`, `plugin/crew/commands/autopilot.md`, `plugin/crew/hooks/scripts/crew_autopilot.py`
and the autopilot tests. Each citation into them was re-read with `grep -n`/`sed -n` at
`c87ac3f4`:

- `crew_autopilot.py` - the first change is at `:495` (`HANDOFF_ABSENT`, `HANDOFF_UNREADABLE`,
  `_read_handoff` `:499`), so every citation above it holds (`:1-16`, `:17-39`, `:119`, `:136`,
  `:142`, `:152`, `:465`). Below it lines moved by 18 up to `WAITING`, by 22 from `_reserved_round` to `_repoint`
  (`LEDGER_STATES` sits between), and by 40 from `_resume_line` on (`_closed` and `_review`'s new
  branches sit between):
  `resume_target` `:536` -> `:554`, `settings` `:606` -> `:624` (its `crew.json` warning
  `:626-630` -> `:644-648`), `stops` `:635` -> `:653`, `route` `:651` -> `:669`, `route_args`
  `:680` -> `:698`, `_takes` `:729` -> `:751`, `_waiting` `:735` -> `:757`, `_repoint` `:759` ->
  `:781`, `_resume_line` `:793` -> `:833`, `status` `:838` -> `:878`, `status_text` `:875` ->
  `:915`, `main` `:913` -> `:953`. `LEDGER_STATES` (`:728`), `_closed` (`:802`) and `_review`
  (`:813`) are newly cited. 1034 lines.
- `autopilot.md` - still 100 lines; six `crew_autopilot.py` lines gained `-B` in place and the
  `## 1. status` paragraph was re-wrapped within its two lines, so `:4`, `:12-26`, `:28-35`,
  `:45-46` and `:47-48` hold.
- `.crew/verify.json` - rule 26's `seconds` (9 -> 11) and `why` changed in place; `:281-289`
  holds, 294 lines.
- `CHANGELOG.md` and the tests - cited by name only here.

## Re-anchor provenance - `c87ac3f4` -> `4755ae1a`, 2026-09-26 (T-0018 round-3 mutation retarget)

`git diff --name-only c87ac3f4 4755ae1a` returns only `plugin/crew/tests/sabotage_autopilot.py`
and `plugin/crew/tests/test_crew_autopilot_status.py`, both cited by name only here, so every
line citation above holds.

## Re-anchor provenance - `2b18f7ab` + `4755ae1a` -> `b1ae1500`, 2026-09-27 (T-0018 round 4, main merge)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `550aa306`, the merge of
main (`502cb137`, crew 1.0.42, T-0005) into the T-0018 branch, and `b1ae1500`, which sets crew
1.0.43. The merge's conflicts in this note were resolved by keeping main's sections and T-0018's
autopilot section; this pass re-reads that section against the merged tree. Of the paths it
cites, `git diff --name-only 4755ae1a b1ae1500` returns, besides main's own paths (main's
provenance above covers them to `2b18f7ab`, and `git diff --name-only 2b18f7ab 502cb137` touches
only `docs/diagrams/` outside the artifacts), `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `CHANGELOG.md`,
`plugin/crew/hooks/scripts/crew_autopilot.py` and the autopilot tests. Each citation into them
was re-read with `grep -n`/`sed -n` on `git show b1ae1500:<path>`:

- `crew_autopilot.py` - round 4 grew the docstring by two lines (`:1-18`, was `:1-16`) and put
  the `__main__` bytecode guard (`:91-93`, four lines with its blank) before the imports, so
  everything from the `next` table to `_repoint` moved by 2 or 6, `_closed` by 15 and everything
  from `_review` on by 20:
  the `next` table `:20-43` (re-measured: heading `:20`, rows `:22-43`; the old `:17-39` was a
  loose span), `FIXED_STOPS` `:119` -> `:125`, `PROCEDURE_STOPS` `:136` -> `:142`, `HUMAN_STOPS`
  `:142` -> `:148`, `SUBCOMMANDS` `:152` -> `:158`, `next_phase` `:465` -> `:471`,
  `_read_handoff` `:499` -> `:505`, `resume_target` `:554` -> `:560`, `settings` `:624` ->
  `:630`, `stops` `:653` -> `:659`, `route` `:669` -> `:675`, `route_args` `:698` -> `:704`,
  `LEDGER_STATES` `:728` -> `:734`, `_takes` `:751` -> `:757`, `_waiting` `:757` -> `:763`,
  `_repoint` `:781` -> `:787`. `_drive` (`:808`) is new and newly cited; `_closed` `:802` ->
  `:817` gained the unreadable-spec branch, so `_review` `:813` -> `:833`, `_resume_line` `:833`
  -> `:853`, `status` `:878` -> `:898`, `status_text` `:915` -> `:935`, `main` `:953` -> `:973`.
  1054 lines.
- `crew_state.py` - `AUTOPILOT_DEFAULTS` is `:1090` on the merged tree (main's line; the branch
  had `:1087`). `crew_config.py:381` and `crew_ticket.py:505` hold.
- `autopilot.md` - unchanged since `4755ae1a`: 100 lines, `:4`, `:12-26`, `:28-35`, `:45-46`,
  `:47-48` hold.
- `.crew/verify.json` - the merged file: the autopilot rule is rule 27 at `:293-301` (main
  inserted rule 6), the resume rule 26 at `:282-292`; 306 lines.
- `marketplace.json:218` and `plugin.json:3` - 1.0.43, and `:217` still states 4 agents, 35
  commands, 29 skills.
- `CHANGELOG.md`, `README.md` and the tests - cited by name only here.

No suite was run by this note.

## Re-anchor provenance - `b1ae1500` -> `9e21a0d9`, 2026-09-27 (T-0018 sabotage retarget, version re-set)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `a0158b3d`, which pointed
`sabotage_autopilot.py`'s route and status `-B` mutations at
`test_every_autopilot_invocation_in_command_skips_bytecode` (the behavioural test they named stayed
green once round 4's `__main__` guard landed), then `9a1394ef` / `9e21a0d9`, which stepped the crew
version back and re-set it to 1.0.43 last. Re-read on `git show 9e21a0d9:<path>`:

- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`,
  `STATUS_MUTATIONS` still `:164`, still 40 entries (two retargeted, none added or removed), the
  `+=` at `:340`.
- The version files and `CHANGELOG.md` are byte-identical to `b1ae1500`'s.

No suite was run by this note.

## Re-anchor provenance - `9e21a0d9` -> `89f73d79`, 2026-09-27 (T-0018 review round 5)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `96d4fa1c`, which fixed
review round 5's three FIX lines in `plugin/crew/hooks/scripts/crew_autopilot.py`, then
`a943f361` / `89f73d79`, which stepped the crew version back and re-set it to 1.0.43 last. Each
citation into the changed files was re-read with `grep -n`/`sed -n` at `89f73d79`:

- `crew_autopilot.py` - one usage line added to the docstring (`:1-18` -> `:1-19`), so
  everything from the `next` table to `next_phase` moved by 1: the table `:20-43` -> `:21-44`,
  the bytecode guard `:91-93` -> `:92-94`, `FIXED_STOPS` `:125` -> `:126`, `PROCEDURE_STOPS`
  `:142` -> `:143`, `HUMAN_STOPS` `:148` -> `:149`, `SUBCOMMANDS` `:158` -> `:159`, `next_phase`
  `:471` -> `:472`, `_read_handoff` `:505` -> `:506`. `_read_handoff` grew by 5 (the
  dangling-entry branch), so `resume_target` `:560` -> `:566`, `settings` `:630` -> `:636`,
  `stops` `:659` -> `:665`, `route` `:675` -> `:681`, `route_args` `:704` -> `:710`,
  `LEDGER_STATES` `:734` -> `:740`, `_takes` `:757` -> `:763`, `_waiting` `:763` -> `:769`,
  `_repoint` `:787` -> `:793`, `_drive` `:808` -> `:814`, `_closed` `:817` -> `:823`, `_review`
  `:833` -> `:839`, `_resume_line` `:853` -> `:859`, `status` `:898` -> `:904`, `status_text`
  `:935` -> `:941`, `main` `:973` -> `:979`. 1063 lines.
- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`,
  `STATUS_MUTATIONS` still `:164`, now 44 entries (four added, one re-anchored), the `+=` at
  `:358`.
- `plugin/crew/README.md` changed on one line in place (the `status` paragraph), so no line
  moved; the version files are byte-identical to `9e21a0d9`'s; `autopilot.md` and
  `.crew/verify.json` are unchanged.

No suite was run by this note.

## Re-anchor provenance - `89f73d79` -> `0834aaf9`, 2026-09-27 (T-0018 plan step 7)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `88f52aa6`. That commit
added one must-block test to `plugin/crew/tests/test_crew_autopilot_status.py` and pointed one
`STATUS_MUTATIONS` entry at it, a one-line change in place in
`plugin/crew/tests/sabotage_autopilot.py`. After it, `5c6cadee` / `0834aaf9` stepped the crew
version back and set 1.0.43 again as the last change. Re-read at `0834aaf9`:

- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`,
  `STATUS_MUTATIONS` still `:164`, still 44 entries (one retargeted, none added), the `+=` still
  at `:358`, 358 lines.
- `plugin/crew/tests/test_crew_autopilot_status.py` - cited by name only, so no line citation
  moved.
- `crew_autopilot.py`, `plugin/crew/tests/sabotage.py`, `.crew/verify.json` and the version files
  are byte-identical to `89f73d79`'s.

No suite was run by this note.

## Re-anchor provenance - main's `53f5482c` -> `0c7f6b84`, 2026-09-27 (T-0018, merge of origin/main `f0b12ee6`)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `11e8afe3` merged origin/main
`f0b12ee6` (T-0042, crew 1.0.43) into T-0018-router and `0c7f6b84` set crew 1.0.44 last. The merge
took main's anchor, so the check measured T-0018's own paths against it. The two sides changed no
source file in common. The files both sides changed are `.crew/verify.json`, `plugin/crew/README.md`,
`CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the three version files. Every `path:line` citation into
them in this note was compared with the same line on each side and at `0c7f6b84`:

- `.crew/verify.json` - 28 rules, 306 lines. Against T-0018's side nothing moved (main's rule 26
  `seconds` and `why` changed in place), so rule 27 is still `:293-301`. Against main's side the
  autopilot rule adds one line after `:295`.
- `plugin/crew/README.md` - main added 14 lines at `:1762`, and T-0018 added 15 lines after `:790`.
  The only citation that moved, the runbook-index line, was recomputed in the merge (`:1959`).
- `CHANGELOG.md` - cited by name, apart from one historical citation that was already recorded as
  out of scope. `plugin/crew/BUDGETS.md:11` is 18,566 over 121 files, re-measured in the merge.
- Version files - `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
  and `plugin/PLUGINS.md:14` read 1.0.44 at `0c7f6b84`. They were 1.0.43 on both sides of the merge.

No suite was run by this note.

## Re-anchor provenance - `db14619c` + `e6b696fb` -> `fbc27b49`, 2026-09-27 (T-0018 lands on T-0021's main)

`515346b1` merges T-0018's reviewed head `e6b696fb` (review round 6 CLEAN) into main `db14619c`
(T-0021 landed as crew 1.0.44 and 1.0.45, PR #243), and `fbc27b49` bumps crew to 1.0.46. The two
sides share no source file: the paths both changed since `f0b12ee6` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`,
`plugin/crew/tests/test_lifecycle_commands.py` (merged cleanly), the version files and the refresh
artifacts. The conflicting provenance sections keep both sides, main's (T-0021's) first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on `fbc27b49` and corrected.
Corrected here: crew's version `:218` is 1.0.46; T-0004's CHANGELOG "117 -> 119" is `:469-470`;
the tracker rule is `.crew/verify.json:302-309`. `crew_autopilot.py`, `commands/autopilot.md` and
the autopilot tests changed only on T-0018's side, so their citations stand as T-0018's refresh left
them. No test suite was executed for this note.

## Re-anchor provenance - `55f59b04` + `bebbb97f` -> `65bb3330`, 2026-09-27 (T-0018 lands on T-0023's main)

`f458e752` merges main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244) into T-0018-land,
which had merged T-0018's reviewed head `e6b696fb` into `db14619c` and been refreshed at
`55f59b04`; `65bb3330` re-bumps crew to 1.0.47. The two sides share no source file: T-0023
changed `crew_route.py`, `crew_context.py`, `crew_config.py`, `sabotage.py` and their tests, T-0018
`crew_autopilot.py`, `autopilot.md` and theirs; both changed `CHANGELOG.md`, `.crew/verify.json`
(merged cleanly: 30 rules, 323 lines), `plugin/crew/README.md` (merged cleanly),
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's (T-0023's) first. Every `path:N` citation in the body was mapped
from the side its line came from onto the merged tree with a line diff, and each one that moved was
re-read with `sed -n` on `65bb3330` and corrected.
Corrected here: crew's version `:218` is 1.0.47; T-0004's CHANGELOG "117 -> 119" is `:515-516`;
`crew_autopilot.settings`' crew.json warning is `:656-660` (it read `:644-648`, stale on T-0018's
side, and `:612-616` on main); T-0023's rule 29 is `.crew/verify.json:310-318`. No test suite was
executed for this note.

## Re-anchor provenance - `65bb3330` + `6fa7fb13` -> `c817782f`, 2026-09-27 (T-0010-solo merges `67caa4b8`)

`c817782f` is T-0010's crew 1.0.48 version commit on top of `d1e119d2`, T-0010-solo's merge of
origin/main `67caa4b8` (T-0018 landed as 1.0.47; its code maps anchored `65bb3330`), and
`3e2c9962`, the reconciliation under the owner's approve carve-out. Main's side of this note was
mapped from `65bb3330`, T-0010's side from its own anchor (`6fa7fb13`), to `c817782f` with `difflib`
over every cited file, a bare `:N` taken as the last path named in its section; sections headed
provenance (and localgpu's re-derivation record) were left as written. The two mapped texts were
then merged three-way from `f0b12ee6`. Between `65bb3330` and `c817782f` the cited paths that
changed are T-0010's: `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py`
(four `AUTOPILOT_DEFAULTS` lines at `:1094`, so every later line moved by 4), `commands/autopilot.md`,
the version files, `BUDGETS.md`, README, CONFIG.md, the tests and sabotage modules, and
`.crew/verify.json` (rule 28 inserted at `:302-308`, so rules 29 and 30 moved down by 7).

Re-read by hand at `c817782f`: the `/crew:autopilot` section, rewritten for the approve
exception (docstring `:1-120`, eight subcommands; every line number re-grepped - `next_phase`
`:512`, `settings` `:676`, `approval_policy` `:759`, `approve` `:837`, `questions_check` `:951`,
`stops` `:988`, `route` `:1004`, `route_args` `:1033`, `status` `:1227`, `_policy_main` `:1306`,
`main` `:1323`); the config leaf counts, re-executed (124 / 68 / 56 / 0, asserted at
`plugin/crew/tests/test_crew_config.py:281`); the version (1.0.48 at `plugin/crew/.claude-plugin/plugin.json:3`);
the `crew.json` warning in `settings` (`:698-702`); and the verify rule numbers (27 autopilot,
28 T-0010's policy, 29 tracker, 30 routing). No test was run by this note.

## Re-anchor provenance - `c817782f` -> `926443d8`, 2026-09-27 (T-0010 review round 3 fixes)

`git diff --name-only c817782f 926443d8` is T-0010's round-3 fix (`caabb005`), the BUDGETS.md
count, the version step-back and re-set, and this refresh. `crew_autopilot.py` (1412 -> 1436 lines): the module and `approve` docstrings name what `approve`
writes (+1 docstring line, so every later line moved by 1 until `_phase`), `_phase`,
`next_phase` and `resume_target` take `policy=True` and `status` passes `policy=False`, and
`POLICY_FREE_APPROVE` / `POLICY_FREE_QUESTIONS` sit above `_approval_hint`. Every citation in
the `/crew:autopilot` and T-0010 sections was mapped with `difflib` and the def lines
re-grepped (`next_phase` `:516`, `resume_target` `:612`, `settings` `:683`, `approval_policy`
`:766`, `approve` `:855`, `questions_check` `:972`, `stops` `:1009`, `route` `:1025`,
`route_args` `:1054`, `status` `:1249`, `_policy_main` `:1330`, `main` `:1347`); the section's
`status` and `approve` prose rewritten for the fix. `commands/autopilot.md` stays 110 lines
(`## 0. Route` now `:14-27`). `sabotage_autopilot.py`'s `POLICY_MUTATIONS` moved `:370` ->
`:371` (47 entries). README and CONFIG.md changed in the cited paragraphs, cited by name
only. No test was run by this note.
