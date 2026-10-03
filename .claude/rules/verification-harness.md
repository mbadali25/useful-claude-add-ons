---
paths:
  - "plugin/crew/**"
  - "_verify/smoke.sh"
  - "scripts/check-marketplace.py"
---
<!-- crew:generated source=.crew/codemap/verification-harness.md sha256=5641091c1c01e473 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# verification-harness
Code map anchor `6475c41c`; if it is behind HEAD, re-check with `git diff --name-only 6475c41c..HEAD -- <cited paths>`.
## Entry points
- `.crew/verify.json:170-175` (rule 9) — the whole-suite pytest rule and its 377s pricing.
- `.crew/verify.json:117-127` (rule 6) — the T-0005 cloud-guard suites.
- `.crew/verify.json:191-196` (rule 11) — the T-0026 approval-digest suite.
- `.crew/verify.json:205-209` (rule 13) — the crew-diagrams `render.sh` exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` / `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap, no-pipe fallback refusal.
- `.crew/verify.json:275` (rule 24) — the `.claude/rules/` sync check.
- `.crew/verify.json:276-294` (rule 25) — the T-0008 refresh-check suite; `plugin/crew/tests/sabotage.py:75`, `:3057` — `sabotage_refresh.py`'s registration.
- `.crew/verify.json:296-306` (rule 26) — the T-0006 auto-resume suite; `plugin/crew/tests/sabotage.py:76`, `:3058` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:307-315` (rule 27) — the T-0004/T-0018/T-0072 autopilot suite; `plugin/crew/tests/sabotage.py:77`, `:3058` — `sabotage_autopilot.py`'s registration.
- `.crew/verify.json:316-322` (rule 28) — the T-0010 policy suite; `plugin/crew/tests/sabotage.py:77`, `:3059` register its `POLICY_MUTATIONS`.
- `.crew/verify.json:323-330` (rule 29) — the T-0021 tracker suite; `plugin/crew/tests/sabotage.py:78`, `:3058` — `sabotage_tracker.py`'s registration.
- `.crew/verify.json:331-339` (rule 30) — the T-0023 plain-text routing suite; `plugin/crew/tests/sabotage.py:79`, `:3058` — `sabotage_route.py`'s registration.
- `.crew/verify.json:341-348` (rule 31) — the T-0024 group-approval suite; `plugin/crew/tests/sabotage.py:81`, `:3059` — `sabotage_approval.py`'s registration.
- `.crew/verify.json:349-356` (rule 32) — T-0094's refresh-admission suite, split out of rule 25.
- `.crew/verify.json:378-390` (rule 36) — the T-0085 standards suite; `plugin/crew/tests/sabotage.py:85`, `:3062` — `sabotage_standards.py`'s registration.
- `.crew/verify.json:391` (rule 37) — L-0520's merge train suite (`crew_train.py`, `test_crew_train.py`); its sabotage entries are L-0526.
- `.crew/verify.json:392-418` (rule 38) — the T-0087 harness rule; `scripts/check-tooling-pr.py` and its suite `scripts/_test/tooling-pr.py`; `plugin/crew/tests/sabotage.py:82`, `:3061` — `sabotage_tooling.py`'s registr...
- `.crew/verify.json:419-432` (rule 39) — T-0028's Kimi Code provider suite (`kimi_probe.py`, its tests, `kimi_fixtures.py`, the fixture run and the provider docs); no sabotage entries, since `sabotage*.py` is review ha...
Full note: `.crew/codemap/verification-harness.md`.
