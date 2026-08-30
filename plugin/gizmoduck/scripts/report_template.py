#!/usr/bin/env python3
"""Presentation layer for gizmoduck HTML/PDF reports. Stdlib only.

This module knows nothing about nuclei. It is handed already-deduped findings
plus the severity vocabulary, and returns a complete HTML document.

CSS CONSTRAINT - READ BEFORE EDITING
------------------------------------
wkhtmltopdf 0.12.x renders through Qt WebKit 4.8, which predates flexbox, CSS
grid and custom properties. A layout built with any of those looks correct in a
browser and silently collapses to an unstyled column in the PDF - and nothing
warns you, because wkhtmltopdf exits 0. Every layout here is therefore built
from tables and block elements, and every colour is a literal.

Verify any change in the PDF, not just the browser.
"""
import datetime
import html

# Presentation only - the domain vocabulary (names, ordering) is injected by the
# caller so there is one source of truth for what a severity *is*.
PALETTE = {
    4: {"ink": "#7a1616", "bg": "#fbeaea", "edge": "#d98c8c"},
    3: {"ink": "#a34a12", "bg": "#fdf0e6", "edge": "#e0a877"},
    2: {"ink": "#8a7400", "bg": "#fdf8e3", "edge": "#d8c86a"},
    1: {"ink": "#2f6b2f", "bg": "#eef7ee", "edge": "#9cc79c"},
    0: {"ink": "#4a5568", "bg": "#f2f4f7", "edge": "#c2cad6"},
}
NEUTRAL = {"ink": "#4a5568", "bg": "#f2f4f7", "edge": "#c2cad6"}

# Findings at or above this severity are "action required"; below it they are
# hardening backlog. Medium is the line because Low/Info from a signature
# scanner are overwhelmingly version banners and header advice.
ACTION_THRESHOLD = 2

# An affected-host list longer than this is truncated in the finding card and
# printed in full in Appendix A instead. Twenty URLs inline is what made the
# previous template unreadable.
INLINE_AFFECTED_CAP = 8

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font: 11pt/1.5 "Segoe UI", -apple-system, Helvetica, Arial, sans-serif;
       color: #1b2029; margin: 0; padding: 0; background: #fff; }
.wrap { max-width: 176mm; margin: 0 auto; }
h1, h2, h3, h4 { margin: 0; font-weight: 600; }
p { margin: .45em 0; }
a { color: #1c4f8b; text-decoration: none; word-break: break-all; }

/* ---- cover ---- */
.cover { border-bottom: 3px solid #1b2029; padding-bottom: 10pt; margin-bottom: 14pt; }
.eyebrow { font-size: 8pt; letter-spacing: .18em; text-transform: uppercase;
           color: #6b7280; margin-bottom: 5pt; }
.cover h1 { font-size: 21pt; line-height: 1.2; margin-bottom: 8pt; }
table.meta { border-collapse: collapse; width: 100%; font-size: 9.5pt; }
table.meta td { padding: 2.5pt 0; vertical-align: top; border: 0; }
table.meta td.k { color: #6b7280; width: 34mm; white-space: nowrap; }
table.meta td.v { color: #1b2029; font-weight: 600; }

/* ---- posture badges (table, NOT flex - see module docstring) ---- */
table.badges { border-collapse: separate; border-spacing: 4pt 0;
               width: 100%; table-layout: fixed; margin: 4pt 0 10pt -4pt; }
table.badges td { text-align: center; padding: 7pt 2pt; border-radius: 4px;
                  border: 1px solid #dfe3e8; background: #fafbfc; }
.badges .n { display: block; font-size: 17pt; font-weight: 700; line-height: 1.1; }
.badges .l { display: block; font-size: 7.5pt; letter-spacing: .09em;
             text-transform: uppercase; color: #6b7280; margin-top: 2pt; }
.verdict { border-left: 3px solid #1b2029; background: #f7f8fa;
           padding: 7pt 10pt; font-size: 10pt; margin: 0 0 4pt 0; }

/* ---- sections ---- */
.section { margin-top: 16pt; }
.section > h2 { font-size: 13pt; padding-bottom: 4pt; border-bottom: 1.5px solid #d5dae1;
                margin-bottom: 9pt; }
.count { color: #6b7280; font-weight: 400; font-size: 10pt; }
.lead { color: #4a5568; font-size: 9.5pt; margin: -4pt 0 9pt 0; }

/* ---- finding card ---- */
.card { border: 1px solid #dfe3e8; border-left-width: 4px; border-radius: 3px;
        padding: 9pt 11pt; margin-bottom: 10pt; page-break-inside: avoid; }
.card h3 { font-size: 12pt; margin-bottom: 6pt; }
.pill { display: inline-block; font-size: 7.5pt; font-weight: 700;
        letter-spacing: .09em; text-transform: uppercase; padding: 1.5pt 6pt;
        border-radius: 2px; margin-right: 7pt; vertical-align: 2pt; }
table.kv { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 5pt 0 7pt 0; }
table.kv th { text-align: left; font-weight: 400; color: #6b7280; width: 26mm;
              padding: 2pt 8pt 2pt 0; vertical-align: top; border: 0; }
table.kv td { padding: 2pt 0; vertical-align: top; border: 0;
              font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; }
.blk { margin-top: 7pt; }
.blk h4 { font-size: 8pt; letter-spacing: .1em; text-transform: uppercase;
          color: #6b7280; margin-bottom: 3pt; }
.blk p { margin: 0; font-size: 9.5pt; }
ul.hosts { margin: 0; padding-left: 15pt; font-size: 8.5pt;
           font-family: Consolas, "Courier New", monospace; }
ul.hosts li { margin: 1pt 0; word-break: break-all; }
.more { color: #6b7280; font-style: italic; font-family: inherit; font-size: 8.5pt; }
.fix { background: #f2f7f2; border: 1px solid #cfe3cf; border-radius: 3px;
       padding: 6pt 9pt; margin-top: 7pt; }
.fix h4 { color: #2f6b2f; }
.refs { margin-top: 6pt; font-size: 8.5pt; }
.refs a { display: block; margin: 1pt 0; }

/* ---- severities counted but not itemised ---- */
.badges .co { display: block; font-size: 6.5pt; letter-spacing: .06em;
              text-transform: uppercase; color: #98a1ad; margin-top: 2pt; }
.suppressed { border: 1px solid #dfe3e8; border-left: 3px solid #c2cad6;
              background: #fafbfc; border-radius: 3px; padding: 7pt 10pt;
              margin: 0 0 4pt 0; font-size: 9.5pt; color: #4a5568; }
.clear { border-left: 3px solid #2f6b2f; background: #f2f7f2;
         border: 1px solid #cfe3cf; border-radius: 3px; padding: 8pt 11pt;
         margin: 0 0 7pt 0; font-size: 10.5pt; font-weight: 600;
         font-family: "Segoe UI", -apple-system, Helvetica, Arial, sans-serif; }

/* ---- finding rank and name ---- */
.rank { display: inline-block; min-width: 15pt; font-size: 9pt; font-weight: 700;
        color: #8a919c; font-variant-numeric: tabular-nums; }
.cname { font-weight: 600; }

/* ---- appendix ---- */
.appendix { page-break-before: always; }
.appendix h2 { font-size: 13pt; }
.apx-group { margin-bottom: 11pt; page-break-inside: avoid; }
.apx-group h3 { font-size: 9.5pt; font-family: Consolas, "Courier New", monospace; }

.foot { margin-top: 18pt; padding-top: 7pt; border-top: 1px solid #dfe3e8;
        font-size: 8pt; color: #8a919c; }
"""


def _pal(sev):
    return PALETTE.get(sev, NEUTRAL)


def _scan_date(findings):
    """Newest timestamp across findings, else today. A report regenerated weeks
    later must still name the date the scan ran, not the date it was printed."""
    stamps = [f.get("timestamp") for f in findings if f.get("timestamp")]
    if stamps:
        raw = max(stamps)[:10]
        try:
            return datetime.date.fromisoformat(raw).strftime("%d %B %Y")
        except ValueError:
            pass
    return datetime.date.today().strftime("%d %B %Y")


def _hosts_of(findings):
    return sorted({f.get("host", "") for f in findings if f.get("host")})


def _verdict(counts, sev_name):
    crit = counts.get(sev_name[4], 0)
    high = counts.get(sev_name[3], 0)
    med = counts.get(sev_name[2], 0)
    if crit:
        return ("Critical exposure present. %d critical and %d high-risk finding(s) "
                "require immediate remediation." % (crit, high))
    if high:
        return ("%d high-risk finding(s) require remediation. No critical exposure "
                "was detected." % high)
    if med:
        return ("No critical or high-risk exposure detected. %d medium finding(s) "
                "should be scheduled for remediation." % med)
    return ("No critical, high or medium findings. Remaining items are hardening "
            "observations, not active exposure.")


def _cover(title, findings, summary, scan_date, e):
    hosts = _hosts_of(findings)
    uniq_n = len({f.get("template_id", "") for f in findings})
    rows = [
        ("Scan date", e(scan_date)),
        ("Hosts scanned", "%d" % (len(hosts) or summary.get("hosts", 0))),
        ("Findings", "%d instances across %d unique checks"
         % (summary.get("total_instances", 0), uniq_n)),
        ("Method", "Unauthenticated external scan, signature-based (nuclei)"),
    ]
    meta = "".join("<tr><td class='k'>%s</td><td class='v'>%s</td></tr>" % (k, v)
                   for k, v in rows)
    return ("<div class='cover'><div class='eyebrow'>Security scan report</div>"
            "<h1>%s</h1><table class='meta'>%s</table></div>" % (e(title), meta))


def _posture(summary, sev_name, order, e, floor=ACTION_THRESHOLD):
    """Severity readout. Every severity is counted; the ones below `floor` carry
    a 'count only' caption so the table itself says why no section follows."""
    counts = summary.get("by_severity", {})
    cells = []
    for s in order:
        name = sev_name[s]
        n = counts.get(name, 0)
        pal = _pal(s)
        itemised = s >= floor
        # A zero count is muted so the eye lands on the severities that fired.
        ink = pal["ink"] if n else "#b6bcc6"
        bg = (pal["bg"] if n else "#fafbfc") if itemised else "#fafbfc"
        edge = (pal["edge"] if n else "#e6e9ed") if itemised else "#e6e9ed"
        caption = "" if itemised else "<span class='co'>count only</span>"
        cells.append("<td style='background:%s;border-color:%s'>"
                     "<span class='n' style='color:%s'>%d</span>"
                     "<span class='l'>%s</span>%s</td>"
                     % (bg, edge, ink, n, e(name), caption))
    return ("<table class='badges'><tr>%s</tr></table>"
            "<p class='verdict'>%s</p>"
            % ("".join(cells), e(_verdict(counts, sev_name))))


def _scope(findings, e):
    hosts = _hosts_of(findings)
    items = "".join("<li>%s</li>" % e(h) for h in hosts) or "<li>none recorded</li>"
    return (
        "<div class='section'><h2>Scope and limitations</h2>"
        "<div class='blk'><h4>Targets assessed</h4>"
        "<ul class='hosts'>%s</ul></div>"
        "<div class='blk'><h4>Limitations</h4><p>"
        "Signature-based detection only: findings are limited to checks a template "
        "exists for. Business logic, authorisation and authenticated-session flaws "
        "are out of scope and require separate testing. Content behind "
        "authentication or a WAF challenge was not assessed. Absence of a finding "
        "is not evidence of absence of a vulnerability."
        "</p></div></div>" % items)


def _card(f, sev_name, e, rank=None):
    sev = f.get("severity", 0)
    pal = _pal(sev)
    locations = f.get("instances", len(f.get("affected") or []))
    raw = f.get("raw_count", locations)
    # Spelled out rather than shown as a bare number: "20" next to 2 listed URLs
    # looks like a rendering fault unless the report says what each number counts.
    hits = ("%d" % raw) if raw == locations else (
        "%d detections across %d location(s)" % (raw, locations))
    kv = [
        ("Template", e(f.get("template_id", "") or "-")),
        ("Type", e(f.get("type", "") or "-")),
        ("CVSS", e(str(f.get("cvss") or "n/a"))),
        ("CVE", e(", ".join(f.get("cve") or []) or "-")),
        ("Detections", hits),
    ]
    kv_html = "".join("<tr><th>%s</th><td>%s</td></tr>" % (k, v) for k, v in kv)

    affected = f.get("affected") or []
    shown = affected[:INLINE_AFFECTED_CAP]
    lis = "".join("<li>%s</li>" % e(a) for a in shown)
    if len(affected) > INLINE_AFFECTED_CAP:
        lis += ("<li class='more'>+%d more - full list in Appendix A</li>"
                % (len(affected) - INLINE_AFFECTED_CAP))
    hosts_blk = ("<div class='blk'><h4>Affected</h4><ul class='hosts'>%s</ul></div>"
                 % lis) if affected else ""

    desc = (f.get("description") or "").strip()
    desc_blk = ("<div class='blk'><h4>Detail</h4><p>%s</p></div>" % e(desc)) if desc else ""

    rem = (f.get("remediation") or "").strip()
    fix_blk = ("<div class='fix'><h4>Remediation</h4><p>%s</p></div>" % e(rem)) if rem else ""

    refs = [r for r in (f.get("reference") or []) if r][:4]
    refs_blk = ("<div class='refs'>%s</div>"
                % "".join("<a href='%s'>%s</a>" % (e(r), e(r)) for r in refs)) if refs else ""

    # The rank is real information here, not decoration: findings are sorted by
    # severity, so the number IS the remediation order.
    rank_html = "<span class='rank'>%d</span>" % rank if rank else ""

    return ("<div class='card' style='border-left-color:%s'>"
            "<h3>%s<span class='pill' style='background:%s;color:%s'>%s</span>"
            "<span class='cname'>%s</span></h3>"
            "<table class='kv'>%s</table>%s%s%s%s</div>"
            % (pal["ink"], rank_html, pal["bg"], pal["ink"],
               e(sev_name.get(sev, "Info")),
               e(f.get("name", "") or f.get("template_id", "")),
               kv_html, desc_blk, hosts_blk, fix_blk, refs_blk))


def _suppressed_note(summary, sev_name, order, floor, e):
    """One line accounting for the severities this report counts but does not list.

    Stated rather than silently omitted: a reader who sees 42 Info in the table
    and no Info section needs to know that was a decision, not a truncation.
    """
    counts = summary.get("by_severity", {})
    n = sum(counts.get(sev_name[x], 0) for x in order if x < floor)
    if not n:
        return ""
    noun = "finding" if n == 1 else "findings"
    return ("<p class='suppressed'><b>%d %s below %s</b> were recorded and are not "
            "itemised here. They are inventory - version banners, DNS records, the "
            "presence of a form - rather than remediation work, and listing them buries "
            "what is meant to be acted on. The full detail remains in the JSONL.</p>"
            % (n, noun, e(sev_name.get(floor, "Medium"))))


def _appendix(uniq, e):
    groups = [f for f in uniq if (f.get("affected") or [])]
    if not groups:
        return ""
    blocks = []
    for f in groups:
        lis = "".join("<li>%s</li>" % e(a) for a in f.get("affected") or [])
        blocks.append("<div class='apx-group'><h3>%s <span class='count'>(%d)</span></h3>"
                      "<ul class='hosts'>%s</ul></div>"
                      % (e(f.get("template_id", "")),
                         f.get("instances", 0), lis))
    return ("<div class='section appendix'><h2>Appendix A - full affected inventory</h2>"
            "<p class='lead'>Every matched location, by check. This is the complete "
            "evidence list the summary sections abbreviate.</p>%s</div>"
            % "".join(blocks))


def render_report(uniq, summary, min_sev, title, sev_name, order, findings=None):
    """Build the full HTML document.

    uniq     - deduped findings, pre-sorted by (-severity, name)
    summary  - {"hosts": int, "total_instances": int, "by_severity": {name: n}}
    min_sev  - integer severity floor already chosen by the caller
    sev_name - {int: "Critical"...} injected so severity naming has one owner
    order    - severity ints, highest first
    findings - raw (undeduped) findings, used for scan date and host list
    """
    e = html.escape
    findings = findings if findings is not None else uniq
    # Never itemise below Medium, however low the caller set min_sev.
    floor = max(min_sev, ACTION_THRESHOLD)
    shown = [f for f in uniq if f.get("severity", 0) >= floor]
    scan_date = _scan_date(findings)

    if shown:
        body = "".join(_card(f, sev_name, e, n)
                       for n, f in enumerate(shown, 1))
        heading = ("<div class='section'><h2>Findings requiring action "
                   "<span class='count'>(%d)</span></h2>"
                   "<p class='lead'>Ordered by severity. Each entry is one check, with "
                   "every location it matched.</p>%s</div>" % (len(shown), body))
    else:
        heading = ("<div class='section'><h2>Findings requiring action</h2>"
                   "<p class='clear'>Nothing at or above %s. No remediation work "
                   "follows from this scan.</p>"
                   "<p class='lead'>That reflects what a signature scanner can match. "
                   "It is not a statement that no vulnerability exists.</p></div>"
                   % e(sev_name.get(floor, "Medium")))

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>%s</title>"
        "<style>%s</style></head><body><div class='wrap'>" % (e(title), CSS),
        _cover(title, findings, summary, scan_date, e),
        _posture(summary, sev_name, order, e, floor),
        _suppressed_note(summary, sev_name, order, floor, e),
        _scope(findings, e),
        heading,
        _appendix(shown, e),
        "<div class='foot'>Generated by gizmoduck from nuclei JSONL output. "
        "Scan date %s. Critical, High and Medium findings are itemised; lower "
        "severities are counted only. Only assets owned or explicitly authorised "
        "for testing were assessed.</div>" % e(scan_date),
        "</div></body></html>",
    ]
    return "\n".join(p for p in parts if p)
