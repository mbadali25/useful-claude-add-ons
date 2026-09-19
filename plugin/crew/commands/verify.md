---
description: Build or refresh the verification map from evidence
argument-hint: [--refresh]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Build `.crew/verify.json` — the map from changed paths to the checks they require.

1. **Look for `_verify/` first**, then the repo's other conventions — `qa/`,
   `spec/`, `_test*/`. If `_verify/` exists, read its `README.md` and the scripts
   in it, and map every one of them into a rule. If **none** of them exists,
   create `_verify/` from
   `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/templates/_verify/` — `README.md`,
   `smoke.sh`, `run-all.sh`, and a `cases/` directory — then fill in that
   README's layout and status tables with what this repo actually needs. Do not
   leave the template's commented-out examples as the whole file: either write
   real checks or say plainly that the directory is a scaffold with none in it
   yet. If a convention does exist, read it and ask me what runs it and
   when. It will not be discovered for you, and it is usually the most valuable
   thing in the repo for this purpose.
2. Inventory what exists: test directories, test scripts in `package.json` /
   `*.csproj` / `Makefile` / `composer.json`, CI workflow steps, `e2e/` specs.
   Read the CI config carefully — it is the closest thing to an existing map.
3. Find what actually changes:
   `git log --format= --name-only -300 | sort | uniq -c | sort -rn | head -30`
4. Pair hot paths with the checks that cover them.
5. **Verify each pairing.** Break the code deliberately, run the mapped check,
   confirm red, revert. An unverified mapping is a guess written in JSON.
   Report any pairing that stayed green — that is a coverage hole worth knowing.
6. Time each check. Anything over ~3 minutes belongs in CI, not the local gate.
7. Write the map with a `why` on every rule and `"unmapped": "fail"`.
8. Report: rules created, paths left unmapped, and every pairing that failed
   step 4.

If the repo has no meaningful tests, do not fabricate a map. Say so, and hand off
to `crew:smoke-author` — a map pointing at checks that cannot fail is worse than
no map, because the gate turns green and everyone relaxes.

**Running the whole map, unbudgeted.** The Stop gate spends a budget
(`verify.stopBudgetSeconds`, default 60) cheapest-first and DEFERS what does
not fit, printing `deferred to /crew:verify: <cmd> (<n>s)` for each one. Those
were not checked.

**`seconds` prices the RULE, and is charged ONCE.** A rule runs whole or
defers whole, however many commands its `run` holds -- so a rule with
`"seconds": 40` and three commands costs 40 against the budget, not 120. This
sentence exists because the unit was left unstated when the budget was
introduced ("run matched rules in ascending seconds"), and the first
implementation read it per command and split rules in half.

**A command named by more than one source carries the STRONGEST obligation of
any of them.** `always` is unconditional; a rule with no `seconds` is
unconditional-until-priced; only a rule that states `seconds` is deferrable.
Naming a command in `always` and also in a 90s rule therefore RUNS it -- the
merge resolves toward running, never toward deferring. Its stated cost is
still charged against the budget, so the arithmetic in the output stays
honest; the cost simply cannot buy the deferral.

To run everything with no budget:

    bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.sh --all

(or `-All` on the PowerShell flavour). Give every rule a measured `seconds`
when you write the map -- step 6 already times them. A rule with no `seconds`
is UNKNOWN cost, not free: it always runs and the gate says its cost is
unstated, which is the honest default but a poor one to leave in place.

With `--sync`: run
`bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/map-audit.sh` and reconcile.

- A check on disk with no rule: ask me what it covers, then add the rule and
  prove it fires. Do not guess the paths — a wrong mapping is worse than none,
  because it produces false confidence in the pull request.
- A rule pointing at a file that no longer exists: that check has been silently
  passing as a failure or silently skipped. Tell me which, then fix or remove it.

Report the counts before and after.

With `--refresh`: keep existing rules, add rules for paths that have appeared
since the recorded anchor, and flag rules whose target files no longer exist.
