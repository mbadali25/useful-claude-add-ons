# 3. Crew departs from three community best practices, on purpose

**Status:** accepted, 2026-09-17
**Decided by:** the user, after an audit against the source below

## Context

<https://rosmur.github.io/claudecode-best-practices/> is a synthesis of roughly
twelve sources on using Claude Code well. The user asked for its rules to be
integrated into the `crew` plugin.

Most of it crew already does, and the audit said so rather than re-implementing
it: planning before coding (`/crew:plan`, the `planner` role), context
management (`crew-context`, the `context-watch` / `handoff-write` /
`handoff-read` hooks — which together are that document's "Document & Clear"
pattern), quality-gate hooks (`verify-gate`), multi-instance review with a
different model family (`/crew:review` via Codex), dev docs, and utility
scripts attached to skills.

Three of its rules, however, call crew's **core architecture** an anti-pattern.
That is not a gap to close; it is a disagreement to record, because the next
reader who finds this document will otherwise re-derive the whole argument from
scratch — or worse, act on it.

## Decision

Crew keeps all three of the following and departs from the document knowingly.

### 1. Specialised subagents rather than the clone pattern

> "Avoid custom subagents; use `Task(…)` to spawn clones … Most users should
> start with the clone pattern."

Crew ships **54 agent definitions**. The document's own §5.2 records this as an
unresolved contradiction between its sources rather than a settled rule, and
concedes that custom subagents suit "highly specialized, narrow tasks".

Crew's reason is independence rather than specialisation. A reviewer that
shares the author's context is the author's judgement at one remove, which is
why `/crew:review` prefers a **different model family** entirely. A clone
inherits the very context whose blind spots the review exists to find. The 40
domain specialists are also opted into per repository, so a checkout that does
no SharePoint never loads the SharePoint role.

**The cost, stated plainly:** 54 definitions are 54 things that can drift from
the code they describe, and crew has shipped agent prompts that claimed
mechanisms crew did not have (fixed in 0.19.43). The clone pattern cannot have
that defect, because there is nothing to drift.

### 2. Twenty-six slash commands

> "If you have a long list of complex custom slash commands, you've created an
> anti-pattern."

Crew ships **26**. The document's recommended set is roughly eight, and it
frames commands as "simple shortcuts, not complex workflows".

Crew's commands are mostly not shortcuts. `/crew:promote` runs a gated
promotion with post-deploy proof; `/crew:upgrade` runs schema migrations that
back up the codemap first; `/crew:onboard` writes a verifiable code map. Each
is a workflow whose steps must not vary between runs, which is exactly what a
command file is for and exactly what a remembered habit is bad at.

**The cost:** a 26-command surface is a discovery problem, and a user who
cannot find the command does not get the workflow. `/crew:roster` and the PM
brief exist partly to mitigate that, and they are not a complete answer.

### 3. A multi-agent system at all

> "Despite multi-agent systems being all the rage, Claude Code has just one
> main thread … I highly doubt your app needs a multi-agent system."

Crew is a multi-agent system by definition. The argument against is
debuggability: "every abstraction layer makes debugging exponentially harder."

That argument is correct and crew accepts it. What crew buys with the
complexity is **context isolation** — the reason it exists is multi-repo legacy
work where one session cannot hold the whole picture, and where the reviewer
must not be the author. Crew also keeps the shape the document recommends
*within* each agent: one main thread, at most one branch, simple iterative tool
calling. It does not build a graph of agents talking to each other.

**The cost:** crew is harder to debug than a single thread, and a defect in
dispatch can look like a defect in a role. The `.crew/metrics.md` record and
`/crew:scale` exist so the crew's size is answerable from evidence rather than
from enthusiasm, and `/crew:scale` can recommend shrinking.

## Consequences

- These three are **not** to be "fixed" by a future reader who encounters the
  source document. If the decision should change, it changes here first.
- The document's non-conflicting rules were integrated. The measurable ones
  were acted on: the `crew-best-practices` skill records the rule set with
  attribution, and the three `SKILL.md` files that exceeded its 500-line
  progressive-disclosure limit were split.
- The document disagrees with itself in §5 on skills-versus-bloat,
  subagents-versus-clones and documentation volume. It is a synthesis of
  practitioners, not a specification, and should be read as one.

## The rule crew already followed without knowing it

§4.3.2 says: **"Don't block at write time — let the agent finish its plan, then
check the final result."**

Crew removed its `PreToolUse` command guard in 0.19.52 and kept the Stop-time
`verify-gate`, on the user's instruction and for the user's own reasons. That
is precisely the shape this rule prescribes, arrived at independently. It is
recorded here because a rule that a codebase reaches on its own is better
evidence for the rule than one it adopts on being told.
