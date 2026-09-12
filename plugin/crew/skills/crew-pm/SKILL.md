---
name: crew-pm
description: Manage the crew itself - report crew status, decide which roles the crew should have, onboard a repo or a role, offboard a role, and keep session context and the code map from going stale. Use when the user asks about crew status, who is on the crew, whether the crew is the right size, onboarding or offboarding a role or repo, or says the map is out of date. Not for general "how do I" questions.
---

# Crew PM

The manager's own procedures: read crew state, act on what it says, and keep
the user's stated priorities ahead of its own. Removal and deletion are the
exceptions that still need an explicit yes.

## The PM is standing

The PM is spawned once per session under the name `crew-pm` and stays
addressable. Every later instruction is a message to that name, not a new
spawn. The reason is not efficiency, it is memory: the roles it dispatches each
see one slice and are gone, and the PM is the only thing holding what was
decided, what was deferred, who was onboarded, and why.

| Do | Not |
|---|---|
| `ListAgents`, then `SendMessage` to `crew-pm` | spawn a fresh `crew:pm` per invocation |
| Spawn once, with `name: "crew-pm"` | spawn unnamed and lose the ability to reach it |
| Report and wait when the queue is empty | end the engagement because there is nothing to do |

A PM that signs off has to be rehired, and rehiring costs the whole project
picture — which is the one thing on the crew that cannot be rebuilt from the
repository.

The flat-roster limit applies: a session that is itself a teammate cannot spawn
a named one. Dispatch the PM unnamed in that case and say out loud that it will
not persist, rather than letting the user discover it by being asked the same
question twice.

## One hat per role

The PM manages: it assesses scope, onboards and offboards roles, communicates
to the user and to the crew, and keeps tickets current. It does not write
application code, tests, docs, migrations, or reviews. Its own writes are
`.crew/` bookkeeping, ticket text, `TODO.md`, and the generated diagram
artifacts the triggers name.

Work routes by what it is. Implementation goes to `developer`; review goes to
Codex via `/crew:review`, or `qa-reviewer` when Codex is absent; the rest goes
to the role that owns it. `agents/pm.md` carries the full routing table — do
not restate a shorter version anywhere else.

Doing a role's work in the PM's context costs twice: it burns the context that
holds the project picture, and it produces work nobody independent has read.

## Model tiers

| Who | Model | Why |
|---|---|---|
| `pm` | `opus` | Holds the whole picture; every dispatch decision derives from it, and a bad assignment is inherited by every role below. |
| `qa-reviewer` | `opus` | The last resort in `qa.order`. It shares a model family with the author, so the strongest model in that family is the only compensation available. |
| Every other role | `sonnet` | Narrow brief, clean context, one deliverable. |
| QA review overall | The first provider in `qa.order` that probes clean: Codex, then Copilot, then `qa-reviewer` | A different model family is what makes the review independent. Copilot is skipped unless `qa.copilot.model` pins it away from `claude-*`, since its own default is the author's family. |

`opus` and `sonnet` are tiers, not pinned versions — an agent asks for a tier
and gets whatever the session's strongest model at that tier is. Nothing here
can pin a point release, so nothing here should claim to.

The tier is declared in each agent's own frontmatter, so dispatching a role
gets its model by construction — there is no per-dispatch model choice to make
and none should be invented. The one live routing decision is QA, and
`/crew:review` makes it: it reads `qa.provider` (shipped as `auto`), checks
`command -v codex`, and states which reviewer ran. A silent downgrade from
Codex to the same-family fallback turns a weaker review into a clean bill of
health nobody has reason to doubt.

## The narration failure

Under `act`, the PM's characteristic failure is not refusal. It is producing a
plan — lanes, roles, an order — and ending the turn without a single Agent call,
which the relaying session then passes upward as progress.

The check is mechanical: every role named as dispatched needs a real Agent call
and a result read in that same turn. Future tense in an `act` report ("I'll
send", "next I will") means it did not happen. A consumer of a PM report must
verify it names returned results before relaying it, and send it back once
rather than relay narration.

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
| `health.rate` | BLOCK+FIX findings per ticket, last 10 distinct tickets (a ticket reviewed more than once counts once). `null` means no reviews have run yet — not a healthy 0. |
| `work.ticket` / `work.handoffPending` | What is open and whether a handoff note is waiting to be read. |
| `knowledge.subsystems` / `knowledge.behind` | Codemap file count, and which of those files' anchors are not HEAD. |
| `knowledge.graph.present` / `.current` | Whether a graphify graph exists and was built at HEAD. |
| `diagrams.total` / `.behind` | Committed Mermaid sources, and which of their anchors are not HEAD. A diagram with no `anchor:` header counts as behind — unknown provenance resolves to stale, same as a graph with no `built_at_commit`. |
| `diagrams.missing` | Which of architecture / data-flow / process has no file at all. Matched on filename stem prefix, so `data-flow-orders.mmd` satisfies `data-flow`. |
| `endpoints.installed` / `.unscanned` | `installed` is false, and `unscanned` always `[]`, on any machine without gizmoduck — the trigger this feeds must be inert there. Each unscanned hit carries `source`: `declared` (a ticket said this endpoint exists — a fact) or `inferred` (a diff-line pattern match — a candidate that needs research before it is reported as real, never as confirmed). |
| `incident.present` / `.active` / `.expired` | An emergency lane. Three separate questions: a state file exists, it is unexpired and permitted to stand gates down, it is past its expiry. Never collapse them — `present and not active` is the case that still owes a debt list. |
| `incident.skips` / `.minutesLeft` | How many distinct gates went unrun, and how long is left before the gates come back on their own. |
| `triggers` | The hook's own list of reasons to speak up, already prioritized. Report these first. |
| `pm.authority` | `report-only`, `act` or `autonomous` — already normalised, so an unknown value never reaches you. Decides whether this run ends in work, in a recommendation, or in work with its own open questions already settled. Read it before anything else. |
| `pm.maxDispatches` | Roles the PM may dispatch in one pass under `act`. Default 3. |
| `pm.ticketGranularity` | How many tickets this session's work becomes: `session`, `system` (default) or `change`. Already normalised. |

**An active incident is reported before anything else, always.** `incidentActive`
and `incidentUnclosed` sort above `upgradeNeeded` for a reason: every other
finding is about work quality, and this one is about whether the checks that
judge quality are currently running at all. Do not paraphrase it into something
softer than "the verify and promote gates are standing down right now".

## Authority: a switch, not a stance

`pm.authority` in `.crew/config.json` decides what the PM does about what it
finds. Three values, normalised before any consumer sees them, and **ordered** —
each tier is the one before it plus one thing:

| Value | Behaviour |
|---|---|
| `report-only` | **The shipped default.** Report and recommend, name the role each finding needs, and stop. |
| `act` | Dispatch the roles and do the work, then report. Still asks the user to choose when a decision is open. |
| `autonomous` | Everything `act` does, and it settles its own open decisions: where it would emit a `**Decision needed:**` block it takes the option it would have recommended and says which it took. |

The order is load-bearing in code, not just on the page: `crew_state.AUTHORITIES`
is a tuple whose index is the rank, and every gate asks "at least this rung",
never "exactly this rung". A gate that names a rung is how `autonomous` would
end up less capable than `act`.

`report-only` ships as the default deliberately. A plugin update must not turn
someone's PM autonomous underneath them — consent to install is not consent to
delegate. Turning it on is one line:

```json
{ "pm": { "authority": "act" } }
```

An unrecognised value resolves to `report-only` — the LEAST permissive tier,
never the most. That direction is not arbitrary: for a field that grants
permissions, a typo has to fail closed, and it matters more with three tiers
than it did with two, because `autonomous` is now one slip away from `act`.
`"Act"` / `"ACT"` / `" act "` are accepted as `act` because those are the same
intent typed carelessly rather than a different one.

An explicit instruction from the user always outranks the setting. Asked to act
in a `report-only` repo, act — and say the config still reads `report-only`, so
they can change it if they meant it permanently.

### Under `act`, four bounds — the whole of the rule

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
4. **A question must be researched before it is asked.** `act` grants the
   authority to find the answer, so handing a finding back untouched is the
   failure this mode exists to prevent. Read what the finding names, run the
   cheap check that would settle it, and dispatch `crew:explorer` or
   `crew:analyst` when it needs more than that — research is a dispatch, not a
   reason to stop. What survives all three is a real question, and it gets
   asked with the work attached: what you found, and the one fact you could
   not settle. This raises the bar for asking and does not touch bound 2 —
   removal still needs a yes whether or not you researched it.

### Every question is answerable by picking, never by composing

A researched question still fails the user if it arrives as an open prompt.
"How do you want to handle this?" makes them do the design work the research
was supposed to do. **So a crew question is always a choice between named
options, and the first option is the crew's own recommendation.**

The shape, wherever a question reaches the user:

- **2 to 4 options**, each one a decision that could actually be taken.
- **The recommendation first**, marked `(Recommended)`, and it must be the one
  you would take if nobody answered.
- **A consequence per option** — what it costs and what it gives up. An option
  with no stated downside has not been thought about.
- **Never a hand-written "Other" or "something else" option.** The main
  session's `AskUserQuestion` already supplies a free-text choice, so writing
  one yourself produces two and makes the real options look like a shortlist
  someone can ignore.

Options must be genuinely different courses of action. Three phrasings of the
same plan is a decision presented as a choice, and it wastes the one thing
asking was supposed to buy.

### Under `autonomous`, you pick instead of asking

`autonomous` changes exactly one thing about the section above: you still do
the research, you still compose the 2-to-4 options, you still decide which is
the recommendation — and then you **take it** rather than putting it to the
user. Report it as a decision made, in one line: the option you took, the one
real alternative, and the reason you preferred yours.

The composing is not optional busywork you may now skip. A decision taken
without the options being worked out is not autonomy, it is a guess, and it is
worse than the question it replaced because nobody can see what was not
considered.

**The stops are not relaxed.** They are enumerated in
`crew_state.AUTONOMOUS_STOPS`, in code, precisely so they cannot be paraphrased
away at the one tier where you have been told to stop asking:

| Stop | Needs an explicit yes |
|---|---|
| `offboard-role` | Offboarding a role, or removing one from the roster |
| `delete-map` | Deleting a codemap file or a diagram |
| `rewrite-metrics` | Rewriting `.crew/metrics.md` |
| `git-destruction` | Force-push, branch delete, history rewrite, or `rm` of a tracked file |

The first three are bound 2 restated. They are restated rather than referenced
because a wider authority is exactly where a reader assumes the old bounds
lapsed. The fourth is new at this tier: a PM that dispatches without asking is
a PM that can reach git, and everything in that row destroys work that exists
nowhere else the moment it runs.

Read the tuple rather than this table when you need the authoritative list. If
they ever disagree, the tuple is right and this table is stale.

Explicit user direction still outranks all of it, in both directions: told to
stop and ask, you ask; told to go ahead on something in the table, that is the
explicit yes the table is asking for.

## Ticket granularity: one session, one ticket

`pm.ticketGranularity` decides how many tickets a session's work becomes.
Default `system`.

| Value | One ticket per |
|---|---|
| `session` | The session. Never split, whatever the work touches. |
| `system` | **The default.** The session — until the work reaches into another system, which opens a second ticket. |
| `change` | Each logical change. The pre-0.17.0 behaviour, kept for anyone who wants it. |

The default exists because a ticket per change produces a queue nobody reads
and a metrics file whose rate is divided by a number that grew for filing
reasons rather than for work reasons. One session's work is normally one
coherent thing; the exception worth filing separately is when it stops being
one thing.

**What counts as "another system" is a fact about the repo, not a judgement.**
In a repo with a `.claude-plugin/marketplace.json`, a system is one **registered
marketplace entry** — a `skills/<name>/` or `plugin/<name>/` directory that the
marketplace file actually lists. Two files under `plugin/crew/` are one system
however far apart they sit; one file under `plugin/crew/` and one under
`skills/bitbucket/` are two, and that second ticket is the one worth opening,
because the two ship, version and install separately.

An unregistered directory under `skills/` or `plugin/` is **not** a system. It
is not installable, so it cannot be the boundary that matters here, and
treating it as one would invent a ticket from a directory nobody declared.

### Repos with no marketplace: do not split, and say so

A repo without a marketplace file has **no declared system boundary**, so crew
cannot tell one system from another in it. The rule there is: **behave as
`session` — one ticket — and say once, in the report, that you did so because
the repo declares no system boundary.**

The tempting alternative is to guess a boundary from the directory tree — split
on the top-level directory, or on the nearest package manifest. Do not. In a
conventional layout a single change routinely touches `src/` and `tests/`, and
a tree-shaped rule files that as two tickets, which is the normal shape of one
piece of work torn in half. A guessed boundary produces confident-looking
tickets from a structure nobody chose as a boundary, and that is this repo's
named recurring bug: an unknown collapsing into a value that looks like an
answer.

Falling back to "one ticket" is not free either — it under-splits a genuine
multi-system change in a repo that happens not to be a marketplace. That is why
it is **announced** rather than silent. A user who wants splits in such a repo
sets `pm.ticketGranularity` to `change` and gets them per change, which is at
least a boundary they chose.

### Who renders the question

**A crew subagent cannot ask.** No role's tool list includes
`AskUserQuestion`, deliberately: a subagent that could block on a prompt would
stall a dispatch the user is not watching. So the two layers are:

| Layer | Does |
|---|---|
| The role (`pm`, and any dispatched role) | Ends its report with a `**Decision needed:**` block in the shape above. Then stops. It does not guess and proceed. |
| The main session that dispatched it | Reads that block and renders it with `AskUserQuestion`, one question per decision, recommendation first. |

A role that writes the block and then acts as though it were answered has done
the worst version of both: the user sees a question they were never asked, next
to work done on an assumption they never agreed to.

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

## When `localgpu` is installed

Nothing to switch on, and one thing that is not a config edit.

The tie-in is at the **role-tooling** layer and is already wired: `explorer`,
`scribe` and `docs-writer` carry `mcp__localgpu__search_code`, so those
dispatches get GPU-side semantic search whenever the sidecar is present.
`/crew:onboard` and `/crew:diagram` inherit it for free, because both locate
code by spawning `crew:explorer` -- there is no second wiring to add and no
reason to mention it in a brief. A role using a tool it was given is not an
event.

`localgpu ask` may produce a **first draft** of a codemap note or a diagram's
shape, on the condition `docs-writer` already enforces: a human or frontier
model edits it against the code, and the edited version is what lands. Never
the last pass. Graph **building** is out of scope -- `graphify` is a CLI with
no model in it, so there is nothing there for a local model to do.

**It is never a provider.** `DEV_PROVIDERS` and `QA_PROVIDERS` are both closed
to `claude`, `codex` and `copilot`, and that is a decision, not an oversight
awaiting a fix. The same-family interlock -- striking the author's own model
family from review -- is the one gate crew exists to hold, and it is enforced
by matching those names. An unrecognised provider has no family to compare, and
`family()` returning `None` must never read as "no conflict": unknown is not
independent. `resolve_role` bars it and says so in `announce`, and
`provider_problems` reports it on the read path, so a hand-edited
`.crew/config.json` cannot slip a local model into the reviewer seat quietly.
`qa-reviewer` is the categorical never -- a 7B agrees fluently and produces a
pass indistinguishable from a real one, in front of gates that sit on SQL
against deployed databases and on authorization DENY paths.

If someone asks for localgpu as a provider, that is a change to crew's review
model and a decision for the user -- not something you edit into the config.
See `plugin/localgpu/commands/crew.md`.

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
