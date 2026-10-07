# Cloud handoff: T-0506

**The repo's own pwsh gate launches run on a private startup-profile cache (`scripts/pwsh-isolated.sh`)**

INDEX title: "concurrent pwsh runs corrupt the shared ~/.cache/powershell startup profile; every later pwsh dies 'Stack overflow.'". The spec is narrower than that title; see below.

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (first handed to cloud on 2026-09-30; spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0506-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0506/direction.md`, `docs/tickets/T-0506/spec.md`
- **Size:** about 90 added production lines (the launcher about 70; `_verify/smoke.sh` and `_verify/run-all.sh` about 12 changed lines; `scripts/gate-runner.py` about 4; the verify rule is one line of configuration).
- **Harness:** no harness path. One feature PR. No file under `plugin/crew/` changes, so there is no crew version bump and the crew doc set does not apply; the PR body says `Docs: none for crew - no plugin/crew file changes`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0557 | merged (PR #300, `ffd11270`) | Established the startup-profile race as the cause and the `XDG_CACHE_HOME` mechanism this ticket reuses. Its static guard (`plugin/crew/tests/test_pwsh_cache_isolation.py`) scans the new `scripts/_test` suite this ticket adds. |

Nothing open blocks this ticket and it blocks nothing: none found in INDEX. It can be worked at any time.

Related, not blocking in either direction:

- L-0559 (direction): owns crew's `.ps1` hooks, the Windows question and the `DOTNET_MultiCoreJitMinNumCpus` alternative. If it adopts the knob, the launcher here is the single place to switch.
- L-0567 (direction): follow-up findings on L-0557's guard and `conftest.py`. It shares only `CHANGELOG.md` with this ticket.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. The launch-site line numbers in the first half of direction.md are older still (origin/main `8ab733d7`).
- No plan.md is published. The implementing session writes the plan.
- **Build the spec, not the top of direction.md.** The seed's scope (reproduce the race, one shared helper for every `_test` suite, crew hooks) is superseded by "Direction check 2026-10-04": L-0557 already measured the cause and isolated every test suite, and crew's `.ps1` hooks moved to L-0559. What is left is four non-test launch sites: the `**/*.ps1` rule in `.crew/verify.json`, `_verify/smoke.sh`, `_verify/run-all.sh` and the `check-powershell` step in `scripts/gate-runner.py`.
- `docs/handoff/cloud/T-0506.md` and its row in `docs/handoff/cloud/README.md` are on main from the first hand-off (2026-09-30). The spec is newer and wins where they differ. This ticket's PR deletes that file and its row.
- The spec cites `.work/tickets/L-0557/spec.md` and `.work/tickets/L-0559/direction.md` as evidence. `.work/` is not tracked, so a cloud session cannot read them. The same facts are in `CHANGELOG.md` (L-0557's entry) and `plugin/crew/README.md`, both cited in the spec.
- The launcher is POSIX sh with LF line endings. If the private cache directory cannot be created, pwsh is not started on the shared cache.
- The launcher never changes pwsh's exit status and never retries. A signal death only adds one `TOOL BROKEN: pwsh` stderr line.
- A TERM or INT to the launcher must end the pwsh child: `run-all.sh` wraps the call in `timeout`, which signals only its direct child.
- stdin is `/dev/null`: `smoke.sh` calls pwsh inside a `while read` loop.
- Not edited: any file under `plugin/crew/` (including `verify-gate.*`, which is harness), `test_pwsh_cache_isolation.py`, `conftest.py`, `scripts/install-prerequisites.sh`, and `plugin/crew/tests/test_crew_shell.py` (its copy of the verify map is frozen on purpose).
- A suite added to `.github/workflows/marketplace.yml` needs a matching step in `scripts/gate-runner.py`'s table, and the reverse; the gate runner's own suite checks the two against each other.
- The suite never reads or writes the real per-user cache. It uses a stub `pwsh` under `mktemp`.
- If `scripts/check-marketplace.py` asks for a version bump, that is a STOP, not a bump to add.
- The PR body states what was not verified: Windows and Git Bash behaviour of the launcher, and `scripts/_test/drift-detection.sh`.
- Nothing was run when the spec was written: no suites, no pwsh, no gate.
- The two "Owner decision 2026-09-30" sections in direction.md were written for local lanes. Merge, never rebase, still applies. The heavy-run wrapper is a local tool and is not in the repo; whether a cloud session needs an equivalent could not be told.

## Open questions for the owner (recommended option taken)

1. Mechanism: a private `XDG_CACHE_HOME` per run, the same as merged L-0557. Alternative: the `DOTNET_MultiCoreJitMinNumCpus=1024` knob once L-0559 settles it. The knob is undocumented and untested on Windows.
2. Windows: "unchanged on Windows, tracked under L-0559" is taken as acceptable. Alternative: a burn-in on a Windows machine before landing. Nobody has measured whether the race exists there.
3. Should crew's verify gate give every rule it runs a private cache, protecting repos that use crew? That edits `verify-gate.*` (harness paths), so it would be a separate tooling-only ticket. Not in this spec; no ticket filed.
4. The ticket was already marked "handed to cloud, do not pick up locally". Only direction.md (appended) and spec.md (new) were written locally as preparation; confirm that is what was wanted.

## Before landing

Merge origin/main, follow the repo's CLAUDE.md (scope discipline, tooling-PR rule; no crew version is needed because `plugin/crew` is not touched), and remove `docs/tickets/T-0506/` in the final PR unless the owner wants it kept.
