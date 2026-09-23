#!/usr/bin/env python3
"""Emit a report as HTML that survives Word's HTML parser, and optionally
convert it to .docx / .pdf through Microsoft Word (COM, Windows) or LibreOffice.

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

Two renderers, never one silently standing in for the other. Word over COM is
the reference -- every rule in `references/word-traps.md` was measured against
it -- and LibreOffice (`soffice --headless`) is the only renderer that exists on
Linux and macOS, at reduced and measured fidelity. The engine is chosen by
`--renderer` or by an explicit platform branch, is printed to stderr with its
reason before any conversion, and is NAMED on the line announcing every file it
wrote. See render_engine.py.

Third-party requirement: `pywin32`, and only for `--renderer word`. Emitting the
HTML is stdlib, and the LibreOffice path needs no Python package at all.

Usage:
    build_report.py --data report.json --out reports/
    build_report.py --data report.json --out reports/ --to-docx --to-pdf
    build_report.py --data report.json --to-pdf --renderer libreoffice
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
import re
import shutil
import sys

import house_style
import render_engine
import resolve_brand

# The stylesheet and the palette it interpolates live in house_style.py, so
# that a hand-authored page can ask for the SAME defaults instead of copying
# a hex literal out of this file. Re-exported under their old names because
# they are this module's public surface and the suite asserts on both.
Palette = house_style.Palette
title_case = house_style.title_case


def stylesheet(pal):
    """The report profile of the house stylesheet. One call, never a copy:
    a second copy here is exactly the fork the shared module exists to
    prevent, and the suite asserts this equals house_style's own output."""
    return house_style.stylesheet(pal, "report")


def esc(value) -> str:
    """HTML-escape any cell value, including None and numbers."""
    return html.escape("" if value is None else str(value), quote=True)


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


def masthead(org, title, subtitle, classification, logo_src=None):
    """`logo_src`, when given, is the `-on-dark` wordmark - `.mast-band` is
    filled navy, so anything else placed there is the wrong variant.

    With a logo the band row has TWO sibling cells, logo left and heading text
    right, and the strip, rule and classification rows span both. Siblings,
    not a table nested inside the band cell: LibreOffice's HTML import moved a
    nested table's content up into the accent-strip row, so the band rendered
    in the accent colour and the logo vanished (measured, soffice 26.2.5.2).
    Word drops float and flex, so a table row is the only layout both apply.
    None renders the masthead exactly as it did before a pack carried a logo."""
    text = (f'    <div class="mast-org">{esc(org)}</div>\n'
            f'    <div class="mast-title">{esc(title)}</div>\n'
            f'    <div class="mast-subtitle">{esc(subtitle)}</div>\n')
    span = ' colspan="2"' if logo_src else ""
    logo_cell = (f'  <td class="mast-logo-cell"><img class="mast-logo" src="{esc(logo_src)}" '
                 f'alt="{esc(org)}"></td>\n' if logo_src else "")
    return (
        '<table class="mast">\n'
        f'  <tr><td class="mast-strip"{span}></td></tr>\n'
        '  <tr>\n'
        f'{logo_cell}'
        '  <td class="mast-band">\n'
        f'{text}'
        '  </td></tr>\n'
        f'  <tr><td class="mast-rule"{span}></td></tr>\n'
        f'  <tr><td class="mast-cls"{span}>{esc(classification)}</td></tr>\n'
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
    # Headings are cased HERE, mechanically, not by whoever typed the JSON.
    # `house_style.title_case` preserves anything already carrying its own
    # capitalisation - PowerShell, SOP, macOS, 0.19.93 - which `str.title()`
    # would destroy. See its docstring.
    title = house_style.title_case(doc.get("title", "Report"))
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
                 doc.get("classification", "INTERNAL USE ONLY"), pal.logo_src),
    ]
    if doc.get("meta"):
        parts.append(meta_table(doc["meta"]))
    if doc.get("lede"):
        parts.append(f'<div class="lede"><p>{esc(doc["lede"])}</p></div>')
    if doc.get("handling"):
        parts.append(f'<div class="handling">{esc(doc["handling"])}</div>')
    if doc.get("cards"):
        parts.append(f"<h2>{esc(house_style.title_case('Summary'))}</h2>")
        parts.append(cards(doc["cards"]))
    if rows:
        heading = esc(house_style.title_case(findings.get("heading", "Findings")))
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
    return house_style.mark_page("\n".join(parts), pal)


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


def convert(src, want_docx=False, want_pdf=False, renderer=None):
    """Convert `src` with a DELIBERATELY chosen engine. Returns an exit code.

    This is the only entry point either pipeline should call. It exists so that
    the choice of engine is made once, announced once, and can never happen by
    accident: if the chosen engine cannot run, this stops and names the flag
    that selects the other one. It does NOT try the other one. A substitution
    the operator did not ask for is the failure this skill spent its whole life
    refusing, and labelling is what makes the substitution acceptable at all.
    """
    engine, why = render_engine.choose_engine(renderer)
    print(f"renderer : {engine} -- {why}", file=sys.stderr)
    if engine == render_engine.LIBREOFFICE:
        rc = render_engine.to_soffice(src, want_docx=want_docx, want_pdf=want_pdf)
        bgr = page_colour(src) if src.lower().endswith((".html", ".htm")) else None
        if rc == 0 and want_docx and bgr is not None:
            # LibreOffice keeps a body bgcolor in its PDF but drops it from the
            # .docx it writes (measured, soffice 26.2.5.2), so a dark-page theme
            # would open in Word as light text on white paper. Put it back.
            docx_path = os.path.splitext(os.path.abspath(src))[0] + ".docx"
            b, g, r = (bgr >> 16) & 0xFF, (bgr >> 8) & 0xFF, bgr & 0xFF
            stamp_page_colour(docx_path, f"{r:02X}{g:02X}{b:02X}")
        return rc
    if sys.platform != "win32":
        print(f"cannot convert: --renderer word needs Microsoft Word over COM, and this is "
              f"{sys.platform}. Microsoft ships no Word desktop app for Linux, so Word is not "
              "installable here. The source file was still written. Use "
              "--renderer libreoffice, or convert on a Windows machine with Word.",
              file=sys.stderr)
        return 1
    return to_word(src, want_docx, want_pdf)


def page_colour(path):
    """The page colour a dark-page theme wrote into `path` -- the
    `doc-builder-page` meta of an HTML report (house_style.mark_page) or the
    `<w:background>` of an SOP .docx (build_sop) -- as a Word BGR integer, or
    None for a white page."""
    low = path.lower()
    if low.endswith(".docx"):
        import zipfile  # pylint: disable=import-outside-toplevel
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
        m = re.search(r'<w:background w:color="([0-9A-Fa-f]{6})"', xml)
    elif low.endswith((".html", ".htm")):
        # The whole <head>, not a fixed prefix: the meta sits just before
        # </head>, after the stylesheet, so any extra head content (an inline
        # script, a second style block) pushed it past an 8 KB window and a
        # dark page read as white.
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        end = re.search(r"</head>", text, re.IGNORECASE)
        head = text[:end.end()] if end else text
        m = re.search(r'<meta name="' + house_style.PAGE_META + r'" content="#([0-9A-Fa-f]{6})"', head)
    else:
        return None
    if not m:
        return None
    r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    return r + (g << 8) + (b << 16)


# CT_Settings children that must PRECEDE <w:displayBackgroundShape/>. The
# schema is a sequence, so inserting the flag first (before <w:zoom>) makes a
# settings part Word may refuse or repair.
SETTINGS_BEFORE_BG = ("writeProtection", "view", "zoom", "removePersonalInformation",
                      "removeDateAndTime", "doNotDisplayPageBoundaries")


def _insert_display_bg(settings_xml: str) -> str:
    if "displayBackgroundShape" in settings_xml:
        return settings_xml
    end = None
    for tag in SETTINGS_BEFORE_BG:
        for m in re.finditer(rf"<w:{tag}\b[^>]*?(/>|>.*?</w:{tag}>)", settings_xml, re.DOTALL):
            end = max(end or 0, m.end())
    if end is None:
        m = re.search(r"<w:settings\b[^>]*>", settings_xml)
        end = m.end()
    return settings_xml[:end] + "<w:displayBackgroundShape/>" + settings_xml[end:]


def stamp_page_colour(docx_path, hex6):
    """Write a page colour into an existing .docx: `<w:background>` as the first
    child of `<w:document>` and `<w:displayBackgroundShape/>` in settings, the
    pair Word writes for Design > Page Color. Rewrites to a temp file and
    `os.replace`s it, so a failure leaves the original intact."""
    import tempfile  # pylint: disable=import-outside-toplevel
    import zipfile  # pylint: disable=import-outside-toplevel
    with zipfile.ZipFile(docx_path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    out = []
    for info, data in items:
        if info.filename == "word/document.xml":
            xml = data.decode("utf-8")
            xml = re.sub(r"<w:background\b[^>]*/>", "", xml)
            m = re.search(r"<w:document\b[^>]*>", xml)
            xml = xml[:m.end()] + f'<w:background w:color="{hex6}"/>' + xml[m.end():]
            data = xml.encode("utf-8")
        elif info.filename == "word/settings.xml":
            data = _insert_display_bg(data.decode("utf-8")).encode("utf-8")
        out.append((info, data))
    fd, tmp = tempfile.mkstemp(suffix=".docx", dir=os.path.dirname(os.path.abspath(docx_path)))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for info, data in out:
                z.writestr(info, data)
        # mkstemp creates 0600; keep the mode the converter gave the original.
        shutil.copymode(docx_path, tmp)
        os.replace(tmp, docx_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def to_word(html_path, want_docx, want_pdf):
    """Convert through Word COM. Windows with Word installed only.

    Opens whatever Word can open - the HTML this script emits, or a .docx from
    build_sop.py. Prefer convert() over calling this directly: convert() is what
    names the engine on stderr before the first file is written.

    Every target is confirmed to exist, be non-empty, and be NEWER than the
    moment its SaveAs2 started - the same three checks `render_engine.to_soffice`
    applies, through the same function. SKILL.md's rule "a conversion that exits
    0 produced a file" was enforced on the LibreOffice side only until
    2026-09-22; a rule that holds on one engine is not a rule, and Word has its
    own way of returning without writing (a SaveAs2 that DisplayAlerts=0
    suppressed, an add-in that cancels the save)."""
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
            print(f"cannot convert: {why}. Close {os.path.basename(target)} and run again.", file=sys.stderr)
            return 1

    # The try must open IMMEDIATELY after Dispatch, and doc must be tracked from
    # None. An earlier version set Visible/DisplayAlerts and computed `base`
    # outside any handler, so a failure in that window left a headless WINWORD
    # process running with no window to close it from -- and one that opened a
    # document before failing left it open too. On a machine that generates
    # reports on a schedule those accumulate until Word refuses to start.
    page_bgr = page_colour(html_path)
    word = win32.Dispatch("Word.Application")
    doc = None
    rc = 0
    # PrintBackground is a USER-WIDE Word option. It is switched on only for a
    # dark-page document, so the PDF export keeps the page colour, and put back
    # in `finally` to whatever the operator had.
    saved_print_bg = None
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        base = os.path.splitext(os.path.abspath(html_path))[0]
        doc = word.Documents.Open(os.path.abspath(html_path), False, True)
        if page_bgr is not None:
            doc.Background.Fill.Visible = True
            doc.Background.Fill.Solid()
            doc.Background.Fill.ForeColor.RGB = page_bgr
            saved_print_bg = word.Options.PrintBackground
            word.Options.PrintBackground = True
        # Every converted file names its engine. A reader must never have to
        # guess whether a .docx came from Word or from LibreOffice.
        label = render_engine.engine_label(render_engine.WORD)
        # wdFormatDocumentDefault / wdFormatPDF. .docx first: SaveAs2 rebinds the
        # document to its new path, and that is the order the soffice side uses.
        saves = ([(base + ".docx", 16)] if want_docx else []) + \
                ([(base + ".pdf", 17)] if want_pdf else [])
        for target, fmt in saves:
            before = os.path.getmtime(target) if os.path.exists(target) else -1.0
            doc.SaveAs2(target, fmt)
            problem = render_engine.conversion_problem(target, before)
            if problem:
                print(f"Word reported no error saving {os.path.basename(target)}, but "
                      f"{problem}. Treating that as a failed conversion, not a success.",
                      file=sys.stderr)
                rc = 1
                break
            print(f"wrote {target}  [renderer: {label}]")
    finally:
        # Both closes are individually guarded: if Close raises, Quit must still
        # run, or the failure that broke the save also leaks the process.
        if saved_print_bg is not None:
            try:
                word.Options.PrintBackground = saved_print_bg
            except Exception:  # pylint: disable=broad-except
                pass
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:  # pylint: disable=broad-except
                pass
        try:
            word.Quit()
        except Exception:  # pylint: disable=broad-except
            pass
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="JSON report document")
    ap.add_argument("--out", default=None,
                    help="output directory (default: the brand pack's report "
                         "directory, normally reports/, which should be "
                         "gitignored - these documents read as an attack plan)")
    resolve_brand.add_brand_argument(ap)
    resolve_brand.add_theme_arguments(ap)
    ap.add_argument("--name", help="basename; default is the title, slugified")
    ap.add_argument("--to-docx", action="store_true")
    ap.add_argument("--to-pdf", action="store_true")
    render_engine.add_renderer_argument(ap)
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

    brand = resolve_brand.resolve(args.brand, theme=args.theme, density=args.density)
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
        return convert(path, args.to_docx, args.to_pdf, renderer=args.renderer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
