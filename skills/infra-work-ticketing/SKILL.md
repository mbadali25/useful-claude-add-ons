---
name: infra-work-ticketing
description: Makes sure infrastructure work gets a ticket and gets logged, in Zoho ServiceDesk Plus Cloud or Jira Cloud. Use this skill whenever the user is doing real work on servers, AWS, Azure, GCP, databases, Active Directory, DNS, networking, virtualization, backups, Windows or Linux server configuration, Kubernetes, CI/CD, Terraform, Ansible, monitoring, patching, firewalls, VPNs, certificates, storage, or any other DevOps/sysadmin task - even if they never mention tickets, Jira, ServiceDesk Plus, or change control. Ask whether a ticket exists, log the work as a note on the ticket they name, or open one for them if they don't have one. Also use it when the user asks to log work, add a work note, update a ticket, email an update about a ticket, or set up the ticket integration.
---

# Infrastructure work ticketing

Infrastructure work that isn't ticketed is invisible: nobody can audit it, nobody
can hand it off, and nobody can reconstruct what changed when something breaks
three weeks later. This skill closes that gap by capturing the work as it
happens, while the details are still fresh, rather than asking someone to
remember it at the end of the day.

The tool is `scripts/ticketctl.py` - Python 3.8+, standard library only,
identical behaviour on Windows and Linux.

## When to log, and when to stay out of the way

Log **work performed on real systems**: changes, investigations, incident
response, migrations, provisioning, patching, config edits, troubleshooting a
specific host or resource.

Do **not** trigger on questions, explanations, or hypotheticals. "How does an
Azure NSG evaluate priority?", "what's the difference between a CNAME and an
ALIAS?", or "review this Terraform module for style" are conversations, not work
on infrastructure. Prompting for a ticket there is pure friction and trains the
user to ignore you.

The line is whether a named piece of real infrastructure is being touched or
diagnosed. If the user says "DC01 is refusing LDAP binds" that's work. If they
say "how do I diagnose LDAP bind failures generally?" it isn't - though if they
then start running commands against DC01, it has become work.

## The flow

### 1. Ask once, early, briefly

The first time infrastructure work appears in a conversation, ask a single
question. Don't preface it with a paragraph about change management.

> Quick one before I dig in - do you have a ticket for this, or should I open one?

If an interactive option picker is available, use it with options like
"I have a ticket" / "Open one for me" / "Skip ticketing" rather than making them
type.

Then **remember the answer for the rest of the conversation**. Re-asking is the
fastest way to make this skill annoying. If they say skip, stay silent about
ticketing unless they raise it. If they go quiet on the question but keep
working, help them with the work and ask again once at a natural pause - not
every turn.

Help with the actual work regardless of whether the ticket question is settled.
The work is the point; the ticket is bookkeeping that should never block it.

### 2a. They have a ticket

Take the number in whatever form they give it - `OPS-412`, `40219`, `#40219`, or
a pasted URL. Verify it before writing to it, so a typo doesn't dump work notes
into a stranger's ticket:

```
python scripts/ticketctl.py get --ticket OPS-412
```

Show them the title in one line and carry on. If the title looks unrelated to
what they're doing, say so and ask - a mismatch usually means a transposed digit.

### 2b. They don't have a ticket

Open one yourself. Infer the title and description from the conversation - that
inference is the main thing this skill is for, so don't punt it back to the user
when the answer is already on screen.

Before creating, check for an existing ticket covering the same work so you don't
duplicate a colleague's:

```
python scripts/ticketctl.py search --text "SQL01 RAID" --open-only
```

If you're confident about what the work is, create the ticket and report what you
made in the same turn - no confirmation round-trip. Tickets are editable and a
follow-up note can correct anything.

Ask first only when a fact you genuinely need is missing and unguessable. The
things actually worth asking about:

- **Which system**, when the target is ambiguous ("the database server" and
  there are four)
- **Which environment** - prod versus staging changes who cares and how urgent
  it is
- **Whether this is planned or an incident** - it changes the ticket type and
  often the priority
- **Who requested it**, if the work came from someone else and that matters for
  your workflow

Ask about at most two of these in one go, and only the ones you can't infer.
Never ask for something the user already told you.

### 3. Write notes as the work progresses

Notes are the running record. Add one at each meaningful checkpoint - not after
every command, and not only once at the very end where detail has already been
lost. Good moments: a change actually applied, a root cause found, a
verification passed, a rollback performed, work paused or handed off.

```
python scripts/ticketctl.py note --ticket OPS-412 --body-file note.md
```

Write the note to a file first and pass `--body-file`. Multi-line text as a
shell argument breaks differently in PowerShell and bash, and quoting bugs
silently truncate the record. `--body-file -` reads stdin. `--body "short text"`
is fine for one-liners.

At the end of a work session, add a closing note summarising what changed and
how it was verified, even if you added notes along the way. That summary is what
someone reads first during the next incident.

### 4. Email only when asked

Notifications go out only when the user asks for them. Add `--email` to `create`
or `note`, or send a standalone message with `notify`:

```
python scripts/ticketctl.py note --ticket OPS-412 --body-file note.md --email "manager@solomoninsight.com"
python scripts/ticketctl.py notify --ticket OPS-412 --subject "SQL01 back online" --body-file summary.md --to "helpdesk@solomoninsight.com"
```

The two platforms differ in a way worth knowing: ServiceDesk Plus adds the
addresses to the request's notify list, so they receive this and subsequent
activity. Jira can only email people who have an account on the site, and will
warn about any address it can't resolve. Pass that warning along rather than
letting the user believe a message went out.

## Writing tickets people can actually use

Format matters less than being specific. A title with no hostname in it is
nearly useless in a queue of two hundred.

**Titles** - system, then what happened, under about 80 characters:

- `SQL01 - RAID array rebuild after disk 2 failure`
- `DC02 - LDAP binds failing after July patch cycle`
- `AWS prod - RDS instance resized db.t3.large to db.r6g.xlarge`
- Not: `Server issue`, `Fixed the database`, `Azure work`

**Descriptions and notes** - lead with what changed, then evidence. `--body-file`
accepts plain text with light markdown (`##` headings, `- ` bullets, triple-
backtick code blocks); it is converted to HTML for ServiceDesk Plus and to
Atlassian Document Format for Jira automatically.

A shape that holds up well:

```
## What changed
Replaced failed disk in bay 2 on SQL01 and rebuilt the RAID 10 array.

## Why
Disk 2 reported predictive failure in the RAID controller log at 08:14.

## Steps taken
- Confirmed array was degraded, not failed
- Hot-swapped the disk
- Rebuild ran 4h12m and completed clean

## Verification
No unhealthy disks reported; SQL Server services came back automatically
and the nightly backup succeeded.

## Impact / rollback
No downtime. Rollback would have been reseating the original disk.
```

Include real specifics - hostnames, IPs, resource IDs, KB numbers, change
windows, error text, command output. Vague notes are the same as no notes.

More patterns and per-platform examples: `references/writing-tickets.md`.

## Guardrails

**Never write credentials into a ticket.** Tickets are widely readable and often
exported. The tool scrubs obvious secrets automatically - private keys, AWS
keys, bearer tokens, `password=` assignments, credentials embedded in URLs and
connection strings - and reports on stderr what it masked. That safety net is
not a licence to be careless: leave secrets out of the text in the first place,
and describe them instead ("rotated the service account password", not the
password). To preview: `python scripts/ticketctl.py redact-check --body-file note.md --show`.

**Don't fabricate.** If you don't know whether a verification step passed, say
the work was done and verification is pending. A confidently wrong note is worse
than a thin one, because someone will rely on it.

**Never invent a ticket number.** If a write fails, the tool queues the text
locally instead of losing it; tell the user to run
`python scripts/ticketctl.py retry` once the problem is fixed.

**Sensitive work still gets logged, carefully.** Security incidents, terminations,
and investigations belong in tickets too - just describe actions and systems
without personal detail that doesn't need to be there.

## Setup

If the tool has never been configured, or any command reports a missing config,
run the doctor and follow it:

```
python scripts/ticketctl.py doctor
```

It prints exactly which fields are missing and tests authentication. To start
from scratch: `python scripts/ticketctl.py init`, then edit the file it names.

Full setup walkthroughs, both with Windows and Linux/macOS command variants:

- `references/setup-zoho-sdp.md` - Zoho ServiceDesk Plus Cloud OAuth
  (`https://ithelpdesk.solomoninsight.com`)
- `references/setup-jira.md` - Jira Cloud API token and OAuth 2.0 3LO
  (`https://solomondevteam.atlassian.net`)
- `references/configuration.md` - every config field, environment variable
  overrides, config file locations, and troubleshooting

Read the relevant reference file before walking a user through setup rather than
guessing at console navigation - both vendors move their UI around, and the
files record the exact scopes and URL shapes that work.

## Command reference

Run from the skill directory, or use the full path to the script.

| Command | Purpose |
| --- | --- |
| `doctor` | Validate config, test auth, report queued writes |
| `init` | Write a config template |
| `create --title T --body-file F` | Open a ticket |
| `note --ticket ID --body-file F` | Add a work note |
| `get --ticket ID` | Show a ticket and recent notes |
| `search --text T [--open-only] [--mine]` | Find tickets before duplicating one |
| `notify --ticket ID --subject S --body-file F --to A` | Send an email |
| `worklog` | What this tool logged locally |
| `retry` | Replay writes that failed earlier |
| `redact-check --body-file F --show` | Preview the secret scrubber |

Useful flags: `--dry-run` prints the exact request without sending it or needing
credentials - reach for it whenever you're unsure what a command will do.
`--json` gives machine-readable output. `--provider zoho_sdp|jira` overrides the
configured platform for one call. `--email a@b,c@d` notifies on create/note.
`--type`, `--priority`, `--project`, `--labels`, `--group`, `--category` override
the configured defaults per ticket.
