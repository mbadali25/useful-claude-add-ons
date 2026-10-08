# L-0649 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built on T-0011 (on release/1.2.0: `_ship_phase`, `crew_ship.merged_phase`), T-0072
(`deploy_allowed`), T-0009 (the classifier, via `crew_ghdeploy.classify`) and L-0644 to L-0648 here.

Kept tight: `crew_autopilot.py` sits at `.pylintrc`'s 3400-line ceiling, so the phase lives in a new
module, `crew_autopilot_deploy.py`, and `crew_autopilot.py` changes by a net zero lines: the MERGED
branch calls `crew_autopilot_deploy.after_merge` (which runs `merged_phase` first), the two stop
slugs join `FIXED_STOPS`, the `deploy_allowed` docstring names its consumer, and `settings`' "nothing
dispatches a deploy" warning becomes one line saying what an armed value does (the `if deploy !=
"none"` anchor and `test_deploy_armed_warns_inert`'s name stay, because sabotage_autopilot.py - a
harness file this PR may not touch - names both).

1. RED: `test_crew_autopilot_deploy_phase.py`: every acceptance case on `after_merge` with a
   stand-in `deploy_allowed`, the real one for prod under `all`, and two cases through `next`.
2. The phase: `merged_phase` not `closed`, or `deploy: none` -> unchanged. Targets: `github`
   environments in file order, nonProd first; each validated by `crew_ghdeploy.validated`, refused
   for `requireHuman` or no `shaInput`, classified by `crew_ghdeploy.classify` on its dispatch for the
   merged sha. Per target: newest row all-pass -> next target; not all-pass -> `failed-deploy`; no row
   -> `deploy_allowed`, `allow` names `/crew:promote <env>`, anything else `deploy-target`.
3. Mutations in `ghdeploy_mutations.py`; docs (CONFIG.md section 20, README, autopilot.md in place,
   github-deploy.md, the daily-workflow guide, rebuilt).

Deviation: `head-not-pr-head` is `merged_phase`'s own `ship` stop (it already refuses a HEAD that is
not the merged head), passed through unchanged; it never names `/crew:promote`.
