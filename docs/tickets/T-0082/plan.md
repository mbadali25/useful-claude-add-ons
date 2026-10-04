# T-0082 plan - verify gate: a rule passes only on a completion record          status: plan
Bundled with T-0080 in harness PR H2a (#399), owner-approved bundling of harness tickets into
harness-only PRs. Built on origin/main merged into T-0082-build, then origin/T-0080-build merged.
Spec decisions taken as written (recommended options 1-4; L-0674 held, L-0673 not built).

## Steps (test-first; each test seen red before the code that turns it green)
1. `plugin/crew/tests/test_verify_gate_rule_completion.py` (new), `[sh]` and `[ps1]` (ps1 runs wherever
   pwsh exists, OS=Windows_NT set past the flavour guard, as test_verify_gate_subset_cover.py does).
   Cases named in the spec's acceptance list: must-allow (exit 0; plain fail + skip 77; own `exit 0`
   and own `trap EXIT`), must-block (killed mid-run; wrapper killed before the record; unreadable
   record: empty / non-numeric / above 255; ps1 launch failure after a pass; timed out from outside),
   marker and summary, command-log `unknown`, signalled sh gate names the in-flight command, no record
   file left behind.
2. `verify-gate.sh`: a second temp path (`RULE_DONE_FILE`) made and removed beside `RULE_OUT_FILE`
   (TMPDIR, then `.crew/.verify-rule-done.XXXXXX`); wrapper `( ( eval "$c" ); printf '%s\n' "$?" >
   "$RULE_DONE_FILE" ) ...&`; the spec's decision table in order; `unknown` prints `VERIFY FAILED`,
   `COULD NOT TELL (<reason>)`, tail 25; `UNKNOWN_N` summary line; TERM/INT/HUP traps print the two
   lines for a rule in flight (`RULE_IN_FLIGHT`), before the unchanged cleanup and exit 128+N.
3. `verify-gate.ps1`, same order: `$rc = $null` per rule, `$global:LASTEXITCODE` no longer preset as
   the answer; record path in `CREW_VERIFY_RULE_DONE`, unset before `eval`; the same table; summary.
4. `verify_record.py`: the docstring status list and the "any other status" comment only.
5. `sabotage_tooling.py`: mutations (a)-(i) of the spec, each naming its test; ps1 ones only where
   pwsh exists.
6. Docs: CONFIG.md, README.md, troubleshooting.md (+ rebuilt guide outputs if the build runs here),
   codemaps, verify.json gate rule (index 4) gets the new file, CHANGELOG, rules regenerated.

## Measured before building
- No shipped rule exits above 128: `git grep -n "exit 1[3-9][0-9]\|exit 2[0-9][0-9]" -- .crew/verify.json
  plugin/crew/skills` prints nothing.
- Windows native kill: not reproducible here (Linux container); the native-Windows run stays unverified.
