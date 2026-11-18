# verify-gate.sh: a repeated `verify` or `stopBudgetSeconds` key at any depth resets the Stop budget to 60 s

Priority: P3 (fail-closed edge on a contrived config; the effect is the 60 s default, never no limit).
Status: needs ticket (no T-/L-/C- id yet; pending tickets carry none). Recorded 2026-11-18 from the Codex gpt-6.2-sol review of PR #788 (crew 1.3.162). Codex labelled it blocking; the lead overrode that under the owner's standing authority: it is outside the two fixes #788 set out to make, so it is a follow-up. Priority is the recording agent's proposal; the owner may change it. Scale: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read in the file named; INFERRED = reasoned, not run. The recording agent did not run the example config below.

## Problem
VERIFIED (read `plugin/crew/hooks/scripts/verify-gate.sh` lines 1941-1948 on the #788 branch, head f4d4c8967): the config is parsed with `json.load(..., object_pairs_hook=_once)`. `_once` counts `stopBudgetSeconds` and `verify` among the keys of whichever object it is handed. Python calls the hook for every object at every depth, so a repeated `verify` or `stopBudgetSeconds` key anywhere in the file is treated as a duplicate, not only the two keys the reader uses.
INFERRED (from the above, not run): `{"verify":{"stopBudgetSeconds":120},"other":{"verify":1,"verify":2}}` is refused, and the Stop budget falls back to the 60 s default although the real `verify.stopBudgetSeconds` is a valid 120. The same follows for a repeated `verify` inside any unrelated object.
Effect: fail-closed. The default 60 applies, never no limit, so nothing is skipped or run longer than allowed. The cost is a budget the owner set being silently ignored.

## Recommended next step
Make the check depth-aware: refuse a repeat only for `stopBudgetSeconds` inside the top-level `verify` object, and for a top-level repeated `verify`. For example an `object_pairs_hook` that tracks nesting depth (or parse once, then walk only the path the reader uses). Add tests: a repeated `verify` inside an unrelated object still reads the real budget; a repeated top-level `verify` and a repeated `verify.stopBudgetSeconds` still fall back to 60.

## Constraints
- verify-gate.sh is review harness: the fix lands alone (owner rule T-0087, `HARNESS` in `scripts/check-tooling-pr.py`), with no feature work in the PR.
- A crew re-bump is needed (plugin.json and every place that states the version), plus the docs that describe it (CLAUDE.md "A change to plugin/crew/"), or a `Docs: none - <why>` line.
- Hook that can block: the suite needs must-block and must-allow cases, sabotage-tested (CLAUDE.md "Adding a hook").

## Acceptance criteria
A repeated key outside the two read paths no longer changes the budget; a repeated key on either read path still yields 60; tests cover each, sabotage-tested.
