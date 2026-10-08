# T-0054 full /crew:autopilot guide, its own document, with every owner-requested example          status: spec   risk: low
## Refreshed 2026-10-04
First spec for this ticket; there was no spec.md or plan.md before. Written against origin/main `155fe6d8` (crew 1.0.322) from direction.md and its "Direction check 2026-10-04". The owner was not available, so each open decision takes the recommended default and is listed in direction.md under "Open questions for the owner".

What differs from the 2026-09-26 direction, and why:
- T-0048 is no longer a blocker. The build pipeline the direction waited for is already on main (`docs/guides/crew/src/build.py:68-74`); this ticket adds one `GUIDES` entry.
- T-0019 is on main (PR #379), so the direction's start condition is met.
- The example list grew by two landed features the direction did not know about: the deploy policy (T-0072) and the final-round auto-accept (L-0510).
- The example that quoted another repository's ticket key uses the neutral id `ABC-510`. This repository is public.
- No plan.md exists. `/crew:plan T-0054` writes one from this spec.

## Intent
One new document, the `/crew:autopilot` guide, in `docs/guides/crew/`: source `docs/guides/crew/src/autopilot.md`, built by `build.py` to `crew-1.0-autopilot.{html,docx,pdf}` like the other five. It is task-first: how to arm autopilot, how to hand it work, what it stops for, and how to read its output. Every example the owner asked for is in it. A landed feature gets the exact command or the real output plus what it means. A feature that has not landed gets one row in a "What is coming" table with its ticket id and no invented output.

A new suite, `scripts/_test/autopilot-guide.py`, holds the example list and fails, naming the example, when the source or the built HTML lacks one. That turns "include all the examples" into a check.

### Sections of the guide, in order
1. What autopilot is, in five lines: one ticket, driven through spec, plan, approval, implement, refresh, review and done; the order comes from files on disk; it stops where a person is needed.
2. Arm it: `"autopilot": {"mode": "plan"}` in `.crew/config.json`, `maxPhases` (default 12), and `crew_autopilot.py settings --root .` with its two output lines explained.
3. Hand it work: `/crew:autopilot`, `/crew:autopilot <id>`, `/crew:autopilot run <id>`; how it picks the ticket (argument, handoff, active ticket, the one open INDEX row); `crew_ticket.py assign` for free-text work.
4. Read its output. Three worked readings:
   - `status` (a sample of its lines, each explained; `unknown` means it could not tell);
   - the `next` line `phase=<p> stop=<0|1> command=<c> reason=<r>`;
   - "Autopilot is armed (mode=plan, maxPhases 12) and has activated ABC-510. Its first phase is spec: /crew:spec ABC-510", and why that is not a stop: with an approved direction, `spec` runs. Autopilot stops first only at `brainstorm` or `direction-approval`.
5. Approvals: `/crew:approve <id>`; why an edit to spec.md or plan.md stales the approval; several ids or a range in one message (group approval); the `human | self | risk` policies for approval and for questions, `scope.allowCliApproval`, the `self-approved <id> under approval=<policy>, risk=<risk>` line; an assigned ticket follows the same policy.
6. What it stops for: the always-a-person stops, the stops `next` enforces from disk, the never-without-a-yes list, the deploy policy (`autopilot.deploy`, `deploy-allowed`), and review: a round ends at its verdict, and only a final round with no BLOCK is auto-accepted.
7. Resume after `/clear`: the handoff's `resume: /crew:autopilot <id>` line, when it is usable, and the plain-text `continue` when `route.enabled` is true.
8. Command table: every `/crew:autopilot ...` form and every `crew_autopilot.py` action, one line each, landed or "arrives with".
9. What is coming: one row per unlanded example, with its ticket id.
10. When something looks wrong: a short list of the stops people misread, each linking to the troubleshooting guide by name.

### The example list (the suite's rows)
Landed at `155fe6d8`: each row's key phrases must be in the guide.

| # | Example | Key phrases |
|---|---|---|
| 1 | arming | `"mode": "plan"`, `maxPhases`, `crew_autopilot.py settings --root .`, `mode=plan maxPhases=12 deploy=none`, `approval=risk questions=risk` |
| 2 | armed, first phase is spec | `Its first phase is spec`, `ABC-510`, `direction-approval` |
| 3 | approving | `/crew:approve`, `stale`, `T-0010..T-0012` (the range form) |
| 4 | policies | `human`, `self`, `risk`, `scope.allowCliApproval`, `self-approved` |
| 5a | status | `/crew:autopilot status`, `waiting on:` |
| 5b | assign from the command line | `crew_ticket.py assign`, `.work/autopilot/` |
| 6 | resume after /clear | `resume: /crew:autopilot`, `/clear` |
| 11b | plain-text continue | `route.enabled`, `keep going` |
| 12 | deploy policy | `autopilot.deploy`, `deploy-allowed`, `environments.prodUnattended` |
| 13 | review stops and auto-accept | `review-acceptance`, `--auto-accept` |

Coming: each row's ticket id and phrase must be in the "What is coming" table.

| # | Example | Ticket ids | Phrase |
|---|---|---|---|
| 3c | approving a goal's split | T-0012 | `goal:<slug>` |
| 5c | `/crew:autopilot assign` route | L-0611 | `assign` |
| 5d | goal | T-0012, L-0541 | `goal` |
| 5e | focus | T-0020 | `focus` |
| 5f | wave | T-0029 | `wave` |
| 5g | split, PR slices | T-0052, T-0058, T-0059 | `split` |
| 6b | resume typed into its own session | T-0013 | `resume` |
| 7 | Telegram pings | T-0051 | `Telegram` |
| 8 | ship as a PR or a merge | T-0011 | `ship` |
| 9 | sleep mode | T-0053 | `sleep` |
| 10 | a goal survives /clear, a branch switch and a crash | T-0056 | `--goal` |
| 11 | the full goal walkthrough | T-0012, L-0541 | `walkthrough` |
| 11c | plain-text phrases for every autopilot command | T-0057 | `plain-text` |

When one of those tickets lands, its own PR moves its row from "coming" to "landed" in the suite and writes the section. That is the repo's doc rule for a `plugin/crew/` change, not part of this ticket.

## Exclusions
- No file under `plugin/` changes. No crew version bump, no CHANGELOG entry, no `plugin/PLUGINS.md` edit. A pointer from `plugin/crew/README.md` is not added: `docs/` does not ship with the plugin, so it would be a dead link on installed copies.
- No behaviour change anywhere. `crew_autopilot.py`, `crew_ticket.py` and `commands/autopilot.md` are read, never edited.
- No sample output for a feature that is not on origin/main. No text copied from an unlanded spec as if it were behaviour.
- No real ticket key, hostname, account, profile or customer id from any other repository. Sample ids are `T-0018`-shaped ids from this repo's own docs, or `ABC-510`.
- No key counts or other numbers this repo states about itself, unless marked with a claim marker. The guide needs none.
- The suite does not import crew code and does not import `markdown`. It reads two files as text.
- No `build.py --check` freshness mode: that is T-0048's. No CI doc-enforcement: that is T-0055's.
- The five existing guide sources are not edited, and their built files are not rebuilt. `daily-workflow.md`'s autopilot recipe is L-0542's.
- The crew guide's link to this document is T-0048's acceptance check, not this ticket's.
- No publish to a shared web page from this ticket's code.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- Nothing on main is this guide: `git ls-tree -r --name-only origin/main | grep -i autopilot` lists only `plugin/crew/commands/autopilot.md`, `plugin/crew/hooks/scripts/crew_autopilot.py` and six test files. `git log origin/main --grep T-0054` prints nothing.
- Build: docs/guides/crew/src/build.py:68-74 `GUIDES` (five entries, name to source list). :222-242 `build_one` writes `crew-1.0-<name>.html`, then DOCX and PDF through `render_engine.to_soffice`. :245-262 `main`; `--guide` choices come from `GUIDES`; `--html-only` skips LibreOffice. :2, :40 and :249 say "five". :52 `import markdown`.
- CI cannot import `markdown`: .pylintrc:59-64.
- Guide index: docs/guides/crew/src/README.md:7-16 (guide table), :42-48 (built-artifacts table).
- Code map that lists the guide sources: .crew/codemap/repo-docs.md:111-115.
- Commands and forms: plugin/crew/commands/autopilot.md:3 (argument hint), :14-27 (route), :29-36 (status), :38-54 (arm and pick), :56-89 (the loop, policies, review), :91-102 (stops), :104-109 (handoff and report).
- Subcommands: plugin/crew/hooks/scripts/crew_autopilot.py:224-226 `SUBCOMMANDS`, `AVAILABLE = {"status", "run"}`, `ARRIVES = {"assign": "T-0019", "goal": "T-0012", "focus": "T-0020"}`. plugin/crew/README.md:868-870 says the assign route lands with L-0611.
- Defaults: plugin/crew/hooks/scripts/crew_state.py:1134-1135 `AUTOPILOT_DEFAULTS` (`mode off`, `maxPhases 12`, `deploy none`, `approval risk`, `questions risk`). Repo only: plugin/crew/hooks/scripts/crew_config.py:389-394, plugin/crew/CONFIG.md:2591-2600.
- `settings` output, two lines plus warnings: crew_autopilot.py:1724-1729. `settings` reader: :759.
- `next` line: crew_autopilot.py:1758-1759. No spec.md runs `/crew:spec`: :454. Phase table: plugin/crew/README.md:884-891.
- `status` lines: crew_autopilot.py:1562-1587; at most 12 lines, :1355.
- Stops: crew_autopilot.py:186-200 `FIXED_STOPS`, :203-207 `PROCEDURE_STOPS`, :209-220 `HUMAN_STOPS`; plugin/crew/hooks/scripts/crew_state.py:1115 `AUTONOMOUS_STOPS`; plugin/crew/README.md:915.
- Policies: crew_autopilot.py:989 `POLICIES`, :1129-1150 `approve` and its `self-approved` line (:1147); plugin/crew/README.md:919.
- Deploy policy: crew_autopilot.py:162 `DEPLOY_VALUES`, :957 `deploy_allowed`; plugin/crew/README.md:917.
- Assign and mint: plugin/crew/hooks/scripts/crew_ticket.py:1355 `mint`, :1477 `assign`; plugin/crew/README.md:874-878.
- Which ticket, and resume: crew_autopilot.py:668 `resume_target`; plugin/crew/hooks/scripts/crew_resume.py:92 `parse_resume`; plugin/crew/commands/handoff.md:17-18; plugin/crew/README.md:913.
- Group approval: plugin/crew/commands/approve.md:27.
- Plain-text `continue`: plugin/crew/hooks/scripts/crew_route.py:82-93 `PHRASES`; plugin/crew/README.md:921-933.
- The "Autopilot is armed ... Its first phase is spec" sentence is not printed by code (`git grep -n "is armed" origin/main -- plugin/crew/hooks/scripts/crew_autopilot.py` finds only a docstring at :1131). It is the session's report under commands/autopilot.md:104-109, so the guide presents it as a report, not as script output.
- Suite wiring: scripts/gate-runner.py:150-154 (`_py_suite` rows), .github/workflows/marketplace.yml:69-70 (a suite's step), .crew/verify.json:96-104 (the `docs/**` rule) and :107-118 (the `scripts/**` rule). scripts/_test/gate-runner.py:18 checks the step table against every `run:` line of the PR-path workflows.
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS`. No path in this spec's Touch matches it.
- Suite style to copy: scripts/_test/verifying-doc.py:1-9 (throwaway roots, must-fail and must-pass cases, one `Run:` line).

## Unknowns
- Whether the implementing session has python-markdown and LibreOffice. Resolved at implement: `python3 -c "import markdown"` and `soffice --version`. If `markdown` is missing, install it for the session. If LibreOffice is missing, build with `--html-only`, commit the source and HTML, and report DOCX and PDF as NOT built so the local session builds and commits them before the PR merges. Never commit a DOCX or PDF made by another tool.
- Exact `status` and `settings` sample output. Resolved at implement by running the script in a throwaway repo under a temp directory and pasting what it printed. Not from memory, and not from this repo's real `.work/`.
- Whether another autopilot ticket lands first and moves a row from coming to landed. Resolved at implement: re-read `AVAILABLE` and `ARRIVES` on origin/main and each coming ticket's INDEX state, and move the row.
- Whether T-0048 lands first. If it has, `build.py` has a `--check` mode and `GUIDES` has two more entries: add `autopilot` beside them and run `build.py --check`. If it has not, nothing changes here.
- The `docs/**` verify rule's `seconds` after the new suite joins it: re-timed at implement.
- Open questions Q1-Q5 in direction.md are the owner's. This spec assumes each default. Q3 answered the other way adds `plugin/crew/README.md`, the three version files and `CHANGELOG.md` to Touch and needs a re-approval.

## Size and split
- Production lines added (code under `plugin/`, `scripts/`, `skills/`, tests and docs aside): about 2, one `_py_suite` row in `scripts/gate-runner.py`. `build.py` lives under `docs/` and gains one `GUIDES` entry and two docstring words.
- No new parser, guard or state machine. The suite is a phrase list read against two text files.
- No harness path. Not split.
- For scale: the guide source is about 350-450 lines of Markdown and the suite about 150 lines.

## Touch
- `docs/guides/crew/src/autopilot.md` - new, the guide source
- `docs/guides/crew/src/build.py` - one GUIDES entry, the docstring's guide count
- `docs/guides/crew/src/README.md` - a row in the guide table and in the built-artifacts table
- `docs/guides/crew/crew-1.0-autopilot.html`
- `docs/guides/crew/crew-1.0-autopilot.docx`
- `docs/guides/crew/crew-1.0-autopilot.pdf`
- `scripts/_test/autopilot-guide.py` - new, the example suite
- `scripts/gate-runner.py` - one step-table row
- `.github/workflows/marketplace.yml` - one step that runs the suite
- `.crew/verify.json` - the suite joins the two rules named in Evidence
- `.crew/codemap/repo-docs.md` - the source list names the new file
- `graphify-out/**` - rebuilt by graphify update, a refresh artifact

Not in Touch, stated: anything under `plugin/` (see Exclusions); `CHANGELOG.md` (its entries are per plugin version and no plugin changes); `docs/diagrams/` (no box or edge changes); the other five guides' sources and built files.

## Acceptance checks
Commands run from the repo root. No pytest suite is needed for this ticket.
- [ ] The guide source exists with the ten sections of the Intent, in that order. `grep -c "^## " docs/guides/crew/src/autopilot.md` prints 10 or more.
- [ ] The new suite passes on the committed tree: `python3 scripts/_test/autopilot-guide.py` exits 0 and prints one PASS line per example row. It reads `docs/guides/crew/src/autopilot.md` and `docs/guides/crew/crew-1.0-autopilot.html` (tags stripped, entities unescaped, whitespace collapsed).
- [ ] The suite's own must-fail cases, each on a throwaway copy under a temp directory, each exiting 1 and naming the example:
  - a landed row's phrase removed from the source;
  - the same phrase present in the source and missing from the HTML (a stale build);
  - a coming row's ticket id removed from the "What is coming" table;
  - a coming row's ticket id present elsewhere in the guide but not in that table;
  - the source file missing, and the HTML file missing (exit 1 naming the file, never a pass).
- [ ] The suite's must-pass cases: the committed pair; a phrase split across a line wrap in the source; a phrase inside a fenced block.
- [ ] Sabotage by hand, recorded in the PR body: delete the "Its first phase is spec" sentence from the source, rebuild the HTML, run the suite, see it fail naming example 2, restore.
- [ ] No foreign identifiers: `grep -ohE "\b[A-Z]{2,}-[0-9]+\b" docs/guides/crew/src/autopilot.md docs/guides/crew/crew-1.0-autopilot.html scripts/_test/autopilot-guide.py | sort -u` prints only `ABC-510` (this repo's own ids are one letter, `T-` or `L-`, so they do not match).
- [ ] Every repo path the guide names in backticks exists: for each backticked token that starts with `plugin/`, `docs/`, `scripts/` or `.crew/`, `git ls-files --error-unmatch <path>` exits 0 (`.crew/config.json` is the one exception: it is the reader's own file). Every `/crew:<name>` the guide names has `plugin/crew/commands/<name>.md`.
- [ ] Every sample of script output in the guide was produced by running the script at the implementing commit in a throwaway repo; the PR body lists the commands run.
- [ ] Nothing unlanded is shown as working: each of `goal`, `focus`, `wave`, `split`, `sleep`, `ship`, `Telegram` appears in the "What is coming" table with its ticket id, and `/crew:autopilot assign` is described as arriving with L-0611 unless `assign` is in `AVAILABLE` at the implementing commit (`git grep -n "^AVAILABLE" origin/main -- plugin/crew/hooks/scripts/crew_autopilot.py`).
- [ ] Built: `python3 docs/guides/crew/src/build.py --guide autopilot` exits 0, prints `-- OK` for the fenced-block count, and writes the HTML, DOCX and PDF; all three are committed. If LibreOffice is absent, see Unknowns: HTML only, and the report says DOCX and PDF were not built.
- [ ] The other guides are untouched: `git diff --stat origin/main -- docs/guides/crew/ ':!docs/guides/crew/crew-1.0-autopilot.*' ':!docs/guides/crew/src/autopilot.md' ':!docs/guides/crew/src/build.py' ':!docs/guides/crew/src/README.md'` prints nothing.
- [ ] `docs/guides/crew/src/README.md` lists the guide in both tables, and `build.py`'s docstring no longer says "five".
- [ ] Wiring: `python3 scripts/_test/gate-runner.py` passes (the step table still covers every workflow `run:` line; exit 77 means a case was skipped and is reported as skipped, not as a pass). `.crew/verify.json` parses (`python3 -c "import json;json.load(open('.crew/verify.json'))"`) and both rules named in Evidence run the new suite.
- [ ] Lint: `python3 -m ruff check scripts/_test/autopilot-guide.py docs/guides/crew/src/build.py` and `python3 -m pylint scripts/_test/autopilot-guide.py` report nothing new.
- [ ] Gate: `python3 scripts/check-marketplace.py` passes after the commit, and `git diff --name-only origin/main -- plugin/` prints nothing.
- [ ] PR body carries `Docs: this PR is the doc - no plugin/crew change`, names which suites ran and which did not (`drift-detection.sh` is skipped), and `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` or reports no harness path.

## Dependencies
Must land first (all are on origin/main already):
- T-0010 (INDEX: merged, PR #261): the approval and questions policies the guide documents.
- T-0018 (INDEX: merged): the subcommand router and `status`.
- T-0019 (INDEX: in-progress; on origin/main as PR #379, merge `d67098ad`): `crew_ticket.py assign` and `mint`. INDEX is behind the merge.
- T-0004 (merged), T-0006 (merged), T-0023 (merged), T-0024 (merged), T-0072 (merged), L-0510 (done): each is behaviour the guide shows as landed.

Named by the direction as a dependency, no longer one:
- T-0048 (INDEX: spec, not landed): the build pipeline it was wanted for is on main. Whichever of the two lands second adds its `GUIDES` entry beside the other's. T-0048's crew guide links to this document.

Not dependencies; each adds its own section here when it lands: L-0611 (direction), T-0011 (approved), T-0012 (approved) and L-0541 (direction), T-0013 (approved), T-0020 (approved), T-0029 (in-progress), T-0049 (in-progress), T-0051 (approved), T-0052 (spec), T-0053 (ready), T-0056 (ready), T-0057 (ready), T-0058 (spec), T-0059 (spec), T-0067 (ready), T-0073 (direction).

This ticket blocks:
- T-0048 (spec), softly: its acceptance check has the crew guide's autopilot section link to this document.
- T-0055 (ready), softly: its doc-enforcement would count this guide among the built guides.
- L-0542 (direction) is related, not blocked: it fixes the autopilot recipe in the daily-workflow guide.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
