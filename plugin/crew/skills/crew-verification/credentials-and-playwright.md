# Credentials And Playwright

_Extracted from `SKILL.md` to keep the main file under the
500-line progressive-disclosure limit. Nothing was changed in the
move._

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

