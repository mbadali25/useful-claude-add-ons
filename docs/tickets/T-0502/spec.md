# T-0502 crew-setup ships a diagram check that renders as root, and its runners show why a check failed          status: spec   risk: low
## Intent
A repo set up by crew gets a ready `_verify` diagram case that renders Mermaid sources as root and in containers (it passes the same `--no-sandbox` puppeteer config as `render.sh`) and prints mmdc's own error lines when a render fails. The two template runners stop discarding a failing check's output and report exit 77 as SKIP, so the cause is visible whichever way the case is run. Taken from direction.md "Direction check 2026-10-04", option 1.

## Exclusions
- No change to `plugin/crew/skills/crew-diagrams/scripts/render.sh`, `diagram_check.py` or `diagram_doc.py`. `render.sh` already passes the config and prints mmdc's output.
- No change to this repo's own `_verify/smoke.sh` or `_verify/run-all.sh`. Only the templates under `plugin/crew/skills/crew-setup/templates/` change.
- No migration of repos that already ran setup. Their copied runners and hand-written cases stay as they are; the docs say what to change by hand.
- The new case is not placed under `templates/_verify/`. That tree is copied whole by setup (`setup-walkthrough.sh:72`), and a repo with no diagrams must not receive a case that fails.
- The case does not call into the plugin (`CLAUDE_PLUGIN_ROOT` is not set in a repo's CI or under the gate).
- No EUID branch: the config is passed always (see direction.md, open question 1).
- No new hook, no config key, no change to `verify-gate.sh`, `verify-gate.ps1`, `verify_record.py` or any other path in `HARNESS` (`scripts/check-tooling-pr.py:58-87`).
- No PowerShell flavour of the case or the runners. The templates are bash only today.
- No install of `mmdc` or Chromium by the case.

## Evidence
All read at origin/main `155fe6d8` (crew 1.0.322) on 2026-10-04.
- The reported file is not a crew template: `git ls-tree -r --name-only origin/main | grep crew-setup/templates/_verify` lists only `README.md`, `run-all.sh`, `smoke.sh`. `git grep -n "diagrams-parse" origin/main` prints nothing. `git grep -n -i "does not render" origin/main -- plugin/crew` prints nothing.
- plugin/crew/skills/crew-setup/phases.md:301 "Phase 3 - Smoke harness"; :307-309 create `_verify/` from `templates/_verify/` with "an empty `cases/`. Then fill it, in this session".
- plugin/crew/commands/verify.md:9-15 the same scaffold step for `/crew:verify`.
- plugin/crew/skills/crew-setup/templates/_verify/smoke.sh:26-28 `check()` runs `"$@" >/dev/null 2>&1` and prints `FAIL $n: $*`; :41 the count line `SMOKE: $PASS/$((PASS+FAIL)) passed against $ENV`.
- plugin/crew/skills/crew-setup/templates/_verify/run-all.sh:31-33 `run()` with the same discard; :34 `skip()`; :45-53 the `_verify/cases/*.sh` loop and the `# readonly: yes` allowlist; :55 the count line.
- plugin/crew/skills/crew-setup/templates/_verify/README.md:20 the `cases/` row; :27-41 the contract (exit 0 pass, `--env`, read-only marker, `PASS`/`FAIL` lines, `trap` cleanup); :44-56 "Adding a check".
- plugin/crew/skills/crew-diagrams/scripts/render.sh:72-75 missing `mmdc` exits 1; :92-95 the puppeteer config `{"args":["--no-sandbox","--disable-dev-shm-usage"]}` and its `trap`; :96-107 the `cygpath -w` conversion needed under `MSYS_NO_PATHCONV=1`; :147 the quiet first attempt; :159-160 `FAIL` then `mmdc ... 2>&1 | tail -5 >&2`.
- plugin/crew/skills/crew-diagrams/SKILL.md:171-172 and plugin/crew/README.md:2399 and :3100 are the only places that say a direct `mmdc` call lacks `--no-sandbox`.
- plugin/crew/skills/crew-setup/SKILL.md:93-97 the scaffold tree; plugin/crew/README.md:393-404 the same tree in the README.
- Exit 77 is crew's SKIP convention: plugin/crew/commands/verify.md "Exit 77 is SKIP"; plugin/crew/skills/crew-diagrams/scripts/_test/render.sh:47-53 and :66.
- plugin/crew/hooks/scripts/_test/setup-walkthrough.sh:72 copies `templates/_verify` whole; :92-101 greps the runners' output for `SMOKE target: dev`, `SMOKE:`, `PASS read-orders`, `SKIP write-order` and exit codes. No `.crew/verify.json` rule runs this script.
- .crew/verify.json:236-241 `plugin/crew/skills/**` maps only to `validate-prompts.py`; :243-245 `plugin/crew/skills/crew-diagrams/**` maps to the render suite. No rule runs a test of the `crew-setup/templates/` scripts.
- plugin/crew/tests/test_diagram_doc.py:161-165 `FAKE_MMDC`, and :172 `crew_fixtures.resolve_bash()`: the existing way to test an mmdc caller without mermaid-cli.
- docs/handoff/cloud/T-0502.md "Cleanup (required)": delete that file and its row (docs/handoff/cloud/README.md:24) in this ticket's PR.
- `git grep -n -E "mmdc|no-sandbox" origin/main -- docs/guides/crew/src` prints nothing: the guides do not cover diagram rendering today.

## Unknowns
- Whether `--no-sandbox` should be root-only. Taken: always, as `render.sh`. Owner question 1 in direction.md; changing it later is a few lines in the case.
- A failing check's last lines now reach the gate log, which could include a secret a check echoes. Accepted as risk: capped at 5 lines, and the template contract already keeps credentials out of files. Owner question 2.
- `setup-walkthrough.sh` is run by no rule and writes under `/tmp`. Resolved at implement by keeping every line it greps byte-compatible (`PASS <name>`, `SKIP <name> (...)`, `SMOKE:` and `REGRESSION:` prefixes, exit codes); the new pytest asserts those same lines. Do not run the walkthrough on the shared host.
- Real `mmdc` as root is not exercised by the tests (they use a fake `mmdc` that records its arguments). Resolved at implement, where a host has mermaid-cli: one manual run of the case as root against `docs/diagrams`, quoted in the PR body. If no such host is available, say so in the PR body.
- `plugin/crew/commands/verify.md` is over the 120-line command budget and listed in `.budget-allowance.json`; growth there is a hard fail. Resolved at plan: if the one added sentence cannot be offset inside the file, put the pointer in `phases.md` and the template README only and leave `verify.md` unchanged.
- The next free crew patch version is set at push time, one past origin/main's.

## Design
- New file `plugin/crew/skills/crew-setup/templates/cases/diagrams-render.sh` (copied to `_verify/cases/diagrams-render.sh` only in a repo that has Mermaid sources):
  - header comment, `# readonly: yes`, `set -uo pipefail`; accepts and ignores `--env <name>`; directory from `DIAGRAMS_DIR`, default `docs/diagrams`;
  - `mmdc` absent: one `SKIP` line on stderr naming the install command, exit 77;
  - no `.mmd` in the directory: `FAIL no .mmd files in <dir>`, exit 1;
  - writes the puppeteer config with `mktemp`, converts the path with `cygpath -w` when present, renders each source to a temp directory, removes both with `trap`;
  - per file `PASS <name>` or `FAIL <name>` followed by the last 5 lines of mmdc's combined output (captured from the one run, no second render); an empty output file with exit 0 is a FAIL;
  - final count line; exit 1 if any failed.
- `templates/_verify/smoke.sh` `check()` and `templates/_verify/run-all.sh` `run()`: capture the check's combined output; exit 0 prints `PASS <name>`; exit 77 prints `SKIP <name> (exit 77: tool or environment absent)` and is not a failure; any other exit prints `FAIL <name>: <command>` then the last 5 output lines, indented. `smoke.sh` gains a skip count in its final line, which still starts `SMOKE: `.
- Docs: the setup phase and the template README say to copy the case when the repo has `.mmd` files and never to call `mmdc` bare; the crew-diagrams skill and the README troubleshooting row name the case.

## Size and split
- Estimate: about 110 added production lines under `plugin/` (the case about 60, the two runners about 20 together, skill and command Markdown about 30). Under the 300-line rule.
- No new parser, guard or fail-closed state machine. No `HARNESS` path (`.crew/verify.json` is in `ALONGSIDE`, and no harness file is edited, so the tooling-PR rule is not engaged).
- Not split. One PR.

## Touch
- `plugin/crew/skills/crew-setup/templates/cases/diagrams-render.sh` - new
- `plugin/crew/skills/crew-setup/templates/_verify/smoke.sh`
- `plugin/crew/skills/crew-setup/templates/_verify/run-all.sh`
- `plugin/crew/skills/crew-setup/templates/_verify/README.md`
- `plugin/crew/skills/crew-setup/phases.md`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/skills/crew-diagrams/SKILL.md`
- `plugin/crew/commands/verify.md` - only if the line budget allows, see Unknowns
- `plugin/crew/tests/test_setup_verify_templates.py` - new
- `.crew/verify.json` - one rule mapping the templates directory to the new test
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `.crew/codemap/INDEX.md`
- `docs/handoff/cloud/T-0502.md` - deleted, as its own cleanup section requires
- `docs/handoff/cloud/README.md` - the T-0502 row removed
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `graphify-out/**` - refresh artifact

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact); `plugin/crew/hooks/scripts/_test/setup-walkthrough.sh` (its assertions stay true); `render.sh` and its suite.

## Acceptance checks
Commands run from the repo root. On a memory-bound host run pytest through the repo's heavy-run wrapper. All tests below are in the new `plugin/crew/tests/test_setup_verify_templates.py`, use a fake `mmdc` on a temp PATH, and skip only where `crew_fixtures.resolve_bash()` finds no bash.
- [ ] The case passes the sandbox config: the fake `mmdc` records its arguments and the file named after `-p`; that file's JSON `args` contains `--no-sandbox`. `python3 -m pytest plugin/crew/tests/test_setup_verify_templates.py -q -k test_diagram_case_passes_a_no_sandbox_puppeteer_config`
- [ ] The cause is shown: a fake `mmdc` that prints `Running as root without --no-sandbox is not supported` on stderr and exits 1 makes the case exit 1 with that sentence in its output and a `FAIL <name>` line. `-k test_diagram_case_prints_mmdc_stderr_on_failure`
- [ ] A fake `mmdc` that exits 0 and writes nothing is a FAIL, not a PASS. `-k test_diagram_case_fails_on_an_empty_render`
- [ ] No `mmdc` on PATH: exit 77 and a line naming the install command. `-k test_diagram_case_exits_77_without_mmdc`
- [ ] A directory with no `.mmd`: exit 1, `no .mmd files`. `-k test_diagram_case_fails_on_no_sources`
- [ ] The case leaves no file behind in the diagrams directory or the temp directory it was given (`TMPDIR` pointed at a test directory, empty after the run), on pass and on failure. `-k test_diagram_case_cleans_up`
- [ ] `run-all.sh` through the copied template: a failing case's last output line appears under its `FAIL` line; a case exiting 77 prints `SKIP`, the run exits 0 and the count line reports one skipped; the `--read-only` lines `PASS read-orders` and `SKIP write-order` and the production refusal (exit 1 without `--read-only`) are unchanged. `-k test_run_all`
- [ ] `smoke.sh` through the copied template: a failing `check` prints its output tail and exits 1; an exit-77 check prints `SKIP` and does not fail the run; the first line is still `SMOKE target: dev -> ...` and the last still starts `SMOKE: `. `-k test_smoke`
- [ ] The diagram case end to end through `run-all.sh` with the failing fake `mmdc`: the sandbox sentence is visible in `run-all.sh`'s output. This is the reported symptom. `-k test_run_all_shows_the_mmdc_error`
- [ ] Sabotage, by hand, each reverted after: (a) drop `-p` from the case's `mmdc` call, the config test goes red; (b) restore `>/dev/null 2>&1` in `run()`, `test_run_all_shows_the_mmdc_error` goes red; (c) make exit 77 fall through to FAIL, the SKIP test goes red. Quote the three red results in the PR body.
- [ ] All three template scripts are LF and parse: `bash -n` on each, and `file` reports no CRLF.
- [ ] The new rule fires: `.crew/verify.json` maps `plugin/crew/skills/crew-setup/templates/**` to the new test with `"reach": "local"` and a measured `seconds`.
- [ ] Prompts still validate: `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`.
- [ ] Instruction budgets hold and `plugin/crew/BUDGETS.md`'s count is re-measured: `python3 scripts/check_instructions.py`.
- [ ] Docs: `phases.md` Phase 3, the template README and `plugin/crew/README.md` section 6 and the `mmdc` troubleshooting row name `diagrams-render.sh` and say a bare `mmdc` call fails as root; the guide's troubleshooting source has the same entry and the guide outputs are rebuilt.
- [ ] The hand-off note is gone: `git ls-files docs/handoff/cloud/T-0502.md` prints nothing and `grep -c T-0502 docs/handoff/cloud/README.md` prints 0.
- [ ] Version bumped one patch past origin/main in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, with a CHANGELOG entry; after committing, `python3 scripts/check-marketplace.py` and `bash _verify/smoke.sh` pass.

## Dependencies
Must land first: none.
- T-0088 (merged): item 17 of the same report; context only.
- T-0500 (approved), T-0501 (done), T-0503 (merged), T-0106 (direction): siblings from the same report. Independent; T-0500 also edits crew-setup phase text, so whichever lands second merges main first.
Blocks: nothing.

## Plan
No plan.md exists. Run `/crew:plan T-0502` against this spec.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
