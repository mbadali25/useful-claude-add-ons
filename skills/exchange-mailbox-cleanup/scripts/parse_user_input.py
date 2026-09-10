#!/usr/bin/env python3
"""Normalise operator input for the Exchange mailbox skills - one address or a CSV.

Standard library only. Windows and Linux. Never touches the tenant.

Accepts either a single email address / UPN or the path to a CSV or text file, and
writes the one-column CSV (header ``UserPrincipalName``) that
``Invoke-M365OffboardingHold.ps1 -UserList`` and ``Import-Csv`` in Windows PowerShell 5.1
both read correctly. Output is UTF-8 **with a BOM** (``utf-8-sig``): 5.1's ``Import-Csv``
assumes the ANSI code page when there is no BOM and turns every accented name into
mojibake.

Input CSVs are read as ``utf-8-sig`` too, and the address column is auto-detected
(UserPrincipalName, EmailAddress, Email, PrimarySmtpAddress, mail, upn ...). Bad rows are
reported with their line number and reason rather than dropped silently - a curated
leaver list that quietly lost a row is worse than one that refused to parse.

Usage:
    parse_user_input.py j.doe@contoso.com --out C:\\scripts\\reports\\holdlist.csv
    parse_user_input.py C:\\temp\\leavers.csv --out C:\\scripts\\reports\\holdlist.csv
    parse_user_input.py C:\\temp\\hr-export.csv --email-column "Work Email" --json
    parse_user_input.py C:\\temp\\leavers.txt          # one address per line, no header

Exit codes:
    0  every row valid; output written if --out given
    1  no valid addresses at all
    2  bad input: file missing, unreadable, no header, or no address column found
    3  valid rows written but at least one row rejected - show the operator the rejected
       rows and ask before proceeding with the subset
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

CANDIDATE_COLUMNS = (
    "UserPrincipalName", "userPrincipalName", "user_principal_name", "upn", "UPN",
    "EmailAddress", "Email", "email", "mail", "Mail", "PrimarySmtpAddress",
    "primary_email", "Work Email", "WorkEmail",
)

# Deliberately loose: one @, no whitespace, a dotted domain. Exchange validates the rest.
ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def die(msg: str, code: int) -> int:
    print(f"ERROR  {msg}", file=sys.stderr)
    return code


def validate(raw: str) -> tuple[str | None, str | None]:
    """Return (normalised_address, None) or (None, reason)."""
    v = (raw or "").strip().strip('"').strip("'")
    if not v:
        return None, "empty"
    if v.count("@") != 1:
        return None, f"expected exactly one '@', got {v.count('@')}"
    if any(ch.isspace() for ch in v):
        return None, "contains whitespace"
    if not ADDRESS_RE.match(v):
        return None, "not shaped like user@domain.tld"
    return v.lower(), None


def detect_column(fieldnames: list[str], explicit: str | None) -> str | None:
    if explicit:
        match = next((f for f in fieldnames if f.strip().lower() == explicit.strip().lower()), None)
        return match
    for cand in CANDIDATE_COLUMNS:
        match = next((f for f in fieldnames if f.strip().lower() == cand.lower()), None)
        if match:
            return match
    # Last resort: any column whose values look like addresses is handled by the caller.
    return None


def read_file(path: Path, explicit_column: str | None):
    """Yield (line_no, raw_value) pairs plus the column used, or raise ValueError."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delimited = ("," in sample) or ("\t" in sample) or (";" in sample)
        if not delimited:
            # One column: either a bare list of addresses, or a one-column CSV whose only
            # line without an '@' is a recognised header. Skip that header rather than
            # reporting the file's own column name as a bad row.
            rows = [(i + 1, line) for i, line in enumerate(fh) if line.strip()]
            if rows:
                first = rows[0][1].strip().strip('"')
                if "@" not in first and first.lower() in {c.lower() for c in CANDIDATE_COLUMNS}:
                    return rows[1:], first
            return rows, "(one address per line)"

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")
        fieldnames = [f for f in reader.fieldnames if f is not None]
        col = detect_column(fieldnames, explicit_column)
        if col is None:
            if explicit_column:
                raise ValueError(
                    f"column '{explicit_column}' not in {path}. Columns present: {', '.join(fieldnames)}")
            raise ValueError(
                f"could not find an address column in {path}. Columns present: "
                f"{', '.join(fieldnames)}. Specify one with --email-column.")
        # DictReader consumed the header as line 1; data starts at line 2.
        rows = [(i + 2, (row.get(col) or "")) for i, row in enumerate(reader)]
        return rows, col


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("value", help="a single address/UPN, or the path to a CSV or text file")
    ap.add_argument("--email-column", help="CSV column holding the address (auto-detected if omitted)")
    ap.add_argument("--out", help="write the normalised one-column CSV here (UTF-8 with BOM)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON on stdout")
    args = ap.parse_args()

    value = args.value.strip()
    candidate = Path(value)
    is_path = candidate.exists() and candidate.is_file()

    rows: list[tuple[int, str]]
    source: str
    column: str | None = None

    if is_path:
        try:
            rows, column = read_file(candidate, args.email_column)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            return die(str(exc), 2)
        source = str(candidate.resolve())
    elif "@" in value:
        rows = [(1, value)]
        source = "(single address)"
    else:
        return die(f"'{value}' is neither an existing file nor an email address", 2)

    valid: list[str] = []
    seen: set[str] = set()
    rejected: list[dict] = []
    duplicates: list[dict] = []
    for line_no, raw in rows:
        addr, reason = validate(raw)
        if addr is None:
            rejected.append({"line": line_no, "value": (raw or "").strip(), "reason": reason})
            continue
        if addr in seen:
            duplicates.append({"line": line_no, "value": addr})
            continue
        seen.add(addr)
        valid.append(addr)

    out_path = None
    if valid and args.out:
        out_path = Path(args.out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, lineterminator="\r\n")
                w.writerow(["UserPrincipalName"])
                for a in valid:
                    w.writerow([a])
        except OSError as exc:
            return die(f"could not write {out_path}: {exc}", 2)

    summary = {
        "source": source,
        "column": column,
        "count": len(valid),
        "addresses": valid,
        "rejected": rejected,
        "duplicates_dropped": duplicates,
        "out": str(out_path.resolve()) if out_path else None,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Source:    {source}")
        if column:
            print(f"Column:    {column}")
        print(f"Valid:     {len(valid)}")
        for a in valid:
            print(f"  {a}")
        if duplicates:
            print(f"Duplicates dropped: {len(duplicates)}")
            for d in duplicates:
                print(f"  line {d['line']}: {d['value']}")
        if rejected:
            print(f"Rejected:  {len(rejected)}")
            for r in rejected:
                print(f"  line {r['line']}: '{r['value']}' - {r['reason']}")
        if out_path:
            print(f"Written:   {out_path}")

    if not valid:
        print("ERROR  no valid addresses", file=sys.stderr)
        return 1
    if rejected:
        print(f"WARNING  {len(rejected)} row(s) rejected - confirm with the operator before proceeding",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
