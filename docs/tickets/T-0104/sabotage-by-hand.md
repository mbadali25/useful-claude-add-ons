# T-0104 sabotage by hand (plan step 8)

Head 37726645. Each (a)-(o) mutation applied to the tracked file, its target test run through heavy-run (/root/crew-tmp/t-0104/sab_by_hand.py), then `git checkout --` and the restored file's sha256 compared with the HEAD blob. Output verbatim:

```
T-0104 (a) scaffold: the module search finds nothing: RED rc=1 [test_a_root_without_a_web_project_lists_its_modules_with_the_command_to_scaffold_each] E       AssertionError: assert (0, ['webtest...irectories)']) == (0, ['webtest...directories']) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (b) scaffold: the module search descends into node_modules: RED rc=1 [test_a_root_without_a_web_project_lists_its_modules_with_the_command_to_scaffold_each] E       AssertionError: assert (0, ['webtest...directories']) == (0, ['webtest...directories']) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (c) scaffold: --module is accepted without the web-project check: RED rc=1 [test_module_must_be_a_relative_web_project_under_root] E       assert (0, False, {'...\n", ...}, []) == (1, True, {'....\n", ...}, []) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (d) scaffold: the config's testDir is ignored: RED rc=1 [test_test_files_follow_the_existing_configs_testdir] E       assert (['mod-c/play...guards" {}\n') == (['mod-c/e2e/...guards" {}\n') | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (e) scaffold: a testDir it cannot read falls back to tests/: RED rc=1 [test_a_non_literal_testdir_is_could_not_tell_and_writes_no_test_file] E       AssertionError: assert (0, ['mod-a/p..., True, True]) == (1, ['mod-a/p..., True, True]) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (f) scaffold: an advisory gap fails the run again: RED rc=1 [test_missing_projects_are_advisory_gap_lines_and_exit_0] E       assert (1, True, ["p...], True, True) == (0, True, ["p...], True, True) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (g) scaffold: auth.setup.ts is written without credentials: RED rc=1 [test_no_credentials_means_no_auth_setup_and_no_setup_project] E       assert (0, [False, F... [True, True]) == (0, [False, F... [True, True]) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (h) scaffold: 'setup' is a gap without credentials: RED rc=1 [test_setup_is_not_a_gap_without_credentials] E       assert (0, True, True) == (0, False, True) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (i) scaffold: the baseline-keeping template is dropped: RED rc=1 [test_visual_snippet_keeps_existing_baseline_names] E       assert (False, True) == (True, True) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (j) scaffold: session files are written into the module: RED rc=1 [test_session_files_land_at_root_and_test_files_in_the_module] E       AssertionError: assert ([False, Fals...de_modules\n') == ([True, True,...de_modules\n') | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (k) scaffold: init-agents is not told the module's config: RED rc=1 [test_init_agents_gets_the_modules_config] E       AssertionError: assert ([['init-agen..._modu0/repo']) == ([['--loop=cl..._modu0/repo']) | restored sha256 1f03b8915c91 == HEAD blob
T-0104 (l) rules: --module does not prefix the watched paths: RED rc=1 [test_rules_module_prefixes_paths_and_runs_from_the_module] E       AssertionError: assert ([['(cd mod-a... True, False]) == ([['(cd mod-a... True, False]) | restored sha256 1fe4e3127e31 == HEAD blob
T-0104 (m) rules: an axe/visual rule the config cannot run is still emitted: RED rc=1 [test_rules_omit_axe_and_visual_when_the_config_lacks_them] E       AssertionError: assert (5, ['webtest...ts the gap)']) == (3, ['webtest...ts the gap)']) | restored sha256 1fe4e3127e31 == HEAD blob
T-0104 (n) guard: auth-leak --module reads .crew/config.json from the module: RED rc=1 [test_auth_leak_module_reads_the_modules_config_and_the_roots_declaration] E       AssertionError: assert (1, ['  mod-a...omeCall ( )']) == (0, []) | restored sha256 b02ce2d32f8f == HEAD blob
T-0104 (o) guard: visual --module runs in the root: RED rc=1 [test_visual_module_reads_the_modules_node_modules_and_runs_there] E       AssertionError: assert (0, '.') == (0, 'mod-a') | restored sha256 b02ce2d32f8f == HEAD blob
```

## init-agents --config (spec Unknown 2), run once on a scratch fixture outside the repo

```
 🎭 Using project "chromium" as a primary project
 📝 specs/README.md - directory for test plans
 🌱 mod/e2e/seed.spec.ts - default environment seed file
 🤖 .claude/agents/playwright-test-generator.md - agent definition
 🤖 .claude/agents/playwright-test-healer.md - agent definition
 🤖 .claude/agents/playwright-test-planner.md - agent definition
 🔧 .mcp.json - mcp configuration
 ✅ Done.
init-agents rc=0
./.claude/agents/playwright-test-generator.md
./.claude/agents/playwright-test-healer.md
./.claude/agents/playwright-test-planner.md
./.mcp.json
./mod/e2e/seed.spec.ts
./mod/playwright.config.ts
./specs/README.md
```
