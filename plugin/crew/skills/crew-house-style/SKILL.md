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

- `doc-builder` — branded findings reports and screenshot SOPs, as HTML,
  DOCX or PDF. Pass `--brand <docs.theme>`;
  for a findings report prefer `docs.reportTheme` when it is set.
  A null theme passes no `--brand` at all and lets doc-builder resolve.
  `scripts/build_report.py` is the findings report — its HTML is a finished
  deliverable on its own, before any `--to-docx`/`--to-pdf` — and
  `scripts/build_sop.py` is the SOP; both take `--brand`.
- `anthropic-office-skills:docx` — DOCX
- `anthropic-office-skills:pdf` — PDF
- `anthropic-office-skills:pptx` or `ppt-master` — decks
- `visio-diagrams` — `.vsdx`, when the recipient has to edit the diagram.
  Authoring diagrams and detecting an installed Visio stay with `crew-diagrams`;
  this is only the route to an editable file for someone outside the repo.

### HTML

**`doc-builder` owns HTML, the same as DOCX and PDF — route to it first.**
`scripts/build_report.py` writes branded HTML directly; that HTML *is* the
deliverable when the destination is a browser or a wiki, with no
`--to-docx`/`--to-pdf` needed. Its brand comes from `resolve_brand.py`, not
from the *Palette* table above, so it carries the installed pack's own
colours — Solomon's navy `#0E2841` and accent `#EF483D`, where the table
above is only the neutral default. Use it whenever the content is a
findings-style write-up — a table with severity, status, priority or verdict
columns — and it already carries both rules below on every table it writes.

`build_report.py`'s `build()` only assembles a masthead, a lede, summary
cards and one findings table, and emits no `<h3>` at all, so a narrative
architecture write-up, runbook or handoff with prose sections past H2 does
not fit it. For that content the page is still hand-authored — but **do not
hand-write the stylesheet any more, and do not lift the palette from the table
above.** Ask doc-builder for it:

```
python3 house_style.py --profile guide --brand solomon          # emit the CSS
python3 house_style.py --profile guide --brand solomon --apply FILE.html
```

run from doc-builder's `scripts/`. `--apply` restyles an existing page in
place and is idempotent. `--brand neutral` gives the unbranded palette.

This replaced a copy-the-hex instruction, and the reason is worth keeping
because the failure was invisible for a while. Until 2026-09-22 every one of
`docs/guides/*.html` carried both print rules below AND `#1F4E79` with none of
Solomon's colours anywhere: the rules had landed and the brand had not, because
a hand-written path never called `resolve_brand.py` and nothing made it. Asking
for the stylesheet is what closes that, not remembering to.

One trap the extraction surfaced, which matters to anyone writing a selector
here: the guides used a bare `th { ... }`, and rewriting it as `table th { ... }`
made the navy header shading vanish from the LibreOffice-rendered PDF while the
HTML still contained the declaration. That is the documented behaviour two
paragraphs down — LibreOffice applies a bare element or a bare `.class` and
silently drops every compound or descendant selector — and it was caught only by
rasterising the PDF and looking at it. The guide profile therefore uses bare
cell selectors; the report profile keeps its scope, because a bare `td` there
would border the masthead's own cells.

Carry **both** print rules below regardless of path. They are one fix in two
places; either one alone changes nothing a reader can see.

1. **Every table gets a real `<thead>`** around its header row, and a
   `<tbody>` around the rest. A bare `<tr>` of `<th>` is styled like a header
   and is not one to anything that paginates.
2. **Every page carries this block**, from
   `skills/doc-builder/scripts/house_style.py:246-248` — the body of
   `print_css`:

   ```css
   @media print {
     h2, h3 { page-break-after:avoid; }
     tr { page-break-inside:avoid; }
     thead { display:table-header-group; }
   }
   ```

   The heading selector is a **parameter** there, not a literal: `print_css`
   takes `headings`, and `stylesheet()` passes `h2` for the report profile and
   `h2, h3` for the guide profile. So the block above is doc-builder's guide
   profile exactly, and `h3` is no longer crew widening someone else's rule —
   ask for the guide CSS and you are handed it. It is still written out here
   because a page authored without asking has to carry it: *Headings* above
   allows an H3, the report profile names `h2` alone because its generator
   emits no `<h3>` at all, and measured on the first re-render with `h2` only,
   `h3`s still ended a page with their table stranded on the next.

`display:table-header-group` has nothing to bind to when the markup has no
`<thead>`, so rule 2 without rule 1 still drops a table's header at every page
break; rule 1 without rule 2 does nothing at all. `doc-builder` already
enforces both together, and says so once per profile — the report profile at
`skills/doc-builder/scripts/house_style.py:342`, "Every table: real grid, real
thead. Both required.", and the guide profile at
`skills/doc-builder/scripts/house_style.py:352`, "Every table: real grid, real
thead. Both required." Both are cited rather than one, because the comment is
duplicated and naming one line would leave the other profile's copy pinned by
nothing while reading as though the pair were covered. That is why routing to
doc-builder removes the whole class of gap instead of adding a third remembered
rule to this list.

### doc-builder's reach, and its degraded paths

**`doc-builder` is additive and narrow. It does not take DOCX and PDF over
generally** — `anthropic-office-skills` keeps both and stays the fallback. The
reason is no longer a rendering-engine gap, and this tree is what falsifies
the old one: `skills/doc-builder/scripts/render_engine.py` defines both a
`WORD` and a `LIBREOFFICE` engine, with `soffice_exe()` resolving LibreOffice
on Windows and macOS as well as Linux, and `build_report.py:453` calls
`render_engine.choose_engine()` and branches to LibreOffice automatically off
Windows. **`pywin32` is required only for the explicit `--renderer word`
opt-in** (`build_report.py:29`), never for the default path — measured here:
with `python-docx` installed and no Word present, `build_sop.py` produced a
valid 43KB branded `.docx` on this Linux host.

The reason `anthropic-office-skills` stays the fallback is scope, not
platform: doc-builder produces exactly two document shapes — branded findings
reports and SOPs — and its own Disambiguation table (below, and repeated in
`doc-builder/SKILL.md`) already sends everything else elsewhere: editing or
find-and-replacing in a `.docx` the user already has, slide decks, and
spreadsheets. `anthropic-office-skills` covers that remainder. That is what
keeps it the fallback, not a Linux/macOS gap that no longer exists.

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

### When the configured theme does not resolve

The two paths above are about whether doc-builder is **available**. This one is
about what the **config says**, and it fails differently: `docs.theme` or
`docs.reportTheme` names a brand pack that doc-builder cannot find.

**Relay doc-builder's error and stop.** Do not fall back to unbranded, and do
not pre-check the name yourself.

doc-builder already answers this. `--brand <name>` that matches nothing raises
`BrandNotFound` (`skills/doc-builder/scripts/resolve_brand.py:78-82`, raised at
`:317`), whose message is `No brand pack named 'x'. Installed: a, b.` — or
`Installed: (none - only 'neutral')`. It subclasses `BrandError(SystemExit)`
(`:66-67`), so the script exits non-zero and the message is already on stderr.
Repeat it; the installed-names list is the part the user needs and you cannot
produce it as well as doc-builder can.

**Falling back to unbranded is the worse failure of the two.** A config that
names a brand is an explicit instruction, so producing an unbranded document
there hands the user a deliverable that is wrong in the one way they took the
trouble to configure against — and, unlike a missing doc-builder, nothing about
the result says so. A document that was not produced is recoverable in a minute.
A wrongly-branded one sent to a client is not.

**Do not validate the theme name before calling.** This is the same rule as *Do
not detect Word yourself*, and here it also gets the answer wrong: a crew-side
check comparing `docs.theme` against installed pack names would reject values
doc-builder accepts. `_match_explicit` (`resolve_brand.py:298-317`) takes a pack
name, a **skill directory name**, a path to a `brand.json`, or a directory
containing one — matching case-insensitively — and `neutral` always resolves
(`:301`) whether or not a pack of that name is installed. A crew-side allowlist
would therefore fail closed on correct configuration, which is the expensive
direction: it blocks work that would have succeeded, and the config looks fine.

Crew's own job here is to **notice that the theme was configured and did not
apply**, and to say which key held it — `docs.theme` or `docs.reportTheme` —
because doc-builder only ever sees a `--brand` value and cannot know which of
crew's two keys supplied it.
