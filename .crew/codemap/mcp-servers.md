# mcp-servers
anchor: useful-claude-add-ons@a02331ee
verified: 2026-09-06

## Does
An npm workspace monorepo shipping four thin stdio MCP servers for Microsoft Graph, Intune and
O365 - `packages/graph`, `intune`, `o365-admin`, `o365-user` - all built on one shared
`packages/core` that owns HTTP, auth, the write gate and the doctor. It is the odd one out in this
repo: everything else here is a Claude Code plugin or skill, and nothing in the marketplace
registers it.

## Entry points
- `mcp-servers/packages/graph/src/cli.ts:1` - the process entry point, representative of all four:
  dispatches either a `doctor` subcommand or `createServer()` over a stdio transport.
- `mcp-servers/package.json:9` - root workspace `build` / `test` scripts. Core builds first, then
  every workspace.
- `mcp-servers/packages/core/src/writeGate.ts:19` - `assertWriteAllowed`, the gate every write tool
  passes through. Requires BOTH `MCP_MS_ALLOW_WRITES=1` in the environment and `confirm: true` on
  the individual call.

## Owns data
- Nothing persistent of its own. State is the caller's Microsoft tenant, reached over HTTP.
- Compiled output under `mcp-servers/packages/core/dist/`, which is what is actually loaded -
  `mcp-servers/packages/core/package.json:11` points `main`/`types`/`exports` at `./dist/src/index.js`.

## Calls out to
- Microsoft Graph and the Intune / O365 admin endpoints, via the shared client in
  `mcp-servers/packages/core/src/graphClient.ts`.
- Azure identity providers through the credential chain at
  `mcp-servers/packages/core/src/adminAuth.ts:48`.

## Landmines
- **The credential chain caches its winner for the process lifetime.** `AdminCredentialChain`
  (`mcp-servers/packages/core/src/adminAuth.ts:48-109`) stores whichever link first succeeds in
  `this.resolved` and never retries an earlier, higher-priority link. Deliberate - the comment at
  `:44-46` says so - but fixing `MS_ADMIN_CLIENT_SECRET` after `cli` or `device` has won changes
  nothing until restart, and nothing tells you that. Re-verified unchanged 2026-09-06; recorded as
  TODO #2.
- **`scopesOverride` silently broadens a narrow scope request.**
  `mcp-servers/packages/core/src/adminAuth.ts:29-36`, `:127` and `:144` force `.default` for the
  `secret` and `cli` links regardless of what the caller asked for. Only `device` (`:159`) honours
  caller-supplied delegated scopes. Code that requests a narrow scope and receives `.default` did
  not fail - it was never asked. Re-verified unchanged 2026-09-06; recorded as TODO #3.
- **`dist/` is what runs, `src/` is what you edit.** Editing a `.ts` file without `npm run build`
  leaves the stale compiled JS in place and the change simply does not take effect.
- **Each server pins an exact core version, not a range.** A core-only bump reaches nobody until
  all four servers republish.

## Unverified
- Only `packages/graph`'s `cli.ts` was read; `intune`, `o365-admin` and `o365-user` entry points
  and their `mcp-servers/packages/*/test/tools.test.ts` files were not opened.
- The bodies of `mcp-servers/packages/core/src/auth.ts`, `jwt.ts`, `doctor.ts` and
  `graphClient.ts` were not
  read; their roles come from the README and from `writeGate.ts`'s imports.
- `mcp-servers/packages/core/test/adminAuth.test.ts` exists and is offline/mocked, which answers "is adminAuth
  covered" - but it was not run here, so it is not known to pass at this anchor.
- Whether `dist/` currently matches `src/` was not checked.
