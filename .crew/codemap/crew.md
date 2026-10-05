anchor: useful-claude-add-ons@e2d2f9f0
verified: 2026-10-04

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
and 2; and to `c2ae46ab` for its review round 3 and merge of main; on T-0024's branch
from `6f96e627` to `a2802526`, then to `32223b8a` for its review round 1, `f8671fdc` for
its successor step 6 and `45345812` for its review round 3; on T-0079's branch from
`8de3c669` to `a6e81869`. See the last sections.

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
| Commands | 36 | `.md` files in `plugin/crew/commands/` (36 since T-0075 added `config-setup.md`; 35 since T-0004 added `autopilot.md`) |
| Skills | 31 | subdirectories of `plugin/crew/skills/` (includes 8 `stack-*` skills; `crew-standards` since T-0085, `crew-qa-standards` since #267) |

`.claude-plugin/marketplace.json:223` states the identical three numbers (4
agents, 36 commands, 31 skills) in its `crew` entry's description, and `:224`
the version, 1.0.184 (T-0061-build's number, allocated by the coordinator after main reached 1.0.162 with L-0601 #327; 1.0.163-1.0.183 not used by it); before that 1.0.162 (L-0601's number, allocated by the coordinator after main reached 1.0.154 with L-0510 #318, #328, #329 and #330; 1.0.141 and 1.0.155-1.0.161 not used by it); before that 1.0.140 (L-0574's claim, allocated by the coordinator 2026-10-03, set last after L-0574 merged main `2a2d6e07` (L-0592 #325, 1.0.139), whose crew is 1.0.139; L-0574 held 1.0.136 after merging main `ffeb0e2f` (L-0598 #321, 1.0.135) and `6ac3b1b3`, whose crew was 1.0.135; L-0574 had earlier merged main `e0c70fc9` (L-0555 #310 1.0.132, #317 1.0.134, L-0597 #316), whose crew was 1.0.134; L-0574 was 1.0.131 after merging main `0487fc39` (L-0599 #315, L-0575 1.0.129), whose crew was 1.0.129; L-0574 had earlier merged main `7ba4f9ea` (L-0593 #312, L-0572 #309, #295), whose crew was 1.0.126; that 1.0.126 is L-0572's bump after merging main `d2ec37d3` (W-0120 #307/#308, 1.0.119), past 1.0.120-1.0.125, held or burned by other lanes; before that 1.0.119 (L-0578's bump after merging main `ffd11270` (L-0557 #300, 1.0.114), past 1.0.115-1.0.118, held or burned by other lanes; before that 1.0.114 (L-0557's re-set at `6053b65d` after merging main `2906dcbd` (L-0516 #298, 1.0.110) at `2f3fb34c`, past 1.0.111 (W-0117-land), 1.0.112 (L-0510) and 1.0.113 (T-0504); L-0557 was 1.0.111 at `c43a9ce3` after merging main `ddcbf90d` (W-0115 #299, 1.0.106) at `0597e5c6`, past 1.0.107 (T-0504), 1.0.108 (L-0510), 1.0.109 (T-0501) and 1.0.110 (L-0516); L-0557 was 1.0.105 at `773ce841` after merging main `05a679bf` (L-0558 #293, 1.0.102) at `2169bd11`, unchanged by the merge of main `cacf7ff0` (L-0513 #301, no plugin version) at `a9608aa5`, skipping 1.0.103 (L-0510) and 1.0.104 (L-0516); these two citations read `:217`/`:218` before this pass, which on this tree are another entry's description and version; L-0557 was 1.0.101 at `90186613` after merging main `52489039` at `327e6ec1`: past main's 1.0.98 (T-0040 #290), skipping 1.0.100 (L-0516) and L-0558's 1.0.95 (#293); L-0557 was 1.0.99 at `4fc11923`, after merging main `44d3dbc6` (T-0110 #297, 1.0.97); L-0557 was 1.0.96 at `97ace923` and `550c39cd`, when main was 1.0.92 (T-0505 #296); before T-0505 main was 1.0.89 (W-0116 #292); L-0557 was 1.0.95 at `d9ccfd5a` and 1.0.89 at `b1d8a4e8`; main's 1.0.86 before W-0116 is L-0520 PR 1's re-set at `14b52c91` after merging main `bd4b2f30`, past main's 1.0.85 and skipping 1.0.84, which T-0505 targets; 1.0.84 on L-0520's branch at `e60d88f2`; main's 1.0.85 is T-0028's re-set at `328fdf4a` after the round-7 fixes, first set at `f4adf923`, past main's 1.0.83 and skipping 1.0.84, which T-0505 targets; 1.0.84 at `c43a54c1`, one past main's 1.0.83 (T-0099 #278, after L-0531 #284 at 1.0.82), which this note on main still read as 1.0.81; 1.0.81 is T-0094's landing re-set, one past origin/main's 1.0.80 after T-0094 merged `d1462bbd`, L-0529's landing (#283); T-0094 was 1.0.78 at `65abeb8d`/`1f21f73b`, one past origin/main's 1.0.77 after T-0094 merged `549cda24`; main's 1.0.77 is T-0086's landing (#282); T-0094 was 1.0.77 at `a0db0703`, one past origin/main's 1.0.76 after T-0094 merged `a7524aac`; main's 1.0.76 is T-0087's landing (#281); T-0094 was 1.0.76 at `1b9e4bfe`, one past origin/main's 1.0.75 after T-0094 merged `9af34e57`; T-0094 was 1.0.71 at `0c19512c`, 1.0.70 at `f5d0f1b1` and 1.0.62 at `fc348c89` on its branch before; main's 1.0.75 is T-0085's landing: 1.0.70 at its merge of main's 1.0.69 at `a61a6f38`, 1.0.71 after one landing-branch sabotage anchor commit, 1.0.72 after rewrapping `commands/review.md` to its line allowance, 1.0.73 at its catch-up merge of main's 1.0.70 at `6813749b` (#268, T-0097), 1.0.74 for the Windows fail-open fix in `gate_applies` at `9b6b0da7`, 1.0.75 for re-targeting the sabotage entry that fix made vacuous; whose 1.0.62-1.0.69 are #263-#267 and T-0088; before that 1.0.61, T-0010's landing re-set `bbd9a66d` after its landing-branch lint fixes, two past main's 1.0.59; 1.0.60 at `cd106b8b`, one past main's 1.0.59 after T-0010-solo merged `e878cc31`; 1.0.55 on T-0010-solo at `d7c7c75c`; main's 1.0.59 is T-0075's landing bumps: 1.0.59 keeps the refused-snapshot probe's message in a local (ruff F821), 1.0.58 re-anchors two round-5 sabotage entries to the new refusal text, 1.0.56 for the landing branch's pylint disable in `plugin/crew/tests/test_config_menu.py`, 1.0.57 for `crew_config_files.os_error_text`, the Windows path fix in the OS-error refusals; 1.0.55 at `3648f59a` on the build branch, one past main's 1.0.54 from T-0092's `136f4b33`; T-0085's build branch declares main's version and carries no bump of its own until land, `.crew/standards.md` REPO-03), matching `plugin/crew/.claude-plugin/plugin.json:3`, so this
site is current — this pass did not re-run the previous note's wider
count-disagreement sweep across `README.md`/`plugin/README.md`/
`INSTALLATION.md`/the install scripts; see "Unverified at this anchor".

## The roster, replaced wholesale

Crew 0.x shipped 54 agents (13 tiered roles + 40 specialists) plus a standing
`pm` agent that dispatched them. Crew 1.0 (`docs/review/04-redesign.md`,
"Roster: 54 agents -> 4", cited in comment at
`plugin/crew/hooks/scripts/crew_state.py:1289-1294`) replaces that with:

- **Four read-only subagents on a tier ladder**, `ROLE_TIERS`
  (`plugin/crew/hooks/scripts/crew_state.py:1298-1303`): `explorer` and
  `reviewer` at tier 0, `security` at tier 1, `researcher` at tier 2. None of
  the four grants `Write` or `Edit` — confirmed by reading each agent file's
  frontmatter (`explorer.md`, `researcher.md`, `reviewer.md`, `security.md`,
  all `tools: Read, Grep, Glob, Bash, Skill`).
- **No specialist roles.** `SPECIALIST_ROLES` is now `frozenset()`
  (`plugin/crew/hooks/scripts/crew_state.py:1313`) — domain knowledge that
  used to be a specialist agent now lives in the on-demand `stack-*` skills
  (`stack-angular`, `stack-bash`, `stack-dotnet`, `stack-powershell`,
  `stack-python`, `stack-sql`, `stack-terraform`, `stack-web`), which are
  never dispatched as a role.
- **No standing PM agent file.** `plugin/crew/agents/pm.md` does not exist at
  this anchor (`find . -iname pm.md` returns nothing). The interactive session
  itself is the "unnamed PM": it implements, dispatches the four subagents,
  and is never itself given an `agent_type`. `PM_DEFAULTS`
  (`plugin/crew/hooks/scripts/crew_state.py:1145-1158`) and `pm.authority`
  (`AUTHORITY_DEFAULT = "report-only"`, `:1102`; three values —
  `report-only`/`act`/`autonomous`, `normalise_authority` at `:1345-1356`)
  still exist as config that governs how far that unnamed session may act
  without asking, and `AUTONOMOUS_STOPS`
  (`plugin/crew/hooks/scripts/crew_state.py:1115-1122`) still names the four
  things even `autonomous` may not do unasked (`offboard-role`, `delete-map`,
  `rewrite-metrics`, `git-destruction`). Since T-0004 they bind
  `/crew:autopilot` too (comment at `:1124-1129`).
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:1316-1325`) still
  distinguishes a deliberately-onboarded off-ladder role from a typo, even
  though `SPECIALIST_ROLES` is empty today.

**DERIVED, and worth flagging as a candidate stale-code finding, not just a
roster fact.** `role_write_guard.py` — the `PreToolUse` `Write|Edit` guard —
still carries PM-specific logic and a docstring that names removed roles:

- `_DENY_ROLES` (`plugin/crew/hooks/scripts/role_write_guard.py:231-236`) is
  exactly the four shipped agents (`explorer`, `researcher`, `reviewer`,
  `security`) — consistent with the roster above, each denied any write
  because none grants `Write`/`Edit` in its `tools:` line.
- `_UNRESTRICTED_ROLES` is `frozenset()` (`:242`) — empty since crew 1.0,
  because no shipped agent writes.
- `_PM_ROLE = "pm"` (`:244`) and `_PM_ALLOWED_PATTERNS` (`:251-260`,
  `.crew/**`, `TODO.md`, `.work/**`, `docs/diagrams/**`) are still live code,
  and `classify` (`:540-593`) still special-cases `role == "pm"` at `:583-590`
  — but nothing in this checkout ever sets `agent_type` to `"pm"` any more:
  the unnamed interactive session sends no `agent_type` at all, and
  `classify`'s own first branch, `if role is None: return True, "no-agent-type"`
  (`:573-574`), is what actually governs it — unconditionally allowed,
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
| `/crew:approve` (`plugin/crew/commands/approve.md:5`, `disable-model-invocation: true`) | Typed by the user only: the UserPromptSubmit `approval-hook` records `<git-common-dir>/crew/tickets/<id>/approval.json`, bound to the digest of `spec.md` and `plan.md` (`:7-16`; since T-0026 a `crew-approval/2` digest that normalises only the header's status value, so the lifecycle's status edits keep the approval); the command body only relays the result. Since T-0024 (crew 1.0.42) several ids, a range `T-0010..T-0012` or the one plain-text form `approve T-1 through T-3` record nothing on that prompt: the hook blocks it with a PENDING list bound to each ticket's hashes, and only the user's own one-line `/crew:approve --confirm` (same session, within `PENDING_TTL`) records one receipt per ticket, or none (`plugin/crew/hooks/scripts/approval_hook.py:361`, `:433`; relay at `approve.md:27-43`). Since 1.0.44 only the prompt's own top-level command counts (a command tag nested in another is refused, and the expanded form carries nothing outside its tags, for a single id too since 1.0.45), commas go only between ids, and the closed-row check matches the id whole and in any case (`crew_ticket.py` `precheck` `:859`; the row's id cell is its first id-shaped cell) | new in 1.0 |
| `/crew:implement` (`plugin/crew/commands/implement.md:8-9`) | Implements an approved plan, then tests/docs/review; loads `crew-execute` (adapted from `superpowers:executing-plans`) | `/crew:work` |
| `/crew:review` (`plugin/crew/commands/review.md`) | Independent QA review of the working diff (Codex, Copilot, or the `crew:reviewer` Claude fallback) | (unchanged name; internals rewritten) |
| `/crew:done` (`plugin/crew/commands/done.md:7-8`) | Closes a ticket; four checks (review receipt, clean verify gate, passing completion audit, current artifacts), any one failing refuses the close, no partial close. Check 4 (`:55-66`, since crew 1.0.36) runs `crew_refresh_check.py` and refuses on any `stale`, `unknown` or (T-0063) `fresh-uncommitted` line **without refreshing** - a write there would stale check 1's receipt (`:61-64`). After check 4, a report that is not a check (`:68-79`, T-0066): `crew_trailers.py --check` lists commits carrying a `git.forbiddenTrailers` token and never refuses or rewrites | new in 1.0 |

`/crew:ticket` and `/crew:work` are now **removal stubs with no behaviour**
(`plugin/crew/commands/ticket.md`, `plugin/crew/commands/work.md`, each a
`Read`-only, no-op command that tells the user the lifecycle name and stops)
— confirmed by reading both files in full, not merely their frontmatter.

`review.md` dispatches `crew:reviewer` at this anchor
(`plugin/crew/commands/review.md:451,467`), **not** the pre-1.0
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
`plugin/crew/hooks/scripts/role-write-guard.sh:380-386` resolves its own
private python (`_resolve_role_write_python`, `:43-` — hand-copied from
`_common.sh`'s `crew_py_strict`, not shared, "because it is the one hook
that can BLOCK a tool call and its test suite patches this file textually",
comment at `:34-41`); if no candidate resolves at all, or one resolves but
the interpreter then fails to launch (`role-write-guard.sh:399-414`, any
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
Since T-0051 the two notify twins are thin wrappers: they keep the claim and
hand the payload to `plugin/crew/hooks/scripts/crew_notify.py` (`hook`,
`send`, `config`), which owns the config layering (`resolve_config`, so a
lane worktree reads the main checkout's config), the `notification_type`
filter, the subject line, the dedupe and episode records under
`<git-common-dir>/crew/notify/`, and the Telegram/Teams send. DERIVED:
`plugin/crew/hooks/scripts/notify.sh` and `plugin/crew/hooks/scripts/notify.ps1`
name no provider endpoint (asserted by `plugin/crew/tests/test_crew_notify_hooks.py`).

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
default functions.** Measured 2026-10-04 on T-0066's branch after merging main `edb2b8ff`
(first measured 2026-09-27 on T-0023's merge of main `502cb137`), module resolved from this checkout
(`plugin/crew/hooks/scripts/crew_config.py`), not an installed plugin cache:

| | Leaves | Source |
|---|---|---|
| `default_config()` | **133** | `plugin/crew/hooks/scripts/crew_config.py:245` |
| `default_global_config()` | **75** | `plugin/crew/hooks/scripts/crew_config.py:432` |
| repo-only | **58** | the set difference |

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
T-0024's landing merge adds no leaf (it changes neither template nor `crew_config.py`).
Re-executed on T-0072's merge of `bebbb97f`: 123 / 68 / 55 / 0 - T-0072 added
`autopilot.deploy` to `default_config()` only. Re-executed on T-0072's merge of `67caa4b8`
(T-0018 landed): 123 / 68 / 55 / 0 - T-0018 added no config leaf. Re-executed at `80326b1d`
(T-0072 on top of T-0024's `8de3c669`): 123 / 68 / 55 / 0.
Re-executed on T-0075's merge of `bebbb97f` (T-0023 landed): 122 / 68 / 54 / 0 - T-0075 added no
config leaf; unchanged again on its merges of `67caa4b8`, `d2fbd408` and `e6e10432`. Re-executed on
T-0075's merge of `f54af3fa` (T-0072 landed): 123 / 68 / 55 / 0, T-0072's `autopilot.deploy`.
On T-0010-solo: re-executed on its merge of `67caa4b8` (T-0018 landed), at `c817782f`: 124 / 68 /
56 / 0 - T-0010 added `autopilot.approval` and `autopilot.questions`, repo-only through the same
`autopilot` block (123 / 67 / 56 on T-0010-solo before the merge); its merge of `f96e9ec9` still
read 124. Re-executed on T-0010-solo's merge of `6387ab49` (T-0072 landed), at `d7c7c75c`: 125 / 68 /
57 / 0 - T-0072's `autopilot.deploy` and T-0010's two keys, all repo-only. Re-executed on T-0010-solo's merge of
`e878cc31` (T-0075 landed as crew 1.0.59): 125 / 68 / 57 / 0 - T-0075 added no config leaf.
Re-executed on T-0028 at `c43a54c1`: 127 / 70 / 57 / 0 - T-0028's `qa.kimi.model` and
`dev.kimi.model`, in both layers. 
Re-executed on T-0040's branch (off `6387ab49`): 125 / 70 / 55 / 0 - T-0040 added
`shellRoute.mode` and `shellRoute.distro` to both `default_config()` and
`default_global_config()`, so repo-only is unchanged. Re-executed on T-0040's landing merge of
`6a8c60b1`: 127 / 70 / 57 / 0 - T-0010's two repo-only keys and T-0040's two in both layers
(`plugin/crew/hooks/scripts/crew_config.py:340` and `:610`).
Re-executed on T-0040-land's merge of main `844bfc36`: 129 / 72 / 57 / 0 - T-0028's two and
T-0040's two, all in both layers. `plugin/crew/tests/test_crew_config.py:347` asserts 129.
Re-executed on T-0061's branch after merging main `34d9f267`: 130 / 72 / 58 / 0 - T-0061's
repo-only `tickets.baseBranch`, read from the resolved repo config (`crew_common.repo_config_file`) by
`scope_base.read_base_branch` (`plugin/crew/hooks/scripts/scope_base.py`), not through
`crew_config`; a value naming no commit makes `scope_base.resolve` answer source `unknown`
with no base (DERIVED). Re-executed on main `edb2b8ff` (T-0013 landed): 132 / 74 / 58 / 0 -
T-0013's `resume.typeDelaySeconds` and `resume.readyTimeoutSeconds` in both layers.
Re-executed on T-0066's branch after merging main `155fe6d8` (crew 1.0.342), which changed no config key: 133 / 75 / 58 / 0 -
`git.forbiddenTrailers` in both layers on top of T-0013's 132 (131 / 73 / 58 / 0 on its earlier
merge of `c9263465`). Re-executed on T-0053's branch after merging main `86d96fa1`: 136 / 75 / 61 / 0 -
T-0053's three repo-only `autopilot.sleep` keys on top of those 133. Re-executed on `batch-7-build` after merging T-0011 (#353) onto main `47f71e93`, which asserts 138: 141 / 81 / 60 / 0 -
T-0011's `autopilot.ship`, `autopilot.knownFailures` (an empty list, one leaf) and `autopilot.ciTimeoutMinutes`, repo-only
(`crew_state.REPO_ONLY_AUTOPILOT`). `plugin/crew/tests/test_crew_config.py` asserts 141.
Re-executed on T-0051's merge of main `abddc302`: 143 / 83 / 60 / 0 - T-0051's `notify.realertHours` and
`notify.questionTypes`, both layers, on top of main's 141; `plugin/crew/tests/test_crew_config.py` asserts 143.
T-0004's `CHANGELOG.md` entry
now says "117 -> 119" (`:1109` on T-0094's branch after its merge of `8ab733d7`, T-0094's entry and its review-round-2 bullets above T-0010's, re-read with `grep -n`; `:1045` at main `bbd9a66d`; `:993-994` at `62744965` on T-0094's branch before that merge; `:1039` on T-0010-solo's merge of `e878cc31`, T-0075's entry and
T-0010's above it; `:915-916` on T-0010-solo at `d7c7c75c`; `:928-929` at `3648f59a`, after T-0075's merge of `6387ab49` put T-0090's, T-0089's and T-0092's entries above it and its round-5 fixes grew its own; `:825-826` at `938e3b11`, after T-0075's round-4 fixes grew its own entry; `:807-808` on T-0075's merge of `f54af3fa`, after T-0072's entry went in above it; `:759-760` at `3724731b`, after T-0075's merge of `e6e10432` put T-0079's entry above it and its round-3 fix grew its own; `:653-654` at `f54af3fa`; `:703-704` since T-0075's merge of `5050ea3b` put shipstation's entry above it, `:692-693` after its merge of `f96e9ec9` put T-0077's entry above it, `:666-667` on T-0075's merge of `d2fbd408`; `:608-609` at `d2fbd408`, before T-0075's entry went in above it; `:545-546` on T-0075's branch before that merge; `:515-516` at `67caa4b8`, before T-0024's four entries and T-0075's went in above it;
`:436-437` at `bebbb97f`, before T-0018's; `:390-391` at `db14619c`, before T-0023's; `:276-277` at `f0b12ee6`, before T-0021's; `:228-229` at `2b18f7ab`, before T-0042's), matching the `07ca3972` execution; it said "116 -> 118" when this
paragraph was first written. T-0005's entry states no leaf count; T-0023's says 121 -> 122; T-0072's says 122 -> 123;
T-0010's says 123 -> 125.

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
`unknown`, and `unknown` counts as `yes`); `_terraform_verdict` (`:2980`) decides. The sidecar
is `.crew/tfplan/<sha256>.json`, written outside the hook by
`plugin/crew/hooks/scripts/crew_tfplan.py` (`summarize`, `:174`; `main`, `:237`), which reads
the plan's workspace out of the plan file itself (`plan_workspace`, `:123`). The config is
`crew_guards.ENVIRONMENTS_DEFAULTS` (`plugin/crew/hooks/scripts/crew_guards.py:251`):
`environments.nonProd` is repo-only, `environments.prodUnattended` ratchets (below). DERIVED from
the docstrings and definitions cited; the verdict table itself is `plugin/crew/CONFIG.md`'s
`environments.*` section, not re-derived here.

**GitHub Actions deploys, slice 1 (T-0045).** `plugin/crew/hooks/scripts/crew_ghdeploy.py` reads an
environment's `github` entry out of `.crew/verify.json` (`_environment`, `:496`; `entries`, `:224`),
validates each against a closed key set (`KEYS`, `:99`) and value grammar (`VALUE`, `:96`;
`entry_problem`, `:186`; the ref as a branch name, `_ref_problem`, `:125`), requires `deploy` to be
exactly the entries' prefixes (`check`, `:542`; `prefix`, `:237`), and applies L-1503's promote-gate
rule, refusing when EITHER gate refuses: twin keys under Python's or .NET's fold and an empty key at
any depth (`_no_twins`, `:289`; the 27 .NET-only pairs, `_DOTNET_ONLY_FOLDS`, `:265`), bad names,
a null, non-string or ConvertFrom-Json date-time `deploy` (`_is_dotnet_date`, `:347`), a list or
object `requireHuman` (`gate_problem`, `:384`) and JSON nested past a fixed 200 levels, scanned iteratively (`_MAX_DEPTH`, `:423`; `_depth`, `:426`)
are `gate-refuses-map`; each dispatch is printed with `gated-as:` - every environment whose
`deploy` matches it literally, ignoring case under either gate's fold, either way round, after CR
stripping (`gate_matches`, `:407`; `simulate_gate`, `:478`, is the agreement tables' entry point).
It prints the dispatch for HEAD (`dispatch`, `:245`), runs only `git rev-parse HEAD`, the git
`crew_common.require_tool` resolves (`_head`, `:528`), and writes nothing; no hook calls it yet,
and promote-gate ignores the `github` key. DERIVED from the definitions cited. Its unwired
mutations are `plugin/crew/tests/ghdeploy_mutations.py` (L-0650 wires them). Added at HEAD after
the anchor; the anchor was not moved for it.

**The literal-word allowlist (T-0005 Steps 8-10).** Before the lexer reads
anything, `scan` calls
`_literal_gate` (`plugin/crew/hooks/scripts/cloud_guard.py:2789`, called at `:2838`, and only at
depth 0 - the raw command, never the lexer's own nested extractions): a line that RUNS terraform,
terragrunt or tofu and holds a word that is not a plain literal (`crew_guards.first_non_literal`,
`plugin/crew/hooks/scripts/crew_guards.py:1206`) yields one `terraformApply` finding whose scope
`op` is `OP_UNREADABLE_LINE`; `_terraform_verdict` answers it before reading any plan or
environment (ask, denied unattended; `block` denies). "Runs" is Step 9's trigger,
`crew_guards.command_trigger` (`:2408`; `command_names_terraform` `:2419` returns its word): its
own bash reader, `_GateReader` (`:1251`), splits the raw text into argv lists, and `_argv_trigger`
(`:1941`) fires on a command word that dequotes to one of the three after `_unwrap`'s wrappers, on
a `bash -c`/`eval`/`pwsh -c` payload or substitution that does, or on an unreadable command word
when the line names terraform, `destroy`, `apply` or `workspace`. Anything the reader does not
read with certainty falls back to Step 8's any-word trigger, `crew_guards.names_terraform`
(`:1194`). PowerShell lines use the same command-word rule since Step 10, `crew_guards.ps_trigger`
(`:2380`, per command `_ps_argv_trigger` `:2294`), read with the lexer's `_lex_ps`: `&`, `.`,
`terraform.exe`, a path, `Start-Process`, `pwsh -c`, `bash -c`, `Invoke-Expression` (its
parameters read by `ps_eval_script` `:2257`; a script that is not a literal string, or a
parameter it does not know, is unseen), `$(...)`, and since T-0047 the same listed wrappers bash strips, through
the same `_unwrap`; a quoted or grouped first word with no `&` is expression mode, never run
(the lexer marks `called`, `opens` and `groups` on each `_Cmd`). Since the third review of
#347 a structural backstop, `_ps_backstop` (`:2212`, counting through `_ps_accounted` `:2187`),
makes a PowerShell line could-not-tell unless every mention of a guarded tool in its raw text is
accounted for: the command word of a command the guard judged, a literal script given to
Invoke-Expression, or -- with no runner (launcher, eval, alias definition, `return`/`throw`/
`exit`, a command word that is not a plain name) on the line -- a literal argument of a plainly
named command or a string only printed or assigned; a group or a bare array among terraform's
own arguments is could-not-tell too.
The trigger returns `(word, unseen)`: `unseen` marks a command the lexer is not known to read (an
opaque script runner such as `flock` or `ssh` whose own words name terraform, `find -exec`'s found
path, zsh's `=terraform`, the reader's give-up, an alias, and the name a line copies or links
terraform to, run with a destroy/apply/workspace operand - `_copies_terraform` `:2028`, and an
option a listed `xargs`/`parallel`/`aws-vault`/`unbuffer` does not know, recorded on the gate's
`GateFed` (`:1776`), which names that wrapper and option in the reason), and an
unseen line is could-not-tell even when every word is plain. Since Step 10 there is no
unknown-wrapper fallback and no data-command exemption: an argument naming terraform is data
unless the command word is terraform (README "What the guard does not catch" lists what that
leaves out). A read-only terraform/tofu subcommand (`_tf_read_only`, `:1861`, which reads terragrunt past its options and `run-all`, and `workspace select` with no `-or-create` that is not false, `_selects_only` `:1894`; a select `xargs`/`parallel` may append `-or-create` to is unseen) does not trigger.
The helpers live in `crew_guards.py` because `cloud_guard.py` sits at `.pylintrc`'s
max-module-lines (3385 of 3400 at `e2d2f9f0`); `cloud_guard._GATE_HELPERS` (`:2785`) passes the
lexer's `_unwrap`, `_shell_args`, `_pwsh_payload`, `_ps_normalise`, `_head_name` and `_lex_ps` in,
so `crew_guards` still imports nothing from it. The lexer's own terraform reading skips options
before the subcommand (`crew_guards.tf_skip_options` `:1559`, terragrunt's boolean options in
`_TF_GLOBAL_FLAG_OPTS` `:1545` taking no value; used by `_terraform_destructive` `:1548`, which also reads terragrunt's `apply-all`,
`destroy-all`, `stack run`, `graph` and `backend delete` through `crew_guards.tg_other_op`
`:1579`; `terragrunt exec` is unwrapped as a wrapper by `tg_exec_rest` `:1602`), so
`terragrunt --working-dir infra destroy` is a destroy, and `_unwrap` reads a listed wrapper's
options as GNU getopt does (`crew_guards.skip_wrapper_options` `:1619`, through `wrapper_rest`
`:1788`): `xargs`, `parallel` and `sem` with complete tables (`WRAPPER_TABLES` `:1771`),
`aws-vault exec` and `unbuffer` by `unwrap_listed` (`:1825`). DERIVED from the code cited.

**The ratchet registry (`_RATCHETED`, `plugin/crew/hooks/scripts/crew_config.py:2541-2653`)
now holds 14 keys**, built in seven steps (a literal dict of two at `:2541`, four `.update()`
calls at `:2556`, `:2569`, `:2580` and `:2590`, and two single-key assignments at `:2626` and
`:2649`) rather than one table: `pm.authority`, `install.policy`, the 6 `GUARD_NAMES` keys, the 2
`PROD_GUARD_NAMES` keys, `guards.roleWrites`, `guards.cloudGuard`,
`change.requireForProduction` and `environments.prodUnattended` (T-0005) =
2 + 6 + 2 + 1 + 1 + 1 + 1 = 14. Counted by reading the construction sites and confirmed with
`len(crew_config._RATCHETED)` on the T-0005 landing merge and again on T-0023's merge of main
(14), not by trusting the literal alone — the literal at `:2541-2552` holds only 2. (Before T-0005 this said "five steps" for 13 keys; the
sites were already six then — the literal, four `.update()` calls and one assignment.) The
same key is registered in `crew_guards.RATCHETED_KEYS`
(`plugin/crew/hooks/scripts/crew_guards.py:545-549`). `autopilot.*` is not ratcheted
(T-0004 added no `_RATCHETED` entry).

## The writers and the `/crew:config` menu (T-0075, crew 1.0.55)

**DERIVED from the source at `3648f59a`** (T-0075's review-round-5 fixes, its merge of main
`6387ab49` and the 1.0.55 bump; first derived at `7d217751`, re-read at `8cabe586`,
`3724731b` and `938e3b11`). Two writers, one per layer, both in `crew_config.py`, one file layer under both, and
nothing else writes either file on the menu's behalf. Each round-2, round-3, round-4 and round-5 finding is
closed by where the check sits, not by a patch at the call site.

- **One file layer, `plugin/crew/hooks/scripts/crew_config_files.py` (new, no crew imports).**
  `Lock` (`:104`, `:90` before T-0075's landing added `os_error_text`) is an `O_CREAT|O_EXCL` `<path>.lock` beside the config holding the PID (a failed PID write
  removes the lock file before re-raising, `:134-141`, round 5), waiting
  `LOCK_WAIT_SECONDS` (`:43`) then raising `Busy` (`:63`); it serialises crew's own writers, not a
  hand edit. `read_strict` (`:181`) is the four-case read (`Unreadable.kind` `absent`,
  `unparsable`, `empty`, `notobject`, `:53`), never `load_config`'s `{}` collapse;
  `read_restorable` (`:199`) is that read on a REGULAR file only (`O_NOFOLLOW`, judged by `fstat`,
  kind `notregular`), the one read delete and restore share. `restorable` (`:171`) is the predicate
  both accept by. `digest` / `state_digest` (`:238`, `:243`) are sha256 of the bytes, `ABSENT`
  (`:50`, the string `absent`) for no file; `is_expectation` / `expectation_problem` (`:248`,
  `:290`) judge an `--expect*` value. `read_tolerant` (`:255`) is the machine file read as
  `read_global_config` reads it plus its `state_digest`; `machine_lock` (`:273`, round 4, replacing
  `lock_if_dir`) is the machine lock, ALWAYS taken: it creates `~/.claude/crew/` when absent (never
  the file) and is taken before any repo lock, crew's one nesting order. `is_dotted` /
  `parse_assignments` (`:285`, `:298`) are the one dotted-path and `PATH=JSON` rule both CLIs use.
  `replace_bytes` / `replace_text` (`:331`, `:352`) write a PID-suffixed sibling, fsync,
  `os.replace`, keeping CRLF and a UTF-8 BOM. `update_json` (`:364`) reads, compares `expect`
  against the `state_digest` (raising `Conflict`, `:67`), mutates and replaces inside the lock.
  `move_no_clobber` (`:466`) never replaces an existing destination by the rename itself (POSIX:
  `os.link`, then `_unlink_source` `:418`, which renames the source onto a reserved name
  (`_reserve` `:406`) and removes that name only when it IS the linked inode; a foreign
  replacement is linked back to the source and its reserved `*.moving` name is KEPT, never
  unlinked - another writer may replace the source again, making it that file's last name (round
  4) - and every failure after the rename is `Displaced` (`:71`, an `OSError` carrying `parked`),
  which `move_no_clobber` passes through without undoing its link to the destination, since the
  original may have no other name; Windows: `os.rename`); `move_aside` (`:508`) is that move plus
  the moved bytes, `create_bytes` (`:517`) a new file by the same move.
- **Per-leaf judgement and per-leaf writing, shared by both planners.** `leaf_updates`
  (`crew_config.py:2674`) flattens every update to its leaves, a whole-block value included, so a
  consent key cannot ride inside a block; `value_allowed` (`:2790`) judges each leaf: the layer's
  path rule (`MACHINE_REFUSED` `:2710` via `_consent_refusal` `:2762`, and `is_global_path` `:748`
  at the machine layer; `REPO_REFUSED` `:3003`, `is_repo_path` `:3060` (`_shape` `:2721` is a leaf
  or open; since round 5 `_shape` also returns `under` for a path past a template leaf, `:2729`) and `REPO_VETO_ONLY` `:3024` by identity, `is_repo_veto` `:3027`, at the repo layer), a
  path under a leaf (`:2798`) and an object at a leaf (both round 5, both layers), a
  block emptied or replaced by a scalar, the null rule (`null_means`, `:2747`), then membership in
  `enum_values` (`:2656`). `assignments` (`:2693`) is what is WRITTEN: the same leaves for a block
  (its untouched siblings, unknown keys included, survive; the widening is marked on the leaf),
  and one whole pin per role for an open role table. `_plan_on` (`:2903`) is both planners on an
  already-read file. `merged_problems` (`:2849`) then judges the FILE the write would produce,
  every known leaf by `_content_problem` (`:2822`): an enum value outside its tuple (a legacy null
  tolerated), a key under a leaf or an object at a leaf (`:2835-2838`, round 5, fixable in the
  same write since a leaf under a touched key is skipped), a consent key in the machine file, an armed veto-only key in the repo file, each
  named "pre-existing"; unknown keys and write-only refusals (`REPO_REFUSED` keys in the repo file,
  a repo-only key in the machine file) are not judged (JUDGEMENT in the docstring). Then
  `validate_providers` (`:179`) runs on the merged file; since round 4 it refuses a `qa.order`
  that is neither a list nor `null` (`:208-210`) before iterating it, so a scalar there is a
  refusal with exit 2 at both layers, a value already in the file included, never a `TypeError`.
  Since round 5 one loop over `dev` then `qa` (`:225-239`) also refuses a `roles` table that is
  not an object or `null`, and an entry under it that is not a pin object or `null`, before the
  pin's provider check - so `qa.roles=1` can no longer wipe every pin, at either layer, in the
  update, the merged file and the menu's probe alike.
- **Machine:** `plan_global_write` (`:2936`) on `global_snapshot` (`:2887`, strict: an
  unparsable or non-object machine file is refused, never merged onto `{}`; absent is `ABSENT`) /
  `write_global_config` (`:2955`), which re-runs `_plan_on` on the bytes `update_json` read under
  the lock, `expect` (a digest or `ABSENT`) refusing a changed file (`GlobalWriteConflict`);
  any other `OSError` from the directory, the lock or the write is a `GlobalWriteRefused`
  naming the path (`:2978`, round 5), exit 2 and never a traceback.
- **Repo:** `plan_repo_write` (`:3136`) on `repo_snapshot` (`:3124`, strict: absent or malformed
  is refused, never created) and `machine_view` (`:3155`, the filtered machine file and its
  `state_digest` from one `read_tolerant`) / `write_repo_config` (`:3162`), the same
  compare-and-swap (`RepoWriteConflict`), plus `expect_global`: the machine file is read once under
  `machine_lock` (taken before the repo lock, even when `~/.claude/crew/` is absent) and a changed
  one is refused; an `OSError` from the machine directory, either lock or the write is a
  `RepoWriteRefused` (`:3192`, round 5). `!` on a widening: the ratchet by what is in force (`repo_widens`, `:3068`) and
  the `_REPO_WIDENING` table (`:3037`).
- **CLI:** `--set PATH=JSON [--repo] [--apply [--expect DIGEST|absent] [--expect-global
  DIGEST|absent]]` through `_set_layer` (`:3282`), which prints `digest:` of the bytes the plan
  read and, with `--repo`, `machine digest:`; `main` (`:3316`) refuses a malformed path, value or
  digest with exit 2. `wc -l` is 3399 at `3648f59a`, under `.pylintrc`'s 3400.

`plugin/crew/hooks/scripts/crew_config_menu.py` (new) is what the menu procedure
(`plugin/crew/skills/crew-setup/config-menu.md`, followed by both `/crew:config` with no argument
and the alias `/crew:config-setup`) calls. `menu_spec` (`crew_config_menu.py:317`) builds the rows
from `leaf_paths(default_global_config())` (machine, plus `platform.*` and `schema` read-only,
`_MACHINE_READ_ONLY` `:301`) and `leaf_paths(default_config())` (repo), grouped by `AREAS`
(`:48`), and returns the layer's `digest`. `choices` (`:215`) offers a value only when
`_probe_for`'s probe (`:168`) - the layer's own planner on one snapshot (and, at the repo layer,
one `machine_view`), with the session's `--pending` set plus the candidate - accepts it; when every
candidate is refused the row is read-only with the planner's first refusal. `save` (`:480`) plans
both layers before writing either (`_plan_both`, `:446`: the repo plan judged against the machine
file as this Save leaves it), prints the machine digest whenever anything changes and the repo
digest when it does, checks every given `--expect-machine` / `--expect-repo` by presence (never
truthiness; `_current_digest` `:441`) before either write and passes each to its writer, binding
the repo write to the machine digest too - after a machine write in the same Save, to the bytes it
wrote (`_machine_as_written`, `:471`); a refusal after a layer landed says which (exit 1). Delete
is two phases: `plan_delete` (`:800`) holds the file's bytes, its digest, the machine digest and
the resolved machine path (`machinePath`; `_machine_digest` `:796`, read before and after the
preview) and refuses what `read_restorable` refuses (a symlink included), pointing at
platform-sync's `config.json.broken` heal; `delete_preview` (`:637`) walks the known leaves AND
the file's own (`_file_leaves`, `:617`: `removed` for unknown keys, `redetected` only for the
`platform.*` leaves in `_redetected()` (`:629`, built from `crew_platform.DERIVED_KEYS`, the keys
platform-sync writes; any other `platform.*` leaf is `removed`, round 4), `heldAgainst` for a
ratcheted key a narrowing keeps, `_held_by_ratchet` `:693`), and its re-detected header promises
no value (a key this machine gives none for is left unset); `delete_repo_config` (`:921`) prints
`repo digest:` and `machine digest:` under the preview; `apply_delete` (`:852`) needs the typed
repo name (`repo_name`, `:569`) and both digests (`_unbound`, `:836`), then takes
`machine_lock(machinePath)` and then the repo config `Lock` and reads the machine digest AGAIN
inside them (a machine write since the preview refuses, exit 2, nothing deleted; round 4), moves
the file to a fresh `.crew/config.json.bak-<UTC>` (`_free_backup`, `:585`) with `move_aside` and
compares the moved bytes with the held ones - a changed file is moved straight back with
`move_no_clobber`, never over a file saved in the gap (exit 2; exit 1 when a new file appeared);
a `Displaced` move exits 1 naming the backup, the config path and the kept `*.moving` name - and
prints three restore lines (`restore_lines` `:773`, `command_forms` `:756`: sh `shlex.quote`, cmd
double-quoted with forward slashes and a `%` warning, PowerShell `&` with single quotes).
`restore_repo_config` (`:962`) accepts exactly what `_valid_backup` (`:946`, location, name, then
`read_restorable` on the backup itself) accepts, moves any current file aside under the lock
first (a `Displaced` move-aside exits 1 with every path named), writes the bytes with
`create_bytes` (a file that appeared meanwhile is refused, never replaced) and reads them back.
`validate_change_set` (`:1010`) and `_usage_problem` (`:1039`) refuse a malformed `--changes`,
`--pending` (an explicitly empty one included), digest, `--confirm` or `--from` with exit 2.
Tests: `plugin/crew/tests/test_config_files.py`, `plugin/crew/tests/test_config_menu.py`,
`plugin/crew/tests/test_crew_config.py`; 98 mutations in `plugin/crew/tests/sabotage_config.py`
(`CONFIG_MENU_MUTATIONS`, `len()` at `938e3b11`: 50 through review round 2, 31 for round 3, 17
for round 4; registered in `sabotage.py:79`, appended at `:3065`); `.crew/verify.json` rule 7
(`:159-176`, one longer since T-0028 added `plugin/crew/skills/crew-setup/SKILL.md`) maps all of
them plus the three modules.

## `.crew/config.json` vs `.crew/crew.json` — the open 1.0.x authority question

**DERIVED, and this is the open TODO the task description names.** Two
different modules read two different files as "the repo's crew config", and
they disagree:

- `crew_config.py` (used by `verify-gate.sh`,
  `role-write-guard.ps1`'s config lookups, and everything the ratchet/guard
  machinery above touches) reads **only** `.crew/config.json`
  (`plugin/crew/hooks/scripts/crew_config.py:1307`, through `crew_common.repo_config_file`
  since T-0088, which in a linked worktree with no config of its own reads the
  main checkout's; and the module's own
  docstring at `:1` — "Owns the single definition of a fresh
  `.crew/config.json`").
- `crew_context.py`'s `load_crew_config`
  (`plugin/crew/hooks/scripts/crew_context.py:122-133`) tries `.crew/crew.json`
  **first**, falling back to `.crew/config.json` only if `crew.json` is
  absent — its own docstring: "1.0's `.crew/crew.json`, else 0.x's
  `config.json`".
- Only `/crew:migrate` (`crew_migrate.py`, `--apply`) ever writes
  `.crew/crew.json`; `/crew:init` still writes only `.crew/config.json`
  (`TODO.md:4003`, "T2 (lane D, additive) deferred items", filed
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
  `crew_autopilot.settings` (`plugin/crew/hooks/scripts/crew_autopilot.py:976`)
  sides with `config.json` explicitly: it reads through
  `crew_config.resolve_config` and warns when `autopilot` is set in
  `crew.json` but not `config.json` ("crew does not read [it] for this key;
  move it to .crew/config.json", `:814-818`, in `_settings_at` `:788`). T-0023's
  `crew_route.settings` (`plugin/crew/hooks/scripts/crew_route.py:336`) does
  the same for `route` (`:361-364`) - and it is the sharper case, because
  its only caller is `crew_context.route_item`, inside the one hook that reads
  `crew.json` first for `memory.inject`: one hook, two files, by key.
- DERIVED (T-0105): `/crew:migrate` carries a config's `autopilot` block to
  crew.json's top-level `autopilot` (`MAPPING` row,
  `plugin/crew/hooks/scripts/crew_migrate.py:121`), not `unmapped`, and says
  the copy is never read: `AUTOPILOT_FILE_NOTE` (`:136`), added by
  `migration_notes` (`:307`, `:315`) to the report and crew.json `notes`.
  Crew still reads the key from `config.json` (the personal keys also from
  the machine-global file, stricter wins, §20a), never crew.json; the mapping means the
  `settings` warning above fires once `config.json` is gone.
  Flagging it is this
  note's job; **deciding which file should win, or whether `crew_config.py`
  should learn to read `crew.json` too, is a decision for scribe to record,
  not this note's to make.**

`SCHEMA_CURRENT` for `config.json` is still **7**
(`plugin/crew/hooks/scripts/crew_state.py:179`) — unchanged by the 1.0
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
  (`plugin/crew/skills/crew-setup/phases.md:191-197`, `plan-windows-default`),
  `/crew:onboard` (`plugin/crew/commands/onboard.md:199`, the identical
  helper, "so a repo onboarded standalone gets the identical question"),
  and `/crew:migrate` (`plugin/crew/commands/migrate.md:78`,
  `apply-migrate`).

### Which terminal: the session's own process (T-0016, crew 1.0.333)

Read in full on `T-0016-build` after review round 1 and the merge of main ce235468; line citations taken with `grep -n` there.

- DERIVED: the bash flavour binds after `resolve_method` and before returning `send`
  (`plugin/crew/hooks/scripts/crew_autocycle.py:1007`, `bind_to_session` at `:1052`), so the
  sender's sent-marker claim (`plugin/crew/hooks/scripts/auto-clear.sh`, after the plan) never
  runs for a binding refusal. `session_owner` (`crew_autocycle.py:568`) walks the hook's chain to
  the first `${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/<pid>.json` whose `sessionId` and
  `procStart` match; `classify` (`:607`) needs kind `interactive`, entrypoint in
  `TERMINAL_ENTRYPOINTS` (`:108`, `{"cli"}`) and a non-zero `tty_nr` for `terminal`;
  `prove_target` (`:731`) re-proves the pane/window from the owner, with `other_sessions`
  (`:635`, None when a live process's record cannot be read) and `_shared_window` (`:695`, the
  descendant tty scan); for tmux every process from the owner up to the pane must be on the
  owner's tty or none (`:769`, review round 1). Headless becomes method
  `notify-headless`, its text from `headless_notice` (`:1024`), printed and claimed at
  `plugin/crew/hooks/scripts/auto-clear.sh:312`.
- DERIVED: `plugin/crew/hooks/scripts/auto-clear.ps1` carries the same rules natively
  (`Get-CrewSessionOwner` `:678`, `Get-CrewSessionClass` `:706` with no tty, the binding block from
  `:767`, the owner-anchored window walk from `:902`); `Get-CrewProcLookup` (`:616`) tells an exited
  parent (the top of the chain) from an unreadable one (refuse).
- DERIVED: every process fact goes through `_proc`, and `CREW_AUTOCLEAR_PROC_STUB`
  (`crew_autocycle.py:101`) replaces the whole table, read only while CREW_AUTOCLEAR_INHIBIT is set
  (`_stubs_allowed`, `:409`, as is the window stub); the suite's fixtures are
  `plugin/crew/tests/crew_fixtures.py:1312` (`write_session_record`), `:1334` (`proc_stub`) and
  `:1357` (`bind_session`), which T-0017 builds on.
- JUDGEMENT: the hook-anchored checks still run first in the bash flavour (their lines are
  sabotage anchors); `prove_target` is the stricter proof and the one that decides.

### Auto wrap-up before the clear (T-0017, crew 1.0.334)

Read in full on `T-0017-build` (stacked on `T-0016-build` d7eb9fbd) before its version commit; line
citations taken with `grep -n` there.

- DERIVED: `context.autoClear.wrapUp` is read by `settings` with `enabled`'s machine-opt-in rule
  (`plugin/crew/hooks/scripts/crew_autocycle.py:215`) and arms only through `wrapup_armed`
  (`:407`: `enabled`, `wrapUp` and `in_scope`). Its default is `None`
  (`plugin/crew/hooks/scripts/crew_state.py:717`) and a repo may only veto it
  (`plugin/crew/hooks/scripts/crew_config.py:3015`).
- DERIVED: `plan` runs `wrapup_check` (`crew_autocycle.py:460`) after `verify_handoff` and before
  `resolve_method` (`:1157`), so a refusal (reason prefixed `wrap-up: `, `:402`) never reaches the
  binding or the sender's claim; `plugin/crew/hooks/scripts/auto-clear.sh:260` also prints it as a
  `systemMessage`. `plugin/crew/hooks/scripts/auto-clear.ps1:727` reads `wrapUp` natively and runs
  the same check through `crew_autocycle.py wrapup-check` (`:734`); no python refuses.
- DERIVED: context-watch sends `wrapup_message` (`crew_autocycle.py:514`) instead of either
  `autoWrapUp` text when armed (`plugin/crew/hooks/scripts/context-watch.sh:597`,
  `plugin/crew/hooks/scripts/context-watch.ps1:630`), and in the marker branch escalates a failed
  check once through `.crew/.wrapup-escalated-<key>` (`context-watch.sh:528`,
  `context-watch.ps1:515`); the CLI verbs are `_wrapup_cli` (`crew_autocycle.py:1381`).
  SessionStart removes the claim (`plugin/crew/hooks/scripts/handoff-read.sh:20`,
  `plugin/crew/hooks/scripts/handoff-read.ps1:200`).
- DERIVED: `/crew:handoff --wrap-up` (`plugin/crew/commands/handoff.md:36`) is the one wrap-up
  procedure; `/crew:autopilot`'s context-watch step names it (`plugin/crew/commands/autopilot.md:106`).
- JUDGEMENT: the only enforcement is the clear. Crew checks the commit and the handoff's fields,
  never that the step's test passed (verify-gate stands down on `stop_hook_active`).

## Auto-resume after `/clear` (T-0006, crew 1.0.40; T-0042, crew 1.0.43)

`plugin/crew/hooks/scripts/crew_resume.py` owns the `resume:` line a handoff
carries (read in full at `6d35ef8c`, its changed functions re-read at `2bb92f32`, and every
function T-0042 touched re-read at `068db4ff`; every line citation below re-taken with `grep -n`
at `53f5482c`): the closed
allowlist `RESUME_COMMANDS` (`:38`, a module constant so no repo can widen it), the grammar
(`parse_resume`, `:92`; ticket digits are ASCII `[0-9]`, `:84`; the automatic PreCompact
skeleton - `crew_autocycle.SKELETON_MARK` - is refused whole before any line is read, `:103-104`),
the opt-in (`settings`, `:173` - armed only when the
machine file `~/.claude/crew/config.json` says `resume.auto: true`; a repo
`false` in `.crew/crew.json` or `.crew/config.json` vetoes, a repo `true`
grants nothing) and the read-only `decide` (`:738`), where the first failing
check wins and every "could not tell" is `wait`, never `run`. It registers no
hook. `crew_context.py`'s SessionStart branch calls it through
`resume_decision` (`plugin/crew/hooks/scripts/crew_context.py:662`) for
`clear`/`compact` only, after `_handoff_verdict` (`:639`), which passes the
staleness VERDICT on rather than whether the archive move succeeded, and a
rule that raises as stale; `resume_line` (`:813`) renders the one injected
line. Nothing starts on its own - the command is named, never sent as
`initialUserMessage`. On `PreCompact` both `handoff-write` flavours call its
`precompact` CLI (`write_precompact_record`,
`plugin/crew/hooks/scripts/crew_resume.py:655`); `decide` trusts a `manual`
record for 600 s and never one it could not have replaced
(`_compact_was_manual`, `:721`). A record a later PreCompact could neither remove nor empty
is MARKED, not predicted: `precompact-<key>.stuck` (`stuck_path` `:630`, `_mark_stuck` `:638`;
the shell flavours write the same marker, `plugin/crew/hooks/scripts/handoff-write.sh:64-65`,
`plugin/crew/hooks/scripts/handoff-write.ps1:430-431`), and a compact is not manual while that
marker exists or cannot be stat'ed; `crew_context.prune_precompact` ages it out with the records.

A handoff resumes only in the session that wrote it (T-0042). On an armed machine every
`PostToolUse` Write/Edit/MultiEdit of the configured handoff is recorded by
`crew_context.record_handoff_author` (`plugin/crew/hooks/scripts/crew_context.py:641`, called
through the never-raising `_record_author_logged` `:1166` from `run` `:1130`, before the
`memory.inject` gate) into `<git-common-dir>/crew/handoff-author.json` (`record_author`,
`plugin/crew/hooks/scripts/crew_resume.py:280`: the note's sha256, `session_id`, and
`session_process()` `:230` - the nearest `claude` ancestor as `{pid, start}`, `None` on any host
without `/proc`). A recorder that cannot take the author lock, or whose write fails - including
one that was only REMOVING this worktree's entry - drops the whole file (`_drop_author` `:351`:
unlinked by `_unlink_author` `:398`, or, where the directory refuses that, blanked in place by
`_blank` `:709`, which reads as unreadable and waits - T-0069). When even that fails it leaves
`handoff-author.json.stuck` (`_mark_author_stuck` `:370`, `author_stuck_path` `:204`), which
`_author_refusal` waits on (present or unknown) until a later record lands and removes it; a
marker that cannot be written either leaves `_author_refusal`'s replaceability check - a record
neither its file nor its directory lets anyone replace or remove is not trusted. So the previous
entry never vouches for a note another session wrote last (T-0042 review rounds 1-2, T-0069). `decide` asks `_author_refusal` (`:479`) after the command checks and before
the state file: `compact` must match the session id, `clear` the process; a missing, unreadable
or sha-mismatched record, or an unidentifiable process, is a `wait`, never a match. `record_run`
(`:806`) is the only writer of
`<git-common-dir>/crew/resume-state.json`, and nothing in the plugin calls it
yet (T-0013's contract). A state file that exists and cannot be read or is not
the shape `record_run` writes is an unknown (`_read_state` `:426`, `_entry` `:448`
return `None`): `decide` waits and `record_run` refuses rather than overwriting it. A PARTIAL
record is that shape too (T-0042, before review round 2): a file with no `worktrees` key, or an
entry of this worktree missing `consumed`, `last`, or last's string `prompt`/`fingerprint`, is
`None`, not "nothing consumed, no loop history"; no entry for this worktree is still `{}`.
Whether it exists at all goes through `_absent` (`:403`): only `FileNotFoundError` /
`NotADirectoryError` is absence, any other stat error is `None` - the round-4 FIX, since
`os.path.lexists` read an unsearchable directory as "no file". `.work/INDEX.md` goes through the
same helper (`_index_rows` `:537`), so an unstat-able index makes the fingerprint unknown.
`record_run` asks consumed-once and the loop guard again under its lock through
the same `_already` (`:510`) `decide` uses, so of two senders holding one `run`
only the first gets `ok`. Tests: `plugin/crew/tests/test_crew_resume.py`,
`plugin/crew/tests/test_crew_resume_hook.py`; mutations
`plugin/crew/tests/sabotage_resume.py` (72 by `len(RESUME_MUTATIONS)` at `53f5482c`); `.crew/verify.json`
rule 27 (`:333-344` since L-0516 inserted rule 10; rule 26 at `:289-299` on T-0094's merge of `8ab733d7`, `:291-301` after T-0094 grew rule 25, `:287-297` before).

## `/crew:autopilot` (T-0004, crew 1.0.41)

DERIVED at `89f73d79` (T-0018) and on T-0010-solo (T-0010), re-read together at `c817782f`, again
at `50a275ea` (T-0010's merge of `f96e9ec9` and review round 4's fixes), and at `d7c7c75c` (T-0010's
merge of `6387ab49`: T-0072's `deploy-allowed`, whose line citations T-0072 re-read on its merge of
`67caa4b8` at `21429244`, joins the same module).
`plugin/crew/commands/autopilot.md` (110 lines since T-0010, 100 since T-0018,
`allowed-tools: Read, Write, Edit, Bash, Agent, Skill`, `:4`) first
routes its whole argument string, single-quoted (`## 0. Route`, `:14-27`), then either
prints `status` (`## 1. status`, `:29-36`, read-only, armed or not) or drives
one ticket through the phase commands **in-session**, following each
command's own procedure; the run refuses unless armed (`:46-47`). The reader
behind it, `plugin/crew/hooks/scripts/crew_autopilot.py` (1999 lines), is
read-only except T-0010's `approve`, only when `approval_policy` allows, which writes what
`crew_ticket.approve` writes for every route: `approval.json`, `scope-tickets.json` on a
ticket's first approval, and a distinct successor plan's NEEDS_REPLAN -> IN_REVIEW ledger move
(module docstring, `:1-152`; the owner's carve-out of 2026-09-27), and T-0074's `auto-reject`,
which writes only the review ledger (below),
with ten subcommands: `next`, `resume`, `settings`, `stops`, `route`, `status`, T-0072's
`deploy-allowed` (read-only too), T-0010's `approve` and `questions-check`, and T-0074's
`auto-reject` - script subcommands, not `/crew:autopilot` ones.
`next_phase` (`:785`) names the next phase from files on disk, first match wins (the table at
`:63-86`); `resume_target` (`:885`) picks the ticket (the handoff's `resume:` line only
when its branch and head match, per `plugin/crew/commands/autopilot.md:48-49`);
`settings` (`:976`, the lookup, then `_settings_at` `:1007`, which `deploy_allowed` reads directly)
arms only on the exact string `plan`, falls back to `maxPhases` 12 for anything not a positive
int, reads `deploy` only as the exact strings in `DEPLOY_VALUES` (`:173`), reads
`maxAutoReplans` as 0 for anything not a non-negative int (T-0074), and warns on each; a `.crew/config.json` that
exists but is not a readable JSON object, or an `autopilot` value that is not an object, reads
`mode` off, both policies `unknown` and `maxAutoReplans` 0 with one warning (`_unreadable_autopilot`, `:956`, which reads
the raw file because `resolve_config` and `merge_defaults` collapse both to the defaults; review
round 4; the check sits in `settings` only, so `deploy_allowed`'s own per-layer probes are
unchanged), while an absent file or block reads the defaults. Its first text line prints `mode`,
`maxPhases`, `deploy` and `maxAutoReplans` (T-0072's line, pinned exactly by
`test_settings_line_names_deploy`; T-0074 put its key here because the second line is a sabotage
anchor), its second `approval` and `questions`. `stops`
(`:1512`) lists every stop from code: `crew_state.AUTONOMOUS_STOPS`,
`FIXED_STOPS` (`:197`; T-0074's `auto-replan-cap` last, and since batch 7 T-0063's `index-disagreement` too), `PROCEDURE_STOPS` (`:216`, three) and
`HUMAN_STOPS` (`:222`, four - brainstorm, plan approval, review acceptance,
open questions; plan approval and open questions wait for a person unless T-0010's policy
allows; review acceptance is FINDINGS with any BLOCK, or a round `review_ledger.py
--auto-accept` refuses, since L-0510; a BLOCK is never accepted by autopilot, T-0074).

**Auto-reject and replan (T-0074).** DERIVED at the anchor below. `autopilot.maxAutoReplans`
(`plugin/crew/hooks/scripts/crew_state.py:1134`, default 0, at most 5) is the switch and the cap.
`auto_replan_policy` (`plugin/crew/hooks/scripts/crew_autopilot.py:519`, the decision in
`_auto_replan_decision` `:539`) allows only when autopilot is armed, the key is 1 or more,
`approval_policy` (`:1263`) allows the successor plan, the ledger loads and is REVIEWED, the
latest round under the current plan (`_current_rounds`) is a completed FINDINGS round whose
counts are three non-negative ints with BLOCK at least 1 and whose single-line `findings` hold
exactly that many `BLOCK|` lines, `rounds_left` is 0, `review_ledger._family_problem` passes (called,
not restated, so the two cannot drift; `test_family_rule_matches_review_ledger` holds them in step),
and fewer than the cap rows are in the ledger's `successors`; anything that raises is "could not
tell". `_phase` passes `_review_phase`'s answer (`:495`) through `_auto_replan_route` (`:634`) only
when `policy` is true, so `status` reads neither route: an allowed `accept-review` becomes
`auto-replan` with the `auto-reject` command, a cap refusal is the `auto-replan-cap` stop naming the cap
and every successor row, and a NEEDS_REPLAN `replan` stops unless `_auto_rejected` (`:657`) finds
`rejected.by == AUTO_REJECT_BY` (`:508`) for the latest round, that round is the current plan's,
the same round checks (`_block_round` `:580`) still pass and the policy still allows: the name alone
is typeable, so it proves nothing (review round 1). `maxAutoReplans` reads at most
`MAX_AUTO_REPLANS` (`:510`, 5). `auto_reject` (`:689`) is the second writer: `review_ledger.reject`
under that constant, refusing with exit 2 and no write otherwise. Tests `plugin/crew/tests/test_crew_autopilot_replan.py`.
JUDGEMENT: the policy is read before `reject` takes the ledger lock (an accepted gap for one
session per ticket), and the constant can be typed by hand with `review_ledger.py --reject --by`,
the forge-local-state threat README's "Scope and approval" already states.

**Ship (T-0011, crew 1.0.349).** DERIVED on T-0011's merge of main `155fe6d8` (re-derived
with `grep -n`); the line numbers in this paragraph are that commit's, not the anchor's. After `/crew:done`
(spec header `status: done`, or INDEX `done` with that header), armed, `_phase` hands off to
`_ship_phase` (`plugin/crew/hooks/scripts/crew_autopilot.py:610`): unarmed is `closed` without
asking gh; a detached HEAD, an unreadable `read_pr` (`:416`), a PR closed unmerged, a working tree
that differs from HEAD (`_clean_tree` `:522`, `git status --porcelain --untracked-files=all`) or
a receipt that no longer stands stops at `ship`; MERGED is `closed` only when the PR's
`headRefOid` and local HEAD are the same full SHA (`_merged_phase`, `:591`; a later
commit or an unreadable head stops at `ship`), and OPEN under `autopilot.ship: pr` is `closed`. `ship` (`:747`) refuses the default branch and a dirty tree before
`git push -u origin <branch>`, takes HEAD once right after the push, opens the PR when none, and
under `merge` polls in `_wait_for_ci` (`:674`): `_head_stop` (`:658`) holds local HEAD and the
PR's `headRefOid` to the pushed commit before and after each `read_checks` (`:437`; a row that
is not exactly `_CHECK_FIELDS` (`:347`) = 5 tab-separated fields is unreadable, measured from gh
v2.46.0's source), and `_ship_gate` (`:557`) re-reads the settings, the spec's risk, the review
families and `_ledger_hash` (`:538`) every poll into `ship_decision` (`:286`, the pure rule;
`SAME_FAMILY` `:272`). `_pre_merge_stop` (`:714`) re-checks the receipt, the ledger hash, both
heads, the tree and `read_merge_queue` (`:476`), then the ledger hash and local HEAD once more;
the merge is `merge_argv` (`:360`), `gh pr merge <n> --merge --match-head-commit <head>`. A merge
call that leaves the PR not MERGED with a queue on (or unreadable) runs `_dequeue` (`:497`), the
one GraphQL mutation, and stops. Tests: `plugin/crew/tests/test_crew_autopilot_ship.py`; no
`SHIP_MUTATIONS` in `sabotage_autopilot.py` on this branch (a harness-only follow-up, T-0087).
Since batch 7 the part that reads no review ledger - `ship_decision`, the gh/git adapter
(`_run_gh`, `_push`, `read_pr`, `read_checks`, `read_merge_queue`, `_dequeue`, the argv builders,
`_branch`, `_default_branch`, `_clean_tree`, `_tree_stop`) and `merged_phase` - lives in
`plugin/crew/hooks/scripts/crew_ship.py`
(crew_autopilot.py had passed pylint's 3400-line cap), and `_run_gh`/`_push` run
`crew_common.require_tool`'s path (L-1508); the cites above are T-0011's, before the move.

**Worktree-aware reads and `commit-refresh` (T-0063, crew 1.0.349).** DERIVED on T-0063-build
at `309575c2`; its line numbers are that commit's, not the anchor's. `_phase` (`plugin/crew/hooks/scripts/crew_autopilot.py:530`) first asks `_main_folder`
(`:353`, called at `:544`): a ticket folder only in the main checkout stops as phase
`folder-elsewhere`, its reason the `cp -r` to make, both paths `shlex.quote`d (`_folder_elsewhere` `:365`);
with no folder here and a main checkout `_main_checkout` could not name, the same phase stops
saying it could not tell whether the folder is in the main checkout, with `why` (review FIX 1,
crew 1.0.349); `resume_target` asks the same at `:852`. The folder is named, never read: `crew_ticket.ticket_dir` and the
scope guard keep reading this checkout's. The INDEX row is `_index_row` (`:329`, called at
`:552`): this checkout's row (`_index_status` `:291`, now taking an `index_path`), else the main
checkout's, whose path comes from `_main_checkout` (`:303`: `(None, "")` with no subprocess when
`.git` is a directory; else the first `git worktree list --porcelain` record, a failed listing, a
bare first record or an unreadable path giving `(None, why)`). Rows in both whose cells differ
return `direction-approval` with a reason starting `index-disagreement:` (`:561`); a missing row
names every INDEX asked plus `why`. The result carries `index_source` (`:542`), printed by
`--json` only. `open_index_tickets` (`:399`) reads `_open_index_rows` (`:381`): this checkout's
rows, then the main checkout's for tickets with none here, each still needing the folder here;
`resume_target` labels that source `.work/INDEX.md (main checkout)` (`:882`). `crew_route`
reads `open_index_tickets` too, so it sees the same rows. `_refresh_state` maps the check's
`fresh-uncommitted` to state `uncommitted` with its `paths` (`:489`); `_toward_review` sends it to
`_commit_refresh` (`:695`, defined `:711`) before review and after an accepted receipt alike: phase
`commit-refresh`, `stop` False, command `git add -- <shlex-quoted paths> && git commit -m
"<id>: commit refreshed artifacts" -- <the same paths>`, which commits only those paths, so
anything else already staged stays staged and out of it (QA F1); a stop when no path is listed,
or when a path is not printable, shown through `completion_audit.shown` (QA F3). When this
checkout's row answers but the main checkout could not be read, the evidence says the two were
not compared, with `why` (QA F2, after `:552`). JUDGEMENT: that a commit
keeps a receipt current rests on the bundle being the working state (`review_patch.py`); the
autopilot suite pins `review_ledger._current_hash` equal across such a commit. T-0063's
sabotage mutations are not in `sabotage_autopilot.py` yet: `plugin/crew/tests/sabotage*.py` is a
harness path, so they land in their own lane.

**Review closure (L-0510, crew 1.0.94).** DERIVED at the anchor below. `_review_phase`
(`plugin/crew/hooks/scripts/crew_autopilot.py:708`) asks `review_ledger.receipt_stands`
(`plugin/crew/hooks/scripts/review_ledger.py:709`) whether a FINDINGS receipt stands, the same
predicate `check_receipt` (`:833`) uses (a CLEAN round stands only under a `clean`
receipt): `owner-accepted`, or `auto-accepted` with
`accepted_by == AUTO_BY`, lines equal to the row's, provider and model family equal to the row's
(`_receipt_names_the_reviewer` `:748`, review round 3 FIX 2) and the row passing `_auto_row_problem`
(`:497`), which first asks `_family_problem` (`:474`, owner decision 2026-10-01 #3): the row's
`provider` is in `AUTO_PROVIDERS` (codex, kimi) and its `model_family` a non-empty string that is
not `AUTHOR_FAMILY` (claude), every missing or unknown value a refusal; a finding carrying `\n` or `\r` is could-not-tell before it is classified (review round 4 FIX 1), and a row whose `ignored_lines` (L-0576's count) is above 0 is refused as recovered, missing / non-int / bool / negative as could-not-tell, never 0 (owner decision 2026-10-01 #6); `auto_accept` also reads this round's `review.json` (`_review_json_problem` `:637`, reading it through `read_review_json` `:613`: never through a link, a duplicate key at any depth refused, review round 6 BLOCK 2) and refuses an unreadable one, another round's or bundle's, one whose `ignored_lines` is not a non-negative int count (L-0576's shape; review round 5 BLOCK), or a count above 0. `review_run.finish` writes the field on every round since L-0576 (`ignored_lines`, with the lines in `ignored_text`), and `review_ledger._ignored_count` records an unknown one as None. Otherwise it stops at `accept-review`, naming `--auto-accept` when
`auto_accept_refusal` (`:559`) returns None and quoting the refusal when not. `auto_accept`
(`:669`) is the guarded verb, and its receipt carries `review_json_sha256` and `ignored_lines`, which `_receipt_binds_review_json` (`:735`) re-checks on every `receipt_stands` (review round 6 BLOCK 1); `accept` (`:421`) refuses a `--by` starting `auto:`;
`check_follow_up` (`:756`) reads the follow-up's `direction.md` with `newline=""`, split on `\n` only, never `splitlines()` (review round 4 FIX 2, round 6 FIX 4; a CRLF line drops its one `\r`). `review_run.finish` records
`findings` and `webtest_open` (`_webtest_open`, `plugin/crew/hooks/scripts/review_run.py:514`)
and prints `auto_accept_line` (`:523`). JUDGEMENT: autopilot never calls `auto_accept`; the
command prose (`plugin/crew/commands/autopilot.md:86`) runs it inside the review phase.

T-0018 (crew 1.0.43) added the router and `status`. `route_args` (`:1328`)
takes the command's `$ARGUMENTS` whole - Claude Code 2.1.283 substitutes
`$0` with the first argument and leaves an out-of-range `$N` literal, so a
positional `$1`/`$2` never carried the ticket - and `route` (`:1299`) decides
the subcommand: `SUBCOMMANDS` (`:224`), of which only `status` and `run` are
`AVAILABLE`; `assign`/`goal`/`focus` stop naming T-0019/T-0012/T-0020; a
bare INDEX-shaped id or existing `.work/tickets/<id>/` is `run`; any other
word - `approve` and `questions-check` included - a second word that is not a ticket, or a
third word stops (`run --goal` stops naming T-0012); `route --first <token>` routes one token
alone. `status` (`:1523`) composes `settings`, `resume_target` or `next_phase`,
`review_ledger.status` and `crew_resume`, and `status_text` (`:1562`) caps it
at 12 lines; `--json` prints the same dict as one line of JSON (`main`, `:1662`), inside the
cap (round 5); what it cannot tell reads `unknown`. Neither reads the approval policy: `status`
composes `resume_target` / `next_phase` / `_phase` with `policy=False` (T-0010 review round 3),
so its approve and open-questions reasons are the fixed `POLICY_FREE_APPROVE` /
`POLICY_FREE_QUESTIONS` (`:1106`, `:1109`) and at the approve phase it names `/crew:approve <id>`
under every setting (`test_route_and_status_unaffected_by_approval_policy`,
`test_status_at_approve_reads_the_same_under_an_allowing_policy`); the one policy effect it shows is
`crew_ticket.accepted`'s demotion of an `autopilot` receipt the policy no longer allows. Its `resume:` line reads usable
only where bare `/crew:autopilot` - `resume_target` itself - would take it (`_resume_line`,
`:1478`; `_takes`, `:1382`), asked only after `_resume_line`'s own read of the handoff passes the
branch, head and folder checks, so a file rewritten after `resume_target` read it is never
vouched for by that earlier read (round 5), and says `unknown` when `resume_target` raised, or when
`.work/HANDOFF.md` exists but cannot be read (`_read_handoff`, `:608`, which `resume`'s
fall-through shares - only a file that is not there reads `no .work/HANDOFF.md`; a dangling
or looping symlink, or a `.work` that is a dangling symlink, is there and reads `unknown`, round 5). A `next` stop
made on the active-ticket pointer rather than the phase waits on re-pointing it (`_repoint`,
`:1412`), never on the owner typing the phase's command, and offers driving the active ticket
only while it is not closed - read by `_closed` (`:1442`) from INDEX.md's status and spec.md's
`status: done` header directly, so no `direction.md` cannot hide either; a `spec.md` that exists
but cannot be read makes `_closed` return None, and the offer becomes "could not tell whether
<active> is still open" (round 4). A `stop=0` phase names
bare `/crew:autopilot` only when that drives the same ticket (`_waiting`, `:1388`). Every drive
suggestion goes through `_drive` (`:1433`), which writes `/crew:autopilot run <id>` for an id that
is exactly a `SUBCOMMANDS` name - `route` would read the bare name as the subcommand - and the
bare `/crew:autopilot <id>` otherwise. Its `review:`
line (`_review`, `:1458`) prints a rounds count only for a ledger state in `LEDGER_STATES`
(`:1358`); a state of `UNKNOWN`, or one review_ledger never writes, reads `unknown`.
`plugin/crew/commands/autopilot.md` runs every `crew_autopilot.py` line as `python3 -B`, and the
script itself sets `sys.dont_write_bytecode` under `__main__` before its sibling imports
(`:160-162`), so neither the command nor the direct CLI writes a bytecode cache into the plugin;
a module importing it keeps its own setting. `main` registers `deploy-allowed` at `:1913`
(T-0072; the policy itself is the `deploy_allowed` paragraph below). Defaults live in
`crew_state.AUTOPILOT_DEFAULTS` (`plugin/crew/hooks/scripts/crew_state.py:1134-1135`,
`{"mode": "off", "maxPhases": 12, "deploy": "none", "approval": "risk", "questions": "risk"}`
since T-0072 and T-0010 merged), deep-copied into `default_config()`
(`plugin/crew/hooks/scripts/crew_config.py:400`). It registers no hook -
`plugin/crew/hooks/hooks.json` is unchanged since `a0c0847e`.

`crew_ticket.parse_risk` (`plugin/crew/hooks/scripts/crew_ticket.py:509`)
also landed in T-0004: it reads `risk:` from the spec header line only, and
an absent or unrecognised value reads as `high` with `known: False`, never
`low`. Its consumer is T-0010's `_ticket_risk` (`plugin/crew/hooks/scripts/crew_autopilot.py:1235`).
Tests: `plugin/crew/tests/test_crew_autopilot.py`,
`plugin/crew/tests/test_crew_autopilot_status.py`,
`plugin/crew/tests/test_lifecycle_commands.py`; mutations
`plugin/crew/tests/sabotage_autopilot.py` (`STATUS_MUTATIONS` appended to
`AUTOPILOT_MUTATIONS`); `.crew/verify.json` rule 28 (`:460-469`; rule 27 at `:415-423` on T-0094's merge of `8ab733d7`, `:413-421` before, until L-0516 inserted rule 10); T-0010's policy rule 29 (`:470-477`; rule 28 at `:425-431`, `:422-428` before),
T-0021's tracker rule 30, T-0023's routing rule 31 and T-0024's group-approval rule 32 follow it. Confirmed present, **not run** by this note.

**T-0053 (sleep schedule, slice 1; DERIVED at f3b3367e on T-0053-build after review round 2, merged main baf193aa).**
`plugin/crew/hooks/scripts/crew_sleep.py` is pure and read-only: `parse_schedule` (`:55`) full-matches
`_SCHEDULE_RE` (`:47`, ASCII `[0-9]` classes), refuses an hour past 23 and a start equal to its end;
`in_window` (`:71`) is start-inclusive, end-exclusive, crossing midnight when start > end; `resolve`
(`:128`) answers `off|awake|asleep|unknown` from a block and a naive local datetime, and names any key
outside `KEYS` "not available in this crew version". `read_overrides` (`:90`) reads each key on its
own through `_override` (`:112`): a non-null value outside `POLICIES` is `STRICTEST` with a warning
(landing decision; it was None, keeping the day value), so is one that cannot be read (`:41`, `human`), and a non-object block gives `human` for both; `render` (`:79`)
bounds every config value in a warning with `reprlib`. The clock is `crew_sleep.now` (`:50`) alone,
local time in the process's `TZ`; crew reads no variable or flag of its own for it.
`crew_autopilot._settings_at` (`plugin/crew/hooks/scripts/crew_autopilot.py:794`) calls `_sleep_at`
(`:870`) on every read (`:829`): `_sleep_block` (`:860`) asks the raw repo file first because
`merge_defaults` drops a non-object `autopilot.sleep` for the default, and a raising read, clock or
resolve is `unknown` with the overrides still read (`human` if even that fails). `_overlay` (`:843`):
asleep, each non-null override replaces the day value; unknown, one applies only when earlier in
`STRICTNESS` (`:840`, human > risk > self) than the day value; the dict gains `day` and `sleep` (with
`applied`). `_decision` (`:1083`) carries the note for an applied key only, inside `risk["sleep"]`
(the `approval_policy` head is a sabotage anchor, so its 3-tuple stays), and `_noted` (`:1100`)
appends it to `approval_policy` (`:1112`) and `question_policy` (`:1176`) reasons. `approve`
(`:1236`) pins its one decision in the thread-local `_PINNED` (`:1135`) while `crew_ticket.approve`
re-checks, and prints the note; `_sleep_line` (`:1713`) is the `settings` CLI's third line, ending
`applied=` under unknown. The defaults are `AUTOPILOT_DEFAULTS["sleep"]`
(`plugin/crew/hooks/scripts/crew_state.py:1134-1135`); the config menu offers the three policies and
unset (`plugin/crew/hooks/scripts/crew_config_menu.py:82-83`). JUDGEMENT: `deploy_allowed` reads
`_settings_at` too but only `deploy`, so sleep cannot reach it. Tests
`plugin/crew/tests/test_crew_autopilot_sleep.py`; no committed mutations yet (L-0651).

**L-0652 (manual sleep and wake; DERIVED after #427 review rounds 1 and 2 on L-0652-build, stacked on
T-0053-build `4cdf076f`; the T-0053 citations above are T-0053's own).**
`crew_sleep` stays free of file input and output: `read_manual`
(`plugin/crew/hooks/scripts/crew_sleep.py:191`) judges the record through `_manual_problem` (`:211`)
into `none|valid|expired|untrusted`; `at`/`until` must be UTC-aware ISO and are compared in UTC
(`to_utc`, `:163`, resolves a skipped spring-forward time forward; a naive record is untrusted, review N1); `next_edge` (`:154`) is the next time of
day strictly after now, the current window's end inside it and the next window's end outside;
`MANUAL_SLEEP_HOURS` (`:57`), `MANUAL_FILE` (`:54`), and the caps `MANUAL_MAX` (24 wall-clock hours, measured by `_wall`, `:174`) and `MANUAL_MAX_REAL` (25 real, `:61-62`). `resolve` (`:242`) takes the record and
`sleep_allowed`: untrusted is `unknown` (source manual), expired is the schedule with a warning, a
manual asleep without the gate is `unknown`, a manual asleep outside the window and a manual awake
over an asleep or unknown schedule carry `tightenOnly` (owner decision 2026-10-04, review B1: a
manual sleep only tightens until L-1504). `crew_autopilot._sleep_at`
(`plugin/crew/hooks/scripts/crew_autopilot.py:886`) passes `_manual_found` (`:931`: absent only with
no `.git` entry at all; otherwise `lstat` must say regular file and `_read_regular` (`:960`) opens
with `O_NOFOLLOW|O_NONBLOCK` and re-checks `fstat`, review N3) and `crew_ticket.cli_approval_allowed`;
`_overlay` (`:854`) is stricter-only under `tightenOnly` or `unknown` (`:866`); `_decision`
(`:1264`) names a manual sleep's end. `sleep_now` (`:986`, validating its record with `read_manual` before writing, refusing when no override is stricter by
`_stricter` (`:1033`) outside the window) and `wake_now` (`:1039`, saying when the schedule cannot be
told, review N2) are the two new writers, through `_manual_path` (`:921`, `<git-common-dir>/crew/`)
and `crew_ticket._write_json` (temp file, `os.replace`); `_manual_main` (`:1928`) makes a crash exit
1; the subparsers are at `:1994`. `SUBCOMMANDS` gains both on a second line (`:235`) because the
first line is a sabotage anchor; `route_args` (`:1622`) stops a second word at `:1634`;
`_sleep_line` (`:1898`) adds `source=` and `until=`. Tests:
`plugin/crew/tests/test_crew_autopilot_sleep.py` (L-0652 section),
`test_crew_autopilot_policy.py::test_approve_sleep_and_wake_are_the_only_writing_subcommands`,
`test_crew_autopilot_status.py::test_route_args_sleep_and_wake_take_no_ticket`; mutations go to
L-0655.

**T-0020 (`/crew:autopilot focus`, an explicit scope lock on one ticket; versionless, joins a
batch).** DERIVED on T-0020-build after its merge of origin/main `47f71e93` (batch 6), with the
explicit-focus rework (owner decision, 2026-10-05) and the re-review fixes, line numbers taken by
`grep -n` in that tree; this file's anchor stays main's, and the other `crew_autopilot.py`
citations in this section were not re-taken (T-0020 moves every line below its insertions).
Focus is explicit: `focus_path` (`plugin/crew/hooks/scripts/crew_autopilot.py:2049`) is
`<git-common-dir>/crew/autopilot-focus.json` (`FOCUS_FILE`, `:2046`), a JSON object keyed by
worktree top-level; `_focus_marker` (`:2109`) reads it and returns why it could not -- not a
file, does not parse or cannot be read, not an object, or this worktree's entry not a ticket
(INDEX-shaped or naming a `.work/tickets/` folder) -- each reason ending with `_focus_remedy`
(`:2103`): through `_remove_by_hand` (`:2090`), the POSIX and PowerShell removal
commands for the exact path only when `_paste_safe` (`:2075`) holds (no control character, whitespace run
or PowerShell quote, and the rm parses back to the path), else the path as JSON with no command, never an empty mapping
in its place. `focus_state` (`:2165`) reports `focus` from the marker only, `unknown` beside it,
and the active-ticket pointer separately (`pointer`, never the `.work/INDEX.md` fallback).
`focus_guard` (`:2183`) lets `status`, `focus off` and `NO_TICKET` (`:299`, L-0652's
`sleep`/`wake`) through; an `unknown` marker refuses everything else without offering `focus
off` (JUDGEMENT: could-not-tell kept as its own value, acted on closed, per CLAUDE.md
"Lessons"); no entry is no focus; focused on T-A it refuses all but `focus T-A` when the pointer
names anything else, and otherwise all but `run`/`focus` with no ticket or T-A. `route`
(`:1958`) calls it after resolving the subcommand and before the `AVAILABLE` check (`:1982`;
`--goal` at `:1975`), `route_args` (`:1995`) guards the ticket word (`:2022`), and
`resume_target` appends its refusal to the handoff/pointer disagreement (`:1055`). `focus_set`
(`:2239`) and `focus_off` (`:2298`) do the marker's read-modify-write inside `_focus_lock`
(`:2136`, `crew_config_files.Lock` on `<marker>.lock`, `FOCUS_LOCK_WAIT` `:2057`; a lock not
taken refuses, nothing written, with the same removal builder for a stale lock), re-reading the marker inside it; `_write_marker` (`:2226`)
removes the file when no entry is left. `focus_set` calls `crew_ticket.activate` (`:2293`, its
one call) only when the pointer names another ticket or none; `focus_off` calls no
`crew_ticket.deactivate` (AST-pinned) and refuses an unknown marker rather than delete it.
`next_phase` asks `_drift` (`:906`) first (`:877`): an `unknown` marker stops as `drift`; else
only when focused on this ticket, approved, and ahead of a phase the loop would run
(`POLICY_PHASES`, `:903`), it runs `completion_audit.audit` read-only, and a failure or a raise
stops as `drift` (`FIXED_STOPS`, `:263`; `WAITING`, `:2382`). `findings_target` (`:2340`) and
`focus_text` (`:2355`, every output ends with `FOCUS_REMINDER`, `:2032`); `main` registers
`focus` at `:2735` and runs it at `:2772`. `plugin/crew/commands/autopilot.md` section 6
(`:112-117`). Tests: `plugin/crew/tests/test_crew_autopilot_focus.py` (two-process lock race
included); `test_crew_autopilot_policy.py::test_approve_is_the_only_writing_subcommand` lists
`focus` in `WRITERS`.

**T-0010 (approval and questions policies, DERIVED on T-0010-solo, crew 1.0.50 on T-0077's main).**
`approval_policy` (`plugin/crew/hooks/scripts/crew_autopilot.py:1263`) refuses a `policy: unknown`
(an unreadable config or non-object `autopilot` block, review round 4) in its own branch before
every other test, and otherwise returns `allow` only when
`crew_ticket.cli_approval_allowed` is true (`scope.allowCliApproval` exactly `true`, at every
setting), the review ledger is not UNKNOWN (NEEDS_REPLAN does not refuse since review round 1:
a distinct successor plan is its only way out, and `review_ledger.continue_with_successor_plan`
refuses a plan approved before, so `approve` exits 3), and then `self` (any risk) or
`risk` on a known `risk: low`; `human` never; a settings read that raises is `policy: unknown`,
refused. `question_policy` (`:1304`) is `take|stop` by the same rule without the
`allowCliApproval` term, and stops on `unknown`. `approve` (`:1358`) also needs `mode: plan`, then calls
`crew_ticket.approve(..., via=crew_ticket.AUTOPILOT)` - the module's one writing path, which lands
`approval.json`; on a ticket's first approval, the scope ramp's `scope-tickets.json`
(`crew_ticket._register_ramp`, `plugin/crew/hooks/scripts/crew_ticket.py:705`, as for every
route); and, for a distinct successor plan under a NEEDS_REPLAN ledger, the ledger moved
NEEDS_REPLAN -> IN_REVIEW (`review_ledger.continue_with_successor_plan`, `plugin/crew/hooks/scripts/review_ledger.py:884`). `questions_check` (`:1246`) validates
`.work/tickets/<id>/questions.md` against `QUESTIONS_SHAPE` (`:1154`) and refuses a `taken:` line
naming a policy that never takes (only `self`/`risk` do; the name is history, not compared with
today's) or any `taken:` while the policy in force says `stop`. `next` appends
`_approval_hint` (`:1114`) / `_question_hint` (`:1123`) to the `approve` and `open-questions`
stops (`:479` for approve), which stay `stop=1`; `commands/autopilot.md` section 3 (`:72-80`)
runs the policy on exactly those two `stop=1` lines before stopping, with `python3 -B`, and
states the `questions.md` shape `questions_check` enforces (review round 2). `main` (`:1662`)
sends both to `_policy_main` (`:1602`) before T-0018's branches. In
`plugin/crew/hooks/scripts/crew_ticket.py`: `AUTOPILOT = "autopilot"` (`:144`), `_autopilot_refusal`
(`:654`), `accepted` (`:671`) demotes an `autopilot` receipt unless that refusal is None, and
`approve` (`:724`) refuses an `autopilot` via the policy denies, and refuses `via=autopilot` with
a group confirm's `expect` outright (`:743-745`, before `expect` is validated or anything written:
the group confirm is owner-only, carried from T-0024's hand-off at T-0010's merge of `f96e9ec9`). `scope_guard.py`'s
`_AUTOPILOT_APPROVE_RE` / `_AUTOPILOT_BARE_RE` (`plugin/crew/hooks/scripts/scope_guard.py:118-122`) and
`_autopilot_refusal` (`:237`) allow only the bare command while the policy says yes;
`shell_refusal` (`:265`) runs `_reading_refusal` (`:281`) on each reading `_joined` (`:257`)
gives - the command as written and with line continuations joined (`_BASH_CONTINUATION_RE` /
`_PS_CONTINUATION_RE`, `:126-127`) - while the bare-command rule judges the command as written.
Tests `plugin/crew/tests/test_crew_autopilot_policy.py` plus new cases in `test_crew_ticket.py`,
`test_scope_guard.py`, `test_crew_autopilot_status.py` and `test_crew_route.py`; mutations
`POLICY_MUTATIONS` in `sabotage_autopilot.py` (55 by `len()` on T-0010-solo's merge of `e878cc31`, `plugin/crew/tests/sabotage_autopilot.py:687`),
registered at `plugin/crew/tests/sabotage.py:76` and `:3065`; `.crew/verify.json` rule 29
(`:355-362`; rule 28 at `:310-316` after T-0094 merged `8ab733d7`, `:307-313` before, until L-0516 inserted rule 10), which also maps `commands/autopilot.md` since review round 2.

## Plain-text lifecycle routing (T-0023, crew 1.0.43)

DERIVED at `eba11657`, re-read after review round 1; every `crew_route.py` line below re-read
at `bb89215d` (L-0662, on T-0057 and T-0069), +1 from line 70 on after the batch-5 merge (one docstring line). `plugin/crew/hooks/scripts/crew_route.py`
(627 lines) decides whether a short plain-text prompt names a lifecycle command. The table
is `PHRASES` (`:141`): brainstorm, spec, plan, implement, review, done,
continue, status, then T-0057's five and L-0662's four autopilot rows - no approve row. `match`
(`:247`) matches the WHOLE prompt after `normalise` (`:224`) refuses a line break - `\n`, `\r`,
or any other boundary `str.splitlines` knows (`_OTHER_LINE_BREAKS` `:184`, T-0069) - more than
`MAX_PROMPT_CHARS` (`:109`, 80), or a leading `/`, `<` or backtick; `AMBIGUOUS` (`:177`) phrases
("do it", "yes", bare "done"...) return None whatever a row says. `decide`
(`:463`) returns `route`, `ask` or `none`; `_resolve` (`:356`) takes an
explicit id only with a `.work/tickets/<id>/` folder, then
`crew_ticket.resolve_active`'s `active-ticket` source, then
`crew_autopilot.open_index_tickets` with exactly one ticket - never
`resolve_active`'s own first-open-line INDEX answer. `continue` goes through
`_continue` (`:377`) to `crew_autopilot.next_phase`; a stop, an exception, or
a command naming approve is an `ask`. Every route answer goes through `_route`
(`:348`): a command `_routable` (`:336`) says `_clip` would change - cut past
`FIELD_CHARS["command"]` (200) or reflowed whitespace - is an `ask`, never a
route of a different command (T-0069), and `render`'s route branch refuses one
the same way through `_run_clause` (`:496`). `render` (`:512`) clips every other
variable-length field it reads to its own `FIELD_CHARS` cap with `_clip`
(`:483`), so the line is at most `MAX_LINE_CHARS` (`:118`, 1400) and always
fits the UserPromptSubmit budget (`crew_context.TURN_CHARS`, 2000) as the
first item: `fit` keeps whole items or none, and before review round 1 a long
open question dropped the ask entirely. `settings` (`:564`) reads
`crew_config.resolve_config` and arms only on `is True`. The one consumer is
`crew_context.route_item` (`plugin/crew/hooks/scripts/crew_context.py:839`),
called first in the UserPromptSubmit branch (`:937`): Claude harness only,
`crew_route` imported inside a `try`, so any exception drops only the route
line and logs `route: "error"` (`:1070` keeps that log line when nothing else
is emitted). No new hook and no new skill: `plugin/crew/hooks/hooks.json` is
unchanged. Tests: `plugin/crew/tests/test_crew_route.py`,
`plugin/crew/tests/test_crew_route_hook.py`; mutations
`plugin/crew/tests/sabotage_route.py` (registered at
`plugin/crew/tests/sabotage.py:78`); `.crew/verify.json` rule 31 (`:372-381`; rule 30 at `:325-333` after T-0094 merged `8ab733d7`, until L-0516 inserted rule 10),
then T-0024's approval rule 32 (`:383-391`), T-0094's admission rule 33 (`:392-400`), T-0088's review-limit rule 34 (`:401-408`), crew 1.0.65's review-gate rule 35 (`:409-416`), crew 1.0.67's QA-audit rule 36 (`:418-424`), T-0085's standards rule 37 (`:425-438`), L-0520's merge train rule 38 (`:439`), T-0087's harness rule 39 (`:440-466`), T-0028's Kimi rule 40 (`:467-480`), L-0513's gate-runner rule 41 (`:481-485`), L-0577's Windows-shards rule 42 (`:486-490`), L-0557's pwsh-cache rule 43 (`:492-499`), T-0040's shell-route rule 44 (`:501-508`), L-0555's CI-receipt rule 45 (`:509`), L-0572's subset-coverage rule 46 (`:511-518`) and L-0575's recurring-findings rule 47 (`:519-528`) and the `pytest_rule.py` rule 48 (`:529-536`, the last, crew 1.0.140) follow it. Every number from rule 10 on is one higher than this sentence gave at `d6e51bb8`, because L-0516 inserted rule 10 (`:210-215`), and every span is 27 lines lower than at `2a2d6e07` because L-0574 added `preReview` above the rules; the spans it gave at earlier anchors are in this file's git history;
T-0010's policy rule 29 (`:355-362`) sits after T-0072's autopilot rule 28 (`:345-354`). (Corrected
2026-09-29, T-0094: this sentence numbered them 31, 32, 29 and 28 at `bbd9a66d`, one too high;
`json.load` puts T-0023's routing rule at index 30, and at 31 since L-0516's rule 10.)

**Autopilot rows (T-0057, crew 1.0.345).** DERIVED at `9c013fb1` (review round 3); lines
re-read at `bb89215d` after the merge onto T-0069's main, +1 from line 70 on after the batch-5 merge. Five rows
follow `status` in `PHRASES` (`plugin/crew/hooks/scripts/crew_route.py:153`): `autopilot-status`,
`assign`, `goal`, `goal-resume`, `focus`, with rules `autopilot`, `autopilot-text`,
`autopilot-resume`, `autopilot-ticket`. `decide` (`:463`) hands them to `_autopilot` (`:433`),
which first runs `_gate` (`:397`): `crew_autopilot.route(top, <command's last word>)` inside a
`try`; a raise, an answer that is not a dict with `sub`, `stop` (a bool) and `reason`, or a `sub`
that is not a string naming the subcommand asked about (`run` for `--goal`) is an `ask`; an empty
`sub` is `none`; a `stop` is an ask with `unavailable: True` carrying the router's reason, or "not
available yet" when it gives none. So whether a subcommand has landed is read from
`crew_autopilot.AVAILABLE` (`plugin/crew/hooks/scripts/crew_autopilot.py:263`) at decide time and
never copied into the table. Before that, `match` (`crew_route.py:247`) passes assign, goal and
focus through `_screen` (`:281`); `normalise` has already refused every line break, so the
`_LINE_BREAKS` check T-0057 carried is gone. In order: the stem `_APPROV` (`:198`,
letters-only) or a first token in `_NOTHING` (`:196`) is no match; then the allowlist, a
character of the raw prompt (after the one prefix `normalise` drops) outside `_PLAIN` (`:195`,
ASCII letters, digits, space and `.,:;_#()-`; no quote, so autopilot.md's refused characters
never route), is carried as `refuse` and asked after the gate; then a word starting with `-` or
`_NEGATION` (`:200`) is a refusal too. The routed text is the typed text. `autopilot-resume`
always asks (no goal slug; T-0056), `autopilot-text` routes `<command> <text>`, and an id goes
through `_resolve`; every route goes through `_route`. `_TEXT` (`:126`) excludes `?`; `_ID`
(`:123`) is ASCII letters (`(?-i:...)`, since IGNORECASE folds a long s or Kelvin sign into
`[a-z]`) and `[0-9]` digits, for every row. `render` (`:512`) gives an `unavailable` ask its own
line (`:545`, "answer the prompt as written", never "which ticket"; `_TICKETED` at `:204` limits
"which ticket" to ticket intents) and ends a route whose intent is in `_UNDO_INTENTS` (`:207`,
goal and sleep) with `GOAL_UNDO` (`:205`, `:535`). JUDGEMENT: the sabotage mutations for
these branches are L-0661 (harness, its own PR).

**Wave, split, sleep and wake (L-0662, crew 1.0.345).** DERIVED at `bb89215d`. Four rows follow
`focus` (`crew_route.py:166-174`). `wave` (`autopilot-tickets`) matches `_IDS` (`:131`, two or
more `_ONE_ID` joined by `,`, `and` or `, and`); `match` reads them back with `_WAVE_ID` (`:130`),
upper-cases and de-duplicates them in order into `tickets`, and a list of fewer than two is no
match; `_wave` (`:422`) asks naming every id without a `.work/tickets/<id>/` folder, else routes
`wave <ID> <ID> ...` with the first id as `ticket` (`command_for` `:318`). `split`
(`autopilot-ref`) routes `split <ID>` through `_resolve` (`:450`), and `split` is in `_TICKETED`.
`sleep` and `wake` use rule `autopilot` with fixed phrases (`_IM` `:132`); the bare greetings
in `_GREETINGS` (`:135`) match but `_autopilot` asks "did you mean ...?" after the gate (`:443`,
owner decision 2026-10-04). `_SCREENED` (`:211`) runs `_screen` on all four with no free text,
adding only the apostrophe sleep and wake spell; `_CURLY_IM` (`:212`) lets U+2019 through as the
second character of a leading `I'm` only, so a long s, a Kelvin sign or any other curly quote
asks. `sleep` and `wake` are in `crew_autopilot.SUBCOMMANDS` and `AVAILABLE`
(`crew_autopilot.py:261-263`, L-0652's manual sleep mode), so both route on main; `wave` and
`split` are not, so `_gate` makes each `none` until its command's ticket (T-0029, T-0058) adds it. JUDGEMENT: the sabotage mutations for these
rows are L-0663 (harness).

**`deploy_allowed` (T-0072, crew 1.0.51).** DERIVED at `80326b1d` (T-0072's review-round-4 redesign, `35733d76`); lines re-read after its merge of T-0077 (`a4eb2f55`, `_rel` +6 at `:170`) and its review-round-5 fix (`0f488706`, `_resolve_root` +4), and again at `d7c7c75c` on T-0010-solo's merge of `6387ab49`, where T-0010's code above it moved every line (re-read by `grep -n` per symbol).
`crew_autopilot.deploy_allowed` (`plugin/crew/hooks/scripts/crew_autopilot.py:1186`) is the policy
layer for a deploy without asking: `allow`, `ask` or `refuse` for one environment, rows in the
order the module docstring's `deploy-allowed` section (`:135-151`) states. It resolves the checkout
root **once**, through `_resolve_root` (`:1079`, whose try holds only the `toplevel` lookup; any
exception, or a root that is not text such as a bytes path, is row 0, `refuse`), reads `crew_config.GLOBAL_CONFIG_PATH` once as `machine_path`, and
hands both to `_decide(top, env_name, env_class, machine_path)` (`:1109`), which never looks the
root up again: settings come from `_settings_at(top)` (`:1007`; `settings(root)` `:976` is the lookup
plus that call) and the ratchet from `resolve_ratcheted(top, "environments.prodUnattended",
path=machine_path)`. The result names the root it judged (`root`). `_probe` (`:1064`) is the only
existence check in the module: a try holding one `os.lstat`, `FileNotFoundError`/`NotADirectoryError`
absent, any other exception `could-not-tell` with its type, else present. The incident file
present or could-not-tell refuses, before `import cloud_guard` (review round 1). An unusable name
or a class outside `cloud_guard.ENV_NONPROD`/`ENV_PROD` asks; `_layer_problem` (`:1094`) asks for a
layer the probe could not tell about, and for a present layer `crew_config.layer_state(...,
environments=True)` does not call `ok` - so `layer_state`'s `lexists` collapse is consulted only for
a path this module saw present (review round 4). Production allows only under `deploy: all` with
the ratchet's `effective` true and `cloud_guard.resolve_mode(top)` exactly `("block", "")`.
Nothing calls it yet: T-0045 is the consumer, and `settings` warns while `deploy` is not `none`.
`deploy_allowed` builds the report inside its never-raises boundary: a value it cannot print is
named by `_safe_text` (`:1129`) and a crash reason comes from `_crash_reason` (`:1138`). The
`deploy-allowed` CLI is `_cli_deploy` (`:1830`), which never raises: stage 1 builds the line, the
JSON and the report from the result; stage 2, on any exception from stage 1, prints the literal
`verdict=ask`, with a constant reason when the exception cannot be described. Each stream is one
line through `_cli_value` (`:1818`), and `--json` is one line of JSON on both stages. `_failure` (`:1788`) renders a `next`/`resume`/`status` crash
through `_safe_text` the same way. Tests `plugin/crew/tests/test_crew_autopilot_deploy.py`
(must-block, must-allow, the 324-case matrix, parity with `cloud_guard.environments_config`, the
one-root, probe and layer cases); mutations `DEPLOY_MUTATIONS` in
`plugin/crew/tests/sabotage_autopilot.py` (`:190`, 64 entries by `len(DEPLOY_MUTATIONS)` at `0f488706`), appended to
`AUTOPILOT_MUTATIONS` at `:608`.

## The Windows shell route (T-0040)

DERIVED at `f05ed74e` (T-0040's branch, after review round 1), read in full; positions re-taken
with `grep -n` on T-0040-land after review round 2's fixes. `plugin/crew/hooks/scripts/crew_shell.py` (1056 lines)
picks the shell crew's long-running jobs run in on native Windows. It is a CLI
(`probe`, `measure`, `classify`, `run`; `main` at `:1033`) and a library for
`crew_status.py`. It imports no crew module at import time. No hook calls it:
`plugin/crew/hooks/hooks.json` and `crew_platform.py` are unchanged. `host_os` (`:59`) gives
`windows`, `windows-bash`, `linux`, `macos`, `wsl` or `other`, and `on_windows` (`:82`) gates
everything: off native Windows `probe` returns `n/a`, `status_line` returns None, and `run`
(`:768`) execs `["bash", "-c", cmd]` with no config read and no message, mapping a
signal-killed child's -N to 128+N as `bash -c` does. The preference is
`shellRoute.mode`/`.distro` in both config layers (`plugin/crew/hooks/scripts/crew_config.py:340`
and `:610`), read through `resolve_config` by `settings` (`:444`). The repo layer's `mode`
is null (review round 2), so a repo that chose nothing inherits the machine's value; `mode`
(`:482`) reads an unset value as `auto`, and an unrecognised one as `auto` naming it. The probe
(`:338`) runs only `wsl.exe --list
--verbose` and one `command -v python3; command -v git` under `bash -lc` (`_in_job_shell`,
`:273`, the job's own shell) in the default `*` distro (or `shellRoute.distro`). It decodes
UTF-16LE with `decode` (`:123`), joins every detail onto one line (`one_line`, `:295`) and
returns `usable`, `not-installed`, `no-distro`, `wsl1-only`, `no-python3`, `no-git`, `broken`
or `unknown`. A runner that raises is `unknown` through `_call` (`:323`), never
`not-installed`. The answer is cached machine-locally at `probe_path` (`:398`), beside
`crew_state.GLOBAL_CONFIG_PATH` and resolved at call time. `load_cache` (`:406`) reads an
absent, unreadable or stateless cache, and a `usable` one that names no distro, as `unknown`.
`write_cache` (`:425`) computes the
text first, then temp file and `os.replace`, LF. `measured_verdict` (`:490`) takes a
measurement only when its `distro` is the cache's current distro, so a reprobe or a switched
`shellRoute.distro` never reuses another distro's verdict. `classify` (`:171`) proves plain argv or
returns bash; `METACHARACTERS` (`:41`) and `SHELL_WORDS` (`:43`) are its lists and
`_embeds_posix_path` (`:148`) refuses a token carrying a POSIX path after `=`, `,`, an option's
letters, or a `:` that is not a drive letter or URL scheme. `decide` (`:560`) is the pure route
table; `route_for` (`:746`) is `decide` plus the `to_wsl_path` distro check, the one decision
path `run` and `status_line` share. `run` then adds the WSL preflight (`_preflight`, `:703`),
run under the job's own `--cd`, which checks the first word and, for `python3 -m <mod>`
(`job_head`, `:683`; `_python_module`, `:654`, skips `-X`/`-W` and their values), that the module
imports inside the distro. `pwsh_argv` (`:615`) doubles `'` and U+2018-U+201B and exits 1 when
the program cannot start. `resolve_pwsh` (`:217`) and `resolve_gitbash` (`:236`) resolve
absolutely and refuse WSL's System32 launcher (`_is_launcher`, `:228`). `measure` (`:861`)
times 50 forks and 200 writes per side, each shell reading its own clock (`$EPOCHREALTIME`, a
pwsh Stopwatch) so no launcher start-up is in the number; an unreadable timing is an error,
never zero. `status_line` (`:923`) reads config and the cache only, and
`plugin/crew/hooks/scripts/crew_status.py:226` calls it and appends it after the `verify` line. Tests:
`plugin/crew/tests/test_crew_shell.py`, `plugin/crew/tests/test_status.py`. Mutations:
`plugin/crew/tests/sabotage_shell.py` (`SHELL_MUTATIONS`, 14 entries) shipped with T-0040 up to
its landing bump, then split out to follow-up ticket W-0115 per rule 36
(`scripts/check-tooling-pr.py`; owner 2026-09-30) - then W-0115 (`59c86b7c`) restored it, registered at
`plugin/crew/tests/sabotage.py:85` and appended at `:3068`. The `.crew/verify.json` rule is rule 44 (`:501-508`); L-0555's rule 45, L-0572's rule 46, L-0575's rule 47 and the `pytest_rule.py` rule 48 follow it.

## verify-gate's temp-file rule capture

`plugin/crew/hooks/scripts/verify-gate.sh` (1863 lines) captures each rule's
output to a temp file rather than a pipe, specifically to avoid a
backgrounded-and-abandoned grandchild process wedging the gate's own read
forever (`:1766-1809`) — `mktemp`, falling back to a repo-local
`.crew/.verify-rule-out.XXXXXX` if `TMPDIR` is unwritable (`:1766-1769`);
refusing the rule outright with a named reason if neither location is
writable (`:1863-1870`), rather than falling back to the old pipe form.

- **The captured output is capped at 1 MiB (1048576 bytes), read as the
  LAST N bytes (`tail -c`), not the first.** `RULE_OUT_CAP`
  (`verify-gate.sh:1855`) defaults to 1048576 and is clamped into `[1,
  1048576]` (`:1677-1683`); a rule that legitimately writes more than that
  before backgrounding something no longer turns a bounded gate into an
  unbounded read. `tail -c`, not `head -c` (`:1850-1860`): what a failing
  rule needs downstream is its actual error, which for noisy output sits at
  the end.
- **Per-rule process-group tracking and kill-on-signal was DESCOPED from
  crew 1.0 entirely**, per the comment at `verify-gate.sh:1805-1816` and
  CHANGELOG 1.0.21 (both cited in the file itself, `:600-601`): a signalled
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
(`plugin/crew/hooks/scripts/_common.sh:59-121`) now probes**: it walks every
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
  (two call sites, `PY` at `:738` and `SHIM_PY` at `:1530`), and
  `completion-audit.sh:67`. **Only two scripts still call plain
  `crew_py()`**: `handoff-read.sh` (`:36,46`) and `promote-gate.sh:79` (`:37` before T-0505), plus
  four more plain call sites *within* `verify-gate.sh` itself
  (`PRICE_PY` at `:18`, `REPORT_PY` at `:276`, `FP_PY` at `:373`,
  `SCOPE_PY` at `:682`) that degrade to a no-op or a narrower error rather
  than gating the whole run.
- **A committed parity test now exists** —
  `plugin/crew/tests/test_context_watch_python_resolver.py` and
  `plugin/crew/tests/test_verify_gate_python_resolver.py`, both confirmed
  present, **neither read this pass**. `_common.sh:140-145`'s own comment
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

**The completion record (T-0082, H2a; DERIVED at the H2a branch head).** The
same capture now carries a second temp file per rule, the completion record:
the wrapper writes the rule's exit status there after the rule ends
(`plugin/crew/hooks/scripts/verify-gate.sh:2101`), and a rule passes only when
the wrapper ended 0 and the record says 0. Killed, never-started (`.ps1`) or
unrecorded is FAILED as `COULD NOT TELL`, status `unknown`, never advancing the
marker. The full decision table and both flavours' line references are in
`verification-harness.md`'s rule-runner section.

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
(`plugin/crew/hooks/scripts/crew_state.py:3376-3382`). Function bodies past
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
fails `--check`. `.crew/verify.json` rule 25 (`.crew/verify.json:311`) runs `--check` for any change under
`.claude/rules/**` or `.crew/codemap/**`, so **a code-map edit without a regeneration fails the Stop
gate** - see `verification-harness.md`. DERIVED from the source above; the command was run by
T-0015 against this refresh.

## The tracker interface (T-0021, crew 1.0.43)

DERIVED at `2a9e0989` (review round 4's fixes; set to 1.0.43 at `d276b268`;
first derived at `7b667587`, re-derived at `bcb77ce2` and `c2ae46ab`); line
citations re-mapped, and the Windows pinning sentence re-derived, at T-0072's
merge of T-0077 (`a4eb2f55`), as T-0079's merge of it had at `81685adf`.
`plugin/crew/hooks/scripts/crew_tracker.py` is the one module that writes a
tracker, and the only crew code that writes outside the repository (an
Obsidian vault). A CLI the commands call, not a hook.

- `resolve` (`:212`) reads BOTH config shapes - `.crew/crew.json`
  `tracker.kind` and `.crew/config.json` `tracker` (`_side`, `:141`) - and
  answers `could not tell` when both state a kind and they differ; for
  obsidian, when the two files yield a different effective vault, `boardDir`,
  `board` or lane names, defaults and the `memory.vaultPath` fallback applied,
  a value only one file yields included (`_effective` `:178`,
  `_effective_disagreements` `:199`); for jira/sdp, when their blocks differ
  whole, a block only one file carries included. `not configured` when
  neither states one. Every write refuses on `could not tell` (`_gate`,
  `:272`).
- Status -> lane is the table `LANE_FOR_STATUS` (`:92`), `ready` (brainstorm's
  approval) included, mapped to the backlog lane; a status absent from it is
  refused with nothing written (`move`, `:1481`). `STATUS_ORDER` (`:91`) is
  read by `_backwards` (`:654`): a move backwards, or from a status crew does
  not know, is `could not update` unless `--reopen`.
- DERIVED (T-0037; measured on this tree, anchors not moved):
  the ticket status vocabulary's one owner is this table. `OWNER_STATUSES`
  (`plugin/crew/hooks/scripts/crew_tracker.py:101`, `needs-owner`: open,
  Backlog lane) and `CLOSED_STATUSES`
  (`plugin/crew/hooks/scripts/crew_tracker.py:102`, `cancelled`,
  `superseded`: Done lane, checked) sit beside `STATUS_ORDER`
  (`plugin/crew/hooks/scripts/crew_tracker.py:100`) as rows of
  `LANE_FOR_STATUS` (`plugin/crew/hooks/scripts/crew_tracker.py:103`).
  `_backwards` (`plugin/crew/hooks/scripts/crew_tracker.py:668`) refuses any
  move out of a closed word, and `done` to a closed word or `needs-owner`,
  without `--reopen`; `needs-owner` to or from an open word is never
  backwards; `_PUSH_AT` (`plugin/crew/hooks/scripts/crew_tracker.py:129`) is
  unchanged, so Jira/SDP push none of the three (`_push`,
  `plugin/crew/hooks/scripts/crew_tracker.py:1477`). The closed words also sit
  in `crew_state._DONE_RE` and `_TABLE_DONE_WORDS`
  (`plugin/crew/hooks/scripts/crew_state.py:218`, `:238`), which
  `crew_ticket._index_closed` (`plugin/crew/hooks/scripts/crew_ticket.py:831`)
  reads, so approval precheck refuses them with `crew_ticket.py` unedited;
  in autopilot's `INDEX_DONE` and the new `HEADER_CLOSED`
  (`plugin/crew/hooks/scripts/crew_autopilot.py:185`, `:188`), used by
  `_phase` (`plugin/crew/hooks/scripts/crew_autopilot.py:472`) and `_closed`
  (`plugin/crew/hooks/scripts/crew_autopilot.py:1470`), whose closed reason
  quotes a `split-into:` / `superseded-by:` line (`_successor`,
  `plugin/crew/hooks/scripts/crew_autopilot.py:295`). `_phase` stops an
  INDEX `needs-owner` row as phase `needs-owner`
  (`plugin/crew/hooks/scripts/crew_autopilot.py:454`), waiting on `owner`
  (`WAITING`, `plugin/crew/hooks/scripts/crew_autopilot.py:1378`).
  `crew_status._ticket_lines` (`plugin/crew/hooks/scripts/crew_status.py:105`)
  prints `owner    <ids> (needs-owner)`. `crew_ticket.STATUS_VALUES`
  (`plugin/crew/hooks/scripts/crew_ticket.py:163`) is unchanged, so a
  `cancelled`/`superseded`/`needs-owner` header edit stales an approval.
  `plugin/crew/tests/test_status_vocabulary.py` holds every list to
  `CLOSED_STATUSES`.
- Files backend: the `.work/INDEX.md` row whose id cell matches exactly
  (`_files_create` `:666`, `_files_move` `:692`, `_files_read` `:720`); a row
  with no status cell is `could not update` / `could not read`; `create` on
  any id INDEX holds, the same title included, is refused with a reason
  beginning `id taken` (`_held`, `:642`; `TAKEN`, `:85`). `title_ok`
  (`:632`) refuses `|` and every break `str.splitlines` honours. Obsidian =
  files + the board (`_obsidian_create` `:1343`, `_obsidian_move` `:1388`,
  `_obsidian_read` `:1427`); a move whose INDEX half refuses writes no board
  (`:1422`), as a create whose INDEX half refuses writes no card (`:1376`).
  Jira/SDP answer `delegated` with `<sync> <KEY> --push --to <status>` at
  `_PUSH_AT` (`:115`: `in-progress`, `done`) and `nothing to push` otherwise
  (`_push` `:1457`, `_delegated` `:1452`); CLI exit codes 0/1/3/2
  (`exit_code` `:266`, `main` `:1535`).
- Obsidian `create`'s order (review round 4): INDEX first (`_index_holds`
  `:1317`, called at `:1345`, before `_vault_paths`), so a vault failure never
  hides a held id; then vault, identity, board and owner check; then the
  claim, the note's exclusive create (`:1370`), before the INDEX row and the
  card. A note that appeared after the owner check makes that create fail,
  and `create` answers `id taken` (`:1371`, reason from `_lost_claim`
  `:1333`) with nothing written after it. A note that was already this repo's
  is not re-created, and the INDEX row decides under its atomic update.
- Every write goes through `_atomic_update` (`:449`): the temp is created by
  `_write_temp` (`:436`) via `_write_new` (`:423`) with `_TEMP_FLAGS` (`:291`,
  `O_EXCL|O_NOFOLLOW`) under a random name, so a planted link is never
  followed; `_carry` (`:407`) gives it the target's owner and mode from
  `_ownership` (`:391`) - a new file takes its directory's owner only as root;
  then re-read the target (`:475`), `os.replace`, at most `WRITE_TRIES`
  (`:109`) recomputes.
- Vault confinement is `_vault_paths` (`:987`): realpath, `.obsidian/`
  required, relative `boardDir` without `..`, a string bare `board`,
  `commonpath` inside the vault (`:1020`), the vault's device and inode
  recorded (`:1012`), and each board or note file inside the worktree only when
  `git check-ignore` says ignored (`:1031`, per file, so a vault that contains
  the repo is covered). It runs before either half writes. The write then
  pins its directory (`_pinned` `:1184`): where `_DIR_FD` (`:298`) holds,
  `_open_pinned` (`:1106`) opens the checked vault (inode matched) and walks the
  real path's components with `_DIR_FLAGS` (`:293`, `O_DIRECTORY|O_NOFOLLOW`),
  every read, temp, replace and note create is relative to that fd, and
  `_pinned_check` (`:1134`) repeats the walk and matches device and inode
  before the temp, before the replace and after it, because the fd follows its
  directory if it is renamed out of the vault; a note written into a directory
  that left is unlinked through the fd (`_create_note_once` `:1236`).
  On Windows (T-0077), where `_DIR_FD` does not hold, `_pinned` instead holds
  a handle on the vault and on every real component down to the directory
  (`_hold_dirs` `:1068`, each opened by `_win_open_dir` `:333` with
  `_PIN_ACCESS` `:313` and no `FILE_SHARE_DELETE`, so the OS refuses to rename
  any of them while held; a reparse point, a non-directory, no file id or
  the wrong vault refuses), and `_held_check` (`:1163`) re-stats the
  directory's device and file id at the same three points. A platform with
  neither (`_WIN_PIN` `:330` false) refuses the write.
- Card ownership on a shared board (`boardDir` unset): the ticket note's
  `repo-id:` (`_NOTE_REPO_ID` `:1279`, trailing `\r` excluded so a CRLF note
  reads as written; `_card_owner` `:1283` -> ours / foreign / unknown). The id
  is `repo_id` (`:594`): the origin URL through `normal_url` (`:555`,
  lowercased, `.git` stripped; an ssh origin - scp-style or a scheme in
  `_SSH_SCHEMES` `:552` - keeps its username and drops a password, every other
  scheme drops the whole userinfo); for a local origin (`_local_path` `:577`,
  a `file://` path percent-decoded as git decodes it), an absolute path's
  realpath, and for a relative one - `../origin/app.git` names a different
  repository from each checkout - the git common dir's realpath, as with no
  origin; `None` (git could not say) refuses via `_no_identity` (`:1312`).
  `_foreign` (`:1302`) refuses create, move and read; unknown refuses create
  and move with the `repo-id:` fix (`_unclaimed` `:1307`) and is a caveat on
  read. There is no claim by title: a card's text matching this repo's INDEX
  title is not an owner. `repo_name` (`:620`) is a human label only.
- The board is edited, never regenerated: `parse_board` (`:802`, lines split
  on LF alone by `_board_lines` `:761`; the done lane must carry exactly one
  `**Complete**`, `_complete_markers` `:841`), `find_card` (`:865`; a card is
  the first id on its first line), `move_card` (`:926`; a card already in its
  lane is repaired in place by `_checkbox` `:913`, which also gives a card
  with no box one (`_BOX` `:910`), and one above `**Complete**` in Done is
  moved below it), `add_card` (`:953`), written by `_board_write` (`:1208`).
  The ticket note (`_note_text` `:1227`) is an exclusive create
  (`_create_note_once` `:1236`, `_NOTE_FLAGS` `:292`).
- Called by `brainstorm.md:28` and `:81`, `spec.md:46`, `plan.md:61`,
  `implement.md:33` and `:113`, `done.md:82` and `fix.md:27`, `:73`, `:81`,
  `:90`, `:92` (all under `plugin/crew/commands/`); brainstorm and fix take
  the next free id on `id taken`, stop on any other failed `create`, and
  create the ticket folder only after a `create` that succeeded;
  `jira-sync.md` and `sdp-sync.md` honour `--to`; `crew_status.py` prints its
  tracker line from `resolve` (`plugin/crew/hooks/scripts/crew_status.py:67`).
- Tests: `plugin/crew/tests/test_crew_tracker.py`, fixtures under
  `plugin/crew/tests/tracker_fixtures/`, 87 mutations (by `len()` at `8cabe586`; 81 before T-0077) in
  `plugin/crew/tests/sabotage_tracker.py` (two of them RED only as root: the
  owner tests skip without it); one `.crew/verify.json` rule, rule 30 (`:363-371`; `:316-323` on T-0094's merge of `8ab733d7`; `:315-322` since T-0010's rule 29 went in above it and T-0075's rule-7 paths landed; `:309-316` on T-0010-solo at `d7c7c75c`; `:307-314` on main at `3648f59a`; `:305-312` on T-0075's branch before its rule-7 paths, `:303-310` after T-0018 landed, `:301-308` before).
  JUDGEMENT: the Kanban plugin's acceptance of the edited board was checked by
  byte comparison only, never by opening Obsidian.

## The split rulebook (T-0052)

- DERIVED (T-0052, after review round 3; measured on this tree, anchors not moved):
  `plugin/crew/hooks/scripts/crew_split.py` holds `/crew:split`'s judgement as code; its module docstring is the
  API T-0058 and T-0059 build on. The thresholds are constants, each with its
  evidence in the comment above it: `PLAN_STEPS_LOOK` (`plugin/crew/hooks/scripts/crew_split.py:106`),
  `ACCEPTANCE_LOOK` (`:110`), `SUBSYSTEMS_LOOK` (`:113`), `CHILDREN_MIN,
  CHILDREN_MAX` (`:116`); `EVIDENCE_KEYS` (`:118`), `VIAS` (`:126`, `command`
  only; T-0058 appends `autopilot`), `SDP_STOP` (`:127`). `measure`
  (`:241`) returns None, never 0, for a measure it cannot read or a readable
  section that yields nothing, and `triggers` (`:268`) reports it as
  `unknown:<name>`. `check_proposal` (`:418`) over `parse_proposal` (`:352`)
  is the placement rule (every parent criterion exactly once,
  whitespace-collapsed equality); `minted_tail` (`:330`) accepts `## Minted`
  only as a trailing block of `- Child N: <id>` lines, and `_proposal_sha`
  (`:495`) hashes everything else. `tracker_mode` (`:465`) reads
  `crew_tracker.resolve`. `check` (`:574`) records the proposal's sha256, the
  current turn (`current_turn`, `:533`) and a hash of the prompt that set it
  (`current_prompt`, `:548`), both read from the context hook's per-session
  state through `crew_context._session_file`
  (`plugin/crew/hooks/scripts/crew_context.py:227`, written at `:1071-1072`),
  keyed by `CLAUDE_CODE_SESSION_ID` (`plugin/crew/hooks/scripts/crew_split.py:128`); `confirm` (`:631`) passes
  only on a different turn for the same session, an unchanged proposal, and a
  readable prompt that is neither a `<`-envelope nor check's own (owner
  decision 2026-10-04: a self-scheduled plain-text "yes" passes; a documented
  limit). `apply` (`:903`) refuses through `_refuse_mode` (`:825`) and
  `_existing_children` (`:760`: under an apply record, `apply_record_path`
  `:506`, each `## Minted` entry and each orphan, `_orphans` `:744`, needs
  provenance, `_provenance` `:706`, an open INDEX row, `_indexed` `:721` (a
  `cancelled`/`superseded` child is never reused), and a direction equal to
  the current proposal's child, `_written_for` `:733`), then writes
  `spec.pre-split.md`, mints through `_mint_children` (`:857`, calling
  `crew_ticket.mint`, `plugin/crew/hooks/scripts/crew_ticket.py:1355`,
  unedited: it takes no risk, so the child's `risk:` rides in its direction
  body), and only then sets the parent `superseded`.
- `plugin/crew/commands/split.md` is the procedure: a tracker switch (files
  and Obsidian through `apply --via command`, Jira's MCP steps kept, SDP
  stops), `check` before the confirmation, `confirm` before the first Jira
  create, and a stop under `/crew:autopilot`.
- Tests: `plugin/crew/tests/test_crew_split.py`, fixture
  `plugin/crew/tests/split_fixtures/t0004_spec_pre_split.md` (reconstructed;
  see the test's docstring); its own `.crew/verify.json` rule (the last one).
  JUDGEMENT: no `sabotage_split.py` yet - `plugin/crew/tests/sabotage*.py` is
  HARNESS, so its mutations were run by hand and a separate tooling PR
  registers them (`TODO.md`).

## The artifact refresh check (T-0008, crew 1.0.36)

`plugin/crew/hooks/scripts/crew_refresh_check.py` answers one read-only
question: are the code maps, diagrams and code graph that THIS ticket's
changed paths reach still current (module docstring, `plugin/crew/hooks/scripts/crew_refresh_check.py:1-8`)? It narrows
`crew_freshness.py`'s per-artifact questions to the paths the ticket changed
(`plugin/crew/hooks/scripts/scope_base.py` `resolve` plus `completion_audit.changed_paths`, minus
`RELEASE_BOOKKEEPING`, `plugin/crew/hooks/scripts/crew_refresh_check.py:267`), so a raw anchor lag is not staleness; each
artifact reads `fresh`/`fresh-uncommitted`/`stale`/`unknown` (`:235-238`) with the refresh command
to run, documents read `not measured`, and a scope base that hides or may
hide the change - a fallback, or (since review round 3) a recorded base with
a commit behind it naming the ticket (`_named_behind`, `:1286`) - makes the
whole answer `unknown`, and every artifact measured against that base with it
(`_unconfirmed`, `:1303`; `ticket_freshness`, `:1325`). It is a CLI the
commands call, not a hook - `plugin/crew/hooks/hooks.json` is unchanged since
`f2bb919b`.

- **`fresh` means current and committed (T-0063, crew 1.0.349).** DERIVED on T-0063-build at `309575c2`; its line numbers are that
  commit's, not the anchor's.
  `ticket_freshness` lists the uncommitted paths under `refresh_artifact_paths` with
  `_uncommitted` (`plugin/crew/hooks/scripts/crew_refresh_check.py:451`, called at `:1470`):
  HEAD against the working tree through `_moved_in_tree` (modified or staged), plus untracked
  files `--exclude-standard` already leaves out ignored ones from, None when git cannot answer,
  which sets the top line `unknown` with the stop "git could not list uncommitted refresh
  artifacts". An artifact `fresh` by anchor whose own file is listed (`_owned` `:463`: the map,
  the diagram source or a same-stem render, anything under `graph.out`) becomes
  `fresh-uncommitted`; the overall answer is `fresh-uncommitted` when any artifact is or the
  list is not empty, ranked below `unknown` and `stale` (`:1477`). `--json` carries
  `uncommitted`; `_render` (`:1508`) prints it on an `uncommitted:` line (`:1523`) and `main`
  (`:1535`) still exits 0 only on `fresh`. The graph is also `fresh` when it is `stale` by sha but
  every committed code path that moved since `built_at_commit` (`_committed_moves` `:438`, None
  on any uncommitted one) has an existing file whose MD5 equals its `ast_hash` in graphify's
  `<graph.out>/manifest.json` (`_manifest_confirms` `:1278`, asked from `_graph` `:1333`); a
  missing or unparseable manifest appends why to the stale reason. JUDGEMENT: safe because every
  `save_manifest` caller in graphify 0.9.65 and 0.9.74 runs after a successful `graph.json` write
  or a same-topology confirmation (re-read for T-0063, recorded in `_manifest_confirms`'
  docstring); a graph restored by hand from an older commit beside a newer manifest would read
  confirmed. T-0063's sabotage mutations wait for their own harness lane
  (`plugin/crew/tests/sabotage*.py` is in `scripts/check-tooling-pr.py`'s HARNESS).
- `/crew:implement` step 6 (`plugin/crew/commands/implement.md:88-116`) runs
  it after `/crew:docs` and before `/crew:review` (`:94`), runs each named
  refresh, commits, and re-runs until `fresh`; `fresh-uncommitted` means commit the listed
  paths (T-0063); a `stop` ends the loop.
- `/crew:done` Check 4 (`plugin/crew/commands/done.md:55-66`) runs it again
  and refuses on `stale`, `unknown` or (T-0063) `fresh-uncommitted` without refreshing (`:61-64`);
  a `fresh-uncommitted` goes back to implement to commit, which keeps check 1's receipt.
- `REFRESH_ARTIFACT_PATHS` (`plugin/crew/hooks/scripts/crew_refresh_check.py:277-283`: the code map,
  `docs.diagramsDir`, `graph.out`, `.claude/rules` and, since T-0036, `docs/reference`) is the one definition.
  The scope guard (`_refresh_artifact`,
  `plugin/crew/hooks/scripts/scope_guard.py:209-220`) lets a ticket write
  under those dirs without a Touch entry **only while its approval is
  current** - a path test, because a write-time check sees one Edit of a
  multi-Edit refresh. The completion audit is the same path test today:
  `_outside_refresh_artifacts` (`plugin/crew/hooks/scripts/completion_audit.py:177-187`)
  drops every refresh-artifact path when the approval is current and none
  otherwise. JUDGEMENT: T-0094 (crew 1.0.78) ships the narrower judgement,
  `artifact_verdicts` (`plugin/crew/hooks/scripts/crew_refresh_check.py:1032`), and
  the owner split its wiring into the audit off to L-0540 on 2026-09-30 (a
  harness change lands alone, `scripts/check-tooling-pr.py`), so until L-0540
  lands nothing in the hooks calls it. It answers True / False / None per
  changed artifact. A `True` needs a changed path to reach the artifact
  through its BASE copy's citations (reach = every path changed since the base,
  release bookkeeping dropped except `ADMISSION_BOOKKEEPING`, a plugin
  manifest, `:264` and `:1050-1059` in `crew_refresh_check.py`; the graph's code
  test reads the whole reach) and a re-anchor or regeneration shape: a map's
  `anchor:` moved forward from the base copy's anchor to a commit behind HEAD
  (`_map_verdict` `:864`, `_sha_moved` `:557`, `_moved_from` `:615`: an
  unchanged anchor text never moved, an anchor added to a base copy with none
  did not move either (review round 3), a base anchor git cannot resolve is
  could-not-tell, a base anchor `cat-file` cannot find counts as moved only
  when `_names_no_commit` (`:647`, review round 4) proves no commit or tag
  carries that prefix - an ambiguous short anchor is could-not-tell -, one on HEAD's history must be behind the new one), INDEX rows
  of admitted maps only, deleted lines included, read from `git diff -U0
  <base> -- INDEX.md` so a changed terminator or a BOM counts
  (`_index_verdict` `:901`, `_diff_lines` `:878`, since review round 3), a
  diagram's provenance sha moved the same way (`_diagram_verdict` `:925`), a
  rendered file beside an admitted same-stem source, its extension compared
  case-folded (`_rendered_verdict` `:1091`, review round 4), a rule
  whose bytes equal `crew_instructions.expected_rules`, or whose blob git would
  store does (`_rule_verdict` `:944`, `_stored_blob` `:984`: a CRLF checkout
  under `core.autocrlf` passes, a CRLF or BOM rewrite does not, since review
  round 3; a rule file that exists but cannot be read is could-not-tell before
  any comparison, in `_on_disk`, since review round 2), the graph after a code
  change (`_graph_verdict` `:1113`). `None` (`COULD_NOT_TELL`, `:491`) never
  admits. Since review round 5 whether the config, a rule or a map exists is
  `_present` (`:356`), lstat's errno rather than `os.path.lexists`: only
  ENOENT or ENOTDIR is absent, and a directory the hook user cannot search is
  could-not-tell (`_read_config` `:329`, `_texts` `:720`). Since review round 6
  every kind that reads or admits a working-tree file first asks `_on_disk`
  (`:839`): a deleted file, a symlink at the path or along its dirs, a git mode
  different from the base copy's (`git diff --raw`, which is why INDEX.md's
  own mode branch is gone) or a 120000/160000 stage entry is refused (since
  L-0688 also a file the base holds and the index does not, `git rm --cached`
  with the file left on disk: the `--cached` pass's `:100644 000000 ... D`
  record, `:841-850`, where a conflicted merge's `U` record with the same
  modes is refused as unmerged instead); and the
  kind comes from the most specific artifact dir holding the path (`_claims`
  `:996`, `_kind` `:1005`), two equally specific ones being could-not-tell. Since review round 7 `_on_disk`
  judges the bytes `_read_regular` (`:719`) read once through a descriptor opened with
  `O_NOFOLLOW` at every component, before any git call (on Windows, which has no `O_NOFOLLOW`,
  W-0116 adds `_FINAL_PATH` (`:769`): the read is refused unless `GetFinalPathNameByHandleW` on
  the open descriptor (`:803-804`) names `realpath(top)/rel`, and an unanswerable final path is
  could-not-tell; `_FINAL_PATH` is None off Windows); an ambiguous new anchor is
  could-not-tell, and `_base_text` (`:583`) looks the base copy up with `git ls-tree`.
  With no current approval nothing is exempt.
- T-0036 adds a fourth judged kind, `reference`: `_references`
  (`plugin/crew/hooks/scripts/crew_refresh_check.py:1383`, called from `ticket_freshness` at `:1568`)
  judges `docs/reference/integrations.md` only - absent is no line, a presence `_present` cannot
  tell or an unreadable doc is `unknown` and a stop, no citation or no Generated header is `unknown`
  and refreshable, otherwise `_judge` against the header's sha. The header is read by
  `generated_header` (`plugin/crew/hooks/scripts/crew_reference.py:113`: `GENERATED_RE` on the first
  non-blank line only, so one inside a fenced example is not it), imported at
  `crew_refresh_check.py:238`. `crew_reference.py lint` (`:213`; CLI `main` `:233`) is what
  `/crew:reference --integrations` (`plugin/crew/commands/reference.md:79`) runs on its draft:
  header, an anchor and an `Auth:` line per `###` entry, every anchor inside the repo and within its
  file, no empty doc, and `SECRET_PATTERNS` (`:62`, known shapes only) reported by name and line,
  never by value nor by an anchor's text on the same line.
  `/crew:implement` step 6 names the doc (`plugin/crew/commands/implement.md:90-91`). Tests:
  `plugin/crew/tests/test_reference_docs.py`. JUDGEMENT: `artifact_verdicts` has no `reference`
  kind, so once L-0540 wires it into the audit a refreshed `integrations.md` will need Touch;
  `--flows` and `docs/reference/flows/` are L-0549's.
- Tests: `plugin/crew/tests/test_refresh_check.py`,
  `plugin/crew/tests/test_scope_guard_refresh_artifacts.py`,
  `plugin/crew/tests/test_completion_audit_refresh_artifacts.py` (main's; T-0094's
  audit cases and every T-0094 `sabotage_refresh.py` entry are L-0540's), and since
  T-0094 `plugin/crew/tests/test_refresh_admission.py` on the shared
  (review round 2 added `test_an_unreadable_rule_is_could_not_tell`,
  `test_a_new_anchor_git_cannot_judge_is_could_not_tell`,
  `test_a_moved_anchor_git_cannot_order_is_could_not_tell` and
  `test_a_removed_rule_whose_base_copy_git_cannot_read_is_could_not_tell` there, and
  `test_an_unreadable_rule_fails_the_audit_as_could_not_tell` in the audit suite (landing with L-0540);
  review round 3 added `test_an_anchor_added_where_the_base_copy_had_none_is_refused`,
  the INDEX byte, mode and git-diff cases, the rule byte and git-hash cases, and
  `test_a_crlf_checkout_under_autocrlf_is_judged_as_git_stores_it`, the must-allow neighbour;
  review round 4's successor added `test_an_ambiguous_base_anchor_is_could_not_tell` (real git, a
  seven-hex sha1 collision found by `refresh_fixtures.ambiguous_commit_prefix`),
  `test_a_base_anchor_git_cannot_disambiguate_is_could_not_tell`,
  `test_a_base_anchor_whose_candidates_git_cannot_type_is_could_not_tell`,
  `test_an_ambiguous_new_anchor_is_refused`, the case-folded rendered-diagram pair and its
  two must-block neighbours, and
  `test_artifact_dirs_that_cannot_be_resolved_fail_the_audit_as_could_not_tell` in the audit suite (landing with L-0540);
  review round 5 added `test_a_config_whose_presence_cannot_be_proven_is_judged_by_its_errno`,
  `test_a_generated_rule_whose_absence_cannot_be_proven_is_could_not_tell` and
  `test_a_map_whose_presence_cannot_be_proven_is_could_not_tell`, lstat failing EACCES under
  the dir, with the not-a-dir and truly-removed must-allow neighbours;
  review round 6 added `test_a_deleted_rendered_diagram_is_refused_beside_a_re_anchored_source`,
  `test_a_deleted_graph_file_is_refused_after_a_code_change`, `test_a_symlinked_artifact_is_refused`
  over six kinds with `test_the_same_artifact_as_a_regular_file_is_admitted` as its control,
  `test_an_artifact_under_a_symlinked_dir_is_refused`, `test_an_artifact_whose_git_mode_changed_is_refused`,
  `test_an_artifact_staged_as_a_symlink_is_refused`, `test_graph_files_under_the_diagrams_dir_are_judged_as_graph`,
  `test_overlapping_artifact_dirs_classify_by_the_most_specific` and
  `test_equally_specific_artifact_dirs_are_could_not_tell`)
  `plugin/crew/tests/refresh_fixtures.py`, with mutations in
  `plugin/crew/tests/sabotage_refresh.py`; `.crew/verify.json:312-331` (rule
  26) maps them, `implement.md`, `done.md`, since review round 3
  `scope_guard.py`, `completion_audit.py`, `crew_freshness.py` and
  `scope_base.py` with their own suites, and since T-0094 `crew_instructions.py`,
  to one pytest rule; since T-0094 review round 2 `test_refresh_admission.py`
  is its own rule 33 (`.crew/verify.json:393-401`, 12s) so it fits the Stop
  budget beside rules 0 and 16 (the `**/*.py` rule, 38s; both `why` texts still call it 15), and rule 26 (58s) is deferred at Stop on a
  hook-script edit (its `why` says so first). Confirmed
  present, **not run and not read** by this note.

`docs/diagrams/process-crew-lifecycle.mmd` drew `/crew:done` as "all three
or nothing" at `adf8d1dd`; T-0008's refresh commit `b7b02842` redrew it as
"all four or nothing" (its `:246` at `d7c7c75c`).

## Development standards and the pre-review self-check (T-0085)

DERIVED at `22399a9c`, read in full: `plugin/crew/hooks/scripts/crew_standards.py`, the
`standards_gate` hunk of `review_run.py` and the block tuple of `review_prompt.py`. Line
numbers re-read at `07bcaf3b` (review round 1 fixes), where `crew_standards.py` was read in
full again, re-read for the successor plan's round-2 fixes, where `_scope` gained the
merge-base fallback, and re-read on T-0085's merge of main `8ab733d7` (`grep -n '^def '` on the
merged tree) after review round 3's fixes (`33521aa4`), whose hunks were read in full.

- **Sets.** `parse_set` (`plugin/crew/hooks/scripts/crew_standards.py:145`) reads a `---`
  front matter (`set`, `applies-to` as JSON, `_front_matter` `:112`), `## <ID> <name>`
  headings whose prefix must equal the set, `## Supplements <ID>` sections, and the bold
  fields in `FIELDS` (`:74`); plugin sets need `PLUGIN_FIELDS` (`:75`), the overlay only
  Rule and Self-check. Any other `## ` heading is a problem, not prose. `_plugin_sets`
  (`:235`) refuses a plugin set that carries Supplements, repeats a set name, or names
  itself `REPO`, the overlay's set.
- **Effective set.** `effective_set` (`:262`): every `*.md` under
  `plugin/crew/skills/crew-standards/references/` whose `applies-to` holds `"**"` or matches
  a changed file through `crew_ticket.glob_match` (`_applies` `:228`), GEN first, then the
  overlay `OVERLAY_REL` (`:71`). Only `FileNotFoundError` on the overlay is `absent`
  (`_read_bytes` `:101`); any other read error, a decode error, a wrong set, a reused plugin
  id or a Supplements naming no plugin standard is `unknown` with a problem. The digest
  covers each included file's set name and bytes, and the overlay's absence.
  The first stack set is `plugin/crew/skills/crew-standards/references/python.md` (set
  `PYTHON`, `applies-to: ["**/*.py"]`, nine standards, T-0086 slice 1); no loader code changed for it.
- **Self-check.** `init` (`:520`) exclusive-creates `.work/tickets/<id>/selfcheck.md`;
  `record_problems` (`:414`) refuses a missing, duplicate or unknown row, a status outside
  `STATUSES` (`:78`) and placeholder evidence; `stamp` (`:535`) validates the rows from one
  read (`_read_selfcheck_raw` `:370`), resolves the ticket's scope base (`_scope` `:460`):
  a recorded start as recorded; a start `scope_base` recorded as a merge-base guess
  (`record-fallback`) used and marked with its reason; a kept record that is gone or no
  longer an ancestor of HEAD as `scope_base.resolve`'s merge-base, the base `/crew:review`
  bundles against, with a `(fallback)` note on every output line derived from it (`_noted`
  `:506`); no entry at all, or the HEAD-only fallback, refused, naming `--record` only when
  `_scope_entry` (`:438`) finds no entry (`--record` keeps an existing one). A
  `.crew/.scope-base` that exists but cannot be read or parsed is refused without naming
  `--record`, which would rewrite it with this ticket's entry alone (`_scope_entry` tells it
  from an absent record through `_read_bytes`). It takes `review_patch.compute`'s
  `bundle_sha256` over it, refuses if the file's bytes changed meanwhile, and writes
  `_STAMP_RE`'s line (`:86`) under the header through a temp file and `os.replace`
  (`_write_replacing` `:329`); `stamp`'s docstring names the remaining window between that
  re-read and the replace as an accepted risk, not a GEN-03 binding.
- **Gate.** `review_run.run` first calls main's `preflight`
  (`plugin/crew/hooks/scripts/review_run.py:672`, at `:846`; #264): a CLEAN receipt covering the
  bundle answers CLEAN with no round and no self-check, and a verify gate that has not passed
  the tree is refused with exit 5 before the self-check is asked for (owner decision
  2026-09-30, "Preflight first"; `test_preflight_answers_before_the_selfcheck_is_asked_for`).
  Then (L-0574, DERIVED) `prereview_gate` (`:731`, called at `:857`) runs
  `plugin/crew/hooks/scripts/review_checks.py` over the bundle's changed files against their base
  blobs, per `.crew/verify.json`'s `preReview`: a NEW linter finding is exit 5 and not
  overridable; COULD NOT CHECK is exit 5 unless `--allow-unverified`; only an active incident
  stands it down. Only then does it call `standards_gate` (`:699`) at `:859`, before
  `review_ledger.reserve` (`:863`), for every provider, unless `review_ledger.status` already
  reads `NEEDS_REPLAN` or no rounds left: then the budget refusal answers first and neither the
  pre-review checks nor the self-check is asked for (review round 3). `crew_standards.review_gate`
  (`:663`) applies unless `gate_applies` (`:597`) proves there is no approval receipt: only
  an `lstat` `FileNotFoundError` whose nearest existing ancestor is a directory
  (`_ancestor_problem` `:577`; Windows answers a lookup under a regular file with
  `FileNotFoundError`, fixed at T-0085's land) is "absent" (a printed "not required" note); a corrupt
  receipt, a failed lookup or any other `OSError` (a non-directory or unreadable parent)
  gates, with a "could not tell" note. It reads the manifest, and `_gate` (`:635`, behind
  `gate_problems` `:629`) re-checks the record's completeness and compares the stamp's bundle and standards digest; on a pass the
  note carries `std:<first 8 of the digest>` for the metrics row. Problems return
  `EXIT_USAGE` (`review_run.py:724`) unless `crew_incident.read_state` is active, which logs
  a `standards-selfcheck` skip (`:714`) and reserves.
- **Checklist.** `review_prompt.build` puts `crew_standards.checklist_block`
  (`plugin/crew/hooks/scripts/review_prompt.py:306`, defined at `crew_standards.py:664`)
  after the test receipts; it never reads `selfcheck.md`. When the manifest's file lists
  are unusable it lists the always-on sets (those whose `applies-to` holds `"**"`) under an
  `UNKNOWN:` line. Since L-0601 the next block is `recurring_findings.review_block(root,
  manifest)`, the recurring-findings classes keyed to the manifest's changed files (every class
  under `UNKNOWN:` when the file lists are unusable), then the web tests.
- **Loop and metric.** `proposals` (`:724`) exclusive-creates
  `standards-proposals-r<N>.md` from `review_verdict.parse`'s findings, NIT dropped, and
  refuses an out.txt the parser calls INCOMPLETE, writing nothing; `metric_summary` (`:795`)
  groups round-1 rows from `crew_migrate.metrics_rows` by ticket and sides each row with
  `_std_side` (`:778`, on `_STD_TOKEN_RE` `:89`): no token is before, `std:<8 hex>` after,
  and `std:none` or any other `std:` value is counted on neither side, as are unknown
  rounds; `metric --record` (`:832`) appends a line with no `|`.
- **Tests.** `plugin/crew/tests/test_crew_standards.py`, `test_review_run_standards.py`,
  `test_review_prompt.py`, `test_lifecycle_commands.py`; fifty-one mutations in
  `plugin/crew/tests/sabotage_standards.py` (`STANDARDS_MUTATIONS` `:61`; 44 at origin/main
  `a7524aac` by `len()`, all T-0085's, then T-0086's seven for the Python set), appended in
  `plugin/crew/tests/sabotage.py` at `:3068`; `.crew/verify.json`'s rule 37 (`:425-438`) runs them.
  JUDGEMENT: the approval-receipt condition is
  the one way a ticket reaches review without the gate; it exists because the pre-existing
  review_run tests run tickets with no receipt, and a ticket without one cannot pass
  `/crew:done`.

## The Kimi Code provider (T-0028, feature half; the review launch is L-0527)

- **DERIVED** at `c43a54c1`: `kimi` is in both provider tuples
  (`plugin/crew/hooks/scripts/crew_state.py:1487-1488`), second in the default `qa.order`
  (`plugin/crew/hooks/scripts/crew_state.py:1199`), with `qa.kimi` / `dev.kimi` blocks holding
  only `model` (`plugin/crew/hooks/scripts/crew_state.py:1203`, `:1212`). `family`
  (`plugin/crew/hooks/scripts/crew_state.py:1491`) answers `kimi` for the `kimi` provider before
  it reads the model (`:1533-1534`), since the Kimi Code id `k3` would otherwise read as family
  `k`. `crew_config.PATH_PROVIDERS` (`plugin/crew/hooks/scripts/crew_config.py:136`) asks `which`
  about `kimi`, presence only.
- **DERIVED**: `plugin/crew/hooks/scripts/kimi_probe.py` has five states (`:81`), only `ok`
  launchable (`:194`); `resolve_alias` (`:257`) maps an id to the config.toml alias served by a
  `type = "kimi"` provider; `probe` (`:506`) runs one live call in a throwaway directory with the
  read-only agent file (`write_agent_file`, `:214`; `read_only_flags`, `:236`) and a scrubbed env
  (`kimi_env`, `:205`), and `classify` (`:478`) reads its stream through `final_message`
  (`:151`), the stream-json parser, which lives here so the review harness can import it. A
  timed-out probe's process group is killed and the follow-up read is bounded (`_run`). `probe`
  refuses (`unknown`) when the temporary directory lies inside a repository
  (`_inside_a_repository`, `:382`), and a wrong-shaped `api_key` or `oauth` entry is `unknown`.
  Round 7: a non-string `default_model` is `unknown`; only the provider's own credential file
  (`credentials/<name>.json` for `key = "oauth/<name>"`) counts as a login; each output pipe is
  drained by `_CappedReader` (`:440`) keeping at most `OUTPUT_CAP`, past which the call is
  `unknown`; config.toml is opened once, non-blocking, and checked and read through that handle
  (`_read_config`, `:348`).
- **DERIVED**: the launch gate. `crew_config.review_launchable`
  (`plugin/crew/hooks/scripts/crew_config.py:1898`) is `review_run.LAUNCHED` plus the in-session
  `claude`, None when that list cannot be read; `order_candidates` (`:1921`) refuses a `qa.order`
  provider outside it ("/crew:review cannot launch `kimi` yet") and None admits nothing. It is the
  one coupling between the provider table and the review harness, pinned by
  `test_launch_gate_agrees_with_review_run` in `plugin/crew/tests/test_provider_table.py`.
- **DERIVED**: nothing launches Kimi for a review yet. `review_run.py`'s `--provider` choices are
  `codex`, `copilot` and `claude` (`plugin/crew/hooks/scripts/review_run.py:941`), and
  `commands/review.md` has no Kimi row; L-0527 (tooling only) adds the launch, and adding `kimi`
  to `review_run.LAUNCHED` makes Kimi eligible with no crew_config change.

## The merge train (L-0520, crew 1.0.86; L-0558 fixes, crew 1.0.102)

DERIVED at this anchor from `plugin/crew/hooks/scripts/crew_train.py` (read in full). This is PR 1
of the owner's split (2026-09-30): the CLI only, plus L-0558's fixes for L-0520's review round 2
and the owner's rerere rule. The gate round refusing on it (`review_run.py` exit 6), the
reviewer's rerere block and the sabotage rows (S1-S19, and L-0558's S20-S33) are L-0526; until
then the train is advisory.

- **What it is.** One locked queue per clone serialising gate+land per overlapping Touch set;
  lanes still implement in parallel. State under `<git-common-dir>/crew/train/` via `train_dir`
  (`plugin/crew/hooks/scripts/crew_train.py:281`, on `crew_ticket.state_dir`): `state.json`
  (`SCHEMA` `:131`), `events.jsonl` (`read_events` `:589`), `merge-log/<id>.jsonl`
  (`merge_log_path` `:296`, `read_merge_log` `:1169`). No config key: `arm`
  (`:799`) publishes a complete `state.json` with `os.link`, which fails if it exists; `disarm`
  (`:829`) refuses under the lock while entries exist.
- **Fail closed.** `load` (`:385`) returns `absent` only when `_absent` (`:305`) proves
  `state.json` missing (ENOENT under a directory ancestor); unreadable, unparseable, a malformed
  top-level field (`_state_problem` `:364`: `schema` an integer 1 and `seq`/`order` non-bool non-negative ints via `_count`
  `:357`, `entries` a list, `armed_at`/`armed_by` strings) or a malformed entry (`_entry_problem`
  `:331`) is `could not tell`. `read_events` names, on every read and whatever its seq, every unparseable line and every record failing
  `_event_problem` (`:575`; `EVENT_KINDS` `:139`) instead of skipping it; `_notices` (`:766`)
  turns each into a `could not tell whether ... concerns you` line, and `arm` refuses on one.
  `_Lock` (`:426`) is `review_ledger._Lock`'s shape plus an owner token checked before removal,
  `LOCK_WAIT_SECONDS` (`:132`), never removed for age. `_mutate` (`:545`) refuses absent as
  `NotArmed` (exit 1) and anything else unreadable as `TrainError` (exit 3), numbers events past
  `max(state.seq, _last_seq)` (`:526`), and hands them to `_commit` (`:473`), which appends the
  events FIRST and then `os.replace`s the state, truncating the events file back (or removing it)
  when either fails. `touch_of` (`:624`) returns `None` (overlaps everything) for any Touch that is
  not a readable, problem-free, non-empty list. `_plain` (`:169`) refuses CLI values that carry
  control characters, and refs that start with `-` or hold whitespace (exit 2).
- **Overlap and the hold rule.** `_prefix` (`:645`) is the case-folded segments before the
  first glob segment; `entries_overlap` (`:664`) is a segment-prefix test; `touch_overlap`
  (`:668`) returns every colliding pair, refresh artifacts dropped by `effective`
  (`:657`, `REFRESH_PREFIXES` `:135`) - for OVERLAP only. `meets_touch` (`:680`) judges the full
  Touch for the moved-path checks and the notices (L-0558). `_blockers` (`:733`) is every holder,
  and every earlier-ordered waiter, on the same base with an overlapping Touch. `acquire` (`:867`)
  upserts the entry, prints unseen notices, logs a `wait` event with each blocker's pairs, or
  refuses `merge <base> first` when `_moved_paths` (`:689`) finds base commits touching Touch, or
  holds and logs `acquire`. `_stale` (`:706`) is printed evidence only.
- **Catch-up and land.** `catch_up` (`:1091`) refuses an in-progress merge or a dirty tree
  (untracked files count, `.work/` excluded), fetches `<remote>/<branch>` bases (`_fetch`
  `:1045`: explicit `+refs/heads/<branch>:refs/remotes/<remote>/<branch>` refspec, then the base
  must equal `FETCH_HEAD` or could-not-tell; it returns that SHA, which the merge, `_merge_tree` and `_moved_paths` then use instead of the ref by name), runs `ensure_rerere` (`:987`; `rerere.enabled` only,
  `--worktree` only when `extensions.worktreeConfig` is already true, else `--local`), then
  `git -c rerere.autoupdate=false merge --no-edit <fetched sha>`, so a replay stays unmerged and unstaged.
  It parses `Resolved`/`Staged '<path>' using previous resolution.`, runs `_forget_version_files`
  (`:1009`; `VERSION_FILES` `:149`: `git rerere forget` then `git checkout -m` on each still
  unmerged with index stages 2 and 3 (`_both_sides` `:1001`), so a modify/delete conflict stays as the merge left it) and logs `conflicted`, `rerere_replayed` and `rerere_forgotten`; it never commits a
  conflicted or rerere-resolved merge, and a merge state it cannot read is `could not tell`
  (exit 3). `check_land` (`:1240`): hold, fetch, `_merge_tree` (`:1217`,
  `--write-tree --name-only`; exit 1 lists conflicts, other codes are could-not-tell),
  moved-in-Touch, `review_ledger.check_receipt`, `review_gate.gate_state`, then re-checks the hold
  and HEAD under the lock and prints `LAND_OK` and the `gh pr merge ... --match-head-commit` line
  and logs `check-land`. `release` (`:904`) logs `release`, `merged` (paths from
  `<sha>^1..<sha>`, `null` when unreadable) or `force-release` (needs `--by` and `--reason`).
- **Callers and tests.** No crew script imports it in this release;
  `plugin/crew/tests/test_crew_train.py` allows only `review_run.py` and `review_prompt.py` to (the
  L-0526 callers). `/crew:done` describes the landing sequence (`plugin/crew/commands/done.md`,
  "Landing through the merge train"; `test_lifecycle_commands.py`). `.crew/verify.json`'s
  crew_train rule runs `test_crew_train.py`. JUDGEMENT: until L-0526 and the machine-local lane
  scripts call it, nothing forces a lane through the train; its value is the queue, the land check
  and the merge log for lanes that use it.

## Forbidden commit trailers (T-0066, crew 1.0.328)

DERIVED from the code cited. `git.forbiddenTrailers` is declared in both layers,
default `[]` (`plugin/crew/hooks/scripts/crew_config.py:386` and `:603`). Its two
layers are NOT combined by `resolve_config`'s precedence: `crew_trailers.forbidden`
(`plugin/crew/hooks/scripts/crew_trailers.py:124`) reads both raw through `_layers`
(`:85`) and returns their union, case-folded and deduplicated, so a repo `[]` never
disarms the machine list. The repo layer is the `.crew/` `crew_common.repo_config_dir`
resolves (a lane worktree with none reads the main checkout's; could-not-tell is unknown). A layer `crew_config.layer_state` calls corrupt, a `git`
that is not an object, or a value that is not a list of `TOKEN_RE` (`:63`) tokens is
returned as an unknown reason, never as `[]`.

`commit_refusal` (`:270`) is the textual command check: `writes_commit` (`:240`)
finds `git [-C d|-c k=v|...] commit|commit-tree|merge` or `gh pr merge` in any simple
command (`_commits`, `:212`; heredoc and here-string bodies kept out of the split by
`_strip_bodies`, `:150`), then the whole text and every literal `-F`/`--file`/
`--body-file` file (`_message_files`, `:247`) is searched with `_trailer_re` (`:146`,
`(?i)\b<token>\s*[:=]`). A `-F` path holding `$`, `%` or a backtick, or a missing one
not written earlier in the command (`_written_earlier`, `:261`), is could-not-tell.
JUDGEMENT: nothing calls `commit_refusal` at this anchor. Its caller, the scope guard
running it ahead of `scope.mode`, touches `HARNESS` paths
(`scripts/check-tooling-pr.py`) and lands in its own change.

`check` (`:351`) is `/crew:done`'s report (`plugin/crew/commands/done.md:68-76`):
`scope_base.resolve`, then `git log --first-parent <base>..HEAD` (`_log_messages`, `:329`), so
commits merged in from main are not the ticket's (a deliberate refinement of the spec), printing
`trailers: clean (<n> commits)`, one `trailers: FINDING <sha7> <Token>` per hit, or
`trailers: unknown - <why>`, exit 0 / 1 / 2. A `head` last-resort base, and a
fallback base that reads no commit, are unknown; a line from any other fallback base
says so. `main` (`:385`) is the `--check` CLI; any unexpected exception, an import failure included, is `unknown` with exit 2. Suite: `plugin/crew/tests/test_crew_trailers.py`,
mapped by `.crew/verify.json:539-546`. The practice note it replaces said a
repository's attribution adds `Co-Authored-By`; it now says the owner's instructions
decide (`plugin/crew/skills/crew-best-practices/references/practices.md:58-62`), and
`/crew:implement` step 2 says a dispatched prompt carries no attribution or trailer
instruction (`plugin/crew/commands/implement.md:48-51`). CONFIG.md §22
(`plugin/crew/CONFIG.md:2639`) is the user-facing account.

## Native-memory vault pointers (T-0084)

Added after this note's anchor; read in full at the T-0084 build head. Read-only: nothing here
writes a vault note, a native memory file or `MEMORY.md` (the writer is L-0677, migration L-0678).

- DERIVED `plugin/crew/hooks/scripts/crew_memory.py:105` - the pointer grammar, one line
  `vault: <name> | note: <path>`; `:150` `_path_problem` refuses an absolute, backslash, `:`
  in any segment, `.`/`..`/empty segment, non-`.md` or Cc/Cf/Zl/Zp-character path (`:119`
  `_invisible`); `:212` `classify` - a pointer attempt (`:173` `_attempt`: the first non-blank
  line, Cf removed and stripped, starts `vault` + optional whitespace + `:` in any case, and
  `note:`/`|` (`:110` `_ATTEMPT_MARK`, `note` starting a word) is on that line, or the second
  non-blank line starts `|` or `note:` (`:111` `_WRAPPED`), or the line is a bare vault name or nothing after the colon
  (`:114` `_BARE`)) must be the whole body and match exactly (`:191` `_grammar`), else
  `malformed`; any other body, a prose line starting `Vault:` included, is `full-text`.
- DERIVED `crew_memory.py:138` `split_body` - CRLF, LF and a lone CR end a line; the frontmatter
  is split on its first two `---` lines and never parsed as YAML.
- DERIVED `crew_memory.py:269` `_config` - a config is absent only when `os.lstat` raises
  FileNotFoundError; anything else must read (at most `CONFIG_CAP`, 1 MiB, `:115`), parse as a
  JSON object with no duplicate key (`:259` `_no_duplicates`) and no RecursionError, and pass
  its schema (`:227` `_obsidian_problem`: `vaults` an object of objects with a string `path`,
  `vaultPath` a string; `:245` `_crew_problem`: `memory` an object, `memory.vaultPath` a string
  or null), or it is `config unreadable: <path>: <field>`.
- DERIVED `crew_memory.py:330` `vault_path` - schema-checks the Obsidian config
  (`crew_recall.obsidian_config_path()`, `:336`) and both crew layers (`:288-289`) before
  resolving; a bad Obsidian config stops every name, a bad crew config stops `memory` (and any
  name when there is no Obsidian config); `role: ignore` is `vault-unknown`; only the name
  `memory` falls back to `crew_config.resolve_config(root)["memory"]["vaultPath"]` (`:306`) and
  then, only with no `vaults` block, the top-level `vaultPath`. `:311` `_vault_dir` stats and
  lists the vault.
- DERIVED `crew_memory.py:378` `note_path` - `os.lstat` per component: a link is
  `outside-vault`, a missing component `note-missing`, any other OSError `unreadable`; the real
  path must stay under the vault's real path, be a regular file (a directory or FIFO there is
  `unreadable`) and open (`:125` `_open_regular`, non-blocking with an fstat `S_ISREG` check).
- DERIVED `crew_memory.py:451` `_check_one` - `check` lists every `*.md` (suffix in any case)
  but the exact name `MEMORY.md` (`:442`; on a case-insensitive filesystem `memory.md` is that file); `os.stat` follows links and only a regular file is
  opened, so a dangling link, FIFO, device or directory is `unreadable` unopened.
- DERIVED `crew_memory.py:1345` `main` - `resolve` and `check`; exit 0 for `resolved`/`full-text`,
  1 for any other state, 2 for usage, a missing `--file`/`--memory-dir` or an unlistable folder.
- JUDGEMENT: no hook reads it; the `crew-memory` skill is the only caller. A session follows it
  because the skill says to (open question 2 in the ticket: a hook is a follow-up, not built).

## Running an external tool: the path `shutil.which` resolves (L-1508)

Read on `L-1508-build` (stacked on `T-0017-build` 01fa9021) before its version commit; line
citations taken with `grep -n` there.

- DERIVED: `resolve_tool` (`plugin/crew/hooks/scripts/crew_common.py:38`) is `shutil.which`, no
  cache; `require_tool` (`:58`) raises `ToolNotFound` (`:53`), a `FileNotFoundError`, so a site's
  existing `except (OSError, ...)` takes the path a missing bare name took. `git_out` (`:87`) runs
  it.
- DERIVED: the sites that run `require_tool`'s path: `plugin/crew/hooks/scripts/ci_receipt.py:133`
  and `:148` (moved by L-0673's two patterns), `plugin/crew/hooks/scripts/crew_instructions.py:293`,
  `plugin/crew/hooks/scripts/crew_refresh_check.py:503`, `:517`, `:548`,
  `plugin/crew/hooks/scripts/crew_state.py:2198`, `plugin/crew/hooks/scripts/crew_status.py:52`,
  `plugin/crew/hooks/scripts/crew_tracker.py:540` and `:980`,
  `plugin/crew/hooks/scripts/crew_trailers.py:337` (imported lazily, as that module does),
  `plugin/crew/hooks/scripts/event_claim.py:100`, `plugin/crew/hooks/scripts/crew_autocycle.py:849`
  (`ps`, reached on native Windows: no `/proc`) and `:997` (`xdotool`, found at `:1017`),
  `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:928`. The crew-qa-standards scripts take
  `crew_common`'s when crew's hooks sit beside them and an equivalent `shutil.which` fallback when
  they do not (`plugin/crew/skills/crew-qa-standards/scripts/qa_audit_env.py:31`).
  `crew_autocycle._git_out` (`crew_autocycle.py:421`) resolves git itself (T-0017).
- DERIVED: `plugin/crew/tests/test_tool_resolution.py:349` fails on any process start in a plugin
  or skill script that names its program literally (`bare_sites`, `:280`), unless `ALLOWLIST`
  (`:61`) names the file, function, tool and reason; a stale entry, an empty reason, or a gate
  citation whose whole line no longer matches also fails
  (`problems`, `:315`). Guard tests stub a failing tool reachable only through `shutil.which`
  (`plugin/crew/tests/tool_fixtures.py:31`).
- DERIVED: `crew_shell.resolve_gitbash` runs the resolved git through its injectable `runner`
  (`plugin/crew/hooks/scripts/crew_shell.py:245`); the lint knows `runner`, `execute` and
  obsidian-vault's `_run_bounded` as argv wrappers (`WRAPPERS`, `:180`).
- JUDGEMENT: the lint sees a literal at the call, or in a name the same function assigns once. An
  argv built in another function, or reassigned, is not checked.

## Native-memory save, the writer (L-0677)

Added after this note's anchor; read in full at the L-0677 build head. The only writer in
`crew_memory.py`; the read side above is unchanged except that `resolve_file` now calls
`resolve_pointer` (`plugin/crew/hooks/scripts/crew_memory.py:429`), which `save` reuses.

- DERIVED `crew_memory.py:534` `writer_vault` - obsidian-vault's writer rule restated: with roles
  the single `primary` (none or several refused), without roles `default: true` else the first,
  with no `vaults` block the name `memory`; the name is resolved by `vault_path`, so writer and
  resolver agree, and the folder must hold `.obsidian/`. Nothing configured is
  `no vault configured`, exit 0; a non-boolean `guard.asciiOnly` is `config unreadable`.
- DERIVED `crew_memory.py:656` `plan_save` - reads the native bytes once, classifies them
  (`already-pointer` / a resolve state / `malformed`), derives title, note path (through
  `_path_problem`), ASCII rule, containment (`:575` `_contained`: lstat walk, a symlink is
  `outside-vault`) and `create` / `append` / `unchanged` / `collision` (`:611`
  `_existing_action`, matching `memory_id`), and computes the full note text and the new native
  bytes before anything is opened for write. `:489` `today` is the only clock read.
- DERIVED `crew_memory.py:983` `apply_note` - create = temp file (`:737` `_write_temp`, fsynced)
  then `os.link` to the name (never over an existing file); append = re-read, compare, temp and
  `os.replace`; containment re-checked after `makedirs`. `:1010` `apply_pointer` re-reads the
  native file, refuses if it changed, writes a temp beside it with the mode copied, then
  `os.replace`. `:1038` `apply_save` orders them: note, read-back (bytes equal AND
  `resolve_pointer` resolved), pointer; each failure is `kept-full-text: <reason>` with the native
  file byte-identical. `:1092` `_save_cli` is the `save` subcommand (dry run unless `--apply`).
- DERIVED (review rounds 2-3) `crew_memory.py:942` `_locked` - `apply_save` takes kernel
  locks, the note's then the native file's (one or two each), for the whole write, one non-blocking try each;
  a busy lock is `another save is running now`, any OSError `lock failed`, and every lock
  already held is released (`:928` `_release`). `:905` `_take_lock` opens (never deletes)
  `<sha256 of each key>.lock` - `:864` `_lock_keys`: the case-folded real path, plus `dev:ino`
  when the file exists - in `:844` `_lock_dir` (no absolute base is `lock failed: no cache
  folder`) (`$XDG_CACHE_HOME` or `~/.cache`,
  `%LOCALAPPDATA%` on Windows, then `crew/memory-locks`) and locks it with `:806`
  `_posix_try_lock` (`flock LOCK_EX|LOCK_NB`) or `:819` `_windows_try_lock`
  (`msvcrt.locking LK_NBLCK`, byte 0); the OS drops the lock when its holder dies. Round 1's
  TTL lock files beside the files are gone. `:639` `_is_index` refuses `MEMORY.md`, and a
  case variant only when it is the same file. `:1051` `_apply_locked` re-checks the native bytes under the locks
  (`:1028` `_now_pointer`: `already-pointer` when another save won); `apply_note` and
  `apply_pointer` re-compare right before each `os.replace`. `:960` `_create_exclusive`
  falls back to an `O_EXCL` create, never `os.replace`, when hard links are refused;
  `:774` `_fsync_dir`; `:759` `_new_mode` (0644 less the umask).
- JUDGEMENT: the locks exclude only other `save` runs by the same user on the same machine
  (not a save on another machine syncing the vault, nor Claude Code or Obsidian, which never
  take them); an edit by another program in the
  instant between the last compare and the rename is not detected (a rename is not a
  compare-and-swap).
- JUDGEMENT: Claude Code 2.1.289 kept a one-line pointer body across three new sessions in a
  probe (it rewrote the frontmatter on an update and kept the body); a later version that
  rewrites it shows as `full-text` in `check`, and `save` can be run again.

## Native-memory migrate and restore (L-0678)

Added after this note's anchor; read in full at the L-0678 build head. No new write path:
`migrate` is a loop over `plan_save` / `apply_save`, `restore` one native-file replace.

- DERIVED `plugin/crew/hooks/scripts/crew_memory.py:1134` `_migrate_row` - one row per file:
  not a regular file is `refuse: not a file`; `resolve_file` first (`resolved` is `skip: already a pointer`, `unreadable` a refuse, any
  other non-`full-text` state `skip: <state>`), then the `name:` line, `:1129` `portable`
  (`:1123` `_UNPORTABLE`: `<>:"/\|?*`, Cc, a trailing dot or space; plus device names), then
  `plan_save` with the note `<note-dir or memories/<project>>/<title>.md`; a non-`pending`
  plan is `refuse: <reason>`, `create` is `convert`, `append`/`unchanged` is `append` only when
  the existing note's `project:` (`:1179` `_owner`) is this run's, else `refuse: note belongs to
  another project`. `:1170` `_default_project`: `<slug>` for `.../<slug>/memory`, else
  --root's basename.
- DERIVED `crew_memory.py:1190` `plan_migrate` - two pending rows with one note path,
  case-folded, are both `refuse: duplicate note path`. `:1205` `_migrate_names` lists `*.md`
  minus the index (`_listed`, `_is_index`), sorted; an `--only` name not there is exit 2.
- DERIVED `crew_memory.py:1223` `_migrate_cli` - `writer_vault` first (`nothing to migrate:
  <reason>`, its exit code); with `--apply` each pending row goes through `:1215`
  `_migrate_apply` (`apply_save`) in name order, a failure being `failed` with the
  `kept-full-text` state and the loop going on. Exit 1 while a row is pending (dry run),
  refused or failed.
- DERIVED `crew_memory.py:1263` `plan_restore` - only a resolving pointer, not a symlink;
  new bytes = BOM + the pointer file's frontmatter bytes + a blank line + the note's text after
  its frontmatter, LF-only; refused when that text is empty or would classify as anything but
  `full-text`. `:1291` `apply_restore` takes `save`'s `_take_lock` on the native file,
  writes a temp beside it, re-compares, `os.replace`, then re-classifies.
- JUDGEMENT: no state file is the design; a re-run is a no-op because converted rows are
  pointers on the next read. Nothing calls either subcommand but the `crew-memory` skill.

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:1034` — `TRIGGERS`, a 15-entry
  tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2979` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:245` / `:432` —
  `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2541` — `_RATCHETED`, the
  14-key ratchet table (seven construction steps).
- `plugin/crew/hooks/scripts/crew_config.py:3136` / `:3162` — `plan_repo_write` /
  `write_repo_config`, the one repo-layer writer (T-0075); `:2936` / `:2955` — the machine pair.
- `plugin/crew/hooks/scripts/crew_config_files.py:364` — `update_json`, the lock and
  compare-and-swap both writers stand on (T-0075).
- `plugin/crew/hooks/scripts/crew_config_menu.py:1051` — `main()`, the `spec` / `save` /
  `delete-repo` / `restore-repo` CLI the `/crew:config` menu calls.
- `plugin/crew/hooks/scripts/role_write_guard.py:540` — `classify`, the
  decision function; `:685` — `main()`.
- `plugin/crew/hooks/scripts/role-write-guard.sh:380` — where the strict
  private-resolver result feeds the guard's fail-closed fallback.
- `plugin/crew/hooks/scripts/event_claim.py` — no single entry point read
  this pass beyond the module docstring; called from `notify.sh` and
  `handoff-write.sh` only.
- `plugin/crew/hooks/scripts/crew_context.py:122` — `load_crew_config`, the
  one function that reads `crew.json` before `config.json`.
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py` — no single `main()`
  confirmed at a specific line this pass; called with subcommands
  (`plan-windows-default`, `apply-migrate`) from the three sites named
  above.
- `plugin/crew/hooks/scripts/crew_resume.py:668` — `decide`, read-only;
  `main()` is the `decide` / `record` / `precompact` CLI.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:1325` — `ticket_freshness`,
  the library entry point; `main()` at `:1425`; `artifact_verdicts` at `:1032`,
  the admission judgement (T-0094) that L-0540 wires into the audit.
- `plugin/crew/hooks/scripts/crew_autopilot.py:759` — `next_phase`, read-only;
  `main()` at `:1861` is the `next` / `resume` / `settings` / `stops` /
  `route` / `status` / `deploy-allowed` / `approve` / `questions-check` CLI
  `plugin/crew/commands/autopilot.md` calls.
- `plugin/crew/hooks/scripts/crew_route.py:243` — `decide`, read-only
  route / ask / none for a prompt; `main()` at `:372` is the `settings` /
  `decide` CLI. Its hook caller is `crew_context.route_item`
  (`plugin/crew/hooks/scripts/crew_context.py:839`).
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
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1298-1303`)
  — 4 roles, all tiered, none a specialist.
- `crew_state.PM_DEFAULTS` (`:1145-1158`) and `crew_state.AUTHORITY_DEFAULT`
  (`:1102`) — the unnamed session's own dispatch authority.
- `crew_state.AUTOPILOT_DEFAULTS` (`:1134-1135`) — the repo-only `autopilot` block, `deploy`
  included (T-0072), with T-0010's `approval` and `questions` keys and T-0053's `sleep` block.
- `crew_guards.ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:195-196`)
  — 10 guard names across 4 vocabularies.
- `.crew/metrics.jsonl` — append-only, one JSON object per line, replacing
  the pre-1.0 `.crew/metrics.md` (`crew_metrics.py`'s module docstring,
  **not otherwise read**). Still machine-local: the `.gitignore` un-ignore
  list at this anchor is exactly four paths — `!.crew/codemap/`,
  `!.crew/endpoints.json`, `!.crew/verify.json` and, since T-0085, `!.crew/standards.md`
  — confirmed by reading `.gitignore:279-337` directly; `metrics.jsonl` is not among them.
- `.crew/metrics.md` — still written, now by code: DERIVED (L-0578) `review_run.finish`
  calls `review_metrics.record` right after `review_ledger.record` accepts the round and before
  review.json (`plugin/crew/hooks/scripts/review_run.py`, grep `review_metrics.record`), one row
  per round into the MAIN checkout's file (`crew_common._main_checkout`), nothing when git cannot
  name it. Readers resolve the same file since L-0582: DERIVED (at the commit adding this text)
  `crew_common.metrics_crew_dir` (`plugin/crew/hooks/scripts/crew_common.py:200`) returns the
  main checkout's `.crew/` from a linked worktree, `root`'s own otherwise, and `(None, problem)`
  when git cannot tell - including a linked worktree whose common dir is not named `.git`
  (`--separate-git-dir`, or a bare repository's worktree: `crew_common._metrics_main`, `crew_common.py:217`), which
  `_main_checkout` itself still reads as "own" for the repo config; `crew_state.read_metrics` (`plugin/crew/hooks/scripts/crew_state.py:313`)
  turns a problem into the verdict `could not tell: <why>` with `rate` None, `crew_standards.metric`
  (`plugin/crew/hooks/scripts/crew_standards.py:840`) exits 1 before any read or `--record`
  write, and `crew_status._metrics_line` (`plugin/crew/hooks/scripts/crew_status.py:197`) prints
  `metrics  could not tell (...)` and names a lane's own `metrics.jsonl`/`metrics.md` as not
  counted (`crew_common.stranded_metrics_copies`, `crew_common.py:247`). None falls back to the
  worktree's own copy. `review_metrics.metrics_path` still joins the path itself (one AST-allowed
  site in `plugin/crew/tests/test_metrics_location.py`'s lint) - JUDGEMENT: delegating it is a
  harness edit for a tooling PR. `crew_metrics.py`'s `metrics.jsonl` WRITER still uses `root`.
- `.crew/endpoints.json` and its lock file `.crew/endpoints.json.oslock`
  (created on first use, never deleted); see above.

## Calls out to

- `crew_context.py` -> `obsidian-vault`'s CLI, via `crew_recall.py` (module
  docstring only, **not read**: "crew does not search vaults itself...
  calls that plugin's read-only contract and nothing else").
- `crew_memory.py` -> `~/.claude/obsidian/config.json` (via `crew_recall.obsidian_config_path`)
  and the crew config's `memory.vaultPath`; read-only (T-0084, section above).
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
- `review_ledger.py`, `review_patch.py` — part of the review pipeline
  `/crew:review` and `/crew:done` depend on — were opened only at the T-0087
  and T-0092 lines cited below; the rest was not re-read.
- DERIVED (T-0092, crew 1.0.54): `EXCLUDED` and `_EXCLUDE_SPEC`
  (`plugin/crew/hooks/scripts/review_patch.py:111`,
  `plugin/crew/hooks/scripts/review_patch.py:112`) name `.work/`, the
  generated `graphify-out/` and, since L-0578, `.crew/metrics.md`, root-anchored, on every diff and listing but
  never on `git add`; the manifest's `excluded` is `list(EXCLUDED)`.
  `_bundle_block` prints that list as `excluded (never in the bundle): ...`,
  an empty list as `excluded (never in the bundle): none`, and a missing
  key or anything but a list of non-blank strings as
  `excluded: not recorded by this manifest (unknown)` (T-0099)
  (`plugin/crew/hooks/scripts/review_prompt.py:111`).
- DERIVED (T-0100, crew 1.0.202): `merged_main.resolve`
  (`plugin/crew/hooks/scripts/merged_main.py:67`) names the latest merged
  integration commit, `git merge-base HEAD <ref>` with `<ref>` from T-0061's
  `scope_base.base_branch` (`tickets.baseBranch`, else origin/HEAD's target,
  origin/main, main); it never applies when HEAD's branch is `<ref>` or when
  that commit is an ancestor of the ticket start, and returns `commit None`
  with a reason starting `could not tell` for no ref, a configured base branch
  naming no commit (T-0061's own reason), a detached HEAD or a git error.
  `merged_main.keep` (`plugin/crew/hooks/scripts/merged_main.py:106`) is the one drop rule: a
  path stays when it differs from the start AND from the merged commit.
  `review_patch._ticket_base_tree`
  (`plugin/crew/hooks/scripts/review_patch.py:271`) builds the synthetic base
  tree (the start's tree with each dropped path set to its working-state
  entry, and each kept path main changed since the fork -- the merge-base of
  the start and the merged commit, `plugin/crew/hooks/scripts/review_patch.py:296`
  -- set to the merged commit's entry, so main's lines are context; one second
  temporary index) that `compute` diffs from
  (`plugin/crew/hooks/scripts/review_patch.py:424`); the manifest carries
  `merged_main` (with `dropped` and `diffed_from_merged`) and `bundle_base_tree`
  (`plugin/crew/hooks/scripts/review_patch.py:462`). `merged_main.fork` is
  that merge-base; when git gives no answer it is null with a `fork_reason`
  (`plugin/crew/hooks/scripts/review_patch.py:302`), every path main also
  changed stays diffed from the start, and `_merged_field`
  (`plugin/crew/hooks/scripts/review_patch.py:558`) prints
  `diffed-from-merged=could-not-tell`. The completion audit
  applies the same rule in `changed_paths(top, base, merged)`
  (`plugin/crew/hooks/scripts/completion_audit.py:173`), where `_as_merged`
  (`plugin/crew/hooks/scripts/completion_audit.py:194`) keeps an untracked
  path whose disk bytes and mode are the merged commit's entry out of the
  since-merged set, as the bundle's `add -A` drops it; the mode is the one
  `git add` records, `_disk_mode`
  (`plugin/crew/hooks/scripts/completion_audit.py:231`): the execute bit only
  when `core.fileMode`, read once by `_file_mode`
  (`plugin/crew/hooks/scripts/completion_audit.py:224`), is not false; called from `audit`
  (`plugin/crew/hooks/scripts/completion_audit.py:279`), which prints its
  `merged main` line from `_merged_lines`
  (`plugin/crew/hooks/scripts/completion_audit.py:316`) on a failure, on an
  applying pass, and on a could-not-tell pass
  (`plugin/crew/hooks/scripts/completion_audit.py:287`); `changed_paths`
  without `merged` is unchanged for `crew_refresh_check`. The prompt's
  `merged main:` line is `_merged_main_line`
  (`plugin/crew/hooks/scripts/review_prompt.py:123`), which appends
  `_fork_clause` (`plugin/crew/hooks/scripts/review_prompt.py:143`) on a null
  fork, and the receipt check's note `_merged_note`
  (`plugin/crew/hooks/scripts/review_ledger.py:834`), which adds
  `; fork: could not tell` there (`plugin/crew/hooks/scripts/review_ledger.py:848`).
  `merged_main.py` is in `HARNESS` (`scripts/check-tooling-pr.py`).
- DERIVED (T-0079): the READ-line rule of the review verdict is
  `review_verdict._covers` (`plugin/crew/hooks/scripts/review_verdict.py:149`):
  a READ token counts for a part when, `\` read as `/` and `normpath`ed, it
  IS the part's listed path, or has no directory and is its file name;
  `parse` applies it at `plugin/crew/hooks/scripts/review_verdict.py:199`.
  The prompt quotes `review_verdict.READ_FORM`
  (`plugin/crew/hooks/scripts/review_verdict.py:108`) in `_bundle_block`
  (`plugin/crew/hooks/scripts/review_prompt.py:99`) and on the webtest
  overflow line (`plugin/crew/hooks/scripts/review_prompt.py:292`), and
  `review_run.finish` hands `parse` the manifest `path`s
  (`plugin/crew/hooks/scripts/review_run.py:540`) and the overflow file's
  scratch path (`plugin/crew/hooks/scripts/review_run.py:542`). `parse` and
  `codex_final_message` split reviewer output on `\n` only, never
  `str.splitlines()`, whose U+2028 break cut a Codex event mid-JSON
  (`plugin/crew/hooks/scripts/review_verdict.py:170`,
  `plugin/crew/hooks/scripts/review_verdict.py:262`). The rest of
  `review_prompt.py`, `review_run.py` and `review_verdict.py` was not opened.
- DERIVED (L-0576): `parse` recovers a FINDINGS round despite stray lines
  (`plugin/crew/hooks/scripts/review_verdict.py:210`): only beside a finding, with no
  other reason (`prior_reasons` lead the list, `:190`; `review_run.finish` passes its
  bundle/webtest/stream reasons in, `plugin/crew/hooks/scripts/review_run.py:549`), and
  only when no stray line is `contract_like` (`plugin/crew/hooks/scripts/review_verdict.py:135`;
  the shortfall wording net `_SHORTFALL` is `:125`). The ignored lines go to
  review.json's `ignored_text`, with the count as `ignored_lines` (`plugin/crew/hooks/scripts/review_run.py:569`), a
  `review: FINDINGS kept; ...` line (`:622`) and, as a count, the ledger row
  (`plugin/crew/hooks/scripts/review_ledger.py:394`; null when review.json's value is missing or not a non-negative int, never 0).
  `/crew:review` states the same verdict rule (`plugin/crew/commands/review.md:482-486`) and, in
  step 3.1, shows every ignored line verbatim beside the BLOCK/FIX lines (`:498-500`); CLEAN is
  exact, so a stray line beside it is still INCOMPLETE (`review_verdict.py:207-209`).
- DERIVED (T-0087, crew 1.0.53): an INCOMPLETE round is classed by
  `review_verdict.failure_class` (`plugin/crew/hooks/scripts/review_verdict.py:240`):
  `tree` when a bundle or webtest reason was added, else `tool` when the answer was
  not `delivered` (`parse` returns it, `plugin/crew/hooks/scripts/review_verdict.py:227`),
  else `reviewer`. `VERDICTS`, `FINDING_FORM` and the class names are at
  `plugin/crew/hooks/scripts/review_verdict.py:90`, `:93` and `:95`, and the Codex
  event and item vocabularies start at `:98`. `review_run.finish` computes the class at
  `plugin/crew/hooks/scripts/review_run.py:560` and prints the refund line at `:626`
  (not refunded, `:629`). The ledger refunds a `tool` round up to `REFUND_LIMIT`
  (`plugin/crew/hooks/scripts/review_ledger.py:135`; `BUDGET` `:132` unchanged).
  `_refunded` (`:296`) counts refunded rows after the successor boundary
  (`_boundary`, `:288`), `_charged` (`:302`) is spent minus refunded, and
  `reserve` tests `_charged` against `BUDGET`. `summary` (`:923`, `load = _load` at
  `:920`) is the dict `status` returns and the one `crew_status._review_lines`
  renders (`plugin/crew/hooks/scripts/crew_status.py:140`). Autopilot sends a
  refunded round back to review (`plugin/crew/hooks/scripts/crew_autopilot.py:749`,
  `_toward_review` `:765`), and `next_phase`'s no-progress stop (`:814`) lets that
  rerun through even when `/crew:review` was the command just run (review round 1).
  Only the review rerun: the marker is set when `_toward_review` answers `review`
  (`:756`), so a refresh named again with its artifact still stale stops as no
  progress (review round 4).
- DERIVED (T-0087): the shared definitions at each review seam are
  `review_patch.MANIFEST_KEYS` / `OPTIONAL_MANIFEST_KEYS` / `PART_KEYS`
  (`plugin/crew/hooks/scripts/review_patch.py:126`, `:123`, `:124`) and
  `verify_record.read_record` (`plugin/crew/hooks/scripts/verify_record.py:82`), now
  the one gate-record reader for `review_prompt._receipts_block`
  (`plugin/crew/hooks/scripts/review_prompt.py:212`) and `crew_status._verify_line`
  (`plugin/crew/hooks/scripts/crew_status.py:155`). The producer-to-consumer tests
  are `plugin/crew/tests/test_review_contracts.py`. The golden corpus of real,
  redacted reviewer output is `plugin/crew/tests/golden/review/` (41 fixtures, one
  Codex stream), built and machine-locally replayed by
  `plugin/crew/tests/golden_build.py` and replayed in CI by
  `plugin/crew/tests/test_review_golden.py`. The canary
  (`plugin/crew/tests/test_review_canary.py`) drives the stub reviewer's `golden`
  mode (`plugin/crew/tests/review_fixtures.py:104`). `scripts/check-tooling-pr.py`
  (`HARNESS` `:58`, `SEAM` `:86`, `ALONGSIDE` `:96`, `check` `:168`, `judge` `:182`)
  refuses feature work on a harness branch. `ALONGSIDE` holds no production code
  and no prompt; a `SEAM` consumer rides along only when a lane commit declares it
  with a `Tooling-seam:` trailer (`declared_seams` `:155`). `.crew/verify.json`
  rule 39 runs all of it. The external tool
  formats crew parses are in `plugin/crew/docs/external-tool-formats.md`. JUDGEMENT:
  the refund and the tooling-alone rule are the two places this area now grants or
  refuses something on its own; both carry sabotage entries in
  `plugin/crew/tests/sabotage_tooling.py`.
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
`crew_status.py`'s `_tracker_line` is `:63`; the tracker rule is `.crew/verify.json:338-346`; crew's
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
T-0004's "117 -> 119" `CHANGELOG.md:1027-1028` -> `:517-518` (T-0021's entry now sits above
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
`CHANGELOG.md:1187-1188` (T-0023's entry sits first). `crew_tracker.py`, `crew_resume.py` and
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
- `CHANGELOG.md` and the tests - cited by name only here, except `CHANGELOG.md:816` (the config
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
the tracker rule is `.crew/verify.json:339-347`. `crew_autopilot.py`, `commands/autopilot.md` and
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
side, and `:612-616` on main); T-0023's rule 29 is `.crew/verify.json:348-357`. No test suite was
executed for this note.

## Re-anchor provenance - `6f96e627` -> `a2802526`, 2026-09-26 (T-0024)

Of the paths this note cites, `git diff --name-only 6f96e627 a2802526` returns
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `plugin/crew/commands/approve.md`,
`approval-hook.sh`, `approval-hook.ps1`, `approval_hook.py`, `crew_ticket.py` and the approval
tests. Each citation into them was re-read with `grep -n`/`sed -n` at `a2802526`:

- `approve.md` - the group relay inserted after `:26` (`:27-41`); `:5` and `:7-16` hold. The
  `/crew:approve` row above now names the group path.
- `crew_ticket.py` - changed only from `:676` down (`approve(..., expect=None)` `:686`, `precheck`
  `:765`, `earlier_plan_hashes` `:800`); `parse_risk` `:505` holds.
- `approval-hook.sh` / `approval-hook.ps1` - both still call `crew_py_strict` / define
  `Resolve-CrewPython`, so the resolver counts (11 and 11) hold; the fast path now matches the
  word `approve` in any case, and with no python only a `crew:approve` prompt blocks.
- `.crew/verify.json` - rule 27 (T-0024) appended at `:290-297`; rule 26 `:281-288` holds (its last
  line gained only a trailing comma). 28 rules, 302 lines.
- `CHANGELOG.md` - the 1.0.42 entry inserted at the top, so `:65` -> `:105`; its text was already
  corrected at `6f96e627`, and the sentence above now says so.
- `marketplace.json` - `:218` is 1.0.42; `:217`'s 4/35/29 counts are unchanged.
- `plugin/crew/README.md`, `PLUGINS.md` - cited by name only here.

`crew_refresh_check.py --ticket T-0024` named this note; nothing was executed for it beyond the
re-reads above.

## Re-anchor provenance - `a2802526` -> `32223b8a`, 2026-09-26 (T-0024 review round 1)

Of the paths this note cites, `git diff --name-only a2802526 32223b8a` returns
`.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `approval_hook.py` and the approval tests. Re-read at
`32223b8a`:

- `approval_hook.py` - the round-1 fixes (one-line rule for a group or confirm, the expanded form
  carrying nothing but its tags, an atomic claim of the pending list, the partial-record report)
  moved `_pending_group` `:313` -> `:334` and `_confirm` `:369` -> `:406`; the `/crew:approve` row
  above is re-pointed. The wrappers and `crew_ticket.py` did not change.
- `CHANGELOG.md` - the 1.0.43 entry inserted above 1.0.42, so `:105` -> `:123`, same text.
- `marketplace.json` - `:218` is 1.0.43; `:217` unchanged.

## Re-anchor provenance - `32223b8a` -> `f8671fdc`, 2026-09-26 (T-0024 successor, step 6)

Of the paths this note cites, `git diff --name-only 32223b8a f8671fdc` returns `approval_hook.py`, `crew_ticket.py`, `plugin/crew/README.md`, `commands/approve.md`, `BUDGETS.md`, the approval tests and `sabotage_approval.py`, plus the version files and `CHANGELOG.md`. Re-read at `f8671fdc`:

- `approval_hook.py` - `_top_level`, the comma rule and `_wrote` added above them moved
  `_pending_group` `:334` -> `:359` and `_confirm` `:406` -> `:431`; the `/crew:approve` row is
  re-pointed and names the three new rules.
- `crew_ticket.py` - `_index_closed` rewritten with its own matcher (`_names`), so `precheck`
  `:765` -> `:793` and `earlier_plan_hashes` `:800` -> `:828`; `approve` `:686`, `parse_risk`
  `:505`, `approval_digest` `:558` and `status` `:585` hold.
- `approve.md` - two lines added inside the relay, now `:27-43`; `:5`, `:7-16` hold.
- `CHANGELOG.md` - the 1.0.44 entry inserted at the top, so `:123` -> `:142`, same text.
- `marketplace.json` - `:218` is 1.0.44; `:217` unchanged. `plugin/crew/README.md` - cited by
  name only here.

## Re-anchor provenance - `f8671fdc` -> `45345812`, 2026-09-26 (T-0024 review round 3)

Of the paths this note cites, `git diff --name-only f8671fdc 45345812` returns `approval_hook.py`,
`crew_ticket.py`, `plugin/crew/README.md`, the approval tests, `sabotage_approval.py`, the version
files and `CHANGELOG.md`. Re-read at `45345812`:

- `approval_hook.py` - the outside-text rule now applies to a single id too; `_pending_group`
  `:359` -> `:361`, `_confirm` `:431` -> `:433`, re-pointed in the `/crew:approve` row.
- `crew_ticket.py` - `_cell_id`/`_prose_names` replace `_names`; `precheck` `:793` -> `:810`,
  `earlier_plan_hashes` `:828` -> `:845`; `approve` `:686`, `parse_risk` `:505`,
  `approval_digest` `:558`, `status` `:585` hold.
- `CHANGELOG.md` - the 1.0.45 entry at the top, so `:142` -> `:154`, same text.
- `marketplace.json` - `:218` is 1.0.45. `approve.md` did not change.

## Re-anchor provenance - `65bb3330` + `474aea8b` -> `8de3c669`, 2026-09-27 (T-0024 lands on T-0018's main)

`affa22a5` merges T-0024's reviewed head `474aea8b` (review round 4 FINDINGS, owner-accepted) into
main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245), and `8de3c669` bumps crew to 1.0.48.
The two sides share no source file: T-0024 changed `approval_hook.py`, both approval-hook wrappers,
`crew_ticket.py`, `commands/approve.md` and their tests; both sides changed `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md` (merged cleanly), `plugin/crew/tests/sabotage.py`,
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's first.
Every body citation into a file either side changed was checked on `8de3c669` against both
sides' content at the same line (a script comparing `git show` at `67caa4b8` and `474aea8b` with the
merged tree). Corrected here: crew's version is 1.0.48 (`:218`, `plugin.json:3`); T-0004's
CHANGELOG "117 -> 119" is `:608-609`, T-0024's four entries now sitting above it; T-0024's branch
range is added to the anchor history at the top. The `/crew:approve` row's `approve.md`,
`approval_hook.py` and `crew_ticket.py` citations are T-0024's and hold (main changed none of those
files). No test suite was executed for this note.

**Re-anchored `53f5482c` -> `d3a1c77e` on 2026-09-27 (T-0072, crew 1.0.44).** `d3a1c77e` is T-0072's version commit on `T-0072-build`, after it merged origin/main `f0b12ee6` (T-0042's landing) with a merge commit. `git diff --name-only 53f5482c d3a1c77e` over the cited paths returns only T-0072's changes and the version files. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,612 lines across 121 files), `plugin/PLUGINS.md` (`:14` 1.0.44, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` docstring section and functions, 694 -> 837 lines), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, a closing §20 section), `CHANGELOG.md` (+32 at the top) and the autopilot tests. Citations into `crew_autopilot.py` were re-taken with `grep -n` and corrected above (`settings` `:592` -> `:610`, `next_phase` `:451` -> `:469`, `main` `:639` -> `:760`, the `crew.json` warning `:612-616` -> `:640-644`, the stop tuples +18); leaf counts re-executed (122 / 67 / 55 / 0); `test_crew_config.py:277` -> `:278`; T-0004's CHANGELOG leaf sentence `:276-277` -> `:307-308`; the version line reads 1.0.44. The `deploy_allowed` paragraph under `/crew:autopilot` is new. No suite was run by this note.

**Re-anchored `d3a1c77e` -> `e30af7f9` on 2026-09-27 (T-0072 review round 1).** `e30af7f9` is T-0072's review-round-1 fix commit on `T-0072-build`. `git diff --name-only d3a1c77e e30af7f9` returns `.crew/verify.json` (rule 27's `why` re-measured in place, still `:293-300`), `CHANGELOG.md` (the 1.0.44 entry, four lines reworded, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, now 18,615 lines across 121 files; `check-marketplace.py` prints `all checks passed`), `plugin/crew/CONFIG.md` (+3 lines in §20's closing section, at `:2317`; nothing cited above it moved, `:2251-2258` holds), `plugin/crew/hooks/scripts/crew_autopilot.py` (+24 lines: the docstring gains a line at `:88`, `_deploy_verdict` moves its `cloud_guard` import below the incident check, `_safe_text` and `_crash_reason` are new), `plugin/crew/tests/sabotage_autopilot.py` (+32: `CLOUD` at `:18`, six mutations) and `plugin/crew/tests/test_crew_autopilot_deploy.py`, plus the refresh artifacts of the previous pass. No crew version change (1.0.44). Citations into `crew_autopilot.py` were re-taken with `grep -n` and corrected above (`settings` `:610` -> `:611`, the `crew.json` warning `:640-644` -> `:641-645`, `next_phase` `:469` -> `:470`, `resume_target` `:540` -> `:541`, `DEPLOY_VALUES` `:110` -> `:111`, the stop tuples +1, `_incident` `:655` -> `:656`, `_deploy_verdict` `:668` -> `:669`, `deploy_allowed` `:724` -> `:742`, `stops` `:742` -> `:766`, `main` `:760` -> `:784`, the docstring section `:81-94` -> `:81-95`, 837 -> 861 lines); the `deploy_allowed` paragraph gained the round-1 ordering and boundary. `verify.json` rule 27 `:293-300` holds. The restricted sabotage run over `AUTOPILOT_MUTATIONS` (61) printed `SABOTAGE SUITE: PASS` at `e30af7f9`'s code.

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:843`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Corrected above, each re-read with `grep -n`/`sed -n`: the version, 1.0.47; the leaf table and paragraph (re-executed on the merge: 123 / 68 / 55 / 0, `test_crew_config.py:282`, T-0004's CHANGELOG leaf sentence `:436-437` -> `:467-468`); the `crew.json` warning in `crew_autopilot.settings` `:612-616` -> `:641-645`. The `/crew:autopilot` paragraph's `crew_autopilot.py` citations and the `deploy_allowed` paragraph are T-0072's from `e30af7f9`: main did not change `crew_autopilot.py`, so they stand. `crew_config.py`, `crew_route.py`, `crew_context.py` and `crew_tracker.py` changed on main's side only, so main's citations into them stand. No test suite was executed for this note.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. Corrected here: every `crew_autopilot.py` citation in the autopilot section (seven subcommands now; `next_phase` `:491`, `settings` `:655`, `stops` `:810`, `route` `:826`, `route_args` `:855`, `status` `:1049`, `main` `:1124`, the bytecode guard `:109-111`), the `deploy_allowed` paragraph (`:786`, `_deploy_verdict` `:713`, docstring `:87-101`, `_incident` `:700`, `_safe_text` `:760`, `_crash_reason` `:769`), the crew.json warning `:685-689`, `autopilot.md`'s armed check `:44-45` and resume sentence `:46-47`, and T-0004's CHANGELOG "117 -> 119" `:546-547`. Leaf counts re-executed on the merge (`leaf_paths`): 123 / 68 / 55 / 0. No test suite was executed for this note.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). Every citation into `crew_autopilot.py` was mapped with a line diff (`21429244` -> `53855ea5`) and each moved one re-read with `sed -n`; corrected above (+2 from `:96`, +8 from `:721`, +20 from `:1124`), with the file's length, and the `deploy_allowed` paragraph gains review round 3 (any failure checking for an incident refuses; `_cli_value`). `.crew/verify.json` rules 27, 28 and 29 are still `:293-301`, `:302-309` and `:310-318`; `CONFIG.md` and `CHANGELOG.md` are cited here without a line in the changed range. No suite was run for this note; the suite runs are reported with the fix.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:852` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. The `deploy_allowed` paragraph is re-derived at `80326b1d` from `crew_autopilot.py` (`deploy_allowed` `:826`, `_resolve_root` `:723`, `_probe` `:708`, `_layer_problem` `:734`, `_decide` `:749`, `_settings_at` `:667`, `_cli_deploy` `:1184`, `_failure` `:1160`); `settings` `:657` -> `:658` (its crew.json warning `:694-697`), `next_phase` `:493` -> `:494`, `main` `:1144` -> `:1215`, each re-read with `sed -n`. The leaf counts were re-executed (123 / 68 / 55 / 0) and T-0004's "117 -> 119" is `CHANGELOG.md:1216-1200`. Corrected in passing: the route paragraph called rule 29 (`:437-445`) the last rule; T-0024's rule 30 (`:447`) follows it on main already. Only the leaf-count functions were executed for this note.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:852` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. The `deploy_allowed` paragraph is re-derived at `80326b1d` from `crew_autopilot.py` (`deploy_allowed` `:826`, `_resolve_root` `:723`, `_probe` `:708`, `_layer_problem` `:734`, `_decide` `:749`, `_settings_at` `:667`, `_cli_deploy` `:1184`, `_failure` `:1160`); `settings` `:657` -> `:658` (its crew.json warning `:694-697`), `next_phase` `:493` -> `:494`, `main` `:1144` -> `:1215`, each re-read with `sed -n`. The leaf counts were re-executed (123 / 68 / 55 / 0) and T-0004's "117 -> 119" is `CHANGELOG.md:1344-1345`. Corrected in passing: the route paragraph called rule 29 (`:437-445`) the last rule; T-0024's rule 30 (`:447`) follows it on main already. Only the leaf-count functions were executed for this note.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1511-1513` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). Every `crew_tracker.py` citation in the tracker-interface section was re-mapped with a line diff (`8de3c669` -> merged) and re-read by symbol; the Windows `_parent_check` sentence, false after T-0077, is re-derived from `_pinned` / `_hold_dirs` / `_held_check`; the mutation count is 87. The `deploy_allowed` paragraph and the other `crew_autopilot.py` citations moved by 6 (`deploy_allowed` `:832`, `settings` `:665`, `next_phase` `:501`, `main` `:1221`). Version 1.0.50. No suite was executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. The `deploy_allowed` paragraph and the key-entry-points `main` line were re-mapped with a line diff and re-read with `sed -n`; the paragraph now also states the text-root refusal and the one-line `--json`, and its mutation count is 64 (it said 59 at `a4eb2f55`, where `len(DEPLOY_MUTATIONS)` was 58). The `/crew:autopilot` section's citations stay scoped to the commit its own DERIVED line names. No suite was executed for this note.

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
`plugin/crew/tests/test_crew_config.py:295`); the version (1.0.48 at `plugin/crew/.claude-plugin/plugin.json:3`);
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

## Re-anchor provenance - `926443d8` + `8de3c669` -> `50a275ea`, 2026-09-28 (T-0010's successor merges `f96e9ec9`)

`ab85880b` merges origin/main `f96e9ec9` (T-0024 landed as crew 1.0.48, its code maps anchored
`8de3c669`; T-0077 as 1.0.49) into T-0010-solo `216ee85f`; `a2f4db76` fixes review round 4's
three FIXes; `3438dc9a` merges `5050ea3b` (shipstation only); `48b2820d` re-measures
`plugin/crew/BUDGETS.md` and `50a275ea` sets crew 1.0.50. The merge took main's side of this
note; it was then re-merged three-way from `67caa4b8`, T-0010's side at `216ee85f` (anchor
`926443d8`) and main's at `f96e9ec9` (anchor `8de3c669`), both sides' provenance kept, main's
first. Every body citation into a file changed since its side's own anchor was mapped with
`difflib` (a bare `:N` taken as the last path named in its section) and each one that moved was
re-read at `50a275ea`.

Re-read by hand: the `/crew:autopilot` section (`crew_autopilot.py` 1478 lines; `next_phase`
`:522`, `resume_target` `:618`, `_unreadable_autopilot` `:689`, `settings` `:707`,
`approval_policy` `:805`, `question_policy` `:846`, `approve` `:900`, `questions_check` `:1017`,
`stops` `:1054`, `route` `:1070`, `route_args` `:1099`, `status` `:1294`, `_policy_main` `:1371`,
`main` `:1388`, each re-grepped), with review round 4's could-not-tell `settings`, the policies on
the `settings` text line, and the owner-only group-confirm refusal in `crew_ticket.approve`
(`plugin/crew/hooks/scripts/crew_ticket.py:742-744`, `approve` `:723`); the `crew.json` warning
(`:744-748`); `POLICY_MUTATIONS` (54, `plugin/crew/tests/sabotage_autopilot.py:376`, registered
at `plugin/crew/tests/sabotage.py:3060`); the config leaf count (124, no key added by either
side; `plugin/crew/tests/test_crew_config.py:281`); the version (1.0.50); T-0004's CHANGELOG
"117 -> 119" (`:732-733`); and the routing and approval verify rules (30 `:317-325`, 31
`:327-334`). No test was run by this note.

## Re-anchor provenance - `8de3c669` -> `a6e81869`, 2026-09-27 (T-0079 on its branch)

`T-0079-read` was cut from `67caa4b8`, merged main `d2fbd408` (T-0024 landed; its refresh `fdc54ce9`
changed refresh artifacts only) in `f034ef5c`, and carries T-0079's commits through `a6e81869`
(crew 1.0.49). `git diff --name-only 8de3c669 a6e81869`, refresh artifacts aside, returns T-0079's
files only: `review_verdict.py`, `review_prompt.py`, `review_run.py`, their tests and
`sabotage_review.py`, `agents/reviewer.md`, `plugin/crew/README.md` (line-neutral), `CHANGELOG.md`
and the three version files. Every body citation into those files was compared by script between
`8de3c669` and `a6e81869` at the same line.
Corrected here: crew's version is 1.0.49 (`:218`, `plugin.json:3`, and the body sentence citing
them); T-0004's CHANGELOG "117 -> 119" is `:649-650`, T-0079's entry sitting above it. The
DERIVED T-0079 review bullet was written against `a6e81869` and its citations re-read there with
`sed -n`; it now also records the newline-only split (the U+2028 amendment). T-0079's branch
range is added to the anchor history at the top. Every other citation held. No test suite was
executed for this note.

## Re-anchor provenance - `a6e81869` -> `81685adf`, 2026-09-27 (T-0079 merges main, Step 7, re-bump)

`T-0079-read` gained T-0079's Step 7 (`8f7c62dd`, one `find` string in
`plugin/crew/tests/sabotage_webtest.py`), merged main `f96e9ec9` (T-0077 landed, crew 1.0.49) in
`548ee44e`, and re-bumped crew to 1.0.50 in `81685adf`. `git diff --name-only a6e81869 81685adf`,
refresh artifacts aside, returns that `sabotage_webtest.py`, T-0077's files (`crew_tracker.py`,
`crew_autopilot.py`, `sabotage_tracker.py`, `sabotage_autopilot.py`, `test_crew_tracker.py`,
`test_crew_autopilot.py`, `test_crew_autopilot_status.py`), `plugin/crew/README.md` (line-neutral
on both sides), `CHANGELOG.md` and the three version files. Every body citation of the form
`path:line` into those files was compared by script between `a6e81869` and `81685adf`.
Moved and re-cited: `crew_autopilot.py` below `_rel` shifted +6 (T-0077's cross-drive `_rel`), so
the autopilot section's citations, `settings` (`:642`), `next_phase` (`:478`) and `main` (`:985`) moved;
the tracker-interface section's `crew_tracker.py` citations were re-mapped line by line, its Windows
sentence re-derived from source (`_parent_check` is gone; `_hold_dirs`, `_release` and `_held_check`
hold and re-check the directories), and its mutation count read from the tuple (87). The version
sentence moves to 1.0.50; T-0004's CHANGELOG "117 -> 119" is now `:672`. Nothing was executed for
this note beyond the citation script and the tuple count.

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:738` and `:742` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

## Re-anchor provenance - `12682e41` + `d2444be9` -> `e95e5964`, 2026-09-27 (T-0075 merges main)

`e95e5964` is T-0075's crew 1.0.46 bump on top of `e94ce6ce`, the merge of origin/main `db14619c`
(T-0021 landed as 1.0.45, whose last note anchor was `12682e41`) into T-0075's branch. The merge
took main's copy of this note and T-0075's `d2444be9` edits were re-applied onto it; T-0075's own
re-verify of `53f5482c` -> `d2444be9` (not kept as a section, since main's side replaced the file)
found the same moves listed here. The two sides share no source file this note cites except
`.crew/verify.json`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage.py` (both sibling imports and both mutation
lists kept) and the version files. Every citation into a path `git diff --name-only
12682e41 e95e5964` names was mapped through `git diff -U0` and each moved one re-read with `sed -n`
on `e95e5964`:

- `crew_config.py` - changed on T-0075 only, everything below `_RATCHETED` (`:2548` onward);
  `:1`, `:126-128`, `:240`, `:381`, `:385`, `:1249`, `:2433-2545` hold. Leaves re-executed: 121 /
  67 / 14 ratcheted, unchanged - T-0075 added no config key. The "writers and menu" section is new.
- `phases.md` - `:180-186` -> `:182-188` (the auto-clear block).
- `.crew/verify.json` - rule 7 gained three paths (+3): rule 24 `:263` -> `:266`, 25 `:264-280`
  -> `:267-283`, 26 `:282-292` -> `:285-295`, 27 `:293-300` -> `:296-303` (no longer the last;
  T-0021's rule 28 follows), 28 `:301-308` -> `:304-311`. 29 rules, 316 lines.
- `CHANGELOG.md` - T-0075's entry (31 lines) above T-0021's; T-0004's leaf-count line `:390-391`
  -> `:420-421`.
- `marketplace.json` / `plugin.json` - `:217` now 36 commands, `:218` / `:3` 1.0.46; `ls
  plugin/crew/commands/*.md` is 36.
- `test_crew_config.py` - `:277` holds (asserts 121).
- `README.md`, `plugin/README.md`, `CONFIG.md`, the crew-setup and crew-best-practices skills,
  `BUDGETS.md`, the install scripts, `sabotage.py` - cited by name or section only here.

## Re-anchor provenance - `e95e5964` + `e463ca53` -> `f7163410`, 2026-09-27 (T-0075 merges T-0023's main)

`96b7e59c` merges origin/main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244; its notes anchored
`e463ca53`) into T-0075's branch at `0c6b5ecb` (notes anchored `e95e5964`), and `f7163410` bumps
crew to 1.0.47. The source files both sides changed since `db14619c` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/tests/sabotage.py`,
`plugin/crew/tests/test_crew_config.py` and the version files. The conflicting provenance sections
keep both sides, main's first. Each body line was classified by origin (in T-0075's copy only, in
main's only, or in both), its `path:N` citations - and bare `:N` after a path in the same
paragraph - into files the other side changed were mapped with a line diff (`git show
<side>:<path>` against the merged tree), each moved one re-read with `sed -n`, and hits the diff
attributed to the wrong file (a bare `:N` after an unrelated path, a same-named file elsewhere)
discarded rather than applied. `crew_config.py`: T-0023's `route` blocks (`:389`, `:563`) sit above T-0075's
writers, so every T-0075 citation below `_RATCHETED` moved +11 - `enum_values` `:2548` -> `:2559`,
`_value_problems` `:2586` -> `:2597`, `plan_global_write` `:2606` -> `:2617`,
`write_global_config` `:2696` -> `:2707`, `is_global_path` `:690` -> `:701`, `REPO_REFUSED`
`:2754` -> `:2765`, `REPO_VETO_ONLY` `:2775` -> `:2786`, `_REPO_WIDENING` `:2779` -> `:2790`,
`repo_widens` `:2821` -> `:2832`, `_read_repo_strict` `:2862` -> `:2873`, `plan_repo_write`
`:2891` -> `:2902`, `write_repo_config` `:2946` -> `:2957`, `_set_repo` `:3060` -> `:3071` (all
re-read); main's citations (`:389`, `:393`, `:563`, `:1260`, `_RATCHETED` `:2444-2556`) hold.
Leaves re-executed on the merge: 122 / 68 / 54 / 0; `test_crew_config.py:279` asserts 122.
`.crew/verify.json` is 325 lines, 30 rules: autopilot rule 27 `:296-303`, tracker 28 `:304-311`,
routing 29 `:312-320`. `sabotage.py` imports `ROUTE_MUTATIONS` at `:79` and
`CONFIG_MENU_MUTATIONS` at `:80`, both appended at `:3053`. T-0004's "117 -> 119" is
`CHANGELOG.md:1184-1185` (T-0075's entry now sits first). The version is 1.0.47 at
`.claude-plugin/marketplace.json:218` and `plugin/crew/.claude-plugin/plugin.json:3`; `:217`
states 36 commands. `crew_context.py`, `crew_route.py` and the templates changed on main's side
only, so the routing section's citations stand.

## Re-anchor provenance - `f7163410` + `65bb3330` -> `23371afb`, 2026-09-27 (T-0075 merges T-0018's main)

`34b5f368` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; its notes anchored
`65bb3330`) into T-0075's branch at `b5ef35df` (notes anchored `f7163410`), and `23371afb` bumps crew
to 1.0.48. The source files both sides changed since `bebbb97f` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and the version files;
`crew_autopilot.py`, `commands/autopilot.md` and the autopilot tests changed on main's side only,
`crew_config.py`, `crew_config_menu.py`, `CONFIG.md` and `sabotage.py` on T-0075's only. The
conflicting provenance sections keep both sides, main's first; each body citation into a file both
sides changed was mapped from the side its line came from onto the merged tree and re-read with
`sed -n`/`grep -n`. Corrected here: T-0004's CHANGELOG "117 -> 119" is `:545-546` (T-0075's entry sits first,
T-0018's second); `.crew/verify.json` is 326 lines, 30 rules - autopilot rule 27 `:296-304`, tracker
28 `:305-312`, routing 29 `:313-321`; `sabotage.py` imports `ROUTE_MUTATIONS` at `:79` and
`CONFIG_MENU_MUTATIONS` at `:80`, both appended at `:3053`. `crew_config.py` did not change on main's
side, so the writers section's citations (`enum_values` `:2559` through `write_repo_config` `:2957`)
hold; leaves re-executed 122 / 68 / 54 / 0, `test_crew_config.py:279` asserts 122. The version is
1.0.48 at `.claude-plugin/marketplace.json:218` and `plugin/crew/.claude-plugin/plugin.json:3`;
`:217` states 36 commands. No test suite was executed for this note.

## Re-anchor provenance - `23371afb` -> `764f6018`, 2026-09-27 (T-0075 review round 1)

`764f6018` fixes T-0075's review round 1. `git diff --name-only 23371afb 764f6018` is `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_config_menu.py`,
`plugin/crew/skills/crew-setup/config-menu.md` and three crew test files. Each citation into one
of them was mapped with a line diff from `87627d86` (the tree `23371afb` describes for those
files) and re-read with `sed -n`/`grep -n`. `crew_config.py` gained `is_repo_veto` (`:2789`) below `REPO_VETO_ONLY` (`:2786`), so the
writers section moved +9 from `:2787` on (`plan_repo_write` `:2902` -> `:2911`, `write_repo_config`
`:2957` -> `:2966`, `_set_repo` `:3071` -> `:3080`, `repo_widens` `:2832` -> `:2841`, `_REPO_WIDENING`
`:2790` -> `:2799`, `_read_repo_strict` `:2873` -> `:2882`); citations above `:2786` hold. The menu
paragraph's `crew_config_menu.py` lines were re-taken with `grep -n` and it gained the round-1
behaviour. `CHANGELOG.md` moved +10 above T-0075's entry; its four body citations were remapped.
`plugin/crew/BUDGETS.md:11` now reads 19,145 lines across 128 files (re-measured by
`scripts/check-marketplace.py`); the older BUDGETS figures above are history at their anchors and
stand. Version 1.0.48 at `764f6018`, re-set to 1.0.49 by `ca667718` (the last `plugin/crew/` commit). The rule-7 suites ran (550 passed) and the 22 `CONFIG_MENU_MUTATIONS`
went RED through `sabotage.py`'s own `main`; the full `sabotage.py` was not run for this note.

## Re-anchor provenance - `764f6018` + `8de3c669` -> `7d217751`, 2026-09-27 (T-0075 successor build, merges T-0024's main)

`7d217751` is T-0075's crew 1.0.49 bump. Between `764f6018` (T-0075 review round 1, this note's
last anchor) and it: the successor build's steps 1-9 (`4911b896`..`763eaeff`: `crew_config_files.py`
new, `crew_config.py` and `crew_config_menu.py` redesigned, their tests and sabotage entries, the
menu procedure, `commands/config.md`, `config-setup.md`, `global-config.md`, `plugin/crew/README.md`,
`CONFIG.md`, the troubleshooting guide and `CHANGELOG.md`), `748a823d` merging origin/main `d2fbd408`
(T-0024 landed as 1.0.48, notes anchored `8de3c669`), `af1ee7ef` adding two paths to
`.crew/verify.json` rule 7, `cb67a6ef` rebuilding the troubleshooting guide, `plugin/crew/BUDGETS.md`
re-measured (19,280 lines across 128 files) and the bump. The merge's provenance sections keep both
sides, main's first. Each citation into a path `git diff --name-only 764f6018 7d217751` names was
checked against the tree it was written for (`git blame` on this note gives the commit) and re-read
at `7d217751` with `sed -n`/`grep -n`; moved in this note: `crew_config.py` +1 above `default_config` (`:240` -> `:241`,
`:393` -> `:394`, `:381` -> `:382`, `:1260` -> `:1261`) and +5 at `_RATCHETED` (`:2444-2556` ->
`:2449-2561`, every construction site re-read); the writers section was rewritten from the source
for the successor design (the file layer, per-leaf judgement, the merged-file check, compare-and-swap,
the two-phase delete, three restore forms); `.crew/verify.json` rules 24-30 (`:268`, `:269-285`,
`:287-297`, `:298-306`, `:315-323`, `:325-332`) and rule 7 (`:129-144`); `sabotage.py` imports
`CONFIG_MENU_MUTATIONS` at `:80`, `APPROVAL_MUTATIONS` at `:81`, appended at `:3052-3055`. T-0024's
approval citations (`approval_hook.py`, `crew_ticket.py`, `approve.md`) changed on main's side only
and stand. Leaves re-executed at `7d217751`: 122 / 68 / 54 / 0. `wc -l crew_config.py` 3396. Suites
are reported in T-0075's implement result, not executed for this note.

## Re-anchor provenance - `7d217751` + `f96e9ec9` -> `8cabe586`, 2026-09-27 (T-0075 post-merge fixes, merges T-0077's main)

`8cabe586` is T-0075's crew 1.0.50 bump. Between `7d217751` and it: `ed7cb36c` (the stray line
step 6 left in `crew_config_menu.py:940`, a restore-line test's assertion, and the widening-warning
mutation re-anchored in `sabotage.py`, each found by the first full suite run after the build), a
1.0.48/1.0.49 step-back and re-set (`b80db8e1`, `81ed193c`), `3ebddc74` merging origin/main
`f96e9ec9` (T-0077 landed as 1.0.49: Windows directory handles in `crew_tracker.py`,
`crew_autopilot._rel`, their tests and mutations, three `plugin/crew/README.md` lines and its
`CHANGELOG.md` entry; main's notes were not refreshed for it) and the bump. Citations into the
paths `git diff --name-only 7d217751 8cabe586` names were mapped with `git diff -U0` and each
moved one checked by content at `8cabe586`; moved in this note: `crew_config_menu.py` `main` `:943` -> `:942` (the
writers section's other menu citations sit above `:940` and hold); every `crew_autopilot.py`
citation below `_rel` (`:170`, +6: `next_phase` `:478`, `settings` `:642`, `main` `:985`, the
status helpers) and its line count (1069); every `crew_tracker.py` citation below `:298` in the
tracker section (+62 up to `:998`, +105 to +123 past the pinning hunks, each matched by content),
with the Windows pinning sentence rewritten for T-0077 (`_parent_check` removed; `_hold_dirs`
`:1066`, `_held_check` `:1161`, `_win_open_dir` `:331`, `_WIN_PIN` `:328`) and the tracker rule
corrected to `.crew/verify.json:345-353` (missed at `7d217751`); 87 `TRACKER_MUTATIONS`; T-0004's
"117 -> 119" is `CHANGELOG.md:1395-1396`; the version is 1.0.50. `.crew/verify.json` did not change.

## Re-anchor provenance - `8cabe586` + `5050ea3b` -> `5e2d71a7`, 2026-09-28 (T-0075 sabotage re-anchor, merges shipstation's main)

Between `8cabe586` and `5e2d71a7`: `c426b5fb` re-anchored `sabotage_config.py`'s "repo writer accepts a
whole block" entry over both block guards (the T-0075 subset run found it vacuous: the leaf-path
rule and `value_allowed`'s shape rule each refuse a block alone), the 1.0.49/1.0.50 step-back and
re-set (`1a3cd377`, `1afd2216`), and `5e2d71a7` merging origin/main `5050ea3b` (shipstation 1.1.1:
`skills/shipstation/`, its marketplace entry and a CHANGELOG entry, none cited here). Moved in
this note: T-0004's "117 -> 119" is `CHANGELOG.md:1406-1407`. `CONFIG_MENU_MUTATIONS` is still 50;
crew is still 1.0.50 (`1afd2216`). Nothing else this note cites changed.

## Re-anchor provenance - `5e2d71a7` + `81685adf` -> `3724731b`, 2026-09-28 (T-0075 review round 3, merge of `e6e10432`)

`3036dc02` is T-0075's review-round-3 fix (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, and `README.md`, `CONFIG.md`,
`commands/config.md`, `config-menu.md`, `global-config.md`, `CHANGELOG.md`); `6d5f0b61` merges
origin/main `e6e10432` (T-0079 landed as crew 1.0.50: `review_prompt.py`, `review_run.py`,
`review_verdict.py`, `agents/reviewer.md`, their tests, `sabotage_review.py`,
`sabotage_webtest.py`, `test_webtest_guard.py`, `README.md`, `CHANGELOG.md`; its notes anchored
`81685adf`); `3724731b` re-bumps crew to 1.0.51 (`plugin.json`, `marketplace.json`,
`plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, `CHANGELOG.md`). The merge's conflicting provenance
sections kept both sides, main's first; anchor lines kept T-0075's and are replaced here.

The writers-and-menu section was re-derived from the source at `3724731b` and rewritten (every
`crew_config.py` citation from `:2567` on, every `crew_config_files.py` and `crew_config_menu.py`
citation moved, and round 3 added `assignments`, `_plan_on`, `_content_problem`, `machine_view`,
`read_restorable`, `move_no_clobber`, `create_bytes`, `read_tolerant`, `lock_if_dir`,
`parse_assignments`, `_plan_both`, `_machine_as_written`, `_unbound` and the delete digests); the
entry-point list's three T-0075 citations were re-read; the version sentence moves to 1.0.51; the
CHANGELOG "117 -> 119" citation moves to `:759-760`. `crew_config.py` is unchanged above `:2567`,
so every earlier citation into it holds. T-0079's `review_*` citations were written at `81685adf`,
and `git diff --name-only 81685adf 3724731b` does not list those three files, so they hold.
Checked by a script mapping every explicit `path:N` through `git diff -U0` and by `sed -n` on each
rewritten symbol; bare `:N` citations were read by hand. `CONFIG_MENU_MUTATIONS` is 81 by `len()`.
Nothing else was executed for this note.

## Re-anchor provenance - `3724731b` + `9631c707` -> `938e3b11`, 2026-09-28 (T-0075 review round 4, merge of `f54af3fa`)

`7d473f24` merges origin/main `f54af3fa` (T-0072 landed as crew 1.0.51: `crew_autopilot.py`,
`commands/autopilot.md`, `crew_state.py`'s line-neutral `AUTOPILOT_DEFAULTS` hunk at `:1086-1090`,
`templates/config.template.json`, `skills/crew-setup/SKILL.md`, `CONFIG.md` §20, `README.md`, its
tests, `sabotage_autopilot.py`, `.crew/verify.json` rule 27's `seconds` and `why`; its notes
anchored `9631c707`); `07354a39`, `df419a55`, `7a206c8e`, `4112498e`, `1b31ed2f` and `7ef3c4f1` are
T-0075's review-round-4 steps 11-16 (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`,
`skills/crew-setup/config-menu.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `938e3b11` re-bumps
crew to 1.0.52 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's
conflicting provenance kept both sides; anchor lines kept T-0075's and are replaced here.

The writers-and-menu section was re-derived from the source at `938e3b11` and rewritten:
`machine_lock` (`crew_config_files.py:252`) replaces `lock_if_dir` and is always taken;
`_unlink_source` keeps a foreign file's `*.moving` name and every failure after its rename is
`Displaced`, which `move_no_clobber` passes through; `apply_delete` takes the machine lock, then the
repo lock, and re-reads the machine digest inside them; `_redetected()` (`crew_config_menu.py:627`)
limits re-detection to `crew_platform.DERIVED_KEYS`; `validate_providers` refuses a non-list
`qa.order` (`crew_config.py:206-208`). Every `crew_config_files.py` and `crew_config_menu.py`
citation in it was re-taken with `grep -n`. `crew_config.py` gained 3 lines at `:206` and lost 2 at
`:239`, so every citation from `:241` on moved +1: `default_config` `:242`, `default_global_config`
`:395`, `_RATCHETED` `:2450-2562` (steps `:2465`, `:2478`, `:2489`, `:2499`, `:2535`, `:2558`,
literal `:2450-2461`), `:1262`, `:383`, the entry points `:3046` / `:3072` / `:2838` / `:2866`;
`crew_config_files.py:343` (`update_json`) and `crew_config_menu.py:1048` (`main`) moved in the
entry list. `test_crew_config.py:282` -> `:284` (T-0072's count comment above the assert). The
CHANGELOG "117 -> 119" citation moves to `:825-826`. The version sentence moves to 1.0.52. Leaves
re-executed: 123 / 68. `CONFIG_MENU_MUTATIONS` is 98 by `len()`. `.crew/verify.json` rule 27
(`:298-306`) and rule 28 (`:307-314`) hold.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N`
carried from the last path named in its paragraph, from both `3724731b` and `9631c707` to the tree
at `938e3b11` (difflib equal blocks); every citation neither base maps to itself was read with `sed
-n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `crew_autopilot.py`
citation after an `autopilot.md` mention, a `plugin.json:3` in another plugin); those were read and
hold. Nothing else was executed for this note.

**Re-anchored `9631c707` -> `b5c37635` on 2026-09-28 (T-0087, crew 1.0.52).** `b5c37635` is T-0087's crew 1.0.52 bump on `T-0087-build`, after `d05727af` merged main `f54af3fa` (T-0072 landed as crew 1.0.51). `git diff --name-only 9631c707 b5c37635`, refresh artifacts aside, returns T-0087's files (the review/gate harness, its tests, the golden corpus, `scripts/check-tooling-pr.py`, rule 31 in `.crew/verify.json`, `CLAUDE.md`'s tooling-alone bullet, the docs and guides) plus the three version files and `CHANGELOG.md`. Every body citation `path:line` into those files, outside the provenance sections, was re-mapped by script (difflib over the two blobs) and the moved ones re-read: `crew_autopilot.py` +10 below `:478` (the refunded-round branch and `_toward_review`), `review_verdict.py` (the T-0079 bullet's `:99`, `:146`, `:90`, `:116`, `:197`), `review_prompt.py` `:85`/`:236`, `review_run.py` `:323`/`:325`, `crew_status.py` `:65`, `CLAUDE.md` +7 below `:40`, `plugin/crew/README.md` +4/+5 below `:737` and `CHANGELOG.md` +59. Two DERIVED bullets for T-0087 were added under "Unverified at this anchor" (the refund, the seam definitions, the corpus, the canary, the checker). The version sentence under Inventory moves to 1.0.52. No suite was executed for this note.

**Re-anchored `b5c37635` -> `1da1233d` on 2026-09-28 (T-0087, crew 1.0.52).** `1da1233d` is T-0087's crew 1.0.52 bump re-set after two reflow commits: `4648581a` rewrapped `plugin/crew/commands/review.md` to its 551-line allowance and `plugin/crew/commands/autopilot.md` to its 100-line budget, and `4304a9da` kept the sabotage anchor "are the human's. Go back" on one line (no rule changed in either). `git diff --name-only b5c37635 1da1233d`, refresh artifacts aside, returns those two command files and the three version files, which read 1.0.52 on both sides. Of this note's citations into them, `review.md:25-29`, `:449,464` and `autopilot.md:4`, `:12-26`, `:28-35`, `:44-45`, `:46-47` sit above both reflowed ranges and were re-read with `sed -n` unchanged; `autopilot.md` is 100 lines again, as the `/crew:autopilot` section states. Nothing was executed for this note.

**Re-anchored `1da1233d` -> `08ed88a5` on 2026-09-28 (T-0087, crew 1.0.52).** `08ed88a5` is T-0087's crew 1.0.52 bump re-set after two fixes the spec's 2026-09-28 amendment brought into Touch: `88d35703` re-measured `plugin/crew/BUDGETS.md`'s line count, and `5aa1d9dc` made the sabotage entry "an edit to scope_guard.py runs no pytest rule" drop `scope_guard.py` from rule 31 as well as rule 27 (`_scope_guard_rule_span` in `plugin/crew/tests/sabotage_refresh.py` reads the span between the two from `.crew/verify.json`, since `apply_mutation` patches one unique span). `git diff --name-only 1da1233d 08ed88a5`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage_refresh.py`, `CHANGELOG.md` and the three version files, which read 1.0.52 on both sides. This note cites `sabotage_refresh.py` by name only; no line moved. Nothing was executed for this note.

**Re-anchored `08ed88a5` -> `0d331967` on 2026-09-28 (T-0087, crew 1.0.52).** `0d331967` adds `plugin/crew/BUDGETS.md` to `scripts/check-tooling-pr.py`'s `ALONGSIDE` (its line count moves with every crew doc edit, and the checker refused this branch's own re-measure) and the `harness+budgets` must-allow case to `scripts/_test/tooling-pr.py`, red first (7 passed, 1 failed), then 8 passed. `git diff --name-only 08ed88a5 0d331967`, refresh artifacts aside, returns those two scripts and `CHANGELOG.md`. `check` moved `:136` -> `:138` (two docstring lines), re-read with `grep -n`; `HARNESS` `:45` and `ALONGSIDE` `:70` are unchanged. Nothing was executed for this note beyond the suite named above.

**Re-anchored `0d331967` -> `c8cc69ec` on 2026-09-28 (T-0087, now crew 1.0.53).** Main moved: `c426c018` (T-0076, the crew suite on native Windows) landed as crew 1.0.52, so T-0087 merged it with a merge commit (no conflict) and re-bumped to 1.0.53 at `c8cc69ec`. `git diff --name-only 0d331967 c8cc69ec`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py` +4 at `:1086`, where `emit` now forces LF stdout; `plugin/crew/tests/crew_fixtures.py`, `review_fixtures.py`, `sabotage_context.py` and nine test files; `scripts/_test/uv-install.sh`; one `plugin/crew/README.md` table cell; its `CHANGELOG.md` entry), the README refund paragraph's version text, and the three version files. Every body `path:N` citation into those files was mapped by script (difflib over the two blobs) and every bare `:N` after one of their names was listed and read: none in the body moved (`crew_context.py` citations are all above `:1083`; the `CHANGELOG.md` ones that moved sit in provenance notes, which record their own anchors). The version sentence under Inventory and the T-0087 DERIVED bullet move to 1.0.53. Nothing was executed for this note.
## Re-anchor provenance - `9631c707` -> `22399a9c`, 2026-09-28 (T-0085)

`22399a9c` is T-0085's crew 1.0.52 version commit on `T-0085-build`, on top of `d02fe008`
(the change) and `2072352e` (the rebuilt guides), from origin/main `f54af3fa` (T-0072 landed
as 1.0.51). `git diff --name-only 9631c707 22399a9c` returns T-0072's landing refresh and
T-0085's files. Every body citation into a changed file was compared by script (the cited
line's text at `9631c707` against `22399a9c`); the ten that moved are corrected in place:
`review.md:449,464` -> `:452,467`, `plan.md:60` -> `:61`, `implement.md:36`/`:110` ->
`:34`/`:112`, `implement.md:89-111`/`:96` -> `:86-114`/`:93`, `review_prompt.py:84`/`:239` ->
`:91`/`:246`, `review_run.py:315`/`:317` -> `:328`/`:330`, and the inventory's skill count and
version (30, 1.0.52). The new "Development standards" section is read from source at
`22399a9c`. Citations inside the earlier provenance paragraphs are history and were not
moved. No suite was executed for this note.

The `.gitignore` un-ignore list (`:279-337`, four paths since T-0085's `!.crew/standards.md` at `:337`) was also re-read at `22399a9c`; the "Owns data" bullet is corrected in place.

**Re-anchored `22399a9c` -> `2aa49bb8` on 2026-09-28 (T-0085 merged onto main `c426c018`, crew 1.0.53).** `c49f3aca` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52) into `T-0085-build`, one mechanical conflict (the crew description's skills count in `.claude-plugin/marketplace.json`, kept at 30), and `2aa49bb8` bumped crew to 1.0.53. `git diff --name-only 22399a9c 2aa49bb8`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py`, four lines added inside `emit()` at `:1086-1089`; `plugin/crew/README.md`, one line in place; `scripts/_test/uv-install.sh`; eleven test files) and the version files. Every body citation into a changed file was compared by script at both commits; only the version moved (1.0.53, corrected in the inventory paragraph). No suite was executed for this note.

**Re-anchored `9631c707` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 9631c707 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). This note cites `CLAUDE.md` by section only, never by line, and cites no `TODO.md` line at or after `:4473` (`:3945`, `:3963` hold). No claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). This note cites `CLAUDE.md` by section only, never by line. No claim moved. Nothing was executed.

**Re-anchored `9631c707` -> `c99e31f6` on 2026-09-28 (T-0092, crew 1.0.52).** `c99e31f6` is T-0092's crew 1.0.52 version commit on `T-0092-build`, cut from main `f54af3fa` (T-0072's landing merge, whose only commit past `9631c707` is the refresh `f1f118de`). `git diff --name-only 9631c707 c99e31f6`, refresh artifacts aside, returns T-0092's files: `plugin/crew/hooks/scripts/review_patch.py` (+8: the docstring paragraph on `graphify-out/` and one comment line; `EXCLUDED` / `_EXCLUDE_SPEC` now at `:104-105`), `plugin/crew/hooks/scripts/review_prompt.py` (+4: one docstring line and the `excluded` line at `:89-91`, so `:84` -> `:85` and `:239` -> `:243`), `test_review_patch.py`, `test_review_prompt.py`, `sabotage_review.py`, line-neutral edits to `plugin/crew/README.md` (`:726`, `:860`), `plugin/crew/commands/review.md` (`:328-332` reflowed in place), `crew_autopilot.py` (`:55-56`), `completion_audit.py` (`:74-75`) and `TODO.md` (`:5048`), `CHANGELOG.md` (+26 at the top) and the three version files (1.0.52 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`). Every body citation of the form `path:line` into those files was compared by script between `9631c707` and `c99e31f6`. The only live citations that moved were `review_prompt.py:84` and `:239`, re-pointed to `:85` and `:243` and re-read; a DERIVED bullet for the exclusion (`review_patch.py:104-105`, `review_prompt.py:89`) is added beside the review-pipeline line, and the version sentence moves to 1.0.52. Every other differing citation is a version-file line changed in place or a `CHANGELOG.md` line inside a dated provenance note, which states that commit's line and is left as history. Only the T-0092 test files were executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1090` -> `:1094`), `plugin/crew/README.md` (`:1695` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1108`. The version sentence and the T-0092 DERIVED bullet move to 1.0.53. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:877` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:877` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. The version sentence and the T-0092 DERIVED bullet move to 1.0.54. Nothing was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1086` -> `:1090`), `plugin/crew/README.md` (`:1691` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1104`. The version sentence and the T-0092 DERIVED bullet move to 1.0.53. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:877` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:877` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. The version sentence and the T-0092 DERIVED bullet move to 1.0.54. Nothing was executed for this note.

## Re-anchor provenance - `938e3b11` + `136f4b33` -> `3648f59a`, 2026-09-28 (T-0075 review round 5, merge of `6387ab49`)

`9420bc16` merges origin/main `6387ab49` into `T-0075-build`: T-0076 (crew 1.0.52, `crew_context.py`'s byte-exact LF), T-0091 (`CLAUDE.md`'s Landmines paragraph, a `TODO.md` entry), T-0089 (crew 1.0.53, `test_role_write_guard.py` fixtures), T-0090 (mcp-servers 0.2.1, `SECURITY.md`) and T-0092 (crew 1.0.54: `review_patch.py` / `review_prompt.py` leave `graphify-out/` out of the review bundle), whose notes above are anchored `136f4b33`, `2442d367`, `c192b83d` or `b2553d26`. `faf4b0db`, `e7825a0e`, `04e3a01c`, `517628b9` and `d1460d77` are T-0075's review-round-5 steps 18-22 (`crew_config.py`, `crew_config_files.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `3648f59a` re-bumps crew to 1.0.55 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's conflicting provenance kept both sides, T-0075's `## Re-anchor provenance` sections first and main's `**Re-anchored ...**` paragraphs after them; the anchor line kept T-0075's and is replaced here.

The writers-and-menu section was re-derived from the source at `3648f59a`: `_shape`'s `under` kind (`crew_config.py:2639`), the two leaf rules in `value_allowed` (`:2708`) and `_content_problem` (`:2745-2748`), the open-table rule in `validate_providers`' one pin loop (`:223-237`), the writers' `OSError` boundary (`:2888`, `:3102`) and `Lock`'s PID-write cleanup (`crew_config_files.py:120-127`). `crew_config.py` moved +1 from `:204` (so `default_config` `:243`, `default_global_config` `:396`, `_RATCHETED` `:2451-2563` with its steps `:2466`, `:2479`, `:2490`, `:2500`, `:2536`, `:2559`, `:1263`, `:384`), then by the docstring trims and the new rules below `:2566` (`leaf_updates` `:2584`, `value_allowed` `:2700`, `plan_global_write` `:2846`, `write_global_config` `:2865`, `plan_repo_write` `:3045`, `write_repo_config` `:3071`), each re-taken with `grep -n`; `crew_config_files.py` +7 from `:120` (`update_json` `:350`). `test_crew_config.py:284` -> `:286`. The CHANGELOG "117 -> 119" citation gains `:928-929` at `3648f59a`. The version sentence moves to 1.0.55. Leaves re-executed: 123 / 68. `CONFIG_MENU_MUTATIONS` is 112 by `len()`. `wc -l crew_config.py` is 3399.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `938e3b11` for a line in T-0075's copy of this note and from `6387ab49` for a line only in main's, to the tree at `3648f59a` (difflib equal blocks); every citation that did not map to itself was read with `sed -n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `.crew/verify.json` range after a test-file mention, a `check-marketplace.py` range after a `PLUGINS.md` mention, a `SKILL.md` in another skill); those were read and hold. A citation inside a list of per-commit positions keeps its commit's line; only the current position is added. Nothing else was executed for this note.

## Re-anchor provenance - `50a275ea` + `81685adf` -> `360c4029`, 2026-09-28 (T-0010-solo merges T-0079's `e6e10432`)

`c312702b` merges origin/main `e6e10432` (T-0079 landed as crew 1.0.50, its code maps anchored
`81685adf`) into T-0010-solo `ac0b5151`; `360c4029` sets crew 1.0.51. The artifact conflicts were
anchor, version and provenance lines only: T-0010's side kept for anchors and body (its
`crew_autopilot.py` and `commands/autopilot.md` line numbers are this tree's), both sides'
provenance kept. `git diff --name-only 50a275ea 360c4029`, refresh artifacts aside, is T-0079's files
(`review_verdict.py`, `review_prompt.py`, `review_run.py`, `agents/reviewer.md`, their tests and
sabotage modules, identical to origin/main's), `plugin/crew/README.md` (two lines rewritten in
place, `:735` and `:739`, line-neutral), `CHANGELOG.md` and the version files. Every citation into
T-0079's files equals main's note at `81685adf` (compared by script). No test was run by this note.

## Re-anchor provenance - `360c4029` + `136f4b33` -> `d7c7c75c`, 2026-09-28 (T-0010-solo merges `6387ab49`)

`597a62b0` merges origin/main `6387ab49` into T-0010-solo `dbb22712`: T-0072 landed as crew
1.0.51, T-0076 as 1.0.52, T-0089 as 1.0.53 and T-0092 as 1.0.54, with T-0090 (mcp-servers 0.2.1)
and T-0091 (`CLAUDE.md`) beside them; main's code maps were anchored `136f4b33`. After it,
`bd066a97` moves `settings`' two policies to a second text line (T-0072's
`test_settings_line_names_deploy` pins the first line exactly), `ab85fed0` puts `deploy-allowed`
in T-0010's only-writer test, `250c6df7` rewraps one docstring line in place, `130bf67e` re-sets
crew 1.0.55 and `d7c7c75c` re-prices `.crew/verify.json` rule 29 in place (20 -> 21). The merge
took main's side of this note; it was then re-merged three-way from `e6e10432`, T-0010's side at
`dbb22712` (anchor `360c4029`) and main's at `6387ab49`, both sides' provenance kept, main's
first. Every body `path:line` citation into a file changed since its side's commit was mapped to
`d7c7c75c` with `difflib` (a bare `:N` taken as the last file named earlier in its paragraph);
a citation followed by `at <sha>`, `before` or `->`, and every provenance section, was left as
written. A citation inside a changed hunk cannot be mapped that way and was left as written unless
this section names it.

The conflicting hunks were resolved by hand and re-read at `d7c7c75c` with `grep -n` per
symbol: the version line (1.0.55), the leaf table and paragraph (re-executed: 125 / 68 / 57 / 0;
`plugin/crew/tests/test_crew_config.py:284` asserts 125; T-0004's "117 -> 119" is
`CHANGELOG.md:1622-1623`), the `crew.json` warning (`:911-915`), the whole `/crew:autopilot`
section (T-0072's `deploy-allowed`, `_settings_at` and `DEPLOY_VALUES` merged into T-0010's
text; every `crew_autopilot.py` and `commands/autopilot.md` citation in it re-read), the
`deploy_allowed` paragraph, the `.crew/verify.json` rules sentence (rules 28-32), and the
entry-point and owns-data bullets. No test was run by this note; the suites ran with the build.

## Re-anchor provenance - `d7c7c75c` + `3648f59a` -> `cd106b8b`, 2026-09-28 (T-0010-solo merges T-0075's `e878cc31`)

`acbb0fb2` merges origin/main `e878cc31` into T-0010-solo `07032fc7`: T-0075 (`/crew:config` menu mode and
`/crew:config-setup`) landed as crew 1.0.59, its code maps anchored `3648f59a`. `92e0717a` re-measures
`plugin/crew/BUDGETS.md` (19,494 lines across 128 files) and rebuilds the troubleshooting guide's DOCX and
PDF; `cd106b8b` re-sets crew 1.0.60, one past main. The code merged without a conflict (T-0010 and T-0075 change
disjoint scripts); the conflicts were this note's anchor, provenance and a few cited lines. Both sides'
provenance was kept, main's first. Every body `path:N` citation was traced to the side whose copy of this
note carries its line (`07032fc7` or `e878cc31`) and mapped to `cd106b8b` through a `difflib` line diff
(`/root/crew-tmp/t-0010/citemap.py`, machine-local); each line that did not map to itself was read with
`sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were
that misattribution (a `crew_ticket.py` or `review_ledger.py` line after another file's mention) and hold.

Resolved by hand and re-read at `cd106b8b`: the version sentence (1.0.60; `.claude-plugin/marketplace.json:217`
keeps T-0075's 36 slash commands), the leaf table and paragraph (re-executed: 125 / 68 / 57 / 0;
`plugin/crew/tests/test_crew_config.py:288` asserts 125; T-0004's "117 -> 119" is `CHANGELOG.md:1746`),
`AUTOPILOT_DEFAULTS` (`crew_state.py:1094-1095`, deep-copied at `crew_config.py:384`), the autopilot and
policy rule sentences (`.crew/verify.json` `:298-306`, `:307-313`, tracker `:314-321`, route `:322-330`,
approval `:332-339`; `POLICY_MUTATIONS` 55 by `len()`, appended at `plugin/crew/tests/sabotage.py:3061`),
and `evaluate_triggers` (`crew_state.py:2906`) with `default_config` / `default_global_config`
(`crew_config.py:243` / `:396`). Nothing else was executed for this note.

## Re-anchor provenance - `cd106b8b` -> `bbd9a66d`, 2026-09-29 (T-0010 landing branch)

`T-0010-land` merges T-0010-solo `6b89c1df` into origin/main `2693d0fa` (README re-pin only past `e878cc31`,
so the merged tree is `6b89c1df` plus that README change). `08eeaa3e` adds the ruff fix-at-land lint fixes
(owner standing rule 2026-09-28; owner decision 2026-09-29 "Fix at land"): ISC004 parentheses in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_scope_guard.py`; `# noqa: BLE001` on five fail-closed broad excepts in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_ticket.py` and
`plugin/crew/hooks/scripts/scope_guard.py`; an I001/RUF100/C0207 fix in
`plugin/crew/tests/test_crew_autopilot_policy.py`. `bbd9a66d` re-sets crew 1.0.61. Each edited line kept its
number (the parentheses and comments were added in place) except in `test_crew_autopilot_policy.py`, whose
import block lost one line; no note cites that file by line. Re-anchor only; nothing was executed for this note.

**Re-anchored `c8cc69ec` -> `c0768d0e` on 2026-09-28 (T-0087, crew 1.0.53).** `c0768d0e` is T-0087's merge of main `f8b6c8d7` (T-0091, no plugin version change) into `T-0087-build`; crew stays 1.0.53, one past main's 1.0.52, and `c8cc69ec` is still the last `plugin/crew` commit. `git diff --name-only c8cc69ec c0768d0e`, refresh artifacts aside, returns `CLAUDE.md` (T-0091's Landmines truncating-`open` measurement paragraph, +35/-18 at `:189`, so every later line moves +17) and `TODO.md`. Every other body `CLAUDE.md:N` citation here is at or above `:189`, or sits inside a dated re-anchor note that states the coordinates of its own commit, so none moved. Nothing was executed for this note.

**Re-anchored `136f4b33` / `c0768d0e` -> `379ab5e6` on 2026-09-28 (T-0087 merged onto `6387ab49`, crew 1.0.55).** `01dd3854` merges origin/main `6387ab49` into `T-0087-build`: T-0089 (crew 1.0.53, `plugin/crew/tests/test_role_write_guard.py`), T-0090 (mcp-servers 0.2.1: `SECURITY.md`, ten files under `mcp-servers/`) and T-0092 (crew 1.0.54: `graphify-out/` left out of review bundles - `review_patch.py`, `review_prompt.py`, `completion_audit.py`'s comment, `crew_autopilot.py`'s docstring, `commands/review.md`, `plugin/crew/README.md`, `TODO.md`, three test files). `379ab5e6` re-bumps crew to 1.0.55, one past main's 1.0.54, and moves T-0087's `1.0.53` mentions (`plugin/crew/README.md:758`, its `CHANGELOG.md` entry) to 1.0.55 in place. The code-map, INDEX, diagram, rules and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the version sentence, `.claude/rules/` and `graphify-out/` taken from main and then refreshed. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from the anchor of the side `git blame` puts the note line on, both anchors for a line common to both, never guessed): seven moved, all in the review-seam bullets - `review_prompt.py` `:89` -> `:90` (T-0092's `excluded` line), `:85` -> `:86`, `:236` -> `:240` and `:156` -> `:160`, and `review_patch.py` `:111`/`:115`/`:116` -> `:119`/`:123`/`:124` (T-0092's docstring paragraph above `MANIFEST_KEYS`); T-0092's `review_patch.py:104`/`:105` hold. Citations the script could not map, or where the two sides' anchors disagree on a line common to both, were not re-read here and are unchanged; they predate this merge (for example `CHANGELOG.md`'s "117 -> 119" is cited at `:653-654` on both sides and sits at `:891-892`), and this pass only re-anchors.

**Re-anchored `379ab5e6` -> `17fa035e` on 2026-09-28 (T-0087 review round 1, crew 1.0.55 unchanged - not yet released).** `bbe68e85` fixes review round 1: autopilot lets a refunded round's `/crew:review` rerun past its no-progress stop, rule 31 triggers on its suites and seam consumers, `scripts/check-tooling-pr.py` admits no production code or prompt alongside the harness (a `SEAM` consumer only with a `Tooling-seam:` trailer), `golden_build.redact` bounds both sides of a match, a malformed `successors` loads as corrupt, `review_run.py`'s summary line counts charged rounds, a worktree rename is parsed, and the guides stop calling a post-refund rerun free; `17fa035e` re-prices rule 31. `git diff --name-only 379ab5e6 17fa035e`, refresh artifacts aside, returns those scripts, their tests, one golden fixture, `.crew/verify.json`, `CLAUDE.md`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `commands/autopilot.md`, `commands/review.md` and the troubleshooting guide. Body citations of the form `path:line` into those files were re-mapped by script (difflib over each cited file from `379ab5e6` to `bbe68e85`, only for note lines committed before this pass, never guessed): 32 moved - `crew_autopilot.py` citations past `:478` (+2 to `_toward_review`, +6 from `next_phase`'s body on), `review_run.py` `:380`/`:383` -> `:385`/`:388` and `review_ledger.py` `:219`/`:227`/`:233`/`:499`/`:502` +5 (the `successors` shape check in `_load`). Corrected by hand: seven `crew_autopilot.py` citations the script attributed to another path on the same line (`:657`, `:818`, `:893`, `:922`, `:967`, `:976`, `:992`, each +6, content-preserving - several already pointed off their named function before this pass and still do), the file's line count (1338), and `CHANGELOG.md`'s "117 -> 119" (`:912-913`; the six older "at <sha>" figures on that line are history and were put back as written after the script moved them). The T-0087 bullets were rewritten for the checker's `SEAM`/`judge` shape and the rerun. Everything else here is unchanged and was not re-read.

## Re-anchor provenance - `bbd9a66d` + `17fa035e` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`0fc7f609` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored
`bbd9a66d`) into `T-0087-build` `674bc4e5` (T-0087's Windows-portability successor plan, Steps 1-5
built; its maps anchored `17fa035e`). After it, `ae448309` renames T-0087's harness rule to rule 32
in text and re-measures `plugin/crew/BUDGETS.md` (19,666 lines across 129 files), `167f69a0` says
the refund ships in 1.0.62 (README, CHANGELOG), `e537e4ce` re-sets crew 1.0.62, one past main, and
`9e38a891` rebuilds the daily-workflow and troubleshooting guides from their merged sources. The code
conflicts were `crew_autopilot.next_phase` (main's `policy` argument plus T-0087's refunded-rerun
pop), `sabotage.py`'s `MUTATIONS +=` line and `test_crew_autopilot.py` (both sides kept) and the
README's Stops line (main's text plus T-0087's refunded-review clause). The artifact conflicts took
main's side for body text and kept both sides' provenance, main's first. Every body `path:N`
citation was traced to the side whose copy of this note carries its line (`674bc4e5` or
`8ab733d7`) and mapped to this tree with a `difflib` line diff (`/root/crew-tmp/t-0010/citemap.py`
and `/root/crew-tmp/t-0087/citeapply.py`, machine-local). The script takes a bare `:N` as the last
path on its line; each misattribution it produced (a `crew_autopilot.py` line after a
`review_ledger.py` or `commands/autopilot.md` mention, a `.crew/verify.json` range after a
`sabotage.py` one, a historical `at <sha>` README line) was reverted or re-read by symbol with
`grep -n`. `crew_autopilot.py` is 1751 lines: T-0087's refund hunks add 16 lines from `:522`, so
main's citations at or past `:522` moved by 6 to 16 (`next_phase` `:556`, `settings` `:745`,
`deploy_allowed` `:943`, `main` `:1648`) and nothing above it moved. T-0087's `sabotage_tooling`
import at `plugin/crew/tests/sabotage.py:81` puts the `MUTATIONS +=` statement at `:3054-3057`
(refresh `:3054`; resume, autopilot, tracker and route `:3055`; policy, approval, config and tooling
`:3056`). `.crew/verify.json` is 33 rules and 370 lines: T-0087's harness rule is rule 32 at
`:340-365`, after T-0024's rule 31 at `:332-339`. Nothing was executed for this note; the suites ran
with the build.

In this note: the version sentence (1.0.62), the `/crew:autopilot` section, the policy and
`deploy_allowed` paragraphs and the entry-point bullet were re-read by symbol on this tree; six
citations main's side already carried stale (`questions_check`, `QUESTIONS_SHAPE`, the two hints,
`main`, `_policy_main`, the approve stop) were set to this tree's lines while there.

## Re-anchor provenance - `9e38a891` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): 138 moved in this map and were set to this tree's lines. Five could not be mapped because main rewrote the cited line and were re-read by symbol: `crew_config.py:1264` (`repo_config_file`), `crew_autopilot.py:803-807` and `_settings_at` `:777`, `crew_route.py:322-325`, and `sabotage.py:3058` (the `MUTATIONS +=` line carrying `POLICY_MUTATIONS`); three bare citations the script bound to the file named just before them were read in `crew_refresh_check.py` instead (`_named_behind` `:538`, `_unconfirmed` `:555`, `ticket_freshness` `:577`). The version sentence (1.0.70), the skills row and the description's count (30 since crew 1.0.66 added `crew-qa-standards`) and the verify.json rule line (main's rules 32-34 at `:340-360`, T-0087's at `:361-386`) were updated to this tree. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.
**Re-anchored `2aa49bb8` -> `b82035e6` on 2026-09-28 (T-0085 merges main `f8b6c8d7`, T-0091).** `17b70570` merged origin/main `f8b6c8d7` into `T-0085-build` (mechanical conflicts only: anchors, provenance paragraphs, INDEX history cells, generated rules and graph); `b82035e6` moves the crew skills claim at `plugin/README.md:414` and `INSTALLATION.md:252` from 29 to 30 (spec Touch amendment). Of the paths this note cites, `git diff --name-only 2aa49bb8 b82035e6` returns `CLAUDE.md`, `INSTALLATION.md` and `plugin/README.md`. `CLAUDE.md`'s change is T-0091's Landmines truncating-`open` paragraph, whose citations were moved on main's side and merged in, plus T-0085's four-line ignore-policy reflow, which shifts no line. Every `CLAUDE.md:N`, `INSTALLATION.md:N` and `plugin/README.md:N` citation was compared by script against its text at `2aa49bb8`, `c192b83d` and HEAD; none needed moving: every `CLAUDE.md:N` citation here reads the same text at HEAD as at main's `c192b83d`, where T-0091 already moved them. No suite was executed for this note.

**Re-anchored `136f4b33` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree: two moved - the checklist call `review_prompt.py:260` -> `:264` and `_bundle_block`'s excluded line `:89` -> `:96`; the READ-line citations `:92` and `:250` were set at the merge; the version sentence now reads 1.0.55. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:530` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: the T-0085 section's `crew_standards.py` line numbers moved; that file was re-read in full at `07bcaf3b` and the section rewritten in place, with the round-1 behaviour (the `lstat`-proven absent receipt, the always-on checklist fallback, the single-read stamp, the `std:` note, the plugin-set `REPO` refusal, fourteen mutations). `plugin/crew/commands/implement.md:86-114` still spans step 6, and the `review.md` citations here (`:449`, `:452`) sit above the +2 shift. Every other hit is a `CHANGELOG.md` or `BUDGETS.md` citation inside an earlier dated provenance paragraph, left as history. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line); the one body claim naming the version (the counts section's `:218` sentence) now reads 1.0.56. The `CHANGELOG.md` hits sit inside earlier dated provenance paragraphs, left as history. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. Four moved, all by T-0075's landing commits after `3648f59a` rather than by T-0085: `plugin/crew/hooks/scripts/crew_config.py:3057` / `:3071` -> `:3046` / `:3072`, `plugin/crew/hooks/scripts/crew_config_files.py:350` -> `:364`, `plugin/crew/hooks/scripts/crew_config_menu.py:1048` -> `:1051`. The counts section now reads 36 commands and 30 skills, and its version sentence 1.0.59 with the build branch's no-bump note. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; the only citations that moved are `CHANGELOG.md:N` ones inside earlier dated provenance sections, left as history. The "Development standards and the pre-review self-check (T-0085)" section was re-derived from the committed `crew_standards.py` (`grep -n '^def '`), its `_scope` claim rewritten for the fallback and its mutation count set to thirty-three. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` -> `61ecbf3c` on 2026-09-29 (T-0085, pylint E1136 in two tests).** `61ecbf3c` changes only `plugin/crew/tests/test_crew_standards.py` and `test_review_run_standards.py` (two stamp reads become None-safe), which this note cites by name only. No citation moved. No suite was executed for this note.

**Re-anchored `61ecbf3c` / `bbd9a66d` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61).** `a7f9c5e4` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61) into `T-0085-build` after T-0085's review round 3 fixes (`33521aa4`), with mechanical conflicts only: crew version lines take main's 1.0.61 with T-0085's 30 skills (the build branch carries no bump, REPO-03 as amended), `plugin/crew/tests/sabotage.py` registers `POLICY_MUTATIONS`, `APPROVAL_MUTATIONS`, `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS` on `:3056`, anchors, provenance (both sides kept, main's first), INDEX history cells, version sentences, diagram headers, generated rules and graph. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`33521aa4` or `8ab733d7`) and mapped from that side's anchor to `a7f9c5e4` through a difflib line diff (`/root/crew-tmp/t-0085/citemap.py`, machine-local; only cited files that changed; a bare file name resolved when unique in `git ls-files`); each citation that did not map to itself was read with `sed -n` / `grep -n`, and the script's misattributed bare `:N` (a `sabotage_autopilot.py` or `crew_ticket.py` line after another file's name, a history list's earlier positions) were read and hold. Moved: `sabotage.py`'s config-menu and policy registrations `:3055` -> `:3056`; the routing section's rule list gains T-0085's standards rule 33 (`:340-352`) as the last. The "Development standards and the pre-review self-check (T-0085)" section was re-derived for review round 3 from the merged tree (`grep -n '^def '` and the `33521aa4` hunks read in full): `_scope_entry` (`:437`) replaces `_has_scope_entry` and refuses an unreadable `.crew/.scope-base` without naming `--record`, a `record-fallback` start is marked, `proposals` refuses an INCOMPLETE out.txt, `_std_side` (`:749`) keeps `std:none` and unreadable tokens on neither side, `review_run.run` answers a spent budget before the gate (`:425`, reserve `:429`), and `STANDARDS_MUTATIONS` (`:45`) holds forty-two. The counts sentence reads 36 commands and 30 skills and the version 1.0.61, with the build branch's no-bump note. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. In this note: 222 citations moved mechanically (most by main's T-0088 and #263-#266 edits to `crew_config.py`, `crew_state.py`, `crew_autopilot.py`, `crew_context.py`, `cloud_guard.py`, `crew_route.py` and the scope/event scripts); the counts table and the marketplace line now read 31 skills and 1.0.70; the `sabotage.py` registration lines read `:3058` (`CONFIG_MENU`/`POLICY`/`APPROVAL`) and `:3061` (`STANDARDS`); `crew_config.py:1264` now reads the config through `crew_common.repo_config_file` (T-0088); the T-0085 Gate paragraph is rewritten for the landing order - main's `preflight` first, then `standards_gate` - and the mutation count is forty-three. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

**Re-anchored `7c86bd13` (`obsidian-vault`: `69c7edbd`) -> `c04dd2ef` on 2026-09-30 (T-0085 landing: `commands/review.md` rewrapped to its 551-line allowance, crew 1.0.71 then 1.0.72).** `git diff --name-only 7c86bd13 c04dd2ef`, refresh artifacts aside, returns the crew version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md` (20,707 lines, in place) and `plugin/crew/commands/review.md`: step 3's item 3 gains its last line on `:511`, item 4 and its `gh pr comment` paragraph and steps 8-9 are rewrapped at 100 columns, and the closing sentence is joined, taking the file from 557 to 551 lines with no text changed. Every line this note cites in `review.md` is at or above `:511` and holds; the version this note states now reads 1.0.72. No suite was executed for this note.

**Re-anchored `c04dd2ef` -> `8a89a596` on 2026-09-30 (T-0085 landing: catch-up merge of main `6813749b`, #268 T-0097, crew 1.0.70; T-0085 now 1.0.73).** `git diff --name-only 54192270 8a89a596` returns the crew version files, `CHANGELOG.md` (T-0097's entry below T-0085's), the 11 `.ps1` hook carriers (one `Resolve-CrewPython` line each: an empty probe answer is no longer piped into `ConvertFrom-Json`), `plugin/crew/tests/sabotage_scope.py` and `plugin/crew/tests/test_ps1_python_probe.py`. Citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 11 moved, 0 unmapped); version-line citations (`marketplace.json:218`, `plugin.json:3`, `PLUGINS.md:14`) hold by line and now read 1.0.73. The `Resolve-CrewPython` copies stay byte-identical across all 11 carriers, so the copy-list claims hold. No suite was executed for this note.

**Re-anchored `8a89a596` -> `9b6b0da7` on 2026-09-30 (T-0085 landing: Windows fail-open fix, crew 1.0.74).** `git diff --name-only 58431f49 9b6b0da7` returns the crew version files, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_standards.py` (`import stat`, new `_ancestor_problem` before `gate_applies`, which now proves a receipt absent only when the nearest existing ancestor is a directory), `plugin/crew/tests/test_crew_standards.py` (new `test_gate_applies_when_a_file_parent_is_reported_as_not_found`) and `plugin/crew/tests/sabotage_standards.py` (one entry). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 10 moved, 0 unmapped); `crew.md`'s bare `crew_standards.py` citations in its standards section were moved by the same diff (27). No suite was executed for this note.

**Re-anchored `9b6b0da7` -> `5c9a9db2` on 2026-09-30 (T-0085 landing: sabotage entry re-targeted, crew 1.0.75).** `git diff --name-only 33da9c91 5c9a9db2` returns the crew version files, `CHANGELOG.md` and `plugin/crew/tests/sabotage_standards.py` (the "receipt that cannot be looked up" entry now flips `gate_applies`' `OSError` verdict). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 9 moved, 0 unmapped). No suite was executed for this note.

## Re-anchor provenance - `b142d8e3` / main `5c9a9db2`-`37f4e807` -> `2697bf67`, 2026-09-30 (T-0087 review round 5 successor, merge of main `9af34e57`)

`4e97588e` (golden leak check) and `2de03e41` (review ledger successors path) fix review round 5; `7b62e321` adds their sabotage entries. `7ccff1db` merges origin/main `9af34e57` (T-0085 landed as crew 1.0.75, with #268, #276, #277, #279) into `T-0087-build` with a merge commit, and `2697bf67` re-sets crew 1.0.76. The merge's map conflicts were mechanical: a hunk that differed only in numbers or in the anchor took main's side, and a provenance hunk kept both. Every body citation of the form `path:line` was then re-mapped by script (difflib from the parent the line came from - T-0087's `7b62e321` for a line T-0087 carries, main's `9af34e57` otherwise - to this tree; a bare `:N` binds to the last path named on its line). `.crew/verify.json` now holds T-0085's standards rule as rule 35 (`:361-373`) and T-0087's harness rule as rule 36 (`:374-399`); those descriptions were re-read by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `2697bf67` -> `45f32c3c`, 2026-09-30 (T-0087, after merging main `9af34e57`)

`5f52ba61` re-maps `plugin/crew/docs/external-tool-formats.md`'s `review_run.py` and `review.md` citations to the merged tree (in place; no line moved), and `2b7e7a05`/`45f32c3c` step crew back and re-set 1.0.76 as the last `plugin/crew` commit. No citation in this note points into a line that moved. Re-anchor only: no claim moved and nothing was executed for this note.

## Re-anchor provenance - `45f32c3c` -> `7c88bf3d`, 2026-09-30 (T-0087 review round 6 fix)

`cff30f72` makes the committed-corpus test in `plugin/crew/tests/test_review_golden.py` run `golden_build.leak` on every fixture (host name included), adds `test_corpus_leak_check_refuses_a_planted_host_name`, and adds sabotage entries (ah)-(ai) to `plugin/crew/tests/sabotage_tooling.py`; its CHANGELOG bullet moved later CHANGELOG lines by 4, and the CHANGELOG citations above were re-mapped by script (difflib `45f32c3c` -> `7c88bf3d`). `49ed9a29` / `7c88bf3d` step crew back and re-set 1.0.76. No other cited line moved. Re-anchor only: nothing was executed for this note.

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history; the body's test list (`STANDARDS_MUTATIONS` line and count) was set to `:57` and forty-nine. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `3648f59a` -> `ea764992`, 2026-09-29 (T-0094)

T-0094 is built on origin/main `2693d0fa`, which is `3648f59a` plus T-0075's landing branch (`bf51a807`..`93da92af`: crew 1.0.56-1.0.59, `crew_config_files.os_error_text`, the `test_config_menu.py` pylint disable, the refused-snapshot probe, two sabotage entries), its graph refresh and rules regeneration, and the README re-pin `17d057db`. T-0094's own commits `be023596`..`ea764992` add `artifact_verdicts` to `crew_refresh_check.py`, route `completion_audit.audit` through it, reword `scope_guard.py`'s rule 6, add `test_refresh_admission.py` and `refresh_fixtures.py`, rewrite the approval-gate and must-allow cases of `test_completion_audit_refresh_artifacts.py`, append fifteen `sabotage_refresh.py` entries, grow `.crew/verify.json` rule 25 by three paths (every later rule moves down three lines), and change `README.md`, `implement.md` step 6, `done.md` check 3, the daily-workflow guide, `CHANGELOG.md` and the version files (crew 1.0.60). Corrected 2026-09-29 (T-0094 review round 2, NIT): fifteen was true at `ea764992`; review round 1 then moved one of them, spec entry (m) "the audit does not print why", below its own `# T-0094 review round 1` marker (fourteen and seventeen at `62744965`), and round 2 moved it back, byte-identical: fifteen after `# T-0094`, sixteen after round 1's marker and nine after round 2's, counted by `ast`.

Re-derived here: the artifact refresh check section (`REFRESH_ARTIFACT_PATHS`, the guard/audit split and the per-kind admission, the tests and rule 25), its bare `crew_refresh_check.py` positions (`:228`, `:197-199`, `:856`, `:873`, `:895`, `:995`), `/crew:done`'s check 4 (`:50-61`, `:56-59`), step 6 (`:89-113`), the version sentence, the `CHANGELOG.md` position of T-0004's "117 -> 119", the shifted verify rules 26-30, and the T-0075-landing moves in `crew_config.py` (`:3046`, `:3072`), `crew_config_files.py` (`:104`, `:364`) and `crew_config_menu.py` (`:1051`), which T-0075's landing did not re-anchor.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `3648f59a` to the working tree at `ea764992` (difflib equal blocks), then reading each citation that did not map to itself with `sed -n` / `grep -n`. Version-file lines changed in place (`plugin.json:3`, `marketplace.json:218`). A citation inside a list of per-commit positions keeps its commit's line; only the current position is added. The new sentences were read from the source at `ea764992`; the suites were run by the ticket (`test_refresh_admission.py` 32 passed), not by this note.

## Re-anchor provenance - `ea764992` -> `50061215`, 2026-09-29 (T-0094 lint)

`50061215` is T-0094's lint commit: `scope_guard.py`'s rule-6 docstring rewrapped (one line longer, pylint C0301), the two could-not-tell `except Exception` lines in `crew_refresh_check.py` marked `noqa: BLE001` in place, one `sabotage_refresh.py` replace string parenthesised in place (ISC004), and `test_refresh_admission.py`'s imports sorted (I001). `_refresh_artifact` moves `scope_guard.py:191-202` -> `:192-203`, re-derived above; no other body citation moved. Checked by the same citation-mapping script, `ea764992` -> `50061215`. Nothing else was executed for this note.

## Re-anchor provenance - `50061215` -> `f79e9f58`, 2026-09-29 (T-0094 review round 1)

`f79e9f58` is the last of T-0094's review-round-1 fix commits (`abe87bc2`..`f79e9f58`): `crew_refresh_check.py` gains `ADMISSION_BOOKKEEPING` and `_in_admission_reach`, reads a map's reach from its base copy only, splits `_sha_moved` into it and `_moved_from` (three-valued base anchor, forward-only), judges INDEX.md's deleted lines, and narrows the RELEASE_BOOKKEEPING comment in place; `completion_audit.py`'s `_outside_refresh_artifacts` now computes the verdicts itself, after the approval gate, and `_verdicts` fails closed on a raise; the refresh suites, `refresh_fixtures.py` and `sabotage_refresh.py` grow; `.crew/verify.json` rule 25 is re-priced in place (`:285`, `:288`); `README.md`, `implement.md` and `daily-workflow-scope.md` are reworded in place. Re-derived here: the artifact refresh check section (`REFRESH_ARTIFACT_PATHS` `:218-223`, the audit's gate and admission bullet with every `crew_refresh_check.py` and `completion_audit.py` position in it, `RELEASE_BOOKKEEPING` `:233`, the status constants `:202-204`, `_named_behind` `:911`, `_unconfirmed` `:928`, `ticket_freshness` `:950`, `main()` `:1050`, `artifact_verdicts` `:682`). Checked by script (every `path:N`, and every `:N` in a paragraph naming a changed file, compared line by line between `50061215` and `f79e9f58`), then each hit read; hits inside earlier provenance sections are history and left as written. Nothing was executed for this note beyond that script.

## Re-anchor provenance - `bbd9a66d` + `f79e9f58` -> `6375524b`, 2026-09-29 (T-0094 merges `8ab733d7`; review round 2's successor)

`f050cd47` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored `bbd9a66d`) into T-0094-build at `ca5b1f35` (T-0094's side anchored `f79e9f58`, plus review round 2's FIX 1 `da1532d6` and FIX 2 `ca5b1f35`). The artifact conflicts were anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first; INDEX history columns joined; body hunks resolved to main's lines except T-0094's own refresh-admission paragraph and refresh-check entry point. After it, `157237c2` splits `.crew/verify.json` rule 25 (the admission suite is rule 32 at `:342-349`, rule 25 `:269-287`, every later rule moves by the merged and split lengths), restates the sabotage counts in `plugin/crew/tests/sabotage_refresh.py`, and edits `plugin/crew/README.md` and `docs/guides/crew/src/daily-workflow-scope.md` in place; `ef5b4c89` re-measures `plugin/crew/BUDGETS.md` (19,500 lines across 128 files); `fc348c89` sets crew 1.0.62; `6375524b` rebuilds the daily-workflow guide. `git diff --name-only bbd9a66d 6375524b`, refresh artifacts aside, is T-0094's files only: `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, the daily-workflow guide and its source, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `commands/done.md`, `commands/implement.md`, `completion_audit.py`, `crew_refresh_check.py`, `scope_guard.py` and T-0094's five test files. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`8ab733d7` or `ca5b1f35`) and mapped to HEAD with a `difflib` line diff (`/root/crew-tmp/t-0094/cite_map_merge.py`, machine-local); each that did not map to itself was read with `sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were that misattribution and hold; a history position ("before", "at <sha>", "since ...") was left as written. Re-derived here: `scope_guard.py`'s T-0010 citations (`:124-128`, `:243`, `:263`, `:271`, `:287`, `:132-133`, the merged file carrying T-0094's rule-6 docstring) and the refresh allowance (`:215-226`); `crew_refresh_check.py`'s positions after FIX 1's six lines (`artifact_verdicts` `:688`, the reach `:706-715`, `_rendered_verdict` `:745`, `ticket_freshness` `:956`, `main` `:1056`) and the unreadable-rule branch (`:652-654`); the round-2 tests; the verify rules 26-32 (rule 30 is T-0023's routing rule and 31 T-0024's, corrected in place with a `Corrected` clause); T-0004's "117 -> 119" at `CHANGELOG.md:1642` (review round 2 NIT 6); the version sentence (1.0.62). No test was run by this note.

## Re-anchor provenance - `6375524b` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only 6375524b f5d0f1b1 -- <the 105 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `.crew/codemap/INDEX.md`, `.crew/verify.json`, `CHANGELOG.md`, `CLAUDE.md`, `INSTALLATION.md`, `README.md`, `docs/diagrams/process-crew-lifecycle.mmd`, `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/cloud_guard.py`, `plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_context.py`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/crew_resume.py`, `plugin/crew/hooks/scripts/crew_route.py`, `plugin/crew/hooks/scripts/crew_state.py`, `plugin/crew/hooks/scripts/crew_status.py`, `plugin/crew/hooks/scripts/crew_ticket.py`, `plugin/crew/hooks/scripts/crew_tracker.py`, `plugin/crew/hooks/scripts/review_run.py`, `plugin/crew/hooks/scripts/role_write_guard.py`, `plugin/crew/skills/crew-setup/phases.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_autopilot.py`, `plugin/crew/tests/sabotage_resume.py`, `plugin/crew/tests/test_context_watch_python_resolver.py`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. Re-derived here: the counts table (skills 29 -> 30, `crew-qa-standards`) and the `marketplace.json:217`/`:218` version sentence (1.0.70); `crew_config.py:1264` now reads `.crew/config.json` through `crew_common.repo_config_file` (T-0088); rule 32 is no longer the last rule (rules 33-35 follow, `.crew/verify.json:393-416`); `sabotage.py`'s `MUTATIONS +=` line `:3057`; `_settings_at` `:761` and the autopilot/route `crew.json` warnings (`crew_autopilot.py:787-791`, `crew_route.py:322-325`); the tracker section's positions (`crew_tracker.py`, +2 near the top); the README's "since 1.0.70". Not described by this note (main's, not T-0094's): `review_limit.py` and the Codex-limit fallback, `review_gate.py`, `crew_common.repo_config_dir`'s linked-worktree fallback beyond the one line above, and `crew-qa-standards`' `qa_audit.py`.

**Re-anchored `f5d0f1b1` -> `2255fb4d` on 2026-09-30 (T-0094 review round 3).** `2255fb4d` is T-0094's review-round-3 fix commit (Codex round 3 on `e0ccd3f7`: 0 BLOCK / 4 FIX). `git diff --name-only f5d0f1b1 2255fb4d` returns `.crew/codemap/crew.md`, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/sabotage_refresh.py` and `plugin/crew/tests/test_refresh_admission.py`; the two commits after `f5d0f1b1` before it are refresh artifacts only. Re-derived here: the refresh-artifact bullet (`REFRESH_ARTIFACT_PATHS` `:223-228`, `artifact_verdicts` `:766`, the reach `:784-793`, `_map_verdict` `:615`, `_sha_moved` `:522`, `_moved_from` `:552`, `_diff_lines` `:629`, `_index_verdict` `:652`, `_diagram_verdict` `:675`, `_rule_verdict` `:694` and its unreadable branch `:701-703`, `_stored_blob` `:739`, `_rendered_verdict` `:823`, `COULD_NOT_TELL` `:459`; `ADMISSION_BOOKKEEPING` is `:251`, where this note had said `:246` since before the merge), the entry-point line (`ticket_freshness` `:1034`, `main` `:1134`), the tests bullet (round 3's cases), and the counts table and version sentence (30 skills, 1.0.70: review round 3's FIX 4; the previous pass's provenance said both were re-derived and neither was). Each position read with `grep -n` at `2255fb4d`. No other body citation names a changed file by line.

**Re-anchored `2255fb4d` -> `0c19512c` on 2026-09-30 (T-0094 crew 1.0.71).** `0c19512c` sets crew 1.0.71 (review round 3's fixes changed `plugin/crew/` after 1.0.70 was set, and origin/main is 1.0.70 too, T-0097 #268). Per-path: `git diff --name-only 2255fb4d 0c19512c` over this note's cited paths returns only `plugin/crew/README.md` (two in-place "since 1.0.70" -> "since 1.0.71" edits, line count unchanged), beside the version files and `CHANGELOG.md` (release bookkeeping). Re-derived here: the version sentence (1.0.71, `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`) and the refresh-artifact bullet's "since" version. No body citation moved.

**Re-anchored `0c19512c` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 111 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/completion_audit.py`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/tests/refresh_fixtures.py`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/test_completion_audit_refresh_artifacts.py`, `plugin/crew/tests/test_refresh_admission.py`, `plugin/crew/tests/test_refresh_check.py`; from T-0094's side, `0c19512c..1b9e4bfe` adds `.crew/standards.md`, `plugin/README.md`, `plugin/crew/commands/fix.md`, `plugin/crew/commands/plan.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/approval-hook.ps1`, `plugin/crew/hooks/scripts/cloud-guard.ps1`, `plugin/crew/hooks/scripts/completion-audit.ps1`, `plugin/crew/hooks/scripts/crew-context.ps1`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/handoff-read.ps1`, `plugin/crew/hooks/scripts/handoff-write.ps1`, `plugin/crew/hooks/scripts/notify.ps1`, `plugin/crew/hooks/scripts/platform-sync.ps1`, `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/hooks/scripts/review_run.py`, `plugin/crew/hooks/scripts/role-write-guard.ps1`, `plugin/crew/hooks/scripts/scope-guard.ps1`, `plugin/crew/hooks/scripts/verify-gate.ps1`, `plugin/crew/skills/crew-execute/SKILL.md`, `plugin/crew/skills/crew-plan/SKILL.md`, `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/skills/crew-setup/phases.md`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/skills/crew-verification/SKILL.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_lifecycle_commands.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_review_prompt.py`, `plugin/crew/tests/test_review_run_standards.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. Moved or re-derived here: the version sentence (1.0.76; the skills row takes main's 31); `.crew/verify.json` rule positions (rule 28 `:309-315`, rules 30-36 through T-0085's standards rule 36 at `:371-383`); `/crew:implement` step 6 at `plugin/crew/commands/implement.md:86-116` (`:93`) and `/crew:done` Check 4 at `:50-61`/`:56-59` of `done.md`; the refresh-admission bullet (`completion_audit.py` `_verdicts` `:188`, `_default_artifacts` `:215`, `_outside_refresh_artifacts` `:225-236`, `_entry` `:239`; `crew_refresh_check.py` `_sha_moved` `:522`, `_names_no_commit` `:552`, `_moved_from` `:573`, `_map_verdict` `:642`, `_diff_lines` `:656`, `_index_verdict` `:679`, `_diagram_verdict` `:702`, `_rule_verdict` `:721`, `_stored_blob` `:766`, `artifact_verdicts` `:793`, `_rendered_verdict` `:850`) with round 4's three behaviours, and its Tests bullet naming round 4's tests; the refresh-check paragraph's `RELEASE_BOOKKEEPING` `:238`, status constants `:207-209`, `_named_behind` `:1028`, `_unconfirmed` `:1045` and `ticket_freshness` `:1067` (those five were already behind the code at `7c261a19`); the entry-point bullet (`ticket_freshness` `:1067`, `main()` `:1167`, `artifact_verdicts` `:793`). Main's T-0085 lines (crew_standards, review_prompt, the `.ps1` carriers) are main's own and kept as main wrote them. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `8a15557b` on 2026-09-30 (T-0094: `implement.md` step 6 rewrapped to its 120-line budget).** `git diff --name-only 1b9e4bfe 8a15557b`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md` (the count, in place: 20,711 lines) and `plugin/crew/commands/implement.md`: the merged step-6 paragraph (T-0094's admission sentence beside main's self-check paragraph) was 122 lines, over `test_lifecycle_commands.py`'s 120-line command budget, and is rewrapped to 104 columns with its wording unchanged, so every line from the self-check paragraph down sits where main has it again (tracker `:112`, step 7 `:116`); the refresh check is still `:93`. In `crew.md`, `/crew:implement` step 6 is now `implement.md:86-115` (was `:86-116`) and the tracker's `done.md` call is `:67` (it read `:63`, main's line, behind T-0094's four extra `done.md` lines on both sides of the merge). No other body citation moved. No suite was executed for this note beyond `test_lifecycle_commands.py`.

**Re-anchored `8a15557b` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 8a15557b a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `docs/guides/crew/src/daily-workflow-scope.md` (one could-not-tell sentence extended, +1 line at `:104-106`), `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines), `plugin/crew/tests/sabotage_refresh.py` (+4 docstring lines, five entries appended after the round-5 marker), `plugin/crew/tests/test_refresh_admission.py` (+1 import line, the round-5 tests appended). `c10e1ccf` is the round-5 fix (`crew_refresh_check.py`: `_present` new before `_listing`, used by `_read_config`, `_texts` and `_rule_verdict`; its tests and sabotage entries), `6ed4f6e4` the CHANGELOG, README and daily-workflow guide text, and `4bdab709`/`a0c171c7` un-set and re-set crew 1.0.76; `4bdab709` also carried this note's body edits, staged with it by an `-a` commit. Moved or re-derived here, each read with `grep -n` at `a0c171c7`: `_named_behind` `:1053`, `_unconfirmed` `:1070`, `ticket_freshness` `:1092`, `main()` `:1192`, `artifact_verdicts` `:818` and its reach `:836-845`, `_sha_moved` `:541`, `_names_no_commit` `:571`, `_moved_from` `:592`, `_map_verdict` `:664`, `_diff_lines` `:678`, `_index_verdict` `:701`, `_diagram_verdict` `:724`, `_rule_verdict` `:743` and its unreadable branch `:753-755`, `_stored_blob` `:791`, `_rendered_verdict` `:875`, `COULD_NOT_TELL` `:478`; new: round 5's `_present` sentence (`:327`, `_read_config` `:300`, `_texts` `:644`) and its tests. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:431-457`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 148 cited, tracked paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/INDEX.md`, `.crew/codemap/crew.md`, `CHANGELOG.md`, `docs/diagrams/process-crew-lifecycle.mmd`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/completion_audit.py`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/refresh_fixtures.py`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_completion_audit_refresh_artifacts.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_refresh_admission.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/INDEX.md`, `.crew/codemap/crew.md`, `.crew/verify.json`, `CHANGELOG.md`, `docs/diagrams/process-crew-lifecycle.mmd`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/refresh_fixtures.py`, `plugin/crew/tests/test_refresh_admission.py`, `plugin/crew/tests/test_refresh_check.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). Re-derived here: the refresh-artifact bullet (`REFRESH_ARTIFACT_PATHS` `:234-239`; `scope_guard.py`'s `_refresh_artifact` `:209-220` and `completion_audit.py`'s `_outside_refresh_artifacts` `:177-187`, both main's again after the split; `artifact_verdicts` `:903` now has no caller in the hooks until L-0540, JUDGEMENT; every `crew_refresh_check.py` position in it, and round 6's `_on_disk` `:676`, `_graph_verdict` `:984`, `_claims` `:867`, `_kind` `:876`), its Tests bullet (round 6's tests; the audit suite's T-0094 cases marked as landing with L-0540), the T-0010 `scope_guard.py` citations (`:118-122`, `:237`, `:265`, `:281`, `:257`, `:126-127`: main's file, without T-0094's six rule-6 docstring lines), the entry-point bullet (`ticket_freshness` `:1196`, `main()` `:1296`, `artifact_verdicts` `:903`) and the version sentence (1.0.78). Citations were checked with `/root/crew-tmp/t-0094/cite_map_merge.py` (`MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local) and each position read with `grep -n`; history positions inside provenance and per-commit position lists were left as written. No suite was executed for this note.

**Re-anchored `65abeb8d` -> `1f21f73b` on 2026-09-30 (T-0094 review round 7: `902fb96a`..`91da43bc` code and tests, docs, guide rebuilt, crew 1.0.78 un-set and re-set as `1f21f73b`).** `git diff --name-only 65abeb8d 1f21f73b` returns `CHANGELOG.md`, `docs/guides/crew/crew-1.0-daily-workflow.docx`, `docs/guides/crew/crew-1.0-daily-workflow.html`, `docs/guides/crew/crew-1.0-daily-workflow.pdf`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. Re-derived here: the refresh-artifact bullet's `crew_refresh_check.py` positions (every function below `_base_text` moved: `_read_regular` is new at `:687`), round 7's sentence, and the entry-point bullet (`ticket_freshness` `:1263`, `main()` `:1363`, `artifact_verdicts` `:970`), each read with `grep -n`. No suite was executed for this note.

**Re-anchored `1f21f73b` (T-0094) / main -> `17d0b1d2` on 2026-09-30 (T-0094 merges origin/main `d1462bbd`, L-0529 landed as crew 1.0.80 (#283), and re-sets crew 1.0.81 in the merge commit).** `git diff --name-only 79ef56c4 17d0b1d2`, refresh artifacts aside, returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_context_watch_python_resolver.py`, `plugin/crew/tests/test_event_claim_crash_safety.py`, `plugin/crew/tests/test_path_link_farm.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/obsidian-vault/.claude-plugin/plugin.json`, `plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py`: main's L-0529 files plus the version statements. The merge's conflicts were version lines and the generated rules' stamps; main's body lines kept. Re-derived here: the version sentence (1.0.81). No body citation moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=79ef56c4`; its only flags are history positions in verification-harness.md's per-commit lists, left as written). No suite was executed for this note.

## Re-anchor provenance - main `6a8c60b1` -> `c43a54c1`, 2026-09-30 (T-0028, feature half, crew 1.0.84)

T-0028 (the Kimi Code provider, feature half after the owner's split; the review launch is L-0527)
merged origin/main `6a8c60b1` (L-0531 #284 and T-0099 #278, crew 1.0.83) with rerere disabled, taking main's code
maps. The branch differs from main only in the Kimi provider's feature files (`crew_state.py`,
`crew_config.py` with the launch gate, `kimi_probe.py`, the templates, provider docs and tests,
`.crew/verify.json`, the release files). This note is main's copy; every body citation into a
changed file was mapped by a `difflib` line diff from `6a8c60b1` to `c43a54c1` with
`/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved citation landing on the
same line text. It gains the Kimi provider section (probe, launch gate, the missing launcher) and the
127-leaf count; rule 7's and rules 37-38's spans were re-read with `grep -n`. T-0028's earlier branch provenance is in git history. Re-anchor
only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `c43a54c1` -> `f4adf923`, 2026-09-30 (T-0028 re-sets crew 1.0.85)

`f4adf923` changes only the release files (crew 1.0.84 -> 1.0.85: `plugin.json`, `marketplace.json`,
`PLUGINS.md`, the README's version mention and the CHANGELOG heading), because T-0505 targets
1.0.84. No cited line moved; the version sentences were re-read. Re-anchor only (owner
refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `f4adf923` -> `328fdf4a`, 2026-09-30 (T-0028 round-7 fixes, crew 1.0.85 re-set)

`233701d5` fixes review round 7's four FIXes in `kimi_probe.py` (the owner accepted round 7 and
ordered the fixes); `328fdf4a` re-sets crew 1.0.85. Body citations were mapped by `difflib` from
`ea90a4e4` to `328fdf4a` with `/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved
citation landing on the same line text. It gains the round-7 probe claims (`_CappedReader`, `_read_config`, the credential file), read
from the code with `grep -n`. Re-anchor only (owner refresh-artifact
standing rule, 2026-09-28); no test suite was executed for this note.

**Re-anchored `17d0b1d2` -> `c4e2eb98` on 2026-09-30 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)).** `git diff --name-only 17d0b1d2 c4e2eb98` adds L-0520's PR 1 outside refresh artifacts: the new `plugin/crew/hooks/scripts/crew_train.py` and its test, `plugin/crew/commands/done.md` (a new section after T-0094's), `plugin/crew/README.md` (a new subsection, and the `<git-common-dir>/crew/` list names the train), two guides and their outputs, `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md:11` (in place), `.crew/verify.json` (one rule) and `test_lifecycle_commands.py`. Path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`, machine-local). The merge train section was regenerated from `crew_train.py` at this anchor, and the version sentence reads 1.0.82. No suite was executed for this note.

**Re-anchored `c4e2eb98` -> `0be97503` on 2026-09-30 (L-0520 PR 1 merges main 42af3fb7 (L-0531)).** `git diff --name-only c4e2eb98 0be97503` returns, outside refresh artifacts, only L-0531's `plugin/crew/tests/sabotage_qa.py` (appended entries), `.crew/verify.json` (one rule's text) and the release bookkeeping; path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`); the merge train section was regenerated (unchanged lines) and the version sentence reads 1.0.83. No suite was executed for this note.

**Re-anchored `0be97503` -> `14bb59ef` on 2026-09-30 (L-0520 PR 1 merges main 6a8c60b1 (T-0099)).** `git diff --name-only 0be97503 14bb59ef` returns, outside refresh artifacts, T-0099's `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/tests/sabotage_review.py`, `plugin/crew/tests/test_review_prompt.py` and release bookkeeping; path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`); the merge train section was regenerated and the version sentence reads 1.0.84. No suite was executed for this note.

**Re-anchored `14bb59ef` -> `8bf710ed` on 2026-09-30 (L-0520 PR 1 review round 1 fixes).** `git diff --name-only 14bb59ef 8bf710ed` returns `plugin/crew/hooks/scripts/crew_train.py` (check-land re-checks the hold and HEAD, state saved before events, status --json notices, untracked files in catch-up, entry shape checks), `plugin/crew/commands/done.md` (two lines quoted in place), `plugin/crew/README.md` (two sentences in place), `plugin/crew/BUDGETS.md`, two tests and the version files. The merge train section was regenerated from crew_train.py at this anchor. No suite was executed for this note.

**Re-anchored `8bf710ed` -> `14b52c91` on 2026-09-30 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86).** `96bfd946` merges origin/main `bd4b2f30` with rerere disabled; `git diff --name-only 8bf710ed 14b52c91` returns, outside refresh artifacts, T-0028's Kimi Code provider files (`crew_state.py`, `crew_config.py`, `kimi_probe.py`, templates, provider docs and tests, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`), main's unregistered `plugin/mailgun/` (which `scripts/check-marketplace.py` reports as not registered, on main as here), `.crew/verify.json` (both sides' rules: the merge train rule is 37, T-0087's harness rule 38, T-0028's Kimi rule 39), `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md` and the version files (1.0.86). Conflicted map hunks were resolved by hand (anchor lines this branch's, provenance and INDEX history both sides', both new crew.md sections kept); body path:line citations were mapped from the side each line came from to the merged tree by difflib (`/root/crew-tmp/l-0520/tools/merge_remap.py`, machine-local), the README runbooks-index citation and the verify.json rule numbers re-read with `grep -n`, and the version sentence reads 1.0.86. No suite was executed for this note.

**Re-anchored `14b52c91` -> `0c3508e9` on 2026-09-30 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86).** `git diff --name-only 14b52c91 0c3508e9` returns, outside refresh artifacts, L-0561's registration of `skills/mailgun` (moved from `plugin/mailgun/`), `.claude-plugin/marketplace.json`, both install scripts, `README.md`, `INSTALLATION.md`, `skills/README.md` and `CHANGELOG.md`; no `plugin/crew` path. Install-script citations in install-scripts.md and marketplace-registration.md were moved by difflib from `3f75648a` (`/root/crew-tmp/l-0520/tools/merge_remap.py`), and repo-docs.md's skills count reads 35. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `fe524012` on 2026-09-30 (L-0513, the shared gate runner `scripts/gate-runner.py`; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 0c3508e9 fe524012` returns, outside refresh artifacts, `.crew/verify.json` (rule 22's `run`, `seconds` and `why` in place, and rule 40 appended after T-0028's Kimi rule 39 at `:426-430`), `CLAUDE.md` (a two-line gate-runner pointer in Commands, so every line from the old `:14` moved down 2), `CHANGELOG.md`, `README.md` (main's re-pin `767fa3ef`, in place), `scripts/gate-runner.py` and `scripts/_test/gate-runner.py`; no `plugin/crew` path. Every `CLAUDE.md:N` and `.crew/verify.json:N` body citation in this note was re-read with `grep -n`/`sed -n`. `.crew/verify.json`'s last rule is now rule 40 (the gate runner), so the standards bullet names rule 36 (`:372-384`), which runs the standards tests, instead of "the last rule" (already stale at `0c3508e9`, where the last rule was T-0028's Kimi rule 39). No suite was executed for this note.

**Re-anchored `fe524012` -> `4eacfacf` on 2026-09-30 (L-0513 step 6 fix: the inner gate runner exits 128+signum after a signal).** `git diff --name-only fe524012 4eacfacf` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py` and `.crew/verify.json` (rules 22 and 40: `why` text only, in place; line count unchanged, rule 40 still `:426-430`). No body citation in this note moved. No suite was executed for this note.

**Re-anchored `4eacfacf` -> `3437cbdd` on 2026-10-01 (L-0513 Fix phase: review round 1's 2 BLOCK and 6 FIX; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 4eacfacf 3437cbdd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `CHANGELOG.md` (the L-0513 Unreleased entry, +9 lines) and `.crew/verify.json` (rules 22 and 40: `seconds` 12 -> 20 and `why` text, in place; line count unchanged, rule 40 still `:426-430`). No body citation of this map points into those files' changed lines. No suite was executed for this note.

**Re-anchored `3437cbdd` -> `e41bc6fd` on 2026-10-01 (L-0513 successor plan: review round 2's six fixes, after `git -c rerere.enabled=false merge origin/main` at `1899c370`; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only 3437cbdd e41bc6fd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 20 -> 41, in place, line count unchanged), and from main's merge `.github/workflows/runner-autostart.yml`, `CHANGELOG.md` (+22 lines at `:31`, W-0116's entry), `plugin/PLUGINS.md:14`, `.claude-plugin/marketplace.json:224` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.86 -> 1.0.89, in place), `plugin/crew/hooks/scripts/crew_refresh_check.py` (+43 lines, inserted after `:686`, `:694` and `:713`) and `plugin/crew/tests/test_refresh_admission.py`. In this map the ten `CHANGELOG.md:N` citations moved +22 and `crew_refresh_check.py:970`/`:1263` moved to `:1013`/`:1306` (each re-read at the new line: `artifact_verdicts`, `ticket_freshness`); `:236-241` is above every inserted hunk; the version sentence at `:59` now reads 1.0.89. No suite was executed for this note.

**Re-anchored `e41bc6fd` -> `4a48f594` on 2026-10-01 (L-0513 Fix phase: review round 3's BLOCK, five FIX and the NIT; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only e41bc6fd 4a48f594` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 41 -> 55 and their `why` text, in place, line count unchanged) and `CHANGELOG.md` (+7 lines inserted after `:29`, inside L-0513's own entry). No map cites a `scripts/gate-runner.py` line. The `CHANGELOG.md:N` figures inside earlier re-anchor notes describe the file at those notes' own anchors and are left as written; none is a body citation of current content. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `6e581365` on 2026-09-30 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91).** `git diff --name-only 0c3508e9 6e581365` outside the refresh artifacts returns W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` and `plugin/crew/tests/test_refresh_admission.py`, `.github/workflows/runner-autostart.yml` (#294), the repo README, and T-0505's files: `promote-gate.sh`/`.ps1`, the new `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md (+2 lines in section 16), the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` (rule 4 path), the troubleshooting guide and its builds, the cloud handoff note and README, CHANGELOG.md and the version files (crew 1.0.91, past main's 1.0.89). A difflib re-map of every path-qualified `path:line` citation in the eight maps (history sections skipped) moved four: `crew_refresh_check.py:970` -> `:1013` (W-0116) and three `plugin/crew/CONFIG.md:2422-2429` -> `:2412-2419` (T-0505's sentence); none was unmapped. Re-applied by hand in `crew.md`: `promote-gate.sh:79` is the plain `crew_py()` call (re-read with `grep -n`), and `promote-gate.sh` is not a `crew_config.py` user (no `crew_config` import or `.crew/config.json` read in either flavour). Bare `:N` continuations and `CHANGELOG.md` citations in history sections were left as written. No suite was executed for this note.

**Re-anchored `6e581365` -> `9580571e` on 2026-10-01 (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91).** `git diff --name-only 6e581365 9580571e` outside the refresh artifacts returns only `plugin/crew/.budget-allowance.json`: promote.md's entry edited in place (`lines` 335 -> 380, reason `T8: to trim` -> a `raised:` reason), line count unchanged. No note cites a line of that file; a difflib re-map of every path-qualified citation moved none. No suite was executed for this note.

**Re-anchored `136f4b33` -> `8f85657a` -> `33c833c8` on 2026-09-28 (T-0040).** `8f85657a` is T-0040's step-8 commit on `T-0040-shell-routes`, cut from main `6387ab49`. `git diff --name-only 136f4b33 8f85657a` over every path this note cites returns, outside the code maps, only T-0040's files: `crew_config.py` (the `shellRoute` block, +8 after `:327` and +4 after `:563`), `crew_status.py` (+1 import, +5 after the verify line), `sabotage.py` (+1 import at `:81`, the concatenation), `crew-setup/SKILL.md` (the inline copy), both templates, `test_crew_config.py`, `test_status.py`, and the new `crew_shell.py`, `sabotage_shell.py` and `test_crew_shell.py`. Every body citation of the form `path:line` into those files was mapped through `git diff -U0` by script and re-read: moved and re-cited are `crew_config.py` `:393` -> `:401`, `:1260` -> `:1272`, `:381` -> `:389`, the ratchet construction sites `:2444`-`:2556` -> `:2456`-`:2568` (bare citations included), `crew_status.py:63` -> `:64`, and `test_crew_config.py:282` -> `:294`. The leaf counts were re-executed (125 / 70 / 55 / 0) and the Windows shell route section is new. Lines cited inside dated provenance notes are left as history at their own commit. Only the leaf-count functions and the citation script were executed for this note. Then `33c833c8`: step 11's native run reopened `measure` (`33c833c8`, in-shell timing, +18 lines in `crew_shell.py`); every `crew_shell.py` citation in the section above was re-taken by content with `grep -n`, and `git diff --name-only 8f85657a {SHA}` touches no other cited path except T-0040's docs: step 9's `phases.md` (+9 above `:180`) and `implement.md` (+2 above `:89`) moved two citations here, re-cited as `phases.md:189-195` and `implement.md:91-113` and re-read with `sed -n`.

**Re-anchored `33c833c8` -> `f05ed74e` on 2026-09-30 (T-0040 review round 1, T-0040-Bdt4JE).** `git diff --name-only 33c833c8 f05ed74e`, refresh artifacts aside, returns `crew_shell.py`, `test_crew_shell.py`, `sabotage_shell.py`, `crew-execute/SKILL.md`, `crew-graph/SKILL.md`, `crew-setup/platform.md`, `BUDGETS.md` and `.crew/verify.json` (step 11's `seconds`). Of those, this note cites line numbers only in `crew_shell.py`, whose section above was re-taken symbol by symbol with `grep -n` at `f05ed74e` (the file grew 875 -> 1020 lines: `route_for`, `job_head`, `_embeds_posix_path`, `one_line`, `_in_job_shell` are new) and `BUDGETS.md:11`, which kept its line (only the count on it changed). `SHELL_MUTATIONS` went 11 -> 13 entries. Nothing was executed for this note beyond `grep -n` and the per-path diff.

**Merged `17d0b1d2` (main) + `f05ed74e` (T-0040) on T-0040-land, 2026-09-30 (T-0040's reviewed `913bec89` merged into origin/main `6a8c60b1`, crew 1.0.83).** Twelve hunks of this file conflicted: the anchor, the leaf table and its paragraph, the ratchet registry's positions, four cited-line pairs and the provenance tail. Both sides' provenance is kept, main's first; T-0040's copy of the `136f4b33` note is the base text main corrected (`plugin/crew/README.md:866`), so main's stands alone. Leaf counts re-executed on the merged tree with the command above: 127 / 70 / 57 / 0 (`plugin/crew/tests/test_crew_config.py:301` asserts 127, measured by running it). Re-taken with `grep -n` on the merged tree: `crew_config.py` `default_config` `:244`, `default_global_config` `:405`, the two `shellRoute` entries `:339` / `:579`, `_RATCHETED` `:2479-2591` (literal `:2479-2490`, updates `:2494`, `:2507`, `:2518`, `:2528`, assignments `:2564`, `:2587`), `production_declaration`'s read `:1276`, the autopilot deep copy `:393`; `crew_status.py` `_tracker_line` `:67`; `implement.md` step 6 `:88-117` and its refresh check `:95`; `crew-setup/phases.md` `plan-windows-default` `:191-197`. Every other body citation into a file the merge changed was mapped from the side that wrote it by script (difflib, main's lines through `6a8c60b1`, T-0040's through `913bec89`) and is listed in this landing's commit; `crew_state.py` and every file only main changed keep main's numbers. Nothing was executed for this note beyond `grep -n`, the leaf-count command and that one test.

**Re-anchored `17d0b1d2` (main) / `f05ed74e` (T-0040) -> `3bb32980` on 2026-09-30 (T-0040-land: the merge `b6ae7c61` of T-0040's `913bec89` into origin/main `6a8c60b1`, then review round 2's five FIXes at `3bb32980`).** The merge's resolution is the note above. The fix commit changed `crew_shell.py` (1020 -> 1056 lines; the T-0040 section's positions re-taken symbol by symbol with `grep -n`, and its `load_cache`, `measured_verdict`, `_python_module` and `--cd` preflight sentences added), `crew_config.py` (the `shellRoute` comment rewritten line for line and `mode` null in `default_config()`; no line moved, `:339` / `:579` hold), `test_crew_config.py` (`assert len(declared) == 127` `:301` -> `:305`), `sabotage_shell.py` (13 -> 14 entries), the repo template, `crew-setup/SKILL.md` and `CONFIG.md` (in place). Leaf counts unchanged: 127 / 70 / 57 / 0. Executed for this note: the leaf-count command, and `test_crew_shell.py`, `test_crew_config.py`, `test_status.py`, `test_sabotage_harness.py` serially (937 passed, 1 skipped).

**Merged `3bb32980` (T-0040-land) + `328fdf4a` (main) on T-0040-land, 2026-09-30 (merge of origin/main `844bfc36`, T-0028 landed as crew 1.0.85).** Seven hunks of this file conflicted: the anchor, the leaf paragraph, the ratchet registry's positions (two), the verify-rule list, the entry points and the provenance tail. Both sides' provenance is kept, main's first. Leaf counts re-executed on the merged tree: 129 / 72 / 57 / 0 (`plugin/crew/tests/test_crew_config.py:310` asserts 129, measured by running it). Re-taken with `grep -n` on the merged tree: `crew_config.py` `default_config` `:244`, `default_global_config` `:405`, `shellRoute` `:339` / `:579`, `_RATCHETED` `:2510-2622` (literal `:2510-2521`, updates `:2525`, `:2538`, `:2549`, `:2559`, assignments `:2595`, `:2618`), `plan_repo_write` / `write_repo_config` `:3105` / `:3131`, `plan_global_write` / `write_global_config` `:2905` / `:2924`; `crew_state.py` `evaluate_triggers` `:2942`; `.crew/verify.json` T-0028's rule 38 `:411-424` and T-0040's rule 39 `:426-432`. Body lines outside the hunks keep the side that wrote them; each citation into a file the merge changed was compared by script against that side's tree (`git diff -U0`). Nothing was executed for this note beyond `grep -n`, the leaf-count command and that one test.

**Re-anchored `328fdf4a` (main) / `3bb32980` (T-0040-land) -> `a54ca704` on 2026-09-30 (T-0040-land's merge of origin/main `844bfc36`, T-0028 landed as crew 1.0.85).** The merge note above names every citation the merge re-took; nothing else moved. No suite was executed for this note beyond the merge's.

**Merged `0c3508e9` (main) + `a54ca704` (T-0040-land) on T-0040-land, 2026-10-01 (merge of origin/main `66651b69`: L-0520 PR 1 #287, the merge train, landed as crew 1.0.86; anchored at that main tip).** Four hunks of this file conflicted: the anchor, the verify-rule list, the gate-record reader citations and the provenance tail. Both sides' provenance is kept, main's first. Re-taken on the merged tree: `.crew/verify.json` by `json.load` index and by line - L-0520's merge train rule 37 `:385`, T-0087's harness rule 38 `:386-411`, T-0028's Kimi rule 39 `:412-425` and T-0040's shell-route rule 40 `:427-432`, the last; `plugin/crew/hooks/scripts/review_prompt.py:178` (main's position; T-0040 does not touch the file) and `plugin/crew/hooks/scripts/crew_status.py:155` (T-0040's +1 import; main does not touch the file), both the `verify_record.read_record` call, with `grep -n`. Every `path:line` either side added into a file only the other side changed was mapped through a line diff onto the merged tree; outside dated provenance none moved. No suite was executed for this note beyond the merge's.

**Merged `66651b69` -> `0c0275e8` on T-0040-land, 2026-10-01 (origin/main after W-0116 #292, crew 1.0.89; a clean merge with rerere off).** `git diff --name-only 66651b69 0c0275e8` returns, outside release bookkeeping, `plugin/crew/hooks/scripts/crew_refresh_check.py` (W-0116: `_win_final_path` and `_FINAL_PATH` new after `:686`, `_read_regular`'s docstring and its Windows final-path check; +43 lines below `:713`) and `plugin/crew/tests/test_refresh_admission.py`. This map's citations into `crew_refresh_check.py` that held at `66651b69` and sat below the insertion were moved and each re-read against the symbol it names: `artifact_verdicts` `:1013`, the reach lines `:1031-1040`, `_map_verdict` `:845`, `_diff_lines` `:859`, `_index_verdict` `:882`, `_diagram_verdict` `:906`, `_rule_verdict` `:925`, `_stored_blob` `:965`, `_claims` `:977`, `_kind` `:986`, `_rendered_verdict` `:1072`, `_graph_verdict` `:1094`, `_on_disk` `:786`, `_read_regular` `:719`, `ticket_freshness` `:1306`, `main` `:1406`. W-0116's Windows final-path check is not described here. Five positions in the CLI paragraph above (`RELEASE_BOOKKEEPING` `:238`, `:207-209`, `_named_behind` `:1053`, `_unconfirmed` `:1070`, `ticket_freshness` `:1092`) were already behind at `66651b69` and are left as found. Anchor kept at `66651b69`. No suite was executed for this note.

**Merged `9580571e` (main) + `66651b69` (T-0040-land) on T-0040-land, 2026-10-01 (merge of origin/main `44d3dbc6`: runner auto-start #294, T-0505 #296 and T-0110 #297, crew 1.0.97, with rerere off; anchored at that main tip).** Three hunks of this file conflicted: the anchor, the `crew_refresh_check.py` entry-point bullet and the provenance tail. The bullet keeps T-0040-land's re-read positions (`main()` `:1406`, `artifact_verdicts` `:1013`; main had re-mapped only the path-qualified `:970`). Both sides' provenance is kept, main's first. Every `path:line` either side added into a file the other side changed was mapped through a line diff onto the merged tree, and every citation into a file both sides changed was compared by text. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `bf7ce780` on 2026-09-30 (L-0558: L-0520 round-2 fixes and the rerere rule, crew 1.0.87).** `git diff --name-only 0c3508e9 bf7ce780` returns, outside refresh artifacts, L-0520's own graph rebuild and main's README re-pin (c260cdfb, via the #287 merge 66651b69), then L-0558's `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md` (merge-train section, in-place line edits), the daily-workflow and troubleshooting guide sources and their six rebuilt outputs, `CHANGELOG.md`, `.crew/verify.json` (rule 37's why and seconds, still :385) and the three version files (1.0.87, same lines). The merge-train section above was re-derived from crew_train.py read in full at bf7ce780; citations elsewhere were checked with l0520_remap.py (0 moved outside that section; verify.json:387 kept, its content changed in place). No suite was executed for this note.

**Re-anchored `bf7ce780` -> `dbad6519` on 2026-09-30 (L-0558 self-review fixes, crew 1.0.87).** `git diff --name-only bf7ce780 dbad6519` returns, outside refresh artifacts, `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py` and `CHANGELOG.md` (L-0558's self-review fixes); the merge-train section's crew_train.py citations were re-mapped by definition name and the `_both_sides` stage filter added. No suite was executed for this note.

**Re-anchored `dbad6519` -> `c8118baf` on 2026-09-30 (L-0558 lint fix and version re-set).** `git diff --name-only dbad6519 c8118baf` returns, outside refresh artifacts, `plugin/crew/tests/test_crew_train.py` (one trailing blank line dropped) and the three version files (stepped back and re-set to 1.0.87 on the same lines); nothing any map cites by line moved. No suite was executed for this note.

**Re-anchored `c8118baf` -> `afd976ee` on 2026-09-30 (L-0558 review round 1 fix).** `git diff --name-only c8118baf afd976ee` returns, outside refresh artifacts: CHANGELOG.md plugin/crew/README.md plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py - see the merge-train section for crew_train.py citations, re-mapped by definition name; no other cited line moved. No suite was executed for this note.

**Re-anchored `afd976ee` -> `d21fa82d` on 2026-09-30 (L-0558 round-2 fixes and main merge, crew 1.0.95).** `git diff --name-only afd976ee d21fa82d` returns, outside refresh artifacts: .claude-plugin/marketplace.json CHANGELOG.md plugin/PLUGINS.md plugin/crew/.claude-plugin/plugin.json plugin/crew/README.md plugin/crew/hooks/scripts/crew_refresh_check.py plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py plugin/crew/tests/test_refresh_admission.py - crew_train.py citations in the merge-train section were re-mapped by definition name; W-0116's crew_refresh_check.py and test_refresh_admission.py are main's (merged with rerere disabled at 8935fc25), and no line this map cites in them is relied on here without re-reading; the version files moved value, not line. No suite was executed for this note.

**Re-anchored `9580571e` -> `b0ac0e1a` on 2026-09-30 (L-0558 merges main 6fe0e0db (T-0505), crew 1.0.95).** Both histories are kept above: main's T-0505 chain to 9580571e and L-0558's chain to d21fa82d, merged at f7118a04 with rerere disabled. `git diff --name-only 9580571e b0ac0e1a` outside refresh artifacts is L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, the two guide sources and their outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's W-0116 files already in 9580571e's ancestry; the merge-train section's crew_train.py citations were re-mapped at d21fa82d and crew_train.py has not changed since; no other cited line moved. No suite was executed for this note.

**Re-anchored `44d3dbc6` (main) and `b0ac0e1a` (L-0558) -> `89ebda03` on 2026-10-01 (L-0558 merges main 52489039: T-0110 #297, T-0040 #290; crew 1.0.102).** Both histories are kept above; the merge (c481ada4) ran with rerere disabled. `git diff --name-only 44d3dbc6 89ebda03` outside refresh artifacts is 35 paths: L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, two guide sources and outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's commits since 44d3dbc6; the merge-train section's crew_train.py citations hold (crew_train.py unchanged since 7a71faff); no other line this map cites was re-checked beyond the merge. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `5ab63076` on 2026-09-30 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines).**  No suite was executed for this note.

**Re-anchored `5ab63076` -> `805b0a25` on 2026-09-30 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place).**  No suite was executed for this note.

**Re-anchored `805b0a25` -> `7ecbdc7f` on 2026-09-30 (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only).**  No suite was executed for this note.

**Re-anchored `7ecbdc7f` -> `a9c0d9ab` on 2026-09-30 (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place).**  No suite was executed for this note.

**Re-anchored `a9c0d9ab` -> `083cda66` on 2026-10-01 (L-0516 merges main `64b04c6b` (W-0116 #292: `crew_refresh_check.py` gains the Windows `_FINAL_PATH` check, `test_refresh_admission.py` two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only a9c0d9ab 083cda66` over this map's cited paths names `plugin/crew/hooks/scripts/crew_refresh_check.py` (three hunks at old `:684-717`, everything from old `:687` down moved +32, from old `:743` down +43): each citation in the refresh-check section and the entry-point list re-read with `grep -n` and moved onto the same line text; `_named_behind`, `_unconfirmed` and `ticket_freshness` in that section were already stale at a9c0d9ab and now read `:1267`, `:1284`, `:1306`; the W-0116 `_FINAL_PATH` clause added. The history sections keep their own anchors' numbers.  No suite was executed for this note.

**Re-anchored `083cda66` -> `908c03af` on 2026-10-01 (L-0516 review round 1 fixes: `poll_until` reads the clock before each probe after the first, `test_poll_fixtures.py` reaps its children with `wait(timeout=10)`, CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only 083cda66 908c03af` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `908c03af` -> `11f476a2` on 2026-10-01 (L-0516 merges main `6fe0e0db` (T-0505 #296: promote-gate judges the deploy's tree, crew 1.0.92) without rerere and re-bumps crew to 1.0.98).** Conflicts were refresh artifacts, CHANGELOG, BUDGETS.md and the version files only; each map keeps both branches' history notes (main's first). `git diff --name-only 908c03af 11f476a2` outside the refresh artifacts returns T-0505's files (`promote-gate.sh`/`.ps1`, `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md, `.budget-allowance.json`, the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` rule 4's path, the troubleshooting guide and its builds, the cloud handoff note and README), CHANGELOG.md, BUDGETS.md (21,621 lines, still `:11`) and the version files. Main's own re-maps of those files (`CONFIG.md:2412-2419`, `promote-gate.sh:79`) arrived with the merge; a difflib re-map of every path-qualified citation from `908c03af` to `11f476a2` moved none outside history sections, where `CHANGELOG.md` and `CONFIG.md` citations are left as written. `crew_refresh_check.py`'s `main()` `:1406` and `artifact_verdicts` `:1013` keep this branch's values (re-read with `grep -n`; main's map still read `:1363`/`:970`). No suite was executed for this note.

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:482-493`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:296`/`:430` lines. The nine shifted citations are at this file's lines 2238, 2317, 2377, 2823, 2906, 2915, 3059, 3080 and 3212. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `b1d8a4e8` on 2026-09-30 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16).** `git diff --name-only 0c3508e9 b1d8a4e8` returns, outside refresh artifacts, L-0557's test-only files (`plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, new `plugin/crew/tests/test_pwsh_cache_isolation.py`, both `test_flavour_guard.py` copies, the obsidian-vault `_test` suites, six `scripts/_test/*.sh`), `.crew/verify.json` (one new rule, appended after the Kimi rule), `plugin/crew/README.md` (one paragraph after the test-layer table), the harness reference's H4 table (one row), `CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the version files. Body `path:line` citations into those files were moved by difflib from `0c3508e9` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 25 moved, in crew.md (CHANGELOG), obsidian-vault.md (its `_test` suites) and verification-harness.md (verify.json range unchanged). No hook or production script changed. No suite was executed for this note. The version sentence reads 1.0.89.

**Re-anchored `b1d8a4e8` -> `d9ccfd5a` on 2026-10-01 (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95).** `git diff --name-only b1d8a4e8 d9ccfd5a` returns, outside refresh artifacts, W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` (a final-path check in `_read_regular`'s no-dir_fd branch, hunks from :684) and `plugin/crew/tests/test_refresh_admission.py`, `CHANGELOG.md` (both sides' Unreleased entries kept) and the version files (crew 1.0.95). Body `path:line` citations into those files were moved by difflib from `b1d8a4e8` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local), each onto the same line text. No suite was executed for this note. The version sentence reads 1.0.95.

**Re-anchored `d9ccfd5a` -> `97ace923` on 2026-10-01 (L-0557 review round 1 fixes, crew 1.0.96).** `git diff --name-only d9ccfd5a 97ace923` returns, outside refresh artifacts, L-0557's test-only `plugin/crew/tests/conftest.py` (the per-test cache dir is now `tmp_path_factory.mktemp("xdg-cache")`), `plugin/crew/tests/crew_fixtures.py` (one comment), `plugin/crew/tests/test_pwsh_cache_isolation.py` (the static guard judges values and returned environments, reports unreadable suites), `CHANGELOG.md` (L-0557's entry, five lines longer) and the version files (crew 1.0.96: 1.0.95 is also claimed by L-0558, #293). Body `path:line` citations into those files were moved by difflib from `d9ccfd5a` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md. No hook or production script changed. No suite was executed for this note.

**Re-anchored `97ace923` / `9580571e` -> `550c39cd` on 2026-10-01 (L-0557 merges main 6fe0e0db: T-0505 #296 crew 1.0.92, runner auto-start #294; crew stays 1.0.96).** `550c39cd` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files and CHANGELOG only. This side's notes were anchored `97ace923` and main's `9580571e`; `git diff --name-only 9580571e 6fe0e0db` outside the refresh artifacts returns only the 1.0.92 version files and CHANGELOG, so main's notes already describe every non-artifact change it brings, and this side's notes describe L-0557's. Body `path:line` citations were moved by difflib, each from the anchor of the side whose copy of this map carries the line (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 17 moved - 10 `CHANGELOG.md` in crew.md (T-0505's 1.0.92 entry now sits below L-0557's) and 7 `plugin/crew/CONFIG.md` in verification-harness.md (T-0505's CONFIG.md edit), every one an exact-text match. No suite was executed for this note.

**Re-anchored `550c39cd` -> `038d5d10` on 2026-10-01 (L-0557 merges main 44d3dbc6: T-0110 #297, crew 1.0.97; L-0557 re-sets crew 1.0.99 at `4fc11923`).** `038d5d10` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were version files, CHANGELOG and one generated rules file. `git diff --name-only 6fe0e0db 44d3dbc6` outside the refresh artifacts returns T-0110's `.github/workflows/pytest-crew.yml`, `AGENTS.md`, `plugin/crew/tests/crew_fixtures.py` (new helpers below L-0557's, auto-merged), seven crew test files, CHANGELOG and the 1.0.97 version files. T-0110 updated verification-harness.md's `pytest-crew.yml` sentence itself; the other files are cited by name only. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md (T-0110's 1.0.97 entry now sits below L-0557's), every one an exact-text match. No suite was executed for this note.

**Re-anchored `038d5d10` / `44d3dbc6` -> `90186613` on 2026-10-01 (L-0557 merges main 52489039 at `327e6ec1`: T-0040 #290, crew 1.0.98; L-0557 re-sets crew 1.0.101 at `90186613`).** `327e6ec1` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files, CHANGELOG, BUDGETS.md's count and `.crew/verify.json` (both sides appended one rule; both kept). Main's notes (anchor line `44d3dbc6`) were re-taken by T-0040 on its own merged tree `52489039`, so a line only in main's copy of a map is measured from `52489039`; a line in this side's copy is measured from `038d5d10`. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 73 moved, all from this side's lines - `plugin/crew/README.md` (+11 lines from T-0040 above :743), `plugin/crew/CONFIG.md` (+11 from T-0040), `CHANGELOG.md` (T-0040's 1.0.98 entry, then this side's below it), `plugin/crew/tests/test_crew_config.py` and `plugin/crew/hooks/scripts/crew_config.py` (T-0040); every one an exact-text match, none on a changed line. T-0040's own claims about crew_shell.py, crew_status.py and the shell-route config are main's notes above and were not re-derived here. No suite was executed for this note.

**Re-anchored `89ebda03` (main) and `90186613` (L-0557) -> `773ce841` on 2026-10-01 (L-0557 merges main `05a679bf`, L-0558 #293, crew 1.0.102, at `2169bd11` with rerere disabled; L-0557 re-sets crew 1.0.105 at `773ce841`).** Both provenance histories are kept above, main's first. Body citations were re-checked by mapping each one from the tree its line came from (`89ebda03` for main's lines, `74dd1aa5` for L-0557's) to this tree with difflib: 10 `CHANGELOG.md` citations moved (+33, L-0558's entry above them), and the version sentence now cites `.claude-plugin/marketplace.json:223`/`:224` and reads 1.0.105. Citations into the version lines of `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` keep their line numbers (the value changed in place). No suite was executed for this note.

**Re-anchored `0d159692` (main, L-0513 #301) and `773ce841` (L-0557) -> `a9608aa5` on 2026-10-01 (L-0557 merges main `cacf7ff0`, L-0513 #301: `scripts/gate-runner.py`, no plugin version; rerere disabled; crew stays 1.0.105).** Both provenance histories are kept, main's first. Where both sides had re-mapped the same citation, main's line was taken, and each citation was then mapped with difflib from the tree its line came from (`cacf7ff0` for main's lines, `95036b4c` for L-0557's) to this tree: 10 `CHANGELOG.md` citations taken from main's side moved +22 (L-0557's entry above them). No suite was executed for this note.

**Re-anchored `a9608aa5` -> `c43a9ce3` on 2026-10-01 (L-0557 merges main `ddcbf90d`, W-0115 #299, crew 1.0.106, at `0597e5c6` with rerere disabled, and re-sets crew 1.0.111 at `c43a9ce3`).** The merge touched no code map. `git diff --name-only a9608aa5 c43a9ce3` outside refresh artifacts is W-0115's `plugin/crew/tests/sabotage.py`, `sabotage_shell.py` and `.crew/verify.json` plus the version files and CHANGELOG; each citation into a changed file was mapped with difflib from `92448f1a` to this tree: 10 `CHANGELOG.md` citations moved +15 (W-0115's entry), and `plugin/crew/tests/sabotage.py:3057`/`:3056` moved to `:3057`/`:3058`; the version sentence reads 1.0.111. No suite was executed for this note.

**Re-anchored `5ffffbe3` (main, L-0516 #298) and `c43a9ce3` (L-0557) -> `6053b65d` on 2026-10-01 (L-0557 merges main `2906dcbd`, L-0516 #298, crew 1.0.110, at `2f3fb34c` with rerere disabled, and re-sets crew 1.0.114 at `6053b65d`).** Both provenance histories are kept, main's first, and main's body citations were taken where both sides had re-mapped the same one. Each citation into a changed file was then mapped with difflib from the tree its line came from (`2906dcbd` for main's lines, `a54ff87b` for L-0557's) to this tree: 10 `CHANGELOG.md` citations moved (+22 from main's side, +35 from L-0557's); the `.crew/verify.json:482-493` range in L-0516's provenance note was kept, because mapping it would stretch it across L-0557's rule. No suite was executed for this note.

**Re-anchored `6053b65d` -> `f5cab1f9` on 2026-10-01 (T-0503 merges origin/main `ffd11270`, L-0557 #300, crew 1.0.114, at `f5cab1f9` with rerere disabled; bitbucket 1.2.3).** The merge took main's side of every code map. `git diff --name-only ffd11270 f5cab1f9` is T-0503's own change only: `.claude-plugin/marketplace.json` (bitbucket version), `CHANGELOG.md` (its entry, 33 lines at the top), the `bitbucket` catalog row in `README.md` and `skills/README.md` (edited in place, no line count changed), `docs/handoff/cloud/T-0503.md`, and `skills/bitbucket/` (`SKILL.md`, `references/api.md`, `scripts/_test/merge_gate.sh`). Every citation into those files was compared by script against `ffd11270` (158 checked across the eight maps); In this map that moved the ten `CHANGELOG.md` citations by +33 (T-0503's entry sits above main's), each re-mapped by difflib and checked to read the same line at `f5cab1f9` as at `ffd11270`; no other cited line moved. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); no suite was executed for this note.

**Re-anchored `f5cab1f9` -> `45bed356` on 2026-10-01 (T-0503 review round 1 fixes, bitbucket 1.2.3).** `git diff --name-only f5cab1f9 45bed356` is `CHANGELOG.md` and `skills/bitbucket/` (`SKILL.md`, `references/api.md`, `scripts/_test/merge_gate.sh`) only; every citation into them was compared by script. In this map the ten `CHANGELOG.md` citations moved +5 more (T-0503's entry grew by five lines describing the fixes), each re-mapped by difflib and checked to read the same line at `45bed356` as at `f5cab1f9`. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); no suite was executed for this note.

**Re-anchored `45bed356` -> `b4f04e23` on 2026-10-02 (L-0578 merges origin/main `8d84786d`, W-0117 #302, crew 1.0.115, at `b4f04e23` with rerere disabled; crew 1.0.119).** L-0578's own change is `review_metrics.py` (new), `review_run.py`, `review_patch.py`, `commands/review.md`, the README, BUDGETS.md, external-tool-formats.md, `.crew/verify.json` rule 38, its tests and sabotage entries, and the version files and CHANGELOG. 16 citations re-mapped by difflib from `45bed356` (ten CHANGELOG.md +37 under the W-0117 and L-0578 entries; review_run.py `:508`->`:524`, `:669`->`:706`, `:398`/`:399`/`:401`->`:409`/`:410`/`:412`; review_patch.py `:119`->`:126`; crew_refresh_check.py `:1013`->`:1019`, `:1306`->`:1312`), plus by hand: review_patch.py `:104`/`:105` -> `:111`/`:112` (EXCLUDED now names `.crew/metrics.md`), and two bare review_run.py citations, `:575`->`:611` (preflight) and `:441`->`:480` (the refund line). Other bare `:N` citations in the T-0085 section were already off at `45bed356` and were not re-derived here. No suite was executed for this note.

**Re-anchored `3648f59a` -> `0da787d3` on 2026-09-29 (T-0107, gizmoduck 0.5.4). Current despite the lag.** `crew_refresh_check.py` named README.md, plugin/README.md as changed since the anchor. T-0107 edits exactly one line of each, in place (`git diff --numstat 2693d0fa 0da787d3 -- README.md plugin/README.md` is `1 1` for both): the gizmoduck catalog row, `README.md:875` and `plugin/README.md:415`, gains one clause naming the routine. No line shifted, and a script over every `README.md:N[-M]` citation in `.crew/codemap/` found none covering either line. `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 lines after it), and no note cites a `PLUGINS.md` line at or after `:441`. No claim re-read; nothing was executed for this note.

**Re-anchored `bbd9a66d` -> `8730119f` on 2026-09-29 (T-0107 merges origin/main `8ab733d7`). Current despite the lag.** `8730119f` merges origin/main (T-0010 landed, crew 1.0.61, main's anchor `bbd9a66d`) into `T-0107-build`; the conflicts were this header and the provenance tail, resolved mechanically - main's anchor taken, both sides' provenance kept, main's first. `git diff --numstat bbd9a66d 8730119f -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, still `README.md:875` and `plugin/README.md:415`, edited in place. No citation outside provenance covers either line, and `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 after it), where no note cites a line. Nothing was executed for this note.

**Re-anchored `6053b65d` -> `40292eca` on 2026-10-02 (T-0107 merges origin/main `ffd11270`, without rerere). Current despite the lag.** `40292eca` merges origin/main into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 6053b65d 40292eca -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, now `README.md:876` (main's side added a line above it) and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck is re-set to 0.5.4, one patch above main's 0.5.3, after the last content change. Nothing was executed for this note.

**Re-anchored `45bed356` -> `e60394fd` on 2026-10-02 (T-0107 merges origin/main `8d84786d`, without rerere). Current despite the lag.** `e60394fd` merges origin/main (W-0117, crew 1.0.115) into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `8d84786d`, `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 8d84786d e60394fd -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, still `README.md:876` and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `b4f04e23` -> `56f28a16` on 2026-10-02 (T-0107 merges origin/main `04dde5a2`, without rerere). Current despite the lag.** The header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `04dde5a2`, `git diff --numstat 04dde5a2 56f28a16 -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, edited in place (`README.md:889`, `plugin/README.md:415`). The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `56f28a16` -> `d6e51bb8` on 2026-10-02 (T-0107 merges origin/main `d2ec37d3`, W-0120's re-pin, without rerere; no conflict).** `git diff -U0 56f28a16 d6e51bb8 -- README.md` is main's two install-URL lines, `:12` and `:18`, re-pinned in place to `04dde5a2` (no line shifts); T-0107's gizmoduck catalog row is still `README.md:889` and `plugin/README.md:415`, unchanged. No body citation covers `:12` or `:18` here. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `6053b65d` -> `1066a28d` on 2026-10-01 (L-0575, the recurring-findings checklist for the implementer; `1066a28d` adds only refresh artifacts and the rebuilt daily-workflow guide HTML, DOCX and PDF to `dac06883`).** `git diff --name-only 6053b65d dac06883` returns `.crew/verify.json` (one rule appended, the last, `:454-464`), `CHANGELOG.md` (one Unreleased section, 18 lines), `docs/guides/crew/src/daily-workflow.md`, `plugin/crew/BUDGETS.md` (the count at `:11`), `plugin/crew/README.md` (one paragraph at `:727`), `plugin/crew/commands/fix.md` (step 4, one line), `plugin/crew/commands/implement.md` (step 2 and the method paragraph, still 120 lines), `plugin/crew/skills/crew-qa-standards/SKILL.md`, and three new files: `plugin/crew/hooks/scripts/recurring_findings.py`, `plugin/crew/skills/crew-qa-standards/references/recurring-findings.md` and `plugin/crew/tests/test_recurring_findings.py`. Each citation into a changed file was mapped with difflib from `6053b65d` to this tree; body citations are named below when one moved, and the citations inside earlier provenance notes were kept, because they describe their own trees. No suite was executed for this note. Body: the `/crew:implement` row of "Lifecycle commands" names step 2's checklist; no body citation moved.

**Re-anchored `1066a28d` -> `871c5043` on 2026-10-02 (L-0575 review round 1 fixes).** `git diff --name-only 1066a28d 871c5043` returns `.crew/verify.json` (the L-0575 rule's why, in place), `plugin/crew/BUDGETS.md` (the count at `:11`), `plugin/crew/README.md` (the L-0575 paragraph, in place), `plugin/crew/commands/implement.md` (step 2 re-wrapped in place, still 120 lines), `recurring_findings.py`, its data file and its suite. Each citation into a changed file was mapped with difflib from `1066a28d` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `b4f04e23` (main) and L-0575's `871c5043` -> `2859ab05` on 2026-10-02 (L-0575 merges origin/main 8d84786d at f12f742c and d2ec37d3 at 2859ab05, rerere disabled; crew 1.0.123. Both provenance histories kept, main's first. Body citations were mapped with difflib from the tree each line came from (4234c443 for L-0575's lines, d2ec37d3 for main's): ten CHANGELOG.md citations in crew.md moved +19 (L-0575's entry above main's); verification-harness.md's two verify.json ranges were set by hand to :448-453 (rule 41) and :455-465 (L-0575's rule); crew.md's version sentence reads 1.0.123. History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `b4f04e23` (main) and L-0575's `2859ab05` -> `99c8f66e` on 2026-10-02 (L-0575 merges origin/main 7ba4f9ea (L-0572 #309 crew 1.0.126, L-0593 #312) at 99c8f66e, rerere disabled; crew 1.0.129 is set in the last commit. Body citations were mapped with difflib from the tree each line came from (9dad04ef for L-0575's lines, 7ba4f9ea for main's): ten CHANGELOG.md citations in crew.md moved +21 (L-0572's entry, below L-0575's); verification-harness.md's verify.json ranges were set by hand to :469-476 (rule 41) and :486-496 (L-0575's rule, after L-0572's at :478-485). History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `d6e51bb8` (main) and L-0575's `99c8f66e` -> `273ec0f6` on 2026-10-02 (L-0575 merges origin/main a9b4734d (L-0576 #306 crew 1.0.128, L-0577 #305, T-0107 #273) at 273ec0f6, rerere disabled; crew 1.0.129 is re-set in the last commit. Both provenance histories kept, main's first. Body citations were mapped with difflib from the tree each line came from (986c9ca5 for L-0575's lines, a9b4734d for main's): ten CHANGELOG.md citations in crew.md moved +113 (main's new entries sit below L-0575's), and ten plugin/crew/README.md citations in crew.md and repo-docs.md moved +2 (L-0575's README paragraph at :727 sits above them); verification-harness.md's verify.json ranges were set by hand to :474-481 (rule 41), :483-490 (L-0572) and :491-501 (L-0575, last). History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `6053b65d` -> `3a33161c` on 2026-10-01 (L-0555 PR 1: the diagnostic CI verify-gate receipt - `plugin/crew/hooks/scripts/ci_receipt.py`, `.github/workflows/verify-gate.yml` (mmdc pinned at 12.0.0), `plugin/crew/tests/test_ci_receipt.py` - merging origin/main `ffd11270` (L-0557 #300, crew 1.0.114) at `751d6d2a` with rerere disabled, crew 1.0.116, skipping 1.0.115 claimed by another lane).** Refresh-artifact conflicts were resolved by taking main's side and redoing this pass. `git diff --name-only 6053b65d 3a33161c` outside refresh artifacts returns L-0555's paths only: the three new files, `.crew/verify.json` (one rule appended last, at `.crew/verify.json:481`), `CHANGELOG.md` (+16 lines at the top), `plugin/crew/README.md` (+23 lines in section 17), `scripts/gate-runner.py` (+2 lines in EXCLUDED_WORKFLOWS), `plugin/crew/BUDGETS.md` (count only) and the version files. A difflib re-map of every path-qualified citation into those files (history notes skipped) moved nine `CHANGELOG.md` citations in `crew.md` by +16 and six `plugin/crew/README.md` citations in `repo-docs.md` by +23; every other citation maps onto itself. No suite was executed for this note.


**Re-anchored `3a33161c` -> `79c116b4` on 2026-10-01 (L-0555 gate fix: `ci_receipt.py` asks `review_gate.gate_state` for NO_GATE instead of reading `.crew/config.json` itself; `plugin/crew/BUDGETS.md` count corrected; crew 1.0.116 re-set at `79c116b4`).** `git diff --name-only 3a33161c 79c116b4` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/BUDGETS.md` (the count line only, changed in place, so the `plugin/crew/BUDGETS.md:10` and `:11` citations keep their lines; the version files net to no change). No note cites `ci_receipt.py` at a line, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `79c116b4` -> `8b21ecc3` on 2026-10-01 (L-0555 pre-review fix: `ci_receipt.py` resolves gh with shutil.which and folds the check reason onto one line; crew 1.0.116 re-set).** `git diff --name-only 79c116b4 8b21ecc3` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py` (the version files net to no change). No note cites either at a line, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `8b21ecc3` -> `1e2762a0` on 2026-10-02 (L-0555 review round 1 fixes: `ci_receipt.py` requires the receipt's gate_impl to match HEAD's and its docstring says diagnostic; the verify.json rule is priced 10s from measured runs; crew 1.0.116 re-set).** `git diff --name-only 8b21ecc3 1e2762a0` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py`, `plugin/crew/tests/test_ci_receipt.py` and `.crew/verify.json` (the last rule's line edited in place, no line moved); the version files net to no change. Every citation maps onto itself. No suite was executed for this note.


**Re-anchored `1e2762a0` -> `b10e3895` on 2026-10-02 (L-0555 review round 2 fixes: `ci_receipt.py` treats an unreadable stand-down as UNKNOWN, re-reads the stand-down at the last look, and anchors the origin host to github.com; crew 1.0.116 re-set).** `git diff --name-only 1e2762a0 b10e3895` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py`; the version files net to no change. No code map cites a line of either file, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `b4f04e23` -> `fa63852d` on 2026-10-02 (L-0555 merges origin/main `dd95135a`, L-0578 #304, crew 1.0.119, at `fa63852d` with rerere disabled; crew 1.0.127).** The merge took main's anchor and INDEX rows and kept both lanes' re-anchor notes. L-0555's own change against main is `ci_receipt.py`, `test_ci_receipt.py`, `.github/workflows/verify-gate.yml`, `scripts/gate-runner.py`, one `.crew/verify.json` rule (line 454 edited in place, 455 appended), `plugin/crew/README.md` (+23 lines after `:2167`), `CHANGELOG.md` (+17 lines at the top) and the version and count lines. Citations moved by difflib: `CHANGELOG.md` +17 in `crew.md`'s current-citation lines, `plugin/crew/README.md` +23 past `:2167` in `repo-docs.md` (nine). No suite was executed for this note.


**Re-anchored `fa63852d` -> `f937576e` on 2026-10-02 (L-0555 merges origin/main `04dde5a2`, W-0120 #307, the claude- prefix renames, at `f937576e` with rerere disabled; crew 1.0.127).** Only `CHANGELOG.md` conflicted. Citations moved by difflib: this lane's `CHANGELOG.md` lines in `crew.md` +26 (W-0120's entry), `README.md:736` -> `:749` (three, in `repo-docs.md` and `install-scripts.md`) and `skills/README.md:15` -> `:28`. No suite was executed for this note.


**Re-anchored `f937576e` -> `af59b237` on 2026-10-02 (L-0555 merges origin/main `d2ec37d3`, W-0120 #308, README install URLs re-pinned to `04dde5a2`).** The merge changed `README.md:12` and `:18` in place; no line moved. The install-URL pin landmines in `install-scripts.md` and `repo-docs.md` now state the `04dde5a2` pin, and `git log --oneline 04dde5a2..af59b237 -- scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` is empty. No suite was executed for this note.


**Re-anchored `af59b237` -> `7e18daf8` on 2026-10-02 (L-0555 merges origin/main `c7a9e649`: L-0572 #309 (subset coverage under --all, crew 1.0.126), runner auto-start #295, L-0593 #312/#313; rerere disabled; crew 1.0.127).** Conflicts: version files, CHANGELOG (both entries, L-0555's on top), BUDGETS count, `.crew/verify.json` (L-0555's rule then L-0572's), `crew.md`'s version sentence, generated rules. Main's notes for L-0572 came in unchanged. Every main-side citation into a file this branch changes resolves to the same line (difflib), except one historical `CHANGELOG.md:1372` in a past-tense note, left as written. No suite was executed for this note.


**Re-anchored `d6e51bb8` (main) and `7e18daf8` (L-0555) -> `5467b110` on 2026-10-02 (L-0555 merges origin/main `75681fba`: L-0577 #305, T-0107 #273 (gizmoduck 0.5.5); rerere disabled; crew 1.0.127).** The header conflict took main's anchor and both sides' provenance notes, main's first; the install-URL pin bullet took main's equivalent wording. Citations moved by difflib: this lane's `CHANGELOG.md` lines in `crew.md` +86 (the entries main added). Main-side citations into files this branch changes resolve to the same text. No suite was executed for this note.


**Re-anchored `5467b110` -> `2594c90f` on 2026-10-02 (L-0555 merges origin/main `a9b4734d`, L-0576 #306, crew 1.0.128; rerere disabled; crew 1.0.132).** 11 citation(s) moved by difflib from `5467b110` to HEAD, each checked to cite the same line text (L-0576 shifted `plugin/crew/README.md` by two lines and `docs/guides/crew/src/troubleshooting.md` by five); citations written by L-0576 itself into this map are left as main has them.

**Re-anchored `2594c90f` (L-0555) and `273ec0f6` (main) -> `a81e4382` on 2026-10-02 (L-0555 merges origin/main `0487fc39`: L-0575 #311, crew 1.0.129, and L-0599 #315, gizmoduck 0.5.6; rerere disabled; crew 1.0.132 re-set after the merge).** The anchor, INDEX and provenance hunks conflicted: both sides' provenance was kept, main's first. Citation-number hunks took main's side. 10 citation(s) moved by difflib, each checked to cite the same line text: main-written lines mapped from `0487fc39`, L-0555-written lines from `c38be472`. A bare `:N` followed by "on <rev>" is history and was left alone, as were citations already stale on main.

**Re-anchored `a81e4382` -> `407f2b33` on 2026-10-02 (L-0587, repository tooling, no plugin version).** `git diff --name-only a81e4382 407f2b33` is main's own history to e0c70fc9 plus L-0587's three commits. L-0587 changes `scripts/install-prerequisites.sh:1675` and `scripts/_test/lsp-stack-tools.sh:7` in place (comment text only, no line added or removed), `.crew/verify.json` rules[3] in place (one command appended on the existing last `run` line, its `why` extended; no line added), adds `scripts/_test/shellcheck-directives.py`, one `_py_suite` TABLE row in `scripts/gate-runner.py` (after `version-drift`, +1 line at `:155`), one step in `.github/workflows/marketplace.yml` (+8 lines after the Shell syntax step) and a CHANGELOG entry (+23 lines near the top). No current citation in this map points into `scripts/gate-runner.py` or `marketplace.yml` past the insertion; the `CHANGELOG.md` line numbers in this map sit in past provenance paragraphs that record the tree they were read at, and are left as written. No claim in this note was re-derived; no suite was executed for this note.

**Re-anchored `407f2b33` -> `4fc93b19` on 2026-10-03 (L-0587 merges origin/main `ffeb0e2f`: L-0598 #321, crew 1.0.135; rerere disabled).** Main's side changes `plugin/crew/hooks/scripts/crew_standards.py` (one hunk at `:729`, +4 lines, in `proposals`) and `plugin/crew/skills/crew-qa-standards/references/review.md` (one hunk at `:40`, +2 lines), plus version files, CHANGELOG, BUDGETS and `crew.md`'s version sentence, which came in unchanged. The only current citations into `crew_standards.py` in these maps are `:145` and `:664`, above the hunk, so they stand; the larger numbers that mention it sit in past provenance paragraphs and are left as written. Only the generated `.claude/rules/crew.md` conflicted and was regenerated. No claim was re-derived; no suite was executed for this note.

**Re-anchored `a81e4382` -> `6475c41c` on 2026-10-02 (L-0592, L-0575's round-2 fixes to the recurring-findings checklist; origin/main `ffeb0e2f` merged first as a fast-forward, rerere disabled).** `git diff --name-only a81e4382 6475c41c` against this map's paths returns five files under the crew plugin: its README, the implement command, recurring_findings.py and two test modules (test_lifecycle_commands.py, test_recurring_findings.py). The README changes one line in place (727) and implement.md re-wraps step 2 in its same five lines (40-44), so no line moves; paths are named here without citation markup so this note does not shift the map's derived rule paths; no citation in this map points at a changed line or at recurring_findings.py or either test. No claim changed.

**Re-anchored `6475c41c` -> `35b9e6d9` on 2026-10-02 (L-0592 review round 1 fixes).** Of this map's paths only the test module test_recurring_findings.py changed (its render table made exhaustive); this map cites no line of it. No claim changed.

**Re-anchored `4fc93b19` (main, L-0587) and `35b9e6d9` (L-0592) -> `39ebbc18` on 2026-10-02 (L-0592 merges origin/main 6ac3b1b3, L-0587 #319 and #322; rerere disabled; crew 1.0.139).** Main's maps, INDEX and diagram were taken and L-0592's notes re-applied after main's. Since main's anchor, L-0592 changed five files under the crew plugin (README, the implement command, recurring_findings.py, two test modules) with no line moved, and main's re-pin changed two root README lines in place. No citation moved; no claim changed.

**Re-anchored `6053b65d` -> `17dc6d23` on 2026-10-01 (L-0574, built on origin/main `ffd11270`: `review_checks.py` and `review_run.py`'s `prereview_gate`, no plugin version yet).** Every citation into a file L-0574 changed (`review_run.py`, `commands/review.md`, `plugin/crew/README.md`, `.crew/verify.json` - which gained a top-level `preReview` block above `rules`, so every rule citation moved by 27 lines - `docs/external-tool-formats.md`, `tests/sabotage.py`, `tests/test_review_contracts.py`, `BUDGETS.md`, `CHANGELOG.md`, the lifecycle diagram) was mapped with difflib from `ffd11270` to `17dc6d23`; `BUDGETS.md:10-11` is the changed count line itself and keeps its number. The verify map still has 44 rules; `preReview` is read by `review_run.py`, not the Stop gate. The **Gate** paragraph now describes question 3, `prereview_gate`, between the verify gate and the standards self-check, and its bare `review_run.py` line numbers (stale since before this ticket) were re-read at `17dc6d23`.

**Re-anchored `17dc6d23` -> `8177fdff` on 2026-10-01 (L-0574 review round 1 and pre-round fixes).** The commits since changed `review_checks.py`, its tests, `sabotage_prereview.py`, `docs/external-tool-formats.md`, `BUDGETS.md`'s count line and `CHANGELOG.md`; the one citation into `review_run.py` that moved was re-mapped by difflib, and the **Gate** paragraph's bare line numbers were re-read at this anchor.

**Re-anchored `8177fdff` -> `3afec6e6` on 2026-10-01 (L-0574: noqa BLE001 on two boundary catches, same lines; difflib moved no citation).**

**Re-anchored `3afec6e6` -> `d640eba3` on 2026-10-01 (L-0574 round-2 fixes and the crew 1.0.122 bump; ten CHANGELOG citations moved +2 by difflib, the crew map's version sentence now reads 1.0.122).**

**Re-anchored `d640eba3` -> `d41c2c94` on 2026-10-01 (L-0574: a sabotage anchor re-targeted and the graph rebuilt; no cited line moved).**

**Re-anchored `d41c2c94` -> `1f5400df` on 2026-10-01 (L-0574 round-3 fixes; ten CHANGELOG citations moved +6 by difflib).**

**Re-anchored `1f5400df` -> `5143dbcd` on 2026-10-02 (L-0574 round-4 fixes and the merge of origin/main d2ec37d3: this branch's map text kept, main's re-anchor notes restored, citations into the eight files round 4 changed re-mapped by difflib from 1f5400df and the rest from 846cc465 onto the merge).**

**Re-anchored `5143dbcd` -> `ded603a7` on 2026-10-02 (L-0574: the gate's pylint findings fixed; no cited line moved).**

**Re-anchored `ded603a7` -> `a4ffe1de` on 2026-10-02 (L-0574 merges origin/main 7ba4f9ea, crew 1.0.126: citations into files main changed re-mapped by difflib, two verify.json:420 read by hand as :439).**

**Re-anchored `a4ffe1de` -> `18b764dc` on 2026-10-02 (L-0574: merge of origin/main 22292d63 (rerere disabled, scope re-based to it) and the round-5 fixes; ten CHANGELOG citations moved by difflib).**

**Re-anchored `18b764dc` -> `22aeb5a8` on 2026-10-02 (L-0574 round-7 class sweep: fifteen citations moved by difflib (review_run.py, CHANGELOG.md), two bare review_run.py citations re-read by hand).**

**Re-anchored `22aeb5a8` -> `9581933e` on 2026-10-02 (L-0574: external-tool-formats.md citation fix and the crew 1.0.131 re-set; no cited line moved).**

**Re-anchored `9581933e` -> `34c9a8bc` on 2026-10-02 (L-0574 merges origin/main 0487fc39 at bd459af7 (rerere disabled; both provenance histories kept, main's first) and fixes review round 7 at 4a35e5d2; citations re-mapped by difflib, bare review_run.py citations re-read by hand).**

**Re-anchored `34c9a8bc` -> `370a7a5b` on 2026-10-02 (L-0574 merges origin/main e0c70fc9 (L-0555 #310, #317, L-0597 #316; crew 1.0.134) at 370a7a5b, rerere disabled: both provenance histories kept (main's first), citations into files either side changed re-mapped by difflib (67 moved), the verify.json heading corrected to 48 rules).**

**Re-anchored `370a7a5b` -> `e2c11c0b` on 2026-10-02 (L-0574 review round 8 fixes at 0f5d76e7 (review_checks.py, review_run.py, CHANGELOG, external-tool-formats.md; install-scripts.md gains an explicit paths: line); citations re-mapped by difflib, bare review_run.py citations re-read).**

**Re-anchored `e2c11c0b` -> `0891d6a6` on 2026-10-02 (L-0574 merges origin/main ffeb0e2f (L-0598 #321, crew 1.0.135; crew_standards.py proposals and references/review.md, which this map cites by name only) at 26d2c1c0, rerere disabled, then fixes review round 9 at c7e4c87f; citations re-mapped by difflib).**

**Re-anchored `0891d6a6` -> `4dcad808` on 2026-10-02 (L-0574 merges origin/main 6ac3b1b3 (L-0587 #319 ShellCheck directive fixes, README re-pin #322; crew 1.0.135) at 4dcad808, rerere disabled: both provenance histories kept (main's first), citations re-mapped by difflib).**

**Re-anchored `4dcad808` -> `819a2d2b` on 2026-10-02 (L-0574: three test_review_checks.py cases made to pass on a real Windows host (PR #323 CI); citations re-mapped by difflib).**

**Re-anchored `819a2d2b` -> `d95d8b25` on 2026-10-02 (L-0574 merges origin/main 2a2d6e07 (L-0592 #325, crew 1.0.139: recurring_findings.py, implement.md step 2 re-wrapped in place, README) at d95d8b25, rerere disabled: both provenance histories kept (main's first), citations re-mapped by difflib; crew is set to 1.0.140).**

**Re-anchored `0c3508e9` -> `963d2905` on 2026-09-30 (L-0510: review closure, a final 0-BLOCK round auto-accepts, crew 1.0.90).** `git diff --name-only 0c3508e9 963d2905` returns, outside refresh artifacts, main's L-0561 README repin and L-0510's files (review_ledger.py, review_run.py, crew_autopilot.py, review.md, done.md, autopilot.md, README.md, CONFIG.md, BUDGETS.md, PLUGINS.md, the troubleshooting guide, CHANGELOG.md, two tests, sabotage_review.py and the version files); path-qualified citations outside dated provenance checked by a line diff: citations into crew_autopilot.py, review_ledger.py, review_run.py, done.md and autopilot.md re-derived by symbol (several were already stale at `0c3508e9` and are corrected to the definition they name), and a DERIVED review-closure paragraph added. No suite was executed for this note.

**Re-anchored `963d2905` -> `bee8b203` on 2026-09-30 (L-0510 suite fixes, crew re-bumped to 1.0.93).** `git diff --name-only 963d2905 bee8b203` returns, outside refresh artifacts, `sabotage_review.py` (one row's find string), `plugin/crew/docs/external-tool-formats.md` (four `review_run.py` citations), CHANGELOG.md and the version files; a body-only line diff moved no citation here (`docs/diagrams/data-flow-crew-config.mmd:1-2` is its re-written header, still lines 1-2). The review-closure paragraph's version now reads 1.0.93. No suite was executed for this note.

**Re-anchored `bee8b203` -> `52e309cf` on 2026-10-01 (L-0510 review fix round, crew re-bumped to 1.0.94).** `git diff --name-only bee8b203 52e309cf` returns, outside refresh artifacts, `review_ledger.py` (the per-severity count check, the CLEAN receipt-kind check and `check_follow_up`'s kind allowlist, UTF-8 refusal and verbatim counted match), its tests and sabotage rows, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/review.md`, `plugin/crew/BUDGETS.md`, the troubleshooting guide and its rendered outputs, CHANGELOG.md and the version files. The body's `review_ledger.py` citations and the `done.md` ranges were moved by a line diff (the bare `:478` beside `crew_ticket` was left alone, it is not a `review_ledger.py` line), and the review-closure paragraph's version now reads 1.0.94. No suite was executed for this note.

**Merged `490f4ec1` (L-0510) + `52489039` (main) on L-0510-build, 2026-10-01 (merge `58fc8da8` of origin/main `52489039`: T-0040 #290, crew 1.0.98, with rerere off), then re-anchored to `5254bbfe` (L-0510 re-bumped to crew 1.0.103).** The code paths are disjoint: main touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, and L-0510 touched none of T-0040's files. The anchor and the provenance tail conflicted in every map (both sides' provenance kept, main's first); `crew.md`'s T-0087 refund paragraph keeps L-0510's `review_run.py` / `review_ledger.py` / `crew_autopilot.py` positions with main's `plugin/crew/hooks/scripts/crew_status.py:140`, and `repo-docs.md`'s runbooks-index citation was re-grepped on the merged tree (`plugin/crew/README.md:2287`). Every body `path:line` into a file either side changed was checked against the parent whose copy of the map carries that line verbatim, by a line diff of that file onto the merged tree (`/root/crew-tmp/l-0510/tools/merge_cites2.py`, machine-local): none moved. `5254bbfe` itself changes only release bookkeeping (version files, CHANGELOG, BUDGETS count). No suite was executed for this note.

**Re-anchored `5254bbfe` -> `a98be035` on 2026-10-01 (L-0510, owner decision 2026-10-01 #3: the family rule).** `git diff --name-only 5254bbfe a98be035` returns `review_ledger.py`, its two test files and `sabotage_review.py`, `commands/review.md`, README, CONFIG, PLUGINS.md, BUDGETS.md, CHANGELOG, the troubleshooting guide and its three outputs, and refresh artifacts. Line counts are unchanged in every file except `review_ledger.py` (+37, cited only in `crew.md`, re-read there), CONFIG.md (+1 at `:2510`, past every CONFIG citation in these maps) and CHANGELOG.md (+3 at `:21`; the CHANGELOG line numbers in these maps are history notes of earlier anchors, not re-cited).

**Merged `a98be035`/`8c82f974` (L-0510) + `5ffffbe3` (main) on L-0510-build, 2026-10-01 (merge `d4193b70` of origin/main `2906dcbd`, crew 1.0.110, rerere off), then re-anchored to `8f0df4ca` (L-0510 re-bumped to crew 1.0.112).** Both provenance blocks are kept above, main's first. Main touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, so every L-0510 citation reads as L-0510 drew it, except `review_ledger.py`, which L-0510's review round 3 FIX 2 (`8c82f974`: `_receipt_names_the_reviewer`) grew by 10 lines below `:590`; `crew.md`'s citations of it were re-read with `grep -n '^def '` on the merged tree and moved (`check_receipt` `:691`, `check_follow_up` `:620`, `continue_with_successor_plan` `:742`, `summary` `:781`). Main's citations are main's, unchanged by L-0510's side.

**Re-anchored `8f0df4ca` -> `39e1237a` on 2026-10-02 (L-0510 review round 4 fixes, owner decision 2026-10-01 #5).** `3181121c` changed `review_ledger.py` (`_auto_row_problem` +6 lines: the embedded line-break refusal; `check_follow_up` +3: newline-only split), `commands/autopilot.md` (one sentence extended in place, line count unchanged) and the L-0510 tests; `00450ce0` CHANGELOG and README text; `fb33f9dc`/`39e1237a` un-set and re-set crew 1.0.112. `crew.md`'s `review_ledger.py` citations were re-read with `grep -n '^def '` and moved (`receipt_stands` `:596`, `check_receipt` `:700`, `_receipt_names_the_reviewer` `:618`, `auto_accept_refusal` `:528`, `auto_accept` `:562`, `check_follow_up` `:626`, `continue_with_successor_plan` `:751`, `summary` `:790`, `load` `:787`). No other note cites a moved line.

**Merged `39e1237a`/`ecc76d10` (L-0510) + `6053b65d` (main, L-0557 #300) on L-0510-build, 2026-10-02 (merge `122fc10d` of origin/main `ffd11270`, crew 1.0.114, rerere off), then re-anchored to `6ffb589d` (L-0510 at crew 1.0.121).** Both provenance blocks are kept above, main's first. L-0557 touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`. L-0510's own changes since `39e1237a`: `156882d2` (decision #6: `_auto_row_problem` +12 lines, `_review_json_problem` new at `:578`, `auto_accept` +3) and `ecc76d10`/`7d32fbc6` (docs and the rebuilt troubleshooting guide); `crew.md`'s `review_ledger.py` citations were re-read with `grep -n '^def '` and moved (`receipt_stands` `:641`, `check_receipt` `:745`, `auto_accept` `:604`, `check_follow_up` `:671`, `continue_with_successor_plan` `:796`, `summary` `:835`). Main's citations are main's.

**Merged `979ea023` (L-0510) + `8d84786d` (main: T-0503 #270 bitbucket 1.2.3, W-0117 #302 crew 1.0.115) on L-0510-build, 2026-10-02 (merge `9f39dd61`, rerere off, owner decision #9), anchored at `9f39dd61`.** Both provenance blocks are kept above, main's first. Neither T-0503 nor W-0117 touched `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, so L-0510's citations read as L-0510 drew them at `e7227a2b` (`receipt_stands` `:644`, `check_receipt` `:748`, `auto_accept` `:607`, `_review_json_problem` `:578`, `check_follow_up` `:674`, `summary` `:838`). Main's citations are main's.

**Merged L-0510 (`553f4aa0`, the UTF-8 console fix) + `04dde5a2` (main: L-0578 #304 crew 1.0.119, W-0120 #307) on L-0510-build, 2026-10-02 (merge `41aa4e2a`, rerere off, standing go #9), anchored at `2b372b84`.** Both provenance blocks are kept above, main's first. L-0578 changed `review_run.py` (the metrics row) and `commands/review.md` step 6; every `review_run.py` citation in this note was re-derived on the merged file by difflib from each parent and read with `sed -n` (preflight `:555`, called at `:642`; `--provider` `:739`; `finish`'s parts `:438`/`:440`; `failure_class` `:458`; refund lines `:508`/`:511`; `_webtest_open` `:412`; `auto_accept_line` `:421`). `review_ledger.py` gained `utf8_stdio` after `summary` (`:838`), so no earlier citation moved.

**Re-anchored `2b372b84` -> `252dd5d4` on 2026-10-02 (L-0510 review round 6 fixes, owner decision #10; merge `24f3ec25` of origin/main `d2ec37d3`, README only).** `d551680c` changed `review_ledger.py` (`read_review_json` `:599` and `_receipt_binds_review_json` `:721` new, `receipt_stands` gained `root, ticket`, `hashlib` imported, docstring +5), `crew_autopilot.py` (one line edited in place), `commands/review.md` (step 3 quoted in place), the L-0510 tests, CHANGELOG and README. `crew.md`'s `review_ledger.py` citations were re-read with `grep -n` by name (`receipt_stands` `:695`, `check_receipt` `:819`, `auto_accept` `:655`, `check_follow_up` `:742`, `summary` `:909`, `BUDGET` `:132`, `REFUND_LIMIT` `:135`). No other note cites a moved line.

**Re-anchored `252dd5d4` -> `97b65952` on 2026-10-02 (L-0510, merge `48cf52dd` of origin/main `7ba4f9ea`, crew 1.0.126 -> 1.0.130).** Main brought L-0572's `verify-gate.sh`/`.ps1`, `verify_record.py`, CONFIG.md and its own codemap edits; it touched none of the files L-0510's citations name (`review_ledger.py`, `crew_autopilot.py`, `review_run.py`, `commands/review.md`, `commands/autopilot.md`), so no L-0510 citation moved; L-0572's citations were written against main and carried by the merge unchanged.

**Re-anchored `273ec0f6` (main) and L-0510's `97b65952` -> `d05b0211` on 2026-10-02 (L-0510 merges origin/main `0487fc39` (L-0599 #315, crew 1.0.129; L-0576, L-0577, T-0107, L-0575 before it) at `ec508e5e`, rerere off; crew 1.0.130 set last at `d05b0211`).** Both provenance histories kept, main's first. In `crew.md` the `review_ledger.py`, `review_run.py` and `review_verdict.py` citations were re-derived on the merged files by function name (`grep -n '^def '`) and difflib from the tree each line came from: L-0510's ledger lines moved +14 (L-0576's `_ignored_count` and `record` row above them), `review_run.py`'s preflight `:563`/`:650`, provider list `:747` and refund lines `:517`/`:520`, `review_verdict.py`'s `VERDICTS`/`FINDING_FORM`/class names `:90`/`:93`/`:95`; main's L-0576 paragraph's three stale lines set to `review_run.py:447`, `:467`, `:513` and `review_ledger.py:394`. One L-0510 sentence that said the field was not written now says L-0576 writes it. Other maps: no cited line moved. History notes were not re-mapped.

**Re-anchored `a81e4382` (main) and L-0510's `d05b0211` -> `77e8dcfd` on 2026-10-02 (L-0510 merges origin/main `e0c70fc9` (#317, L-0597 #316, L-0555 #310; crew 1.0.134) at `e6dc6b1b`, rerere off; crew 1.0.137 set last at `77e8dcfd`).** Both provenance histories kept, main's first. Main touched none of `review_ledger.py`, `review_run.py`, `review_verdict.py`, `crew_autopilot.py`, `review.md` or `autopilot.md`; `crew.md`'s `crew_autopilot.py` `questions_check` `:1246` / `QUESTIONS_SHAPE` `:1154` are L-0510's merged-file lines (main's side read `:1232` / `:1140` without L-0510's autopilot change); `repo-docs.md`'s README citation is `:2314` on the merged README (L-0555 +23). History notes were not re-mapped.

**Re-anchored `4fc93b19` (main) and L-0510's `77e8dcfd` -> `96a69068` on 2026-10-03 (L-0510 merges origin/main `bd3e9ad1` (L-0598 #321, L-0587 #319; crew 1.0.135) at `d3f26a4b`, rerere off; crew 1.0.137 set last at `96a69068`).** Both provenance histories kept, main's first. Main touched no file L-0510's citations name; L-0510's `c86365ee` (a test helper) moves no cited line. History notes were not re-mapped.

**Re-anchored `39ebbc18` (main) and L-0510's `96a69068` -> `a06dd790` on 2026-10-03 (L-0510 merges origin/main `2a2d6e07` (L-0592 #325, L-0587 re-pin #322; crew 1.0.139) at `39c290be`, rerere off; crew 1.0.142 set last at `a06dd790`).** Both provenance histories kept, main's first. Main touched no file L-0510's citations name (its README edit is one line, no cited line moved). History notes were not re-mapped.

**Re-anchored `d95d8b25` (main) and L-0510's `a06dd790` -> `b8d09685` on 2026-10-03 (L-0510 merges origin/main `8123fe74` (L-0574 #323; crew 1.0.140) at `8c04c783`, rerere off; crew 1.0.142 set last at `b8d09685`).** Both provenance histories kept, main's first. In `crew.md` main's L-0574 `review_run.py` citations were re-derived on the merged file (L-0510 adds 8 lines above `finish` and 28 through it): by difflib, and by name for `prereview_gate` `:731` (called `:857`), `standards_gate` `:699` (at `:859`) and `review_ledger.reserve` `:863`, which main's side had stale; L-0510's `review_ledger.py` citations are unchanged. `verification-harness.md`'s `sabotage.py` citations moved +1 (main's import at `:87`; main's side had them stale). History notes were not re-mapped.

**Re-anchored `b8d09685` -> `452b30cc` on 2026-10-03.** `204e813b` routes `review_run.finish`'s auto-accept line through `_out` (main's L-0574 one-writer test), one line, no line count change, so no citation moved; `452b30cc` re-sets crew 1.0.142 last.

**Re-anchored `452b30cc` -> `f808e5f0` on 2026-10-03 (L-0600, a correction of this map's body citations on main at crew 1.0.154, #330; refresh artifacts only, no plugin version).** Earlier re-anchors advanced the anchor through drift they did not re-point, so this pass re-checked the whole body (everything above "Re-anchor provenance - `6c497a14` -> `f2bb919b`"), not one lane's paths. Every `path:N` and bare `:N` citation was compared, by script, with the line it named in the commit that last wrote it (`git blame`), and separately with the hand-read result of the unmerged L-0576-reanchor-v2 pass (at `a9b4734d`), mapped forward to this tree with difflib; the file behind each bare `:N` was taken from the sentence's symbol, not the nearest file name. Each re-point was then read against the symbol or block it names. 257 body citations changed and 9 were added: 231 re-pointed to moved lines (nearly all whole-function shifts in crew_config.py, crew_config_files.py, crew_autopilot.py, crew_tracker.py, crew_refresh_check.py, verify-gate.sh, review_run.py, review_ledger.py, crew_standards.py and the implement and fix commands), among them two the v2 pass missed (`:2784`, `:2964` in crew_config.py) and four in L-0510's review-closure paragraph and the Kimi note (`_webtest_open` `:514`, `auto_accept_line` `:523`, `PROVIDERS` `:941` in review_run.py, the approve stop `:479` in crew_autopilot.py); the rest are in claims corrected rather than re-pointed. Corrected: `.crew/verify.json` rule numbers from rule 10 on are one higher than this map said, because L-0516 inserted rule 10, and L-0577, L-0557, L-0555, L-0572, L-0575 and crew 1.0.140 added rules 42, 43, 45, 46, 47 and 48, so T-0040's shell-route rule is 44 and is no longer the last (the rule list under the routing section is restated, every span 27 lines lower than at `2a2d6e07`, where L-0574's `preReview` block now sits above the rules); `SHELL_MUTATIONS` is registered in sabotage.py again since W-0115 (`59c86b7c`); the L-0576 entry gains `/crew:review`'s side (review.md 482-486 and 498-500). Lines that state a position at a named commit ("`:1109` on T-0094's branch", "`:3854` at `6c497a14`", "`:376-381` on the merge", "its `:246` at `d7c7c75c`", which was right at the commit that wrote it) are history and were left as written, and so were the provenance sections below. Not done: no claim outside a citation was re-derived from scratch beyond the review flow, the verify.json rules and the shell mutations. Run: see the PR for the verify-gate pass at this commit.

**Re-anchored `39ebbc18` -> `238e326a` on 2026-10-03 (L-0601, the recurring-findings checklist in the review prompt).** Changed since the anchor: review_prompt.py (an import and a docstring bullet move every later line down five; the crew map's five current citations into it were moved by matching their text), verify.json (the recurring-findings rule, last in the file, grew two lines: 492-504), sabotage.py (an import after the cited ones), the new sabotage_recurring.py, test_review_prompt.py, review.md (one comment re-wrapped in place), the crew README (one line in place) and the working-with-codex guide. The crew map's Checklist bullet and the verification-harness map's rule line describe the new block; no other claim changed.

**Re-anchored `d95d8b25` (main, L-0574) and `238e326a` (L-0601) -> `6a2869bd` on 2026-10-03 (L-0601 merges origin/main 8123fe74, L-0574 #323; rerere disabled; crew 1.0.141).** Main's maps, INDEX and diagram were taken and L-0601's edits re-applied: the crew map's Checklist bullet and version sentence, its five review_prompt.py citations moved by five (an import and a docstring bullet above them), and the verification-harness map's recurring-findings rule line (now 519-530, two paths and one suite added). Other L-0601 changes (sabotage.py import after the cited lines, review.md and the crew README in place, the guide) move no cited line. No other claim changed.

**Re-anchored `6a2869bd` -> `38975c7a` on 2026-10-03 (L-0601: sabotage_recurring.py reads its data section with newline translation, the Windows CI fix).** Only that test helper changed; this map cites no line of it. No claim changed.

**Re-anchored `452b30cc` (main) and L-0601's `8d5134b5` -> `0620587f` on 2026-10-03 (L-0601 merges origin/main f808e5f0: L-0510 #318, #328, #329, #330, crew 1.0.154; rerere disabled; crew 1.0.162 set last).** Main's maps were anchored at `452b30cc` while main changed 34 more files after it; their citations into those files were moved by difflib from `452b30cc` to the merge (78 moved; 17 whose line itself changed were moved by the offset of the line above and each checked to cite the same construct, e.g. `verify_record.py` `tree_snapshot`, `review_run.py` `--provider`, the rules' `why` lines). L-0601's own edits were re-applied after main's text. Main's claims about #328-#330 were not re-derived; no suite was executed for this note.

**Re-anchored `f808e5f0` (main, L-0600) and L-0601's `3e53c568` -> `42effe14` on 2026-10-03 (L-0601 merges origin/main 34d9f267: L-0600 #332, L-0618 docs #335; rerere disabled; crew 1.0.162 kept).** Main changed no code after `f808e5f0`, only this map, INDEX, the lifecycle diagram, the generated rules and docs/review. Main's map, with L-0600's citation correction, was taken whole; its citations into files L-0601 changed were moved by difflib from main to the merge (17 moved: review_prompt.py by five, CHANGELOG.md by thirteen for L-0601's entry, sabotage.py by one; plugin.json:3 and PLUGINS.md:14 are the version lines, which L-0601 rewrote in place). L-0601's version sentence and Checklist bullet were then re-applied, and its four provenance notes above were carried over after main's. No claim of L-0600's was re-derived; no suite was executed for this note.

**Re-anchored `42effe14` -> `174b6613` on 2026-10-04 (T-0047, the round-8 terraform guard spellings).** Changed since the anchor, among the paths this map cites: `cloud_guard.py` (the PowerShell lexer marks `called`/`opens`, `_unwrap` reads listed wrappers through `crew_guards.wrapper_rest`; still 3380 lines) and `crew_guards.py` (the wrapper tables, `GateFed`, `unwrap_listed`, `_TF_GLOBAL_FLAG_OPTS`, `_selects_only`, and the PowerShell trigger's unwrap and expression rule, 1887 -> 2170 lines). The literal-word allowlist paragraph was re-taken by content (`grep -n` at `174b6613`) and describes the new reading; the environment-layer paragraph's `_terraform_verdict` moved one line. The earlier citations into `crew_guards.py` above `:1206` did not move. Other paths changed since `42effe14` came in with origin/main and were not re-derived here.

**Re-anchored `174b6613` -> `c642a355` on 2026-10-04 (T-0047, first review of #347).** `cloud_guard.py` (3380 -> 3381 lines: the PowerShell lexer's call rule, `sem`, `tg_other_op`'s call, the fed `workspace select` in `_fed_finding`) and `crew_guards.py` (2170 -> 2250: `ps_eval_script`, `tg_other_op`, the fed-select branch) changed; the allowlist paragraph's citations were re-taken by content (`grep -n` at `c642a355`). No other claim changed.

**Re-anchored `c642a355` -> `30f25211` on 2026-10-04 (T-0047, second review of #347).** `cloud_guard.py` (3381 -> 3385 lines: `_Cmd.groups`, the lexer's assignment slot, `terragrunt exec` unwrapped in `_unwrap`) and `crew_guards.py` (2250 -> 2324: `_ps_backstop`/`_ps_unplain`, `ps_head_slot`, `tg_exec_rest`, `tg_other_op`'s stack/backend reading) changed; the allowlist paragraph's citations were re-taken by content (`grep -n` at `30f25211`). origin/main `baf193aa` (merged at `ee9dbe81`) changed none of this paragraph. No other claim changed.

**Re-anchored `30f25211` -> `5a13ff97` on 2026-10-04 (T-0047, second review, sabotage follow-through).** Only `crew_guards.py` changed (2324 -> 2325: the backstop also flags a bare array; two subsumed checks removed); the allowlist paragraph's citations were re-taken by content. No other claim changed.

**Re-anchored to `51b2222b` on 2026-10-03 (T-0066, crew 1.0.185: `git.forbiddenTrailers` and the `/crew:done` trailer report; `51b2222b` merges origin/main `4f6ef540`, crew 1.0.162, into `T-0066-build`).** Main's maps were taken at the merge and T-0066's edits re-applied on them. T-0066 changes, among the paths these maps cite: `.crew/verify.json` (one rule appended, `:539-546`), `plugin/crew/CONFIG.md` (section 10/11 headings, one section 10 row, new section 22), `plugin/crew/commands/done.md` (a report section after check 4, `:68-79`), `plugin/crew/commands/implement.md` (step 2 `:46-52`; still 120 lines), `plugin/crew/hooks/scripts/crew_config.py` (the `git` block, +6 after main's `:380` and +4 after its `:595`), `plugin/crew/skills/crew-setup/SKILL.md`, the two templates, `plugin/crew/tests/test_crew_config.py`, the new `crew_trailers.py` and its suite, and release bookkeeping (`CHANGELOG.md`, `TODO.md` +11 at `:241`, `plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, both version files). Body `path:N` citations into those files were re-mapped by a difflib line diff from main `4f6ef540` to the merged tree; a bare `:N` was re-mapped only where T-0066's earlier pass (`f7fd2e78`) had read the sentence and applied it. History notes were not re-mapped. No other claim was re-derived and no suite was executed for this note.

**Re-anchored `5a13ff97` (and main's `51b2222b`) -> `e2d2f9f0` on 2026-10-04 (T-0047, third review of #347, merging origin/main `86d96fa1`).** Only `crew_guards.py` changed among this paragraph's paths (2325 -> 2422: the shape backstop replaced by `_ps_accounted`/`_ps_backstop`, `graph run`); main changed neither guard file. The allowlist paragraph's citations were re-taken by content at `e2d2f9f0`; main's own re-anchor note above stands for the paths T-0066 changed.

## Shell and PowerShell repo-config readers in a linked worktree (T-0096, slice 0)

Added 2026-10-04 on `T-0096-build`; the citations are to that branch's content
commit. This section does not move the file's `anchor:`.

- **DERIVED.** `crew_repo_config_dir` (`plugin/crew/hooks/scripts/_common.sh:365`)
  sets `CREW_CFG_DIR` / `CREW_CFG_SOURCE` (`own`, `main`, `unknown`) by the rules of
  `crew_common.repo_config_dir` (`plugin/crew/hooks/scripts/crew_common.py:96`), with no
  python; `crew_repo_config_file` (`plugin/crew/hooks/scripts/_common.sh:391`) prints a
  resolved path. The PowerShell twin `Get-CrewRepoConfigDir` is one body copied into
  `plugin/crew/hooks/scripts/cloud-guard.ps1:192`, `plugin/crew/hooks/scripts/promote-gate.ps1:142`
  and `plugin/crew/hooks/scripts/auto-clear.ps1:132`.
- **DERIVED.** Routed readers: `crew_incident_active`'s `standDown` read
  (`plugin/crew/hooks/scripts/_common.sh:460`), `_cloud_guard_armed`
  (`plugin/crew/hooks/scripts/cloud-guard.sh:40-53`, a missing resolver armed at `:42`, `unknown` at `:44`),
  `Test-CloudGuardArmed` (`plugin/crew/hooks/scripts/cloud-guard.ps1:248-249`),
  promote-gate's `Test-CrewIncidentActive` (`plugin/crew/hooks/scripts/promote-gate.ps1:201`)
  and `auto-clear.ps1`'s `$repoCfg` (`plugin/crew/hooks/scripts/auto-clear.ps1:374`).
  `.crew/incident.json`, markers and logs stay in the worktree's own `.crew/`.
- **DERIVED.** Held by `plugin/crew/tests/test_worktree_config_shell.py`: parity with the
  Python resolver on ten cases per flavour, the copies byte-identical, the cloud-guard
  fallback's must-block / must-allow cases, the stand-down and the auto-clear veto.
- **JUDGEMENT.** Still own-file only, and the next two slices: the session hooks
  (L-0680) and the harness readers `verify-gate.*`, `scope-guard.*`,
  `completion-audit.*`, `review_gate.py` (L-0681, a tooling PR). Until L-0681,
  `verify-gate.ps1`'s inline `Test-CrewIncidentActive` reads the lane's own
  `standDown` while the bash gate (through `_common.sh`) and `crew_incident.py` read
  the inherited one.

## The session hooks read the resolved repo config (L-0680, slice 1)

Added 2026-10-04 on `L-0680-build`, stacked on `T-0096-build`; the citations are
to that branch's content commits. This section does not move the file's `anchor:`.

- **DERIVED.** Each `.sh` hook calls `crew_repo_config_dir .` after its `cd` and reads
  `$CREW_CFG_DIR/config.json`: `plugin/crew/hooks/scripts/notify.sh:11`,
  `plugin/crew/hooks/scripts/handoff-read.sh:49`, `plugin/crew/hooks/scripts/handoff-write.sh:16`,
  `plugin/crew/hooks/scripts/context-watch.sh:180` (after the `.crew/` directory gate, which
  stays). Python is handed the path as an argument; context-watch's no-python awk pass reads the
  same file.
- **DERIVED.** Each `.ps1` hook carries a verbatim `Get-CrewRepoConfigDir` (now seven copies, held
  equal by `PS_COPIES`, `plugin/crew/tests/test_worktree_config_shell.py:45`) and routes through
  it: `plugin/crew/hooks/scripts/notify.ps1:345`, `plugin/crew/hooks/scripts/handoff-read.ps1:320`,
  `plugin/crew/hooks/scripts/handoff-write.ps1:388`, `plugin/crew/hooks/scripts/context-watch.ps1:434`.
  `notify.ps1` run with `&` from `context-watch.ps1` gets its own script scope, so its copy only
  shadows the caller's identical one.
- **JUDGEMENT (T-0051, batch 8).** The two bullets above no longer hold for notify:
  T-0051 made `notify.sh` and `notify.ps1` thin wrappers around `crew_notify.py`, so
  `notify.ps1` carries no `Get-CrewRepoConfigDir` (six copies remain, `PS_COPIES` in
  `plugin/crew/tests/test_worktree_config_shell.py` names notify.ps1's removal) and
  `crew_notify.py` reads the config itself. Its dedupe state is written to
  `<git-common-dir>/crew/notify`, shared by every worktree, not kept in the lane. The
  `notify.*` line cites above are pre-T-0051 and were not re-derived.
- **DERIVED.** handoff-write keeps the literal own-or-unknown gate in its non-`main` branch
  (`plugin/crew/hooks/scripts/handoff-write.sh:23`, `plugin/crew/hooks/scripts/handoff-write.ps1:396`):
  there the resolved directory is the own `.crew/`, and `plugin/crew/tests/sabotage_resume.py`
  (a harness path) anchors on that text. `handoff-write.ps1:484` accepts an Int64 or
  BigInteger `keepTranscripts` (PowerShell 7's `ConvertFrom-Json`), clamped to Int32.MaxValue as
  bash's one-liner clamps it; both flavours take an integer only (review rounds 1-2).
- **DERIVED.** context-watch's messages name the file in force: `CFG_SHOWN`
  (`plugin/crew/hooks/scripts/context-watch.sh:182`) and `$cfgShown`
  (`plugin/crew/hooks/scripts/context-watch.ps1:436`) are `.crew/config.json` for an own file and
  the main checkout's full path when inherited.
- **DERIVED.** `test_no_session_hook_names_the_own_config_path`
  (`plugin/crew/tests/test_worktree_config_shell.py:892`) fails on any executable line in the
  eight scripts naming `.crew/config.json` or `.crew/crew.json` beyond `OWN_PATH_ALLOWED` (`:869`).
- **DERIVED.** The handoff path stays inside the checkout (review round 1, B1): bash through
  `crew_handoff_path` (`plugin/crew/hooks/scripts/_common.sh:405`), which calls
  `crew_state.handoff_path`, and context-watch's own read (`plugin/crew/hooks/scripts/context-watch.sh:354`);
  PowerShell through `Get-CrewHandoffPath`, three byte-identical copies
  (`plugin/crew/hooks/scripts/handoff-read.ps1:235`, `plugin/crew/hooks/scripts/handoff-write.ps1:335`,
  `plugin/crew/hooks/scripts/context-watch.ps1:78`), stricter on links. An inherited absolute or
  `..` value, or one naming a directory, is the lane's `.work/HANDOFF.md`, with a warning, and
  the path is printed with forward slashes on every OS (a Windows pre-flight read `.work\HANDOFF.md`);
  context-watch's message, both flavours, says the configured path leaves the checkout. The `.ps1`
  copies turn `\` into `/` before the check off Windows, since PowerShell's file cmdlets read it as
  a separator there too (review round 3). Held by
  `plugin/crew/tests/test_worktree_config_shell.py:745` and its two siblings.
- **JUDGEMENT.** Still own-file only: the harness readers `verify-gate.*`, `scope-guard.*`,
  `completion-audit.*`, `review_gate.py` (L-0681, a tooling PR).

**Re-anchored `42effe14` -> `69de978c` on 2026-10-04 (T-0041 feature half, crew version set at landing, after merging origin/main into T-0041-build).** `69de978c` changes .crew/verify.json, plugin/crew/README.md, plugin/crew/agents/{explorer,researcher,security}.md, plugin/crew/commands/{done,debug}.md, plugin/crew/hooks/scripts/_test/validate-prompts.py, plugin/crew/skills/{crew-best-practices,crew-brainstorm,crew-plan}/SKILL.md and the new plugin/crew/tests/test_verify_before_stating.py: inserted lines only, plus `**Unverified**` renamed in place in researcher.md, the crew-best-practices description (`:3`) and `.crew/verify.json:554` gaining a comma before a rule appended last. Every body citation of the form `<changed file>:N` in this note was listed by script against each file's first inserted line (verify.json 554, README 2804, explorer 55, researcher 70, security 143, debug 95, done 86, validate-prompts 106, crew-best-practices 76, crew-brainstorm 41, crew-plan 73); every hit was a line number of another file or a dated provenance position, so no body citation moved. One body fact is new and not yet written into the sections above: `validate-prompts.py` now also runs `check_verification_rule()` (`plugin/crew/hooks/scripts/_test/validate-prompts.py:345`, called from `main` at `:381`), which fails when an `agents/*.md` (reviewer exempt by name at `:116`) or `crew-best-practices` loses "Verify before you state", or when explorer, researcher, security, `done.md` or `debug.md` loses its `**Not verified` report section (DERIVED, read at this anchor). No suite was executed for this note.

**L-0582 (2026-10-04, on `62889e15`, the merge of origin/main `ce235468`; the crew version is set at landing).** Only the `.crew/metrics.md` writers bullet was re-derived, at the commit adding this note, by reading the four cited functions. The anchor stays `42effe14`: the rest of this map was not re-verified against the files main changed since, so moving it would claim a check nobody ran. Batch 6 merge: the `crew_common.py` and `crew_status.py` citations in that bullet were re-taken by content on the merged tree (`crew_state.py:313`, `crew_standards.py:840` unmoved).

## Re-anchor provenance - `f808e5f0` -> `308ac2fa`, 2026-10-03 (T-0063, crew 1.0.164)

T-0063 changed `crew_autopilot.py` (the main checkout's INDEX row, `folder-elsewhere`, `index-disagreement`, `commit-refresh`), `crew_refresh_check.py` (`fresh-uncommitted`, graphify's manifest), `commands/autopilot.md`, `done.md`, `implement.md`, the README, the troubleshooting guide and the version files. The `/crew:autopilot` section gains the T-0063 paragraph and the refresh-check section the `fresh` means committed bullet, both DERIVED with `grep -n` on `308ac2fa`. Every other body `path:line` citation into a changed file was re-mapped by a difflib line map from the scope base `34d9f267` to `308ac2fa` (crew_autopilot.py +150 lines below `:244`, then for the QA fixes +1 below `:163` and +14 around `_commit_refresh`, re-mapped the same way from `7807dbcc`, crew_refresh_check.py +16 below `:220` and +53 below `:419`, done.md +5 inside check 4), and the ones covering an edited line re-read by hand; bare `:N` citations whose file the paragraph names without a line (the autopilot intro, the refresh-check intro) were re-derived by hand, several of which were already behind at `f808e5f0`. Citations inside provenance notes are history and were left as written.

## Re-anchor provenance - `308ac2fa` -> `c9867c59`, 2026-10-03 (T-0063, crew 1.0.182)

After PR #368 was pushed, `f0d40c66` fixed the Windows CI failure (`_rel_inside` no longer re-slashes a path outside the checkout; its docstring grew three lines, so every `crew_autopilot.py` citation below `:266` moved +3, re-mapped by the same difflib script from `308ac2fa`) and the README and troubleshooting guide name crew 1.0.182; `c9867c59` sets 1.0.182. The version sentence (`:59`) and the two T-0063 paragraph headings now say 1.0.182. No claim changed.

## Re-anchor provenance - `c9867c59` -> `0e36a87d`, 2026-10-03 (T-0063 merges origin/main, crew 1.0.182)

**Re-anchored `c9867c59` (T-0063) and main's `0620587f`/`42effe14` -> `0e36a87d` on 2026-10-03 (T-0063 merges origin/main `4f6ef540`, L-0601 #327, crew 1.0.162; crew stays 1.0.182).** Main's text was taken in every conflict and T-0063's notes re-applied after it. The only source file both sides changed is `plugin/crew/README.md`, and main's edit there is one line in place (`:768`), so no citation on either side moved; the runbooks-index citation `plugin/crew/README.md:2320` was re-read with `grep -n` on the merge. Main's other changes (`review_prompt.py`, `review.md`, `sabotage.py`, `sabotage_recurring.py`, `test_review_prompt.py`, the working-with-codex guide, `scripts/gate-runner.py`, `_verify/smoke.sh`, the marketplace workflow) touch no file T-0063 changed and were carried by main's own maps. No claim re-derived.

## Version re-allocation - 1.0.182 -> 1.0.201, 2026-10-03 (T-0063, after the merge of main `4f6ef540`)

The coordinator re-allocated T-0063's crew version to 1.0.201 after the merge. The version sentence above, the T-0063 autopilot paragraph and the `fresh` means committed bullet now name 1.0.201; the README, the troubleshooting guide's source and HTML, the CHANGELOG heading, `plugin/PLUGINS.md` and both manifests changed with it (version mentions edited in place, no line moved). The anchor stays `0e36a87d`: no other line any citation here covers changed. Notes above that name 1.0.182 are history.

**Re-anchored `0e36a87d` -> `5bd4fae2` on 2026-10-03 (T-0063, crew 1.0.201). Current despite the lag.** `5bd4fae2` re-states the crew version as 1.0.201 in place (manifests, `plugin/PLUGINS.md`, the CHANGELOG heading, four mentions in `plugin/crew/README.md`, the troubleshooting guide's source and HTML); no line moved, so no body citation changed.

## Version re-allocation - 1.0.201 -> 1.0.213, 2026-10-03 (T-0063, review-fix round on PR #368)

The coordinator allocated 1.0.213 for the review-fix round (`_main_folder` carries the main-checkout could-not-tell into the stop; `_folder_elsewhere` shell-quotes its `cp -r`). The version sentence above, the T-0063 autopilot paragraph and the `fresh` means committed bullet now name 1.0.213, with the manifests, `plugin/PLUGINS.md`, the CHANGELOG heading, four mentions in `plugin/crew/README.md` and the troubleshooting guide's source and HTML. JUDGEMENT: the fix commit moved lines in `plugin/crew/hooks/scripts/crew_autopilot.py` below `:352`, so its citations there (e.g. `_folder_elsewhere` `:362`) are not re-derived by this note; the anchor stays `5bd4fae2`, and a refresh re-checks them.

**Re-anchored `5bd4fae2` -> `309575c2` on 2026-10-03 (T-0063 review fixes, crew 1.0.213).** `git diff --name-only 5bd4fae2 309575c2 -- plugin/crew/hooks/scripts/` returns only `crew_autopilot.py`; its 56 body citations into code the fix moved were re-mapped by a `difflib` line map from `6c6517a8` to `309575c2` (every mapped line text-identical at both ends) and, where the cited line itself changed, re-read with `grep -n` per symbol (`_main_folder`'s callers `:544`/`:852`, `_folder_elsewhere` `:365`). Two were wrong before this pass and were re-derived by symbol: `sys.dont_write_bytecode` under `__main__` is `:166-168` (was `:149-151`) and `main` registers `deploy-allowed` at `:1856` (was `:1683`). The `folder-elsewhere` sentence gains the could-not-tell stop and the quoted `cp -r`. Provenance sections were left as written.
