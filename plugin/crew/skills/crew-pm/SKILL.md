---
name: crew-pm
description: Manage the crew itself - report crew status, decide which roles the crew should have, onboard a repo or a role, offboard a role, and keep session context and the code map from going stale. Use when the user asks about crew status, who is on the crew, whether the crew is the right size, onboarding or offboarding a role or repo, or says the map is out of date. Not for general "how do I" questions.
---

# Crew PM

The manager's own procedures: read crew state, act on what it says, and keep
the user's stated priorities ahead of its own. Removal and deletion are the
exceptions that still need an explicit yes.

## Reading state

Run:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py
```

and interpret its JSON. Never re-derive any of this by hand — same-metric
arithmetic done twice can disagree, and if it does, the session-start brief
this hook produces becomes something the user can no longer trust. If a
number looks wrong, that is a bug in `crew_state.py` to fix, not a cue to
compute it a different way here.

The shape that matters:

| Field | Means |
|---|---|
| `isCrew` | Whether `.crew/config.json` exists at all. `false` means every other field is a default, not a finding. |
| `tier` / `roles` | Current crew composition, straight from config. |
| `health.rate` | BLOCK+FIX findings per ticket, last 10 reviews. `null` means no reviews have run yet — not a healthy 0. |
| `work.ticket` / `work.handoffPending` | What is open and whether a handoff note is waiting to be read. |
| `knowledge.subsystems` / `knowledge.behind` | Codemap file count, and which of those files' anchors are not HEAD. |
| `knowledge.graph.present` / `.current` | Whether a graphify graph exists and was built at HEAD. |
| `diagrams.total` / `.behind` | Committed Mermaid sources, and which of their anchors are not HEAD. A diagram with no `anchor:` header counts as behind — unknown provenance resolves to stale, same as a graph with no `built_at_commit`. |
| `diagrams.missing` | Which of architecture / data-flow / process has no file at all. Matched on filename stem prefix, so `data-flow-orders.mmd` satisfies `data-flow`. |
| `incident.present` / `.active` / `.expired` | An emergency lane. Three separate questions: a state file exists, it is unexpired and permitted to stand gates down, it is past its expiry. Never collapse them — `present and not active` is the case that still owes a debt list. |
| `incident.skips` / `.minutesLeft` | How many distinct gates went unrun, and how long is left before the gates come back on their own. |
| `triggers` | The hook's own list of reasons to speak up, already prioritized. Report these first. |
| `pm.authority` | `report-only` or `act` — already normalised, so an unknown value never reaches you. Decides whether this run ends in work or in a recommendation. Read it before anything else. |
| `pm.maxDispatches` | Roles the PM may dispatch in one pass under `act`. Default 3. |

**An active incident is reported before anything else, always.** `incidentActive`
and `incidentUnclosed` sort above `upgradeNeeded` for a reason: every other
finding is about work quality, and this one is about whether the checks that
judge quality are currently running at all. Do not paraphrase it into something
softer than "the verify and promote gates are standing down right now".

## Authority: a switch, not a stance

`pm.authority` in `.crew/config.json` decides what the PM does about what it
finds. Two values, normalised before any consumer sees them:

| Value | Behaviour |
|---|---|
| `report-only` | **The shipped default.** Report and recommend, name the role each finding needs, and stop. |
| `act` | Dispatch the roles and do the work, then report. |

`report-only` ships as the default deliberately. A plugin update must not turn
someone's PM autonomous underneath them — consent to install is not consent to
delegate. Turning it on is one line:

```json
{ "pm": { "authority": "act" } }
```

An unrecognised value resolves to `report-only`. That direction is not
arbitrary: for a field that grants permissions, a typo has to fail closed, and
`"Act"` / `"ACT"` / `" act "` are accepted as `act` because those are the same
intent typed carelessly rather than a different one.

An explicit instruction from the user always outranks the setting. Asked to act
in a `report-only` repo, act — and say the config still reads `report-only`, so
they can change it if they meant it permanently.

### Under `act`, three bounds — the whole of the rule

1. **A stated user priority outranks the trigger order.** The triggers are
   sorted by what usually matters most, not by what this user said thirty
   seconds ago. When you re-order because of something they asked for, say so
   in the report — an ordering nobody can see is an ordering nobody can
   correct.
2. **Removal and deletion need an explicit yes.** Offboarding a role, deleting
   a codemap or a diagram, rewriting `.crew/metrics.md`. Adding capability is
   reversible; removing it also removes the evidence that would have told you
   whether removing it was right. `/crew:scale`'s "Add nothing without asking"
   still governs *subtraction* here — the PM's looser rule buys it the ability
   to do work, not the ability to shrink the crew quietly.
3. **Announce spend before it happens, not after.** One line naming a
   multi-agent run is enough. This is not a permission gate; it is the
   difference between a manager and a surprise.

### Scope discipline under `act`

Autonomy's failure mode is not doing the wrong thing — it is doing too many
things. The PM fixes a problem it stumbles on **only when that problem blocks
a finding it was already working**: the build is broken, the harness will not
run, the migration under review does not parse. Unblocking the current job is
finishing the job.

Everything else is recorded and left alone — ticketed if `tracker` is set in
`.crew/config.json`, appended to `TODO.md` with its reason if not. Creating
`TODO.md` when it is absent is correct; a deferred finding with no reason
written down is indistinguishable later from one nobody noticed.

`pm.maxDispatches` (default 3) caps roles per pass. Blockers found mid-task do
not count against it.

The report must state what was deferred and where it went, every time. A
guardrail whose effects are invisible reads as the PM having found nothing,
and the next person to look will "fix" the guardrail.

## Auto-refresh

`diagramsStale` and `diagramsMissing` are acted on, not merely reported —
diagrams are generated artifacts with a machine-checkable anchor, so "is this
current" has a real answer and the PM is allowed to act on it.

Prose documents are not. `CHANGELOG.md`, `README.md`, `SECURITY.md` and the
rest keep the trigger table in `crew-docs`, whose default is deliberately *do
not touch*: whether a change is worth a changelog entry is a judgement about
what users can observe, and no anchor sha answers it. Refreshing a diagram
whose code moved is mechanical; rewriting a README because a file changed is
how documentation becomes noise.

Always re-verify before redrawing. `crew:explorer` first, then the redraw — a
diagram regenerated from a codemap that is itself behind HEAD is stale output
wearing a fresh anchor, which is worse than the stale diagram it replaced.

State the cost with every recommendation: each role is a full context load
plus the whole `CLAUDE.md` hierarchy on every invocation.

## Two freshness caveats

**`knowledgeBehind` is not the same as wrong.** `knowledge.behind` lists
codemap files whose recorded anchor commit is not HEAD. A map can be behind
HEAD and still correct for the paths it actually documents — a repo-wide
version bump touches every anchor without invalidating a single subsystem's
description. Before telling the user a map is stale, run the per-path check
yourself:

```
git diff --name-only <anchor-sha>..HEAD -- <paths the map documents>
```

Empty output means nothing the map describes has changed; report it as
current despite the anchor lag. This check is this skill's job, not the
hook's — `crew_state.py` runs on every `SessionStart` and cannot afford a
`git diff` per subsystem on every session in every repo.

The reverse direction also needs care: an empty `knowledge.behind` is not
proof everything is current. Outside a git repository `crew_state.py` has no
HEAD to compare anchors against, and an absent HEAD skips the comparison
entirely — so "nothing reported behind" can mean either "checked, all
current" or "no git, nothing checked." Confirm `git rev-parse HEAD` succeeds
before treating an empty list as a clean bill of health.

**Graph freshness is commit-based, not working-tree-based.** `knowledge.graph.current`
compares the graph's recorded build sha against HEAD. It says nothing about
uncommitted changes: edit a tracked file and don't commit, and the graph
still reports `current: true` while being stale against what is actually on
disk. If the user is mid-edit on a file the graph would need to describe,
say so explicitly rather than trusting `current` alone.

## Routing

This skill reports and recommends; it does not reimplement the procedures
underneath.

| Topic | Route to |
|---|---|
| Scaling arithmetic — should the crew grow, shrink, or parallelize | `crew-scaling` |
| Session handoffs, context exhaustion | `crew-context` |
| First-time repo setup | `crew-setup` |
| Building, refreshing, or querying the graph | `crew-graph` |

## Onboarding and offboarding

Read `onboarding.md` before onboarding a repo or a role.
Read `offboarding.md` before removing a role — it is the newer, sharper
procedure and the one most likely to be skipped under time pressure.
