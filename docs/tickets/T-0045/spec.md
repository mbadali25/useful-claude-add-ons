# T-0045 crew runs GitHub Actions deployments, slice 1: the `github` entry and `crew_ghdeploy.py check`          status: spec   risk: med
## Refreshed 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04". The owner was not available, so each open decision took the recommended option and is listed under Unknowns.

What changed from the 2026-09-26 spec, and why:
- **Narrowed to the first slice.** The old spec was one landing of about 950 production lines with three fail-closed state machines, a guard change in two flavours and sabotage files. It is now this ticket plus seven children under `children/` (see "Size and split"). This ticket keeps plan.md Step 1 only: the `github` entry, its validation, the canonical dispatch text, and `check`.
- **Dropped, already on main:** `autopilot.deploy` and its defaults, template rows and config tests (T-0072, `plugin/crew/hooks/scripts/crew_state.py:1134`); the promote-gate tree and dirty-check change (T-0505, `plugin/crew/hooks/scripts/promote-gate.sh:19-26`).
- **Dropped, owned elsewhere:** the `gh api ... /dispatches` form in promote-gate and the first-row `passed()` behaviour belong to T-0062.
- **Superseded decision:** "a github deploy skips the local dirty check". Main keeps the clean-tree check for every deploy, judged on the tree the deploy runs from. The sha-on-remote check moves to L-0644's `prepare`.
- **Sabotage:** mutations ship in `plugin/crew/tests/ghdeploy_mutations.py`, unwired, as T-0505 did. `sabotage*.py` is harness and is wired by L-0650, a tooling-only PR.
- **Risk** is `med` for this slice: `check` reads config and prints text. It dispatches nothing and no hook depends on it yet. The ticket family stays high.
- The design decisions in plan.md "Design" are kept for every slice. plan.md itself does **not** match any more: its anchors are from `1e0706ac`, its Step 2 edits `cloud_guard.py` for a classifier that now lives in `crew_guards.py` on T-0009's branch, its Step 7 adds a config key that exists, and its Step 8 edits harness files in a feature PR. Re-plan this slice from plan.md Step 1 before building.
- Consumer-repository details (name, paths, workflow inputs) are removed from this file; the repository is public.

## Intent
A `.crew/verify.json` environment can describe a GitHub Actions deploy as data: a `github` entry naming the workflow file, the ref, the fixed inputs and which input carries the sha. `python3 plugin/crew/hooks/scripts/crew_ghdeploy.py check --root . --env <name>` validates the entry, checks that the environment's `deploy` list is exactly the entry's canonical prefix (so promote-gate's existing substring match fires on the real dispatch), and prints the one literal `gh workflow run` command for HEAD. It writes nothing and calls no `gh` command. Later slices build on this module to prepare, identify, watch and record the run.

## Exclusions
- No dispatch, and no `gh` call of any kind in this slice. `check` reads `.crew/verify.json` and `git rev-parse HEAD` only.
- No `prepare`, `identify`, `watch` or `record` (L-0644 to L-0647), no promote-gate change (L-0648), no autopilot change (L-0649), no edit to any `plugin/crew/tests/sabotage*.py` (L-0650).
- No edit to `plugin/crew/commands/promote.md`: it is at its 380-line allowance. The sequence prose lands with L-0647.
- No reading of workflow YAML. Everything comes from the entry.
- Not accepted in an entry: a workflow named by display name or numeric id (a `.yml`/`.yaml` filename only), a tag as `ref` (branches only), `-R/--repo`, and any value with shell metacharacters.
- No authority decision. Whether a dispatch may run unattended is T-0009's guard on the Bash call; this module never decides it and never copies its classifier.
- No change to `plugin/crew/hooks/scripts/crew_config.py`, the config templates or `autopilot.*`: the entry lives in `.crew/verify.json`, not in config.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/commands/promote.md:69 gate 2 is "Run the `deploy` commands. A non-zero exit is a stop."; :73-76 "Check the job, not the run"; :19-23 `--dry-run` prints the resolved sequence. The file is 380 lines and `plugin/crew/.budget-allowance.json` allows 380.
- plugin/crew/hooks/scripts/promote-gate.sh:193-214 reads each environment's `deploy` (a string or a list of strings, anything else is exit 4) and matches `d in cmd or cmd in d` at :213. :130-142 is the same match for the committed map. :376-384 a literal sha in the command must be the tree's HEAD. :510-511 writes `.crew/.deploy-in-flight`.
- plugin/crew/hooks/scripts/promote-gate.ps1:134 is the PowerShell match (`-like "*$dep*"`).
- An unknown key inside an environment is ignored by both gates: promote-gate.sh reads only `deploy` (:197), `requires` (:409), `rollback` (:417-455) and `requireHuman` (:457). So adding `github` breaks no existing map.
- plugin/crew/skills/crew-verification/SKILL.md:352-409 documents the `environments` block and its key table; :426-442 the promotion record. The file is 474 lines.
- Nothing on main implements this: `git grep -n ghdeploy origin/main -- plugin scripts` prints nothing.
- .crew/verify.json:122-134 maps promote-gate and `test_promote*.py`; no rule names `crew_ghdeploy.py`.
- scripts/check-tooling-pr.py:58-87 `HARNESS` includes `plugin/crew/tests/sabotage*.py` (:79); :99-118 `ALONGSIDE` includes `plugin/crew/tests/**`. A new `ghdeploy_mutations.py` matches no harness glob.
- plugin/crew/tests/promote_tree_mutations.py:1-10 is the precedent: mutations in `sabotage.py`'s tuple shape, unwired, with the one-line runner.
- gh 2.46.0 help text, read 2026-10-04, nothing dispatched: `gh workflow run` takes `-f/--raw-field`, `-F/--field`, `--json` (inputs on stdin) and `-r/--ref` "branch or tag name". Its help documents no run id in the output.
- Rules run through `python3 plugin/crew/tests/pytest_rule.py <files> -q` (plugin/crew/tests/pytest_rule.py:1-12).

## Unknowns
- Owner decision - the eight-way split. Default taken: yes (direction.md, option 1).
- Owner decision - `github` as one object or a list. Kept from plan.md: either, normalised to a list, because the first consumer dispatches the same workflow twice per environment with different inputs.
- Whether a real workflow's input values fit the closed value grammar `[A-Za-z0-9._/@:+-]`. Accepted as risk: a value outside it is refused with its name, never quoted or escaped, and the grammar is widened only by a spec amendment.
- The exact crew patch version is set at landing: one past origin/main's at that time.
- Nothing here observes a real dispatch. Accepted: L-0647's attended run is the first measurement.

## Size and split
- This slice: about 170 added production lines, all in the new `plugin/crew/hooks/scripts/crew_ghdeploy.py` (entry validation about 80, prefix and dispatch text about 30, `check` and `main` about 60). One parser (the entry validator), no guard, no state machine, no harness path.
- The whole of T-0045 is about 950 production lines, so it is split. Children, each a complete ticket under `children/<k>/`:
  1. `prepare`: refuse or snapshot before the dispatch (needs T-0009).
  2. `identify`: exactly one new run, or could-not-tell.
  3. `watch` and `classify`: pass, fail or unknown from the run and its deploy job.
  4. `record`, the promote sequence prose and the attended evidence run.
  5. promote-gate reads the `github` entry, both flavours.
  6. autopilot's deploy phase (needs T-0011 and T-0009).
  7. tooling-only: wire the ghdeploy mutations into the sabotage harness.

## Touch
- plugin/crew/hooks/scripts/crew_ghdeploy.py
- plugin/crew/tests/test_crew_ghdeploy.py
- plugin/crew/tests/ghdeploy_mutations.py
- plugin/crew/skills/crew-verification/SKILL.md
- plugin/crew/README.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json
- plugin/PLUGINS.md
- CHANGELOG.md
- .crew/verify.json
- `.crew/codemap/**` - refresh and re-anchor only
- `.claude/rules/**` - regenerated by the code map refresh
- `graphify-out/**` - rebuilt by graphify update
- `docs/diagrams/**` - re-anchor only, no node or edge changes

## Acceptance checks
Run: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_ghdeploy.py -q`
- [ ] must-block `test_entry_problem`, each refused by name with exit 2 and a last line `result=refused reason=<...>`: a missing `workflow`; a workflow that is not a `.yml`/`.yaml` filename from `[A-Za-z0-9._-]`; `ref` starting with `-`; `ref` containing `..`; `inputs` that is not an object; an input value that is not a string; a value with a space; a value with `$(`; `shaInput` also present in `inputs`; `shaInput` equal to `correlationInput`; `watchMinutes` 0 and 361; `identifySeconds` 5; a `github` that is neither an object nor a list of objects; an unknown key in an entry
- [ ] must-block `test_check_refuses_deploy_prefix_mismatch` (exit 2, `deploy-prefix-mismatch`): `deploy` missing one entry's prefix, and `deploy` carrying a string that is no entry's prefix
- [ ] must-block `test_check_unreadable_map_is_could_not_tell` (exit 3): `.crew/verify.json` absent, unparseable, or with no such environment; and HEAD unreadable. None reads as "no github entry"
- [ ] must-allow `test_prefix_is_listed_order`: the prefix is `gh workflow run <workflow> --ref <ref>` then ` -f k=v` per input in the entry's order
- [ ] must-allow `test_dispatch_appends_sha_then_correlation`: the sha input carries the full 40-character HEAD; the correlation id is `crew-<env>-<sha7>-<8 hex>`
- [ ] must-allow `test_check_prints_dispatch_for_head`: exit 0, one dispatch line per entry, nothing created under `.crew/` or `.work/`
- [ ] must-allow `test_environment_without_github_is_not_a_problem`: `check` on a plain `deploy` environment exits 0 and says there is no github entry
- [ ] `test_check_calls_no_gh`: with `gh` replaced on PATH by a stub that records and fails, `check` passes and the stub was never run
- [ ] the printed dispatch is matched by the real gate: `test_dispatch_matches_promote_gate` feeds the printed line to `plugin/crew/hooks/scripts/promote-gate.sh` on a throwaway repo and the gate names that environment (blocked or allowed, but never "matches nothing")
- [ ] mutations: `plugin/crew/tests/ghdeploy_mutations.py` holds one entry per refusing branch above plus one must-allow non-vacuity entry, and each turns its named test red with no ANCHOR LOST: `cd plugin/crew/tests && python3 -c "import sabotage, ghdeploy_mutations as m; sabotage.MUTATIONS = m.GHDEPLOY_MUTATIONS; raise SystemExit(sabotage.main())"`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 (no harness path in the diff)
- [ ] `.crew/verify.json` gains a rule mapping `crew_ghdeploy.py`, `test_crew_ghdeploy.py` and `ghdeploy_mutations.py` to the run line above, with measured seconds; `python3 scripts/check-marketplace.py` passes after the commit
- [ ] docs: crew-verification section 4 documents the `github` keys and `check`, and says the dispatch sequence is not built yet; README names `crew_ghdeploy.py check`; BUDGETS.md's `crew-markdown-lines` claim is re-measured. The PR body states `Docs:` for each of CONFIG.md, the guide sources and the diagrams (none - the entry is verify.json data and no guide or diagram describes it)
- [ ] crew version is one patch above origin/main's at landing, in `plugin.json`, `marketplace.json` and `PLUGINS.md`, as the last `plugin/crew` commit, with a CHANGELOG entry

## Split
- L-0644 (child 1 of T-0045, filed 2026-10-04): crew_ghdeploy.py prepare - refuse or snapshot before a GitHub Actions dispatch
- L-0645 (child 2 of T-0045, filed 2026-10-04): crew_ghdeploy.py identify - exactly one new workflow run, or could-not-tell
- L-0646 (child 3 of T-0045, filed 2026-10-04): crew_ghdeploy.py watch - pass, fail or unknown from the run and its deploy job
- L-0647 (child 4 of T-0045, filed 2026-10-04): crew_ghdeploy.py record and the /crew:promote github sequence
- L-0648 (child 5 of T-0045, filed 2026-10-04): promote-gate reads the github entry - the sha input must be the reviewed HEAD
- L-0649 (child 6 of T-0045, filed 2026-10-04): autopilot's deploy phase - promote to the first nonProd GitHub environment after the merge
- L-0650 (child 7 of T-0045, filed 2026-10-04): wire the GitHub-deploy mutations into the sabotage harness (tooling only)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
