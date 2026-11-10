<!-- Moved verbatim from plugin/crew/README.md (8. Verification, secrets, and browser tests) by L-0726; the README keeps an index entry. -->

## 8. Verification, secrets, and browser tests

A code map describes the codebase. It does not verify anything. These three
artifacts are what actually reduce mistakes.

### The verification map

```
/crew:verify
```

Builds `.crew/verify.json` — a routing table from changed paths to the checks
those paths require:

```json
{
  "rules": [
    { "paths": ["src/Api/**"], "run": ["dotnet test tests/Api", "./_verify/smoke.sh"],
      "why": "Domain changes break API contracts" },
    { "paths": ["**/*.css", "src/components/**"], "run": ["npx playwright test --grep @visual"],
      "why": "Style changes are invisible to API tests" },
    { "paths": ["migrations/**"], "run": ["./_verify/cases/migrate-fresh.sh"],
      "agents": ["dba"], "why": "Fresh-apply catches ordering bugs" },
    { "paths": ["**/*.ps1"], "run": ["pwsh -NoProfile -Command \"Invoke-ScriptAnalyzer -Path . -Recurse -EnableExit\""],
      "agents": ["powershell-security-hardening"], "why": "runs with real privilege; a linter sees style, not blast radius" }
  ],
  "always": ["npm run lint"],
  "unmapped": "fail"
}
```

This is a data file a hook reads, deliberately not knowledge an agent carries.
Agent judgment about which tests to skip is exactly the judgment that skips the
important one, confidently, on the turn it mattered.

`agents` names **any installed subagent**, not only crew's own roles. This
sentence said "crew's eleven" until 2026-09-14, long after `agents/` stopped
holding eleven files; the count is deliberately gone rather than corrected,
because the roster moves and nothing checks a number written here — the same
shape `commands/review.md` uses, which `tests/test_verify_absent_and_diagram_kind.py`
holds in place. Both rules above happen to name roles crew does ship, but a name
from any other installed plugin works the same way. A bare name resolves to
crew's own role first
(`security` → `crew:security`), then to any other installed agent of that name;
namespace it when you mean the other one. This is how a machine's domain
specialists get pulled in *by path match* rather than when somebody remembers
they exist — the change touches `.tf` under `iam/`, so the IAM auditor reviews it,
every time, without being asked.

The safeguard matters as much as the feature. `.crew/verify.json` is committed
and travels between machines — it is one of the three paths on the un-ignore list
(`!.crew/codemap/`, `!.crew/endpoints.json`, `!.crew/verify.json`) that `.crew/*`
would otherwise ignore — so a rule naming an agent the author has and a teammate
does not would quietly review less on the second machine while producing output
that looks identical. Travelling is exactly what makes the gap possible; it is
also the only reason the map is worth writing once. `/crew:review` therefore reports a named-but-missing
agent as a gap and logs it to `.crew/metrics.md`, so "this rule asked for
`security-auditor` eleven times and never got it" becomes evidence for either
installing it or deleting the rule.

Each pairing is **verified when written**: break the code, run the mapped check,
confirm it goes red, revert. An unverified mapping is a guess written in JSON —
and a pairing that stays green has just told you about a coverage hole.

### Checks and rules are written together

**Whoever writes a check writes its rule, in the same turn.** The implementing
session does this, and proves the rule fires before calling
it done — break the code, run the mapped command, confirm red, revert.

The failure this prevents is quiet and common: a check exists, is committed, is
visible in the repo, and never runs. Nobody finds out until the change it was
meant to catch ships. **An unmapped check is worse than a missing one, because
it reads as coverage.**

Watch the tag/grep interaction on browser tests in particular: a rule running
`--grep @visual` does not run your new `@flow` spec. That is the most common way
UI coverage ends up existing but never executing.

```bash
bash skills/crew-setup/scripts/map-audit.sh   # or /crew:verify --sync
```

Reports both directions — checks on disk that no rule invokes, and rules pointing
at files that no longer exist. Run it after any session that touched tests.

### After database changes

Code-level rules do not cover schema. A migration needs three checks, and the
rule runs all three:

| Check | Catches |
|---|---|
| Fresh apply to an empty database | Ordering bugs invisible on an already-migrated dev box |
| Rollback apply | An untested down script, which is not a rollback |
| Round trip through the changed path | Shape errors a successful migration hides |

The third is the one people skip, and it is the one that matters: a migration
that applies cleanly and leaves a column nullable the code assumes is populated
passes the first two and fails in production.

The implementing session writes the specific check — which script, what it
asserts, which paths — with the `stack-sql` skill loaded.

`"unmapped": "fail"` is the most valuable line in the file. A changed path with
no rule blocks the turn and names the file, so "we forgot to test that area"
becomes a visible condition rather than a silent one, and the map improves as a
side effect of normal work. Two kinds of path are never unmapped (T-0068):
crew's own bookkeeping (`crew_ticket.CREW_BOOKKEEPING_PATHS` - the gate's own
records, the scope base, the metrics files), which leaves the changed list
altogether, and the refresh artifacts (`.crew/codemap/`, the diagrams dir, the
graph dir, `.claude/rules/`), which `/crew:done` checks for freshness on its
own - a rule that names one still runs.

### Secrets

**The agent learns the access pattern. It never handles the value.**
`.crew/secrets.md` records where a secret lives, its identifier, which
environment variable it lands in, and the command that retrieves it. Names and
commands only.

The reason is not squeamishness. A secret printed into a command result does not
stay in the conversation: it is written to the on-disk session transcript,
carried into compaction summaries, and repeated into every subagent receiving
that context. You cannot un-print it; rotation is the only remedy.

`guard.sh` enforces this — a bare `aws secretsmanager get-secret-value` is
blocked, while capturing into an environment variable is allowed.

Preferred order for test credentials, and the order people usually invert:

1. **No credential at all** — ephemeral containers with seeded fixtures
2. **`.env.smoke`, gitignored** — test-only values, offline, reviewable
3. **A secret store with test-scoped credentials** — read-only, separate account

Option 3 is reached for first and belongs last. A suite that needs cloud
credentials cannot run on a plane, in CI without a role, or on a new laptop.

Never: production credentials in any automated check, a secret in any config or
fixture, or `AWS_PROFILE=production` anywhere reachable.

### Browser tests

```
Write Playwright specs for the checkout flow and the pricing page styling
```

Deliverables are spec files under `e2e/`, runnable by `npx playwright test` with
no agent and no MCP server attached. A test that only works while an agent drives
a browser is a demo, not a regression suite.

- Locators: `getByRole`, `getByLabel`, `getByTestId`. Never CSS selectors tied to
  layout classes — those break on exactly the styling changes you are validating,
  producing failures that teach people to ignore the suite.
- CSS: screenshot comparison against committed baselines, dynamic regions masked,
  viewport pinned, animations disabled.
- `retries: 0`, deliberately. Retries convert a race condition into a
  statistically-passing test, which is how a real bug survives to production.
- Flaky and unfixable goes to `e2e/quarantine/` with a reason, never papered over.

Use the Playwright MCP server to *explore* a flow interactively, then write the
spec. The spec is the asset.

Tag specs `@visual` and `@flow` so `verify.json` can run them selectively.
