---
description: Build or refresh the verification map from evidence
argument-hint: [--refresh]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Build `.crew/verify.json` — the map from changed paths to the checks they require.

1. Inventory what exists: test directories, test scripts in `package.json` /
   `*.csproj` / `Makefile` / `composer.json`, CI workflow steps, `e2e/` specs.
   Read the CI config carefully — it is the closest thing to an existing map.
2. Find what actually changes:
   `git log --format= --name-only -300 | sort | uniq -c | sort -rn | head -30`
3. Pair hot paths with the checks that cover them.
4. **Verify each pairing.** Break the code deliberately, run the mapped check,
   confirm red, revert. An unverified mapping is a guess written in JSON.
   Report any pairing that stayed green — that is a coverage hole worth knowing.
5. Time each check. Anything over ~3 minutes belongs in CI, not the local gate.
6. Write the map with a `why` on every rule and `"unmapped": "fail"`.
7. Report: rules created, paths left unmapped, and every pairing that failed
   step 4.

If the repo has no meaningful tests, do not fabricate a map. Say so, and hand off
to `crew:smoke-author` — a map pointing at checks that cannot fail is worse than
no map, because the gate turns green and everyone relaxes.

With `--refresh`: keep existing rules, add rules for paths that have appeared
since the recorded anchor, and flag rules whose target files no longer exist.
