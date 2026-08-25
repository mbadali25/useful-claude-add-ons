# Setup phases

Shared by the `crew-setup` skill and the `/crew:init` command. One source of truth.

Walk this repository through crew setup, one phase at a time.

## How this works

Read `.crew/STATUS.md`. If it does not exist, start at Phase 0. If it does,
resume at the first phase not marked `done`.

**Run one phase, then stop and report.** Do not chain phases without me saying
go. Each phase ends with something I can verify myself, and the whole point is
that I see each result before the next thing is built on top of it.

With `--status`: print the phase table and stop.
With `--phase N`: run that phase only, even if earlier ones are incomplete —
and warn me about what is missing.

After every phase, rewrite `.crew/STATUS.md`:

```
# crew setup status
repo: <name>
updated: <date>

| # | Phase | State | Notes |
|---|-------|-------|-------|
| 0 | Platform          | done    | wsl2/Ubuntu, repo on native fs |
| 1 | Config+context    | done    | files tracker, verifyGate on, warnAt 0.8 |
| 2 | Providers+notify  | partial | codex ok; gemini key not set |
| 3 | Smoke harness     | blocked | 4/7 checks passing |
| 4 | Code map          | todo    | |
| 5 | Verification map  | todo    | |
| 6 | Browser tests     | n/a     | no UI in this repo |
| 7 | First ticket      | todo    | |
| 8 | Promotion gates   | todo    | |
```

States: `todo`, `in progress`, `partial`, `blocked`, `done`, `n/a`.
Be honest with `partial` and `blocked`. A status file that says `done` when a
thing half works is how the whole system quietly stops meaning anything.

---

## Phase 0 — Platform

Run `platform.sh` (or `platform.ps1` on native Windows). Record the `platform`
block in `.crew/config.json`. Act on `windows-mount` and `crlfDetected` per
`crew-setup/platform.md`, and ask before re-cloning anything.

**Then resolve the toolchain**, which is the half that actually blocks work:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/resolve-tools.sh <tools>
```

Knowing you are on WSL2 is not useful on its own. Knowing that `terraform` is
not on this shell's PATH but does exist inside WSL is, because a bare
`terraform validate` in a rule then fails with "command not found" and the gate
reports that as a **failed check** rather than a missing tool - and someone
spends an afternoon on a config bug that does not exist.

Write the resolved form into config, and later into `.crew/verify.json`:
`terraform` if native, `wsl.exe -e terraform` if it only lives in WSL. Resolve
once here; never branch at runtime. If a tool is WSL-only, say the two things
that bite - `/mnt/c` is dramatically slower than the WSL filesystem, and
credentials do not cross the boundary (a Windows `aws` is not the WSL `aws`) -
and offer moving the clone inside WSL, which removes the problem rather than
wrapping it.

**Done when:** platform recorded, every tool the repo needs resolved to a form
that runs on this machine, and any CRLF or filesystem issue either fixed or
explicitly accepted by me.

## Phase 1 — Config and structure

Run `detect.sh`. If it reports a global `~/.claude/skills/find-skills`, say so:
its trigger competes with `crew-setup` and `crew-verification` for ordinary
requests, and offer to remove it. Never delete it yourself — it is the user's
own global configuration.

Ask the three questions (reviewer, tracker, memory). Create
`.crew/`, `.work/`, `docs/adr/`, `_verify/` from template (README.md, smoke.sh,
run-all.sh, cases/), gitignore
entries for secrets, and a `CLAUDE.md` if absent.

**The CLAUDE.md, whether or not one already exists.** Run:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/claude-md-audit.sh
```

It compares the repo's CLAUDE.md against the template section by section and
prints what is missing, what is extra, the line count against the 60-line
ceiling, and how many template placeholders are still unfilled.

- **No CLAUDE.md:** create it from `repo-claude-template.md` and fill it in with
  me.
- **One already exists:** **append the missing sections, never regenerate.** Most
  legacy repos already have a CLAUDE.md, and the repo's own sections are the
  valuable part - the template only supplies headings the repo has not thought
  about yet. Show me the audit output and ask which missing sections to add.
  Silently skipping this is how a repo ends up crew-managed with no promotion
  discipline and no stop-and-ask list.
- **Over 60 lines:** say so and propose what to move into `.crew/verify.json`.
  Every line loads into every subagent on every delegation.

Read `examples/terraform-CLAUDE.md` and `examples/verify-terraform.json` first —
they show the split between judgment (CLAUDE.md) and mechanism (verify.json),
which is the decision that matters most here. Adapt the shape; never copy the
specifics. Ask for the build command, the run command, the do-not-touch paths,
and the landmine that breaks every time. Forty lines, no more.

**Context handling.** Write the `context` block into config and explain the cycle
in one breath, per the `crew-context` skill:

- Near the limit, the `Stop` hook asks for a handoff note — once per session.
- `PreCompact` snapshots the transcript and writes a skeleton if none exists.
- After `/clear` or `/compact`, `SessionStart` injects the note automatically.

Say plainly that **you cannot clear the session yourself** — a hook runs as a
child process and cannot reset its parent. The `/clear` stays manual, which is
the right place for it to stay.

Tell them the threshold is read from the transcript's own usage records, not
estimated, and that the window is derived from the model (Claude 5 family 1M,
Haiku and 4.x 200k) and corrected by the session's peak. Leave `budgetTokens`
at `null` unless `/context` and the warning disagree.

Add `.crew/transcripts/` to `.gitignore` — raw transcripts contain everything
the session saw, including any secret that reached it.

**Done when:** `.crew/config.json` is complete, `claude-md-audit.sh` reports no
missing sections and no remaining placeholders,
and `.gitignore` covers secrets and transcripts.

## Phase 2 — Providers and notifications

Run `providers.sh`. Then, per the `crew-providers` skill:

- **QA:** if `codex` is present, make one real call to prove auth works. If it is
  absent, tell me what the fallback costs and let me decide whether to install it.
- **Design:** offer Gemini. Walk me through getting a key from AI Studio if I
  want it, and confirm the CLI's non-interactive flag rather than assuming.
  Write `secondOpinion` into config with `sendsCode: false`.
- If I decline both, set them to `none` and say what that means for the loop.

**Notifications.** Offer them, do not assume them. Per the `crew-notify` skill:

- Ask whether they want Teams, Telegram, or neither.
- **Teams:** walk them through the Workflows (Power Automate) webhook. The old
  Connectors path was permanently disabled in May 2026, so any tutorial they
  find describing "channel → Connectors → Incoming Webhook" is dead. Have them
  export the URL to an env var — it is the credential for that channel.
- **Telegram:** BotFather → token → they message the bot first (a bot cannot
  open a conversation) → read the chat id from `getUpdates`. Group ids are
  negative; that is normal.
- Write the `notify` block with a **short** `events` list. Push back on
  selecting everything: a channel that pings constantly gets muted within a
  week, and a muted channel is worse than none because they believe they are
  covered.
- Send one real test message and confirm they saw it.

**Cloud MCP (optional).** If this repo deploys to AWS or Azure, offer the
official servers per the `crew-cloud` skill. Start with the AWS documentation and
pricing servers, which touch no account. Only add account-reaching servers once a
task needs one, and only after confirming the credential is a scoped read-only
profile — not the daily driver, never production. The credential is the boundary;
there is no read-only flag that substitutes for it.

Notifications are outbound only. If they ask about driving crew from chat, read
them the two-way section of `crew-notify` before agreeing to anything.

**Done when:** every configured provider has completed one real round trip, and
if notifications are on, a test message has actually arrived. Not when something
is found on PATH or a URL is pasted — those are different things, and the
difference shows up later as a gate that never fires.

## Phase 3 — Smoke harness in `_verify/`

Checks live in `_verify/`. Look for it first, along with `qa/`, `spec/` and
`_test*/`. If the repo already has one of those, adopt it — do not build a
second home for checks beside an existing one.

If none exists, create `_verify/` from `templates/_verify/`: `README.md`,
`smoke.sh`, `run-all.sh`, and an empty `cases/`. Then delegate to
`crew:smoke-author` to fill it. Nothing else happens in this repo until
`bash _verify/smoke.sh` runs green from a clean checkout.

`_verify/README.md` is part of the deliverable, not an afterthought. Its layout
table lists what each script covers and its status table records when each check
was last sabotage-tested. Update both as checks are added; a check with no row is
a check nobody knows about.

`scripts/smoke.sh` is still honoured if a repo already has one — the gate checks
`_verify/smoke.sh` first and falls back. Do not migrate a working harness just
to move it.

If it cannot reach green — missing fixtures, prod-only dependencies — mark the
phase `blocked`, write the reasons into `.work/SMOKE-GAPS.md`, and bring them to
me. Do not proceed to Phase 4 with a red or vacuous harness. A gate that passes
because it checks nothing is worse than no gate.

**Done when:** `_verify/` exists with a current `README.md`, and
`bash _verify/smoke.sh` is green from a clean checkout, under ~90 seconds, 5–9
real checks.

## Phase 4 — Code map

`/crew:onboard`. One `explorer` per subsystem, capped at six per run. Every claim
anchored to a file path and a sha.

**Done when:** `.crew/codemap/INDEX.md` exists and every subsystem file carries
an anchor. Report which areas are still unmapped rather than implying full coverage.

## Phase 5 — Verification map

`/crew:verify`. Build `.crew/verify.json` from git history, and **verify each
pairing by breaking the code and confirming the mapped check goes red.**

Report every pairing that stayed green — those are coverage holes, and finding
them is half the value of this phase.

**Also in this phase:**

- **Repo conventions.** Map every script in `_verify/` (and any `qa/`, `spec/`
  equivalent) to a rule. A script in `_verify/` that no rule names never runs,
  which is the exact failure this directory was meant to prevent. Cross-check
  against `_verify/README.md`: anything in the layout table with no rule, or any
  rule pointing at a script the README does not list, is drift — fix both.
- **Linters.** Per the `crew-lint` skill, add path-scoped rules for the languages
  actually present. Baseline existing findings so the gate starts green — a gate
  that starts red never becomes a gate.
- **Terraform.** If there are `.tf` files, set up terraform-docs and tflint per
  `crew-terraform`. Put the **`--output-check`** form in the gate, never the
  writing form: `terraform-docs markdown table . --output-file README.md
  --output-check` fails when the README is stale instead of rewriting it. The
  writing form mutates the tree mid-gate, which makes `README.md` a changed file
  on the next run and trips `unmapped: fail` in a loop. Run the writing form by
  hand, or from `/crew:docs`.

**Re-run the resolver once the map exists**, because now it can read the map
rather than being told:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/resolve-tools.sh
```

With no arguments it extracts the first word of every command in every `run`,
`always`, `default` and environment list, and reports each as native, WSL-only,
or missing. Any `MISSING` row is a rule that will fail at the gate on the turn
someone needed it. Fix them now, or delete the rule and record in
`.crew/STATUS.md` that you did.

**Done when:** rules cover the hot paths, each is verified, `"unmapped": "fail"`,
`resolve-tools.sh` reports no MISSING tool, and linters run green on the current
tree.

## Phase 6 — Browser tests

Skip with `n/a` if there is no UI. Otherwise **install Playwright first** and
confirm it runs:

```
npm init playwright@latest
npx playwright install --with-deps chromium
npx playwright test --list
```

Chromium alone unless there is evidence of a browser-specific bug. Then delegate
to `crew:browser-tester`
for the two or three flows where breakage is expensive, plus visual baselines
for the pages that matter. Tag `@visual` and `@flow`, then add the rules to
`verify.json`.

**Done when:** `npx playwright test` passes with no agent attached.

## Phase 8 — Promotion gates

Read `crew-verification` section 4 first. Add the `environments` block to
`.crew/verify.json` so `development -> qa -> production` is declared rather than
remembered.

Ask me, per environment, and do not guess any of it:

- What actually deploys it? The command, not the concept.
- What proves it responded — the `smoke` command against **that** environment.
- What proves nothing else broke — the `regression` command. This is a separate
  gate from smoke and it is the one that catches the module three directories
  over. A setup with only smoke has skipped it.
- What signals do we read afterwards — error logs, alarms, queue depth — and how
  long do we wait first (`soakMinutes`).
- Where is the rollback runbook, and when was it last verified?

Fill in only what exists. An `environments` block with `deploy` and `smoke` and
nothing else is honest. One with five aspirational commands nobody has run is
worse than an empty file, because it reads as coverage.

Set `requireHuman: true` on production. Create `.work/PROMOTIONS.md` with its
header row. Then run `/crew:promote development --dry-run` and read the sequence
back to me before anything real is deployed.

**Two of these are enforced by a hook, not by good intentions.** `promote-gate.sh`
runs on `PreToolUse` and refuses a command matching a declared `deploy` entry
unless, for the sha at HEAD:

- every environment in `requires` has an **all-pass** row in `.work/PROMOTIONS.md`
- the `rollback` runbook exists and carries `last verified: YYYY-MM-DD` inside 90 days
- `requireHuman` has an approval marker at `.crew/.approved-<env>-<sha>`
- the working tree is clean

And `verify-gate.sh` will not let the turn end after a deploy that wrote no
`.work/PROMOTIONS.md` row. So the log is not paperwork - it is the thing the next
promotion reads.

**Two consequences to set up now.** `.gitignore` must cover `.crew/` and `.work/`,
or the gate's own marker file dirties the tree and blocks the next deploy. And
the rollback runbook needs a literal `last verified: YYYY-MM-DD` line, because
that is what the hook greps for.

**Done when:** the `environments` block matches how this repo genuinely ships,
`.work/PROMOTIONS.md` exists with its header, production has a `rollback` path
pointing at a runbook that carries a fresh `last verified` line, `.gitignore`
covers `.crew/` and `.work/`, and `--dry-run` prints a sequence I recognise.

## Phase 7 — First real ticket

Run one small, real piece of work end to end: `/crew:ticket` → `/crew:plan` if
the design is not obvious → `/crew:work` → `/crew:review`.

Pick something genuinely small. The purpose is to test the loop, not the code.

Afterwards, tell me what was awkward. The prompts in this plugin are written, not
proven — the first ticket is where that shows, and the fix is usually editing a
command file rather than working around it.

**Done when:** one ticket has been through the full loop and the metrics line
exists. If notifications are on, confirm the `review` and `done` messages
actually arrived.

---

## After Phase 7

Say this plainly:

- Repeat Phases 0–5 for the next repo when this one has earned it — not before.
- Run `/crew:survey` now that there is a safety net worth acting on.
- Write the first runbook for whatever this repo's deploy or rollback actually
  is, then `/crew:runbook --verify` it. An unverified runbook is a guess
  formatted as instructions.
- Run `/crew:scale` after about ten tickets, and believe the numbers over the
  ambition.
