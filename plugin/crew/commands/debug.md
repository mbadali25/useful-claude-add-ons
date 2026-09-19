---
description: Find the cause of a defect before anyone proposes a fix
argument-hint: <the symptom, or a ticket id, e.g. "login 500s after deploy" or T-0042>
allowed-tools: Read, Bash, Grep, Glob, Skill
---

Find the root cause of: $1

**You are not fixing it in this command.** This command ends with a cause and
the evidence for it. The fix is `/crew:work`'s job, or the developer's, and it
starts from what you hand them. A command that diagnoses and patches in one
breath is one nobody can audit, because the evidence that justified the patch
was never written down separately from the patch.

Note the tool grant above: `Read, Bash, Grep, Glob, Skill`. There is no `Write`
and no `Edit`, and that is deliberate — it removes the *convenient* path to a
fix, the one where a diff appears without anyone writing down what it was
for. It is not the enforcement: `Bash` can write a file as readily as `Edit`
can (`bash -c 'echo fix > file'` is a write this grant permits), so nothing
here stops a command from patching the tree. The Iron Law below is the rule
this role follows and reports against, not a mechanical guarantee the tool
grant backs up — treat a report that skipped Phase 1 as a broken contract to
flag, not an impossible state the grant already ruled out.

## 1. Load the method

Follow the `crew-debugging` skill, which owns the method. Its first section
tells you how to choose between `superpowers:systematic-debugging` and crew's
bundled copy: invoke the upstream skill with the `Skill` tool, use it if it
returns, use the bundled copy if it errors. Report which you used.

Do not restate the four phases here from memory. Read them.

## 2. The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If Phase 1 is not complete, you cannot propose a fix. Not a small one, not a
provisional one, not one labelled "just to see".

**Under pressure this is the rule that goes first, which is why it is restated
here rather than left in the skill.** If the request arrived with a deadline, a
dollar figure per minute, or somebody senior who already knows what it is, that
is the condition the method exists for — not a reason to shorten it. The skill
ships three pressure-test scenarios that are exactly this situation; if you
find yourself constructing an argument for why this case is the exception, you
are reproducing them.

## 3. Gather this repository's evidence first

The skill's "Phase 1 in a crew repository" section lists the sources and what
each is for. In short, and before you instrument anything:

- `.crew/codemap/INDEX.md`, then the **`## Landmines`** section of every
  `.crew/codemap/<subsystem>.md` whose paths intersect the failing code.
  An anchor behind HEAD means re-check with
  `git diff --name-only <anchor>..HEAD -- <paths>`, not ignore.
- `.crew/codemap/schema-<datasource>.md` when the defect touches a migration,
  DDL, a model, a query or a column.
- `graphify-out/graph.json` for "what called this?" when the trace crosses
  files.
- `.crew/verify.json` for the command that actually checks these paths —
  reproduce with that one, because it is the one the gate will run.

Where a source is absent, empty or stale, that is a finding to report, not a
step to skip silently.

## 4. Report

Produce this, and nothing that edits the tree:

- **Symptom** — what was observed, and the exact error text with its exit code.
- **Reproduction** — the command that triggers it, and whether it is reliable.
  If it is not reproducible, say so plainly; a cause asserted without a
  reproduction is a guess with a citation.
- **Evidence read** — which codemap notes, schema note, graph and verify rules
  you opened, and what each one gave you. Name the ones that were absent or
  stale too. A source read and a source skipped look identical in a report
  that mentions neither.
- **Which method ran** — upstream `superpowers:systematic-debugging` or crew's
  bundled copy. If upstream errored, say "not available in this session" — a
  failed invocation does not prove it is absent from the machine.
- **Hypothesis** — one, stated as "X is the cause because Y", with the
  observation that would falsify it.
- **Root cause** — the originating trigger, at `path:line`, not the place the
  error surfaced. If Phase 1 did not reach one, say **"cause not established"**
  and list what you ruled out. That is a legitimate and useful result; a
  confident wrong cause is not.
- **Proposed fix, unimplemented** — where it goes and what it changes, in two
  sentences. Plus the failing test that should exist before it lands.
- **Confidence, and what would raise it** — if the cause is inferred rather
  than demonstrated, say which observation is missing.

## Deferred — and where it went

Your report ends with this section, **present even when empty**. One line per
thing you found and did not chase: what it was, where it went, why it did not
block the diagnosis. When you found nothing, write "Nothing deferred." — those
words, not an omitted section.

Debugging finds unrelated problems more reliably than any other crew activity,
because tracing a data flow means reading code nobody was looking at. Those
belong in `TODO.md` at the repo root with their `path:line` and a reason, not
in this investigation and not in the fix that follows it. A second defect
chased inside a first one's diagnosis is how a scoped ticket becomes a week.

An absent section is ambiguous in the one direction that costs: it reads
identically whether you found nothing or found something and dealt with it
quietly.
