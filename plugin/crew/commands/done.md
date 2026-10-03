---
description: Close a ticket - needs an accepted review receipt, a clean verify gate, a passing completion audit, current artifacts
argument-hint: <ticket id>
allowed-tools: Read, Write, Edit, Bash
---

Close ticket $1. **All four checks below must pass. Any one failing refuses
done** — there is no partial close.

## Check 1 — the review receipt

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/review_ledger.py --ticket "$1" --check-receipt
```

Rebuilds the bundle and fails if anything changed since the receipt was
written. No receipt, a failing rebuild, or a ticket still `NEEDS_REPLAN`
(budget spent, no successor plan approved) all refuse — say which, and point
at `/crew:review $1` or `/crew:plan $1` for a replan.

## Check 2 — the verify gate

The Stop hook already refuses to end a turn on a red gate, so this check is
confirming, not re-deriving:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_status.py --root .
```

Read its `verify` line. Every rule `pass` passes this check. Anything else —
`fail`, `unverified`, or no record at all — passes only on what
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/ci_receipt.py check --root .` says:
exit 0 `CI_RECEIPT VERIFIED` (the self-hosted gate passed every rule on exactly
this committed tree), or exit 4 `NO_GATE` (no verify map, or the gate is stood
down; `check-land` and `/crew:review` pass it too). Any other exit (local edits,
no run for HEAD, an unreadable artifact) refuses done; say its `CI_RECEIPT`
line. Then run `./_verify/smoke.sh` (or the mapped `.crew/verify.json` rule)
yourself and re-read the `verify` line.

## Check 3 — the completion audit

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/completion_audit.py --check --ticket "$1"
```

Diffs the whole tree against this ticket's scope base, the same way the Stop
hook's scope audit does, but as a pre-close confirmation rather than a
per-turn block. A path byte-identical to the merged integration commit (after
a merge of main) is not counted; the verdict's `merged main` line names that
commit and the count, and `merged main: could not tell` (on a pass too) means
every path was counted. A non-zero exit names the out-of-scope path, or a
refresh artifact with the reason it was not admitted (`[anchor did not move]`,
`[no changed path reaches it]`, `[bytes differ from expected_rules ...]`,
`[could not tell: ...]`): re-anchor or regenerate it in `/crew:implement $1`
step 6, or put it in Touch. File any other out-of-scope path to `TODO.md`, not
to this ticket, and rerun.

## Check 4 — artifacts are current

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_refresh_check.py --root . --ticket "$1"
```

Read-only. Any `stale` or `unknown` line refuses done: name the artifact and
what the line says — `refresh with <command>`, or `stop` with its reason (a
missing tool, or a scope base that hides the change). **Do not run the refresh here — a write now
stales check 1's receipt.** Go back to `/crew:implement $1` step 6: refresh,
commit, then `/crew:review $1` again, then rerun this command. Documents read
`not measured`, which is `/crew:docs`'s judgement, not a pass or a refusal.

## On all four passing

1. Set `.work/tickets/$1/spec.md`'s header to `status: done`; changing only
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
4. If `notify.provider` is not `none`:
   `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh done "$1 complete"`

## Landing through the merge train

Only when `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_train.py" status`
prints `armed: yes` (L-0520; parallel lanes in one clone). Crew never merges:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_train.py" check-land --ticket "$1" --pr <PR>
```

It refuses unless this ticket holds the train, `git merge-tree` is clean, the
base has not moved in Touch paths, and HEAD carries checks 1 and 2. On
`LAND_OK` run the `gh pr merge <PR> --merge --match-head-commit <sha>` it
printed, then `crew_train.py release --ticket "$1" --merged <merge sha>`. A
refusal names `crew_train.py catch-up` (a merge, never a rebase): catch up,
gate the merged head again, rerun this command.

Do not run step 4 before checks 1–4 pass. "Done" that means "I stopped typing"
is the reason nobody trusts a notification channel — the same line `/crew:work`
opened with. <!-- deliberate -->
