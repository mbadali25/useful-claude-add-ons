"""Rendering for work log reports: HTML email body, plain-text fallback, and
the detailed PDF attachment.

The split of responsibility matters and is intentional. The email body carries
the *high level* story — what got done, where, and roughly when — so a manager
can read it on a phone in fifteen seconds without opening anything. The PDF
carries the full record, including per-entry detail prose and the exact
commands run, for the reader who wants to audit it.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from wlconfig import (
    FIELD_LABELS,
    LIST_FIELDS,
    aggregate,
    date_range_label,
    parse_iso,
)

# A restrained palette: graphite for structure, one accent, and tinted chips
# so the different dimensions (systems vs databases vs tables) stay scannable.
INK = "#101828"
MUTED = "#667085"
BORDER = "#e4e7ec"
CANVAS = "#f2f4f7"
PANEL = "#f9fafb"
ACCENT = "#0e7490"

CHIP_STYLES = {
    "code": ("#fffaeb", "#b54708"),
    "systems": ("#eef2f6", "#344054"),
    "databases": ("#f4f3ff", "#5925dc"),
    "tables": ("#f0fdfa", "#0f766e"),
    "commands": ("#f8fafc", "#475467"),
    # Red is reserved for the blocked badge, so tickets take a neutral blue.
    "tickets": ("#eff8ff", "#175cd3"),
}

STATUS_STYLES = {
    "blocked": ("#fef3f2", "#b42318"),
    "in-progress": ("#fffaeb", "#b54708"),
    "investigated": ("#eef2f6", "#344054"),
}

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',"
        "Arial,sans-serif")
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


def _time(value: str | None) -> str:
    dt = parse_iso(value)
    return dt.strftime("%-I:%M %p") if dt else ""


def _day(value: str | None) -> str:
    dt = parse_iso(value)
    return dt.strftime("%a %b %-d") if dt else ""


def _duration(session: dict) -> str:
    start, end = parse_iso(session.get("started_at")), parse_iso(session.get("ended_at"))
    if not (start and end):
        return ""
    minutes = max(0, int((end - start).total_seconds() // 60))
    if minutes < 1:
        return ""
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    return f"{hours}h" if hours else f"{minutes}m"


# --------------------------------------------------------------------------
# HTML email
# --------------------------------------------------------------------------

def _chips(field: str, values: list[str], limit: int = 8) -> str:
    if not values:
        return ""
    bg, fg = CHIP_STYLES.get(field, ("#f2f4f7", "#344054"))
    shown, extra = values[:limit], max(0, len(values) - limit)
    spans = "".join(
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'font-family:{MONO};font-size:11px;line-height:16px;padding:3px 8px;'
        f'border-radius:5px;margin:0 6px 6px 0;">{escape(v)}</span>'
        for v in shown
    )
    if extra:
        spans += (
            f'<span style="display:inline-block;color:{MUTED};font-size:11px;'
            'line-height:16px;padding:3px 2px;margin:0 0 6px 0;">'
            f'+{extra} more</span>'
        )
    return (
        '<tr><td style="padding:0 0 4px 0;">'
        '<div style="font-size:10px;letter-spacing:.7px;text-transform:uppercase;'
        f'color:{MUTED};font-weight:600;margin:0 0 6px 0;">'
        f'{escape(FIELD_LABELS[field])}</div>{spans}</td></tr>'
    )


def _stat(value: str, label: str) -> str:
    return (
        '<td width="33%" style="padding:16px 8px;text-align:center;">'
        f'<div style="font-family:{FONT};font-size:22px;font-weight:700;'
        f'color:{INK};line-height:26px;">{escape(value)}</div>'
        f'<div style="font-family:{FONT};font-size:10px;letter-spacing:.8px;'
        f'text-transform:uppercase;color:{MUTED};font-weight:600;'
        f'padding-top:4px;">{escape(label)}</div></td>'
    )


def _status_badge(status: str) -> str:
    """Render a badge for anything that is not plain 'done'.

    A blocked or in-progress item is the single most actionable thing in a
    report, so it has to be visible in the email body rather than only in the
    attachment. 'done' gets no badge — marking the normal case just adds noise.
    """
    if not status or status == "done":
        return ""
    bg, fg = STATUS_STYLES.get(status, ("#f2f4f7", "#344054"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        'font-size:10px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;'
        'line-height:14px;padding:2px 6px;border-radius:4px;margin-left:6px;'
        f'vertical-align:middle;">{escape(status)}</span>'
    )


def _session_card(session: dict, last: bool) -> str:
    entries = session.get("entries", [])

    bullets = "".join(
        '<tr><td width="14" valign="top" style="padding:3px 8px 0 0;">'
        f'<div style="width:5px;height:5px;border-radius:3px;background:{ACCENT};'
        'margin-top:6px;"></div></td>'
        f'<td style="font-family:{FONT};font-size:14px;line-height:21px;'
        f'color:#344054;padding-bottom:7px;">{escape(e.get("summary", ""))}'
        + _status_badge(e.get("status", ""))
        + (f'<span style="color:{MUTED};font-size:12px;"> · '
           f'{escape(_time(e.get("timestamp")))}</span>' if _time(e.get("timestamp")) else "")
        + "</td></tr>"
        for e in entries
    )

    rolled = aggregate([session])["totals"]
    chip_rows = "".join(
        _chips(field, rolled[field])
        for field in ("systems", "databases", "tables", "code", "tickets")
        if rolled[field]
    )
    chips_block = (
        f'<tr><td style="padding:12px 0 0 0;border-top:1px solid {BORDER};">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'{chip_rows}</table></td></tr>'
    ) if chip_rows else ""

    window = " – ".join(x for x in [_time(session.get("started_at")),
                                    _time(session.get("ended_at"))] if x)
    duration = _duration(session)
    meta = " · ".join(x for x in [_day(session.get("started_at")), window, duration] if x)

    summary_line = (
        f'<tr><td style="font-family:{FONT};font-size:14px;line-height:21px;'
        f'color:{MUTED};padding:0 0 12px 0;">{escape(session["summary"])}</td></tr>'
    ) if session.get("summary") else ""

    margin = "0" if last else "0 0 14px 0"
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {BORDER};border-radius:10px;margin:{margin};">'
        '<tr><td style="padding:18px 20px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-family:{FONT};font-size:16px;font-weight:650;'
        f'color:{INK};line-height:22px;padding:0 0 3px 0;">'
        f'{escape(session.get("title") or session["session_id"])}</td></tr>'
        f'<tr><td style="font-family:{FONT};font-size:11px;color:{MUTED};'
        f'padding:0 0 12px 0;">{escape(meta)}</td></tr>'
        f'{summary_line}'
        '<tr><td><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0">{bullets}</table></td></tr>'
        f'{chips_block}'
        '</table></td></tr></table>'
    )


def render_email_html(sessions: list[dict], cfg: dict, *,
                      headline: str = "", has_attachment: bool = True) -> str:
    agg = aggregate(sessions)
    project = cfg["project"].get("name") or "Work Log"
    env = cfg["project"].get("environment")
    eyebrow = f"{project} · {env}" if env else project

    cards = "".join(
        _session_card(s, last=i == len(sessions) - 1)
        for i, s in enumerate(sessions)
    ) or (
        f'<div style="font-family:{FONT};font-size:14px;color:{MUTED};">'
        'No sessions were recorded in this period.</div>'
    )

    systems_touched = len(set(agg["totals"]["systems"]) | set(agg["totals"]["databases"]))
    stats = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{PANEL};border-top:1px solid {BORDER};'
        f'border-bottom:1px solid {BORDER};"><tr>'
        + _stat(str(agg["session_count"]), "Sessions")
        + _stat(str(agg["entry_count"]), "Items of work")
        + _stat(str(systems_touched), "Systems touched")
        + "</tr></table>"
    )

    headline_block = (
        '<tr><td style="padding:0 0 20px 0;">'
        f'<div style="border-left:3px solid {ACCENT};padding:2px 0 2px 14px;'
        f'font-family:{FONT};font-size:15px;line-height:23px;color:#344054;">'
        f'{escape(headline)}</div></td></tr>'
    ) if headline else ""

    attach_note = (
        '<tr><td style="padding:20px 0 0 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{PANEL};border:1px solid {BORDER};border-radius:8px;">'
        f'<tr><td style="padding:12px 16px;font-family:{FONT};font-size:12px;'
        f'line-height:18px;color:{MUTED};">'
        f'<strong style="color:{INK};">Full detail attached.</strong> '
        'The PDF includes every log entry with its notes, the exact commands run, '
        'and the complete list of files, databases, and tables touched.'
        '</td></tr></table></td></tr>'
    ) if has_attachment else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(project)} — Work Log Report</title></head>
<body style="margin:0;padding:0;background:{CANVAS};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
 style="background:{CANVAS};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0"
 style="width:640px;max-width:100%;background:#ffffff;border:1px solid {BORDER};
 border-radius:12px;overflow:hidden;">

  <tr><td style="background:{INK};padding:26px 32px;">
    <div style="font-family:{FONT};font-size:10px;letter-spacing:1.2px;
     text-transform:uppercase;color:#98a2b3;font-weight:600;">
     {escape(eyebrow)}</div>
    <div style="font-family:{FONT};font-size:23px;line-height:30px;
     font-weight:700;color:#ffffff;padding-top:6px;">Work Log Report</div>
    <div style="font-family:{FONT};font-size:13px;color:#98a2b3;padding-top:4px;">
     {escape(date_range_label(agg))}</div>
  </td></tr>

  <tr><td>{stats}</td></tr>

  <tr><td style="padding:24px 32px 28px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {headline_block}
      <tr><td style="font-family:{FONT};font-size:11px;letter-spacing:.9px;
       text-transform:uppercase;color:{MUTED};font-weight:700;
       padding:0 0 12px 0;">Sessions</td></tr>
      <tr><td>{cards}</td></tr>
      {attach_note}
    </table>
  </td></tr>

  <tr><td style="background:{PANEL};border-top:1px solid {BORDER};
   padding:16px 32px;font-family:{FONT};font-size:11px;line-height:17px;
   color:{MUTED};">
    Generated automatically from <span style="font-family:{MONO};">work-log/</span>
    in the {escape(project)} repository.
  </td></tr>

</table></td></tr></table></body></html>"""


def render_email_text(sessions: list[dict], cfg: dict, *,
                      headline: str = "", has_attachment: bool = True) -> str:
    agg = aggregate(sessions)
    project = cfg["project"].get("name") or "Work Log"
    lines = [
        f"{project} — Work Log Report",
        date_range_label(agg),
        "=" * 60,
        "",
    ]
    if headline:
        lines += [headline, ""]
    lines.append(
        f"{agg['session_count']} session(s) · {agg['entry_count']} items of work"
    )
    lines.append("")

    for session in sessions:
        window = " - ".join(x for x in [_time(session.get("started_at")),
                                        _time(session.get("ended_at"))] if x)
        lines.append(f"{session.get('title') or session['session_id']}")
        lines.append(f"  {_day(session.get('started_at'))} {window}".rstrip())
        if session.get("summary"):
            lines.append(f"  {session['summary']}")
        for entry in session.get("entries", []):
            status = entry.get("status", "done")
            mark = "" if status == "done" else f"  [{status.upper()}]"
            lines.append(f"  * {entry.get('summary', '')}{mark}")
        rolled = aggregate([session])["totals"]
        for field in ("systems", "databases", "tables", "code", "tickets"):
            if rolled[field]:
                lines.append(f"  {FIELD_LABELS[field]}: {', '.join(rolled[field])}")
        lines.append("")

    if has_attachment:
        lines.append("Full detail — including per-entry notes and commands run — "
                     "is in the attached PDF.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# PDF attachment
# --------------------------------------------------------------------------

def render_pdf(sessions: list[dict], cfg: dict, out_path: Path, *,
               headline: str = "") -> Path:
    """Build the detailed PDF. Raises ImportError if reportlab is missing so
    the caller can degrade gracefully rather than failing the whole send."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    agg = aggregate(sessions)
    project = cfg["project"].get("name") or "Work Log"
    include_commands = cfg["reporting"].get("include_commands_in_pdf", True)

    base = getSampleStyleSheet()
    ink = colors.HexColor(INK)
    muted = colors.HexColor(MUTED)
    rule = colors.HexColor(BORDER)

    styles = {
        "eyebrow": ParagraphStyle("eyebrow", parent=base["Normal"], fontName="Helvetica-Bold",
                                  fontSize=8, textColor=muted, spaceAfter=4, leading=10),
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=22, textColor=ink, alignment=TA_LEFT,
                                spaceAfter=2, leading=26),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=10,
                              textColor=muted, spaceAfter=14, leading=13),
        "h2": ParagraphStyle("h2", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=13, textColor=ink, spaceBefore=4,
                             spaceAfter=2, leading=16),
        "meta": ParagraphStyle("meta", parent=base["Normal"], fontSize=8.5,
                               textColor=muted, spaceAfter=7, leading=11),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9.5,
                               textColor=colors.HexColor("#344054"),
                               spaceAfter=5, leading=14),
        "entry": ParagraphStyle("entry", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=10, textColor=ink, spaceBefore=8,
                                spaceAfter=2, leading=13),
        "detail": ParagraphStyle("detail", parent=base["Normal"], fontSize=9.5,
                                 textColor=colors.HexColor("#475467"),
                                 leftIndent=10, spaceAfter=4, leading=13.5),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=7.5, textColor=muted, leading=10),
        "mono": ParagraphStyle("mono", parent=base["Normal"], fontName="Courier",
                               fontSize=8, textColor=colors.HexColor("#344054"),
                               leading=11),
    }

    def kv_table(pairs: list[tuple[str, str]]) -> Table:
        rows = [[Paragraph(k.upper(), styles["label"]), Paragraph(v, styles["mono"])]
                for k, v in pairs]
        table = Table(rows, colWidths=[1.05 * inch, 5.2 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, rule),
        ]))
        return table

    story: list = []
    story.append(Paragraph(escape(project.upper()), styles["eyebrow"]))
    story.append(Paragraph("Work Log — Detailed Report", styles["title"]))
    story.append(Paragraph(
        f"{escape(date_range_label(agg))} &nbsp;·&nbsp; "
        f"{agg['session_count']} session(s) &nbsp;·&nbsp; "
        f"{agg['entry_count']} items of work", styles["sub"]))
    story.append(HRFlowable(width="100%", thickness=1, color=rule, spaceAfter=14))

    if headline:
        story.append(Paragraph("Summary", styles["h2"]))
        story.append(Paragraph(escape(headline), styles["body"]))
        story.append(Spacer(1, 8))

    scope_pairs = [(FIELD_LABELS[f], ", ".join(escape(v) for v in agg["totals"][f]))
                   for f in LIST_FIELDS
                   if agg["totals"][f] and (f != "commands" or include_commands)]
    if scope_pairs:
        story.append(Paragraph("Everything touched in this period", styles["h2"]))
        story.append(Spacer(1, 4))
        story.append(kv_table(scope_pairs))
        story.append(Spacer(1, 6))

    for index, session in enumerate(sessions):
        story.append(PageBreak() if index or scope_pairs else Spacer(1, 4))
        window = " – ".join(x for x in [_time(session.get("started_at")),
                                        _time(session.get("ended_at"))] if x)
        meta = " · ".join(x for x in [
            session["session_id"], _day(session.get("started_at")),
            window, _duration(session)] if x)

        story.append(Paragraph(escape(session.get("title") or session["session_id"]),
                               styles["h2"]))
        story.append(Paragraph(escape(meta), styles["meta"]))
        if session.get("summary"):
            story.append(Paragraph(escape(session["summary"]), styles["body"]))
        story.append(HRFlowable(width="100%", thickness=0.6, color=rule,
                                spaceBefore=2, spaceAfter=2))

        for number, entry in enumerate(session.get("entries", []), start=1):
            block: list = [Paragraph(
                f'<font color="{ACCENT}">{number}.</font> '
                f'{escape(entry.get("summary", ""))}', styles["entry"])]
            stamp = _time(entry.get("timestamp"))
            status = entry.get("status", "")
            tag = " · ".join(x for x in [stamp, status] if x)
            if tag:
                block.append(Paragraph(escape(tag), styles["meta"]))
            if entry.get("detail"):
                block.append(Paragraph(escape(entry["detail"]), styles["detail"]))
            pairs = [(FIELD_LABELS[f], ", ".join(escape(v) for v in entry.get(f, [])))
                     for f in LIST_FIELDS
                     if entry.get(f) and (f != "commands" or include_commands)]
            if pairs:
                block.append(Spacer(1, 2))
                block.append(kv_table(pairs))
            block.append(Spacer(1, 4))
            story.append(KeepTogether(block))

        if not session.get("entries"):
            story.append(Paragraph("No individual entries were logged for this session.",
                                   styles["detail"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(0.75 * inch, 0.5 * inch,
                          f"{project} — work log detail")
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch,
                               f"Page {doc.page}")
        canvas.setStrokeColor(rule)
        canvas.setLineWidth(0.5)
        canvas.line(0.75 * inch, 0.68 * inch, letter[0] - 0.75 * inch, 0.68 * inch)
        canvas.restoreState()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.85 * inch,
        title=f"{project} — Work Log Detail", author="work-log-reporter",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out_path
