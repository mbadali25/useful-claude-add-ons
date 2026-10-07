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
import tempfile
import time
import zipfile

import requests

from auth import AuthError
from graph import GraphClient, GraphError

# Common report names. Not exhaustive - the Learn page above is authoritative,
# and available reports change over time.
COMMON_REPORTS = {
    "Devices": "Core device inventory (one row per device)",
    "DevicesWithInventory": "Devices plus hardware inventory - serial, storage, memory",
    "DeviceCompliance": "Per-device compliance state",
    "DeviceNonCompliance": "Non-compliant devices only",
    "DevicesStatusBySettingReport": "Which setting failed on which device",
    "AllAppsList": "Every app in the tenant",
    "AppInstallStatusAggregate": "Install success/failure counts per app",
    "DeviceInstallStatusByApp": "Per-device install status for one app (needs filter)",
    "ActiveMalware": "Defender malware detections",
    "ComanagedDeviceWorkloads": "SCCM/Intune workload split - useful for co-management migrations",
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


def _stage_write(dest, data):
    """Write `data` to a temp file in `dest`'s directory, with the mode
    `dest` would end up with, and return `(dest, tmp_path)` for a later
    `os.replace`. Does not touch `dest` itself - see `_download`'s two-phase
    commit for why.

    Mode: `mkstemp` always creates its temp file `0600`, and `os.replace`
    installs that inode as-is - so without this, every export would come out
    `0600` regardless of what was there before (an existing `0664` export
    reset to owner-only on every re-run). If `dest` already exists, copy its
    mode onto the temp file before replacing. If it doesn't, apply the
    process umask the way a fresh `open(dest, "wb")` would have
    (`0o666 & ~umask`), rather than leaving the temp file's `0600`.

    Symlinks: `os.replace(tmp, dest)` does not follow a symlink at `dest` -
    it unlinks the symlink and installs the new file in its place, breaking
    the link, where the old `open(dest, "wb")` would have followed it and
    written through to the linked-to file. Resolving `dest` with
    `os.path.realpath` and writing through would restore that behaviour, but
    `out_dir` is caller-supplied on the CLI and a symlink inside it could
    point anywhere on the filesystem - following it silently is exactly the
    kind of surprise a tool that writes files named after a zip's own
    members should not have. Refuse loudly instead; the caller can remove or
    replace the symlink themselves.
    """
    directory = os.path.dirname(dest) or "."
    if os.path.islink(dest):
        raise OSError(
            f"refusing to write through a symlink at {dest} - remove it or "
            "replace it with a regular file (or nothing) first"
        )

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".export-report-tmp-")
    try:
        with os.fdopen(fd, "wb") as tmp_f:
            tmp_f.write(data)
            tmp_f.flush()
            os.fsync(tmp_f.fileno())

        try:
            mode = os.stat(dest).st_mode & 0o777
        except FileNotFoundError:
            umask = os.umask(0)
            os.umask(umask)  # os.umask() only reads by also setting - restore it
            mode = 0o666 & ~umask
        os.chmod(tmp_path, mode)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise
    return dest, tmp_path


def _download(url, report, out_dir):
    """The URL is a pre-signed blob link - no auth header, and it expires."""
    os.makedirs(out_dir, exist_ok=True)
    r = requests.get(url, timeout=300)
    r.raise_for_status()

    # Two-phase, all-or-nothing: stage every member into its own temp file
    # first - reading it AND writing+fsyncing it - and only replace any of
    # them onto their real destinations once every member has staged
    # successfully. A multi-member export where member N fails, whether the
    # *read* is a corrupt zip entry or the *write* hits ENOSPC/EIO, must not
    # leave members 1..N-1 already installed while N.. are stale or missing;
    # that mixes generations in out_dir with nothing recording which files
    # are from which run.
    #
    # Trade-off is disk, not memory: each member is read, staged to its own
    # temp file, and its `data` bytes then go out of scope before the next
    # member is read - so peak memory stays roughly one member's size, the
    # same as before this staging existed. Peak *disk* use is what grows:
    # every member's old file (if any) and its staged replacement coexist
    # from that member's staging until the commit loop runs, so out_dir can
    # briefly hold ~2x the export's total size. Fine for report-sized
    # CSV/JSON exports; a streaming/rollback design would be needed for
    # anything large.
    #
    # The commit loop CAN still fail partway even though staging succeeded
    # for everything - `os.replace` fails with PermissionError every time on
    # Windows when the destination CSV is open in Excel, and that is not a
    # rare race, it is the normal shape of "someone left last week's export
    # open". Unlike a staging failure (fully rolled back, nothing on disk
    # changes), a commit failure happens after some members may have already
    # been installed: there is no undo for an `os.replace` that already
    # succeeded, so this names exactly which destinations got the new
    # export, which are still at their old version (or never existed), and
    # which staged temp files are left needing cleanup - rather than a bare
    # traceback over a directory nobody can trust anymore.
    staged = []
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                if name.endswith("/"):
                    # zipfile represents a directory entry as a member whose
                    # name ends in "/" - normally zero bytes, nothing to
                    # read or write. But a trailing "/" is just a naming
                    # convention, not a guarantee: a member could be named
                    # "report.csv/" and still carry real data (a
                    # mis-generated export, a hand-built zip, ...). Skip it
                    # ONLY if it is actually empty; otherwise it would be
                    # silently discarded with no warning, and its dest -
                    # os.path.join(out_dir, "") == out_dir itself - is not
                    # even a name anyone could write to. Check BEFORE
                    # staging anything, for this member or any other in the
                    # zip.
                    info = z.getinfo(name)
                    if info.file_size == 0:
                        continue
                    raise ValueError(
                        f"zip member {name!r} is named like a directory "
                        f"(ends in '/') but has {info.file_size} byte(s) of "
                        "data - refusing to silently discard it"
                    )
                dest = os.path.join(out_dir, os.path.basename(name))
                with z.open(name) as src:
                    data = src.read()
                staged.append(_stage_write(dest, data))

        written = []
        for i, (dest, tmp_path) in enumerate(staged):
            try:
                os.replace(tmp_path, dest)
            except OSError as e:
                not_committed = staged[i:]
                stale = [d for d, _ in not_committed]
                leftover_temps = [t for _, t in not_committed]
                raise OSError(
                    "export partially committed - out_dir is not all one "
                    f"version. {len(written)} file(s) already replaced with "
                    f"the new export: {written or '(none)'}. {len(stale)} "
                    f"file(s) left at their OLD version (or never created) "
                    f"because replacing {dest} failed ({e}): {stale}. "
                    f"Staged temp file(s) for those (cleanup will be "
                    f"attempted next): {leftover_temps}."
                ) from e
            written.append(dest)
            print(f"  wrote {dest} ({os.path.getsize(dest):,} bytes)", file=sys.stderr)
        return written
    finally:
        # Anything still present here is a temp file whose replace never
        # ran (staging failed partway, commit failed partway, or we raised
        # before the commit loop started) - clean it up. A successfully
        # replaced temp file is gone already, so FileNotFoundError there is
        # expected and not a problem.
        #
        # A genuine failure to remove a temp file (e.g. it's read-only or
        # locked on Windows) must not stop this loop - every OTHER staged
        # temp still needs its own cleanup attempt - and must never raise
        # from here: this `finally` can run while a real error (the commit
        # failure above, a corrupt member, anything) is already propagating,
        # and raising a new exception from a `finally` block REPLACES that
        # original exception in Python rather than adding to it. Report and
        # move on instead.
        for _dest, tmp_path in staged:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"  warning: could not remove temp file {tmp_path}: {e}", file=sys.stderr)


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
    except (GraphError, AuthError, OSError) as e:
        # OSError covers _download's own errors too (symlinked dest, a
        # commit-loop failure such as PermissionError from a Windows file
        # open in Excel) - those need the same clean "message and exit 1"
        # treatment as GraphError/AuthError, not a raw traceback.
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
