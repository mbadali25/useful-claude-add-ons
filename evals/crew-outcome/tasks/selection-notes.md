# Selection notes: L-0728 slice 2, Step 8 (task set for the outcome eval)

Procedure applied: spec Acceptance 9 (frozen). Buckets by `git diff --numstat base reference` added+deleted, excluding
tests (`tests/`, `_test/`, `test_*`), docs (`*.md`, `docs/`), generated (`graphify-out/`, `.claude/rules/`, built guide
files) and version files (`plugin.json`, `marketplace.json`); S < 150, M 150-599, L >= 600. `.crew/verify.json` and
workflow yml files are counted (they are not in the exclusion list). INDEX `done` rows walked oldest first (file order of
`.work/INDEX.md`), measured on 2026-10-19 from the main checkout at origin/main `8fd3df757`.

## Result

Accepted: 2 tasks of the 6 slots.

| bucket | tasks found | status |
|---|---|---|
| S (< 150) | 0 of 2 | could not tell (INDEX exhausted; see rejects) |
| M (150-599) | 1 of 2 (t-0108-nuclei-safe-defaults) | short bucket, could not tell |
| L (>= 600) | 1 of 2 (t-0107-gizmoduck-routine-cli) | short bucket, could not tell |

The INDEX was walked to its last `done` row (row 258, L-0841); no bucket reached 2 tasks, so the walk did not stop early.
Almost every `done` ticket in this repo changes `plugin/crew/`, and most of the rest have either no tests or tests that are
standalone scripts (`python3 scripts/_test/x.py`, no pytest node ids). Reject counts by main reason: touches plugin/crew: 219, other: 21, no tests: 9, tests are not pytest node ids: 7, accepted: 2.

## 1. Task table

| name | ticket | bucket | referenceLines (how measured) | base | reference | hidden tests | defects | run time |
|---|---|---|---|---|---|---|---|---|
| t-0108-nuclei-safe-defaults | T-0108 | M | 263 = gizmoduck.py 138 + scanners/nuclei.py 117 + routine.py 8, from `git diff --numstat base reference` of the ticket's own PR (merge commit d785ccd0); tests, docs, version files excluded | abddc3021878df102a1f6457373edffbecaae118 | 64712986eee7524839beabc70e3c5cfbda640b34 | 148 fail at base with the grading files and pass at reference; 49 are scored in defects (the rest are hardening the statement does not state, see below) | 10 | 1.7 s base, 1.0 s reference (5 test files, 314 tests) |
| t-0107-gizmoduck-routine-cli | T-0107 | L | 656 = gizmoduck.py 649 + bootstrap.sh 4 + bootstrap.ps1 3, from `git diff --numstat base reference` of PR merge 75681fba; tests, fixtures under `_test/`, docs, version files, graphify-out, rules excluded | 22292d633b7d38570daa5fa24fccc060199e317e | 17141f09ef14128dbf8ab01afccd59b98bd30d50 | 99 fail at base and pass at reference; 32 are scored in defects | 9 | 1.8 s base, 0.8 s reference (5 test files, 173 tests); the first cold run took about 4 s |

Both were self-checked by hand with `/root/crew-tmp/l-0728/selfcheck.py <task dir>`: `git archive` of the base sha into a
fresh dir, `git init` plus one commit, the grading files copied over it, `testCommand` run with HOME and TMPDIR pointed at a
scratch dir. Base: every defect test fails, every regression-inventory id passes. Reference tree, same procedure: every
defect test and every inventory id passes and no test is skipped or errors. Ids are the ones `pytest -rA` prints from the
repo root (`plugin/gizmoduck/scripts/_test/...`). The real `validate` command does not exist yet, so this is an
approximation. Runs took 1-4 s in one pytest process, so they did not go through heavy-run.

Test dependencies beyond python3 + pytest: PyYAML (`routine.py` imports it; both tasks and their regression inventory
need it; the repo's own CI installs it).

### What the statements carry and what was left out of the defects (judgement calls)

The ticket suites were hardened over several review rounds and pin private helper names, exact stderr texts and details the
ticket Intent never states (atomic-write retries, lock files, Windows device names, config-file scanning, a `-rld 1s`
flag). A statement written from Intent alone would make those unwinnable for both arms. So:

- Each statement is written from the spec's Intent, Design and Acceptance (not from the diff). It also carries the
  interface the checks drive (`cmd_routine(...)`, `nuclei_argv(...)`, a few constants) and, for T-0107, the stderr texts
  the checks match. This is a deliberate contract-in-the-statement choice; the reviewer should confirm it is acceptable.
- Hidden tests that need something the statement does not state are in the grading files (they run and the reference passes
  them) but are NOT in any defect and NOT in the inventory: neither scored nor counted as regressions.
  T-0108: 99 of 148 (config-file refusal, `-rld`, the nine attack flags, exact manifest error texts, not-a-string and
  not-a-bool refusals). T-0107: 67 of 99 (atomic write, lock, PDF, Windows names, replace hardening, manifest shape
  errors, `--run-manifest` cell shapes).

## 2. Rejects (every `done` row, oldest first, with bucket where measured)

Bucket is the bucket of the row's first code PR (or the named PR) after the exclusions; "n/a" means not measured because
the row has no PR in the INDEX or no code PR. A row is "touches plugin/crew" when a code PR listed for it changes a file
under `plugin/crew/` (strict reading of Acceptance 9). The table is also the list of INDEX rows walked, in order (section 3).

| # | ticket | bucket | outcome |
|---|---|---|---|
| 1 | T-0001 | n/a | REJECT: reference commit is a non-merge (fast-forward) commit that touches plugin/crew (checked with git show --stat). |
| 2 | T-0002 | n/a | REJECT: reference commit is a non-merge (fast-forward) commit that touches plugin/crew (checked with git show --stat). |
| 3 | T-0003 | n/a | REJECT: reference commit is a non-merge (fast-forward) commit that touches plugin/crew (checked with git show --stat). |
| 4 | T-0004 | L(765) | REJECT: reference touches plugin/crew/ (PR #240: 21 files). |
| 5 | T-0005 | L(2923) | REJECT: reference touches plugin/crew/ (PR #241: 19 files). |
| 6 | T-0007 | n/a | REJECT: reference commit is a non-merge (fast-forward) commit that touches plugin/crew (checked with git show --stat). |
| 7 | T-0008 | S(5) | REJECT: reference touches plugin/crew/ (PR #237: 3 files). |
| 8 | T-0006 | L(833) | REJECT: reference touches plugin/crew/ (PR #239: 20 files). |
| 9 | T-0014 | n/a | REJECT: TODO.md only (docs); PR landed as a fast-forward commit. |
| 10 | T-0009 | S(0) | REJECT: reference touches plugin/crew/ (PR #549: 2 files). |
| 11 | T-0010 | L(654) | REJECT: reference touches plugin/crew/ (PR #261: 21 files). |
| 12 | T-0011 | L(719) | REJECT: reference touches plugin/crew/ (PR #353: 15 files). |
| 13 | T-0012 | M(562) | REJECT: reference touches plugin/crew/ (PR #354: 10 files). |
| 14 | T-0013 | M(526) | REJECT: reference touches plugin/crew/ (PR #355: 18 files). |
| 15 | T-0015 | n/a | REJECT: generated refresh only (codemap, graph, diagrams, rules); no hidden tests. |
| 16 | T-0026 | S(113) | REJECT: reference touches plugin/crew/ (PR #238: 11 files). |
| 17 | T-0016 | L(751) | REJECT: reference touches plugin/crew/ (PR #356: 24 files). |
| 18 | T-0017 | L(751) | REJECT: reference touches plugin/crew/ (PR #356: 24 files). |
| 19 | T-0021 | L(1474) | REJECT: reference touches plugin/crew/ (PR #243: 28 files). |
| 20 | T-0022 | L(745) | REJECT: reference touches plugin/crew/ (PR #358: 15 files). |
| 21 | T-0018 | M(390) | REJECT: reference touches plugin/crew/ (PR #245: 9 files). |
| 22 | T-0019 | M(545) | REJECT: reference touches plugin/crew/ (PR #379: 9 files). |
| 23 | T-0020 | M(499) | REJECT: reference touches plugin/crew/ (PR #357: 9 files). |
| 24 | T-0023 | M(424) | REJECT: reference touches plugin/crew/ (PR #244: 15 files). |
| 25 | T-0024 | L(691) | REJECT: reference touches plugin/crew/ (PR #246: 13 files). |
| 26 | T-0025 | M(409) | REJECT: reference touches plugin/crew/ (PR #359: 12 files). |
| 27 | T-0029 | L(3187) | REJECT: reference touches plugin/crew/ (PR #546: 23 files). |
| 28 | T-0028 | L(733) | REJECT: reference touches plugin/crew/ (PR #288: 24 files). |
| 29 | T-0030 | L(3187) | REJECT: reference touches plugin/crew/ (PR #546: 23 files). |
| 30 | T-0031 | L(954) | REJECT: reference touches plugin/crew/ (PR #565: 8 files). |
| 31 | T-0032 | L(1225) | REJECT: reference touches plugin/crew/ (PR #567: 23 files). |
| 32 | T-0034 | S(5) | REJECT: reference touches plugin/crew/ (PR #237: 3 files). |
| 33 | T-0035 | M(546) | REJECT: reference touches plugin/crew/ (PR #344: 11 files). |
| 34 | T-0036 | L(869) | REJECT: reference touches plugin/crew/ (PR #345: 19 files). |
| 35 | T-0038 | M(230) | REJECT: reference touches plugin/crew/ (PR #370: 20 files). |
| 36 | T-0039 | L(767) | REJECT: reference touches plugin/crew/ (PR #346: 14 files). |
| 37 | T-0040 | L(1091) | REJECT: reference touches plugin/crew/ (PR #290: 21 files). |
| 38 | T-0041 | S(7) | REJECT: reference touches plugin/crew/ (PR #348: 13 files). |
| 39 | T-0042 | M(364) | REJECT: reference touches plugin/crew/ (PR #242: 13 files). |
| 40 | T-0043 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 41 | T-0044 | L(1143) | REJECT: reference touches plugin/crew/ (PR #369: 14 files). |
| 42 | T-0045 | L(607) | REJECT: reference touches plugin/crew/ (PR #500: 7 files). |
| 43 | T-0047 | L(619) | REJECT: reference touches plugin/crew/ (PR #347: 8 files). |
| 44 | T-0049 | L(1131) | REJECT: reference touches plugin/crew/ (PR #395: 13 files). |
| 45 | T-0050 | L(1492) | REJECT: reference touches plugin/crew/ (PR #361: 30 files). |
| 46 | T-0051 | L(1224) | REJECT: reference touches plugin/crew/ (PR #362: 28 files). |
| 47 | T-0052 | L(1145) | REJECT: reference touches plugin/crew/ (PR #364: 23 files). |
| 48 | T-0048 | L(623) | REJECT: reference touches plugin/crew/ (PR #360: 6 files). |
| 49 | T-0053 | M(352) | REJECT: reference touches plugin/crew/ (PR #403: 17 files). |
| 50 | T-0054 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 51 | T-0055 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 52 | T-0057 | M(173) | REJECT: reference touches plugin/crew/ (PR #416: 7 files). |
| 53 | T-0058 | L(1145) | REJECT: reference touches plugin/crew/ (PR #364: 23 files). |
| 54 | T-0059 | L(1145) | REJECT: reference touches plugin/crew/ (PR #364: 23 files). |
| 55 | T-0060 | L(1224) | REJECT: reference touches plugin/crew/ (PR #362: 28 files). |
| 56 | T-0061 | S(7) | REJECT: reference touches plugin/crew/ (PR #350: 9 files). |
| 57 | T-0062 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 58 | T-0063 | M(360) | REJECT: reference touches plugin/crew/ (PR #368: 10 files). |
| 59 | T-0064 | L(692) | REJECT: reference touches plugin/crew/ (PR #367: 15 files). |
| 60 | T-0065 | M(477) | REJECT: reference touches plugin/crew/ (PR #349: 24 files). |
| 61 | T-0066 | M(457) | REJECT: reference touches plugin/crew/ (PR #351: 15 files). |
| 62 | T-0067 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 63 | T-0068 | M(428) | REJECT: reference touches plugin/crew/ (PR #343: 22 files). |
| 64 | T-0069 | S(148) | REJECT: reference touches plugin/crew/ (PR #352: 10 files). |
| 65 | T-0070 | M(308) | REJECT: reference touches plugin/crew/ (PR #342: 15 files). |
| 66 | T-0071 | L(2003) | REJECT: reference touches plugin/crew/ (PR #541: 43 files). |
| 67 | T-0072 | M(294) | REJECT: reference touches plugin/crew/ (PR #250: 13 files). |
| 68 | T-0073 | n/a | REJECT: no merged PR in INDEX; subject is /crew:autopilot (plugin/crew). |
| 69 | T-0074 | M(290) | REJECT: reference touches plugin/crew/ (PR #481: 16 files). |
| 70 | T-0075 | M(429) | REJECT: reference touches plugin/crew/ (PR #254: 24 files). |
| 71 | T-0076 | S(4) | REJECT: reference touches plugin/crew/ (PR #251: 15 files). |
| 72 | T-0077 | M(161) | REJECT: reference touches plugin/crew/ (PR #247: 9 files). |
| 73 | T-0078 | n/a | REJECT: merged into T-0010 (plugin/crew); no PR of its own. |
| 74 | T-0079 | S(61) | REJECT: reference touches plugin/crew/ (PR #249: 11 files). |
| 75 | T-0080 | M(287) | REJECT: reference touches plugin/crew/ (PR #399: 18 files). |
| 76 | T-0081 | S(69) | REJECT: reference touches plugin/crew/ (PR #478: 4 files). |
| 77 | T-0082 | M(287) | REJECT: reference touches plugin/crew/ (PR #399: 18 files). |
| 78 | T-0083 | M(337) | REJECT: hidden tests not pytest-addressable. The only changed test file (plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py) is a script that runs its checks and calls sys.exit at import; `pytest -rA` on it gives INTERNALERROR SystemExit and 0 test ids. |
| 79 | T-0084 | M(486) | REJECT: reference touches plugin/crew/ (PR #450: 6 files). |
| 80 | T-0085 | L(1005) | REJECT: reference touches plugin/crew/ (PR #269: 23 files). |
| 81 | T-0086 | S(0) | REJECT: reference touches plugin/crew/ (PR #282: 8 files). |
| 82 | T-0087 | M(533) | REJECT: reference touches plugin/crew/ (PR #281: 153 files). |
| 83 | T-0088 | M(461) | REJECT: reference touches plugin/crew/ (PR #262: 35 files). |
| 84 | T-0090 | M(395) | REJECT: tests are TypeScript (mcp-servers graphClient.test.ts, node); no python3/pytest tests. |
| 85 | T-0091 | S(0) | REJECT: no non-test, non-doc changed lines (CLAUDE.md edit); nothing to test. |
| 86 | T-0092 | S(30) | REJECT: reference touches plugin/crew/ (PR #257: 10 files). |
| 87 | T-0093 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 88 | T-0094 | L(706) | REJECT: reference touches plugin/crew/ (PR #285: 9 files). |
| 89 | T-0095 | S | REJECT: related PR (a ruff/pylint CI tidy-up) touches plugin/crew files (cloud_guard.py, crew_status.py, tests). |
| 90 | T-0096 | M(226) | REJECT: reference touches plugin/crew/ (PR #398: 10 files). |
| 91 | T-0097 | S(55) | REJECT: reference touches plugin/crew/ (PR #268: 14 files). |
| 92 | T-0098 | M(223) | REJECT: reference touches plugin/crew/ (PR #418: 9 files). |
| 93 | T-0099 | S(10) | REJECT: reference touches plugin/crew/ (PR #278: 4 files). |
| 94 | T-0100 | M(454) | REJECT: reference touches plugin/crew/ (PR #371: 16 files). |
| 95 | T-0101 | M(223) | REJECT: reference touches plugin/crew/ (PR #418: 9 files). |
| 96 | T-0102 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 97 | T-0103 | M(560) | REJECT: reference touches plugin/crew/ (PR #551: 24 files). |
| 98 | T-0104 | S(0) | REJECT: no code diff of its own: its PRs change only Kanban/handoff/doc files (0 changed lines after exclusions); the ticket's work reached main through another route that touches plugin/crew or has no PR. |
| 99 | T-0105 | S(23) | REJECT: reference touches plugin/crew/ (PR #433: 6 files). |
| 100 | T-0106 | M(560) | REJECT: reference touches plugin/crew/ (PR #551: 24 files). |
| 101 | T-0107 | L(656) | ACCEPTED (task t-0107-gizmoduck-routine-cli). |
| 102 | T-0108 | M(263) | ACCEPTED (task t-0108-nuclei-safe-defaults); reference is the ticket's own PR (a cloud-session PR); related bundle PR touching plugin/crew not used. |
| 103 | T-0109 | M(223) | REJECT: reference touches plugin/crew/ (PR #418: 9 files). |
| 104 | T-0027 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 105 | T-0500 | S(0) | REJECT: no code diff of its own: its PRs change only Kanban/handoff/doc files (0 changed lines after exclusions); the ticket's work reached main through another route that touches plugin/crew or has no PR. |
| 106 | T-0501 | S(0) | REJECT: no code diff of its own: its PRs change only Kanban/handoff/doc files (0 changed lines after exclusions); the ticket's work reached main through another route that touches plugin/crew or has no PR. |
| 107 | T-0502 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 108 | T-0503 | S(0) | REJECT: after exclusions 0 changed lines (SKILL.md/api.md/docs); the only test is a shell script (skills/bitbucket/scripts/_test/merge_gate.sh). |
| 109 | T-0504 | S(0) | REJECT: no code diff of its own: its PRs change only Kanban/handoff/doc files (0 changed lines after exclusions); the ticket's work reached main through another route that touches plugin/crew or has no PR. |
| 110 | T-0505 | L(746) | REJECT: reference touches plugin/crew/ (PR #296: 12 files). |
| 111 | T-0506 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 112 | T-0508 | S(2) | REJECT: no tests changed (one workflow line). |
| 113 | L-0509 | L(704) | REJECT: reference touches plugin/crew/ (PR #341: 38 files). |
| 114 | L-0510 | M(497) | REJECT: reference touches plugin/crew/ (PR #318: 13 files). |
| 115 | L-0512 | n/a | REJECT: DROPPED by the owner 2026-10-02; no diff. |
| 116 | L-0513 | L(1413) | REJECT: tests are a standalone script (scripts/_test/gate-runner.py, no test_* functions, run with python3) that also reads .github/workflows; no pytest node ids. |
| 117 | L-0514 | L(1878) | REJECT: reference touches plugin/crew/ (PR #540: 39 files). |
| 118 | L-0516 | S(6) | REJECT: reference touches plugin/crew/ (PR #298: 8 files). |
| 119 | L-0517 | M(151) | REJECT: reference touches plugin/crew/ (PR #539: 7 files). |
| 120 | L-0518 | L(1878) | REJECT: reference touches plugin/crew/ (PR #540: 39 files). |
| 121 | L-0519 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 122 | L-0520 | L(1145) | REJECT: reference touches plugin/crew/ (PR #287: 7 files). |
| 123 | L-0521 | S(18) | REJECT: no tests changed (CI workflow routing). |
| 124 | L-0527 | L(733) | REJECT: reference touches plugin/crew/ (PR #288: 24 files). |
| 125 | L-0528 | L(1878) | REJECT: reference touches plugin/crew/ (PR #540: 39 files). |
| 126 | L-0526 | L(1145) | REJECT: reference touches plugin/crew/ (PR #287: 7 files). |
| 127 | L-0529 | S(0) | REJECT: reference touches plugin/crew/ (PR #283: 6 files). |
| 128 | L-0530 | M(151) | REJECT: reference touches plugin/crew/ (PR #539: 7 files). |
| 129 | L-0531 | S(4) | REJECT: reference touches plugin/crew/ (PR #284: 2 files). |
| 130 | L-0532 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 131 | L-0533 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 132 | L-0534 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 133 | L-0535 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 134 | L-0536 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 135 | L-0537 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 136 | L-0538 | S(112) | REJECT: reference touches plugin/crew/ (PR #548: 28 files). |
| 137 | L-0544 | n/a | REJECT: folded back into T-0029 (plugin/crew). |
| 138 | L-0545 | n/a | REJECT: folded back into T-0029 (plugin/crew). |
| 139 | L-0550 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 140 | L-0551 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 141 | L-0555 | L(690) | REJECT: reference touches plugin/crew/ (PR #310: 5 files). |
| 142 | L-0557 | S(9) | REJECT: reference touches plugin/crew/ (PR #300: 8 files). |
| 143 | L-0558 | L(1145) | REJECT: reference touches plugin/crew/ (PR #287: 7 files). |
| 144 | L-0562 | M(318) | REJECT: reference touches plugin/crew/ (PR #372: 7 files). |
| 145 | L-0561 | S(46) | REJECT: no tests changed (registration). |
| 146 | L-0563 | S(6) | REJECT: reference touches plugin/crew/ (PR #298: 8 files). |
| 147 | L-0572 | M(550) | REJECT: reference touches plugin/crew/ (PR #309: 9 files). |
| 148 | L-0574 | L(1643) | REJECT: reference touches plugin/crew/ (PR #323: 13 files). |
| 149 | L-0575 | M(365) | REJECT: reference touches plugin/crew/ (PR #311: 9 files). |
| 150 | L-0576 | S(125) | REJECT: reference touches plugin/crew/ (PR #306: 16 files). |
| 151 | L-0577 | L(626) | REJECT: tests are a standalone script (scripts/_test/windows-shards.py); no pytest node ids. |
| 152 | L-0578 | M(442) | REJECT: reference touches plugin/crew/ (PR #304: 12 files). |
| 153 | L-0582 | S(149) | REJECT: reference touches plugin/crew/ (PR #338: 10 files). |
| 154 | L-0587 | S(15) | REJECT: test is a standalone script (scripts/_test/shellcheck-directives.py); no pytest node ids. |
| 155 | L-0590 | L(2371) | REJECT: reference touches plugin/crew/ (PR #555: 75 files). |
| 156 | L-0591 | n/a | REJECT: no merged PR in INDEX and no merge commit found by grep; title is a marketplace rename (not measured). |
| 157 | L-0593 | S(6) | REJECT: no tests changed (workflow line). |
| 158 | L-0595 | n/a | REJECT: investigation of CI runner slowness; no merged PR in INDEX, no code diff found. |
| 159 | L-0592 | M(365) | REJECT: reference touches plugin/crew/ (PR #311: 9 files). |
| 160 | L-0597 | S(0) | REJECT: docs only. |
| 161 | L-0598 | S(14) | REJECT: reference touches plugin/crew/ (PR #321: 4 files). |
| 162 | L-0599 | S(4) | REJECT: no tests changed (pylint fix). |
| 163 | L-0600 | S(0) | REJECT: docs/verify map only. |
| 164 | L-0601 | S(119) | REJECT: reference touches plugin/crew/ (PR #325: 6 files). |
| 165 | L-0605 | L(1643) | REJECT: reference touches plugin/crew/ (PR #323: 13 files). |
| 166 | L-0608 | S(7) | REJECT: reference touches plugin/crew/ (PR #331: 11 files). |
| 167 | L-0618 | L(1257) | REJECT: reference touches plugin/crew/ (PR #337: 15 files). |
| 168 | L-0633 | L(954) | REJECT: reference touches plugin/crew/ (PR #565: 8 files). |
| 169 | L-0634 | L(954) | REJECT: reference touches plugin/crew/ (PR #565: 8 files). |
| 170 | L-0636 | L(1225) | REJECT: reference touches plugin/crew/ (PR #567: 23 files). |
| 171 | L-0637 | L(1225) | REJECT: reference touches plugin/crew/ (PR #567: 23 files). |
| 172 | L-0639 | M(443) | REJECT: reference touches plugin/crew/ (PR #543: 8 files). |
| 173 | L-0640 | M(443) | REJECT: reference touches plugin/crew/ (PR #543: 8 files). |
| 174 | L-0641 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 175 | L-0642 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 176 | L-0644 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 177 | L-0645 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 178 | L-0646 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 179 | L-0647 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 180 | L-0648 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 181 | L-0649 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 182 | L-0652 | M(381) | REJECT: reference touches plugin/crew/ (PR #427: 12 files). |
| 183 | L-0657 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 184 | L-0661 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 185 | L-0662 | M(253) | REJECT: reference touches plugin/crew/ (PR #420: 7 files). |
| 186 | L-0663 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 187 | L-0664 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 188 | L-0665 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 189 | L-0666 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 190 | L-0667 | L(1225) | REJECT: reference touches plugin/crew/ (PR #567: 23 files). |
| 191 | L-0669 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 192 | L-0670 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 193 | L-0672 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 194 | L-0673 | S(51) | REJECT: reference touches plugin/crew/ (PR #401: 5 files). |
| 195 | L-0675 | M(560) | REJECT: reference touches plugin/crew/ (PR #551: 24 files). |
| 196 | L-0676 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 197 | L-0677 | L(701) | REJECT: reference touches plugin/crew/ (PR #456: 6 files). |
| 198 | L-0678 | M(276) | REJECT: reference touches plugin/crew/ (PR #462: 5 files). |
| 199 | L-0679 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 200 | L-0680 | M(569) | REJECT: reference touches plugin/crew/ (PR #400: 15 files). |
| 201 | L-0681 | L(1889) | REJECT: reference touches plugin/crew/ (PR #542: 63 files). |
| 202 | L-0682 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 203 | L-0683 | S(23) | REJECT: reference touches plugin/crew/ (PR #433: 6 files). |
| 204 | L-0684 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 205 | L-0685 | L(1691) | REJECT: reference touches plugin/crew/ (PR #552: 10 files). |
| 206 | L-0687 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 207 | L-0688 | S(31) | REJECT: reference touches plugin/crew/ (PR #405: 4 files). |
| 208 | L-0689 | L(3540) | REJECT: reference touches plugin/crew/ (PR #562: 43 files). |
| 209 | L-0690 | L(1889) | REJECT: reference touches plugin/crew/ (PR #542: 63 files). |
| 210 | L-1500 | S(78) | REJECT: reference touches plugin/crew/ (PR #392: 5 files). |
| 211 | L-1501 | S(0) | REJECT: reference touches plugin/crew/ (PR #393: 2 files). |
| 212 | L-1503 | L(651) | REJECT: reference touches plugin/crew/ (PR #489: 9 files). |
| 213 | L-1506 | S(19) | REJECT: no tests changed (workflow and a script line). |
| 214 | L-1507 | S(135) | REJECT: test is a standalone script (scripts/_test/windows-shards.py); no pytest node ids. |
| 215 | L-1508 | S(127) | REJECT: reference touches plugin/crew/ (PR #493: 24 files). |
| 216 | L-1510 | S(20) | REJECT: reference touches plugin/crew/ (PR #494: 6 files). |
| 217 | L-1512 | M(153) | REJECT: reference touches plugin/crew/ (PR #497: 5 files). |
| 218 | L-1514 | S(0) | REJECT: skill markdown only. |
| 219 | L-1518 | M(224) | REJECT: test is a standalone script (scripts/_test/sync-updates.py); no pytest node ids. |
| 220 | C-0001 | M(478) | REJECT: test is a standalone script (scripts/_test/ci-select.py); no pytest node ids. |
| 221 | C-0008 | M(572) | REJECT: not hermetic. Its tests (test_bootstrap_version.py) drive bootstrap.sh under bash and bootstrap.ps1 under pwsh (pwsh cases skip without it, and a skip counts as failed); run against the base tree with the reference tests they call real `curl` (HTTP 403 seen) because the behaviour that stubs the network is what the task asks for. |
| 222 | C-0009 | M(230) | REJECT: no tests changed (cloud setup script). |
| 223 | C-0006 | S(0) | REJECT: reference touches plugin/crew/ (PR #512: 1 files). |
| 224 | C-0015 | S(32) | REJECT: hidden tests are bash/pwsh driven: with the reference tests applied to the base tree exactly 1 test fails and it needs pwsh (ps1 function under pwsh); not python3 + pytest only, and a single-test defect set. |
| 225 | C-0017 | S(32) | REJECT: same PR as C-0015 (and its diff is the C-0015 diff, not the crew_keys NIT the row names). |
| 226 | L-0704 | S(0) | REJECT: reference touches plugin/crew/ (PR #545: 1 files). |
| 227 | L-0708 | L(1225) | REJECT: reference touches plugin/crew/ (PR #567: 23 files). |
| 228 | T-0089 | S(4) | REJECT: reference touches plugin/crew/ (PR #251: 15 files). |
| 229 | C-0021 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 230 | C-0025 | L(2003) | REJECT: reference touches plugin/crew/ (PR #541: 43 files). |
| 231 | C-0028 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 232 | C-0034 | L(1751) | REJECT: reference touches plugin/crew/ (PR #570: 32 files). |
| 233 | C-0042 | S(62) | REJECT: reference touches plugin/crew/ (PR #564: 31 files). |
| 234 | C-0060 | S(1) | REJECT: reference touches plugin/crew/ (PR #561: 2 files). |
| 235 | C-0063 | L(2371) | REJECT: reference touches plugin/crew/ (PR #559: 76 files). |
| 236 | L-0709 | n/a | REJECT: reference touches plugin/crew/ (10 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 237 | L-0710 | n/a | REJECT: reference touches plugin/crew/ (5 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 238 | L-0711 | n/a | REJECT: reference touches plugin/crew/ (9 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 239 | L-0712 | n/a | REJECT: reference touches plugin/crew/ (23 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 240 | L-0713 | L(695) | REJECT: reference touches plugin/crew/ (PR #580: 35 files). |
| 241 | L-0726 | n/a | REJECT: reference touches plugin/crew/ (15 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 242 | L-0758 | n/a | REJECT: no merge commit found; subject is a plugin/crew test marker. |
| 243 | L-0759 | n/a | REJECT: reference touches plugin/crew/ (2 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 244 | L-0760 | S | REJECT: workflow yml only (2 files, 0 under plugin/crew) but no tests. |
| 245 | L-0770 | n/a | REJECT: reference touches plugin/crew/ (9 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 246 | L-0780 | n/a | REJECT: reference touches plugin/crew/ (10 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 247 | L-0782 | n/a | REJECT: reference touches plugin/crew/ (8 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 248 | L-0789 | n/a | REJECT: reference touches plugin/crew/ (2 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 249 | L-0797 | n/a | REJECT: reference touches plugin/crew/ (12 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 250 | L-0798 | n/a | REJECT: no merge commit found; subject is crew role/model pins (plugin/crew). |
| 251 | L-0801 | S | REJECT: README install-URL re-pin only; no tests. |
| 252 | L-0796 | n/a | REJECT: reference touches plugin/crew/ (15 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 253 | L-0802 | n/a | REJECT: reference touches plugin/crew/ (2 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 254 | L-0804 | n/a | REJECT: codemap re-anchor only; no merge commit found. |
| 255 | L-0806 | n/a | REJECT: reference touches plugin/crew/ (2 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 256 | L-0805 | n/a | REJECT: reference touches plugin/crew/ (16 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 257 | L-0836 | n/a | REJECT: reference touches plugin/crew/ (6 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |
| 258 | L-0841 | n/a | REJECT: reference touches plugin/crew/ (15 files in the ticket's merge, found by `git log --merges --grep`; the INDEX row lists no merged PR). |

## 3. INDEX rows walked

All 258 `done` rows of `.work/INDEX.md` were walked in file order, T-0001 first and L-0841 last (the table above is that
order; `#` is the position among `done` rows). Stopped at: no row; the INDEX was exhausted with S 0/2, M 1/2, L 1/2.

## Ambiguities in the procedure and what was chosen

1. **Which diff is "the reference diff" for a ticket with several PRs.** Chosen: the ticket's own PR (branch named for the
   ticket, or for a cloud-session ticket the PR its row names first). A bundle PR that merges several tickets (one that
   lists T-0108 beside T-0035, T-0051 and T-0105 and touches `plugin/crew/`) is not the ticket's reference. Under a
   stricter reading that counts any listed PR, T-0108 would also be rejected as touching `plugin/crew/`.
2. **"Touches nothing under plugin/crew/"** is applied to the whole PR net diff, docs and version files included.
3. **"Hermetic, python3 + pytest only"** is read as: pytest-collectable node ids, no bash/pwsh/node/docker dependency, no
   network at base or reference. PyYAML is allowed (the plugin's own import). Under a looser reading C-0008 (M,
   bash-driven) and C-0015 (S, pwsh-driven) would qualify; they are rejected because the base-tree run reaches `curl`
   (HTTP 403 seen) and a pwsh-gated skip counts as failed.
4. **Standalone script tests** (`scripts/_test/*.py` run by `python3`) have no pytest node ids, so they cannot fill
   `defects` or `regressionInventory`; seven M/L/S candidates were rejected for that (L-0513, L-0577, L-0587, L-1507,
   L-1518, C-0001, T-0083). A wrapper that runs the script and exposes one node id per case would be a harness change.
5. **Row order** is the file order of `.work/INDEX.md`: ticket-number order within each prefix (T-, then L-, then C-), not
   merge date.
6. **Same-PR tickets** (C-0015 and C-0017) are one candidate for selection purposes.
7. **Merge shape.** T-0108 and T-0107 both merged as merge commits; reference = second parent (PR head), base =
   `git merge-base M^1 M^2`. Both PR heads contain merges of main, and the net numstat shows only the ticket's own files.
