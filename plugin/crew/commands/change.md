---
description: File, check and close a change request — SDP, Jira or local
argument-hint: <new | status <id> | close <id> | list>
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, ToolSearch
---

Change request: $ARGUMENTS

Follow the `crew-change` skill. It holds the template, the ten questions
verbatim, and the per-backend field mapping — this file is the workflow, that
one is the wording, and neither restates the other.

## 0. The backend, first

Read `tracker` from the effective config, through `/crew:config` rather than
out of `.crew/config.json`, because a machine-global file can set keys the repo
file would not show.

| `tracker` | Backend |
|---|---|
| `sdp` | ServiceDesk Plus, `sdp_create module=change`, against `change.sdpTemplate` |
| `jira` | Jira, an issue of type `change.jiraIssueType` |
| `files`, `obsidian` | `.work/changes/<id>.md` |

**Missing tooling for the chosen backend is a stop.** If `tracker` is `sdp` and
the `sdp_*` MCP tools are not connected, or `jira` and the Jira tools are not,
say exactly which is missing, name the install or the connection that fixes it,
and **stop**. Search your tools before concluding they are absent — under tool
search they are not listed until you search for them.

**Never fall through to `local`.** A silent fallback splits the source of
truth, and the failure is invisible: a change sitting in a file, looking filed,
that nobody on the change board can see. Worse than not filing, because the
operator now believes a change request exists.

## 1. `new`

### Collect

The eleven template fields (`crew-change` §1) and the ten answers
(`crew-change` §2). `change.requester`, `change.implementor` and
`change.category` supply three of the fields when they are set; ask for them
when they are null. Everything else is per-request — a default Priority is a
Priority nobody chose.

Ask in **one round**, not three. Show the ten questions as the template words
them, because that is how the change board will read them back.

Answers 2 and 3 go in **twice**, once in the Description and once in Requestor
Details, which is what the template asks for. Say the same thing in both
places.

### Gate — this is the feature

Write the answers to a scratch JSON file keyed by question number, then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_change.py --answers <file> --mode new
```

That gates questions 1-9. **Exit 0 is the only thing that authorises filing.**
On exit 2, relay stderr verbatim — it names every failing question and says
whether the box was empty or held a placeholder — and **file nothing**. Do not summarise the refusal, do
not file "the answered ones", and do not fill a gap yourself: an answer the
operator did not give is the change board being told something nobody
verified.

Run the script. Do not read the answers and decide for yourself whether they
look complete — "I checked them" is exactly the unknown-wearing-the-label-of-a-
check that CLAUDE.md's first lesson is about, and it is why this gate is a
program rather than a paragraph. The placeholder list lives in
`crew_change.PLACEHOLDERS` and nowhere else.

Question 10 is **not** required here and must not be asked for. The change has
not happened yet; `close` collects it.

### File

Create it in the backend, per `crew-change` §4. For SDP, resolve Priority,
Impact, Urgency, Category and status against `sdp_list_metadata` **before**
writing — one unrecognised value rejects the entire request rather than
partially applying it.

Then write `.work/changes/<id>.md` with the same content, for every backend,
and append to `.work/INDEX.md`:

`<id> | filed | change | <repos> | <subject>`

Use the id the backend returned. For SDP that is `CHG-<id>`, in crew's usual
`LETTERS-digits` shape — the bare number the desk returns is invisible to the
rest of crew. For files mode, the next free `CHG-####`.

**The id exists before the work does**, for the same reasons `/crew:ticket`
gives: a change filed after the change is a record of the outcome, not of the
ask.

## 2. `status <id>`

Read the change from the **backend**, not from `.work/changes/<id>.md`. The
local file records what was filed; only the backend knows whether a change
board approved it.

Print: state, requester, implementor, the scheduled window, and whether the
window is open right now. If the backend cannot be read, say **"could not read
the state"** and stop. Never print a state from the cache while implying it
came from the desk.

Refresh the local cache from what you read, the same way `/crew:sdp-sync` does
— store the fields that matter and discard the payload.

## 3. `close <id>`

**Requires the post-change validation results, question 10.** Collect them —
what was checked after the change, and what the checks returned — then:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_change.py --answers <file> --mode close
```

Exit 2 means refuse: say which question is missing and **do not close**. A
change closed without validation results is a change nobody proved worked, and
the record then says it was fine.

Attach the results to the change in the backend — an SDP note or a Jira
comment, and the same text appended to `.work/changes/<id>.md` — **before**
transitioning it. If the attach fails, the close does not happen: there is no
local outbox, and a closed change with no results attached cannot be repaired
by a later note nobody looks for.

`sdp.closeOnDone` still governs whether crew transitions an SDP record at all.
At `false`, attach the results, say the change is ready to close, and leave the
closure to whoever owns the queue.

## 4. `list`

Read `.work/INDEX.md` for the local view, then confirm the state of anything
not closed against the backend. Say which rows were confirmed and which were
read from the cache — a list that mixes the two without saying so is a list
that reports an approval nobody granted.

## 5. `change.requireForProduction`

`false` by default, and at `false` this command changes nothing about
promotion: `/crew:promote production` asks for no change request, exactly as it
did before schema 7.

At `true`, `/crew:promote production` gate 1 requires a change in an **approved**
state for the sha being promoted, read from the backend, and refuses outside
`Scheduled Start Time`..`Scheduled End Time`. See `commands/promote.md`.

It is the one key in crew a repo may only turn **ON**. A machine-global `true`
cannot be defeated by a `false` in a repo you cloned; a repo's own `true` holds
on a machine that said nothing; and a value that is neither `true` nor `false`
reads as `true`, so a typo stops a promotion and names the key rather than
quietly waving it through. CONFIG.md §17.

## What not to do

- Do not file with a question unanswered because the operator said it was
  obvious. The template's rule is that missing information results in denial,
  and the gate is that rule made mechanical.
- Do not answer a question on the operator's behalf. A rollback plan you
  inferred is a rollback plan nobody agreed to execute.
- Do not read approval out of this session's memory, or out of
  `.work/changes/<id>.md`. Only the backend knows.
- Do not close on the strength of the change having been deployed. Deployed
  and validated are two claims, and question 10 is the second one.
