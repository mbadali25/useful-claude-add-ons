# work-log

A running record of work done in this repository, one folder per session.

```
work-log/
â”œâ”€â”€ worklog.config.json          committed â€” SMTP + reporting settings, no secrets
â”œâ”€â”€ .gitignore                   keeps local state and generated PDFs out of git
â”œâ”€â”€ 2026-07-30-session-01/
â”‚   â”œâ”€â”€ notes.md                 human-readable log
â”‚   â””â”€â”€ session.json             structured source of truth
â””â”€â”€ reports/                     generated HTML + PDF (gitignored by default)
```

## Configuring email

Edit `worklog.config.json`.

| Setting | What it does |
| --- | --- |
| `project.name` | Shown in the report header and subject line |
| `project.environment` | Optional qualifier, e.g. `production` |
| `smtp.server` | SMTP hostname |
| `smtp.port` | `587` for STARTTLS, `465` for SSL, `25` for a plain internal relay |
| `smtp.security` | `starttls`, `ssl`, or `none` |
| `smtp.auth.enabled` | `false` for an internal relay that authorises by IP |
| `smtp.auth.username` | Login name when auth is enabled |
| `smtp.auth.password_env` | **Name of the environment variable** holding the password |
| `email.from_address` | Sender address |
| `email.to` | List of recipients |
| `email.cc` | List of cc recipients |
| `reporting.auto_email_enabled` | Master switch for automatic sending |
| `reporting.mode` | `per_session` sends when a session closes; `end_of_day` batches |
| `reporting.attach_detail_pdf` | Attach the full-detail PDF |

### The password is never stored here

This file is committed, and anything committed lives in the clone history
forever. So the config holds only the *name* of an environment variable:

```bash
export WORKLOG_SMTP_PASSWORD='...'
```

If you relay through an internal server that does not require a login, set
`smtp.auth.enabled` to `false` and no password is needed at all.

## Per-session vs end-of-day

With `mode: "per_session"`, closing a session emails that session immediately.

With `mode: "end_of_day"`, sessions accumulate. When you say it's the end of
the day, one report goes out covering everything since the last report â€” which
may span several sessions, or several days if you skipped a day.

Either way, a report is only sent when you ask for it or when auto-email is
switched on; nothing leaves the machine silently by default.
