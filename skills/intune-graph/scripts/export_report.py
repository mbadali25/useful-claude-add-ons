#!/usr/bin/env python3
"""Run an Intune Export API job end to end: submit -> poll -> download -> unzip.

This is the right tool for anything fleet-wide. Paging GET /managedDevices across
a large tenant takes hours and gets throttled; this returns the same data as CSV
in about a minute.

    python export_report.py --report Devices
    python export_report.py --report DevicesWithInventory --format csv -o ./out
    python export_report.py --report Devices --filter "(OwnerType eq '1')" \
        --select DeviceName,OS,OSVersion,LastContact,UPN
    python export_report.py --list

Throttling: 100 requests/tenant/minute, 8/user/minute, 48/app/minute.
Docs: https://learn.microsoft.com/en-us/intune/intune-service/fundamentals/reports-export-graph-available-reports
"""
import argparse
import io
import os
import sys
import time
import zipfile

import requests

from auth import AuthError
from graph import GraphClient, GraphError

# Common report names. Not exhaustive — the Learn page above is authoritative,
# and available reports change over time.
COMMON_REPORTS = {
    "Devices": "Core device inventory (one row per device)",
    "DevicesWithInventory": "Devices plus hardware inventory — serial, storage, memory",
    "DeviceCompliance": "Per-device compliance state",
    "DeviceNonCompliance": "Non-compliant devices only",
    "DevicesStatusBySettingReport": "Which setting failed on which device",
    "AllAppsList": "Every app in the tenant",
    "AppInstallStatusAggregate": "Install success/failure counts per app",
    "DeviceInstallStatusByApp": "Per-device install status for one app (needs filter)",
    "ActiveMalware": "Defender malware detections",
    "ComanagedDeviceWorkloads": "SCCM/Intune workload split — useful for co-management migrations",
    "AllDeviceCertificates": "Certificates deployed to devices",
    "ChromeOSDevices": "ChromeOS device inventory",
}


# `filter` shadows the builtin deliberately: it mirrors OData's $filter.
# pylint: disable-next=redefined-builtin
def run_export(g, report, fmt="csv", filter=None, select=None, localization=None,
               out_dir=".", timeout=900, poll=10):
    body = {"reportName": report, "format": fmt}
    if filter:
        body["filter"] = filter
    if select:
        body["select"] = select
    if localization:
        body["localizationType"] = localization

    print(f"Submitting export job: {report}", file=sys.stderr)
    job = g.post("deviceManagement/reports/exportJobs", body=body)
    job_id = job["id"]
    print(f"  job id: {job_id}", file=sys.stderr)

    deadline = time.time() + timeout
    while time.time() < deadline:
        # The id embeds the report name and must be quoted in the URL.
        status = g.request("GET", f"deviceManagement/reports/exportJobs('{job_id}')")
        state = status.get("status")
        if state == "completed":
            url = status["url"]
            print("  completed, downloading...", file=sys.stderr)
            return _download(url, report, out_dir)
        if state == "failed":
            raise GraphError(f"Export job failed: {status}")
        print(f"  status={state}, waiting {poll}s...", file=sys.stderr)
        time.sleep(poll)
    raise GraphError(f"Export job {job_id} did not complete within {timeout}s.")


def _download(url, report, out_dir):
    """The URL is a pre-signed blob link — no auth header, and it expires."""
    os.makedirs(out_dir, exist_ok=True)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    written = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            dest = os.path.join(out_dir, os.path.basename(name))
            with z.open(name) as src, open(dest, "wb") as dst:
                dst.write(src.read())
            written.append(dest)
            print(f"  wrote {dest} ({os.path.getsize(dest):,} bytes)", file=sys.stderr)
    return written


def main():
    ap = argparse.ArgumentParser(description="Export an Intune report via the Graph Export API.")
    ap.add_argument("--report", help="reportName, e.g. Devices, DevicesWithInventory")
    ap.add_argument("--list", action="store_true", help="list common report names")
    ap.add_argument("--format", default="csv", choices=["csv", "json"])
    ap.add_argument("--filter", help="report filter, e.g. \"(OwnerType eq '1')\"")
    ap.add_argument("--select", help="comma-separated columns")
    ap.add_argument("--localization", choices=["LocalizedValuesAsAdditionalColumn", "ReplaceLocalizableValues"],
                    help="Devices/DevicesWithInventory ignore this for legacy compat reasons")
    ap.add_argument("-o", "--out", default=".", help="output directory")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--beta", action="store_true", help="use beta (some reports are beta-only)")
    ap.add_argument("--mode", choices=["client_credentials", "device_code", "azure_cli"])
    a = ap.parse_args()

    if a.list:
        print("Common report names (see Learn docs for the full, current list):\n")
        for k, v in COMMON_REPORTS.items():
            print(f"  {k:38s} {v}")
        return
    if not a.report:
        ap.error("--report is required (or use --list)")

    try:
        g = GraphClient(mode=a.mode, beta=a.beta)
        files = run_export(
            g, a.report, fmt=a.format, filter=a.filter,
            select=a.select.split(",") if a.select else None,
            localization=a.localization, out_dir=a.out, timeout=a.timeout,
        )
        for f in files:
            print(f)
    except (GraphError, AuthError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
