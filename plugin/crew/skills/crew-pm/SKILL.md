---
name: crew-pm
description: Manage the crew itself - report crew status, decide which roles the crew should have, onboard a repo or a role, offboard a role, and keep session context and the code map from going stale. Use when the user asks about crew status, who is on the crew, whether the crew is the right size, onboarding or offboarding a role or repo, or says the map is out of date. Not for general "how do I" questions.
---

# Crew PM

The manager's own procedures: read crew state, report it plainly, and
recommend changes to roles, tier, or knowledge freshness. Never decide those
changes alone.

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
| `triggers` | The hook's own list of reasons to speak up, already prioritized. Report these first. |

## Authority: report and recommend only

Report state, propose a change, and stop. Role additions, role removals, and
tier changes all need the user's explicit yes before you touch
`.crew/config.json`. This mirrors `commands/scale.md`'s "Add nothing without
asking" — the PM does not get a looser rule than `/crew:scale` just because
it also reads state.

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
