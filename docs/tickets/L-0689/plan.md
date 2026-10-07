# L-0689 plan (implementing session, 2026-10-05, rush/g4-deploy)

1. Reproduced first, on this branch's unfixed promote-gate.sh, in a throwaway repository with the
   spec's fixture map: `git rev-parse HEAD` exited 2, blocked as `development,production` (the union
   rule L-1503 added since the spec matched the fragment to both). With development alone declared:
   `exit=0`, `.crew/.deploy-in-flight` read `development 4b07c68`. The bug holds (U1).
2. On this branch each flavour has ONE match function used for both the working and the committed
   map (promote-gate.sh `matching()`, promote-gate.ps1 `Test-DeployMatch`, which L-1503 already made
   literal and case-insensitive): the reverse test is dropped there, which covers all four sites.
   `crew_ghdeploy.py`'s gate simulation (`_matches`) follows so `check`'s `gated-as` stays equal.
3. RED: `test_promote_gate_match.py` on both flavours: the fragments, the committed-map case, the
   production block, still-gated forms, literal/case matching. L-1503's tests that pinned the
   reverse match (`git push` inside two deploys, `./deploy.sh` inside `./deploy.sh --prod`, `deploy`
   inside `Deploy-Prod`, a CR'd shorter command) and three `crew_ghdeploy` expectations follow the
   new rule. Deviation: `gh workflow run` and `gh workflow run deploy.yml` are read by T-0062's
   dispatch reader once containment no longer matches them, and block as could-not-tell (no
   workflow / fits no environment) rather than exiting 0; still no marker.
4. Mutations in `promote_tree_mutations.py`; docs state "contains the declared text", the breaking
   change and the stale-marker note; troubleshooting guide rebuilt.
