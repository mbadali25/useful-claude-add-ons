# crew outcome eval (L-0728)

Does crew pay for itself? Real tasks from this repository's history are run two ways, in a container, and graded by
frozen hidden tests outside it:

- **crew arm**: crew's own lifecycle, driven unattended by `/crew:autopilot run` on a ticket made by
  `crew_ticket.py assign`, with Codex as the reviewer.
- **baseline arm**: plain Claude Code plus `/code-review`: implement, review, fix every finding, repeat.

Per run it records escaped defects, review cycles, tokens, total cost (Claude and Codex, list price) and wall time. The
published result (`docs/evals/crew-outcome-results.md`, Slice 3) is a per-bucket verdict under the rules in this file,
which are frozen before the first scored run. This directory is **Slice 2** (harness, container, arm protocols, task
set, spike). No scored run has happened yet; nothing here claims an outcome.

## Layout

| Path | What |
|---|---|
| `arms/crew.json`, `arms/baseline.json` | The two arm protocols: pinned author and reviewer model and effort, crew config, CLI flags, prompts, review parse rule, wall-clock limits |
| `container/` | `Dockerfile`, `codex-shim.sh` (the `codex` on PATH), `eval-run.py` (the in-container wrapper that forwards a loopback port to the proxy socket), `proxy.py` + `proxy-allowlist.txt` (the allowlisting proxy), `canary.sh` (the isolation canary) |
| `tasks/<name>/` | `task.json`, `statement.md`, `grading/` (frozen hidden tests and test config); `tasks/selection-notes.md` is the selection record |
| `spike/` | The throwaway S task and `run-spike.py`, the spike through the harness itself |
| `../../scripts/crew-outcome-eval.py` | The harness: `validate`, `run`, `report` |
| `../../scripts/_test/crew-outcome-eval.py` | Its suite (stubs only; runs in CI) |

## Commands

```bash
# once: build the image (this host forwards no container traffic, so build on the host network)
docker build --network host -t crew-outcome-eval:1 evals/crew-outcome/container

# before the first scored run: the isolation canary (no model call); keep its output beside the results
evals/crew-outcome/container/canary.sh results/canary.txt <host checkout> <task store> <an earlier run dir>

python3 scripts/crew-outcome-eval.py validate --all
python3 scripts/crew-outcome-eval.py run --all --results results/results.jsonl --runs-dir runs --max-cost-usd 150
python3 scripts/crew-outcome-eval.py report --results results/results.jsonl
```

`run` refuses to start without `canary.txt` (last line `canary: PASS`) beside the results file. The host needs
`docker` and `git` and `python3` (the graded tests run in the same image, in a container with no network and nothing
mounted but the copy under test; no arm-written code runs on the host), and the
owner's Claude and Codex logins (see Isolation).

## Isolation (spec U10)

Every run gets a new repository made by `git init` from the task base's tree (one commit, no history, so the reference
commit is not reachable; the harness refuses a run where it is), its own `.git` (so its own review ledger), and fresh
`HOME`, `CLAUDE_CONFIG_DIR` and `CODEX_HOME` holding only:

- the OAuth **access** token of the owner's Claude login, without its refresh token, and the owner's Codex ChatGPT login
  with its refresh token replaced by a placeholder. The run therefore cannot rotate (and so log out) the owner's
  sessions. The proxy does not allow `auth.openai.com` either. Both access tokens expire; the harness does not check
  that they outlive a run, an expired one makes the run `unscorable` (rerun once).
- a `settings.json` denying `WebFetch` and `WebSearch`, and, for Codex, a `config.toml` turning off plugin sync (which
  reaches `github.com` at startup).

The arm runs in a container whose only mounts are that run's `repo` and `home` and the proxy's socket directory, with
`--network none`: a loopback and no other interface, so none of the host's own listening services (ssh, a docker API, a
database) is reachable. (An earlier design used an `--internal` Docker network with the proxy bound to its gateway; the
canary found the host's sshd answering on that gateway address, so it was dropped.) The only way out is the allowlisting
proxy, a host process listening on a unix socket in that directory (`container/proxy.py`, `container/proxy-allowlist.txt`:
`api.anthropic.com`, `api.openai.com`, `chatgpt.com` and its subdomains, CONNECT on 443 only); `container/eval-run.py`,
which wraps every command in the container, listens on `127.0.0.1:3128` and forwards each connection to that socket. The
proxy logs every decision to `<run>/proxylog/proxy.jsonl`, outside the mounts.
The container runs as uid 1000 (not root), with `--cap-drop ALL`, `no-new-privileges`, `--pids-limit 1024`, `--memory 6g`,
no `--privileged`, no `--cap-add` and no `seccomp=unconfined` or `apparmor=unconfined`. Grading uses the same options with
`--network none` and the copy under test as its only mount, so the arm's code (its modules, any `conftest.py`, `.pth`
file or `pytest.ini`) never runs on the host, and a symlink the arm planted cannot make the host overwrite a file. Codex's own sandbox cannot start in a container on this host
(see Spike), so the image puts a `codex` shim first on `PATH` (`container/codex-shim.sh`): it rewrites `--sandbox
read-only` (also `-s`, `--sandbox=`) to `--sandbox danger-full-access` and passes everything else through, which makes the
**container the only boundary**. That is a treatment difference from crew as shipped (the Codex reviewer is not held
read-only) and the results doc says so. It is acceptable only because the container has: no host mounts beyond the run's
`repo` and `home` (and the proxy socket); no network beyond the proxy's model hosts; and no secrets beyond the two short-lived access tokens
above (no cloud, SSH or git credentials, no environment passthrough, no connectors). Codex can read those two tokens and the
Codex `id_token` (it names the account and its email; Codex needs it to read the login); the access tokens expire within
hours and cannot be refreshed. The Codex auth copy is an allowlist (`auth_mode`, `access_token`, `id_token`, `account_id`,
the placeholder refresh token, `last_refresh`), so an `OPENAI_API_KEY` in the owner's file never reaches a run. The CLI is started with
`--strict-mcp-config` and an empty server list, so none of the owner's claude.ai connectors (Gmail, Drive, ...) load.

`container/canary.sh` runs a scripted shell in that container, with the same options an arm gets, behind that proxy, with no
model call and no credential. It must fail to see the host checkout, the task store and an earlier run directory that
reuses the same ticket id, must have no network interface but loopback, must fail to reach `github.com`,
`codeload.github.com` and `api.github.com` through the proxy and every host directly, must not resolve an external name,
and must reach the two model API hosts through the proxy. `run` refuses unless `canary.txt` beside the results file ends in
`canary: PASS` and its first line names the id of the image that is current (`docker image inspect`), so a canary does not
vouch for a rebuilt image.

Grading is hardened beyond the container. Before the frozen tests run, every pytest-affecting file in the copy
(`conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `sitecustomize.py`, `.pth`) is replaced by the base
tree's, so an arm cannot change the test environment. A result is read only from pytest's own `short test summary info`
section (the last one, up to the first non-result line); a `PASSED` line the code under test prints elsewhere is ignored, a
run that exits other than 0 or 1 or times out has no result, and a missing result is `MISSING`, which fails. Residual,
accepted: the code under test runs inside pytest's process, so a determined forger could print a whole fake report; this
closes the echo, not that. `run` also holds an exclusive lock on the results file (two processes would each pass the
budget check), refuses a NaN, infinite or non-positive budget, and refuses to grade after a timed-out container could
not be stopped. `canary.txt` is valid only for the current image and the current proxy allowlist, proxy and wrapper (a
fingerprint on its first line); the canary needs the host checkout, the task store and an earlier run dir.

**Cost baseline.** `CODEX_PRICES` carries one row, `gpt-6-sol` (the pinned crew reviewer): Standard tier, short context,
USD per million tokens, input 2.00, cached input 0.20, output 10.00, read on 2026-10-23 from
https://developers.openai.com/api/docs/pricing (`CODEX_PRICES_AS_OF`). The same page charges 4.00 / 0.40 / 15.00 for a call
with more than 272K input tokens; Codex reports usage per turn, not per call, so such a call cannot be seen and the Codex
cost is a lower bound at the short-context rate. A model with no row still makes the cost UNKNOWN. Image supply
chain, accepted: the base is pinned by digest, but Claude Code needs its postinstall, so npm transitive dependencies and
apt packages float at build time; the canary records the image id it vouches for.

A run is flagged `contaminated` (excluded from the verdict and listed) only on evidence of reference access: the
reference commit sha or the reference PR's URL in a Claude transcript or Codex event; three or more distinct,
distinctive lines (60+ characters, absent from the base version of that file and from the task statement) of a hidden
test file in one; or a proxy-refused host that is not on the arm's `proxyIgnoreHosts` list. Text that exists in the
base tree (the repo path in `README.md`, `.claude-plugin/marketplace.json`) never flags a run.

## Metrics

| Metric | Definition |
|---|---|
| `escapedDefects` | Number of named defects with at least one hidden test that does not report PASSED after grading (fail, error, skip and not collected alike). `task.json` groups the hidden test ids into non-overlapping defects. Every hidden test is listed: in a defect group (scored), in `regressionInventory`, in `hiddenRegression` (passes before and after; counted in `regressionTestsFailed`) or in `unscoredHidden` (hardening the statement cannot state; must pass at the reference, never counted). `validate` sweeps every grading test file and refuses a task with a hidden test in none of them. |
| `regressionTestsFailed` | Base-passing visible test ids from the frozen inventory that do not pass after. Reported beside the verdict, never added to `escapedDefects`. |
| `reviewCycles` | A completed review with a parsed verdict. Crew: a ledger round with verdict CLEAN or FINDINGS. Baseline: a `/code-review` invocation whose output parses by the rule in `arms/baseline.json`. |
| `reviewAttemptsIncomplete` | Errored, refused, INCOMPLETE or unparseable review attempts. Each arm retries an errored review at most once. |
| `tokens` | Claude tokens split `{input, output, cacheRead, cacheCreation, total}`, every transcript in the run's own Claude home including subagent files, each message once (`crew_metrics`). |
| `claudeCostUsd` | List price of those tokens from `crew_metrics.PRICES`; UNKNOWN when a session's transcript is missing or does not parse, a subagent file a transcript names is missing, or a model is unpriced. |
| `codexTokens`, `codexCostUsd` | The sum of every `turn.completed` usage in the run's `codex-events.jsonl` files. UNKNOWN when a Codex session exists in the run's own `CODEX_HOME` that no events file accounts for, or the model has no price row (only `gpt-6-sol` has one). |
| `costUsd` | `claudeCostUsd + codexCostUsd`, plus the cost of any unscorable attempt this run replaced; UNKNOWN if any part is. |
| `cliTotalCostUsd` | The CLI's own `total_cost_usd`, per session (the CLI reports it cumulatively across `--resume`, so only the last value of each session counts). A cross-check, never the cost. |
| `wallSeconds` | Monotonic clock over the whole arm. |

A run is `unscorable` (rerun once) only for a harness, auth, container or API failure of the ARM (a CLI that exits
non-zero or prints no `session_id` included); an agent that stops early or times out is graded as it left the repo. A
rerun's `costUsd` carries the attempt it replaced, so a scored chain reports what the whole chain cost and the task cost is
the median of the chains; an attempt that produced no score (`unscorable`, `infra`, `error`) also records its spend as
`unscoredSpendUsd` when it is written, so a refused rerun leaves exactly one row for attempt 1. Only a chain that never
scored adds its final row's `unscoredSpendUsd` to the arm's task cost. Arm and task files are shape-checked (types, nulls, missing keys) before any billed call, and
the run's `settings.json` always carries the `WebFetch` and `WebSearch` denials whatever the arm adds.

Grading has its own two non-verdicts, both written as a row with the arm's cost and neither rerun (the arm already
ran and was paid for): `infra` (the grading container exited 125, 126 or 127, timed out, or docker could not be
started; `docker rm -f` after a timeout is bounded too) and `error` (grading raised). Neither is a defect and neither is
MISSING tests: `escapedDefects` and `regressionTestsFailed` are null, and a bucket with such a row says "could not
tell" and names it. A pytest exit other than 0 or 1 (interrupted, internal error, no tests collected) is still the
code's own failure and its tests are MISSING.

`endedBy` says why the arm stopped: `stop` (autopilot or the arm ended it), `wall-clock`, or `resume-cap` (crew arm:
the harness's `maxResumes` ran out while autopilot still said `stop=0`). A `resume-cap` run is graded as it stands, like
a wall-clock stop, and the report says how many runs were graded that way; it is never silently dropped.

## Method (frozen before the first scored run)

- **Buckets** by the reference diff's changed lines (`git diff --numstat base reference`, added + deleted), excluding
  tests (`tests/`, `_test/`, `test_*`), docs (`*.md`, `docs/`), generated files (`graphify-out/`, `.claude/rules/`,
  built `docs/guides/**`) and version files: **S** < 150, **M** 150-599, **L** >= 600.
- **Selection**: walk `.work/INDEX.md` `done` rows oldest first; take the first 2 per bucket whose reference diff touches
  nothing under `plugin/crew/` and whose hidden tests run hermetically in under 60 s; record every reject with its reason
  (`tasks/selection-notes.md`). Statements come from the ticket's direction/spec Intent, never the diff.
- **Arms**, pinned in `arms/*.json`: the author model and effort are identical in both arms (`claude-sonnet-5-5`,
  medium); the crew reviewer is Codex (`gpt-6-sol`, medium); the baseline reviewer is `/code-review` at the author model
  and effort, so it is **the same model family as the author** and the results doc says so. Wall-clock limit per bucket
  S 60 min, M 120, L 240; no human input. Crew's own agents (explorer, reviewer, ...) run on the models their agent files
  name; only the main session's model is pinned.
- **Crew arm**: `crew_ticket.py assign` (the harness writes the staging file from the statement; README "assign") makes a
  ticket whose direction is already approved, then `/crew:autopilot run <ticket>`; after each run the harness asks
  autopilot's own `next` and resumes (`--resume`, at most 3 times) only while it says `stop=0`. The arm ends at the first
  `stop=1` (a person is needed, `accept-review` included, or the ticket is closed), at the wall-clock limit, or when the
  3 resumes are used up (`endedBy: resume-cap`, graded as it stands and reported as such). Config:
  `autopilot.mode: plan`, `approval: self`, `questions: self`, `reviewPolicy: fix-and-rereview`,
  `scope.allowCliApproval: true`, the Codex model pinned, everything else crew's default.
  **No codemap in the crew arm** (`removePaths: [".crew/codemap"]`, arm file): this repository's map places only some
  Touch entries (not `CHANGELOG.md`, `README.md` or `.claude-plugin/marketplace.json`), so autopilot's size check reads
  `subsystems` as unknown and stops at `split-check-unknown` before writing any code. With no codemap the measure is
  `unmeasured` and does not stop. It is a treatment difference (crew runs as on a repository not yet onboarded, without
  codemap context) and the results doc says so.
- **Baseline arm**: implement, run `/code-review`, fix every reported finding, repeat until a cycle reports no findings
  or 3 cycles complete.
- **Verdict**: per task, the median over that arm's scored runs (at least 2 known runs per arm per task, else the task
  drops out and is listed); per bucket, the median over tasks of the paired differences (crew minus baseline) in escaped
  defects and in cost (an exhausted failed chain's `unscoredSpendUsd` is added to its arm's task cost). Crew pays for
  itself in a bucket when a reader values one escaped defect above `cost difference / defects avoided` USD; "crew leaves no
  fewer escaped defects" when the defect difference is >= 0; "could not tell" when fewer than 2 tasks remain or any cost
  input is UNKNOWN. Regressions are reported per bucket beside the verdict. Contaminated runs are excluded and listed.
- **Budget**: `--max-cost-usd` (default 150) is a scheduling threshold, not a meter. Before each run the harness refuses
  when spent so far plus the projected cost of this run would pass it. The projection is the highest cost observed for
  this bucket and arm, else for this arm (the pilot's), else `--first-run-estimate-usd` (default 25). A run whose cost is
  UNKNOWN stops the batch. Overshoot is bounded by one run, itself bounded by the bucket's wall-clock limit.

## Tasks (spec U5)

The frozen procedure ran over all 258 `done` rows of `.work/INDEX.md` on 2026-10-19 (origin/main `8fd3df757`). It found
**2 tasks, not 6**:

| Task | Ticket | Bucket | Lines (how measured) | Hidden tests scored | Defects | Regression ids |
|---|---|---|---|---|---|---|
| `t-0108-nuclei-safe-defaults` | T-0108 | M | 263 = `gizmoduck.py` 138 + `scanners/nuclei.py` 117 + `routine.py` 8 | 49 of 148 (99 listed as unscored, 6 as hidden regression) | 10 | 160 |
| `t-0107-gizmoduck-routine-cli` | T-0107 | L | 656 = `gizmoduck.py` 649 + `bootstrap.sh` 4 + `bootstrap.ps1` 3 | 32 of 99 (67 listed as unscored, 2 as hidden regression) | 9 | 72 |

No S task exists, and M and L have one each, so under the verdict rule **every bucket is "could not tell"** (fewer than
2 tasks). Owner-approved decision 2026-10-20 (spec "Amendment 2026-10-20", A3): the selection is **not widened**. The only
routes (relaxing the frozen `plugin/crew/` rule, or inventing synthetic tasks) are not cheap and change what is measured;
the 2-task run is the **accepted baseline**, published as per-task observations, never as a bucket verdict. 219 of the 256 rejects touch `plugin/crew/`, 9 have no tests, 7 have
tests that are standalone scripts with no pytest node ids, and 21 fall under other reasons; every reject with its
reason, the INDEX rows walked and the ambiguities in the procedure are in `tasks/selection-notes.md`. `validate --all`
passes for both tasks (hidden tests fail at base, pass at reference, regression ids pass at both).

Two judgement calls the owner may overturn, both recorded in the notes: the statements carry the interface the checks
drive (function names, a few constants, for T-0107 the stderr texts), because without it nearly every defect escapes for
both arms; and hidden tests that need something the statement cannot state stay in `grading/` and are listed in `unscoredHidden`
(99 of 148 for T-0108, 67 of 99 for T-0107), so they are neither scored nor counted as regressions; they must still pass at
the reference.

## Spike, 2026-10-19 (Slice 2 Step 6; resolves U1, U2, U3, U10)

Run on this host (Linux 7.0.0-38-generic, Docker 29.1.3, `net.ipv4.ip_forward = 0`) at crew 1.2.56
(`8fd3df757`), image `crew-outcome-eval:1` (Claude Code 2.1.303, codex-cli 0.162.1, node 22, Debian bookworm),
throwaway task `evals/crew-outcome/spike/` (a `slugify` function; `run-spike.py` reproduces it through the harness).
About 3 USD of Claude list price in all; the Codex sessions were small and are unpriced.

**Canary (U10): PASS.** Output of `canary.sh` (kept as `canary.txt` beside any results): the host checkout, the task
store and an earlier run dir are not visible; `github.com`, `codeload.github.com`, `api.github.com` are refused through the
proxy and every host is unreachable directly; `api.anthropic.com` and `chatgpt.com` are reachable through the proxy. The
first design (an `--internal` network with the proxy on its gateway) failed an added probe: the gateway address answered
on the host's port 22. The container now has `--network none` and reaches the proxy only through its unix socket; the
canary checks that loopback is the only interface and that no external name resolves.

**U3, the CLI JSON.** `claude -p ... --output-format json` prints one object with these keys: `api_error_status`,
`duration_api_ms`, `duration_ms`, `is_error`, `modelUsage` (per model: `inputTokens`, `outputTokens`,
`cacheReadInputTokens`, `cacheCreationInputTokens`, `costUSD`, `costBasis: "list"`), `num_turns`, `permission_denials`,
`result`, `session_id`, `stop_reason`, `subagent_stats`, `subtype`, `terminal_reason`, `total_cost_usd`, `type`, `usage`,
`uuid` and timing fields. `total_cost_usd` is **cumulative for the session across `--resume`** (an implement call
reported 0.0398, the resumed fix call 0.0602), so summing it per invocation double counts; the harness keeps each session's
last value. The transcripts, not the JSON, are the cost source: they match `modelUsage` to the token for a `/code-review`
call (27,554 tokens both ways; the price differs 0.0466 vs 0.0453 because `crew_metrics` prices 1-hour cache writes at
2x input).

**U2, `/code-review` runs inside `claude -p`**, as a built-in skill, with no plugin installed. It forks one subagent (its
own `subagents/agent-*.jsonl`; the review session's main transcript has no usage at all) and answers with a short prose
line and a fenced JSON array: `[{"file", "line", "summary", "failure_scenario"}, ...]`, or
`[]` alone when there is nothing to report. The parse rule in `arms/baseline.json` is exactly that: any line matching
`"summary":` is findings, a line that is only `[]` is no findings, anything else (both, neither) is an unparseable
attempt. One implement -> review (5 findings) -> fix -> review (2 findings) -> fix cycle cost 0.17 USD and about 10 s per call.

**U1, the crew arm.** `/crew:brainstorm` mints a ticket and stops at a direction nobody can approve unattended
(`phase=direction-approval stop=1 decision=direction`), so the arm uses the supported route: the harness writes
`.work/autopilot/assign-1.md` from the statement and runs `crew_ticket.py assign` (it prints `ticket=T-0001 risk=med`,
status `ready`), then `/crew:autopilot run T-0001`. With the pinned config, and with the Codex wrapper described under the blocker below, that one `claude -p` ran
`/crew:spec`, `/crew:plan`, `self-approved T-0001 under approval=self, risk=med`, `/crew:implement` (tests first), the
Codex review, `/crew:done` and then stopped at `phase=ship stop=1 decision=look` ("could not read the PR state for main"),
which is the terminal stop: the code is committed in the run repo, nothing is pushed. It needed `"tracker": "files"` in
the config and a git identity in the container's environment; both are now in the arm file and the harness. It took
141 s and 0.52 USD on the S task.

**Blocker found, resolved 2026-10-20 (owner decision): Codex's own sandbox cannot start in a Docker container on this host.**
`review_run.py` runs `codex exec --json --sandbox read-only`; inside the container every Codex shell command failed with
`bwrap: Failed to make / slave: Permission denied`, so Codex never read the diff and the round was recorded `INCOMPLETE`.
Measured by hand:

| Container options (uid 1000, `--cap-drop ALL`, `no-new-privileges`) | Result |
|---|---|
| Docker default seccomp | `unshare --user` is denied |
| `seccomp=unconfined` | `unshare --user` works; making `/` a slave mount is denied (Docker's default AppArmor profile is the likely cause; not isolated further) |
| `seccomp=unconfined` + `apparmor=unconfined` | `/proc/self/uid_map` write denied (the host's `kernel.apparmor_restrict_unprivileged_userns = 1`) |
| `+ cap-add SYS_ADMIN` | no change |
| Codex `use_legacy_landlock` | "the filesystem sandbox requires bubblewrap" |

Resolution: the `codex` shim (see Isolation), spec "Amendment 2026-10-20". A first shimmed run (with `seccomp=unconfined`)
ran spec, plan, implement, one Codex review (`CLEAN`, `gpt-6-sol`), done and the `ship` stop in 141 s. After the
amendment the image was rebuilt (the shim is `chmod 0755` in the Dockerfile and executable in git), `canary.sh` passed
under the same options the scored runs use (default seccomp and AppArmor, `--cap-drop ALL`, `no-new-privileges`, uid 1000;
an earlier canary ran with `seccomp=unconfined` and did not prove that), and `spike/run-spike.py` was re-run through the
harness at the Slice 2 close, after the container moved to `--network none` with the proxy on a unix socket and grading
moved into the image (one intermediate run was `contaminated`: with `last_refresh` dropped from the Codex login, Codex tried
to refresh it at `auth.openai.com` and the proxy refused, which is why `last_refresh` is kept): baseline scored
(3 `/code-review` cycles, 0.19 USD), crew scored with 1 review cycle, 0 incomplete attempts, 0.80 USD Claude list price,
Codex 190,878 input / 1,121 output tokens (unpriced, so the crew run's `costUsd` is UNKNOWN), 0 escaped defects, 219 s (final
run, after the grading hardening below; an earlier run of the same design had 2 review cycles).

Codex usage as `review_run.py` leaves it in `codex-events.jsonl` (the same five keys the spec quoted):
`{"type":"turn.completed","usage":{"input_tokens":102324,"cached_input_tokens":76800,"cache_write_input_tokens":0,"output_tokens":633,"reasoning_output_tokens":159}}`.

**FINDINGS -> fix -> re-review (spec U1), shown 2026-10-20 on the L-0851 head `aa3e98726`** (crew arm only, one run of
`spike/run-spike.py --arms crew`, canary PASS for the rebuilt image, through the harness and the same container options as
a scored run). One `claude -p` ran spec, plan, self-approval, implement, then Codex review round 1 = `FINDINGS`
(`FIX|slug.py:11|Unicode characters that lowercase to ASCII are kept instead of treated as separators`, plus one NIT about a
hook marker file in `.crew/`); autopilot's `phase=fix` committed `Treat non-ASCII as separators before lowercasing (T-0001
review round 1)`; Codex review round 2 on the fixed commit = `FINDINGS` with the NIT only (0 FIX, 0 BLOCK); the arm then
stopped at `accept-review`, the terminal stop that needs a person (`autopilot.reviewPolicy: fix-and-rereview` as pinned).
The ledger in the run repo has two rounds, both completed, no INCOMPLETE; the row: `runStatus scored`, `reviewCycles 2`,
`reviewAttemptsIncomplete 0`, `escapedDefects 0`, `endedBy stop`, 257.9 s, Claude list price 0.68 USD, Codex 405,691 input
(348,672 cached) / 3,083 output tokens (unpriced, so `costUsd` is UNKNOWN), the CLI's own `total_cost_usd` 0.51. Spend for
this spike step: one run, 0.68 USD Claude list price plus the unpriced Codex usage, against the 10 USD stop set in the
plan (the spec's 150 USD cap is for Slice 3). Earlier runs of the same design, before the L-0851 fixes, gave `CLEAN` in
round 1 and, once, 2 cycles; the FINDINGS cycle depends on what the model writes, so this is one observed cycle, not a rate.

**Not shown by the spike:** the baseline arm on a real task; a timeout (`docker kill`) mid-arm; the Windows host path; a
FINDINGS cycle on a real (not throwaway) task. The S task's statement is 3 lines; a real task's run is much longer than
the 258 s measured here.

Other things the spike found, all handled in the harness: claude.ai account connectors try to load through
`mcp-proxy.anthropic.com` (refused; `--strict-mcp-config` with no servers stops it); Codex syncs plugins from
`github.com` at startup (refused; `config.toml` turns plugin sync off, because a refused `github.com` is contamination
evidence); Codex needs `api.openai.com` as well as `chatgpt.com`; Codex treats a login with no refresh token as signed
out, so the placeholder stays.

## Not verified

- A scored run of either arm on a real task; every figure above is from the one throwaway task.
- That an access token outlives a long run (Claude's expires in hours; the harness does not check).
- Codex cost is a lower bound: the price row is the short-context rate, and a call over 272K input tokens (charged 4.00 /
  0.40 / 15.00) is not visible in per-turn usage.
- The harness on Windows; the host needs `docker`, so only the stub suite runs in CI.
- That statements written from the Intent alone are solvable by either arm (no agent was run on a real statement).
