---
paths:
  - "plugin/crew/**"
  - "_verify/smoke.sh"
  - "scripts/check-marketplace.py"
---
<!-- crew:generated source=.crew/codemap/verification-harness.md sha256=bc0ae8499b0c49c7 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# verification-harness
Code map anchor `92c93bf7`; if it is behind HEAD, re-check with `git diff --name-only 92c93bf7..HEAD -- <cited paths>`.
Covers: _verify/smoke.sh, _verify/run-all.sh, scripts/check-marketplace.py, and .crew/verify.json — what each actually runs, and where they overlap or don't. .crew/verify.json is tracked; its own anchor field (:3) is stale at 5238be3d, independent of this note's anchor.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); re-anchored to 89ebda03 (L-0558 merges main 52489039); re-anchored to b83598eb (T-0504 merges main 05a679bf, crew 1.0.107); re-anchored to 92c93bf7 (T-0504 guide rebuild)
## Entry points
- `.crew/verify.json:170-175` (rule 9) — the whole-suite pytest rule and its 377s pricing.
- `.crew/verify.json:117-127` (rule 6) — the T-0005 cloud-guard suites.
- `.crew/verify.json:185-190` (rule 11) — the T-0026 approval-digest suite.
- `.crew/verify.json:199-203` (rule 13) — the crew-diagrams `render.sh` exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` / `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap, no-pipe fallback refusal.
- `.crew/verify.json:269` (rule 24) — the `.claude/rules/` sync check.
- `.crew/verify.json:270-289` (rule 25) — the T-0008 refresh-check suite; `plugin/crew/tests/sabotage.py:75`, `:3057` — `sabotage_refresh.py`'s registration.
- `.crew/verify.json:291-301` (rule 26) — the T-0006 auto-resume suite; `plugin/crew/tests/sabotage.py:76`, `:3058` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:302-311` (rule 27) — the T-0004/T-0018/T-0072 autopilot suite; `plugin/crew/tests/sabotage.py:77`, `:3058` — `sabotage_autopilot.py`'s registration.
- `.crew/verify.json:312-318` (rule 28) — the T-0010 policy suite; `plugin/crew/tests/sabotage.py:77`, `:3059` register its `POLICY_MUTATIONS`.
- `.crew/verify.json:319-326` (rule 29) — the T-0021 tracker suite; `plugin/crew/tests/sabotage.py:78`, `:3058` — `sabotage_tracker.py`'s registration.
- `.crew/verify.json:327-335` (rule 30) — the T-0023 plain-text routing suite; `plugin/crew/tests/sabotage.py:79`, `:3058` — `sabotage_route.py`'s registration.
- `.crew/verify.json:337-344` (rule 31) — the T-0024 group-approval suite; `plugin/crew/tests/sabotage.py:81`, `:3059` — `sabotage_approval.py`'s registration.
- `.crew/verify.json:345-352` (rule 32) — T-0094's refresh-admission suite, split out of rule 25.
- `.crew/verify.json:374-386` (rule 36) — the T-0085 standards suite; `plugin/crew/tests/sabotage.py:85`, `:3062` — `sabotage_standards.py`'s registration.
- `.crew/verify.json:387` (rule 37) — L-0520's merge train suite (`crew_train.py`, `test_crew_train.py`); its sabotage entries are L-0526.
- `.crew/verify.json:388-413` (rule 38) — the T-0087 harness rule; `scripts/check-tooling-pr.py` and its suite `scripts/_test/tooling-pr.py`; `plugin/crew/tests/sabotage.py:82`, `:3061` — `sabotage_tooling.py`'s registr...
Full note: `.crew/codemap/verification-harness.md`.
