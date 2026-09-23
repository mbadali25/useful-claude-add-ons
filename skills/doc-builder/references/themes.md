# Built-in themes

A theme is `assets/themes/<name>.json`: the `report` and `sop` colour keys of a brand pack
and nothing else. Resolution merges **neutral -> brand pack -> theme -> density**, so an
explicitly chosen theme wins on colour while the brand keeps its identity. `apply_overlay`
in `scripts/resolve_brand.py` strips identity keys (`sop.template`, `masters_dir`,
`assets_dir`, `specs_dir`, `footer`, `help_contact`, `report.output_dir`) from any overlay,
and ignores `fonts` and `logo` entirely - a theme cannot put one client's footer on another
client's document.

## The palettes

Measured with the WCAG 2.1 relative-luminance formula (`contrast()` in
`scripts/_test/test_themes.py`, which asserts every pair below and more on every run - the
test is authoritative, this table is a snapshot).

| Theme | Page | Band | Table head / text | Grid | Zebra | Ink:page | Head | Ink:zebra |
|---|---|---|---|---|---|---|---|---|
| `blue` | `#FFFFFF` | `#1D4ED8` | `#1E40AF` / `#FFFFFF` | `#3B5998` | `#EFF6FF` | 17.9 | 8.7 | 16.4 |
| `corporate` | `#FFFFFF` | `#001D6C` | `#002D9C` / `#FFFFFF` | `#6F6F6F` | `#F2F4F8` | 18.1 | 11.3 | 16.4 |
| `dark` | `#FFFFFF` | `#0F172A` | `#0F172A` / `#FFFFFF` | `#1E293B` | `#E2E8F0` | 17.9 | 17.9 | 14.5 |
| `high-contrast` | `#000000` | `#000000` | `#1A1A1A` / `#FFEE32` | `#FFFFFF` | `#1F1F1F` | 21.0 | 14.5 | 16.5 |
| `midnight` | `#2E3440` | `#3B4252` | `#434C5E` / `#ECEFF4` | `#6B7A94` | `#3B4252` | 10.8 | 7.5 | 8.7 |
| `modern` | `#FFFFFF` | `#18181B` | `#18181B` / `#FFFFFF` | `#52525B` | `#F4F4F5` | 17.7 | 17.7 | 16.1 |
| `professional` | `#FFFFFF` | `#1E293B` | `#000000` / `#FFFFFF` | `#000000` | `#E8ECF1` | 17.9 | 21.0 | 15.0 |
| `red` | `#FFFFFF` | `#991B1B` | `#B91C1C` / `#FFFFFF` | `#9B4545` | `#FEF2F2` | 17.9 | 6.5 | 16.3 |

Floors: 4.5:1 for every text pair (WCAG AA 1.4.3), 7:1 for `high-contrast` (AAA 1.4.6);
1.3:1 for the grid against the cell, which is a visibility floor for a non-text edge rather
than a WCAG criterion. Severity chips are not re-themed: they carry their own pastel
background, so they read the same on every page colour.

**One deliberate departure from the sources:** the Tailwind and Carbon palettes put table
borders at the 200-level (`#E2E8F0` on white is about 1.2:1), which disappears in print.
Every light theme here uses a mid-tone or black grid instead, because a visible grid on
every cell is a house rule, not a theme choice.

## Sources

- **Blue** (`blue`): https://tailwindcss.com/docs/colors (blue)
- **Corporate** (`corporate`): https://carbondesignsystem.com/elements/color/overview/ (Blue 60-100, Gray 10-100)
- **Dark** (`dark`): https://tailwindcss.com/docs/colors (slate 900/950)
- **High Contrast** (`high-contrast`): https://learn.microsoft.com/en-us/windows/apps/design/accessibility/high-contrast-themes; https://webaim.org/articles/contrast/
- **Midnight** (`midnight`): https://www.nordtheme.com/docs/colors-and-palettes
- **Modern** (`modern`): https://tailwindcss.com/docs/colors (zinc); flat neutral + single accent, as on Vercel/Linear/Stripe docs (convention, not a published spec)
- **Professional** (`professional`): https://tailwindcss.com/docs/colors (slate)
- **Red** (`red`): https://tailwindcss.com/docs/colors (red)

`high-contrast` swaps the Windows Night-sky link purple (`#8080FF`, 6.45:1 on black - under
its own AAA floor) for `#99CCFF` (about 12:1). `modern` borrows the flat-neutral-plus-one-
accent convention of Vercel, Linear and Stripe's documentation sites; none of them publishes
a token table, so its hex values are Tailwind zinc.

## Dark pages

`midnight` and `high-contrast` set `report.page` / `sop.page`. A dark page is only useful if
it survives conversion, so it is carried every way each renderer can read it:

| Path | How the page colour is kept |
|---|---|
| HTML (browser) | `body { background }` |
| HTML -> Word | `<body bgcolor>`, plus `build_report.to_word` reading the `doc-builder-page` meta and setting `Document.Background` over COM; `Options.PrintBackground` is switched on for that save only and restored in `finally` |
| HTML -> LibreOffice PDF | `<body bgcolor>` - kept (measured, soffice 26.2.5.2) |
| HTML -> LibreOffice DOCX | **dropped by LibreOffice** (measured), so `build_report.stamp_page_colour` writes `<w:background>` and `<w:displayBackgroundShape/>` back in; re-opening that DOCX renders dark again |
| SOP (python-docx) | `SopBuilder.save` writes `<w:background>` + `<w:displayBackgroundShape/>` itself |

Every body cell also carries its own fill (`report.row`). Word keeps that fill when a print
drops the page colour; LibreOffice keeps it only in the guide profile, whose cell selectors
are bare (it drops the report profile's scoped ones - see word-traps.md). Body paragraphs have
no fill at all, so **a dark-page document printed from Word with "Print background colors"
off comes out as light text on white paper** - hand over the PDF, which carries the page. **Not verified here:** the Word COM
branch (no Windows host in the session that wrote it) - the first Word run of a dark theme
should be checked by eye.

## Density

`assets/densities/compact.json` and `comfortable.json` set sizes only (`report.density`, and
the SOP point sizes and margins). They combine with any theme.

| Token | Comfortable | Compact |
|---|---|---|
| Report body | 13px | 11.5px |
| Table cell padding | 7px 10px | 3px 6px |
| Masthead title / logo | 26px / 44px | 20px / 32px |
| Guide body / margin | 11pt / 2cm | 10pt / 1.5cm |
| SOP title / heading / caption | 20 / 13.5 / 9.5pt | 17 / 12 / 8.5pt |

Compact follows the convention of Bootstrap's `.table-sm`, which halves the default cell
padding (https://getbootstrap.com/docs/5.3/content/tables/), and of Word's built-in banded
table styles, which pair a header row and zebra bands with tight padding. Neither the
Microsoft Writing Style Guide nor Google's developer documentation style guide publishes
numeric size or density guidance, so none is attributed to them. GOV.UK's type scale
(https://design-system.service.gov.uk/styles/type-scale) is why nothing here goes below 10pt
in a guide.

## The gallery

`assets/themes/gallery/` holds one sample report per theme (`<theme>.html` + `.png`), a
`professional-compact` sample, and `index.html` showing them side by side with swatches and
the flags to pass. It is generated by `scripts/build_gallery.py` from the same
`build_report.build()` the pipeline uses, against the neutral brand, and
`test_gallery_is_current` fails when a theme or the CSS changes without a rebuild:

```bash
python scripts/build_gallery.py --png   # needs a Chromium: $CHROME, PATH, or ~/.cache/ms-playwright
```
