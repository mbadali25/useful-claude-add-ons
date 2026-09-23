# What Word silently drops

Every rule here was measured against the Word object model on a real estate, not
assumed. The test method is at the bottom — re-verify after any Office update.

Word is the **reference** renderer, and these are its rules. The other renderer,
LibreOffice, drops a *different* and largely disjoint set — see "What LibreOffice
silently drops" at the end of this file before assuming a Word-safe stylesheet is
safe anywhere else.

The common property of all five: they fail **silently and completely**. No
error, no console message, just a document that reads as though nobody styled
it. Two of them are worse than unstyled — they produce invisible text.

---

## 1. Literal hex colours only. Never CSS variables.

```css
/* WRONG - renders with NO background in .docx and .pdf */
:root { --header-bg:#1f4e79; }
th { background:var(--header-bg); color:#ffffff; }

/* RIGHT */
th { background:#1f4e79; color:#ffffff; }
```

The single most damaging trap. `var()` is not merely ignored — **the whole
declaration is dropped**, so `background:var(--header-bg); color:#ffffff`
produces white text on a white background. Invisible, not just unstyled.

Measured: a `var()` cell reports `Shading.BackgroundPatternColor = -16777216`
(`wdColorAutomatic`, i.e. none); the same colour written literally reports
`7949855`.

If you want named colours for maintainability, substitute real hex at build
time. Do not ship `var()`.

## 2. Zebra striping is an explicit class. `:nth-child` does not work.

```css
/* WRONG - every row comes out unshaded */
tbody tr:nth-child(even) td { background:#eef3f8; }

/* RIGHT */
tr.alt td { background:#eef3f8; }
```

The builder writes the class as it emits rows. Structural pseudo-classes
(`:nth-child`, `:first-child`, `:last-of-type`) are all unsupported, as are
`:hover`, `::before` and `::after` — **never put content in a pseudo-element**,
it will not exist in the PDF.

## 3. Every table gets a real grid and a `<thead>`.

Requirements, not preferences. A borderless forty-row table is unreadable on
paper, and a table whose header does not repeat is unreadable the moment it
crosses a page break.

```css
table { border-collapse:collapse; width:100%; }
th, td { border:1px solid #b8bcc6; padding:7px 10px; text-align:left; vertical-align:top; }
th { background:#1f4e79; color:#ffffff; font-weight:600; }
tr.alt td { background:#eef3f8; }
```

Word converts `<thead>` into a repeating header row automatically — a table
built that way reports `Rows(1).HeadingFormat = -1` with no COM post-processing.
**This is free; there is no reason to skip it.**

## 4. One class per element. Two class names applies NEITHER.

The least obvious trap, and it fails completely rather than partially.

```html
<!-- WRONG - Word applies NEITHER rule; the chip renders as plain body text -->
<span class="chip chip-fail">FAIL</span>

<!-- RIGHT -->
<span class="chip-fail">FAIL</span>
```

```css
/* WRONG - a base class plus a modifier is a browser idiom Word cannot follow */
.chip { display:inline-block; padding:2px 8px; font-weight:700; }
.chip-fail { background:#fde8e6; color:#a01b12; }

/* RIGHT - repeat the common declarations in every variant, however inelegant */
.chip-fail { display:inline-block; padding:2px 8px; font-weight:700;
             background:#fde8e6; color:#a01b12; }
.chip-pass { display:inline-block; padding:2px 8px; font-weight:700;
             background:#e3f4ea; color:#1c6b3f; }
```

Measured: the two-class span returned `Font.Shading.BackgroundPatternColor =
-16777216` **and** `Font.Color = -16777216` — neither rule applied. The
single-class span returned `15132925` and `1186720` as authored.

**The duplication is deliberate.** Factoring shared declarations into a base
class is correct CSS and produces an unstyled PDF.

**Grouped selectors are fine** — `.chip-fail, .chip-critical { ... }` works and
is the right way to keep the repetition manageable. It is multiple classes *on
the element* that breaks, not multiple selectors on the rule.

## 5. No flexbox, no grid, no float layouts.

`display:flex` and `display:grid` are ignored; cards laid out with flex collapse
into a vertical stack of borderless blocks. For anything that must sit side by
side, use a table with fixed-width cells.

`display:block` on a `<span>` is also ignored, so a card's number and label must
be real block elements:

```html
<table class="cards"><tr>
  <td class="card"><div class="n">218</div><div class="l">Under 14 characters</div></td>
  <td class="card"><div class="n">5</div><div class="l">Blocked by banned list</div></td>
</tr></table>
```

---

## Column widths: measure, do not guess

Fixed table layout needs widths, and **deriving them from column names does not
work.** Failed here in both directions: a numeric column keyed `Count` but
headed `Passwords` was sized 6% and its header collided with the next one, while
account names keyed `Account` were sized 14% and ran off the page.

Weight each column by the longest string it actually renders, header included:

```python
longest = len(str(labels[i]))
for row in rows:
    longest = max(longest, len(str(row[i])))
# Long prose is compressible; damp the top end so one wide column
# cannot starve the rest.
if longest > 40:
    longest = 40 + int((longest - 40) ** 0.5) * 4
# A chip has padding and never wraps, so its column needs more than its text.
if key in ("Status", "Priority", "Severity", "Verdict"):
    longest += 5
```

Normalise to **exactly 100** and push the rounding drift into the widest column.
A row totalling 101 pushes the table past the margin.

Three rules that go with it, each of which caused a visible defect:

- **`th` must not be `white-space:nowrap`.** In a narrow fixed column the header
  overflows into its neighbour and the header row becomes unreadable.
- **`white-space:nowrap` on a data cell is only for short atomic tokens** such
  as `CRK-001`. On an account name it overflows rather than wrapping.
- **Use `overflow-wrap:break-word`, not `word-break:break-word`.** The latter
  breaks short tokens mid-word (`CRK-` / `001`); the former breaks only when
  there is no alternative.

## Print rules

```css
@media print {
  body { font-size:11pt; }
  .wrap { padding:0; max-width:none; }
  h2 { page-break-after:avoid; }
  tr { page-break-inside:avoid; }
  thead { display:table-header-group; }
}
```

---

## Verifying a change

**Do not trust a browser preview.** Convert and inspect the Word object model.

**This verification needs Word, and where Word cannot exist the answer is UNAVAILABLE —
not "skipped", and never "passed".** The snippet below drives `Word.Application` over COM.
Microsoft ships no Word desktop app for Linux, so on Linux (and on a macOS machine without
Office) it cannot run at all, and neither can Gate 2, which asks the same kind of question
about the SOP path. A LibreOffice render does **not** substitute: it answers a question
about LibreOffice. `verify_borders.py` reports that state explicitly and exits 3; say the
same thing in prose — "Gate 1 passed, Gate 2 UNAVAILABLE on this host" — rather than
reporting a green run. A check that could not run is not a check that passed.

```powershell
$w = New-Object -ComObject Word.Application
$w.Visible = $false; $w.DisplayAlerts = 0
$d = $w.Documents.Open('C:\path\to\report.html', [ref]$false, [ref]$true)

$t = $d.Tables(1)
# -16777216 is wdColorAutomatic, i.e. NO shading was applied.
'header shade  = ' + $t.Cell(1,1).Shading.BackgroundPatternColor
'zebra  shade  = ' + $t.Cell(3,1).Shading.BackgroundPatternColor
'header repeats= ' + $t.Rows(1).HeadingFormat      # -1 = True

$d.Close([ref]$false); $w.Quit()
```

Colours come back as **BGR, not RGB** — `#1F4E79` reads as `7949855`
(`0x794E1F`). Reverse the byte pairs before concluding a colour is wrong.

If `BackgroundPatternColor` is `-16777216` anywhere you expected a fill, the CSS
did not apply. The usual cause is rule 1 or rule 2.

---

## Checklist before shipping a report change

Items 1–7 are mechanical and `scripts/_test/checklist.sh` runs them against a report the
builder actually emitted (16 checks, exit 0 = pass). Items 8 and 9 need a person.

1. No `var(--` anywhere in the emitted stylesheet.
2. No `:nth-child`, `::before`, `::after`, `:hover`.
3. No element carries two class names (`class="a b"`).
4. No `display:flex`, `display:grid`, or `display:block` on a `<span>`.
5. Every `<table>` has `<thead>` and a visible border on `th` and `td`.
6. Alternating rows carry `class="alt"` written by the builder.
7. Every severity colour is accompanied by its word.
8. Converted to PDF and **opened** — not previewed in a browser.
9. Report written to `reports/` at the repo root, and `reports/` is gitignored.

---

## What LibreOffice silently drops (the other renderer)

LibreOffice (`soffice --headless`) is the only renderer that exists on Linux and macOS, so
on those machines a report is converted by it or not at all. **It fails the opposite way
from Word**, and the overlap between the two rule sets is smaller than it looks — a
stylesheet written to survive Word does not automatically survive LibreOffice.

Measured 2026-09-22 with LibreOffice 26.2.5.2 on Ubuntu 26.04, by converting a
one-table HTML file carrying six selector shapes and rasterising the PDF at 120 dpi:

| Selector | Word | LibreOffice HTML import |
|---|---|---|
| `.a { background }` — bare class | applies | **applies** |
| `td.b { background }` — element.class | applies | **dropped** |
| `table.c td { background }` — descendant | applies | **dropped** |
| `table.d th { background }` — descendant | applies | **dropped** |
| `table.e th, table.e td { border }` — grouped descendant | applies | **dropped** |
| `tr.f td { background }` — descendant | applies | **dropped** |
| `class="a b"` — two classes on one element | **dropped** (rule 4) | not measured |

So LibreOffice honours **simple selectors only**. In a doc-builder report that costs, all
silently:

- the table grid — `table.data th, table.data td { border:1px solid ... }`
- the header row — `table.data th { background:TABLE_HEAD; color:TABLE_HEAD_INK }`
- the zebra rows — `table.data tr.alt td { background:ZEBRA }`
- the summary-card panels — `td.card { background:PANEL; border:... }`
- the meta-table key shading — `table.meta td.k { background:ZEBRA }`

What **does** survive, because each is a bare class: the masthead strip, band, rule and
classification bar; the lede panel; the handling banner; every severity chip, with its word.
The document still reads as branded — it is simply flatter, and a reader cannot tell from
the file which of the two rendered it unless doc-builder's `[renderer: ...]` line is carried
with it.

**Do not "fix" this by rewriting the stylesheet into bare classes.** Every rule above it in
this file was measured against Word, which is the reference renderer, and a change made for
LibreOffice that breaks Word trades a legible report for an unstyled one on the platform
most of these documents are read on. If parity is wanted, it is its own piece of work with
its own measurement on both engines.

The SOP path is much less affected: `build_sop.py` emits real OOXML, so LibreOffice is
importing a Word document rather than parsing HTML. The self-test fixture renders correctly
through it, screenshot border on all four edges included. That is still not evidence about
Word — see the UNAVAILABLE rule above.
