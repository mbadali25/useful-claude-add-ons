---
name: work-log-reporter
description: Keep a per-session work log in a committed work-log/ directory at the repo root, recording what was done with timestamps plus the code, systems, databases, and tables touched — then generate a professionally formatted email report with a detailed PDF attachment and send it over SMTP. Use this skill whenever the user asks to track, log, or journal work; asks for a work summary, status report, daily report, or standup writeup; says "log this", "note what we did", "end of day", "EOD report", "wrap up", "send the report", or "email my manager what I worked on"; or asks to set up work logging, configure SMTP for reports, or change who reports go to. Also start using it proactively at the beginning of a working session if a work-log/ directory already exists in the repository, since a log written after the fact is always worse than one written as the work happens.
---

# Work Log Reporter

Records work as it happens, then turns it into a report someone else will
actually read.

The value of this skill lives almost entirely in the quality of what gets
logged. A log that says "fixed the bug" is worthless three weeks later; a log
that says "added a partial index on `orders.customer_id` because the dashboard
query was doing a seq scan on 40M rows" is still useful a year later. Aim for
the second kind.

## The command

Everything runs through one CLI. Substitute the real path to this skill's
`scripts/` directory:

```bash
python scripts/worklog.py <init|start|log|end|status|report|send> [flags]
```

Run `python scripts/worklog.py <command> -h` for the flags on any command.
The CLI finds the repository root by walking up for `.git`, so it can be run
from anywhere inside the repo. Set `WORKLOG_ROOT` to override that if you are
in a workspace that is not a git repo.

## The shape of a working session

### 1. Check the ground first

Run `status` before anything else. It tells you whether `work-log/` exists,
whether the config is complete, whether a session is already open, and how many
sessions are waiting to be reported.

```bash
python scripts/worklog.py status
```

If `work-log/` does not exist, run `init`, then walk the user through the
config — see [Setting up email](#setting-up-email) below. Do not start logging
into an unconfigured repo and hope it works out; a five-line conversation up
front avoids a failed send at 6pm.

### 2. Open a session

```bash
python scripts/worklog.py start --title "Fix duplicate order rows in nightly sync"
```

One session is one continuous stretch of work with a coherent goal. If the
user comes back after lunch to work on something unrelated, that is a second
session, and the folder naming (`2026-07-30-session-01`, `-02`) handles it.

Give the title real content. It becomes the email subject line when the report
covers a single session, so "Fix duplicate order rows in nightly sync" earns
its place and "Tuesday work" does not.

### 3. Log as you go

This is the part that matters. Append an entry as each meaningful piece of work
completes — not at the end, when the specifics have already blurred.

```bash
python scripts/worklog.py log \
  --summary "Added a unique constraint to stop duplicate order rows" \
  --detail "The nightly sync was upserting on order_number alone, so orders
resubmitted with a new revision created a second row. Added a composite unique
index on (order_number, revision) and made the upsert target it." \
  --code "src/sync/orders.py:118-164,migrations/0042_order_unique_idx.sql" \
  --systems "order-sync-service,prod-k8s" \
  --databases "warehouse_pg" \
  --tables "public.orders,public.order_revisions" \
  --commands "alembic upgrade head" \
  --tickets "OPS-1421"
```

**What each field is for**, and why the distinction is worth respecting:

| Field | Holds | Why it is separate |
| --- | --- | --- |
| `--summary` | One line, plain language | This is what appears in the email body. Write it for someone who was not there. |
| `--detail` | The reasoning, the cause, the tradeoff | Goes in the PDF only, so it can be as long as it needs to be. |
| `--code` | Files, functions, line ranges | Lets a reviewer jump straight to the change. |
| `--systems` | Services, hosts, environments, queues | Answers "what could this have affected?" during an incident. |
| `--databases` | Database or cluster names | Separate from tables so a DBA can filter on it. |
| `--tables` | Schema-qualified table names | The single most useful field for anyone tracing a data problem later. |
| `--commands` | Migrations, deploys, scripts actually run | The audit trail. Include what you ran, not what you considered running. |
| `--tickets` | Ticket IDs, PR links, incident numbers | Ties the log to the tracker. |
| `--status` | `done`, `in-progress`, `blocked`, `investigated` | Defaults to `done`. Use `blocked` honestly — a report that hides blockers is worse than no report. |

List flags accept comma-separated values or repeated flags, whichever is
cleaner. For entries with awkward quoting, or to write several at once, use
`--json '{"summary": "...", "tables": ["public.orders"]}'` or `--stdin`.

Schema-qualify table names (`public.orders`, not `orders`). It costs nothing
now and removes real ambiguity later when someone greps the log.

Log investigation too, not just changes. "Ruled out the connection pool as the
cause — pool metrics were flat through the incident window" is genuinely
valuable to the next person, and time spent looking is still time spent.

### 4. Close the session

```bash
python scripts/worklog.py end --summary "Duplicate orders traced to an incomplete
upsert key. Constraint added and backfill run; the nightly job has been clean
for two cycles since."
```

The session summary is a short paragraph tying the entries together — the
narrative, not a restatement of the bullets. Write it yourself rather than
concatenating the entry summaries; the whole point is the connective tissue
the individual entries lack.

`end` writes `notes.md` and `session.json`, then checks the config: if
auto-email is on and the mode is `per_session`, it sends immediately. If the
mode is `end_of_day` it holds the session and tells you how many are pending.

## Reporting

### End of day

When the user says it is the end of the day, or asks to send the report, the
default scope covers everything since the last report went out:

```bash
python scripts/worklog.py send --headline "Two sessions today, both on the order
sync duplicate-row incident. Root cause found and fixed; monitoring for one
more cycle before closing OPS-1421."
```

That is the batching behaviour: if three sessions have accumulated since the
last email — or two days' worth because yesterday's report never went out —
they all go in one report, and only then are they marked as reported.

The `--headline` is the lead paragraph, set apart at the top of the email. Use
it to say what a reader should take away before they read anything else. It is
optional, but a report without one asks the reader to synthesise, which is
work you should be doing for them.

Other scopes when needed: `--scope session` (most recent), `--scope today`,
`--scope all`, or `--session 2026-07-30-session-01` for one specific folder.

### Preview before sending

Two safe options. `report` builds the HTML and PDF without touching SMTP;
`send --dry-run` additionally shows the exact subject and recipient list.

```bash
python scripts/worklog.py send --dry-run
```

Offer a preview the first time a report goes out in a repo, and any time the
recipient list includes someone outside the immediate team. Read the generated
HTML file to check the content before it lands in a manager's inbox.

### What the report looks like

The email body carries the high-level story: header with project and date
range, a summary strip of counts, the headline, then a card per session with
its entry summaries and colour-coded chips for the systems, databases, tables,
and code touched. The PDF attachment carries everything — full `--detail`
prose, exact commands, and complete field listings per entry.

That split is deliberate, so keep it in mind when writing entries: a `summary`
that only makes sense next to its `detail` will read as a non-sequitur in the
email. Each summary should stand on its own.

## Setting up email

`init` creates `work-log/worklog.config.json` from a template. Walk the user
through it rather than guessing values — you cannot know their mail server.

```bash
python scripts/worklog.py init --project "warehouse-api"
```

Ask for: SMTP server and port, whether the server requires a login, the from
address, and the to/cc lists. Then set `reporting.mode` based on how they want
reports — per session or batched to end of day — and flip
`reporting.auto_email_enabled` on only once a dry run has succeeded.

**The password never goes in the config file.** `work-log/` is committed, and a
credential in a committed file is in the clone history permanently. The config
holds only the *name* of an environment variable:

```bash
export WORKLOG_SMTP_PASSWORD='...'
```

For an internal relay that authorises by IP rather than credentials, set
`smtp.auth.enabled` to `false` and no password is involved at all. If a user
asks you to put a password directly in the config, explain why that is a bad
trade and offer the environment variable or the no-auth relay instead.

Port and security pair up predictably: `587` with `starttls`, `465` with
`ssl`, `25` with `none` for an internal relay.

For the full config reference, read `references/configuration.md`. Read it when
setting up for the first time, changing transport settings, or debugging a
failed send — the troubleshooting table there covers the common SMTP errors and
what each one actually means.

## What gets committed

Sessions and the config are committed, so the log is shared history the whole
team can read. `init` writes a `work-log/.gitignore` that excludes the local
state file (which machine has emailed which sessions — per-machine bookkeeping
that would only cause merge conflicts) and the `reports/` directory of
generated PDFs. Mention this to the user; if they want the PDFs committed as an
archive, deleting two lines from that file is all it takes.

## Judgement calls

**Do not send without being asked.** Auto-email exists and is off by default,
which is the right default — a report leaving the machine is a message to a
real person. Send when the user asks, or when they have explicitly enabled
auto-email and closed a session under `per_session` mode.

**Do not invent entries.** Log what actually happened in the session. If asked
to reconstruct work from earlier that you were not present for, ask the user
what they did rather than inferring it from the diff — a work log that quietly
contains guesses is worse than a short one.

**Redact before logging.** Connection strings, tokens, customer PII, and
production credentials sometimes appear in the middle of real debugging work.
They must not end up in a committed log or an email. Log the shape of the
thing — "rotated the API token for the billing webhook" — never the value.

**Keep it proportional.** A ten-minute typo fix does not need six fields and a
detail paragraph. A schema migration on a production table does.
