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
