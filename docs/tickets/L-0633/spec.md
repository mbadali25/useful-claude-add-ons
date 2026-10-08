# L-0633: cross-session dependencies `<channel>:<id>` in the autopilot wave          status: spec   risk: high
Split from T-0031. Written 2026-10-04 against origin/main 155fe6d8 (crew 1.0.322) and the unmerged branches `T-0029-wave` 574985ce and `T-0030-coord` ec9a28a2.
## Intent
`crew_wave.py plan` and `start` accept a dependency written `<channel>:<id>` (or `<channel>:<repo>:<id>`) in a set file's `deps` and in an INDEX row's `(depends on ...)`. Such a dependency is closed only when the channel `crew-coord/<channel>` was fetched and exactly one claim for that ticket reads `done`. Every other outcome keeps the ticket out of the wave, with the reason: `not closed` when the claim is `working` or `released`, `unknown` when the channel cannot be fetched, the claim is missing, corrupt or ambiguous.
## Exclusions
- No contract check and no hash comparison: T-0031 (the record) and L-0634 (the wave refusal).
- No edit to `crew_coord.py`; it is imported and read. No write to the channel: this slice only fetches and reads.
- No edit to any `HARNESS` path of `scripts/check-tooling-pr.py`: no `sabotage*.py`, no `crew_ticket.py`, no `scope_guard.py`. Sabotage for this slice is L-0635.
- No change to how local dependencies are judged, to the Touch-overlap rule, to lane launch, or to `collect`.
- No new config key. The remote is T-0030's `coord.remote` (default `origin`); the channel comes from the dependency text.
- No bridge message, no claim made or released on the peer's behalf, no automatic retry loop waiting for a peer.
- No new hook.
## Evidence
At origin/main 155fe6d8, checked 2026-10-04:
- Neither `crew_wave.py` nor `crew_coord.py` is on main (`git ls-tree -r --name-only origin/main | grep -E "crew_(coord|wave)"` prints nothing). `plugin/crew/hooks/scripts/crew_autopilot.py:224-226`: `SUBCOMMANDS` has no `wave`.
- `scripts/check-tooling-pr.py:58-87` `HARNESS`; `:79` `plugin/crew/tests/sabotage*.py`; `:65` `crew_ticket.py`.
- `plugin/crew/hooks/scripts/crew_ticket.py:193` `check_ticket` accepts a plain ticket id only.
- `plugin/crew/BUDGETS.md:10` crew-markdown-lines claim.

At `T-0029-wave` 574985ce (re-find by content after T-0029 lands):
- `plugin/crew/hooks/scripts/crew_wave.py:184-198` `write_set` passes every dep through `crew_ticket.check_ticket`; `:201-219` `_valid_set` does the same on read, so a set file carrying `chan:T-1` is `corrupt` today.
- `:233-235` `_DEPENDS_RE`, `_ID_RE`, `_DEP_FILLER_RE`; `:280-291` `_deps` returns None (unknown) when anything but ids, commas and "and" follows `depends on`, so `chan:T-1` in an INDEX row reads `unknown` today.
- `:294-304` `_dep_refusal`: `dependencies unknown`, `dependency <id> has no INDEX.md row`, `dependency <id> is not closed`. `:361` `_judge`, `:380` `plan`, `:982` `_parse_deps` (the CLI's `--deps`).
- T-0029's spec requires `plan` to write nothing in the tree, `.work/`, `<git-common-dir>/crew/` or the index.

At `T-0030-coord` ec9a28a2 (re-find by content after T-0030 lands):
- `plugin/crew/hooks/scripts/crew_coord.py:567` `Channel`, `fetch` using `git fetch --no-tags --no-write-fetch-head --refmap=` (no ref and no FETCH_HEAD written), `read(tip)`.
- `:167` `_CHANNEL_RE` `[a-z0-9][a-z0-9-]{0,63}`, `:171` `_REPO_RE`, `:163` `STATES = ("working", "done", "released")`, `:165` `CLAIMS = "claims/"`, `:1149` `parse_claim`, `:1177` `is_stale`, claim files named `claims/<repo>__<ticket>.json`.
## Unknowns
- **Both dependencies are unmerged**, and every branch anchor above can move. Resolved at implement by re-reading the landed files.
- **A fetch inside `plan`.** `git fetch --no-write-fetch-head --refmap=` adds objects to the object store and nothing else. T-0029's "plan writes nothing" test covers the tree, `.work/`, `<git-common-dir>/crew/` and the index, not `objects/`. Resolved at plan: confirm against the landed test; if it also pins `objects/`, the cross-session check moves to `start` only and `plan` reports such a dependency as `unknown (not fetched)`.
- **Trusting a peer's `done`.** A `done` claim is peer-written. It decides only whether this side may start, never an approval. Accepted as risk, as the parent direction states it.
- **Ticket ids on the peer side** may be Jira or SDP keys. The id half is matched with the same pattern the claim key allows, upper-cased as `crew_coord` does.
- Next free crew patch version is set at land time.
## Dependencies
Must land first:
- T-0029 (in-progress; local branch `T-0029-wave`, not on the shared remote) - the wave and its dependency judgement.
- T-0030 (in-progress; local branch `T-0030-coord`, not on the shared remote) - the channel and claim records.
- T-0031 is not required by this slice, but both edit crew docs and the version files; land T-0031 first to keep the version order simple.

Blocks: L-0634 (same function in `crew_wave.py`), L-0635, T-0032.
## Touch
- `plugin/crew/hooks/scripts/crew_wave.py`
- `plugin/crew/tests/test_crew_wave_coord_deps.py`
- `plugin/crew/README.md` - the dependency form and what each refusal means
- `plugin/crew/BUDGETS.md` - the crew-markdown-lines claim
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/verify.json` - add the new test file to the wave rule T-0029 adds
- `.crew/codemap/crew.md`
- `docs/guides/crew/src/troubleshooting.md` - the new refusal lines
- `docs/guides/crew/crew-1.0-troubleshooting.html` - rebuilt by the guide build script
- `docs/guides/crew/crew-1.0-troubleshooting.docx` - rebuilt by the guide build script
- `docs/guides/crew/crew-1.0-troubleshooting.pdf` - rebuilt by the guide build script
## Acceptance checks
Suite command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_wave_coord_deps.py plugin/crew/tests/test_crew_wave.py -q`. Tests use a local bare remote under `tmp_path`.
- [ ] Grammar: `chan:T-0001` and `chan:repo.key:T-0001` parse to (channel, repo or None, id). Refused as `dependencies unknown`: an empty half, a channel outside `[a-z0-9][a-z0-9-]{0,63}`, a fourth colon part, an id that is not a ticket id, whitespace inside the token (`test_cross_dep_grammar`, one parametrised row per form).
- [ ] A set file whose `deps` holds `chan:T-0001` is valid and round-trips through `write_set` / `read_set`; a set file with a malformed cross dependency is `corrupt`, never an empty dependency list (`test_set_file_accepts_and_validates_cross_deps`).
- [ ] An INDEX row `(depends on T-0004, chan:T-0001)` yields both dependencies; a row with a malformed one yields `unknown` (`test_index_row_cross_deps`).
- [ ] Must-allow: the peer claim `claims/<repo>__T-0001.json` reads `done` on a fetched channel, and the ticket is `eligible` (`test_done_peer_claim_closes_the_dependency`).
- [ ] Must-block, one test each, the ticket `refused` with the named reason and the lane never started: the claim is `working`; the claim is `working` and stale (reason carries the heartbeat age); the claim is `released`; no claim file for the id; two repositories on the channel both hold the id and the short form was used; the claim file is corrupt; the channel does not exist on the remote; the fetch fails; the remote is not configured.
- [ ] The long form picks one of two same-id claims and is judged on that claim alone (`test_long_form_disambiguates`).
- [ ] Local dependencies are judged exactly as before: T-0029's own dependency tests pass unchanged, and a ticket with only local dependencies causes no fetch (`test_no_cross_dep_means_no_fetch`, asserting no `git fetch` or `ls-remote` call).
- [ ] Nothing is written: after `plan` with a cross dependency, the working tree, `.work/`, `<git-common-dir>/crew/`, `HEAD`, every ref and `FETCH_HEAD` are unchanged, and no `git push` is ever called (`test_cross_dep_check_writes_nothing`).
- [ ] Refusal text labels the peer state as peer-written data and passes it through `crew_coord.safe` (`test_refusal_text_is_sanitised`, with a control character in a claim field).
- [ ] The README and the troubleshooting guide state the form and each refusal; the guide is rebuilt with `python3 docs/guides/crew/src/build.py`; `python3 scripts/check-tooling-pr.py` exits 0; crew is one patch above origin/main with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.
## Size
About 140 production lines in `crew_wave.py`: the dependency parser, the set-file and INDEX-row changes that call it, and the peer-claim lookup with its refusals.
## Open questions for the owner
1. Short form ambiguity: refuse as `unknown` and require the long form (taken), or prefer a claim from another repository over this one?
2. Should a `released` peer claim close the dependency? Taken: no.
3. Should `plan` be allowed to fetch, or only `start`? Taken: `plan` fetches, subject to the Unknown above.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
