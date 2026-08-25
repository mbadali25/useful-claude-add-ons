---
name: crew-docs
description: Keep CHANGELOG.md, README.md, SECURITY.md, TODO.md, ADRs, generated docs, and the API and feature reference current as work lands. Use when the user says update the changelog, keep the docs in sync, update the README, maintain TODO, document the API, list the endpoints or features, or asks which docs a change should touch.
---

# Document maintenance

## The default is: do not touch

Updating every document on every change is how documentation becomes noise. A
CHANGELOG with an entry for each typo fix is unreadable; a README rewritten every
sprint stops being trusted because nobody can tell what actually changed.

So each document has a **trigger condition**, and if the condition is not met,
the document is left alone and that is the correct outcome.

| Document | Update when | Never |
|---|---|---|
| `CHANGELOG.md` | Behaviour users or callers can observe changed | Refactors, formatting, internal renames |
| `README.md` | Setup, commands, or the mental model changed | Every ticket |
| `SECURITY.md` | Reporting process, supported versions, or a disclosed issue changed | Routine security fixes |
| `TODO.md` | Something deliberately deferred, with a reason | As a substitute for tickets |
| `docs/adr/` | A decision was made with a rejected alternative | Implementation detail |
| `docs/diagrams/` | The structure a diagram shows moved (see `crew-diagrams`) | Cosmetic changes |
| `docs/runbooks/` | An operational procedure changed, or a new one was needed | Anything `make deploy` already does |

`/crew:work` step 10 asks this question once per ticket. The honest answer is
usually "none of them."

## Generated blocks are not yours to edit

Some documentation is compiled from source. Editing the output is work that gets
destroyed on the next build, silently.

Before editing any markdown, check for these and stop if you are inside one:

```
<!-- BEGIN_TF_DOCS -->  ... <!-- END_TF_DOCS -->     terraform-docs
<!-- begin-openapi -->  ... <!-- end-openapi -->      openapi generators
<!-- AUTO-GENERATED -->                                various
```

For terraform-docs specifically, the content comes from the `/** */` header in
`main.tf`, from `footer.md`, and from the `description` fields on variables and
outputs. Change those. See `crew-terraform`.

If a README has such a block, hand-written prose belongs **above** it.

## CHANGELOG

Keep a Changelog format, semantic versions, newest first.

```markdown
## [Unreleased]
### Added
- Scheduled report Lambda replacing the sbmovement .NET job (THDDEV-1058)
### Fixed
- Header validation rejected files with a UTF-8 BOM
```

Write from the **ticket and the diff**, not from the conversation. One line per
user-visible change, in the language of someone using the thing rather than
someone who built it: "rejects files with a BOM" not "added BOM strip in
`validate_header()`".

Reference the ticket id. Do not paste commit hashes — they are in git already and
they make the file unreadable.

## SECURITY.md

Rarely changes, and that is fine. It should carry: how to report a vulnerability
and to whom, which versions get fixes, and expected response time.

**Never** log specific vulnerabilities here while they are unfixed. A public
`SECURITY.md` describing an open hole is a disclosure, not documentation. Fixed
issues go in the CHANGELOG once released.

## TODO.md

Only for work deliberately deferred with a reason, which is different from work
not yet started — that belongs in tickets.

```markdown
- [ ] Replace the polling loop with EventBridge — deferred until the SFTP
      migration lands, because the current trigger depends on the share path
```

Each entry says **why it is deferred and what would unblock it**. Without that,
it is an inbox that grows forever and gets deleted in frustration two years later.

`.work/SMOKE-GAPS.md` is the same idea for test coverage and stays separate.

## ADRs

One decision per file, append-only, never edited after acceptance. A superseded
decision gets a new ADR that references the old one — the record of having
changed your mind is the valuable part.

Write them when the alternative was real. "We used the standard library" is not
an ADR. "We chose stored procedures over application logic because the batch
window requires set-based operations" is.

## Doing the work

```
/crew:docs            # check what this change should touch, and do it
/crew:docs --audit    # report staleness across all docs, change nothing
```

`--audit` is worth running monthly. It checks generated blocks are current,
anchors still resolve, and CHANGELOG `[Unreleased]` is not months old — and it
reports rather than fixes, because bulk doc edits are unreviewable.

---

## References: API and features

`/crew:reference` writes these; `crew:docs-writer` does the writing. They are
separate from everything above because they are **enumerations**, not narratives
- the value is in being complete and anchored, not in being well written.

| File | Answers |
|---|---|
| `docs/reference/api.md` | What can I call, with what, and what does it do to the system |
| `docs/reference/features.md` | What can this system do, including the parts with no UI |

### Why the codemap does not cover this

`.crew/codemap/` answers "where does this live" for an agent about to change
code. A reference answers "what exists" for a human who has to use or operate
the thing. A subsystem note saying `orders: handles order lifecycle, entry
src/Orders/` is a good codemap entry and tells you nothing about the eleven
endpoints under it.

### The two rules

1. **Anchor every entry to `file:line`.** Unanchored, it cannot be re-verified,
   so it rots silently and keeps being trusted. This is the same reason codemap
   notes carry anchors.
2. **Enumerate from code, never from the existing docs.** The existing docs are
   the thing being checked. A reference regenerated from a stale reference is
   just a stale reference with a newer date on it.

### What is actually worth writing down

For an endpoint, the signature is the guessable part. Spend the effort on:

- **Side effects** - what it writes, what it emits, what it calls out to
- **Error responses** - the status codes and what causes each
- **Idempotency** - what a retry does. This is the one that causes incidents

For features, the headless ones are the ones nobody documents and everybody
needs: scheduled jobs (and what happens when one is missed), queue consumers,
admin scripts, feature flags and the config keys behind them.

### Keeping it honest

`/crew:reference --audit` reports drift in both directions: endpoints in the
code with no entry, and entries whose anchor no longer holds. Wire a rule into
`.crew/verify.json` on the route and job paths so a change to them is a prompt
to run the audit.

Mark anything you could not confirm as `undocumented - needs a human` and leave
it visible. A reference that admits a gap is useful; one that implies full
coverage while missing a third of the endpoints is worse than no reference,
because the absence of an endpoint reads as proof it does not exist.
