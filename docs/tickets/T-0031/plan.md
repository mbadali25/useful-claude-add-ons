# T-0031 plan: versioned contracts on the coordination channel          spec: docs/tickets/T-0031/spec.md

Written by the implementing session (rush lane g3c-contracts, 2026-10-05) on a base that carries
T-0030 (`crew_coord.py`) and T-0029 (`crew_wave.py`) as ported to `release/1.2.0` by rush g0
(`origin/rush/g0-coord-wave` 3488fbe4b), merged with `origin/release/1.2.0` 3dbc033b.

Anchors re-found by content in the ported `crew_coord.py` (the spec's line numbers are from the
owner's unmerged branch):
- `class Channel` (`fetch`, `read`, `write`, `push_argv`), `run_git`, `child_env`, `safe`, `peer`,
  `PEER`, `log_line`, `stamp`, `Result`, `repo_key`, `UsageError`, `UnknownKey`, `EXIT_*`: all
  public and unchanged in meaning. `write(change, message)` passes a non-`ok` status from `change`
  straight back without writing, which this module uses for an idempotent `build-against`.
- `_setup` is private. It is not the only route to the channel: `Channel(top, remote, channel)` is
  public, and the channel and remote resolution is ten lines over public names
  (`crew_ticket.toplevel`, `crew_config.resolve_config`, `crew_coord.run_git`). This module carries
  its own copy of that resolution; `crew_coord.py` is not edited. `_CHANNEL_RE` is private too; the
  spec gives the contract name the same rule, so the module defines that regex once and uses it for
  both.
- `_SECRET_NAMES` is private. `main` drops from its own environment every name that
  `crew_coord.child_env()` (public) leaves out, which is the same set.
- `test_worktree_config.py`'s `ALLOWED` table counts reads of `.crew/config.json` outside the
  resolver. This module reads config only through `crew_config.resolve_config`, so it needs no row.

Rules for every step: tests first and watched red; every pytest run through the shared lock;
no edit to `crew_coord.py`, `crew_ticket.py` or any `HARNESS` path; no `sabotage*.py` (L-0635).

### Step 1: the record, `put` and `status`
Files: plugin/crew/hooks/scripts/crew_contract.py, plugin/crew/tests/test_crew_contract.py
Test: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_contract.py -q`
Risk: high. A frozen version that can still be edited is the defect this ticket exists to close.
- [ ] Record parser: `contracts/<name>/v<N>.json` must be a JSON object naming its own name and
  version, a `sha256:<64 hex>` hash, a status of `draft` or `built-against`, and a `built_by` list
  of `{repo, ticket, hash, at}` strings that is empty exactly when the status is `draft`. Anything
  else is corrupt and reads `unknown`, never skipped. A path under `contracts/<name>/` that is not
  `v<N>.json` / `v<N>.body`, a version missing one of its two files, or versions not numbered
  1..N read `unknown` too.
- [ ] `put` writes v1, replaces a `draft` latest in place, refuses a `built-against` latest
  (exit 1, naming who built against it), and with `--new-version --ticket <id>` writes v(N+1) only
  over a `built-against` vN. `--ticket` missing or not a ticket id, `--ticket` without
  `--new-version`, a bad name, and a body over 1 MiB or unreadable are usage errors before any git
  call.
- [ ] `status` prints every version with status, hash prefix and `built_by`, each line ending
  `[peer-written]` with peer fields through `safe`; a corrupt record or a body that does not match
  its hash prints `unknown` and exits 3.

### Step 2: `build-against` and the local binding
Files: plugin/crew/hooks/scripts/crew_contract.py, plugin/crew/tests/test_crew_contract.py
Test: as Step 1
Risk: high. A binding written for an unapproved ticket, or a second `built_by` entry, breaks L-0634.
- [ ] Refused before any fetch unless `crew_ticket.accepted(top, id)` is `approved`, and `unknown`
  before any fetch when `.work/tickets/<id>/contracts.json` exists but is not
  `{"schema": 1, "bindings": [{channel, name, version, hash}]}`.
- [ ] On the fetched tip: the version must exist, its record parse, and its body's sha256 equal the
  record's hash. It then becomes `built-against` with one `{repo, ticket, hash, at}` entry for this
  repository and ticket; an entry already there writes nothing to the channel. A local binding for
  the same channel, name and version with another hash is refused.
- [ ] The binding is written after the push, through a temp file and `os.replace`.

### Step 3: isolation, no force, claims carried, the race
Files: plugin/crew/tests/test_crew_contract.py
Test: as Step 1
Risk: med. These pin `Channel`'s behaviour as this module uses it.
- [ ] Every push argv is `push --no-verify -- crew-coord--push <sha>:refs/heads/crew-coord/<c>`.
- [ ] Working tree, `HEAD`, index, `FETCH_HEAD`, `<git-common-dir>/crew/` and every ref but the
  channel's are unchanged; under `.work/` only `tickets/<id>/contracts.json` changes.
- [ ] `claims/*.json` blobs stay byte-identical across `put` and `build-against`.
- [ ] A peer freezing vN between this side's fetch and push makes this side's `put` refused on the
  retry.

### Step 4: docs, verify rule, version
Files: plugin/crew/README.md, docs/guides/crew/src/daily-workflow.md, docs/guides/crew/crew-daily-workflow.html, docs/guides/crew/crew-daily-workflow.docx, docs/guides/crew/crew-daily-workflow.pdf, .crew/verify.json, .crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: `python3 scripts/check-tooling-pr.py`; `python3 scripts/check-marketplace.py` after the commit
Risk: low.
- [ ] README section beside "Cross-session claims": the commands, the freeze rule, the binding, and
  what a peer can rewrite (anything on the channel, which only L-0634 detects).
- [ ] The guide's short section and a rebuild with `python3 docs/guides/crew/src/build.py
  --guide daily-workflow` (the guide files dropped `1.0` from their names since the spec was
  written).
- [ ] One verify rule for `crew_contract.py` and its suite; the code map names the module.
