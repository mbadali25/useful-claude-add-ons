#!/usr/bin/env python3
"""Emit a report as HTML that survives Word's HTML parser, and optionally
convert it to .docx / .pdf through Word COM on Windows.

The stylesheet this writes is deliberately repetitive and deliberately old
fashioned: no custom properties, no `:nth-child`, no flex, no element carrying
two class names. Every one of those is correct CSS that Word drops SILENTLY,
turning a styled report into flat black-on-white text with no error anywhere.
`references/word-traps.md` records what was measured against the Word object
model; read it before changing any selector here.

Input is a JSON document (see `--example`) so a report that talked to a live
system can be re-rendered later without contacting it again -- which is what
makes a restyle possible on an estate whose credentials nobody has today.

Usage:
    build_report.py --data report.json --out reports/
    build_report.py --data report.json --out reports/ --to-docx --to-pdf
    build_report.py --example > report.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import os
import sys

# Literal hex, never var(). See word-traps.md rule 1: `var()` does not degrade,
# it drops the whole declaration, so `background:var(--x); color:#fff` renders
# white on white.
NAVY = "#1F4E79"
NAVY_DARK = "#143A5A"
ACCENT = "#4A90C2"
ORG_INK = "#A8C8E4"
CLASSIFICATION = "#8B1A13"
INK = "#1B1B1F"
MUTED = "#5C5F6B"
GRID = "#B8BCC6"
ZEBRA = "#EEF3F8"
PANEL = "#F6F7F9"
RULE = "#DCDEE5"

SEVERITIES = {
    "critical": ("#FDE8E6", "#A01B12"),
    "high": ("#FFEDD5", "#9A3412"),
    "medium": ("#FDF3D7", "#8A6100"),
    "low": ("#E3F4EA", "#1C6B3F"),
    "info": ("#E8EFF8", "#2F4B7C"),
    # Its own severity on purpose. A check that could not run is not a check
    # that passed, and rendering the two alike is lying by omission.
    "unverified": ("#EDEEF1", "#5C5F6B"),
}


def esc(value) -> str:
    """HTML-escape any cell value, including None and numbers."""
    return html.escape("" if value is None else str(value), quote=True)


def _chip_css() -> str:
    """Severity chips.

    The shared declarations sit in a GROUPED SELECTOR, not in a base class the
    element also carries. `class="chip chip-high"` applies NEITHER rule in Word
    -- measured, both the shading and the font colour come back as
    wdColorAutomatic. Grouped selectors are fine; two classes on the element
    are not. See word-traps.md rule 4.
    """
    names = ", ".join(".chip-%s" % s for s in SEVERITIES)
    out = [
        "%s { display:inline-block; padding:2px 8px; font-weight:700; "
        "font-size:11px; white-space:nowrap; }" % names
    ]
    for sev, (bg, fg) in SEVERITIES.items():
        out.append(".chip-%s { background:%s; color:%s; }" % (sev, bg, fg))
    return "\n".join(out)


def stylesheet() -> str:
    return """
body { font-family:'Segoe UI',Calibri,Arial,sans-serif; font-size:13px;
       color:%(ink)s; margin:0; }
.wrap { max-width:1000px; margin:0 auto; padding:18px 22px 40px; }

h1 { font-size:20px; margin:18px 0 2px; color:%(navy)s; }
h2 { font-size:15px; margin:22px 0 8px; padding-bottom:4px;
     border-bottom:1px solid %(rule)s; color:%(navy)s; }
p  { margin:6px 0; }
.sub    { color:%(muted)s; font-size:12px; margin:0 0 10px; }
.footer { color:%(muted)s; font-size:11px; margin-top:26px;
          border-top:1px solid %(rule)s; padding-top:8px; }

/* Masthead: tables with cell shading, never coloured divs. */
table.mast { border-collapse:collapse; width:100%%; margin-bottom:14px; }
.mast-strip { background:%(accent)s; height:4px; line-height:4px; font-size:1px; }
.mast-band  { background:%(navy)s; padding:14px 18px; }
.mast-rule  { background:%(navydark)s; height:3px; line-height:3px; font-size:1px; }
.mast-cls   { background:%(cls)s; color:#FFFFFF; padding:5px 18px;
              font-size:11px; font-weight:700; letter-spacing:1.6px; }
.mast-org   { color:%(orgink)s; font-size:11px; font-weight:600;
              letter-spacing:1.8px; }
.mast-title { color:#FFFFFF; font-size:26px; font-weight:600; }
.mast-subtitle { color:%(orgink)s; font-size:12px; }

/* Every table: real grid, real thead. Both required. */
table.data { border-collapse:collapse; width:100%%; table-layout:fixed;
             margin:8px 0 4px; }
table.data th, table.data td { border:1px solid %(grid)s; padding:7px 10px;
             text-align:left; vertical-align:top; overflow-wrap:break-word; }
table.data th { background:%(navy)s; color:#FFFFFF; font-weight:600; }
/* Zebra is an explicit class, written per row by the builder. */
table.data tr.alt td { background:%(zebra)s; }

table.meta { border-collapse:collapse; width:100%%; margin:0 0 14px; }
table.meta td { border:1px solid %(grid)s; padding:6px 10px; font-size:12px; }
table.meta td.k { background:%(zebra)s; font-weight:600; width:17%%; }

.lede { background:%(panel)s; border-left:4px solid %(navy)s;
        padding:10px 14px; margin:10px 0 4px; }
.handling { background:#FDE8E6; border-left:4px solid %(cls)s;
            padding:8px 14px; margin:10px 0; font-size:12px; color:#A01B12; }

/* Cards are a table on purpose; the number and label are real block
   elements rather than styled spans. */
table.cards { border-collapse:separate; border-spacing:8px 0; width:100%%;
              margin:6px 0 2px; }
td.card { background:%(panel)s; border:1px solid %(grid)s; padding:10px 12px;
          text-align:center; }
div.n { font-size:22px; font-weight:700; color:%(navy)s; }
div.l { font-size:11px; color:%(muted)s; }

%(chips)s

@media print {
  body { font-size:11pt; }
  .wrap { padding:0; max-width:none; }
  h2 { page-break-after:avoid; }
  tr { page-break-inside:avoid; }
  thead { display:table-header-group; }
}
""" % {
        "ink": INK, "navy": NAVY, "navydark": NAVY_DARK, "accent": ACCENT,
        "cls": CLASSIFICATION, "orgink": ORG_INK, "muted": MUTED,
        "grid": GRID, "zebra": ZEBRA, "panel": PANEL, "rule": RULE,
        "chips": _chip_css(),
    }


def column_widths(labels, rows):
    """Percent widths summing to exactly 100, weighted by rendered length.

    Deriving widths from column NAMES does not work and was tried in both
    directions: a numeric column headed `Passwords` came out at 6% and collided
    with its neighbour, and account names keyed `Account` came out at 14% and
    ran off the page. Measure what each column actually has to render.
    """
    if not labels:
        return []
    weights = []
    for i, label in enumerate(labels):
        longest = len(str(label))
        for row in rows:
            cell = row[i] if i < len(row) else ""
            longest = max(longest, len(str(cell)))
        # Long prose compresses; damp the top end so one wide column cannot
        # starve the rest of the table.
        if longest > 40:
            longest = 40 + int((longest - 40) ** 0.5) * 4
        # A chip has padding and never wraps, so it needs more than its text.
        if str(label).strip().lower() in ("status", "priority", "severity", "verdict"):
            longest += 5
        weights.append(max(longest, 4))
    total = float(sum(weights))
    pcts = [int(round(w * 100.0 / total)) for w in weights]
    # Push rounding drift into the widest column: a row totalling 101 pushes the
    # table past the margin.
    drift = 100 - sum(pcts)
    if drift:
        pcts[pcts.index(max(pcts))] += drift
    return pcts


def masthead(org, title, subtitle, classification):
    return (
        '<table class="mast">\n'
        '  <tr><td class="mast-strip"></td></tr>\n'
        '  <tr><td class="mast-band">\n'
        '    <div class="mast-org">%s</div>\n'
        '    <div class="mast-title">%s</div>\n'
        '    <div class="mast-subtitle">%s</div>\n'
        '  </td></tr>\n'
        '  <tr><td class="mast-rule"></td></tr>\n'
        '  <tr><td class="mast-cls">%s</td></tr>\n'
        '</table>\n'
        % (esc(org), esc(title), esc(subtitle), esc(classification))
    )


def meta_table(meta):
    """Label/value pairs, two per row."""
    items = list(meta.items())
    out = ['<table class="meta">']
    for i in range(0, len(items), 2):
        out.append("  <tr>")
        for k, v in items[i:i + 2]:
            out.append('    <td class="k">%s</td><td>%s</td>' % (esc(k), esc(v)))
        if len(items[i:i + 2]) == 1:
            out.append('    <td class="k"></td><td></td>')
        out.append("  </tr>")
    out.append("</table>")
    return "\n".join(out) + "\n"


def cards(items):
    """At most five. More than five and none of them register."""
    items = items[:5]
    if not items:
        return ""
    tds = "".join(
        '<td class="card"><div class="n">%s</div><div class="l">%s</div></td>'
        % (esc(c.get("value")), esc(c.get("label")))
        for c in items
    )
    return '<table class="cards"><tr>%s</tr></table>\n' % tds


def data_table(labels, rows, chip_column=None):
    """A grid, a thead, and `class="alt"` written per row.

    `chip_column` is the index whose value is rendered as a severity chip. The
    chip always carries its WORD as well as its colour: a red cell means nothing
    to a reader with colour-vision deficiency and nothing at all on a mono
    office printer, which is where these documents end up.
    """
    pcts = column_widths(labels, rows)
    out = ['<table class="data">', "  <colgroup>"]
    out += ['    <col style="width:%d%%">' % p for p in pcts]
    out += ["  </colgroup>", "  <thead><tr>"]
    out += ["    <th>%s</th>" % esc(x) for x in labels]
    out += ["  </tr></thead>", "  <tbody>"]
    for i, row in enumerate(rows):
        cls = ' class="alt"' if i % 2 else ""
        cells = []
        for j, label in enumerate(labels):
            val = row[j] if j < len(row) else ""
            if chip_column is not None and j == chip_column:
                sev = str(val).strip().lower()
                if sev in SEVERITIES:
                    cells.append(
                        '<td><span class="chip-%s">%s</span></td>'
                        % (sev, esc(str(val).upper()))
                    )
                    continue
            cells.append("<td>%s</td>" % esc(val))
        out.append("    <tr%s>%s</tr>" % (cls, "".join(cells)))
    out += ["  </tbody>", "</table>"]
    return "\n".join(out) + "\n"


def build(doc):
    org = doc.get("organisation", "")
    title = doc.get("title", "Report")
    findings = doc.get("findings") or {}
    labels = findings.get("columns") or []
    rows = findings.get("rows") or []

    chip_col = None
    for i, label in enumerate(labels):
        if str(label).strip().lower() in ("severity", "status", "priority", "verdict"):
            chip_col = i
            break

    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<title>%s</title>" % esc(title),
        "<style>%s</style>" % stylesheet(),
        "</head><body>",
        '<div class="wrap">',
        masthead(org, title, doc.get("subtitle", ""),
                 doc.get("classification", "INTERNAL USE ONLY")),
    ]
    if doc.get("meta"):
        parts.append(meta_table(doc["meta"]))
    if doc.get("lede"):
        parts.append('<div class="lede"><p>%s</p></div>' % esc(doc["lede"]))
    if doc.get("handling"):
        parts.append('<div class="handling">%s</div>' % esc(doc["handling"]))
    if doc.get("cards"):
        parts.append("<h2>Summary</h2>")
        parts.append(cards(doc["cards"]))
    if rows:
        parts.append("<h2>%s</h2>" % esc(findings.get("heading", "Findings")))
        parts.append(data_table(labels, rows, chip_col))
    if doc.get("collected_at"):
        # A re-render must say it is one. A restyled report carrying today's
        # date over month-old findings is worse than the ugly one it replaced.
        parts.append(
            '<p class="sub">Findings collected %s. This document was rendered '
            "later from stored state and was not re-collected.</p>"
            % esc(doc["collected_at"])
        )
    parts.append('<div class="footer">%s</div>' % esc(doc.get("footer", "")))
    parts += ["</div>", "</body></html>"]
    return "\n".join(parts)


EXAMPLE = {
    "organisation": "CONTOSO",
    "title": "Entra Password Posture",
    "subtitle": "Tenant-wide assessment of password strength and policy",
    "classification": "CONFIDENTIAL - HANDLE AS RESTRICTED",
    "meta": {
        "Report": "EntraPasswordPosture",
        "Generated": "2026-09-09 01:15 UTC",
        "Scope": "All enabled cloud accounts",
        "Run by": "svc-reporting",
        "Accounts assessed": "4,182",
        "Findings": "6",
    },
    "lede": "218 enabled accounts have passwords under 14 characters, and 5 of "
            "them hold privileged roles. Nothing else in this report is more "
            "urgent than those 5.",
    "handling": "This document names accounts with weak credentials. It is a "
                "target list if it leaves the organisation.",
    "cards": [
        {"value": "218", "label": "Under 14 characters"},
        {"value": "5", "label": "Privileged and weak"},
        {"value": "41", "label": "No MFA registered"},
        {"value": "0", "label": "Blocked by banned list"},
    ],
    "findings": {
        "heading": "Findings",
        "columns": ["ID", "Finding", "Severity", "Count"],
        "rows": [
            ["EPP-001", "Privileged accounts with passwords under 14 characters",
             "critical", 5],
            ["EPP-002", "Enabled accounts with passwords under 14 characters",
             "high", 218],
            ["EPP-003", "Accounts with no MFA method registered", "high", 41],
            ["EPP-004", "Custom banned-password list not configured", "medium", 1],
            ["EPP-005", "Password writeback health could not be queried",
             "unverified", 1],
            ["EPP-006", "Smart lockout thresholds at Microsoft defaults",
             "info", 1],
        ],
    },
    "footer": "Get-EntraPasswordPostureReport.ps1 v2.4 | host: RPT01 | "
              "account: svc-reporting | 2026-09-09T01:15:22Z",
}


def to_word(html_path, want_docx, want_pdf):
    """Convert through Word COM. Windows with Word installed only."""
    try:
        import win32com.client  # noqa: F401  pylint: disable=import-outside-toplevel
    except ImportError:
        print("pywin32 is not installed - cannot convert. "
              "The HTML was still written.", file=sys.stderr)
        return 1
    import win32com.client as win32  # pylint: disable=import-outside-toplevel

    word = win32.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(os.path.abspath(html_path), False, True)
        base = os.path.splitext(os.path.abspath(html_path))[0]
        try:
            if want_docx:
                doc.SaveAs2(base + ".docx", 16)   # wdFormatDocumentDefault
                print("wrote %s.docx" % base)
            if want_pdf:
                doc.SaveAs2(base + ".pdf", 17)    # wdFormatPDF
                print("wrote %s.pdf" % base)
        finally:
            doc.Close(False)
    finally:
        word.Quit()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="JSON report document")
    ap.add_argument("--out", default="reports",
                    help="output directory (default: reports/, which should be "
                         "gitignored - these documents read as an attack plan)")
    ap.add_argument("--name", help="basename; default is the title, slugified")
    ap.add_argument("--to-docx", action="store_true")
    ap.add_argument("--to-pdf", action="store_true")
    ap.add_argument("--example", action="store_true",
                    help="print an example JSON document and exit")
    args = ap.parse_args(argv)

    if args.example:
        print(json.dumps(EXAMPLE, indent=2))
        return 0
    if not args.data:
        ap.error("--data is required (or use --example)")

    with open(args.data, encoding="utf-8") as fh:
        doc = json.load(fh)

    # Compute the whole document BEFORE opening the output file. `open(p,"w")`
    # truncates at open time, so a write whose argument expression raises leaves
    # a zero-byte file where the original was.
    text = build(doc)

    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M")
    base = args.name or "".join(
        c if c.isalnum() else "-" for c in doc.get("title", "Report")
    ).strip("-")
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "%s-%s.html" % (base, stamp))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote %s" % path)

    if args.to_docx or args.to_pdf:
        return to_word(path, args.to_docx, args.to_pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
