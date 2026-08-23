---
name: crew-runbooks
description: Write, index, and maintain operational runbooks - deploys, rollbacks, alert response, recurring jobs, disaster recovery. Use when the user says write a runbook, document the deploy process, what do I do when X alerts, how do we roll this back, or asks to capture an operational procedure for later.
---

# Runbooks

A runbook answers one question: **"it is 3am, this is broken, what do I type?"**

That framing decides everything else. Not "how the system works" — that is
architecture documentation. Not "why we chose this" — that is an ADR. A runbook
is a procedure someone half-awake can follow without judgement calls.

## When one gets written

Trigger a runbook when a ticket involved a procedure that:

- has to be done again (deploys, restores, rotations, recurring jobs)
- is destructive or hard to undo (migrations, DNS, key rotation)
- someone would get wrong under pressure
- required knowledge that lived only in one person's head

**Not** for things the tooling already does. If `make deploy` is the whole
procedure, the runbook is one line and should not exist as a file.

## Format

`docs/runbooks/<verb>-<thing>.md`, and keep it short enough to follow on a phone.

```markdown
# Roll back the inventory loader

symptoms: SES error mail from thd-prod-inventory-loader; CloudWatch alarm
          thd-prod-inventory-loader-errors
severity: sev2 - files stop loading, no data loss
last verified: 2026-08-14 by MB
owner: data platform

## Before you start
- [ ] You have AWS creds for account 718678532558
- [ ] You know which version was deployed (check the TFC run history)

## Steps
1. Stop the trigger so nothing new arrives mid-rollback:
   `aws events disable-rule --name thd-prod-inventory-created`
   Verify: `aws events describe-rule --name thd-prod-inventory-created` shows DISABLED

2. Roll the Lambda to the previous version:
   `aws lambda update-alias --function-name thd-prod-inventory-loader --name live --function-version <N-1>`
   Verify: `aws lambda get-alias ...` shows the expected version

3. Re-enable the trigger:
   `aws events enable-rule --name thd-prod-inventory-created`

4. Replay anything missed: re-copy the objects from the archive prefix.

## Verify it worked
- One test file lands and a row appears in `stg.Inventory`
- No new error mail within 10 minutes

## If this did not work
Escalate to <name/channel>. Do not attempt a schema change to work around it.

## Rollback of the rollback
Re-point the alias to the newer version; nothing else changed.
```

Rules that make it usable at 3am:

- **Exact commands, copy-pasteable.** No `<replace with your value>` unless the
  value genuinely cannot be known ahead of time — and then say where to find it.
- **A verify line after every destructive step.** The failure mode is a step that
  silently did nothing while the operator moves on.
- **Rollback for the runbook itself.** What if the fix makes it worse?
- **Escalation named**, so the answer to "I am stuck" is not a decision.
- No prose paragraphs. Numbered steps or checkboxes only.

## The index

`docs/runbooks/INDEX.md`, one line per runbook, keyed by **symptom** rather than
by system:

```
| Symptom | Runbook | Severity | Last verified |
|---|---|---|---|
| Inventory files stop loading | roll-back-inventory-loader.md | sev2 | 2026-08-14 |
| SQL connections exhausted | restart-connection-pool.md | sev1 | 2026-07-02 |
```

Symptom-first because that is what you have at 3am. You do not know which
component failed; you know what you are seeing.

**Only INDEX.md is loaded by default.** Agents read the index, then one runbook.
Same rule as the code map and the Obsidian vault: a directory of procedures
pulled wholesale into context is expensive and mostly irrelevant to the question.

## Verification is the whole value

**A runbook nobody has executed is a wish.** The commands drift, the resource
names change, a step that used to work now needs a flag. An unverified runbook
is actively dangerous: it is trusted precisely when there is no time to check it.

So every runbook carries `last verified: <date> by <who>`, and that line is the
first thing to look at. Verify by actually running it — in dev, or as a
game-day exercise in prod where that is safe.

`/crew:runbook --audit` reports every runbook not verified in 90 days, and every
one whose commands reference resources that no longer exist. It reports; it does
not quietly update, because a runbook edited without being run is still unverified.

## Generating from real work

The good source is what actually happened, not what someone imagines the
procedure to be. After a ticket that involved an operational procedure, build the
draft from:

- the commands actually run in the session (they are in the transcript)
- `.crew/verify.json` for how the thing is validated
- the terraform or deploy config for resource names — never from memory, since
  a wrong resource name in a runbook is worse than a missing runbook

Then mark it `last verified: NEVER` until someone runs it end to end. Be explicit
about that state rather than leaving the field blank and hoping.

## Incident capture

After an incident, the runbook update is more valuable than the postmortem
document, and it is the part that usually gets skipped. Two questions:

1. What did we type? That becomes or corrects a runbook.
2. What did we wish existed? That becomes a ticket, not a runbook entry.
