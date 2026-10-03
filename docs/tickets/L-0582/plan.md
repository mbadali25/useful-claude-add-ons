# L-0582 plan            spec: .work/tickets/L-0582/spec.md

Anchor: origin/main `8d84786d` (crew 1.0.115). Worktree: `/repos/personal/uca-l0582` on branch
`L-0582-build`, created off origin/main. Copy `.work/tickets/L-0582/` into it and check with `cmp`.
Copy the main checkout's `.crew/config.json` into it (`scope.allowCliApproval` true), and keep all
crew bookkeeping untracked. Run every pytest under
`TMPDIR=/root/crew-tmp/l-0582 /root/crew-tmp/heavy-run`, one at a time, after `free -g`.

Second opinion (plan step 3): skipped. The design reuses the T-0088 resolver unchanged, and direction
Option 1 already compares the three alternatives. This is a single opinion, and review round 1 is the
first independent read.

### Step 1: Failing tests first
Files: create `plugin/crew/tests/test_metrics_location.py`
Test: `python3 -m pytest plugin/crew/tests/test_metrics_location.py -q` must be RED. Expect
ImportError/AttributeError on `crew_common.metrics_crew_dir` and assertion failures for each caller.
Paste the failure summary into notes.md.
Risk: tests that pass against the old code would prove nothing. The decoy file in the lane is what
makes the linked-worktree tests bite.
Standards: GEN-04 (a control that fails in both directions), GEN-01 (could-not-tell has its own
assertion, never "no data"), PYTHON-01 (every fixture write uses `encoding="utf-8"`).
- [ ] Module docstring: a throwaway repo under `tmp_path`, a real `git worktree add`, and nothing that
      reads the real repo's `.crew/`.
- [ ] Fixtures. Use `_lane(tmp_path)`, which follows `test_worktree_config.py:38-45`:
      `scope_fixtures.make_repo(tmp_path, mode=None, name="main")` plus
      `review_fixtures.git(main, "worktree", "add", "-q", "-b", "lane", str(tmp_path / "wt"))`.
      `_rows(crew_dir, rows)` writes a header and separator plus
      `| 2026-10-02 | <t> | <reviewer> | <b> | <f> |` lines. MAIN gets `[("T-1", 2, 1), ("T-2", 0, 1)]`
      and the lane DECOY gets `[("T-9", 9, 9)]`.
- [ ] Resolver tests. `test_resolver_linked_worktree_names_main_checkout`: `metrics_crew_dir(str(wt))`
      equals `(os.path.join(realpath(main), ".crew"), "")`. Also
      `test_resolver_main_checkout_names_its_own`, `test_resolver_plain_directory_names_its_own`
      (tmp dir, no `.git`), and `test_resolver_submodule_names_its_own`, which builds the fixture the
      way `test_worktree_config.py:104-111` does.
      `test_resolver_unresolvable_git_file_is_could_not_tell` writes `.git` containing
      `gitdir: <tmp_path>/missing` and expects `(None, <non-empty>)`.
      `test_resolver_git_unanswering_is_could_not_tell` sets
      `monkeypatch.setattr(crew_common, "git_out", lambda *a: None)` on a real lane and expects
      `(None, <non-empty>)`.
- [ ] read_metrics. `test_read_metrics_from_linked_worktree_finds_main_rows` expects
      `(tickets, findings, rate) == (2, 4, 2.0)`; the decoy would give `(1, 18, 18.0)`.
      `test_read_metrics_from_main_checkout_finds_its_rows` expects the same triple from `str(main)`.
      `test_read_metrics_could_not_tell_is_not_no_data` patches `git_out` to None, then expects the
      verdict to start with `"could not tell: "`, `rate is None`, `tickets == 0`, and
      `crew_state.evaluate_triggers({"health": got})` to contain neither `reviewNotWorking` nor
      `ticketsTooLarge`.
- [ ] crew_standards.metric. `test_standards_metric_from_linked_worktree_reads_main`: `cs.metric(str(wt))`
      returns 0, and its header line names the main checkout's path.
      `test_standards_metric_record_from_linked_worktree_appends_to_main`: with `record=True,
      today="2026-10-02"`, the main file's last line starts with `standards-metric 2026-10-02:`, the
      lane decoy is byte-identical, and in a second lane with no `.crew/`, `wt/.crew/metrics.md` does
      not exist afterwards.
      `test_standards_metric_could_not_tell_exits_1_and_writes_nothing`: patch `git_out`, call
      `record=True`, and expect code 1, a line containing `could not tell`, and both files
      byte-identical.
- [ ] crew_status. `test_status_metrics_line_from_linked_worktree_counts_main`: `_metrics_line(str(wt))`
      reports MAIN's non-blank row count and names the main checkout.
      `test_status_metrics_line_could_not_tell` expects `metrics  could not tell (` as the prefix.
      `test_status_names_stranded_lane_copy_as_not_counted`, parametrized over `metrics.md` and
      `metrics.jsonl`, writes that one file into the lane's own `.crew/` and expects the single
      `metrics` line to contain its path and `not counted`.
      `test_status_has_no_stranded_note_without_a_lane_copy` covers the main checkout and a lane with no
      own file: no `not counted` anywhere in `_metrics_line`'s output.
- [ ] Lint. `test_no_module_opens_metrics_outside_the_resolver` reuses the `_repo_config_sites` walk
      shape from `test_worktree_config.py:242-260`. It counts `os.path.join` calls in which a `".crew"`
      argument is immediately followed by the constant `"metrics.md"` or `"metrics.jsonl"`, in every
      `hooks/scripts/*.py` except `crew_common.py`. A non-constant follower is NOT counted, since it
      matches unrelated markers: measured at 8d84786d, these are `crew_autocycle.py:302`,
      `crew_config.py:1161`, `crew_config_menu.py:586` and `crew_migrate.py:515`.
      `ALLOWED = {"crew_migrate.py": (2, "one-time migration of the checkout it is pointed at"),
      "crew_metrics.py": (1, "metrics.jsonl writer, out of L-0582 scope"),
      "review_metrics.py": (1, "L-0578 writer, delegates in the tooling PR")}`. An ALLOWED file absent
      from `SCRIPTS` is skipped, so L-0578 and L-0582 may land in either order. These counts were
      measured by AST at 8d84786d. Re-measure after merging origin/main and record the result in
      notes.md. Before the fix, `crew_state.py:314` and `crew_standards.py:831` make the lint RED.

### Step 2: The shared resolver in crew_common
Files: `plugin/crew/hooks/scripts/crew_common.py`
Where: after `_main_checkout` (crew_common.py lines 129-148 at 8d84786d).
Test: `pytest plugin/crew/tests/test_metrics_location.py -k resolver -q` is green, and
`pytest plugin/crew/tests/test_worktree_config.py -q` stays green
Risk: med. Every caller trusts this one answer, and a wrong `main_root or root` sends rows back to the
lane.
Standards: GEN-01, GEN-05 (a narrow allowlist of shapes; everything else is could-not-tell), REPO-01
(identity canonicalised via `realpath`, which `_main_checkout` already applies), PYTHON-13.
- [ ] `def metrics_crew_dir(root)`, with the docstring "(crew_dir, problem)". It returns the `.crew/`
      directory that holds review metrics for `root`: the main checkout's for a linked worktree, and
      `root`'s own otherwise. `problem` is non-empty only when git could not tell, and `crew_dir` is then
      None. Callers must not fall back. Body: `main_root, problem = _main_checkout(root)`; `if problem:
      return None, problem`; `return os.path.join(main_root or root, ".crew"), ""`.
- [ ] `def metrics_md_path(root)` returns `(path, problem)` and joins `"metrics.md"` onto
      `metrics_crew_dir`.
- [ ] `def stranded_metrics_copies(root)` returns a tuple of the worktree's own `.crew/metrics.jsonl`
      and `.crew/metrics.md` paths, in that order, that `os.path.lexists`, when `root` is a linked
      worktree (main_root not None, no problem), and `()` otherwise. Both names, because after this
      ticket a lane's own `metrics.jsonl` (which `crew_metrics.record` still writes) is no longer what
      the status line counts (spec Unknowns).
- [ ] Add module constants `METRICS_NAMES = ("metrics.jsonl", "metrics.md")` and
      `METRICS_MD = "metrics.md"`. Every join keeps `".crew"` as its LAST argument
      (`own = os.path.join(root, ".crew")`, then `os.path.join(own, name)`), the shape `repo_config_dir`
      uses. crew_common is skipped by the new lint only; `test_worktree_config.py`'s
      `_repo_config_sites` still walks it and counts a `".crew"` followed by any non-config argument,
      so this shape is what keeps crew_common at zero sites there. Run `test_worktree_config.py` to
      prove it.

### Step 3: read_metrics routes through it
Files: `plugin/crew/hooks/scripts/crew_state.py`
Where: `read_metrics`, crew_state.py lines 295-316 at 8d84786d (docstring and the `read_text` line).
Test: `pytest plugin/crew/tests/test_metrics_location.py -k read_metrics -q` plus verify.json rule 8's
run line
Risk: med. A could-not-tell that reads as `no data` hides the problem, and the evaluate_triggers
assertion covers the trigger side.
Standards: GEN-01, GEN-07 (`health` keeps its four keys, so `/crew:split` and `evaluate_triggers` read
the same shape).
- [ ] `path, problem = crew_common.metrics_md_path(root)`. If there is a problem, return
      `{"tickets": 0, "findings": 0, "rate": None, "verdict": f"could not tell: {problem}"}`. Otherwise
      `text = read_text(path)`.
- [ ] Docstring: one paragraph naming the main checkout resolution and the could-not-tell verdict.

### Step 4: crew_standards.metric reads and records the resolved file
Files: `plugin/crew/hooks/scripts/crew_standards.py`
Where: the imports (crew_standards.py lines 59-70; add `import crew_common`) and `metric` (lines 828-859).
Test: `pytest plugin/crew/tests/test_metrics_location.py -k standards_metric -q` plus verify.json rule
37's run line (`test_crew_standards.py` `test_metric_*` unchanged, since tmp_path has no `.git`)
Risk: med. `--record` is a writer, and creating the lane's `.crew/metrics.md` is the bug being fixed.
Standards: GEN-01, GEN-03 (an irreversible append happens only once the target is known), PYTHON-01
(the existing `open(..., "a", encoding="utf-8", newline="\n")` is kept).
- [ ] `path, problem = crew_common.metrics_md_path(root)`. If there is a problem, return
      `1, [f"standards-metric: could not tell which .crew/metrics.md to use ({problem}); nothing read, nothing recorded"]`
      before any read or `os.makedirs`.
- [ ] The header and recorded lines name `path` instead of the literal `.crew/metrics.md`, so a lane run
      shows the main checkout's file. The `_read_bytes` error line names `path` too.
- [ ] Docstring: the resolution, and that `--record` writes nothing on could-not-tell.

### Step 5: crew_status._metrics_line and the stranded note
Files: `plugin/crew/hooks/scripts/crew_status.py`, `plugin/crew/tests/test_worktree_config.py`, `plugin/crew/tests/test_status.py`
Where: crew_status.py `_metrics_line` (lines 179-185); test_worktree_config.py line 219 (remove the
crew_status.py ALLOWED entry); test_status.py only if the forty-line check below fails.
Test: `pytest plugin/crew/tests/test_metrics_location.py -k status -q`,
`pytest plugin/crew/tests/test_worktree_config.py -q`, and verify.json rule 43's run line
(`test_status.py` including `test_status_output_fits_forty_lines_on_a_busy_repo`)
Risk: med. The status output is capped at 40 lines, and a second metrics line could clip another line.
Standards: GEN-01, PYTHON-03 (each output line is one line, so the problem goes through
`_one_line`-style flattening of newlines).
- [ ] `crew_dir, problem = crew_common.metrics_crew_dir(root)`. If there is a problem, return
      `metrics  could not tell (<problem with newlines replaced by spaces>)`. Otherwise loop
      `crew_common.METRICS_NAMES` over `os.path.join(crew_dir, name)`, labelling the line with the
      main checkout's path when `os.path.normcase(os.path.realpath(crew_dir))` differs from the same
      of `os.path.join(root, ".crew")`.
- [ ] `stranded = crew_common.stranded_metrics_copies(root)`. When it is non-empty, add
      `; this worktree's own <paths joined by ", "> not counted` to the same line, so the line count is
      unchanged. No ticket number in user-facing output.
- [ ] Remove `"crew_status.py": (1, ...)` from `test_worktree_config.py` ALLOWED, because its only site
      moved into crew_common.
- [ ] Run the forty-line test. If it fails, add a linked-worktree variant there and fix the line
      budget rather than the test.

### Step 6: Register the new test file
Files: `.crew/verify.json`
Where: rule 34 (verify.json lines 359-361 at 8d84786d).
Test: `python3 scripts/check-marketplace.py`, and `test_verify_rule_paths_*` if present, via the rule 9
full suite at gate
Risk: low. Without this, an unregistered test is never run by the per-path gate.
Standards: GEN-11 (the named requirement holds on every path).
- [ ] Add `plugin/crew/tests/test_metrics_location.py` to rule 34's `paths` and `run`, and add
      `crew_state.py`, `crew_standards.py` and `crew_status.py` to its paths. Re-measure `seconds`
      under heavy-run and put the measurement and the date in `why`.

### Step 7: Sabotage, run in the feature lane and recorded
Files: none committed in the feature PR. notes.md under `.work/tickets/L-0582/`.
Test: the five entries are not in any `sabotage*.py` until the tooling PR, so in this lane apply each
mutation by hand (one at a time, a `str.replace` whose `find` occurs exactly once, computed into a
variable before the file is opened for writing), run its named tests with
`TMPDIR=/root/crew-tmp/l-0582 /root/crew-tmp/heavy-run python3 -m pytest plugin/crew/tests/test_metrics_location.py -q`,
then restore with `git checkout -- <file>` and confirm `git diff --quiet` before the next one.
Risk: a mutation that stays green means its test does not bite. Fix the test, never the mutation.
Standards: GEN-04.
- [ ] (a) `crew_common.metrics_crew_dir`: `os.path.join(main_root or root, ".crew")` becomes
      `os.path.join(root, ".crew")`. Expect RED in
      `test_resolver_linked_worktree_names_main_checkout`,
      `test_read_metrics_from_linked_worktree_finds_main_rows`,
      `test_standards_metric_from_linked_worktree_reads_main`,
      `test_standards_metric_record_from_linked_worktree_appends_to_main` and
      `test_status_metrics_line_from_linked_worktree_counts_main`.
- [ ] (b) `if problem:\n        return None, problem` becomes
      `if problem:\n        return os.path.join(root, ".crew"), ""`. Expect RED in both resolver
      could-not-tell tests and the three caller could-not-tell tests.
- [ ] (c) crew_state: `f"could not tell: {problem}"` becomes `"no data"`. Expect RED in
      `test_read_metrics_could_not_tell_is_not_no_data`.
- [ ] (d) crew_standards: the `if problem:` return becomes `if False:`. Expect RED in
      `test_standards_metric_could_not_tell_exits_1_and_writes_nothing`.
- [ ] (e) crew_status: `if stranded:` becomes `if False:`. Expect RED in both cases of
      `test_status_names_stranded_lane_copy_as_not_counted`.
- [ ] Record each RED count and the restored green verbatim in notes.md.

### Step 8: Docs
Files: `plugin/crew/commands/status.md`, `plugin/crew/commands/split.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`
Where: status.md line 35 (the metrics row), split.md line 46, README.md lines 739 and 793, and
BUDGETS.md's re-measured line count.
Test: rule 2 (`python3 scripts/check-marketplace.py`, `python3 scripts/_test/self-claims.py`,
`python3 scripts/sync-updates.py --check`)
Risk: low.
Standards: GEN-09 (what the change says is true at this commit).
- [ ] status.md metrics row: "`.crew/metrics.jsonl`, else `.crew/metrics.md`, in the main checkout's
      `.crew/` when run from a linked worktree; `could not tell (<why>)` when git cannot name it; a lane's
      own stranded copy is named as not counted". The "unknown" column: git cannot name the main
      checkout.
- [ ] split.md:46: `.crew/metrics.md` (the main checkout's, from a linked worktree).
- [ ] README.md first: `git ls-tree origin/main plugin/crew/hooks/scripts/review_metrics.py`. If
      L-0578 has landed, keep its line 739 wording (it already says "the main checkout's, also from a
      linked worktree") and add only the `crew_standards.py metric` clause below to its line 793 row.
      If it has not: line 739 "the main checkout's `.crew/metrics.md`, also from a lane worktree", and
      line 793 `crew_standards.py metric` reads and `--record` appends the main checkout's file, and
      exits 1 without writing when git cannot tell. Record which branch was taken in notes.md.

### Step 9: Gate, review, then land bookkeeping
Files:
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `.crew/codemap/**`
- `docs/diagrams/**`
- `.claude/rules/**`
- `graphify-out/**`
- `.work/INDEX.md`
Where: the version files on the land branch only, per REPO-03; the last four are refresh artifacts.
Test: `python3 scripts/check-marketplace.py`, `python3 scripts/check-tooling-pr.py` (expect 0: no
harness path), `python3 /root/crew-tmp/ruff-no-new.py /repos/personal/uca-l0582` exiting 0, pylint as CI
runs it on crew_common, crew_state, crew_standards and crew_status plus their imported modules,
verify-gate under heavy-run, and the required `crew-shell-matrix (windows-latest)` check
Risk: med. Version collisions with other lanes.
Standards: REPO-03, GEN-12 (verification evidence at the final HEAD).
- [ ] Before bumping, re-check origin/main and every `/repos/personal/uca-*/plugin/crew/.claude-plugin/plugin.json`,
      take the next free number (1.0.123 as of 2026-10-02), and report the claim.
- [ ] CHANGELOG entry: `### Fixed — crew 1.0.<n>: review metrics resolve the main checkout's .crew/
      from a linked worktree (L-0582)`, naming the could-not-tell behaviour, the stranded note, and
      "Docs: guides none - no guide describes where metrics.md is read from".
- [ ] Refresh: re-anchor `.crew/codemap/crew.md`, regenerate `.claude/rules`, refresh
      `docs/diagrams/process-crew-brief.mmd:268`'s crew_status line range, and run `graphify update .`
      once `~/.cache/graphify-rebuild.log` is quiet. All are in scope by standing rule, and the PR body
      says so.
- [ ] File the jsonl-writer follow-up (spec Unknowns) as the next free L- ticket with a Kanban card.

### Step 10: Tooling PR (next free L- number, after the feature PR lands)
Files: `plugin/crew/tests/sabotage_limit_worktree.py`, `plugin/crew/hooks/scripts/review_metrics.py`
Where: append to `LIMIT_WORKTREE_MUTATIONS` (sabotage_limit_worktree.py lines 26-123); review_metrics.py
`metrics_path` (lines 89-96 on L-0578's branch) only if L-0578 is on origin/main. No review.md edit:
L-0578 owns steps 6 and 8 (spec Exclusions).
Test: `python3 plugin/crew/tests/sabotage.py` (filtered to the new entries) all RED;
`pytest plugin/crew/tests/test_sabotage_harness.py -q`
(`test_every_shipped_anchor_is_present_in_its_target_exactly_once`); verify.json rules 34 and 35;
`check-tooling-pr.py` exits 0 (harness and ALONGSIDE paths only)
Risk: med. A sabotage `find` string that is not unique fails the harness anchor test.
Standards: GEN-04, REPO-03 (its own version bump at its land).
- [ ] Add the five step-7 mutations as tuples `(label, target, find, replace, test)`, with `find`
      strings copied from the merged feature code and checked unique.
- [ ] If L-0578 closed unmerged by then, file a follow-up L- ticket (next free number, Kanban card)
      for review.md steps 6 and 8, instead of editing them here.
- [ ] If `review_metrics.py` exists on origin/main: `metrics_path(root)` returns
      `crew_common.metrics_md_path(root)`, its own tests stay green, and the lint ALLOWED entry for it is
      removed (count 0).
