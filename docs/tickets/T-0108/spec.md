# T-0108 gizmoduck safe Nuclei defaults: dos/intrusive/fuzz excluded and a rate limit unless opted out by name (external report item 11)          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md and there is no plan.md. Written against origin/main `155fe6d8` (gizmoduck 0.5.6). See direction.md "Direction check 2026-10-04".

- **Narrowed by a split.** The INDEX title covers report items 9, 10 and 11. This ticket now carries item 11 only. Item 10 (tool-home lookup order) is L-0684 (`children/1/`), item 9 (bootstrap without sudo, CI guidance) is L-0685 (`children/2/`). Reason: 345 estimated production lines as one ticket; see "Size and split".
- The owner was not available. Every default taken is listed under "Open questions for the owner".

## Intent
A Nuclei scan started through gizmoduck sends safe traffic unless the caller opts out by name. `gizmoduck.py scan` and the routine's Nuclei adapter build their command line through one shared builder that adds `-etags dos,intrusive,fuzz` and `-rl 50` by default. Opting out is explicit and visible: `scan --intrusive`, `scan --rate-limit N`, and in a routine manifest `options.nuclei_intrusive: true` and `options.nuclei_rate_limit: N`, with the routine recording the Nuclei cell as `ran(safe)` or `ran(safe+intrusive)` instead of a bare `ran`.

## Exclusions
- No change to `bootstrap.sh`, `bootstrap.ps1`, or any tool lookup. Those are L-0685 and L-0684.
- No change to `plugin/crew/**`. This is a gizmoduck-only change, so the repo rule "a change to plugin/crew updates every document that describes it" does not apply; the PR body says `Docs: none for crew - gizmoduck only`.
- No harness path. Nothing in `HARNESS` or `SEAM` (`scripts/check-tooling-pr.py:58-95`) is touched.
- No hook, no new slash command, no new registered entry. Command and skill counts in `plugin/PLUGINS.md`, `plugin/README.md` and `README.md` do not change.
- `scan --extra` stays a raw passthrough. It is not parsed for safety beyond the one rate-flag rule below; a caller who writes `--extra "-itags dos"` on the single-scanner CLI gets what they typed, and the full argv is already printed to stderr (`gizmoduck.py:161`). Only the routine path refuses safety flags inside `extra`, because there the status label would otherwise lie.
- No change to the other nine adapters' defaults (ZAP baseline, nmap safe, sqlmap gates stay as they are).
- `nuclei_intrusive` does not require `--confirm-active`. That flag stays sqlmap's second gate only.
- The guides under `docs/guides/gizmoduck/` (HTML, DOCX, PDF) have no source in the repo and are not rebuilt; a follow-up bullet goes in `TODO.md`, as T-0107 did.
- No per-template allow list, no config file for defaults, no environment variable that changes the defaults.

## Design
- `gizmoduck.py` gains two constants, `NUCLEI_SAFE_EXCLUDE_TAGS = ("dos", "intrusive", "fuzz")` and `NUCLEI_DEFAULT_RATE_LIMIT = 50`, and one builder, `nuclei_argv(exe, target, severity, extra, *, intrusive=False, rate_limit=None, strict=False)`. `cmd_scan` and `scanners/nuclei.run` both call it; neither builds an argv of its own any more.
- Order of the argv: `-jsonl -silent -nc`, `-l`/`-u` and the target, `-severity` when given, `-etags dos,intrusive,fuzz` unless `intrusive`, the rate flag, then the `extra` tokens.
- Rate limit: an explicit `rate_limit` wins. Otherwise, if `extra` already names a rate flag, no default is added (the caller's value stands in either direction). Otherwise `-rl 50`. An explicit `rate_limit` together with a rate flag in `extra` is a usage error (exit 2), not a guess about which one wins.
- A flag is recognised in `extra` by token: strip leading dashes, split at the first `=`, compare the name. Go's flag parser accepts both `-rl` and `--rl`, and both `-rl 10` and `-rl=10`, so all four spellings count. Rate names: `rl`, `rate-limit`, `rlm`, `rate-limit-minute`. Tag names: `etags`, `exclude-tags`, `itags`, `include-tags`.
- `strict=True` (the routine adapter) raises `ValueError` when `extra` names any rate or tag flag above. The adapter turns that into `(None, ToolResult(-1, "", <message>, False))` without calling `base.run_tool`, which routine records as `error:returncode=-1`. So that a manifest author sees the reason before anything runs, `_check_manifest_shape` refuses the same manifest at parse time with exit 2 and a message naming `nuclei_intrusive` and `nuclei_rate_limit` as the supported options. Two call sites, the same pattern as `_require_authorized_by` (`routine.py:53-70`): a `Manifest` built by hand skips the parse-time check.
- `scan` gains `--intrusive` (store_true) and `--rate-limit N`. N must be an integer of 1 or more; anything else is exit 2 from argparse.
- Manifest: `options.nuclei_intrusive` joins the gate options by setting `ACTIVE_OPTS = ["nuclei_intrusive"]` in `scanners/nuclei.py`, so `_gate_option_keys` (`gizmoduck.py:946-957`) already demands a real boolean. `ACTIVE` stays `False` and `DEFAULT_ENABLED` stays `True`. `options.nuclei_rate_limit` must be an integer of 1 or more and not a boolean (`True` is an `int` in Python); `_check_manifest_shape` refuses anything else.
- `routine._MODE_LABELS` gains `"nuclei": {"base": "safe", "nuclei_intrusive": "intrusive"}`. `_ran_status` needs no other change.
- Flag as a behaviour change in the CHANGELOG: a default scan now runs fewer templates and sends at most 50 requests per second, so it can find less and take longer than 0.5.6 did. A later `diff` against a 0.5.6 baseline shows nothing new for that reason alone (diff reports only what is new), but a report count can drop.

## Evidence
All at origin/main `155fe6d8`, read 2026-10-04.
- `plugin/gizmoduck/scripts/gizmoduck.py:151-160` - `cmd_scan` argv: `-jsonl -silent -nc`, target, `-severity`, then `extra.split()`. No `-etags`, no `-rl`.
- `plugin/gizmoduck/scripts/gizmoduck.py:161` - the argv is printed to stderr as `# running: ...`.
- `plugin/gizmoduck/scripts/gizmoduck.py:1438-1439` - `--severity` and `--extra` are the only Nuclei-shaping arguments; `:1538` passes them to `cmd_scan`.
- `plugin/gizmoduck/scripts/scanners/nuclei.py:121-128` - the adapter's own copy of the same argv; `:1-9` says it borrows only the shape and must not drift.
- `plugin/gizmoduck/scripts/scanners/nuclei.py:62-64` - `ACTIVE = False`, `ACTIVE_OPTS = []`, `DEFAULT_ENABLED = True`.
- `plugin/gizmoduck/scripts/routine.py:278-281` - `_MODE_LABELS` holds nmap and zap only; `:309-312` returns a bare `ran` for an adapter with no `ACTIVE_OPTS`.
- `plugin/gizmoduck/scripts/routine.py:445` - `opts = dict(target.options)` reaches the adapter unfiltered; `:474-477` records `error:returncode=<n>` when `run()` returns no path.
- `plugin/gizmoduck/scripts/gizmoduck.py:946-957` - gate keys come from every adapter's `ACTIVE_OPTS`; `:1018-1021` refuses a non-boolean gate option.
- `plugin/gizmoduck/scripts/gizmoduck.py:841-848` - `_status_family` already folds `ran(safe)` into `ran`, so coverage counts and the exit status are unaffected by the new label.
- `plugin/gizmoduck/scripts/_test/test_scanner_nuclei.py:150` - `test_run_reuses_cmd_scans_argv_shape`, the existing argv-shape test this change extends.
- `plugin/gizmoduck/README.md:105` and `:120-122` - the manifest example and the sentence listing the gate options; `:134-135` lists the cell statuses; `:196-200` is the manual CLI block.
- `plugin/gizmoduck/skills/gizmoduck/SKILL.md:24-32` and `plugin/gizmoduck/commands/scan.md:5` - the scan step as documented today, no mention of safety defaults.
- `plugin/gizmoduck/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:230`, `plugin/PLUGINS.md:449` - the three places that state gizmoduck's version (0.5.6); PLUGINS.md's carries a `claim: plugin-version:gizmoduck` marker.
- `.crew/verify.json:263-267` - the rule for `plugin/gizmoduck/**`: `python3 -m pytest plugin/gizmoduck/scripts/_test/ -q`.
- `docs/handoff/cloud/T-0108.md` and `docs/handoff/cloud/README.md:29` - the temporary cloud handoff note and its row, which the note itself says to delete in this ticket's PR.
- `git grep -n -i "etags\|exclude-tags\|rate-limit" origin/main -- plugin/gizmoduck` - no hits: nothing on main already does this.

## Unknowns
- **Nuclei flag names and precedence on the installed version.** `-etags`, `-itags`, `-rl` and `-rlm` are from Nuclei v3's help text, not from a run here (no pytest or scanner runs were allowed while writing this). Resolve before implement: run `nuclei -h` on the version bootstrap installs, record that version in the PR, and confirm with the template lister, which sends no traffic: `nuclei -tl -etags dos,intrusive,fuzz -tags dos` must list nothing tagged `dos`. If exclusion does not beat `-tags`, stop and report; the design assumes it does.
- **Whether a repeated flag accumulates or replaces.** The design never emits the same flag twice (the default rate flag is dropped when `extra` carries one), so it does not depend on this. Accepted as risk for tag flags in `scan --extra`, which is documented as the caller's own business.
- **Other Nuclei switches that send attack traffic** (for example a DAST or fuzzing mode switch). Resolve before implement from `nuclei -h`: any switch that enables fuzzing joins the `strict` refusal list. If the list grows past the eight names above, say so in the PR.
- **Nuclei's own ignore file may already exclude some of these tags.** Not relied on. The explicit flag makes the behaviour independent of what the template set ships.
- **Is 50 requests per second low enough for the targets this is used on?** Accepted as risk; it is an owner question below, and one constant to change.

## Touch
- `plugin/gizmoduck/scripts/gizmoduck.py` - constants, the shared builder, scan arguments, manifest shape checks, module docstring usage line
- `plugin/gizmoduck/scripts/scanners/nuclei.py` - call the builder, ACTIVE_OPTS, the strict refusal
- `plugin/gizmoduck/scripts/routine.py` - one mode-label entry and the comment above it
- `plugin/gizmoduck/scripts/_test/test_nuclei_defaults.py` - new
- `plugin/gizmoduck/scripts/_test/test_scanner_nuclei.py` - the argv-shape test now asserts the defaults
- `plugin/gizmoduck/scripts/_test/test_routine_cli.py` - manifest refusals and the recorded mode
- `plugin/gizmoduck/scripts/_test/test_routine_orchestration.py` - only if an existing assertion on the nuclei status needs the new label
- `plugin/gizmoduck/scripts/_test/fixtures/**` - a manifest fixture carrying the new options
- `plugin/gizmoduck/README.md`
- `plugin/gizmoduck/skills/gizmoduck/SKILL.md`
- `plugin/gizmoduck/commands/scan.md`
- `plugin/gizmoduck/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `TODO.md` - one follow-up bullet: the gizmoduck guides do not describe the safe defaults
- `docs/handoff/cloud/T-0108.md` - deleted, as that note requires
- `docs/handoff/cloud/README.md` - the T-0108 row removed
- `.crew/codemap/**` - re-anchor only, owner's standing rule
- `.claude/rules/**` - regenerated
- `graphify-out/**` - rebuilt by graphify update, committed as it leaves them

## Acceptance checks
Rule for every pytest line: `.crew/verify.json` `plugin/gizmoduck/**` (`python3 -m pytest plugin/gizmoduck/scripts/_test/ -q`). No test here runs a real scanner; `base.run_tool` and `subprocess.run` are replaced.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_nuclei_defaults.py -q` passes, with these tests by name:
  - `test_nuclei_argv_excludes_dos_intrusive_fuzz_by_default` - the argv holds `-etags` followed by exactly `dos,intrusive,fuzz`.
  - `test_nuclei_argv_default_rate_limit_is_50` - the argv holds `-rl` followed by `50`.
  - `test_nuclei_argv_intrusive_drops_the_tag_exclusion_and_keeps_the_rate_limit`.
  - `test_nuclei_argv_explicit_rate_limit_replaces_the_default`.
  - `test_nuclei_argv_rate_flag_in_extra_suppresses_the_default` - parametrized over `-rl 10`, `--rl 10`, `-rl=10`, `-rate-limit 10`, `-rlm 600`, `-rate-limit-minute=600`; the argv holds no second rate flag.
  - `test_nuclei_argv_explicit_rate_limit_with_rate_flag_in_extra_is_refused` - `ValueError`, and through `main()` exit 2.
  - `test_nuclei_argv_extra_is_appended_last_and_unchanged`.
  - `test_nuclei_argv_strict_refuses_tag_and_rate_flags_in_extra` - parametrized over the eight names and both dash and `=` spellings.
  - `test_cmd_scan_and_adapter_build_the_same_argv` - same inputs, equal argv, proving one builder.
  - `test_scan_rate_limit_rejects_zero_negative_and_non_integer` - parametrized over `0`, `-5`, `abc`, `1.5`; exit 2, no findings file written.
  - `test_scan_intrusive_flag_reaches_the_argv`.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_scanner_nuclei.py -q` passes, including `test_adapter_refuses_safety_flags_in_extra_without_running_nuclei` (the fake `run_tool` records zero calls; the result is `(None, ToolResult)` with return code -1 and the message naming `nuclei_intrusive`).
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_routine_cli.py -q` passes, including:
  - `test_manifest_nuclei_intrusive_must_be_a_boolean` - a quoted `"false"` is exit 2 and nothing is written.
  - `test_manifest_nuclei_rate_limit_must_be_a_positive_integer` - parametrized over `0`, `-1`, `"50"`, `true`, `1.5`; exit 2.
  - `test_manifest_refuses_nuclei_safety_flags_in_extra` - exit 2, the output directory is not created.
  - `test_routine_records_nuclei_mode` - a fake nuclei adapter with the real `ACTIVE_OPTS` records `ran(safe)` by default and `ran(safe+intrusive)` with `nuclei_intrusive: true`, and `scan-meta.json` coverage still counts both under `ran` with `complete: true`.
- [ ] Sabotage, run by hand and quoted in the PR: delete the `-etags` line from the builder, run the three suites above, confirm red; restore, confirm green. Then the same for the strict refusal. Check the `.pyc` timestamp if a restore appears not to take.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/ -q` passes whole (the full gizmoduck rule).
- [ ] Manual, quoted in the PR with the Nuclei version: `nuclei -tl -etags dos,intrusive,fuzz -tags dos` lists no template; `nuclei -tl -tags dos` lists at least one. No traffic is sent by `-tl`. If Nuclei is not installed where the PR is built, say so; do not imply it ran.
- [ ] `plugin/gizmoduck/README.md` states the two defaults, the two `scan` switches, the two manifest options, the routine refusal of safety flags in `extra`, and the `ran(safe)` / `ran(safe+intrusive)` statuses; `git grep -n "nuclei_intrusive" -- plugin/gizmoduck/README.md plugin/gizmoduck/skills/gizmoduck/SKILL.md` hits both files, and `git grep -n -- "--intrusive" -- plugin/gizmoduck/commands/scan.md` hits.
- [ ] `SKILL.md` and `commands/scan.md` say `--intrusive` is passed only after the target's owner has authorised intrusive testing.
- [ ] Version bumped in all three places to the same value, then committed, then `python3 scripts/check-marketplace.py` passes (its drift check compares commits, so run it after the commit).
- [ ] `CHANGELOG.md` has a heading entry in the current shape naming the version, T-0108, and the behaviour change in one plain sentence.
- [ ] `git ls-files docs/handoff/cloud/T-0108.md` prints nothing and `git grep -n "T-0108" -- docs/handoff/cloud/README.md` prints nothing.
- [ ] ruff and pylint: no new findings against the merge-base (`.crew/verify.json` rule for `**/*.py`).
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 (no `HARNESS` path changed). Exit 77 means `origin/main` is not a ref and the check did not run; report that, do not call it a pass.

## Dependencies
Must land before this ticket:
- T-0107 - **done** (merged as #273, `75681fba`, gizmoduck 0.5.5). It added `gizmoduck.py routine`, `_check_manifest_shape` and `_gate_option_keys`, which this spec extends.
- L-0599 - **done** (merged as #315, gizmoduck 0.5.6). The pylint fix on `gizmoduck.py`; listed so the version this ticket bumps from is clear.

Same report, no ordering constraint: T-0104 (approved), T-0105 (direction), T-0106 (direction), T-0500 (approved), T-0501 (done), T-0502 (direction), T-0503 (merged).

This ticket blocks: nothing hard. L-0684 and L-0685 are independent of it in code, but all three bump gizmoduck's version and edit the same README, so land them one at a time, each merging origin/main first (merge, never rebase).

## Size and split
- This slice: about 95 production lines (`gizmoduck.py` about 70, `scanners/nuclei.py` about 20, `routine.py` about 3).
- The whole of T-0108 as first written: about 345 (95 + 100 for L-0684 + 150 for L-0685), over the 300-line rule, and three unrelated behaviours. Split into this ticket and two children.
- One new guard (the strict refusal of safety flags in a routine manifest). No new parser, no state machine, no harness path.

## Open questions for the owner
Each has a default already taken; none blocks the build.
1. Default rate limit: 50 requests per second taken. Alternatives: 25 (gentler on small sites), 150 (Nuclei's own, which would make the default a no-op), or no default with a required manifest value.
2. Excluded tags: `dos,intrusive,fuzz` taken, as the report names them. Add `bruteforce`?
3. Version: 0.6.0 taken, because a default changed. Alternative: 0.5.7, the next patch.
4. Should `nuclei_intrusive: true` in a manifest also need `--confirm-active`, like sqlmap? Default taken: no, matching `zap_active` and `nmap_vuln`.
5. In a routine manifest, safety flags inside `extra` are refused. Alternative: allow them and record the cell as `ran(custom)`.
6. `scan --extra` is left unchecked for tag flags. Alternative: refuse them there too and make `--intrusive` the only way.

## Split
- L-0684 (child 1 of T-0108, filed 2026-10-04): gizmoduck tool lookup: one tool home, and an explicit override beats PATH (external report item 10)
- L-0685 (child 2 of T-0108, filed 2026-10-04): gizmoduck bootstrap.sh without sudo, and a CI and containers guide (external report item 9)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
