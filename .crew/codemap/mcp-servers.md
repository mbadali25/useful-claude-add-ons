# mcp-servers
anchor: useful-claude-add-ons@1f97e51c
verified: 2026-09-06

## Does
An npm workspace monorepo shipping four thin stdio MCP servers for Microsoft Graph, Intune and
O365 - `packages/graph`, `intune`, `o365-admin`, `o365-user` - all built on one shared
`packages/core` that owns HTTP, auth, the write gate and the doctor. It is the odd one out in this
repo: everything else here is a Claude Code plugin or skill, and nothing in the marketplace
registers it. (DERIVED: `grep -c mcp-servers .claude-plugin/marketplace.json` returns 0.)

## Entry points
- `mcp-servers/packages/graph/src/cli.ts:1` - the process entry point: dispatches either a `doctor`
  subcommand or `createServer()` over a stdio transport. Representative of **three** of the four,
  not all four - see the `o365-user` landmine below.
- `mcp-servers/package.json:9-11` - root workspace scripts. `build` (`:9`) builds core first, then
  every workspace; `test` (`:10`) is `npm run build && npm run test:scripts && npm run test
  --workspaces`; `test:scripts` (`:11`) runs the stale-build guard's own suite.
- `mcp-servers/packages/core/src/writeGate.ts:19` - `assertWriteAllowed`, the gate every write tool
  passes through. Requires BOTH `MCP_MS_ALLOW_WRITES=1` in the environment (`:20`) and
  `confirm: true` on the individual call (`:26`).
- `mcp-servers/scripts/check-dist-fresh.mjs:126` - `main()`, the stale-build guard, wired as every
  package's `pretest` (`mcp-servers/packages/core/package.json:26`, and `:25` in each of the four
  server manifests).

## Owns data
- Nothing persistent of its own. State is the caller's Microsoft tenant, reached over HTTP.
- Compiled output under `mcp-servers/packages/core/dist/`, which is what is actually loaded -
  `mcp-servers/packages/core/package.json:11` points `main`/`types`/`exports` at `./dist/src/index.js`.
- `dist/` is **untracked** (DERIVED: `git ls-files mcp-servers/packages/core/dist` returns nothing).
  So there is no committed build to diff a rebuild against, and CI cannot ship a stale one.

## Calls out to
- Microsoft Graph and the Intune / O365 admin endpoints, via the shared client in
  `mcp-servers/packages/core/src/graphClient.ts`.
- Azure identity providers through **two** separate paths: the admin credential chain at
  `mcp-servers/packages/core/src/adminAuth.ts:48` (`graph`, `intune`, `o365-admin`), and the
  device-code-only user credential at `mcp-servers/packages/core/src/auth.ts:66` (`o365-user`).

## Landmines
- **The credential chain caches its winner for the process lifetime.** `AdminCredentialChain`
  (`mcp-servers/packages/core/src/adminAuth.ts:48-109`) stores whichever link first succeeds in
  `this.resolved` and never retries an earlier, higher-priority link. Deliberate - the comment at
  `:44-46` says so - but fixing `MS_ADMIN_CLIENT_SECRET` after `cli` or `device` has won changes
  nothing until restart, and nothing tells you that. Re-verified unchanged 2026-09-06 at
  `1f97e51c`; still open as `TODO.md:51` (item 2).
- **`scopesOverride` silently broadens a narrow scope request.**
  `mcp-servers/packages/core/src/adminAuth.ts:29-36` (the field and its doc comment), `:127`
  (`secret`) and `:144` (`cli`) force `.default` regardless of what the caller asked for. Only
  `device` (`mcp-servers/packages/core/src/adminAuth.ts:149-158` - no `scopesOverride` key, and the
  comment at `:155-158` says why) honours caller-supplied delegated scopes. Code that requests a
  narrow scope and receives `.default` did not fail - it was never asked. Re-verified unchanged
  2026-09-06 at `1f97e51c`; still open as `TODO.md:62` (item 3).
- **`dist/` is what runs, `src/` is what you edit.** Editing a `.ts` file and then *starting a
  server* leaves the stale compiled JS in place and the change does not take effect. Nothing guards
  that path - the guard below is a `pretest`, so it fires on `npm test` and on nothing else.
- **The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).** Do not build a
  fix for it. `mcp-servers/scripts/check-dist-fresh.mjs` runs as every package's `pretest` and
  refuses a run whose newest `.js` under `dist/` is not strictly newer than the newest `.ts` under
  `src/` and `test/` (`:95-101`). Three design points that are easy to get backwards:
  - A consumer is checked by checking **core itself, recursively** (`:117-122`), never by comparing
    the consumer's `dist` to `core/src` - the latter passes the moment the consumer is rebuilt while
    `core/dist` is still stale.
  - **Equal mtimes are stale, not fresh** (`:96-97`, reasoning at `:82-94`). The commit message for
    `4e2bfb78` states the opposite ("Equal timestamps count as fresh"); the shipped code and
    `TODO.md:143-150` are the later, correct account. Trust the code.
  - An unreadable directory throws rather than returning mtime `0` (`:44-51`), because `0` compares
    older than everything and would read as fresh.
  14 tests at `mcp-servers/scripts/_test/check-dist-fresh.test.mjs` (DERIVED: 14 `test(` at column
  0), run by the root `npm run test:scripts`. (The commit message says ten; the file has 14.)
- **`o365-user` does not use the admin credential chain at all.** Its `cli.ts` calls
  `getUserCredential` (`mcp-servers/packages/o365-user/src/cli.ts:3`,`:11`), which is device-code
  only with no chain and no CLI fallback (`mcp-servers/packages/core/src/auth.ts:66-70`, rationale
  at `:55-61`). The two `adminAuth` landmines above therefore do **not** apply to it. The other
  three all call `buildAdminCredential` (`mcp-servers/packages/core/src/adminAuth.ts:176`).
- **Each server pins an exact core version, not a range.** All four carry
  `"@badali404/mcp-ms-core": "0.2.0"` at line `:29` of their own `package.json`, and core is at
  `0.2.0` (`mcp-servers/packages/core/package.json:3`). A core-only bump reaches nobody until all
  four servers republish.

## Unverified
- All four `cli.ts` files were read at this anchor, but only their first ~25 lines. Each package's
  `src/index.ts` (where `createServer` and the tool list live) and each
  `mcp-servers/packages/*/test/tools.test.ts` were not opened.
- The bodies of `mcp-servers/packages/core/src/jwt.ts`, `doctor.ts`, `toolResult.ts` and
  `graphClient.ts` were not read; their roles come from the README and from import sites.
- `mcp-servers/packages/core/test/adminAuth.test.ts` exists and is offline/mocked, which answers "is
  adminAuth covered" - but it was not run here, so it is not known to pass at this anchor.
- **This worktree's `dist/` is stale right now** (measured 2026-09-06 by importing `checkPackage`
  from `mcp-servers/scripts/check-dist-fresh.mjs` and calling it per package - no build run): all
  five report `compiled output is not newer than core/test`. That is a fact about one untracked
  working tree on one machine, not about the repo, and it means `npm test -w packages/<anything>`
  here would exit 1 at `pretest` until `npm run build` is run from `mcp-servers/`. (JUDGEMENT: this
  is the guard working, not a defect.)

## Re-anchor provenance
Re-anchored `a02331ee` -> `1f97e51c` on 2026-09-06. The per-path check flagged
`mcp-servers/package.json` and `mcp-servers/packages/core/package.json` as moved; the cause was
`4e2bfb78`, which added the stale-build guard.

Re-read in full or in the cited region: `mcp-servers/package.json`,
`mcp-servers/packages/core/package.json`, all four server `package.json` files,
`mcp-servers/scripts/check-dist-fresh.mjs` (whole file),
`mcp-servers/scripts/_test/check-dist-fresh.test.mjs` (test names only),
`mcp-servers/packages/core/src/adminAuth.ts:20-176`, `mcp-servers/packages/core/src/auth.ts:55-70`,
`mcp-servers/packages/core/src/writeGate.ts:1-32`, all four `src/cli.ts` heads, and
`TODO.md:105-158` plus its heading list.

Corrected here: the `dist/` staleness gap was described as open and is closed in the test path
(`TODO.md:113`, item 5, CLOSED 2026-09-06); `graph/src/cli.ts` was called representative of all four
when `o365-user` takes a different credential path; the `device` link was cited at `:159` (the
`build:` line) rather than at the function and comment that carry the claim.

Not re-verified: nothing was built, installed or executed beyond importing `checkPackage` as a
library to read mtimes. No test suite was run.
