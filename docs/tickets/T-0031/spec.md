# T-0031 cross-session versioned contracts on the coordination record, frozen once built against          status: spec   risk: high
## Refreshed 2026-10-04
- First spec for this ticket; there was no earlier spec.md or plan.md. Written against origin/main 155fe6d8 (crew 1.0.322) and the unmerged dependency branches named under Dependencies.
- Narrowed to the first slice of the 2026-09-30 scope. This ticket is the contract record only. The rest is split out, as L-0633 (`<channel>:<id>` dependencies in the wave), L-0634 (the wave refuses a built-against hash mismatch) and L-0635 (the sabotage mutations, a tooling PR). Their specs are in `children/<k>/`. Research findings stay in L-0546.
- Reason for the split: the whole scope is about 470 production lines with two parsers and a guard, and its sabotage mutations sit on a harness path (`plugin/crew/tests/sabotage*.py`) that may not share a PR with feature code.
- The INDEX row already says `split: L-0546`. That split moved research findings only; it does not cover the dependency form, the wave refusal or the sabotage mutations, so the rest of the scope was still over the size rule and is split again here. Listed under "Open questions for the owner".
- Anchors re-checked 2026-10-04 in a second pass: every origin/main `path:line` under Evidence, and every branch anchor at `T-0030-coord` ec9a28a2 and `T-0029-wave` 574985ce, reads as stated.
## Decisions (taken as the recommended option, owner not available 2026-10-04)
- A new module, `crew_contract.py`, beside `crew_coord.py`. It reuses T-0030's `Channel` (fetch, read, write, no force push) and adds no git plumbing of its own.
- A contract version is two files on the channel branch: `contracts/<name>/v<N>.json` (the record) and `contracts/<name>/v<N>.body` (opaque bytes, the interface text itself). The record is `{"name", "version": N, "hash": "sha256:<hex of the body bytes>", "status": "draft" | "built-against", "built_by": [{"repo", "ticket", "hash", "at"}]}`.
- A `draft` version may be replaced in place. A `built-against` version is frozen: `put` refuses to change its body, hash or status. The only way forward is a new version, `put --new-version --ticket <id>`, where `<id>` is this side's new ticket for the change.
- "Owner-approved" is enforced through the ticket, not through a new signal. `build-against --ticket <id>` is refused unless `crew_ticket.accepted(root, <id>)` reads `approved`, so only a ticket the owner approved can bind to a version.
- Each side records what it built against twice: an entry in the record's `built_by` on the channel, and a local binding in `.work/tickets/<id>/contracts.json` (`{"schema": 1, "bindings": [{"channel", "name", "version", "hash"}]}`), written by the script. The local copy is the evidence L-0634 compares against, because a peer can rewrite the channel.
- `<name>` matches `[a-z0-9][a-z0-9-]{0,63}`, the same rule as a channel name.
## Intent
Two sessions building against each other can put an interface contract on the shared channel as a numbered version with a content hash, and either side can record that its ticket built against that version. From the first such record the version is frozen: it cannot be edited, only superseded by a new version tied to a new ticket. Everything read from the channel is peer-written data, and a record that cannot be fetched or parsed reads `unknown`, never current.
## Exclusions
- No change to `crew_wave.py`, and no `<channel>:<id>` dependency: L-0633. No refusal of a wave on a hash mismatch and no `verify` command: L-0634.
- No edit to any path in `HARNESS` of `scripts/check-tooling-pr.py` (`plugin/crew/tests/sabotage*.py`, `crew_ticket.py`, `scope_guard.py`, `review_*.py`, the verify gate). The sabotage mutations for this code are L-0635. `crew_ticket` is imported and called, never edited.
- No edit to `crew_coord.py` beyond what T-0030 lands. If a helper there needs to become public for reuse, that is a stop for the owner, not a quiet edit.
- No research findings as files (L-0546). No messaging, no bridge calls, no `/crew:` command surface (T-0032).
- No force push, `--force-with-lease` or `+` refspec; no checkout of the channel branch; no write to a working tree, to `<git-common-dir>/crew/`, or to any tracked file. The only local file written is `.work/tickets/<id>/contracts.json`.
- No new hook, no change to an existing hook, no new config key. `coord.channel` and `coord.remote` are T-0030's.
- No deletion of a contract version, and no way to return a `built-against` version to `draft`.
- Never read, print or log a credential-shaped environment value. Git children get the environment T-0030's `child_env` builds.
## Evidence
At origin/main 155fe6d8, checked 2026-10-04:
- Nothing to build on exists on main yet: `git ls-tree -r --name-only origin/main | grep -E "crew_(coord|wave|contract)"` prints nothing.
- Crew version: `plugin/crew/.claude-plugin/plugin.json:3` is `1.0.322`.
- The no-force rule this must keep: `plugin/crew/hooks/scripts/cloud_guard.py:21` (`git push --force|-f|--force-with-lease|+ref` -> `guards.forcePush`), `_git_force_push` at `:2029`, the lease forms at `:2037-2038`.
- The scope guard refuses Claude's own writes that name `<git-common-dir>/crew/`: `plugin/crew/hooks/scripts/scope_guard.py:128` (`_DOTGIT_CREW_RE`), used at `:293`. The local binding therefore lives under `.work/tickets/<id>/`, not there.
- Approval state this ticket reads: `plugin/crew/hooks/scripts/crew_ticket.py:687` `accepted(root, ticket)`, `:605` `status`, `:193` `check_ticket`. `crew_ticket.py` is a harness path (`scripts/check-tooling-pr.py:65`).
- The harness list: `scripts/check-tooling-pr.py:58-87`; `plugin/crew/tests/sabotage*.py` at `:79`. The seam list at `:89-95` does not name `crew_coord.py`, `crew_wave.py` or the new module, so they are ordinary feature files.
- One ticket per repo, cross-referenced by id: `plugin/crew/commands/spec.md:64` ("Multi-repo and cross-references").
- The markdown line claim that moves with every crew `.md` edit: `plugin/crew/BUDGETS.md:10` (`<!-- claim: crew-markdown-lines -->`).
- Verify rules run suites through `plugin/crew/tests/pytest_rule.py` (for example `.crew/verify.json:232`).
- `.pylintrc:140` `max-module-lines=3400`.

At the unmerged branch `T-0030-coord` ec9a28a2 (re-find by content after T-0030 lands; these are not origin/main lines):
- `plugin/crew/hooks/scripts/crew_coord.py:567` `class Channel`; `fetch` returns `(tip, 'ok'|'absent'|'failed', why)`; `read(tip)` returns `{path: bytes}` or None; `write(change, message)` applies `change(files)` on the fetched tip, pushes without force and retries at most `MAX_RETRIES` (`:159`) times.
- The module docstring states that other files on the channel "are carried through untouched", and `_blob` keeps an unchanged file's blob and mode. Contract files can share the branch with claims.
- `:1149` `parse_claim` ("a corrupt claim is never skipped"), `:1190` `log_line`, `:239` `safe`, `:248` `peer` and `PEER = "[peer-written]"` (`:182`), `:1085` `repo_key`, `:1606` `_setup` (resolves `coord.channel` / `coord.remote`), `:195` `Result`, exit codes `:154-157` (0 ok, 1 refused, 2 usage, 3 unknown).
## Unknowns
- **T-0030 is not on main.** Every `crew_coord.py` name above can move before it lands. Resolved at implement: re-read the landed file and re-anchor; a helper that was renamed is followed, a helper that was removed is a stop for the owner.
- **`_setup` and other underscore names are private to `crew_coord.py`.** Using them from a second module needs a pylint disable per call or a public alias. Resolved at plan: prefer the public names (`Channel`, `repo_key`, `safe`, `peer`, `log_line`, `Result`); if `_setup` is the only route to the channel, ask the owner before widening `crew_coord.py`.
- **Size of a body.** A contract body is read into memory and stored as one blob. Accepted as risk, with a refusal above 1 MiB so a mistaken `--file` cannot bloat the channel.
- **A peer can push to the channel without this tool** and rewrite a frozen record. This ticket cannot prevent that. It is detected by L-0634 from the local binding. Accepted as risk here, and stated in the README.
- **The script writes under `.work/tickets/<id>/`.** `test_worktree_config.py` on the T-0029 branch keeps an allowlist of script writes; whether a write to `.work/` needs an entry there is measured at plan against the landed file.
- **The next free crew patch version** is set at land time, one above origin/main.
- Refresh artifacts (`graphify-out/`, `docs/diagrams/`, `.claude/rules`) are covered by the scope guard's refresh allowance for an approved ticket, so they are not in Touch.
## Dependencies
Must land first:
- T-0030 (in-progress; local branch `T-0030-coord` at ec9a28a2, crew 1.0.71, not on the shared remote) - provides `crew_coord.py`, the channel branch and the `coord` config block. This ticket cannot start until it is merged to main.
- T-0029 (in-progress; local branch `T-0029-wave`) - named in the INDEX row as a dependency of the original scope. After the split this slice does not touch the wave, so T-0029 is a dependency of L-0633 and L-0634 only, not of this slice.
- T-0010 (merged) - the questions and approval policies `crew_ticket.accepted` already honours.

Blocks:
- L-0634 (the wave's hash-mismatch refusal reads this ticket's records and bindings).
- L-0635 (sabotage for this module).
- T-0032 (ready; messaging announces "contract vN is up").
- L-0546 (direction; only where a finding is filed against a contract version).

No plan.md exists for this ticket; `/crew:plan T-0031` writes it after T-0030 lands.
## Touch
- `plugin/crew/hooks/scripts/crew_contract.py`
- `plugin/crew/tests/test_crew_contract.py`
- `plugin/crew/README.md` - contracts, the freeze rule, what a peer can and cannot rewrite
- `plugin/crew/BUDGETS.md` - the crew-markdown-lines claim
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/verify.json` - one rule mapping the new module and its suite
- `.crew/codemap/crew.md`
- `docs/guides/crew/src/daily-workflow.md` - a short section on contracts between two sessions
- `docs/guides/crew/crew-1.0-daily-workflow.html` - rebuilt by the guide build script
- `docs/guides/crew/crew-1.0-daily-workflow.docx` - rebuilt by the guide build script
- `docs/guides/crew/crew-1.0-daily-workflow.pdf` - rebuilt by the guide build script
## Acceptance checks
Suite command for every test below: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_contract.py -q`. Tests use a local bare remote under `tmp_path`, as T-0030's do.
- [ ] `crew_contract.py put --name <n> --file <path>` on a channel with no version of `<n>` writes `contracts/<n>/v1.json` and `contracts/<n>/v1.body` in one commit on the fetched tip, with `status: draft`, `hash` equal to `sha256:` plus the sha256 of the body bytes, and one `log.jsonl` line (`test_put_writes_v1_draft_with_the_body_hash`).
- [ ] Must-allow: `put` on a `draft` latest version replaces the body and hash in place and keeps the version number (`test_put_replaces_a_draft_in_place`).
- [ ] Must-block: `put` on a `built-against` latest version exits 1, names the version and who built against it, and changes nothing on the channel (`test_put_on_a_frozen_version_is_refused`).
- [ ] `put --new-version --ticket <id>` writes v(N+1) as `draft` only when vN is `built-against`. It is refused when vN is still `draft`, when `--ticket` is missing or not a ticket id, and it never touches vN's two files (`test_new_version_needs_a_frozen_predecessor_and_a_ticket`, `test_new_version_leaves_the_old_version_byte_identical`).
- [ ] `build-against --name <n> --version N --ticket <id>` with an approved ticket sets `status: built-against`, appends `{repo, ticket, hash, at}` to `built_by`, and writes the binding to `.work/tickets/<id>/contracts.json`. Running it twice adds no second entry (`test_build_against_freezes_and_writes_the_binding`, `test_build_against_is_idempotent`).
- [ ] Must-block for `build-against`, one test each, nothing written on the channel or locally: the ticket's approval is not `approved`; the version does not exist; the body's sha256 does not equal the record's `hash`; the record is not JSON, is not an object, or has a `status` outside the two values; the fetch fails (exit 3, `unknown`).
- [ ] A second repository's `build-against` on an already frozen version appends its own `built_by` entry and leaves the first entry and the body unchanged (`test_two_sides_build_against_one_version`).
- [ ] `status` is read-only apart from the fetch. It prints every contract version with status, hash prefix and `built_by`, each line labelled `[peer-written]`. A corrupt record prints `unknown` and makes the exit code 3; it is never skipped (`test_status_is_read_only_and_labels_peer_data`, `test_status_reads_a_corrupt_record_as_unknown`).
- [ ] Names: `--name` outside `[a-z0-9][a-z0-9-]{0,63}`, a version that is not a positive integer, and a body over 1 MiB are usage errors (exit 2) before any fetch (`test_bad_name_version_or_size_is_refused_before_any_fetch`).
- [ ] No force and isolation: every `git push` argv the module causes has no `--force`, `-f`, `--force-with-lease` or `+` refspec; across every command the working tree, `HEAD`, `<git-common-dir>/crew/` and every ref except `refs/heads/crew-coord/<c>` are unchanged, and under `.work/` only `tickets/<id>/contracts.json` changes (`test_push_argv_never_forces`, `test_only_the_channel_ref_and_the_binding_file_change`).
- [ ] Claims are carried through: after `put` and `build-against`, every `claims/*.json` blob on the channel is byte-identical (`test_claims_survive_contract_writes`).
- [ ] A rejected push re-fetches and re-applies: when a peer freezes vN between this side's fetch and push, this side's `put` is refused on the retry, not written (`test_put_loses_the_race_to_a_freeze_and_is_refused`).
- [ ] `.crew/verify.json` gains a rule mapping `crew_contract.py` and `test_crew_contract.py` to the suite command above. The README and the daily-workflow guide describe contracts and the freeze rule, the guide is rebuilt with `python3 docs/guides/crew/src/build.py`, and `.crew/codemap/crew.md` names the module.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 on the branch (no harness path changed), crew is one patch above origin/main in `plugin.json` and `marketplace.json` with a CHANGELOG entry and the `plugin/PLUGINS.md` row, and `python3 scripts/check-marketplace.py` passes after the commit.
## Size
About 260 production lines, all in `crew_contract.py`: one record parser with its freeze rule, three commands (`put`, `build-against`, `status`) and the binding writer. Tests and docs are not counted.
## Open questions for the owner
1. Is tying "owner-approved" to the ticket's approval receipt enough, or should a new contract version also need an owner-only signal like T-0030's `--break`? Taken: the receipt is enough.
2. Is the local binding in `.work/tickets/<id>/contracts.json` acceptable, given `.work/` is per worktree and ignored? Taken: yes, with the channel's `built_by` as the shared copy.
3. Should a contract body be limited to text formats? Taken: opaque bytes, 1 MiB limit.
4. One sabotage PR for all three slices (L-0635), or one per slice? Taken: one.
5. The row was already split once (L-0546, findings). Is a second split into three children acceptable, or should the dependency form and the wave refusal stay in this ticket as one larger PR (about 470 production lines, sabotage still separate)? Taken: split.

## Split
- L-0633 (child 1 of T-0031, filed 2026-10-04): Cross-session dependencies <channel>:<id> in the autopilot wave
- L-0634 (child 2 of T-0031, filed 2026-10-04): The wave refuses a ticket whose built-against contract hash no longer matches
- L-0635 (child 3 of T-0031, filed 2026-10-04): Sabotage mutations for cross-session contracts and dependencies (tooling PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
