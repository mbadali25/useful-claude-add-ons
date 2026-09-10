# Report palette

Every colour the report stylesheet emits comes from the active brand pack's
`report` block in `brand.json`, substituted as **literal hex at build time** —
see `word-traps.md` rule 1 for why `var()` must never appear in an emitted
stylesheet. The values below are the **neutral pack**
(`assets/brands/neutral/brand.json`); a brand pack overrides any key and
inherits the rest. Run `python resolve_brand.py --json` to see the merged
values actually in force.

Chosen for contrast on white **and** for staying distinguishable when printed in
greyscale, which is where most of these documents end up.

## Structure

| `brand.json` key | Neutral | Used for |
|---|---|---|
| `report.navy` | `#1F4E79` | Table header fill, `h1`/`h2` colour, masthead band, card numbers |
| `report.navy_dark` | `#143A5A` | 3px rule under the masthead band |
| `report.accent` | `#4A90C2` | 4px strip above the masthead |
| `report.org_ink` | `#A8C8E4` | Organisation name and subtitle on the masthead band |
| `report.classification` | `#8B1A13` | Classification bar; border of the handling notice |
| `report.ink` | `#1B1B1F` | Body text |
| `report.muted` | `#5C5F6B` | Subtitles, captions, footer |
| `report.grid` | `#B8BCC6` | All table borders |
| `report.zebra` | `#EEF3F8` | `tr.alt` rows, meta-table labels |
| `report.panel` | `#F6F7F9` | Lede panel and card background |
| `report.rule` | `#DCDEE5` | `h2` underline, footer rule |
| `fonts.report_stack` | `'Segoe UI',Calibri,Arial,sans-serif` | `body` font-family |

Header text on `navy` is always `#FFFFFF`; the classification bar text is white
letterspaced caps. Those two are fixed in the stylesheet because every sensible
brand's header fill is dark.

## Masthead

Four stacked table rows — tables with cell shading, never coloured `<div>`s,
which render as bare paragraphs in the DOCX:

| Row | Class | Colour key | What it is |
|---|---|---|---|
| 1 | `mast-strip` | `accent` | 4px accent rule |
| 2 | `mast-band` | `navy` | Organisation (small letterspaced caps in `org_ink`), 26px white title, subtitle |
| 3 | `mast-rule` | `navy_dark` | 3px darker rule |
| 4 | `mast-cls` | `classification` | Classification bar |

## Severity — chip background and text

Under `report.severity`, each value is `[chip background, text colour]`. Brand
packs normally leave these alone: severity is a shared vocabulary, not a brand.

| Severity | Text | Chip background | Meaning |
|---|---|---|---|
| Critical | `#A01B12` | `#FDE8E6` | Act now; exploited or trivially exploitable |
| High | `#9A3412` | `#FFEDD5` | Act this week |
| Medium | `#8A6100` | `#FDF3D7` | Scheduled remediation |
| Low | `#1C6B3F` | `#E3F4EA` | Note and move on |
| Info | `#2F4B7C` | `#E8EFF8` | Context, no action |
| Unverified | `#5C5F6B` | `#EDEEF1` | **Could not be checked — not the same as Pass** |

`Unverified` earns its own row deliberately. **A check that could not run is not
a check that passed**, and a report that renders the two identically is lying by
omission. If a probe failed, say so in its own severity rather than letting it
inherit the colour of success.

## Writing the chips

One class per element, every declaration repeated — `word-traps.md` rule 4.
Grouped selectors are the way to keep that manageable, and are what
`build_report.py` emits:

```css
.chip-critical, .chip-high, .chip-medium, .chip-low, .chip-info, .chip-unverified {
  display:inline-block; padding:2px 8px; font-weight:700; font-size:11px;
  white-space:nowrap;
}
.chip-critical   { background:#FDE8E6; color:#A01B12; }
.chip-high       { background:#FFEDD5; color:#9A3412; }
.chip-medium     { background:#FDF3D7; color:#8A6100; }
.chip-low        { background:#E3F4EA; color:#1C6B3F; }
.chip-info       { background:#E8EFF8; color:#2F4B7C; }
.chip-unverified { background:#EDEEF1; color:#5C5F6B; }
```

Note what that is doing: the shared declarations live in a **grouped selector**,
not in a base class the element also carries. `class="chip chip-critical"` would
apply neither rule.

## Adding a brand

Create `skills/<name>-doc-builder/assets/brand.json` with a `name` and only the
keys that differ. Check the result against a dark header (`navy`) and a
greyscale print before shipping — a light `navy` makes the white masthead text
unreadable, and nothing in the toolchain checks contrast for you.
