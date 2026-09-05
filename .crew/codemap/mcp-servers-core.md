# mcp-servers-core

anchor: useful-claude-add-ons@875c9c6f
verified: 2026-09-05

## Does

`@badali404/mcp-ms-core` is the shared library the `graph`, `intune`,
`o365-admin` and `o365-user` MCP server packages all sit on: Azure/Graph auth
(device-code and an admin credential chain), a Graph HTTP client, a write-gate,
JWT decoding, a doctor/health check, and MCP tool-result helpers
(`mcp-servers/packages/core/src/index.ts:1-27`).

It is one package rather than four copies so the auth chain and the JSON-RPC
stdout safety rule live in one place. That rule matters: stdout **is** the MCP
protocol channel, so nothing in this package may `console.log`
(`src/auth.ts:3-6`).

This is the one area of the repo with real cross-file structure — 3 graph
communities across 15 files, against 148 communities across 156 files in
`skills/`. It is a system; most of this repo is a catalogue.

## Entry points

- `mcp-servers/packages/core/src/index.ts:1` — the public surface.
- `mcp-servers/packages/core/src/adminAuth.ts:48` — `AdminCredentialChain`, the admin auth path.
- `mcp-servers/packages/core/src/auth.ts:66` — `getUserCredential()`, the delegated-user path.

## Owns data

- Nothing persistent. Credentials are read from `process.env` at call time
  (`mcp-servers/packages/core/src/adminAuth.ts:114`, `:122`) and handed straight to
  `ClientSecretCredential`; nothing here stores or caches a secret to disk.

## Calls out to

- Microsoft Graph over HTTPS.
- Azure Identity (`ClientSecretCredential`, device-code, Azure CLI credential).
- Consumed by `packages/graph`, `packages/intune`, `packages/o365-admin`,
  `packages/o365-user`.

## Landmines

- **The credential chain caches its winner and never re-tries earlier links.**
  `AdminCredentialChain` stores whichever link first succeeds in
  `this.resolved` (`src/adminAuth.ts:48-109`) and keeps it for the process
  lifetime, so a later-fixed `secret` config is silently ignored once `cli` or
  `device` has won. Deliberate, per the comment at `:44-46` — but it means
  "I fixed the env var and it still uses the wrong identity" is expected
  behaviour, not a bug.
- **`scopesOverride` forces `.default` for `secret` and `cli`**
  (`src/adminAuth.ts:29-36`, `:127`, `:144`). Only `device` honours
  caller-supplied delegated scopes (`:159`). Code that asks for a narrow scope
  and gets `.default` did not fail — it was never asked for.
- **`getUserCredential()` is deliberately narrower than the admin chain**
  (`src/auth.ts:66-70`): device-code only, never falling back to Azure CLI, to
  avoid widening past the server's `/me`-only `USER_SCOPES` (`:54-60`).
  "Making it consistent" with the admin chain would be a privilege escalation.
- **Consumers import the BUILT artifact, not source.** `package.json:11-14`
  points `main`/`types`/`exports` at `./dist/src/index.js`. Editing `src/*.ts`
  without `npm run build` leaves every consumer on stale compiled JS, and
  nothing in the edit path warns.
- **Never `console.log` from this package** (`src/auth.ts:3-6`) — stdout is the
  JSON-RPC channel and a stray write corrupts the protocol.

## Unverified

- Whether `dist/` is currently in step with `src/`. Every `src` file has a
  matching `.js`/`.d.ts`/`.map`, so it was built at some commit, but no
  timestamp or hash comparison was done. Inferred risk, not confirmed staleness.
- Whether the four consumer packages resolve this via a workspace symlink or a
  published npm version — their version specifiers and the root workspace
  config were not inspected.
