# Auth setup for Intune Graph

Read this before touching any other reference. Almost every "the API is broken" report
in Intune automation is an auth problem wearing a costume.

## Contents
- [Picking a mode](#picking-a-mode)
- [Mode 1: app registration (client credentials)](#mode-1-app-registration-client-credentials)
- [Mode 2: device code flow](#mode-2-device-code-flow)
- [Mode 3: Azure CLI passthrough](#mode-3-azure-cli-passthrough)
- [Permission scopes](#permission-scopes)
- [Certificate auth](#certificate-auth)
- [Diagnosing failures](#diagnosing-failures)

## Picking a mode

| | client_credentials | device_code | azure_cli |
|---|---|---|---|
| Human needed | No | Yes, once per token | No (after `az login`) |
| Good for | Scheduled jobs, CI, bulk exports | Ad-hoc troubleshooting | Quick local work |
| Permissions | Application (tenant-wide) | Delegated (user's own rights) | Delegated |
| Respects Intune RBAC scope tags | No — sees everything | Yes | Yes |
| Secret to manage | Yes | No | No |

The RBAC row matters more than it looks. An app-only token ignores Intune role scoping
and sees the entire tenant. That is exactly what you want for a nightly inventory export
and exactly what you don't want for handing someone a troubleshooting script. If the
work is interactive, prefer device code — the blast radius is the operator's own rights.

## Mode 1: app registration (client credentials)

In the Entra admin center (entra.microsoft.com):

1. **Identity > Applications > App registrations > New registration**. Name it something
   a future admin will understand — `intune-automation-reporting`, not `test-app-2`.
   Single tenant. No redirect URI needed.
2. Copy the **Application (client) ID** and **Directory (tenant) ID** from Overview.
3. **API permissions > Add a permission > Microsoft Graph > Application permissions**.
   This is the step people get wrong: pick **Application permissions**, not Delegated.
   Delegated permissions on an app-only token produce a 403 that claims you lack a
   permission you can plainly see listed in the portal.
4. Add the scopes you need (see below). Then **Grant admin consent** — the permissions do
   nothing until this is clicked, and the column must read "Granted for {tenant}".
5. **Certificates & secrets > New client secret**. Copy the *Value* (not the Secret ID)
   immediately; it's shown once. Set a calendar reminder for expiry — a 24-month secret
   silently breaking a nightly job two years later is a classic legacy failure.

```bash
export INTUNE_AUTH_MODE=client_credentials
export INTUNE_TENANT_ID=00000000-0000-0000-0000-000000000000
export INTUNE_CLIENT_ID=00000000-0000-0000-0000-000000000000
export INTUNE_CLIENT_SECRET='...'     # from a vault, never committed
python scripts/auth.py --check
```

Put these in a vault (Key Vault, a CI secret store, `pass`) and export at runtime. If a
secret ever lands in a repo, rotate it — it's compromised, and history rewriting doesn't
change that it was cloned.

## Mode 2: device code flow

Requires no app registration at all: it defaults to Microsoft's well-known Azure PowerShell
public client ID, which is pre-consented in most tenants.

```bash
export INTUNE_AUTH_MODE=device_code
export INTUNE_TENANT_ID=contoso.onmicrosoft.com   # optional
python scripts/auth.py --check
# prints a code -> open microsoft.com/devicelogin -> sign in
```

The token lands in `~/.intune_graph_token.json` (0600) and lasts ~1 hour, so you won't
re-prompt on every command. If your tenant blocks the default client, register a public
client app (Authentication > Add platform > Mobile and desktop, enable "Allow public
client flows") and set `INTUNE_CLIENT_ID`.

Conditional Access can block device code flow outright — some tenants disable it as an
anti-phishing measure. If sign-in fails with a CA policy error, that's policy, not a bug;
use `azure_cli` or an app registration.

## Mode 3: Azure CLI passthrough

```bash
az login
export INTUNE_AUTH_MODE=azure_cli
python scripts/auth.py --check
```

Simplest when it works. The catch: the Azure CLI's own client ID must have the Graph
permissions consented, which in locked-down tenants it doesn't. Fine for exploration,
not something to build a pipeline on.

## Permission scopes

Grant the narrowest set that does the job. `.ReadWrite.All` on an app-only token is
effectively tenant admin over every managed device in the company.

| Scope | Covers |
|---|---|
| `DeviceManagementManagedDevices.Read.All` | Read devices, compliance state, hardware inventory |
| `DeviceManagementManagedDevices.ReadWrite.All` | Above + remote actions (sync, reboot, **wipe**, **retire**) |
| `DeviceManagementConfiguration.Read.All` | Read compliance policies, config profiles, settings catalog |
| `DeviceManagementConfiguration.ReadWrite.All` | Create/modify/delete policies |
| `DeviceManagementApps.Read.All` | Read apps and assignments |
| `DeviceManagementApps.ReadWrite.All` | Create apps, upload `.intunewin`, assign |
| `DeviceManagementServiceConfig.Read.All` | Enrollment config, Autopilot profiles |
| `DeviceManagementRBAC.Read.All` | Roles and scope tags |
| `Directory.Read.All` | Resolve users/groups referenced by assignments |

Read-only reporting needs only the three `.Read.All` scopes plus `Directory.Read.All`.
That covers most troubleshooting. Note that `ReadWrite` on managed devices includes wipe
— there is no separate "remote actions but not destructive" scope, which is precisely why
the confirmation practice in SKILL.md exists.

Export jobs accept any of `DeviceManagementConfiguration.*`, `DeviceManagementApps.*`,
or `DeviceManagementManagedDevices.*` — the report you request determines which you need.

## Certificate auth

Better than a secret for long-lived automation: no expiring string in a vault, and the
private key can live in an HSM. Needs a signed JWT assertion, so use `msal`:

```python
import msal
app = msal.ConfidentialClientApplication(
    client_id=CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    client_credential={"thumbprint": THUMBPRINT, "private_key": open("key.pem").read()},
)
token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])["access_token"]
```

Upload the public cert under **Certificates & secrets > Certificates**. `scripts/auth.py`
raises a pointer to this section rather than half-implementing it.

## Diagnosing failures

Run `python scripts/auth.py --check` first. It prints tenant, identity, token type, and
granted scopes — which resolves most of these on sight.

| Symptom | Cause |
|---|---|
| 403, "Application is not authorized... must have one of the following scopes" | Scope missing, or admin consent never granted. The portal listing a permission is not the same as consent. |
| 403, "called in app only context but does not have application permissions configured" | Delegated permissions on an app-only token. Add the **Application** variant. |
| 403 with correct scopes on a delegated token | The signed-in user has no Intune RBAC role, or scope tags exclude the object. |
| 401 immediately | Expired token. Delete `~/.intune_graph_token.json`. |
| 400 `AADSTS7000215` | Invalid client secret — usually the Secret ID was copied instead of the Value, or it expired. |
| 400 `AADSTS700016` | App not found in tenant — wrong tenant ID, or app registered elsewhere. |
| "Tenant does not have a valid Intune license" | Real. Graph's Intune surface requires an active Intune license on the tenant. |
| 429 | Throttling. `scripts/graph.py` honors Retry-After automatically; if you're hitting it constantly, switch to the Export API. |
