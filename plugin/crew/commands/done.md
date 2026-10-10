---
description: Close a ticket - needs an accepted review receipt, a clean gate, a passing completion audit, current artifacts and docs
argument-hint: <ticket id>
allowed-tools: Read, Write, Edit, Bash
---

Close ticket $1. **All five checks below must pass. Any one failing refuses done** — there is no partial close.

## Check 1 — the review receipt

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_ledger.py --ticket "$1" --check-receipt
```

Rebuilds the bundle and fails if anything changed since the receipt was written. No receipt, a failing rebuild, or a ticket
still `NEEDS_REPLAN` (budget spent, no successor plan approved) all refuse — say which, and point at `/crew:review $1` or `/crew:plan $1` for a replan.

## Check 2 — the verify gate, settled for HEAD

Stop never refuses a deferral: a rule over `verify.stopBudgetSeconds` is deferred to CI (`chronic`), and a turn
where `0 rules ran` records nothing (L-0710). So this check needs evidence that HEAD itself passed every rule:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_status.py --root .
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import review_gate; print("GATE %s %s" % review_gate.gate_state("."))' "${CLAUDE_PLUGIN_ROOT}/hooks/scripts"
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/ci_receipt.py check --root .
```

It passes on exit 0 `CI_RECEIPT VERIFIED` (the `verify-gate` workflow ran the whole map, unbudgeted, on exactly this
committed tree: HEAD's run, or when HEAD has none, as on a merge to main, the run of a parent with HEAD's exact tree),
on exit 4 `NO_GATE` (no verify map, or the gate stood down), or when the `verify` line reads `no rules recorded` (a
clean pass empties the record) AND the `GATE` line reads `VERIFIED` (the marker names HEAD and the tree still has that
pass's fingerprint: a marker at HEAD alone also survives an uncommitted edit). Anything else (a `chronic`, `unverified`, `skipped` or `fail` count, `no gate record
yet`, `GATE UNVERIFIED`/`UNKNOWN`) refuses: quote both lines, push for the workflow or run `/crew:verify --all`, rerun.

## Check 3 — the completion audit

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/completion_audit.py --check --ticket "$1"
```

Diffs the whole tree against this ticket's scope base, as the Stop audit does (and the gate's `outside-scope:` line
reports), a shell-made `sed -i` included, as a pre-close confirmation rather than a per-turn block. A non-zero exit
names the out-of-scope path, or a refresh artifact with the reason it was not admitted (`[anchor did not move]`,
`[no changed path reaches it]`, `[bytes differ from expected_rules ...]`, `[could not tell: ...]`): re-anchor or
regenerate it in `/crew:implement $1` step 6, or put it in Touch. Any other out-of-scope path: `TODO.md`, not this
ticket; rerun.

## Check 4 — artifacts are current

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_refresh_check.py --root . --ticket "$1"
```

Read-only. Checks 4 and 5 judge this ticket's own changes: before it lands, paths identical to merged main are main's;
after, close from a branch at `origin/main` and its own are what its landing merge (found from the receipt's head)
brought; `every path since the base is judged - could not tell ...` leaves nothing out. Any `stale`, `unknown` or
`fresh-uncommitted` line refuses done: name the artifact and what the line says — `refresh with <command>` (a drifted README diagram embed included), or `stop` with its reason (a missing tool, a scope base that hides the change, broken embed markers). **Do not run the refresh here — a write now stales check 1's receipt.** Go back to `/crew:implement $1` step 6: refresh, commit, then `/crew:review $1` again,
then rerun this command. On `fresh-uncommitted` the artifacts are current but the files its `uncommitted:` line lists are not
committed: commit them in `/crew:implement $1` step 6 (no byte of the review bundle's working state changes, so check 1's receipt
stays current). Documents read `not measured` here: check 5 judges them.

## Check 5 — the documents this change owes

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_docs_check.py --root . --ticket "$1"
```

Read-only. Its CHANGELOG line is one this ticket added under `## [Unreleased]` or `## [<version>]` naming the plugin at
its own range's version. Any `MISSING` line, or `unknown`, refuses done: quote it. **Do not edit a document here — a write now stales
check 1's receipt.** Fix it in `/crew:implement $1` step 6 (`/crew:docs $1`), commit, then `/crew:review $1` again, then rerun this command.

## Report — forbidden trailers (never refuses)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_trailers.py --check --root . --ticket "$1"
```

Copy its lines verbatim into the close note and the PR body. `clean`, a `FINDING <sha> <trailer>` (a commit
carrying a trailer `git.forbiddenTrailers` lists) or `unknown - <why>`: this report never refuses done and crew
never rewrites the commits — a rewrite is the owner's decision, and it stales check 1.

## On all five passing

1. A sliced plan (T-0059): run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py slice --root . --ticket "$1"`; on `final=no` set the header to `status: in-progress` instead (it keeps the approval), run the same script's `slice-done --root . --ticket "$1"`, say "slice <n> of <m> done" and stop here - the ticket stays open and steps 2-4 wait for the last slice (`slice=none` or `final=yes` goes on; exit 1 stops). Otherwise set `.work/tickets/$1/spec.md`'s header to `status: done`; changing only
   that value keeps the approval, so the checks above stay true. Then move the
   tracker: `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket "$1" --to done`.
   Print its lines verbatim; on exit 3 run the command it printed (Jira, SDP);
   on exit 1 tell me `tracker not updated: <reason>` — done still stands.
2. Append this ticket's row to `.crew/metrics.jsonl` with the metrics
   harness. Anything it cannot measure is written `UNKNOWN`, never `0`:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_metrics.py record --ticket "$1"
```

3. Delete `.work/HANDOFF.md` if present — a stale handoff reads as current to
   the next session, the same rule `/crew:work`'s old step 14 states. <!-- deliberate -->
4. Report: each of the five checks and its result, then **Not verified:** every verify rule that exited 77 (a
   missing tool, not a pass), any suite that did not run on this OS, `drift-detection.sh` (skipped by
   default), and anything checked only by reading. Write "Nothing" only when that is true.

## Landing through the merge train

Only when `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_train.py" status`
prints `armed: yes` (L-0520; parallel lanes in one clone). Crew never merges:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_train.py" check-land --ticket "$1" --pr <PR>
```

It refuses unless this ticket holds the train, `git merge-tree` is clean, the base has not moved in Touch
paths, and HEAD carries checks 1 and 2. On `LAND_OK` run the `gh pr merge <PR> --merge --match-head-commit <sha>`
it printed, then `crew_train.py release --ticket "$1" --merged <merge sha>`. A refusal names
`crew_train.py catch-up` (a merge, never a rebase). Land in this order, so the tree the gate passed is the
tree that lands: catch up (resolve any conflict), bump the version one past the base's, refresh the artifacts,
commit, gate the merged head, review it again if `review_ledger.py --check-receipt` reads stale, then rerun
this command. After the review, a re-anchor changes only the sha on the `anchor:` line (or a diagram's header)
and regenerates the rules; its provenance sentence goes in the ticket's `notes.md`, since any other byte in a
code map, rules file or diagram is read as unreviewed.
