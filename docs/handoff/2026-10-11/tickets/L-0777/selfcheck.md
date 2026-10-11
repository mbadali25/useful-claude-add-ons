# L-0777 self-check
<!-- stamp: bundle=f875b6b4d688a6e17794566ff0538a500883054b4728076a171ff158da6fcd73 standards=2a02982acc8605a42efda8d9aeddcccbcc18a81e18d78b19dfbd5cade8a11c2f base=c972653ad1cd500a99c4355d34316135f6fad0df -->

standards: 24 in sets GEN, PYTHON, REPO; overlay: present (.crew/standards.md); digest 2a02982a

Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that
covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`
(the reason it does not apply to this change). Then run `crew_standards.py stamp`;
any later edit to the change needs a new stamp.

| ID | Status | Evidence or reason |
|---|---|---|
| GEN-01 | addressed | every non-ok state is its own exit-3 state, never KIMI OK; empty author set for a reviewing role is author-unknown: crew_kimi_agent.py route()/run(), tests test_a_reviewing_role_with_no_author_family_is_author_unknown, sabotage (vi) in notes.md |
| GEN-02 | addressed | prompt written via review_run._write_atomic into a private mkdtemp scratch; kimi_probe.write_agent_file tmp + os.replace; no shared file written |
| GEN-03 | n/a | no irreversible action: the script only reads and launches a read-only child; exit 8 stops the dispatcher |
| GEN-04 | addressed | hand sabotage (i)-(vii) in notes.md, plus the two restored sabotage anchors (test_an_unknown_author_family_bars_nothing, test_kimi_agent_file_is_read_only red) and the two encoding guards (cp1252 / not-UTF-8 tests red) |
| GEN-05 | addressed | only provider == kimi routes; launchable(state) is ok only; any other probe state is unavailable: route() and run() |
| GEN-06 | addressed | argv list launch via review_run.launch; task passed by file pointer over INLINE_PROMPT_LIMIT; answer redacted with kimi_probe.redact; agent files tell the dispatcher to pass the task through a quoted heredoc |
| GEN-07 | addressed | the first-line contract (KIMI OK / KIMI UNAVAILABLE / KIMI CHANGED THE TREE / KIMI TREE UNKNOWN, exits 0/3/8/2) is asserted by test_crew_kimi_agent.py and quoted verbatim in the three agent files |
| GEN-08 | addressed | test PATH uses git's own directory (_git_only_path; WinError 2 fixed); stdout reconfigured UTF-8 (test_a_non_ascii_answer_reaches_a_cp1252_stdout_intact); fake kimi ships a .cmd shim |
| GEN-09 | addressed | README Agents on Kimi, CONFIG.md, PLUGINS row, guide, codemap, diagram and CHANGELOG describe this commit; build.py --check, config_reference --check, check-crew-docs, check-marketplace pass |
| GEN-10 | addressed | live smoke against real Kimi Code 2.1.1 kimi-code/k3, explorer and researcher, recorded in notes.md (latency, WebSearch/FetchURL present) |
| GEN-11 | addressed | tree fingerprint before probe, after probe and after run on every path; stop_survivors before the last fingerprint; tests for probe write, late write, staged/committed change |
| GEN-12 | addressed | gate-runner and CI run on the final HEAD after the version commit; review bundle hash recorded by review_run |
| PYTHON-01 | addressed | role_instructions opens utf-8/strict/newline=''; stdin decoded utf-8 strict with a usage error (test_the_cli_refuses_a_task_that_is_not_utf8) |
| PYTHON-03 | addressed | _say writes one line per contract line (rstrip newline); Kimi stream parsed by kimi_probe.final_message (JSONL) |
| PYTHON-04 | addressed | no file another process reads is rewritten in place; scratch files are private and removed |
| PYTHON-06 | addressed | kimi resolved by kimi_probe.probe (which), launched as an argv list by review_run.launch; tests launch sys.executable |
| PYTHON-07 | addressed | --timeout (default 900 s) on the run via review_run.launch; probe has its own timeout; test_a_run_that_times_out_is_unavailable |
| PYTHON-08 | addressed | child env is kimi_probe.kimi_env() (KIMI_MODEL_* and infinite-retry stripped); test_the_launch_is_read_only_and_scrubbed |
| PYTHON-10 | addressed | config resolved through crew_config.resolve_config / resolve_role (dict_or_empty); a read error is exit 2 |
| PYTHON-11 | addressed | try bodies wrap only the open/read (role_instructions), the decode (main) and route() config read |
| PYTHON-13 | addressed | root is abspath'd once; tree comparison is review_run.reviewer_changes over repo-relative git paths; no path containment decided here |
| REPO-01 | n/a | no identity or author recording changed; author families come from crew_state.author_families |
| REPO-02 | addressed | change detector is review_run.tree_fingerprint (contents, modes, untracked, staged, commits) reused; tests cover append, new file, replace, chmod, stage, commit, late process, probe write |
| REPO-03 | addressed | plugin.json and marketplace.json bumped together, PLUGINS claim, CHANGELOG entry, check-marketplace.py run after the version commit |
