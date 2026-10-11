# L-0709 plan - Hermetic tests, then a green main

Against spec.md including the 2026-10-08 amendments and the 2026-10-09 Touch amendment. Branch
`L-0709-hermetic`, worktree `/repos/personal/uca-L-0709`, from origin/main 554ed783 (crew 1.2.1).
Successor plan 2026-10-09: steps 1-6 are the approved plan restated in the Files/Test/Risk form,
unchanged in substance; step 7 is the owner's one-round grant.

1. `crew_fixtures.py`: home isolation helpers - `REAL_HOME_VAR`, `real_homes`, `home_env`,
   `home_allowed_prefixes`, the pure `home_open_violation` / `home_spawn_violation`, `home_audit`,
   `install_home_audit`, `set_home_guard`.
   Files: `plugin/crew/tests/crew_fixtures.py`
   Test: test_hermetic_home.py pure audit cases (must-block and must-allow).
   Risk: an audit hook on every `open` - kept to abspath and prefix compares.
2. `conftest.py`: session home at configure (+ PYTHONUSERBASE / PSModulePath carry, real-home record,
   audit install), restore at unconfigure; autouse `_isolated_home` per test with teardown failure;
   `quarantine` marker, validation and deselection.
   Files: `plugin/crew/tests/conftest.py`
   Test: a full combined run on this host with the real config present, compared against an
   origin/main baseline run.
   Risk: tests that depended on HOME-derived tooling (git global identity, pwsh user modules).
3. Quarantine the two flakes (L-0737); hold the global-config names in test_upgrade.py.
   Files: `plugin/crew/tests/test_review_checks.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_upgrade.py`
   Test: the quarantine rule cases in test_hermetic_home.py; test_upgrade.py itself.
   Risk: a quarantined test silently never runs - it runs when named by node id.
4. `test_hermetic_home.py`: isolation (in-process and spawned), the L-0729 regression against a planted
   operator home with a control that the plant is read, audit must-block/must-allow (pure and end to
   end), quarantine rule cases.
   Files: `plugin/crew/tests/test_hermetic_home.py`
   Test: sabotage by hand - per-test HOME override, session + per-test override, audit off,
   quarantine validation off - each must go red.
   Risk: a test that passes because the plant was never read - the control asserts it is.
5. Docs: crew README paragraph, harness reference, VERIFYING.md, codemap note, CHANGELOG, version
   files, PLUGINS.md, BUDGETS.md.
   Files: `plugin/crew/README.md`, `plugin/crew/skills/crew-qa-standards/references/harness.md`, `VERIFYING.md`, `README.md`, `.crew/codemap/crew.md`, `.crew/codemap/verification-harness.md`, `.claude/rules/verification-harness.md`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/crew/BUDGETS.md`
   Test: python3 scripts/check-marketplace.py; scripts/check-crew-docs.py.
   Risk: version drift between the two version files - the checker compares them.
6. Gate `python3 scripts/gate-runner.py`; review `/crew:review`; PR. Follow-ups: L-0737 (fix the
   flakes), L-0738 (sabotage entries, tooling PR).
   Files: `.crew/verify.json`, `.github/workflows/pytest-crew.yml`
   Test: the local gate and CI on the PR head.
   Risk: pre-existing sabotage failures on main read as this ticket's - compared against main.
7. Owner grant 2026-10-09 (Matthew): ONE extra review round (round 4), narrow scope. The round-3
   budget was spent, so the round runs under this successor plan's fresh budget and uses ONE round of
   it. Scope: the L-0709 commits after the round-3-reviewed tree (4f497f16e, content-equal to round
   3's head 0216c3bec), merges of main excluded - ad50a69df (round-3 fixes), 1d2707dfc, a62f19247,
   a1b71e0b7 (CI fixes), 828fda239 and 9d252f152 (gate fixes). The reviewer also confirms or rejects
   the two declined round-3 findings (BLOCK 3 sys.path prefixes under ~/.claude; FIX 2 symlink
   check/open race). Clean or edge-case-only: accept, file follow-ups, /crew:done, land. Any BLOCK:
   stop for the owner.
   Files: `plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_hermetic_home.py`
   Test: the round-4 review verdict, then /crew:done and CI.
   Risk: a fix found in round 4 has no round left to review it - any BLOCK stops for the owner.
8. Owner decision 2026-10-10 (Matthew): narrow the home audit to the pre-open guard (remove the
   post-open wrapper; the symlink swap, dir_fd-relative opens and pre-install aliases are a declared
   known limit, follow-up L-0761), fix round-5 FIX 2 (the interpreter's own prefix under ~/.claude
   imports), keep the other round-4 fixes. ONE more review round, scoped to a7def3417 and the
   version commit, under a second successor plan (owner-attributed reject, as in step 7).
   Files: `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_hermetic_home.py`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`
   Test: test_hermetic_home.py; hand sabotage S1, S3-S6, S8, S9 red; the local gate; CI.
   Risk: the declared limit is real - L-0761 carries it.
