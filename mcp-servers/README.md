# Microsoft MCP servers

Four local, stdio-based MCP servers for Microsoft 365 and Intune, built on one shared
auth/HTTP workspace package. They are **not** Claude Code marketplace plugins -- there is
nothing to install via `claude plugin install`. They are npm packages you build once
(`npm install && npm run build`) and register with `claude mcp add`, either from this
local clone or, once published, via `npx`.

| Package | What it does | Auth |
|---|---|---|
| `@badali404/mcp-msgraph` | Tenant directory: users, groups, membership | app-only (tenant-wide) |
| `@badali404/mcp-intune` | Intune device management, compliance, config profiles | app-only (tenant-wide) |
| `@badali404/mcp-o365-user` | The signed-in user's own mail, calendar, files | delegated (device code) |
| `@badali404/mcp-o365-admin` | Tenant mailboxes, licenses, password reset, user deletion | app-only (tenant-wide) |

All four sit on `@badali404/mcp-ms-core`, an npm workspace package meant to be published
to the registry alongside them (so once that's done, `npx`-installing a server resolves
its dependency the normal way -- see "Publishing" below for what that actually requires
and why it hasn't happened yet): one `GraphClient` HTTP wrapper, one `getUserCredential`
/ `getAdminCredential` pair, one write-gate, one `doctor` implementation. No server
reimplements auth or HTTP. Source: `mcp-servers/packages/`.

Each server pins an **exact** version of core (`"@badali404/mcp-ms-core": "0.1.0"`, not a
range) rather than `^0.1.0` or `workspace:*`. That is deliberate -- it means a core-only
change can never silently ship to a server that hasn't been tested against it -- but it
also means **a core-only version bump has no effect on npm until all four servers are
re-published with their pin updated to match**. See
[`PUBLISHING.md`](PUBLISHING.md#5-releasing-an-update) for the exact steps.

## Azure: use the official server, not a new one

Azure Resource Manager is already covered by Microsoft's own
[`@azure/mcp`](https://www.npmjs.com/package/@azure/mcp), which is registered on this
machine and runnable with:

```bash
npx -y @azure/mcp@latest server start
```

It exposes dozens of service-scoped tool groups (`arm` generic CRUD, plus dedicated tools
for AKS, App Service, Storage, Key Vault, SQL, Cosmos DB, Monitor, Policy, RBAC roles,
Resource Health, Quota, pricing, the Marketplace, `azd`, and an `az`/`azqr` CLI
generator/installer, among many more) -- comprehensively covering ARM. Writing a second,
thinner ARM server here would duplicate that surface for no benefit, so **this repo does
not ship an `azure` package**. If a genuine gap shows up later (something ARM-shaped that
`@azure/mcp` doesn't cover), add `packages/azure` then, scoped to exactly that gap, on
top of the same `@badali404/mcp-ms-core` package the other four servers use.

That leaves four thin server packages -- Intune, Graph, and Office 365 (user and admin)
-- which is what `packages/` actually contains.

## User-scope vs admin-scope: why they're separate packages

- **`mcp-o365-user`** authenticates the person running Claude Code via `DeviceCodeCredential`
  (`@azure/identity`) -- a device-code flow where you sign in once as yourself in a
  browser. Every tool call runs as `/me`: your own mailbox, your own calendar, your own
  OneDrive. It cannot see anyone else's data, and it cannot see tenant-wide data, because
  the token it holds is delegated to your account and whatever your admin has consented to.
- **`mcp-intune`**, **`mcp-msgraph`**, and **`mcp-o365-admin`** authenticate as an Azure AD
  app registration via `ClientSecretCredential`, using **application** (not delegated)
  Graph permissions granted tenant-wide admin consent. These see and can change data for
  the whole tenant.

They use **different environment variables on purpose** (`MS_USER_*` vs `MS_ADMIN_*`), so
a Claude Code session wired up for "read my calendar" literally has no credential that can
reach tenant data, and vice versa. Never set both in the same MCP client config unless you
mean to grant a session both kinds of access.

## Environment variables

| Variable | Used by | Required | Notes |
|---|---|---|---|
| `MS_USER_CLIENT_ID` | `mcp-o365-user` | yes | App registration (public client, "Allow public client flows" / device code enabled) |
| `MS_USER_TENANT_ID` | `mcp-o365-user` | no | Defaults to `organizations`. Set to your tenant ID/domain to restrict sign-in to one tenant |
| `MS_ADMIN_TENANT_ID` | `mcp-intune`, `mcp-msgraph`, `mcp-o365-admin` | yes | Directory (tenant) ID |
| `MS_ADMIN_CLIENT_ID` | `mcp-intune`, `mcp-msgraph`, `mcp-o365-admin` | yes | App registration (confidential client) with admin-consented application permissions |
| `MS_ADMIN_CLIENT_SECRET` | `mcp-intune`, `mcp-msgraph`, `mcp-o365-admin` | yes | Client secret for the above app registration |
| `MCP_MS_ALLOW_WRITES` | all four | no | Set to exactly `1` to allow write/destructive tools. Unset or any other value keeps every server read-only |

No server reads these from `~/.claude.json` or any other config file, and none of them
ever print secret values -- set them in the environment that launches the process (your
shell profile, a `.env` loaded by your process manager, or your MCP client's `env` block).

### Minimum Graph application permissions to grant `MS_ADMIN_*`

Grant only what the tools you intend to use need, then admin-consent in Entra ID:

- `mcp-msgraph`: `User.Read.All`, `Group.Read.All` (read tools); `User.ReadWrite.All`,
  `GroupMember.ReadWrite.All` (write tools)
- `mcp-intune`: `DeviceManagementManagedDevices.Read.All`,
  `DeviceManagementConfiguration.Read.All` (read tools);
  `DeviceManagementManagedDevices.PrivilegedOperations.All`,
  `DeviceManagementConfiguration.ReadWrite.All` (write tools)
- `mcp-o365-admin`: `User.Read.All`, `MailboxSettings.Read` (read tools);
  `User.ReadWrite.All` (write tools)

### Delegated permissions to consent for `MS_USER_*`

`User.Read`, `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `Files.Read` -- see
`packages/o365-user/src/index.ts`'s `USER_SCOPES` for the exact list requested at sign-in.

## Write and destructive tools are gated -- twice

Every write/destructive tool checks **both**:

1. The environment flag `MCP_MS_ALLOW_WRITES=1`, set once by whoever launches the server
   (an operator decision, made outside any one conversation).
2. A per-call `confirm: true` parameter (a decision made for that specific call).

Neither alone is enough -- see `packages/core/src/writeGate.ts`. All other tools are
read-only and need neither.

| Server | Tool | What it does |
|---|---|---|
| `mcp-msgraph` | `update_user_profile` | Change displayName/jobTitle/department/officeLocation |
| `mcp-msgraph` | `disable_user_account` | Disable a user's sign-in |
| `mcp-msgraph` | `add_group_member` / `remove_group_member` | Change group membership |
| `mcp-intune` | `sync_device` | Trigger an immediate device check-in |
| `mcp-intune` | `retire_device` | **Destructive** -- removes company data and management |
| `mcp-intune` | `wipe_device` | **Destructive** -- factory-resets the device |
| `mcp-intune` | `update_compliance_policy` | Policy change -- JSON-merge-patch a compliance policy |
| `mcp-o365-user` | `send_mail` | Sends mail as the signed-in user |
| `mcp-o365-user` | `create_calendar_event` | Creates an event and sends invites |
| `mcp-o365-user` | `delete_mail_message` | **Destructive** -- deletes one message |
| `mcp-o365-admin` | `reset_user_password` | Force-resets a user's password |
| `mcp-o365-admin` | `assign_license` | Assigns a license SKU to a user |
| `mcp-o365-admin` | `delete_user` | **Destructive** -- deletes a user (recoverable ~30 days via the AAD recycle bin) |

## Doctor: prove auth actually works

Every server ships a `doctor` subcommand. It acquires a real token, decodes its claims
(never verifies -- verification is Azure AD's job), and prints what was **actually
granted**: tenant, identity, delegated scopes or app roles, token expiry, and whether
`MCP_MS_ALLOW_WRITES` is set. A process that starts cleanly proves nothing about whether
auth works -- run `doctor` before trusting a server is wired up correctly.

```bash
node packages/intune/dist/src/cli.js doctor
node packages/o365-user/dist/src/cli.js doctor   # prompts a device-code sign-in
```

If you registered via Option B or `npx` below, the global/published command name works
the same way: `mcp-intune doctor`, `npx -y @badali404/mcp-intune@latest doctor`.

## Install and register

Nothing here is on the npm registry yet (see "Publishing" below), so today there are
two ways to run these servers from a local clone -- pick one per server, they are not
mutually exclusive. Once published, a third, simpler way (`npx`) replaces both.

```bash
cd mcp-servers
npm install
npm run build
```

That builds `packages/core` first, then all four servers into `packages/<name>/dist/`.
Both options below assume this has already been run.

### Option A: direct path (no global install)

Register the compiled entry point directly. Nothing touches your global npm
install; the registered command is this exact file.

**Linux/macOS:**

```bash
claude mcp add mcp-msgraph -- node /path/to/mcp-servers/packages/graph/dist/src/cli.js
claude mcp add mcp-intune -- node /path/to/mcp-servers/packages/intune/dist/src/cli.js
claude mcp add mcp-o365-user -- node /path/to/mcp-servers/packages/o365-user/dist/src/cli.js
claude mcp add mcp-o365-admin -- node /path/to/mcp-servers/packages/o365-admin/dist/src/cli.js
```

**Windows (PowerShell):**

```powershell
claude mcp add mcp-msgraph -- node C:\path\to\mcp-servers\packages\graph\dist\src\cli.js
claude mcp add mcp-intune -- node C:\path\to\mcp-servers\packages\intune\dist\src\cli.js
claude mcp add mcp-o365-user -- node C:\path\to\mcp-servers\packages\o365-user\dist\src\cli.js
claude mcp add mcp-o365-admin -- node C:\path\to\mcp-servers\packages\o365-admin\dist\src\cli.js
```

### Option B: `npm install -g` from this clone (what the installer script uses)

Installs a global command (`mcp-msgraph`, `mcp-intune`, `mcp-o365-user`,
`mcp-o365-admin`) so the registration line matches what it will look like after
publishing -- only the command changes, not the shape of the `claude mcp add` call.
Run once per server you want, from inside `mcp-servers/`:

```bash
(cd packages/graph && npm install -g .)
(cd packages/intune && npm install -g .)
(cd packages/o365-user && npm install -g .)
(cd packages/o365-admin && npm install -g .)
```

Same commands on Windows (PowerShell resolves `.` the same way; no path changes
needed). Then, same on both platforms:

```bash
claude mcp add mcp-msgraph -- mcp-msgraph
claude mcp add mcp-intune -- mcp-intune
claude mcp add mcp-o365-user -- mcp-o365-user
claude mcp add mcp-o365-admin -- mcp-o365-admin
```

This works pre-publish because these are npm **workspace** members: `npm install -g .`
on a workspace member symlinks it globally rather than reinstalling it fresh, so its
`require("@badali404/mcp-ms-core")` still resolves through `mcp-servers/node_modules`
(hoisted there by the `npm install` above) instead of hitting the registry, where it
would 404 today. The trade-off: the global command only keeps working as long as this
clone stays where it is -- moving or deleting `mcp-servers/` breaks it, the same
caveat as `npm link`. This is exactly the mechanism menu item 21 of the install
scripts (`scripts/install-prerequisites.sh` / `.ps1`) uses.

Both options register the server bare -- no `--env`, so no secret gets written into
`~/.claude.json`. The credentials still have to reach the process at runtime, which
means they must be exported wherever `claude` itself gets launched (shell profile,
service manager, etc.), not just in the shell you happened to run `claude mcp add`
from.

### Via npx (the standard path -- published on npm under `@badali404`)

```bash
claude mcp add mcp-msgraph -- npx -y @badali404/mcp-msgraph@latest
claude mcp add mcp-intune -- npx -y @badali404/mcp-intune@latest
claude mcp add mcp-o365-user -- npx -y @badali404/mcp-o365-user@latest
claude mcp add mcp-o365-admin -- npx -y @badali404/mcp-o365-admin@latest
```

Same command on Windows and Linux -- `npx` resolves the right platform build itself,
and downloads/caches the package on the server's first launch. This is the standard
install; the two local options above remain only for developing against a clone.
Releasing a new version: "Publishing" below, full step-by-step in
[`PUBLISHING.md`](PUBLISHING.md).

## Publishing

Summary below; [`PUBLISHING.md`](PUBLISHING.md) is the full walkthrough -- npm account
and `@badali404` scope setup, generating and setting the CI token, the tag-and-push
release flow, the manual fallback, bumping versions for an update, verifying the first
publish actually worked, and troubleshooting (`402`, `403`, `ENEEDAUTH`, a stale `npx`
cache).

[`.github/workflows/publish-mcp-servers.yml`](../.github/workflows/publish-mcp-servers.yml)
publishes all five packages -- `@badali404/mcp-ms-core` first, then the four servers,
since each server's `package.json` pins `"@badali404/mcp-ms-core": "0.1.0"` and npm
needs that version resolvable on the registry before it will install a server that
depends on it. It fires on a pushed tag matching `mcp-servers-v*` (e.g.
`mcp-servers-v0.1.0`) and runs `npm publish --provenance --access public` for each
package, authenticated with `NPM_TOKEN` from repository secrets.

Two things have to be true before that tag push does anything useful, and neither is
true yet in this repo:

1. **The `@badali404` scope has to exist on npmjs.com** and be owned by an account that
   can grant the token below publish rights to it. `--access public` only controls
   whether the *published package* is public within that scope -- it does not create
   the scope itself.
2. **An `NPM_TOKEN` repository secret** (an npm "Automation" or "Granular Access"
   token with publish rights to that scope) has to be set in this repo's GitHub
   Actions secrets.

**Until both exist and a `mcp-servers-v*` tag has actually been pushed and published
successfully, `npx -y @badali404/<pkg>@latest` cannot resolve anything** -- npm will
report a 404 for an unscoped-nonexistent or unpublished package. Use Option A or
Option B above until then.

### Verify a registration

1. Run `doctor` for the server directly (see above) -- confirms auth and prints granted
   scopes/roles before you ever go through Claude.
2. Start Claude Code and check `/mcp` (or your client's equivalent) lists the server as
   connected.
3. Call one read-only tool (e.g. `list_users` on `mcp-msgraph`, `get_my_profile` on
   `mcp-o365-user`) and confirm it returns real data.
4. Only after that, if you need writes, set `MCP_MS_ALLOW_WRITES=1` in the server's
   environment and re-verify a write tool with `confirm: true` against a throwaway test
   object -- never against production data on the first try.

## Tests

Offline, no live tenant needed -- every test mocks `global.fetch` and passes a fake
`TokenCredential`, so `npm test` never makes a real network call:

```bash
cd mcp-servers
npm test
```

This builds every package (tests run against compiled `dist/test/*.test.js`, using
Node's built-in test runner -- no extra test framework dependency) and runs all suites.
Every package's `test` script passes an explicit glob (`node --test "dist/test/**/*.test.js"`)
rather than a bare directory path -- CI and local testing here have only been verified
on Node 26; `engines` says `>=18` as a floor but that is unverified below 26.
`packages/core/test/` covers the shared `GraphClient` (request building, pagination,
error surfacing), the write gate (env flag AND confirm, every combination), and JWT
claim decoding. Each server's `test/tools.test.ts` covers: at least one read-only tool
returning real (mocked) data, every write/destructive tool rejecting when
`MCP_MS_ALLOW_WRITES` is unset, rejecting when `confirm` is missing even with the flag
set, and succeeding -- with the right HTTP method/URL/body -- when both gates are open.

## What is NOT proven by these tests

Everything above is exercised against a mocked `fetch`, never a real Microsoft Graph
endpoint or a real Azure AD tenant. Unproven until run against a live tenant:

- That the granted Graph application/delegated permissions listed above are actually
  sufficient (or correctly named) for every tool -- Graph permission names and required
  scopes do shift between docs and reality.
- Device-code sign-in UX end to end (the `userPromptCallback` message, token caching
  across restarts -- `DeviceCodeCredential` here is unauthenticated/uncached; `doctor`
  or the first real tool call re-prompts each process start unless you wire up
  `@azure/identity`'s token cache persistence yourself).
- Real Graph pagination beyond the 2-10 page caps used here on large tenants.
- Throttling/retry behavior under Graph's `429 Retry-After` -- not implemented; a
  throttled call currently surfaces as a plain `GraphApiError`.
