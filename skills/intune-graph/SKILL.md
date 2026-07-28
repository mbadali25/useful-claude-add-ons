---
name: intune-graph
description: Query and manage Microsoft Intune through the Microsoft Graph API — device lookup and troubleshooting, compliance and configuration profiles, Win32/LOB app deployment, and bulk report exports. Use this skill whenever the user mentions Intune, Endpoint Manager, MEM, MDM, managed devices, Autopilot, compliance policies, configuration profiles, settings catalog, .intunewin packages, device enrollment, co-management, or the deviceManagement/deviceAppManagement Graph endpoints — even if they don't say "Graph API" or "Intune" explicitly (e.g. "why is this laptop showing non-compliant", "push a sync to these machines", "export our device inventory", "which policy is setting BitLocker"). Also use it when writing PowerShell or Python that touches Intune, or when debugging a 403/429 from graph.microsoft.com, since the auth setup and endpoint quirks documented here prevent most of the common failures.
---

# Intune via Microsoft Graph

Intune has no first-party MCP connector. Everything goes through the Microsoft Graph REST API under two roots:

- `deviceManagement/*` — devices, policies, compliance, scripts, reports
- `deviceAppManagement/*` — apps, app protection policies, assignments

The bundled scripts handle auth, paging, and throttling so those don't have to be re-solved every time.

## Before doing anything: establish auth

Nothing works without a token, and token setup is where most Intune automation dies. **Read `references/auth-setup.md` first** on any new engagement — it covers the three viable auth modes, how to pick between them, and the exact app registration steps.

Quick decision:

| Situation | Mode |
|---|---|
| Scheduled jobs, CI, no human present | App registration + client secret/cert (`client_credentials`) |
| Ad-hoc troubleshooting as yourself, RBAC scoping matters | Device code flow |
| Already have `az login` on the box | Azure CLI token passthrough |

Then verify before proceeding:

```bash
python scripts/auth.py --check
```

This prints the token's tenant, app/user identity, and granted scopes. Run it before debugging any 403 — the answer is almost always a missing scope or absent admin consent, and this shows it in one line instead of ten minutes of guessing.

## Making requests

Use `scripts/graph.py` rather than raw `requests`/`Invoke-RestMethod`. It handles `@odata.nextLink` paging, honors `Retry-After` on 429s (Intune throttles aggressively), and surfaces the nested Intune error message that Graph buries inside a JSON-string-within-JSON.

```bash
# List — pages automatically
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "complianceState eq 'noncompliant'" \
  --select "deviceName,userPrincipalName,osVersion,lastSyncDateTime"

# Single object
python scripts/graph.py GET "deviceManagement/managedDevices/{id}"

# Action
python scripts/graph.py POST "deviceManagement/managedDevices/{id}/syncDevice"

# Write
python scripts/graph.py PATCH "deviceManagement/managedDevices/{id}" --body '{"deviceCategoryDisplayName":"Kiosk"}'
```

Import it instead when scripting something multi-step:

```python
from graph import GraphClient
g = GraphClient()
devices = g.get_all("deviceManagement/managedDevices", filter="operatingSystem eq 'Windows'")
```

### v1.0 vs beta

Default to `v1.0`. Reach for `beta` (`--beta`) only when the resource genuinely doesn't exist in v1.0 — notably the settings catalog (`configurationPolicies`), several Win32 app sub-resources, and some report types. Beta can change without notice, so when a script depends on it, note why in a comment so the next person isn't left guessing.

## Task routing

Read the reference file for the task at hand — each contains the endpoint shapes, the filterable fields (Intune's OData support is patchy and inconsistent between endpoints), and the failure modes:

| Task | Read |
|---|---|
| Find devices, diagnose enrollment/sync/compliance on a specific machine, remote actions | `references/devices.md` |
| Compliance policies, configuration profiles, settings catalog, which policy set which setting | `references/compliance-and-config.md` |
| Win32/LOB apps, `.intunewin` upload, assignments, install failures | `references/apps.md` |
| Bulk exports, inventory, fleet-wide reporting | `references/reporting.md` |

## Working practices

**Prefer the Export API for anything fleet-wide.** Looping `GET /managedDevices` across 20k devices takes hours and gets throttled; `deviceManagement/reports/exportJobs` returns the same data as a CSV in about a minute. Rule of thumb: more than a few hundred records, or you need a field that only appears on individual GETs, means use the Export API. `scripts/export_report.py` runs the whole submit→poll→download→unzip cycle.

**Sparse list responses are expected, not a bug.** Many `managedDevice` properties — `ethernetMacAddress`, `physicalMemoryInBytes`, `activationLockBypassCode`, `totalStorageSpaceInBytes` — come back null or zero from a list call and only populate on an individual GET with an explicit `$select`. Don't conclude the data is missing from the tenant; re-fetch the single device with `$select` before telling the user anything is wrong.

**Confirm destructive actions before firing them.** `wipe`, `retire`, `resetPasscode`, `deleteUserFromSharedAppleDevice`, and deleting policies or apps are irreversible and hit real hardware belonging to real people. State the exact scope — how many devices, which ones, by name — and get explicit confirmation first. If a filter would hit more devices than the user seems to expect, surface that gap rather than proceeding. `syncDevice` and `rebootNow` are lower stakes but still worth naming the count.

**Reproduce read-only first.** When troubleshooting, pull current state and show it before proposing a change. Legacy tenants accumulate overlapping policies, and the profile someone assumes is responsible frequently isn't.

**Never write secrets into scripts or output.** Client secrets belong in environment variables (see `references/auth-setup.md`). When showing a command or config to the user, reference `$INTUNE_CLIENT_SECRET`, never the value. Certificate auth beats a secret for anything long-lived.

**Report what actually happened.** Graph actions frequently return `204 No Content` while the device does nothing for hours — a queued `syncDevice` is not a completed sync. Say "queued" when it's queued. Check `deviceActionResults` on the device for real state.
