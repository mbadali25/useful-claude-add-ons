---
name: crew-verification
description: Build the verification map, wire test credentials safely, and set up Playwright. Use when the user asks which tests should run after a change, says set up the test map, add browser tests, add visual testing, validate UI changes, or when tests need credentials from AWS Secrets Manager, Vault, Key Vault, or a .env file.
---

# Verification

Three pieces: a map from changed files to the checks they require, a safe path
for credentials, and browser coverage for what an API check cannot see.

---

## 1. The verification map

The goal is not for an agent to *remember* which tests matter. Agent judgment
about which tests to skip is exactly the judgment that skips the important one,
confidently, on the turn where it mattered. The goal is a **data file a hook
reads**, so the decision is deterministic and reviewable.

Write `.crew/verify.json`:

```json
{
  "version": 1,
  "anchor": "repo@a1b2c3d",
  "rules": [
    { "paths": ["src/Api/**", "src/Domain/**"],
      "run": ["dotnet test tests/Api --no-restore", "./_verify/smoke.sh"],
      "why": "Domain changes break API contracts; smoke catches boot failures" },

    { "paths": ["**/*.css", "**/*.scss", "src/components/**"],
      "run": ["npx playwright test --grep @visual"],
      "why": "Style changes are invisible to API tests" },

    { "paths": ["migrations/**", "**/*.sql"],
      "run": ["./_verify/cases/migrate-fresh.sh", "./_verify/smoke.sh"],
      "agents": ["dba"],
      "why": "Fresh-database apply is the only check that catches ordering bugs" },

    { "paths": ["terraform/**"],
      "run": ["terraform validate", "terraform plan -no-color"],
      "why": "Plan is the review artifact; apply is never automatic" }
  ],
  "always": ["npm run lint"],
  "default": ["./_verify/smoke.sh"],
  "unmapped": "fail"
}
```

### Find the repo's own conventions first

Before deriving anything, look for verification the team already built. Repos
often carry a convention the tooling knows nothing about:

```bash
find . -maxdepth 3 -type d \( -name '_verify' -o -name '_test*' -o -name 'tests' \
  -o -name 'spec' -o -name 'e2e' -o -name '__tests__' -o -name 'qa' \) \
  -not -path './node_modules/*' -not -path './.git/*'
```

A `_verify/` directory (or any local equivalent) is a deliberate signal from
whoever built it. **Nothing in crew discovers it automatically** — you have to
read it and map it, once.

When you find one, ask the user rather than guessing:

- What runs it? A script, a test runner, or is it read by a human?
- Which changes should trigger it?
- Does it need credentials or a running service?

Then give it a rule of its own in `verify.json`, naming the directory in `why`
so the mapping survives the person who explained it:

```json
{ "paths": ["src/loaders/**"],
  "run": ["bash _verify/run.sh loaders"],
  "why": "_verify/ holds the team's hand-written QA checks for loader changes" }
```

If a `_verify` directory exists but nothing runs it, say so. An unrun check
directory is worse than none: it reads like coverage to the next person.

### How to build the rest

Derive it from evidence, not from a naming convention:

1. `git log --format= --name-only -300 | sort | uniq -c | sort -rn | head -30`
   — what actually changes.
2. For each hot path, find the test that would have caught a break in it. Run
   that test, break the code deliberately, confirm it goes red. **An unverified
   mapping is a guess.** If the test stays green, the mapping is wrong and you
   have just learned something important about your coverage.
3. Record the pairing with a `why`. A rule nobody can justify gets deleted in six
   months by someone who assumes it was cargo cult.

### Which keys are executed, and which are for you

Not every key in `verify.json` is read by the gate, and it matters which is
which - a key that looks executable and is not is how a rule ends up trusted
without ever running.

| Key | Read by |
|---|---|
| `paths`, `run`, `always`, `default`, `unmapped` | the `Stop` hook. These execute. |
| `agents` | `/crew:review` - the hook cannot spawn a subagent, so specialist review is a review-time concern |
| `agents`, continued | any installed subagent, not only crew's own. See below. |
| `environments` and everything under it | `/crew:promote` |
| `why`, `anchor`, `version` | **nothing.** They are notes for the next human. |

`why` is worth writing anyway: a rule whose reason nobody remembers gets deleted
the first time it is inconvenient. `anchor` records the sha the map was built
against, so you can tell how stale it is. Neither changes what runs.

### `agents` can name any installed subagent

Crew ships eleven roles. A machine usually has many more — domain specialists
from other marketplaces, and whatever the user wrote themselves. A rule may name
any of them, and the point is that a path match dispatches the right expert
*from evidence* instead of when somebody happens to remember it exists:

```json
{ "paths": ["**/*.ps1", "**/*.psm1"],
  "agents": ["powershell-security-hardening"],
  "why": "these run with real privilege on domain-joined hosts" },

{ "paths": ["iam/**", "**/policy*.json", "**/*iam*.tf"],
  "agents": ["security", "security-auditor"],
  "why": "crew's reviewer for the diff, the domain auditor for the model" }
```

Resolution order for a bare name: crew's own role first (`security` →
`crew:security`), then any other installed agent of that name. Namespace it
(`crew:security`, `voltagent:security-auditor`) when both exist and you mean the
other one.

**A named agent that is not installed is a reported gap, never a silent skip.**
This is the whole risk of the feature: `.crew/verify.json` is committed and
shared, so a rule naming an agent that one machine has and another does not will
quietly review less on the second machine, and nothing about the output looks
different. `/crew:review` therefore lists every agent a matched rule asked for
and could not find, and treats it exactly like a specialist that was skipped.

Two agents, one job, is the failure mode on the other side. Naming `security`,
`security-auditor` and `security-engineer` on the same rule buys three
overlapping passes and three sets of duplicated findings to reconcile. Pick the
one whose brief actually matches the change, and say in `why` why that one.

### The authoring contract

**Whoever writes a check writes its rule, in the same turn.** This applies to
`smoke-author`, `browser-tester`, and to you when you add a check by hand.

The failure this prevents is subtle and common: a check exists, is committed, is
visible in the repo, and never runs. Nobody discovers that until the change it
was supposed to catch ships. An unmapped check is worse than a missing one,
because it reads as coverage.

Reconcile both directions with:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/map-audit.sh
```

It reports checks on disk that no rule invokes, and rules pointing at files that
no longer exist. Run it at the end of any session that touched tests, and in
`/crew:verify --sync`.

### Every check ships a demonstrated failing control

A check that has never failed has never been shown to be able to fail. Writing
one and watching it go green proves only that green is reachable — and a check
that can only be green is worse than no check, because it retires the question
it appears to answer.

So the check is not finished until you have broken the thing it watches and
seen it go **red with a message that names what is wrong**. Delete the line it
asserts on, invert the condition, drop a file it counts, hand it the bad input
— whichever mutation corresponds to the defect the check exists for. Then
restore, and record it: the `Last sabotage-tested` column in `_verify/README.md`
is that record.

The shapes that pass green forever, all of which have shipped:

| Shape | What it looks like | What it misses |
|---|---|---|
| Floor far below the real count | `assert count >= 2` where 33 exist | a regression dropping 31 of them |
| Stale expected data | the expected table still names the old host or column | goes red on a *correct* change, green on the broken one |
| Syntax standing in for behaviour | a parse check, a lint pass, a dry run reported as "it runs" | everything that only happens at runtime |
| A sample that cannot discriminate | two rows, so every sort ties; an empty scope, so a deny "passes" | the ordering or permission it claims to prove |
| An assertion on the wrong object | the workflow run, not the job; the exit code, not the artifact | a step that was skipped, a deploy that shipped nothing |

Two rules follow, and both are cheap:

- **Assert against the real number, not a floor you know is safe.** If the
  count is derived, derive it in the check.
- **A negative proof needs a populated positive side.** "Access was denied"
  means nothing against an empty scope. State the setup that makes the denial
  discriminating, or the proof does not count.

The reviewer's half of this is in `/crew:review`: re-run the mutation rather
than reading a transcript of it.

### After database changes

Code-level rules do not cover schema. A migration needs three checks, and the
rule runs all three:

| Check | Catches |
|---|---|
| Fresh apply to an empty database | Ordering bugs invisible on an already-migrated dev box |
| Rollback apply | An untested down script, which is not a rollback |
| Round trip through the changed path | Shape errors that a successful migration hides |

The third is the one people skip. A migration that applies cleanly and leaves a
column nullable that the code assumes is populated will pass the first two.

All three run against a **real database** — ephemeral, containerised, or dev.
Parse-checking a migration is a lint pass, not an apply, and the defects that
only appear at apply time are the expensive ones: a string literal overflowing
its column's width, a lock taken on a table with rows in it, a changelog row
that rolls back while the DDL beside it commits. A migration whose first real
apply happens in production has no verification at all, however many people
read it.

### `"unmapped": "fail"`

If a changed file matches no rule, the gate fails and names the file. This is the
single most valuable line in the config: it converts "we forgot to test that
area" from a silent condition into a blocking one, and it makes the map improve
as a side effect of normal work.

Set it to `"warn"` only while first building the map.

### Cost discipline

The map exists to run *fewer* checks, not more. If every rule runs the full
suite, delete the map and just run the suite. Target under three minutes for a
typical change; put the slow, broad checks in CI on the pull request instead.

---

## 2. Credentials and secrets

### The rule

**The agent learns the access pattern. It never handles the value.**

Record in `.crew/secrets.md`:

```
## Test database password
where: AWS Secrets Manager, us-east-1
id: myapp/test/db
into: PGPASSWORD
how: export PGPASSWORD=$(aws secretsmanager get-secret-value \
       --secret-id myapp/test/db --query SecretString --output text)
scope: test account only. No production secret is reachable from this repo.
```

Names, locations, and retrieval commands. Never values.

### Why this is a hard line

A secret value printed into a command result does not stay in the conversation.
It is written to the session transcript on disk, carried into any compaction
summary, and repeated into every subagent that receives that context. You cannot
un-print it, and rotating afterward is the only real remedy.

The `guard.sh` hook blocks bare secret reads for this reason. Capturing into an
environment variable is allowed; printing to stdout is not.

### Preferred order for test credentials

1. **No credential at all** — ephemeral containers with fixture data. A local
   Postgres with a seeded schema needs no secret and no network.
2. **`.env.smoke`, gitignored** — a local file with test-only values, referenced
   by name in documentation. Simple, offline, reviewable.
3. **A secret store with test-scoped credentials** — read-only IAM, a separate
   account or namespace, never the production principal.

Option 3 is the one people reach for first and it should be the last. A smoke
suite that needs cloud credentials cannot run on a plane, in CI without a role,
or on a new laptop until someone grants access.

### Platform note

Under WSL2, a database or service running on the Windows host is not on
`localhost`. Put the host IP in `.env.smoke` as a variable rather than hardcoding
it — it changes on reboot. On native Windows, capture secrets with
`$env:NAME = (...)`, not `export`.

### Never

- Production credentials in any automated check, read-only or not.
- A secret in `verify.json`, `config.json`, a spec file, or a fixture.
- `AWS_PROFILE=production` anywhere the agent can reach.
- Committing `.env` files. Add them to `.gitignore` during setup, before the
  first secret exists.

---

## 3. Playwright

### Install

```bash
npm init playwright@latest
npx playwright install --with-deps chromium
```

Chromium alone is usually enough. Add browsers when you have evidence of a
browser-specific bug, not preemptively — each one multiplies runtime and baselines.

### Config that keeps the suite honest

```js
// playwright.config.js
export default {
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,                        // deliberate: see below
  use: {
    baseURL: process.env.APP_URL ?? 'http://localhost:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    reducedMotion: 'reduce',
  },
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
};
```

`retries: 0` is intentional. Retries convert a race condition into a
statistically-passing test, which is how a real bug survives to production. If a
test is flaky, fix the test or fix the race.

### Two modes, different purposes

| Mode | Use for | Runs in CI |
|---|---|---|
| Spec files (`npx playwright test`) | Regression, visual baselines, the gate | Yes |
| Playwright MCP server | Exploring a flow, authoring a new spec | No |

Use MCP to *discover* the flow interactively, then write it down as a spec. The
spec is the asset. An agent driving a browser live is a way to learn what to
write, not a substitute for having written it.

If you add the MCP server, scope it in the repository's `.mcp.json` — plugin
agents cannot declare `mcpServers` in frontmatter.

### Wiring into the gate

Tag specs so the map can be selective:

```js
test('checkout renders correctly @visual', async ({ page }) => { /* ... */ });
test('user can complete checkout @flow', async ({ page }) => { /* ... */ });
```

Then `@visual` on stylesheet changes, `@flow` on anything touching the affected
routes, everything on a release branch.

### What Playwright is not for

Business logic. If a rule can be tested at the unit or API level, test it there —
it will be a hundred times faster and it will not break when a button moves.
Browser tests are for what only a browser can observe: rendering, layout,
navigation, and the integration of the whole stack.

---

## 4. Promotion: development -> qa -> production

A merge is not a deploy, a deploy is not a working application, and a green
pipeline says only that the pipeline is green. Every environment gets its own
post-deploy proof, run against the environment that was just deployed to.

### The order is fixed

```
development  ->  qa  ->  production
```

No skipping. Code reaches production only by having passed the same artifact
through qa. A hotfix is not an exception - it is the same path, run faster.

**The one exception, and it is not really one.** `/crew:emergency` can stand the
gates down for a declared, time-boxed incident: the checks do not run, the
preconditions are recorded rather than enforced, and the deploy is allowed. That
does not make the path optional - it defers it. Every gate that did not run is
written to the incident's skip log, the lane expires on its own (default 120
minutes), and closing it produces a debt list to work through. The order above
still applies to everything after the environment is stable, and a repository
that must never do this sets `emergency.standDown: false`.

### The five gates, per environment

Each promotion runs these in order, and **stops at the first failure**:

| # | Gate | Answers |
|---|---|---|
| 1 | Pre-deploy | Is the source environment still green, is this the artifact it proved, and is the tree reconciled with what the target is running? |
| 2 | Deploy | Did the deploy *job* run, and is the artifact on the box the one we sent? |
| 3 | Smoke | Does the deployed thing respond at all, in this environment? |
| 4 | Regression | Does everything that worked yesterday still work? |
| 5 | Verify | Are the environment's own signals clean - error logs, alarms, queue depth? |

Gate 2 is the weakest evidence in the list and the one most often mistaken for
the whole set. A successful deploy proves bytes moved. Gates 3-5 are what prove
the application works.

Two ways gate 2 lies, and both are green:

- **A conditional deploy step.** Path filters, `if:` guards and changed-file
  checks make a workflow report success having deployed nothing. Read the
  status of the deploy job, not of the run that contains it.
- **The wrong ref.** A pipeline that resolved tooling from one ref and code
  from another is green and wrong. Hash or line-count the file that landed and
  compare it against the source; the log will not tell you.

And one way gate 1 lies: a branch that was never reconciled against the live
environment deploys *backwards*, silently reverting on-box hotfixes and config
changed during an incident. Classify every difference between the live artifact
and the source tree before deploying - roll-forward, on-box edit, or
unexplained - and stop on the last two.

### The mechanism: an `environments` block

Put it in `.crew/verify.json` alongside the path rules. Same file, same idea:
the checks are declared, not remembered.

```json
{
  "rules": [ /* ... path rules, as above ... */ ],
  "environments": {
    "development": {
      "deploy":     ["./scripts/deploy.sh dev"],
      "smoke":      ["./_verify/smoke.sh --env dev"],
      "regression": ["npm test"],
      "verify":     ["./scripts/check-logs.sh dev --since 10m"],
      "rollback":       "none",
      "rollbackReason": "dev is rebuilt on every push; there is nothing to roll back to",
      "promotesTo": "qa"
    },
    "qa": {
      "requires":   ["development"],
      "deploy":     ["./scripts/deploy.sh qa"],
      "smoke":      ["./_verify/smoke.sh --env qa"],
      "regression": ["npm test", "npx playwright test --grep @flow"],
      "verify":     ["./scripts/check-logs.sh qa --since 10m"],
      "soakMinutes": 10,
      "rollback":       "none",
      "rollbackReason": "qa is rebuilt from the latest development deploy; there is nothing to roll back to",
      "promotesTo": "production"
    },
    "production": {
      "requires":     ["qa"],
      "deploy":       ["./scripts/deploy.sh prod"],
      "smoke":        ["./_verify/smoke.sh --env prod"],
      "regression":   ["npx playwright test --grep @flow --project=prod"],
      "verify":       ["./scripts/check-logs.sh prod --since 15m",
                       "./scripts/check-alarms.sh prod"],
      "soakMinutes":  15,
      "rollback":     "docs/runbooks/rollback.md",
      "requireHuman": true
    }
  }
}
```

| Key | Meaning |
|---|---|
| `requires` | Environments that must have a green promotion record first |
| `deploy` | The deploy command. Never inferred |
| `smoke` | Does it respond - fast, shallow, this environment |
| `regression` | Does everything else still work - the slow, broad suite |
| `verify` | The environment's own signals: logs, alarms, queues, dashboards |
| `soakMinutes` | Wait this long after deploy before running `verify` |
| `rollback` | Path to the runbook, or the literal `"none"` plus a `rollbackReason`. Required - an absent key blocks the deploy |
| `rollbackReason` | Required alongside `rollback: "none"`. Why this environment does not need a rollback plan |
| `requireHuman` | Stop and get explicit approval before deploying |

**Limitation: this file is data, not enforcement by itself.** `promote-gate.sh`
reads `.crew/verify.json` and blocks a matching `deploy` command - but that
hook only runs inside a Claude Code session that has the crew plugin active.
A fresh session without it (a teammate who never installed crew, a different
machine, any tool other than Claude Code) can run the same `deploy` command
straight through, `requires`/`rollback`/`requireHuman` and all, because none
of those checks live in this file - they live in the hook that reads it. This
`.crew/verify.json` is the same, unguarded JSON in every session; only the
plugin being active turns it into a gate.

### The promotion record

Every promotion appends one line to `.work/PROMOTIONS.md`:

```
| when (UTC) | env | sha | smoke | regression | verify | by |
|---|---|---|---|---|---|---|
| 2026-08-23T14:02Z | qa | a1b2c3d | pass | pass | pass | mbadali |
| 2026-08-23T15:40Z | production | a1b2c3d | pass | pass | FAIL | mbadali |
```

This is what `requires` reads. It is also the only honest answer to "is prod
running the thing qa signed off on" - compare the shas, not the branch names.

Record failures too. A promotions log with no failures in it is a log nobody
is actually writing to.

### Rules that are not negotiable

- **The sha must match across environments.** A rebuild between qa and prod is
  a different artifact, and qa proved nothing about it.
- **Smoke and regression are separate gates.** Smoke that passes tells you the
  deploy landed; it says nothing about the feature that broke three modules over.
  A run that only smoke-tests has skipped the gate that catches regressions.
- **`verify` runs after the soak, not immediately.** Errors surface on the first
  real traffic, which arrives after the deploy finishes, not during it.
- **Every gated environment declares a rollback plan, or says explicitly why
  it does not need one.** A verified runbook inside 90 days, or
  `rollback: "none"` plus a `rollbackReason` - never a silently absent key.
  Production without a verified runbook is the one case with no override.
- **A failed gate is a stop, not a note.** Roll back or fix forward, then run the
  whole sequence again from gate 1. Do not resume mid-sequence.

### What to do when the repo has none of this

Most legacy repos have a deploy script and nothing else. Do not invent five
scripts. Build the sequence in the order it pays off:

1. `smoke` for the environment you deploy to most - one command, exit non-zero
   on failure. This is the whole of `crew-verification` section 1 applied to a
   running system rather than a working tree.
2. `verify` - even `grep -c ERROR` over the last ten minutes of log beats nothing,
   because it turns "looks fine" into a number.
3. `regression` last. It is the most expensive to build and the least useful
   until the first two are trustworthy.

An `environments` block with only `deploy` and `smoke` filled in is honest and
useful. One with five aspirational commands that nobody has run is worse than
an empty file, because it reads as coverage.
