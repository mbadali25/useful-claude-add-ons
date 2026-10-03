# T-0036 plan            spec: .work/tickets/T-0036/spec.md

Work in a fresh worktree, `/repos/personal/uca-t-0036`, on branch `T-0036-build`, cut from origin/main (`502cb137` or later). Every line number below is origin/main's at `502cb137`. Re-grep each quoted string before editing, because T-0063, T-0064 and others land in between. Two parts carry the risk: the refresh check can refuse `/crew:done`, and the allowance widens what an approved ticket may write without Touch. Each gets must-allow and must-block tests, and sabotage mutations that must go red, with the neighbouring case checked after each fix. There is no second opinion (step 3 of `/crew:plan`): the design is direction.md's approved recommendation, and the spec's Unknowns record the four decisions it leaves. Heavy runs are serial under `flock /root/crew-tmp/heavy.lock`, with `TMPDIR=/root/crew-tmp/t-0036`.

### Step 1: crew_reference.py lint - header, integration entries, anchors
Files: plugin/crew/tests/test_reference_docs.py, plugin/crew/hooks/scripts/crew_reference.py
Test: python3 -m pytest plugin/crew/tests/test_reference_docs.py -q -p no:cacheprovider
Risk: med. A lint that passes an unanchored entry lets an unverifiable reference ship. A lint that is too strict refuses every real doc.
- [ ] In `test_reference_docs.py`, build fixtures in `tmp_path`: a small repo with `src/client.py` (20 lines) and a `docs/reference/integrations.md` that has:
  - the header `> Generated from demo@502cb13 on 2026-09-27. Every entry is anchored to a` / `> file and line - re-verify the anchor before trusting the entry.`;
  - `## ShipStation`;
  - `### POST https://ssapi.shipstation.com/orders/createorder`;
  - `` `src/client.py:12` ``;
  - ``Auth: basic, key from env `SHIPSTATION_API_KEY` ``;
  - `Request:`, `Response:`, `Retries:` and `Call sites: `src/client.py:12``.
  Call the module through `crew_reference.lint(root, path, kind)`, which returns `{"problems": [...], "undocumented": n}`.
- [ ] Write the must-allow tests `test_lint_accepts_a_well_formed_integrations_doc`, `test_lint_allows_credential_source_names` and `test_lint_counts_undocumented_entries`.
- [ ] Write the must-block tests `test_lint_refuses_a_doc_without_the_generated_header`, `test_lint_refuses_an_integration_entry_without_an_anchor`, `test_lint_refuses_an_integration_entry_without_an_auth_line` and `test_lint_refuses_an_anchor_to_a_missing_file_or_past_its_end` (parametrised: missing file, and line 99 of a 20-line file).
- [ ] Run them and watch them fail (the module does not exist).
- [ ] Create `plugin/crew/hooks/scripts/crew_reference.py`, standard library only, with:
  - a docstring stating the doc contract;
  - `GENERATED_RE = re.compile(r"^> Generated from (\S+)@([0-9a-f]{7,40}) on (\d{4}-\d{2}-\d{2})\b", re.MULTILINE | re.IGNORECASE)`;
  - `ANCHOR_RE = re.compile(r"`(\.?[A-Za-z0-9_][A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+-]+)*):(\d+)(?:-(\d+))?`")`;
  - `_sections(text)` splitting on `### ` headings;
  - `lint(root, path, kind)`, where `kind` is `integrations` or `flow`.
- [ ] Integration rules:
  - Every `### ` entry needs one or more `ANCHOR_RE` matches and a line starting `Auth:`. The value may be `none` or `undocumented - needs a human`.
  - Every anchor's file must exist under `root`, checked with `os.path.realpath` so it stays inside `root`, and its end line must be at most the file's line count.
  - Problems read `<doc>:<line>: <what>`.
- [ ] Run the Test command.

### Step 2: crew_reference.py lint - flow docs
Files: plugin/crew/tests/test_reference_docs.py, plugin/crew/hooks/scripts/crew_reference.py
Test: python3 -m pytest plugin/crew/tests/test_reference_docs.py -q -p no:cacheprovider
Risk: med. An unlabelled arrow or a missing "What is not covered" section passing is the silent-gap failure the flow doc exists to prevent.
- [ ] Write the fixture flow `docs/reference/flows/order-sync.md` with:
  - the header;
  - `Summary: orders move from the shop to ShipStation every 10 minutes.`;
  - a ```` ```mermaid ```` block with `sequenceDiagram`, `Job->>Client: poll new orders (since cursor)` and `Client->>ShipStation: POST /orders/createorder (order JSON)`;
  - `## Steps`, a table `| Step | Caller -> callee | Carries | Anchor | On failure |` with two rows, each citing `src/client.py:<n>`;
  - `## State between steps`;
  - `## Failure and retry`;
  - `## What is not covered`.
- [ ] Write the must-allow test `test_lint_accepts_a_well_formed_flow_doc`.
- [ ] Write the must-block tests:
  - `test_lint_refuses_a_flow_without_a_sequence_diagram`;
  - `test_lint_refuses_an_unlabelled_sequence_arrow`, parametrised over the arrow forms `->>`, `-->>`, `->`, `-->`, `-x`, `--x`, `-)` and `--)` with no `: label`, or an empty one;
  - `test_lint_refuses_a_flow_missing_a_required_section` (the summary, `## Steps`, `## Failure and retry` and `## What is not covered`, absent or with an empty body);
  - `test_lint_refuses_a_flow_step_row_without_an_anchor`.
- [ ] Watch them fail.
- [ ] Implement the flow rules in `lint`:
  - Find the first fenced `mermaid` block. Its first non-blank line must be `sequenceDiagram`.
  - Each line matching `^\s*[\w.-]+\s*(--?>>|--?>|--?x|--?\))\s*[\w.-]+` needs `:` followed by non-blank text.
  - `REQUIRED_FLOW_SECTIONS = ("## Steps", "## State between steps", "## Failure and retry", "## What is not covered")` each need a non-blank body.
  - A `Summary:` line must appear before the mermaid block.
  - Every data row of the `## Steps` table must hold one or more `ANCHOR_RE` matches, and the anchors are checked as in Step 1.
- [ ] Run the Test command. Then run the Step 1 tests again, the neighbouring case.

### Step 3: the secret refusal and the CLI
Files: plugin/crew/tests/test_reference_docs.py, plugin/crew/hooks/scripts/crew_reference.py
Test: python3 -m pytest plugin/crew/tests/test_reference_docs.py -q -p no:cacheprovider
Risk: high. A missed pattern ships a credential into a tracked doc. A lint that echoes the value leaks it into the transcript.
- [ ] Write the must-block test `test_lint_refuses_secret_shaped_strings`, parametrised with synthetic values built at runtime by string concatenation (so this test file itself holds no literal secret shape):
  - `"AKIA" + "Q" * 16`;
  - a `-----BEGIN RSA PRIVATE KEY-----` block;
  - `"ghp_" + "a" * 36`;
  - `"github_pat_" + "a" * 60`;
  - `"xoxb-" + "1" * 12 + "-" + "a" * 24`;
  - `"sk-" + "a" * 40`;
  - a three-part `eyJ...` JWT;
  - `password = "hunter2hunter2"`.
  Each doc must fail with `secret-shaped string (<pattern name>)`, and `value not in output` must hold for stdout and stderr.
- [ ] Extend `test_lint_allows_credential_source_names` with ``Auth: bearer, token from env `ORDERS_API_TOKEN` (`src/client.py:3`)`` and `secret name orders/prod/api`, which must pass.
- [ ] Write `test_lint_cli_exit_codes`. It runs `python3 plugin/crew/hooks/scripts/crew_reference.py lint --root <repo> --kind flow <file>` as a subprocess, with `stdin=subprocess.DEVNULL`, and asserts:
  - 0 on the clean fixture;
  - 1 on a broken one;
  - 2 with no `--kind`;
  - 2 on a missing file (message names the file).
- [ ] Watch them fail.
- [ ] Add `SECRET_PATTERNS`, a tuple of `(name, compiled)` pairs, and run it over every line before any shape check. A secret hit reports the name and `path:line` only.
- [ ] Add `main(argv)` with argparse:
  - the `lint` subcommand, `--root` (default `.`), `--kind {integrations,flow}` (required) and a `path`;
  - print each problem, then `lint <path>: ok (<n> undocumented)` or `lint <path>: <k> problem(s)`;
  - an unreadable file prints `cannot read <path>: <reason>` to stderr and exits 2.
- [ ] Run the Test command.

### Step 4: the reference kind in the refresh check
Files: plugin/crew/tests/test_refresh_check.py, plugin/crew/hooks/scripts/crew_refresh_check.py
Test: python3 -m pytest plugin/crew/tests/test_refresh_check.py -q -p no:cacheprovider
Risk: high. `/crew:done` check 4 trusts this. A no-header or unreadable doc read as `fresh` is the recurring unknown-to-safe defect, and judging `api.md` would refuse done in consumer repos.
- [ ] Add a helper `_reference(root, rel, anchor, cites)` beside `_codemap` (`test_refresh_check.py:73`). It writes the Generated header with `anchor` (or none when `anchor` is None) and one `### ` entry citing each path.
- [ ] Write the tests:
  - `test_reference_doc_citing_changed_path_behind_is_stale`, with both `docs/reference/integrations.md` and `docs/reference/flows/order-sync.md`. The command is `/crew:reference --integrations` or `/crew:reference --flows order-sync`.
  - `test_reference_doc_refreshed_is_fresh`
  - `test_reference_doc_not_citing_a_changed_path_is_out_of_scope`
  - `test_reference_doc_without_generated_header_is_unknown_and_refreshable`
  - `test_reference_doc_citing_no_path_is_unknown`
  - `test_api_and_features_docs_are_not_judged`: a stale `api.md` and `features.md` citing a changed path produce no `reference` artifact.
  - Add `("reference", "docs/reference/flows")` to the parametrisation of `test_an_unlistable_artifact_dir_is_unknown` (`:737-738`).
- [ ] Watch them fail.
- [ ] In `crew_refresh_check.py`:
  - import `GENERATED_RE` from `crew_reference`;
  - add `_references(root, changed, untracked)` after `_diagrams` (`:455-486`). It judges `docs/reference/integrations.md` (when it exists) and every `*.md` in `docs/reference/flows/`, with `_listing` for the flows dir.
  - Per doc:
    - An unreadable doc is `unknown`, not refreshable (only when `changed`).
    - Its citations use `_CITATION_RE`, filtered the way `_codemaps` filters (`:425`).
    - No citations is `unknown` and refreshable.
    - Nothing reached is skipped.
    - No `GENERATED_RE` match is `unknown` and refreshable ("no `Generated from <repo>@<sha>` header").
    - Otherwise `_judge(root, match.group(2), reached, untracked)`.
  - The kind is `reference`, and the name is `integrations` or `flows/<stem>`.
  - Call it in `ticket_freshness` after `_diagrams` (`:623`).
  - Update the module docstring's kind list (`:12-36`) to four kinds.
- [ ] Run the Test command. Every existing test must pass unedited.

### Step 5: docs/reference joins the refresh-artifact allowance
Files: plugin/crew/tests/test_refresh_check.py, plugin/crew/tests/test_scope_guard_refresh_artifacts.py, plugin/crew/tests/test_completion_audit_refresh_artifacts.py, plugin/crew/hooks/scripts/crew_refresh_check.py
Test: python3 -m pytest plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_scope_guard_refresh_artifacts.py plugin/crew/tests/test_completion_audit_refresh_artifacts.py plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_completion_audit.py -q -p no:cacheprovider
Risk: high. A blocking hook opens wider. Only an approved ticket may write `docs/reference/**`, and only under whole-segment matching.
- [ ] Rename `test_refresh_artifact_paths_default_to_the_four_documented_dirs` (`test_refresh_check.py:419-423`) to `..._five_documented_dirs`, expecting `[".crew/codemap", "docs/diagrams", "graphify-out", ".claude/rules", "docs/reference"]`.
- [ ] Add `docs/reference/integrations.md` and `docs/reference/flows/order-sync.md` to `ARTIFACTS` in `test_scope_guard_refresh_artifacts.py:27-28` and `test_completion_audit_refresh_artifacts.py:25`.
- [ ] Add `docs/referenceX/a.md` to the prefix-only parametrisation (`test_scope_guard_refresh_artifacts.py:79-81`).
- [ ] Watch the renamed test and the new must-allow rows fail. The must-block rows (unapproved, stale, `cli`) pass already, since today nothing exempts `docs/reference`. Record that as a neighbour check, not a new red.
- [ ] Append `(None, "docs/reference")` to `REFRESH_ARTIFACT_PATHS` (`crew_refresh_check.py:168-173`), and update its comment and the docstring paragraph at `:106-118`.
- [ ] Confirm that `ticket_freshness`'s `own` (`:617`) now drops `docs/reference/**` from the changed set, so a refresh commit cannot stale its own doc. Add `test_a_reference_refresh_commit_stales_nothing`.
- [ ] Run the Test command.

### Step 6: sabotage and the verify map
Files: plugin/crew/tests/sabotage_reference.py, plugin/crew/tests/sabotage_refresh.py, plugin/crew/tests/sabotage.py, .crew/verify.json
Test: python3 plugin/crew/tests/sabotage.py
Risk: med. A mutation that stays green means a test that does not test.
- [ ] Create `plugin/crew/tests/sabotage_reference.py` with `REFERENCE_MUTATIONS`, in the same `(label, target, find, replace, test)` shape as `sabotage_refresh.py`, and a docstring. It has one entry for each of these, each naming its test from Steps 1 to 3:
  - header check removed;
  - anchor requirement removed;
  - anchor existence check removed;
  - line-count check removed;
  - arrow-label check accepts empty;
  - `## What is not covered` dropped from `REQUIRED_FLOW_SECTIONS`;
  - each `SECRET_PATTERNS` class removed (one entry per class);
  - the secret problem formats the matched value.
- [ ] Append to `REFRESH_MUTATIONS`:
  - `artifacts += _references(...)` removed;
  - the no-header branch returns `FRESH`;
  - `(None, "docs/reference")` removed;
  - the file filter widened to every `*.md` in `docs/reference`.
  Each names its Step 4 or Step 5 test.
- [ ] In `sabotage.py`, add `from sabotage_reference import REFERENCE_MUTATIONS` after `:77`, and add `+ REFERENCE_MUTATIONS` to the concatenation (`:3047-3048`). Keep the file at 3400 lines or fewer (`.pylintrc:140`).
- [ ] Extend `test_every_refresh_sabotage_anchor_is_present_exactly_once` (`test_refresh_check.py:566`), or add the same check for `REFERENCE_MUTATIONS` in `test_reference_docs.py`.
- [ ] In `.crew/verify.json`:
  - Add a rule for `plugin/crew/hooks/scripts/crew_reference.py`, `plugin/crew/tests/test_reference_docs.py`, `plugin/crew/tests/sabotage_reference.py`, `plugin/crew/commands/reference.md` and `plugin/crew/skills/crew-docs/integrations-and-flows.md`, running `python3 -m pytest plugin/crew/tests/test_reference_docs.py -q`, with `seconds` measured on this host and a `why` naming the must-block cases.
  - Add `crew_reference.py` to the refresh rule's paths (`:264-270`).
- [ ] Run the Test command under the heavy lock, and confirm each new entry reports RED on its named test.

### Step 7: the command, the skill reference and the lifecycle wording
Files: plugin/crew/commands/reference.md, plugin/crew/skills/crew-docs/integrations-and-flows.md, plugin/crew/skills/crew-docs/SKILL.md, plugin/crew/commands/implement.md, plugin/crew/commands/onboard.md, plugin/crew/tests/test_reference_docs.py
Test: python3 -m pytest plugin/crew/tests/test_reference_docs.py plugin/crew/tests/test_refresh_check.py -q -p no:cacheprovider && python3 scripts/check_instructions.py
Risk: med. `reference.md` breaks the 120-line budget, or `implement.md`'s ordering test (`test_implement_refreshes_between_docs_and_review`, `test_refresh_check.py:541`) breaks.
- [ ] Write `test_reference_md_documents_integrations_flows_and_audit`. It asserts:
  - `reference.md` has headings `` ## `--integrations` `` and `` ## `--flows [<name>]` ``;
  - it names `crew_reference.py lint`, `crew:security` and `integrations-and-flows.md`;
  - its `--audit` list names `integrations.md`;
  - it is 120 lines or fewer;
  - `implement.md` step 6 mentions reference docs.
  Watch it fail.
- [ ] Write `plugin/crew/skills/crew-docs/integrations-and-flows.md`, a reference file with frontmatter if `check_instructions.py` requires it for skill files. It covers:
  - the integrations entry format, one `##` per external system, from direction.md item 1;
  - the flow doc format from Step 2, with a worked order-sync example;
  - the `--flows` with no name proposal format, recommendation first, which waits for the owner;
  - the lint-before-write rule: draft to `${TMPDIR:-/tmp}/crew-reference/<name>.md`, run `crew_reference.py lint`, copy into `docs/reference/` only on exit 0, never print the value on a secret hit;
  - auth, login and token flows and every credential source going to `crew:security` with the draft before it is written;
  - "no outbound calls" meaning no `integrations.md`, stated in the report.
- [ ] In `reference.md`:
  - the frontmatter `argument-hint` becomes `[--api | --features | --integrations | --flows [<name>] | --audit | <area>]`;
  - add the two sections, about 10 lines, pointing at `${CLAUDE_PLUGIN_ROOT}/skills/crew-docs/integrations-and-flows.md`;
  - `--audit` gains items for `integrations.md` (calls with no entry, entries whose anchor no longer holds) and flow docs failing the lint.
- [ ] In `crew-docs/SKILL.md`, the table (`:129-132`) gains the `integrations.md` and `flows/<name>.md` rows.
- [ ] In `implement.md` step 6 (`:87-89`), "the code maps, diagrams and code graph" becomes "the code maps, diagrams, reference docs (`docs/reference/integrations.md`, `flows/`) and code graph". Add one sentence: a change that adds an outbound call or a multi-step flow gets its integrations entry or a proposed flow doc from `/crew:docs`, and naming a new flow is an owner question.
- [ ] In `onboard.md:190-195`, name `--integrations`, and `--flows` (propose only).
- [ ] Run the Test command.

### Step 8: every document that describes it, version and changelog
Files: plugin/crew/README.md, plugin/PLUGINS.md, plugin/crew/BUDGETS.md, .crew/codemap/crew.md, docs/diagrams/process-crew-lifecycle.mmd, docs/guides/crew/src/*.md, docs/guides/crew/crew-1.0-*, TODO.md, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json
Test: python3 scripts/check-marketplace.py && python3 scripts/check_instructions.py
Risk: low. A stale doc sentence, or a version bump missed in one of three places.
- [ ] Update the README:
  - section 7b (`:445-470`): the usage block and the document table gain `--integrations` and `--flows`;
  - `:762`: "Per code map, diagram, reference doc and code graph", with the reference refresh commands;
  - `:764`: reference docs judged, and a no-header or no-citation doc is `unknown`;
  - `:766`: the allowance lists `docs/reference/`;
  - `:2358`: the command row.
- [ ] Update `plugin/PLUGINS.md` `:149` (command row) and `:233` (the `docs/reference/` row).
- [ ] Re-grep `docs/guides/crew/src/*.md` for `crew:reference`, `refresh_check` and "code maps, diagrams". If a hit appears, edit it and rebuild with `docs/guides/crew/src/build.py`. If there is none, the PR body says `Docs: guides none - no guide describes step 6 or /crew:reference (grep at <sha>)`.
- [ ] Refresh `.crew/codemap/crew.md` (`:609-640`) with `/crew:onboard --refresh crew`, and `docs/diagrams/process-crew-lifecycle.mmd` with `/crew:diagram refresh`. Both are refresh artifacts.
- [ ] File the follow-ups in `TODO.md`:
  - judge `api.md` and `features.md` in the refresh check;
  - an outbound-call candidate detector over a ticket's diff;
  - T-0035 adopting the inline flow diagrams.
- [ ] Version:
  - bump crew one patch above origin/main's version at land time, in `plugin.json`, `marketplace.json` and `PLUGINS.md`;
  - add a CHANGELOG entry naming the two flags, the lint and the fourth artifact kind;
  - re-measure `crew-markdown-lines` in `BUDGETS.md` with `git ls-files 'plugin/crew/*.md' | xargs wc -l`.
- [ ] Run the Test command.

### Step 9: gates and the refresh loop
Files: .crew/verify.json, .crew/codemap/**, docs/diagrams/**, graphify-out/**, .claude/rules/**
Test: python3 -m pytest plugin/crew/tests/ -q && python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0036
Risk: med. A gate that goes red late, or a refresh left uncommitted, stales the review receipt.
- [ ] Under `flock /root/crew-tmp/heavy.lock` with `TMPDIR=/root/crew-tmp/t-0036`, run:
  - the full crew suite;
  - `python3 plugin/crew/tests/sabotage.py`;
  - `python3 scripts/check_instructions.py`;
  - `python3 scripts/check-marketplace.py`;
  - `graphify update .`, after waiting for `~/.cache/graphify-rebuild.log` to stop growing, then read the counts from both `graph.json` (`nodes`, `links`) and `GRAPH_REPORT.md`.
- [ ] Measure the new verify rule's `seconds` and record it.
- [ ] Run `crew_refresh_check.py --root . --ticket T-0036` until every line is `fresh`, committing each refresh. Keep `.crew/.scope-base`, `.crew/metrics.md` and `.crew/.verify-gate*.json` untracked.
- [ ] Record what was not verified in the PR body: Windows (no native run of `crew_reference.py`'s CLI) and `scripts/_test/drift-detection.sh` (not run).
