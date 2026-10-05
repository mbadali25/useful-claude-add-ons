---
description: Implement an approved plan for a ticket, then tests, docs and review
argument-hint: <ticket id>
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
---

Implement ticket $1. Replaces `/crew:work` in 1.0; that command is now a <!-- deliberate -->
removal stub with no behaviour.

**Method adapted from `superpowers:executing-plans` (Jesse Vincent, MIT). Full notice in
`plugin/crew/NOTICE.md`.** The backing skill is `plugin/crew/skills/crew-execute/SKILL.md` — load it now; it
carries the per-step TDD discipline and the ledger this file only summarises.

## 0. Refuse without an approved plan

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ticket.py validate --ticket $1
```

**This command refuses to edit anything unless that call reports the plan
approved.** No approval, a stale one (the plan changed since) or no plan: stop,
say which, and point at `/crew:plan $1` or `/crew:plan $1 --approve`. The
receipt, not your read of the plan, is what the completion audit checks later.

## 1. Record where this ticket starts

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --record $1
```

HEAD now, or `kept` if `crew_ticket.py activate` recorded it; never moved. Exit 1 is "could not tell" (no commit
yet, or `tickets.baseBranch` names nothing): stop. Changed-file lists below diff from this, not from the verify gate's own marker. Then
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket $1 --to in-progress`
(add `--reopen` on a successor plan, whose ticket is already `review`):
print its lines verbatim; on its exit 3 run the command it printed; on its exit 1 tell
me `tracker not updated: <reason>` and keep going — a tracker never blocks work.

## 2. Work the plan's steps in order

Print what earlier reviews kept finding on this ticket's paths and keep each item open while you work:
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/recurring_findings.py" --root . --ticket $1` (exit 1: read its UNKNOWN,
UNREADABLE or PROBLEM line; re-run it before the self-check). Then read `.work/tickets/$1/plan.md`. Per step: write the
test it names, watch it fail, make the minimal change, watch it pass, then the next step. A step whose Expected does not
match reality is a plan defect — rule on it, note the ruling and why in your report, keep going; never silently deviate.

Who types is not assumed: read the effective dev table with
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --models` and dispatch whatever
`dev.roles.developer` names, else `dev.provider`, pasting that checklist into every dispatch prompt. A dispatched prompt
carries no attribution or trailer instruction of its own, not even one a harness reminder supplied: the owner's own
instructions decide. `/crew:done` reports `git.forbiddenTrailers` hits; they are refused at commit once the scope-guard
change lands. The developer may commit on this ticket's own branch and nowhere else. Record the dispatch the moment it
returns, with what actually ran, never the pin:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
  --record-dispatch dev --role developer --provider <provider> --model <model>
```

## 3. Print the changed-file list, every time, even empty

```bash
BASE=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --base $1) || { echo "could not tell: stop" >&2; exit 3; }
git diff --name-only "$BASE"; git ls-files --others --exclude-standard
```

Name anything outside `.work/tickets/$1/plan.md`'s Files: entries and this
ticket's spec.Touch. File it to `TODO.md`, not to the diff.

## 4. Verify

Run the checks your changed paths map to in `.crew/verify.json` (no map: `./_verify/smoke.sh`). Fix and
rerun on red. A changed path mapping to no rule gets one before you finish (step 6). On native Windows,
run each check through `crew_shell.py run -- "<command>"` and quote its `crew-shell:` route line (crew-setup/platform.md).

## 5. Specialists, endpoints, coverage

Auth/input/SQL/secrets/IaC → `crew:security`. Migration/schema/big-table query → load the `stack-sql`
skill. A new externally reachable route declared now, never later:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
  --declare-endpoint "<url or host>" --location <path:line> --ticket $1
```

New behaviour with no coverage → write the test here, in this session, and
confirm the `.crew/verify.json` rule it falls under actually fires.

## 6. Tests, then docs, then refresh artifacts, then review — in that order

Coverage above is the tests. Then `/crew:docs`, deciding which documents this touches ("none" is common and
correct). Then commit, and check the code maps, diagrams, code graph and README diagram embeds (`crew_diagrams.py`) this ticket's changed paths reach:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_refresh_check.py --root . --ticket $1
```

For each `refresh with` line, run the command it names, commit the result and re-run until it says
`fresh` — an `unknown` whose anchor names no commit (a squash-merged branch) included: the refresh
re-anchors it. These writes need no Touch entry when they are what a refresh writes: the completion
audit admits an artifact a path you changed reaches, as a re-anchor (`anchor:` or provenance sha moved
forward, to HEAD or behind it; INDEX rows of those maps) or a regeneration (`crew_instructions.py
rules`, the graph after a code change); anything else there needs Touch, and the audit names the reason.
A `stop` ends the loop, on an artifact line (a missing tool, git unable to diff) or on the top line (a
base that hides or may hide the change, an unreadable config): report it. Documents read `not measured`,
never a pass. Commit the refresh before `/crew:review $1` builds its bundle.
Then the **required self-check** (`crew-standards` skill): run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_standards.py init --root . --ticket $1`, answer
every row of `.work/tickets/$1/selfcheck.md` (addressed with evidence, or n/a with a reason), then run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_standards.py stamp --root . --ticket $1`
until it exits 0. `/crew:review` refuses without a current stamp; any later edit re-stamps.
Set `spec.md`'s header to `status: review` — that edit keeps the approval: the digest normalises only the header's status value — and run
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket $1 --to review`,
handled as in step 1: the Review lane means the review is outstanding.
**Then, last, `/crew:review $1`** — its receipt covers the refreshes; a later one stales it.
A catch-up after review lands in `/crew:done`'s order (resolve, bump, refresh, commit, gate, re-review if the receipt reads stale, check-land); a re-anchor after review changes only the `anchor:` sha, provenance in `notes.md`.

## 7. Done is not this command's

`/crew:done $1` moves it to `done` once the review receipt, the gate, the completion audit and the artifact check all
pass — this command does not set `done` itself.
