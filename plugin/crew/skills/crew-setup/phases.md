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
```

States: `todo`, `in progress`, `partial`, `blocked`, `done`, `n/a`.
Be honest with `partial` and `blocked`. A status file that says `done` when a
thing half works is how the whole system quietly stops meaning anything.

---

## Phase 0 — Platform

Run `platform.sh` (or `platform.ps1` on native Windows). Record the `platform`
block in `.crew/config.json`. Act on `windows-mount` and `crlfDetected` per
`crew-setup/platform.md`, and ask before re-cloning anything.

**Done when:** platform recorded, and any CRLF or filesystem issue either fixed
or explicitly accepted by me.

## Phase 1 — Config and structure

Run `detect.sh`. Ask the three questions (reviewer, tracker, memory). Create
`.crew/`, `.work/`, `docs/adr/`, `scripts/smoke.sh` from template, gitignore
entries for secrets, and a `CLAUDE.md` if absent.

Then **fill in the CLAUDE.md with me**, do not leave the template blanks. Ask
for the build command, the run command, the do-not-touch paths, and the landmine
that breaks every time. Thirty lines, no more.

**Context handling.** Write the `context` block into config and explain the cycle
in one breath, per the `crew-context` skill:

- Near the limit, the `Stop` hook asks for a handoff note — once per session.
- `PreCompact` snapshots the transcript and writes a skeleton if none exists.
- After `/clear` or `/compact`, `SessionStart` injects the note automatically.

Say plainly that **you cannot clear the session yourself** — a hook runs as a
child process and cannot reset its parent. The `/clear` stays manual, which is
the right place for it to stay.

Tell them the threshold is an estimate from transcript size, not a token count,
and that they should calibrate once against `/context` and adjust
`budgetTokens`. Being early is fine; being late defeats the purpose.

Add `.crew/transcripts/` to `.gitignore` — raw transcripts contain everything
the session saw, including any secret that reached it.

**Done when:** `.crew/config.json` is complete, `CLAUDE.md` has no placeholders,
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

## Phase 3 — Smoke harness

Delegate to `crew:smoke-author`. Nothing else happens in this repo until
`./scripts/smoke.sh` runs green from a clean checkout.

If it cannot reach green — missing fixtures, prod-only dependencies — mark the
phase `blocked`, write the reasons into `.work/SMOKE-GAPS.md`, and bring them to
me. Do not proceed to Phase 4 with a red or vacuous harness. A gate that passes
because it checks nothing is worse than no gate.

**Done when:** green from a clean checkout, under ~90 seconds, 5–9 real checks.

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

- **Repo conventions.** Search for `_verify/`, `qa/`, `spec/` and similar. If one
  exists, ask what runs it and give it a rule. This is the most commonly missed
  step and the most valuable one.
- **Linters.** Per the `crew-lint` skill, add path-scoped rules for the languages
  actually present. Baseline existing findings so the gate starts green — a gate
  that starts red never becomes a gate.
- **Terraform.** If there are `.tf` files, set up terraform-docs and tflint per
  `crew-terraform`, and put `terraform-docs .` in the gate so an undocumented
  variable shows up as a README diff in the pull request.

**Done when:** rules cover the hot paths, each is verified, `"unmapped": "fail"`,
and linters run green on the current tree.

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
