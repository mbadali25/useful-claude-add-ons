# Configuration reference

Contents:
1. [File locations](#file-locations)
2. [Config schema](#config-schema)
3. [Transport recipes](#transport-recipes)
4. [Credentials](#credentials)
5. [Reporting modes and state](#reporting-modes-and-state)
6. [Data formats on disk](#data-formats-on-disk)
7. [Troubleshooting](#troubleshooting)

## File locations

Everything lives under `work-log/` at the repository root. Root detection
walks up from the working directory looking for `.git` or an existing
`work-log/`; `WORKLOG_ROOT` overrides it for non-git workspaces.

| Path | Committed | Purpose |
| --- | --- | --- |
| `work-log/worklog.config.json` | yes | All settings. No secrets. |
| `work-log/README.md` | yes | Explains the setup to humans browsing the repo. |
| `work-log/.gitignore` | yes | Excludes the two entries below. |
| `work-log/.worklog-state.json` | no | Open session, last-report time, reported session ids. |
| `work-log/reports/` | no | Generated HTML and PDF artifacts. |
| `work-log/<date>-session-NN/session.json` | yes | Structured source of truth. |
| `work-log/<date>-session-NN/notes.md` | yes | Human-readable view, regenerated from session.json. |

`notes.md` is derived. Edits to it are overwritten on the next `log` call —
change `session.json` instead, or re-log the entry.

## Config schema

```json
{
  "project": {
    "name": "warehouse-api",
    "environment": "production"
  },
  "smtp": {
    "server": "smtp.company.com",
    "port": 587,
    "security": "starttls",
    "timeout_seconds": 30,
    "auth": {
      "enabled": true,
      "username": "svc-worklog@company.com",
      "password_env": "WORKLOG_SMTP_PASSWORD"
    }
  },
  "email": {
    "from_address": "svc-worklog@company.com",
    "from_name": "Work Log Reporter",
    "to": ["lead@company.com"],
    "cc": ["pm@company.com"],
    "subject_prefix": "[Work Log]"
  },
  "reporting": {
    "auto_email_enabled": false,
    "mode": "end_of_day",
    "attach_detail_pdf": true,
    "include_commands_in_pdf": true
  }
}
```

| Key | Type | Notes |
| --- | --- | --- |
| `project.name` | string | Header, subject line, PDF footer. Defaults to the repo directory name at init. |
| `project.environment` | string | Optional qualifier shown next to the name. |
| `smtp.server` | string | Hostname. |
| `smtp.port` | int | 1–65535. |
| `smtp.security` | enum | `starttls` \| `ssl` \| `none`. |
| `smtp.timeout_seconds` | int | Socket timeout. Raise it on slow corporate relays. |
| `smtp.auth.enabled` | bool | `false` skips login entirely. |
| `smtp.auth.username` | string | Required when auth is enabled. |
| `smtp.auth.password_env` | string | Name of the env var, never the password. |
| `email.from_address` | string | Some relays require this to match the auth user. |
| `email.from_name` | string | Display name. |
| `email.to` | array | At least one address, or sending fails validation. |
| `email.cc` | array | May be empty. |
| `email.subject_prefix` | string | Prepended to every subject. |
| `reporting.auto_email_enabled` | bool | Master switch. Off by default. |
| `reporting.mode` | enum | `per_session` \| `end_of_day`. |
| `reporting.attach_detail_pdf` | bool | Off means the email goes alone. |
| `reporting.include_commands_in_pdf` | bool | Set false where command history is sensitive. |

Unknown keys are preserved. Missing keys fall back to defaults, so a partial
config is valid — but `validate_config` will still block a send if the fields
that actually matter for delivery are unset.

## Transport recipes

**Hosted provider, STARTTLS** — the common case.

```json
{ "server": "smtp.gmail.com", "port": 587, "security": "starttls",
  "auth": { "enabled": true, "username": "you@company.com",
            "password_env": "WORKLOG_SMTP_PASSWORD" } }
```

Google and Microsoft both require an app password rather than the account
password when 2FA is on.

**Implicit SSL**

```json
{ "server": "smtp.company.com", "port": 465, "security": "ssl",
  "auth": { "enabled": true, "username": "...", "password_env": "..." } }
```

**Internal relay, no authentication** — authorised by source IP.

```json
{ "server": "mailrelay.internal", "port": 25, "security": "none",
  "auth": { "enabled": false } }
```

With `auth.enabled: false` no environment variable is read and no password is
needed. This is the right configuration for a relay inside a trusted network;
it is the wrong configuration for anything reachable from the internet.

## Credentials

The password is read from the environment variable named in
`smtp.auth.password_env`, and from nowhere else. There is deliberately no
config field to hold it, because `work-log/` is committed and a secret in a
committed file remains in the history after it is deleted.

```bash
export WORKLOG_SMTP_PASSWORD='...'
```

For persistence, put it in a shell profile, a CI secret store, a `.env` file
that is gitignored at the repo root, or a secret manager that exports into the
environment. Confirm it is visible to the process with
`python scripts/worklog.py status`, which reports whether the variable is set
without printing its value.

## Reporting modes and state

`.worklog-state.json`:

```json
{
  "current_session": "2026-07-30-session-02",
  "last_report_sent_at": "2026-07-29T17:48:00-05:00",
  "reported_sessions": ["2026-07-28-session-01", "2026-07-29-session-01"]
}
```

`reported_sessions` is what makes end-of-day batching correct rather than
approximate. The default `since-last-report` scope is the set difference
between the session folders on disk and this list, so a day when no report went
out is picked up by the next one instead of being silently skipped. Sessions
are added to the list only after SMTP accepts the message — a failed send
leaves them pending, and retrying sends the same content.

`per_session` mode sends at `end`. `end_of_day` mode accumulates and waits for
an explicit `send`. In both cases `auto_email_enabled: false` blocks automatic
delivery entirely while leaving manual `send` available.

Scopes for `report` and `send`:

| Scope | Covers |
| --- | --- |
| `since-last-report` (default) | Every session not yet included in a sent report. |
| `session` | The open session, or the most recent one if none is open. |
| `today` | All sessions dated today, reported or not. |
| `all` | Every session ever recorded. |
| `--session <id>` | Exactly one folder. |

Only `send` updates state. `report` is always read-only, which is why it is
safe to run repeatedly while iterating on a headline.

## Data formats on disk

`session.json`:

```json
{
  "session_id": "2026-07-30-session-01",
  "title": "Fix duplicate order rows in nightly sync",
  "started_at": "2026-07-30T09:12:04-05:00",
  "ended_at": "2026-07-30T11:40:19-05:00",
  "summary": "Duplicate orders traced to an incomplete upsert key...",
  "entries": [
    {
      "timestamp": "2026-07-30T09:48:11-05:00",
      "summary": "Added a unique constraint to stop duplicate order rows",
      "detail": "The nightly sync was upserting on order_number alone...",
      "status": "done",
      "code": ["src/sync/orders.py:118-164", "migrations/0042_order_unique_idx.sql"],
      "systems": ["order-sync-service", "prod-k8s"],
      "databases": ["warehouse_pg"],
      "tables": ["public.orders", "public.order_revisions"],
      "commands": ["alembic upgrade head"],
      "tickets": ["OPS-1421"]
    }
  ]
}
```

Timestamps are local ISO 8601 with offset, so a log written in one timezone
still reads correctly elsewhere. `status` is one of `done`, `in-progress`,
`blocked`, `investigated`.

Writing entries programmatically avoids shell quoting problems:

```bash
python scripts/worklog.py log --json '[
  {"summary": "Reindexed the orders table", "tables": ["public.orders"]},
  {"summary": "Verified sync output against source", "status": "done"}
]'
```

`--json-file <path>` and `--stdin` accept the same object or array.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `Auth is enabled but $VAR is not set` | Export the variable in the same shell, or set `smtp.auth.enabled` to `false` for an internal relay. |
| `SMTP rejected the login` | Wrong username, or the provider needs an app-specific password rather than the account password. |
| `[SSL: WRONG_VERSION_NUMBER]` | `security` and `port` disagree. Use `starttls` with 587 and `ssl` with 465. |
| Connection times out | Firewall or VPN. Confirm reachability with `nc -vz <server> <port>` before touching config. |
| `550 relay denied` / `553 sender rejected` | The relay requires `from_address` to match the authenticated user or an allowlisted domain. |
| Send succeeds, nothing arrives | Check spam; many relays quarantine mail whose From domain does not align with SPF/DKIM. Prefer a from address on your own domain. |
| `reportlab is not installed` | `pip install reportlab`. The email still sends, just without the PDF. |
| Report is empty | Every session in scope was already reported. Check `status`, or use `--scope today` / `--session <id>`. |
| `is not a session id` | Session ids look like `2026-07-30-session-01`. List the folders in `work-log/`. |
| Nothing lands in the expected repo | Root detection found a different `.git`. Check the first line of `status` and set `WORKLOG_ROOT` if needed. |
