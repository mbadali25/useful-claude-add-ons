# Reporting and bulk exports

**Use the Export API for anything fleet-wide.** It's not merely faster than paging list
endpoints — for large tenants it's the difference between a minute and several throttled
hours, and it exposes fields (serial numbers, storage, discovered apps) that list calls
either omit or only return per-device.

Endpoint: `deviceManagement/reports/exportJobs` (v1.0 and beta; some report names are
beta-only).

## Quick use

```bash
python scripts/export_report.py --list                      # common report names
python scripts/export_report.py --report Devices
python scripts/export_report.py --report DevicesWithInventory --format csv -o ./out

python scripts/export_report.py --report Devices \
  --filter "(OwnerType eq '1')" \
  --select DeviceName,OS,OSVersion,LastContact,UPN,complianceState
```

The script handles the full submit → poll → download → unzip cycle. Output is a zipped
CSV or JSON; it unzips into `-o`.

## The flow, if hand-rolling

1. `POST deviceManagement/reports/exportJobs` with `{"reportName": "...", "format": "csv",
   "select": [...], "filter": "...", "localizationType": "..."}` → returns an `id` like
   `Devices_05e62361-783b-4cec-b635-0aed0ecf14a3`
2. `GET deviceManagement/reports/exportJobs('{id}')` — poll until `status` is `completed`.
   The id must be quoted in the URL. Takes seconds to minutes depending on tenant size.
3. `GET` the returned `url` — a **pre-signed blob URL**. Send no Authorization header
   (it 403s if you do), and note it expires within hours.
4. Unzip → CSV/JSON inside.

## Choosing a report

| Report | Use for |
|---|---|
| `Devices` | Core inventory, one row per device |
| `DevicesWithInventory` | Devices + serial, storage, memory, manufacturer/model — **the one you usually want** |
| `DeviceCompliance` | Compliance state per device |
| `DeviceNonCompliance` | Non-compliant only — smaller, faster |
| `DevicesStatusBySettingReport` | Which devices fail which setting |
| `AllAppsList` | Every app in the tenant |
| `AppInstallStatusAggregate` | Install success/failure counts per app |
| `DeviceInstallStatusByApp` | Per-device install status (requires an app filter) |
| `ActiveMalware` / `Malware` | Defender detections |
| `ComanagedDeviceWorkloads` | SCCM/Intune workload split — the report for co-management migrations |
| `AllDeviceCertificates` | Deployed certificates |
| `ChromeOSDevices` | ChromeOS inventory |

Full current list (report names and their filterable columns change over time):
https://learn.microsoft.com/en-us/intune/intune-service/fundamentals/reports-export-graph-available-reports

## Filters

Export filters are **not** OData — different syntax, parenthesised, with numeric enum
codes rather than the string values the regular API uses:

```
(OwnerType eq '1')                              # 1 = company, 2 = personal
(ManagementAgents eq '2')
(ManagementAgents eq '2') and (OwnerType eq '1')
```

Only the columns documented as filterable for that specific report will work. An
unsupported column produces an empty or failed job rather than a clear error, which is
worth knowing before you spend twenty minutes on it. `select` accepts any column the
report defines; omitting `select` returns all of them.

`localizationType`: `LocalizedValuesAsAdditionalColumn` adds a friendly-name column
alongside each raw enum. Worth setting — otherwise `OwnerType` reads `1` and nobody knows
what that means. **`Devices` and `DevicesWithInventory` ignore this parameter** for
legacy-compatibility reasons, so their enums stay raw regardless.

## Throttling

100 requests/tenant/minute; 8/user/minute for delegated tokens; 48/app/minute for app-only.
Well clear of anything a single export needs — but if you're generating exports in a loop,
app-only auth gives you 6x the headroom of a user token.

## Analysing the output

Once downloaded it's an ordinary CSV — pandas, or the `xlsx` skill if the user wants a
formatted workbook.

```python
import pandas as pd
df = pd.read_csv("out/DevicesWithInventory_....csv")
stale = df[pd.to_datetime(df["LastContact"], errors="coerce") < "2026-04-01"]
print(f"{len(stale)} devices with no check-in since April")
print(stale.groupby("OS").size())
```

Cross-referencing exports is where this gets genuinely useful for legacy cleanup: join
`Devices` against `DeviceNonCompliance` on `DeviceId` to separate devices that are
non-compliant because something is misconfigured from devices that are non-compliant
because they simply stopped checking in months ago. Those two groups look identical in
the console and need completely different remediation — one is a policy fix, the other is
asset recovery.

## When not to use the Export API

- Single device, or a handful — just GET them; the export round-trip isn't worth it.
- You need live state right now. Exports run off a reporting snapshot that can lag the
  device's actual last check-in.
- The data isn't in any report (e.g. the settings tree of a specific config policy). Use
  the direct endpoints.
