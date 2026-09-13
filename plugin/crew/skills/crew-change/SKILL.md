---
name: crew-change
description: The change-request template, the ten questions a change board requires, and how each field maps onto ServiceDesk Plus, Jira and a local file. Use when filing, checking or closing a change request, when a production promotion asks for an approved change, or when the user says change request, change management, CAB, change window, rollback plan or post-change validation.
---

# Change requests

One process, three backends. The wording lives here and nowhere else:
`commands/change.md` reads this file, and the gate that enforces it is
`hooks/scripts/crew_change.py`. Three copies of a question list is two copies
that drift, and they drift in the direction of being shorter.

---

## 1. The template

The ServiceDesk Plus **Change Management Request** template is the shape all
three backends carry. Jira and files mode reproduce it exactly; the only thing
that differs between backends is where the text lands.

| Field | Where it comes from |
|---|---|
| Priority | asked per request |
| Impact | asked per request |
| Urgency | asked per request |
| Impact Details | asked per request — the blast radius in prose, not a repeat of Impact |
| Requester name | `change.requester`, asked when it is null |
| Implementor of Change | `change.implementor`, asked when it is null — and it is also answer 2 |
| Scheduled Start Time | asked per request — and it is also part of answer 3 |
| Scheduled End Time | asked per request — and it is also part of answer 3 |
| Subject | asked per request |
| Category | `change.category`, asked when it is null |
| Description | the ten answers in §2, in order, verbatim question then answer |

`Requester name` and `Implementor of Change` default from config because they
are facts about a person, not about a request. Everything else is per-request:
a default Priority is a Priority nobody chose.

**Scheduled Start Time and Scheduled End Time are the change window**, and they
are not decoration. When `change.requireForProduction` is true they are what
`/crew:promote production` checks the clock against.

---

## 2. The ten questions, verbatim

The template prints this above them, and it is the whole reason the gate
exists:

> ALL THE BELOW QUESTIONS MUST BE ANSWERED. ANY PERTINENT MISSING INFORMATION
> WILL RESULT IN THE REQUEST BEING DENIED.

1. What specifically is the change?
2. Who will be implementing the change (added to Requestor Details also)?
3. What is the scheduled time for the change - list downtime duration and
   day/time (added to Requestor Details also)?
4. Who will this change affect? (how many are affected, what areas, or how
   many users)
5. What is the worst-case scenario of impact to end users?
6. What systems/applications are affected? (IP address, URL and/or hostname)
7. List the system/applications/services impact, and whether each impacted
   system/application/service is hosted locally or in the cloud
8. What is your rollback plan?
9. Has there been a notification sent to those affected?
10. Attach results of post-change validation

**Questions 2 and 3 are answered twice on purpose** — once here, and once in
Requestor Details, because that is what the template asks for. Say the same
thing in both places rather than abbreviating one of them.

---

## 3. The gate

`hooks/scripts/crew_change.py` owns it. Run it; do not judge the answers by
reading them.

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_change.py --answers <file.json> --mode new
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_change.py --answers <file.json> --mode close
```

- `--mode new` gates **questions 1–9**. Exit 0 means every one has a real
  answer. Exit 2 means it refused, and stderr names each failing question and
  says whether the box was empty or held a placeholder.
- `--mode close` gates **question 10 only**. The other nine were gated at
  filing and the backend holds them.
- **Any non-zero exit is a refusal, including one caused by unreadable input.**
  The two states that must never be confused are "complete" and "could not
  tell", so everything that is not a verified pass exits non-zero.

The placeholder list is `crew_change.PLACEHOLDERS` and it is **not repeated
here** — a second copy is a copy that drifts. Two of its judgement calls are
worth knowing while you collect answers: a bare `none` is refused (say "no
users are affected: the service has no consumers yet" instead, which is what a
change board wants anyway), and a bare `no` is accepted, because it is a
complete answer to question 9.

Question 10 is answered at `close`, never at `new`: at filing time the change
has not happened, so requiring it would make the gate unsatisfiable and the
natural repair would be to type `N/A` — which teaches an operator that
placeholders are how you get past this gate.

---

## 4. Field mapping per backend

The **content is identical in all three**. Only the transport differs.

### ServiceDesk Plus (`tracker: "sdp"`)

Reached through the `sdp_*` MCP tools, the same ones `/crew:sdp-sync` and the
`infra-work-ticketing` skill use. Filed with `sdp_create module=change`.

| Template field | SDP |
|---|---|
| — | `template` = `change.sdpTemplate` (ships as `Change Management Request`) |
| Subject | `subject` |
| Priority / Impact / Urgency / Category | resolve each against `sdp_list_metadata` **first** |
| Impact Details | `impact_details` |
| Requester name | `requester` |
| Implementor of Change | `change_owner`, and repeated in the description as answer 2 |
| Scheduled Start / End Time | `scheduled_start_time` / `scheduled_end_time` |
| Description | the ten Q&A pairs, question then answer, in order |

**Resolve every named value against `sdp_list_metadata` before writing.** SDP
rejects the whole request on one unrecognised value rather than partially
applying it — the same trap `/crew:sdp-sync` documents for requests, and it
costs more here because a change carries more named fields than a ticket does.

The description is visible to the requester. Scrub it the way `/crew:sdp-sync`
describes: no hostnames you were not given, no credentials, no internal IPs,
no customer names from other records.

### Jira (`tracker: "jira"`)

Reached through the Jira MCP tools, as `/crew:jira-sync` does.

| Template field | Jira |
|---|---|
| — | issue type = `change.jiraIssueType` (ships as `Change`) |
| Subject | `summary` |
| Priority | `priority` |
| Category | `labels`, plus `components` where the project has them |
| Impact / Urgency / Impact Details | the description's own headed sections — most Jira projects have no native field for these |
| Requester name / Implementor of Change | `reporter` / `assignee`, and both repeated in the description |
| Scheduled Start / End Time | the description's `Scheduled` section, plus the project's own date fields when it has them |
| Description | the ten Q&A pairs, question then answer, in order |

Jira Cloud projects vary. Read the project's own fields with
`getJiraIssueTypeMetaWithFields` before inventing one, and put anything the
project cannot hold into the description rather than dropping it.

### Local (`tracker: "files"` or `"obsidian"`)

`.work/changes/<id>.md`, with `<id>` the next free `CHG-####`. The whole
template, in the order §1 lists, then the ten Q&A pairs. Same content; the file
IS the record, so nothing may be abbreviated on the grounds that it is "only
local".

---

## 5. State, and where it lives

**The backend's own state is the truth. The local cache is a cache.**

`.work/changes/<id>.md` is written for every backend, so `/crew:change status`
and `/crew:work` can read a change back without an API call. It records what
was filed. It does **not** record whether the change was APPROVED — a change
board approves in the desk, and nothing crew writes locally can know that has
happened.

So anything that turns on approval — `/crew:promote production` under
`change.requireForProduction`, and `/crew:change close` — reads the state from
the backend at that moment. A cached `approved`, or this session's memory of
having seen one, is not evidence. If the backend cannot be reached, the answer
is **"could not read the state", and that is a stop**, never a pass.

---

## 6. Missing tooling is a stop

If the tracker is `sdp` and the `sdp_*` tools are not connected, or `jira` and
the Jira tools are not, say exactly which is missing, name how to connect it,
and stop.

**Never fall through to `local`.** A silent fallback splits the source of
truth: a change nobody on the change board can see, sitting in a file, looking
filed. That is worse than not filing, because the operator believes a change
request exists.
