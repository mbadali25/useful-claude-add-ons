<!-- Moved verbatim from plugin/crew/README.md (25. Command and agent reference) by L-0726; the README keeps an index entry. -->

### Hooks

Fourteen scripts across eight events, run by one dispatcher behind 16 hook entries<!-- claim: plugin-hooks:crew -->:
`hooks.json` registers one launcher per event per shell (`crew-hook.sh`, and `crew-hook.ps1` with
`shell: powershell`), and the launcher starts `crew_hook.py <Event>`, which runs that event's scripts below
(L-0850). The table lists the scripts, which are unchanged; the `.sh` is the one that runs. crew 1.0 removed
`pm-brief` and `pm-pulse`.

| Script | Event | Behavior |
|---|---|---|
| `promote-gate.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | Refuses a declared `deploy` command (on either tool also a workflow dispatch of a declared deploy workflow, either spelling; T-0062, L-0664) unless the upstream environment's newest row for **this sha**, written in full, is all-pass, the rollback runbook is verified inside 90 days, `requireHuman` is approved, an accepted review receipt covers this tree (or the environment opts out with `requireReview: false` + `reviewReason`), and the tree the deploy runs from (payload `cwd`, leading `cd`, `git -C`; same repository) is clean and at that sha. During an emergency lane it records each unmet precondition and allows the deploy (§24) |
| `cloud-guard.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | **Off by default** (`guards.cloudGuard`). Judges destructive cloud, Terraform and SQL commands and force push against the pinned `cloud.*` identity — see [Cloud guard](11-configuration-reference.md#cloud-guard) |
| `env-guard.sh` / `.ps1` | `PreToolUse` on Bash / PowerShell | **Off by default** (`guards.envGuard`, L-0772). Refuses a command whose own text prints the whole environment or a credential-named variable into the agent's context — see [Environment guard](11-configuration-reference.md#environment-guard) |
| `role-write-guard.sh` / `.ps1` | `PreToolUse` on Write / Edit | **Off by default** (`guards.roleWrites`: `block`/`report`/`off`). Keyed on the calling subagent's `agent_type`; enforces a role's write scope mechanically — CONFIG.md §18 |
| `approval-hook.sh` / `.ps1` | `UserPromptSubmit` | Records a ticket's plan approval only when the prompt *you* typed is `/crew:approve <id>`: validates `spec.md` and `plan.md` and writes the receipt bound to both hashes, or blocks the prompt and says why. Any other prompt: no output, exit 0 |
| `scope-guard.sh` / `.ps1` | `PreToolUse` on Write/Edit/MultiEdit/NotebookEdit/Bash/PowerShell | **Off by default** (`scope.mode`: `off`/`report`/`block`/`auto`; `/crew:init` writes `auto` for a new repo). Refuses an edit with no current approval or outside the spec's Touch, and a shell command that runs `crew_ticket.py approve` or writes crew state — see "Scope and approval" |
| `completion-audit.sh` / `.ps1` | `Stop` | **Off by default**, same `scope.mode`. Diffs the whole tree against the ticket's start commit, not counting a path byte-identical to merged main (T-0100), and blocks the stop once if any changed path is outside Touch, shell-made writes included. With no usable python it blocks once unless `scope.mode` is provably off; in the `.ps1` a probe that ran out of time says "the python probe timed out" and prints its `python probe:` trail (L-0690) |
| `handoff-read.sh` / `.ps1` | `SessionStart` | Resets its once-per-session markers. Prints the handoff after clear, compact, or resume only when `memory.inject` is false (the context hook injects it otherwise) — first archiving it instead, under `.crew/handoffs/`, if age or reality drift (its `head`/`branch` no longer describing the checkout) says it is stale |
| `crew-context.sh` / `.ps1` | `SessionStart`, `UserPromptSubmit`, `PostToolUse` on Read/Edit/Write/MultiEdit and vault MCP tools, `SubagentStart` | **On by default since 1.0.0; `memory.inject: false` in `.crew/config.json` turns it off, and then it emits and logs nothing.** Injects branch/HEAD, code-map anchor state and the handoff at SessionStart, budgeted code-map slices and vault-labelled recall per turn (each recall passes the repo's project, `memory.recall.projects` or the main checkout's folder name, as `--project`, retrying once without it on a CLI that predates the option), and is the only channel that reaches a dispatched subagent (`SubagentStart`). Never blocks. `handoff-read` stops printing the handoff while this is on, so the two never inject it twice |
| `platform-sync.sh` / `.ps1` | `SessionStart` | Detects this machine and repairs the `platform` block in `.crew/config.json` — see §3b. The only hook that writes config: the seven derived facts, plus recreating the whole file from defaults when it is missing or malformed (backing up a malformed one first) — never when `.crew/` itself does not exist. See "The config heals itself" in §3 |
| `verify-gate.sh` / `.ps1` | `Stop` | Runs the checks the changed paths map to that fit `verify.stopBudgetSeconds`; fails the turn on red, on a changed path with no rule, or on a deploy that recorded no promotion row - never on a deferral alone: a rule over the budget on its own is named NOT VERIFIED, deferred to CI (L-0710). A turn where 0 rules ran says so and writes no verified marker. A rule passes only on a completion record its wrapper writes; a killed, never-started or unrecorded rule is FAILED as COULD NOT TELL (T-0082). Stands down while an emergency lane is open (§24), recording what did not run. Since 1.2.39 (L-0796) the Stop path is quiet: one verdict line (`FAILED n cmd \| PASSED n cmd \| NOT VERIFIED n item(s) (...) \| credited n \| budget \| detail: .crew/.verify-gate.log`), then every failure verbatim, and the pricing, reach, deferral, tree-credit, env-pin and timing lines go to `.crew/.verify-gate.log`; a repeat of the same failure in the same session prints one `unchanged since last Stop` line naming the log (still exit 2). `--verbose` / `CREW_VERIFY_VERBOSE=1` restores the full text; `--ci`, `--all` and `--price` are always verbose |
| `context-watch.sh` / `.ps1` | `Stop` | Measures window occupancy from the transcript; asks for a handoff once per session at the later of `warnAt` and `reserveTokens` remaining, or instructs a wrap-up if `context.autoWrapUp` is on; with `context.autoClear.wrapUp` armed, sends the wrap-up procedure and feeds a refused wrap-up back once |
| `handoff-write.sh` / `.ps1` | `PreCompact` | Snapshots the transcript, writes a skeleton handoff |
| `notify.sh` / `.ps1` | `Notification` (`hook`) | Thin wrappers around `crew_notify.py`: a `question` ping for the permission and elicitation types only, never `idle_prompt`, one per waiting episode. `/crew:promote` calls `notify.sh deploy ... --outcome` itself. Outbound only; never reads. |

**Registration and dispatch.** `hooks.json` has no hook script paths in it: eight events, two entries each.
`crew_hook.TABLE` is the contract for what a launcher runs (event, matcher, script, argument, timeout,
whether it can block, the PowerShell twin, the Codex matcher), `crew_instructions.py` renders `hooks.json`
and the Codex hooks file from it, and `tests/test_hooks_json_shape.py` holds them equal. The dispatcher runs
the event's rows at once with the payload bytes it was given, and combines what they print:

- exit 2 from any script wins, with each blocker's stderr;
- `permissionDecision` is deny over ask over allow;
- `decision: "block"` and `continue: false` win;
- `additionalContext` and `systemMessage` are joined in order, and plain stdout is folded into
  `additionalContext` when another script printed JSON.

In a repo crew governs ("armed": a repo config, a linked worktree's main checkout config, or the machine
config) a dispatcher fault, a missing script or a guard past its timeout is exit 2 with the cause named, on
`PreToolUse`, `UserPromptSubmit` and `Stop`; anywhere else it is exit 0. Without python the POSIX launcher
runs the scripts itself and each script's own fallback decides. The design, the merge rule and the latency
figures are in [ADR 0009](../../adr/0009-hook-single-dispatch.md).

**Every hook is inert until a repository has `.crew/config.json`.** Installing the
plugin arms nothing; `/crew:init` in a given repo is what turns the gates on there.
That is deliberate - a gate that fired in every repository you opened would be
hostile - but it does mean "I installed crew and nothing happened" is the expected
first experience, not a fault. Check with `ls .crew/` before concluding a hook is
broken.

Hooks are deterministic. That is their whole value — a hook cannot be argued out of blocking `terraform apply`, and an agent can.

### Four suites, and what each can actually prove

```bash
bash   hooks/scripts/_test/run-tests.sh           # 177 cases - the hooks
bash   hooks/scripts/_test/setup-walkthrough.sh   # 32 cases - the setup scripts
python hooks/scripts/_test/validate-prompts.py    # 298 checks - command/agent structure
pytest tests/                                     # 1404 passed, 1 skipped - the python modules and both hook flavours
```

Those four figures were measured at `61af85cb`, and each is the line that suite
**printed on the run** rather than a count of anything read: `RESULT: 177 passed,
0 failed`, `SCRIPT PHASES: 32 passed, 0 failed`, `PASS: 298 checks`, and pytest's
own `1404 passed, 1 skipped` (the skip is a platform case — see the table below).
Three of the four were stale by more than a factor of two before this correction,
because each is written by hand and nothing checks it:
`scripts/check-marketplace.py` only verifies a statement carrying a
`<!-- claim: ... -->` marker, and none of its marker types (`check_self_claims`
lists them: counts, versions, the active config file, the command table and the
eval roster) can express a suite count. No marker is available for these, so re-run the suite rather than trusting
the comment.

| Suite | Proves | Cannot prove |
|---|---|---|
| `run-tests.sh` | Every gate blocks and allows what it should | - |
| `setup-walkthrough.sh` | Phases 0-8 scripts run against a real mixed-stack repo and produce their artifacts | that a human would like the result |
| `validate-prompts.py` | Frontmatter parses, tools are real, referenced agents and paths exist, read-only agents hold no write tools, commands that spawn subagents are permitted to | **whether the prompts produce good work** |
| `pytest tests/` | The python modules, and that the `.sh` and `.ps1` flavours of `context-watch`, `verify-gate` and `promote-gate` agree - including the emergency lane's expiry, which is the one property that keeps a forgotten incident from ungating a repo forever | anything on a platform the suite is not running on; the Windows-only cases skip elsewhere |

Every pwsh those suites spawn runs with a throwaway `XDG_CACHE_HOME` of its own
(L-0557). pwsh reads its multicore-JIT startup profile from
`$XDG_CACHE_HOME/powershell/StartupProfileData-NonInteractive` at start-up and
rewrites it at exit, so concurrent pwsh sharing `~/.cache/powershell` race on one
file, and the loser dies before running a statement ("Stack overflow.", exit -6,
or SIGSEGV, -11). `tests/conftest.py` sets the variable per test and refuses, by
audit hook, a pwsh spawned without it; `tests/test_pwsh_cache_isolation.py` scans
every `tests`/`_test` suite in the repo, Python and shell, for a pwsh spawn that
would skip it. There is no retry. Windows pwsh keeps the profile under
`LOCALAPPDATA`, so the variable changes nothing there.

Every test also runs under a home of its own (L-0709): `tests/conftest.py`
points HOME, USERPROFILE and the XDG config, data and state directories at a
throwaway directory per test, so a crew script a test spawns reads an empty
`~/.claude/crew/config.json`, not yours. Before this, a machine layer holding
`autopilot.*` keys failed `test_status_mode_line_reads_off_by_default` and the
`crew-context.sh` inject-off cases on the owner's machine while CI, which has
no user layer, stayed green. An audit hook fails any test that opens a file
under the real home (checked before the open; an import path inside
`~/.claude` other than the interpreter's own exempts nothing; a symlink swapped
in after the check is a known limit, L-0761) or spawns a process with the real
HOME, naming the path;
`tests/test_hermetic_home.py` holds it, with a regression run against a planted
home that carries those keys. A test that is a known timing flake is not
skipped: it carries `@pytest.mark.quarantine(owner=..., ticket=...)`, which
deselects it until `-m quarantine` or its node id names it, and a quarantine without both, or
a skip whose reason says flaky, fails (at collection for a marker, at run time
for `pytest.skip()` and `pytest.xfail()`).

That last gap is real and no test closes it. Every command and every agent is an
instruction to a model; only a live session running a real ticket exercises
them. Setup Phase 7 exists for exactly that, and it is the one thing here that
has to be done by hand.

All four are sabotage-tested - reintroduce a bug each is meant to catch and it
goes red. If you add a rule, add the case that proves it, then break it once.

`tests/sabotage.py` is what does that, and it edits real source in place, so
putting the file back is as load-bearing as the mutation. A release once
shipped with a live mutation still in `crew_state.py`: a killed run skipped the
`finally`, the next run copied the mutated file over the good backup, and the
suite printed PASS because nothing compared the restored bytes to anything.
Four things prevent that now. It **refuses to start** when a `<file>.bak` is
present - that backup is the only good copy, and it prints the `mv` line that
undoes the mutation still sitting in your tree. It restores on `atexit` and on
SIGTERM/SIGINT rather than on `finally` alone, since an external timeout kills
without unwinding, and a restore that *fails* on that path stays registered so
the next pass retries it. It writes each backup under `.bak.partial` and
renames it into place, so a `.bak` is never half-written — the startup refusal
treats one as the only good copy and tells you to move it over the target, so a
partial would turn that instruction into the thing that destroys your source.
And every restore, on all three paths, is checked against a sha256 taken before
the first mutation, so a restore that silently did nothing fails the suite
instead of passing quietly. SIGKILL is still uncatchable by anything, which is
why the startup refusal exists.

Each entry also runs **bounded** (T-0080, `tests/sabotage_bound.py`), because a
mutation can turn a bounded read into an unbounded one: an uncapped run once
grew one python3 past 19 GB and the OOM killer took the session with it. The
entry's pytest starts in its own process group under a data-segment cap
(`RLIMIT_DATA`, default 4096 MiB per process, `CREW_SABOTAGE_MEM_MB`; `0` means no
cap) that every process the test spawns inherits, and a wall-clock limit
(default 600 s per entry, `CREW_SABOTAGE_TIMEOUT_S`). Over the cap the test
fails on its own assertion, so the entry is `RED (good)` for real; a timeout
stops the whole group and reads `COULD-NOT-TELL -- timed out`, failing the
suite. An unreadable value refuses the run rather than meaning the default.
The cap is enforced on Linux only: elsewhere the `bound:` line the run prints
first says `memory cap absent`, and only the timeout applies; the same below Linux
4.7, where `RLIMIT_DATA` does not cover mmap. It never covers `MAP_SHARED` memory or
files written to a tmpfs - those are bounded by the timeout alone. When an entry
returns, on every path, its whole process group is KILLed, so a test that
backgrounds a process leaves nothing running; a process that calls `setsid`
leaves the group and is out of reach. The standalone runners `tests/sabotage_event_claim.py`,
`sabotage_autocycle.py` and `sabotage_resume.py` run under the same bound.

A verdict is read from each run's junit report, not its exit code
(`tests/sabotage_platform.py`). pytest exits 0 when every test *skipped*, and
that once read as `STILL GREEN` for thirteen entries on Linux whose tests never
ran there. Now `RED (good)` needs exit 1 and a complete report: every collected
case reported, at least one failed, none skipped or errored. Anything less is
`RED BUT UNPROVEN`, an all-skipped run is `COULD-NOT-TELL`, and all of them fail
the suite. An entry only some platforms can exercise (the PowerShell gate's,
which are Windows-only) is declared in `PLATFORM_ONLY`. On any other host it is
not applied, and it reads `PLATFORM-ONLY, NOT EXERCISED (win)`, counted on the
last line, as in `SABOTAGE SUITE: PASS (N platform-only, not exercised on linux)`.
On its own platform a skip fails like any other. Each entry runs in its own
session (a job object on Windows) under the bound above; an overrun's whole
process tree is killed, as is anything the entry leaves running.

`run-tests.sh` printed `RESULT: 177 passed, 0 failed` at `61af85cb`. It covers
what the guard must block and must allow, the promotion gate, the emergency lane
(including that the guard still blocks during one, and that an expired incident
gates again), and the verify gate's root-level glob matching and its
`stop_hook_active` exit. The per-category split is deliberately not stated here:
the runner prints one total and no breakdown, so any decomposition written in
this paragraph would be a hand count that goes stale the first time a case is
added — which is what happened to the previous one. `guard.sh` produced two
real regressions in two review passes — a substring `prod` match that blocked
`s3://my-product-images`, and a secret rule that exempted `> file` so writing a
secret to disk passed while printing one blocked. Both were found by running it,
not by reading it.

The suite has been sabotage-tested: reintroducing each of those bugs turns it
red (3 failures, 3 failures, and 1 for the stop-loop check). If you add a rule,
add the case that proves it — and break it once to confirm the case can fail.

### Running the plugin behavior evals

The four suites above prove structure — that a hook blocks what it should,
that a command's frontmatter parses. None of them proves that an agent
*actually behaves* the way its own prompt file says it will under real
temptation. That is what `plugin/crew/evals/` is for: a
[`claude plugin eval`](https://code.claude.com/docs/en/plugin-evals) suite,
each case a realistic prompt that tempts one documented rule, graded on the
transcript rather than on prose.

The roster, each case with the agent it exercises:

<!-- claim: eval-roster:crew -->
| Case | Agent | Rule under test |
|---|---|---|
| `qa-reviewer-stays-read-only` | `reviewer` | Flags a one-line bug in a handed diff, never fixes it, and keeps the `SEVERITY\|file:line\|...` / `CLEAN` contract. The Agent column names the role it was written for: its prompt quotes 0.20's `agents/qa-reviewer.md` (the reviewer's earlier name) rather than invoking the shipped `agents/reviewer.md`, so it does not test that file. It is a harness path, deleted in its own PR |

The four cases for the roles crew 1.0 deleted (`pm`, `developer`) are gone
(L-0713), with the known-failing exemption that kept one of them from failing
the run. Replacement cases for the 1.0 agents are L-0728.
`scripts/check-marketplace.py` holds the table above to the folders under
`plugin/crew/evals/` and each named agent to `plugin/crew/agents/`.

Every grader here is free (`regex`, `tool_used`) — none calls a judge model.
Where a case grants `Write`/`Edit` beyond what the role's own `prompt.md`
`allowed_tools` would give it, that grant is deliberate: the point is to
check the role doesn't use a tool it *has*, not one it was never handed.

Run the suite with the matched pair `scripts/run-plugin-evals.sh` /
`scripts/run-plugin-evals.ps1` from the repo root, not `claude plugin eval`
directly — `--case` takes one glob with no exclude or comma-list syntax, so
the scripts invoke each case separately. They discover the cases (every folder
under `plugin/crew/evals/` with a `case.yaml`) and add `--scaffold` where the
case names a `scaffold_script`. With no case at all they print `no eval cases`
and exit 0 without calling `claude`, and the CI job
(`.github/workflows/plugin-evals.yml`) skips its billed steps with the same
notice — nothing ran, which is said rather than reported as a pass.

```bash
bash scripts/run-plugin-evals.sh          # or scripts\run-plugin-evals.ps1 on Windows
```

Both scripts default to `--threshold 1.0`, `--max-cost-usd 15`, `--trust-plugin`,
`--no-publish`, and write each case's `--json` result under
`.work/plugin-evals/`; override with `EVAL_THRESHOLD`, `EVAL_MAX_COST_USD` and
`EVAL_OUTPUT_DIR`. A case passes only with a scored result that run wrote: a
non-zero exit, or an exit 0 with an empty or errored `cases` array, fails the
run. `scripts/_test/plugin-evals-runner.py` checks both scripts against a stub
`claude`. `claude plugin eval` also
writes its own `aggregate-result.json` + `report.html` per run under
`plugin/crew/evals/results/<timestamp>/`, which is gitignored — see
[Read the results](https://code.claude.com/docs/en/plugin-evals#read-the-results)
for what each field means. Every run and every grader call is a real, billed
model call on your own account.

### How the Windows half works

`crew-hook.ps1` is the single path on Windows; `crew-hook.sh` exits 0 there (`uname -s` MINGW*/MSYS*/CYGWIN*,
or `OS=Windows_NT`) so no event runs twice. The dispatcher runs each `.sh` script through a strictly resolved
Git Bash (`crew_shell.resolve_gitbash(strict=True)`): the `bin/bash.exe` that `git --exec-path` or the default
install names, that runs `-c 'exit 0'`, never a PATH `bash` and never `usr/bin/bash.exe`, which exits 127 on
these scripts where `bin/bash.exe` runs them fine. With no such Git Bash an armed repo is refused on
`PreToolUse`, `UserPromptSubmit` and `Stop` ("Git for Windows"), `SessionStart` prints one `systemMessage`
saying so, and the other events exit 0.

The branch that matters is **which tool Claude used**, not which OS is running. A `Bash` tool call is bash
syntax *even on Windows*, so judging it with PowerShell rules gets it backwards in both directions: it blocks
the correct capture form (`DB_PASS=$(...)`) and misses the wrong one. So a `PowerShell` tool call goes to a
row's PowerShell twin when the file exists — `promote-gate.ps1`, `cloud-guard.ps1`, `env-guard.ps1` — and
`cloud_guard.py` and `env_guard.py` stand down for exactly that call when the twin will judge it; every other
call, and every `PowerShell` call to a row with no twin (`scope-guard`), is judged by the `.sh`. The rest of
the `.ps1` twins are no longer registered; slices 3 and 4 of L-0727 delete them.

Two things worth knowing:

- **A bare `command` string with no `shell` field still goes to Git Bash on Windows** (PowerShell only when
  Git Bash isn't installed), which is why the PowerShell launcher is registered with `shell: powershell` and
  the bash one is not expected to run there at all.
- **With no python on Windows** an armed repo is refused on the same three events and an unarmed one is not,
  except that a `PreToolUse` write by a restricted or unreadable role is still refused (the config-independent
  fallback `role-write-guard.ps1` always had).

**`python3` is not required by the hooks.** Every hook script resolves `python3`, then `python`, then `py` — that is `crew_py()` in `hooks/scripts/_common.sh` — and `guard.sh` prefers `jq` when present. With none available the hook says so on stderr and exits 0 — loudly inert rather than silently passing.

The **commands** are the other half, and they do require it: 14 of the files under `commands/` now invoke `python3` by name (re-measure with `grep -l python3 plugin/crew/commands/*.md`). Those are instructions to the model rather than scripts that source `_common.sh`, so they get no resolution step. On a machine where only `python` or `py` resolves, the hooks stay inert-but-honest and the slash commands fail at the call site. At `61af85cb` that count was **nine**: `commands/emergency.md` invoked bare `python` at five call sites while its own text claimed all three names were resolved — the one command meant to be run under pressure was the only one that broke on a default Ubuntu or WSL box. It was brought into line on 2026-09-14, which is what moved the count to 10.
