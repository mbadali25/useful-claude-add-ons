---
description: Implement an approved plan for a ticket, then tests, docs and review
argument-hint: <ticket id>
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
---

Implement ticket $1. Replaces `/crew:work` in 1.0; that command is now a <!-- deliberate -->
removal stub with no behaviour.

**Method adapted from `superpowers:executing-plans` (Jesse Vincent, MIT). Full
notice in `plugin/crew/NOTICE.md`.** The backing skill is
`plugin/crew/skills/crew-execute/SKILL.md` — load it now; it carries the
per-step TDD discipline and the ledger this file only summarises.

## 0. Refuse without an approved plan

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ticket.py validate --ticket $1
```

**This command refuses to edit anything unless that call reports the plan
approved.** No approval, a stale one (the plan changed after approval), or no
plan at all — stop, say which, and point at `/crew:plan $1` or
`/crew:plan $1 --approve`. Do not proceed "since the plan looks fine" — the
receipt, not your read of the plan, is what the completion audit checks
later.

## 1. Record where this ticket starts

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --record $1
```

HEAD now, keyed by ticket, never moved by a later re-run. Every changed-file
list below diffs from this, not from the verify gate's own marker.

## 2. Work the plan's steps in order

Read `.work/tickets/$1/plan.md`. Per step: write the test it names, watch it
fail, implement the minimal change, watch it pass, then the next step. A step
whose Expected does not match reality is a plan defect — rule on it, note the
ruling and why in your report, and keep going; do not silently deviate.

Who types is not assumed: read the effective dev table with
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --models`
and dispatch whatever `dev.roles.developer` names, else `dev.provider`. The
developer may commit on this ticket's own branch and nowhere else. Record the
dispatch the moment it returns, with what actually ran, never the pin:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
  --record-dispatch dev --role developer --provider <provider> --model <model>
```

## 3. Print the changed-file list, every time, even empty

```bash
BASE=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scope_base.py --root . --base $1)
git diff --name-only "$BASE"; git ls-files --others --exclude-standard
```

Name anything outside `.work/tickets/$1/plan.md`'s Files: entries and this
ticket's spec.Touch. File it to `TODO.md`, not to the diff.

## 4. Verify

Run the checks your changed paths map to in `.crew/verify.json`, or
`./_verify/smoke.sh` when there is no map. Fix and rerun on red. A changed
path mapping to no rule gets one before you finish (step 6).

## 5. Specialists, endpoints, coverage

Auth/input/SQL/secrets/IaC → `crew:security`. Migration/schema/big-table query
→ load the `stack-sql` skill. A new externally reachable route declared
now, never later:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
  --declare-endpoint "<url or host>" --location <path:line> --ticket $1
```

New behaviour with no coverage → write the test here, in this session, and
confirm the `.crew/verify.json` rule it falls under actually fires.

## 6. Tests, then docs, then refresh artifacts, then review — in that order

Coverage above is the tests. Then `/crew:docs`, deciding which documents this
touches ("none" is common and correct). Then commit, and check the code maps,
diagrams and code graph this ticket's changed paths reach:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_refresh_check.py --root . --ticket $1
```

For each `refresh with` line, run the command it names, commit the result and
re-run until it says `fresh` — an `unknown` whose anchor names no commit (a
squash-merged branch) included: the refresh re-anchors it. These writes need no
Touch entry; the scope guard and completion audit allow the refresh-artifact
paths for an approved ticket. A `stop` anywhere ends the loop, on an artifact
line (a missing tool, git unable to diff) or on the top line (a scope base that
hides or may hide the change, an unreadable config): report it with its reason.
Documents read `not measured` — `/crew:docs`'s judgement, never a pass. Commit
the refresh before `/crew:review $1` builds its bundle. **Then, last,
`/crew:review $1`** — its receipt covers the refreshes; a later one stales it.

## 7. Update status

Set `spec.md`'s header to `status: review`. That edit keeps the approval: the
digest normalises only the header's status value. `/crew:done $1` moves it to
`done` once the review receipt, the gate, the completion audit and the artifact
check all pass — this command does not set `done` itself.
