# Devices: lookup, troubleshooting, remote actions

Base: `deviceManagement/managedDevices`

## Finding a device

Intune's OData support is inconsistent per field. These filters work on `managedDevices`:

```bash
# By name — 'contains' is NOT supported here; use eq or startswith
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "deviceName eq 'LAPTOP-4471'"

python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "startswith(deviceName,'LAP-')"

# By user — userPrincipalName supports eq; emailAddress supports contains
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "userPrincipalName eq 'jsmith@contoso.com'"

# By serial — NOT filterable on managedDevices. Filter client-side, or use
# the DevicesWithInventory export (see reporting.md) for fleet-wide serial lookup.
```

Reliably filterable: `deviceName` (eq/startswith), `userPrincipalName`, `complianceState`,
`operatingSystem`, `managementAgent`, `ownerType`, `azureADDeviceId` (eq), `deviceCategoryDisplayName`,
`lastSyncDateTime` (ge/le). If a filter 400s, it isn't supported — pull a `$select`ed
list and filter locally rather than fighting it.

## The sparse-field trap

A list call returns nulls/zeros for many fields. These populate only on an individual GET
with an explicit `$select`:

`ethernetMacAddress`, `physicalMemoryInBytes`, `totalStorageSpaceInBytes`,
`freeStorageSpaceInBytes`, `activationLockBypassCode`, `hardwareInformation` (beta)

```bash
python scripts/graph.py GET "deviceManagement/managedDevices/{id}" \
  --select "deviceName,ethernetMacAddress,physicalMemoryInBytes,totalStorageSpaceInBytes"
```

Before reporting a field as empty in the tenant, re-fetch the single device this way.

## Troubleshooting a specific device

Work in this order — it's roughly cheapest-to-most-invasive, and usually stops early:

**1. Current state.**
```bash
python scripts/graph.py GET "deviceManagement/managedDevices/{id}" \
  --select "deviceName,userPrincipalName,complianceState,managementState,lastSyncDateTime,osVersion,enrolledDateTime,managementAgent,jailBroken,partnerReportedThreatState"
```
Read `lastSyncDateTime` first. A device that hasn't checked in for weeks explains most
"policy isn't applying" reports on its own — nothing is broken, the machine is just gone
or asleep. `managementState` also matters: `retirePending` or `wipePending` means someone
already queued a destructive action.

**2. Why is it non-compliant?** The per-setting states live under the policy states:
```bash
python scripts/graph.py GET "deviceManagement/managedDevices/{id}/deviceCompliancePolicyStates"
python scripts/graph.py GET "deviceManagement/managedDevices/{id}/deviceConfigurationStates"
```
Each entry has `state`, `displayName`, and `settingStates` naming the exact failing
setting. This is the answer to "which policy is doing this" — start here, not in the
policy list.

**3. What actions are pending?** `deviceActionResults` on the device object shows queued
vs. completed actions with timestamps — this is how you tell whether an earlier sync
actually landed.

**4. Discovered apps** (per-device only; there's no fleet-wide list call):
```bash
python scripts/graph.py GET "deviceManagement/managedDevices/{id}/detectedApps"
```
For fleet-wide app inventory use the Export API — looping this endpoint across a tenant
is exactly the pattern that gets you throttled into oblivion.

## Common diagnostic filters

```bash
# Stale — no check-in in 30 days. Prime legacy-cleanup target.
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "lastSyncDateTime le 2026-06-14T00:00:00Z" \
  --select "deviceName,userPrincipalName,lastSyncDateTime,complianceState"

# Non-compliant Windows
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "complianceState eq 'noncompliant' and operatingSystem eq 'Windows'" \
  --select "deviceName,userPrincipalName,osVersion,lastSyncDateTime" --count-only

# Co-managed (SCCM + Intune) — the usual legacy migration cohort
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "managementAgent eq 'configurationManagerClientMdm'" \
  --select "deviceName,managementAgent,osVersion"
```

`complianceState`: `unknown`, `compliant`, `noncompliant`, `conflict`, `error`, `inGracePeriod`, `configManager`.
`conflict` and `error` are distinct from `noncompliant` and are frequently the interesting
ones in a legacy tenant — they mean two policies disagree, or evaluation itself failed.

## Remote actions

POST to `deviceManagement/managedDevices/{id}/{action}`. Nearly all return **204 No Content**,
which means *queued*, not *done*. The device acts on next check-in — which for a laptop in
a drawer is never.

Non-destructive:

| Action | Notes |
|---|---|
| `syncDevice` | Force check-in. First thing to try for "policy not applying". |
| `rebootNow` | Reboots. Users lose unsaved work — warn them. |
| `locateDevice` | iOS/Android supervised only |
| `windowsDefenderScan` | body: `{"quickScan": true}` |
| `windowsDefenderUpdateSignatures` | |
| `rotateBitLockerKeys` | |

Destructive — **confirm scope with the user by name and count before firing**:

| Action | Effect |
|---|---|
| `wipe` | Factory reset. Data gone. body: `{"keepEnrollmentData": false, "keepUserData": false}` |
| `retire` | Removes company data + management, leaves personal data. The right choice for BYOD offboarding. |
| `resetPasscode` | Locks user out until they set a new one |
| `deleteUserFromSharedAppleDevice` | |
| `disableLostMode` / `enableLostMode` | Supervised iOS |

`wipe` vs `retire` gets confused constantly and the difference is somebody's personal
photos. If the user says "wipe" but describes offboarding a BYOD phone, ask which they mean.

Bulk sync, with the count stated up front:

```bash
python scripts/graph.py GET "deviceManagement/managedDevices" \
  --filter "complianceState eq 'noncompliant'" --select "id,deviceName" > /tmp/d.json
python3 - << 'PY'
import json, sys
sys.path.insert(0, "scripts")
from graph import GraphClient
devices = json.load(open("/tmp/d.json"))
print(f"About to sync {len(devices)} devices")   # show this before proceeding
g = GraphClient()
for d in devices:
    g.post(f"deviceManagement/managedDevices/{d['id']}/syncDevice")
    print(f"  queued: {d['deviceName']}")
PY
```

## Autopilot

Separate resource — Autopilot registration is not the same as enrollment, and a device
can exist in one and not the other:

```bash
python scripts/graph.py GET "deviceManagement/windowsAutopilotDeviceIdentities" \
  --filter "contains(serialNumber,'ABC')"
```

`deviceManagement/windowsAutopilotDeploymentProfiles` holds the profiles. When a machine
"isn't getting its Autopilot profile", check that it appears here *and* that a profile is
assigned to a group containing it — those are two different failures with one symptom.
