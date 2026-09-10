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

Colours and fonts come from the active brand pack (resolve_brand.py): the
single installed pack by default, `--brand neutral` for the unbranded palette.
The stylesheet still receives LITERAL hex -- the brand is substituted at build
time, never shipped as `var()`.

Third-party requirement: `pywin32`, and only for `--to-docx` / `--to-pdf`.
Emitting the HTML is stdlib.

Usage:
    build_report.py --data report.json --out reports/
    build_report.py --data report.json --out reports/ --to-docx --to-pdf
    build_report.py --data report.json --brand neutral
    build_report.py --example > report.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import uuid as _uuid
import html
import json
import os
import sys

import resolve_brand


class Palette:
    """The report colours of one brand pack, as attributes the stylesheet
    interpolates. Literal hex, never var(). See word-traps.md rule 1: `var()`
    does not degrade, it drops the whole declaration, so
    `background:var(--x); color:#fff` renders white on white."""

    def __init__(self, brand):
        r = brand.report
        self.navy = r["navy"]
        self.navy_dark = r["navy_dark"]
        self.accent = r["accent"]
        self.org_ink = r["org_ink"]
        self.classification = r["classification"]
        self.ink = r["ink"]
        self.muted = r["muted"]
        self.grid = r["grid"]
        self.zebra = r["zebra"]
        self.panel = r["panel"]
        self.rule = r["rule"]
        self.font_stack = brand.fonts["report_stack"]
        # (chip background, chip text) per severity. `unverified` is its own
        # severity on purpose: a check that could not run is not a check that
        # passed, and rendering the two alike is lying by omission.
        self.severities = {k: tuple(v) for k, v in r["severity"].items()}


def esc(value) -> str:
    """HTML-escape any cell value, including None and numbers."""
    return html.escape("" if value is None else str(value), quote=True)


def _chip_css(pal: Palette) -> str:
    """Severity chips.

    The shared declarations sit in a GROUPED SELECTOR, not in a base class the
    element also carries. `class="chip chip-high"` applies NEITHER rule in Word
    -- measured, both the shading and the font colour come back as
    wdColorAutomatic. Grouped selectors are fine; two classes on the element
    are not. See word-traps.md rule 4.
    """
    names = ", ".join(f".chip-{s}" for s in pal.severities)
    out = [
        f"{names} {{ display:inline-block; padding:2px 8px; font-weight:700; "
        "font-size:11px; white-space:nowrap; }"
    ]
    for sev, (bg, fg) in pal.severities.items():
        out.append(f".chip-{sev} {{ background:{bg}; color:{fg}; }}")
    return "\n".join(out)


def stylesheet(pal: Palette) -> str:
    NAVY, NAVY_DARK, ACCENT = pal.navy, pal.navy_dark, pal.accent
    ORG_INK, CLASSIFICATION, INK = pal.org_ink, pal.classification, pal.ink
    MUTED, GRID, ZEBRA, PANEL, RULE = pal.muted, pal.grid, pal.zebra, pal.panel, pal.rule
    return f"""
body {{ font-family:{pal.font_stack}; font-size:13px;
       color:{INK}; margin:0; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:18px 22px 40px; }}

h1 {{ font-size:20px; margin:18px 0 2px; color:{NAVY}; }}
h2 {{ font-size:15px; margin:22px 0 8px; padding-bottom:4px;
     border-bottom:1px solid {RULE}; color:{NAVY}; }}
p  {{ margin:6px 0; }}
.sub    {{ color:{MUTED}; font-size:12px; margin:0 0 10px; }}
.footer {{ color:{MUTED}; font-size:11px; margin-top:26px;
          border-top:1px solid {RULE}; padding-top:8px; }}

/* Masthead: tables with cell shading, never coloured divs. */
table.mast {{ border-collapse:collapse; width:100%; margin-bottom:14px; }}
.mast-strip {{ background:{ACCENT}; height:4px; line-height:4px; font-size:1px; }}
.mast-band  {{ background:{NAVY}; padding:14px 18px; }}
.mast-rule  {{ background:{NAVY_DARK}; height:3px; line-height:3px; font-size:1px; }}
.mast-cls   {{ background:{CLASSIFICATION}; color:#FFFFFF; padding:5px 18px;
              font-size:11px; font-weight:700; letter-spacing:1.6px; }}
.mast-org   {{ color:{ORG_INK}; font-size:11px; font-weight:600;
              letter-spacing:1.8px; }}
.mast-title {{ color:#FFFFFF; font-size:26px; font-weight:600; }}
.mast-subtitle {{ color:{ORG_INK}; font-size:12px; }}

/* Every table: real grid, real thead. Both required. */
table.data {{ border-collapse:collapse; width:100%; table-layout:fixed;
             margin:8px 0 4px; }}
table.data th, table.data td {{ border:1px solid {GRID}; padding:7px 10px;
             text-align:left; vertical-align:top; overflow-wrap:break-word; }}
table.data th {{ background:{NAVY}; color:#FFFFFF; font-weight:600; }}
/* Zebra is an explicit class, written per row by the builder. */
table.data tr.alt td {{ background:{ZEBRA}; }}

table.meta {{ border-collapse:collapse; width:100%; margin:0 0 14px; }}
table.meta td {{ border:1px solid {GRID}; padding:6px 10px; font-size:12px; }}
table.meta td.k {{ background:{ZEBRA}; font-weight:600; width:17%; }}

.lede {{ background:{PANEL}; border-left:4px solid {NAVY};
        padding:10px 14px; margin:10px 0 4px; }}
.handling {{ background:#FDE8E6; border-left:4px solid {CLASSIFICATION};
            padding:8px 14px; margin:10px 0; font-size:12px; color:#A01B12; }}

/* Cards are a table on purpose; the number and label are real block
   elements rather than styled spans. */
table.cards {{ border-collapse:separate; border-spacing:8px 0; width:100%;
              margin:6px 0 2px; }}
td.card {{ background:{PANEL}; border:1px solid {GRID}; padding:10px 12px;
          text-align:center; }}
div.n {{ font-size:22px; font-weight:700; color:{NAVY}; }}
div.l {{ font-size:11px; color:{MUTED}; }}

{_chip_css(pal)}

@media print {{
  body {{ font-size:11pt; }}
  .wrap {{ padding:0; max-width:none; }}
  h2 {{ page-break-after:avoid; }}
  tr {{ page-break-inside:avoid; }}
  thead {{ display:table-header-group; }}
}}
"""


def column_widths(labels, rows):
    """Percent widths weighted by what each column actually renders.

    Sums to exactly 100 for any table with 100 columns or fewer, which is every
    real one. Past that the guarantee is impossible rather than merely hard --
    each column has a 1% floor because a 0% column is invisible, so 102 columns
    need 102%. The floor wins: a table that wide is already unreadable, and a
    zero-width column would hide data rather than merely crowd it. Stated here
    because an earlier docstring promised "exactly 100" unconditionally and the
    code quietly returned a NEGATIVE width instead.

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
    # Every column gets at least 1%: with many equal columns the rounding drift
    # is larger than a single share, and dumping it all on the widest produced a
    # NEGATIVE width (102 equal columns -> one -1%). Clamp first, then settle any
    # remaining drift one point at a time across the widest columns, so no single
    # column can be driven below the floor.
    pcts = [max(1, p) for p in pcts]
    drift = 100 - sum(pcts)
    order = sorted(range(len(pcts)), key=lambda i: pcts[i], reverse=True)
    step = 1 if drift > 0 else -1
    idx = 0
    while drift != 0 and order:
        i = order[idx % len(order)]
        if step < 0 and pcts[i] <= 1:
            if all(p <= 1 for p in pcts):
                break  # cannot shrink further without going below the floor
        else:
            pcts[i] += step
            drift -= step
        idx += 1
    return pcts


def masthead(org, title, subtitle, classification):
    return (
        '<table class="mast">\n'
        '  <tr><td class="mast-strip"></td></tr>\n'
        '  <tr><td class="mast-band">\n'
        f'    <div class="mast-org">{esc(org)}</div>\n'
        f'    <div class="mast-title">{esc(title)}</div>\n'
        f'    <div class="mast-subtitle">{esc(subtitle)}</div>\n'
        '  </td></tr>\n'
        '  <tr><td class="mast-rule"></td></tr>\n'
        f'  <tr><td class="mast-cls">{esc(classification)}</td></tr>\n'
        '</table>\n'
    )


def meta_table(meta):
    """Label/value pairs, two per row."""
    items = list(meta.items())
    out = ['<table class="meta">']
    for i in range(0, len(items), 2):
        out.append("  <tr>")
        for k, v in items[i:i + 2]:
            out.append(f'    <td class="k">{esc(k)}</td><td>{esc(v)}</td>')
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
        f'<td class="card"><div class="n">{esc(c.get("value"))}</div>'
        f'<div class="l">{esc(c.get("label"))}</div></td>'
        for c in items
    )
    return f'<table class="cards"><tr>{tds}</tr></table>\n'


def data_table(labels, rows, chip_column=None, severities=None):
    """A grid, a thead, and `class="alt"` written per row.

    `chip_column` is the index whose value is rendered as a severity chip. The
    chip always carries its WORD as well as its colour: a red cell means nothing
    to a reader with colour-vision deficiency and nothing at all on a mono
    office printer, which is where these documents end up.
    """
    severities = severities or {}
    pcts = column_widths(labels, rows)
    out = ['<table class="data">', "  <colgroup>"]
    out += [f'    <col style="width:{p}%">' for p in pcts]
    out += ["  </colgroup>", "  <thead><tr>"]
    out += [f"    <th>{esc(x)}</th>" for x in labels]
    out += ["  </tr></thead>", "  <tbody>"]
    for i, row in enumerate(rows):
        cls = ' class="alt"' if i % 2 else ""
        cells = []
        for j in range(len(labels)):
            val = row[j] if j < len(row) else ""
            if chip_column is not None and j == chip_column:
                sev = str(val).strip().lower()
                if sev in severities:
                    cells.append(
                        f'<td><span class="chip-{sev}">{esc(str(val).upper())}</span></td>'
                    )
                    continue
            cells.append(f"<td>{esc(val)}</td>")
        joined = "".join(cells)
        out.append(f"    <tr{cls}>{joined}</tr>")
    out += ["  </tbody>", "</table>"]
    return "\n".join(out) + "\n"


def build(doc, brand):
    pal = Palette(brand)
    # The organisation is the SUBJECT of the report - the tenant or domain that
    # was assessed - and comes from the data, so the report identifies its own
    # subject. The brand pack's organisation is only a fallback for documents
    # that have no assessed subject (an internal write-up, a memo).
    org = doc.get("organisation") or brand.organisation
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
        f"<title>{esc(title)}</title>",
        f"<style>{stylesheet(pal)}</style>",
        "</head><body>",
        '<div class="wrap">',
        masthead(org, title, doc.get("subtitle", ""),
                 doc.get("classification", "INTERNAL USE ONLY")),
    ]
    if doc.get("meta"):
        parts.append(meta_table(doc["meta"]))
    if doc.get("lede"):
        parts.append(f'<div class="lede"><p>{esc(doc["lede"])}</p></div>')
    if doc.get("handling"):
        parts.append(f'<div class="handling">{esc(doc["handling"])}</div>')
    if doc.get("cards"):
        parts.append("<h2>Summary</h2>")
        parts.append(cards(doc["cards"]))
    if rows:
        heading = esc(findings.get("heading", "Findings"))
        parts.append(f"<h2>{heading}</h2>")
        parts.append(data_table(labels, rows, chip_col, pal.severities))
    if doc.get("collected_at"):
        # A re-render must say it is one. A restyled report carrying today's
        # date over month-old findings is worse than the ugly one it replaced.
        collected = esc(doc["collected_at"])
        parts.append(
            f'<p class="sub">Findings collected {collected}. This document was '
            "rendered later from stored state and was not re-collected.</p>"
        )
    parts.append(f'<div class="footer">{esc(doc.get("footer", ""))}</div>')
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
    """Convert through Word COM. Windows with Word installed only.

    Opens whatever Word can open - the HTML this script emits, or a .docx from
    build_sop.py, which imports this function for its own --to-pdf step so the
    process-hygiene rules below live in exactly one place."""
    # ONE import, bound to the name actually used. An earlier version imported
    # `win32com.client` as an availability probe and then imported it again as
    # `win32`, which made the first genuinely unused -- pylint W0611 on a line
    # whose only job was to fail.
    try:
        import win32com.client as win32  # pylint: disable=import-outside-toplevel
    except ImportError:
        print("pywin32 is not installed - cannot convert. The source file was still "
              "written. Run preflight.py to install it under your profile.", file=sys.stderr)
        return 1

    # A viewer holding the target PDF (or Word holding the target DOCX) makes
    # SaveAs2 fail "read-only" from inside COM, after Word has already started.
    # Check first and name the file, so the operator knows what to close.
    from preflight import locked  # pylint: disable=import-outside-toplevel
    base = os.path.splitext(os.path.abspath(html_path))[0]
    for target in ([base + ".docx"] if want_docx else []) + ([base + ".pdf"] if want_pdf else []):
        why = locked(target)
        if why:
            print("cannot convert: %s. Close %s and run again."
                  % (why, os.path.basename(target)), file=sys.stderr)
            return 1

    # The try must open IMMEDIATELY after Dispatch, and doc must be tracked from
    # None. An earlier version set Visible/DisplayAlerts and computed `base`
    # outside any handler, so a failure in that window left a headless WINWORD
    # process running with no window to close it from -- and one that opened a
    # document before failing left it open too. On a machine that generates
    # reports on a schedule those accumulate until Word refuses to start.
    word = win32.Dispatch("Word.Application")
    doc = None
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        base = os.path.splitext(os.path.abspath(html_path))[0]
        doc = word.Documents.Open(os.path.abspath(html_path), False, True)
        if want_docx:
            doc.SaveAs2(base + ".docx", 16)   # wdFormatDocumentDefault
            print(f"wrote {base}.docx")
        if want_pdf:
            doc.SaveAs2(base + ".pdf", 17)    # wdFormatPDF
            print(f"wrote {base}.pdf")
    finally:
        # Both closes are individually guarded: if Close raises, Quit must still
        # run, or the failure that broke the save also leaks the process.
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:  # pylint: disable=broad-except
                pass
        try:
            word.Quit()
        except Exception:  # pylint: disable=broad-except
            pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="JSON report document")
    ap.add_argument("--out", default=None,
                    help="output directory (default: the brand pack's report "
                         "directory, normally reports/, which should be "
                         "gitignored - these documents read as an attack plan)")
    resolve_brand.add_brand_argument(ap)
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

    brand = resolve_brand.resolve(args.brand)
    out_dir = args.out or brand.report_output_dir

    # Compute the whole document BEFORE opening the output file. `open(p,"w")`
    # truncates at open time, so a write whose argument expression raises leaves
    # a zero-byte file where the original was.
    text = build(doc, brand)

    # Seconds, not minutes, plus a short random tail. Minute precision let two
    # runs of the same report inside one minute overwrite each other - and the
    # converted .docx/.pdf too, since they derive from this basename.
    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + _uuid.uuid4().hex[:4]
    base = args.name or "".join(
        c if c.isalnum() else "-" for c in doc.get("title", "Report")
    ).strip("-")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{base}-{stamp}.html")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {path}")

    if args.to_docx or args.to_pdf:
        return to_word(path, args.to_docx, args.to_pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
