---
description: Write, update, or audit operational runbooks
argument-hint: <name | --from-ticket T-#### | --audit | --verify <name>>
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

$ARGUMENTS

## Writing one (`<name>` or `--from-ticket`)

1. Build from evidence, per the `crew-runbooks` skill: the commands actually run
   in this session, `.crew/verify.json`, and the deploy or terraform config for
   real resource names. **Never write a resource name from memory** — a wrong
   name in a runbook is worse than no runbook, because it is followed under
   pressure.
2. Ask me for the two things that are not in any file: the symptoms someone would
   see when this is needed, and who to escalate to.
3. Write `docs/runbooks/<verb>-<thing>.md` in the skill's format. Exact commands,
   a verify line after every destructive step, a rollback, and named escalation.
4. Set `last verified: NEVER` unless I confirm it has actually been run end to
   end. Do not leave the field blank.
5. Add the symptom row to `docs/runbooks/INDEX.md`.

## `--verify <name>`

Walk me through it step by step, in dev or a safe environment. Record what
differed from what was written and fix the runbook as we go. Then update
`last verified` with today's date and my name.

This is the only thing that makes a runbook trustworthy. A runbook that has never
been executed is a guess formatted as instructions.

## `--audit`

Report only:

- Runbooks with `last verified: NEVER` or older than 90 days
- Commands referencing resources absent from the current terraform or config
- Symptoms in INDEX.md with no matching alarm or alert
- Runbooks for systems that no longer exist

Do not fix them. A runbook edited without being run is still unverified, and
quietly updating one converts a known-stale procedure into an apparently-fresh
one, which is worse.
