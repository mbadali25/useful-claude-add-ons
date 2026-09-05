# TODO

Findings queued for a later PR. Each carries the `path:line` it came from so it
can be re-verified rather than re-discovered — and so an item that turns out to
be wrong can be closed on evidence.

Opened 2026-09-05 from the codemap pass (`.crew/codemap/`). Every citation here
was checked against source when it was written; anchor `fe538879`.

## Blast radius — act on these first

### 1. `gizmoduck` opens real SDP tickets with no per-item gate

`plugin/gizmoduck/commands/scan.md:6-8` and `commands/tickets.md:5-7` both
instruct auto-creating one ticket per Critical/High finding and explicitly say
not to prompt per ticket. Floor is `high`
(`plugin/gizmoduck/scripts/gizmoduck.py:426`). De-dupe is a subject search for
an existing open `[Nuclei <template-id>]` only.

A scan of a noisy target can therefore file real tickets in a real system
unattended.

**Unresolved, and it decides the fix:** whether the `infra-work-ticketing`
skill or the SDP MCP tools impose their own confirmation. That file was not
read. If they do gate it, this is documentation-only. If they do not, this
needs a gate or an explicit opt-in flag.

### 2. `mcp-servers/core` credential chain caches its winner permanently

`AdminCredentialChain` (`mcp-servers/packages/core/src/adminAuth.ts:48-109`)
stores whichever link first succeeds in `this.resolved` and never retries an
earlier link for the process lifetime. Deliberate — the comment at `:44-46`
says so — but the consequence is that fixing `MS_ADMIN_CLIENT_SECRET` after
`cli` or `device` has won changes nothing until restart, and nothing says so.

Not necessarily a code change. A log line naming which link won, once, would
turn a silent wrong-identity into an obvious one.

### 3. `scopesOverride` silently broadens a narrow scope request

`src/adminAuth.ts:29-36`, `:127`, `:144` force `.default` for the `secret` and
`cli` links regardless of what the caller asked for. Only `device` honours
caller-supplied delegated scopes (`:159`).

Code that requests a narrow scope and receives `.default` did not fail — it was
never asked. That is the wrong default for a least-privilege story and should
at minimum be loud.

## Correctness and verification gaps

### 4. `vault_guard.py` blocks every edit to a vault's own `CLAUDE.md`

`plugin/obsidian-vault/hooks/scripts/vault_guard.py:35` exempts `CLAUDE.md`
from the ASCII check **by design**, but not from the frontmatter check — so the
vault's instructions file is required to carry note frontmatter it can never
have. Every edit to it blocks.

Hit twice on 2026-09-05 while widening the `wiki/decisions` scope. The write
still lands (`PostToolUse`), so it is noise rather than prevention — but it is
noise on a legitimate, necessary edit, and it trains people to ignore the
guard. Extend the existing exemption to cover the frontmatter rule.

**A fix is already written and stashed**, not lost: `git stash list` ->
`TODO#4: vault_guard frontmatter exemption`. It adds
`FRONTMATTER_EXEMPT_NAMES = {"claude.md", "readme.md", "agents.md",
"gemini.md"}` and skips `check_note` for those basenames. It was kept out of
the crew 0.16.0 PR on purpose - an `obsidian-vault` file changing in that PR
would force an `obsidian-vault` version bump into a crew change. Before
shipping it: it has no regression test, and `CLAUDE.md` requires one for a
hook that can block. `git stash pop` it, add the must-block/must-allow cases,
bump `obsidian-vault` to 0.3.1.

### 5. `core` consumers import the built artifact; `dist/` staleness is unchecked

`mcp-servers/packages/core/package.json:11-14` points `main`, `types` and
`exports` at `./dist/src/index.js`. Editing `src/*.ts` without `npm run build`
leaves `graph`, `intune`, `o365-admin` and `o365-user` on stale compiled JS,
with nothing in the edit path warning.

Every `src` file currently has a matching `.js`/`.d.ts`/`.map`, so it was built
at some commit — but no timestamp or hash comparison was done. **Inferred risk,
not confirmed staleness.** A CI check that rebuilds and diffs would settle it
permanently.

### 6. `check_skill_manifests` is unread

`scripts/check-marketplace.py:122`. Confirmed to exist and to sit between
`check_registration` and `check_plugin_manifests`. Which SKILL.md frontmatter
fields it cross-checks against the marketplace entry is unknown, so
`.crew/codemap/skills.md` records the four-place registration rule without
being able to say what this function adds to it.

### 7. The install-scripts matched-pair rule has no identified enforcer

`CLAUDE.md` requires `install-prerequisites.sh` and `.ps1` to keep identical
menu keys, order and default flags — otherwise `--select 3,7` means different
things on Windows and Linux. `scripts/check-marketplace.py` is said to enforce
it; the specific check was not located. Either find it and cite it, or write it.

## Deferred by design, not oversight

- **`plugin/crew` is unmapped** in `.crew/codemap/`. It is the file set the
  in-flight PR is rewriting; mapping it now yields `DERIVE` facts from
  `fe538879` and judgment from a moved-on working tree. Run
  `/crew:onboard --refresh plugin/crew` after that PR merges.
- **Unmapped smaller areas**, in node order: `mcp-servers/` root (65),
  `mcp-servers/graph` / `intune` / `o365-admin` / `o365-user` (54 each),
  `claude-obsidian-setup/` (48), `vault-automation/` (22).
- **`/crew:diagram`** — deferred until the codemap covers `plugin/crew`, so the
  diagram does not need redrawing immediately.
