# L-0633 plan: `<channel>:<id>` dependencies in the autopilot wave          spec: docs/tickets/L-0633/spec.md

Written by the implementing session (rush lane g3c-contracts, 2026-10-05) on a base carrying T-0029
(`crew_wave.py`) and T-0030 (`crew_coord.py`) as ported by rush g0, plus T-0031 from this lane.

Anchors re-found by content in the ported files:
- `crew_wave.py`: `write_set` and `_valid_set` pass each dep through `_plain_id` (the port's
  hardened `crew_ticket.check_ticket` plus no newline); `_DEPENDS_RE`, `_ID_RE`, `_DEP_FILLER_RE`
  and `_deps` read the INDEX row; `_dep_refusal`, `_judge`, `plan`, `start` and the CLI's
  `_parse_deps` are as the spec describes.
- `crew_coord.py` public names used: `Channel` (`fetch`, `read`), `run_git`, `CLAIMS`,
  `claim_path`, `parse_claim`, `is_stale`, `ttl_minutes`, `describe`, `parse_ticket` (validates and
  upper-cases the id), `safe`, `peer`, `UsageError`. `_CHANNEL_RE` and `_REPO_RE` are private, so
  `crew_wave.py` states the same two rules itself; `crew_coord.py` is not edited.
- T-0029's write-nothing test (`test_plan_writes_nothing`) snapshots the tree, `<git-common-dir>/crew/`
  and the index mtime, not `objects/`, so `plan` fetches (the spec's taken option 3).

### Step 1: the grammar, the set file and the INDEX row
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave_coord_deps.py
Test: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_wave_coord_deps.py plugin/crew/tests/test_crew_wave.py -q`
Risk: high. A malformed dependency read as none would start a lane early.
- [ ] `cross_dep(value)`: (channel, repo or None, id) for two or three non-empty parts with no
  whitespace; channel `[a-z0-9][a-z0-9-]{0,63}`, repo the derived repo key's rule with no `__`/`..`,
  id through `crew_coord.parse_ticket`. Anything else is `TicketError`.
- [ ] `write_set`, `_valid_set` and `--deps` accept a valid cross dependency; a malformed one is
  refused on write and makes the set file `corrupt` on read.
- [ ] `_deps` takes whole `:`-tokens out of the `depends on` text, validates each, and reads the
  rest exactly as before; any malformed token is `None` (dependencies unknown). Row order is kept.

### Step 2: the peer claim
Files: plugin/crew/hooks/scripts/crew_wave.py, plugin/crew/tests/test_crew_wave_coord_deps.py
Test: as Step 1
Risk: high. Only `done` may close a dependency; everything that cannot be told is `unknown`.
- [ ] `_dep_refusal` judges local dependencies first, then cross ones, so a local refusal fetches
  nothing; `plan` passes one cache per call, so a channel is fetched once.
- [ ] `_channel_files`: `coord.remote` (default `origin`) must be a configured remote; a failed
  fetch, an absent channel or an unreadable tree is `unknown`.
- [ ] `_cross_refusal`: exactly one `claims/<repo>__<ID>.json` (any repo for the short form) or
  `unknown`; a corrupt claim `unknown`; `done` closes; `working` (with `owner unknown` when stale)
  and `released` are `not closed`. Peer fields through `crew_coord.describe`/`safe`, `[peer-written]`.

### Step 3: docs, verify rule
Files: plugin/crew/README.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/crew-troubleshooting.html, docs/guides/crew/crew-troubleshooting.docx, docs/guides/crew/crew-troubleshooting.pdf, .crew/verify.json, .crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: `python3 scripts/check-tooling-pr.py`; `python3 scripts/check-marketplace.py` after the commit
Risk: low.
- [ ] README paragraph after `wave`; the troubleshooting table of refusals, rebuilt with
  `python3 docs/guides/crew/src/build.py --guide troubleshooting` (the guide files dropped `1.0`
  from their names since the spec was written).
- [ ] The wave rule in `.crew/verify.json` gains the new test file; the code map names the change.
