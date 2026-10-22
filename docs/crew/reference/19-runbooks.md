<!-- Moved verbatim from plugin/crew/README.md (19. Runbooks) by L-0726; the README keeps an index entry. -->

## 19. Runbooks

```
/crew:runbook roll-back-inventory-loader
/crew:runbook --from-ticket T-0042
/crew:runbook --verify roll-back-inventory-loader
/crew:runbook --audit
```

A runbook answers exactly one question: **"it's 3am, this is broken, what do I
type?"** Not how the system works — that's architecture. Not why it was built
that way — that's an ADR. A procedure someone half-awake can follow without
judgement calls.

`/crew:implement` captures one when a ticket involved a procedure that will
be repeated, is destructive, or lived only in one person's head. Drafts are built
from the commands **actually run in the session**, plus `verify.json` and the
terraform config for real resource names — never from memory, because a wrong
resource name in a runbook is worse than no runbook. It's followed under
pressure.

Format rules that make one usable at 3am: exact copy-pasteable commands, a
**verify line after every destructive step** (the failure mode is a step that
silently did nothing while the operator moves on), a rollback for the fix itself,
and a named escalation so "I'm stuck" isn't a decision.

### The index is keyed by symptom

`docs/runbooks/INDEX.md` lists symptom → runbook → severity → last verified.
Symptom-first because that's what you have at 3am: you don't know which component
failed, you know what you're seeing. Only the index loads by default; agents read
it, then one runbook — the same token rule as the code map.

### Verification is the whole value

**A runbook nobody has executed is a wish.** Commands drift, resource names
change, a step that used to work now needs a flag. And an unverified runbook is
actively dangerous, because it's trusted exactly when there's no time to check
it.

So every runbook carries `last verified: <date> by <who>`, drafts start at
`NEVER` rather than blank, and `--verify` walks it in dev and fixes what differed.
`--audit` reports anything unverified in 90 days or referencing resources that no
longer exist — and **reports rather than fixes**, because quietly updating a
stale runbook converts a known-stale procedure into an apparently-fresh one.
