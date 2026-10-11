# L-0753 /crew:done waivers (2026-10-10)

- Check 2: environment-blocked, owner-accepted 2026-10-10 (Matthew, relayed by the coordinator).
  ci_receipt says `CI_RECEIPT UNVERIFIED ... this branch changes the receipt producer (plugin/crew/hooks/scripts/ci_receipt.py)`,
  so only a local verify-gate pass could satisfy it, and this host cannot produce one. Reproductions on main:
  - test_crew_context_wrappers.py::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false[config0-False] and [None-False]
    fail identically on an origin/main d8de3daf worktree (host ~/.claude/crew/config.json leaks; fixed by L-0709).
  - 12 sabotage entries STILL GREEN on origin/main d8de3daf too (control entries go red): L-0766.
  - 16 ps1 verify-gate tests: subprocess.TimeoutExpired on pwsh verify-gate.ps1 -All under -n auto (pass under -n 4): L-0767.
  - obsidian-vault run-tests vault-guard.ps1 near-deadline flake under load; 71/71 pass when run alone.
  Logs: /root/crew-tmp/l-0753/gate-r1/ (gate-runner), /root/crew-tmp/l-0753/verify-all.log (verify-gate --all, stopped).
- Checks 1/3: standing staleness waiver. After the accepted head 7a874c8f only merges of main, version bumps and
  refreshes (code maps, rules, graph) followed; the completion audit puts the own diff inside Touch.
