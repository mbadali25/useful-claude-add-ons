# L-0582 Review metrics resolve the main checkout's .crew/ from a linked worktree          status: spec   risk: med

Anchored to origin/main `8d84786d` (crew 1.0.115, 2026-10-02). L-0578 (`review_metrics.py`, crew
1.0.119) is NOT on origin/main at this anchor: `git ls-tree origin/main plugin/crew/hooks/scripts/`
lists no `review_metrics.py`.

## Intent

Every production reader and writer of `.crew/metrics.md` (`crew_state.read_metrics`,
`crew_standards.metric` with and without `--record`, `crew_status._metrics_line`) gets its `.crew/`
from one shared resolver in `crew_common`. Run from a linked worktree, that resolver returns the main
checkout's `.crew/`, found through `git rev-parse --git-dir --git-common-dir`. When git cannot answer,
it returns a could-not-tell problem and no path. Each caller then reports could-not-tell visibly and
never falls back to the worktree's own copy. This is direction.md Option 1.

## Exclusions

- No change to `crew_metrics.py`'s `metrics.jsonl` writer (`metrics_path`,
  `plugin/crew/hooks/scripts/crew_metrics.py:138-139`). It is out of scope per the direction's settled
  Q1 and is recorded below as a candidate follow-up.
- No change to `crew_migrate.py`. It is a one-time migration that runs against the checkout it is
  pointed at (direction Q1).
- No reading, merging, moving or deleting of rows already stranded in a lane's own
  `.crew/metrics.md` (direction Q4). Recovering them is L-0583. `/crew:status` only names the
  stranded file as not counted.
- No union of the main and local copies (direction Option 3).
- No change to the row format, the `read_metrics` grouping and windowing, `metric_summary`, or the
  `HEALTHY_LOW`/`HEALTHY_HIGH` thresholds.
- No harness path in the feature PR. `plugin/crew/tests/sabotage*.py` and `review_*.py` are
  `HARNESS` in `scripts/check-tooling-pr.py:56-83`, so the sabotage entries and any
  `review_metrics.py` delegation go in the separate tooling PR. That PR takes the next free L- number,
  under the standing tooling-PR rule (see Touch, "tooling PR").
- No edit to `plugin/crew/commands/review.md` (the prose writer, steps 6 and 8) in either PR. L-0578
  owns those lines: its branch (`/repos/personal/uca-l0578`, `L-0578-build` at `da9d1107`) already
  rewrites step 6 to "the MAIN checkout's `.crew/metrics.md` (also from a worktree)" and step 8 to "the
  file step 6's `review:` line named". Editing them here would collide with a lane this workflow must
  not touch. If L-0578 closes unmerged, the prose fix becomes a follow-up L- ticket filed at land.
- No edit to another lane's worktree, and none to `/repos/personal/uca-l0578`.

## Evidence

Callers that join `.crew/metrics.md` to `root` (origin/main 8d84786d):
- `plugin/crew/hooks/scripts/crew_state.py:313-316`: `read_metrics` builds `empty = {..., "verdict":
  "no data"}`, then calls `read_text(os.path.join(root, ".crew", "metrics.md"))` and returns `empty` on
  no text. A lane therefore reads its own (usually absent) copy as "no data".
- `plugin/crew/hooks/scripts/crew_state.py:3099`: `"health": read_metrics(root)` in `collect`. Its
  consumers are `evaluate_triggers` at `crew_state.py:3011-3014` (`reviewNotWorking` and
  `ticketsTooLarge` both fire only on `rate is not None`) and `/crew:split`'s `health.rate`
  (`plugin/crew/commands/split.md:46-51`).
- `plugin/crew/hooks/scripts/crew_standards.py:828-859`: `metric(root, record, today)`. It sets
  `path = os.path.join(root, ".crew", "metrics.md")` (`:831`) and reads it with `_read_bytes`. Under
  `--record` it runs `os.makedirs` and opens the same path in append mode (`:852-856`), so a lane
  creates and writes its own copy.
- `plugin/crew/hooks/scripts/crew_status.py:179-185`: `_metrics_line` loops
  `("metrics.jsonl", "metrics.md")` over `os.path.join(root, ".crew", name)`. It is called from
  `collect` at `crew_status.py:230`.
- `plugin/crew/hooks/scripts/crew_migrate.py:507` and `plugin/crew/hooks/scripts/crew_metrics.py:139`
  are out of scope (Exclusions).
- `plugin/crew/commands/review.md:527` (step 6, "Append the result to `.crew/metrics.md`") and `:541`
  are the prose writer. L-0578's branch already rewrites both to name the main checkout's file
  (`git -C /repos/personal/uca-l0578 diff origin/main...HEAD -- plugin/crew/commands/review.md`), so
  they are excluded here.
- L-0578's branch also rewrites `plugin/crew/README.md:739` (to "the main checkout's, also from a
  linked worktree") and `:793` (to "Written by `review_run.py` ... in the main checkout"). Those are
  the same two README lines this ticket's docs step names: a known merge point with L-0578.

Sibling tickets in this workflow: L-0583 (direction only) backfills rows into "the main checkout's
`.crew/metrics.md`" and depends on this ticket for the target; it is expected to call
`crew_common.metrics_md_path` and touch none of this ticket's files. L-0587 touches only the shell
scripts, a new `scripts/_test/shellcheck-directives.py`, the marketplace workflow, `.crew/verify.json`
rule 3, CHANGELOG and README (its spec's Touch). The shared files are `.crew/verify.json` (different
rules) and `CHANGELOG.md`, which merge as text. Measured 2026-10-02 against the lanes named in the
workflow's AUTHORITY (`git diff --name-only origin/main...HEAD` in each worktree): none changes
`crew_common.py`, `crew_standards.py`, `crew_status.py`, `test_worktree_config.py`, `test_status.py`,
`status.md` or `split.md`. T-0049 changes `crew_state.py` only at `AUTONOMOUS_STOPS` (`:1082`), not
`read_metrics`. `.crew/verify.json` and `plugin/crew/README.md` are changed by most lanes and are
text merges at land.

The resolver already exists:
- `plugin/crew/hooks/scripts/crew_common.py:129-148`: `_main_checkout(root)` returns
  `(main_root | None, problem)`. If `.git` is not a file there is no subprocess and the result is
  `(None, "")`. Otherwise it runs `git_out(root, "rev-parse", "--git-dir", "--git-common-dir")`
  (`crew_common.py:51`, which returns None on any failure). Anything other than exactly two lines
  gives `problem` = "this looks like a linked worktree, but git could not name its main checkout". A
  submodule (`git-dir == common-dir`) or a bare common dir (basename not `.git`) gives `(None, "")`.
- `plugin/crew/hooks/scripts/crew_common.py:96-126`: `repo_config_dir` is the T-0088 consumer of the
  same resolver, and it keeps `SOURCE_UNKNOWN` as its own value (`:118-119`).
- L-0578 (not merged) adopted it: `/repos/personal/uca-l0578/plugin/crew/hooks/scripts/review_metrics.py:89-96`
  `metrics_path(root)` returns `(None, problem)` on problem, and otherwise
  `os.path.join(main_root or root, ".crew", "metrics.md")`.

Guards this change must keep green:
- `plugin/crew/tests/test_worktree_config.py:199-224` `ALLOWED` and `:263`
  `test_no_module_reads_repo_config_outside_the_resolver`. `crew_status.py` is allowed exactly 1 site
  (`:219`, "the metrics file `.crew/<metrics name>`"). The site counter (`:242-260`) counts every
  `os.path.join(..., ".crew", <non-constant>)`, so routing `_metrics_line` through the resolver
  changes that count to 0, and the entry must go.
- `plugin/crew/tests/test_status.py:84-94` `test_status_output_fits_forty_lines_on_a_busy_repo`
  asserts at most 40 lines.
- `plugin/crew/tests/test_crew_standards.py:645-705` and `plugin/crew/tests/test_crew_state.py:96-200`
  write `metrics.md` under a plain `tmp_path`, which has no `.git`. That keeps the `(None, "")` "own"
  path, so these tests are unchanged.

Fixtures and sabotage to reuse:
- `plugin/crew/tests/test_worktree_config.py:38-45` `_lane` (a `make_repo` main and
  `git worktree add`), and `:114-122` (`monkeypatch.setattr(crew_common, "git_out", lambda *a: None)`
  for the git-cannot-answer case).
- `plugin/crew/tests/sabotage_limit_worktree.py:26-123` `LIMIT_WORKTREE_MUTATIONS` holds the T-0088
  resolver mutations. It is already imported by `plugin/crew/tests/sabotage.py:83`.
- `.crew/verify.json` rule 34 (`:359-361`) covers `crew_common.py` and `test_worktree_config.py`.
  Rule 8 covers `crew_state.py`, rule 37 covers `crew_standards.py`, and rule 43 covers
  `crew_status.py`.

Problem measurement: `/repos/personal/uca-l0578/.work/tickets/L-0578/spec.md:25` records "162 ledger
rounds, 59 scored rows in the main file, 25 more stranded in lane worktrees, 27 of 49 tickets with no
row anywhere". `/repos/personal/uca-l0578/.work/tickets/L-0578/notes.md:9` records "root fallback
recreates stranded rows". On this host, 17 `/repos/personal/uca-*/.crew/metrics.md` files exist
(measured 2026-10-02 by `ls`).

External (git):
- git-rev-parse(1), https://git-scm.com/docs/git-rev-parse: `--git-common-dir` is documented as "Show
  `$GIT_COMMON_DIR` if defined, else `$GIT_DIR`". For `--git-dir`: "The path shown, when relative, is
  relative to the current working directory", and outside a repository it will "print a message to
  stderr and exit with nonzero status".
- git-worktree(1) DETAILS, https://git-scm.com/docs/git-worktree: "Within a linked worktree, `$GIT_DIR`
  is set to point to this private directory ... and `$GIT_COMMON_DIR` is set to point back to the main
  worktree's `$GIT_DIR` (e.g. `/path/main/.git`). These settings are made in a `.git` file located at
  the top directory of the linked worktree."
- Measured on this host with git 2.53.0 (2026-10-02, throwaway repo under `/root/crew-tmp/l-0582`). A
  linked worktree printed `<main>/.git/worktrees/wt` and `<main>/.git`, both absolute. The main
  checkout printed `.git` and `.git`, both relative. A `.git` file holding `gitdir: /nonexistent/x`
  printed `fatal: not a git repository: /nonexistent/x` with rc=128. `_main_checkout` handles all three
  shapes as written.

## Unknowns

- **"Could-not-tell outside git" (seed wording).** Settled in this spec. A directory with no `.git`
  entry is not a linked worktree by construction (`crew_common.py:139-140`), so it reads its own
  `.crew/`. That matches T-0088 config resolution and L-0578's writer, and it is pinned by a must-find
  test. Could-not-tell is reachable only where a `.git` *file* exists and git cannot resolve it. Two
  tests cover it: a real fixture whose `.git` file points at a missing gitdir (git exits 128, as
  measured above), and `git_out` patched to return None, which stands for git not on PATH or a timeout.
  The direction's Q5 says "outside git or with git unable to answer", and the seed asks for no
  fallback. A plain non-git directory has nothing to fall back *from*, so this reading drops nothing.
- **L-0578 lands before or after this ticket.** Resolved at implement and at land by re-checking
  `git ls-tree origin/main plugin/crew/hooks/scripts/review_metrics.py`. The new lint
  (`test_no_module_opens_metrics_outside_the_resolver`) carries an `ALLOWED` entry for
  `review_metrics.py` that is skipped while the file is absent, so it passes in either order. Making
  `review_metrics.metrics_path` delegate to the shared resolver is a harness edit. It goes in the
  tooling PR if L-0578 has landed by then, and otherwise in L-0578's own follow-up. This is a known
  merge point of one function.
- **The `metrics.jsonl` reader/writer asymmetry.** After this ticket, `/crew:status` reads the main
  checkout's `metrics.jsonl`, while `crew_metrics.record` (run by `/crew:done`) still writes `root`'s.
  This is accepted as risk, because the direction settled the reader side as one loop. It must not
  become a new silent drop: before this ticket a lane's own `metrics.jsonl` was what its status line
  counted, and after it that file is ignored. So the stranded-copy note covers BOTH names: a lane's
  own `.crew/metrics.jsonl` and `.crew/metrics.md`, each named as not counted when present (acceptance
  checks the jsonl case). A candidate follow-up L- ticket for the jsonl writer is to be filed at land
  with a Kanban card, numbered from INDEX.md at that time.
- **The README lines L-0578 also rewrites.** Resolved at implement by re-checking origin/main. If
  L-0578 has landed, its `:739` wording already names the main checkout and is kept; this ticket adds
  only the `crew_standards.py metric` could-not-tell clause to the `:793` row. If it has not, this
  ticket makes the minimal edit to both, and whichever lands second resolves the text merge.
- **40-line cap.** Adding the stranded-copy line could push a busy repo over 40. Resolved in the plan
  by appending the stranded note to the existing `metrics` line when it fits the line budget, and
  proven by the existing `test_status_output_fits_forty_lines_on_a_busy_repo` plus a new linked-worktree
  case.
- **Version number.** This ticket claims none. REPO-03 (`.crew/standards.md:73-80`) puts the bump on
  the land branch after the review receipt. At land, take the next free number after re-checking
  origin/main and every `uca-*/plugin/crew/.claude-plugin/plugin.json`. 1.0.123 is next free as of
  2026-10-02. The tooling PR needs its own bump.

## Touch

Feature PR (L-0582):
- `plugin/crew/hooks/scripts/crew_common.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_standards.py`
- `plugin/crew/hooks/scripts/crew_status.py`
- `plugin/crew/tests/test_metrics_location.py` - new, the must-find, could-not-tell and lint tests
- `plugin/crew/tests/test_worktree_config.py` - drop the crew_status ALLOWED entry whose site moves
- `plugin/crew/tests/test_status.py` - only if the forty-line case needs a linked-worktree variant
- `.crew/verify.json` - rule 34 paths and run gain the new test file
- `plugin/crew/commands/status.md` - the metrics row: main checkout source, could not tell, stranded note
- `plugin/crew/commands/split.md` - health.rate reads the main checkout's file
- `plugin/crew/README.md` - the review metrics paragraph and the standards metric row
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/codemap/**` - refresh artifact, re-anchor
- `docs/diagrams/**` - refresh artifact, process-crew-brief status lines move
- `.claude/rules/**` - refresh artifact, regenerated
- `graphify-out/**` - refresh artifact, graphify update
- `.work/tickets/L-0582/**`
- `.work/INDEX.md`

Tooling PR (next free L- number, split under the standing check-tooling-pr.py rule):
- `plugin/crew/tests/sabotage_limit_worktree.py` - the L-0582 resolver and caller mutations
- `plugin/crew/hooks/scripts/review_metrics.py` - only if L-0578 has landed, delegate metrics_path

Docs checked and unchanged, with reasons. `plugin/crew/CONFIG.md:326,338`,
`plugin/crew/commands/autopilot.md:102`, `README.md:267,554`, `plugin/README.md:43,330` and
`plugin/UPDATE.md:39,326` name `.crew/metrics.md` only as the `rewrite-metrics` authority category or
as a history pointer, and say nothing about which checkout holds it.
`plugin/crew/skills/crew-setup/SKILL.md:88` describes the initial header row, and
`plugin/crew/skills/crew-qa-standards/references/review.md:59` describes where savings are claimed
from. `plugin/crew/README.md:567` says `/crew:review` logs a missing named agent to `.crew/metrics.md`
(the review writer's prose, L-0578's); `plugin/crew/README.md:927`, `plugin/crew/commands/migrate.md:48,63`
and `plugin/crew/README.md:2748` describe the one-time migration, which is excluded;
`plugin/crew/commands/review.md:229` is about the reviewer cell's identity, not the file's location;
`plugin/crew/skills/crew-setup/SKILL.md:409` and `plugin/crew/skills/crew-setup/global-config.md:112`
list it as a file or an authority category; and `docs/guides/crew/src/daily-workflow.md:95` describes
`/crew:done`'s `metrics.jsonl` row, whose writer is excluded. `docs/guides/crew/src/*.md` name only `metrics.jsonl` (`quickstart.md:98`,
`daily-workflow.md:95`), and the crew, configuration and autopilot guides (T-0048, T-0054) have not
landed. So guides: none, because no guide describes where `metrics.md` is read from. The PR body
says so.

## Acceptance checks

- [ ] `test_metrics_location.py::test_resolver_linked_worktree_names_main_checkout`: run from a real
  `git worktree add` lane, `crew_common.metrics_crew_dir` returns `<main>/.crew` and no problem
  (verify.json rule 34).
- [ ] `test_metrics_location.py::test_resolver_main_checkout_names_its_own`,
  `::test_resolver_plain_directory_names_its_own`, and `::test_resolver_submodule_names_its_own` (rule
  34).
- [ ] `test_metrics_location.py::test_resolver_unresolvable_git_file_is_could_not_tell`, with a real
  `.git` file pointing at a missing gitdir, and `::test_resolver_git_unanswering_is_could_not_tell`,
  with `git_out` returning None. Both return no path and a non-empty problem (rule 34).
- [ ] `test_metrics_location.py::test_read_metrics_from_linked_worktree_finds_main_rows`: main holds
  rows, and the lane's own `.crew/metrics.md` holds a decoy with different counts. The result is the
  main rows' tickets, findings and rate (rules 34 and 8).
- [ ] `test_metrics_location.py::test_read_metrics_from_main_checkout_finds_its_rows` (rules 34 and 8).
- [ ] `test_metrics_location.py::test_read_metrics_could_not_tell_is_not_no_data`: the verdict starts
  `could not tell:`, `rate` is None, the decoy is not read, and `evaluate_triggers` fires neither health
  trigger (rules 34 and 8).
- [ ] `test_metrics_location.py::test_standards_metric_from_linked_worktree_reads_main` and
  `::test_standards_metric_record_from_linked_worktree_appends_to_main`: after `--record` the main file
  gains one line, and the lane's `.crew/` gains no `metrics.md` (rules 34 and 37).
- [ ] `test_metrics_location.py::test_standards_metric_could_not_tell_exits_1_and_writes_nothing`:
  exit 1, the line names the problem, and both the lane and main files are byte-identical before and
  after `--record` (rules 34 and 37).
- [ ] `test_metrics_location.py::test_status_metrics_line_from_linked_worktree_counts_main` (main's
  rows are counted, the decoy is not), `::test_status_metrics_line_could_not_tell`
  (`metrics  could not tell (<problem>)`), `::test_status_names_stranded_lane_copy_as_not_counted`,
  parametrized over `metrics.md` and `metrics.jsonl` (the lane's own file's path and `not counted`
  appear on the one `metrics` line), and `::test_status_has_no_stranded_note_without_a_lane_copy`
  (the main checkout, and a lane with no own file, print no `not counted`) (rules 34 and 43).
- [ ] `test_metrics_location.py::test_no_module_opens_metrics_outside_the_resolver`: an AST lint, so
  that no `os.path.join(..., ".crew", "metrics.md" | "metrics.jsonl")` exists outside `crew_common.py`
  except in the listed `ALLOWED` files with exact counts. Measured at 8d84786d: `crew_migrate.py` 2
  (`:507`, `:511`) and `crew_metrics.py` 1 (`:139`), plus `review_metrics.py` 1 while that file
  exists. `crew_state.py:314` and `crew_standards.py:831` are the sites this ticket removes. A
  non-constant second argument is not counted, because at 8d84786d it also matches unrelated markers
  (`crew_autocycle.py:302`, `crew_config.py:1161`, `crew_config_menu.py:586`, `crew_migrate.py:515`).
  The variable join in `crew_status.py:181` is already counted by `test_worktree_config.py`'s lint.
  `crew_common.py` is skipped by this new lint only; `test_worktree_config.py`'s lint still walks it,
  so every new join in `crew_common.py` keeps `".crew"` as its LAST argument (`own =
  os.path.join(root, ".crew")`, then `os.path.join(own, name)`), the shape `repo_config_dir` already
  uses, and adds no site there. Rule 34.
- [ ] The existing `test_worktree_config.py::test_no_module_reads_repo_config_outside_the_resolver`
  stays green with the `crew_status.py` entry removed (rule 34).
- [ ] The existing suites stay green: rule 8 (`test_crew_state.py` and peers), rule 37
  (`test_crew_standards.py` and peers), rule 43 (`test_status.py` including the 40-line case), and rule
  34. All run under heavy-run.
- [ ] Sabotage, recorded in notes.md for the feature PR and landed as entries in the tooling PR. Each
  mutation turns its named test RED, and restoring it turns it green:
  (a) the resolver returns `root/.crew` for a linked worktree, which turns
  `test_resolver_linked_worktree_names_main_checkout` and the four caller linked-worktree must-find
  tests (read_metrics, standards metric read, standards metric record, status line) RED;
  (b) a problem collapses to `root/.crew` with no problem, which turns both resolver could-not-tell
  tests and the three caller could-not-tell tests RED;
  (c) `read_metrics` maps a problem to the `no data` verdict, which turns
  `test_read_metrics_could_not_tell_is_not_no_data` RED;
  (d) `metric --record` writes on a problem, which turns
  `test_standards_metric_could_not_tell_exits_1_and_writes_nothing` RED;
  (e) the stranded-copy note is dropped, which turns both cases of
  `test_status_names_stranded_lane_copy_as_not_counted` RED.
- [ ] `python3 scripts/check-marketplace.py` exits 0 on the land branch after the bump, and
  `python3 scripts/check-tooling-pr.py` exits 0 on the feature branch, which holds no harness path.
- [ ] `python3 /root/crew-tmp/ruff-no-new.py <worktree>` exits 0, and pylint passes as CI runs it on the
  changed modules plus the modules they import.
- [ ] The docs listed in Touch describe the new behaviour, and the PR body names the docs checked and
  left unchanged with reasons.
