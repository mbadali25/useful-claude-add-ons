# T-0062 promote-gate treats a workflow dispatch of a declared deploy workflow as that deploy, in either spelling (shared reader + Bash flavour)          status: spec   risk: high
## Refreshed 2026-10-04
Written against origin/main `155fe6d8` (crew 1.0.322). There was no earlier spec.md and there is no plan.md. See direction.md "Direction check 2026-10-04".
- The tree half of the original ask shipped as T-0505 (#296). It is out of this ticket.
- What is left is the coverage gap, narrowed to the first slice: the shared reader and `promote-gate.sh`.
- Split from the rest: L-0664 (PowerShell twin) and L-0665 (first-row fix), under `children/`.
- **Not buildable until T-0009 (PR #336) is merged.** Evidence lines marked `T-0009@f08ae7fb` are read from that branch, not from main, and must be re-read after the merge.

## Intent
`promote-gate.sh` stops deciding "is this a deploy" by text containment alone. The containment match stays first and unchanged. When it matches nothing, and `.crew/verify.json` declares at least one `deploy` that is a GitHub workflow dispatch, the command is read by T-0009's dispatch reader in `crew_guards.py` (the same one `cloud_guard.py` uses; no second parser), through a new helper `_promote_dispatch.py`:

- **Not a dispatch** (the reader finds no dispatch-shaped command): passes untouched, as today.
- **Read, and its workflow is a declared deploy workflow**: it is the deploy of the one environment whose declared dispatch names that workflow and whose declared literal inputs all appear in the command with the same value. `gh workflow run <wf> -f environment=x` and `gh api ... /actions/workflows/<wf>/dispatches -f 'inputs[environment]=x'` therefore reach the same environment, and every existing check (tree, clean, literal sha, `requires`, `rollback`, `requireHuman`, in-flight marker) runs for it.
- **Read, declared workflow, but zero or several environments fit**: blocked. The gate cannot say which environment's preconditions apply.
- **Read, and the workflow is a file name no declared deploy uses**: passes untouched.
- **Could not tell**: blocked, at every setting, naming the word. That is: a dispatch-shaped line the reader refuses (a variable, a substitution, double quotes, a pipe, `--json`, `--input`, `-F k=@file`, a nested shell, an alias of `gh`); a workflow named by numeric id or display name (it cannot be compared with a declared file name); a declared dispatch in the map that the reader itself cannot read; the helper failing.

A declared `deploy` string may hold `$(...)` or backtick substitutions (`-f ref=$(git rev-parse HEAD)` is the common shape). Reading a DECLARED string, and only a declared one, the helper replaces each substitution with one placeholder word, and an input whose declared value is that placeholder is not compared. The command being judged gets no such treatment.

With the map dirty, the committed map's declared dispatches are matched too, as `matches()` already does for containment. During an open incident each block is a recorded skip, as for every other block.

## Exclusions
- `promote-gate.ps1`: L-0664. Until it lands the PowerShell tool keeps today's containment-only match; the docs say so.
- The first-row PROMOTIONS.md bug: L-0665.
- Symbolic refs. `--ref <branch>`, the REST body's top-level `ref=<branch>` and `inputs[ref]=<branch>` are not resolved (T-0505's decision, unchanged). A literal sha anywhere in the command is already checked against the tree's HEAD.
- No change to T-0009's grammar, to `cloud_guard.py`'s decisions, to `guards.deployWorkflow`, or to `environments.workflows`. promote-gate's reading does not depend on `environments.workflows` being set: its list of deploy workflows is `.crew/verify.json`.
- Other routes to a dispatch: `curl`, a script file, `gh run rerun`, a `gh alias` set in an earlier command. Out of reach of a PreToolUse hook; stated in the docs as a limit, as T-0009 states it.
- L-0564's findings (escaped `cd`, the map hash/read race, block-message wording, sabotage wiring).
- `plugin/crew/tests/sabotage*.py` and every other path in `HARNESS` (`scripts/check-tooling-pr.py`). New mutations go in `promote_tree_mutations.py`, which is not harness.
- No rewrite of any consumer's `.crew/verify.json`.

## Evidence
All at origin/main `155fe6d8` unless marked.
- Containment is the only match: `plugin/crew/hooks/scripts/promote-gate.sh:140` (committed map) and `:213` (working map), `if d and (d in cmd or cmd in d)`. No match leaves `ENVNAME` empty and `:230` exits 0.
- The helper pattern to follow: `promote-gate.sh:275-276` runs `_promote_tree.py` and blocks when it fails; `:120-217` is the inline matcher with exit status 3/4 for an unreadable map.
- No python on the Bash side is an existing opt-out: `promote-gate.sh:79`. Unchanged here.
- The literal-sha check that will cover `inputs[ref]=<sha>`: `promote-gate.sh:376-384`, fed by `_promote_tree.py`'s `hex` records (`plugin/crew/hooks/scripts/_promote_tree.py:17`, `:186`).
- The reader is absent from main: `git grep -n "def dispatch_scopes" origin/main -- plugin/crew/hooks/scripts/` prints nothing.
- `T-0009@f08ae7fb` `plugin/crew/hooks/scripts/crew_guards.py`: `_DISPATCH_RE` `:2115`, `dispatch_trigger` `:2551`, `dispatch_first_non_literal` `:2651`, `_dispatch_grammar` `:2617`, `dispatch_scopes` `:2818` (returns `form`, `workflow`, `inputs: [(name, value-or-None, why)]`, `reads`), `dispatch_answer` `:2935`. `dispatch_answer` returns `unlisted` at once unless `environments.workflows` is set (`dispatch_engaged`), so promote-gate cannot call it as it stands.
- Observed (direction.md, 2026-09-26): the `gh api ... /dispatches` spelling of a declared deploy ran with no gate output at all.
- Existing suite and fixtures: `plugin/crew/tests/test_promote_gate_effective_tree.py:82` (`Repo`), `:149` (`run_gate`), `FLAVOURS` `:47`. Mutations: `plugin/crew/tests/promote_tree_mutations.py:1-15` (not wired into `sabotage.py`; run ad hoc).
- The verify rule already covers `test_promote*.py` and `_promote_tree.py`: `.crew/verify.json:124-135`.
- Docs that state the match rule: `plugin/crew/README.md:2558`, `:2850`; `plugin/crew/commands/promote.md:311` (file is 380 lines, ceiling 380 in `plugin/crew/.budget-allowance.json:18-21`); `plugin/crew/skills/crew-verification/SKILL.md:408`; `plugin/PLUGINS.md:33`; `INSTALLATION.md:271`; `docs/guides/crew/src/troubleshooting.md:310`.
- `HARNESS` does not list `promote-gate.*`, `_promote_*.py`, `crew_guards.py` or `promote_tree_mutations.py` (`scripts/check-tooling-pr.py`, `HARNESS = (`), so this is a feature PR.

## Unknowns
- U1 `crew_guards` entry point. DECIDED: add one public function, `dispatch_read(text, shell, helpers=None)`, returning `("none" | "unsure" | "read", why, scopes)`: `dispatch_answer`'s steps up to and including `dispatch_scopes`, without the `dispatch_engaged` test and without classification. `dispatch_answer` may be re-expressed on top of it only if T-0009's suites stay green with no assertion edited; otherwise it is left alone. Re-read the names after #336 merges; if they moved, the function keeps this contract.
- U2 Comparing workflow names. DECIDED: a leading `.github/workflows/` is dropped, then names ending `.yml`/`.yaml` compare exactly. Anything else (an id, a display name) is could-not-tell.
- U3 Which inputs pick the environment. DECIDED: every literal input of the declared dispatch must be present and equal; extra inputs on the command are allowed; a command input the reader could not name (`*`) is could-not-tell.
- U4 An unrelated workflow run with a variable in it (`gh workflow run ci.yml --ref "$B"`) is blocked in a repo whose map declares a dispatch deploy. ACCEPTED as risk: the reader is all-or-nothing by design and cannot vouch for the workflow name on a line it refused. The block message gives the literal spelling. Repos that declare no dispatch deploy see no change.
- U5 Whether `_promote_tree.py` emits a `hex` record for a sha inside a single-quoted `'inputs[ref]=<sha>'`. NOT MEASURED (no test runs allowed in this phase). An acceptance check pins it; if it fails, the fix is in `_promote_tree.py`, which is in Touch.
- U6 Version number: next free crew patch past origin/main at implement time, in both version files.

## Open questions for the owner
1. U4: block every unreadable dispatch-shaped line when the map declares a dispatch deploy (taken, recommended), or only those whose text names a declared workflow file?
2. Symbolic refs stay unresolved (taken, recommended), or should `inputs[ref]=<branch>` be resolved in the deploy's tree and compared with HEAD?
3. Split order: Bash first, PowerShell as L-0664 (taken, recommended), or hold both for one PR of about 330 lines?
4. direction.md's older sections name a consumer repository and a local path. `.work/` is ignored, but scrub them before any of it is published.

## Size and split
Estimated added production lines: `_promote_dispatch.py` about 170, `crew_guards.py` about 30, `promote-gate.sh` about 35. About 235, one new fail-closed matcher, no harness path. With the PowerShell twin (about 100, most of it the inline `Resolve-CrewPython` copy) it would pass 300, so the twin is L-0664. L-0665 is about 15 lines.

## Touch
- `plugin/crew/hooks/scripts/_promote_dispatch.py` - new: reads the map's declared dispatches and the command through crew_guards, prints the environment or exits non-zero with the reason on stderr
- `plugin/crew/hooks/scripts/crew_guards.py` - dispatch_read only (U1)
- `plugin/crew/hooks/scripts/promote-gate.sh` - call the helper when containment matched nothing; header comment
- `plugin/crew/hooks/scripts/_promote_tree.py` - only if U5 fails
- `plugin/crew/tests/test_promote_gate_dispatch.py` - new: must-block / must-allow, sh flavour (L-0664 adds ps1)
- `plugin/crew/tests/test_promote_dispatch_reader.py` - new: unit cases for the helper and dispatch_read
- `plugin/crew/tests/promote_tree_mutations.py` - new entries
- `plugin/crew/tests/test_cloud_guard_deploy.py` - only if dispatch_answer is re-expressed; no assertion loosened
- `plugin/crew/commands/promote.md` - the "Enforced by" paragraph
- `plugin/crew/.budget-allowance.json` - promote.md's ceiling, only if the paragraph does not fit in 380 lines
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/skills/crew-verification/SKILL.md`
- `plugin/crew/skills/crew-cloud/SKILL.md`
- `plugin/crew/BUDGETS.md` - counts
- `plugin/PLUGINS.md`
- `INSTALLATION.md`
- `docs/guides/crew/**` - src/troubleshooting.md plus the rebuilt HTML, DOCX and PDF
- `.crew/verify.json` - add _promote_dispatch.py and the two new test files to the promote-gate rule
- `.crew/codemap/**` - refreshed
- `.claude/rules/**` - refreshed
- `docs/diagrams/**` - refreshed
- `graphify-out/**` - refreshed
- `CHANGELOG.md`
- `TODO.md`
- `plugin/crew/.claude-plugin/plugin.json` - version
- `.claude-plugin/marketplace.json` - version

## Acceptance checks
Fixture map for all cases: `dev.deploy = "gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)"`; `prod.deploy = "gh workflow run deploy.yml -f environment=production -f ref=$(git rev-parse HEAD)"`, `requires: ["dev"]`, `requireHuman: true`.
Run: `python3 -m pytest plugin/crew/tests/test_promote_gate_dispatch.py plugin/crew/tests/test_promote_dispatch_reader.py -q`
- [ ] Must-block: `gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches -f ref=main -f 'inputs[environment]=production'` with no dev PASS row and no marker: exit 2, stderr names `prod`.
- [ ] Must-block: the same REST line for `development` from a dirty tree: exit 2, "dirty".
- [ ] Must-block: `gh workflow run deploy.yml -f ref=<sha> -f environment=production` (inputs reordered, so containment misses) with no PASS row: exit 2.
- [ ] Must-block: `'inputs[ref]=<full sha that is not HEAD>'` on the REST line: exit 2, names the commit (U5).
- [ ] Must-block, could-not-tell: `-f environment=$E`; `-f "environment=production"`; `--json`; `--input body.json`; `-F 'inputs[environment]=@f'`; `echo ... | bash`; `gh workflow run 12345`; `gh workflow run 'Deploy'`; `gh api repos/o/r/actions/workflows/$WF/dispatches -f x=y`. Each exit 2, and stderr says the gate could not tell, never "dirty" or a precondition.
- [ ] Must-block: declared workflow, `environment=staging` (fits no environment); and a map where two environments both fit: exit 2.
- [ ] Must-block: the working map has the dispatch deploy removed (uncommitted) and the REST line is run: exit 2 through the committed map.
- [ ] Must-block: `_promote_dispatch.py` made to raise: exit 2, "This is not a pass".
- [ ] Must-allow: the REST line for `development` from a clean tree: exit 0, `.crew/.deploy-in-flight` reads `dev <sha>`.
- [ ] Must-allow: the REST line for `production` with a dev PASS row and the marker for this sha: exit 0.
- [ ] Must-allow, untouched (exit 0, no marker written): `gh workflow run ci.yml`; `gh api repos/o/r/actions/workflows/ci.yml/dispatches -f ref=main`; `gh api repos/o/r/actions/workflows/deploy.yml/runs` (a GET); `gh workflow run deploy.yml --help`; `gh pr create --title "$T"`; `echo done`.
- [ ] Must-allow: a map with no dispatch deploy at all and `gh workflow run x.yml -f a=$B`: exit 0 (no new refusal for repos that declare none).
- [ ] The declared commands run verbatim still match by containment, with the same output as before: `python3 -m pytest plugin/crew/tests/test_promote_gate_effective_tree.py plugin/crew/tests/test_promote_gate_fails_closed.py plugin/crew/tests/test_promote_gate_unreadable_map.py -q` passes with no edit to those files.
- [ ] An open incident turns each new block into one row of the incident log and exit 0.
- [ ] Mutations, each RED on a named test: the helper call removed from `promote-gate.sh`; could-not-tell returning "no match"; the environment picked by workflow alone, ignoring inputs; the committed-map match dropped; the helper's failure read as empty output. Run: `cd plugin/crew/tests && python3 -c "import sabotage, promote_tree_mutations as m; sabotage.MUTATIONS = m.PROMOTE_TREE_MUTATIONS; raise SystemExit(sabotage.main())"`
- [ ] T-0009's suites unchanged and green: `python3 -m pytest plugin/crew/tests/test_cloud_guard_deploy.py plugin/crew/tests/test_cloud_guard.py -q`
- [ ] `git grep -n "_DISPATCH_RE\|/dispatches" -- plugin/crew/hooks/scripts/_promote_dispatch.py plugin/crew/hooks/scripts/promote-gate.sh` prints nothing: no second reader of the endpoint.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; `python3 scripts/check-marketplace.py` passes after the commit; crew suite `-n 4 -m "not wallclock"` then `-m wallclock`; pylint and ruff with no new findings.
- [ ] Docs state: both spellings are gated on the Bash tool; what is could-not-tell and the literal spelling that passes; that the PowerShell tool is containment-only until L-0664; the limits in Exclusions.

## Dependencies
Must land first:
- T-0009 - in-progress (PR #336 open, owner-accepted round 6, not merged). Supplies the dispatch reader. Hard blocker.
- T-0505 - merged (#296, `6fe0e0db`). The effective-tree gate this builds on.
- T-0005 - merged. T-0009's base.
Related, not blocking:
- L-0564 - direction. Same files; second to land merges main.
- L-0614, L-0615 - direction. T-0009 follow-ups in `crew_config.py` / the approval marker; no overlap.
This ticket blocks:
- L-0664 (PowerShell twin).
- T-0045 - direction. `/crew:promote` dispatching workflow runs relies on the gate recognising a dispatch.
L-0665 is independent of all of the above.

## Split
- L-0664 (child 1 of T-0062, filed 2026-10-04): promote-gate.ps1 treats a workflow dispatch of a declared deploy workflow as that deploy
- L-0665 (child 2 of T-0062, filed 2026-10-04): promote-gate reads the newest PROMOTIONS.md row for an environment and sha, not the first

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
