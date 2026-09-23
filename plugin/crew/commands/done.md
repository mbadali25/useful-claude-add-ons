---
description: Close a ticket - requires an accepted review receipt, a clean verify gate, and a passing completion audit
argument-hint: <ticket id>
allowed-tools: Read, Write, Edit, Bash
---

Close ticket $1. **All three checks below must pass. Any one failing refuses
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

Read its `verify` line. Anything other than every rule `pass` — `fail`,
`unverified`, or no record at all — refuses done. Run `./_verify/smoke.sh` (or
the mapped `.crew/verify.json` rule) yourself first if this is the first time
this session has checked.

## Check 3 — the completion audit

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/completion_audit.py --check --ticket "$1"
```

Diffs the whole tree against this ticket's scope base, the same way the Stop
hook's scope audit does, but as a pre-close confirmation rather than a
per-turn block. A non-zero exit names the out-of-scope path; file it to
`TODO.md`, not to this ticket, and rerun.

## On all three passing

1. Set `.work/tickets/$1/spec.md`'s header to `status: done`. Update
   `.work/INDEX.md`'s row to match (files and Obsidian modes), or push the
   tracker item to its closed state (Jira, ServiceDesk Plus) the way
   `/crew:work`'s old step 13 did.
2. Append one row to `.crew/metrics.jsonl` — best effort until T9's harness
   lands; UNKNOWN for anything not measured here, never a guess:

```bash
python3 -c '
import json, datetime
row = {"ticket": "'"$1"'", "date": datetime.date.today().isoformat(),
       "phases": "brainstorm,spec,plan,implement,review,done",
       "activeTime": "UNKNOWN", "tokens": "UNKNOWN", "cost": "UNKNOWN",
       "findingsConfirmed": "UNKNOWN", "findingsRejected": "UNKNOWN",
       "findingsDuplicate": "UNKNOWN", "scopeBlocks": "UNKNOWN",
       "injectedChars": "UNKNOWN", "escapedDefects": "UNKNOWN"}
with open(".crew/metrics.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(row) + "\n")
'
```

3. Delete `.work/HANDOFF.md` if present — a stale handoff reads as current to
   the next session, the same rule `/crew:work`'s old step 14 states.
4. If `notify.provider` is not `none`:
   `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh done "$1 complete"`

Do not run step 4 before checks 1–3 pass. "Done" that means "I stopped typing"
is the reason nobody trusts a notification channel — the same line `/crew:work`
opened with.
