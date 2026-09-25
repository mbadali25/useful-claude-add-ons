anchor: useful-claude-add-ons@6c497a14
verified: 2026-09-25

## Re-derive provenance

Full re-derivation, not a re-point. The previous anchor (`5d1fc5fd`) predates
crew 1.0 (`6c497a14`, PR #225): a per-path check against `6c497a14` found 37 of
the old note's 44 cited, still-existing paths changed and 9 cited paths gone
entirely (`pm_brief.py`, `pm-pulse.sh`, `pm-brief.sh`, `agents/pm.md`, and the
54-agent roster files among them), so re-pointing would have produced correct
line numbers describing a crew that no longer exists. Read in full this pass:
`plugin/crew/hooks/hooks.json`, `_common.sh`, `role_write_guard.py`,
`role-write-guard.sh`, `auto-clear.sh`, `crew_autoclear_setup.py`,
`crew_state.py`'s roster/config block (:983-1350), `crew_guards.py`'s guard
vocabulary block (:91-505), `crew_context.py`, `event_claim.py`'s module
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
`plugin/crew/hooks/scripts/crew_state.py:1216-1221`) replaces that with:

- **Four read-only subagents on a tier ladder**, `ROLE_TIERS`
  (`plugin/crew/hooks/scripts/crew_state.py:1225-1230`): `explorer` and
  `reviewer` at tier 0, `security` at tier 1, `researcher` at tier 2. None of
  the four grants `Write` or `Edit` — confirmed by reading each agent file's
  frontmatter (`explorer.md`, `researcher.md`, `reviewer.md`, `security.md`,
  all `tools: Read, Grep, Glob, Bash, Skill`).
- **No specialist roles.** `SPECIALIST_ROLES` is now `frozenset()`
  (`plugin/crew/hooks/scripts/crew_state.py:1240`) — domain knowledge that
  used to be a specialist agent now lives in the on-demand `stack-*` skills
  (`stack-angular`, `stack-bash`, `stack-dotnet`, `stack-powershell`,
  `stack-python`, `stack-sql`, `stack-terraform`, `stack-web`), which are
  never dispatched as a role.
- **No standing PM agent file.** `plugin/crew/agents/pm.md` does not exist at
  this anchor (`find . -iname pm.md` returns nothing). The interactive session
  itself is the "unnamed PM": it implements, dispatches the four subagents,
  and is never itself given an `agent_type`. `PM_DEFAULTS`
  (`plugin/crew/hooks/scripts/crew_state.py:1079-1092`) and `pm.authority`
  (`AUTHORITY_DEFAULT = "report-only"`, `:1049`; three values —
  `report-only`/`act`/`autonomous`, `normalise_authority` at `:1272-1283`)
  still exist as config that governs how far that unnamed session may act
  without asking, and `AUTONOMOUS_STOPS`
  (`plugin/crew/hooks/scripts/crew_state.py:1062-1069`) still names the four
  things even `autonomous` may not do unasked (`offboard-role`, `delete-map`,
  `rewrite-metrics`, `git-destruction`).
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:1243-1252`) still
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
  and `classify` (`:539-588`) still special-cases `role == "pm"` at `:576-582`
  — but nothing in this checkout ever sets `agent_type` to `"pm"` any more:
  the unnamed interactive session sends no `agent_type` at all, and
  `classify`'s own first branch, `if role is None: return True, "no-agent-type"`
  (`:570-571`), is what actually governs it — unconditionally allowed,
  never reaching the `pm`-scoped branch. The module's own docstring at
  `:63-64` still reads "`crew`'s own agents are registered as `crew:pm`,
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

Crew 1.0's lifecycle is `brainstorm -> spec -> plan -> implement -> review ->
done`, one command per phase:

| Command | Does | Replaces |
|---|---|---|
| `/crew:brainstorm` (`plugin/crew/commands/brainstorm.md`) | Mints a ticket and settles an approved direction; loads `crew-brainstorm` (method adapted from `superpowers:brainstorming`, notice in `plugin/crew/NOTICE.md`) | new in 1.0 |
| `/crew:spec` (`plugin/crew/commands/spec.md:8-9`) | Fills the ticket contract (Intent/Exclusions/Evidence/Unknowns/Touch/Acceptance) from an approved direction | `/crew:ticket` |
| `/crew:plan` (`plugin/crew/commands/plan.md:8-9`) | Turns an approved spec into a step plan; the old standalone second-opinion step is now step 3, optional, inside this phase | redefined |
| `/crew:implement` (`plugin/crew/commands/implement.md:8-9`) | Implements an approved plan, then tests/docs/review; loads `crew-execute` (adapted from `superpowers:executing-plans`) | `/crew:work` |
| `/crew:review` (`plugin/crew/commands/review.md`) | Independent QA review of the working diff (Codex, Copilot, or the `crew:reviewer` Claude fallback) | (unchanged name; internals rewritten) |
| `/crew:done` (`plugin/crew/commands/done.md:7-8`) | Closes a ticket; three checks (review receipt, clean verify gate, passing completion audit), any one failing refuses the close, no partial close | new in 1.0 |

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
default functions.**

| | Leaves | Source |
|---|---|---|
| `default_config()` | **114** | `plugin/crew/hooks/scripts/crew_config.py:239` |
| `default_global_config()` | **63** | `plugin/crew/hooks/scripts/crew_config.py:367` |
| repo-only | **51** | the set difference |

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
| `GUARD_NAMES` | `terraformApply`, `forcePush`, `adminMerge`, `mergeGate`, `cloudDestructive`, `sqlDestructive` (6) | `block`/`ask`/`allow`, `guard_policy_rank` (`:378`) | `:104-105` |
| `PROD_GUARD_NAMES` | `prodDatabase`, `prodServer` (2) | `none`/`read`/`full`, `prod_level_rank` (`:407`) | `:126` |
| `ROLE_WRITE_GUARD_NAMES` | `roleWrites` (1) | `block`/`report`/`off`, default `off` not floor, `role_writes_rank` (`:443`) | `:149` |
| `CLOUD_GUARD_NAMES` | `cloudGuard` (1) — **new since the previous anchor** | same vocabulary and functions as `roleWrites`, its own words | `:188` |

`ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:194-195`) is the
concatenation of all four — **ten** guard names in total.
`cloud_guard.py`'s own docstring (`:1-6`) states what `cloudGuard` actually
is: a switch, not a policy — turning it on is what makes the six
`GUARD_NAMES` policies (which existed and ratcheted but governed nothing
since the pre-1.0 command guard was removed) mean something again for the
`Bash`/`PowerShell` `PreToolUse` matcher.

**The ratchet registry (`_RATCHETED`, `plugin/crew/hooks/scripts/crew_config.py:2342-2431`)
now holds 13 keys**, built in five steps (a literal dict of two, then four
`.update()`/assignment calls) rather than one table, exactly the shape the
previous anchor's note described for a smaller version of the same table:
`pm.authority`, `install.policy`, the 6 `GUARD_NAMES` keys, the 2
`PROD_GUARD_NAMES` keys, `guards.roleWrites`, `guards.cloudGuard` (new), and
`change.requireForProduction` = 2 + 6 + 2 + 1 + 1 + 1 = 13. Counted by
reading the five construction sites, not by trusting the literal alone —
the literal at `:2342-2353` holds only 2.

## `.crew/config.json` vs `.crew/crew.json` — the open 1.0.x authority question

**DERIVED, and this is the open TODO the task description names.** Two
different modules read two different files as "the repo's crew config", and
they disagree:

- `crew_config.py` (used by `verify-gate.sh`, `promote-gate.sh`,
  `role-write-guard.ps1`'s config lookups, and everything the ratchet/guard
  machinery above touches) reads **only** `.crew/config.json`
  (`plugin/crew/hooks/scripts/crew_config.py:1158`, and the module's own
  docstring at `:1` — "Owns the single definition of a fresh
  `.crew/config.json`").
- `crew_context.py`'s `load_crew_config`
  (`plugin/crew/hooks/scripts/crew_context.py:120-129`) tries `.crew/crew.json`
  **first**, falling back to `.crew/config.json` only if `crew.json` is
  absent — its own docstring: "1.0's `.crew/crew.json`, else 0.x's
  `config.json`".
- Only `/crew:migrate` (`crew_migrate.py`, `--apply`) ever writes
  `.crew/crew.json`; `/crew:init` still writes only `.crew/config.json`
  (`TODO.md:3854`, "T2 (lane D, additive) deferred items", filed
  2026-09-23, still open at this anchor). `crew_migrate.py`'s own module
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
  `crew_migrate.py`'s own comment (`crew_autoclear_setup.py:501-507`) names
  the specific consequence for auto-clear: "`crew_status.py` reads it
  [`crew.json`] only to report the migration schema... converting
  `crew.json` alone [does nothing for autoClear behaviour, which
  `crew_config.py` still reads from `config.json`]". This is a real,
  present-tense inconsistency, not a hypothetical — flagging it is this
  note's job; **deciding which file should win, or whether `crew_config.py`
  should learn to read `crew.json` too, is a decision for scribe to record,
  not this note's to make.**

`SCHEMA_CURRENT` for `config.json` is still **7**
(`plugin/crew/hooks/scripts/crew_state.py:175`) — unchanged by the 1.0
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
  needs an explicit yes (`plan_windows_default`'s docstring, `:9`,
  `apply_migrate`'s consent gate at `:242-254`) — because it "drives real
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

## `crew_endpoints.py` — unchanged since the previous anchor

Re-checked, not carried forward blind: `_ENDPOINTS_PATH_PARTS`
(`plugin/crew/hooks/scripts/crew_endpoints.py:34`), `declare_endpoint`
(`:255`), `infer_endpoints` (`:411`), `gizmoduck_installed` (`:499`),
`_is_monorepo` (`:581`), `scan_artifact_path` (`:668`), `_endpoint_needle`
(`:795`), `_artifact_confirms_scan` (`:830`), `read_endpoints` (`:915`) are
all at the identical line numbers the previous anchor's note cited, and the
file is 979 lines at both anchors — the crew 1.0 redesign did not touch this
subsystem. `.crew/endpoints.json` still does not exist in this checkout;
`git ls-files .crew/` still returns only the codemap `.md` files plus
`.crew/verify.json`.

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:983` — `TRIGGERS`, a 15-entry
  tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2880` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:239` / `:367` —
  `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2342` — `_RATCHETED`, the
  13-key ratchet table (five construction steps).
- `plugin/crew/hooks/scripts/role_write_guard.py:539` — `classify`, the
  decision function; `:684` — `main()`.
- `plugin/crew/hooks/scripts/role-write-guard.sh:348` — where the strict
  private-resolver result feeds the guard's fail-closed fallback.
- `plugin/crew/hooks/scripts/event_claim.py` — no single entry point read
  this pass beyond the module docstring; called from `notify.sh` and
  `handoff-write.sh` only.
- `plugin/crew/hooks/scripts/crew_context.py:120` — `load_crew_config`, the
  one function that reads `crew.json` before `config.json`.
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py` — no single `main()`
  confirmed at a specific line this pass; called with subcommands
  (`plan-windows-default`, `apply-migrate`) from the three sites named
  above.
- `plugin/crew/hooks/scripts/crew_endpoints.py:255` — `declare_endpoint`,
  still the only writer of `.crew/endpoints.json`.

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
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1225-1230`)
  — 4 roles, all tiered, none a specialist.
- `crew_state.PM_DEFAULTS` (`:1079-1092`) and `crew_state.AUTHORITY_DEFAULT`
  (`:1049`) — the unnamed session's own dispatch authority.
- `crew_guards.ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:194-195`)
  — 10 guard names across 4 vocabularies.
- `.crew/metrics.jsonl` — append-only, one JSON object per line, replacing
  the pre-1.0 `.crew/metrics.md` (`crew_metrics.py`'s module docstring,
  **not otherwise read**). Still machine-local: the `.gitignore` un-ignore
  list at this anchor is still exactly three paths — `!.crew/codemap/`,
  `!.crew/endpoints.json`, `!.crew/verify.json` — confirmed by reading
  `.gitignore:279-330` directly; `metrics.jsonl` is not among them.
- `.crew/endpoints.json` — unchanged; see above.

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
areas; `INDEX.md` is the table of contents (not edited by this pass, per
this pass's own instructions — its anchor column is the integrator's to
update).
