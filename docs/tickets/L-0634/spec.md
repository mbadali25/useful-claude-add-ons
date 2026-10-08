# L-0634: the wave refuses a ticket whose built-against contract hash no longer matches          status: spec   risk: high
Split from T-0031. Written 2026-10-04 against origin/main 155fe6d8 (crew 1.0.322). It builds on T-0031 (`crew_contract.py`, not yet written) and on the unmerged branch `T-0029-wave` 574985ce.
## Intent
A ticket that recorded "built against contract `<name>` v`<N>` with hash H" is refused by the wave when the channel no longer shows that version with hash H, a body whose sha256 is H, status `built-against` and this ticket in `built_by`. The same check is available on its own as `crew_contract.py verify --ticket <id>`: exit 0 when every binding holds, exit 1 on a mismatch, exit 3 when it could not tell.
## Exclusions
- No change to how a contract is written or frozen: T-0031. No `<channel>:<id>` dependency: L-0633.
- No edit to any `HARNESS` path of `scripts/check-tooling-pr.py`. Sabotage for this guard is L-0635.
- No automatic repair: the check never rewrites a binding, a record or a body, and never picks the newer version.
- No write to the channel, no push. No hook, no config key.
- A ticket with no `.work/tickets/<id>/contracts.json` is not checked and causes no fetch.
- No check at implement, review or done time in this slice; only `verify` and the wave's `plan` / `start`.
## Evidence
At origin/main 155fe6d8, checked 2026-10-04:
- Neither `crew_wave.py` nor `crew_contract.py` exists on main.
- `scripts/check-tooling-pr.py:58-87` `HARNESS`.
- The precedent for a mechanical stale check: `plugin/crew/hooks/scripts/crew_ticket.py:687` `accepted`, which demotes a receipt that no longer matches instead of trusting it.

At `T-0029-wave` 574985ce (re-find after T-0029 lands):
- `plugin/crew/hooks/scripts/crew_wave.py:361` `_judge(top, ticket, given)` returns the per-ticket refusal; `:380` `plan`; `:537` `start`; `:640` `lane_init` copies the ticket folder into the lane, so the bindings file travels with it.

From T-0031's spec (`.work/tickets/T-0031/spec.md`, Decisions): the record `contracts/<name>/v<N>.json` with `hash`, `status`, `built_by`; the body `contracts/<name>/v<N>.body`; the binding file `.work/tickets/<id>/contracts.json` with `{"schema": 1, "bindings": [{"channel", "name", "version", "hash"}]}`.
## Unknowns
- **T-0031 and T-0029 are not on main.** Names and line numbers are re-read after they land.
- **Order inside `_judge`.** Whether the contract check runs before or after the dependency check changes only which reason is printed first. Resolved at plan: after dependencies, so the cheaper local refusals come first.
- **A binding copied into a lane worktree goes stale if the main checkout re-binds.** Accepted as risk: `start` checks from the main checkout before any lane is launched.
- Next free crew patch version is set at land time.
## Dependencies
Must land first:
- T-0031 (ready; this hand-off's first slice) - the contract record and the binding file.
- T-0029 (in-progress; local branch `T-0029-wave`) - the wave.
- T-0030 (in-progress; local branch `T-0030-coord`) - the channel.
- L-0633 - not a functional dependency, but it edits the same function in `crew_wave.py`; land it first so the two do not conflict.

Blocks: L-0635, T-0032.
## Touch
- `plugin/crew/hooks/scripts/crew_contract.py`
- `plugin/crew/hooks/scripts/crew_wave.py`
- `plugin/crew/tests/test_crew_contract_verify.py`
- `plugin/crew/README.md` - the verify command and the wave refusal
- `plugin/crew/BUDGETS.md` - the crew-markdown-lines claim
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/verify.json` - add the new test file to the contract rule and the wave rule
- `.crew/codemap/crew.md`
- `docs/guides/crew/src/troubleshooting.md` - the new refusal line and what to do about it
- `docs/guides/crew/crew-1.0-troubleshooting.html` - rebuilt by the guide build script
- `docs/guides/crew/crew-1.0-troubleshooting.docx` - rebuilt by the guide build script
- `docs/guides/crew/crew-1.0-troubleshooting.pdf` - rebuilt by the guide build script
## Acceptance checks
Suite command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_contract_verify.py plugin/crew/tests/test_crew_contract.py plugin/crew/tests/test_crew_wave.py -q`.
- [ ] Must-allow: after `build-against`, with the channel unchanged, `verify --ticket <id>` exits 0 and names each binding as current (`test_verify_passes_on_an_unchanged_contract`).
- [ ] Must-allow: a newer `draft` version on the channel does not refuse; it is printed as information (`test_a_newer_draft_does_not_refuse`).
- [ ] Must-block, exit 1, one test each, the message naming the contract, the version and the ticket: the record's `hash` differs from the binding's; the body's sha256 differs from the record's `hash`; the record's `status` is `draft` again; this repo and ticket are missing from `built_by`.
- [ ] Unknown, exit 3, one test each: the fetch fails; the channel is absent; the version's record or body file is missing; the record is corrupt; the bindings file is not JSON, has another `schema`, or has a binding with a missing field. None of these is read as "no bindings".
- [ ] A ticket with no bindings file exits 0 and makes no `git fetch` or `ls-remote` call (`test_no_bindings_means_no_fetch`).
- [ ] The wave: `crew_wave.py plan` marks a ticket `refused: contract <name> v<N> changed since <ticket> built against it` on a mismatch and `refused: contract <name> v<N> unknown (<why>)` when it cannot tell; `start` launches no lane for it; other tickets in the set are unaffected (`test_wave_refuses_a_contract_mismatch`, `test_wave_refuses_an_unknown_contract`, `test_wave_other_tickets_still_eligible`).
- [ ] Nothing is written by the check: tree, `.work/`, `<git-common-dir>/crew/`, `HEAD`, refs and `FETCH_HEAD` unchanged, no `git push` called (`test_verify_writes_nothing`).
- [ ] Peer-written fields in every message go through `crew_coord.safe` (`test_verify_messages_are_sanitised`).
- [ ] The README and the troubleshooting guide describe the refusal and the owner's way out (a new contract version and a new ticket on each side); the guide is rebuilt with `python3 docs/guides/crew/src/build.py`; `python3 scripts/check-tooling-pr.py` exits 0; crew is one patch above origin/main with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.
## Size
About 110 production lines: `check_bindings` and the `verify` command in `crew_contract.py` (about 80), the call and its two refusal lines in `crew_wave.py` (about 30).
## Open questions for the owner
1. Should the same check also run at `/crew:done`? Taken: not in this slice; it would touch harness-adjacent commands and belongs in a follow-up if wanted.
2. Is a newer draft version information only (taken), or should it stop the wave for the owner?

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
