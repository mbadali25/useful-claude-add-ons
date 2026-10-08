# L-0667: /crew:graph - one command for graph status, the sanctioned refresh and queries          status: spec   risk: med
Split from T-0067 on 2026-10-04. Written against origin/main `155fe6d8` (crew 1.0.322). **Do not start before T-0064 has merged**: it adds the checker this command calls and edits the same function in `crew_refresh_check.py`. Re-read every anchor below on the main that contains T-0064.

## Design (for the owner to confirm at approval)
- **`plugin/crew/commands/graph.md`**, arguments `[--status | --refresh | --query "<question>"]`, default `--status`. Thin prose over the script; the `crew-graph` skill stays the method (detect, install offer, MCP server, query help).
- **`plugin/crew/hooks/scripts/crew_graph.py`**:
  - `status --root . [--json]`, read-only. One line: `graph=<fresh|stale|unknown|absent> built_at=<sha|none> pair=<agree|disagree|unknown|untracked> ignore=<covered|uncovered|unknown> command=<what refresh would run>`. Freshness and the command come from the functions the refresh check already uses, never a second copy of the rule.
  - `refresh --root .`. In this order, stopping at the first that fails:
    1. `graphify` not on PATH: exit 2, `graphify missing`. Never installs.
    2. T-0064's `crew_graph_ignore.coverage`: `uncovered` exits 1 and names the files and `crew_graph_ignore.py --write`; `unknown` exits 2 with its reason. Nothing is built in either case.
    3. Run the sanctioned command (`graphify update .` when the report is tracked, else `graphify . --no-viz --code-only`) from the repo root, through `crew_shell.py run --` on native Windows as the skill does. A non-zero exit is exit 1 with the tool's output verbatim.
    4. Verify. `graph.json` must carry `built_at_commit`. When the report is tracked, the first `- <N> nodes · <M> edges` line under `## Summary` in `GRAPH_REPORT.md` must equal `len(graph["nodes"])` and `len(graph["links"])`. A mismatch is exit 1, `pair=disagree`, printing all four numbers. A report with no such line, or a graph that cannot be parsed, is exit 2, `pair=unknown`. Neither reads as agree.
    5. Print the changed paths under the graph directory. It does not commit.
  - Exit codes: 0 done and verified, 1 refused or failed, 2 could not tell.
- **`--query`** is prose: run `status`; print a warning line when the graph is not `fresh`; then `graphify query "<question>"` as the skill documents.
- **The refresh hint.** The graph artifact that `crew_refresh_check` reports names `/crew:graph --refresh` as its `command` and carries the raw command in a new `runs` field. The line `    command = ("graphify update ." if info["reportTracked"]` stays byte-identical and exactly once (it may move into a small helper at the same indent), because `sabotage_refresh.py:151-154` anchors it and a feature PR may not edit a sabotage file. The mutation's test (`test_graph_without_a_tracked_report_names_the_code_only_build`) asserts on `runs` afterwards, so the mutation still turns it red.
- **The skill** gains a short "Refresh" section: prefer `/crew:graph --refresh`; `graphify update .` where the report is tracked. Its Build section stays for a first build.

## Intent
Crew has one command for the code graph. `/crew:graph --refresh` runs the refresh this repo sanctions, refuses when a secrets-denylisted file would be read, and proves the tracked pair agrees before anyone commits it. `/crew:graph --status` says in one line whether the graph is current. Refresh hints name the command instead of a raw tool line.

## Exclusions
- No change to graphify, its hook, or `graphify hook install`. No install of anything.
- No new denylist logic: T-0064's checker is called, not copied. No write to `.graphifyignore` (that is `crew_graph_ignore.py --write`).
- No commit, push or staging by the script.
- No edit to `plugin/crew/tests/sabotage*.py` or any other harness path. If the anchored line cannot stay byte-identical, stop: the hint rename moves to a tooling follow-up and this ticket ships without it.
- No change to `/crew:onboard` step 1 or `/crew:upgrade` step 3 (first builds; T-0064 edits them).
- No config key. `graph.out` and `graph.mode` are read as they are today.
- No Obsidian or vault export (the skill's closed question).
- No autopilot behaviour change: the refresh phase still runs the named command; only the name changes.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04, except the T-0064 lines, read on its open branch.
- `git ls-tree origin/main plugin/crew/commands/` lists 36 files; no `graph.md`.
- plugin/crew/skills/crew-graph/SKILL.md:41-45 the Build command; :46-49 the Windows route through `crew_shell.py run --`; :72-84 Query; :86-121 Freshness and `built_at_commit`.
- plugin/crew/hooks/scripts/crew_refresh_check.py:1225-1243 `_graph`: the command choice at :1226-1227, `not applicable` with no graph, `unknown` and not refreshable when graphify is missing, `unknown` and refreshable with no `built_at_commit`. :236 `REFRESH_ARTIFACT_PATHS`.
- plugin/crew/hooks/scripts/crew_freshness.py:104 `GRAPH_OUT_DEFAULT`, :155 the `built_at_commit` reader, :310-311 the same two commands.
- plugin/crew/tests/sabotage_refresh.py:151-154 the mutation "the graph always names graphify update" and its test.
- graphify-out/GRAPH_REPORT.md:8-9 `## Summary` then `- 23840 nodes · 50994 edges · 1044 communities (...)`. The repo CLAUDE.md, "Memory": the graph's keys are `nodes` and `links`.
- plugin/crew/commands/autopilot.md:65-67 names the three refresh commands, `graphify update .` among them.
- T-0064's branch: `crew_graph_ignore.py` defines `COVERED`, `UNCOVERED`, `UNKNOWN` and `coverage(root, git="git")`, and a CLI `--check` / `--write`.
- Counts that move from 36 to 37 commands: plugin/crew/README.md:2822 (marker `plugin-commands:crew`) and its command table near :2795; README.md:168; plugin/PLUGINS.md:17; plugin/crew/skills/crew-best-practices/SKILL.md:29; plugin/crew/skills/crew-best-practices/references/practices.md:147; .claude-plugin/marketplace.json:223 (the crew description); scripts/install-prerequisites.sh:1393 and scripts/install-prerequisites.ps1:1175 (a matched pair); .crew/codemap/crew.md:54 and :58.
- .crew/verify.json:236-241 the prompts rule (`validate-prompts.py`) covers a new command file; :314-334 the refresh-check rule.
- scripts/check-tooling-pr.py:58-87: no path in this Touch is a harness path.

## Unknowns
- **T-0064's final shape.** `_graph` and the checker's API are read again after it merges; this spec's line numbers will have moved.
- **Does anything execute the artifact's `command` string as a shell line?** Resolved at plan: `git grep -n '"command"' origin/main -- plugin/crew/hooks/scripts/crew_train.py plugin/crew/hooks/scripts/crew_autopilot.py plugin/crew/commands/implement.md plugin/crew/commands/done.md`. If a script runs it, that script reads `runs` instead and joins Touch by amendment.
- **Report format drift.** The Summary line is graphify's, not crew's. A format the matcher does not recognise is `pair=unknown` (exit 2), never agree. The test fixture copies the real line.
- **Cost of a full parse.** `graph.json` is parsed whole for the pair check. Accepted for an explicit command; the session-start path keeps its bounded tail read.
- **A background rebuild on commit** (a host's own hook) can overwrite the build mid-check. Out of scope; `status` reports what is on disk when it runs.
- **Install-script pin.** The root README pins both install scripts to a commit SHA; after this merges, both are re-pinned (a promotion step no script enforces).
- The next free crew patch version is set at implement time.

## Size and split
About 250 added production lines: `crew_graph.py` about 170, `graph.md` about 60, `crew_refresh_check.py` about 12, the skill, `autopilot.md` and the two install scripts about 8. One parser (the Summary line) and one refusal chain. If `crew_graph.py` passes 200 lines at plan, the hint rename (the `runs` field) is cut to a follow-up rather than growing this PR past 300.

## Touch
- `plugin/crew/commands/graph.md` - new
- `plugin/crew/hooks/scripts/crew_graph.py` - new
- `plugin/crew/hooks/scripts/crew_refresh_check.py` - the graph artifact's command and the new runs field only
- `plugin/crew/commands/autopilot.md` - the list of refresh commands
- `plugin/crew/skills/crew-graph/SKILL.md`
- `plugin/crew/skills/crew-best-practices/SKILL.md` - the command count
- `plugin/crew/skills/crew-best-practices/references/practices.md` - the command count
- `plugin/crew/tests/test_crew_graph.py` - new
- `plugin/crew/tests/test_refresh_check.py`
- `.crew/verify.json` - a rule for crew_graph.py and its test
- `scripts/install-prerequisites.sh` - the crew row's command count
- `scripts/install-prerequisites.ps1` - the same text, same place
- `README.md`
- `plugin/README.md`
- `plugin/PLUGINS.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/**` - src/troubleshooting.md if T-0064 left a raw graph command there, plus the rebuilt HTML, DOCX and PDF
- `.crew/codemap/**`
- `docs/diagrams/**`
- `.claude/rules/**` - regenerated, never hand-edited
- `graphify-out/**` - refresh artifact
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `plugin/crew/CONFIG.md` (no key); every harness path; `crew_graph_ignore.py` (T-0064's).

## Acceptance checks
Commands run from the repo root. `T` is `plugin/crew/tests/test_crew_graph.py`. Tests use a fake `graphify` on PATH that writes a fixture graph and report; none runs the real tool or touches this repo's `graphify-out/`.
- [ ] `status` on a fixture with a tracked pair that agrees prints `graph=fresh ... pair=agree ignore=covered command=graphify update .` and writes nothing (the tree's `git status --porcelain` is unchanged). `python3 -m pytest T -q -k test_status_is_one_line_and_read_only`
- [ ] `status` with no graph prints `graph=absent`; with an untracked report prints `pair=untracked` and `command=graphify . --no-viz --code-only`. `-k test_status_absent_and_untracked`
- [ ] Must-allow: `refresh` on a covered fixture runs the fake tool once with the sanctioned arguments, exits 0, prints the changed paths, and makes no commit (`git rev-parse HEAD` unchanged). `-k test_refresh_runs_the_sanctioned_command_and_verifies`
- [ ] Must-block, one test each; in each the fake tool's call log stays empty unless stated:
  - graphify missing: exit 2;
  - coverage `uncovered`: exit 1, the file named;
  - coverage `unknown`: exit 2;
  - the tool exits non-zero: exit 1, its output verbatim (called once);
  - the built graph has no `built_at_commit`: exit 2 (called once);
  - Summary says 10 nodes and the graph holds 9: exit 1, `pair=disagree`, all four numbers printed (called once);
  - links differ while nodes agree: exit 1;
  - no `## Summary` line: exit 2, `pair=unknown`;
  - `graph.json` is not valid JSON: exit 2;
  - a graph with an `edges` key and no `links`: exit 2, never read as zero links.
- [ ] The refresh check's graph artifact names `/crew:graph --refresh` and carries the raw command in `runs`, for both the tracked and the untracked report. `python3 -m pytest plugin/crew/tests/test_refresh_check.py -q -k "graph and names"`
- [ ] The anchor is intact and no sabotage file changed: `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q -k test_every_shipped_anchor_is_present_in_its_target_exactly_once`; `git diff --name-only origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- [ ] The command file is valid and names only paths that exist: `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`.
- [ ] `autopilot.md` lists `/crew:graph --refresh` among the refresh commands. `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -k command`
- [ ] Registration is whole: every count listed in Evidence reads 37, both install scripts carry the same text, and `python3 scripts/check-marketplace.py` passes after the commit (run it after committing: its drift check compares commits).
- [ ] Not a tooling PR: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`.
- [ ] Docs: crew README (command table and the refresh-check row), PLUGINS.md ("The code graph"), the skill, the code map and the lifecycle diagram describe the command. Crew is bumped to the next free patch with a CHANGELOG entry.
- [ ] On this repo, by hand, once: `/crew:graph --status` prints one line, and `--refresh` leaves `pair=agree`. Reported as run or not run; not a CI check.

## Dependencies
Must land first:
- T-0064 (approved; draft PR open): `crew_graph_ignore.coverage` and its edit to `_graph`.
- T-0008 (merged): the refresh check.

Related: T-0063 (approved; graph freshness when topology is unchanged - edits `crew_refresh_check.py` too, whichever lands second re-reads), T-0067 and L-0666 (both edit `commands/autopilot.md`; L-0666's `MECHANICAL` list already names `/crew:graph --refresh`).

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
