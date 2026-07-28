# Compliance policies and configuration profiles

The single most useful thing to know: **to find out why a device has a setting, start from
the device, not from the policy list.** `deviceManagement/managedDevices/{id}/deviceConfigurationStates`
answers "which policy did this" directly. Enumerating policies and reasoning about
assignments is slow, and in a legacy tenant with overlapping profiles it's often wrong.

## The three generations

Legacy tenants accumulate all three at once. This is usually the actual source of confusion,
and it's worth naming explicitly to the user when it comes up:

| Generation | Endpoint | Notes |
|---|---|---|
| Compliance policies | `deviceManagement/deviceCompliancePolicies` (v1.0) | Marks devices compliant/not. Feeds Conditional Access. |
| Device configuration (legacy) | `deviceManagement/deviceConfigurations` (v1.0) | The older templates. Most old profiles live here. |
| Settings catalog (current) | `deviceManagement/configurationPolicies` (**beta**) | Where new work goes. Different schema entirely. |

A setting can be delivered by any of the three, and they can conflict. `complianceState`
of `conflict` on a device means exactly this. When someone says "I deleted the policy but
the setting is still there", the setting is nearly always coming from a different
generation than the one they were looking at.

## Compliance policies

```bash
python scripts/graph.py GET "deviceManagement/deviceCompliancePolicies" \
  --select "id,displayName,description,lastModifiedDateTime"

# Who is it assigned to?
python scripts/graph.py GET "deviceManagement/deviceCompliancePolicies/{id}/assignments"

# Aggregate pass/fail
python scripts/graph.py GET "deviceManagement/deviceCompliancePolicies/{id}/deviceStatusOverview"

# Per-device detail
python scripts/graph.py GET "deviceManagement/deviceCompliancePolicies/{id}/deviceStatuses"
```

The `@odata.type` on each policy tells you the platform:
`#microsoft.graph.windows10CompliancePolicy`, `androidWorkProfileCompliancePolicy`,
`iosCompliancePolicy`, `macOSCompliancePolicy`. Filtering by type needs the cast syntax:

```bash
python scripts/graph.py GET "deviceManagement/deviceCompliancePolicies" \
  --filter "isof('microsoft.graph.windows10CompliancePolicy')"
```

Assignments reference group IDs, not names. Resolve them (needs `Directory.Read.All`):

```bash
python scripts/graph.py GET "groups/{groupId}" --select "displayName"
```

Watch for `#microsoft.graph.allDevicesAssignmentTarget` and `allLicensedUsersAssignmentTarget`
in the target — those are tenant-wide and don't name a group. An "All Devices" assignment
left over from a pilot is a classic legacy landmine: it explains why a policy applies to
machines nobody intended.

Also check `exclusionGroupAssignmentTarget`. A policy that "isn't applying" to a device
that's clearly in the included group is very often excluded by a second, forgotten
assignment.

## Configuration profiles (legacy)

```bash
python scripts/graph.py GET "deviceManagement/deviceConfigurations" \
  --select "id,displayName,lastModifiedDateTime"
python scripts/graph.py GET "deviceManagement/deviceConfigurations/{id}/assignments"
python scripts/graph.py GET "deviceManagement/deviceConfigurations/{id}/deviceStatuses"
```

`deviceConfigurations/{id}/deviceSettingStateSummaries` gives per-setting rollups —
useful when one setting in an otherwise-fine profile is failing fleet-wide.

## Settings catalog (beta only)

Different shape: settings are a nested `settingInstance` tree keyed by opaque IDs like
`device_vendor_msft_bitlocker_requiredeviceencryption`, not friendly names.

```bash
python scripts/graph.py GET "deviceManagement/configurationPolicies" --beta \
  --select "id,name,description,platforms,technologies"

# Expand the settings tree — verbose, but it's the only way to see actual values
python scripts/graph.py GET "deviceManagement/configurationPolicies/{id}" --beta \
  --expand "settings"
```

To resolve what a setting ID actually means:
```bash
python scripts/graph.py GET "deviceManagement/configurationSettings" --beta \
  --filter "id eq 'device_vendor_msft_bitlocker_requiredeviceencryption'"
```

Creating settings catalog policies by hand-writing JSON is genuinely painful and easy to
get subtly wrong. The reliable move: build it once in the Intune portal, GET it with
`--expand settings`, and use that as the template. Say so rather than improvising a tree
from scratch — the portal is faster and correct.

## Which policy set this setting?

```bash
# 1. Device's config states — names the responsible profile per setting
python scripts/graph.py GET "deviceManagement/managedDevices/{id}/deviceConfigurationStates"

# 2. Drill into a specific one
python scripts/graph.py GET \
  "deviceManagement/managedDevices/{id}/deviceConfigurationStates/{stateId}/settingStates"
```

`settingStates` gives `setting`, `settingName`, `state`, `errorCode`, `errorDescription`,
and `sources` — `sources` names the conflicting policies when state is `conflict`. That
field is the whole answer to a conflict investigation.

For fleet-wide "which devices fail setting X", use the `DevicesStatusBySettingReport`
export (see reporting.md) rather than looping devices.

## Scripts and remediations

```bash
python scripts/graph.py GET "deviceManagement/deviceManagementScripts" --beta   # PowerShell scripts
python scripts/graph.py GET "deviceManagement/deviceHealthScripts" --beta        # Proactive remediations
python scripts/graph.py GET "deviceManagement/deviceManagementScripts/{id}/deviceRunStates" --beta
```

Script content comes back base64 in `scriptContent`. Decode before reading:
```bash
python3 -c "import base64,sys,json; print(base64.b64decode(json.load(sys.stdin)['scriptContent']).decode())"
```

Orphaned platform scripts from years past are a frequent legacy culprit — a script that
still runs at every check-in and reverses whatever the current policy sets. If a setting
keeps reverting and no policy explains it, look here.

## Modifying policies

PATCH needs the `@odata.type` in the body or it 400s:

```bash
python scripts/graph.py PATCH "deviceManagement/deviceCompliancePolicies/{id}" \
  --body '{"@odata.type":"#microsoft.graph.windows10CompliancePolicy","passwordMinimumLength":8}'
```

Before changing an assigned policy, GET it and show the user the current value alongside
the proposed one. A compliance policy edit can cascade into Conditional Access and lock
people out of email within the hour — the change is small, the blast radius isn't.
