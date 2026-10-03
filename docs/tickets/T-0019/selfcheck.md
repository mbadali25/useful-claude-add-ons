# T-0019 self-check
<!-- stamp: bundle=2c9ed68077abadd7ab8be4f01baee2784c40e16944e7fc4189297a24b25ebee1 standards=664c6164d4c470821315df2c01f32a6f5fd197093ce9e837676bb7d6fe2ef804 base=f808e5f0344a5821ee3bc5fd17d08ced92d1bb37 -->

standards: 24 in sets GEN, PYTHON, REPO; overlay: present (.crew/standards.md); digest 664c6164

Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that
covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`
(the reason it does not apply to this change). Then run `crew_standards.py stamp`;
any later edit to the change needs a new stamp.

| ID | Status | Evidence or reason |
|---|---|---|
| GEN-01 | addressed | an INDEX that exists but cannot be read refuses (`_mint_taken` plugin/crew/hooks/scripts/crew_ticket.py:1049-1052; `_mint_indexed` :1168 returns None = could not tell, and the folder is kept): test_mint_unreadable_index_refuses, test_mint_create_that_raises_after_writing_the_row_keeps_the_ticket; a tracker that `could not tell` refuses before mkdir (`_mint_gate` :1079): test_mint_refuses_under_a_delegated_or_unknown_tracker |
| GEN-02 | addressed | direction.md via temp + fsync + os.replace (plugin/crew/hooks/scripts/crew_ticket.py:1103-1125): test_mint_half_written_direction_leaves_no_ticket; INDEX writes only through crew_tracker under `.work/INDEX.md.lock` across create and move (:1245): test_index_rows_intact_after_concurrent_slow_mints, test_mint_create_runs_under_the_index_lock |
| GEN-03 | addressed | the folder claim is an exclusive os.mkdir after the gate, title and status checks (plugin/crew/hooks/scripts/crew_ticket.py:1283-1293); assign checks staging path, armed state and every section before the one mint call (:1356-1395): test_assign_refuses_missing_section_and_mints_nothing, test_assign_refuses_when_not_armed |
| GEN-04 | addressed | 27 ASSIGN_MUTATIONS in plugin/crew/tests/sabotage_autopilot.py, each red on its named test (SABOTAGE SUITE: PASS at 88bbf678), including the allowing-direction origin-rule mutation -> test_assigned_ticket_self_approved_under_self / test_origin_line_changes_no_policy |
| GEN-05 | addressed | tracker kinds allowlisted to files/obsidian (`_mint_gate` plugin/crew/hooks/scripts/crew_ticket.py:1079), statuses to MINT_STATUSES, risk to low/med/high (anything else written high, with a warning): test_mint_refuses_under_a_delegated_or_unknown_tracker, test_mint_rejects_unknown_status, test_assign_unknown_risk_is_high |
| GEN-06 | addressed | a title with a pipe character, a line break, empty or over 120 chars is refused before anything is claimed (`_mint_title_problem` plugin/crew/hooks/scripts/crew_ticket.py:1092): test_mint_rejects_bad_title; the work text never reaches a shell line - title and risk are read from the staging file, never argv: test_assign_cli_takes_no_title |
| GEN-07 | addressed | one staging-file contract (`check_direction` plugin/crew/hooks/scripts/crew_ticket.py:1316) read by assign, the same `/crew:brainstorm` sections; mint's return dict {ticket, folder, status, warnings} is the one CLI line: test_assign_mints_exactly_one, test_mint_cli_prints_ticket |
| GEN-08 | addressed | paths built with os.path.join, realpath containment (plugin/crew/hooks/scripts/crew_ticket.py:1364-1371), `xb` binary write with explicit utf-8 encode; the Windows CI leg runs both suites (concurrency measured on Linux only, stated in the CHANGELOG) |
| GEN-09 | addressed | README, CONFIG.md, CHANGELOG and the crew code map say /crew:autopilot assign arrives with L-0611 and crew_ticket.py assign works from the command line since 1.0.157; maps re-anchored at e5820efc |
| GEN-10 | addressed | the tracker's lost-write window was measured (15 runs x 8 concurrent creates kept 103 of 120 rows, codemap crew.md tracker section) before mint took the INDEX lock; 8 concurrent mints then gave 8 distinct ids/folders/rows: test_concurrent_mints_distinct, test_index_rows_intact_after_concurrent_mints |
| GEN-11 | addressed | spec acceptance checks for mint and assign each map to a test in test_crew_ticket_mint.py / test_crew_autopilot_assign.py; the two router checks are struck to L-0611 in the spec, which was re-approved |
| GEN-12 | addressed | verify-gate --all and the full crew suite run at the final HEAD after the graph commit (/root/crew-tmp/t-0019/post/status); 27 mutations at 88bbf678, whose plugin tree equals the final one |
| PYTHON-01 | addressed | staging file and --direction-file read with encoding='utf-8-sig' (plugin/crew/hooks/scripts/crew_ticket.py:1377, :1417), direction written as explicit utf-8 bytes (:1108): test_assign_reads_a_bom_staging_file, test_mint_cli_direction_file_bom_is_not_carried |
| PYTHON-03 | addressed | the CLI prints one `ticket=<id>` (assign: `ticket=<id> risk=<r>`) line then one `warning:` line each; a title with a line break is refused: test_mint_cli_prints_ticket, test_assign_cli_prints_ticket_and_risk, test_mint_rejects_bad_title |
| PYTHON-04 | addressed | direction.md is replaced via os.replace (plugin/crew/hooks/scripts/crew_ticket.py:1116); INDEX is rewritten only by crew_tracker's own replace, under the lock |
| PYTHON-06 | n/a | mint and assign launch no child process; the only subprocess is the existing git helper (crew_ticket.py:203), unchanged |
| PYTHON-07 | addressed | the INDEX lock wait is bounded at _MINT_LOCK_WAIT = 30.0 s (plugin/crew/hooks/scripts/crew_ticket.py:1046) through crew_config_files.Lock; the id claim gives up after 20 attempts: test_mint_gives_up_after_max_attempts |
| PYTHON-08 | n/a | no child process is launched by this change |
| PYTHON-10 | n/a | mint and assign parse no JSON or TOML; tracker answers come back as crew_tracker report objects read through _mint_lines/_mint_failures |
| PYTHON-11 | addressed | the create call's try covers only `_mint_create`, and its failure is classified by `_mint_indexed` (row written or not, or could not tell) (plugin/crew/hooks/scripts/crew_ticket.py:1184-1213): test_mint_create_that_raises_leaves_no_ticket, test_mint_create_that_raises_after_writing_the_row_keeps_the_ticket |
| PYTHON-13 | addressed | the staging path and the file are both realpath'd before containment (plugin/crew/hooks/scripts/crew_ticket.py:1364-1371), so a symlink out of .work/autopilot/ is refused: test_assign_refuses_direction_file_outside_staging |
| REPO-01 | addressed | the ticket id is one past the highest T- number over folders AND every INDEX line's first T-<n>, claimed by exclusive mkdir: test_mint_never_takes_an_index_only_id, test_mint_skips_existing_folder, test_mint_moves_on_when_the_tracker_says_id_taken |
| REPO-02 | addressed | verify.json's autopilot rule maps crew_ticket.py and both new test files; check-tooling-pr.py OK (harness paths only, crew_autopilot.py/autopilot.md split to L-0611) |
| REPO-03 | addressed | crew 1.0.157 in plugin.json, marketplace.json and PLUGINS.md's claim, set as the last plugin commit e5820efc; CHANGELOG entry; BUDGETS.md re-measured (22,064/138); check-marketplace.py all checks passed |
