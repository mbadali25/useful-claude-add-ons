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
| `container/` | `Dockerfile`, `proxy.py` + `proxy-allowlist.txt` (the allowlisting proxy), `canary.sh` (the isolation canary) |
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
`docker`, `git`, `python3` with `pytest` and `PyYAML` (the graded tests run on the host, outside the container), and the
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

The arm runs in a container whose only mounts are that run's `repo` and `home`, on a Docker network created with
`--internal` (no route out). The only way out is the allowlisting proxy, a host process bound to that network's gateway
address (`container/proxy.py`, `container/proxy-allowlist.txt`: `api.anthropic.com`, `api.openai.com`, `chatgpt.com`
and its subdomains, CONNECT on 443 only). It logs every decision to `<run>/proxylog/proxy.jsonl`, outside the mounts.
The container runs as uid 1000 (not root), with `--cap-drop ALL`, `no-new-privileges` and
`--security-opt seccomp=unconfined` (Codex's own sandbox needs unprivileged user namespaces, which Docker's default
seccomp profile denies; without it the crew arm's review ends INCOMPLETE). The CLI is started with
`--strict-mcp-config` and an empty server list, so none of the owner's claude.ai connectors (Gmail, Drive, ...) load.

`container/canary.sh` runs a scripted shell in that container behind that proxy with no model call and no credential. It
must fail to see the host checkout, the task store and an earlier run directory that reuses the same ticket id, must
fail to reach `github.com`, `codeload.github.com` and `api.github.com` through the proxy and every host directly, and must
reach the two model API hosts through the proxy. On this host `net.ipv4.ip_forward` is 0, so a container could not reach
the internet even on the default network; the canary's "direct is unreachable" lines therefore hold for two reasons here,
and the internal network is what keeps them true on a host that does forward.

A run is flagged `contaminated` (excluded from the verdict and listed) only on evidence of reference access: the
reference commit sha or the reference PR's URL in a Claude transcript or Codex event; three or more distinct,
distinctive lines (60+ characters, absent from the base version of that file and from the task statement) of a hidden
test file in one; or a proxy-refused host that is not on the arm's `proxyIgnoreHosts` list. Text that exists in the
base tree (the repo path in `README.md`, `.claude-plugin/marketplace.json`) never flags a run.

## Metrics

| Metric | Definition |
|---|---|
| `escapedDefects` | Number of named defects with at least one hidden test that does not report PASSED after grading (fail, error, skip and not collected alike). `task.json` groups the hidden test ids into non-overlapping defects. |
| `regressionTestsFailed` | Base-passing visible test ids from the frozen inventory that do not pass after. Reported beside the verdict, never added to `escapedDefects`. |
| `reviewCycles` | A completed review with a parsed verdict. Crew: a ledger round with verdict CLEAN or FINDINGS. Baseline: a `/code-review` invocation whose output parses by the rule in `arms/baseline.json`. |
| `reviewAttemptsIncomplete` | Errored, refused, INCOMPLETE or unparseable review attempts. Each arm retries an errored review at most once. |
| `tokens` | Claude tokens split `{input, output, cacheRead, cacheCreation, total}`, every transcript in the run's own Claude home including subagent files, each message once (`crew_metrics`). |
| `claudeCostUsd` | List price of those tokens from `crew_metrics.PRICES`; UNKNOWN when a session's transcript is missing or does not parse, a subagent file a transcript names is missing, or a model is unpriced. |
| `codexTokens`, `codexCostUsd` | The sum of every `turn.completed` usage in the run's `codex-events.jsonl` files. UNKNOWN when a Codex session exists in the run's own `CODEX_HOME` that no events file accounts for, or the model has no price row (none yet: `CODEX_PRICES` is empty). |
| `costUsd` | `claudeCostUsd + codexCostUsd`, plus the cost of any unscorable attempt this run replaced; UNKNOWN if any part is. |
| `cliTotalCostUsd` | The CLI's own `total_cost_usd`, per session (the CLI reports it cumulatively across `--resume`, so only the last value of each session counts). A cross-check, never the cost. |
| `wallSeconds` | Monotonic clock over the whole arm. |

A run is `unscorable` (rerun once) only for a harness, auth, container or API failure; an agent that stops early or times
out is graded as it left the repo. A chain that ends unscorable keeps its spend as `unscoredSpendUsd`, which counts in
the arm's task cost.

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
  `stop=1` (a person is needed, `accept-review` included, or the ticket is closed) or at the wall-clock limit. Config:
  `autopilot.mode: plan`, `approval: self`, `questions: self`, `reviewPolicy: fix-and-rereview`,
  `scope.allowCliApproval: true`, the Codex model pinned, everything else crew's default.
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
| `t-0108-nuclei-safe-defaults` | T-0108 | M | 263 = `gizmoduck.py` 138 + `scanners/nuclei.py` 117 + `routine.py` 8 | 49 of 148 | 10 | 160 |
| `t-0107-gizmoduck-routine-cli` | T-0107 | L | 656 = `gizmoduck.py` 649 + `bootstrap.sh` 4 + `bootstrap.ps1` 3 | 32 of 99 | 9 | 72 |

No S task exists, and M and L have one each, so under the verdict rule **every bucket is "could not tell"** (fewer than
2 tasks) unless the owner widens the selection. 219 of the 256 rejects touch `plugin/crew/`, 9 have no tests, 7 have
tests that are standalone scripts with no pytest node ids, and 21 fall under other reasons; every reject with its
reason, the INDEX rows walked and the ambiguities in the procedure are in `tasks/selection-notes.md`. `validate --all`
passes for both tasks (hidden tests fail at base, pass at reference, regression ids pass at both).

Two judgement calls the owner may overturn, both recorded in the notes: the statements carry the interface the checks
drive (function names, a few constants, for T-0107 the stderr texts), because without it nearly every defect escapes for
both arms; and hidden tests that need something the statement cannot state stay in `grading/` but are in no defect
(99 of 148 for T-0108, 67 of 99 for T-0107), so they are neither scored nor counted as regressions.

## Spike, 2026-10-19 (Slice 2 Step 6; resolves U1, U2, U3, U10)

Run on this host (Linux 7.0.0-38-generic, Docker 29.1.3, `net.ipv4.ip_forward = 0`) at crew 1.2.56
(`8fd3df757`), image `crew-outcome-eval:1` (Claude Code 2.1.303, codex-cli 0.162.1, node 22, Debian bookworm),
throwaway task `evals/crew-outcome/spike/` (a `slugify` function; `run-spike.py` reproduces it through the harness).
About 2.5 USD of Claude list price in all; the Codex sessions were small and are unpriced.

**Canary (U10): PASS.** Output of `canary.sh` (kept as `canary.txt` beside any results): the host checkout, the task
store and an earlier run dir are not visible; `github.com`, `codeload.github.com`, `api.github.com` are refused through the
proxy and every host is unreachable directly; `api.anthropic.com` and `chatgpt.com` are reachable through the proxy.

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

**Blocker found: Codex's own sandbox cannot start in a Docker container on this host.** `review_run.py` runs
`codex exec --json --sandbox read-only`; inside the container every Codex shell command fails with
`bwrap: Failed to make / slave: Permission denied`, so Codex never reads the diff and the round is recorded
`INCOMPLETE` (reviewer class, not refunded; a second `/crew:autopilot run` then stops at `split-check-unknown` because the
INCOMPLETE round's `.crew/metrics.md` row is unreadable to the split check). Measured by hand:

| Container options (uid 1000, `--cap-drop ALL`, `no-new-privileges`) | Result |
|---|---|
| Docker default seccomp | `unshare --user` is denied |
| `seccomp=unconfined` (what the harness uses) | `unshare --user` works; making `/` a slave mount is denied (Docker's default AppArmor profile is the likely cause; not isolated further) |
| `seccomp=unconfined` + `apparmor=unconfined` | `/proc/self/uid_map` write denied (the host's `kernel.apparmor_restrict_unprivileged_userns = 1`) |
| `+ cap-add SYS_ADMIN` | no change |
| Codex `use_legacy_landlock` | "the filesystem sandbox requires bubblewrap" |

Making it work needs a container that is root with `CAP_SYS_ADMIN` and no AppArmor profile, or a host AppArmor change.
Neither was done: the plan says that if crew cannot run unattended with the pinned config or the container cannot hold
Codex, the design changes and the spec is amended, with no workaround inside this ticket.

For the owner's decision, evidence only: a `codex` wrapper earlier on `PATH` in the container that rewrites
`--sandbox read-only` to `--sandbox danger-full-access` (the container is then the sandbox) made the whole crew arm work:
the shimmed run (the one just described) ran spec, plan, implement, one Codex review (`CLEAN`, 0 BLOCK / 0 FIX / 0 NIT, `gpt-6-sol`), done, and the
`ship` stop, in 141 s. Its cost is that the Codex reviewer is no longer held read-only (the container is the only
boundary), which is a treatment difference from crew as shipped. It is not in the harness.

Codex usage as `review_run.py` leaves it in `codex-events.jsonl` (the same five keys the spec quoted):
`{"type":"turn.completed","usage":{"input_tokens":102324,"cached_input_tokens":76800,"cache_write_input_tokens":0,"output_tokens":633,"reasoning_output_tokens":159}}`.

**Not shown by the spike:** one crew FINDINGS -> fix -> re-review cycle (the only completed Codex round was `CLEAN`;
`autopilot.reviewPolicy: fix-and-rereview` and `commands/autopilot.md` section 3's `phase=fix` are as documented but were
not exercised); the baseline arm on a real task; a timeout (`docker kill`) mid-arm; the Windows host path. The S task's
statement is 3 lines; a real task's run is much longer than 141 s.

Other things the spike found, all handled in the harness: claude.ai account connectors try to load through
`mcp-proxy.anthropic.com` (refused; `--strict-mcp-config` with no servers stops it); Codex syncs plugins from
`github.com` at startup (refused; `config.toml` turns plugin sync off, because a refused `github.com` is contamination
evidence); Codex needs `api.openai.com` as well as `chatgpt.com`; Codex treats a login with no refresh token as signed
out, so the placeholder stays.

## Not verified

- A scored run of either arm on a real task; every figure above is from the one throwaway task.
- That an access token outlives a long run (Claude's expires in hours; the harness does not check).
- `CODEX_PRICES` is empty: Codex cost is UNKNOWN for every run until a price row for the pinned model is read from the
  vendor page and dated here. The verdict is "could not tell" for any bucket until then.
- The harness on Windows; the host needs `docker`, so only the stub suite runs in CI.
- That statements written from the Intent alone are solvable by either arm (no agent was run on a real statement).
