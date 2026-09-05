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

- `anthropic-office-skills:docx` — DOCX
- `anthropic-office-skills:pdf` — PDF
- `anthropic-office-skills:pptx` or `ppt-master` — decks
- `visio-diagrams` — `.vsdx`, when the recipient has to edit the diagram.
  Authoring diagrams and detecting an installed Visio stay with `crew-diagrams`;
  this is only the route to an editable file for someone outside the repo.

HTML needs no skill; write the file and apply the palette above.

These are user- and plugin-level skills. Crew does not bundle them, so the one
you want may not be installed. When it is missing, hand over the markdown and
say so in the handoff — "PDF export unavailable, `anthropic-office-skills:pdf`
is not installed" — rather than assuming it is present or improvising a
generator. An honest markdown file beats a converter written on the spot.
