#!/usr/bin/env python3
"""work-log-reporter CLI.

    init      Create work-log/ and a config file at the repo root
    start     Begin a session folder for today
    log       Append one item of work to the current session
    end       Close the session, write its summary, auto-email if configured
    status    Show config health, current session, and unreported sessions
    report    Build the HTML + PDF report without sending
    send      Build and email the report, then mark those sessions reported

Run any subcommand with -h for its flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# sys.path is set up immediately above, so these cannot move to the top.
# pylint: disable=wrong-import-position
import render  # noqa: E402
from mailer import build_message, recipients, send as smtp_send  # noqa: E402
from wlconfig import (  # noqa: E402
    FIELD_LABELS,
    LIST_FIELDS,
    SESSION_ID_RE,
    WorkLogError,
    aggregate,
    config_path,
    date_range_label,
    find_root,
    list_session_ids,
    load_config,
    load_session,
    load_state,
    new_session,
    normalize_entry,
    now_iso,
    parse_iso,
    save_session,
    save_state,
    session_dir,
    unreported_session_ids,
    utc_stamp,
    validate_config,
    worklog_dir,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"


# --------------------------------------------------------------------------
# notes.md
# --------------------------------------------------------------------------

def write_notes(session: dict, root: Path) -> Path:
    """Regenerate notes.md from session.json.

    session.json is the source of truth and notes.md is the human-readable
    view of it. Rewriting the whole file on every append is cheap and means
    the two can never drift apart.
    """
    def fmt(value, pattern):
        dt = parse_iso(value)
        return dt.strftime(pattern) if dt else "-"

    lines = [
        f"# {session.get('title') or session['session_id']}",
        "",
        f"- **Session:** `{session['session_id']}`",
        f"- **Started:** {fmt(session.get('started_at'), '%A, %B %-d, %Y at %-I:%M %p %Z')}",
        f"- **Ended:** {fmt(session.get('ended_at'), '%A, %B %-d, %Y at %-I:%M %p %Z')}",
        "",
    ]

    if session.get("summary"):
        lines += ["## Summary", "", session["summary"], ""]

    rolled = aggregate([session])["totals"]
    scope = [f"- **{FIELD_LABELS[f]}:** "
             + ", ".join(f"`{v}`" for v in rolled[f])
             for f in LIST_FIELDS if rolled[f]]
    if scope:
        lines += ["## Touched in this session", "", *scope, ""]

    lines += ["## Log", ""]
    if not session.get("entries"):
        lines += ["_No entries logged yet._", ""]

    for number, entry in enumerate(session.get("entries", []), start=1):
        stamp = fmt(entry.get("timestamp"), "%-I:%M %p")
        lines.append(f"### {number}. {entry.get('summary', '')}")
        lines.append("")
        lines.append(f"`{stamp}` | {entry.get('status', 'done')}")
        lines.append("")
        if entry.get("detail"):
            lines += [entry["detail"], ""]
        for field in LIST_FIELDS:
            if entry.get(field):
                joined = ", ".join(f"`{v}`" for v in entry[field])
                lines.append(f"- **{FIELD_LABELS[field]}:** {joined}")
        lines.append("")

    path = session_dir(session["session_id"], root) / "notes.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Scope resolution
# --------------------------------------------------------------------------

def resolve_scope(args, root: Path) -> tuple[list[str], str]:
    """Return (session_ids, human label) for the requested reporting scope."""
    state = load_state(root)

    if getattr(args, "session", None):
        if not (session_dir(args.session, root) / "session.json").exists():
            existing = list_session_ids(root)
            raise WorkLogError(
                f"No session {args.session} in work-log/. "
                + (f"Available: {', '.join(existing[-5:])}" if existing
                   else "No sessions recorded yet.")
            )
        return [args.session], f"session {args.session}"

    scope = getattr(args, "scope", "since-last-report")
    if scope == "session":
        current = state.get("current_session")
        if not current:
            recent = list_session_ids(root)
            if not recent:
                raise WorkLogError("No sessions exist yet. Run: worklog.py start")
            current = recent[-1]
        return [current], f"session {current}"

    if scope == "today":
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        ids = [s for s in list_session_ids(root) if s.startswith(today)]
        return ids, "today"

    if scope == "all":
        return list_session_ids(root), "all recorded work"

    ids = unreported_session_ids(root)
    last = state.get("last_report_sent_at")
    label = "since the last report" if last else "all work so far"
    return ids, label


def build_subject(cfg: dict, sessions: list[dict], label: str) -> str:
    prefix = cfg["email"].get("subject_prefix") or ""
    project = cfg["project"].get("name") or "Work Log"
    agg = aggregate(sessions)
    when = date_range_label(agg)
    if len(sessions) == 1 and sessions[0].get("title"):
        core = f"{project} - {sessions[0]['title']} ({when})"
    else:
        core = f"{project} - {agg['session_count']} session(s), {when}"
    return f"{prefix} {core}".strip()


def build_artifacts(cfg: dict, sessions: list[dict], root: Path,
                    headline: str, out_dir: Path | None) -> dict:
    out_dir = out_dir or (worklog_dir(root) / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"work-log-report-{utc_stamp()}"

    attach = cfg["reporting"].get("attach_detail_pdf", True)
    pdf_path, pdf_error = None, None
    if attach:
        try:
            pdf_path = render.render_pdf(sessions, cfg, out_dir / f"{stem}.pdf",
                                         headline=headline)
        except ImportError:
            pdf_error = ("reportlab is not installed, so no PDF was produced. "
                         "Install it with: pip install reportlab")

    html = render.render_email_html(sessions, cfg, headline=headline,
                                    has_attachment=pdf_path is not None)
    text = render.render_email_text(sessions, cfg, headline=headline,
                                    has_attachment=pdf_path is not None)
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")

    return {"html": html, "text": text, "html_path": html_path,
            "pdf_path": pdf_path, "pdf_error": pdf_error}


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_init(args) -> int:
    root = find_root()
    base = worklog_dir(root)
    base.mkdir(parents=True, exist_ok=True)

    cfg_path = config_path(root)
    created = False
    if not cfg_path.exists() or args.force:
        template = json.loads((ASSETS / "worklog.config.example.json").read_text())
        template["project"]["name"] = args.project or root.name
        cfg_path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        created = True

    # Sessions and config are committed so the log is shared history. Local
    # bookkeeping and generated PDFs are not - they are per-machine and would
    # only produce merge conflicts and repo bloat.
    gitignore = base / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Local bookkeeping: which sessions this machine has already emailed.\n"
            ".worklog-state.json\n\n"
            "# Generated report artifacts. Delete these two lines if you want\n"
            "# the PDFs committed alongside the notes.\n"
            "reports/\n",
            encoding="utf-8",
        )

    readme = base / "README.md"
    if not readme.exists() and (ASSETS / "worklog-readme.md").exists():
        readme.write_text((ASSETS / "worklog-readme.md").read_text(), encoding="utf-8")

    print(f"work-log ready at {base}")
    print(f"  config   {cfg_path} {'(created)' if created else '(already existed)'}")
    print(f"  gitignore{'':<1} {gitignore}")
    print()
    problems = validate_config(load_config(root))
    if problems:
        print("Still needs filling in before mail will send:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("Config looks complete.")
    return 0


def cmd_start(args) -> int:
    root = find_root()
    if not worklog_dir(root).exists():
        raise WorkLogError("work-log/ does not exist yet. Run: worklog.py init")

    state = load_state(root)
    if state.get("current_session") and not args.force:
        print(f"Session {state['current_session']} is already open. "
              f"Use --force to open another anyway.")
        return 0

    session = new_session(title=args.title, root=root)
    save_session(session, root)
    write_notes(session, root)
    state["current_session"] = session["session_id"]
    save_state(state, root)

    print(f"Started {session['session_id']} - {session['title']}")
    print(f"  {session_dir(session['session_id'], root)}")
    return 0


def cmd_log(args) -> int:
    root = find_root()
    state = load_state(root)

    session_id = args.session or state.get("current_session")
    if not session_id:
        # Auto-start rather than erroring: losing a note because no session was
        # open is worse than silently creating one.
        session = new_session(title=args.title or "Untitled session", root=root)
        save_session(session, root)
        state["current_session"] = session["session_id"]
        save_state(state, root)
        session_id = session["session_id"]
        print(f"(no open session - started {session_id})")

    session = load_session(session_id, root)

    if args.json or args.json_file or args.stdin:
        if args.json:
            payload = json.loads(args.json)
        elif args.json_file:
            payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        else:
            payload = json.loads(sys.stdin.read())
        raw_entries = payload if isinstance(payload, list) else [payload]
    else:
        raw_entries = [{
            "summary": args.summary,
            "detail": args.detail,
            "status": args.status,
            **{field: _split(getattr(args, field)) for field in LIST_FIELDS},
        }]

    for raw in raw_entries:
        session["entries"].append(normalize_entry(raw))

    save_session(session, root)
    notes = write_notes(session, root)
    print(f"Logged {len(raw_entries)} entr{'y' if len(raw_entries) == 1 else 'ies'} "
          f"to {session_id} ({len(session['entries'])} total)")
    print(f"  {notes}")
    return 0


def _split(values: list[str] | None) -> list[str]:
    """Accept both repeated flags and comma-separated values in one flag."""
    out: list[str] = []
    for value in values or []:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def cmd_end(args) -> int:
    root = find_root()
    state = load_state(root)
    session_id = args.session or state.get("current_session")
    if not session_id:
        raise WorkLogError("No open session to end.")

    session = load_session(session_id, root)
    session["ended_at"] = now_iso()
    if args.summary:
        session["summary"] = args.summary
    if args.title:
        session["title"] = args.title
    save_session(session, root)
    write_notes(session, root)

    state["current_session"] = None
    save_state(state, root)
    print(f"Closed {session_id} ({len(session['entries'])} entries)")

    cfg = load_config(root)
    reporting = cfg["reporting"]
    if args.no_send:
        print("Auto-email skipped (--no-send).")
        return 0
    if not reporting.get("auto_email_enabled"):
        print("Auto-email is off (reporting.auto_email_enabled = false).")
        return 0
    if reporting.get("mode") != "per_session":
        pending = len(unreported_session_ids(root))
        print(f"Mode is end_of_day - holding this session. "
              f"{pending} session(s) waiting. Send with: "
              f"python scripts/worklog.py send")
        return 0

    print("Auto-email is on and mode is per_session - sending now.")
    return _do_send(root, cfg, [session_id], f"session {session_id}",
                    args.headline or "", None, dry_run=False)


def cmd_status(args) -> int:
    root = find_root()
    base = worklog_dir(root)
    print(f"Repo root       {root}")
    print(f"Work log        {base} {'' if base.exists() else '(missing - run init)'}")

    if not config_path(root).exists():
        print("Config          missing - run: python scripts/worklog.py init")
        return 0

    cfg = load_config(root)
    smtp = cfg["smtp"]
    auth = smtp["auth"]
    reporting = cfg["reporting"]
    print(f"Project         {cfg['project'].get('name') or '(unset)'}")
    print(f"SMTP            {smtp['server']}:{smtp['port']} ({smtp['security']})")
    auth_label = ("on as " + (auth.get("username") or "?") if auth.get("enabled")
                  else "off (internal relay)")
    print(f"Auth            {auth_label}")
    if auth.get("enabled"):
        import os
        var = auth.get("password_env", "WORKLOG_SMTP_PASSWORD")
        print(f"Password        ${var} {'is set' if os.environ.get(var) else 'is NOT set'}")
    print(f"To              {', '.join(cfg['email'].get('to') or []) or '(none)'}")
    print(f"Cc              {', '.join(cfg['email'].get('cc') or []) or '(none)'}")
    print(f"Auto-email      {'on' if reporting.get('auto_email_enabled') else 'off'}"
          f" | mode={reporting.get('mode')}")

    state = load_state(root)
    print(f"Open session    {state.get('current_session') or 'none'}")
    print(f"Last report     {state.get('last_report_sent_at') or 'never'}")
    pending = unreported_session_ids(root)
    print(f"Unreported      {len(pending)}" + (f" -> {', '.join(pending)}" if pending else ""))

    problems = validate_config(cfg)
    if problems:
        print("\nConfig problems:")
        for problem in problems:
            print(f"  - {problem}")
    return 0


def cmd_report(args) -> int:
    root = find_root()
    cfg = load_config(root)
    ids, label = resolve_scope(args, root)
    sessions = [load_session(s, root) for s in ids if
                (session_dir(s, root) / "session.json").exists()]
    if not sessions:
        print(f"Nothing to report for {label}.")
        return 0

    out = build_artifacts(cfg, sessions, root, args.headline or "",
                          Path(args.out) if args.out else None)
    print(f"Report for {label} ({len(sessions)} session(s)):")
    print(f"  HTML  {out['html_path']}")
    print(f"  PDF   {out['pdf_path'] or out['pdf_error']}")
    print(f"  Subject would be: {build_subject(cfg, sessions, label)}")
    return 0


def cmd_send(args) -> int:
    root = find_root()
    cfg = load_config(root)
    ids, label = resolve_scope(args, root)
    return _do_send(root, cfg, ids, label, args.headline or "",
                    Path(args.out) if args.out else None, dry_run=args.dry_run)


def _do_send(root: Path, cfg: dict, ids: list[str], label: str,
             headline: str, out_dir: Path | None, *, dry_run: bool) -> int:
    sessions = [load_session(s, root) for s in ids
                if (session_dir(s, root) / "session.json").exists()]
    if not sessions:
        print(f"Nothing to send for {label}.")
        return 0

    problems = validate_config(cfg)
    if problems:
        raise WorkLogError(
            "Config is not ready to send:\n  - " + "\n  - ".join(problems)
            + f"\nEdit {config_path(root)}"
        )

    out = build_artifacts(cfg, sessions, root, headline, out_dir)
    subject = build_subject(cfg, sessions, label)
    attachments = [out["pdf_path"]] if out["pdf_path"] else []
    if out["pdf_error"]:
        print(f"warning: {out['pdf_error']}")

    if dry_run:
        print("DRY RUN - nothing sent.")
        print(f"  Subject     {subject}")
        print(f"  Recipients  {', '.join(recipients(cfg))}")
        print(f"  Preview     {out['html_path']}")
        print(f"  Attachment  {out['pdf_path'] or 'none'}")
        return 0

    msg = build_message(cfg, subject, out["html"], out["text"], attachments)
    sent_to = smtp_send(cfg, msg)

    state = load_state(root)
    reported = set(state.get("reported_sessions") or [])
    reported.update(s["session_id"] for s in sessions)
    state["reported_sessions"] = sorted(reported)
    state["last_report_sent_at"] = now_iso()
    save_state(state, root)

    print(f'Sent "{subject}"')
    print(f"  to          {sent_to}")
    print(f"  covering    {len(sessions)} session(s): {', '.join(s['session_id'] for s in sessions)}")
    print(f"  attachment  {out['pdf_path'].name if out['pdf_path'] else 'none'}")
    return 0


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worklog.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create work-log/ and the config file")
    p.add_argument("--project", help="project name for report headers")
    p.add_argument("--force", action="store_true", help="overwrite existing config")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("start", help="begin a session")
    p.add_argument("--title", default="", help="what this session is about")
    p.add_argument("--force", action="store_true", help="start even if one is open")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("log", help="append an item of work")
    p.add_argument("--summary", help="one-line description (shown in the email)")
    p.add_argument("--detail", default="", help="longer prose (PDF only)")
    p.add_argument("--status", default="done",
                   choices=["done", "in-progress", "blocked", "investigated"])
    for field in LIST_FIELDS:
        p.add_argument(f"--{field}", action="append",
                       help=f"{FIELD_LABELS[field]} (repeatable or comma-separated)")
    p.add_argument("--session", help="target a specific session id")
    p.add_argument("--title", help="title if a session has to be auto-started")
    p.add_argument("--json", help="a full entry object (or array) as a JSON string")
    p.add_argument("--json-file", help="path to a JSON file with entry object(s)")
    p.add_argument("--stdin", action="store_true", help="read JSON entries from stdin")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("end", help="close the session and maybe email it")
    p.add_argument("--summary", default="", help="session-level summary paragraph")
    p.add_argument("--title", help="rename the session")
    p.add_argument("--session", help="close a specific session id")
    p.add_argument("--headline", default="", help="lead paragraph for the email")
    p.add_argument("--no-send", action="store_true", help="never auto-email")
    p.set_defaults(func=cmd_end)

    p = sub.add_parser("status", help="show config health and pending sessions")
    p.set_defaults(func=cmd_status)

    for name, help_text in (("report", "build the report without sending"),
                            ("send", "build and email the report")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--scope", default="since-last-report",
                       choices=["session", "today", "since-last-report", "all"])
        p.add_argument("--session", help="report on one specific session id")
        p.add_argument("--headline", default="",
                       help="lead paragraph summarising the period")
        p.add_argument("--out", help="output directory for html/pdf artifacts")
        if name == "send":
            p.add_argument("--dry-run", action="store_true",
                           help="build and preview, but do not send")
        p.set_defaults(func=cmd_send if name == "send" else cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "log" and not (args.summary or args.json
                                      or args.json_file or args.stdin):
        print("error: log needs --summary, or --json/--json-file/--stdin",
              file=sys.stderr)
        return 2
    if getattr(args, "session", None) and not SESSION_ID_RE.match(args.session):
        print(f"error: '{args.session}' is not a session id "
              f"(expected e.g. 2026-07-30-session-01)", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except WorkLogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
