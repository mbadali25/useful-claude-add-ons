# L-0709 self-check
<!-- stamp: bundle=eef049089f63f0b6b87de4d3b533b188569865f53b479714497b07f1bf180681 standards=2a02982acc8605a42efda8d9aeddcccbcc18a81e18d78b19dfbd5cade8a11c2f base=f3ccccc36fffe17a167366b0c1696b37063ee73a -->

standards: 24 in sets GEN, PYTHON, REPO; overlay: present (.crew/standards.md); digest 2a02982a

Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that
covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`
(the reason it does not apply to this change). Then run `crew_standards.py stamp`;
any later edit to the change needs a new stamp.

| ID | Status | Evidence or reason |
|---|---|---|
| GEN-01 | addressed | an unreadable/absent real-home record is treated as a home to guard, not as no home; audit violations fail the test at teardown (plugin/crew/tests/test_hermetic_home.py::test_the_audit_fails_a_test_that_reaches_the_real_home) |
| GEN-02 | n/a | the change writes only throwaway per-test/session homes under pytest tmp dirs; no file another process shares is rewritten |
| GEN-03 | n/a | no irreversible action; test-suite fixtures only |
| GEN-04 | addressed | must-block and must-allow pairs: plugin/crew/tests/test_hermetic_home.py::test_an_open_under_the_real_home_is_a_violation / test_an_open_elsewhere_is_allowed, test_a_spawn_is_a_violation_only_when_handed_a_real_home, quarantine deselected / runs when named; hand sabotage per plan step 4 (sabotage entries are L-0738) |
| GEN-05 | n/a | no classification of text another program interprets |
| GEN-06 | addressed | audit paths are compared after abspath/realpath and normalised roots (plugin/crew/tests/test_hermetic_home.py::test_an_open_through_a_symlink_into_the_real_home_is_a_violation) |
| GEN-07 | addressed | quarantine marker args are validated at collection (test_an_ownerless_quarantine_fails_collection) |
| GEN-08 | addressed | Windows drive-letter case normalised (1d2707dfc, CI run 37804465747); crew-windows-default/slow jobs green on 6245dfce6 |
| GEN-09 | addressed | README section 25 paragraph, harness.md H3/H4, VERIFYING.md and CHANGELOG describe the fixture, audit and node-id quarantine as built at HEAD |
| GEN-10 | addressed | pytest monkeypatch.undo and audit-hook behaviour measured in CI runs 37807328232 and 37811774146 (fixed by a62f19247, a1b71e0b7) |
| GEN-11 | addressed | every HOME-family variable (HOME, USERPROFILE, XDG_*, CLAUDE_CONFIG_DIR, CLAUDE_PROJECT_DIR) handled on every path: test_every_home_variable_is_this_test_s_own, test_claude_dirs_are_unset_for_the_session_too |
| GEN-12 | addressed | local gate (scripts/gate-runner.py) on 60d5fb6bf: pytest-combined 19913 passed; CI re-runs on the pushed head before merge |
| PYTHON-01 | addressed | text writes in plugin/crew/tests/test_hermetic_home.py state encoding="utf-8"; subprocess text mode for pytest output only |
| PYTHON-03 | n/a | no line protocol produced or consumed |
| PYTHON-04 | n/a | no file another process reads is rewritten |
| PYTHON-06 | addressed | children launched as argv lists via sys.executable (plugin/crew/tests/test_hermetic_home.py::_pytest) |
| PYTHON-07 | addressed | every inner subprocess.run carries timeout= (plugin/crew/tests/test_hermetic_home.py:91,128,146) |
| PYTHON-08 | addressed | the change is this rule: every test and its children get a constructed home (conftest.py _isolated_home, session home) |
| PYTHON-10 | n/a | no JSON or TOML parsed by the change |
| PYTHON-11 | n/a | no exception classification added |
| PYTHON-13 | addressed | home_open_violation compares canonicalised (realpath, normcase) paths against normalised roots; symlink case tested |
| REPO-01 | n/a | no identity decision |
| REPO-02 | n/a | no change detector or fingerprint |
| REPO-03 | addressed | version bump set last on the land branch above origin/main; CHANGELOG under the release entry at land time |
