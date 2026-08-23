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
      "run": ["dotnet test tests/Api --no-restore", "./scripts/smoke.sh"],
      "why": "Domain changes break API contracts; smoke catches boot failures" },

    { "paths": ["**/*.css", "**/*.scss", "src/components/**"],
      "run": ["npx playwright test --grep @visual"],
      "why": "Style changes are invisible to API tests" },

    { "paths": ["migrations/**", "**/*.sql"],
      "run": ["./scripts/_smoke/migrate-fresh.sh", "./scripts/smoke.sh"],
      "agents": ["dba"],
      "why": "Fresh-database apply is the only check that catches ordering bugs" },

    { "paths": ["terraform/**"],
      "run": ["terraform validate", "terraform plan -no-color"],
      "why": "Plan is the review artifact; apply is never automatic" }
  ],
  "always": ["npm run lint"],
  "default": ["./scripts/smoke.sh"],
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
