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

There are two ways to reach ServiceDesk Plus. **The MCP server is the default —
reach for it first, every time, and treat `ticketctl.py` as the fallback.**

1. **The SDP MCP server — the default.** Tools named `sdp_*`, served by
   `https://sdp-mcp.solomoninsight.com/mcp` and registered in Claude Code as the
   connector "Solomon Service Desk Plus". **Writes are enabled.** It acts as the
   signed-in user, so SDP's own audit trail names that person rather than a
   shared service account — which is *why* it is the default and not merely a
   preference. A ticket created here is attributable; one created through a
   service account is not.
2. **`scripts/ticketctl.py` — the fallback.** Python 3.8+, standard library only,
   identical on Windows and Linux. Holds its own credentials, and is still the
   **only** path to Jira and to email, so it never goes away entirely.

**Check that the `sdp_*` tools are actually loaded before calling one** — a call
to a tool that is not present just fails. But do not read their absence as "MCP
is not available here": the connector is registered centrally and authenticated
per person, so the usual cause is an unauthenticated session, not a missing
server. "The MCP server" under Setup covers how to tell those apart, and what to
do about it in the same turn.

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

## Choosing a path

Routing lives in the `mcp` block of the config file, so the skill and the script
agree on one answer:

```json
"mcp": {
  "enabled": true,
  "prefer_mcp": true,
  "connector_name": "Solomon Service Desk Plus",
  "endpoint": "https://sdp-mcp.solomoninsight.com/mcp",
  "health_url": "https://sdp-mcp.solomoninsight.com/health",
  "tool_prefix": "sdp_",
  "fallback_provider": "zoho_sdp",
  "scrub_before_write": true
}
```

`python scripts/ticketctl.py doctor` prints the resolved routing, including a
health probe of the connector. **No credentials go in this block** - the
connector authenticates each person separately through Claude Code, which is the
whole point of preferring it.

Setting `prefer_mcp` to `false` (or `INFRA_TICKET_PREFER_MCP=false` for one
session) makes `ticketctl.py` the primary path. Do that only when the connector
is genuinely unavailable to everyone, not because one session failed to
authenticate.

**Default to the `sdp_*` tools.** Check once per conversation whether they are
loaded; if they are, every row below goes through MCP and `ticketctl.py` is not
consulted at all except for the two jobs it alone can do (email, Jira) and for
the secret scrub described below. Never announce which path you took — the user
cares about the ticket, not the transport.

| Job | Preferred | Fall back to |
| --- | --- | --- |
| Look up a ticket | `sdp_get` | `ticketctl.py get` |
| Find existing tickets | `sdp_search` | `ticketctl.py search` |
| Read the discussion | `sdp_list_notes` | `ticketctl.py get` |
| Open a ticket | `sdp_create` | `ticketctl.py create` |
| Add a work note | `sdp_add_note` | `ticketctl.py note` |
| Log time | `sdp_add_worklog` | no equivalent - skip |
| Send email | none | `ticketctl.py notify` / `--email` |
| Anything in Jira | none | `ticketctl.py --provider jira` |

**Writes are enabled on the Solomon server**, so `sdp_create` and
`sdp_add_note` are the normal path - use them without hesitating and without
asking permission to use one transport over another.

**Fall back on refusal, not just on absence.** Writes are a flag an
administrator can turn off again, so a tool may answer *"Writes are disabled on
this server, so nothing was changed"*. That is a routing signal, not an error to
report. Run the same operation through `ticketctl.py` and carry on. Telling
someone they cannot have a ticket, when a working path is sitting right there,
is the one outcome this skill exists to prevent.

The same applies to `module=asset`: CMDB writes are gated separately and can
refuse on their own. Fall back rather than giving up.

Fall back the same way if a tool reports no linked account - though offer the
link too, since `sdp_link_account` fixes it permanently in about two minutes.

### Scrub before writing through MCP

`ticketctl.py` strips secrets from every note it sends. **The MCP server does
not.** So when writing through `sdp_create` or `sdp_add_note`, scrub the text
first:

```
python scripts/ticketctl.py redact-check --body-file note.md --emit > note.clean.md
```

`--emit` puts only the scrubbed body on stdout, findings on stderr. Send
`note.clean.md`. Do not use `--show` for this - it prints headings that would end
up inside the ticket.

This is not optional, and it is not a formality. Notes routinely quote command
output, and command output routinely contains a token.

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
sdp_get      module=request  id=40219        # preferred
python scripts/ticketctl.py get --ticket OPS-412   # fallback
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
sdp_search   module=request  value="SQL01 RAID"  open_only=true    # preferred
python scripts/ticketctl.py search --text "SQL01 RAID" --open-only  # fallback
```

`open_only` matters more than it looks: this desk has three terminal statuses
(Closed, "Closed - Unable to resolve", Canceled), and a hand-written
`status is not Closed` filter leaves finished tickets in the results. Let the
flag do it.

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
# preferred - scrub first, the MCP server has no scrubber of its own
python scripts/ticketctl.py redact-check --body-file note.md --emit > note.clean.md
sdp_add_note module=request id=40219 note=<contents of note.clean.md> public=false

# fallback - ticketctl scrubs on the way through
python scripts/ticketctl.py note --ticket OPS-412 --body-file note.md
```

Write the note to a file first either way. Multi-line text as a shell argument
breaks differently in PowerShell and bash, and quoting bugs silently truncate
the record. `--body-file -` reads stdin. `--body "short text"` is fine for
one-liners.

Keep `public=false` unless the requester is meant to see it and be emailed. A
work note that reads fine internally often reads badly to the person who raised
the ticket.

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
exported. `ticketctl.py` scrubs obvious secrets automatically - private keys, AWS
keys, bearer tokens, `password=` assignments, credentials embedded in URLs and
connection strings - and reports on stderr what it masked. That safety net is
not a licence to be careless: leave secrets out of the text in the first place,
and describe them instead ("rotated the service account password", not the
password). To preview: `python scripts/ticketctl.py redact-check --body-file note.md --show`.

**Don't fabricate.** If you don't know whether a verification step passed, say
the work was done and verification is pending. A confidently wrong note is worse
than a thin one, because someone will rely on it.

**Never invent a ticket number.** If a `ticketctl.py` write fails, it queues the
text locally instead of losing it; tell the user to run
`python scripts/ticketctl.py retry` once the problem is fixed.

**The MCP server has no such queue.** A failed `sdp_add_note` is simply gone.
When an MCP write fails for any reason other than the disabled-writes refusal,
re-send the same file through `ticketctl.py note` rather than retrying the MCP
call - that way a second failure is captured rather than lost.

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

### The MCP server

**Endpoint:** `https://sdp-mcp.solomoninsight.com/mcp`, registered in Claude Code
as the connector "Solomon Service Desk Plus".

Two halves, configured in different places. **Authentication** is not configured
from inside this skill at all - the connector is registered centrally and each
person signs in through Claude Code. **Routing** is: the `mcp` block in the
config file records the connector name, endpoint, tool prefix, whether to prefer
it, and where to fall back. Changing that block changes which transport this
skill reaches for; it cannot grant or revoke access to the server.

**If the `sdp_*` tools are not loaded, the server is almost certainly registered
but unauthenticated — a two-minute fix, not a reason to abandon MCP.** Tell the
two states apart with `claude mcp list`, which prints one of:

```
claude.ai Solomon Service Desk Plus: https://sdp-mcp.solomoninsight.com/mcp - ✔ Connected
claude.ai Solomon Service Desk Plus: https://sdp-mcp.solomoninsight.com/mcp - ! Needs authentication
```

On `! Needs authentication`, do both of these in the same turn: tell the user to
authenticate the connector (`/mcp` in Claude Code), and use `ticketctl.py` for
the work in front of you rather than stalling on it. **Do not conclude from one
unauthenticated session that `ticketctl.py` should be the default** — that
inverts the attribution guarantee this skill exists to preserve.

Each person also links their own Zoho account once via `sdp_link_account`. If a
tool reports no linked account, that is the fix - it takes about two minutes and
is permanent.

Two things the administrator controls: whether writes are enabled at all, and
whether asset/CMDB writes are. Both are currently ON for the Solomon server.
Either being turned off shows up as a refusal message, which is a signal to fall
back rather than a problem to solve. `GET https://sdp-mcp.solomoninsight.com/health`
reports both without needing a token. Repository: `service-desk-plus-mcp` in
`aws-managed-services`.

### ticketctl.py

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
| `redact-check --body-file F --emit` | Print only the scrubbed text, for piping into an MCP write |

Useful flags: `--dry-run` prints the exact request without sending it or needing
credentials - reach for it whenever you're unsure what a command will do.
`--json` gives machine-readable output. `--provider zoho_sdp|jira` overrides the
configured platform for one call. `--email a@b,c@d` notifies on create/note.
`--type`, `--priority`, `--project`, `--labels`, `--group`, `--category` override
the configured defaults per ticket.
