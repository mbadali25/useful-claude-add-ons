---
name: crew-house-style
description: House style for documents the crew hands to a human - palette, heading hierarchy, capitalization, and whether the artifact should be PDF, DOCX, HTML or plain markdown. Use when exporting an architecture write-up, runbook, report or handoff, when asked what a delivered document should look like, or when choosing between PDF and DOCX.
---

# House style

This skill owns what a delivered document looks like. It does not build one —
the generators already exist and are named below. If you find yourself writing
instructions for producing a file, you have gone out of scope.

## Palette

Five roles, and nothing else. A document that introduces a sixth colour is
decorating rather than communicating.

| Role | Hex | Used for |
|---|---|---|
| Ink | `#1A1A1A` | Body text |
| Muted | `#5C6670` | Captions, table rules, the provenance line |
| Accent | `#1F4E79` | Headings, links, the primary path in a diagram |
| Warn | `#B45309` | Caveats, anything the reader must verify |
| Fail | `#B02A1E` | Failure paths, blocked states |

Paper is white. Accent carries structure; warn and fail carry meaning only —
never reach for either because a sentence felt important.

## Headings

One H1: the document title, matching the filename. H2 for sections, H3 for the
level below it, and no skipped levels — an H3 sitting under an H1 tells a
screen reader and a generated contents page that a section is missing.

Depth stops at H3. If you want an H4, that subsection is its own document.

Carry the source's provenance line into the export:
`Generated from <repo>@<short-sha> on <date>. Verify before trusting.`
Dropping it on export removes the one thing that makes the artifact checkable.

## Capitalization

Sentence case for every heading, table header and figure caption. Title Case
reads as marketing, and it makes two headings written a week apart look like
they came from different authors.

Product, service and tool names keep their own casing: PostgreSQL, GitHub
Actions, `terraform-docs`. Expand an acronym on first use, then stop.

## Which format

| The reader | Format | Because |
|---|---|---|
| Needs it final, printed, or identical everywhere | PDF | Nothing reflows, and page references survive |
| Will edit, comment, or track changes on it | DOCX | A PDF forces them to retype it to respond |
| Opens it in a browser or a wiki, or wants a link | HTML | Renders anywhere with no reader application |
| Is an engineer, or is the repository itself | Markdown | It diffs, and it is already the source |

Decks answer a different question. If the ask is "walk the room through it",
that is PPTX, not a document with a title page bolted on.

## Generating it

Route to the skill that owns the format. Do not reimplement any of them:

- `doc-builder` — branded findings reports and screenshot SOPs. Pass
  `--brand <docs.theme>`; for a findings report prefer `docs.reportTheme` when
  it is set. A null theme passes no `--brand` at all and lets doc-builder
  resolve. `scripts/build_report.py` is the findings report,
  `scripts/build_sop.py` is the SOP — both take `--brand`.
- `anthropic-office-skills:docx` — DOCX
- `anthropic-office-skills:pdf` — PDF
- `anthropic-office-skills:pptx` or `ppt-master` — decks
- `visio-diagrams` — `.vsdx`, when the recipient has to edit the diagram.
  Authoring diagrams and detecting an installed Visio stay with `crew-diagrams`;
  this is only the route to an editable file for someone outside the repo.

HTML needs no skill; write the file and apply the palette above.

**`doc-builder` is additive and narrow. It does not take DOCX and PDF over
generally** — `anthropic-office-skills` keeps both and stays the fallback. The
reason is a property of the tools rather than a preference: doc-builder's
`--to-docx`/`--to-pdf` run through **Microsoft Word on Windows via COM**
(`pywin32`; see `doc-builder/SKILL.md`, the requirements table), and
`anthropic-office-skills` needs neither. Routing all DOCX and PDF to
doc-builder would break crew's document path on Linux and macOS.

**Do not detect Word yourself.** Crew testing for Word is crew reimplementing
doc-builder's own capability check, which is what the rule at the top of this
list forbids, and it goes stale the moment doc-builder's requirements change.
Condition only on whether **doc-builder is installed**; let doc-builder report
what it cannot do, in its own voice, and relay that.

These are user- and plugin-level skills. Crew does not bundle them, so the one
you want may not be installed. When it is missing, hand over the markdown and
say so in the handoff — "PDF export unavailable, `anthropic-office-skills:pdf`
is not installed" — rather than assuming it is present or improvising a
generator. An honest markdown file beats a converter written on the spot.

**doc-builder has two distinct degraded paths, and they are not the same
sentence.** Reporting the wrong one sends the reader to fix the wrong thing,
which costs more than saying nothing:

- **doc-builder is not installed.** Route to `anthropic-office-skills` instead,
  produce the document unbranded, and say so — "branded report unavailable,
  `doc-builder` is not installed; produced with `anthropic-office-skills:docx`,
  unbranded". The theme in `docs.theme` was not applied and the handoff must
  say that, or the reader assumes their configured brand is on the document.
- **doc-builder is installed but Microsoft Word is absent.** doc-builder says
  this itself; relay its message rather than composing your own. **This is a
  PARTIAL loss, not a fall back to unbranded.** Word's absence costs
  `--to-docx`/`--to-pdf` and Gate 2 only — doc-builder still produces the
  branded HTML report and, through `python-docx`, the branded SOP `.docx`. So
  take the branded artefact it CAN produce and name the one format that is
  unavailable. Announcing "doc-builder is not installed" here, or discarding a
  branded document that was successfully built, are both wrong.

Never fall back to pandoc or LibreOffice for a doc-builder format —
`doc-builder/SKILL.md` rules that out explicitly, and neither is assumed to
exist on any machine here.
