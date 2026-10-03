---
name: mailgun
description: Operate a Mailgun account end to end through its API - send email (plain, HTML, templates, attachments, scheduled, test mode), receive and read inbound email, pull event logs and delivery reports, read statistics/metrics, and configure everything (domains, DNS verification, routes, webhooks, templates, suppressions like bounces/unsubscribes/complaints, mailing lists, tracking, IPs, API keys, subaccounts). Use this skill whenever the user mentions Mailgun, or asks to send an email, check an inbox on their mail domain, see whether an email was delivered, bounced or opened, get email stats, or change email/domain settings in a setup that uses Mailgun - even if they don't say "Mailgun" by name.
---

# Mailgun

Everything goes through one script: `scripts/mg.py` (Python 3 standard library, no installs).
All 258 Mailgun API operations are listed in `references/endpoints.md`; the shortcuts below
cover the common jobs, and `call` reaches anything else.

## 1. Setup (check first, every session)

The script reads these from environment variables, or from `~/.mailgun.env`:

| Variable | Needed | Value |
|---|---|---|
| `MAILGUN_API_KEY` | yes | the private API key |
| `MAILGUN_DOMAIN` | recommended | default domain, e.g. `mg.example.com` |
| `MAILGUN_REGION` | if EU | `eu` (default `us`) |
| `MAILGUN_FROM` | optional | default sender, e.g. `Me <me@mg.example.com>` |

Never write the API key into this skill, into chat output, or into files the user will share.
If the key is missing, ask the user to put it in `~/.mailgun.env` themselves.

Quick health check: `python3 scripts/mg.py domains`. A 401 usually means the wrong region.

## 2. Send mail

```bash
python3 scripts/mg.py send --to a@x.com --subject "Hi" --text "Body"
python3 scripts/mg.py send --to a@x.com --to b@x.com --subject "Report" --html @report.html --attach q3.pdf
python3 scripts/mg.py send --to a@x.com --template welcome --var name=Ana --tag onboarding
python3 scripts/mg.py send --to a@x.com --subject "Later" --text "..." --deliver-at "Fri, 02 Oct 2026 09:00:00 -0400"
python3 scripts/mg.py send ... --test          # accepted by Mailgun but not delivered
```
Other options: `--cc --bcc --reply-to --inline img.png --header Name=value --data key=value --opt o:tracking=no`.

Before sending real mail, show the user the recipients, subject and a summary of the body
and get a yes. Sending cannot be undone. For bulk sends (more than ~10 recipients) suggest
`--test` first.

## 3. Receive mail

Mailgun has no mailbox. Inbound mail is handled by **routes**. Two ways to read it:

| Method | Needs | Use when |
|---|---|---|
| store() route + poll (built in) | nothing extra | reading mail from here; messages kept ~3 days |
| forward to URL (webhook) | a public HTTPS endpoint | a live app must react instantly |

One-time setup (domain must have Mailgun MX records - check with `domain-check`):
```bash
python3 scripts/mg.py inbox-setup                       # store everything sent to *@MAILGUN_DOMAIN
python3 scripts/mg.py inbox-setup --expression 'match_recipient("support@mg.example.com")' --forward "me@gmail.com"
```
Then:
```bash
python3 scripts/mg.py inbox --hours 24                  # list
python3 scripts/mg.py read <storage-url>                # read one (clean text)
python3 scripts/mg.py read <storage-url> --full         # all fields incl. attachment URLs
python3 scripts/mg.py attachment <attachment-url> out.pdf
```
Details, route expressions, webhook payloads and signature checking: `references/receiving.md`.

## 4. Reports (what happened to messages)

```bash
python3 scripts/mg.py logs --duration 1d                          # recent events
python3 scripts/mg.py logs --duration 7d --event failed           # bounces/failures
python3 scripts/mg.py logs --recipient bob@x.com --duration 3d    # "did Bob get it?"
python3 scripts/mg.py logs --message-id "<id@mg.example.com>"
```
Event names: accepted, delivered, failed, opened, clicked, unsubscribed, complained, stored, rejected.

## 5. Statistics

```bash
python3 scripts/mg.py metrics --duration 30d                       # totals + rates
python3 scripts/mg.py metrics --duration 30d --dimension time      # per day
python3 scripts/mg.py metrics --duration 7d --dimension recipient_provider
python3 scripts/mg.py metrics --duration 30d --tag onboarding
```
Present results as a short table. Flag anything alarming: bounce rate above 2%, complaint
rate above 0.1%, or delivered rate below 95% - these threaten sender reputation.
More on metric names and dimensions: `references/reports-and-stats.md`.

## 6. Configure (anything else)

Find the endpoint, check its parameters, call it:
```bash
python3 scripts/mg.py find webhook
python3 scripts/mg.py describe "POST /v3/domains/{domain}/webhooks"
python3 scripts/mg.py call POST /v3/domains/{domain}/webhooks -f id=delivered -f url=https://x.com/hook
python3 scripts/mg.py call GET /v3/{domain_name}/bounces -q limit=100
python3 scripts/mg.py call PUT /v3/domains/{name}/tracking/open -f active=yes
python3 scripts/mg.py call POST /v1/analytics/metrics --json '{"duration":"1d"}'
```
`{domain_name}`, `{domain}` and `/domains/{name}` placeholders are filled from `--domain` or `MAILGUN_DOMAIN`;
fill any other placeholder (like `{id}`) yourself. `-f` = form field, `-q` = query param,
`--json` = JSON body, `--file field=path` = upload. Check `describe` for which one an endpoint takes.

Common tasks and their endpoints are in `references/configure.md`.

### Safety rules
- DELETE calls are refused unless `--yes` is passed. Only add it after the user confirms.
- Also confirm before: sending, removing suppressions (it re-enables mail to people who
  bounced or complained), changing DNS-affecting domain settings, creating/deleting API keys.
- Prefer non-deprecated endpoints (marked in `endpoints.md`): use Logs instead of Events and
  Metrics instead of Stats, except that reading stored inbound mail still uses Events.

## Output style
Summarise in a compact table; offer the raw JSON (`--json`) only if asked.
