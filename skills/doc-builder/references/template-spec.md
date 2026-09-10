# SOP house template — structural spec

_The structure below was measured 2026-08-25 from a 19-document production set of end-user
onboarding SOPs (now the `solomon` brand pack). The **structure** — page setup, block
shapes, spacing, indents, the border mechanism — is the same for every brand.
The **values** — colours, fonts, footer text, template file — come from the active brand
pack's `sop` block in `brand.json`, and are named here by key. Neutral values are shown;
run `python resolve_brand.py --json` for the ones in force._

`check_conformance.py` is the executable version of this document. If you change a
structural value here, change it in `build_sop.py` and re-run the checker over the whole
set. If you change a brand value, change it in that pack's `brand.json` — the checker reads
it from there.

## Page setup

| Property | Value | Source |
|---|---|---|
| Page size | US Letter, 8.5" × 11" | fixed |
| Margins | top **0.8"**, bottom 0.6", left 0.5", right 0.5" | `sop.margins_in` |
| Text column | 7.5" | derived |
| Base font (`Normal` style) | Calibri (neutral) | `fonts.body` |
| Heading font | Calibri (neutral) | `fonts.heading` |

> **The top margin has nothing to do with screenshot borders.** It was recorded as the fix
> for clipped borders on 2026-08-14 because raising it reflowed three documents so their
> images no longer landed at page top. The defect was untouched; 14 borders across 9
> documents stayed clipped until the real fix landed. See *Screenshot borders* below.

## Palette

| `brand.json` key | Neutral | Used for |
|---|---|---|
| `sop.accent` | `1F4E79` | title accent bar, step numbers, bullet glyphs |
| `sop.image_border` | `FF0000` | screenshot borders — **a different colour from the accent in every pack; keep it so** |
| `sop.heading` | `1F4E79` | section headings |
| `sop.title` | `404040` | document title |
| `sop.caption` | `7F7F7F` | subtitle and image captions |
| `sop.body` | `000000` | body text (set explicitly on every run) |
| `sop.link` | `0563C1` | hyperlink text, single underline |

Hex without `#` here, because these go into OOXML attributes, not CSS.

## Block styles

All formatting is **direct run formatting on the `Normal` style**. The measured masters
define no custom Word styles — the generator sets fonts, sizes and colours per run;
nothing is inherited beyond the base font. Cloning a master therefore inherits only the
base font, which is why the generator exists.

| Block | Paragraph | Runs |
|---|---|---|
| **Title banner** | 1-row/2-col table, `tblLayout=fixed`, grid `236`/`10714` twips, no borders. Cell 1: `tcW=86`, shaded `sop.accent` (this cell *is* the accent bar). Cell 2 holds the text. | Title: `fonts.heading` `sop.title_pt` (20) `sop.title`, `after=40`. Subtitle: `fonts.body` `sop.subtitle_pt` (12) `sop.caption`, `before=40`. |
| **Body paragraph** | default spacing | inherited font, `sop.body`; bold spans for UI labels |
| **Heading** | `before=240`, `after=100` | `fonts.heading` `sop.heading_pt` (13.5) **bold** `sop.heading` |
| **Numbered step** | `after=80`, tab stop + hanging indent at **475 twips** | marker `"1."` + tab: **bold** `sop.accent`; body text `sop.body` |
| **Bullet** | `after=80`, tab stop + hanging indent at **403 twips** | glyph `U+2022` + tab: `sop.accent` (not bold); body text `sop.body` |
| **Screenshot** | `before=360`, `after=40`, centred | inline picture with `<a:ln w="9525">` solid `sop.image_border` (0.75 pt) **and `<wp:effectExtent l/t/r/b="19050">` on the `wp:inline`** — see below |
| **Caption** | `after=200` | `sop.caption_pt` (9.5) `sop.caption`, ***italic***, bold spans allowed |
| **Tip / note** | `before=40` | whole line **bold** `sop.body` |
| **Hyperlink** | inline in any text block | `<w:hyperlink r:id>` with an external relationship; runs `sop.link`, `<w:u val="single">` |

Step numbers auto-increment and **reset at each heading**.

## Footer

Three-cell table in the section footer. With a brand template file it is inherited from
that file; without one (`sop.template` null) `build_sop.py` synthesises it from
`sop.footer.left`, `sop.footer.centre` and a `PAGE` field on the right.

`check_conformance.py` asserts every string in `sop.footer.required_text` appears in the
footer and warns on any in `sop.footer.optional_text`. **This is the inverted gate**: it
does not assert one hard-coded organisation, it asserts the footer matches the brand the
document was built for. A Solomon footer on a neutral document fails, and so does a
missing one.

## Document pattern

Conforming SOPs follow this shape:

1. Title banner (title + one-line subtitle)
2. One short intro paragraph saying what the thing is and why the reader cares
3. `Heading` → numbered steps → screenshot → caption, repeated per section
4. Optional bold `Tip:` line
5. `Need help?` heading + the brand's `sop.help_contact`

## Screenshots

Anonymisation and provenance rules are in `screenshots.md`. The layout rule that lives
here: never exceed the 7.5" text column. `build_sop.py` scales down to 7.5" × 6.5"
automatically, never up; set `width_in` explicitly when a screenshot needs to stay
readable at a specific size.

## Screenshot borders — the clipping defect and its real fix

Word strokes a picture's `<a:ln>` outline **outside** the picture's `wp:extent` box. The only
thing that reserves room for that stroke is `<wp:effectExtent>`. python-docx never writes it,
so the ink lands outside the line box — and whenever the image sits at the top of a page,
Word clips it at the text boundary and **the top border silently disappears**.

Raising the top margin cannot fix this: it moves the boundary and the image together.

**The fix:** every `wp:inline` carrying an `a:ln` must also carry
`<wp:effectExtent l="19050" t="19050" r="19050" b="19050"/>`, inserted immediately after
`<wp:extent>`. The generator does this automatically; `fix_effect_extent.py` patches masters
that predate it. Values at or above `9525` (one line width) are accepted and left alone —
Word's own `10795` renders correctly.

**Evidence.** A master in the measured set contained a controlled pair: same document, same
margins, same spacing, same outline. img1 had `effectExtent` all-zero → top border clipped.
img2 had Word-authored `19050` → top border rendered. Pixel measurement of another master's
page 2 at 300 dpi before the fix: top edge 4/1159 red pixels, bottom edge 1159/1159. After:
1159/1159 both.

**Verify with pixels, not eyes.** `verify_borders.py` renders each page at 300 dpi and
measures the coverage of all four edges of every screenshot. A 0.75 pt line is sub-pixel at
100 dpi — a casual render will not show this defect. Full-set result after the fix: 0 clipped
edges of 51 bordered screenshots.

## Measurement history

- **Captions are italic — added 2026-09-08, after a defect.** The spec previously recorded
  caption size and colour but not italic, so the generator produced plain captions and the
  checker passed them. Measured across the set: **47 italic caption paragraphs in 17
  masters, zero plain** — the only exception was the one master the generator had built.
  Same shape as the missing `wp:effectExtent`: an incomplete measurement, so the generator
  diverged from the set and the gate validated the wrong property. Only 3 italic runs in the
  whole set are real inline emphasis, outside a caption.
- **No `keepNext` anywhere in the set.** Step/image/caption groups were once documented as
  held together with keep-with-next; they never were, and the generator does not emit it.
  Widows are managed by adjusting `width_in` and tightening wording.
- **Two banner grid variants exist** in the set (`5400/5400` and `236/10714`). Both carry
  identical `tcW` values, so they render the same; the grid is vestigial. The generator
  emits `236/10714`.

Brand-specific deviations in a particular document set belong in that brand pack's
`SKILL.md`, not here.
