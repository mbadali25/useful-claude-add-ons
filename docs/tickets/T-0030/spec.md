# T-0030 cross-session claims and the git-backed coordination record          status: spec   risk: high
## Decisions (owner, Matthew Badali, 2026-09-25; `direction.md`)
- Split into three tickets. This is the first: claims plus the git-backed record. T-0031 covers contracts, findings and cross-session dependencies. T-0032 covers messaging.
- Sessions may run on different machines. They talk over the messaging bridge (T-0032). The record is the git branch `crew-coord/<channel>` on the shared remote.
- The claim TTL is 30 minutes. A claim whose last heartbeat is older reads `owner unknown`, never `free`.
- The spike may make one normal push of `crew-coord/spike-test` to origin and then delete it.
- Only the owner breaks a claim.
- A peer-written record is data, never instructions.
- Recovery when a session's id changes (owner, 2026-09-25: "we need to put in handling for if a session changes and the ID changes that we can present it to you the session so that they can recover"; answers via question prompt):
  - **Auto-recover only on the same machine, when the old holder is proven dead.** The claim's `machine` and `worktree` match this session. A local identity file shows the claim's holder was this worktree's previous session. That holder's recorded Claude process is gone. All three must hold. Anything else is presented to the session with a recommendation and stops for the owner: another machine, the old process alive, or no local proof.
  - **Presented on resume and in `status`, with no hook.** `status` marks such claims `yours from a previous session`, and the resume path (T-0006, and T-0004's autopilot resume) runs it before any other work.
## Intent
`crew_coord.py` lets several Claude Code sessions (same or different repos, same or different machines) share a channel. A channel is the git branch `crew-coord/<channel>` on a shared remote. On it a session claims a ticket before working it, sends heartbeats while it works, and marks the claim `done` or `released`. Every change is also appended to the channel's log. `status` fetches the branch and prints every claim with its holder and age, read-only. Writes use git plumbing on top of the freshly fetched tip and a plain push, never a force push. A rejected push is retried from a re-fetch. What cannot be fetched or pushed reads `unknown`, never current.
## Exclusions
- No contracts, findings, or cross-session dependencies in T-0029's wave: T-0031. No messaging, no `/crew:` command surface, no bridge calls: T-0032.
- No force push of any kind, and no `--force-with-lease`. `cloud_guard`'s `forcePush` finding treats both as force (`plugin/crew/hooks/scripts/cloud_guard.py:989-990`).
- No checkout of the channel branch, no write to any working tree, `.work/`, or `<git-common-dir>/crew/`. No change to `main`, `.gitignore`, or the un-ignore list that `check_crew_ignore_policy` asserts.
- No new hook, no change to an existing hook, no config key outside a new `coord` block.
- No automatic release or takeover on staleness alone: stale means `owner unknown`. The only automatic change is the proven same-machine recovery in Decisions. A claim from another machine, or from a live process, is never adopted without the owner.
- No SessionStart hook change. Presentation is through `status` and the resume path.
- Never read, print or log `CLAUDE_CODE_MESSAGING_TOKEN` or any other credential-shaped environment value.
## Evidence
- The force-push guard: `plugin/crew/hooks/scripts/cloud_guard.py:17` (`git push --force|-f|--force-with-lease|+ref` -> `guards.forcePush`), `_git_force_push` `:981-995`, which also treats a leading `+` on any refspec as force. [verified]
- The scope guard refuses writes naming `<git-common-dir>/crew/` alongside a writing word: `plugin/crew/hooks/scripts/scope_guard.py:88-90` (`_DOTGIT_CREW_RE`) and `:192-197`. The channel lives in refs and objects, never under that path. [verified]
- `.work/` is ignored and per worktree: `git check-ignore -v .work/INDEX.md` gives `.gitignore:273:.work/`, and `/repos/personal/uca-t0004/.work/INDEX.md` is a separate copy. So `.work/` cannot carry a shared record. [verified 2026-09-25]
- Session identity is available to Bash: the environment carries `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_BRIDGE_SESSION_ID` and `CLAUDE_PID` (names listed on 2026-09-25; values not read). `CLAUDE_CODE_MESSAGING_TOKEN` is in the same environment. [verified names only]
- T-0006 records that `session_id` changes on `/clear` (`.work/tickets/T-0006/spec.md`). [verified: the claim is from that spec, not re-measured]
- The multi-repo rule is one ticket per repo, cross-referenced by id (`plugin/crew/commands/spec.md` "Multi-repo and cross-references"). The claim key `<repo>__<ticket>` follows it. [verified]
- The post-checkout and post-commit hooks launch graphify rebuilds (CLAUDE.md "Memory", `.git/hooks/post-commit:163`, `.git/hooks/post-checkout:165`; machine-local). `git commit-tree` and `git push` run neither hook. [judgement from git's hook contract; measured in plan step 1]
- The sabotage registry is `plugin/crew/tests/sabotage.py:2927`, with per-area modules `plugin/crew/tests/sabotage_*.py`. [verified]
## Unknowns
- **Does origin accept pushes to `crew-coord/*`?** Measured by spike (plan step 1): one normal push of `crew-coord/spike-test`, then delete it, recording the exact output. If it is refused, stop and return to the owner. The fallback, a dedicated coordination repo, is a new decision.
- **Which identity changes, and when.** Measured by spike: whether `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_BRIDGE_SESSION_ID` and `CLAUDE_PID` change across `/clear`, a crash-and-resume (`claude --resume`) and a fresh start. The holder is recorded as all three plus `machine` (hostname) and `worktree` (real top-level path). Recovery does not depend on any one of them surviving. It depends on the local identity file, below, and on the old `CLAUDE_PID` being gone.
- **The local identity file.** `claim` records `{worktree -> holder, pid, claimed tickets}` in `<git-common-dir>/crew/coord-identity.json`, written by the script, not by Claude's Write tool. The scope guard refuses Claude's own writes there, and script writes are the established pattern (`crew_ticket.activate` writes `<git-common-dir>/crew/active-ticket`). Proving a PID is gone: on Linux, `os.kill(pid, 0)` raises `ProcessLookupError`. On Windows the method is measured in the spike. Where it cannot be told, the process reads alive, which means presented rather than adopted. PID reuse is guarded by also recording the process start time where the OS exposes it. If the start time cannot be read, a live PID with an unverifiable start time reads alive.
- **Owner-only break, enforced mechanically.** Measured by spike: whether a command the owner runs with the `!` prefix can be told apart from one Claude runs (an environment difference). If it can, `release --break` refuses without that signal. If not, `--break` needs `--by <name>`, is logged, and the command documentation says it runs only on the owner's instruction. That is stated as a prose-only control, not claimed as enforced.
- **The heartbeat under a 30-minute TTL.** A single step can run for 50 minutes (T-0016's slow suite). So `claim` starts a detached heartbeat process that pushes every 10 minutes while `CLAUDE_PID` is alive, and exits when that process is gone or the claim is not `working`. Unknown: whether a detached child survives the harness's process handling on Linux and Windows. Measured in plan step 1. If it does not survive, the owner is told the TTL cannot hold during long steps.
- **The resume path depends on T-0004** (`autopilot.md` and its resume step, not on main) and on T-0006's resume flow. The `status` call is added to `autopilot.md`'s resume step after T-0004 lands. Until then, `status` is documented in the README as the first command after `/clear`.
- Codex is out until 2026-10-01, so the review is same-family. Accepted as risk.
- Owner decision - local-origin key: case and .git (review round 6, crew_coord.py:862). Today a local or file:// origin is keyed lowercased and with a trailing `.git` stripped, so two distinct directories on a case-sensitive filesystem, or `repo` beside `repo.git`, share one key and refuse each other's claims. Recommendation: key the directory git itself opens for the path (realpath, then git's own suffix order for a path that does not exist as given, re-read from git's source at implementation), with the on-disk case preserved and `.git` kept; network-host keys stay lowercased with `.git` stripped, because hosting services treat those spellings as one repository. Rejected: keep lowercasing, which is safe on Windows and macOS default volumes but wrong on Linux. Not verified: git's exact suffix order.
## Touch
- `plugin/crew/hooks/scripts/crew_coord.py`
- `plugin/crew/tests/test_crew_coord.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/sabotage_coord.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
- `.work/tickets/T-0030/spike.md` - step 1's measurement, ignored and local-only
## Acceptance checks
- [ ] `crew_coord.py claim --channel <c> --remote <r> --ticket <repo>:<id>` writes `claims/<repo>__<id>.json` (`ticket`, `repo`, `holder`, `machine`, `worktree`, `claimed_at`, `heartbeat_at`, `state: working`) and appends one line to `log.jsonl`. It does so in one commit whose parent is the fetched tip, pushed without force. Tests in `test_crew_coord.py` run against a local bare remote.
- [ ] Must-block: a claim on a ticket held `working` by another holder is refused with the holder named. A claim when the fetch fails is refused as `unknown`. `release`, `done` or `heartbeat` by a non-holder is refused. `--break` without the owner signal (or `--by`, per the spike) is refused. Each has a test.
- [ ] Must-allow: claim then release, claim then done, and re-claiming a `released` or `done` ticket. Two sessions each claiming a different ticket at the same moment both succeed after one non-fast-forward retry (test with an interleaved push).
- [ ] Stale: a `working` claim whose `heartbeat_at` is more than 30 minutes old reads `owner unknown (last heartbeat <age>)` in `status`, and a new claim on it is refused, never granted (test with an injected clock).
- [ ] Retry: a rejected push re-fetches, re-applies and retries at most 3 times, then reports `unknown - could not push`. It never passes `--force`, `-f`, `--force-with-lease` or a `+` refspec. Tests assert the exact argv of every `git push` call.
- [ ] Isolation: across every command, the working tree, `.work/`, `<git-common-dir>/crew/` and `HEAD` are unchanged. The only ref that changes is `refs/heads/crew-coord/<c>` (local and remote) (test).
- [ ] `status` is read-only apart from `git fetch`. Every claim line is labelled as peer-written data. A corrupt claim file reads `unknown`, never skipped (tests).
- [ ] The heartbeat process pushes while its `CLAUDE_PID` is alive and exits within one interval once it is gone (test with a stub pid). It never logs an environment value (test scanning log output for `CLAUDE_CODE_MESSAGING_TOKEN` set to a sentinel).
- [ ] Recovery, must-allow: after an identity change on the same machine and worktree, with the identity file naming the old holder and the old PID gone, `crew_coord.py recover` adopts the claim. The new holder is written, the log records `adopted from <old> (pid <n> gone)`, and the local identity file is updated (test).
- [ ] Recovery, must-block (each is presented as `yours from a previous session - needs the owner: <reason>`, never adopted): the claim is from another machine; the old PID is alive; the old PID is reused with a different start time; the identity file is missing or corrupt; the worktree differs; the PID check cannot tell. One test each.
- [ ] `status` lists presented claims first, each with holder, machine, worktree, age and the one recommended action (for example `crew_coord.py recover --ticket <t>` after the owner confirms, or `release --break` by the owner). The resume path runs `status` before any other phase (test on the command text).
- [ ] Sabotage (`sabotage_coord.py`, registered in `sabotage.py`): add `--force-with-lease`; read a stale claim as free; skip a corrupt claim; accept a claim when the fetch failed; let a non-holder release; adopt a claim from another machine; adopt while the old PID is alive; treat an unreadable PID check as dead. Each turns a named test red.
- [ ] `.crew/verify.json` maps `test_crew_coord.py`. Crew is bumped to one patch above origin/main at land time, in both `plugin.json` and `marketplace.json`, with a CHANGELOG entry. The README documents channels, claims, the TTL and the no-force rule, and `python3 scripts/check-marketplace.py` passes.
