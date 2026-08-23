# _verify

Every check that proves this repository works. One directory, so that "is it
tested" has a place to be answered instead of being folk knowledge.

crew reads this directory. `.crew/verify.json` maps changed paths to the scripts
in here, the `Stop` hook runs whichever ones a change requires, and
`/crew:promote` runs them against a deployed environment. A check that lives
here and is named in `verify.json` is a check that actually runs; one that lives
here and is named nowhere is decoration, and the audit will say so.

## Layout

| Path | What it is | When it runs |
|---|---|---|
| `smoke.sh` | Fast, shallow: does the thing respond at all | Every change, every deploy |
| `run-all.sh` | The full regression suite | Before promotion, nightly |
| `check-logs.sh` | Reads an environment's error log, exits non-zero on new errors | After a deploy soak |
| `check-alarms.sh` | Reads the monitoring/alarm state for an environment | After a deploy soak |
| `cases/` | Individual named checks, one file each | Called by the two runners |
| `fixtures/` | Test data. Never real customer data | Loaded by cases |

Delete the rows that do not apply. An empty file that pretends to be a check is
worse than a missing one.

## The contract every script here honours

1. **Exit 0 means pass. Any other exit means stop.** No "warnings" that exit 0.
2. **Takes `--env <name>`**, defaulting to the local/development environment.
   Print the resolved target host or URL on the first line - a suite that passes
   against the wrong environment is the most convincing wrong answer available.
3. **Never touches production data.** Read-only against prod, or it does not run
   against prod at all. Under `run-all.sh --read-only` a case runs **only** if it
   contains the line `# readonly: yes` - an allowlist, because the cost of
   guessing wrong is a write against production. Unmarked cases are skipped and
   reported as skipped, so the omission is visible rather than silent.
4. **Says what it checked**, one line per check, `PASS`/`FAIL` prefixed, and a
   final count. Silence on success is not acceptable - it is indistinguishable
   from a suite that ran nothing.
5. **Cleans up after itself**, via `trap`, including on failure.

## Adding a check

1. Write it in `cases/` as one file, one concern, named for what it proves:
   `write-roundtrip.sh`, not `test3.sh`.
2. Call it from `smoke.sh` (if it is fast and shallow) or `run-all.sh`.
3. Add or extend the rule in `.crew/verify.json` so a change to the code it
   covers actually triggers it. **This step is the one that gets skipped**, and
   skipping it is how a repo ends up with a full `_verify/` directory and no
   coverage.
4. Add a row to the table in this file.
5. Sabotage-test it once: reintroduce the bug it is supposed to catch and
   confirm it goes red. A check that has never failed has never been proven to
   be able to fail.

## What does not belong here

- Unit tests. Those live with the code and run from the language's own runner.
  `run-all.sh` may call that runner; it does not replace it.
- Anything needing a credential in a file. Credentials come from the environment
  or a secrets manager at run time - see the `crew-verification` skill.
- Anything that takes longer than the gate can afford. Slow checks belong in
  `run-all.sh` and the pull request, not in `smoke.sh`.

## Status

| Check | Covers | Last sabotage-tested |
|---|---|---|
| _(fill this in as you add checks)_ | | |
