# L-0563 Sabotage entries for L-0516's deadline polls (tooling PR split from L-0516)          status: spec   risk: low

## Intent

`sabotage.py` carries four mutations that prove L-0516's fixes catch real failures: `poll_until` probing once, `poll_until` reporting success at the deadline, `wait_for_pidfile` accepting an empty pidfile, and `completion-audit.ps1`'s tree kill reduced to `Kill($false)`. Each goes RED on its named test.

## Exclusions

- No change to `poll_fixtures.py`, the tests or `completion-audit.ps1` (L-0516 owns them; the ps1 file is only a mutation target).
- Do not edit `sabotage.py` (max-module-lines); the entries ride in `sabotage_qa.py`, as L-0531 did.

## Evidence

- Measured on L-0516's branch at `080cea00`: each entry applied by hand turned its target test red, and a `sabotage.py` run filtered to the four printed `RED (good)` x4 and `SABOTAGE SUITE: PASS` (exit 0). The ps1 entry's hand run failed with `AssertionError: assert ('/usr/bin/py...4', [1852359]) == ('/usr/bin/python3.14', [])`.
- `test_sabotage_harness.py::test_every_shipped_anchor_is_present_in_its_target_exactly_once` passed with the four entries.

## Unknowns

- U1. The ps1 entry needs pwsh on the host running sabotage.py (7.6.5 here). Where pwsh is absent the target test skips; check how sabotage.py reports a skipped target before landing.

## Touch

- `plugin/crew/tests/sabotage_qa.py`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/verify.json`
- `.crew/codemap/**` - refresh artifact: re-anchor only
- `.claude/rules/**` - refresh artifact: regenerated
- `graphify-out/**` - refresh artifact
- `.work/tickets/L-0563/**`

## Acceptance checks

1. A `sabotage.py` run filtered to the four entries reports each `RED (good)`, and the full run ends `SABOTAGE SUITE: PASS`.
2. `python3 scripts/check-tooling-pr.py` exits 0.
3. `python3 scripts/check-marketplace.py` exits 0 after the version bump.
4. `test_sabotage_harness.py::test_every_shipped_anchor_is_present_in_its_target_exactly_once` passes.
