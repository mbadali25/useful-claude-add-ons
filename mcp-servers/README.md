# mcp-servers/

Four local (stdio) MCP servers giving Claude Code access to Intune, Entra ID
(Azure AD) directory administration, and Office 365 - both as the
signed-in user and as a tenant admin - over Microsoft Graph. Python 3.11+,
run with `uv`/`uvx`, no network dependency beyond `graph.microsoft.com` and
`login.microsoftonline.com` at runtime.

They share one auth + HTTP core ([`core/`](core/)) and expose four thin,
differently-scoped toolsets on top of it - not four unrelated servers, since
Intune, directory admin, and O365 all sit on the same Graph API surface.

| Server | Package | Scope | Auth | Reach |
|---|---|---|---|---|
| Intune | [`intune/`](intune/) | admin | app-only (client credentials) | tenant-wide device/policy/app management |
| Entra ID admin | [`graph-admin/`](graph-admin/) | admin | app-only (client credentials) | tenant-wide directory: users, groups, app registrations, roles, conditional access |
| O365 (you) | [`o365-user/`](o365-user/) | **user** | delegated (device-code sign-in) | only the signed-in user's own mail/calendar/OneDrive |
| O365 (admin) | [`o365-admin/`](o365-admin/) | admin | app-only (client credentials) | tenant-wide: any mailbox, SharePoint, Teams, licensing |

## Why this split, and why it's structural

`mcp-o365-user` and `mcp-o365-admin` are **separate server processes with
separate env-var prefixes**, not one server with a mode switch. That is
deliberate:

- `mcp-o365-user` is built on `mcp_ms_core.DeviceCodeAuth`, which never reads
  a client secret and only ever acquires a token scoped to whichever human
  signed in through the device-code flow. There is no parameter, tool, or
  code path in this server that can reach another user's mailbox or
  tenant-wide data - Graph enforces that server-side based on the token's
  delegated scopes, and the token this server can even ask for is delegated
  by construction.
- `mcp-o365-admin`, `mcp-intune`, and `mcp-graph-admin` are built on
  `mcp_ms_core.ClientCredentialAuth`, which needs an app registration with
  **application permissions** and admin consent - inherently tenant-wide.

So a Claude Code session that only has `MS_O365_USER_*` configured cannot
reach tenant-wide anything, no matter what it's asked to do: the code that
would do it doesn't exist in that process, and the credentials that would
authorize it were never read. Give a session admin reach only by registering
one of the three admin servers for it, deliberately.

## Auth model

### App-only (admin-scope): Intune, Entra ID admin, O365 admin

OAuth2 client-credentials grant via [MSAL](https://github.com/AzureAD/microsoft-authentication-library-for-python).
Needs an **app registration** in Entra ID with:

- **Application permissions** (not delegated) for whatever the server's
  tools touch - see each package's docstring-level comments for the exact
  Graph permission a failing call is usually missing (`mcp-*-doctor` also
  prints a hint).
- **Admin consent granted** on those permissions.
- Either a **client secret** or a **certificate** - prefer a certificate for
  anything long-lived; it doesn't expire on the app registration's own
  clock and is easier to rotate without touching the secret list.

Each of the three app-only servers reads its own env-var prefix
(`MS_INTUNE_*`, `MS_GRAPH_ADMIN_*`, `MS_O365_ADMIN_*`) - use one app
registration per server, scoped to only the permissions that server's tools
need, rather than one god-app shared by all three. That keeps a compromised
or over-broadly-consented credential from mattering more than it has to.

### Delegated (user-scope): O365 user

OAuth2 device-code flow. Needs an app registration that is a **public
client** (no client secret) with **delegated** permissions matching
`mcp_o365_user.client.SCOPES` (`User.Read`, `Mail.Read`, `Mail.Send`,
`Calendars.ReadWrite`, `Files.Read.All`). First run prints a
`https://microsoft.com/devicelogin` code to **stderr** (never stdout - stdout
carries the MCP JSON-RPC stream) and waits for you to sign in in a browser.
The resulting refresh token is cached to disk (not the password) so later
runs don't prompt again - see `MS_O365_USER_TOKEN_CACHE_PATH` below.

## Environment variables

Never set any of these inside `~/.claude.json` or a `claude mcp add --env`
flag - that writes the value in plaintext into Claude Code's own config file,
which is exactly the pattern this workspace avoids. Set them in the shell
profile / OS environment that launches Claude Code instead; a stdio MCP
server inherits its parent process's environment, so nothing further is
needed once they're exported there.

| Server | Variable | Required | Notes |
|---|---|---|---|
| Intune | `MS_INTUNE_TENANT_ID` | yes | Entra ID tenant id or verified domain |
| | `MS_INTUNE_CLIENT_ID` | yes | app registration (application) id |
| | `MS_INTUNE_CLIENT_SECRET` | yes, unless cert | client secret |
| | `MS_INTUNE_CLIENT_CERT_PATH` | no | PEM private key path; used instead of the secret |
| | `MS_INTUNE_CLIENT_CERT_THUMBPRINT` | with cert path | cert thumbprint |
| | `MS_INTUNE_ALLOW_WRITES` | no | `1`/`true`/`yes` to allow gated write tools |
| Entra ID admin | `MS_GRAPH_ADMIN_TENANT_ID` | yes | |
| | `MS_GRAPH_ADMIN_CLIENT_ID` | yes | |
| | `MS_GRAPH_ADMIN_CLIENT_SECRET` | yes, unless cert | |
| | `MS_GRAPH_ADMIN_CLIENT_CERT_PATH` / `_THUMBPRINT` | no | |
| | `MS_GRAPH_ADMIN_ALLOW_WRITES` | no | |
| O365 user | `MS_O365_USER_TENANT_ID` | yes | |
| | `MS_O365_USER_CLIENT_ID` | yes | public-client app registration id |
| | `MS_O365_USER_TOKEN_CACHE_PATH` | no | default: `%LOCALAPPDATA%\mcp-o365-user\token-cache.json` (Windows) / `~/.cache/mcp-o365-user/token-cache.json` (Linux) |
| | `MS_O365_USER_ALLOW_WRITES` | no | |
| O365 admin | `MS_O365_ADMIN_TENANT_ID` | yes | |
| | `MS_O365_ADMIN_CLIENT_ID` | yes | |
| | `MS_O365_ADMIN_CLIENT_SECRET` | yes, unless cert | |
| | `MS_O365_ADMIN_CLIENT_CERT_PATH` / `_THUMBPRINT` | no | |
| | `MS_O365_ADMIN_ALLOW_WRITES` | no | |

No variable here ever holds a value this repo ships - every one is read at
call time from the process environment, and none is logged or written back
to disk except the O365-user token cache noted above (refresh tokens, never
the password, `chmod 600` on POSIX).

## Read-only by default

Every tool that mutates or deletes something is gated behind **both**:

1. the server's `*_ALLOW_WRITES` env var set to `1`/`true`/`yes`, **and**
2. a `confirm=true` argument on the call itself.

Missing either returns a preview (`wouldExecute: false`, the target(s), and
what's missing) instead of acting - see `mcp_ms_core.write_gate`. The gated
tools:

| Server | Gated tools |
|---|---|
| Intune | `intune_sync_device`, `intune_reboot_device`, `intune_retire_device`, `intune_wipe_device` |
| Entra ID admin | `graph_admin_add_group_member`, `graph_admin_remove_group_member`, `graph_admin_disable_user`, `graph_admin_delete_user` |
| O365 user | `o365_user_send_mail`, `o365_user_create_calendar_event`, `o365_user_delete_message` |
| O365 admin | `o365_admin_assign_license`, `o365_admin_remove_license`, `o365_admin_remove_team_member`, `o365_admin_delete_drive_item` |

`retire`/`wipe` (Intune) and `delete_user` are irreversible; the rest range
from "reversible but immediately disruptive" (`disable_user`) to "moves to a
recoverable state" (`delete_message`) - treat the env flag as a per-server
switch you leave off until a session genuinely needs to write, not a
one-time setup step.

## Azure: why there's no `mcp-azure` server here

The official [`@azure/mcp`](https://github.com/Azure/azure-mcp) server is
already registered on this machine (menu item 10 in
[`scripts/install-prerequisites.sh`](../scripts/install-prerequisites.sh) /
`.ps1`, `npx -y @azure/mcp@latest server start`) and its tool surface -
`arm`, `compute`, `storage`, `aks`, `keyvault`, `sql`, `cosmos`, `monitor`,
`role` (Azure RBAC), `policy`, and several dozen more - is a thorough wrapper
over the **ARM control plane** (`management.azure.com`): the resources you'd
manage in the Azure Portal's resource blade.

None of that overlaps what this workspace builds, because Intune, Entra ID
directory administration, and Office 365 are not ARM resources - they're
served entirely from **`graph.microsoft.com`**, a different API surface with
different auth scopes (`https://graph.microsoft.com/.default` vs
`https://management.azure.com/.default`) that `@azure/mcp` does not touch at
all. Checked its tool list directly (`mcp__azure__*` in this environment):
there is no user/group/application/directoryRole/conditionalAccess tool
anywhere in it, and nothing under `deviceManagement` or `deviceAppManagement`.

So rather than duplicate `@azure/mcp`'s ARM coverage, `graph-admin/` fills
the actual gap - Entra ID (Azure AD) identity administration - and Azure
resource management stays `@azure/mcp`'s job. If you need both, they compose
fine: nothing here registers or touches `management.azure.com`.

## Registering the servers

Each server is a `uv`-managed project inside this workspace. `uv run
--directory <path>` resolves and syncs its own (shared) virtual environment
on first use and then runs the named console script - no separate install
step, no PyPI publish, works identically on Windows and Linux.

Pick the servers a given session actually needs - each is a separate
`claude mcp add`, and only the ones you register are reachable.

**Linux / macOS:**

```bash
claude mcp add ms-intune -- uv run --directory /path/to/useful-claude-add-ons/mcp-servers/intune mcp-intune
claude mcp add ms-graph-admin -- uv run --directory /path/to/useful-claude-add-ons/mcp-servers/graph-admin mcp-graph-admin
claude mcp add ms-o365-user -- uv run --directory /path/to/useful-claude-add-ons/mcp-servers/o365-user mcp-o365-user
claude mcp add ms-o365-admin -- uv run --directory /path/to/useful-claude-add-ons/mcp-servers/o365-admin mcp-o365-admin
```

**Windows (PowerShell):**

```powershell
claude mcp add ms-intune -- uv run --directory C:\path\to\useful-claude-add-ons\mcp-servers\intune mcp-intune
claude mcp add ms-graph-admin -- uv run --directory C:\path\to\useful-claude-add-ons\mcp-servers\graph-admin mcp-graph-admin
claude mcp add ms-o365-user -- uv run --directory C:\path\to\useful-claude-add-ons\mcp-servers\o365-user mcp-o365-user
claude mcp add ms-o365-admin -- uv run --directory C:\path\to\useful-claude-add-ons\mcp-servers\o365-admin mcp-o365-admin
```

None of these pass `--env` - the required variables (above) must already be
exported in the shell that launches Claude Code, on both platforms. `claude
mcp remove <name>` un-registers any of them.

The prerequisite installer scripts offer the same four as opt-in menu rows -
see [`../README.md`](../README.md#optional-mcp-servers) and
[`../INSTALLATION.md`](../INSTALLATION.md) - which ensure `uv` is on `PATH`
and print (never set) the env vars each row still needs before it will work.

## Verifying a real round trip

**Presence on `PATH` is not working auth.** Each server ships a `doctor`
entry point that acquires a real token, decodes its claims for display
(tenant, app/user identity, granted roles or scopes - no signature
verification, this is a display aid, not a trust decision), and makes one
harmless read call, so a scope or consent problem surfaces here instead of
on the first real tool call:

```bash
uv run --directory mcp-servers/intune mcp-intune-doctor
uv run --directory mcp-servers/graph-admin mcp-graph-admin-doctor
uv run --directory mcp-servers/o365-user mcp-o365-user-doctor   # first run prompts a device-code sign-in
uv run --directory mcp-servers/o365-admin mcp-o365-admin-doctor
```

A clean run prints the resolved tenant/app/user, the roles or scopes the
token actually carries, whether `*_ALLOW_WRITES` is on, and `OK` from one
live read. `READ FAILED` with a valid token almost always means a missing
Graph permission or missing admin consent - the doctor output names which
permission to check first, and `python scripts/auth.py --check`-style
reasoning in the [`intune-graph`](../skills/intune-graph/) skill covers the
same failure mode in more depth for Intune specifically.

Once a `doctor` run is clean, register the server (above) and re-run it from
inside a Claude Code session - ask Claude to list a handful of the read-only
tool's results and check them against the portal.

## Testing

```bash
cd mcp-servers
uv sync --all-packages
uv run pytest -q
```

All tests mock the Graph HTTP layer (`httpx.MockTransport`) and MSAL's
application classes - no network access, no live tenant, no credentials
needed. They verify request shaping (paths, `$select`/`$filter`/`$top`,
request bodies), paging (`@odata.nextLink`), retry/backoff on 429/5xx, error
message shape, the write-gate's four confirm/env-flag combinations per
gated tool, and - for `DeviceCodeAuth` - that the sign-in prompt goes to
stderr, never stdout.

**What is not covered, and cannot be without a live tenant:** whether a
given Graph permission set actually resolves the way its name suggests,
whether admin consent is correctly granted, real throttling behavior under
load, and the device-code flow's actual browser round trip. Run the
`doctor` entry points above against a real (ideally non-production) tenant
before trusting any of this against production data.
